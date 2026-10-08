#!/usr/bin/env python3
"""Score the board's pictures against Mealybug Tearoom's DMG-blob screenshots (pixel counts).

    python scripts/mealybug_compare.py [--frames 420] [--skip-boot] [--png-dir DIR]

Run from the repository root with ``scripts/fetch_references.py`` done. The tests draw tiles the
boot ROM left in VRAM (the (R) glyph), so they are booted with the real DMG boot ROM by default. Prints, per test, how many
of the 23,040 pixels differ from ``<test>_dmg_blob.png``; the expected pictures are the Mealybug
author's emulator output checked against photographs (tier 2: docs/validation.md), so a match is
strong evidence and a miss is a lead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.image import write_png  # noqa: E402
from gameboy_python.testrom import run_mooneye  # noqa: E402
from tests.pngread import read_shades  # noqa: E402

PPU_DIR = ROOT / "tests/test_roms/gbtr/mealybug-tearoom-tests/ppu"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--frames", type=int, default=420, help="frames to run, boot included")
    parser.add_argument("--skip-boot", action="store_true", help="start from the skip-boot state")
    parser.add_argument("--png-dir", type=Path)
    args = parser.parse_args()
    boot = None
    if not args.skip_boot:
        boot, label = find_boot_rom("DMG")
        if label != "real boot ROM":
            sys.exit(f"no real DMG boot ROM ({label}); pass --skip-boot")
    exact = total = 0
    for rom in sorted(PPU_DIR.glob("*.gb")):
        expected = PPU_DIR / f"{rom.stem}_dmg_blob.png"
        if not expected.exists():
            continue
        gb = GameBoy(load_cartridge(rom.read_bytes()), boot_rom=boot)
        run_mooneye(gb, max_frames=args.frames)
        want = read_shades(expected)[0]
        diff = sum(1 for a, b in zip(gb.ppu.frame, want, strict=True) if a != b)
        print(f"{rom.stem:40s} {diff:6d}")
        exact += diff == 0
        total += 1
        if args.png_dir:
            args.png_dir.mkdir(parents=True, exist_ok=True)
            write_png(args.png_dir / f"{rom.stem}.png", gb.ppu.frame)
    print(f"{exact} of {total} pixel-exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
