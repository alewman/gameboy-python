"""The Mooneye set and blargg's serial tests, booted from a boot ROM (docs/handoff-brief.md).

Milestone 1 required them to pass booted with the real DMG boot ROM *and* with dmg-sim's
``quickboot.bin``; the quickboot variant was removed on 2026-11-26 (dmg-sim is set aside for the
author's wishes: docs/provenance.md "Author respect"). The real ROM is read in place (never
copied), SHA-256-checked (docs/start-here.md "Boot ROMs"); the test skips when it is absent.
The real ROM takes about 335 frames before the cartridge starts, so these are marked slow.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS, applicable

pytestmark = pytest.mark.slow

REAL, REAL_LABEL = find_boot_rom("DMG")
REAL_OK = REAL is not None and REAL_LABEL == "real boot ROM"

NAMES = applicable()


def run(name: str, image: bytes) -> bool:
    rom = Path(ROMS / f"{name}.gb").read_bytes()
    return run_mooneye(GameBoy(load_cartridge(rom), boot_rom=image), max_frames=1500).passed


@pytest.mark.skipif(not REAL_OK, reason="the real DMG boot ROM is not at its documented place")
@pytest.mark.parametrize("name", NAMES)
def test_real_boot_rom(name):
    assert run(name, REAL)
