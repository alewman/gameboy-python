"""The frontend (frontend.py): its conversions without pygame, and a window driven headless
(SDL's dummy drivers) through dmg-acid2, with a save written beside the image."""

import zipfile
from array import array
from pathlib import Path

import pytest

from gameboy_python.frontend import (
    PALETTES,
    WORDS,
    Console,
    frame_image,
    machine_for,
    read_rom,
    save_path,
)

GBTR = Path(__file__).parent / "test_roms" / "gbtr"
DMG_ACID = GBTR / "dmg-acid2" / "dmg-acid2.gb"
CGB_ACID = GBTR / "cgb-acid2" / "cgb-acid2.gbc"
needs_roms = pytest.mark.skipif(not DMG_ACID.exists(), reason="test ROMs not fetched")


def battery_copy(folder: Path) -> Path:
    """dmg-acid2 as if it were an MBC1 cartridge with 8 KiB of battery RAM."""
    image = bytearray(DMG_ACID.read_bytes())
    image[0x147], image[0x149] = 0x03, 0x02
    rom = folder / "acid.gb"
    rom.write_bytes(image)
    return rom


def test_words_widen_five_bits_as_the_png_writer_does() -> None:
    assert WORDS[0] == 0xFF000000
    assert WORDS[0x7FFF] == 0xFFFFFFFF
    assert WORDS[31] == 0xFFFF0000  # red is the low five bits
    assert WORDS[16 << 10] == 0xFF000084  # round(16 * 255 / 31)


def test_frame_image_maps_shades_and_colours() -> None:
    assert array("I", frame_image(bytes((0, 3)), False)).tolist() == [0xFFFFFFFF, 0xFF000000]
    green = array("I", frame_image(bytes((0, 3)), False, "green")).tolist()
    assert green == [PALETTES["green"][0], PALETTES["green"][3]]
    assert array("I", frame_image(b"\x1f\x00\xff\x7f", True)).tolist() == [0xFFFF0000, 0xFFFFFFFF]


@needs_roms
def test_the_header_picks_the_console(tmp_path: Path) -> None:
    assert machine_for(DMG_ACID.read_bytes()) == "dmg"
    assert machine_for(CGB_ACID.read_bytes()) == "cgb"
    packed = tmp_path / "game.zip"
    with zipfile.ZipFile(packed, "w") as archive:
        archive.writestr("readme.txt", "x")
        archive.writestr("game.gbc", CGB_ACID.read_bytes())
    assert read_rom(packed) == CGB_ACID.read_bytes()
    assert save_path(packed) == tmp_path / "game.sav"


@needs_roms
def test_the_console_draws_acid2_and_takes_buttons() -> None:
    console = Console(DMG_ACID, boot="skip")
    sound = b"".join(console.run_frame() for _ in range(30))
    assert console.gb.t >= 30 * 70224
    assert len(sound) % 4 == 0 and len(sound) > 0
    assert len(set(console.gb.ppu.frame)) == 4  # the face, in all four shades
    console.press({"a", "left"})
    assert console.gb.joypad.pressed == {"a", "left"}
    console.press({"left", "start"})
    assert console.gb.joypad.pressed == {"left", "start"}


@needs_roms
def test_a_colour_cartridge_runs_on_a_cgb() -> None:
    console = Console(CGB_ACID, boot="skip")
    assert console.cgb
    for _ in range(30):
        console.run_frame()
    frame = console.gb.ppu.frame
    words = array("I", frame_image(frame, True))
    rgb = bytes(c for w in words for c in (w >> 16 & 255, w >> 8 & 255, w & 255))
    word = frame[0] | frame[1] << 8
    assert rgb[:3] == bytes(round(v * 255 / 31) for v in (word & 31, word >> 5 & 31, word >> 10))
    assert len(set(words)) > 4


@needs_roms
def test_a_headless_window_plays_and_saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pygame = pytest.importorskip("pygame")
    controller = pytest.importorskip("pygame._sdl2.controller")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    rom = battery_copy(tmp_path)
    from gameboy_python.frontend import Frontend

    pygame.display.init()
    controller.init()
    try:
        frontend = Frontend(pygame, rom, "auto", "skip", 1, True, False)
        frontend.console.cartridge.ram[:] = b"\x12" * 0x2000
        seen = []
        frontend.run(max_frames=5, on_frame=lambda f: seen.append(len(f.sound)))
        frontend.console.save()
    finally:
        pygame.quit()
    assert len(seen) == 5
    assert (tmp_path / "acid.sav").read_bytes() == b"\x12" * 0x2000
    again = Console(rom, boot="skip")  # the next power-on reads it back
    assert bytes(again.cartridge.ram) == b"\x12" * 0x2000
