"""
emulator.robot_emulator -- RobotEmulator orchestrator.

Accepts one TCP connection, then runs four daemon threads:
  rx-loop      -- decode CONTROL_REF frames, send ACK; echo HEARTBEAT
  hb-loop      -- send HEARTBEAT every 1 s
  control-loop -- call SimulatedRobot.update() at CONTROL_HZ (50 Hz)
  display-loop -- print one-line status every 500 ms

Spec reference: emulator/SPEC.md §4, §6.
"""

from __future__ import annotations

import sys
import threading
import time

from protocol        import FrameDecoder, FrameEncoder, MSG_CONTROL_REF, MSG_ACK, MSG_HEARTBEAT
from tcp_link        import TcpLink
from simulated_robot import SimulatedRobot, CONTROL_HZ


class RobotEmulator:
    def __init__(self, port: int = 5001, verbose: bool = False) -> None:
        self._port    = port
        self._verbose = verbose

        self._link    = TcpLink(port, verbose=verbose)
        self._encoder = FrameEncoder()
        self._decoder = FrameDecoder()
        self._robot   = SimulatedRobot()

        self._seq       = 0
        self._seq_lock  = threading.Lock()
        self._tx_count  = 0
        self._rx_count  = 0

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
        self._link.send(data)
        self._tx_count += 1

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def run(self) -> None:
        """
        Open the server socket, then loop: accept -> spawn threads -> wait for
        disconnect -> accept again. Blocks until stop() is called.
        """
        self._link.listen()
        print(f"[EMU] Robot emulator starting -- listening on 0.0.0.0:{self._port}")

        while not self._stop_event.is_set():
            print("[EMU] Waiting for computer to connect...")
            try:
                addr = self._link.accept()
            except OSError:
                break
            print(f"[EMU] Computer connected from {addr}")
            print("[EMU] All loops running. Ctrl+C to stop.")

            self._stop_event.clear()
            self._threads = [
                threading.Thread(target=self._rx_loop,      name="emu-rx",      daemon=True),
                threading.Thread(target=self._hb_loop,      name="emu-hb",      daemon=True),
                threading.Thread(target=self._control_loop, name="emu-control", daemon=True),
                threading.Thread(target=self._display_loop, name="emu-display", daemon=True),
            ]
            for t in self._threads:
                t.start()

            # Wait until the connection drops or stop() is called
            while not self._stop_event.is_set() and self._link.is_connected:
                time.sleep(0.1)

            # Connection lost -- stop threads, clean up, accept again
            if not self._stop_event.is_set():
                print("\n[EMU] Connection lost -- waiting for reconnect")
            self._stop_event.set()
            for t in self._threads:
                t.join(timeout=2.0)
            self._link.close_conn()
            self._stop_event.clear()   # ready for next accept()

        self._link.close()
        print("[EMU] Emulator stopped")

    def stop(self) -> None:
        """Signal all loops to exit and close the server socket."""
        self._stop_event.set()
        self._link.close()

    # -------------------------------------------------------------------------
    # rx-loop
    # -------------------------------------------------------------------------

    def _rx_loop(self) -> None:
        last_hb_tx = 0.0

        while not self._stop_event.is_set() and self._link.is_connected:
            data = self._link.recv()
            if not data:
                time.sleep(0.005)
                continue

            for frame in self._decoder.feed(data):
                self._rx_count += 1

                if not frame.crc_ok:
                    ack = self._encoder.build_ack(self._next_seq(), frame.seq_num, status=1)
                    self._send(ack)
                    if self._verbose:
                        print(f"[RX] CRC error seq={frame.seq_num}")
                    continue

                t = frame.msg_type

                if t == MSG_CONTROL_REF:
                    if len(frame.payload) >= 8:
                        angle_deg, speed_ref = frame.decode_control_ref()
                        self._robot.set_ref(angle_deg, speed_ref)
                        ack = self._encoder.build_ack(self._next_seq(), frame.seq_num, status=0)
                        self._send(ack)
                        if self._verbose:
                            print(f"[RX] CONTROL_REF angle={angle_deg:.1f} speed={speed_ref:+.2f}")

                elif t == MSG_HEARTBEAT:
                    now = time.monotonic()
                    if now - last_hb_tx >= 1.0:
                        hb = self._encoder.build_heartbeat(self._next_seq())
                        self._send(hb)
                        last_hb_tx = now
                    if self._verbose:
                        print("[RX] HEARTBEAT")

                elif t == MSG_ACK:
                    if self._verbose:
                        acked, status = frame.decode_ack()
                        print(f"[RX] ACK acked_seq={acked} status={status}")

                else:
                    ack = self._encoder.build_ack(self._next_seq(), frame.seq_num, status=2)
                    self._send(ack)
                    if self._verbose:
                        print(f"[RX] Unknown type=0x{t:02X}")

    # -------------------------------------------------------------------------
    # hb-loop
    # -------------------------------------------------------------------------

    def _hb_loop(self) -> None:
        while not self._stop_event.is_set() and self._link.is_connected:
            hb = self._encoder.build_heartbeat(self._next_seq())
            self._send(hb)
            if self._verbose:
                print(f"[HB] HEARTBEAT sent")
            time.sleep(1.0)

    # -------------------------------------------------------------------------
    # control-loop
    # -------------------------------------------------------------------------

    def _control_loop(self) -> None:
        interval = 1.0 / CONTROL_HZ
        while not self._stop_event.is_set() and self._link.is_connected:
            self._robot.update()
            time.sleep(interval)

    # -------------------------------------------------------------------------
    # display-loop
    # -------------------------------------------------------------------------

    def _display_loop(self) -> None:
        while not self._stop_event.is_set() and self._link.is_connected:
            s     = self._robot.snapshot()
            speed = self._robot.speed_mps
            line  = (
                f"\r[EMU] angle={s['angle_deg']:+7.1f} deg"
                f"  speed={s['speed_ref']:+.2f}"
                f"  L={s['current_left']:+.2f}"
                f"  R={s['current_right']:+.2f}"
                f"  speed_mps={speed:+.2f} m/s"
                f"  tx={self._tx_count}"
                f"  rx={self._rx_count}   "
            )
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.5)
