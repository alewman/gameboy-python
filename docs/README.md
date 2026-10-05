# Documents

Read in this order.

| Document | What it holds |
| --- | --- |
| [start-here.md](start-here.md) | The models as data and why DMG-CPU B; clocks; the memory map and which bus each range is on; I/O registers; interrupts, timer, joypad, serial; the PPU programming model, modes and output format; the APU; boot ROMs and the measured open replacements; a suggested module shape |
| [timing.md](timing.md) | The M-cycle callback design and where in the M-cycle things land; the system counter and every timer quirk; when each IF bit rises; the PPU dot schedule and Mooneye's measured consequences; OAM DMA; the OAM corruption bug; the APU on the clock; CGB double speed |
| [cartridge.md](cartridge.md) | Why MBCs live here; the connector and the proposed protocol; the header; MBC coverage measured over the local No-Intro sets; per-MBC registers and judges; save data |
| [undocumented-behavior.md](undocumented-behavior.md) | Fifteen DMG quirks with their judges, the DMG revision table, contradictions C1–C10, open items |
| [validation.md](validation.md) | Every oracle by tier with pins and provenance quotes; the result protocols; the die-level models and how to run dmg-sim and build GateBoy; SameBoy and MAME measured as detectors; what is not available; local romsets |
| [mame-oracle.md](mame-oracle.md) | The verified MAME 0.285 recipe for `gameboy`, its output, six traps, and its measured score |
| [handoff-brief.md](handoff-brief.md) | The task for the session that builds the board: decisions, what the board needs from sm83-python, seven milestones with acceptance tests, constraints, Aubrey's decisions and the one still open |

## Findings made while gathering (2026-10-05)

These came out of running the tools and checking the sources against each
other, not out of any single document:

1. **A complete DMG-CPU B including the SM83 runs here from the die.**
   msinger's dmg-sim (SystemVerilog generated from the corrected schematics,
   with transistor-derived delays fitted to measurements on a real DMG-CPU B)
   compiles with Icarus Verilog built from source in under a minute and ran
   Mooneye `bits/mem_oam` (0.4 emulated seconds) in 29 minutes, matching its
   expected picture byte for byte. It is the die-level
   judge for anything a short test ROM can show, CPU included, which GateBoy
   (CPU guessed) cannot be.
2. **The hardware-captured DMG suites were captured on a DMG-CPU C (blob),**
   not on the B that every die model describes: Gambatte (`dmg08`),
   GBMicrotest and c-sp's blargg/AGE runs all name the DMG-CPU-08 board.
   Mealybug already shows two B/blob picture differences.
3. **SameBoy's open DMG boot ROM fails three Mooneye boot-state tests**
   (`boot_div`, `boot_hwio`, `boot_sclk_align`) on SameBoy itself; the real
   boot ROM and dmg-sim's `quickboot.bin` pass all four. The test harness must
   not boot with SameBoy's ROM.
4. **SameBoy passes all 66 Mooneye acceptance tests that apply to DMG-B,
   all blargg DMG suites, and 476 of 513 GBMicrotest ROMs** through a 230-line
   ctypes driver; **MAME 0.285 passes 58 of the 66**, fails `dmg_sound` and has
   no OAM bug, but its CPU trace is sound (`cpu_instrs` passes).
5. **Gambatte's results are in its file names** (`_dmg08_out3`,
   `_cgb04c_outFF`, `_outaudio1`), 1,747 for DMG and 3,154 for CGB, and its
   `hwtests/` hold hardware memory dumps; its upstream repository has gone
   private, so it is pinned through the `gambatte-core` fork.
6. **Mealybug's expected pictures are emulator screenshots checked against
   blurry photos**, not photographs: tier 2.
7. **Five MBC families run 98.9 % of licensed cartridges** (MBC1 45.8 %, MBC5
   45.2 %, ROM-only 3.0 %, MBC2 3.0 %, MBC3 1.9 %); 8 MBC1 multicarts and 2
   MMM01 carts lie in their headers and are found by GBCTR's and Pan Docs'
   heuristics, which agree with MAME's software list.
8. **SameSuite's APU tests are CGB tests**: only two pass on a DMG; the DMG
   APU's judges are blargg `dmg_sound` and the die model.
9. **MAME's `PC` at a frame boundary is sometimes one past the instruction**
   (the SM83's fetch overlap), so test-result detection must look on both
   sides.
