"""The DMG's picture: OAM scan and mode 3 as a background fetcher, an object fetcher and two FIFOs.

This machine only draws. STAT, the interrupts and the VRAM/OAM locks keep their timing from
``ppu.PPU`` (fitted to Mooneye and Gambatte); this one runs alongside it, ``DRAW_LAG`` dots behind,
reading the registers, VRAM and OAM as they are on each of its dots, and writes the shades into its
own frame. It is used for DMG hardware only: the CGB's picture is still drawn by the PPU's shadow.

It is a translation of docboy's DMG pixel pipeline (``src/docboy/docboy/ppu/ppu.cpp``, the
``ENABLE_CGB``-off paths; github.com/Docheinstein/docboy, MIT licence, notice below), the emulator
that draws all 24 of Mealybug Tearoom's DMG pictures. What it models, in its words:

* the first fetch of a line is thrown away (dots 80-82), and ``SCX % 8`` pixels are dropped;
* ``lx`` counts from 0 and the first 8 pixels are popped but not shown, so an object at OAM X is
  met at ``lx == X``: objects hanging off the left edge are fetched during those 8 pixels;
* the background fetcher: GetTile (the map address from SCX, SCY, LCDC.3 and its own tile counter;
  the tile number read), GetTileDataLow and GetTileDataHigh (each works out its address from SCY
  and LCDC.4 *at that dot*, so a write between them mixes two rows or two tiles), then Push, which
  waits for an empty FIFO;
* an object due at this ``lx`` is fetched only from the Push step; the tile already fetched is kept
  and pushed after it, and the background FIFO does not move while the object is fetched;
* the window starts when ``lx`` meets WX (seen one dot late), or one pixel late if LCDC.5 was off a
  dot before; each start moves the window a row on; a Push on the dot ``lx == WX`` after the window
  was seen this frame pushes one colour-0 pixel instead;
* a pixel is coloured with LCDC.0/.1 as they were a dot before (except at ``lx == 8``) and with
  ``BGP | the previous dot's BGP`` (Mealybug m3_bgp_change).

docboy, Copyright (c) 2025 Docheinstein. Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to
whom the Software is furnished to do so, subject to the following conditions: The above copyright
notice and this permission notice shall be included in all copies or substantial portions of the
Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gameboy_python.ppu import PPU

SCREEN_W = 160
SCREEN_H = 144
LAST_X = 168  # lx runs 0..167: 8 hidden pixels, then the 160 shown ones
PIXELS_START = 80  # the dot pixel transfer starts at, on every line
DUMMY_DOTS = 3  # the thrown-away first fetch: the FIFO is filled with junk on its last dot


class DmgPixels:
    """The DMG's drawing machine (see the module notes)."""

    def __init__(self, ppu: PPU) -> None:
        self.ppu = ppu  # the registers, VRAM and OAM are read from here, live
        self.framebuffer = bytearray(SCREEN_W * SCREEN_H)
        self.last_bgp = 0
        self.last_wx = 0
        self.last_lcdc = 0
        self.active_for_frame = False  # WY met LY with the window on, at some dot of this frame
        self.wly = 255  # the window's line counter (goes to 0 at its first start)
        self.after_on = False  # the first line after the LCD is turned on has no OAM scan
        self.carry = False  # WX=166: the next line starts inside the window
        self.stage = self._idle
        self.oam_entries: list[list[tuple[int, int]]] = [[] for _ in range(LAST_X)]
        self.scan_count = 0
        self._reset_fetcher()

    # ----- per dot ------------------------------------------------------------------------

    def tick(self, ly: int, dot: int) -> None:
        """One dot at line ``ly``, dot ``dot``."""
        p = self.ppu
        self.ly = ly
        if ly < SCREEN_H:
            if dot == 0:
                if ly == 0:
                    self.wly = 255
                    self.active_for_frame = False
                self.scan_count = 0
                for entries in self.oam_entries:
                    entries.clear()
                self.stage = self._idle
            if dot < 80 and not dot & 1 and not self.after_on:
                self._scan(dot >> 1)
            if dot == PIXELS_START:
                self._reset_fetcher()
                if self.carry:
                    self.carry = False
                    self.wly = (self.wly + 1) & 255
                    self.w_active = True
                    self.win_x = 1
                self.dummy_left = DUMMY_DOTS
                self.stage = self._dummy
            self.stage()
        # the window's WY condition is checked on every dot of the frame
        if not self.active_for_frame and p.lcdc & 0x20 and ly == p.wy:
            self.active_for_frame = True
        self.last_bgp = p.bgp
        self.last_wx = p.wx
        self.last_lcdc = p.lcdc

    def lcd_off(self) -> None:
        self.framebuffer[:] = bytes(SCREEN_W * SCREEN_H)
        self.carry = False
        self._reset_fetcher()
        for entries in self.oam_entries:
            entries.clear()
        self.stage = self._idle

    def lcd_on(self) -> None:
        self.after_on = True
        self.active_for_frame = False
        self.wly = 255

    def line_done(self) -> None:
        self.after_on = False

    # ----- OAM scan -----------------------------------------------------------------------

    def _scan(self, entry: int) -> None:
        if self.scan_count >= 10 or entry >= 40:
            return
        oam = self.ppu.oam
        y = oam[entry * 4]
        height = 16 if self.ppu.lcdc & 4 else 8
        top = y - 16
        if top <= self.ly < top + height:
            x = oam[entry * 4 + 1]
            if x < LAST_X:
                self.oam_entries[x].append((entry, y))
            self.scan_count += 1

    # ----- pixel transfer stages ----------------------------------------------------------

    def _idle(self) -> None:
        pass

    def _reset_fetcher(self) -> None:
        self.lx = 0
        self.popped = False
        self.bg_fifo: list[int] = []  # colour numbers
        self.obj_fifo: list[tuple[int, int, int, int]] = []  # (colour, attributes, entry, x)
        self.push_enabled = False
        self.pending_fill = False
        self.fetching_object = False
        self.w_activating = False
        self.w_active = False
        self.w_just_activated = False
        self.tile_number = 0
        self.map_address = 0
        self.data_address = 0
        self.data_low = 0
        self.data_high = 0
        self.kept: tuple[int, int] | None = None  # a fetched tile held over an object fetch
        self.win_x = 0  # the window fetcher's tile counter
        self.obj_entry = (0, 0)
        self.obj_tile = 0
        self.obj_attrs = 0
        self.discarded = 0
        self.dummy_left = 0
        self.fetch = self._bgwin_tile_0

    def _dummy(self) -> None:
        self.dummy_left -= 1
        if self.dummy_left:
            return
        self.bg_fifo = [0] * 8  # junk: these 8 pixels are never shown
        self.discarded = 0
        self.stage = self._discard
        if self.ppu.scx & 7:
            self._check_window()  # with SCX % 8 > 0 the window can start before the background
            if self.w_activating:
                self.stage = self._discard_wx0

    def _discard(self) -> None:
        """SCX % 8 pixels are dropped (lx does not move). The drop ends when its count meets SCX's
        low bits *now*, not as they were when it began (Gambatte scx_during_m3, hardware;
        SameBoy compares on every dropped pixel; docboy reads SCX once)."""
        if self.discarded == self.ppu.scx & 7:
            self.stage = self._pixels
            self._pixels()
            return
        self._pending_fill()
        if self._can_pop():
            self.bg_fifo.pop(0)
            self.discarded = (self.discarded + 1) & 7
        self.fetch()
        self._push()

    def _discard_wx0(self) -> None:
        self._pending_window()
        self.stage = self._discard  # a window at WX=0 starts a dot late: no fetcher dot here

    def _pixels(self) -> None:
        self._pending_window()
        self._pending_fill()
        popped = False
        if self._can_pop():
            colour = self.bg_fifo.pop(0)
            obj = self.obj_fifo.pop(0) if self.obj_fifo else None
            lx = self.lx
            if lx >= 8:
                p = self.ppu
                lcdc = p.lcdc if lx == 8 else self.last_lcdc
                shade = -1
                if obj is not None and obj[0] and lcdc & 2:
                    if not lcdc & 1 or not colour or not obj[1] & 0x80:
                        palette = p.obp1 if obj[1] & 0x10 else p.obp0
                        shade = (palette >> (obj[0] * 2)) & 3
                if shade < 0:
                    shade = ((p.bgp | self.last_bgp) >> (colour * 2)) & 3 if lcdc & 1 else 0
                self.framebuffer[self.ly * SCREEN_W + lx - 8] = shade
                if lx + 1 == LAST_X:
                    self._next_lx()
                    self.stage = self._idle
                    # WX=166 never opens the window on its own line, but the next line starts
                    # inside it, at its second tile (SameBoy; Gambatte window/on_screen/wxA6_*)
                    self.carry = bool(self.active_for_frame and p.lcdc & 0x20 and p.wx == 166)
                    return
            popped = True
            self._check_window()
        self.popped = popped  # the fetcher sees the position after this dot's pixel
        self.fetch()
        self.popped = False
        self._push()
        if popped:
            self._next_lx()

    def _next_lx(self) -> None:
        self.oam_entries[self.lx].clear()  # objects not fetched at this lx are dropped
        self.lx += 1

    def _can_pop(self) -> bool:
        return bool(
            self.bg_fifo
            and not self.fetching_object
            and (not self.oam_entries[self.lx] or not self.ppu.lcdc & 2)
        )

    def _obj_due(self) -> bool:
        return bool(self.oam_entries[self.lx]) and bool(self.ppu.lcdc & 2)

    def _pending_fill(self) -> None:
        if self.pending_fill:
            self.pending_fill = False
            self.bg_fifo = _row(self.data_low, self.data_high, False)

    def _push(self) -> None:
        """The Push step: into an empty FIFO, or an object fetch from here."""
        if not self.push_enabled or self.fetching_object:
            return
        can_push = not self.bg_fifo
        if can_push:
            if self.active_for_frame and self.lx == self.ppu.wx and not self.w_just_activated:
                self.bg_fifo.append(0)  # the WX glitch: a colour-0 pixel, the tile waits a dot
                return
            self.pending_fill = True
            self.push_enabled = False
            self.fetch = self._bgwin_tile_0
            if self.w_just_activated:  # no object fetch just after the window's first push
                self.w_just_activated = False
                return
        if self._obj_due():
            if not can_push:
                self.kept = (self.data_low, self.data_high)
            self.fetching_object = True
            self.obj_entry = self.oam_entries[self.lx].pop()
            self._obj_tile_0()

    # ----- window -------------------------------------------------------------------------

    def _check_window(self) -> None:
        lx = self.lx
        if (
            self.active_for_frame
            and not self.w_active
            and self.ppu.lcdc & 0x20
            and (lx == self.last_wx or (lx == self.last_wx + 1 and not self.last_lcdc & 0x20))
        ):
            if self.last_wx == 166:  # WX=166 moves the window a row on but does not open it
                self.wly = (self.wly + 1) & 255
                return
            self.w_activating = True
            self.wly = (self.wly + 1) & 255
            self.push_enabled = False
            self.fetch = self._fetch_idle  # the next fetcher dot is lost

    def _pending_window(self) -> None:
        if self.w_activating:
            self.bg_fifo = []
            self.w_active = True
            self.w_just_activated = True
            self.win_x = 0
            self.w_activating = False
            self.fetch = self._bgwin_tile_0

    # ----- background / window fetcher ----------------------------------------------------

    def _fetch_idle(self) -> None:
        pass

    def _bgwin_tile_0(self) -> None:
        if self.w_active:
            if self.ppu.lcdc & 0x20:
                self._win_tile_0()
                return
            self.w_active = False  # the window was turned off: back to the background
        self._bg_tile_0()

    def _bg_tile_0(self) -> None:
        p = self.ppu
        # the map column is worked out from the pixel position (after this dot's pixel) and SCX
        # at this dot, as SameBoy's position_in_line + SCX: a write that changes SCX's low bits
        # mid-line moves the column (Gambatte scx_during_m3, hardware). docboy keeps a tile
        # counter instead, which agrees while SCX stands still.
        tile_x = ((self.lx + self.popped + p.scx) >> 3) & 31
        tile_y = ((self.ly + p.scy) & 255) >> 3
        self.map_address = (0x1C00 if p.lcdc & 8 else 0x1800) + tile_y * 32 + tile_x
        self.tile_number = p.vram[self.map_address]
        self.fetch = self._bg_tile_1

    def _bg_tile_1(self) -> None:
        self.fetch = self._bg_low_0

    def _bg_data_address(self) -> None:
        p = self.ppu
        n = self.tile_number
        base = n * 16 if p.lcdc & 0x10 else 0x1000 + ((n ^ 0x80) - 0x80) * 16
        self.data_address = base + ((self.ly + p.scy) & 7) * 2

    def _bg_low_0(self) -> None:
        self._bg_data_address()
        self.data_low = self.ppu.vram[self.data_address]
        self.fetch = self._bg_low_1

    def _bg_low_1(self) -> None:
        self.fetch = self._bg_high_0

    def _bg_high_0(self) -> None:
        self._bg_data_address()
        self.data_high = self.ppu.vram[self.data_address + 1]
        self.fetch = self._bgwin_high_1

    def _win_tile_0(self) -> None:
        p = self.ppu
        if not p.lcdc & 0x20:
            self._bg_tile_0()
            return
        tile_x = self.win_x & 31
        self.win_x += 1
        self.map_address = (0x1C00 if p.lcdc & 0x40 else 0x1800) + (self.wly >> 3) * 32 + tile_x
        self.tile_number = p.vram[self.map_address]
        self.fetch = self._win_tile_1

    def _win_tile_1(self) -> None:
        if not self.ppu.lcdc & 0x20:
            self._bg_tile_1()
            return
        self.fetch = self._win_low_0

    def _win_data_address(self) -> None:
        p = self.ppu
        n = self.tile_number
        base = n * 16 if p.lcdc & 0x10 else 0x1000 + ((n ^ 0x80) - 0x80) * 16
        self.data_address = base + (self.wly & 7) * 2

    def _win_low_0(self) -> None:
        if not self.ppu.lcdc & 0x20:
            self._bg_low_0()
            return
        self._win_data_address()
        self.data_low = self.ppu.vram[self.data_address]
        self.fetch = self._win_low_1

    def _win_low_1(self) -> None:
        if not self.ppu.lcdc & 0x20:
            self._bg_low_1()
            return
        self.fetch = self._win_high_0

    def _win_high_0(self) -> None:
        if not self.ppu.lcdc & 0x20:
            self._bg_high_0()
            return
        self._win_data_address()
        self.data_high = self.ppu.vram[self.data_address + 1]
        self.fetch = self._bgwin_high_1

    def _bgwin_high_1(self) -> None:
        self.fetch = self._fetch_idle
        self.push_enabled = True

    # ----- object fetcher -----------------------------------------------------------------

    def _obj_tile_0(self) -> None:
        self.fetch = self._obj_tile_1

    def _obj_tile_1(self) -> None:
        oam = self.ppu.oam
        entry = self.obj_entry[0]
        self.obj_tile = oam[entry * 4 + 2]
        self.obj_attrs = oam[entry * 4 + 3] & 0xF0  # the low nibble is the CGB's
        self.fetch = self._obj_low_0

    def _obj_data_address(self) -> None:
        tall = bool(self.ppu.lcdc & 4)
        mask = 15 if tall else 7
        row = (self.ly - (self.obj_entry[1] - 16)) & mask
        if self.obj_attrs & 0x40:
            row ^= mask
        tile = self.obj_tile & 0xFE if tall else self.obj_tile
        self.data_address = tile * 16 + row * 2

    def _obj_low_0(self) -> None:
        self.fetch = self._obj_low_1

    def _obj_low_1(self) -> None:
        self._obj_data_address()
        self.data_low = self.ppu.vram[self.data_address]
        self.fetch = self._obj_high_0

    def _obj_high_0(self) -> None:
        self.fetch = self._obj_high_1

    def _obj_high_1(self) -> None:
        self._obj_data_address()
        self.data_high = self.ppu.vram[self.data_address + 1]
        attrs, number, lx = self.obj_attrs, self.obj_entry[0], self.lx
        colours = _row(self.data_low, self.data_high, bool(attrs & 0x20))
        fifo = self.obj_fifo
        for i, c in enumerate(colours):
            if i < len(fifo):
                old = fifo[i]
                # a new opaque pixel wins over a transparent one, or over an opaque one of an
                # object at the same X that comes later in OAM
                if c and (not old[0] or (old[3] == lx and number < old[2])):
                    fifo[i] = (c, attrs, number, lx)
            else:
                fifo.append((c, attrs, number, lx))
        if self._obj_due():
            self.obj_entry = self.oam_entries[self.lx].pop()
            self.fetch = self._obj_tile_0
        else:
            if self.kept is not None:
                self.data_low, self.data_high = self.kept
                self.kept = None
            self.fetching_object = False
            # back to the Push step with the kept tile; with none kept (the object came on a
            # push into an empty FIFO, which docboy leaves idle) the next tile is fetched
            self.fetch = self._fetch_idle if self.push_enabled else self._bgwin_tile_0


def _row(low: int, high: int, flip: bool) -> list[int]:
    """The 8 colour numbers of a tile row, leftmost first."""
    bits = range(8) if flip else range(7, -1, -1)
    return [((low >> b) & 1) | (((high >> b) & 1) << 1) for b in bits]
