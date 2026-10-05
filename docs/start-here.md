# Start here: the Game Boy as a board author needs it

The machine in one paragraph: one SoC (the "DMG-CPU" on the original Game Boy,
"CPU CGB" on the Color) holds the **SM83** CPU core, the boot ROM, the picture
processor (PPU), the sound unit (APU), the timer, the serial port, the joypad
matrix, OAM DMA, 127 bytes of HRAM and the interrupt flags. Outside it on the
board are 8 KiB of work RAM (WRAM) and 8 KiB of video RAM (VRAM), on two
separate buses, and the cartridge, which shares the **external bus** with
WRAM. The LCD, the speaker/headphone amplifier and the link port are the rest.
Bank switching, cartridge RAM and real-time clocks are all on the cartridge.

Paths: `pandocs/X.md` is `reference/src/pandocs/src/X.md` (Pan Docs,
gbdev/pandocs at `0191af06`); `gb-ctr/...` is Gekkio's *Game Boy: Complete
Technical Reference* source at `5ce83a10` (the PDF, revision 192 of
2026-08-16, is `reference/docs/gbctr.pdf`); other `src/` trees are under
`reference/src/`. Each source's tier is in [validation.md](validation.md);
timing is in [timing.md](timing.md), quirks and contradictions in
[undocumented-behavior.md](undocumented-behavior.md), cartridges in
[cartridge.md](cartridge.md).

## The machines (DMG first)

The board is built for the original Game Boy. Every other model is a row in
the same table from the start, so that adding it later is data, not a
refactor. Revision letters follow Mooneye's naming
(`mooneye-test-suite/README.markdown` "Test naming"): DMG 0/A/B/C, CGB
0/A/B/C/D/E, and the groups G = dmg+mgb, S = sgb+sgb2, C = cgb+agb+ags.

| Machine | SoC | Boot ROM (SHA-1, GBCTR table) | Clock | Phase |
| --- | --- | --- | --- | --- |
| **DMG-01 with DMG-CPU B: the reference model** | DMG-CPU B | DMG `4ed31ec6…` | 4.194304 MHz crystal | **1** |
| DMG-01, DMG-CPU A / C | DMG-CPU A, C (C is often a "blob" die under epoxy) | DMG `4ed31ec6…` | same | 1, as fields |
| DMG-01, DMG-CPU (rev 0) | DMG-CPU | DMG0 `8bd501e3…` | same | 1, as fields |
| MGB (Pocket), MGL (Light) | CPU MGB | MGB `4e68f9da…` (writes $FF to $FF50 where DMG writes $01) | same | later |
| SGB, SGB2 | SGB-CPU-01, CPU SGB2 | SGB `aa2f50a7…`, SGB2 `93407ea1…` | SGB: SNES master ÷ 5; SGB2: own 20.971520 MHz ÷ 5 | later, on a SNES board |
| CGB-001 | CPU CGB 0, A, B, C, D, **E** | CGB0 / CGB (not in GBCTR's table; Pan Docs `Power_Up_Sequence.md`) | 4.194304 MHz, CPU ×2 in double speed | **2** (rows from day one) |
| AGB/AGS in GB mode | CPU AGB … | CGB-AGB | | out of scope (a GBA board would embed this one) |

Why **DMG-CPU B**: it is the only revision with a die-level model
(`dmg-schematics`, `dmg-sim` and GateBoy are all DMG-CPU B: their READMEs'
first lines), it is in Mooneye's main test fleet (`DMG-CPU-04` mainboard,
"Hardware testing" table), and it was the volume part. The catch: several
hardware-captured suites were captured on a **DMG-CPU C (blob)** unit
(Gambatte's `dmg08` names, GBMicrotest, c-sp's blargg runs: see
[validation.md](validation.md) and [undocumented-behavior.md](undocumented-behavior.md)
C1–C3). So `revision` is a field from milestone 1, and every known B/C
difference is a row in undocumented-behavior.md.

