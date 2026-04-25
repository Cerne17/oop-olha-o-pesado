"""
computer.communication.robot_sender — manages Link B (Computer ↔ Robot).

Consumes ControlSignal events (newest-wins queue) and sends CONTROL_REF frames
to the robot at up to max_rate_hz.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from computer.types.observers import ControlObserver
from computer.types.signals   import ControlSignal
from computer.types.transport import Transport
from .protocol import ControlRefPayload, FrameEncoder, RobotMsg


class RobotSender(ControlObserver):
    """
    Parameters
    ----------
    transport   : Transport — constructed but not yet connected
    max_rate_hz : float     — maximum CONTROL_REF send rate
    reconnect   : bool      — retry on link loss
    """

    def __init__(self,
                 transport:   Transport,
                 max_rate_hz: float = 20.0,
                 reconnect:   bool  = True) -> None:
        self._transport   = transport
        self._interval    = 1.0 / max_rate_hz
        self._reconnect   = reconnect

        self._encoder     = FrameEncoder()
        self._cmd_queue: queue.Queue[ControlSignal] = queue.Queue(maxsize=1)

        self._seq        = 0
        self._seq_lock   = threading.Lock()
        self._stop_event = threading.Event()
        self._tx_thread: Optional[threading.Thread] = None

        self._last_heartbeat = 0.0
        self._tx_frames      = 0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        self._connect()
        self._stop_event.clear()
        self._tx_thread = threading.Thread(
            target=self._tx_loop, name="robot-tx", daemon=True
        )
        self._tx_thread.start()
        print("[ROBOT] Sender started")

    def stop(self) -> None:
        self._stop_event.set()
        # Unblock the queue.get() in _tx_loop
        try:
            self._cmd_queue.put_nowait(ControlSignal.stopped())
        except queue.Full:
            pass
        if self._tx_thread:
            self._tx_thread.join(timeout=3.0)
        self._transport.disconnect()
        print("[ROBOT] Sender stopped")

    # -------------------------------------------------------------------------
    # ControlObserver
    # -------------------------------------------------------------------------

    def on_control(self, signal: ControlSignal) -> None:
        """Enqueue signal (newest wins — drop old entry if full)."""
        try:
            self._cmd_queue.put_nowait(signal)
        except queue.Full:
            try:
                self._cmd_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._cmd_queue.put_nowait(signal)
            except queue.Full:
                pass

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _next_seq(self) -> int:
        with self._seq_lock:
            s = self._seq
            self._seq = (self._seq + 1) & 0xFFFF
            return s

    def _connect(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._transport.connect()
                self._last_heartbeat = time.monotonic()
                return
            except ConnectionError as exc:
                print(f"[ROBOT] Connect failed: {exc} — retrying in 3 s")
                time.sleep(3.0)

    def _tx_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._transport.is_connected():
                if self._reconnect:
                    print("[ROBOT] Connection lost — reconnecting")
                    self._connect()
                else:
                    break

            try:
                signal = self._cmd_queue.get(timeout=self._interval)
            except queue.Empty:
                signal = None

            if self._stop_event.is_set():
                break

            try:
                if signal is not None:
                    payload = ControlRefPayload(signal.angle_deg, signal.speed_ref)
                    frame   = self._encoder.build_control_ref(self._next_seq(), payload)
                    self._transport.send(frame)
                    self._tx_frames += 1

                # Heartbeat if no CONTROL_REF was sent recently
                now = time.monotonic()
                if now - self._last_heartbeat >= 1.0:
                    hb = self._encoder.build_heartbeat(
                        self._next_seq(), RobotMsg.HEARTBEAT
                    )
                    self._transport.send(hb)
                    self._last_heartbeat = now

            except ConnectionError as exc:
                print(f"[ROBOT] Send error: {exc}")
                if self._reconnect:
                    self._connect()

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    def stats(self) -> dict:
        return {"tx_frames": self._tx_frames}
