"""blargg's CPU and timing tests on the board (hardware-verified tier).

``cpu_instrs`` (the eleven individual ROMs and the combined one), ``instr_timing`` and
``mem_timing`` print on the serial port; ``mem_timing-2`` writes its result to cartridge RAM
($A000 protocol). All run from the skip-boot state; the real-boot-ROM and quickboot variants of
the same ROMs are in tests/test_boot_variants.py.
"""

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.testrom import run_blargg_ram, run_blargg_serial

BLARGG = Path(__file__).resolve().parents[1] / "tests" / "test_roms" / "gbtr" / "blargg"
INDIVIDUAL = sorted((BLARGG / "cpu_instrs" / "individual").glob("*.gb"))

pytestmark = pytest.mark.skipif(not INDIVIDUAL, reason="run scripts/fetch_references.py")


@pytest.mark.parametrize("path", INDIVIDUAL, ids=[p.stem for p in INDIVIDUAL])
def test_cpu_instrs_individual(path):
    result = run_blargg_serial(GameBoy(load_cartridge(path.read_bytes())), max_frames=2000)
    assert result.passed, result.text


@pytest.mark.slow
def test_cpu_instrs_combined():
    path = BLARGG / "cpu_instrs" / "cpu_instrs.gb"
    result = run_blargg_serial(GameBoy(load_cartridge(path.read_bytes())), max_frames=6000)
    assert result.passed and result.text.count(":ok") == 11, result.text


@pytest.mark.parametrize("rom", ["instr_timing/instr_timing.gb", "mem_timing/mem_timing.gb"])
def test_timing_serial(rom):
    result = run_blargg_serial(GameBoy(load_cartridge((BLARGG / rom).read_bytes())))
    assert result.passed, result.text


def test_mem_timing_2_cartridge_ram_protocol():
    path = BLARGG / "mem_timing-2" / "mem_timing.gb"
    result = run_blargg_ram(GameBoy(load_cartridge(path.read_bytes())))
    assert result.protocol == "blargg-ram" and result.passed, result.text
