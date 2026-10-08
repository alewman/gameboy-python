"""Which Mooneye acceptance ROMs apply to the reference model (DMG-CPU B).

Every test's source carries a "Verified results" header naming the devices that pass:
``pass: DMG, MGB, SGB, ...`` or ``pass: DMG ABC, MGB`` (``DMG 0`` is the first revision only).
A ROM applies to a DMG-CPU B when its pass list names ``DMG`` or ``DMG ABC``.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "reference" / "src" / "mooneye-test-suite" / "acceptance"
ROMS = next(iter((ROOT / "tests" / "test_roms").glob("mts-*/acceptance")), None)


def passes_on_dmg_abc(source: str) -> bool:
    match = re.search(r"^;\s*pass:\s*(.+)$", source, re.MULTILINE)
    if not match:
        return False
    devices = [d.strip() for d in match.group(1).split(",")]
    return any(d in ("DMG", "DMG ABC") for d in devices)


def applicable() -> list[str]:
    """Names (path under acceptance/, no extension) of the ROMs that apply to DMG-CPU B."""
    if not SOURCES.is_dir():
        return []
    return [
        str(path.relative_to(SOURCES).with_suffix(""))
        for path in sorted(SOURCES.rglob("*.s"))
        if passes_on_dmg_abc(path.read_text(errors="replace"))
    ]
