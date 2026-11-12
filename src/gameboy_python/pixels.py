"""The picture: OAM scan and mode 3 as a background fetcher, an object fetcher and two FIFOs.

This machine only draws. STAT, the interrupts and the VRAM/OAM locks keep their timing from
``ppu.PPU`` (fitted to Mooneye and Gambatte); this one runs alongside it, ``DRAW_LAG`` dots behind,
reading the registers, VRAM and OAM as they are on each of its dots, and writes the picture into
its own frame, on DMG and CGB hardware alike (a CGB in its own mode or in the compatibility mode
a DMG cartridge gets, ``cgb_mode`` false).

It is a translation of docboy's pixel pipeline (``src/docboy/docboy/ppu/ppu.cpp``;
github.com/Docheinstein/docboy, MIT licence, notice below), the emulator that draws all of
Mealybug Tearoom's DMG and CGB-D pictures and cgb-acid-hell. What it models, in its words:

* the first fetch of a line is thrown away (dots 80-82), and ``SCX % 8`` pixels are dropped;
* ``lx`` counts from 0 and the first 8 pixels are popped but not shown, so an object at OAM X is
  met at ``lx == X``: objects hanging off the left edge are fetched during those 8 pixels;
* the background fetcher: GetTile (the map address from SCX, SCY, LCDC.3; the tile number read),
  GetTileDataLow and GetTileDataHigh (each works out its address from SCY and LCDC.4 *at that
  dot*, so a write between them mixes two rows or two tiles), then Push, which waits for an
  empty FIFO;
* an object due at this ``lx`` is fetched only from the Push step; the tile already fetched is kept
  and pushed after it, and the background FIFO does not move while the object is fetched;
* the window starts when ``lx`` meets WX, and each start moves the window a row on; a Push on the
  dot ``lx == WX`` after the window was seen this frame pushes one colour-0 pixel instead.

The DMG: WX is seen a dot late, and the window starts a pixel late if LCDC.5 was off a dot before;
a pixel is coloured with LCDC.0/.1 as they were a dot before (except at ``lx == 8``) and with
``BGP | the previous dot's BGP`` (Mealybug m3_bgp_change); with LCDC.0 clear the background's
colour 0 still goes through BGP (Gambatte, SameBoy; docboy draws white).

The CGB: LCDC, SCX, SCY and WX writes reach it ``CGB_REG_DELAY`` dots late (one more in double
speed); no BGP glitch; SCY is taken once per tile, at GetTile; three glitches: TILE_SEL changed
between a data read's two dots, WX met again during a window tile fetch, and the window turned off
on the dot it starts; and, in its own mode, each tile's attributes from VRAM bank 1 (palette,
bank, flips, priority), objects in OAM order, and SameBoy's TILE_SEL glitch (``_number_glitch``).

Not docboy's, and taken from Gambatte's hardware pictures: the map column follows the pixel
position and SCX (``scx_during_m3``), the ``SCX % 8`` drop follows SCX as it changes, and the DMG's
WX=166 rule (see ``_check_window``).

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

from array import array
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gameboy_python.ppu import PPU

SCREEN_W = 160
SCREEN_H = 144
LAST_X = 168  # lx runs 0..167: 8 hidden pixels, then the 160 shown ones
PIXELS_START = 80  # the dot pixel transfer starts at, on every line
DUMMY_DOTS = 3  # the thrown-away first fetch: the FIFO is filled with junk on its last dot
DMA_INDEX_BACK = 1
CGB_REG_DELAY = 2  # CGB: dots before an LCDC, SCX, SCY or WX write reaches the pixel pipeline
CGB_REG_DELAY_DS = 3  # FITTED (Gambatte cgb04c scx_during_m3 *_ds_*): ... in double speed


class Pixels:
    """The drawing machine (see the module notes)."""

    def __init__(self, ppu: PPU) -> None:
        self.ppu = ppu  # the registers, VRAM and OAM are read from here
        self.cgb = ppu.cgb
        self.framebuffer = (
            array("H", [0x7FFF] * (SCREEN_W * SCREEN_H)) if self.cgb else bytearray(SCREEN_W * SCREEN_H)
        )
        # the registers as the pipeline sees them on this dot (the CGB's arrive late)
        self.lcdc = self.scx = self.scy = self.wx = 0
        self.next_lcdc = 0  # CGB: what LCDC will be on the next dot
        # CGB C and older: SCY read again at each tile-data fetch (machines.py; the board sets it)
        self.scy_at_data_fetch = False
        # CGB C and older: a BGP/OBP0/OBP1 write reaches the pixels a dot later (machines.py)
        self.palette_late = False
        self.last_bgp = 0
        self.last_obp0 = self.last_obp1 = 0
        self.last_wx = 0
        self.last_lcdc = 0
        self.active_for_frame = False  # WY met LY with the window on, at some dot of this frame
        self.wly = 255  # the window's line counter (goes to 0 at its first start)
        self.after_on = False  # the first line after the LCD is turned on has no OAM scan
        self.carry = False  # DMG, WX=166: the next line starts inside the window
        self.stage = self._idle
        self.oam_entries: list[list[tuple[int, int]]] = [[] for _ in range(LAST_X)]
        self.scan_count = 0
        self.scan_y = self.scan_x = 0
        # CGB: the last data the fetcher read, for its glitches
        self.last_low = self.last_high = self.last_unsigned = 0
        self.last_fetch = 0
        self.last_fetch_decay = 0
        self._reset_fetcher()

    # ----- per dot ------------------------------------------------------------------------

    def tick(self, ly: int, dot: int) -> None:
        """One dot at line ``ly``, dot ``dot``."""
        p = self.ppu
        if self.cgb:
            d = CGB_REG_DELAY_DS if p.double_speed else CGB_REG_DELAY
            self.lcdc, self.scx = p.lcdc_hist[-1 - d], p.scx_hist[-1 - d]
            self.scy, self.wx = p.scy_hist[-1 - d], p.wx_hist[-1 - d]
            self.next_lcdc = p.lcdc_hist[-d]
        else:
            self.lcdc, self.scx, self.scy, self.wx = p.lcdc, p.scx, p.scy, p.wx
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
        if not self.active_for_frame and self.lcdc & 0x20 and ly == p.wy:
            self.active_for_frame = True
        self.last_bgp = p.bgp
        self.last_obp0, self.last_obp1 = p.obp0, p.obp1
        self.last_wx = self.wx
        self.last_lcdc = self.lcdc

    def lcd_off(self) -> None:
        if self.cgb:
            self.framebuffer[:] = array("H", [0x7FFF] * (SCREEN_W * SCREEN_H))
        else:
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

    def _dma_busy(self) -> bool:
        dma = self.ppu.dma
        return dma is not None and dma.active

    def _scan(self, entry: int) -> None:
        if entry >= 40:
            return
        oam = self.ppu.oam
        if not self._dma_busy():
            # an OAM DMA holds the bus: the scan does not read, and goes on with the Y and X it
            # read last (docboy oam_scan_flush_read_request; strikethrough.gb)
            self.scan_y, self.scan_x = oam[entry * 4], oam[entry * 4 + 1]
        if self.scan_count >= 10:
            return
        y = self.scan_y
        height = 16 if self.lcdc & 4 else 8
        top = y - 16
        if top <= self.ly < top + height:
            x = self.scan_x
            if x < LAST_X:
                self.oam_entries[x].append((entry, y))
            self.scan_count += 1

    # ----- pixel transfer stages ----------------------------------------------------------

    def _idle(self) -> None:
        pass

    def _reset_fetcher(self) -> None:
        self.lx = 0
        self.popped = False
        self.bg_fifo: list[int] = []  # colour number | the tile's CGB attributes << 2
        self.tile_attrs = 0  # CGB mode: the tile's attributes, from VRAM bank 1
        self.obj_fifo: list[tuple[int, int, int, int]] = []  # (colour, attributes, entry, x)
        self.push_enabled = False
        self.pending_fill = False
        self.partial_fill = 0  # CGB: the window-off glitch refills only this many pixels
        self.fetching_object = False
        self.w_activating = False
        self.w_active = False
        self.w_just_activated = False
        self.w_off_while_starting = False  # CGB: the window was turned off on the dot it started
        self.tile_number = 0
        self.tile_scy = 0  # CGB: SCY taken at GetTile
        self.last_fetch_decay = 0  # CGB: the last read is not reused across a line start
        self.map_address = 0
        self.data_address = 0
        self.data_low = 0
        self.data_high = 0
        self.kept: tuple[int, int, int] | None = None  # a fetched tile held over an object fetch
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
        if self.scx & 7:
            self._check_window()  # with SCX % 8 > 0 the window can start before the background
            if self.w_activating:
                self.stage = self._discard_wx0

    def _discard(self) -> None:
        """SCX % 8 pixels are dropped (lx does not move). The drop ends when its count meets SCX's
        low bits *now*, not as they were when it began (Gambatte scx_during_m3, hardware;
        SameBoy compares on every dropped pixel; docboy reads SCX once)."""
        if self.discarded == self.scx & 7:
            self.stage = self._pixels
            self._pixels()
            return
        self._pending_fill()
        if self._can_pop():
            self.bg_fifo.pop(0)
            self.discarded = (self.discarded + 1) & 7
        self._tick_fetcher()
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
                self._colour(colour, obj, lx)
                if lx + 1 == LAST_X:
                    self._next_lx()
                    self.stage = self._idle
                    # DMG: WX=166 never opens the window on its own line, but the next line
                    # starts inside it, at its second tile (SameBoy; Gambatte window/on_screen/
                    # wxA6_*). The CGB starts the window at 166 as at any other WX (docboy).
                    self.carry = not self.cgb and bool(
                        self.active_for_frame and self.lcdc & 0x20 and self.wx == 166
                    )
                    return
            popped = True
            self._check_window()
        self.popped = popped  # the fetcher sees the position after this dot's pixel
        self._tick_fetcher()
        self.popped = False
        if self.cgb and (self.w_activating or self.w_just_activated) and self._disabling_window():
            self.push_enabled = True  # CGB: the window turned off as it starts pushes at once
        self._push()
        if popped:
            self._next_lx()

    def _colour(self, pixel: int, obj: tuple[int, int, int, int] | None, lx: int) -> None:
        p = self.ppu
        colour = pixel & 3
        i = self.ly * SCREEN_W + lx - 8
        if self.cgb:
            lcdc = self.lcdc
        else:
            lcdc = self.lcdc if lx == 8 else self.last_lcdc  # LCDC.0/.1 a dot late, but at lx 8
        if p.cgb_mode:
            # CGB mode: LCDC.0 clear takes the background's priority away, it still draws; a
            # background pixel of colour 1-3 is over the object when either asks for it
            attrs = pixel >> 2
            if obj is not None and obj[0] and lcdc & 2:
                if not lcdc & 1 or not colour or not ((attrs | obj[1]) & 0x80):
                    self.framebuffer[i] = p._rgb(p.obj_pal, obj[1] & 7, obj[0])
                    return
            self.framebuffer[i] = p._rgb(p.bg_pal, attrs & 7, colour)
            return
        if obj is not None and obj[0] and lcdc & 2:
            if not lcdc & 1 or not colour or not obj[1] & 0x80:
                if self.palette_late:
                    obp = self.last_obp1 if obj[1] & 0x10 else self.last_obp0
                else:
                    obp = p.obp1 if obj[1] & 0x10 else p.obp0
                shade = (obp >> (obj[0] * 2)) & 3
                self.framebuffer[i] = p._rgb(p.obj_pal, (obj[1] >> 4) & 1, shade) if self.cgb else shade
                return
        if self.cgb:
            bgp = self.last_bgp if self.palette_late else p.bgp
            shade = (bgp >> (colour * 2)) & 3 if lcdc & 1 else 0
            self.framebuffer[i] = p._rgb(p.bg_pal, 0, shade)
        else:
            # LCDC.0 clear: the background's colour number is 0, still looked up in BGP (Gambatte
            # ppu.cpp tileword, SameBoy; Megami Tensei Gaiden: Last Bible II fades this way).
            # docboy and Pan Docs draw white, which is the same for the usual BGP
            if not lcdc & 1:
                colour = 0
            self.framebuffer[i] = ((p.bgp | self.last_bgp) >> (colour * 2)) & 3

    def _next_lx(self) -> None:
        self.oam_entries[self.lx].clear()  # objects not fetched at this lx are dropped
        self.lx += 1

    def _can_pop(self) -> bool:
        return bool(
            self.bg_fifo
            and not self.fetching_object
            and (not self.oam_entries[self.lx] or not self.lcdc & 2)
        )

    def _obj_due(self) -> bool:
        return bool(self.oam_entries[self.lx]) and bool(self.lcdc & 2)

    def _pending_fill(self) -> None:
        if self.pending_fill:
            self.pending_fill = False
            self.bg_fifo = self._tile_row()
        elif self.partial_fill:
            # CGB, the window turned off as it starts: the FIFO's pixels left are overwritten
            # with whatever the fetcher holds
            size, self.partial_fill = self.partial_fill, 0
            self.bg_fifo = self._tile_row()[:size]

    def _tile_row(self) -> list[int]:
        attrs = self.tile_attrs
        return _row(self.data_low, self.data_high, bool(attrs & 0x20), attrs)

    def _push(self) -> None:
        """The Push step: into an empty FIFO, or an object fetch from here."""
        if not self.push_enabled or self.fetching_object:
            return
        can_push = not self.bg_fifo
        if can_push:
            if (
                self.active_for_frame
                and self.lx == self.wx
                and not self.w_just_activated
                and (self.w_active or not self.cgb)
            ):
                self.bg_fifo.append(0)  # the WX glitch: a colour-0 pixel, the tile waits a dot
                return
            self.pending_fill = True
            self._push_off()
            self.fetch = self._bgwin_tile_0
            if self.w_just_activated:  # no object fetch just after the window's first push
                self.w_just_activated = False
                return
        if self._obj_due():
            if not can_push:
                self.kept = (self.data_low, self.data_high, self.tile_attrs)
            self.fetching_object = True
            self.obj_entry = self.oam_entries[self.lx].pop()
            self._obj_tile_0()

    def _push_off(self) -> None:
        self.push_enabled = False

    def _tick_fetcher(self) -> None:
        if self.last_fetch_decay:
            self.last_fetch_decay -= 1
        self.fetch()

    # ----- window -------------------------------------------------------------------------

    def _disabling_window(self) -> bool:
        """CGB: a write turning the window off reaches the pipeline on the next dot."""
        return self.next_lcdc != self.lcdc and not self.next_lcdc & 0x20

    def _check_window(self) -> None:
        lx = self.lx
        if not (self.active_for_frame and not self.w_active and self.lcdc & 0x20):
            return
        if self.cgb:
            if lx != self.wx:
                return
        elif not (lx == self.last_wx or (lx == self.last_wx + 1 and not self.last_lcdc & 0x20)):
            return
        if not self.cgb and self.last_wx == 166:
            # DMG: WX=166 moves the window a row on but does not open it (SameBoy)
            self.wly = (self.wly + 1) & 255
            return
        self.w_activating = True
        self.wly = (self.wly + 1) & 255
        self._push_off()
        if self.cgb and self._disabling_window():
            self.w_off_while_starting = True  # the fetcher is not held this time
            return
        self.fetch = self._fetch_idle  # the next fetcher dot is lost

    def _pending_window(self) -> None:
        if self.w_activating:
            if self.cgb and not self.lcdc & 0x20:
                # CGB: turned off on the dot it started: the background goes on, and the FIFO's
                # pixels left are refilled with what the fetcher holds (all 8 if it is empty)
                self.partial_fill = len(self.bg_fifo) or 8
                self.w_off_while_starting = False
            else:
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
            if self.lcdc & 0x20:
                self._win_tile_0()
                return
            self.w_active = False  # the window was turned off: back to the background
        self._bg_tile_0()

    def _bg_tile_0(self) -> None:
        # the map column is worked out from the pixel position and SCX at this dot, as SameBoy's
        # position_in_line + SCX: a write that changes SCX's low bits mid-line moves the column
        # (Gambatte scx_during_m3, hardware; docboy keeps a tile counter, which agrees while SCX
        # stands still). The DMG counts the pixel popped on this dot, the CGB does not.
        position = self.lx if self.cgb else self.lx + self.popped
        tile_x = ((position + self.scx) >> 3) & 31
        tile_y = ((self.ly + self.scy) & 255) >> 3
        self.map_address = (0x1C00 if self.lcdc & 8 else 0x1800) + tile_y * 32 + tile_x
        if self.cgb and (self.w_off_while_starting or self.last_fetch_decay == 1):
            self.tile_number = self.last_fetch  # CGB: the window-off glitch reuses the last read
        else:
            self._read_tile_number()
        self.tile_scy = self.scy
        self.fetch = self._bg_tile_1

    def _bg_tile_1(self) -> None:
        self.fetch = self._bg_low_0

    def _data_base(self) -> int:
        n = self.tile_number
        return n * 16 if self.lcdc & 0x10 else 0x1000 + ((n ^ 0x80) - 0x80) * 16

    def _bg_data_address(self) -> None:
        # the CGB D and E take SCY once, at GetTile; the DMG and CGB C and older read it again here
        scy = self.tile_scy if self.cgb and not self.scy_at_data_fetch else self.scy
        row = (self.ly + scy) & 7
        attrs = self.tile_attrs
        if attrs & 0x40:  # CGB mode: vertical flip
            row ^= 7
        self.data_address = self._data_base() + row * 2 + (0x2000 if attrs & 8 else 0)

    def _bg_low_0(self) -> None:
        self._bg_data_address()
        if self.cgb and self.w_off_while_starting:
            self.data_low = self.last_fetch
        else:
            self._read_low()
        self.fetch = self._bg_low_1

    def _bg_low_1(self) -> None:
        if self.cgb:
            self._sel_glitch(self._bg_data_address, high=False)
        self.fetch = self._bg_high_0

    def _bg_high_0(self) -> None:
        self._bg_data_address()
        if self.cgb and self.w_off_while_starting:
            self.data_high = self.last_fetch
        else:
            self._read_high()
        self.fetch = self._bg_high_1

    def _bg_high_1(self) -> None:
        if self.cgb:
            self._sel_glitch(self._bg_data_address, high=True)
        self._bgwin_high_1()

    def _win_tile_0(self) -> None:
        if not self.lcdc & 0x20:
            self._bg_tile_0()
            return
        tile_x = self.win_x & 31
        self.win_x += 1
        self.map_address = (0x1C00 if self.lcdc & 0x40 else 0x1800) + (self.wly >> 3) * 32 + tile_x
        if not (self.cgb and self.lx == self.wx):  # CGB: WX met again keeps the last tile
            self._read_tile_number()
        self.fetch = self._win_tile_1

    def _win_tile_1(self) -> None:
        if not self.lcdc & 0x20:
            self._bg_tile_1()
            return
        self.fetch = self._win_low_0

    def _win_data_address(self) -> None:
        row = self.wly & 7
        attrs = self.tile_attrs
        if attrs & 0x40:  # CGB mode: vertical flip
            row ^= 7
        self.data_address = self._data_base() + row * 2 + (0x2000 if attrs & 8 else 0)

    def _win_low_0(self) -> None:
        if not self.lcdc & 0x20:
            self._bg_low_0()
            return
        self._win_data_address()
        if self.cgb and self.lx == self.wx:
            self.data_low = self.last_high  # CGB: WX met again: the last high byte instead
        else:
            self._read_low()
        self.fetch = self._win_low_1

    def _win_low_1(self) -> None:
        if not self.lcdc & 0x20:
            self._bg_low_1()
            return
        if self.cgb:
            self._sel_glitch(self._win_data_address, high=False)
        self.fetch = self._win_high_0

    def _win_high_0(self) -> None:
        if not self.lcdc & 0x20:
            self._bg_high_0()
            return
        self._win_data_address()
        if self.cgb and self.lx == self.wx:
            self.data_high = self.last_low  # CGB: WX met again: the last low byte instead
        else:
            self._read_high()
        self.fetch = self._win_high_1

    def _win_high_1(self) -> None:
        if self.cgb:
            self._sel_glitch(self._win_data_address, high=True)
        self._bgwin_high_1()

    def _bgwin_high_1(self) -> None:
        self.fetch = self._fetch_idle
        self.push_enabled = True

    def _sel_glitch(self, address, high: bool) -> None:
        """CGB: LCDC.4 changed between a data read's two dots. Cleared: the read is made again
        with the signed address; set: the data is the last read made with unsigned addresses
        (an object's, maybe), for tiles in $9000-$97FF only (docboy; Mealybug
        m3_lcdc_tile_sel_change, CGB D)."""
        if self.last_lcdc & 0x10 and not self.lcdc & 0x10:
            address()
            self._read_high() if high else self._read_low()
        elif not self.last_lcdc & 0x10 and self.lcdc & 0x10 and not self.data_address & 0x800:  # bit 11 of the address in its bank
            if high:
                self.data_high = self.last_unsigned
            else:
                self.data_low = self.last_unsigned

    # ----- VRAM reads ---------------------------------------------------------------------

    def _read_tile_number(self) -> None:
        self.tile_number = self.ppu.vram[self.map_address]
        self.tile_attrs = self.ppu.vram[0x2000 + self.map_address] if self.ppu.cgb_mode else 0
        if self.cgb:
            self.data_high = self.tile_number  # the CGB's tile number and high byte share a latch
            self.last_fetch, self.last_fetch_decay = self.tile_number, 2

    def _number_glitch(self) -> bool:
        """CGB mode, single speed: a background data read on the dot LCDC.4's fall reaches the
        pipeline returns the tile's number, for numbers below $80 (SameBoy
        data_for_tile_sel_glitch; cgb-acid-hell, column 80)."""
        p = self.ppu
        if not (p.cgb_mode and not p.double_speed and self.tile_number < 0x80):
            return False
        h = p.lcdc_hist
        k = CGB_REG_DELAY
        return bool(h[-2 - k] & ~h[-1 - k] & 0x10)

    def _read_low(self, obj: bool = False) -> None:
        if not obj and self._number_glitch():
            self.data_low = self.tile_number
            return
        self.data_low = value = self.ppu.vram[self.data_address]
        if self.cgb:
            self.last_low = value
            if obj or self.lcdc & 0x10:
                self.last_unsigned = value
            self.last_fetch, self.last_fetch_decay = value, 2

    def _read_high(self, obj: bool = False) -> None:
        if not obj and self._number_glitch():
            self.data_high = self.tile_number
            return
        self.data_high = value = self.ppu.vram[self.data_address + 1]
        if self.cgb:
            self.last_high = value
            if obj or self.lcdc & 0x10:
                self.last_unsigned = value
            self.last_fetch, self.last_fetch_decay = value, 2

    # ----- object fetcher -----------------------------------------------------------------

    def _obj_tile_0(self) -> None:
        self.fetch = self._obj_tile_1

    def _obj_tile_1(self) -> None:
        oam = self.ppu.oam
        address = self.obj_entry[0] * 4 + 2
        if self._dma_busy():
            # the PPU does not drive OAM's address while a DMA writes: the read gets the pair of
            # bytes at the DMA's address (docboy OamBus::read_word_request; strikethrough.gb)
            address = (self.ppu.dma.index - DMA_INDEX_BACK) & 0xFE
        self.obj_tile = oam[address]
        self.obj_attrs = oam[address + 1]
        if not self.ppu.cgb_mode:
            self.obj_attrs &= 0xF0  # the low nibble is a CGB game's
        self.fetch = self._obj_low_0

    def _obj_data_address(self) -> None:
        tall = bool(self.lcdc & 4)
        mask = 15 if tall else 7
        row = (self.ly - (self.obj_entry[1] - 16)) & mask
        if self.obj_attrs & 0x40:
            row ^= mask
        tile = self.obj_tile & 0xFE if tall else self.obj_tile
        self.data_address = tile * 16 + row * 2 + (0x2000 if self.obj_attrs & 8 else 0)

    def _obj_low_0(self) -> None:
        self.fetch = self._obj_low_1

    def _obj_low_1(self) -> None:
        self._obj_data_address()
        self._read_low(obj=True)
        self.fetch = self._obj_high_0

    def _obj_high_0(self) -> None:
        self.fetch = self._obj_high_1

    def _obj_high_1(self) -> None:
        self._obj_data_address()
        self._read_high(obj=True)
        attrs, number, lx = self.obj_attrs, self.obj_entry[0], self.lx
        colours = _row(self.data_low, self.data_high, bool(attrs & 0x20), 0)
        by_x = not self.cgb or self.ppu.opri & 1  # the CGB in its own mode: OAM order only
        fifo = self.obj_fifo
        for i, c in enumerate(colours):
            if i < len(fifo):
                old = fifo[i]
                # a new opaque pixel wins over a transparent one, or over an opaque one of an
                # object at the same X (any X, by OAM order) that comes later in OAM
                if c and (not old[0] or ((old[3] == lx or not by_x) and number < old[2])):
                    fifo[i] = (c, attrs, number, lx)
            else:
                fifo.append((c, attrs, number, lx))
        if self._obj_due():
            self.obj_entry = self.oam_entries[self.lx].pop()
            self.fetch = self._obj_tile_0
        else:
            if self.kept is not None:
                self.data_low, self.data_high, self.tile_attrs = self.kept
                self.kept = None
            self.fetching_object = False
            # back to the Push step with the kept tile; with none kept (the object came on a
            # push into an empty FIFO, which docboy leaves idle) the next tile is fetched
            self.fetch = self._fetch_idle if self.push_enabled else self._bgwin_tile_0


def _row(low: int, high: int, flip: bool, attrs: int) -> list[int]:
    """The 8 colour numbers of a tile row, leftmost first, each with ``attrs << 2`` added."""
    bits = range(8) if flip else range(7, -1, -1)
    tag = attrs << 2
    return [((low >> b) & 1) | (((high >> b) & 1) << 1) | tag for b in bits]
