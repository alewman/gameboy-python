"""The DMG 0 revision: its boot ROM, and the one behaviour Mooneye says differs (milestone 6).

Mooneye's three DMG 0 boot tests pass from the DMG0 boot ROM; ``ppu/stat_irq_blocking`` passes on
DMG A/B/C and *fails* on DMG 0 (its header: hardware-verified), so the DMG 0 machine must fail it
and the DMG-B machine must pass it. The DMG0 boot ROM is read in place and SHA-checked.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.machines import MACHINES
from gameboy_python.testrom import run_mooneye
from tests.mooneye_meta import ROMS

pytestmark = pytest.mark.slow

BOOT, LABEL = find_boot_rom("DMG0")
needs_boot = pytest.mark.skipif(
    BOOT is None or LABEL != "real boot ROM", reason="the real DMG0 boot ROM is not present"
)


def run(name: str, machine: str) -> bool:
    rom = Path(ROMS / f"{name}.gb").read_bytes()
    gb = GameBoy(load_cartridge(rom), boot_rom=BOOT, machine=MACHINES[machine])
    return run_mooneye(gb, max_frames=1500).passed


@needs_boot
@pytest.mark.parametrize("name", ["boot_div-dmg0", "boot_hwio-dmg0", "boot_regs-dmg0"])
def test_dmg0_boot(name):
    assert run(name, "dmg-0")


@needs_boot
def test_stat_irq_blocking_fails_on_dmg0():
    assert not run("ppu/stat_irq_blocking", "dmg-0")


def test_stat_irq_blocking_passes_on_dmg_b():
    rom = Path(ROMS / "ppu/stat_irq_blocking.gb").read_bytes()
    assert run_mooneye(GameBoy(load_cartridge(rom)), max_frames=60).passed
