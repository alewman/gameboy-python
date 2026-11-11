#!/usr/bin/env python3
"""Run SameSuite and the AGE test ROMs that apply to a CPU CGB E on the CGB board.

    python scripts/cgb_suites.py [same-suite|age] [--jobs 8] [--sameboy] [--json OUT] [NAME ...]

Both suites pass when B, C, D, E, H, L = 3, 5, 8, 13, 21, 34 at ``LD B,B``. AGE names carry their
devices (``-cgbBCE``, ``-cgbE``, ``-ncmE`` for non-CGB mode on that revision, ``-dmgC-cgbBCE``):
a ROM applies to CGB E when a device group names E. Screenshot-only AGE tests are left to
``scripts/cgb_picture.py``. SameSuite's sgb/ directory is not a CGB test.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.testrom import run_mooneye  # noqa: E402

BASE = ROOT / "tests/test_roms/gbtr"


def applies_age(name: str) -> bool:
    stem = Path(name).stem
    return any(
        re.fullmatch(r"(cgb|ncm)[A-Z]*E[A-Z]*", part) for part in stem.split("-")[1:]
    )


def roms(suite: str) -> list[Path]:
    root = BASE / ("same-suite" if suite == "same-suite" else "age-test-roms")
    found = sorted(root.rglob("*.gb"))
    if suite == "same-suite":
        # a trailing device suffix (-cgb0B, -cgbDE, -A) names the revisions the ROM was captured
        # on; it applies to a CGB E only when the group names E
        return [
            p
            for p in found
            if "sgb" not in p.parts
            and (not (m := re.search(r"-([A-Za-z0-9]+)\.gb$", p.name)) or re.fullmatch(r"cgb[0-9A-Z]*E", m.group(1)))
        ]
    return [p for p in found if applies_age(p.name)]


def one(path: Path) -> tuple[str, bool, str]:
    gb = GameBoy(load_cartridge(path.read_bytes()), MACHINES["cgb"])
    result = run_mooneye(gb, max_frames=600)
    return str(path.relative_to(BASE)), result.passed, f"{result.protocol} {result.registers}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("suite", choices=("same-suite", "age"))
    parser.add_argument("names", nargs="*")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    items = [p for p in roms(args.suite) if not args.names or any(n in str(p) for n in args.names)]
    with Pool(args.jobs) as pool:
        results = pool.map(one, items, chunksize=1)
    if args.json:
        args.json.write_text(json.dumps(results))
    failed = [r for r in results if not r[1]]
    for name, _ok, info in failed:
        print(f"FAIL {name}: {info}")
    print(f"{len(results) - len(failed)} of {len(results)} pass")
    return 0 if not failed else 1


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
