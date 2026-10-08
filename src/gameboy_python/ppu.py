"""The PPU, dot by dot: OAM scan, a pixel stepper for mode 3, LY, the STAT line, VBlank.

One call to ``_dot`` per PPU dot (4 per M-cycle). Mode 3 is a **pixel stepper** rather than a
literal fetcher and FIFO pair: after the 12-dot start-up plus ``SCX % 8`` it emits one pixel per
dot, and stalls for the Pan Docs penalties (6 dots for the window, 6-11 per object by the
"OBJ penalty algorithm", Rendering.md). Pixel values are read from VRAM and the registers at the dot
the pixel is emitted, so a mid-line write to BGP, SCX, LCDC lands on the dot Mealybug's tests
measure it at, to the precision the penalties are right; the tile-data fetch *time* is not
modelled (UNVERIFIED against Mealybug: the first place to look if a picture is a few pixels off).

Also modelled: 456 dots per line, 154 lines, LYC, the STAT interrupt **line** (rising edge only),
the VBlank interrupt at LY 144, VRAM locked in mode 3 and OAM in modes 2-3 (reads return $FF,
writes dropped), nothing locked with the LCD off. The mode edges are fitted to Mooneye ppu/*.
"""

from __future__ import annotations

from collections.abc import Callable

from gameboy_python.machines import DOTS_PER_LINE