CGB reference revision when CGB arrives: **CPU CGB E** (SameSuite's APU suite
passes in full only on E, `SameSuite/apu/README.md`; SameBoy's default; c-sp
verifies on B, C and E). Mealybug's CGB pictures are C and D, Gambatte's
are `cgb04c`, so CGB revision is also a field.

Fields the machine table needs (each with its source in a comment, as
sms-python does):

- `model` (dmg, mgb, sgb, sgb2, cgb, agb) and `revision` (0, A, B, C, … E);
- `boot_rom` (BYOR path, or a named open replacement, see "Boot ROMs" below);
- `cgb_mode` (CGB hardware running a CGB cartridge vs DMG compatibility
  mode, chosen by the boot ROM from header byte $0143 and latched in KEY0);
- `oam_bug` (DMG/MGB/SGB yes; CGB/AGB no: `pandocs/OAM_Corruption_Bug.md`);
- `tac_disable_glitch` (DMG yes, CGB no: `pandocs/Timer_Obscure_Behaviour.md`);
- `stat_write_glitch` (on monochrome models a STAT write behaves as if $FF
  were written for one M-cycle; CGB not; *Road Rash* and *Xerd no Densetsu*
  depend on it: `pandocs/STAT.md` "Spurious STAT interrupts");
- `wave_ram_while_on` (DMG: reads/writes only in the cycle the channel reads;
  CGB: any time: blargg `dmg_sound` 09/12 vs `cgb_sound`);
- `fea0_read` (what $FEA0–$FEFF return: DMG/MGB/SGB $00 when OAM is free,
  OAM corruption when blocked; CGB 0–D revision-masked RAM; CGB E the high
  nibble twice: `pandocs/Memory_Map.md` "FEA0–FEFF range");
- power-on randomness: WRAM/HRAM/VRAM/OAM fill, and whether the boot ROM ran.

## Clocks

| | DMG / MGB / CGB normal | CGB double speed | SGB (NTSC) | SGB2 |
| --- | --- | --- | --- | --- |
| System clock | 4.194304 MHz (2²² Hz) | same | 21.477272 MHz ÷ 5 = 4.295454 MHz | 20.971520 ÷ 5 = 4.194304 MHz |
| CPU M-cycle | 4 clocks (1.048576 MHz) | **2 clocks** | 4 clocks | 4 clocks |
| PPU dot | 1 clock | 1 clock | 1 clock | 1 clock |
| Dots per line, lines per frame | 456 × 154 | same | same | same |
| Clocks per frame | 70,224 | 70,224 (35,112 M-cycles ×2) | 70,224 | 70,224 |
| Frame rate | 59.7275 Hz | same | 61.17 Hz | 59.7275 Hz |

`gb-ctr/chapter/console/clocks.typ` "System clock frequency" (it prints the
NTSC SNES clock as "21.447 MHz": C4); `pandocs/Rendering.md` (456 dots, 154
lines); `pandocs/CGB_Registers.md` "KEY1". **Use one timeline in system
clocks** (T-cycles): a dot is 1, a CPU M-cycle 4 (2 in double speed). The APU,
timer, serial and DMA all derive from one 16-bit system counter whose top 8
bits are DIV ($FF04): [timing.md](timing.md) "The system counter".

## The CPU side

### Memory map

