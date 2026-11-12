#!/usr/bin/env python3
"""Run a CGB test ROM on the CGB E board and compare its picture with a reference PNG.

    python scripts/cgb_picture.py ROM.gbc REFERENCE.png [--frames 60] [--boot real|skip] [--save out.png]

The reference pictures (cgb-acid2, cgb-acid-hell, Mealybug's CGB set) hold 8-bit channels made
from RGB555 by ``v * 255 / 31``; the board's frame is compared in RGB555 after scaling back. Prints
the number of differing pixels and, with ``--map``, a coarse map of where.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from pngread import read_rgb555  # noqa: E402

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.image import write_rgb_png  # noqa: E402

FRAME_T = 70224


def words(frame: bytes) -> list[int]:
    return [frame[i] | (frame[i + 1] << 8) for i in range(0, len(frame), 2)]


def run(rom: Path, frames: int, boot: str, machine: str = "cgb") -> bytes:
    image, label = (None, "skip-boot") if boot == "skip" else find_boot_rom("CGB")
    if boot == "real" and label != "real boot ROM":
        raise SystemExit("no real CGB boot ROM")
    gb = GameBoy(load_cartridge(rom.read_bytes()), MACHINES[machine], boot_rom=image)
    step = gb.cpu.step
    end = frames * FRAME_T
    while gb.t < end:
        step()
    return gb.ppu.frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rom", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--boot", choices=("real", "skip"), default="real")
    parser.add_argument("--machine", default="cgb")
    parser.add_argument("--save", type=Path)
    parser.add_argument("--map", action="store_true")
    args = parser.parse_args()
    frame = run(args.rom, args.frames, args.boot, args.machine)
    if args.save:
        write_rgb_png(args.save, frame)
    got = words(frame)
    want, _w, _h = read_rgb555(args.reference)
    bad = [i for i, (a, b) in enumerate(zip(got, want, strict=True)) if a != b]
    print(f"{len(bad)} of {len(want)} pixels differ")
    if args.map and bad:
        for y in range(0, 144, 4):
            print(
                "".join(
                    "X"
                    if any(
                        got[(y + dy) * 160 + x] != want[(y + dy) * 160 + x]
                        for dy in range(4)
                        for x in range(xx, xx + 4)
                    )
                    else "."
                    for xx in range(0, 160, 4)
                )
            )
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
