"""The APU: blargg dmg_sound, SameSuite's DMG DIV-APU tests, Gambatte's audio ROMs, and the
sample output. The APU is behind a boundary (tests/test_import_boundaries.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.apu import APU
from gameboy_python.boot import find_boot_rom
from gameboy_python.testrom import run_blargg_ram, run_mooneye

GBTR = Path(__file__).parent / "test_roms" / "gbtr"
DMG_SOUND = sorted((GBTR / "blargg" / "dmg_sound" / "rom_singles").glob("*.gb"))
SAME_SUITE = GBTR / "same-suite" / "apu"
GAMBATTE = GBTR / "gambatte"
PASSING = Path(__file__).with_name("gambatte_audio_pass.txt")


@pytest.mark.skipif(not DMG_SOUND, reason="run scripts/fetch_references.py")
@pytest.mark.parametrize("path", DMG_SOUND, ids=[p.stem for p in DMG_SOUND])
def test_dmg_sound(path):
    result = run_blargg_ram(GameBoy(load_cartridge(path.read_bytes())), max_frames=3000)
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


def test_a_pulse_channel_makes_a_square_wave():
    apu = APU(sample_rate=44100)
    apu.capture = True
    apu.write(0xFF26, 0x80)  # power
    apu.write(0xFF24, 0x77)
    apu.write(0xFF25, 0xFF)
    apu.write(0xFF11, 0x80)  # duty 50%
    apu.write(0xFF12, 0xF0)  # volume 15, no envelope
    apu.write(0xFF13, 0x00)
    apu.write(0xFF14, 0x87)  # trigger, frequency 0x700: about 2 kHz
    for _ in range(100_000):  # 0.095 s of the 4 MHz clock
        apu.tick(4)
    samples = apu.take_samples()
    assert len(samples) > 2 * 4000  # about 4,200 stereo frames
    assert max(samples) > 2000 and min(samples) < -2000


def test_power_off_clears_registers_but_not_length_counters():
    apu = APU()
    apu.write(0xFF26, 0x80)
    apu.write(0xFF12, 0xF0)
    apu.write(0xFF11, 0x3F)
    apu.write(0xFF26, 0x00)
    assert apu.read(0xFF12) == 0x00
    assert apu.ch1.length == 1  # DMG: the length counter survives
    apu.write(0xFF12, 0xF0)  # ignored while off
    assert apu.read(0xFF12) == 0x00
