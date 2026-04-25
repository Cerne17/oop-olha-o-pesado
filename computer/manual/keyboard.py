"""
computer.manual.keyboard — KeyboardController.

Reads arrow key state via pynput and publishes ControlSignal at a fixed rate.
See SPEC.md §8.1 for the key → angle mapping.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

from pynput import keyboard
from pynput.keyboard import Key

from computer.types.observers import ControlObservable
from computer.types.signals   import ControlSignal


class KeyboardController(ControlObservable):
    """
    Parameters
    ----------
    publish_rate_hz : float — how often to emit ControlSignal events
    """

    def __init__(self, publish_rate_hz: float = 20.0) -> None:
        super().__init__()
        self._interval = 1.0 / publish_rate_hz
        self._pressed: set = set()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._stop_event   = threading.Event()
        self._pub_thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._listener.start()
        self._pub_thread = threading.Thread(
            target=self._publish_loop, name="keyboard-pub", daemon=True
        )
        self._pub_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._listener.stop()
        if self._pub_thread:
            self._pub_thread.join(timeout=2.0)

    @property
    def is_esc_pressed(self) -> bool:
        return Key.esc in self._pressed

    # -------------------------------------------------------------------------
    # pynput callbacks
    # -------------------------------------------------------------------------

    def _on_press(self, key) -> None:
        self._pressed.add(key)

    def _on_release(self, key) -> None:
        self._pressed.discard(key)

    # -------------------------------------------------------------------------
    # Direction computation (SPEC.md §8.1)
    # -------------------------------------------------------------------------

    def _get_signal(self) -> ControlSignal:
        pressed = self._pressed.copy()
        up    = Key.up    in pressed
        down  = Key.down  in pressed
        right = Key.right in pressed
        left  = Key.left  in pressed

        dy = (-1 if up    else 0) + (1 if down  else 0)
        dx = ( 1 if right else 0) + (-1 if left else 0)

        if dy == 0 and dx == 0:
            return ControlSignal.stopped()

        angle_deg = math.degrees(math.atan2(dx, -dy))
        return ControlSignal(angle_deg=angle_deg, speed_ref=1.0)

    # -------------------------------------------------------------------------
    # Publish loop
    # -------------------------------------------------------------------------

    def _publish_loop(self) -> None:
        while not self._stop_event.is_set():
            signal = self._get_signal()
            self._notify_control(signal)
            time.sleep(self._interval)
