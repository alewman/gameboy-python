# Quirks, revisions, contradictions, open items

Everything here is either undocumented by Nintendo or documented wrongly
somewhere. Each item names its source and the test that judges it.

## Quirks the board must have (DMG)

| # | Quirk | Source | Judge |
| --- | --- | --- | --- |
| 1 | OAM corruption: CPU accesses and IDU addresses in $FE00–$FEFF during mode 2 corrupt OAM rows | `pandocs/OAM_Corruption_Bug.md` | blargg `oam_bug` (8) |
| 2 | STAT write glitch: a write behaves as $FF for one M-cycle (DMG/MGB/SGB only) | `pandocs/STAT.md` "Spurious STAT interrupts" | *Road Rash*, *Xerd no Densetsu*; Gambatte `miscmstatirq` |
| 3 | STAT blocking: one IRQ line, rising edge only | `pandocs/Interrupt_Sources.md` | Mooneye `ppu/stat_irq_blocking` |
| 4 | LY=153 reads 153 only briefly, then 0; LYC=0 matches on line 153 | `pandocs/STAT.md`; Gambatte `ly0`, `lyc153int_m2irq` | Gambatte |
| 5 | Line 0 after LCD on: mode 0 then 3, no mode 2, 2 T late; first frame blank | Mooneye `ppu/lcdon_timing-GS` header; `pandocs/LCDC.md` | Mooneye |
| 6 | Timer: TIMA reload one M-cycle late, write-cancel rules, TAC-disable glitch | `pandocs/Timer_Obscure_Behaviour.md` | Mooneye `timer/*` |
| 7 | Writing DIV can clock TIMA and DIV-APU | same; `Audio_details.md` "DIV-APU" | Mooneye `tim*_div_trigger`; SameSuite `div_write_trigger` (passes on DMG-B) |
| 8 | OAM DMA: start after 1 M; $A000–$FFFF sources read the external bus; CPU bus conflicts | Mooneye `oam_dma_start.s`; `gb-ctr/.../dma.typ` | Mooneye `oam_dma*` |
| 9 | Unused I/O bits read 1; IF top bits read 1 | Mooneye `bits/unused_hwio-GS`, `if_ie_registers` | Mooneye |
| 10 | $FEA0–$FEFF: $00 when OAM free, corruption when blocked (DMG) | `pandocs/Memory_Map.md` | Gambatte `fexx_*_dumper_dmg08.bin` dumps |
| 11 | DMG wave RAM: CPU access while CH3 plays reaches the byte CH3 is reading, only in that cycle; retrigger corrupts wave RAM | blargg `dmg_sound` 09, 10, 12 | blargg (10 is not reproduced by dmg-sim either) |
| 12 | APU: power off clears registers except length counters (DMG) and wave RAM | blargg `dmg_sound` 08, 11 | blargg |
| 13 | HALT bug, EI delay, IE-push cancellation, opcode holes lock up | sm83-python `docs/start-here.md` | Mooneye `halt_*`, `ei_*`, `interrupts/ie_push`; blargg `halt_bug`; Gambatte `undef_ops` |
| 14 | Joypad: inputs settle over several reads ("the first reads are used as a short delay, allowing the inputs to stabilize"); with both rows selected the rows combine; with neither, $F | `pandocs/Joypad_Input.md` | Gambatte `jpadirq_*` (how the rows combine and how long settling takes: read dmg-schematics) |
| 15 | OAM scan picks the first 10 objects (by Y) in OAM order; on DMG the smaller X wins overlaps | `pandocs/OAM.md` "Object Priority and Conflicts" | Mooneye `manual-only/sprite_priority`, dmg-acid2 |

## Revision table (DMG family)

| Behaviour | DMG-CPU (0) | A | **B** | C | MGB | Source |
| --- | --- | --- | --- | --- | --- | --- |
| Boot ROM | DMG0 | DMG | DMG | DMG | MGB | GBCTR boot-rom table |
| `stat_irq_blocking` | fails | pass | pass | pass | pass | Mooneye header |
| `boot_*` state | own | ABC | ABC | ABC | own (A=$FF) | Mooneye `boot_regs-*` |
| Mealybug `m3_lcdc_bg_en_change`, `m3_lcdc_win_en_change_multiple_wx` | ? | ? | **B picture** | **blob picture** | ? | `expected/DMG-CPU B` vs `expected/DMG-blob` (C2) |

Unknown cells are unknown, not "same as B".

## Contradictions and doubts

