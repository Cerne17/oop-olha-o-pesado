"""
computer.main -- unified entry point for all development phases.

Usage:
    python -m computer.main --phase 1   # manual control, socat virtual ports
    python -m computer.main --phase 2   # manual control, physical robot over BT
    python -m computer.main --phase 3   # autonomous vision, physical robot + CAM over BT

Or after `pip install -e .`:
    robot-vision --phase <1|2|3>
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Per-phase configuration                                                      #
# --------------------------------------------------------------------------- #

@dataclass
class PhaseConfig:
    robot_port:      str
    robot_transport: str        = "serial"  # "serial" | "rfcomm"
    cam_port:        str | None = None
    cam_transport:   str | None = None
    # Phase 3 vision tuning
    frame_width:  int   = 320
    show_preview: bool  = True
    hsv_low:      tuple[int, int, int] = field(default_factory=lambda: (0,  120,  70))
    hsv_high:     tuple[int, int, int] = field(default_factory=lambda: (10, 255, 255))
    min_area:     int   = 400
    steer_gain:   float = 90.0
    base_speed:   float = 0.5


# Phase 1 -- manual, socat virtual ports (no hardware)
# Phase 2 -- manual, physical robot over BT
# Phase 3 -- autonomous vision, physical robot + CAM over BT
PHASE_CONFIGS: dict[int, PhaseConfig] = {
    1: PhaseConfig(
        robot_port = "/tmp/robot-computer",
        cam_port   = None,
    ),
    2: PhaseConfig(
        robot_port = "/dev/cu.RobotESP32-SerialPort",  # macOS BT serial
        # robot_port = "/dev/rfcomm0",                 # Linux RFCOMM
        cam_port   = None,
    ),
    3: PhaseConfig(
        robot_port = "/dev/cu.RobotESP32-SerialPort",
        cam_port   = "/dev/cu.RobotCAM-SerialPort",
        # robot_port = "/dev/rfcomm0",                 # Linux RFCOMM
        # cam_port   = "/dev/rfcomm1",
    ),
}


# --------------------------------------------------------------------------- #
# Transport factory                                                            #
# --------------------------------------------------------------------------- #

def _make_transport(kind: str, port: str):
    from computer.communication.transport import SerialTransport, RFCOMMTransport
    if kind == "serial":
        return SerialTransport(port)
    if kind == "rfcomm":
        return RFCOMMTransport(port)
    raise ValueError(f"Unknown transport kind: {kind!r}")


# --------------------------------------------------------------------------- #
# Phase 1 / 2 -- manual keyboard control                                      #
# --------------------------------------------------------------------------- #

def _run_manual(cfg: PhaseConfig, phase: int) -> None:
    from computer.communication.robot_sender import RobotSender
    from computer.manual.keyboard import KeyboardController

    transport = _make_transport(cfg.robot_transport, cfg.robot_port)
    sender    = RobotSender(transport)
    keyboard  = KeyboardController()

    keyboard.add_control_observer(sender)

    def _shutdown(sig, frame):
        print(f"\n[PHASE {phase}] Shutting down...")
        sender.stop()
        keyboard.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sender.start()
    keyboard.start()
    print(f"[PHASE {phase}] Running -- arrow keys to move, ESC or Ctrl+C to stop")

    while not keyboard.is_esc_pressed:
        time.sleep(0.1)

    _shutdown(None, None)


# --------------------------------------------------------------------------- #
# Phase 3 -- autonomous vision pipeline                                       #
# --------------------------------------------------------------------------- #

def _run_autonomous(cfg: PhaseConfig) -> None:
    from computer.communication.cam_receiver import CamReceiver
    from computer.communication.robot_sender import RobotSender
    from computer.vision.processor          import VisionProcessor
    from computer.vision.strategy           import BlobFollowerStrategy
    from computer.vision.detectors          import ColourBlobDetector

    cam_transport   = _make_transport(cfg.cam_transport,   cfg.cam_port)
    robot_transport = _make_transport(cfg.robot_transport, cfg.robot_port)

    cam_receiver = CamReceiver(cam_transport)
    processor    = VisionProcessor(show_preview=cfg.show_preview)
    strategy     = BlobFollowerStrategy(
        frame_width = cfg.frame_width,
        steer_gain  = cfg.steer_gain,
        base_speed  = cfg.base_speed,
    )
    robot_sender = RobotSender(robot_transport)

    processor.add_detector(ColourBlobDetector(
        label    = "target",
        hsv_low  = cfg.hsv_low,
        hsv_high = cfg.hsv_high,
        min_area = cfg.min_area,
    ))

    cam_receiver.add_frame_observer(processor)
    processor.add_result_observer(strategy)
    strategy.add_control_observer(robot_sender)

    def _shutdown(sig, frame):
        print("\n[PHASE 3] Shutting down...")
        cam_receiver.stop()
        processor.stop()
        robot_sender.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    robot_sender.start()
    processor.start()
    cam_receiver.start()
    print("[PHASE 3] Running -- press Ctrl+C to stop")

    while True:
        time.sleep(5.0)
        cam_stats = cam_receiver.stats()
        rob_stats = robot_sender.stats()
        print(
            f"[STATS] rx_frames={cam_stats['rx_frames']} "
            f"images={cam_stats['rx_images']} "
            f"pending={cam_stats['pending']} "
            f"tx_frames={rob_stats['tx_frames']}"
        )


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #

def _phase_label(phase: int) -> str:
    return {
        1: "manual / socat virtual ports",
        2: "manual / physical robot BT",
        3: "autonomous / physical robot + CAM BT",
    }[phase]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog        = "python -m computer.main",
        description = "Robot Vision System -- unified entry point",
    )
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3], required=True,
        metavar="PHASE",
        help=(
            "1 = manual / socat virtual ports  |  "
            "2 = manual / physical robot BT  |  "
            "3 = autonomous / physical robot + CAM BT"
        ),
    )
    args = parser.parse_args()
    cfg  = PHASE_CONFIGS[args.phase]

    print(f"[MAIN] Phase {args.phase} -- {_phase_label(args.phase)}")

    if args.phase in (1, 2):
        _run_manual(cfg, args.phase)
    else:
        _run_autonomous(cfg)


if __name__ == "__main__":
    main()
