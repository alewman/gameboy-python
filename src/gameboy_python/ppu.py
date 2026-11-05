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

from array import array
from collections.abc import Callable

from gameboy_python.machines import DOTS_PER_LINE

MODE2_END = 80
OAM_BUG_LAST_ROW = 19  # FITTED (blargg oam_bug 7): the last row that can be corrupted
OAM_BUG_START = 0  # FITTED (blargg oam_bug): the dot at which the scan reads row 0
MODE_READ_LAG = 4  # FITTED: STAT and the CPU's VRAM/OAM locks see the mode 4 dots late (Mooneye
# intr_2_mode0_timing, intr_2_mode3_timing, intr_2_oam_ok_timing); interrupts do not
OAM_IRQ_EARLY = (
    4  # FITTED: the CPU's dispatch sees the line-start OAM interrupt this early (GBMicrotest)
)
HBLANK_IRQ_EARLY = 2  # FITTED (GBMicrotest hblank_int_scx*): pixels before the end it fires
MODE0_READ_LAG = 1  # FITTED (GBMicrotest ppu_sprite0_scx*): STAT shows mode 0 this many dots after
MODE0_READ_LAG_DS = 0  # FITTED: the same in double speed (Gambatte cgb04c *_ds m3stat, vramw_m3end,
# gdma/hdma_cycles)
PAL_HOLD_DS = 2  # FITTED (Gambatte cgbpal_m3end_ds): dots the CGB palettes stay locked after STAT
# leaves mode 3 in double speed (SameBoy frees them after STAT and VRAM too)
LY_LEAD = 0  # FITTED (Mooneye hblank_ly_scx_timing with the early HBlank interrupt)
WX_GLITCH = 0  # 1 = Pan Docs' WX-reached-again colour-0 pixel; it made wx_4/5 worse, so off
SHADOW_LAG = 2  # the pixel-drawing PPU runs this many dots behind the one that times STAT
SHADOW_WX_LAG = 4
WX_LAG = 1  # FITTED (Gambatte cgb04c window 143 -> 148 of 193 at 0 or 1; was 4, the shadow's SHADOW_WX_LAG carries the Mealybug fit): the timing PPU's window comparator sees WX this many dots late
WIN_LAG = 0  # ... and LCDC.5/.0 this many
WINDOW_HEAD = 4  # FITTED (GBMicrotest win*): fetcher dots the window restart gets for free
WINDOW_EDGE_HEAD = 6  # ... when the window starts at the left edge (WX < 7)
VBLANK_IF_LATE = 4  # FITTED (GBMicrotest stat_write_glitch_l143_*): IF shows VBlank this much later
MODE1_IRQ_DOT = 4  # FITTED (GBMicrotest vblank_int_if_*): the STAT VBlank source comes this late
LYC_IRQ_EARLY = 4  # the LY=LYC interrupt comes this many dots before the flag shows
OAM_IRQ_WIDTH = 4  # and lasts this many dots
LINE0_START_DOT = 4  # FITTED: after LCD on, line 0 is 'late by 2 T' (Mooneye lcdon_timing-GS)
LINE0_LEAD = 0  # FITTED (Mealybug line_0_fix): on line 0 the pixel pipeline runs this early
BGP_GLITCH_DOT = 1  # FITTED: the dot, counted from the write's, whose palette is the OR
# FITTED (Mealybug): dots from a pop to each register sample
LCDC_DELAY = 3
BGP_DELAY = 1
SCY_LAG = 4
  # FITTED (Gambatte scy/scy_during_m3_*): dots a SCY write takes to reach the fetcher