| Range | Device | Bus | Notes |
| --- | --- | --- | --- |
| $0000–$00FF | boot ROM while BANK=0 | internal | then cartridge; CGB also overlays $0200–$08FF |
| $0000–$7FFF | cartridge ROM | external (A15 low) | writes go to the MBC |
| $8000–$9FFF | VRAM | VRAM bus | locked in mode 3; CGB: 2 banks (VBK) |
| $A000–$BFFF | cartridge RAM / MBC registers | external (/CS) | |
| $C000–$DFFF | WRAM | **external** (/CS) | CGB: $D000 bank 1–7 (SVBK) |
| $E000–$FDFF | echo of $C000–$DDFF | external | the cartridge sees these accesses too |
| $FE00–$FE9F | OAM | internal | locked in modes 2 and 3; OAM DMA |
| $FEA0–$FEFF | nothing usable | internal | revision-dependent read value; OAM bug on DMG |
| $FF00–$FF7F | I/O registers | internal | open bits read 1 |
| $FF80–$FFFE | HRAM | internal | the only memory usable during OAM DMA |
| $FFFF | IE | internal | in the CPU core per GBCTR (sm83-python's contract) |

`pandocs/Memory_Map.md`; external-bus ranges from
`gb-ctr/appendix/external-bus.typ` ("a) $0000–$7FFF", "b) $A000–$FDFF";
boot-ROM accesses leave the external bus idle). WRAM on the external bus
matters twice: OAM DMA from $C000 conflicts with the CPU on that bus, and the
cartridge connector sees every WRAM access (some flash carts and the
MBC1 multicart wiring care).

### I/O registers (DMG)

| Address | Register | Unit | Address | Register | Unit |
| --- | --- | --- | --- | --- | --- |
| $FF00 | P1/JOYP | joypad | $FF40 | LCDC | PPU |
| $FF01 | SB | serial | $FF41 | STAT | PPU |
| $FF02 | SC | serial | $FF42/43 | SCY/SCX | PPU |
| $FF04 | DIV | timer | $FF44 | LY | PPU |
| $FF05 | TIMA | timer | $FF45 | LYC | PPU |
| $FF06 | TMA | timer | $FF46 | DMA | OAM DMA |
| $FF07 | TAC | timer | $FF47–49 | BGP/OBP0/OBP1 | PPU |
| $FF0F | IF | interrupts | $FF4A/4B | WY/WX | PPU |
| $FF10–$FF26 | NR10–NR52 | APU | $FF50 | BANK (boot ROM off) | boot |
| $FF30–$FF3F | wave RAM | APU | $FF80–FE | HRAM | |

Unused bits and unmapped registers read 1 (Mooneye `acceptance/bits/unused_hwio-GS`
checks every one; `pandocs/Hardware_Reg_List.md`). CGB adds KEY0 $FF4C,
KEY1 $FF4D, VBK $FF4F, HDMA1–5 $FF51–55, RP $FF56, BCPS/BCPD/OCPS/OCPD
$FF68–6B, OPRI $FF6C, SVBK $FF70, PCM12/PCM34 $FF76/77, and the undocumented
$FF72–$FF75 (`pandocs/CGB_Registers.md`).

### Interrupts

Five sources (VBlank, STAT, Timer, Serial, Joypad), bits 0–4 of IF ($FF0F) and
IE ($FFFF); IF's top three bits read 1 (Mooneye `if_ie_registers`). **IF is
the board's**: each unit raises its bit at a defined T-cycle, and the CPU
samples `IE & IF` at its fetch cycles. Dispatch, IME, HALT, the HALT bug and
the IE-push cancellation are the core's (sm83-python `docs/start-here.md`
"Interrupts"); what the board must give the core is in
[handoff-brief.md](handoff-brief.md) "What the board needs from sm83-python".

### Timer

DIV is the top byte of a 16-bit system counter that counts every T-cycle;
writing DIV clears the whole counter. TIMA increments on the **falling edge**
of (selected counter bit AND TAC enable), bit 9/3/5/7 for TAC 0/1/2/3 (4096,
262144, 65536, 16384 Hz). Overflow reloads TMA and sets IF bit 2 **one
M-cycle later**; TIMA reads $00 during that M-cycle; a write to TIMA in that
M-cycle cancels the reload, a write in the reload cycle is ignored.
`pandocs/Timer_and_Divider_Registers.md`, `pandocs/Timer_Obscure_Behaviour.md`;
Mooneye `acceptance/timer/*` (13 tests, all hardware-checked). The details
and the DMG-only TAC-disable glitch are in [timing.md](timing.md).

### Joypad and serial

