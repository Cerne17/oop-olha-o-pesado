"""
transport.py — Abstract Bluetooth transport layer with two concrete back-ends.

BluetoothTransport (ABC)
├── RFCOMMTransport   — Linux: raw AF_BLUETOOTH / BTPROTO_RFCOMM sockets
└── SerialTransport   — macOS / any OS: pyserial over the paired BT serial port

Usage (Linux):
    t = RFCOMMTransport(mac_address="AA:BB:CC:DD:EE:FF", channel=1)
    t.connect()

Usage (macOS — after pairing the ESP32 in System Settings):
    t = SerialTransport(port="/dev/cu.RobotESP32-xxx", baudrate=115200)
    t.connect()
"""

from __future__ import annotations

import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class BluetoothTransport(ABC):
    """
    Provides a uniform send / receive interface regardless of the underlying
    BT mechanism.  All implementations must be thread-safe.
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the connection.  Raises ConnectionError on failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection cleanly."""

    @abstractmethod
    def send(self, data: bytes) -> None:
        """
        Send raw bytes.  Raises ConnectionError if not connected.
        Thread-safe — may be called from multiple threads simultaneously.
        """

    @abstractmethod
    def receive(self, size: int, timeout: float = 5.0) -> bytes:
        """
        Read exactly *size* bytes.  Blocks until all bytes arrive or
        *timeout* seconds elapse.  Raises TimeoutError / ConnectionError.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True iff the transport has an active connection."""

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        """
        Non-blocking read of up to *max_bytes*.  Returns b'' if nothing is
        available.  Default implementation wraps receive() with a short timeout;
        subclasses can override with a true non-blocking path.
        """
        try:
            return self.receive(max_bytes, timeout=0.0)
        except (TimeoutError, OSError):
            return b''


# ---------------------------------------------------------------------------
# RFCOMM transport (Linux)
# ---------------------------------------------------------------------------
class RFCOMMTransport(BluetoothTransport):
    """
    Bluetooth Classic SPP via a raw RFCOMM socket.
    Works out-of-the-box on Linux (no extra libraries needed).
    May also work on macOS depending on the OS version.

    Parameters
    ----------
    mac_address : str
        Bluetooth MAC of the ESP32, e.g. "AA:BB:CC:DD:EE:FF".
    channel : int
        RFCOMM channel.  The ESP32 BluetoothSerial library uses channel 1.
    """

    def __init__(self, mac_address: str, channel: int = 1) -> None:
        self._mac     = mac_address
        self._channel = channel
        self._sock: Optional[socket.socket] = None
        self._lock    = threading.Lock()

    def connect(self) -> None:
        try:
            sock = socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                socket.BTPROTO_RFCOMM,   # type: ignore[attr-defined]
            )
            sock.settimeout(10.0)
            sock.connect((self._mac, self._channel))
            sock.settimeout(None)   # switch to blocking after connect
            self._sock = sock
            print(f"[BT] Connected to {self._mac} on RFCOMM channel {self._channel}")
        except OSError as exc:
            raise ConnectionError(f"RFCOMM connect failed: {exc}") from exc

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send(self, data: bytes) -> None:
        if not self._sock:
            raise ConnectionError("Not connected")
        with self._lock:
            try:
                self._sock.sendall(data)
            except OSError as exc:
                self._sock = None
                raise ConnectionError(f"Send failed: {exc}") from exc

    def receive(self, size: int, timeout: float = 5.0) -> bytes:
        if not self._sock:
            raise ConnectionError("Not connected")

        self._sock.settimeout(timeout if timeout > 0 else None)
        buf = bytearray()
        deadline = time.monotonic() + timeout if timeout > 0 else None

        try:
            while len(buf) < size:
                if deadline and time.monotonic() > deadline:
                    raise TimeoutError(f"Timed out after receiving {len(buf)}/{size} bytes")
                chunk = self._sock.recv(size - len(buf))
                if not chunk:
                    raise ConnectionError("Connection closed by remote")
                buf.extend(chunk)
        except socket.timeout as exc:
            raise TimeoutError("Socket timed out") from exc
        finally:
            self._sock.settimeout(None)

        return bytes(buf)

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        if not self._sock:
            return b''
        self._sock.setblocking(False)
        try:
            return self._sock.recv(max_bytes)
        except BlockingIOError:
            return b''
        except OSError:
            return b''
        finally:
            self._sock.setblocking(True)

    def is_connected(self) -> bool:
        return self._sock is not None


# ---------------------------------------------------------------------------
# Serial transport (macOS / cross-platform)
# ---------------------------------------------------------------------------
class SerialTransport(BluetoothTransport):
    """
    Bluetooth Classic SPP via a paired serial port (pyserial).

    On macOS: pair the ESP32 in System Settings → Bluetooth, then macOS
    creates /dev/cu.RobotESP32-SerialPort (or similar).  Pass that path here.

    On Linux: the paired device appears as /dev/rfcomm0 after running
        sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1

    Parameters
    ----------
    port : str
        Serial port path, e.g. "/dev/cu.RobotESP32-xxx".
    baudrate : int
        Must match the ESP32 Serial.begin() rate (default 115200).
    """

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self._port     = port
        self._baudrate = baudrate
        self._serial   = None
        self._lock     = threading.Lock()

    def connect(self) -> None:
        try:
            import serial   # pyserial — imported lazily so it's optional
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=5.0,
            )
            print(f"[BT] Opened serial port {self._port} at {self._baudrate} baud")
        except Exception as exc:
            raise ConnectionError(f"Serial connect failed: {exc}") from exc

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def send(self, data: bytes) -> None:
        if not self._serial or not self._serial.is_open:
            raise ConnectionError("Not connected")
        with self._lock:
            self._serial.write(data)

    def receive(self, size: int, timeout: float = 5.0) -> bytes:
        if not self._serial:
            raise ConnectionError("Not connected")
        self._serial.timeout = timeout
        data = self._serial.read(size)
        if len(data) < size:
            raise TimeoutError(f"Serial read timeout ({len(data)}/{size} bytes)")
        return data

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        if not self._serial or not self._serial.is_open:
            return b''
        waiting = self._serial.in_waiting
        if waiting == 0:
            return b''
        return self._serial.read(min(waiting, max_bytes))

    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open
