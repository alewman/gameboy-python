#!/usr/bin/env python3
"""Run the Mooneye acceptance and misc ROMs that apply to a CPU CGB E on the CGB board.

    python scripts/mooneye_cgb.py [--boot skip|real] [--jobs 8] [NAME ...]

A ROM applies when its source's ``pass:`` list names CGB (or CGB ABCDE). Each is run to ``LD B,B``
and judged by Mooneye's Fibonacci registers.
"""

from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.testrom import run_mooneye  # noqa: E402
from tests.mooneye_meta import ROMS, applicable, applicable_misc  # noqa: E402


def one(args: tuple[str, str, str]) -> tuple[str, bool, str]:
    name, path, boot = args
    image = find_boot_rom("CGB")[0] if boot == "real" else None
    gb = GameBoy(load_cartridge(Path(path).read_bytes()), MACHINES["cgb"], boot_rom=image)
    result = run_mooneye(gb, max_frames=1500)
    return name, result.passed, f"{result.protocol} {result.registers}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*")
    parser.add_argument("--boot", choices=("skip", "real"), default="skip")
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    assert ROMS is not None
    items = [(n, str(ROMS / f"{n}.gb")) for n in applicable("cgb")]
    items += [(f"misc/{n}", str(ROMS.parent / "misc" / f"{n}.gb")) for n in applicable_misc()]
    if args.names:
        items = [i for i in items if any(n in i[0] for n in args.names)]
    with Pool(args.jobs) as pool:
        results = pool.map(one, [(n, p, args.boot) for n, p in items], chunksize=1)
    failed = [r for r in results if not r[1]]
    for name, _ok, info in failed:
        print(f"FAIL {name}: {info}")
    print(f"{len(results) - len(failed)} of {len(results)} pass")
    return 0 if not failed else 1


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
