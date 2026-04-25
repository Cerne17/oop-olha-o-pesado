"""
computer.communication.cam_receiver — manages Link A (Computer ↔ CAM).

Receives IMAGE_CHUNK frames, assembles them into Frames, notifies observers,
and sends ACK back to the CAM after each complete frame.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from computer.types.observers import FrameObservable
from computer.types.transport import Transport
from .protocol import (
    CamMsg, FrameDecoder, FrameEncoder, ImageChunkHeader,
)
from .assembler import ImageAssembler


class CamReceiver(FrameObservable):
    """
    Parameters
    ----------
    transport : Transport — constructed but not yet connected
    reconnect : bool      — retry on link loss
    """

    def __init__(self,
                 transport: Transport,
                 reconnect: bool = True) -> None:
        super().__init__()
        self._transport = transport
        self._reconnect = reconnect

        self._decoder   = FrameDecoder()
        self._encoder   = FrameEncoder()
        self._assembler = ImageAssembler(frame_timeout_s=2.0)

        self._seq        = 0
        self._seq_lock   = threading.Lock()
        self._stop_event = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None

        self._last_heartbeat_rx  = 0.0
        self._last_heartbeat_tx  = 0.0
        self._rx_frames          = 0
        self._rx_images          = 0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        self._connect()
        self._stop_event.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="cam-rx", daemon=True
        )
        self._rx_thread.start()
        print("[CAM] Receiver started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._rx_thread:
            self._rx_thread.join(timeout=3.0)
        self._transport.disconnect()
        print("[CAM] Receiver stopped")

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
                self._last_heartbeat_rx = time.monotonic()
                return
            except ConnectionError as exc:
                print(f"[CAM] Connect failed: {exc} — retrying in 3 s")
                time.sleep(3.0)

    def _rx_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._transport.is_connected():
                if self._reconnect:
                    print("[CAM] Connection lost — reconnecting")
                    self._connect()
                else:
                    break

            try:
                raw = self._transport.receive_available(max_bytes=4096)
            except ConnectionError as exc:
                print(f"[CAM] Receive error: {exc}")
                if self._reconnect:
                    self._connect()
                continue

            if not raw:
                # Heartbeat watchdog
                if time.monotonic() - self._last_heartbeat_rx > 5.0:
                    print("[CAM] Warning: no HEARTBEAT from CAM in 5 s")
                    self._last_heartbeat_rx = time.monotonic()  # suppress repeat
                time.sleep(0.005)
                continue

            for frame in self._decoder.feed(raw):
                self._rx_frames += 1

                if not frame.crc_ok:
                    seq = self._next_seq()
                    self._transport.send(
                        self._encoder.build_ack(seq, frame.seq_num, status=1)
                    )
                    continue

                t = frame.msg_type

                if t == CamMsg.IMAGE_CHUNK:
                    if len(frame.payload) >= ImageChunkHeader.SIZE:
                        header    = ImageChunkHeader.unpack(frame.payload)
                        jpeg_data = frame.payload[ImageChunkHeader.SIZE:]
                        result    = self._assembler.on_chunk(header, jpeg_data)
                        if result is not None:
                            self._rx_images += 1
                            self._notify_frame(result)
                            seq = self._next_seq()
                            self._transport.send(
                                self._encoder.build_ack(seq, frame.seq_num, status=0)
                            )

                elif t == CamMsg.HEARTBEAT:
                    self._last_heartbeat_rx = time.monotonic()
                    now = time.monotonic()
                    if now - self._last_heartbeat_tx >= 1.0:
                        seq = self._next_seq()
                        self._transport.send(
                            self._encoder.build_heartbeat(seq, CamMsg.HEARTBEAT)
                        )
                        self._last_heartbeat_tx = now

                else:
                    seq = self._next_seq()
                    self._transport.send(
                        self._encoder.build_ack(seq, frame.seq_num, status=2)
                    )

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "rx_frames": self._rx_frames,
            "rx_images": self._rx_images,
            "pending":   self._assembler.pending_frame_count,
        }
