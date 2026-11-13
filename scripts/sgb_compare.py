#!/usr/bin/env python3
"""Compare the HLE Super Game Boy's pictures (src/gameboy_python/sgb.py) with a judge's:
snes-python running the real SGB BIOS (scripts/sgb_lle_run.py) or SameBoy's SGB
(scripts/sgb_sameboy.py). Colours are compared at the SNES's 5 bits per channel.

    python scripts/sgb_compare.py GAME.zip --boot sns_rom_sgb.zip --lle OUT_DIR
    python scripts/sgb_compare.py GAME.zip --boot sns_rom_sgb.zip --sameboy OUT_DIR \
        --frames 600 900 1200 1500

Frame matching: the two sides count frames differently (snes-python saves at SNES frames and
records the Game Boy frame count; SameBoy counts its own), so each judge picture is compared
with the HLE pictures of nearby Game Boy frames and the closest is reported (``--search``).
SameBoy draws the layers from line 0, the SNES (and sgb.py) from line 1: its line y + 1 is
compared with our line y. The last line (blanked by the BIOS, sgb.BLANK_LINES) is compared
only against snes-python. ``--out-dir`` keeps the closest HLE picture of each point as PNG.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gameboy_python import MACHINES, GameBoy, load_cartridge
from gameboy_python.boot import read_image
from gameboy_python.frontend import read_rom
from gameboy_python.image import rgb24_png_bytes
from gameboy_python.sgb import (
    FIRST_LINE,
    GB_H,
    GB_W,
    SNES_H,
    SNES_W,
    WINDOW_X,
    WINDOW_Y,
    SuperGameBoy,
    rgb_bytes,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from pngread import read_rgb888


def words_of(path: Path) -> list[int]:
    """A PNG as SNES words (each 8-bit channel's top 5 bits)."""
    return [
        (value >> 19 & 31) | (value >> 11 & 31) << 5 | (value >> 3 & 31) << 10
        for value in read_rgb888(path)[0]
    ]


def differences(mine, judge: list[int], shift: int, lines: int) -> tuple[int, int]:
    """(pixels differing, of which in the Game Boy window) over the first ``lines`` lines."""
    total = window = 0
    for y in range(lines):
        gy = y + FIRST_LINE - WINDOW_Y
        for x in range(SNES_W):
            if mine[y * SNES_W + x] != judge[(y + shift) * SNES_W + x]:
                total += 1
                if 0 <= gy < GB_H and 0 <= x - WINDOW_X < GB_W:
                    window += 1
    return total, window


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rom", type=Path)
    parser.add_argument("--boot", type=Path, required=True, help="the SGB boot ROM both used")
    judge = parser.add_mutually_exclusive_group(required=True)
    judge.add_argument("--lle", type=Path, help="a directory from sgb_lle_run.py")
    judge.add_argument("--sameboy", type=Path, help="a directory from sgb_sameboy.py")
    parser.add_argument("--frames", type=int, nargs="*", help="judge frames (default: all)")
    parser.add_argument("--search", type=int, help="frames either side (lle 3, sameboy 8)")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)

    points: dict[int, tuple[Path, int]] = {}  # judge frame -> (picture, centre HLE frame)
    if args.lle:
        index = json.loads((args.lle / "index.json").read_text())
        for snes_frame, gb_frame in index.items():
            points[int(snes_frame)] = (args.lle / f"snes_{int(snes_frame):05d}.png", gb_frame)
        shift, lines, search = 0, SNES_H, 3 if args.search is None else args.search
    else:
        for path in sorted(args.sameboy.glob("sameboy_*.png")):
            frame = int(path.stem.split("_")[1])
            points[frame] = (path, frame)
        shift, lines, search = 1, SNES_H - 1, 8 if args.search is None else args.search
    if args.frames:
        points = {f: p for f, p in points.items() if f in args.frames}
    wanted: dict[int, list[int]] = {}
    for frame, (_path, centre) in points.items():
        for hle in range(centre - search, centre + search + 1):
            wanted.setdefault(hle, []).append(frame)

    gb = GameBoy(
        load_cartridge(read_rom(args.rom)), MACHINES["sgb"], boot_rom=read_image(args.boot)
    )
    sgb = SuperGameBoy(gb)
    judges = {frame: words_of(path) for frame, (path, _c) in points.items()}
    best: dict[int, tuple[int, int, int]] = {}
    keep: dict[int, bytes] = {}
    while wanted and gb.ppu.frames <= max(wanted):
        gb.run_frames(1)
        if gb.ppu.frames not in wanted:
            continue
        mine = sgb.render()
        for frame in wanted[gb.ppu.frames]:
            total, window = differences(mine, judges[frame], shift, lines)
            if frame not in best or total < best[frame][0]:
                best[frame] = (total, window, gb.ppu.frames)
                keep[frame] = rgb_bytes(mine)
    exact = 0
    for frame in sorted(best):
        total, window, hle = best[frame]
        exact += total == 0
        print(f"judge frame {frame:5d}  HLE frame {hle:5d}  differ {total:6d}  (window {window})")
        if args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            png = rgb24_png_bytes(keep[frame], SNES_W, SNES_H)
            (args.out_dir / f"hle_{frame:05d}.png").write_bytes(png)
    print(f"{exact} of {len(best)} pictures exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
