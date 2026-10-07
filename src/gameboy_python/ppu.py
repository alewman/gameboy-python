"""The PPU, as a timing skeleton (milestone 1): LY, the modes, the STAT line, VBlank.

No pixels yet and a **fixed 172-dot mode 3**; the dot-accurate fetcher and FIFOs are milestone 2
(docs/handoff-brief.md). What it does model, because the CPU tests and the boot ROM need it:

* 456 dots per line, 154 lines; mode 2 for dots 0-79, mode 3 for 80-251, mode 0 for the rest of a
  visible line; mode 1 for lines 144-153 (Pan Docs Rendering.md);
* LY, LYC, the LY=LYC flag, STAT's bits, and the STAT interrupt **line** (the OR of the enabled
  sources; the interrupt fires only on its rising edge: Pan Docs Interrupt_Sources.md);
* the VBlank interrupt when LY becomes 144;
* VRAM locked from the CPU in mode 3, OAM in modes 2 and 3 (reads return $FF, writes are
  dropped: Pan Docs Accessing_VRAM_and_OAM.md); nothing is locked with the LCD off.

All of it advances in whole M-cycles (4 dots), which the line length and the mode boundaries
divide evenly. The edges are a few T off the real ones (docs/timing.md "The PPU"); milestone 2
settles them against Mooneye ppu/* and Mealybug.
"""

from __future__ import annotations

from collections.abc import Callable

from gameboy_python.machines import DOTS_PER_LINE

MODE2_END = 80
MODE3_END = 80 + 172
VBLANK_LINE = 144
LAST_LINE = 153


class PPU:
    def __init__(self, raise_irq: Callable[[int], None]) -> None:
        self.raise_irq = raise_irq
        self.vram = bytearray(0x2000)
        self.oam = bytearray(0xA0)
        self.lcdc = 0
        self.stat_select = 0  # STAT bits 6-3 as written
        self.scy = self.scx = 0
        self.ly = 0
        self.lyc = 0
        self.bgp = self.obp0 = self.obp1 = 0
        self.wy = self.wx = 0
        self.dot = 0
        self.mode = 0
        self.lyc_flag = False
        self.stat_line = False
        self.frames = 0  # VBlanks since power-on

    # ----- state --------------------------------------------------------------------------

    @property
    def lcd_on(self) -> bool:
        return bool(self.lcdc & 0x80)

    @property
    def vram_locked(self) -> bool:
        return self.lcd_on and self.mode == 3

    @property
    def oam_locked(self) -> bool:
        return self.lcd_on and self.mode in (2, 3)

    def _mode_at(self) -> int:
        if self.ly >= VBLANK_LINE:
            return 1
        if self.dot < MODE2_END:
            return 2
        return 3 if self.dot < MODE3_END else 0

    # ----- time ---------------------------------------------------------------------------

    def tick(self, dots: int = 4) -> None:
        """Advance ``dots`` PPU dots (one M-cycle)."""
        if not self.lcdc & 0x80:
            return
        self.dot += dots
        if self.dot >= DOTS_PER_LINE:
            self.dot -= DOTS_PER_LINE
            self.ly = 0 if self.ly == LAST_LINE else self.ly + 1
            if self.ly == VBLANK_LINE:
                self.frames += 1
                self.raise_irq(0)
        self.mode = self._mode_at()
        self._update_stat_line()

    def _update_stat_line(self) -> None:
        self.lyc_flag = self.ly == self.lyc
        select = self.stat_select
        line = bool(
            (select & 0x40 and self.lyc_flag)
            or (select & 0x08 and self.mode == 0)
            or (select & 0x10 and self.mode == 1)
            or (select & 0x20 and self.mode == 2)
        )
        if line and not self.stat_line:
            self.raise_irq(1)
        self.stat_line = line

    # ----- registers ----------------------------------------------------------------------

    def read_stat(self) -> int:
        if not self.lcd_on:
            return 0x80 | self.stat_select
        return 0x80 | self.stat_select | (4 if self.lyc_flag else 0) | self.mode

    def write_stat(self, value: int) -> None:
        self.stat_select = value & 0x78
        if self.lcd_on:
            self._update_stat_line()

    def write_lcdc(self, value: int) -> None:
        was_on = self.lcd_on
        self.lcdc = value
        if was_on and not self.lcd_on:  # LCD off: LY, the dot and the mode reset
            self.ly = 0
            self.dot = 0
            self.mode = 0
            self.lyc_flag = False
            self.stat_line = False
        elif not was_on and self.lcd_on:  # LCD on: line 0 starts now
            self.ly = 0
            self.dot = 0
            self.mode = 0  # line 0 starts in mode 0 (Mooneye ppu/lcdon_timing-GS)
            self._update_stat_line()

    def write_lyc(self, value: int) -> None:
        self.lyc = value
        if self.lcd_on:
            self._update_stat_line()

    def read_ly(self) -> int:
        return self.ly if self.lcd_on else 0
