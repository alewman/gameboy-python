#!/usr/bin/env python3
"""Run every GBMicrotest ROM and report which pass ($FF82 = 1).

    python scripts/gbmicrotest.py [--write tests/gbmicrotest_pass.txt] [--jobs N]

Tests are started from the skip-boot state, except ``poweron_*``, which measure what the real boot
ROM leaves behind and so run from the real DMG boot ROM (skipped when it is absent). ROMs that
report no result by protocol (screens, test benches: $FF82 stays 0) count as not passing and are
listed apart. ``--write`` records the passing set that ``tests/test_gbmicrotest.py`` holds the
board to.
"""

from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.testrom import run_microtest  # noqa: E402

ROMS = ROOT / "tests/test_roms/gbtr/gbmicrotest"
BOOT_FRAMES = 352


def run(path: Path) -> tuple[str, int, int, int]:
    real = path.name.startswith("poweron_")
    boot, label = find_boot_rom("DMG") if real else (None, "")
    if real and label != "real boot ROM":
        return path.name, -1, 0, 0
    gb = GameBoy(load_cartridge(path.read_bytes()), boot_rom=boot)
    run_microtest(gb, 12 + (BOOT_FRAMES if real else 0))
    return path.name, gb.hram[2], gb.hram[0], gb.hram[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", type=Path)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    roms = sorted(ROMS.glob("*.gb"))
    with Pool(args.jobs) as pool:
        results = pool.map(run, roms, chunksize=4)
    passed = [r[0] for r in results if r[1] == 1]
    silent = [r[0] for r in results if r[1] == 0]
    failed = [r for r in results if r[1] == 255]
    print(
        f"{len(passed)} of {len(results)} pass; {len(silent)} report no result; {len(failed)} fail"
    )
    for name, _status, got, want in failed:
        print(f"  fail {name}: got {got} expected {want}")
    if args.write:
        args.write.write_text("".join(f"{n}\n" for n in passed))
        print(f"wrote {len(passed)} names to {args.write}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
