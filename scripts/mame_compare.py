#!/usr/bin/env python3
"""Compare the board's per-instruction registers with a MAME trace (scripts/mame_trace.py).

    python scripts/mame_compare.py TRACE.log ROM.gb --boot dmg_boot.bin [--start 0000]
        [--ignore if] [--limit 1200000] [--require 100000]

MAME is a detector, not a judge (docs/validation.md): a divergence is a lead, to be settled with a
hardware-verified ROM or the die models. MAME's trace lines are ``pc af bc de hl sp ie if ...`` in
hex (MAME's T/4 = M); ``--start`` skips lines until the first PC (``0000`` for a boot ROM,
``0100`` for skip-boot). Both sides must run the same boot ROM. Exit 0 when the first divergence
is at or beyond ``--require`` instructions (the milestone-1 acceptance is 100,000 from $0100).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gameboy_python import GameBoy, load_cartridge

NAMES = ("pc", "af", "b", "c", "d", "e", "h", "l", "sp", "ie", "if")


def read_trace(path: Path, start: int, limit: int) -> list[list[int]]:
    rows: list[list[int]] = []
    started = False
    with path.open("rb") as stream:
        for line in stream:
            fields = line.split()
            if len(fields) < 13 or fields[0] in (b"R", b"W"):
                continue
            try:
                row = [int(x, 16) for x in fields[:12]]
            except ValueError:
                continue
            if not started and row[0] != start:
                continue
            started = True
            rows.append(row)
            if len(rows) > limit:
                break
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("trace", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--boot", type=Path, help="boot ROM image both sides ran")
    parser.add_argument("--start", default="0100", help="first PC in the trace (hex)")
    parser.add_argument("--ignore", default="", help="comma-separated fields to ignore")
    parser.add_argument("--limit", type=int, default=1_200_000)
    parser.add_argument("--require", type=int, default=100_000)
    args = parser.parse_args()
    ignore = set(filter(None, args.ignore.split(",")))
    rows = read_trace(args.trace, int(args.start, 16), args.limit)
    gb = GameBoy(
        load_cartridge(args.rom.read_bytes()),
        boot_rom=args.boot.read_bytes() if args.boot else None,
    )
    cpu = gb.cpu
    for i, row in enumerate(rows[: args.limit]):
        got = (
            cpu.pc,
            (cpu.a << 8) | cpu.f,
            cpu.b,
            cpu.c,
            cpu.d,
            cpu.e,
            cpu.h,
            cpu.l,
            cpu.sp,
            cpu.ie,
            cpu.if_,
        )
        bad = [
            n for n, g, w in zip(NAMES, got, row[:11], strict=True) if g != w and n not in ignore
        ]
        if bad:
            print(f"first divergence at instruction {i}: {bad}")
            print("  board", [hex(x) for x in got])
            print("  MAME ", [hex(x) for x in row[:11]])
            return 0 if i >= args.require else 1
        cpu.step()
    n = min(args.limit, len(rows))
    print(f"no divergence over {n} instructions")
    return 0 if n >= args.require else 1


if __name__ == "__main__":
    sys.exit(main())
