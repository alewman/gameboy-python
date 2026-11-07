"""Gambatte's ``cgb04c`` hardware tests on the CGB E board: keep passing what it passes today.

``tests/gambatte_cgb04c_pass.txt`` (2,741 verdicts, written by ``scripts/gambatte_dmg08.py --cgb
--skip-boot --write``) lists them; this holds every STRIDE-th one, from the CGB post-boot state.
Gambatte's reference is a CPU CGB C (04c); the board is a CGB E, so the open items are not all
bugs (docs/validation.md "Results: milestone 7"). Rerun the script after a change that touches
timing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "tests/test_roms/gbtr/gambatte"
LIST = Path(__file__).with_name("gambatte_cgb04c_pass.txt")
STRIDE = 60
ENTRIES = [line.split() for line in LIST.read_text().splitlines()][::STRIDE] if LIST.exists() else []

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not SUITE.exists() or not ENTRIES, reason="run scripts/fetch_references.py"),
]


def _runner():
    spec = importlib.util.spec_from_file_location("gambatte_dmg08", ROOT / "scripts/gambatte_dmg08.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name,kind", ENTRIES)
def test_passes(name, kind):
    runner = _runner()
    rom = SUITE / name
    results = runner.run((rom, True, False, True))
    assert any(ok for _n, k, ok, _sb in results if k == kind), f"{name} [{kind}]"
