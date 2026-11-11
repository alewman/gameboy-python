#!/usr/bin/env python3
"""Run Gambatte's ``_outaudio`` hardware tests that have a DMG-08 result and compare.

    python scripts/gambatte_audio.py [--skip-boot] [--write tests/gambatte_audio_pass.txt]

Each ROM (tests/test_roms/gbtr/gambatte/**) runs for 15 LCD frames after the boot ROM; its name says
whether the DMG-08 produced audio (``outaudio1``) or stayed silent (``outaudio0``). *Audio* here is
the board's ``APU.audible()``: a routed channel with an enabled DAC at a non-zero digital value, at
any point in the last frame (the tests park a channel at one duty position, so the last frame is the
state). Tests whose name marks the DMG result as unknown (``x``) are left out. The real DMG boot
ROM is the default start (these tests were captured from boot); ``--skip-boot`` is faster.
"""

from __future__ import annotations

import argparse
import re
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402

SUITE = ROOT / "tests/test_roms/gbtr/gambatte"
FRAME_T = 70224
BOOT_FRAMES = 336
PATTERNS = (r"dmg08_outaudio(\d)", r"dmg08_cgb\w*?_outaudio(\d)")


def expected(name: str) -> int | None:
    if "_x" in name:
        return None
    for pattern in PATTERNS:
        match = re.search(pattern, name)
        if match:
            return int(match.group(1))
    return None


def run(args: tuple[Path, bool]) -> tuple[str, int, int]:
    path, real = args
    boot, label = find_boot_rom("DMG") if real else (None, "")
    if real and label != "real boot ROM":
        raise SystemExit("no real DMG boot ROM; pass --skip-boot")
    gb = GameBoy(load_cartridge(path.read_bytes()), boot_rom=boot)
    start = gb.t + (BOOT_FRAMES * FRAME_T if real else 0)
    end = start + 15 * FRAME_T
    step, apu = gb.cpu.step, gb.apu
    heard = False
    while gb.t < end:
        step()
        if gb.t >= end - FRAME_T and apu.audible():
            heard = True
    return path.name, expected(path.name) or 0, int(heard)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-boot", action="store_true")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    files = [p for p in sorted(SUITE.rglob("*.gbc")) if expected(p.name) is not None]
    with Pool(args.jobs) as pool:
        results = pool.map(run, [(p, not args.skip_boot) for p in files])
    agree = [r for r in results if r[1] == r[2]]
    print(f"{len(agree)} of {len(results)} agree with the DMG-08")
    for name, want, got in results:
        if want != got:
            print(f"  disagree {name}: DMG-08 {want}, board {got}")
    if args.write:
        args.write.write_text("".join(f"{r[0]}\n" for r in agree))
    return 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
