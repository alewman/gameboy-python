<!-- SPDX-License-Identifier: MIT -->
# Provenance

The licence findings for this repository are in [validation.md](validation.md): "Closed-box
sources removed (2026-11-24)" and the licence notes beside each source in its tables; the
family's verdict per source is emulator-lineage `docs/sources.md`. This file holds what is kept
apart from them.

## Author respect (2026-11-26)

This is respect, not law. furrtek objects to AI use of his work, and the family sets his work
and its lineage aside for that wish, whatever their licences allow (Aubrey, 2026-11-26;
emulator-lineage `docs/sources.md` at `d9b8ce2`: the "set aside (author's wishes)" verdict and
the Excluded row).

### What this repository used, when, and what replaced it

| Source | Lineage | Used here | Now |
| --- | --- | --- | --- |
| furrtek's DMG-CPU-Inside | the root | pinned until 2026-11-12, then moved to `reference/trash/`; never used in code | the leftover copy moved unopened to the backup folder |
| msinger's dmg-schematics (`28f66aed`) | "derived from the schematics in furrtek/DMG-CPU-Inside" (its README) | pinned from 2026-10-05; named as the place to settle the serial clock bit and joypad settling, which was never done | pin removed |
| msinger's gbdoc (`5ff3cb65`) | started from "Furrtek's schematics" | pinned from 2026-10-05; nothing cites it | pin removed |
| msinger's dmg-sim (`786f8c8a`) | simulates dmg-schematics | pinned and built (with Icarus Verilog from source) from 2026-10-05: the "die judge"; run on Mooneye `bits/mem_oam`; its `boot/quickboot.bin` was the second boot ROM choice in `boot.py`, `__main__.py --boot quick`, `scripts/sameboy_run.py` and the milestone 1 gate `tests/test_boot_variants.py::test_quickboot` | pins (dmg-sim and Icarus Verilog) removed; the quickboot path and its test removed; the boot order is now real ROM, then SameBoy's open ROM (labelled), else skip-boot |
| GateBoy / metroboy (`36797ad4`) | a gate-level port of furrtek's schematics | README read (clock phases, CPU "a guess", audio); source read before 2026-11-14 (C6, HYPOTHESIS); built as `reference/build-gateboy/GateBoyTests`, never driven; source unfetched since 2026-11-24 | the built binary moved to the backup folder |

The fetched trees and builds (`reference/src/dmg-sim`, `dmg-schematics`, `gbdoc`,
`reference/build-gateboy`, `reference/trash/excluded-2026-11-12/DMG-CPU-Inside`) moved
unopened to `/data/backup/gameboy-python-furrtek-lineage-2026-11-26/`. `reference/build-iverilog`
(Icarus Verilog, GPL-2.0, built only for dmg-sim) is not in the lineage and stays where it is,
unpinned. The repository's history before 2026-11-19 was reset to one commit, so earlier uses
are known from the documents only.

The earlier text "furrtek's DMG-CPU-Inside is not used" (validation.md, 2026-10-05 and
2026-11-19) was true of his repository and not of its derivatives, which were used as above.

### The facts

