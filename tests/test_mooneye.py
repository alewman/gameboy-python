"""Mooneye acceptance tests applicable to the reference model (DMG-CPU B).

Hardware-verified tier: each ROM's header names the consoles it was verified on; the ones that
apply to a DMG-CPU B (66) are run, booted from the skip-boot state. The pass criterion is
Mooneye's: B, C, D, E, H, L = 3, 5, 8, 13, 21, 34 at ``LD B,B``.

All 66 pass (milestone 2 made the PPU dot-accurate; the constants fitted to ppu/* are marked
FITTED in ppu.py).
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS, applicable

NAMES = applicable()

pytestmark = pytest.mark.skipif(ROMS is None or not NAMES, reason="run scripts/fetch_references.py")


@pytest.mark.parametrize("name", NAMES)
def test_acceptance_from_skip_boot(name):
    rom = Path(ROMS / f"{name}.gb").read_bytes()
    result = run_mooneye(GameBoy(load_cartridge(rom)), max_frames=1500)
    assert result.passed, f"{result.protocol}, registers {result.registers}"
