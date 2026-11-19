"""Mooneye tests that apply to a CPU CGB E (milestone 7).

A ROM applies when its ``pass:`` header names CGB or CGB ABCDE (tests/mooneye_meta.py). The
acceptance ROMs run from the CGB skip-boot state (measured from the real boot ROM on this board);
the ``misc/boot_*`` ROMs need the real CGB boot ROM (read in place, SHA-checked) and are slow.
Result 2026-10-10: all 58 pass.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.machines import MACHINES
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS, applicable, applicable_misc

ACCEPTANCE = applicable("cgb")
MISC = applicable_misc()
BOOT, LABEL = find_boot_rom("CGB")

pytestmark = pytest.mark.skipif(
    ROMS is None or not ACCEPTANCE, reason="run scripts/fetch_references.py"
)


def run(path: Path, boot: bytes | None) -> bool:
    gb = GameBoy(load_cartridge(path.read_bytes()), MACHINES["cgb"], boot_rom=boot)
    return run_mooneye(gb, max_frames=1500).passed


@pytest.mark.parametrize("name", ACCEPTANCE)
def test_acceptance_from_skip_boot(name):
    assert run(ROMS / f"{name}.gb", None)


@pytest.mark.slow
@pytest.mark.skipif(LABEL != "real boot ROM", reason="the real CGB boot ROM is not present")
@pytest.mark.parametrize("name", MISC)
def test_misc_from_real_boot(name):
    assert run(ROMS.parent / "misc" / f"{name}.gb", BOOT)
