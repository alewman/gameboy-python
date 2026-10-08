"""Mooneye acceptance tests applicable to the reference model (DMG-CPU B).

Hardware-verified tier: each ROM's header names the consoles it was verified on; the ones that
apply to a DMG-CPU B (66) are run, booted from the skip-boot state. The pass criterion is
Mooneye's: B, C, D, E, H, L = 3, 5, 8, 13, 21, 34 at ``LD B,B``.

The failures below need the PPU to be dot-accurate (milestone 2): they are strict expected
failures, so fixing one fails the test until it is moved to the passing set.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS, applicable

NAMES = applicable()

#: name -> why it fails today (all are milestone 2: the PPU is a timing skeleton)
NEEDS_PPU = {
    "ppu/hblank_ly_scx_timing-GS": "mode-3 length from SCX",
    "ppu/intr_2_mode0_timing": "mode-0 interrupt timing",
    "ppu/intr_2_mode0_timing_sprites": "object penalties in mode 3",
    "ppu/intr_2_mode3_timing": "mode-3 timing",
    "ppu/intr_2_oam_ok_timing": "OAM unlock edge",
    "ppu/lcdon_timing-GS": "the first line after LCD on",
    "ppu/lcdon_write_timing-GS": "VRAM/OAM access just after LCD on",
    "ppu/stat_lyc_onoff": "LYC compare while the LCD is toggled",
    "ppu/vblank_stat_intr-GS": "mode-2 STAT condition at line 144",
}

pytestmark = pytest.mark.skipif(ROMS is None or not NAMES, reason="run scripts/fetch_references.py")


def params():
    for name in NAMES:
        marks = []
        if name in NEEDS_PPU:
            marks.append(pytest.mark.xfail(strict=True, reason=NEEDS_PPU[name]))
        yield pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize("name", params())
def test_acceptance_from_skip_boot(name):
    rom = Path(ROMS / f"{name}.gb").read_bytes()
    result = run_mooneye(GameBoy(load_cartridge(rom)), max_frames=120)
    assert result.passed, f"{result.protocol}, registers {result.registers}"
