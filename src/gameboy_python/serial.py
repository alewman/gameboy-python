"""Serial port with nothing attached (docs/start-here.md "Joypad and serial").

SB shifts out MSB first with the internal clock, one bit per falling edge of system-counter bit 8
(8192 Hz). The serial divider is shared with the main clock but has its own reset, so its edges
run a fixed number of T-cycles ahead of the counter DIV shows: ``SERIAL_PHASE_T``. That constant
is **fitted**: with it (and the counter's 4 T power-on phase in board.py) Mooneye
serial/boot_sclk_align (verified DMG ABC and MGB) passes together with boot_div, from skip-boot
and from dmg-sim's quickboot. It has not been read off the die (dmg-schematics): UNVERIFIED
there. With nothing connected every incoming bit is 1, so a transfer ends with SB = $FF. The
eighth shift clears SC bit 7 and raises IF bit 3.
"""

from __future__ import annotations

from collections.abc import Callable

SERIAL_CLOCK_BIT = 8  # 4194304 / 512 = 8192 Hz
SERIAL_PHASE_T = 4  # the divider's edges come this many T-cycles before the counter's
SERIAL_FINISH_DELAY = 1  # M-cycles from the eighth edge to the last shift showing


class Serial:
    def __init__(self, raise_irq: Callable[[int], None]) -> None:
        self.raise_irq = raise_irq
        self.sb = 0
        self.sc = 0  # bit 7 transfer in progress, bit 0 internal clock
        self.shifted = 0
        self._finish_in = 0  # M-cycles until the eighth shift and SC's clearing show
        self.master = True  # the divider's toggle flip-flop
        self.output = bytearray()  # every byte that finished shifting out, for test harnesses

    def tick(self, previous: int, counter: int) -> None:
        """Called every M-cycle with the system counter before and after."""
        if self._finish_in:
            self._finish_in -= 1
            if not self._finish_in:
                self.sb = ((self.sb << 1) | 1) & 0xFF
                self.sc &= 0x7F
        if self.sc & 0x81 != 0x81 or self._finish_in:
            return
        before = (previous + SERIAL_PHASE_T) >> SERIAL_CLOCK_BIT & 1
        after = (counter + SERIAL_PHASE_T) >> SERIAL_CLOCK_BIT & 1
        if before and not after:
            self.shifted += 1
            if self.shifted == 8:
                # the interrupt goes out now; the last shift and the clearing of SC bit 7 show
                # one M-cycle later (FITTED: Gambatte serial/start_wait_read_s[bc]_*)
                self._finish_in = SERIAL_FINISH_DELAY
                self.raise_irq(3)
                if not SERIAL_FINISH_DELAY:
                    self.sb = ((self.sb << 1) | 1) & 0xFF
                    self.sc &= 0x7F
            else:
                self.sb = ((self.sb << 1) | 1) & 0xFF

    def write_sb(self, value: int) -> None:
        self.sb = value

    def write_sc(self, value: int) -> None:
        self.sc = value & 0x81
        if value & 0x80:
            self.shifted = 0
            self.output.append(self.sb)  # the byte as it leaves (MSB first on the wire)

    def read_sc(self) -> int:
        return self.sc | 0x7E
