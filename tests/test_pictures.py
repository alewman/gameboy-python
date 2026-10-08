"""Picture tests: the board's frame against reference pictures, pixel for pixel."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from tests.pngread import read_shades

GBTR = Path(__file__).parent / "test_roms" / "gbtr"

pytestmark = pytest.mark.skipif(not GBTR.exists(), reason="run scripts/fetch_references.py")


def frame_of(rom: Path, frames: int, **kwargs) -> bytes:
    gb = GameBoy(load_cartridge(rom.read_bytes()), **kwargs)
    gb.run_frames(frames)
    return gb.ppu.frame


def test_dmg_acid2_from_skip_boot():
    want, _w, _h = read_shades(GBTR / "dmg-acid2" / "dmg-acid2-dmg.png")
    assert frame_of(GBTR / "dmg-acid2" / "dmg-acid2.gb", 30) == want
