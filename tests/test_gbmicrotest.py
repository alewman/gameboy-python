"""GBMicrotest: the board must keep passing every ROM it passes today
(``tests/gbmicrotest_pass.txt``, written by ``scripts/gbmicrotest.py --write``). ``poweron_*`` ROMs run from the real boot ROM."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.testrom import run_microtest

ROMS = Path(__file__).parent / "test_roms" / "gbtr" / "gbmicrotest"
PASSING = Path(__file__).with_name("gbmicrotest_pass.txt")
NAMES = PASSING.read_text().split() if PASSING.exists() else []
REAL, REAL_LABEL = find_boot_rom("DMG")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not ROMS.exists() or not NAMES, reason="run scripts/fetch_references.py"),
]


@pytest.mark.parametrize("name", NAMES)
def test_passes(name):
    real = name.startswith("poweron_")
    if real and REAL_LABEL != "real boot ROM":
        pytest.skip("needs the real DMG boot ROM")
    gb = GameBoy(load_cartridge((ROMS / name).read_bytes()), boot_rom=REAL if real else None)
    run_microtest(gb, 12 + (352 if real else 0))
    assert gb.hram[2] == 1, f"got ${gb.hram[0]:02X}, expected ${gb.hram[1]:02X}"