MODE2_END = 80
MODE_READ_LAG = 4  # FITTED: STAT and the CPU's VRAM/OAM locks see the mode 4 dots late (Mooneye
# intr_2_mode0_timing, intr_2_mode3_timing, intr_2_oam_ok_timing); interrupts do not
LINE0_START_DOT = 4  # FITTED: after LCD on, line 0 is 'late by 2 T' (Mooneye lcdon_timing-GS)
FIRST_OBJECT_DISCOUNT = 3  # FITTED to Mooneye ppu/intr_2_mode0_timing_sprites: the first object's
# stall on a line is 3 dots shorter than Pan Docs' penalty (every later one is as documented)
START_UP_DOTS = 12  # two tile fetches before the first pixel (Pan Docs Rendering.md)
VBLANK_LINE = 144
LAST_LINE = 153
SCREEN_W = 160
SCREEN_H = 144


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
        self.framebuffer = bytearray(SCREEN_W * SCREEN_H)  # shades 0-3, being drawn
        self.frame = bytes(SCREEN_W * SCREEN_H)  # the last completed picture
        # per-line state
        self.line_objs: list[
            tuple[int, int, int, int, int]
        ] = []  # (x, index, tile, flags, y), by x then index
        self.skip_scan = False
        self.x = 0  # next pixel to emit
        self.delay = 0  # start-up dots left
        self.stall = 0  # penalty dots left
        self.next_obj = 0
        self.penalised_tiles: set[tuple[bool, int | None]] = set()
        self.window_active = False
        self.window_line = 0  # the window's own line counter
        self.window_used = False  # window pixels drawn on this line
        self.wy_hit = False  # WY == LY seen this frame
        self.read_mode = 0  # the mode as the CPU sees it: ``mode`` from MODE_READ_LAG dots ago
        self._recent = [0] * MODE_READ_LAG
        self.drawing = False  # mode 3's pixel stepper is running
        self.penalised = False  # an object stalled this line
        self.line0 = False  # the first line after LCD on: late, and its STAT mode is not lagged
        self.mode3_start = MODE2_END

    # ----- state --------------------------------------------------------------------------

    @property
    def lcd_on(self) -> bool:
        return bool(self.lcdc & 0x80)

    @property
    def vram_write_locked(self) -> bool:
        """Writes lock 4 dots after reads do (Mooneye lcdon_write_timing-GS)."""
        return self.lcd_on and self.read_mode == 3

    @property
    def oam_write_locked(self) -> bool:
        """Like the read lock, but free at dot 0 and in the dot where mode 2 turns into 3."""
        return (
            self.lcd_on
            and self.read_mode in (2, 3)
            and not (self.mode == 3 and self.read_mode == 2)
        )

    @property
    def vram_locked(self) -> bool:
        return self.lcd_on and (self.mode == 3 or self.read_mode == 3)  # locks at once, frees late

    @property
    def oam_locked(self) -> bool:
        return self.lcd_on and (self.mode in (2, 3) or self.read_mode in (2, 3))

    # ----- time ---------------------------------------------------------------------------

    def tick(self, dots: int = 4) -> None:
        """Advance ``dots`` PPU dots (one M-cycle)."""
        if not self.lcdc & 0x80:
            return
        for _ in range(dots):
            self._dot()

    def _dot(self) -> None:
        self.dot += 1
        if self.dot >= DOTS_PER_LINE:
            self._next_line()
        if self.ly < VBLANK_LINE:
            dot = self.dot
            if dot < MODE2_END:
                if not self.skip_scan and not dot & 1:
                    self._scan(dot >> 1)
            elif dot == self.mode3_start:
                self._start_mode3()
            elif self.drawing:
                self._step_pixel()
        self._recent.append(self.mode)
        lagged = self._recent.pop(0)
        self.read_mode = self.mode if self.line0 else lagged
        self._update_stat_line()

    def _next_line(self) -> None:
        self.dot = 0
        self.line0 = False
        self.mode3_start = MODE2_END
        self.skip_scan = False
        if self.window_used:
            self.window_line += 1
        self.window_used = False
        self.ly = 0 if self.ly == LAST_LINE else self.ly + 1
        if self.ly == 0:
            self.window_line = 0
            self.wy_hit = False
        if self.ly == VBLANK_LINE:
            self.frames += 1
            self.frame = bytes(self.framebuffer)
            self.mode = 1
            self.raise_irq(0)
        elif self.ly < VBLANK_LINE:
            self.mode = 2
            self.line_objs = []
            self.window_active = False
            if self.ly == self.wy:
                self.wy_hit = True

    # ----- OAM scan -----------------------------------------------------------------------

    def _scan(self, entry: int) -> None:
        if entry >= 40 or len(self.line_objs) >= 10:
            return
        base = entry * 4
        y = self.oam[base] - 16
        height = 16 if self.lcdc & 4 else 8
        if y <= self.ly < y + height:
            self.line_objs.append(
                (self.oam[base + 1], entry, self.oam[base + 2], self.oam[base + 3], y)
            )
            self.line_objs.sort(key=lambda o: (o[0], o[1]))

    # ----- mode 3 -------------------------------------------------------------------------

    def _start_mode3(self) -> None:
        self.mode = 3
        self.drawing = True
        self.penalised = False
        self.x = 0
        self.delay = START_UP_DOTS + (self.scx & 7)
        self.stall = 0
        self.next_obj = 0
        self.penalised_tiles = set()
        self.window_active = False

    def _step_pixel(self) -> None:
        if self.delay:
            self.delay -= 1
            return
        if self.stall:
            self.stall -= 1
            return
        x = self.x
        lcdc = self.lcdc
        if not self.window_active and lcdc & 0x20 and lcdc & 1 and self.wy_hit and x + 7 >= self.wx:
            self.window_active = True
            self.window_used = True
            self.stall = 6 - 1
            return
        objs = self.line_objs
        penalty = 0
        while self.next_obj < len(objs) and objs[self.next_obj][0] - 8 <= x:
            ox = objs[self.next_obj][0]
            self.next_obj += 1
            if not lcdc & 2:
                continue
            if ox == 0:  # off the left edge: its own "tile", waited for in full, whatever SCX is
                key = (False, None)
                wait = 5
            else:
                pixel = ox - 8
                position = pixel - (self.wx - 7) if self.window_active else pixel + self.scx
                key = (self.window_active, position >> 3)
                wait = max(0, 7 - (position & 7) - 2)
            if key not in self.penalised_tiles:
                self.penalised_tiles.add(key)
                penalty += wait
            penalty += 6
        if penalty:
            if not self.penalised:
                self.penalised = True
                penalty -= FIRST_OBJECT_DISCOUNT
            self.stall = penalty - 1
            return
        self.framebuffer[self.ly * SCREEN_W + x] = self._pixel(x)
        self.x = x + 1
        if self.x >= SCREEN_W:
            self.mode = 0
            self.drawing = False

    def _pixel(self, x: int) -> int:
        lcdc = self.lcdc
        bg = 0
        if lcdc & 1:
            if self.window_active:
                column = x - (self.wx - 7)
                row = self.window_line
                tile_map = 0x1C00 if lcdc & 0x40 else 0x1800
            else:
                column = (x + self.scx) & 255
                row = (self.ly + self.scy) & 255
                tile_map = 0x1C00 if lcdc & 8 else 0x1800
            vram = self.vram
            tile = vram[tile_map + (row >> 3) * 32 + ((column >> 3) & 31)]
            signed_tile = 0x1000 + ((tile ^ 0x80) - 0x80) * 16
            address = (tile * 16 if lcdc & 0x10 else signed_tile) + (row & 7) * 2
            bit = 7 - (column & 7)
            bg = ((vram[address] >> bit) & 1) | (((vram[address + 1] >> bit) & 1) << 1)
        if lcdc & 2:
            for ox, _index, tile, flags, oy in self.line_objs:
                if ox - 8 <= x < ox:
                    color = self._object_pixel(ox, oy, tile, flags, x)
                    if color:
                        if flags & 0x80 and bg:
                            break
                        palette = self.obp1 if flags & 0x10 else self.obp0
                        return (palette >> (color * 2)) & 3
        return (self.bgp >> (bg * 2)) & 3

    def _object_pixel(self, ox: int, oy: int, tile: int, flags: int, x: int) -> int:
        height = 16 if self.lcdc & 4 else 8
        row = self.ly - oy
        if flags & 0x40:
            row = height - 1 - row
        if height == 16:
            tile &= 0xFE
        address = tile * 16 + row * 2
        column = x - (ox - 8)
        bit = column if flags & 0x20 else 7 - column
        return ((self.vram[address] >> bit) & 1) | (((self.vram[address + 1] >> bit) & 1) << 1)

    @property
    def visible_ly(self) -> int:
        """LY as software reads it: on line 153 it reads 153 for only the first few dots and then
        0 for the rest of the line (Pan Docs STAT.md; Gambatte hwtests/ly0, lyc153int_m2irq)."""
        return 0 if self.ly == LAST_LINE and self.dot >= 4 else self.ly

    def _update_stat_line(self) -> None:
        # (and for the first 4 dots of a new line it reads as false: Mooneye lcdon_timing-GS)
        self.lyc_flag = (self.dot >= 4 or self.ly == 0) and self.visible_ly == self.lyc
        select = self.stat_select
        line = bool(
            (select & 0x40 and self.lyc_flag)
            or (select & 0x08 and self.mode == 0)
            or (select & 0x10 and self.mode == 1)
            # the mode-2 source also fires as VBlank starts (Mooneye vblank_stat_intr-GS)
            or (select & 0x20 and (self.mode == 2 or (self.ly == VBLANK_LINE and self.dot < 4)))
        )
        if line and not self.stat_line:
            self.raise_irq(1)
        self.stat_line = line

    # ----- registers ----------------------------------------------------------------------

    def read_stat(self) -> int:
        if not self.lcd_on:  # mode 0, the comparison flag frozen
            return 0x80 | self.stat_select | (4 if self.lyc_flag else 0)
        return 0x80 | self.stat_select | (4 if self.lyc_flag else 0) | self.read_mode

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
            self.mode = 0  # the LY=LYC flag and the STAT line stay as they were (stat_lyc_onoff)
            self.window_line = 0
            self.window_used = self.window_active = self.wy_hit = False
            self.line_objs = []
            self._settle(0)
        elif not was_on and self.lcd_on:  # LCD on: line 0 starts now, but late
            self.ly = 0
            self.dot = LINE0_START_DOT
            self.line0 = True
            self.mode3_start = MODE2_END + LINE0_START_DOT
            self.mode = 0  # line 0 starts in mode 0 (Mooneye ppu/lcdon_timing-GS)
            self.skip_scan = True  # and has no OAM scan
            self._settle(0)
            self.wy_hit = self.wy == 0
            self._update_stat_line()

    def _settle(self, mode: int) -> None:
        """Make ``mode`` the current and the lagged mode (a jump, not a transition)."""
        self.mode = self.read_mode = mode
        self._recent = [mode] * MODE_READ_LAG

    def place(self, ly: int, dot: int, mode: int) -> None:
        """Put the beam at a line, dot and mode (the skip-boot hand-off state)."""
        self.ly, self.dot = ly, dot
        self._settle(mode)
        self._update_stat_line()

    def write_lyc(self, value: int) -> None:
        self.lyc = value
        if self.lcd_on:
            self._update_stat_line()

    def read_ly(self) -> int:
        return self.visible_ly if self.lcd_on else 0
