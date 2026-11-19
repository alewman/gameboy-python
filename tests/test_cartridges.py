"""Cartridge boards: Mooneye emulator-only (MBC1, MBC1M, MBC2, MBC5), the MBC3 clock, MMM01."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.cartridge import MBC1, MBC3, MMM01
from gameboy_python.machines import CLOCK_HZ
from gameboy_python.testrom import run_mooneye
from tests.pngread import read_shades

GBTR = Path(__file__).parent / "test_roms" / "gbtr"
EMULATOR_ONLY = sorted((GBTR / "mooneye-test-suite" / "emulator-only").rglob("*.gb"))
RTC3 = GBTR / "rtc3test"


@pytest.mark.skipif(not EMULATOR_ONLY, reason="run scripts/fetch_references.py")
@pytest.mark.parametrize(
    "path", EMULATOR_ONLY, ids=[f"{p.parent.name}/{p.stem}" for p in EMULATOR_ONLY]
)
def test_mooneye_emulator_only(path):
    result = run_mooneye(GameBoy(load_cartridge(path.read_bytes())), max_frames=600)
    assert result.passed, result.registers


def test_multicart_is_found_by_its_second_logo():
    path = GBTR / "mooneye-test-suite" / "emulator-only" / "mbc1" / "multicart_rom_8Mb.gb"
    if not path.exists():
        pytest.skip("run scripts/fetch_references.py")
    cart = load_cartridge(path.read_bytes())
    assert isinstance(cart, MBC1) and cart.multicart


@pytest.mark.skipif(not (RTC3 / "rtc3test.gb").exists(), reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("index, name", [(0, "basic-tests"), (1, "range-tests")])
def test_rtc3test_pictures(index, name):
    """rtc3test (a detector: docs/cartridge.md) with the clock tied to emulated time."""
    box: list[GameBoy] = []
    cart = load_cartridge(
        (RTC3 / "rtc3test.gb").read_bytes(), clock=lambda: (box[0].t if box else 0) / CLOCK_HZ
    )
    gb = GameBoy(cart)
    box.append(gb)
    gb.run_frames(30)
    for button in ["down"] * index + ["a"]:
        gb.joypad.set_pressed(button, True)
        gb.run_frames(3)
        gb.joypad.set_pressed(button, False)
        gb.run_frames(5)
    gb.run_frames(60 * (40 + 20 * index))
    want, _w, _h = read_shades(RTC3 / f"rtc3test-{name}-dmg.png")
    assert gb.ppu.frame == want


def mbc3(clock):
    rom = bytearray(0x8000)
    rom[0x147], rom[0x148], rom[0x149] = 0x10, 0, 3  # MBC3+TIMER+RAM+BATTERY
    return load_cartridge(bytes(rom), clock=clock)


def read_clock(cart, register, now):
    cart.write(0x6000, 0, 0)
    cart.write(0x6000, 1, 0)
    cart.write(0x4000, register, 0)
    return cart.read(0xA000, 0)


def test_mbc3_clock_counts_latches_and_halts():
    now = [100.0]
    cart = mbc3(lambda: now[0])
    assert isinstance(cart, MBC3)
    cart.write(0x0000, 0x0A, 0)
    cart.write(0x4000, 0x08, 0)
    cart.write(0xA000, 58, 0)  # seconds = 58 (restarts the sub-second count)
    now[0] += 3
    assert read_clock(cart, 0x08, now) == 1 and read_clock(cart, 0x09, now) == 1
    cart.write(0x4000, 0x0C, 0)
    cart.write(0xA000, 0x40, 0)  # halt
    now[0] += 500
    assert read_clock(cart, 0x08, now) == 1  # frozen
    cart.write(0x4000, 0x0C, 0)
    cart.write(0xA000, 0x00, 0)  # run again
    now[0] += 60
    assert read_clock(cart, 0x09, now) == 2


def test_mbc3_select_is_four_bits_with_holes():
    """CasualPokePlayer's rtc-invalid-banks-test, as the Emulator Shootout expects it."""
    cart = mbc3(lambda: 0.0)
    cart.write(0x0000, 0x0A, 0)
    for bank in range(4):
        cart.write(0x4000, bank, 0)
        cart.write(0xA000, bank, 0)
    for register in range(0x08, 0x0D):
        cart.write(0x4000, register, 0)
        cart.write(0xA000, register, 0)
    cart.write(0x6000, 0, 0)
    row = [0, 1, 2, 3, 0xFF, 0xFF, 0xFF, 0xFF, 8, 9, 10, 11, 0, 0xFF, 0xFF, 0xFF]  # $0C & $C1
    for high in range(0, 0x100, 0x10):
        got = []
        for select in range(16):
            cart.write(0x4000, high | select, 0)
            got.append(cart.read(0xA000, 0))
        assert got == row
    cart.write(0x4000, 0x05, 0)
    cart.write(0xA000, 0x77, 0)  # a hole takes no write
    assert [cart.ram[b << 13] for b in range(4)] == [0, 1, 2, 3]


def test_mbc3_latches_on_any_write():
    """CasualPokePlayer's latch-rtc-test: one write to $6000-$7FFF latches, whatever its value."""
    cart = mbc3(lambda: 0.0)
    cart.write(0x0000, 0x0A, 0)
    cart.write(0x4000, 0x09, 0)
    cart.write(0xA000, 0x2A, 0)
    assert cart.read(0xA000, 0) == 0  # not latched yet
    cart.write(0x7FFF, 0x55, 0)
    assert cart.read(0xA000, 0) == 0x2A


def test_mbc3_day_counter_overflow_is_sticky():
    now = [0.0]
    cart = mbc3(lambda: now[0])
    cart.write(0x0000, 0x0A, 0)
    for register, value in ((0x0A, 23), (0x09, 59), (0x08, 59), (0x0B, 255), (0x0C, 1)):
        cart.write(0x4000, register, 0)
        cart.write(0xA000, value, 0)
    now[0] += 1
    assert read_clock(cart, 0x0C, now) & 0x80  # 511 days + 1 s: carry
    now[0] += 86400 * 3
    assert read_clock(cart, 0x0C, now) & 0x80  # still set


def test_mbc3_save_has_the_48_byte_trailer():
    cart = mbc3(lambda: 5.0)
    data = cart.save_ram()
    assert data is not None and len(data) == 0x8000 + 48


def test_mmm01_starts_on_the_menu_in_the_last_32k():
    rom = bytearray(0x80000)
    menu = 0x80000 - 0x8000
    rom[menu + 0x104 : menu + 0x114] = bytes.fromhex("CEED6666CC0D000B03730083000C000D")
    rom[menu + 0x147] = 0x0B
    rom[0] = 0x11  # the first game's first byte
    rom[menu] = 0x22  # the menu's
    cart = load_cartridge(bytes(rom))
    assert isinstance(cart, MMM01)
    assert cart.read(0x0000, 0) == 0x22  # unmapped: the menu
    cart.write(0x0000, 0x40, 0)  # mapping enable
    assert cart.read(0x0000, 0) == 0x11  # mapped: the selected game (bank 0)
