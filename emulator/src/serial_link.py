"""
emulator.serial_link — serial port wrapper with thread-safe TX.
"""

from __future__ import annotations

import threading
import time

import serial


class SerialLink:
    def __init__(self, port: str, verbose: bool = False) -> None:
        self._port_path = port
        self._verbose = verbose
        self._serial: serial.Serial | None = None
        self._tx_lock = threading.Lock()

    def open(self, retry_interval: float = 1.0) -> None:
        while True:
            try:
                self._serial = serial.Serial(
                    self._port_path,
                    baudrate=115200,
                    timeout=0.1,
                )
                return
            except serial.SerialException as exc:
                print(f"[EMU] Cannot open {self._port_path}: {exc} "
                      f"— retrying in {retry_interval}s")
                time.sleep(retry_interval)

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()

    def send(self, data: bytes) -> None:
        with self._tx_lock:
            if self._serial and self._serial.is_open:
                self._serial.write(data)
                if self._verbose:
                    print(f"[EMU] TX {len(data)} bytes: {data[:16].hex()}…")

    def recv(self, size: int = 256) -> bytes:
        if self._serial and self._serial.is_open:
            try:
                return self._serial.read(size)
            except serial.SerialException:
                return b''
        return b''

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open
