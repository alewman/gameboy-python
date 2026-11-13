"""The Super Game Boy, high-level: what the SGB's SNES program does with a Game Boy's packets.

A real Super Game Boy is a Game Boy on a SNES cartridge. The ICD2 chip between them hands the
SNES each LCD line and each 16-byte command packet the Game Boy sends through P1, and drives the
Game Boy's joypad input lines; the SNES program (the "SGB BIOS", Nintendo's, in the SGB's ROM)
reads the packets, keeps the palettes, the attribute map and the border, and draws the picture.
snes-python runs that program for real (its ``sgb.py``, the low-level SGB). This module does its
job directly, for a player that cannot run a SNES: docs/sgb.md is the transcriber's guide.

Use::

    gb = GameBoy(cartridge, MACHINES["sgb"], boot_rom=...)
    sgb = SuperGameBoy(gb)        # takes the joypad and PPU taps; nothing else changes
    gb.run_frames(600)
    words = sgb.render()          # 256 x 224 SNES colours (BGR555), rows top to bottom

Only a Game Boy with an attached ``SuperGameBoy`` runs any of this: the DMG and CGB rows, and an
``sgb`` row without one, behave exactly as before.

Two layers, kept apart:

- **ICD2** (hardware; the same rules as snes-python's ``sgb.py``, which passes Mooneye's SGB
  boot tests and shows the real BIOS's pictures): the packet receiver on P1 writes (Pan Docs
  SGB_Command_Packet.md: a both-low start pulse, 128 bits LSB first, P14 low = 0, P15 low = 1,
  both lines high between bits, a 0 stop bit) and the multiplayer ID (Pan Docs
  SGB_Command_Multiplayer.md: with no packet coming, each P15 low-to-high edge selects the next
  player; with both lines high the input lines read $F minus the player).
- **BIOS** (high level): packets gathered into commands (the first packet's low 3 bits count
  them, 1-7) and each command's effect (Pan Docs SGB_Command_*.md, SGB_VRAM_Transfer.md,
  SGB_Color_Palettes.md, CC0). Behaviour seen in SameBoy's HLE SGB (Core/sgb.c, Expat; read,
  not copied) is cited where it settled a detail the documents leave open.

The picture is the SNES's: 256 x 224, the Game Boy's 160 x 144 at (48, 40), colourised through
four 4-colour palettes picked per 8 x 8 cell by the attribute map, under a border of 4bpp tiles
in palettes 4-6. Colours are SNES words, ``0bbbbbgggggrrrrr``. Colour 0 is the backdrop: every
shade-0 Game Boy pixel and every transparent border pixel shows ``cgram[0]``.

Not modelled (docs/sgb.md "Out of scope"): the BIOS's own border artwork, built-in palettes,
menus, boot animation and fades; SOUND/SOU_TRN; DATA_SND/DATA_TRN/JUMP (SNES code and data);
OBJ_TRN; ICON_EN, ATRC_EN, TEST_EN, PAL_PRI (accepted, no effect). Commands act the moment their
last packet's stop bit arrives; the real BIOS takes frames.
"""

from __future__ import annotations

from array import array

from gameboy_python.board import GameBoy

SNES_W, SNES_H = 256, 224
GB_W, GB_H = 160, 144
#: the Game Boy picture's top-left corner in the border's 256 x 232 layer (tiles 6-25, rows 5-22)
WINDOW_X, WINDOW_Y = 48, 40
#: the screen's line 0 shows the layers' line 1: the BIOS leaves BG1VOFS at 0 and the S-PPU
#: draws lines VOFS+1 to VOFS+224 (Pan Docs SGB_Command_Border.md). snes-python running the
#: real BIOS agrees: its picture is this one's, one line up, 0 pixels off (docs/sgb.md).
FIRST_LINE = 1
#: ... so the last screen line would show the map's 29th row; the BIOS blanks it (INIDISP $80)
#: almost always (Pan Docs SGB_Command_Border.md; snes-python: black in every settled frame of
#: Pokemon Red and Kirby's Dream Land 2). It is drawn black here.
BLANK_LINES = 1
CELLS_W, CELLS_H = 20, 18  # attribute cells (8 x 8 pixels each)
BORDER_ROWS = 29  # PCT_TRN's map: 28 rows and the extra one (Pan Docs SGB_Command_Border.md)

