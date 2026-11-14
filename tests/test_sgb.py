"""The HLE Super Game Boy (sgb.py): synthetic packets through P1 writes and synthetic LCD lines
through the PPU taps, no ROMs; then one game, where a No-Intro set is at $NO_INTRO_DIR."""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from gameboy_python import MACHINES, GameBoy, load_cartridge
from gameboy_python.sgb import (
    BORDER_ROWS,
    FADE_DELAY_FRAMES,
    FADE_END_TICK,
    FADE_IN_TICK,
    FADE_TICK_FRAMES,
    FIRST_LINE,
    GREY_RAMP,
    SNES_FRAME_T,
    SNES_W,
    WINDOW_X,
    WINDOW_Y,
    SuperGameBoy,
    rgb_bytes,
)


def cartridge(sgb_flag: int = 0x03, licensee: int = 0x33) -> bytes:
    rom = bytearray(0x8000)
    rom[0x100:0x104] = b"\x00\xc3\x00\x01"  # nop; jp $0100
    rom[0x146] = sgb_flag
    rom[0x14B] = licensee
    return bytes(rom)


def machine(model: str = "sgb", boot: bytes | None = None, **header) -> SuperGameBoy:
    gb = GameBoy(load_cartridge(cartridge(**header)), MACHINES[model], boot_rom=boot)
    return SuperGameBoy(gb)


def send(sgb: SuperGameBoy, data: bytes, stop: int = 0) -> None:
    """One 16-byte packet as a game sends it: start pulse, 128 bits LSB first, stop bit."""
    assert len(data) == 16
    write = sgb.gb.joypad.write
    write(0x30)
    write(0x00)
    write(0x30)
    for bit in [byte >> n & 1 for byte in data for n in range(8)] + [stop]:
        write(0x10 if bit else 0x20)
        write(0x30)


