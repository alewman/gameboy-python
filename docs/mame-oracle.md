# MAME 0.285 as a trace oracle for the Game Boy

MAME is a **detector** here ([validation.md](validation.md)): it fails 8 of
the 66 Mooneye acceptance tests that apply to DMG-CPU B and has no OAM bug.
Its use is the SM83 trace: per-instruction registers and cycle counts on real
cartridges, for the board's CPU-side milestone and for finding where the
board's CPU and I/O diverge first.

Everything here was run on 2026-10-05 with `/usr/games/mame` 0.285 and
`scripts/mame_trace.py`.

## Drivers and boot ROMs

| Driver | Machine | ROMs MAME requires (`mame -listroms`) |
| --- | --- | --- |
| `gameboy` | DMG | `dmg_boot.bin` (SHA-1 `4ed31ec6…`, DMG A/B/C), `dmg_v0.rom` (`8bd501e3…`, DMG0) |
| `gbpocket` | MGB | `mgb_boot.bin` (`4e68f9da…`) |
| `gbcolor` | CGB | `gbc_boot.1` (256 B, `e4b40c9f…`) + `gbc_boot.2` (1,792 B, `f943b1e0…`) |
| `supergb` | SGB on SNES | `sgb_boot.bin` (`aa2f50a7…`) plus the SNES side |

**Every driver needs its boot ROM; none is shipped.** `--rompath` points at a
directory you make from boot ROMs you own, with MAME's file names
(`<rompath>/gameboy/dmg_boot.bin`). The No-Intro `[BIOS] Nintendo Game Boy
Boot ROM (World) (Rev 1)` is byte-identical to `dmg_boot.bin`; the CGB image
(2,304 bytes) is MAME's two files with the $100–$1FF gap removed (not tried
here: check the SHA-1s after splitting).

## The recipe

```
mame gameboy -cart ROM.gb -rompath <yours> -homepath <out> \
     -video none -sound none -nothrottle -noreadconfig -skip_gameinfo \
     -debug -debugger none -log -seconds_to_run N -autoboot_script trace.lua
```

with, in `trace.lua` (the family recipe from the arcade groundwork, verified
again here):

```lua
local dbg = manager.machine.debugger
dbg.visible_cpu = manager.machine.devices[":maincpu"]
dbg:command('trace cpu.trace,,noloop,{logerror "%X %02X%02X %X %X %X %X %X %X %X %X %X %d %d\\n",pc,a,f,b,c,d,e,h,l,sp,ie,if,totalcycles,beamy}')
dbg:command('wpset ff00,80,r,1,{logerror "R %X %X %d\\n",wpaddr,wpdata,totalcycles; g}')
dbg:command('wpset ff00,80,w,1,{logerror "W %X %X %d\\n",wpaddr,wpdata,totalcycles; g}')
dbg:command("go")
```

`error.log` lands in the **working directory**, not under `-homepath`
(the script runs MAME with `cwd` set to the output directory). Measured:
`ei_sequence.gb`, 2 s emulated: 1,221,258 log lines.

## What the output means

- Device tags: CPU `:maincpu` (shortname `lr35902`), PPU `:ppu` (`dmg_ppu`),
  APU `:apu` (`dmg_apu`), cartridge `:cartslot`. CPU state symbols: `A B C D E
  F H L SP PC IE IF IRQ CURPC GENPC CURFLAGS` (Lua probe of `cpu.state`).
- **`totalcycles` counts T-cycles**: `LD SP,$FFFE` (3 M) advances it by 12,
  `NOP` by 4. sm83-python and GBCTR count M: divide by 4.
- The first instruction of the boot ROM is at totalcycles 0, beamy 144. With
  the DMG boot ROM the cartridge entry ($0100) is reached at **totalcycles
  5,881,108 (≈1.402 s)**, registers AF=$01B0 BC=$0013 DE=$00D8 HL=$014D
  SP=$FFFE, which match Pan Docs `Power_Up_Sequence.md` for DMG.
- `beamy` is MAME's *screen* raster line, not LY.
- The watchpoint lines are stamped with the **instruction's start** cycle,
  not the M-cycle of the access (the same trap as on the NES and Z80 boards).

## Traps found

1. **PC in a frame callback is not the instruction's address.** At the end of
   a frame, `cpu.state["PC"]` and `cpu.state["CURPC"]` were sometimes the
   address of the `JR -2` the test is parked on and sometimes one past it
   (the SM83 overlaps the next opcode fetch). `mame_trace.py` therefore reads
   `pc-2 … pc+1` and looks for `40 18 FE` (LD B,B; JR -2) at either offset.
   The trace line's `pc` *is* the instruction address (the `$0100`, `$0101`,
   `$0150` sequence at cartridge entry).
2. **Without cartridge RAM, $A000 reads open bus $FF**, so the blargg text
   field is 400 × $FF: read `status.txt` as Latin-1.
3. **blargg's serial-only ROMs** (`cpu_instrs`, `instr_timing`, `mem_timing`)
   report nothing through `$A000`; MAME's result for them is on screen only
   (`snap/`), so `mame_trace.py` says "no result yet" for them.
4. `-video none` without `-seconds_to_run` warns; always pass a duration.
5. A logerror action silently drops values past 14 (found on the Z80
   boards); the trace line packs A and F into one `%02X%02X` to stay at 14.
6. Notifier subscriptions must be held in globals or they stop after about a
   second (family trap; the script does).

## Measured detector quality (DMG, `gameboy`, real boot ROM)

Mooneye acceptance (`mts-20260714-0944-31510e1`), 3 s each, `--no-trace`:
55 pass, 18 fail, 2 no result over all 75; over the 66 that apply to DMG
A/B/C: **58 pass**. Failing: `ei_sequence`, `interrupts/ie_push`,
`oam_dma/reg_read`, `ppu/lcdon_timing-GS`, `ppu/lcdon_write_timing-GS`,
`ppu/stat_lyc_onoff`; no result: `oam_dma/sources-GS`,
`ppu/intr_2_mode0_timing_sprites`. blargg (60 s): `mem_timing-2` pass,
`dmg_sound` fail $0A, `oam_bug` fail $02.

So: trust MAME's CPU instruction stream and register values (its exit
snapshot after 60 s of `cpu_instrs` reads "Passed all tests", 11/11, checked
2026-10-05; `mem_timing-2` passes through $A000) and distrust its
interrupt-dispatch corner cases, LCD-enable timing and OAM DMA source
decoding.
