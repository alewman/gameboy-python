"""SameSuite and AGE ROMs that pass on the CGB E board (milestone 7), cgb-acid2, Mealybug CGB D.

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

pytestmark = pytest.mark.skipif(
    not BASE.exists() or not NAMES, reason="run scripts/fetch_references.py"
)


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


MEALYBUG = BASE / "mealybug-tearoom-tests/ppu"
#: Mealybug's CPU CGB D pictures the board draws exactly, from the real CGB boot ROM (a DMG
#: cartridge: the compatibility mode, pixels.py). Left out: m3_lcdc_obj_size_change_scx,
#: whose expected picture has a 4x4 block that the CGB-D photograph does not (docs/validation.md).
MEALYBUG_CGB_D = sorted(
    p.name[: -len("_cgb_d.png")]
    for p in MEALYBUG.glob("*_cgb_d.png")
    if p.name != "m3_lcdc_obj_size_change_scx_cgb_d.png"
)


@pytest.mark.slow
@pytest.mark.skipif(find_boot_rom("CGB")[1] != "real boot ROM", reason="no real CGB boot ROM")
@pytest.mark.parametrize("name", MEALYBUG_CGB_D)
def test_mealybug_cgb_d(name):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "tests"))
    from cgb_picture import run, words
    from pngread import read_rgb555

    got = words(run(MEALYBUG / f"{name}.gb", 260, "real"))
    want, _w, _h = read_rgb555(MEALYBUG / f"{name}_cgb_d.png")
    assert got == want


#: Mealybug's CPU CGB C pictures, on the ``cgb-c`` machine row. Left out: the two TILE_SEL
#: change2 tests (166 pixels each: SameBoy has a CGB C TILE_SEL rule of its own, not modelled)
#: and m3_lcdc_obj_size_change_scx (15 pixels, as on the CGB D).
MEALYBUG_CGB_C_OPEN = {
    "m3_lcdc_obj_size_change_scx",
    "m3_lcdc_tile_sel_change2",
    "m3_lcdc_tile_sel_win_change2",
}
MEALYBUG_CGB_C = sorted(
    name
    for name in (p.name[: -len("_cgb_c.png")] for p in MEALYBUG.glob("*_cgb_c.png"))
    if name not in MEALYBUG_CGB_C_OPEN and (MEALYBUG / f"{name}.gb").exists()
)


@pytest.mark.slow
@pytest.mark.skipif(find_boot_rom("CGB")[1] != "real boot ROM", reason="no real CGB boot ROM")
@pytest.mark.parametrize("name", MEALYBUG_CGB_C)
def test_mealybug_cgb_c(name):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "tests"))
    from cgb_picture import run, words
    from pngread import read_rgb555

    got = words(run(MEALYBUG / f"{name}.gb", 260, "real", "cgb-c"))
    want, _w, _h = read_rgb555(MEALYBUG / f"{name}_cgb_c.png")
    assert got == want