#: the default palettes (all four): a neutral grey ramp, white to black. The real BIOS starts
#: from its built-in palette 1-A, which is Nintendo's data and not reproduced (docs/sgb.md); a
#: frontend may pass other colours (``SuperGameBoy(gb, palette=...)``). Games that never send a
#: palette (Tetris DX) keep this one, so their Game Boy picture differs from a real SGB's.
GREY_RAMP = (0x7FFF, 0x56B5, 0x294A, 0x0000)

#: MLT_REQ's byte 1 (bits 1-0) -> the mask on the player number: one, two, (two), four players.
#: 2 is undocumented and taken as 3 (as snes-python's ICD2 model does for $6003 bits 5-4).
PLAYER_MASK = (0, 1, 3, 3)

#: the joypad's button names -> bit of an ICD2 pad byte (Start Select B A Down Up Left Right,
#: 0 = pressed; snes-python sgb.py $6004-$6007)
PAD_BITS = {
    "right": 0,
    "left": 1,
    "up": 2,
    "down": 3,
    "a": 4,
    "b": 5,
    "select": 6,
    "start": 7,
}

# command codes (Pan Docs SGB_Command_Summary.md)
PAL01, PAL23, PAL03, PAL12 = 0x00, 0x01, 0x02, 0x03
ATTR_BLK, ATTR_LIN, ATTR_DIV, ATTR_CHR = 0x04, 0x05, 0x06, 0x07
PAL_SET, PAL_TRN = 0x0A, 0x0B
MLT_REQ = 0x11
CHR_TRN, PCT_TRN, ATTR_TRN, ATTR_SET, MASK_EN = 0x13, 0x14, 0x15, 0x16, 0x17
#: the commands from $1E up are the boot ROM's header packets ($F1, $F3 ... $FB), which the
#: BIOS reads to decide whether the game may use SGB commands at all
HEADER_CODE = 0x1E

# MASK_EN modes (Pan Docs SGB_Command_System.md)
MASK_OFF, MASK_FREEZE, MASK_BLACK, MASK_COLOR0 = 0, 1, 2, 3

# what a pending VRAM transfer fills
TRN_NONE, TRN_PAL, TRN_ATTR, TRN_CHR_LOW, TRN_CHR_HIGH, TRN_PCT = 0, 1, 2, 3, 4, 5
#: frame starts from the command to the transfer: the frame in progress when the packet ends,
#: then one whole frame drawn after it, whose picture is the data (Pan Docs SGB_VRAM_Transfer.md:
#: "the actual transfer starts at the beginning of the next frame after the command")
TRANSFER_DELAY = 2
TRANSFER_BYTES = 4096  # 256 tiles of the screen, 16 bytes each
ATF_BYTES = 90  # one attribute file: 18 rows of 20 two-bit cells
ATF_COUNT = 45  # $00-$2C

#: save_state's layout, in order: (name, kind, length). Kinds: "u8" one integer (or bool),
#: "bytes" a bytearray, "words" an array of u16 (little-endian). Plain data for a transcriber.
STATE_LAYOUT = (
    ("p1", "u8", 1),
    ("receiving", "u8", 1),
    ("wait_high", "u8", 1),
    ("bit_count", "u8", 1),
    ("packet", "bytes", 16),
    ("players", "u8", 1),
    ("player", "u8", 1),
    ("pads", "bytes", 4),
    ("command", "bytes", 112),
    ("packets_due", "u8", 1),
    ("packets_got", "u8", 1),
    ("header", "bytes", 84),
    ("enabled", "u8", 1),
    ("lcd", "bytes", GB_W * GB_H),
    ("shown", "bytes", GB_W * GB_H),
    ("mask", "u8", 1),
    ("transfer", "u8", 1),
    ("transfer_wait", "u8", 1),
    ("cgram", "words", 128),
    ("system_palettes", "words", 512 * 4),
    ("attr_map", "bytes", CELLS_W * CELLS_H),
    ("attr_files", "bytes", ATF_BYTES * ATF_COUNT),
    ("tiles", "bytes", 256 * 32),
    ("tiles_pending", "bytes", 256 * 32),
    ("border_map", "words", 32 * BORDER_ROWS),
    ("border_loaded", "u8", 1),
)
STATE_VERSION = 1


