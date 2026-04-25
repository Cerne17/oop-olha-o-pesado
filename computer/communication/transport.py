"""
computer.communication.transport — concrete Transport implementations.

SerialTransport  : pyserial — works on macOS after pairing via System Settings
RFCOMMTransport  : Linux AF_BLUETOOTH RFCOMM socket — no system pairing needed
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Optional

import serial

from computer.types.transport import Transport


class SerialTransport(Transport):
    """
    pyserial-backed transport. Works on macOS (paired BT SPP device shows up
    as /dev/cu.*) and Linux, and with socat virtual ports for testing.
    """

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self._port     = port
        self._baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._tx_lock  = threading.Lock()

    def connect(self) -> None:
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(
            self._port, baudrate=self._baudrate, timeout=0.0
        )

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def send(self, data: bytes) -> None:
        with self._tx_lock:
            if not self._serial or not self._serial.is_open:
                raise ConnectionError("SerialTransport: not connected")
            self._serial.write(data)

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        if not self._serial or not self._serial.is_open:
            return b''
        try:
            waiting = self._serial.in_waiting
            if waiting == 0:
                return b''
            return self._serial.read(min(waiting, max_bytes))
        except serial.SerialException as exc:
            raise ConnectionError(f"SerialTransport read error: {exc}") from exc

    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open


class RFCOMMTransport(Transport):
    """
    Linux-only AF_BLUETOOTH RFCOMM socket transport. Does not require the
    device to be paired in the system Bluetooth settings.
    """

    def __init__(self, mac_address: str, channel: int = 1) -> None:
        self._mac      = mac_address
        self._channel  = channel
        self._sock: Optional[socket.socket] = None
        self._tx_lock  = threading.Lock()

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_BLUETOOTH,
                                   socket.SOCK_STREAM,
                                   socket.BTPROTO_RFCOMM)
        try:
            self._sock.connect((self._mac, self._channel))
            self._sock.setblocking(False)
        except OSError as exc:
            self._sock.close()
            self._sock = None
            raise ConnectionError(
                f"RFCOMMTransport: cannot connect to {self._mac}:{self._channel}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send(self, data: bytes) -> None:
        with self._tx_lock:
            if not self._sock:
                raise ConnectionError("RFCOMMTransport: not connected")
            try:
                self._sock.sendall(data)
            except OSError as exc:
                raise ConnectionError(f"RFCOMMTransport send error: {exc}") from exc

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        if not self._sock:
            return b''
        try:
            return self._sock.recv(max_bytes)
        except BlockingIOError:
            return b''
        except OSError as exc:
            raise ConnectionError(f"RFCOMMTransport recv error: {exc}") from exc

    def is_connected(self) -> bool:
        return self._sock is not None
