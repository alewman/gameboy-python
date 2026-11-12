"""Picture tests: the board's frame against reference pictures, pixel for pixel."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from tests.pngread import read_shades

GBTR = Path(__file__).parent / "test_roms" / "gbtr"

REAL, REAL_LABEL = find_boot_rom("DMG")
REAL_OK = REAL is not None and REAL_LABEL == "real boot ROM"

pytestmark = pytest.mark.skipif(not GBTR.exists(), reason="run scripts/fetch_references.py")


def frame_of(rom: Path, frames: int, **kwargs) -> bytes:
    gb = GameBoy(load_cartridge(rom.read_bytes()), **kwargs)
    gb.run_frames(frames)
    return gb.ppu.frame


def test_dmg_acid2_from_skip_boot():
    want, _w, _h = read_shades(GBTR / "dmg-acid2" / "dmg-acid2-dmg.png")
    assert frame_of(GBTR / "dmg-acid2" / "dmg-acid2.gb", 30) == want


MEALYBUG = GBTR / "mealybug-tearoom-tests" / "ppu"
#: the Mealybug DMG pictures the board matches pixel for pixel (scripts/mealybug_compare.py scores
#: all 24; the rest are listed in docs/validation.md). They draw the boot ROM's (R) tile, so they
#: are booted with the real DMG boot ROM.
MEALYBUG_EXACT = sorted(
    p.name[: -len("_dmg_blob.png")] for p in MEALYBUG.glob("*_dmg_blob.png")
)  # all 24 (pixels.py)


@pytest.mark.slow
@pytest.mark.skipif(not REAL_OK, reason="the real DMG boot ROM is not at its documented place")
@pytest.mark.parametrize("name", MEALYBUG_EXACT)
def test_mealybug_dmg_blob(name):
    want, _w, _h = read_shades(MEALYBUG / f"{name}_dmg_blob.png")
    gb = GameBoy(load_cartridge((MEALYBUG / f"{name}.gb").read_bytes()), boot_rom=REAL)
    gb.run_frames(420)
    assert gb.ppu.frame == want


def test_blargg_halt_bug_screen():
    want, _w, _h = read_shades(GBTR / "blargg" / "halt_bug-dmg-cgb.png")
    assert frame_of(GBTR / "blargg" / "halt_bug.gb", 600) == want


def test_a_bgp_write_glitches_one_pixel_of_one_frame():
    """The OR of the old and new palettes is shown for one dot (Mealybug m3_bgp_change); the
    next frames show the picture the VRAM holds. It used to return at the same dot of every
    later frame: one wrong pixel on a still screen."""
    gb = GameBoy(load_cartridge((GBTR / "dmg-acid2" / "dmg-acid2.gb").read_bytes()))
    gb.run_frames(30)
    still = gb.ppu.frame
    while not (gb.ppu.ly == 20 and gb.ppu.mode == 3 and gb.ppu.x >= 40):
        gb.cpu.step()
    old = gb.ppu.bgp
    gb.ppu.write_bgp(old ^ 0xFF)  # a glitch pixel, then the other palette ...
    gb.ppu.write_bgp(old)  # ... and back before the next pixel
    assert gb.ppu.bgp_glitch[1:] == (20, 0xFF)
    gb.run_frames(3)
    assert gb.ppu.bgp_glitch == (-1, -1, 0)
    assert gb.ppu.frame == still


def test_strikethrough_reads_oam_through_a_dma():
    """strikethrough.gb: the scan keeps its last Y and X while an OAM DMA holds the bus, and an
    object's tile read gets the pair of bytes the DMA is writing (pixels.py)."""
    path = GBTR / "strikethrough"
    if not (path / "strikethrough.gb").exists():
        pytest.skip("run scripts/fetch_references.py")
    want, _w, _h = read_shades(path / "strikethrough-dmg.png")
    assert frame_of(path / "strikethrough.gb", 60) == want
