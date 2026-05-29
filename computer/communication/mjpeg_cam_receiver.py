"""
computer.communication.mjpeg_cam_receiver — MJPEG-over-HTTP cam receiver.

Connects to the ESP32-CAM's HTTP MJPEG stream (port 81 /stream),
extracts JPEG frames from the multipart boundary stream, and notifies
FrameObservers — same interface as CamReceiver.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import requests

from computer.types.observers import FrameObservable
from computer.types.signals import Frame


class MJPEGCamReceiver(FrameObservable):
    """
    Parameters
    ----------
    host : str  — ESP32-CAM IP address
    port : int  — HTTP server port (default 81)
    path : str  — stream URL path (default /stream)
    """

    _CHUNK_SIZE = 8192
    _JPEG_SOI   = b"\xff\xd8"
    _JPEG_EOI   = b"\xff\xd9"

    def __init__(self, host: str, port: int = 81, path: str = "/stream") -> None:
        super().__init__()
        self._url        = f"http://{host}:{port}{path}"
        self._stop_event = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._frame_id   = 0

    def start(self) -> None:
        self._stop_event.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="cam-rx", daemon=True
        )
        self._rx_thread.start()
        print(f"[CAM] MJPEG receiver started: {self._url}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._rx_thread:
            self._rx_thread.join(timeout=3.0)
        print("[CAM] MJPEG receiver stopped")

    def _rx_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                r = requests.get(self._url, stream=True, timeout=5)
            except requests.exceptions.RequestException as exc:
                print(f"[CAM] Connect failed: {exc} — retrying in 2 s")
                self._stop_event.wait(2)
                continue

            if r.status_code != 200:
                print(f"[CAM] HTTP {r.status_code} — retrying in 2 s")
                r.close()
                self._stop_event.wait(2)
                continue

            print("[CAM] Connected to MJPEG stream")
            buf = bytearray()
            try:
                for chunk in r.iter_content(chunk_size=self._CHUNK_SIZE):
                    if self._stop_event.is_set():
                        break
                    buf.extend(chunk)

                    # Drain all complete JPEGs; keep only the latest (newest-wins).
                    latest_jpg: Optional[bytes] = None
                    while True:
                        s = buf.find(self._JPEG_SOI)
                        e = buf.find(self._JPEG_EOI, s + 2) if s != -1 else -1
                        if s == -1 or e == -1:
                            break
                        latest_jpg = bytes(buf[s : e + 2])
                        del buf[: e + 2]

                    if latest_jpg is not None:
                        self._notify_frame(Frame(
                            frame_id  = self._frame_id,
                            jpeg      = latest_jpg,
                            timestamp = time.monotonic(),
                        ))
                        self._frame_id += 1

            except requests.exceptions.RequestException as exc:
                print(f"[CAM] Stream dropped: {exc} — reconnecting")
            finally:
                r.close()
