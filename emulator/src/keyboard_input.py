"""
emulator.keyboard_input — non-blocking arrow key state via pynput.
"""

from __future__ import annotations

import math

from pynput import keyboard
from pynput.keyboard import Key


class KeyboardInput:
    def __init__(self) -> None:
        self._pressed: set = set()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()

    def _on_press(self, key) -> None:
        self._pressed.add(key)

    def _on_release(self, key) -> None:
        self._pressed.discard(key)

    def get_direction(self) -> tuple[float, bool]:
        """
        Returns (angle_deg, stop).
        angle_deg: clockwise from straight forward.
        stop: True when no directional key is pressed.
        """
        pressed = self._pressed.copy()
        up    = Key.up    in pressed
        down  = Key.down  in pressed
        right = Key.right in pressed
        left  = Key.left  in pressed

        if not any([up, down, right, left]):
            return 0.0, True

        dy = (-1 if up   else 0) + (1 if down  else 0)
        dx = ( 1 if right else 0) + (-1 if left else 0)

        angle_deg = math.degrees(math.atan2(dx, -dy))
        return angle_deg, False

    @property
    def is_esc_pressed(self) -> bool:
        return Key.esc in self._pressed
