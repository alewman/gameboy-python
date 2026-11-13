#!/usr/bin/env python3
"""SameBoy's Super Game Boy (its HLE SGB, model ``sgb-ntsc``) as a second detector for
src/gameboy_python/sgb.py: run a game and save SameBoy's 256 x 224 picture (border included)
every N frames, with SameBoy's colour correction off, so its colours are the SNES words
widened ``c << 3 | c >> 2`` like ours.

    python scripts/sgb_sameboy.py GAME.zip --boot sns_rom_sgb.zip --frames 1500 \
        --every 30 --out-dir pictures/sameboy

The library is the one scripts/sameboy_run.py builds (docs/validation.md "SameBoy built
here"). SameBoy's own SGB (Core/sgb.c, Expat) plays a boot animation for its first 200 frames
and fades borders in and out; compare settled frames only.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sameboy_run import MODELS, QUIET, RGB_CB, load_library, read_image, write_png

COLOR_CORRECTION_DISABLED = 0
BORDER_SGB = 0  # GB_BORDER_SGB: a border on SGB models


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rom", type=Path)
    parser.add_argument("--boot", type=Path, required=True, help="an SGB boot ROM (raw or .zip)")
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--every", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--png", type=Path, help="save the last frame")
    args = parser.parse_args(argv)

    lib = load_library()
    lib.GB_set_color_correction_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.GB_set_border_mode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gb = lib.GB_init(lib.GB_alloc(), MODELS["sgb-ntsc"][0])
    rgb = RGB_CB(lambda _gb, r, g, b: (r << 16) | (g << 8) | b)
    lib.GB_set_log_callback(gb, QUIET)
    lib.GB_set_rgb_encode_callback(gb, rgb)
    lib.GB_set_color_correction_mode(gb, COLOR_CORRECTION_DISABLED)
    lib.GB_set_border_mode(gb, BORDER_SGB)
    pixels = (ctypes.c_uint32 * (256 * 224))()
    lib.GB_set_pixels_output(gb, pixels)
    boot = read_image(args.boot)
    lib.GB_load_boot_rom_from_buffer(gb, boot, len(boot))
    with tempfile.TemporaryDirectory() as folder:
        rom = Path(folder) / "game.gb"
        rom.write_bytes(read_image(args.rom))
        if lib.GB_load_rom(gb, str(rom).encode()):
            raise SystemExit(f"SameBoy could not load {args.rom}")
    width, height = lib.GB_get_screen_width(gb), lib.GB_get_screen_height(gb)
    for frame in range(1, args.frames + 1):
        lib.GB_run_frame(gb)
        if args.every and frame % args.every == 0:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            write_png(args.out_dir / f"sameboy_{frame:05d}.png", width, height, pixels)
    if args.png:
        write_png(args.png, width, height, pixels)
    lib.GB_free(gb)
    lib.GB_dealloc(gb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