P1 selects the button or direction row (bits 5/4, active low); the four
inputs read on bits 0–3, active low; any high-to-low transition on an input
line raises the Joypad interrupt (`pandocs/Joypad_Input.md`). The SGB uses P1
writes as its command channel (later). Serial: SB shifts out MSB first on SC
bit 7 with the internal clock at 8192 Hz (CGB fast mode 262144 Hz); with
nothing attached the input reads 1, so a transfer receives $FF
(`pandocs/Serial_Data_Transfer_(Link_Cable).md`). The internal serial clock
is divided from the main clock by "a big counter, so clock edges align based
on the *reset time*, not the time when SC is written" (Mooneye
`serial/boot_sclk_align-dmgABCmgb.s` l.24–26, verified pass on DMG ABC and MGB,
fail on DMG 0, SGB, CGB): serial timing after boot depends on the boot ROM.
Which counter bit it is, is not stated there; take it from the die
(dmg-schematics) before building, and record the source.

## The PPU

### Programming model

LCDC $FF40 (bit 7 LCD on, 6 window map, 5 window on, 4 BG/window tile data,
3 BG map, 2 OBJ 8×16, 1 OBJ on, 0 BG/window on: on CGB "BG priority");
STAT $FF41 (bits 6–3 interrupt sources LYC/mode 2/mode 1/mode 0, bit 2
LY=LYC, bits 1–0 mode); SCY/SCX, LY (read only), LYC, WY/WX (window at
WX−7), BGP/OBP0/OBP1 (2-bit shades). VRAM: tile data $8000–$97FF (384 tiles
of 16 bytes, 2 bits per pixel, two addressing modes), maps $9800 and $9C00
(32×32). OAM: 40 entries of Y, X, tile, attributes (Y−16, X−8).
`pandocs/LCDC.md`, `STAT.md`, `Tile_Data.md`, `Tile_Maps.md`, `OAM.md`,
`Palettes.md`, `Scrolling.md`, `Window.md`.

### The modes on one line

| Mode | What | Dots | CPU can't touch |
| --- | --- | --- | --- |
| 2 | OAM scan: pick ≤10 objects on this line, in OAM order | 80 | OAM |
| 3 | pixel transfer: fetcher + FIFOs, one pixel per dot | 172–289 | OAM, VRAM (CGB palettes) |
| 0 | HBlank | 376 − mode 3 | — |
| 1 | VBlank (lines 144–153) | 4560 | — |

`pandocs/Rendering.md`. Mode 3's length = 172 + (SCX mod 8) + 6 if the window
starts + 6–11 per object (the OBJ penalty algorithm in `Rendering.md`; an
object at X=0 always costs 11). **This board renders dot by dot with the
background and object FIFOs** (`pandocs/pixel_fifo.md`;
`mealybug-tearoom-tests/the-comprehensive-game-boy-ppu-documentation.md`),
because the hardware-tier PPU tests (Mealybug, Gambatte's hundreds of
`m3`/`scx`/`window` tests, Mooneye's `ppu/*`) change registers mid-mode-3 and
measure the result. No scanline renderer, not even as a fallback.

### Output format

A DMG frame is 160×144 **2-bit shades after the palette**, i.e. the value
the LCD driver sees (0–3); colour is the frontend's. The suites compare
pictures with shades `$FF, $AA, $55, $00` (Mealybug `README.md` "Usage",
dmg-acid2 `README.md`, c-sp blargg howto), so the test harness maps 0–3 to
those exactly. A CGB frame is 15-bit RGB per pixel; the suites convert with
`(x << 3) | (x >> 2)` (Mealybug, cgb-acid2) except Gambatte, which uses its
own colour-correction formula (`tests/test_roms/gbtr/gambatte/game-boy-test-roms-howto.md`
"Screenshot Colors"). Keep the raw 15-bit value in the frame and convert per
consumer.

When the LCD is switched on, the first frame is not shown (the LCD stays
blank: `pandocs/LCDC.md` l.46); with LCDC.7 off the DMG shows a whiter-than-
white blank screen. The frame type needs a "blank" state, not shade 0.

## The APU

Four channels: CH1 pulse with sweep (NR10–NR14), CH2 pulse (NR21–NR24), CH3
wave (NR30–NR34, 32 4-bit samples at $FF30), CH4 noise (NR41–NR44, 15/7-bit
LFSR); NR50 master volume + VIN, NR51 panning, NR52 power and channel status.
Each channel feeds a DAC (on when NRx2's top 5 bits are non-zero, NR30 bit 7
for CH3); DAC outputs are mixed per side, scaled by NR50, then high-pass
filtered (a capacitor) on the board (`pandocs/Audio.md`,
`Audio_Registers.md`, `Audio_details.md`). The **frame sequencer** ("DIV-APU")
ticks on the falling edge of DIV bit 4 (bit 5 in double speed): 512 Hz,
length at 256 Hz, sweep 128 Hz, envelope 64 Hz (`Audio_details.md` "DIV-APU").
That coupling to the timer's counter is why the APU is in this board and not
a core of its own (see [handoff-brief.md](handoff-brief.md) "Decisions").

The judges are blargg `dmg_sound` (hardware-verified on DMG), the die model
(dmg-sim: passes 11 of 12 `dmg_sound` tests, its `README.md` "Tests") and,
for CGB, blargg `cgb_sound` and SameSuite's `apu/` (sample-accurate through
the CGB-only PCM12/PCM34 registers). No hardware capture of DMG analogue
output is pinned; the analogue stage is a labelled fit.

