"""The Mooneye set and blargg's serial tests, booted from a boot ROM (docs/handoff-brief.md).

Milestone 1 requires them to pass booted with the real DMG boot ROM *and* with dmg-sim's
``quickboot.bin``. The real ROM is read in place (never copied), SHA-256-checked
(docs/start-here.md "Boot ROMs"); both variants skip when their image is absent. The real ROM
takes about 335 frames before the cartridge starts, so these are marked slow.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import QUICKBOOT, find_boot_rom
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS, applicable
from tests.test_mooneye import NEEDS_PPU

pytestmark = pytest.mark.slow

REAL, REAL_LABEL = find_boot_rom("DMG")
REAL_OK = REAL is not None and REAL_LABEL == "real boot ROM"

#: the real boot ROM's duration (and so DIV's phase and the serial divider's alignment at
#: handoff) depends on the exact LCD-on alignment of the PPU: milestone 2
REAL_NEEDS_PPU = {
    "boot_div-dmgABCmgb",
    "boot_hwio-dmgABCmgb",
    "serial/boot_sclk_align-dmgABCmgb",
}

NAMES = [n for n in applicable() if n not in NEEDS_PPU]


def run(name: str, image: bytes) -> bool:
    rom = Path(ROMS / f"{name}.gb").read_bytes()
    return run_mooneye(GameBoy(load_cartridge(rom), boot_rom=image), max_frames=900).passed


@pytest.mark.skipif(not QUICKBOOT.exists(), reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("name", NAMES)
def test_quickboot(name):
    assert run(name, QUICKBOOT.read_bytes())


@pytest.mark.skipif(not REAL_OK, reason="the real DMG boot ROM is not at its documented place")
@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            n, marks=[pytest.mark.xfail(strict=True, reason="needs the PPU's LCD-on timing")]
        )
        if n in REAL_NEEDS_PPU
        else n
        for n in NAMES
    ],
)
def test_real_boot_rom(name):
    assert run(name, REAL)
