#!/usr/bin/env python3
"""Run the picture-judged CGB tests: cgb-acid-hell and Mealybug's CGB pictures (CPU CGB D).

    python scripts/cgb_pictures.py [--jobs 8] [--frames 260] [--revision cgb_d|cgb_c] [NAME ...]

Each ROM runs from the real CGB boot ROM (the boot ROM chooses the compatibility palettes of the
DMG-header Mealybug ROMs) and the last frame is compared pixel by pixel in RGB555 with the
reference PNG (``cgb_picture.py``).
"""

from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from cgb_picture import run, words  # noqa: E402
from pngread import read_rgb555  # noqa: E402

BASE = ROOT / "tests/test_roms/gbtr"


def cases(revision: str) -> list[tuple[Path, Path]]:
    found = [(BASE / "cgb-acid-hell/cgb-acid-hell.gbc", BASE / "cgb-acid-hell/cgb-acid-hell.png")]
    for png in sorted((BASE / "mealybug-tearoom-tests/ppu").glob(f"*_{revision}.png")):
        rom = png.with_name(png.name[: -len(f"_{revision}.png")] + ".gb")
        if rom.exists():
            found.append((rom, png))
    return found


def one(args: tuple[Path, Path, int]) -> tuple[str, int]:
    rom, png, frames = args
    got = words(run(rom, frames, "real"))
    want, _w, _h = read_rgb555(png)
    return rom.name, sum(a != b for a, b in zip(got, want, strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--frames", type=int, default=260)
    parser.add_argument("--revision", default="cgb_d")
    args = parser.parse_args()
    work = [
        (rom, png, args.frames)
        for rom, png in cases(args.revision)
        if not args.names or any(n in rom.name for n in args.names)
    ]
    with Pool(args.jobs) as pool:
        results = pool.map(one, work, chunksize=1)
    exact = 0
    for name, bad in results:
        print(f"{'ok  ' if not bad else 'DIFF'} {name}: {bad} pixels differ")
        exact += not bad
    print(f"{exact} of {len(results)} pixel-exact")
    return 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
