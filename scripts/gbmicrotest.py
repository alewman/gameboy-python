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
from gameboy_python.testrom import VRAM_FLAG_ROMS, run_microtest  # noqa: E402

ROMS = ROOT / "tests/test_roms/gbtr/gbmicrotest"
BOOT_FRAMES = 352
FRAMES = 30  # is_if_set_during_ime0 takes ~380 ms; the rest stop in a loop


def run(path: Path) -> tuple[str, int, int, int]:
    real = path.name.startswith("poweron_")
    boot, label = find_boot_rom("DMG") if real else (None, "")
    if real and label != "real boot ROM":
        return path.name, -1, 0, 0
    gb = GameBoy(load_cartridge(path.read_bytes()), boot_rom=boot)
    flagged = path.name in VRAM_FLAG_ROMS
    result = run_microtest(gb, FRAMES + (BOOT_FRAMES if real else 0), flagged)
    if flagged:
        return path.name, 1 if result.passed else 255, gb.peek(0x8000), 0x55
    return path.name, gb.hram[2], gb.hram[0], gb.hram[1]


def sameboy(path: Path) -> int:
    """SameBoy DMG-B's $FF82 for the ROM, from the real boot ROM (it has no skip-boot state)."""
    import ctypes

    sys.path.insert(0, str(ROOT / "scripts"))
    import sameboy_run as sb

    boot = find_boot_rom("DMG")[0]
    lib = sb.load_library()
    gb = lib.GB_init(lib.GB_alloc(), sb.MODELS["dmg-b"][0])
    lib.GB_set_log_callback(gb, sb.QUIET)
    cb = sb.RGB_CB(lambda _g, r, g, b: (r << 16) | (g << 8) | b)
    lib.GB_set_rgb_encode_callback(gb, cb)
    pixels = (ctypes.c_uint32 * (256 * 224))()
    lib.GB_set_pixels_output(gb, pixels)
    lib.GB_load_boot_rom_from_buffer(gb, boot, len(boot))
    tmp = ROOT / "reference" / "build" / "microtest_rom.tmp"
    tmp.write_bytes(path.read_bytes())
    lib.GB_load_rom(gb, str(tmp).encode())
    for _ in range(FRAMES + BOOT_FRAMES):
        lib.GB_run_frame(gb)
    value = lib.GB_safe_read_memory(gb, 0x8000 if path.name in VRAM_FLAG_ROMS else 0xFF82)
    if path.name in VRAM_FLAG_ROMS:
        value = 1 if value == 0x55 else 255
    lib.GB_free(gb)
    lib.GB_dealloc(gb)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", type=Path)
    parser.add_argument("--sameboy", action="store_true", help="tabulate SameBoy's verdicts too")
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
    if args.sameboy:
        theirs = {path.name: sameboy(path) for path in roms}
        mine = {r[0]: r[1] for r in results}
        table: dict[str, list[str]] = {
            "both": [],
            "board only": [],
            "SameBoy only": [],
            "neither": [],
        }
        for name, got in mine.items():
            a, b = got == 1, theirs[name] == 1
            table[
                "both" if a and b else "board only" if a else "SameBoy only" if b else "neither"
            ].append(name)
        for key, names in table.items():
            print(f"{key} pass: {len(names)}")
            if key != "both":
                for name in names:
                    print(f"  {name} (board $FF82 {mine[name]:#04x}, SameBoy {theirs[name]:#04x})")
    if args.write:
        args.write.write_text("".join(f"{n}\n" for n in passed))
        print(f"wrote {len(passed)} names to {args.write}")
    return 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
