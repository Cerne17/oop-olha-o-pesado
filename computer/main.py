"""
computer.main -- unified entry point for all development phases.

Usage:
    python -m computer.main --phase 1   # manual control, TCP to emulator
    python -m computer.main --phase 2   # manual control, physical robot over UDP/WiFi
    python -m computer.main --phase 3   # autonomous vision, physical robot + CAM over UDP/WiFi

Or after `pip install -e .`:
    robot-vision --phase <1|2|3>
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Per-phase configuration                                                      #
# --------------------------------------------------------------------------- #

@dataclass
class PhaseConfig:
    robot_port:      str
    robot_transport: str        = "serial"  # "serial" | "rfcomm"
    cam_port:        str | None = None
    cam_transport:   str | None = None

ROBOT_IP = "10.231.207.240:5005"
CAM_IP = "10.231.207.112:81"

# Phase 1 -- manual, TCP loopback to robot emulator
# Phase 2 -- manual, physical robot over UDP/WiFi (ESP32 IP:port)
# Phase 3 -- autonomous vision, physical robot over UDP/WiFi + CAM over BT
PHASE_CONFIGS: dict[int, PhaseConfig] = {
    1: PhaseConfig(
        robot_port      = "localhost:5001",
        robot_transport = "tcp",
        cam_port        = None,
    ),
    2: PhaseConfig(
        robot_port      = ROBOT_IP,  # ESP32 WiFi IP + listen port
        robot_transport = "udp",
        cam_port        = None,
    ),
    3: PhaseConfig(
        robot_port      = ROBOT_IP,  # robot ESP32 WiFi IP + listen port
        robot_transport = "udp",
        cam_port        = CAM_IP,  # CAM ESP32 WiFi IP + HTTP MJPEG port
        cam_transport   = "mjpeg",
    ),
}


# --------------------------------------------------------------------------- #
# Transport factory                                                            #
# --------------------------------------------------------------------------- #

def _make_transport(kind: str, port: str):
    from computer.communication.transport import SerialTransport, RFCOMMTransport, TCPTransport, UDPTransport
    if kind == "serial":
        return SerialTransport(port)
    if kind == "rfcomm":
        return RFCOMMTransport(port)
    if kind == "tcp":
        host, port_str = port.rsplit(":", 1)
        return TCPTransport(host, int(port_str))
    if kind == "udp":
        host, port_str = port.rsplit(":", 1)
        return UDPTransport(host, int(port_str))
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
    import cv2
    from computer.communication.robot_sender         import RobotSender
    from computer.vision.computer_vision_class import ComputerVision

    robot_transport = _make_transport(cfg.robot_transport, cfg.robot_port)

    if cfg.cam_transport == "mjpeg":
        from computer.communication.mjpeg_cam_receiver import MJPEGCamReceiver
        host, port_str = cfg.cam_port.rsplit(":", 1)
        cam_receiver = MJPEGCamReceiver(host, int(port_str))
    else:
        from computer.communication.cam_receiver import CamReceiver
        cam_transport = _make_transport(cfg.cam_transport, cfg.cam_port)
        cam_receiver  = CamReceiver(cam_transport)

    cv           = ComputerVision()
    robot_sender = RobotSender(robot_transport)

    cam_receiver.add_frame_observer(cv)
    cv.add_control_observer(robot_sender)

    def _shutdown(sig, frame):
        print("\n[PHASE 3] Shutting down...")
        cv.finish = True
        cam_receiver.stop()
        robot_sender.stop()
        cv2.destroyAllWindows()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    robot_sender.start()
    cam_receiver.start()
    print("[PHASE 3] Running -- press 'q' or Ctrl+C to stop")

    cv.Run()

    cam_receiver.stop()
    robot_sender.stop()
    cv2.destroyAllWindows()


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #

def _phase_label(phase: int) -> str:
    return {
        1: "manual / TCP emulator",
        2: "manual / physical robot UDP+WiFi",
        3: "autonomous / physical robot + CAM over UDP+WiFi",
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
            "1 = manual / TCP emulator  |  "
            "2 = manual / physical robot UDP+WiFi  |  "
            "3 = autonomous / physical robot + CAM over UDP+WiFi"
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
