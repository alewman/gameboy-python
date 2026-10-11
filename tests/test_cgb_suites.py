"""SameSuite and AGE ROMs that pass on the CGB E board today (milestone 7), plus cgb-acid2.

``tests/cgb_suites_pass.txt`` lists them (SameSuite 23 of 76, AGE 7 of 28 on 2026-10-10; the rest
are open items in docs/validation.md "Results: milestone 7"). Each passes when B, C, D, E, H, L =
3, 5, 8, 13, 21, 34 at ``LD B,B``. cgb-acid2 must be pixel-exact from the real CGB boot ROM (slow).
"""

from pathlib import Path

import pytest

from gameboy_python import MACHINES, GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.testrom import run_mooneye

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/test_roms/gbtr"
LIST = Path(__file__).with_name("cgb_suites_pass.txt")
NAMES = LIST.read_text().split() if LIST.exists() else []

pytestmark = pytest.mark.skipif(not BASE.exists() or not NAMES, reason="run scripts/fetch_references.py")


@pytest.mark.parametrize("name", NAMES)
def test_register_protocol(name):
    gb = GameBoy(load_cartridge((BASE / name).read_bytes()), MACHINES["cgb"])
    assert run_mooneye(gb, max_frames=600).passed


@pytest.mark.slow
@pytest.mark.skipif(find_boot_rom("CGB")[1] != "real boot ROM", reason="no real CGB boot ROM")
def test_cgb_acid2_pixel_exact():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "tests"))
    from cgb_picture import run, words
    from pngread import read_rgb555

    got = words(run(BASE / "cgb-acid2/cgb-acid2.gbc", 300, "real"))
    want, _w, _h = read_rgb555(BASE / "cgb-acid2/cgb-acid2.png")
    assert got == want