**C1. The hardware-captured DMG results come from a DMG-CPU C, the die model
is a DMG-CPU B.** Gambatte's `dmg08` files, GBMicrotest ("DMG-CPU-08 I
believe") and c-sp's blargg/AGE runs ("DMG-CPU-08 (DMG-CPU C blob)") all name
the DMG-CPU-08 mainboard, which Mooneye's fleet table pairs with **DMG-CPU C
(blob)**. dmg-sim, GateBoy and dmg-schematics are DMG-CPU B. Mooneye's main
fleet includes a B. Resolution for the build: reference model B; a failure
that only Gambatte/GBMicrotest report is run on dmg-sim before the board is
changed; a B/C split, if found, becomes a `revision` field.

**C2. Mealybug's DMG pictures differ by revision.** `expected/DMG-CPU B` holds
two pictures that differ from `expected/DMG-blob`
(`m3_lcdc_bg_en_change.png`, `m3_lcdc_win_en_change_multiple_wx.png`,
`cmp` 2026-10-05). The board judged as DMG-CPU B uses the B pictures for
those two and the blob pictures for the other 22 (assuming no difference,
which is UNVERIFIED for those 22).

**C3. What "cgb04c" means.** Gambatte names its CGB results `cgb04c`. c-sp
guesses "CGB-CPU-04 (CPU CGB C)"; Mooneye's own table lists a CGB-CPU-04
mainboard carrying **CPU CGB D** and puts CPU CGB C on CGB-CPU-03. Either the
"c" is the CPU letter on a 04 board (possible: boards and SoC letters are not
one-to-one) or it is not. Until sinamas's notes are found, Gambatte's CGB
results are "CGB, revision C or D".

**C4. The SGB clock.** GBCTR (`clocks.typ`) gives the NTSC SNES clock as
"21.447 MHz"; the NTSC SNES master clock is 21.477272 MHz (6 × 3.579545).
A typo, almost certainly; it matters only to the SNES board that embeds this one.

**C5. Mealybug "photographs".** The expected images are the author's
emulator's screenshots; the photos are separate and blurry (`README.md`
"Usage"). Tier 2, not tier 1, and pixel-exact matching is against an
emulator's output that was checked by eye.

**C6. GateBoy's README vs its source on audio.** The README says the audio
cells "aren't being simulated"; `src/GateBoyLib/GateBoyCh1–4.cpp` and
`GateBoySPU.cpp` (2,639 lines) carry schematic-tagged gates (`/*#p13.COWE*/`).
The README predates the audio work, or the audio is traced but not checked.
Not used as an audio judge either way (dmg-sim is).

**C7. SameBoy's boot ROM is not a timing-faithful replacement.** With it,
Mooneye `boot_div-dmgABCmgb`, `boot_hwio-dmgABCmgb` and
`serial/boot_sclk_align-dmgABCmgb` fail on SameBoy itself; with the real DMG
boot ROM or dmg-sim's `quickboot.bin` they pass (measured 2026-10-05). Any
document that calls SameBoy's boot ROMs drop-in replacements means "for
games", not "for tests".

**C8. OAM bug determinism.** blargg `oam_bug` passes on a DMG-C (c-sp); dmg-sim
says some cases depend on signal delays and temperature and SameBoy's source
notes nondeterminism. Judge only the 8 blargg tests, and do not chase
cases outside them.

**C9. Gambatte's repository went private.** sinamas/gambatte now answers
"This project has been taken private" (its README at HEAD, 2026-10-05); the
suite is pinned through the `pokemon-speedrunning/gambatte-core` fork and the
c-sp bundle. Provenance claims ("verification on hardware") are the fork's
copy of the original README.

**C10. DMA register initial value.** Pan Docs' post-boot table gives $FF46 =
$FF (DMG); GBCTR says it "is not cleared on reset, so the initial value before
the first write is unknown". Both can hold (the boot ROM does not write it;
power-on contents are whatever they are); model it as power-on noise, and
the skip-boot path loads $FF.

## Open items

1. Which system-counter bit clocks the serial port (Mooneye says only "a big
   counter"); read dmg-schematics.
2. Where in the M-cycle each unit samples (timing.md "Where in the
   M-cycle"); settle with GBMicrotest families and dmg-sim.
3. Whether interrupts can occur during the CGB speed-switch pause (Pan Docs
   TODO).
4. The 22 Mealybug DMG-blob pictures on a B (C2).
5. The DMG analogue audio path (no capture pinned).
