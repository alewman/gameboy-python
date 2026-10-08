"""The joypad matrix at $FF00 (Pan Docs Joypad_Input.md).

Bits 5 and 4 select the button row and the direction row (active low); bits 3-0 read the
four lines of the selected rows, 0 = pressed; bits 7-6 read 1. Any high-to-low transition on a
selected input raises IF bit 4.
"""

from __future__ import annotations

from collections.abc import Callable

BUTTONS = ("a", "b", "select", "start")
DIRECTIONS = ("right", "left", "up", "down")


class Joypad:
    def __init__(self, raise_irq: Callable[[int], None]) -> None:
        self.raise_irq = raise_irq
        self.select = 0x00  # bits 5-4: both rows selected at power-on, so P1 reads $CF
        self.pressed: set[str] = set()

    def _lines(self) -> int:
        value = 0x0F
        if not self.select & 0x20:  # buttons selected
            value &= ~sum(1 << i for i, name in enumerate(BUTTONS) if name in self.pressed)
        if not self.select & 0x10:  # directions selected
            value &= ~sum(1 << i for i, name in enumerate(DIRECTIONS) if name in self.pressed)
        return value & 0x0F

    def read(self) -> int:
        return 0xC0 | self.select | self._lines()

    def write(self, value: int) -> None:
        before = self._lines()
        self.select = value & 0x30
        if before & ~self._lines():
            self.raise_irq(4)

    def set_pressed(self, name: str, down: bool) -> None:
        """A host-side button change; raises the joypad interrupt on a selected press."""
        before = self._lines()
        (self.pressed.add if down else self.pressed.discard)(name)
        if before & ~self._lines():
            self.raise_irq(4)
