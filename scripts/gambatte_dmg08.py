#!/usr/bin/env python3
"""Run Gambatte's hardware-captured tests that carry a DMG-08 result and tabulate them.

    python scripts/gambatte_dmg08.py [--write tests/gambatte_dmg08_pass.txt] [--only SUBDIR]

The rules are testrunner.cpp's. A ROM whose name holds ``dmg08_out<hex digits>`` or
``dmg08_cgb04c_out<hex digits>`` is a screen-digit test (the digits are 8x8 tiles along the top row
of the picture); ``<name>_dmg08.png`` / ``<name>_dmg08_cgb04c.png`` beside a ROM is a picture test
(every pixel compared after masking the low three bits of each channel). Both run on a DMG with the
real boot ROM for 334 + 15 frames (70,224 T-cycles each) from power-on and read the final picture.
The ``_outaudio`` tests are ``scripts/gambatte_audio.py``'s.
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
sys.path.insert(0, str(ROOT / "tests"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from pngread import read_shades  # noqa: E402

SUITE = ROOT / "tests/test_roms/gbtr/gambatte"
FRAME_T = 70224
FRAMES = 334 + 15

# testrunner.cpp's 8x8 digit tiles: 3 black, 0 the lightest


def _glyphs() -> dict[str, bytes]:
    rows = {
        "0": "........|.#######|.#.....#|.#.....#|.#.....#|.#.....#|.#.....#|.#######",
        "1": "........|....#...|....#...|....#...|....#...|....#...|....#...|....#...",
        "2": "........|.#######|.......#|.......#|.#######|.#......|.#......|.#######",
        "3": "........|.#######|.......#|.......#|..######|.......#|.......#|.#######",
        "4": "........|.#.....#|.#.....#|.#.....#|.#######|.......#|.......#|.......#",
        "5": "........|.#######|.#......|.#......|.######.|.......#|.......#|.######.",
        "6": "........|.#######|.#......|.#......|.#######|.#.....#|.#.....#|.#######",
        "7": "........|.#######|.......#|......#.|.....#..|....#...|...#....|...#....",
        "8": "........|..#####.|.#.....#|.#.....#|..#####.|.#.....#|.#.....#|..#####.",
        "9": "........|.#######|.#.....#|.#.....#|.#######|.......#|.......#|.#######",
        "a": "........|....#...|..#...#.|.#.....#|.#######|.#.....#|.#.....#|.#.....#",
        "b": "........|.######.|.#.....#|.#.....#|.######.|.#.....#|.#.....#|.######.",
        "c": "........|..#####.|.#.....#|.#......|.#......|.#......|.#.....#|..#####.",
        "d": "........|.######.|.#.....#|.#.....#|.#.....#|.#.....#|.#.....#|.######.",
        "e": "........|.#######|.#......|.#......|.#######|.#......|.#......|.#######",
        "f": "........|.#######|.#......|.#......|.#######|.#......|.#......|.#......",
    }
    return {k: bytes(3 if c == "#" else 0 for r in v.split("|") for c in r) for k, v in rows.items()}


TILES = _glyphs()


def plan(rom: Path) -> list[tuple[str, str]]:
    """The DMG tests this ROM carries: ("out", digits) or ("png", path)."""
    stem = rom.with_suffix("").name
    tests: list[tuple[str, str]] = []
    for marker in ("dmg08_cgb04c_out", "dmg08_out"):
        if marker in stem:
            tail = stem[stem.index(marker) + len(marker) :]
            if not tail.startswith("audio"):
                match = re.match(r"[0-9a-fA-F]+", tail)
                tests.append(("out", match.group(0).lower() if match else ""))
            break
    for suffix in ("_dmg08_cgb04c.png", "_dmg08.png"):
        png = rom.with_name(rom.with_suffix("").name + suffix)
        if png.exists():
            tests.append(("png", str(png)))
            break
    return tests


def matches_out(frame: bytes, digits: str) -> bool:
    for i, ch in enumerate(digits):
        tile = TILES[ch]
        for y in range(8):
            if frame[y * 160 + i * 8 : y * 160 + i * 8 + 8] != tile[y * 8 : y * 8 + 8]:
                return False
    return True


def judge(frame: bytes, tests: list[tuple[str, str]]) -> list[bool]:
    out = []
    for kind, what in tests:
        if kind == "out":
            out.append(matches_out(frame, what))
        else:
            shades, width, height = read_shades(Path(what))
            out.append((width, height) == (160, 144) and shades == frame)
    return out


def run(args: tuple[Path, bool, bool]) -> list[tuple[str, str, bool, bool | None]]:
    rom, skip_boot, with_sameboy = args
    tests = plan(rom)
    if not tests:
        return []
    boot, label = (None, "") if skip_boot else find_boot_rom("DMG")
    if not skip_boot and label != "real boot ROM":
        raise SystemExit("no real DMG boot ROM")
    gb = GameBoy(load_cartridge(rom.read_bytes()), boot_rom=boot)
    end = (15 if skip_boot else FRAMES) * FRAME_T
    step = gb.cpu.step
    while gb.t < end:
        step()
    frame = bytes(gb.ppu.frame)
    ours = judge(frame, tests)
    theirs = sameboy(rom) if with_sameboy else [None] * len(tests)
    return [
        (rom.name, k, ok, sb)
        for (k, _), ok, sb in zip(tests, ours, theirs, strict=True)
    ]


def sameboy(rom: Path) -> list[bool]:
    """SameBoy DMG-B's verdicts on the same tests, from the same boot ROM."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from compat_sweep import sameboy_frames

    boot = find_boot_rom("DMG")[0]
    frame = sameboy_frames(rom.read_bytes(), FRAMES, boot, 1)[0]
    return judge(frame, plan(rom))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", type=Path)
    parser.add_argument("--only", help="a subdirectory of the suite, e.g. m2int_m2stat")
    parser.add_argument("--sameboy", action="store_true")
    parser.add_argument("--skip-boot", action="store_true", help="start from the post-boot state, 15 frames")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--sameboy-from", type=Path, help="reuse the SameBoy column of an earlier --json")
    parser.add_argument("--jobs", type=int, default=14)
    args = parser.parse_args()
    base = SUITE / args.only if args.only else SUITE
    roms = [p for p in sorted(base.rglob("*")) if p.suffix in (".gb", ".gbc") and plan(p)]
    work = [(p, args.skip_boot, args.sameboy) for p in roms]
    with Pool(args.jobs) as pool:
        results = [r for rs in pool.imap(run, work, chunksize=2) for r in rs]
    if args.sameboy_from:
        old = {(n, k): sb for n, k, _ok, sb in json.loads(args.sameboy_from.read_text())}
        results = [(n, k, ok, old.get((n, k))) for n, k, ok, _sb in results]
        args.sameboy = True
    if args.json:
        args.json.write_text(json.dumps([[*r[:2], r[2], r[3]] for r in results]))
    passed = [r for r in results if r[2]]
    print(f"{len(passed)} of {len(results)} agree with the DMG-08 ({len(roms)} ROMs)", flush=True)
    where = {p.name: p for p in roms}
    by_dir: dict[str, list[int]] = {}
    for name, _kind, ok, _sb in results:
        tally = by_dir.setdefault(where[name].parent.name, [0, 0])
        tally[0] += ok
        tally[1] += 1
    for d, (a, b) in sorted(by_dir.items()):
        if a != b:
            print(f"  {d}: {a}/{b}")
    if args.sameboy:
        table = {(a, b): 0 for a in (True, False) for b in (True, False)}
        for _name, _kind, ok, sb in results:
            table[ok, sb] += 1
        print(
            "board / SameBoy: both pass %d, both fail %d, board only %d, SameBoy only %d"
            % (table[True, True], table[False, False], table[True, False], table[False, True])
        )
        for name, kind, ok, sb in results:
            if not ok:
                note = "(SameBoy too)" if not sb else "(SameBoy passes)"
                print(f"  fails {note} {where[name].relative_to(SUITE)} [{kind}]")
    if args.write:
        args.write.write_text("".join(f"{r[0]} {r[1]}\n" for r in passed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
