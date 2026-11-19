#!/usr/bin/env python3
"""Show what a SameSuite ROM measured against what it expects (CGB E board).

    python scripts/samesuite_diag.py apu/channel_3/channel_3_delay [--frames 30] [--machine cgb]

SameSuite tests store one row of 8 results each at $C000 and compare them with the ``db`` rows
after ``CorrectResults:`` in their source; this prints both, a row per line, and marks differences.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402

SOURCES = ROOT / "reference/src/SameSuite"
ROMS = ROOT / "tests/test_roms/gbtr/same-suite"


def expected(source: str) -> list[list[int]]:
    rows: list[list[int]] = []
    inside = False
    for line in source.splitlines():
        if line.strip().startswith("CorrectResults:"):
            inside = True
            continue
        if inside:
            text = line.split(";")[0].strip()
            if text.lower().startswith("db"):
                values = [
                    int(v.strip().replace("$", "0x"), 0) for v in text[2:].split(",") if v.strip()
                ]
                rows.append(values)
            elif text and not text.lower().startswith(("dw", "ds")) and rows:
                break
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name")
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--machine", default="cgb")
    args = parser.parse_args()
    rom = ROMS / f"{args.name}.gb"
    source = (SOURCES / f"{args.name}.asm").read_text()
    gb = GameBoy(load_cartridge(rom.read_bytes()), MACHINES[args.machine])
    end = args.frames * 70224
    while gb.t < end:
        gb.cpu.step()
    want = expected(source)
    n = (
        int(re.search(r"RESULTS_N_ROWS\s+EQU\s+(\d+)", source).group(1))
        if "RESULTS_N_ROWS" in source
        else len(want)
    )
    width = len(want[0]) if want else 8
    bad = 0
    for i in range(n):
        got = [gb.peek(0xC000 + i * width + j) for j in range(width)]
        w = want[i] if i < len(want) else []
        mark = "" if got == w else "   <-- differs"
        bad += got != w
        print("got ", " ".join(f"{v:02x}" for v in got))
        print("want", " ".join(f"{v:02x}" for v in w), mark)
    print(f"{n - bad} of {n} rows match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
