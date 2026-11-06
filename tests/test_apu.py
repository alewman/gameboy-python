"""The APU on the board: blargg dmg_sound and cgb_sound, SameSuite's DMG DIV-APU tests and
Gambatte's audio ROMs. The APU itself is gb-apu-python (pinned in pyproject.toml), which tests
its own seams."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import MACHINES, GameBoy, load_cartridge
from gameboy_python.boot import find_boot_rom
from gameboy_python.testrom import run_blargg_ram, run_mooneye

GBTR = Path(__file__).parent / "test_roms" / "gbtr"
DMG_SOUND = sorted((GBTR / "blargg" / "dmg_sound" / "rom_singles").glob("*.gb"))
CGB_SOUND = sorted((GBTR / "blargg" / "cgb_sound" / "rom_singles").glob("*.gb"))
SAME_SUITE = GBTR / "same-suite" / "apu"
GAMBATTE = GBTR / "gambatte"
PASSING = Path(__file__).with_name("gambatte_audio_pass.txt")


@pytest.mark.skipif(not DMG_SOUND, reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("path", DMG_SOUND, ids=[p.stem for p in DMG_SOUND])
def test_dmg_sound(path):
    result = run_blargg_ram(GameBoy(load_cartridge(path.read_bytes())), max_frames=3000)
    assert result.protocol == "blargg-ram" and result.passed, result.text


@pytest.mark.skipif(not CGB_SOUND, reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("path", CGB_SOUND, ids=[p.stem for p in CGB_SOUND])
def test_cgb_sound(path):
    gb = GameBoy(load_cartridge(path.read_bytes()), MACHINES["cgb"])
    result = run_blargg_ram(gb, max_frames=3000)
    assert result.protocol == "blargg-ram" and result.passed, result.text


@pytest.mark.skipif(not SAME_SUITE.exists(), reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("name", ["div_write_trigger", "div_write_trigger_10"])
def test_same_suite_div_write_trigger(name):
    result = run_mooneye(GameBoy(load_cartridge((SAME_SUITE / f"{name}.gb").read_bytes())), 600)
    assert result.passed, result.registers


@pytest.mark.slow
@pytest.mark.skipif(not PASSING.exists() or not GAMBATTE.exists(), reason="run fetch_references")
@pytest.mark.skipif(find_boot_rom("DMG")[1] != "real boot ROM", reason="needs the real boot ROM")
@pytest.mark.parametrize("name", PASSING.read_text().split() if PASSING.exists() else [])
def test_gambatte_audio(name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gambatte_audio", Path(__file__).parents[1] / "scripts" / "gambatte_audio.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = next(GAMBATTE.rglob(name))
    _name, want, got = module.run((path, True))
    assert want == got
