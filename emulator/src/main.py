"""
emulator.main -- CLI entry point for the robot emulator.

Run from the emulator directory:
    python src/main.py [--port 5001] [--verbose]

Then in a second terminal:
    python -m computer.main --phase 1
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

# Ensure src/ is on the path when run as `python src/main.py`
sys.path.insert(0, os.path.dirname(__file__))

from robot_emulator import RobotEmulator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Robot Emulator -- TCP loopback mode (Phase 1)"
    )
    parser.add_argument(
        "--port", type=int, default=5001,
        help="TCP port to listen on (default: 5001)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Log every sent/received frame",
    )
    args = parser.parse_args()

    emulator = RobotEmulator(port=args.port, verbose=args.verbose)

    def _shutdown(sig, frame):
        print("\n[MAIN] Shutting down...")
        emulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    emulator.run()  # blocks until stop() is called


if __name__ == "__main__":
    main()