| # | Where | What | Set-aside source | Other evidence today | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | `board.py` `_skip_boot` (counter `$ABC8`) | the system counter's phase at the DMG boot hand-off | dmg-sim's quickboot ("what quickboot leaves") | TEST ROM: the only phase that passes Mooneye `boot_div-dmgABCmgb` (verified DMG ABC); OBSERVED 2026-11-26: this board running the real DMG boot ROM reaches `$ABC8` at `$0100` | backed |
| 2 | `board.py` `_skip_boot` (`ppu.place(153, 396, 1)`) | the PPU's line, dot and mode at the hand-off | dmg-sim's quickboot | OBSERVED 2026-11-26: the board on the real DMG boot ROM reaches line 153, the same dot, mode 1; TEST ROM: Mooneye acceptance (66) passes with the phase moved 4 dots early or 4 late and fails `ppu/stat_irq_blocking` 8 dots late (ablation). FITTED within that window | backed (bounded) |
| 3 | `serial.py` (`SERIAL_PHASE_T`) | the serial divider's phase | dmg-schematics named as unread ("UNVERIFIED there") | TEST ROM, FITTED: Mooneye `serial/boot_sclk_align` with `boot_div` | backed (the lineage was only named) |
| 4 | start-here.md "Joypad and serial"; undocumented-behavior.md open item 1 | which counter bit clocks the serial port | "take it from the die (dmg-schematics)", never done | the board's bit 7 is SameBoy's reading (`GB_serial_master_edge`), FITTED to Mooneye `boot_sclk_align` | backed as FITTED; a console probe timing SB shifts against DIV would make it MEASURED |
| 5 | undocumented-behavior.md table row 14 | how joypad rows combine and how long inputs take to settle | "read dmg-schematics", never done | DOC: Pan Docs `Joypad_Input.md`; TEST ROM: Gambatte `jpadirq_*` (dmg08) | **needs new evidence** for the settling time: a console probe reading P1 on successive cycles after a select write |
| 6 | timing.md "Where in the M-cycle" | a read is sampled late in the M-cycle, a write driven in its second half | GateBoy's README (phases A-H) | DOC: GBCTR `appendix/external-bus.typ`; TEST ROM: Mooneye `*_timing`, blargg `mem_timing`, GBMicrotest families | backed |
| 7 | timing.md "OAM corruption"; undocumented-behavior.md C8; validation.md | some OAM-bug cases are not deterministic on real hardware | dmg-sim's README | OBSERVED by SameBoy's author on his DMG (`Core/memory.c` line 70) | backed |
| 8 | start-here.md, `machines.py` | DMG-CPU B is the reference revision | "the only revision with a die-level model" (dmg-sim, GateBoy, dmg-schematics) | Mooneye's fleet includes a DMG-CPU B; Mealybug has `expected/DMG-CPU B` pictures | backed (the decision stands; one of its reasons is gone) |
| 9 | undocumented-behavior.md C1; validation.md "not available"; handoff-brief milestones 2 and 6 | a DMG-CPU B vs C (blob) difference is decided on dmg-sim | dmg-sim | none | **needs new evidence**: any suspected B/C split is an open item until a DMG-CPU B console runs the ROM |
| 10 | start-here.md "The APU"; undocumented-behavior.md row 11, C6 | dmg-sim named as an APU judge ("11 of 12 `dmg_sound`"; "dmg-sim is") | dmg-sim | TEST ROM: blargg `dmg_sound` 12/12; SameBoy as detector. No APU constant was decided by dmg-sim (validation.md milestone 4: the wave constants were fitted to blargg) | backed (the naming was wrong) |
| 11 | sm83-python, inherited through the pinned core | the halted bus and the HALT wake | dmg-sim | see sm83-python `docs/provenance.md` "Author respect": DIE (Gekkio's VHDL) and TEST ROM (Mooneye `halt_ime1_timing2-GS`, `di_timing-GS` fail with one extra wake cycle, ablation on this board 2026-11-26) | backed |

Counts: 11 facts; 9 backed by other evidence (1-4, 6-8, 10, 11), 2 needing new evidence (5, 9).
No behaviour changed: the quickboot boot ROM was a choice of program, not of hardware
behaviour, and the skip-boot state it had stood for is the real boot ROM's on this board.

Statements about the set-aside sources themselves (C6's GateBoy audio, C7's quickboot result,
dmg-sim's speed and fitted delays, "every miss run on dmg-sim") are kept, dated, as history.

**Gates.** No rung was the die rung here: dmg-sim was a judge to consult, never a gate. The
one gate that used the lineage, milestone 1's `test_quickboot` (the 66 Mooneye ROMs booted from
quickboot), is removed; `test_real_boot_rom` (the same ROMs from Nintendo's ROM, read in place)
and the skip-boot suites carry the claim. The Rust tiers' rung 4 still lists
`mooneye-dmg-quick/*` jobs (they read quickboot through this repository's `reference/`): a
carry-down for gameboy-rust and gameboy-rust-fast, in their own gated session.

### Lineage notes on the judges that remain

- **GBMicrotest** (aappleby, MIT): "All tests in this repo have been checked on real hardware
  (version DMG-CPU-08 I believe)" (its README), so its verdicts are hardware results. It was
  written "to debug GateBoy", by GateBoy's author. Kept as a gate (481 passes) for now; whether
  a hardware-checked test written alongside a port of furrtek's schematics is in the lineage is
  Aubrey's call.
- **Pan Docs** (CC0): lists Furrtek among its authors and links his schematics and his Game Boy
  Printer page in its references. Facts cited here from Pan Docs should be checked page by page
  for ones that rest on him (the Game Boy Printer page links his write-up; nothing here uses the
  printer).
- **SameBoy** (Expat), **Mooneye** (MIT), **GBCTR** and **gb-research** (Gekkio, own decap of
  an SGB-CPU 01), **Mealybug Tearoom**, **SameSuite**, **AGE**, **blargg**, **Gambatte's
  suite**, **docboy**, **dmg/cgb-acid2**: their fetched trees name none of furrtek, his
  schematics, msinger's works or GateBoy (searched 2026-11-26).
- **Not candidates**: emu-russia/dmgcpu (CC0) builds on msinger's dmg-schematics ("the main
  source of both correct schematics and signal names", its README), and msinger's visual-sm83
  is his own schematics' model: both in the lineage.

### Replacing a die-level answer

No respect-clean model of the DMG SoC is known. What could answer the questions dmg-sim
answered: a DMG-CPU B console with a flash cartridge running the probe ROMs (rows 5 and 9, and
sm83-python's 24 HALT cases); or a Super Game Boy (SGB-CPU 01, the die Gekkio traced) with a
Game Boy flash cartridge in Aubrey's Super Famicom (the Super Game Boy and the cartridge would
be new hardware; the family's rule today is emulation only). Either is a decision for Aubrey, and any
behaviour change that came of it would be a separate one.
