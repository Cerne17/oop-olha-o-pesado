"""
computer.types.transport — abstract transport interface.

Concrete implementations live in computer/communication/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_available(self, max_bytes: int = 4096) -> bytes:
        """Return available bytes without blocking. Return b'' if none."""
        ...

    @abstractmethod
    def is_connected(self) -> bool: ...
