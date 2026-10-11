#!/usr/bin/env python3
"""Show what an AGE test ROM measured against what it expects (CGB E board).

    python scripts/age_diag.py ly/ly-ncmE [--frames 40]

The numerical AGE tests keep one row of 8 results each at $C000 ("TEST_RESULTS") and compare them
with ``EXPECTED_TEST_RESULTS_DMG`` (non-CGB mode) or ``_CGB`` in their source. Names with a table
this script cannot parse are reported as such.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402

SOURCES = ROOT / "reference/src/age-test-roms/src"
ROMS = ROOT / "tests/test_roms/gbtr/age-test-roms"


def source_text(asm: Path) -> str:
    text = asm.read_text()
    for include in re.findall(r'INCLUDE\s+"([^"]+)"', text):
        path = SOURCES / include
        if path.exists() and not include.startswith("hardware") and "test-setup" not in include:
            text += "\n" + source_text(path)
    return text


def table(text: str, name: str, l99: int) -> list[list[int]] | None:
    match = re.search(rf"{name}:(.*?)(?:\n\s*\n|\n[A-Za-z_.]+:)", text, re.S)
    if not match:
        return None
    rows = []
    for line in match.group(1).splitlines():
        line = line.split(";")[0].strip()
        if not line.upper().startswith("DB"):
            continue
        values = []
        for item in line[2:].split(","):
            item = item.strip().replace("$", "0x")
            if item == "L99":
                values.append(l99)
            elif item:
                try:
                    values.append(int(item, 0))
                except ValueError:
                    values.append(-1)
        rows.append(values)
    return rows[1:]  # the first DB is the row count


def timing(gb: GameBoy, text: str) -> int:
    """Raw TIMING_RESULTS ($C080, 12 bytes a line) against EXPECTED_TIMING_RESULTS."""
    eff = 0xFF if "CGB_E EQU 1" in text else 0
    match = re.search(r"EXPECTED_TIMING_RESULTS:(.*?)(?:\n\s*\n\s*\n|\ntimed)", text, re.S)
    assert match, "no timing table"
    lines = []
    for line in match.group(1).splitlines():
        line = line.split(";")[0].strip()
        if line.upper().startswith("DB"):
            lines.append(
                [eff if v.strip() == "EFF" else int(v.strip().replace("$", "0x"), 0) for v in line[2:].split(",") if v.strip()]
            )
    bad = 0
    for i, want in enumerate(lines):
        got = [gb.peek(0xC000 + i * len(want) + j) for j in range(len(want))]
        if got != want:
            bad += 1
            print(f"line {i:3d} got  " + " ".join(f"{v:02x}" for v in got))
            print(f"         want " + " ".join(f"{v:02x}" for v in want))
    print(f"{len(lines) - bad} of {len(lines)} timing lines match")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", help="e.g. ly/ly-ncmE")
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--timing", action="store_true", help="raw timing rows (oam/vram tests)")
    args = parser.parse_args()
    stem = Path(args.name).name
    asm = SOURCES / Path(args.name).parent / f"{stem}.asm"
    text = source_text(asm)
    non_cgb = "CART_REQUIRES_NON_CGB_MODE" in text or "CART_COMPATIBLE_DMG\n" in text
    l99 = 0x99 if "EXTEND_L99" in text else 0
    rom = ROMS / Path(args.name).parent / f"{stem}.gb"
    gb = GameBoy(load_cartridge(rom.read_bytes()), MACHINES["cgb"])
    end = args.frames * 70224
    while gb.t < end:
        gb.cpu.step()
    if args.timing:
        return timing(gb, text)
    want = table(text, "EXPECTED_TEST_RESULTS_DMG" if non_cgb else "EXPECTED_TEST_RESULTS_CGB", l99)
    if want is None:
        print("no expected table parsed")
        return 1
    bad = 0
    for i, row in enumerate(want):
        got = [gb.peek(0xC000 + i * 8 + j) for j in range(len(row))]
        mark = "" if got == row else "   <-- differs"
        bad += got != row
        print("got ", " ".join(f"{v:02x}" for v in got))
        print("want", " ".join(f"{v:02x}" for v in row), mark)
    print(f"{len(want) - bad} of {len(want)} rows match ({'non-CGB' if non_cgb else 'CGB'} mode table)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
