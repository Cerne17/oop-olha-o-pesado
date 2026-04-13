"""
main.py — Entry point for the computer-side communication module.

Edit the CONFIG section below to match your setup, then run:

    python src/main.py

macOS (after pairing in System Settings → Bluetooth):
    TRANSPORT = "serial"
    SERIAL_PORT = "/dev/cu.RobotESP32-SerialPort"

Linux (RFCOMM socket, no pairing needed):
    TRANSPORT = "rfcomm"
    BT_MAC = "AA:BB:CC:DD:EE:FF"   ← your ESP32's Bluetooth MAC
"""

import signal
import sys
import time

# ============================================================
# CONFIG — edit these values before running
# ============================================================
TRANSPORT    = "serial"                         # "serial" | "rfcomm"
SERIAL_PORT  = "/dev/cu.RobotESP32-SerialPort"  # macOS serial port
BT_MAC       = "AA:BB:CC:DD:EE:FF"              # ESP32 BT MAC (RFCOMM mode)
BT_CHANNEL   = 1

FRAME_WIDTH  = 320
SHOW_PREVIEW = True    # open a live camera window (requires a display)
# ============================================================

sys.path.insert(0, "src")

from transport            import RFCOMMTransport, SerialTransport
from image_processor      import ImageProcessor, ColourBlobDetector
from robot_controller     import RobotController
from communication_module import CommunicationModule


def build_transport():
    if TRANSPORT == "rfcomm":
        return RFCOMMTransport(BT_MAC, BT_CHANNEL)
    elif TRANSPORT == "serial":
        return SerialTransport(SERIAL_PORT)
    else:
        raise ValueError(f"Unknown TRANSPORT value: {TRANSPORT!r}")


def build_image_processor() -> ImageProcessor:
    processor = ImageProcessor(max_queue_size=4, show_preview=SHOW_PREVIEW)

    # Detect red blobs — the robot steers toward the largest one.
    # Replace / extend with hand-sign detectors when that module is ready.
    processor.add_detector(ColourBlobDetector(
        label    = "target",
        hsv_low  = (0,   120, 70),
        hsv_high = (10,  255, 255),
        min_area = 400,
    ))

    return processor


def main() -> None:
    transport  = build_transport()
    ip         = build_image_processor()
    controller = RobotController(
        frame_width = FRAME_WIDTH,
        steer_gain  = 90.0,   # degrees of steering at full edge offset
    )
    module = CommunicationModule(
        transport        = transport,
        image_processor  = ip,
        robot_controller = controller,
        send_interval_s  = 0.05,   # 20 Hz command rate
        reconnect        = True,
    )

    def _shutdown(sig, frame):
        print("\n[MAIN] Shutting down…")
        module.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    module.start()

    print("[MAIN] Running — press Ctrl+C to stop")
    while True:
        time.sleep(5.0)
        s = module.stats()
        print(
            f"[STATS] rx={s['rx_frames']} tx={s['tx_frames']} "
            f"images={s['rx_images']} "
            f"hb_age={s['heartbeat_age_s']:.1f}s"
        )


if __name__ == "__main__":
    main()
