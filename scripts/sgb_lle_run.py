#!/usr/bin/env python3
"""The low-level Super Game Boy on snes-python (the real SGB BIOS on its SNES, gameboy-python as
the Game Boy): save its 256 x 224 picture every N SNES frames, with the Game Boy's frame count
at each, and every command packet the Game Boy sends. The judge for src/gameboy_python/sgb.py
(scripts/sgb_compare.py reads what this writes).

Run it with snes-python's interpreter (it imports snes_python; snes-python's venv has
gameboy-python installed editable):

    nice env PYPY_GC_NURSERY=1M ../snes-python/.venv-pypy/bin/python scripts/sgb_lle_run.py \
        "SGB.zip" GAME.zip OUT_DIR --frames 1800 --start 600 --every 30 --ipl snes.zip

``SGB.zip`` is the SNES cartridge (No-Intro "Super Game Boy (World) (Rev 2)"); the SGB boot ROM
comes from MAME's device set as snes-python finds it (``SNES_DSP_ROMS``); ``--ipl`` is MAME's
``snes.zip`` (the S-SMP's 64-byte IPL, which the BIOS's sound upload waits on). The BIOS
restarts the Game Boy once, around SNES frame 430; Game Boy frame counts are from that start.

Writes ``OUT_DIR/snes_FFFFF.png``, ``OUT_DIR/index.json`` (SNES frame -> Game Boy frames
completed) and ``OUT_DIR/packets.json``. ``--log`` also writes ``OUT_DIR/frames.jsonl``, one
line per SNES frame from the start: the frame, the Game Boy's frame count, the INIDISP ($2100)
values written in it, the number of CGRAM data ($2122) writes, and all 256 CGRAM words (hex)
when they changed since the last line: how the border fade was measured (docs/sgb.md). A
picture saved at frame f shows CGRAM as logged at frame f - 1.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from snes_python.board import SNES
from snes_python.cartridge import load_image
from snes_python.machines import NTSC
from snes_python.slot import gb_image, open_cartridge
from snes_python.video import picture, write_png


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sgb", type=Path, help="the Super Game Boy SNES cartridge")
    parser.add_argument("game", type=Path, help="the Game Boy cartridge")
    parser.add_argument("out", type=Path)
    parser.add_argument("--frames", type=int, default=1800, help="SNES frames to run")
    parser.add_argument("--start", type=int, default=600)
    parser.add_argument("--every", type=int, default=30)
    parser.add_argument("--ipl", type=Path, help="MAME's snes.zip (or the raw 64-byte IPL)")
    parser.add_argument("--log", action="store_true", help="also write frames.jsonl")
    args = parser.parse_args(argv)

    ipl = None
    if args.ipl is not None:
        if args.ipl.suffix.lower() == ".zip":
            with zipfile.ZipFile(args.ipl) as archive:
                ipl = next(archive.read(i) for i in archive.infolist() if i.file_size == 64)
        else:
            ipl = args.ipl.read_bytes()
    args.out.mkdir(parents=True, exist_ok=True)
    cart = open_cartridge(load_image(args.sgb), None, gb_rom=gb_image(args.game))
    snes = SNES(cart, NTSC, ipl=ipl)
    packets: list[dict] = []
    index: dict[int, int] = {}
    restart = cart._restart
    inidisp: list[int] = []
    cgram_writes = 0
    last_cgram = b""
    log = (args.out / "frames.jsonl").open("w") if args.log else None
    if log is not None:
        ppu_write = snes.ppu.write

        def logged_write(port: int, value: int) -> None:
            nonlocal cgram_writes
            if port == 0x00:
                inidisp.append(value)
            elif port == 0x22:
                cgram_writes += 1
            ppu_write(port, value)

        snes.ppu.write = logged_write

    def restarted() -> None:  # wrap the new Game Boy's P1 hook to log packets
        restart()
        gb = cart.gb
        hook = gb.joypad.on_write

        def logged(select: int) -> None:
            before = cart.packet_ready
            hook(select)
            if cart.packet_ready and not before:
                packets.append(
                    {
                        "snes_frame": snes.frames,
                        "gb_frame": gb.ppu.frames,
                        "packet": cart.packet.hex(),
                    }
                )

        gb.joypad.on_write = logged

    cart._restart = restarted
    while snes.frames < args.frames:
        snes.run_frames(1)
        frame = snes.frames
        if log is not None:
            cgram = bytes(snes.ppu.cgram)
            line = {
                "frame": frame,
                "gb_frame": cart.gb.ppu.frames if cart.gb is not None else None,
                "inidisp": inidisp,
                "cgram_writes": cgram_writes,
            }
            if cgram != last_cgram:
                line["cgram"] = cgram.hex()
                last_cgram = cgram
            log.write(json.dumps(line) + "\n")
            inidisp = []
            cgram_writes = 0
        if frame >= args.start and (frame - args.start) % args.every == 0 and cart.gb is not None:
            write_png(args.out / f"snes_{frame:05d}.png", picture(snes.ppu))
            index[frame] = cart.gb.ppu.frames
            (args.out / "index.json").write_text(json.dumps(index, indent=0))
            (args.out / "packets.json").write_text(json.dumps(packets, indent=0))
            print(frame, cart.gb.ppu.frames, flush=True)
    if log is not None:
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