def command(sgb: SuperGameBoy, code: int, data: bytes) -> None:
    """A command of as many packets as its data needs (header byte = code * 8 + packets)."""
    packets = max(1, -(-(len(data) + 1) // 16))
    body = bytes([code << 3 | packets]) + data
    body += bytes(packets * 16 - len(body))
    for n in range(packets):
        send(sgb, body[n * 16 : n * 16 + 16])


def show(sgb: SuperGameBoy, shades: bytes, frames: int = 1) -> None:
    """Draw ``shades`` (160 x 144) as whole LCD frames, as the PPU taps deliver them."""
    for _ in range(frames):
        for y in range(144):
            sgb.ppu.ly = y
            sgb.lcd_line(shades[y * 160 : y * 160 + 160])
        sgb.lcd_frame()


def pixel(words, x: int, y: int) -> int:
    """The SNES picture at layer coordinates (the screen shows the layers from line 1)."""
    return words[(y - FIRST_LINE) * SNES_W + x]


def gb_pixel(words, x: int, y: int) -> int:
    return pixel(words, WINDOW_X + x, WINDOW_Y + y)


def le(*words: int) -> bytes:
    return b"".join(w.to_bytes(2, "little") for w in words)


def tiles_screen(data: bytes) -> bytes:
    """The 160 x 144 shades that carry ``data`` (up to 4 KiB) by VRAM transfer: tile n of the
    data at cell (n mod 20, n div 20), as a game shows $8000-$8FFF with BGP $E4."""
    data = data + bytes(4096 - len(data))
    shades = bytearray(160 * 144)
    for tile in range(256):
        for row in range(8):
            low, high = data[tile * 16 + row * 2], data[tile * 16 + row * 2 + 1]
            for x in range(8):
                shade = (low >> (7 - x) & 1) | (high >> (7 - x) & 1) << 1
                shades[((tile // 20) * 8 + row) * 160 + (tile % 20) * 8 + x] = shade
    return bytes(shades)


def transfer(sgb: SuperGameBoy, code: int, data: bytes, arg: int = 0) -> None:
    """A *_TRN command and the frames that carry its data."""
    command(sgb, code, bytes([arg]))
    show(sgb, tiles_screen(data), frames=2)


def wait(sgb: SuperGameBoy, snes_frames: int) -> None:
    """Let SNES frames pass on the Game Boy's clock (the fade's time), no LCD frames drawn."""
    sgb.gb.t += snes_frames * SNES_FRAME_T
    sgb.run_fade()


def fade_through(sgb: SuperGameBoy) -> None:
    """Wait out a whole border fade (the new border is then shown at its own colours)."""
    wait(sgb, FADE_DELAY_FRAMES + FADE_END_TICK * FADE_TICK_FRAMES)
    assert not sgb.fading


# ----- attaching ------------------------------------------------------------------------


def test_only_an_sgb_machine_takes_one() -> None:
    gb = GameBoy(load_cartridge(cartridge()), MACHINES["dmg"])
    with pytest.raises(ValueError):
        SuperGameBoy(gb)
    assert machine("sgb2").enabled


def test_power_on_picture_is_greys_in_a_black_border() -> None:
    sgb = machine()
    show(sgb, bytes([0, 1, 2, 3] * 40 * 144))
    words = sgb.render()
    assert len(words) == 256 * 224
    assert [gb_pixel(words, x, 0) for x in range(4)] == list(GREY_RAMP)
    assert pixel(words, 0, 1) == 0 and pixel(words, 255, 224) == 0


# ----- the ICD2 -------------------------------------------------------------------------


def test_a_bad_stop_bit_drops_the_packet() -> None:
    sgb = machine()
    command(sgb, 0x17, b"\x02")  # MASK_EN black
    assert sgb.mask == 2
    send(sgb, bytes([0x17 << 3 | 1, 0]) + bytes(14), stop=1)
    assert sgb.mask == 2


def test_mlt_req_and_the_player_id() -> None:
    sgb = machine()
    joypad = sgb.gb.joypad
    joypad.write(0x30)
    assert joypad.read() & 0x0F == 0x0F  # one player: player 1's ID
    joypad.write(0x10)
    joypad.write(0x30)
    assert joypad.read() & 0x0F == 0x0F  # one player: P15's edge changes nothing
    command(sgb, 0x11, b"\x01")  # two players
    joypad.write(0x30)
    joypad.write(0x10)
    joypad.write(0x30)
    assert joypad.read() & 0x0F == 0x0E  # player 2
    joypad.write(0x10)
    joypad.write(0x30)
    assert joypad.read() & 0x0F == 0x0F  # back to player 1
    command(sgb, 0x11, b"\x03")  # four players
    for expected in (0x0E, 0x0D, 0x0C, 0x0F):
        joypad.write(0x10)
        joypad.write(0x30)
        assert joypad.read() & 0x0F == expected


def test_pads_drive_the_input_lines() -> None:
    sgb = machine()
    joypad = sgb.gb.joypad
    sgb.set_pressed("a", True)
    sgb.set_pressed("left", True)
    joypad.write(0x10)  # buttons
    assert joypad.read() & 0x0F == 0b1110
    joypad.write(0x20)  # directions
    assert joypad.read() & 0x0F == 0b1101
    sgb.set_pressed("a", False)
    joypad.write(0x10)
    assert joypad.read() & 0x0F == 0x0F


# ----- palettes and attributes ----------------------------------------------------------


def test_pal01_and_the_shared_colour_0() -> None:
    sgb = machine()
    command(sgb, 0x00, le(0x1111, 0x0001, 0x0002, 0x0003, 0x0011, 0x0012, 0x0013))
    command(sgb, 0x01, le(0x2222, 0x0021, 0x0022, 0x0023, 0x0031, 0x0032, 0x0033))  # PAL23
    command(sgb, 0x06, bytes([0b0100_0100 | 3 << 4, 9]))  # ATTR_DIV: rows; 9 is the line
    # cells above row 9: palette 1; row 9: 3; below: 0
    show(sgb, bytes([0, 1, 2, 3] * 40 * 144))
    words = sgb.render()
    assert gb_pixel(words, 0, 0) == 0x2222  # colour 0 is the last one sent, for all palettes
    assert [gb_pixel(words, x, 0) for x in (1, 2, 3)] == [0x0011, 0x0012, 0x0013]
    assert [gb_pixel(words, x, 72) for x in (1, 2, 3)] == [0x0031, 0x0032, 0x0033]
    assert [gb_pixel(words, x, 80) for x in (1, 2, 3)] == [0x0001, 0x0002, 0x0003]
    assert pixel(words, 0, 1) == 0  # no border loaded yet: black


def test_attr_blk_inside_edge_outside_and_the_exception() -> None:
    sgb = machine()
    # set 1: outside only, palette 3, rectangle (31,31)-(31,31): every cell is outside it
    # set 2: inside only, palette 1, rectangle (2,2)-(5,5): the edge follows the inside
    # set 3: edge only, palette 2, rectangle (10,10)-(12,12)
    sets = bytes([4, 3 << 4, 31, 31, 31, 31, 1, 1, 2, 2, 5, 5, 2, 2 << 2, 10, 10, 12, 12])
    command(sgb, 0x04, bytes([3]) + sets)  # 19 data bytes: two packets
    cells = sgb.attr_map
    assert cells[0] == 3 and cells[19 * 1 + 17 * 20] == 3
    assert cells[2 * 20 + 2] == 1 and cells[3 * 20 + 3] == 1 and cells[5 * 20 + 5] == 1
    assert cells[6 * 20 + 6] == 3
    assert cells[10 * 20 + 10] == 2 and cells[12 * 20 + 11] == 2
    assert cells[11 * 20 + 11] == 3  # the inside of an edge-only block is unchanged


def test_attr_lin_and_attr_chr() -> None:
    sgb = machine()
    command(sgb, 0x05, bytes([2, 0x80 | 1 << 5 | 4, 2 << 5 | 7]))  # row 4 -> 1, column 7 -> 2
    assert sgb.attr_map[4 * 20 + 0] == 1 and sgb.attr_map[4 * 20 + 7] == 2
    assert sgb.attr_map[0 * 20 + 7] == 2 and sgb.attr_map[0] == 0
    # ATTR_CHR from (18, 0), left to right, 4 cells 3,2,1,0: wraps to row 1
    command(sgb, 0x07, bytes([18, 0, 4, 0, 0, 0b11_10_01_00]))
    assert [sgb.attr_map[18], sgb.attr_map[19], sgb.attr_map[20], sgb.attr_map[21]] == [3, 2, 1, 0]
    command(sgb, 0x07, bytes([0, 16, 3, 0, 1, 0b11_11_11_00]))  # top to bottom from (0, 16)
    assert [sgb.attr_map[16 * 20], sgb.attr_map[17 * 20], sgb.attr_map[1]] == [3, 3, 3]


def test_pal_trn_attr_trn_and_pal_set() -> None:
    sgb = machine()
    colours = bytearray(4096)
    colours[7 * 8 : 7 * 8 + 8] = le(0x0100, 0x0101, 0x0102, 0x0103)  # system palette 7
    colours[300 * 8 : 300 * 8 + 8] = le(0x0200, 0x0201, 0x0202, 0x0203)  # 300: a 9-bit ID
    transfer(sgb, 0x0B, bytes(colours))  # PAL_TRN
    assert sgb.system_palettes[7 * 4 + 2] == 0x0102
    files = bytearray(4050)
    files[3 * 90 : 4 * 90] = bytes([0b01_10_11_00]) * 90  # ATF 3: cells 1,2,3,0 repeating
    transfer(sgb, 0x15, bytes(files))  # ATTR_TRN
    command(sgb, 0x17, b"\x01")  # MASK_EN freeze
    # PAL_SET: palettes 0-3 = 7, 300, 7, 300; apply ATF 3, cancel the mask
    command(sgb, 0x0A, le(7, 300, 7, 300) + bytes([0x80 | 0x40 | 3]))
    assert sgb.mask == 0
    assert sgb.attr_map[:4] == bytes([1, 2, 3, 0])
    show(sgb, bytes([1] * 160 * 144))
    words = sgb.render()
    assert gb_pixel(words, 0, 0) == 0x0201  # cell 0: palette 1 = system 300
    assert gb_pixel(words, 8, 0) == 0x0101  # cell 1: palette 2 = system 7
    assert sgb.cgram[0] == sgb.cgram[48] == 0x0100  # colour 0 from palette 0's system palette


# ----- the border, the mask ---------------------------------------------------------------


def test_chr_trn_pct_trn_border() -> None:
    sgb = machine()
    tile = bytearray(32)
    tile[0:2] = b"\x80\x00"  # row 0: the leftmost pixel colour 1 (plane 0)
    tile[16:18] = b"\x00\x80"  # ... and colour 9 in its plane 3: colour 1 | 8 = 9
    chr_data = bytes(32) + bytes(tile)  # tile 1
    transfer(sgb, 0x13, chr_data, arg=0)  # CHR_TRN, tiles $00-$7F
    assert not sgb.border_loaded  # tiles alone show nothing until a PCT_TRN
    pct = bytearray(4096)
    entries = [0] * (32 * BORDER_ROWS)
    entries[0] = 1 | 4 << 10  # row 0, column 0: tile 1, palette 4
    entries[1] = 1 | 5 << 10 | 0x4000 | 0x8000  # column 1: flipped both ways, palette 5
    entries[5 * 32 + 6] = 1 | 6 << 10  # over the Game Boy window's first cell
    pct[0 : 2 * len(entries)] = le(*entries)
    pct[0x800 + 9 * 2 : 0x800 + 9 * 2 + 2] = le(0x4444)  # palette 4, colour 9
    pct[0x820 + 9 * 2 : 0x820 + 9 * 2 + 2] = le(0x5555)  # palette 5
    pct[0x840 + 9 * 2 : 0x840 + 9 * 2 + 2] = le(0x6666)  # palette 6
    command(sgb, 0x00, le(0x0123))  # colour 0: the backdrop
    transfer(sgb, 0x14, bytes(pct))  # PCT_TRN
    fade_through(sgb)
    assert sgb.border_loaded
    words = sgb.render()
    assert pixel(words, 0, 1) == 0x0123  # row 1 of tile 1 is transparent: the backdrop
    assert pixel(words, 1, 1) == 0x0123
    assert pixel(words, 15, 7) == 0x5555  # flipped: row 7, rightmost pixel
    assert pixel(words, 8, 7) == 0x0123
    assert pixel(words, WINDOW_X, WINDOW_Y) == 0x6666  # the border covers the Game Boy picture
    # the layers' line 0 is not on the screen: the screen starts at line 1
    assert words[0] == 0x0123


def one_tile_border(sgb: SuperGameBoy, color: int, tile_number: int = 1) -> None:
    """CHR_TRN then PCT_TRN: map entry 0 is tile ``tile_number``, whose pixel (0, 1) is colour
    9 of palette 4, which is ``color``; the rest is transparent tile 0. Layer line 0 is off the
    screen, hence row 1."""
    tile = bytearray(32)
    tile[2:4] = b"\x80\x00"
    tile[18:20] = b"\x00\x80"
    transfer(sgb, 0x13, bytes(32 * tile_number) + bytes(tile))
    pct = bytearray(4096)
    pct[0:2] = le(tile_number | 4 << 10)
    pct[0x800 + 9 * 2 : 0x800 + 9 * 2 + 2] = le(color)
    transfer(sgb, 0x14, bytes(pct))


def test_the_border_fades_out_then_in() -> None:
    """The BIOS's fade as measured on the low-level SGB (docs/sgb.md "The border fade"): every
    other SNES frame each channel of palettes 4-6 steps by one, the old border down to black
    (32 steps), five steps' pause, then the new border up from black (33 steps)."""
    sgb = machine()
    one_tile_border(sgb, 0x7FFF)  # white
    fade_through(sgb)
    assert pixel(sgb.render(), 0, 1) == 0x7FFF
    one_tile_border(sgb, 25 | 10 << 5 | 3 << 10, tile_number=2)  # a new border (r 25 g 10 b 3)
    assert pixel(sgb.render(), 0, 1) == 0x7FFF  # not yet
    wait(sgb, FADE_DELAY_FRAMES - 1)
    assert pixel(sgb.render(), 0, 1) == 0x7FFF
    wait(sgb, 1)  # tick 1: the old border, each channel down by one
    assert pixel(sgb.render(), 0, 1) == 30 | 30 << 5 | 30 << 10
    wait(sgb, 29 * FADE_TICK_FRAMES)  # tick 30
    assert pixel(sgb.render(), 0, 1) == 1 | 1 << 5 | 1 << 10
    wait(sgb, 1)  # half a tick: no step
    assert pixel(sgb.render(), 0, 1) == 1 | 1 << 5 | 1 << 10
    wait(sgb, 1)  # tick 31: black, and stays black until the new border
    assert pixel(sgb.render(), 0, 1) == 0
    assert sgb.border_map[0] & 0xFF == 1  # still the old map
    wait(sgb, (FADE_IN_TICK - 1 - 31) * FADE_TICK_FRAMES)
    assert sgb.fade_tick == FADE_IN_TICK - 1 and pixel(sgb.render(), 0, 1) == 0
    wait(sgb, FADE_TICK_FRAMES)  # the new border, each channel at most 1
    assert sgb.border_map[0] & 0xFF == 2
    assert pixel(sgb.render(), 0, 1) == 1 | 1 << 5 | 1 << 10
    wait(sgb, 9 * FADE_TICK_FRAMES)  # fade-in step 10: blue has reached its 3
    assert pixel(sgb.render(), 0, 1) == 10 | 10 << 5 | 3 << 10
    wait(sgb, (FADE_END_TICK - FADE_IN_TICK - 10) * FADE_TICK_FRAMES)
    assert sgb.fading and pixel(sgb.render(), 0, 1) == 25 | 10 << 5 | 3 << 10
    wait(sgb, FADE_TICK_FRAMES)  # tick 70: over
    assert not sgb.fading
    words = sgb.render()
    assert pixel(words, 0, 1) == 25 | 10 << 5 | 3 << 10
    assert words[(WINDOW_Y - FIRST_LINE) * SNES_W + WINDOW_X] == GREY_RAMP[0]  # window: no fade


def test_the_first_border_comes_out_of_black() -> None:
    """From power-on (boot ROM or skip-boot) there is no border to fade out: black until the
    new border's fade-in, which starts at the same time as after any other border."""
    sgb = machine()
    one_tile_border(sgb, 0x7FFF)
    wait(sgb, FADE_DELAY_FRAMES + (FADE_IN_TICK - 2) * FADE_TICK_FRAMES)
    assert not sgb.border_loaded and pixel(sgb.render(), 0, 1) == 0
    wait(sgb, FADE_TICK_FRAMES)
    assert sgb.border_loaded and pixel(sgb.render(), 0, 1) == 1 | 1 << 5 | 1 << 10


def test_commands_hold_the_fade_up_and_the_lcd_does_not_drive_it() -> None:
    sgb = machine()
    one_tile_border(sgb, 0x7FFF)
    fade_through(sgb)
    one_tile_border(sgb, 0x7FFF)
    wait(sgb, FADE_DELAY_FRAMES)
    assert sgb.fade_tick == 1
    command(sgb, 0x17, b"\x00")  # MASK_EN: one SNES frame
    command(sgb, 0x0A, bytes(9))  # PAL_SET: one more
    wait(sgb, FADE_TICK_FRAMES + 1)
    assert sgb.fade_tick == 1
    wait(sgb, 1)
    assert sgb.fade_tick == 2
    command(sgb, 0x0F, bytes(15))  # DATA_SND: none
    wait(sgb, FADE_TICK_FRAMES)
    assert sgb.fade_tick == 3


def test_a_second_border_during_the_fade_out_takes_the_first_ones_place() -> None:
    sgb = machine()
    one_tile_border(sgb, 0x7FFF)
    wait(sgb, FADE_DELAY_FRAMES + 9 * FADE_TICK_FRAMES)
    assert sgb.fade_tick == 10
    one_tile_border(sgb, 0x001F, tile_number=3)  # the timeline goes on, held up 3 + 3 frames
    assert sgb.fade_tick == 10
    wait(sgb, (FADE_IN_TICK - 10) * FADE_TICK_FRAMES + 6)
    assert sgb.fade_tick == FADE_IN_TICK and sgb.border_map[0] & 0xFF == 3
    fade_through(sgb)
    assert pixel(sgb.render(), 0, 1) == 0x001F


def test_mask_en() -> None:
    sgb = machine()
    show(sgb, bytes([3] * 160 * 144))
    command(sgb, 0x17, b"\x01")  # freeze
    show(sgb, bytes([1] * 160 * 144))
    assert gb_pixel(sgb.render(), 0, 0) == GREY_RAMP[3]
    command(sgb, 0x17, b"\x02")  # black
    assert gb_pixel(sgb.render(), 0, 0) == 0
    command(sgb, 0x17, b"\x03")  # colour 0
    assert gb_pixel(sgb.render(), 0, 0) == GREY_RAMP[0]
    command(sgb, 0x17, b"\x00")
    show(sgb, bytes([1] * 160 * 144))
    assert gb_pixel(sgb.render(), 0, 0) == GREY_RAMP[1]


def test_a_transfer_reads_the_first_whole_frame_after_the_command() -> None:
    sgb = machine()
    command(sgb, 0x0B, b"")  # PAL_TRN, mid-frame
    show(sgb, bytes(160 * 144))  # the frame in progress ends: not the data
    assert sgb.transfer
    colours = bytearray(4096)
    colours[0:2] = le(0x7C00)
    show(sgb, tiles_screen(bytes(colours)))
    assert not sgb.transfer and sgb.system_palettes[0] == 0x7C00


# ----- the header, save states --------------------------------------------------------------


def test_a_game_without_the_sgb_flag_is_not_obeyed() -> None:
    sgb = machine(sgb_flag=0x00)
    command(sgb, 0x17, b"\x02")
    assert sgb.mask == 0
    sgb = machine(licensee=0x01)
    command(sgb, 0x17, b"\x02")
    assert sgb.mask == 0


def test_header_packets_decide_while_the_boot_rom_runs() -> None:
    sgb = machine(boot=bytes(256), sgb_flag=0x00)  # a boot ROM is mapped: it sends the header
    assert not sgb.enabled
    header = bytearray(84)
    header[0x146 - 0x104] = 0x03
    header[0x14B - 0x104] = 0x33
    for index in range(6):
        send(sgb, bytes([0xF1 + 2 * index, 0]) + bytes(header[index * 14 : index * 14 + 14]))
    assert sgb.enabled


def test_save_state_round_trip() -> None:
    sgb = machine()
    command(sgb, 0x00, le(0x1111, 2, 3, 4, 5, 6, 7))
    command(sgb, 0x11, b"\x01")
    show(sgb, bytes([2] * 160 * 144))
    blob = sgb.save_state()
    other = machine()
    other.load_state(blob)
    assert other.save_state() == blob
    assert list(other.render()) == list(sgb.render())
    assert other.players == 1


def test_save_state_mid_fade() -> None:
    sgb = machine()
    one_tile_border(sgb, 0x7FFF)
    fade_through(sgb)
    one_tile_border(sgb, 0x03E0, tile_number=2)
    wait(sgb, FADE_DELAY_FRAMES + 12 * FADE_TICK_FRAMES)
    blob = sgb.save_state()
    other = machine()
    other.gb.t = sgb.gb.t  # the board's own state carries its clock
    other.load_state(blob)
    assert other.save_state() == blob
    for _ in range(60):
        wait(sgb, FADE_TICK_FRAMES)
        wait(other, FADE_TICK_FRAMES)
        assert list(other.render()) == list(sgb.render())
    assert not other.fading and pixel(other.render(), 0, 1) == 0x03E0


def test_no_object_outgrows_pypy_layout() -> None:
    assert len(vars(machine())) < 80


# ----- a game -------------------------------------------------------------------------------

NO_INTRO = Path(os.environ.get("NO_INTRO_DIR", "No-Intro"))
DONKEY_KONG_600 = "0cf50643cd06aeecbf242767242a7de5c8805603"
DONKEY_KONG = NO_INTRO / "Nintendo - Game Boy" / "Donkey Kong (World) (Rev 1) (SGB Enhanced).zip"


@pytest.mark.slow
@pytest.mark.skipif(not DONKEY_KONG.exists(), reason="set NO_INTRO_DIR to a No-Intro set")
def test_donkey_kong_title_with_border() -> None:
    """Skip-boot, 600 frames: the title screen with the game's border and palettes. The digest
    is this module's own picture (a regression check); docs/sgb.md has the comparison with the
    real BIOS on snes-python, which this frame point matched pixel for pixel when recorded."""
    with zipfile.ZipFile(DONKEY_KONG) as archive:
        rom = archive.read(archive.namelist()[0])
    sgb = SuperGameBoy(GameBoy(load_cartridge(rom), MACHINES["sgb"]))
    sgb.gb.run_frames(600)
    assert sgb.enabled and sgb.border_loaded
    words = sgb.render()
    assert hashlib.sha1(rgb_bytes(words)).hexdigest() == DONKEY_KONG_600


def test_from_skip_boot_the_first_packet_arrives() -> None:
    """Skip-boot starts after the SGB boot ROM, which leaves the ICD2 at both lines high: a
    game's very first packet (Pokemon Red's MLT_REQ check) is a write of $00 straight away,
    and it must not be taken for no change."""
    sgb = machine()
    assert sgb.p1 == 0x30
    send(sgb, bytes([0x89, 0x01]) + bytes(14))  # MLT_REQ, two players, with no $30 first
    assert sgb.players == 1
