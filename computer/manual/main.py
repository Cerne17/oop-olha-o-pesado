"""
computer.manual.main — standalone manual control entry point (legacy).

Prefer the unified entry point:
    python -m computer.main --phase 1   # socat virtual ports
    python -m computer.main --phase 2   # physical robot BT

This module is kept for direct invocation convenience:
    python -m computer.manual.main
"""

from __future__ import annotations

import signal
import sys
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
ROBOT_TRANSPORT = "serial"
ROBOT_PORT      = "/tmp/robot-computer"   # socat virtual port (Phase 1)
# ROBOT_PORT    = "/dev/cu.RobotESP32-SerialPort"  # physical BT (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

from computer.communication.transport  import SerialTransport, RFCOMMTransport
from computer.communication.robot_sender import RobotSender
from .keyboard import KeyboardController


def _build_transport():
    if ROBOT_TRANSPORT == "serial":
        return SerialTransport(ROBOT_PORT)
    raise ValueError(f"Unknown ROBOT_TRANSPORT: {ROBOT_TRANSPORT!r}")


def main() -> None:
    transport = _build_transport()
    sender    = RobotSender(transport)
    keyboard  = KeyboardController()

    keyboard.add_control_observer(sender)

    def _shutdown(sig, frame):
        print("\n[MANUAL] Shutting down…")
        sender.stop()
        keyboard.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sender.start()
    keyboard.start()
    print("[MANUAL] Running — arrow keys to move, ESC or Ctrl+C to stop")

    while not keyboard.is_esc_pressed:
        time.sleep(0.1)

    _shutdown(None, None)


if __name__ == "__main__":
    main()