# FITTED (Gambatte scx_during_m3, Mealybug m3_scx_high_5_bits, dmg-acid2, cgb-acid2; SameBoy
# display.c's fetcher, x = (SCX + position + 8 - (cgb && !during_object_fetch)) / 8): a map read
# takes its column from SCX this many dots after its step's first dot, and the screen position at
# that first dot
SCX_COL_DOT = 2
SCX_COL_DOT_OBJ = 5  # ... once an object has been fetched (our fetches then run 3 dots early)
SCX_COL0_DOT = 0  # column 0: SCX >> 3 at its step's first dot (scx_during_m3 variants 3 and 4)
# FITTED (Gambatte scx_during_m3, Mealybug m3_scx_low_3_bits): dots late the fine-scroll drop
# sees SCX
SKIP_LAG = 7
# FITTED (Gambatte scx_during_m3_ds_*, against SameBoy CGB E's fetch log): in double speed the
# drawing PPU sees SCX writes this many dots late (they reach ours 4 dots before SameBoy's)
DS_SCX_LAG = 4
# FITTED (Gambatte window/arg/late_wy_*_2, CGB 207 -> 217 of 273 in window): on CGB a written WY is
# compared this many dots later (SameBoy runs the compare at the next 4-dot boundary, on CGB one
# phase later than on DMG); 4-5 gain, 6 loses the _1 halves, DMG keeps the immediate compare
WY_WAIT_CGB = 5
# FITTED (Gambatte sprites/space 9pos8_wx*_m3stat_ds_1, 1pos8_8pos9_wx08: 346 -> 355 of 380): in
# double speed a window started after an object fetch stalls the pipeline this many dots (3 loses
# them, 5 loses a _2 half; SameBoy's fetch log puts its mode 3 about 4 dots past ours)
WIN_OBJ_STALL_DS = 4
# SameBoy (sm83_cpu.c cgb_conflict_map, LYC = GB_CONFLICT_WRITE_CPU against DMG's READ_OLD): on CGB
# at single speed a LYC write lands this many dots later (Gambatte lycEnable +2; 1-3 agree, 4 trades
# the lcdoffset1 halves)
LYC_WAIT_CGB = 1
# FITTED (Gambatte scx_during_m3_ds_* row 0): in double speed line 0's OAM interrupt also comes
# early, by one M-cycle (SameBoy's line-0 writes land one M-cycle after line 1's, ours two)
EARLY_LINE0_DS = 2
OBP_DELAY = 4
BG_MAP_LAG = 4  # FITTED (Gambatte bgtilemap): dots LCDC.3 (map select) arrives late at the fetcher
BG_DATA_LAG = 4  # ... and LCDC.4 (tile data select); both make Gambatte bgtilemap/bgtiledata rows below the sprites exact
OBJ_SIZE_LAG = 0  # FITTED (Mealybug): dots LCDC.2 arrives late at an object fetch
# FITTED (Mealybug): dots each background VRAM read is deferred past its fetcher step
MAP_SHIFT = 4
LOW_SHIFT = 4
HIGH_SHIFT = 4
MAP_READ_DOT = LOW_READ_DOT = HIGH_READ_DOT = 2  # which dot (1 or 2) of its step each fetch reads
OBJ_FETCH_DOTS = 6
FIRST_OBJECT_DISCOUNT = 3  # FITTED to Mooneye ppu/intr_2_mode0_timing_sprites
FIRST_OBJECT_DISCOUNT_DS = 2  # FITTED (Gambatte cgb04c sprites/space in double speed, 261 -> 341 of 380); AGE stat-mode-sprites (single speed) needs 3
VBLANK_LINE = 144
LAST_LINE = 153
SCREEN_W = 160
SCREEN_H = 144


def _ignore_irq(bit: int) -> None:
    return None


