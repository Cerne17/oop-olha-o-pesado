"""
computer.main — entry point for autonomous vision mode.

Wires: CamReceiver → VisionProcessor → BlobFollowerStrategy → RobotSender.

Run from the repository root:
    python -m computer.main

Or after `pip install -e .`:
    robot-vision
"""

from __future__ import annotations

import signal
import sys
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
CAM_TRANSPORT   = "serial"
CAM_PORT        = "/tmp/cam-computer"     # socat virtual port (Phase 1)
# CAM_PORT      = "/dev/cu.RobotCAM-SerialPort"  # physical BT (Phase 3)

ROBOT_TRANSPORT = "serial"
ROBOT_PORT      = "/tmp/robot-computer"  # socat virtual port (Phase 1)
# ROBOT_PORT    = "/dev/cu.RobotESP32-SerialPort"  # physical BT (Phase 2/3)

FRAME_WIDTH  = 320
SHOW_PREVIEW = True
# ─────────────────────────────────────────────────────────────────────────────

from computer.communication.transport   import SerialTransport, RFCOMMTransport
from computer.communication.cam_receiver  import CamReceiver
from computer.communication.robot_sender  import RobotSender
from computer.vision.processor            import VisionProcessor
from computer.vision.strategy             import BlobFollowerStrategy
from computer.vision.detectors            import ColourBlobDetector


def _build_transport(kind: str, port: str):
    if kind == "serial":
        return SerialTransport(port)
    raise ValueError(f"Unknown transport: {kind!r}")


def main() -> None:
    cam_transport   = _build_transport(CAM_TRANSPORT,   CAM_PORT)
    robot_transport = _build_transport(ROBOT_TRANSPORT, ROBOT_PORT)

    cam_receiver = CamReceiver(cam_transport)
    processor    = VisionProcessor(show_preview=SHOW_PREVIEW)
    strategy     = BlobFollowerStrategy(
        frame_width = FRAME_WIDTH,
        steer_gain  = 90.0,
        base_speed  = 0.5,
    )
    robot_sender = RobotSender(robot_transport)

    processor.add_detector(ColourBlobDetector(
        label    = "target",
        hsv_low  = (0,   120,  70),
        hsv_high = (10,  255, 255),
        min_area = 400,
    ))

    # Wire observer graph
    cam_receiver.add_frame_observer(processor)
    processor.add_result_observer(strategy)
    strategy.add_control_observer(robot_sender)

    def _shutdown(sig, frame):
        print("\n[MAIN] Shutting down…")
        cam_receiver.stop()
        processor.stop()
        robot_sender.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    robot_sender.start()
    processor.start()
    cam_receiver.start()
    print("[MAIN] Running — press Ctrl+C to stop")

    while True:
        time.sleep(5.0)
        cam  = cam_receiver.stats()
        rob  = robot_sender.stats()
        print(
            f"[STATS] rx_frames={cam['rx_frames']} images={cam['rx_images']} "
            f"pending={cam['pending']} tx_frames={rob['tx_frames']}"
        )


if __name__ == "__main__":
    main()