## Boot ROMs

The boot ROMs are Nintendo's; never ship them. The board takes a path
(bring your own: the user's No-Intro `[BIOS] Nintendo Game Boy Boot ROM
(World) (Rev 1)` is SHA-1 `4ed31ec6…`, the DMG ROM in GBCTR's table) or one
of two open replacements, both pinned:

| Replacement | What it leaves | Mooneye boot tests on SameBoy (DMG-B) | Licence |
| --- | --- | --- | --- |
| SameBoy `BootROMs/dmg_boot.asm` (built with RGBDS 1.0.4) | logo + animation; registers as DMG | `boot_regs-dmgABC` passes; **`boot_div-dmgABCmgb`, `boot_hwio-dmgABCmgb`, `serial/boot_sclk_align-dmgABCmgb` fail** | MIT (SameBoy `LICENSE`) |
| dmg-sim `boot/quickboot.bin` (msinger) | the DMG A/B/C exit state incl. DIV phase, PPU phase and serial clock; VRAM zeroed (no logo) | **all four pass** | CC BY-SA 4.0 (dmg-sim `LICENSE`) |
| your DMG boot ROM | the real thing | all four pass | Nintendo's |

Measured here 2026-10-05 with `scripts/sameboy_run.py` on the Mooneye build
`mts-20260714-0944-31510e1`. So: **the acceptance harness boots with the real
ROM when given one and with `quickboot.bin` otherwise**; SameBoy's open ROM is
the default for *users* (it draws a logo) and is wrong for timing tests.
Whether that split is right is an open decision in the brief.

A "skip boot" path (load the post-boot register and I/O state directly) is
also needed, as every emulator has: Pan Docs `Power_Up_Sequence.md` tables
give the CPU registers per model and the I/O state for DMG0, DMG/MGB, SGB and
CGB, confirmed by Mooneye `boot_regs-*`/`boot_hwio-*`. The system counter's
phase at handoff is the part a table cannot hold: take it from
`boot_div-dmgABCmgb` (and quickboot's source, which reproduces it).

## A suggested module shape

The family shape (sms-python, famicom-python) adapted:

```
src/gameboy_python/
  machines.py        # the machine table above, as data
  board.py           # the bus: decodes CPU M-cycles, owns IF, advances units
  clock.py           # the system counter: DIV, timer edges, DIV-APU, serial clock
  timer.py
  ppu/               # dot-accurate: fetcher, FIFOs, OAM scan, STAT line, LCD output
  apu/               # pin-shaped boundary (registers in, DIV-APU tick in, samples out)
  dma.py             # OAM DMA (and CGB HDMA/GDMA in phase 2)
  serial.py, joypad.py
  cartridge/         # MBCs behind the connector protocol (cartridge.md)
  boot.py            # boot ROM mapping, skip-boot state
  state.py, debug.py, trace.py, frontend.py
```

`apu/` and `cartridge/` import nothing from the rest of the board; a test
enforces it ([handoff-brief.md](handoff-brief.md)).
