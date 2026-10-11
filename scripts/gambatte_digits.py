#!/usr/bin/env python3
"""Print the digits a Gambatte test ROM shows on the board (to compare with its name's ``out``).

    python scripts/gambatte_digits.py [--cgb] [--boot real|skip] ROM [ROM ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import gambatte_dmg08 as g  # noqa: E402
from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.machines import DMG_B  # noqa: E402


def digits(frame: bytes, count: int = 8) -> str:
    out = ""
    for i in range(count):
        for ch, tile in g.TILES.items():
            if all(frame[y * 160 + i * 8 : y * 160 + i * 8 + 8] == tile[y * 8 : y * 8 + 8] for y in range(8)):
                out += ch.upper()
                break
        else:
            out += "?"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("roms", nargs="+", type=Path)
    parser.add_argument("--cgb", action="store_true")
    parser.add_argument("--boot", choices=("real", "skip"), default="skip")
    args = parser.parse_args()
    for rom in args.roms:
        boot = find_boot_rom("CGB" if args.cgb else "DMG")[0] if args.boot == "real" else None
        gb = GameBoy(load_cartridge(rom.read_bytes()), MACHINES["cgb"] if args.cgb else DMG_B, boot_rom=boot)
        frames = 15 if args.boot == "skip" else (g.CGB_FRAMES if args.cgb else g.FRAMES)
        while gb.t < frames * g.FRAME_T:
            gb.cpu.step()
        frame = bytes(gb.ppu.frame)
        shades = g.cgb_shades(frame) if args.cgb else frame
        print(f"{rom.name}: {digits(shades)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
