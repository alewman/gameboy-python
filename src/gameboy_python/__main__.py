"""Run a Game Boy ROM: ``python -m gameboy_python ROM.gb``.

    python -m gameboy_python rom.gb --frames 60                  # run, print the serial text
    python -m gameboy_python rom.gb --boot real --frames 400     # boot from the real boot ROM
    python -m gameboy_python rom.gb --protocol mooneye           # run to LD B,B, report pass/fail
    python -m gameboy_python rom.gb --trace out.jsonl --steps 100000

``--boot`` is ``skip`` (the default), ``real`` (your No-Intro boot ROM, read in place),
``quick`` (dmg-sim's quickboot), or a path to a raw or zipped image. Pictures and sound arrive with
the PPU (milestone 2) and the APU (milestone 4); ``--png`` and ``--wav`` say so for now.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gameboy_python import GameBoy, load_cartridge
from gameboy_python.boot import QUICKBOOT, find_boot_rom, read_image
from gameboy_python.testrom import run_blargg_ram, run_blargg_serial, run_mooneye
from gameboy_python.trace import write_trace

PROTOCOLS = {
    "mooneye": run_mooneye,
    "blargg-serial": run_blargg_serial,
    "blargg-ram": run_blargg_ram,
}


def boot_image(choice: str) -> tuple[bytes | None, str]:
    if choice == "skip":
        return None, "skip-boot state"
    if choice == "real":
        return find_boot_rom("DMG")
    if choice == "quick":
        return QUICKBOOT.read_bytes(), "quickboot (dmg-sim)"
    return read_image(Path(choice)), f"boot ROM {choice}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gameboy_python", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("rom", type=Path)
    parser.add_argument("--boot", default="skip", help="skip, real, quick, or a path")
    parser.add_argument("--frames", type=int, default=60, help="frames to run (default 60)")
    parser.add_argument(
        "--protocol", choices=sorted(PROTOCOLS), help="run until a test ROM's result"
    )
    parser.add_argument("--trace", type=Path, metavar="FILE", help="write a JSONL trace")
    parser.add_argument("--steps", type=int, default=100_000, help="boundaries to trace")
    parser.add_argument("--png", type=Path, help="(milestone 2: the PPU draws no pixels yet)")
    parser.add_argument("--wav", type=Path, help="(milestone 4: no audio yet)")
    args = parser.parse_args(argv)
    if args.png or args.wav:
        parser.error("pictures need the PPU (milestone 2) and sound the APU (milestone 4)")
    image, label = boot_image(args.boot)
    if image is None and args.boot not in ("skip", "real"):
        parser.error(f"no boot image for {args.boot!r}")
    gb = GameBoy(load_cartridge(args.rom.read_bytes()), boot_rom=image)
    print(f"[{gb.cartridge.header.title!r}, {gb.cartridge.header.board}; {label}]", file=sys.stderr)
    if args.trace:
        with args.trace.open("w") as stream:
            write_trace(gb, args.steps, stream)
        print(f"[{args.steps} boundaries traced to {args.trace}]", file=sys.stderr)
        return 0
    if args.protocol:
        result = PROTOCOLS[args.protocol](gb)
        sys.stdout.write(
            result.text if result.text.endswith("\n") or not result.text else result.text + "\n"
        )
        print(
            f"[{result.protocol}: {'PASS' if result.passed else 'FAIL'}; regs {result.registers}; "
            f"{result.frames} frames, {result.t_cycles} T]",
            file=sys.stderr,
        )
        return 0 if result.passed else 1
    gb.run_frames(args.frames)
    text = gb.serial.output.decode("ascii", "replace")
    sys.stdout.write(text if text.endswith("\n") or not text else text + "\n")
    print(f"[{gb.ppu.frames} frames, {gb.t} T]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
