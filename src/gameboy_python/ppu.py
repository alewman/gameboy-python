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
OAM_IRQ_EARLY = 0  # the OAM interrupt pulse begins this early (GBMicrotest wants 4, Mooneye 0)
LYC_IRQ_EARLY = 4  # the LY=LYC interrupt comes this many dots before the flag shows
OAM_IRQ_WIDTH = 4  # and lasts this many dots
LINE0_START_DOT = 4  # FITTED: after LCD on, line 0 is 'late by 2 T' (Mooneye lcdon_timing-GS)
LINE0_LEAD = 4  # FITTED (Mealybug line_0_fix): on line 0 the pixel pipeline runs this early
BGP_GLITCH_DOT = 1  # FITTED: the dot, counted from the write's, whose palette is the OR
# FITTED (Mealybug): dots from a pop to each register sample
LCDC_DELAY = 9
BGP_DELAY = 7
OBP_DELAY = 10
OBJ_SIZE_LAG = 0  # FITTED (Mealybug): dots LCDC.2 arrives late at an object fetch
MAP_SHIFT = LOW_SHIFT = HIGH_SHIFT = (
    10  # FITTED (Mealybug): dots each background VRAM read is deferred
)
SKIP_LATCH_DOT = 10  # FITTED (Mealybug m3_scx_low_3_bits): last dot SCX's low bits are read
MAP_READ_DOT = LOW_READ_DOT = HIGH_READ_DOT = 2  # which dot (1 or 2) of its step each fetch reads
OBJ_FETCH_DOTS = 6
FIRST_OBJECT_DISCOUNT = 3  # FITTED to Mooneye ppu/intr_2_mode0_timing_sprites
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
        self.f_events: list[list[int]] = []  # deferred fetcher reads [dots left, step]
        self.lcdc_hist = [0] * 16  # LCDC as of each of the last dots (for the lagged bits)
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
        self.next_obj = 0
        self.window_active = False
        self.window_line = 0  # the window's own line counter
        self.window_used = False  # window pixels drawn on this line
        self.wy_hit = False  # WY == LY seen this frame
        self.read_mode = 0  # the mode as the CPU sees it: ``mode`` from MODE_READ_LAG dots ago
        self._recent = [0] * MODE_READ_LAG
        self.pipe: list[list] = []  # popped pixels waiting for their register samples
        self.drawing = False  # mode 3 is running
        self.line0 = False  # the first line after LCD on: starts at dot 4
        self.mode3_start = MODE2_END
        self.mode0_dot = 0
        self.m3 = self.skip = self.fetch_col = 0
        self.bg: list[tuple[list[int], int]] = []
        self.obj_fifo: list[tuple[int, int]] = []
        self.f_step = self.f_dot = 0
        self.ticket = [0, 0, 0, 0]
        self.ticket_col = 0
        self.obj_lo = self.obj_hi = 0
        self.dummy = False
        self.bgp_glitch: tuple[int, int, int] = (-1, -1, 0)  # (dot, line, OR of old and new)
        self.penalised = False
        self.obj_wait_left = 0
        self.obj_tiles_waited = set()
        self.obj_low_at = self.obj_high_at = 0
        self.obj_dots = 0
        self.obj_entry = None

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
        return self.lcd_on and (
            (self.mode == 3 and not self.line0) or self.read_mode == 3
        )  # locks at once, frees late

    @property
    def oam_locked(self) -> bool:
        return self.lcd_on and (
            (self.mode in (2, 3) and not self.line0) or self.read_mode in (2, 3)
        )

    # ----- time ---------------------------------------------------------------------------

    def tick(self, dots: int = 4) -> None:
        """Advance ``dots`` PPU dots (one M-cycle)."""
        if not self.lcdc & 0x80:
            return
        for _ in range(dots):
            self._dot()

    def _dot(self) -> None:
        self.lcdc_hist.append(self.lcdc)
        del self.lcdc_hist[0]
        self.dot += 1
        if self.dot >= DOTS_PER_LINE:
            self._next_line()
        if self.ly < VBLANK_LINE:
            dot = self.dot
            if dot < MODE2_END and not self.skip_scan and not dot & 1:
                self._scan(dot >> 1)
            if dot == self.mode3_start:
                self._start_mode3()
            elif self.drawing:
                self._step_pixel()
            if dot == MODE2_END and self.drawing:
                self.mode = 3
            if self.mode0_dot and dot >= self.mode0_dot:
                self.mode = 0
                self.mode0_dot = 0
        if self.f_events:
            self._run_fetch_events()
        if self.pipe:
            self._colour_pixels()
        self._recent.append(self.mode)
        lagged = self._recent.pop(0)
        self.read_mode = lagged
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
            self.mode3_start = MODE2_END - LINE0_LEAD
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
        if self.dot >= MODE2_END:
            self.mode = 3
        self.drawing = True
        self.x = 0
        self.m3 = 0
        self.skip = self.scx & 7  # latched now: later SCX writes move tiles, not the fine scroll
        self.next_obj = 0
        self.window_active = False
        self.bg: list[tuple[list[int], int]] = []  # the background FIFO: (tile ticket, bit)
        self.obj_fifo: list[tuple[int, int]] = []  # (colour, flags) for the next pixels
        self.f_step = 0  # 0 tile, 1 data low, 2 data high, 3 waiting to push
        self.f_dot = 0
        self.fetch_col = 0
        self.dummy = True  # the first fetch is thrown away (Pan Docs Rendering.md, "first12")
        self.penalised = False  # an object has been fetched on this line
        self.obj_wait_left = 0
        self.obj_tiles_waited: set[tuple[bool, int | None]] = set()
        self.obj_dots = 0  # dots left of the object fetch
        self.obj_entry: tuple[int, int, int, int, int] | None = None

    # ----- the background fetcher ---------------------------------------------------------

    def _lcdc_ago(self, lag: int) -> int:
        return self.lcdc_hist[-lag] if lag else self.lcdc

    def _fetch_read(self, step: int, ticket: list[int], window: bool, col: int) -> None:
        """The VRAM read of one fetcher step, with the registers as they are *now*; ``ticket``
        collects a tile's [map byte, data low, data high, done]."""
        lcdc = self.lcdc
        if step == 0:
            if window:
                base = 0x1C00 if lcdc & 0x40 else 0x1800
                index = base + (self.window_line >> 3) * 32 + (col & 31)
            else:
                base = 0x1C00 if lcdc & 8 else 0x1800
                row = (self.ly + self.scy) & 255
                index = base + (row >> 3) * 32 + (((self.scx >> 3) + col) & 31)
            ticket[0] = self.vram[index]
            return
        tile = ticket[0]
        signed = 0x1000 + ((tile ^ 0x80) - 0x80) * 16
        address = tile * 16 if lcdc & 0x10 else signed
        row = self.window_line if window else (self.ly + self.scy) & 255
        address += (row & 7) * 2 + (step - 1)
        ticket[step] = self.vram[address]
        if step == 2:
            ticket[3] = 1

    def _run_fetch_events(self) -> None:
        pending = []
        for event in self.f_events:
            event[0] -= 1
            if event[0] <= 0:
                self._fetch_read(*event[1:])
            else:
                pending.append(event)
        self.f_events = pending

    def _fetcher_dot(self) -> None:
        step = self.f_step
        if step < 3:
            self.f_dot += 1
            if self.f_dot == (MAP_READ_DOT, LOW_READ_DOT, HIGH_READ_DOT)[step]:
                if step == 0:
                    self.ticket = [0, 0, 0, 0]
                    self.ticket_col = self.fetch_col
                    self.fetch_col += 1
                args = (step, self.ticket, self.window_active, self.ticket_col)
                shift = (MAP_SHIFT, LOW_SHIFT, HIGH_SHIFT)[step]
                if shift:
                    self.f_events.append([shift, *args])
                else:
                    self._fetch_read(*args)
            if self.f_dot < 2:
                return
            self.f_dot = 0
            self.f_step = step + 1
            if self.f_step < 3:
                return
        # step 3: push, retried every dot until the FIFO is empty
        if not self.bg:
            if self.dummy:
                self.dummy = False
                self.fetch_col = 0
            else:
                self.bg = [(self.ticket, b) for b in range(7, -1, -1)]
            self.f_step = 0
            self.f_dot = 0

    # ----- objects ------------------------------------------------------------------------

    def _object_dot(self) -> None:
        """One dot of an object fetch; the background fetcher is frozen."""
        self.obj_dots -= 1
        entry = self.obj_entry
        assert entry is not None
        ox, _index, tile, flags, oy = entry
        for read_at, is_high in ((self.obj_low_at, 0), (self.obj_high_at, 1)):
            if self.obj_dots == read_at:
                height = 16 if self._lcdc_ago(OBJ_SIZE_LAG) & 4 else 8
                row = self.ly - oy
                if flags & 0x40:
                    row = height - 1 - row
                if height == 16:
                    tile &= 0xFE
                data = self.vram[tile * 16 + row * 2 + is_high]
                if is_high:
                    self.obj_hi = data
                else:
                    self.obj_lo = data
        if self.obj_dots == 0:
            self._merge_object(ox, flags)
            self.obj_entry = None

    def _start_object_fetch(self, entry: tuple[int, int, int, int, int]) -> None:
        dots = OBJ_FETCH_DOTS
        if not self.penalised:  # FITTED: the first object on a line costs less
            self.penalised = True
            dots -= FIRST_OBJECT_DISCOUNT
        self.obj_dots = dots
        self.obj_low_at = max(dots - 3, 0)
        self.obj_high_at = max(dots - 5, 0)
        self.obj_entry = entry
        self._object_dot()

    def _object_wait(self, ox: int) -> int:
        """Pan Docs' "OBJ penalty algorithm" (Rendering.md): dots spent waiting for the background
        tile under the object's leftmost pixel, once per tile; an object at X=0 is a tile of its
        own that is waited for in full."""
        if ox == 0:
            key, wait = (False, None), 5
        else:
            pixel = ox - 8
            position = pixel - (self.wx - 7) if self.window_active else pixel + self.scx
            key, wait = (self.window_active, position >> 3), max(0, 7 - (position & 7) - 2)
        if key in self.obj_tiles_waited:
            return 0
        self.obj_tiles_waited.add(key)
        return wait

    def _merge_object(self, ox: int, flags: int) -> None:
        skip = max(0, 8 - ox)  # the part hanging off the left edge
        fifo = self.obj_fifo
        while len(fifo) < 8 - skip:
            fifo.append((0, 0))
        for i in range(skip, 8):
            bit = i if flags & 0x20 else 7 - i
            colour = ((self.obj_lo >> bit) & 1) | (((self.obj_hi >> bit) & 1) << 1)
            slot = i - skip
            if colour and not fifo[slot][0]:
                fifo[slot] = (colour, flags)

    def _step_pixel(self) -> None:
        self.m3 += 1
        if self.m3 <= SKIP_LATCH_DOT:
            self.skip = self.scx & 7  # the fine scroll is read here, then frozen for the line
        if self.obj_dots:
            self._object_dot()
            return
        if self.obj_entry is not None:  # the wait for the object's tile is over: fetch it
            if self.obj_wait_left:
                self.obj_wait_left -= 1
                self._fetcher_dot()
            else:
                self._start_object_fetch(self.obj_entry)
            return
        lcdc = self.lcdc
        if self.bg and not self.skip:
            x = self.x
            if (
                not self.window_active
                and lcdc & 0x20
                and lcdc & 1
                and self.wy_hit
                and (x + 7 == self.wx or (x == 0 and self.wx < 7))
            ):
                self.window_active = True
                self.window_used = True
                self.bg = []
                self.f_step = 0
                self.f_dot = 0
                self.fetch_col = 0
                self.skip = max(0, 7 - self.wx)
                self._fetcher_dot()
                return
            objs = self.line_objs
            if self.next_obj < len(objs) and objs[self.next_obj][0] - 8 <= x:
                if not lcdc & 2:
                    self.next_obj += 1
                else:
                    entry = objs[self.next_obj]
                    self.next_obj += 1
                    self.obj_entry = entry
                    self.obj_wait_left = self._object_wait(entry[0])
                    if self.obj_wait_left:  # this dot is the first of the wait
                        self.obj_wait_left -= 1
                        self._fetcher_dot()
                    else:
                        self._start_object_fetch(entry)
                    return
        if self.bg:
            colour = self.bg.pop(0)  # (ticket, bit): resolved when the pixel is coloured
            if self.skip:
                self.skip -= 1
            else:
                obj = self.obj_fifo.pop(0) if self.obj_fifo else (0, 0)
                d = self.dot
                self.pipe.append(
                    [
                        self.x,
                        colour,
                        obj,
                        d + LCDC_DELAY,
                        d + BGP_DELAY,
                        d + OBP_DELAY,
                        None,
                        None,
                        None,
                        None,
                        self.ly,
                    ]
                )
                self.x += 1
                if self.x >= SCREEN_W:
                    if self.mode3_start < MODE2_END:  # line 0: the pipeline ran early, STAT did not
                        self.mode0_dot = self.dot + MODE2_END - self.mode3_start
                    else:
                        self.mode = 0
                    self.drawing = False
                    return
        self._fetcher_dot()

    # A popped pixel is coloured from three registers, each sampled a fixed number of dots after
    # the pop (they pass different stages of the pipeline): LCDC's BG/OBJ enables, BGP, OBP0/1.

    def _colour_pixels(self) -> None:
        dot = self.dot
        keep = []
        for rec in self.pipe:
            # rec = [x, bg, obj, lcdc_due, bgp_due, obp_due, lcdc, bgp, obp0, obp1, ly]
            if rec[3] <= dot and rec[6] is None:
                rec[6] = self.lcdc
            if rec[4] <= dot and rec[7] is None:
                g_dot, g_ly, g_value = self.bgp_glitch
                glitch = g_dot + BGP_GLITCH_DOT == dot and g_ly == self.ly
                rec[7] = g_value if glitch else self.bgp
            if rec[5] <= dot and rec[8] is None:
                rec[8], rec[9] = self.obp0, self.obp1
            if rec[8] is None or rec[7] is None or rec[6] is None or not rec[1][0][3]:
                keep.append(rec)
                continue
            self.framebuffer[rec[10] * SCREEN_W + rec[0]] = self._pixel(rec)
        self.pipe = keep

    @staticmethod
    def _pixel(rec: list) -> int:
        _x, (ticket, bit), (colour, flags), _a, _b, _c, lcdc, bgp, obp0, obp1, _ly = rec
        bg = ((ticket[1] >> bit) & 1) | (((ticket[2] >> bit) & 1) << 1)
        if not lcdc & 1:
            bg = 0
        if colour and lcdc & 2 and not (flags & 0x80 and bg):
            return ((obp1 if flags & 0x10 else obp0) >> (colour * 2)) & 3
        return (bgp >> (bg * 2)) & 3

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
            or (select & 0x40 and self._lyc_early())
            or (
                select & 0x08
                and self.mode == 0
                and not (self.line0 and self.dot < self.mode3_start)
            )
            or (select & 0x10 and self.mode == 1)
            # the OAM source is a short pulse at the start of each line, VBlank's first line
            # included (Mooneye vblank_stat_intr-GS, GBMicrotest lcdon_to_oam_int_l1)
            or (select & 0x20 and self._oam_pulse())
        )
        if line and not self.stat_line:
            self.raise_irq(1)
        self.stat_line = line

    def _lyc_early(self) -> bool:
        """The LY=LYC interrupt comes LYC_IRQ_EARLY dots before the flag (GBMicrotest int_lyc_*)."""
        return (
            self.dot < 4
            and self.dot >= 4 - LYC_IRQ_EARLY
            and self.ly != 0
            and self.visible_ly == self.lyc
        )

    def _oam_pulse(self) -> bool:
        if self.dot >= DOTS_PER_LINE - OAM_IRQ_EARLY:
            following = 0 if self.ly == LAST_LINE else self.ly + 1
            return following <= VBLANK_LINE
        return (
            self.dot < OAM_IRQ_WIDTH - OAM_IRQ_EARLY and self.ly <= VBLANK_LINE and not self.line0
        )

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
            self.pipe = []
            self._settle(0)
        elif not was_on and self.lcd_on:  # LCD on: line 0 starts now, but late
            self.ly = 0
            self.dot = LINE0_START_DOT
            self.line0 = True
            self.mode3_start = MODE2_END
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

    def write_bgp(self, value: int) -> None:
        """DMG: for one dot around a BGP write the palette is the OR of the old and new values
        (Mealybug m3_bgp_change: each band is one pixel wider at both edges)."""
        self.bgp_glitch = (self.dot, self.ly, self.bgp | value)
        self.bgp = value

    def write_lyc(self, value: int) -> None:
        self.lyc = value
        if self.lcd_on:
            self._update_stat_line()

    def read_ly(self) -> int:
        return self.visible_ly if self.lcd_on else 0
