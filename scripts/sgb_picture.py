#!/usr/bin/env python3
"""Run a game on the Super Game Boy row with the HLE SGB (src/gameboy_python/sgb.py) and save
the 256 x 224 SNES picture (border + colourised Game Boy picture) as PNG.

    python scripts/sgb_picture.py GAME.zip --frames 900 --png out.png
    python scripts/sgb_picture.py GAME.gb --boot sgb_boot.bin --frames 1500 \
        --every 60 --out-dir pictures/ --packets

``--boot`` is ``skip`` (the default: the skip-boot state), or a raw or zipped SGB boot ROM
(MAME's ``sns_rom_sgb.zip`` / ``sns_rom_sgb2.zip`` device sets hold them); ``mame`` looks for
those zips in each directory of ``$MAME_ROMPATH`` (``;``-separated). Nothing is copied.
``--packets`` prints each command packet with the Game Boy frame it arrived in.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from gameboy_python import MACHINES, GameBoy, load_cartridge
from gameboy_python.boot import read_image
from gameboy_python.frontend import read_rom
from gameboy_python.image import rgb24_png_bytes
from gameboy_python.sgb import SNES_H, SNES_W, SuperGameBoy, rgb_bytes

MAME_SETS = {"sgb": "sns_rom_sgb.zip", "sgb2": "sns_rom_sgb2.zip"}


def find_boot(choice: str, machine: str) -> bytes | None:
    if choice == "skip":
        return None
    if choice == "mame":
        for folder in os.environ.get("MAME_ROMPATH", "").split(";"):
            path = Path(folder) / MAME_SETS[machine]
            if folder and path.exists():
                return read_image(path)
        raise SystemExit(f"no {MAME_SETS[machine]} in $MAME_ROMPATH")
    return read_image(Path(choice))


def save(sgb: SuperGameBoy, path: Path) -> None:
    path.write_bytes(rgb24_png_bytes(rgb_bytes(sgb.render()), SNES_W, SNES_H))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rom", type=Path)
    parser.add_argument("--machine", choices=("sgb", "sgb2"), default="sgb")
    parser.add_argument("--boot", default="skip", help="skip, mame, or a path")
    parser.add_argument("--frames", type=int, default=900, help="Game Boy frames to run")
    parser.add_argument("--png", type=Path, help="save the picture after the last frame")
    parser.add_argument("--every", type=int, help="also save every N frames into --out-dir")
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--packets", action="store_true", help="print each packet")
    args = parser.parse_args(argv)

    gb = GameBoy(
        load_cartridge(read_rom(args.rom)),
        MACHINES[args.machine],
        boot_rom=find_boot(args.boot, args.machine),
    )
    sgb = SuperGameBoy(gb)
    if args.packets:
        receive = sgb.receive_packet

        def logged(packet: bytes) -> None:
            print(f"frame {gb.ppu.frames:5d}: {bytes(packet).hex()}")
            receive(packet)

        sgb.receive_packet = logged  # type: ignore[method-assign]
    for frame in range(1, args.frames + 1):
        gb.run_frames(1)
        if args.every and frame % args.every == 0:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            save(sgb, args.out_dir / f"sgb_{frame:05d}.png")
    if args.png:
        save(sgb, args.png)
    print(f"{args.frames} frames; SGB commands {'on' if sgb.enabled else 'off'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
