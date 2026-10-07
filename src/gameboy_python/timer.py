"""The system counter, DIV and the timer (docs/timing.md "The system counter").

One 16-bit counter counts every T-cycle. DIV ($FF04) is its top byte; any write to DIV clears
the whole counter. TIMA increments on the **falling edge** of ``selected counter bit AND TAC
enable``, so writing DIV, or changing TAC, can produce an extra edge (Pan Docs
Timer_and_Divider_Registers.md and Timer_Obscure_Behaviour.md; Mooneye acceptance/timer/*,
hardware-verified). On overflow TIMA reads $00 for one M-cycle, then TMA is loaded and IF bit 2
is raised; a write to TIMA in the first of those cycles cancels the reload, a write in the
second is ignored, a write to TMA in the second is loaded too.

Other consumers of the counter (the serial clock, the frame sequencer) read :attr:`previous` and
:attr:`counter` after :meth:`tick` and look for falling edges themselves.
"""

from __future__ import annotations

from collections.abc import Callable

#: counter bit selected by TAC bits 1-0 (Pan Docs): 4096, 262144, 65536, 16384 Hz
TIMER_BITS = (9, 3, 5, 7)


class Timer:
    """The counter, TIMA, TMA and TAC."""

    def __init__(self, raise_irq: Callable[[int], None], tac_disable_glitch: bool = True) -> None:
        self.raise_irq = raise_irq
        self.tac_disable_glitch = tac_disable_glitch
        self.counter = 0
        self.previous = 0  # the counter before the last tick
        self.tima = 0
        self.tma = 0
        self.tac = 0
        self.reload_pending = False  # TIMA overflowed in the previous M-cycle
        self.reloading = False  # this M-cycle is the one that loads TMA

    # ----- time ---------------------------------------------------------------------------

    def tick(self, t_cycles: int = 4) -> None:
        """Advance one M-cycle: ``t_cycles`` counts of the system counter."""
        if self.reload_pending:
            self.reload_pending = False
            self.reloading = True
            self.tima = self.tma
            self.raise_irq(2)
        else:
            self.reloading = False
        previous = self.counter
        self.previous = previous
        counter = self.counter = (previous + t_cycles) & 0xFFFF
        if self.tac & 4:
            bit = TIMER_BITS[self.tac & 3]
            if (previous >> bit) & 1 and not (counter >> bit) & 1:
                self._increment()

    def _increment(self) -> None:
        self.tima += 1
        if self.tima > 0xFF:
            self.tima = 0
            self.reload_pending = True

    def _signal(self, counter: int, tac: int) -> int:
        """The level that clocks TIMA: the selected counter bit AND the enable."""
        return (counter >> TIMER_BITS[tac & 3]) & 1 if tac & 4 else 0

    # ----- registers ----------------------------------------------------------------------

    def read_div(self) -> int:
        return self.counter >> 8

    def write_div(self) -> None:
        """Any write clears the counter; if the clocking level was high, that is a falling edge."""
        if self._signal(self.counter, self.tac):
            self._increment()
        self.counter = 0

    def write_tima(self, value: int) -> None:
        if self.reloading:
            return  # TMA wins during the reload cycle
        self.reload_pending = False  # a write in the overflow cycle cancels the reload
        self.tima = value

    def write_tma(self, value: int) -> None:
        self.tma = value
        if self.reloading:
            self.tima = value  # loaded too if written in the reload cycle

    def write_tac(self, value: int) -> None:
        value &= 7
        old, new = self._signal(self.counter, self.tac), self._signal(self.counter, value)
        enabling_edge = old and not new
        if enabling_edge and (value & 4 or self.tac_disable_glitch):
            # a falling edge: a different bit selected while enabled, or (DMG only) disabling
            self._increment()
        self.tac = value
