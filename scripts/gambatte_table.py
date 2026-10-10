#!/usr/bin/env python3
"""Tabulate a ``gambatte_dmg08.py --json`` result by test directory: board and SameBoy beside
each other, only directories where either fails.  python scripts/gambatte_table.py RESULT.json"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1] / "tests/test_roms/gbtr/gambatte"


def main() -> int:
    where = {}
    for p in SUITE.rglob("*"):
        where.setdefault(p.name, p.parent.name)
    rows: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for name, _kind, ok, sb in json.loads(Path(sys.argv[1]).read_text()):
        row = rows[where[name]]
        row[0] += 1
        row[1] += bool(ok)
        row[2] += bool(sb)
    total = [sum(r[i] for r in rows.values()) for i in range(3)]
    print(f"| all | {total[0]} | {total[1]} | {total[2]} |")
    print("| directory | tests | board | SameBoy |\n|---|---|---|---|")
    for d, (n, a, b) in sorted(rows.items()):
        if a != n or b != n:
            print(f"| {d} | {n} | {a} | {b} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