class SuperGameBoy:
    """The ICD2 and an HLE of the SGB's SNES program, attached to one Game Boy."""

    def __init__(self, gb: GameBoy, palette: tuple[int, int, int, int] = GREY_RAMP) -> None:
        if gb.machine.model not in ("sgb", "sgb2"):
            raise ValueError(
                f"a Super Game Boy needs an sgb or sgb2 machine, not {gb.machine.name}"
            )
        self.gb = gb
        # -- the ICD2: packet receiver, players, pads
        # the last select bits written (bits 5-4). The SGB boot ROM leaves the ICD2 at $30 (both
        # lines high after its header packets); skip-boot starts after the boot ROM, so it starts
        # there too: from the board's skip-boot select ($00) a game's first start pulse ($00)
        # would look like no change and its first packet (Pokemon Red's MLT_REQ check) be lost
        self.p1 = gb.joypad.select if gb.boot_mapped else 0x30
        self.receiving = False
        self.wait_high = False  # a pulse was seen: both lines must go high before the next bit
        self.bit_count = 0
        self.packet = bytearray(16)
        self.players = 0  # MLT_REQ's byte 1, bits 1-0
        self.player = 0  # the selected player, 0-3
        self.pads = bytearray(b"\xff\xff\xff\xff")  # per player, 0 = pressed
        # -- the BIOS: commands
        self.command = bytearray(16 * 7)
        self.packets_due = 0  # packets in the command being gathered
        self.packets_got = 0
        self.header = bytearray(84)  # $0104-$0157 as the boot ROM's header packets carry it
        # commands are obeyed only for a header with the SGB flag ($0146 = 3) and the new
        # licensee code ($014B = $33); the header packets decide it again when a boot ROM runs
        rom = gb.cartridge.rom
        self.enabled = rom[0x146] == 0x03 and rom[0x14B] == 0x33
        # -- the picture
        self.lcd = bytearray(GB_W * GB_H)  # the LCD's shades as lines end
        self.shown = bytearray(GB_W * GB_H)  # the last whole frame, or the frozen one
        self.mask = MASK_OFF
        self.transfer = TRN_NONE
        self.transfer_wait = 0
        # the SNES's palettes: 0-3 the Game Boy's (colours 0-3 used), 4-6 the border's, 7 unused
        self.cgram = array("H", bytes(256))
        for number in range(4):
            for shade in range(4):
                self.cgram[number * 16 + shade] = palette[shade]
        self.system_palettes = array("H", bytes(512 * 4 * 2))  # PAL_TRN's 512 x 4 colours
        self.attr_map = bytearray(CELLS_W * CELLS_H)  # palette 0-3 per cell
        self.attr_files = bytearray(ATF_BYTES * ATF_COUNT)  # ATTR_TRN's 45 files
        self.tiles = bytearray(256 * 32)  # the border's 4bpp tiles, as shown
        self.tiles_pending = bytearray(256 * 32)  # CHR_TRN's, shown from the next PCT_TRN
        self.border_map = array("H", bytes(32 * BORDER_ROWS * 2))
        self.border_loaded = False  # before any PCT_TRN the border area is black
        self.ppu = gb.ppu
        gb.joypad.on_write = self.p1_write
        gb.ppu.line_out = self.lcd_line
        gb.ppu.frame_start = self.lcd_frame
        self._update_lines()

    # ----- the ICD2 --------------------------------------------------------------------

    def p1_write(self, select: int) -> None:
        """Every P1 write's select bits (bits 5-4): packets, and the next player."""
        before = self.p1
        if select == before:
            return
        self.p1 = select
        if select == 0x00:  # the start pulse
            self.receiving = True
            self.wait_high = True
            self.bit_count = 0
            for i in range(16):
                self.packet[i] = 0
        elif self.wait_high:
            self.wait_high = False
            if select != 0x30:  # a bit without both lines high first: not a packet
                self.receiving = False
        elif self.receiving:
            bit = 1 if select == 0x10 else 0  # P15 low: 1; P14 low: 0
            if self.bit_count == 128:  # the stop bit
                self.receiving = False
                if bit == 0:
                    self.receive_packet(self.packet)
            else:
                if bit:
                    self.packet[self.bit_count >> 3] |= 1 << (self.bit_count & 7)
                self.bit_count += 1
                self.wait_high = True
        elif not before & 0x20 and select & 0x20:  # P15 low to high: the next player
            self.player = (self.player + 1) & PLAYER_MASK[self.players]
        self._update_lines()

    def _update_lines(self) -> None:
        """Drive P1's input lines: the selected player's pad, or its ID with both lines high."""
        pad = self.pads[self.player]
        select = self.p1
        lines = 0x0F - self.player if select == 0x30 else 0x0F
        if not select & 0x10:  # directions
            lines &= pad & 0x0F
        if not select & 0x20:  # buttons
            lines &= pad >> 4
        self.gb.joypad.set_external(lines)

    def set_pressed(self, name: str, down: bool, player: int = 0) -> None:
        """A host button change on one of the SNES pads (names as gameboy_python.joypad's)."""
        bit = 1 << PAD_BITS[name]
        if down:
            self.pads[player] &= ~bit & 0xFF
        else:
            self.pads[player] |= bit
        self._update_lines()

    # ----- the LCD ---------------------------------------------------------------------

    def lcd_line(self, shades: bytes) -> None:
        """PPU.line_out: one visible line's 160 shades, as it ends (the PPU's LY is its line)."""
        start = self.ppu.ly * GB_W
        self.lcd[start : start + GB_W] = shades

    def lcd_frame(self) -> None:
        """PPU.frame_start: line 0 begins, so the last frame is whole in ``lcd``."""
        if self.mask != MASK_FREEZE:
            self.shown[:] = self.lcd
        if self.transfer_wait:
            self.transfer_wait -= 1
            if self.transfer_wait == 0:
                self._finish_transfer()

    def screen_data(self) -> bytearray:
        """The first 4 KiB of the screen read back as Game Boy tiles (Pan Docs
        SGB_VRAM_Transfer.md): tile n is cell (n mod 20, n div 20), 16 bytes, two bit planes per
        row with the leftmost pixel in bit 7, as the ICD2 packs its row buffers."""
        data = bytearray(TRANSFER_BYTES)
        lcd = self.lcd
        for tile in range(TRANSFER_BYTES // 16):
            x0 = (tile % CELLS_W) * 8
            y0 = (tile // CELLS_W) * 8
            for row in range(8):
                low = high = 0
                at = (y0 + row) * GB_W + x0
                for x in range(8):
                    shade = lcd[at + x]
                    low = low << 1 | shade & 1
                    high = high << 1 | shade >> 1 & 1
                data[tile * 16 + row * 2] = low
                data[tile * 16 + row * 2 + 1] = high
        return data

    # ----- commands --------------------------------------------------------------------

    def receive_packet(self, packet: bytes | bytearray) -> None:
        """One 16-byte packet from the ICD2: the first of a command, or the next of one."""
        if self.packets_got == self.packets_due:  # a new command
            count = packet[0] & 7
            if packet[0] >> 3 >= HEADER_CODE:
                count = 1  # a header packet is one packet: its low bits are its index
            if count == 0:
                return  # a zero length: ignored (SameBoy ignores it too)
            for i in range(len(self.command)):
                self.command[i] = 0
            self.packets_due = count
            self.packets_got = 0
        at = self.packets_got * 16
        self.command[at : at + 16] = packet
        self.packets_got += 1
        if self.packets_got == self.packets_due:
            self.packets_due = self.packets_got = 0
            self.execute(self.command)

    def execute(self, c: bytearray) -> None:
        """A whole command: header byte (code x 8 + packets), then its data."""
        code = c[0] >> 3
        if code >= HEADER_CODE:
            self._header_packet(c)
            return
        if not self.enabled:
            return
        if code == PAL01:
            self._pal_pair(c, 0, 1)
        elif code == PAL23:
            self._pal_pair(c, 2, 3)
        elif code == PAL03:
            self._pal_pair(c, 0, 3)
        elif code == PAL12:
            self._pal_pair(c, 1, 2)
        elif code == ATTR_BLK:
            self._attr_blk(c)
        elif code == ATTR_LIN:
            self._attr_lin(c)
        elif code == ATTR_DIV:
            self._attr_div(c)
        elif code == ATTR_CHR:
            self._attr_chr(c)
        elif code == PAL_SET:
            self._pal_set(c)
        elif code == PAL_TRN:
            self._start_transfer(TRN_PAL)
        elif code == MLT_REQ:
            self.players = c[1] & 3
            self.player &= PLAYER_MASK[self.players]
            self._update_lines()
        elif code == CHR_TRN:
            self._start_transfer(TRN_CHR_HIGH if c[1] & 1 else TRN_CHR_LOW)
        elif code == PCT_TRN:
            self._start_transfer(TRN_PCT)
        elif code == ATTR_TRN:
            self._start_transfer(TRN_ATTR)
        elif code == ATTR_SET:
            self._apply_atf(c[1] & 0x3F)
            if c[1] & 0x40:
                self.mask = MASK_OFF
        elif code == MASK_EN:
            self.mask = c[1] & 3
        # anything else (SOUND, SOU_TRN, DATA_SND, DATA_TRN, JUMP, OBJ_TRN, ICON_EN, ATRC_EN,
        # TEST_EN, PAL_PRI, $1A-$1D): no effect here

    def _header_packet(self, c: bytearray) -> None:
        """$F1, $F3 ... $FB: the boot ROM sends $0104-$014F, 14 bytes a packet (byte 1 is a
        checksum, not checked here). After $FB the BIOS knows whether to obey the game."""
        if c[0] & 0xF1 != 0xF1 or not self.gb.boot_mapped:
            return
        index = c[0] >> 1 & 7
        if index > 5:
            return
        self.header[index * 14 : index * 14 + 14] = c[2:16]
        if c[0] == 0xFB:
            self.enabled = self.header[0x146 - 0x104] == 0x03 and self.header[0x14B - 0x104] == 0x33

    def _set_color0(self, color: int) -> None:
        """Colour 0 is shared: it is the backdrop for every palette (Pan Docs
        SGB_Color_Palettes.md "Color 0 Restriction")."""
        for palette in range(4):
            self.cgram[palette * 16] = color

    def _pal_pair(self, c: bytearray, first: int, second: int) -> None:
        """PAL01/PAL23/PAL03/PAL12: colour 0, then colours 1-3 of two palettes."""
        self._set_color0(c[1] | c[2] << 8)
        for i in range(3):
            self.cgram[first * 16 + 1 + i] = (c[3 + 2 * i] | c[4 + 2 * i] << 8) & 0x7FFF
            self.cgram[second * 16 + 1 + i] = (c[9 + 2 * i] | c[10 + 2 * i] << 8) & 0x7FFF

    def _pal_set(self, c: bytearray) -> None:
        """PAL_SET: four system palettes (9-bit IDs) into palettes 0-3; palette 0's colour 0
        becomes the shared one. Byte 9: bit 7 apply ATF (bits 5-0), bit 6 cancel MASK_EN."""
        for palette in range(4):
            number = (c[1 + 2 * palette] | c[2 + 2 * palette] << 8) & 0x1FF
            for shade in range(1, 4):
                self.cgram[palette * 16 + shade] = self.system_palettes[number * 4 + shade]
            if palette == 0:
                self._set_color0(self.system_palettes[number * 4])
        flags = c[9]
        if flags & 0x80:
            self._apply_atf(flags & 0x3F)
        if flags & 0x40:
            self.mask = MASK_OFF

    def _apply_atf(self, number: int) -> None:
        """ATTR_SET (and PAL_SET's flag): attribute file ``number`` becomes the map; numbers
        above $2C are invalid and change nothing (Pan Docs)."""
        if number >= ATF_COUNT:
            return
        base = number * ATF_BYTES
        for cell in range(CELLS_W * CELLS_H):
            byte = self.attr_files[base + cell // 4]
            self.attr_map[cell] = byte >> (6 - 2 * (cell % 4)) & 3  # first cell in bits 7-6

    def _attr_blk(self, c: bytearray) -> None:
        """ATTR_BLK: rectangles, each with palettes for its inside, its edge (the surrounding
        character line) and its outside. Changing only the inside or only the outside changes
        the edge too, to the same palette (Pan Docs). At most 18 data sets fit in 7 packets."""
        count = min(c[1], 18)
        for n in range(count):
            at = 2 + n * 6
            control, palettes = c[at], c[at + 1]
            left, top, right, bottom = (
                c[at + 2] & 31,
                c[at + 3] & 31,
                c[at + 4] & 31,
                c[at + 5] & 31,
            )
            inside, edge, outside = control & 1, control & 2, control & 4
            inside_pal, edge_pal, outside_pal = palettes & 3, palettes >> 2 & 3, palettes >> 4 & 3
            if inside and not edge and not outside:
                edge, edge_pal = 2, inside_pal
            elif outside and not edge and not inside:
                edge, edge_pal = 2, outside_pal
            for y in range(CELLS_H):
                for x in range(CELLS_W):
                    if x < left or x > right or y < top or y > bottom:
                        if outside:
                            self.attr_map[y * CELLS_W + x] = outside_pal
                    elif left < x < right and top < y < bottom:
                        if inside:
                            self.attr_map[y * CELLS_W + x] = inside_pal
                    elif edge:
                        self.attr_map[y * CELLS_W + x] = edge_pal

    def _attr_lin(self, c: bytearray) -> None:
        """ATTR_LIN: whole rows or columns, one byte each (bits 4-0 line, 6-5 palette, bit 7
        horizontal); later ones overwrite earlier ones; lines off the screen do nothing."""
        count = min(c[1], len(c) - 2)
        for n in range(count):
            data = c[2 + n]
            line, palette = data & 31, data >> 5 & 3
            if data & 0x80:  # a horizontal line: a row of cells
                if line < CELLS_H:
                    for x in range(CELLS_W):
                        self.attr_map[line * CELLS_W + x] = palette
            elif line < CELLS_W:  # a vertical line: a column of cells
                for y in range(CELLS_H):
                    self.attr_map[y * CELLS_W + line] = palette

    def _attr_div(self, c: bytearray) -> None:
        """ATTR_DIV: split at one row (bit 6 set) or column; cells before the line take bits
        3-2, the line bits 5-4, cells after it bits 1-0."""
        after, before, on = c[1] & 3, c[1] >> 2 & 3, c[1] >> 4 & 3
        rows = c[1] & 0x40
        line = c[2] & 31
        for y in range(CELLS_H):
            for x in range(CELLS_W):
                at = y if rows else x
                palette = before if at < line else on if at == line else after
                self.attr_map[y * CELLS_W + x] = palette

    def _attr_chr(self, c: bytearray) -> None:
        """ATTR_CHR: two-bit palettes for consecutive cells from (x, y), the first in bits 7-6,
        left to right (byte 5 = 0) or top to bottom (1), wrapping at the screen's edge. It stops
        at the last cell; a start off the screen does nothing (both as SameBoy, unverified)."""
        x, y = c[1], c[2]
        count = min(c[3] | c[4] << 8, CELLS_W * CELLS_H, (len(c) - 6) * 4)
        down = c[5] & 1
        if x >= CELLS_W or y >= CELLS_H:
            return
        for n in range(count):
            self.attr_map[y * CELLS_W + x] = c[6 + n // 4] >> (6 - 2 * (n % 4)) & 3
            if down:
                y += 1
                if y == CELLS_H:
                    y, x = 0, x + 1
                    if x == CELLS_W:
                        return
            else:
                x += 1
                if x == CELLS_W:
                    x, y = 0, y + 1
                    if y == CELLS_H:
                        return

    # ----- VRAM transfers ----------------------------------------------------------------

    def _start_transfer(self, kind: int) -> None:
        self.transfer = kind
        self.transfer_wait = TRANSFER_DELAY

    def _finish_transfer(self) -> None:
        data = self.screen_data()
        kind = self.transfer
        self.transfer = TRN_NONE
        if kind == TRN_PAL:  # 512 palettes x 4 colours
            for i in range(512 * 4):
                self.system_palettes[i] = (data[2 * i] | data[2 * i + 1] << 8) & 0x7FFF
        elif kind == TRN_ATTR:  # 45 attribute files, 90 bytes each ($FD2-$FFF unused)
            self.attr_files[:] = data[: ATF_BYTES * ATF_COUNT]
        elif kind == TRN_CHR_LOW:  # tiles $00-$7F
            self.tiles_pending[0:4096] = data
        elif kind == TRN_CHR_HIGH:  # tiles $80-$FF
            self.tiles_pending[4096:8192] = data
        elif kind == TRN_PCT:
            # $000-$73F: the map, 29 rows of 32 entries; $800-$85F: palettes 4-6
            for i in range(32 * BORDER_ROWS):
                self.border_map[i] = data[2 * i] | data[2 * i + 1] << 8
            for i in range(48):
                self.cgram[64 + i] = (data[0x800 + 2 * i] | data[0x801 + 2 * i] << 8) & 0x7FFF
            self.tiles[:] = self.tiles_pending
            self.border_loaded = True

    # ----- the picture -------------------------------------------------------------------

    def border_pixel(self, x: int, y: int) -> int:
        """The border's colour index at SNES pixel (x, y): 0 transparent, else palette * 16 +
        colour (map entry: bits 7-0 tile, 12-10 palette, 14 X flip, 15 Y flip; Pan Docs
        SGB_Command_Border.md). Tile numbers from $100 up are taken as transparent."""
        entry = self.border_map[(y >> 3) * 32 + (x >> 3)]
        if entry & 0x0300:
            return 0
        row = y & 7
        if entry & 0x8000:
            row = 7 - row
        bit = 7 - (x & 7)
        if entry & 0x4000:
            bit = 7 - bit
        base = (entry & 0xFF) * 32 + row * 2
        tiles = self.tiles
        color = (
            (tiles[base] >> bit & 1)
            | (tiles[base + 1] >> bit & 1) << 1
            | (tiles[base + 16] >> bit & 1) << 2
            | (tiles[base + 17] >> bit & 1) << 3
        )
        if color == 0:
            return 0
        return (entry >> 10 & 7) * 16 + color

    def render(self) -> array:
        """The SNES picture: 256 x 224 BGR555 words, rows top to bottom."""
        out = array("H", bytes(SNES_W * SNES_H * 2))
        cgram = self.cgram
        backdrop = cgram[0]
        shown = self.shown
        for screen_y in range(SNES_H - BLANK_LINES):  # the blanked lines stay 0
            y = screen_y + FIRST_LINE
            gy = y - WINDOW_Y
            for x in range(SNES_W):
                index = self.border_pixel(x, y) if self.border_loaded else 0
                gx = x - WINDOW_X
                if index:
                    color = cgram[index]
                elif 0 <= gx < GB_W and 0 <= gy < GB_H:
                    if self.mask == MASK_BLACK:
                        color = 0
                    elif self.mask == MASK_COLOR0:
                        color = backdrop
                    else:
                        shade = shown[gy * GB_W + gx]
                        palette = self.attr_map[(gy >> 3) * CELLS_W + (gx >> 3)]
                        color = cgram[palette * 16 + shade] if shade else backdrop
                elif self.border_loaded:
                    color = backdrop
                else:
                    color = 0
                out[screen_y * SNES_W + x] = color
        return out

    # ----- save states -------------------------------------------------------------------

    def save_state(self) -> bytes:
        """Everything above as one blob, in STATE_LAYOUT's order, after a version byte."""
        out = bytearray([STATE_VERSION])
        for name, kind, length in STATE_LAYOUT:
            value = getattr(self, name)
            if kind == "u8":
                out.append(int(value))
            elif kind == "bytes":
                assert len(value) == length
                out += value
            else:  # words
                assert len(value) == length
                for word in value:
                    out += bytes((word & 0xFF, word >> 8))
        return bytes(out)

    def load_state(self, data: bytes) -> None:
        if data[0] != STATE_VERSION:
            raise ValueError(f"SGB state version {data[0]}, expected {STATE_VERSION}")
        at = 1
        for name, kind, length in STATE_LAYOUT:
            if kind == "u8":
                value = data[at]
                at += 1
                current = getattr(self, name)
                setattr(self, name, bool(value) if isinstance(current, bool) else value)
            elif kind == "bytes":
                getattr(self, name)[:] = data[at : at + length]
                at += length
            else:
                words = getattr(self, name)
                for i in range(length):
                    words[i] = data[at + 2 * i] | data[at + 2 * i + 1] << 8
                at += 2 * length
        self._update_lines()


def rgb_bytes(words: array) -> bytes:
    """SNES words as 8-bit RGB, each 5-bit channel widened ``c << 3 | c >> 2`` (as
    snes-python's video.picture does, so the two pictures compare byte for byte)."""
    widen = bytes((c << 3 | c >> 2) for c in range(32))
    out = bytearray(len(words) * 3)
    for i, word in enumerate(words):
        out[3 * i] = widen[word & 31]
        out[3 * i + 1] = widen[word >> 5 & 31]
        out[3 * i + 2] = widen[word >> 10 & 31]
    return bytes(out)


__all__ = ["SNES_H", "SNES_W", "SuperGameBoy", "rgb_bytes"]
