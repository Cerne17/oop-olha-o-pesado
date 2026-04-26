"""
emulator.emulator — EmulatorApp, the main thread orchestrator.
"""

from __future__ import annotations

import math
import sys
import threading
import time

from protocol import (
    FrameDecoder, FrameEncoder,
    MSG_DIRECTION_REF, MSG_ACK, MSG_HEARTBEAT,
)
from serial_link    import SerialLink
from simulated_robot import SimulatedRobot, CONTROL_HZ
from image_generator import ImageGenerator
from keyboard_input  import KeyboardInput

CHUNK_SIZE = 512


class EmulatorApp:
    def __init__(
        self,
        port:      str        = '/tmp/robot-emulator',
        mode:      str        = 'blob',
        image_dir: str | None = None,
        fps:       float      = 6.0,
        verbose:   bool       = False,
    ) -> None:
        self._port           = port
        self._fps            = fps
        self._verbose        = verbose
        self._image_interval = 1.0 / fps

        self._serial    = SerialLink(port, verbose=verbose)
        self._encoder   = FrameEncoder()
        self._decoder   = FrameDecoder()
        self._robot     = SimulatedRobot()
        self._keyboard  = KeyboardInput()
        self._image_gen = ImageGenerator(mode=mode, image_dir=image_dir)

        self._seq       = 0
        self._seq_lock  = threading.Lock()
        self._tx_count  = 0
        self._rx_count  = 0
        self._frame_id  = 0

        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    # -------------------------------------------------------------------------
    # Sequence number
    # -------------------------------------------------------------------------

    def _next_seq(self) -> int:
        with self._seq_lock:
            s = self._seq
            self._seq = (self._seq + 1) & 0xFFFF
            return s

    def _send(self, data: bytes) -> None:
        self._serial.send(data)
        self._tx_count += 1

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        print(f"[EMU] Opening {self._port} …")
        self._serial.open()
        print(f"[EMU] Serial port open. Starting loops.")
        print(f"[EMU] Arrow keys: ↑ forward | ↓ backward | ← left | → right")
        print(f"[EMU] Combinations supported (e.g. ↑+→ = 45°).  ESC or Ctrl+C to quit.")

        self._keyboard.start()
        self._stop_event.clear()

        self._threads = [
            threading.Thread(target=self._rx_loop,        name='rx',        daemon=True),
            threading.Thread(target=self._image_loop,     name='image',     daemon=True),
            threading.Thread(target=self._heartbeat_loop, name='heartbeat', daemon=True),
            threading.Thread(target=self._control_loop,   name='control',   daemon=True),
            threading.Thread(target=self._keyboard_loop,  name='keyboard',  daemon=True),
            threading.Thread(target=self._display_loop,   name='display',   daemon=True),
        ]
        for t in self._threads:
            t.start()
        print("[EMU] Emulator started")

    def stop(self) -> None:
        self._stop_event.set()
        self._keyboard.stop()
        for t in self._threads:
            t.join(timeout=3.0)
        self._serial.close()
        print("[EMU] Emulator stopped")

    @property
    def is_esc_pressed(self) -> bool:
        return self._keyboard.is_esc_pressed

    # -------------------------------------------------------------------------
    # Threads
    # -------------------------------------------------------------------------

    def _rx_loop(self) -> None:
        while not self._stop_event.is_set():
            data = self._serial.recv(256)
            if not data:
                continue
            for frame in self._decoder.feed(data):
                self._rx_count += 1
                if not frame.crc_ok:
                    if self._verbose:
                        print(f"[EMU] CRC error seq={frame.seq_num}")
                    continue
                t = frame.msg_type
                if t == MSG_DIRECTION_REF:
                    angle, stop = frame.decode_direction_ref()
                    self._robot.set_ref(angle, stop)
                    if self._verbose:
                        print(f"[EMU] RX DIRECTION_REF angle={angle:.1f} stop={int(stop)}")
                elif t == MSG_ACK:
                    acked, status = frame.decode_ack()
                    if self._verbose:
                        print(f"[EMU] RX ACK seq={acked} status={status}")
                elif t == MSG_HEARTBEAT:
                    if self._verbose:
                        print(f"[EMU] RX HEARTBEAT")
                else:
                    if self._verbose:
                        print(f"[EMU] RX unknown type=0x{t:02X}")

    def _image_loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                jpeg = self._image_gen.next_jpeg()
            except Exception as exc:
                print(f"[EMU] Image error: {exc}")
                time.sleep(self._image_interval)
                continue

            total  = len(jpeg)
            chunks = math.ceil(total / CHUNK_SIZE)
            for i in range(chunks):
                if self._stop_event.is_set():
                    break
                offset = i * CHUNK_SIZE
                seq    = self._next_seq()
                frame  = self._encoder.build_image_chunk(
                    seq, self._frame_id, i, chunks, total,
                    jpeg[offset: offset + CHUNK_SIZE],
                )
                self._send(frame)
                if self._verbose:
                    print(f"[EMU] TX IMAGE_CHUNK frame={self._frame_id} "
                          f"chunk={i}/{chunks} seq={seq}")
                time.sleep(0)   # yield

            self._frame_id = (self._frame_id + 1) & 0xFFFF
            elapsed   = time.monotonic() - start
            remaining = self._image_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            seq   = self._next_seq()
            frame = self._encoder.build_heartbeat(seq)
            self._send(frame)
            if self._verbose:
                print(f"[EMU] TX HEARTBEAT seq={seq}")
            time.sleep(1.0)

    def _control_loop(self) -> None:
        interval = 1.0 / CONTROL_HZ
        while not self._stop_event.is_set():
            self._robot.update()
            time.sleep(interval)

    def _keyboard_loop(self) -> None:
        interval = 1.0 / 20.0   # 20 Hz
        while not self._stop_event.is_set():
            angle, stop = self._keyboard.get_direction()
            self._robot.set_ref(angle, stop)
            seq   = self._next_seq()
            frame = self._encoder.build_direction_ref(seq, angle, stop)
            self._send(frame)
            if self._verbose:
                print(f"[EMU] TX DIRECTION_REF angle={angle:.1f} stop={int(stop)}")
            time.sleep(interval)

    def _display_loop(self) -> None:
        while not self._stop_event.is_set():
            s     = self._robot.snapshot()
            speed = self._robot.speed_mps
            line  = (
                f"\r[EMU] angle={s['angle_deg']:+7.1f}°  stop={int(s['stop'])}"
                f"  L={s['current_left']:+.2f}  R={s['current_right']:+.2f}"
                f"  speed={speed:+.2f} m/s"
                f"  tx={self._tx_count}  rx={self._rx_count}   "
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.5)