class PPU:
    # PyPy keeps an instance's attributes in a fixed layout only up to 79; past that every
    # ``self.x`` is a dict lookup. Slots have no such limit: with them dmg-acid2 runs 3x as fast
    # and cgb-acid2 8x (tests/test_pypy_layout.py keeps it so).
    __slots__ = (
        "_recent",
        "_sources",
        "bcps",
        "bg",
        "bg_pal",
        "bgp",
        "bgp_glitch",
        "cgb",
        "cgb_mode",
        "dot",
        "double_speed",
        "drawing",
        "dropped",
        "dummy",
        "early_fired",
        "early_lyc153",
        "f_dot",
        "f_events",
        "f_step",
        "fetch_col",
        "frame",
        "framebuffer",
        "frames",
        "free_skip",
        "glitching",
        "hblank_early",
        "irq_early_by",
        "irq_halt_delay",
        "is_shadow",
        "lcdc",
        "lcdc_hist",
        "line0",
        "line_objs",
        "ly",
        "ly153_dots",
        "lyc",
        "lyc_flag",
        "lyc_next",
        "lyc_wait",
        "m3",
        "mode",
        "mode0_dot",
        "mode0_dots",
        "mode3_start",
        "next_obj",
        "oam",
        "obj_dots",
        "obj_entry",
        "obj_fifo",
        "obj_hi",
        "obj_high_at",
        "obj_lo",
        "obj_low_at",
        "obj_pal",
        "obj_tiles_waited",
        "obj_wait_left",
        "obp0",
        "obp1",
        "ocps",
        "opri",
        "pal_hold",
        "penalised",
        "pipe",
        "raise_irq",
        "read_mode",
        "scx",
        "scx_hist",
        "scy",
        "scy_hist",
        "shadow",
        "skip",
        "skip_scan",
        "stat_blocking",
        "stat_line",
        "stat_select",
        "stat_write_glitch",
        "sub",
        "t1_obj",
        "t1_x",
        "ticket",
        "ticket_col",
        "vram",
        "vram_bank",
        "win_stall",
        "win_started_wx",
        "window_active",
        "window_line",
        "window_used",
        "wx",
        "wx_hist",
        "wy",
        "wy_hit",
        "wy_wait",
        "x"
    )

    def __init__(
        self,
        raise_irq: Callable[[int], None],
        stat_write_glitch: bool = False,
        _shadow: bool = False,
        stat_blocking: bool = True,
        cgb: bool = False,
    ) -> None:
        """A PPU is two: this one times the mode, the STAT line and the interrupts from register
        values at the pops; a *shadow* copy of the same machinery runs ``SHADOW_LAG`` dots behind
        it, shares VRAM and OAM, sees the registers as they are by then, and draws the picture."""
        self.is_shadow = _shadow
        #: CGB hardware: two VRAM banks and palette RAM; ``cgb_mode`` is false when the boot ROM
        #: chose the DMG-compatible mode (KEY0), where BGP/OBPn still pick the shades
        self.cgb = cgb
        #: dots LY reads 153 for at the start of line 153: 4 on a DMG, 8 on a CGB E (AGE ly-cgbE)
        self.ly153_dots = 8 if cgb else 4
        self.double_speed = False  # the CPU runs at twice the PPU's rate (set by the board)
        self.cgb_mode = False
        self.opri = 0 if cgb else 1  # $FF6C bit 0: 1 = objects ordered by X (DMG), 0 = by OAM index
        self.vram_bank = 0  # the bank the CPU sees ($FF4F)
        self.bg_pal = bytearray(64)
        self.obj_pal = bytearray(64)
        self.bcps = self.ocps = 0
        self.raise_irq = raise_irq
        self.stat_write_glitch = stat_write_glitch
        #: the STAT interrupt line is one OR: a source that rises while another holds it raises
        #: nothing (every model but DMG 0, Mooneye ppu/stat_irq_blocking)
        self.stat_blocking = stat_blocking
        self._sources = (False, False, False, False)
        self.hblank_early = False  # mode 3 is within HBLANK_IRQ_EARLY pixels of its end
        self.mode0_dots = 0
        self.glitching = False
        self.early_lyc153 = False
        self.early_fired = False
        self.irq_early_by = 0  # dots before its real time the interrupt just raised came
        self.irq_halt_delay = 0  # dots later a halted CPU sees the STAT interrupt just raised
        self.sub = 0  # the dot within the M-cycle being ticked (0-3)
        self.vram = bytearray(0x4000 if cgb else 0x2000)
        self.oam = bytearray(0xA0)
        self.lcdc = 0
        self.f_events: list[list[int]] = []  # deferred fetcher reads [dots left, step]
        self.wx_hist = [0] * 16
        self.scy_hist = [0] * 16
        self.scx_hist = [0] * 16
        self.lcdc_hist = [0] * 16  # LCDC as of each of the last dots (for the lagged bits)
        self.stat_select = 0  # STAT bits 6-3 as written
        self.scy = self.scx = 0
        self.ly = 0
        self.lyc = 0
        self.bgp = 0
        self.obp0 = self.obp1 = 0xFF  # power-on: GBMicrotest poweron_obp*_000 read $FF
        self.wy = self.wx = 0
        self.dot = 0
        self.mode = 0
        self.lyc_flag = False
        self.stat_line = False
        self.frames = 0  # VBlanks since power-on
        # shades 0-3 (DMG); on CGB hardware RGB555 words, 16 bits per pixel little-endian in
        # ``frame``, the last completed picture
        self.framebuffer = array("H", [0x7FFF] * (SCREEN_W * SCREEN_H)) if cgb else bytearray(SCREEN_W * SCREEN_H)
        self.frame = self._blank()
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
        self.wy_wait = 0  # dots until a written WY is compared (CGB)
        self.lyc_wait = self.lyc_next = 0  # dots until a written LYC lands, and its value (CGB)
        self.pal_hold = 0  # dots the CGB palettes stay locked after read_mode leaves 3
        self.read_mode = 0  # the mode as the CPU sees it: ``mode`` from MODE_READ_LAG dots ago
        self._recent = [0] * MODE_READ_LAG
        self.pipe: list[list] = []  # popped pixels waiting for their register samples
        self.drawing = False  # mode 3 is running
        self.line0 = False  # the first line after LCD on: starts at dot 4
        self.mode3_start = MODE2_END
        self.mode0_dot = 0
        self.m3 = self.skip = self.fetch_col = 0
        self.bg: list[tuple[list[int], int]] = []
        self.obj_fifo: list[tuple[int, int, int]] = []
        self.f_step = self.f_dot = 0
        self.ticket = [0, 0, 0, 0, 0]
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
        self.win_started_wx = -1
        self.shadow: PPU | None = None
        if not _shadow:
            self.shadow = PPU(_ignore_irq, False, _shadow=True, cgb=cgb)
            self.shadow.vram = self.vram
            self.shadow.oam = self.oam
            self.shadow.bg_pal = self.bg_pal
            self.shadow.obj_pal = self.obj_pal

    # ----- state --------------------------------------------------------------------------

    def _blank(self) -> bytes:
        """A white screen: shade 0, or RGB555 $7FFF on CGB hardware."""
        return (b"\xff\x7f" if self.cgb else b"\x00") * (SCREEN_W * SCREEN_H)

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
        for sub in range(dots):
            self.sub = sub
            self._dot()

    def _dot(self) -> None:
        self.lcdc_hist.append(self.lcdc)
        del self.lcdc_hist[0]
        self.wx_hist.append(self.wx)
        del self.wx_hist[0]
        self.scy_hist.append(self.scy)
        del self.scy_hist[0]
        self.scx_hist.append(self.scx)
        del self.scx_hist[0]
        self.dot += 1
        if self.dot >= DOTS_PER_LINE:
            self._next_line()
        if self.wy_wait:
            self.wy_wait -= 1
            if not self.wy_wait:
                self._compare_wy_now()
        if self.lyc_wait:
            self.lyc_wait -= 1
            if not self.lyc_wait:
                self._write_lyc_now(self.lyc_next)
        if self.ly < VBLANK_LINE:
            dot = self.dot
            if 0 <= dot < MODE2_END and not self.skip_scan and not dot & 1:
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
        if self.is_shadow:
            return
        if self.shadow is not None:
            self._step_shadow()
        self._recent.append(self.mode)
        lagged = self._recent.pop(0)
        self.mode0_dots = self.mode0_dots + 1 if self.mode == 0 else 0
        lag = (
            (MODE0_READ_LAG_DS if self.double_speed else MODE0_READ_LAG)
            if not (self.penalised or self.window_used)
            else MODE_READ_LAG
        )
        if lagged == 3 and self.mode == 0 and self.mode0_dots > lag:
            lagged = 0  # the end of mode 3 shows up in STAT sooner than the start of it does
        if lagged == 1 and self.mode == 2:
            lagged = 0  # the first dots of line 0 read as mode 0, not VBlank's 1
        if self.pal_hold:
            self.pal_hold -= 1
        if self.read_mode == 3 and lagged != 3:
            self.pal_hold = PAL_HOLD_DS if self.double_speed else 0
        self.read_mode = lagged
        self._update_stat_line()

    def _step_shadow(self) -> None:
        shadow = self.shadow
        assert shadow is not None
        shadow.lcdc = (
            (self.lcdc & ~0x18)
            | (self._lcdc_ago(BG_MAP_LAG) & 0x08)
            | (self._lcdc_ago(BG_DATA_LAG) & 0x10)
        )
        shadow.cgb_mode, shadow.opri = self.cgb_mode, self.opri
        shadow.scx = self.scx_hist[-DS_SCX_LAG] if self.double_speed else self.scx
        shadow.scy = self.scy_hist[-SCY_LAG] if SCY_LAG else self.scy
        shadow.wx, shadow.wy = self.wx, self.wy
        shadow.bgp, shadow.obp0, shadow.obp1 = self.bgp, self.obp0, self.obp1
        g_dot, g_ly, g_value = self.bgp_glitch
        shadow.bgp_glitch = (g_dot - SHADOW_LAG, g_ly, g_value)
        shadow._dot()

    def _follow(self) -> None:
        """Put the shadow SHADOW_LAG dots behind where this PPU is now."""
        shadow = self.shadow
        if shadow is None:
            return
        ly, dot = self.ly, self.dot - SHADOW_LAG
        if dot < 0 and self.ly == 0 and not self.line0:
            ly, dot = LAST_LINE, dot + DOTS_PER_LINE
        elif dot < 0 and not self.line0:
            ly, dot = ly - 1, dot + DOTS_PER_LINE
        shadow.ly, shadow.dot = ly, dot
        shadow.line0, shadow.skip_scan = self.line0, self.skip_scan
        shadow.mode3_start = self.mode3_start
        shadow.wy_hit = self.wy_hit
        shadow.window_line = self.window_line

    def _next_line(self) -> None:
        self.dot = 0
        self.hblank_early = False
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
            self.frame = (self.shadow or self).framebuffer.tobytes() if self.cgb else bytes((self.shadow or self).framebuffer)
            self.mode = 1
            self.irq_early_by = VBLANK_IF_LATE
            self.irq_halt_delay = 0
            self.raise_irq(0)
            self.irq_early_by = 0
        elif self.ly < VBLANK_LINE:
            self.mode = 2
            self.line_objs = []
            self.window_active = False
            if self.ly == self.wy:
                self.wy_hit = True

    # ----- the OAM corruption bug (DMG): Pan Docs OAM_Corruption_Bug.md ---------------------------

    def oam_row(self) -> int | None:
        """The OAM row the PPU is reading this M-cycle, or None outside the scan."""
        if not self.lcd_on or self.ly >= VBLANK_LINE or self.line0:
            return None
        row = (self.dot - OAM_BUG_START) // 4
        return row if 0 <= row <= OAM_BUG_LAST_ROW else None

    def corrupt_oam(self, kind: str) -> None:
        """An address in $FE00-$FEFF on the bus during the scan: ``kind`` is 'read', 'write' or
        'readinc' (a read in the cycle the IDU steps the same register)."""
        row = self.oam_row()
        if row is None:
            return
        oam = self.oam

        def word(r: int, w: int) -> int:
            return oam[r * 8 + w * 2] | (oam[r * 8 + w * 2 + 1] << 8)

        def put(r: int, w: int, value: int) -> None:
            oam[r * 8 + w * 2] = value & 0xFF
            oam[r * 8 + w * 2 + 1] = (value >> 8) & 0xFF

        def copy_row(src: int, dst: int) -> None:
            oam[dst * 8 : dst * 8 + 8] = oam[src * 8 : src * 8 + 8]

        if kind == "readinc" and 4 <= row < 19:
            a, b, c, d = word(row - 2, 0), word(row - 1, 0), word(row, 0), word(row - 1, 2)
            put(row - 1, 0, (b & (a | c | d)) | (a & c & d))
            copy_row(row - 1, row)
            copy_row(row - 1, row - 2)
        if row == 0:
            return
        a, b, c = word(row, 0), word(row - 1, 0), word(row - 1, 2)
        if kind == "write":
            put(row, 0, ((a ^ c) & (b ^ c)) ^ c)
        else:
            put(row, 0, b | (a & c))
        oam[row * 8 + 2 : row * 8 + 8] = oam[(row - 1) * 8 + 2 : (row - 1) * 8 + 8]

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
        self.win_stall = 0
        # the fine scroll: pixels are dropped until their count matches SCX's low bits (SameBoy)
        self.skip = 1
        self.dropped = 0
        self.next_obj = 0
        self.window_active = False
        self.free_skip = 0
        self.bg: list[tuple[list[int], int]] = []  # the background FIFO: (tile ticket, bit)
        self.obj_fifo: list[tuple[int, int, int]] = []  # (colour, flags, OAM index) for the next pixels
        self.f_step = 0  # 0 tile, 1 data low, 2 data high, 3 waiting to push
        self.f_dot = 0
        self.t1_x = 0
        self.t1_obj = False
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

    def _fetch_read(
        self, step: int, ticket: list[int], window: bool, col: int, pos: int = 0, obj: bool = False
    ) -> None:
        """The VRAM read of one fetcher step, with the registers as they are *now*; ``ticket``
        collects a tile's [map byte, data low, data high, done]."""
        if not self.is_shadow:  # this PPU only needs the timing, not the data
            if step == 2:
                ticket[3] = 1
            return
        lcdc = self.lcdc
        if step == 0:
            if window:
                base = 0x1C00 if lcdc & 0x40 else 0x1800
                index = base + (self.window_line >> 3) * 32 + (col & 31)
            else:
                base = 0x1C00 if lcdc & 8 else 0x1800
                row = (self.ly + self.scy) & 255
                # this read runs MAP_SHIFT + MAP_READ_DOT - 1 dots after its step's first dot
                ago = MAP_SHIFT + MAP_READ_DOT
                if not col:
                    tile_x = (self.scx_hist[SCX_COL0_DOT - ago] >> 3) & 31
                else:
                    d = SCX_COL_DOT_OBJ if self.penalised else SCX_COL_DOT
                    if obj:  # begun during an object fetch: SameBoy reads after it, SCX at the read
                        d = ago - 1
                    scx = self.scx_hist[d - ago]
                    tile_x = ((scx + pos + 8 - (self.cgb and not obj)) >> 3) & 31
                index = base + (row >> 3) * 32 + tile_x
            ticket[0] = self.vram[index]
            if self.cgb_mode:
                ticket[4] = self.vram[0x2000 + index]  # the tile's attributes, from bank 1
            return
        tile = ticket[0]
        signed = 0x1000 + ((tile ^ 0x80) - 0x80) * 16
        address = tile * 16 if lcdc & 0x10 else signed
        row = self.window_line if window else (self.ly + self.scy) & 255
        attr = ticket[4]
        if attr & 0x40:
            row = 7 - (row & 7)  # vertical flip
        address += (row & 7) * 2 + (step - 1) + (0x2000 if attr & 8 else 0)
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
            if self.f_dot == 1 and step == 0:
                self.t1_x = self.x  # the map column's position is taken on the step's first dot
                if self.skip and self.dropped > (self.scx & 7):
                    # the drop has passed SCX's low bits and will wrap: SameBoy's position went
                    # back by 8 (Gambatte scx_during_m3 scx_0360c0)
                    self.t1_x = self.dropped - 8
                self.t1_obj = self.obj_entry is not None  # ... during an object's fetch
            if self.f_dot == (MAP_READ_DOT, LOW_READ_DOT, HIGH_READ_DOT)[step]:
                if step == 0:
                    self.ticket = [0, 0, 0, 0, 0]
                    self.ticket_col = self.fetch_col
                    self.fetch_col += 1
                args = (step, self.ticket, self.window_active, self.ticket_col, self.t1_x)
                args += (self.t1_obj,)
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
                bits = range(8) if self.ticket[4] & 0x20 else range(7, -1, -1)  # horizontal flip
                self.bg = [(self.ticket, b) for b in bits]
                if self.free_skip:
                    del self.bg[: self.free_skip]
                    self.free_skip = 0
            self.f_step = 0
            self.f_dot = 0

    # ----- objects ------------------------------------------------------------------------

    def _object_dot(self) -> None:
        """One dot of an object fetch; the background fetcher is frozen."""
        self.obj_dots -= 1
        entry = self.obj_entry
        assert entry is not None
        ox, index, tile, flags, oy = entry
        for read_at, is_high in ((self.obj_low_at, 0), (self.obj_high_at, 1)):
            if self.obj_dots == read_at:
                height = 16 if self._lcdc_ago(OBJ_SIZE_LAG) & 4 else 8
                row = self.ly - oy
                if flags & 0x40:
                    row = height - 1 - row
                if height == 16:
                    tile &= 0xFE
                bank = 0x2000 if self.cgb_mode and flags & 8 else 0
                data = self.vram[bank + tile * 16 + row * 2 + is_high]
                if is_high:
                    self.obj_hi = data
                else:
                    self.obj_lo = data
        if self.obj_dots == 0:
            self._merge_object(ox, flags, index)
            self.obj_entry = None

    def _start_object_fetch(self, entry: tuple[int, int, int, int, int]) -> None:
        dots = OBJ_FETCH_DOTS
        if not self.penalised:  # FITTED: the first object on a line costs less
            self.penalised = True
            dots -= FIRST_OBJECT_DISCOUNT_DS if self.cgb_mode and self.double_speed else FIRST_OBJECT_DISCOUNT
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

    def _merge_object(self, ox: int, flags: int, index: int) -> None:
        skip = max(0, 8 - ox)  # the part hanging off the left edge
        fifo = self.obj_fifo
        while len(fifo) < 8 - skip:
            fifo.append((0, 0, 255))
        by_index = self.cgb_mode and not self.opri & 1  # CGB: the lower OAM index wins
        for i in range(skip, 8):
            bit = i if flags & 0x20 else 7 - i
            colour = ((self.obj_lo >> bit) & 1) | (((self.obj_hi >> bit) & 1) << 1)
            slot = i - skip
            if colour and (not fifo[slot][0] or (by_index and index < fifo[slot][2])):
                fifo[slot] = (colour, flags, index)

    def _step_pixel(self) -> None:
        self.m3 += 1
        if self.win_stall:
            self.win_stall -= 1
            return
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
        if self.skip and self.bg and self.dropped == self.scx_hist[-1 - SKIP_LAG] & 7:
            self.skip = 0  # the next pixel is the first one shown
        if self.bg and not self.skip:
            x = self.x
            lag = SHADOW_WX_LAG if self.is_shadow else WX_LAG
            wx = self.wx_hist[-lag] if lag else self.wx
            win_lcdc = self._lcdc_ago(WIN_LAG)
            if (
                self.window_active
                and WX_GLITCH
                and x + 7 == wx
                and wx != self.win_started_wx
                and self.is_shadow
            ):
                # WX reached again after the window started: a colour-0 pixel is pushed (Pan Docs
                # pixel_fifo.md "The Window")
                self.win_started_wx = wx
                self.bg.insert(0, ([0, 0, 0, 1, 0], 0))
            if (
                not self.window_active
                and win_lcdc & 0x20
                and (win_lcdc & 1 or self.cgb_mode)
                and self.wy_hit
                and (x + 7 == wx or (x == 0 and wx < 7))
            ):
                self.window_active = True
                self.win_started_wx = wx
                self.window_used = True
                if self.double_speed and self.penalised:  # an object was fetched before it
                    self.win_stall = WIN_OBJ_STALL_DS
                self.bg = []
                self.f_step = 0
                self.f_dot = 0
                self.fetch_col = 0
                self.free_skip = max(0, 7 - wx)  # hidden window pixels cost no dots
                for _ in range(1 + (WINDOW_EDGE_HEAD if wx < 7 else WINDOW_HEAD)):
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
                self.dropped = (self.dropped + 1) & 7
            else:
                obj = self.obj_fifo.pop(0) if self.obj_fifo else (0, 0, 255)
                d = self.dot
                if self.is_shadow:
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
                if (
                    self.x == SCREEN_W - HBLANK_IRQ_EARLY
                    and self.next_obj >= len(self.line_objs)
                    and not self.line0
                ):
                    self.hblank_early = True  # the HBlank interrupt precedes mode 0 by a few dots
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

    def _rgb(self, palette: bytearray, number: int, colour: int) -> int:
        """RGB555 colour ``colour`` of palette ``number`` in palette RAM."""
        i = number * 8 + colour * 2
        return (palette[i] | (palette[i + 1] << 8)) & 0x7FFF

    def _pixel(self, rec: list) -> int:
        _x, (ticket, bit), (colour, flags, _i), _a, _b, _c, lcdc, bgp, obp0, obp1, _ly = rec
        bg = ((ticket[1] >> bit) & 1) | (((ticket[2] >> bit) & 1) << 1)
        if self.cgb_mode:
            # LCDC.0 clear: the background loses its priority over objects; it is still drawn
            if colour and lcdc & 2 and (not lcdc & 1 or not ((flags | ticket[4]) & 0x80 and bg)):
                return self._rgb(self.obj_pal, flags & 7, colour)
            return self._rgb(self.bg_pal, ticket[4] & 7, bg)
        if not lcdc & 1:
            bg = 0
        if colour and lcdc & 2 and not (flags & 0x80 and bg):
            shade = ((obp1 if flags & 0x10 else obp0) >> (colour * 2)) & 3
            return self._rgb(self.obj_pal, (flags >> 4) & 1, shade) if self.cgb else shade
        shade = (bgp >> (bg * 2)) & 3
        return self._rgb(self.bg_pal, 0, shade) if self.cgb else shade

    @property
    def visible_ly(self) -> int:
        """LY as software reads it: on line 153 it reads 153 for only the first few dots and then
        0 for the rest of the line (Pan Docs STAT.md; Gambatte hwtests/ly0, lyc153int_m2irq)."""
        return 0 if self.ly == LAST_LINE and self.dot >= self.ly153_dots - (2 if self.double_speed else 0) else self.ly

    def _update_stat_line(self) -> None:
        # (and for the first 4 dots of a new line it reads as false: Mooneye lcdon_timing-GS)
        self.lyc_flag = self._lyc_match()
        select = self.stat_select
        oam = bool(select & 0x20 and self._oam_pulse())
        sources = (
            bool(select & 0x40 and (self.lyc_flag or self._lyc_early())),
            bool(
                select & 0x08
                and (
                    (self.read_mode == 0)
                    if self.glitching
                    else (self.mode == 0 or self.hblank_early)
                )
                and not (self.line0 and self.dot < self.mode3_start)
            ),
            bool(select & 0x10 and self.mode == 1),
            oam,
        )
        line = any(sources)
        # without blocking each source's own rising edge interrupts, line held high or not
        rising = (
            line and not self.stat_line
            if self.stat_blocking
            else any(now and not before for now, before in zip(sources, self._sources, strict=True))
        )
        self._sources = sources
        early_dot = DOTS_PER_LINE - OAM_IRQ_EARLY
        if OAM_IRQ_EARLY and select & 0x20 and self.dot == early_dot and not self.stat_line:
            following = 0 if self.ly == LAST_LINE else self.ly + 1
            if 0 < following <= VBLANK_LINE:
                # the interrupt the CPU's dispatch sees a cycle before the line's pulse is real
                self.early_fired = True
                self.irq_halt_delay = OAM_IRQ_EARLY
                self.irq_early_by = OAM_IRQ_EARLY
                self.raise_irq(1)
        line0_dot = DOTS_PER_LINE - EARLY_LINE0_DS
        line0_early = self.double_speed and self.ly == LAST_LINE and self.dot == line0_dot
        if line0_early and select & 0x20 and not self.stat_line:
            self.early_fired = True
            self.irq_halt_delay = self.irq_early_by = EARLY_LINE0_DS
            self.raise_irq(1)
        if rising:
            if self.early_lyc153 and self.ly == LAST_LINE and not oam:
                self.early_lyc153 = False  # already raised, early
            elif self.early_fired and oam:
                self.early_fired = False  # already raised, early
            else:
                # the early HBlank interrupt, like the OAM one, wakes a halted CPU a cycle later
                self.irq_halt_delay = self._halt_delay(oam)
                hblank = select & 0x08 and (self.mode == 0 or self.hblank_early)
                self.irq_early_by = HBLANK_IRQ_EARLY if hblank else 0
                if select & 0x40 and self._lyc_early() and not self.lyc_flag and not hblank:
                    self.irq_early_by = LYC_IRQ_EARLY  # the dispatch sees it before IF does
                if select & 0x10 and self.mode == 1 and self.ly == VBLANK_LINE and self.dot < 4:
                    # the VBlank STAT source: the dispatch sees it on time, IF shows it later
                    self.irq_early_by = MODE1_IRQ_DOT
                    self.irq_halt_delay = 0
                self.raise_irq(1)
        if self.dot == 1:
            self.early_fired = False
            self.early_lyc153 = False
        self.stat_line = line

    def _halt_delay(self, oam: bool) -> int:
        """Dots after its raise at which a halted CPU sees this interrupt: the HBlank one lands
        2 dots after it is raised (GBMicrotest int_hblank_halt_*, Mooneye
        hblank_ly_scx_timing), whether it was raised early or on time."""
        if oam:
            return 0
        if self.hblank_early and self.mode != 0:
            return 2
        return 2 if self.mode == 0 and self.select_has_hblank() else 0

    def select_has_hblank(self) -> bool:
        return bool(self.stat_select & 0x08)

    def _compare_ly(self) -> int:
        """The LY the comparator sees: 153 for line 153's first 8 dots (a read sees it for 4)."""
        if self.ly == LAST_LINE:
            return LAST_LINE if self.dot < 8 else 0
        return self.ly

    def _lyc_match(self) -> bool:
        """The LY=LYC flag: false for 4 dots after the comparator's LY changes (at a line's start,
        and on line 153 at dot 8; line 0 keeps LYC=0's flag across the wrap): GBMicrotest
        line_153_lyc*_stat_timing_*, Mooneye lcdon_timing-GS."""
        dot = self.dot
        if dot < 4 and self.ly != 0:
            return False
        if self.ly == LAST_LINE and 8 <= dot < 12:
            return False
        return self._compare_ly() == self.lyc

    def _lyc_early(self) -> bool:
        """The LY=LYC interrupt comes LYC_IRQ_EARLY dots before the flag (GBMicrotest int_lyc_*)."""
        return (
            self.dot < 4
            and self.dot >= 4 - LYC_IRQ_EARLY
            and self.ly != 0
            and self.visible_ly == self.lyc
        )

    def after_access(self) -> None:
        """Called by the board after each M-cycle's bus access, with the registers as written.
        Line 153's LY=LYC interrupt for LYC=0 reaches the CPU's dispatch at the end of the cycle
        that ends at dot 8, so a LYC write in that cycle still cancels it (GBMicrotest
        line_153_lyc0_int_inc_sled, line_153_lyc_int_b)."""
        if (
            self.ly == LAST_LINE
            and self.dot == 8
            and self.lcd_on
            and self.stat_select & 0x40
            and self.lyc == 0
            and not self.stat_line
        ):
            self.early_lyc153 = True
            self.irq_halt_delay = 0
            self.irq_early_by = LYC_IRQ_EARLY
            self.raise_irq(1)

    def compare_wy(self) -> None:
        """WY==LY is compared whenever either changes, not only at a line's start: a WY written to
        the current line number late in the line still starts the window on the next one
        (Gambatte window/arg/late_wy_*)."""
        if self.cgb and WY_WAIT_CGB:
            self.wy_wait = WY_WAIT_CGB
            return
        self._compare_wy_now()

    def _compare_wy_now(self) -> None:
        if self.lcd_on and self.ly < VBLANK_LINE and self.ly == self.wy:
            self.wy_hit = True

    def _oam_pulse(self) -> bool:
        """The line-start OAM source: a short pulse at dots 0-3 of each line, VBlank's first line
        included (Mooneye vblank_stat_intr-GS, GBMicrotest lcdon_to_oam_int_l1)."""
        return self.dot < OAM_IRQ_WIDTH and self.ly <= VBLANK_LINE and not self.line0

    # ----- registers ----------------------------------------------------------------------

    def read_stat(self) -> int:
        if not self.lcd_on:  # mode 0, the comparison flag frozen
            return 0x80 | self.stat_select | (4 if self.lyc_flag else 0)
        return 0x80 | self.stat_select | (4 if self.lyc_flag else 0) | self.read_mode

    def write_stat(self, value: int) -> None:
        if self.lcd_on and self.stat_write_glitch:
            # DMG: for the write's cycle every source is enabled, so a source that is true raises
            # the interrupt if the line was low (Pan Docs STAT.md; GBMicrotest stat_write_glitch_*)
            saved = self.stat_select
            self.stat_select = 0x78
            self.glitching = True  # the glitch sees the mode as a read does
            self._update_stat_line()
            self.glitching = False
            self.stat_select = saved
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
            if self.shadow is not None:
                self.shadow.lcdc = value
                self.shadow.write_lcdc(value)
            blank = self._blank()  # the screen goes blank (white)
            self.framebuffer[:] = array("H", blank) if self.cgb else blank
            self.frame = blank
        elif not was_on and self.lcd_on:  # LCD on: line 0 starts now, but late
            self.ly = 0
            self.dot = LINE0_START_DOT
            self.line0 = True
            self.mode3_start = MODE2_END
            self.mode = 0  # line 0 starts in mode 0 (Mooneye ppu/lcdon_timing-GS)
            self.skip_scan = True  # and has no OAM scan
            self._settle(0)
            self.wy_hit = self.wy == 0
            if self.shadow is not None:
                self.shadow.wy = self.wy
                self.shadow.write_lcdc(value)
                self._follow()
            self._update_stat_line()

    def _settle(self, mode: int) -> None:
        """Make ``mode`` the current and the lagged mode (a jump, not a transition)."""
        self.mode = self.read_mode = mode
        self._recent = [mode] * MODE_READ_LAG

    def place(self, ly: int, dot: int, mode: int) -> None:
        """Put the beam at a line, dot and mode (the skip-boot hand-off state)."""
        self.ly, self.dot = ly, dot
        self._settle(mode)
        self._follow()
        self._update_stat_line()

    def write_bgp(self, value: int) -> None:
        """DMG: for one dot around a BGP write the palette is the OR of the old and new values
        (Mealybug m3_bgp_change: each band is one pixel wider at both edges)."""
        self.bgp_glitch = (self.dot, self.ly, self.bgp | value)
        self.bgp = value

    # ----- CGB palette RAM ($FF68-$FF6B) ----------------------------------------------------------

    @property
    def palettes_blocked(self) -> bool:
        """Palette RAM is out of reach of the CPU while the LCD is drawing (Pan Docs Palettes.md)."""
        return self.lcd_on and (self.read_mode == 3 or self.pal_hold > 0)

    def read_palette(self, obj: bool) -> int:
        if self.palettes_blocked:
            return 0xFF
        return (self.obj_pal if obj else self.bg_pal)[(self.ocps if obj else self.bcps) & 0x3F]

    def write_palette(self, obj: bool, value: int) -> None:
        spec = self.ocps if obj else self.bcps
        if not self.palettes_blocked:
            (self.obj_pal if obj else self.bg_pal)[spec & 0x3F] = value
        if spec & 0x80:  # auto-increment, even when the write was blocked
            spec = 0x80 | ((spec + 1) & 0x3F)
            if obj:
                self.ocps = spec
            else:
                self.bcps = spec

    def write_lyc(self, value: int) -> None:
        if self.cgb and not self.double_speed and LYC_WAIT_CGB and self.lcd_on:
            self.lyc_wait, self.lyc_next = LYC_WAIT_CGB, value
            return
        self._write_lyc_now(value)

    def _write_lyc_now(self, value: int) -> None:
        self.lyc = value
        if self.lcd_on:
            self._update_stat_line()

    def read_ly(self) -> int:
        if not self.lcd_on:
            return 0
        if LY_LEAD and not self.line0 and self.dot >= DOTS_PER_LINE - LY_LEAD and self.ly < 143:
            return self.ly + 1  # LY reads as the next line a little before it starts
        return self.visible_ly
