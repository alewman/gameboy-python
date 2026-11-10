"""Gambatte's ``dmg08`` hardware tests: the board must keep passing what it passes today.

``tests/gambatte_dmg08_pass.txt`` (1,618 verdicts, written from ``scripts/gambatte_dmg08.py --json``)
lists them; running all takes hours, so this holds every STRIDE-th one, from the post-boot state
(the real-boot run gave the same total). Rerun the script after a change that touches timing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "tests/test_roms/gbtr/gambatte"
LIST = Path(__file__).with_name("gambatte_dmg08_pass.txt")
STRIDE = 40
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
    results = runner.run((rom, True, False, False))
    assert any(ok for _n, k, ok, _sb in results if k == kind), f"{name} [{kind}]"
