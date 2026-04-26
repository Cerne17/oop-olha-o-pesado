"""
emulator.tcp_link -- TCP server socket wrapper with thread-safe TX.

The emulator acts as the TCP server; the computer's TCPTransport connects as
the client. This matches the real-world model where the ESP32 is always-on and
the computer connects to it.

Spec reference: emulator/SPEC.md §4.1, §6.
"""

from __future__ import annotations

import socket
import threading


class TcpLink:
    def __init__(self, port: int, verbose: bool = False) -> None:
        self._port         = port
        self._verbose      = verbose
        self._server_sock: socket.socket | None = None
        self._conn:        socket.socket | None = None
        self._tx_lock      = threading.Lock()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def listen(self) -> None:
        """Create and bind the server socket. Call once at startup."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(('0.0.0.0', self._port))
        self._server_sock.listen(1)

    def accept(self) -> str:
        """Block until a client connects. Returns 'host:port' string."""
        assert self._server_sock is not None, "call listen() first"
        conn, addr = self._server_sock.accept()
        conn.setblocking(False)
        with self._tx_lock:
            self._conn = conn
        return f"{addr[0]}:{addr[1]}"

    def close_conn(self) -> None:
        """Close the accepted connection without stopping the server socket."""
        with self._tx_lock:
            if self._conn:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None

    def close(self) -> None:
        """Close both the accepted connection and the server socket."""
        self.close_conn()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    # -------------------------------------------------------------------------
    # IO
    # -------------------------------------------------------------------------

    def send(self, data: bytes) -> None:
        """Thread-safe write. Silently drops if not connected."""
        with self._tx_lock:
            if not self._conn:
                return
            try:
                self._conn.sendall(data)
                if self._verbose:
                    print(f"[EMU] TX {len(data)} bytes: {data[:16].hex()}")
            except OSError:
                self._conn = None

    def recv(self, max_bytes: int = 4096) -> bytes:
        """Non-blocking read. Returns b'' when no data or not connected."""
        if not self._conn:
            return b''
        try:
            return self._conn.recv(max_bytes)
        except BlockingIOError:
            return b''
        except OSError:
            with self._tx_lock:
                self._conn = None
            return b''

    # -------------------------------------------------------------------------
    # State
    # -------------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._conn is not None
