"""Serial port with nothing attached (docs/start-here.md "Joypad and serial").

SB shifts out MSB first with the internal clock at 8192 Hz. The clock is a toggle flip-flop that
each falling edge of system-counter bit 7 flips; a shift happens when it falls (SameBoy
GB_serial_master_edge). Any SC write drops a high toggle, so a transfer's first shift comes two
bit-7 falls later, and a DIV write while bit 7 is high is a fall too. Both writes act before a fall
in their own M-cycle (FITTED: Gambatte serial/nopx*_start*, *_late_div_write_*). The serial
divider is shared with the main clock but has its own reset, so its edges run a fixed number of
T-cycles ahead of the counter DIV shows: ``SERIAL_PHASE_T``. That constant is **fitted**: with it
(and the counter's 4 T power-on phase in board.py) Mooneye serial/boot_sclk_align (verified DMG ABC
and MGB) passes together with boot_div, from skip-boot and from dmg-sim's quickboot. It has not
been read off the die (dmg-schematics): UNVERIFIED there. With nothing connected every incoming
bit is 1, so a transfer ends with SB = $FF. The eighth shift clears SC bit 7 and raises IF bit 3.
"""

from __future__ import annotations

from collections.abc import Callable

SERIAL_CLOCK_BIT = 7  # its falls clock a toggle: 4194304 / 512 = 8192 Hz
FAST_CLOCK_BIT = 2  # CGB mode, SC bit 1: 262144 Hz (Pan Docs Serial_Data_Transfer_(Link_Cable).md)
SERIAL_PHASE_T = 4  # the divider's edges come this many T-cycles before the counter's
SC_BEFORE_EDGE = 1  # an SC write comes before its M-cycle's fall
SERIAL_DIV_PHASE = -4  # ... and a DIV write sees the clock bit as it was before the M-cycle
SERIAL_FINISH_DELAY = 1  # M-cycles from the eighth edge to the last shift showing


class Serial:
    def __init__(self, raise_irq: Callable[[int], None]) -> None:
        self.raise_irq = raise_irq
        self.sb = 0
        self.sc = 0  # bit 7 transfer in progress, bit 0 internal clock
        self.shifted = 0
        self._finish_in = 0  # M-cycles until the eighth shift and SC's clearing show
        self.master = False  # the toggle flip-flop the clock bit drives
        self._fell = False  # the clock bit fell in this M-cycle
        self.cgb_mode = False  # SC bit 1 (the fast clock) exists only in CGB mode
        self.output = bytearray()  # every byte that finished shifting out, for test harnesses

    def tick(self, previous: int, counter: int) -> None:
        """Called every M-cycle with the system counter before and after."""
        if self._finish_in:
            self._finish_in -= 1
            if not self._finish_in:
                self.sb = ((self.sb << 1) | 1) & 0xFF
                self.sc &= 0x7F
        bit = FAST_CLOCK_BIT if self.sc & 2 else SERIAL_CLOCK_BIT
        phase = SERIAL_PHASE_T
        self._fell = (previous + phase) >> bit & 1 and not (counter + phase) >> bit & 1
        if self._fell:
            self._master_edge()

    def div_reset(self, counter: int) -> None:
        """A DIV write clears the counter: a high clock bit falls, which clocks the toggle."""
        bit = FAST_CLOCK_BIT if self.sc & 2 else SERIAL_CLOCK_BIT
        if (counter + SERIAL_PHASE_T + SERIAL_DIV_PHASE) >> bit & 1:
            self._master_edge()

    def _master_edge(self) -> None:
        """A falling edge of the clock bit flips the toggle; the toggle's fall shifts."""
        self.master = not self.master
        if self.master or self.sc & 0x81 != 0x81 or self._finish_in:
            return
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

    def cancel_finish(self) -> None:
        """The eighth shift has not shown yet and now never will."""
        self._finish_in = 0

    def write_sb(self, value: int) -> None:
        self.sb = value

    def write_sc(self, value: int) -> None:
        # any write restarts the count and drops a high toggle, which is a fall (SameBoy)
        fell = SC_BEFORE_EDGE and self._fell
        if fell:
            self.master = not self.master  # the write comes before this M-cycle's fall
        self.shifted = 0
        if self.master:
            self._master_edge()
        self.sc = value & (0x83 if self.cgb_mode else 0x81)
        if fell:
            self._master_edge()
        if value & 0x80:
            self.output.append(self.sb)  # the byte as it leaves (MSB first on the wire)

    def read_sc(self) -> int:
        return self.sc | (0x7C if self.cgb_mode else 0x7E)
