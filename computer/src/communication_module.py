"""
communication_module.py — Top-level orchestrator on the computer side.

Wires together:
  Transport → FrameDecoder → [ImageAssembler | TelemetryCallback | AckHandler]
                           ← FrameEncoder ← RobotController

Two threads are spawned:
  receive_loop  — reads bytes from the transport, feeds the decoder,
                  dispatches decoded frames to the right subsystem.
  send_loop     — drains RobotController's command queue and transmits
                  WheelControl frames.

Usage:

    transport = SerialTransport("/dev/cu.RobotESP32-xxx")
    module    = CommunicationModule(transport)
    module.start()
    # ... main thread can now do other work or just wait ...
    module.stop()
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from protocol  import (FrameDecoder, FrameEncoder, MsgType,
                       TelemetryPayload, ImageChunkHeader, AckPayload)
from transport import BluetoothTransport
from image_assembler  import ImageAssembler
from image_processor  import ImageProcessor
from robot_controller import RobotController


class CommunicationModule:
    """
    Ties all components together and manages the two I/O threads.

    Parameters
    ----------
    transport        : BluetoothTransport — already-constructed transport (not yet connected)
    image_processor  : ImageProcessor     — configured with detectors
    robot_controller : RobotController    — provides next_command()
    send_interval_s  : float              — how often to poll for a new wheel command (s)
    reconnect        : bool               — attempt automatic reconnect on disconnect
    """

    def __init__(self,
                 transport:        BluetoothTransport,
                 image_processor:  ImageProcessor,
                 robot_controller: RobotController,
                 send_interval_s:  float = 0.05,
                 reconnect:        bool  = True) -> None:

        self._transport  = transport
        self._ip         = image_processor
        self._rc         = robot_controller
        self._send_interval = send_interval_s
        self._reconnect  = reconnect

        self._decoder    = FrameDecoder()
        self._encoder    = FrameEncoder()
        self._assembler  = ImageAssembler(frame_timeout_s=2.0)

        # Wire assembler → image processor
        self._assembler.on_frame_ready(self._ip.push_frame)

        # Wire image processor → robot controller
        self._ip.on_result(self._rc.on_frame_result)

        self._stop_event = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._tx_thread: Optional[threading.Thread] = None

        # Stats
        self._rx_frames   = 0
        self._tx_frames   = 0
        self._rx_images   = 0
        self._rx_telemetry = 0
        self._last_heartbeat = 0.0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def start(self) -> None:
        """Connect and start I/O threads.  Blocks until connected."""
        self._connect()

        self._ip.start()

        self._stop_event.clear()
        self._rx_thread = threading.Thread(
            target=self._receive_loop, name="bt-rx", daemon=True
        )
        self._tx_thread = threading.Thread(
            target=self._send_loop, name="bt-tx", daemon=True
        )
        self._rx_thread.start()
        self._tx_thread.start()
        print("[COMM] Communication module started")

    def stop(self) -> None:
        """Signal all threads to stop and disconnect."""
        self._stop_event.set()
        self._rc.stop()
        self._ip.stop()
        if self._rx_thread:
            self._rx_thread.join(timeout=3.0)
        if self._tx_thread:
            self._tx_thread.join(timeout=3.0)
        self._transport.disconnect()
        print("[COMM] Communication module stopped")

    # -------------------------------------------------------------------------
    # Connection management
    # -------------------------------------------------------------------------
    def _connect(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._transport.connect()
                self._last_heartbeat = time.monotonic()
                return
            except ConnectionError as exc:
                print(f"[COMM] Connect failed: {exc} — retrying in 3 s")
                time.sleep(3.0)

    # -------------------------------------------------------------------------
    # Receive loop
    # -------------------------------------------------------------------------
    def _receive_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._transport.is_connected():
                if self._reconnect:
                    print("[COMM] Connection lost — reconnecting")
                    self._connect()
                else:
                    break

            raw = self._transport.receive_available(max_bytes=2048)
            if not raw:
                time.sleep(0.005)
                continue

            frames = self._decoder.feed(raw)
            for frame in frames:
                self._rx_frames += 1
                self._dispatch(frame.msg_type, frame.seq_num, frame.payload)

        print("[COMM] Receive loop ended")

    def _dispatch(self, msg_type: MsgType, seq: int, payload: bytes) -> None:
        if msg_type == MsgType.IMAGE_CHUNK:
            self._handle_image_chunk(payload)
        elif msg_type == MsgType.TELEMETRY:
            self._handle_telemetry(payload)
        elif msg_type == MsgType.ACK:
            self._handle_ack(payload)
        elif msg_type == MsgType.HEARTBEAT:
            self._last_heartbeat = time.monotonic()
        else:
            print(f"[COMM] Unknown message type: {msg_type!r}")

    def _handle_image_chunk(self, payload: bytes) -> None:
        hdr_size = ImageChunkHeader.SIZE
        if len(payload) < hdr_size:
            return
        header     = ImageChunkHeader.unpack(payload[:hdr_size])
        chunk_data = payload[hdr_size:]
        self._assembler.on_chunk(header, chunk_data)
        self._rx_images += 1

    def _handle_telemetry(self, payload: bytes) -> None:
        if len(payload) < TelemetryPayload.SIZE:
            return
        t = TelemetryPayload.unpack(payload)
        self._rc.on_telemetry(t.left_rpm, t.right_rpm,
                              t.speed_mps, t.timestamp_ms)
        self._rx_telemetry += 1

    def _handle_ack(self, payload: bytes) -> None:
        if len(payload) < AckPayload.SIZE:
            return
        ack = AckPayload.unpack(payload)
        if ack.status != 0:
            print(f"[COMM] Remote NACK for seq {ack.acked_seq} (status {ack.status})")

    # -------------------------------------------------------------------------
    # Send loop
    # -------------------------------------------------------------------------
    def _send_loop(self) -> None:
        while not self._stop_event.is_set():
            cmd = self._rc.next_command(timeout=self._send_interval)
            if cmd is None:
                continue
            if not self._transport.is_connected():
                continue

            frame = self._encoder.encode_wheel_control(cmd.left, cmd.right)
            try:
                self._transport.send(frame)
                self._tx_frames += 1
            except ConnectionError as exc:
                print(f"[COMM] Send error: {exc}")

        print("[COMM] Send loop ended")

    # -------------------------------------------------------------------------
    # Stats / diagnostics
    # -------------------------------------------------------------------------
    def stats(self) -> dict:
        return {
            "rx_frames":    self._rx_frames,
            "tx_frames":    self._tx_frames,
            "rx_images":    self._rx_images,
            "rx_telemetry": self._rx_telemetry,
            "pending_frames": self._assembler.pending_frame_count,
            "heartbeat_age_s": time.monotonic() - self._last_heartbeat,
            "speed_mps":    self._rc.speed_mps,
            "left_rpm":     self._rc.left_rpm,
            "right_rpm":    self._rc.right_rpm,
        }
