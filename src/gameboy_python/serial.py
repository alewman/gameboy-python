"""Serial port with nothing attached (docs/start-here.md "Joypad and serial").

SB shifts out MSB first with the internal clock, one bit per falling edge of system-counter
bit 8 (8192 Hz: the divider is shared with the main clock, so the phase depends on when the
counter was last reset, Mooneye serial/boot_sclk_align); with nothing connected every incoming
bit is 1, so a transfer ends with SB = $FF. The eighth shift clears SC bit 7 and raises IF bit 3.
"""

from __future__ import annotations

from collections.abc import Callable

SERIAL_CLOCK_BIT = 8  # 4194304 / 512 = 8192 Hz: UNVERIFIED against the die (start-here.md)


class Serial:
    def __init__(self, raise_irq: Callable[[int], None]) -> None:
        self.raise_irq = raise_irq
        self.sb = 0
        self.sc = 0  # bit 7 transfer in progress, bit 0 internal clock
        self.shifted = 0
        self.output = bytearray()  # every byte that finished shifting out, for test harnesses

    def tick(self, previous: int, counter: int) -> None:
        """Called every M-cycle with the system counter before and after."""
        if (
            self.sc & 0x81 == 0x81
            and (previous >> SERIAL_CLOCK_BIT) & 1
            and not (counter >> SERIAL_CLOCK_BIT) & 1
        ):
            self.sb = ((self.sb << 1) | 1) & 0xFF
            self.shifted += 1
            if self.shifted == 8:
                self.sc &= 0x7F
                self.raise_irq(3)

    def write_sb(self, value: int) -> None:
        self.sb = value

    def write_sc(self, value: int) -> None:
        self.sc = value & 0x81
        if value & 0x80:
            self.shifted = 0
            self.output.append(self.sb)  # the byte as it leaves (MSB first on the wire)

    def read_sc(self) -> int:
        return self.sc | 0x7E
