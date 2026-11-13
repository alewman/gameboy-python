#!/usr/bin/env python3
"""Learn how Gambatte's test ROMs report, from the ROMs and their expected pictures alone.

    python scripts/gambatte_learn.py [--jobs J] [--stride N]

Writes the two tables ``scripts/gambatte_dmg08.py`` reads:

* ``tests/gambatte_glyphs.txt``: the 8x8 tile each hex digit is drawn with. A digit test's ROM
  name gives the digits its screen shows on hardware (``..._out5576AA34``), and the digits are
  drawn along the top row of the picture, one tile each; every N-th such ROM is run on the DMG
  board and each tile is filed under the digit the name gives for it. The tile seen most often for
  a digit is its glyph (the board passes most of these ROMs, so a wrong picture loses the vote).
* ``tests/gambatte_cgb_colours.txt``: the colour a CGB picture test's expected PNG shows for each
  RGB555 colour word. Every CGB picture test is run on the ``cgb-c`` board and its frame paired
  with the PNG pixel by pixel; each word is filed under the PNG colour (low three bits of each
  channel masked) and the colour seen most often wins.
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from pngread import read_rgb888  # noqa: E402

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.machines import DMG_B  # noqa: E402

SUITE = ROOT / "tests/test_roms/gbtr/gambatte"
FRAME_T = 70224
GLYPHS = ROOT / "tests/gambatte_glyphs.txt"
COLOURS = ROOT / "tests/gambatte_cgb_colours.txt"
DIGITS = re.compile(r"dmg08(?:_cgb04c)?_out([0-9A-Fa-f]+)")


def frame_of(rom: Path, cgb: bool) -> bytes:
    gb = GameBoy(load_cartridge(rom.read_bytes()), MACHINES["cgb-c"] if cgb else DMG_B)
    while gb.t < 15 * FRAME_T:
        gb.cpu.step()
    return bytes(gb.ppu.frame)


def tiles(rom: Path) -> list[tuple[str, bytes]]:
    digits = DIGITS.search(rom.with_suffix("").name).group(1).lower()
    frame = frame_of(rom, False)
    return [
        (ch, b"".join(frame[y * 160 + i * 8 : y * 160 + i * 8 + 8] for y in range(8)))
        for i, ch in enumerate(digits)
    ]


def colour_pairs(rom: Path) -> collections.Counter:
    png = rom.with_name(rom.with_suffix("").name + "_cgb04c.png")
    if not png.exists():
        png = rom.with_name(rom.with_suffix("").name + "_dmg08_cgb04c.png")
    pixels, width, height = read_rgb888(png)
    frame = frame_of(rom, True)
    if (width, height) != (160, 144):
        return collections.Counter()
    words = [(frame[i] | (frame[i + 1] << 8)) & 0x7FFF for i in range(0, len(frame), 2)]
    return collections.Counter(zip(words, (p & 0xF8F8F8 for p in pixels), strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--stride", type=int, default=5)
    args = parser.parse_args()
    roms = sorted(p for p in SUITE.rglob("*.gb*") if DIGITS.search(p.with_suffix("").name))
    cgb_roms = sorted(
        p
        for p in SUITE.rglob("*.gbc")
        if p.with_name(p.with_suffix("").name + "_cgb04c.png").exists()
        or p.with_name(p.with_suffix("").name + "_dmg08_cgb04c.png").exists()
    )
    with Pool(args.jobs) as pool:
        votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for result in pool.imap_unordered(tiles, roms[:: args.stride]):
            for ch, tile in result:
                votes[ch][tile] += 1
        pairs: collections.Counter = collections.Counter()
        for result in pool.imap_unordered(colour_pairs, cgb_roms):
            pairs.update(result)
    lines = [f"# scripts/gambatte_learn.py --stride {args.stride}: digit, 8 rows (# = shade 3)"]
    for ch in "0123456789abcdef":
        (tile, n), *_ = votes[ch].most_common(1)
        share = n / sum(votes[ch].values())
        rows = "|".join(
            "".join("#" if tile[y * 8 + x] == 3 else "." for x in range(8)) for y in range(8)
        )
        lines.append(f"{ch} {rows}  # {n} of {sum(votes[ch].values())} ({share:.0%})")
    GLYPHS.write_text("\n".join(lines) + "\n")
    best: dict[int, tuple[int, int]] = {}
    for (word, colour), n in pairs.items():
        if n > best.get(word, (0, 0))[1]:
            best[word] = (colour, n)
    out = [f"# scripts/gambatte_learn.py over {len(cgb_roms)} CGB picture tests: RGB555, RRGGBB"]
    out += [f"{word:04X} {colour:06X}" for word, (colour, _) in sorted(best.items())]
    COLOURS.write_text("\n".join(out) + "\n")
    print(f"{GLYPHS.name}: 16 digits; {COLOURS.name}: {len(best)} colour words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
