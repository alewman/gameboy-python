#!/usr/bin/env python3
"""Record MAME 0.285's per-instruction SM83 trace and test result for a Game Boy cartridge.

Runs the recipe in docs/mame-oracle.md in a fresh directory (default
``tests/mame_traces/<driver>-<cart stem>``, gitignored) and leaves ``error.log``
there. MAME is a detector here, never a judge (docs/validation.md).

Every Game Boy driver needs its boot ROM, which is not ours to ship
(bring your own). Pass the directory that holds ``<driver>/<file>`` with the
names MAME expects (``mame -listroms gameboy``), e.g. ``roms/gameboy/dmg_boot.bin``:

    python scripts/mame_trace.py gameboy ROM.gb --rompath ~/gb-boot --seconds 2
    python scripts/mame_trace.py gameboy ROM.gb --rompath ~/gb-boot --no-trace --seconds 60

``error.log`` then holds, in execution order:

- one line per instruction, before it executes:
  ``PC A F B C D E H L SP IE IF totalcycles beamy beamx`` (hex, then decimal).
  ``totalcycles`` counts T-cycles (4 per M-cycle), see docs/mame-oracle.md;
- ``R addr value totalcycles`` / ``W addr value totalcycles`` for every CPU
  access to $FF00-$FF7F and $FFFF, stamped with the *instruction's* start.

A frame notifier writes ``status.txt`` once per emulated second with the two
result protocols the suites use: the mooneye registers (B/C/D/E/H/L, and the
opcodes at PC) and blargg's cartridge-RAM block at $A000.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAME = "/usr/games/mame"

# MAME 0.285 nintendo/gb.cpp. The CPU is ":maincpu" (shortname lr35902), the PPU
# ":ppu", the APU ":apu". State symbols seen in the debugger: A B C D E F H L
# SP PC IE IF (checked 2026-10-05 with a Lua probe).
DRIVERS = {
    "gameboy": "DMG; boot ROM dmg_boot.bin (DMG A/B/C) or dmg_v0.rom (DMG 0)",
    "gbpocket": "MGB; mgb_boot.bin",
    "supergb": "SGB on SNES; sgb_boot.bin plus the SNES side",
    "gbcolor": "CGB; gbc_boot.1 + gbc_boot.2 (the No-Intro image split at $100/$200)",
}
CPU_TAG = ":maincpu"

# A logerror action silently drops lines past 14 values (found on the Z80
# boards); 15 here would be one too many, so A and F share a slot as AF.
TRACE_LUA = """\
local dbg = manager.machine.debugger
dbg.visible_cpu = manager.machine.devices["{cpu}"]
dbg:command('trace cpu.trace,,noloop,{{logerror "%X %02X%02X %X %X %X %X %X %X %X %X %X %d %d\\\\n",\
pc,a,f,b,c,d,e,h,l,sp,ie,if,totalcycles,beamy}}')
dbg:command('wpset ff00,80,r,1,{{logerror "R %X %X %d\\\\n",wpaddr,wpdata,totalcycles; g}}')
dbg:command('wpset ff00,80,w,1,{{logerror "W %X %X %d\\\\n",wpaddr,wpdata,totalcycles; g}}')
dbg:command('wpset ffff,1,rw,1,{{logerror "%s %X %X %d\\\\n",wpaddr,wpdata,totalcycles; g}}')
dbg:command("go")
"""

# Notifier subscriptions are unsubscribed when garbage-collected: keep them in
# globals, or the callbacks silently stop after about a second.
STATUS_LUA = """\
local cpu = manager.machine.devices["{cpu}"]
local prog = cpu.spaces["program"]
local frames = 0
local log = io.open("status.txt", "w")
status_sub = emu.add_machine_frame_notifier(function()
  frames = frames + 1
  if frames % 60 == 0 then
    local s = cpu.state
    -- When the frame ends, PC is sometimes the JR's own address and sometimes
    -- one past it (the SM83 overlaps the next opcode fetch; CURPC is no
    -- better, checked 2026-10-05), so print pc-2 .. pc+1 and let the
    -- reader look for LD B,B / JR -2 (40 18 FE) at either offset.
    local pc = s["PC"].value
    local text = {{}}
    for a = 0xA004, 0xA1FF do
      local c = prog:read_u8(a)
      if c == 0 then break end
      text[#text + 1] = string.char(c)
    end
    log:write(string.format(
      "frame %d pc %04X ops %02X %02X %02X %02X regs %02X %02X %02X %02X %02X %02X a000 %02X sig %02X %02X %02X text %s\\n",
      frames, pc, prog:read_u8(pc - 2), prog:read_u8(pc - 1), prog:read_u8(pc), prog:read_u8(pc + 1),
      s["B"].value, s["C"].value, s["D"].value, s["E"].value, s["H"].value, s["L"].value,
      prog:read_u8(0xA000), prog:read_u8(0xA001), prog:read_u8(0xA002), prog:read_u8(0xA003),
      (table.concat(text):gsub("\\n", " / "))))
    log:flush()
  end
end)
"""


def verdict(line: str) -> str:
    fields = line.split()
    ops = fields[5:9]
    regs = fields[10:16]
    if ["40", "18", "FE"] in (ops[:3], ops[1:]):
        if regs == ["03", "05", "08", "0D", "15", "22"]:
            return "pass (mooneye)"
        if regs == ["42"] * 6:
            return "fail (mooneye)"
    if fields[19:22] == ["DE", "B0", "61"] and fields[17] != "80":
        return ("pass" if fields[17] == "00" else f"fail {fields[17]}") + " (blargg $A000)"
    return "no result yet"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("driver", choices=sorted(DRIVERS))
    parser.add_argument("cart", type=Path, help=".gb / .gbc image")
    parser.add_argument("--rompath", type=Path, required=True, help="your boot ROMs (BYOR)")
    parser.add_argument("--seconds", type=int, default=2, help="emulated seconds")
    parser.add_argument("--no-trace", action="store_true", help="no debugger: status only")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--mame", default=MAME)
    args = parser.parse_args()
    cart = args.cart.resolve()
    out = (args.out or ROOT / "tests" / "mame_traces" / f"{args.driver}-{cart.stem}").resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(cart, out / cart.name)
    lua = "" if args.no_trace else TRACE_LUA.format(cpu=CPU_TAG)
    lua += STATUS_LUA.format(cpu=CPU_TAG)
    (out / "trace.lua").write_text(lua, encoding="utf-8")
    version = subprocess.run(
        [args.mame, "-version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    debug = [] if args.no_trace else ["-debug", "-debugger", "none"]
    began = time.monotonic()
    # error.log lands in the working directory, not under -homepath.
    subprocess.run(
        [args.mame, args.driver, "-cart", cart.name, "-rompath", str(args.rompath.resolve()),
         "-homepath", str(out), "-snapshot_directory", "snap",
         "-video", "none", "-sound", "none", "-nothrottle",
         "-noreadconfig", "-skip_gameinfo", *debug, "-log",
         "-seconds_to_run", str(args.seconds), "-autoboot_script", str(out / "trace.lua")],
        cwd=out, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    wall = time.monotonic() - began
    instructions = accesses = 0
    if (out / "error.log").exists():
        with (out / "error.log").open("rb") as log:
            for line in log:
                if line.startswith((b"R ", b"W ")):
                    accesses += 1
                elif line.count(b" ") == 13:
                    instructions += 1
    # Without cartridge RAM the $A004 text is open-bus $FF bytes: latin-1, not UTF-8.
    status = (out / "status.txt").read_text(encoding="latin-1").splitlines()
    print(f"MAME {version}, {args.driver}, {args.seconds} s emulated in {wall:.1f} s: {out}")
    if not args.no_trace:
        print(f"  {instructions:,} instructions, {accesses:,} I/O register accesses")
    if status:
        print(f"  {verdict(status[-1])}: {status[-1][:120]}")
    return 0 if args.no_trace or instructions else 1


if __name__ == "__main__":
    sys.exit(main())
