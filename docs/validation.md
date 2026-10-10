# Validation: every oracle, its tier, its pin, how to read its answer

The family's tier rule: **hardware-captured** (a real unit produced the
expected result) > **hardware-corrected** (expected results come from a model,
checked against real units) > **emulator-derived**. A low-tier source is a
*detector*: it can point at a suspect, never decide. Every claim below about
a suite's provenance quotes where it is stated; where nothing states it, it
says UNVERIFIED.

All test ROMs come from two pinned archives in `tests/test_roms/` (fetched,
never committed): c-sp's **game-boy-test-roms v7.0** bundle (2024-02-25,
4,510 ROMs from 19 suites, with c-sp's per-suite `game-boy-test-roms-howto.md`
on devices, exit conditions and pass criteria) and Gekkio's prebuilt
**Mooneye Test Suite `mts-20260714-0944-31510e1`** (the build of the pinned
source commit `31510e12`; the bundle's Mooneye copy is older but has the same
75 acceptance ROMs).

## Tier 1: hardware-captured

| Suite | Size | Hardware | Result protocol | Notes |
| --- | --- | --- | --- | --- |
| **Mooneye Test Suite** (Gekkio, MIT, `31510e12`) | 75 acceptance + 28 emulator-only (MBC) + misc/manual/madness | Every `.s` has a "Verified results: pass: … fail: …" header naming models (DMG 0 / ABC, MGB, SGB, SGB2, CGB, AGB, AGS); fleet table in `README.markdown` "Hardware testing" (DMG-CPU, A, **B**, C; CGB 0–E; AGB …) | B/C/D/E/H/L = 3/5/8/13/21/34 and `LD B,B` = pass; all $42 = fail; also sent over serial (`README.markdown` "Pass/fail reporting") | Of the 75 acceptance tests, 51 are verified on all seven models, 9 on G+S only, the rest per model. **66 apply to DMG-CPU B.** |
| **Gambatte test suite** (sinamas, GPL-2; repository now private, pinned through `pokemon-speedrunning/gambatte-core` `5a41a68c`) | 3,524 ROMs; 1,747 with a `dmg08` result, 3,154 with `cgb04c` | README: "The development of numerous tests, and their verification on hardware, is as much an emphasis as the development of an efficient software implementation." `dmg08` / `cgb04c` name the units (C1, C3) | **Encoded in the file name**: `_dmg08_out3`, `_cgb04c_outFF`, `_dmg08_cgb04c_out2` = the hex digits the screen shows after 15 frames (pattern table in `test/testrunner.cpp` l.65); `_outaudio0/1` = silent or not; a `.png` beside the ROM = expected picture | Also hardware *dumps*: `hwtests/*_dumper_dmg08.bin`, `*_cgb.bin` (I/O registers after reset, VRAM, WRAM, $FExx/$FFxx reads). The deepest PPU/interrupt-timing corpus there is. |
| **GBMicrotest** (aappleby, MIT, `463eb6bc`) | 513 ROMs, no mapper needed | README: "All tests in this repo have been checked on real hardware (version DMG-CPU-08 I believe)" (C1) | $FF82 = $01 pass / $FF fail ($FF80 got, $FF81 expected: "not always set consistently", c-sp) after 2 frames (`is_if_set_during_ime0` ~380 ms) | One register at one T offset after boot; `_a … _d` families step the offset. 304 ROMs are in such families. Built to bring up GateBoy, so small enough for the die model. |
| **blargg** (Shay Green; `retrio/gb-test-roms` `c240dd7d`) | `cpu_instrs`, `instr_timing`, `mem_timing`, `mem_timing-2`, `halt_bug`, `dmg_sound`, `cgb_sound`, `oam_bug`, `interrupt_time` | c-sp: "verified on DMG-CPU-08 (DMG-CPU C blob), CPU-CGB-02 (CPU CGB B) and CPU-CGB-06 (CPU CGB E)" with per-test tables (blargg howto) | Serial text ending "Passed"/"Failed" (`cpu_instrs`, `instr_timing`, `mem_timing`); cartridge RAM: $A001–$A003 = DE B0 61, $A000 = $80 running then the result code, text from $A004 (`dmg_sound`, `cgb_sound`, `oam_bug`, `mem_timing-2`); screen only (`halt_bug`, `interrupt_time`) | `dmg_sound`'s run "never really finishes" on hardware, and its expected picture "was created with SameBoy" (c-sp): use the $A000 protocol, not the picture. |
| **AGE test ROMs** (c-sp, MIT, `1f5bc10e`) | 47 | c-sp: "verified on DMG-CPU-08 (DMG-CPU C blob), CPU-CGB-02, -04, -06"; names carry the devices | per test (c-sp howto) | |
| **Scribbltests** (Hacktix, MIT) | 8 | "verified on MGB 9638 D and CPU CGB D by their author" (c-sp) | pictures | |
| **dmg-acid2 / cgb-acid2** (Matt Currie, MIT) | 1 + 1 | reference *photos* from DMG and CGB in the repo (`img/photo-dmg.jpg`); the reference *image* is exact output | picture match after `LD B,B` | A line renderer passes it: an early PPU milestone, not a timing judge. |

## Tier 2: hardware-corrected

| Suite | What is corrected against what |
| --- | --- |
| **Mealybug Tearoom Tests** (Matt Currie, MIT, `70e88fb9`), 35 ROMs | Expected pictures are "screenshots from my Game Boy emulator (which I believe to be correct)", and `photos/` holds "blurry photos of the ROMs running on real devices" (`README.md` "Usage"). Pictures per revision: `expected/DMG-blob` (24), `expected/DMG-CPU B` (2, both **different** from DMG-blob: C2), `CPU CGB C` (31), `CPU CGB D` (24). Mid-mode-3 register writes: the PPU timing judge. Not "photographs" as the expected images. |
| **Mooneye emulator-only MBC tests** | "Results have been verified using a flash cartridge with a genuine MBC1B1 / MBC2A / MBC5 chip". |
| **SameSuite** (Lior Halphon, X11, `f15645fb`), 78 ROMs | Per-sub-suite README results: the APU sub-suite is sample-accurate through the **CGB-only** PCM12/PCM34 registers; "Pre-CGB devices pass `div_write_trigger` and `div_write_trigger_10` (Tested: DMG-B, blob)", CPU CGB E passes all. A CGB judge, and nearly silent on DMG. |
| **dmg-sim** (msinger, CC BY-SA 4.0, `786f8c8a`) | The die model below; its timing constants were fitted to 11 measured delays on a real DMG-CPU B cartridge port (`README.md` "Timing Model", all within −35 % … +15 %). |

## Die-level models

| Model | Covers | CPU | Speed here | Standing |
| --- | --- | --- | --- | --- |
| **dmg-sim** (SystemVerilog, generated from `dmg-schematics` netlists `28f66aed`) | the whole DMG-CPU B **including the SM83**, WRAM, VRAM, LCD, APU, MBC1/MBC5 carts | from the die (msinger's SM83 schematics; `visual-sm83` exists too) | **~74 min of host time per emulated second**: Mooneye `bits/mem_oam` with `+SECS=0.4` took 29 min 26 s and 506 MB, and its frame 23 matched dmg-sim's expected picture byte for byte (measured 2026-10-05, Icarus Verilog 14.0-devel built here); README says 150 min/s on a Ryzen 5 3600 | The judge for anything a short ROM can show: its README table passes `cpu_instrs`, `instr_timing`, `mem_timing`, `halt_bug`, 11/12 `dmg_sound` (not 10, wave-RAM corruption), every applicable Mooneye acceptance test; not `oam_bug` ("depend on small differences in signal delays which could change with temperature"). |
| **GateBoy** (aappleby, `metroboy` `36797ad4`) | every standard cell of DMG-CPU B; audio channels are traced in the source (`GateBoyCh1–4.cpp`, `/*#p13.…*/` gate tags) though the README says audio is not simulated (C6) | **"my current best guess"**: the CPU is *not* from the die (README) | README: 6–8 fps (≈8× slower than real time) in fast mode | A fast die-ish detector for PPU/timer/DMA; not a CPU judge. |
| Gekkio's `gb-research/sm83-cpu-core` (VHDL) | the SM83 alone, from the die | from the die | sibling's measurement: ~6,400 instructions/s | sm83-python's die judge (its rung 5); listed here because a board failure the core cannot explain goes there first |
| `dmg-schematics` / `DMG-CPU-Inside` (KiCad, CC BY-SA) | schematics, netlists; DMG-CPU-Inside is archived, its errors fixed in dmg-schematics | dmg-schematics includes `sm83/` | — | The document behind both models; read it to settle "which counter bit" questions. |

**Running dmg-sim here** (no root needed; done 2026-10-05):

1. Icarus Verilog 12 (Ubuntu's) cannot parse it (`const real` in functions,
   `timing-default.sv` l.50). Build Icarus from source at the pinned
   `steveicarus/iverilog` commit (`467d830d`): `apt-get download gperf` +
   `dpkg -x` for the one missing tool, `sh autoconf.sh && ./configure
   --prefix=… && make -j16 && make install` (29 s).
2. `make dmg_cpu_b_gameboy.vvp IVERILOG=<that iverilog>` (under a second;
   many "sorry: … not yet fully supported" warnings are expected).
3. `vvp -N dmg_cpu_b_gameboy.vvp -none +BOOTROM=boot/quickboot.bin
   +ROM=<rom> +SECS=<s> +VID_FILE=… +SAV_FILE=…`; `tests/run_test.sh` shows
   how its own harness turns the video dump into a frame (`mkvid/mkimgs`) and
   compares it with ImageMagick (not installed here: `mkvid/mkimgs --raw`
   plus Pillow did the comparison). A GBMicrotest ROM needs quickboot's
   < 0.2 s plus ~2 frames, so roughly 15–20 host minutes each: run the
   disputed ones, not the suite.

**Building GateBoy here** (2026-10-05): `metroboy`'s `symlinks/` point at
sibling checkouts, so clone `aappleby/metrolib` and `aappleby/metron` beside it
(both pinned), then, from `reference/src/metroboy`:

```
g++ -std=c++20 -O2 -DNDEBUG -DCONFIG_RELEASE -w -Isrc -Isymlinks -Isymlinks/metrolib \
    src/GateBoyLib/*.cpp src/GateBoyTests/GateBoyTests.cpp \
    ../metrolib/metrolib/core/*.cpp <metrolib/gameboy/*.cpp except GBBlitter.cpp> \
    audio_stub.cpp -o ../../build-gateboy/GateBoyTests -lpthread
```

(`audio_stub.cpp` defines an empty `audio_post(int, short, short)`; 30 s.)
It links and is headless, but at `36797ad4` every suite in `main()` sits under
`if (0)` and `config_fastmode` makes it return at once; it expects ROMs at
`symlinks/GBMicrotests/bin/` and `tests/mooneye-gb/tests/build/`. Driving it
needs a small driver of our own: **decided not to write one** (Aubrey,
2026-10-05; handoff-brief.md "Decisions made"): dmg-sim is the die judge.

**SameBoy built here** (2026-10-05, 4 s): `make -C reference/src/SameBoy lib
tester CONF=release RGBDS=$PWD/reference/build-rgbds/` (RGBDS 1.0.4 builds
SameBoy's boot ROMs). `libsameboy.so` leaves glibc's vector maths unresolved;
`scripts/sameboy_run.py` loads `libmvec.so.1` globally first. GBMicrotest runs
need `--seconds 0.5` after quickboot (the boot itself takes under 0.2 s).

## Tier 3: emulator-derived, and the detectors

| Source | Use | Measured here (DMG-B, 2026-10-05) |
| --- | --- | --- |
| **SameBoy** (`c458e7c5`, built locally as `libsameboy.so` + tester in 4 s; MIT) | the reference detector, driven by `scripts/sameboy_run.py` (ctypes; mooneye, blargg serial, blargg $A000 and GBMicrotest protocols) | Mooneye acceptance 66/66 applicable (with a real or quickboot boot ROM; 63/66 with SameBoy's own boot ROM, see start-here.md "Boot ROMs"); blargg `cpu_instrs`, `instr_timing`, `mem_timing`, `mem_timing-2`, `dmg_sound`, `oam_bug` pass; GBMicrotest 476 pass, 5 fail, 32 give no result (non-protocol testbenches such as `minimal`, `temp`, `*_testbench`) |
| **MAME 0.285** `gameboy` | trace oracle for the CPU (`scripts/mame_trace.py`, [mame-oracle.md](mame-oracle.md)) | Mooneye acceptance **58/66** applicable: fails `ei_sequence`, `interrupts/ie_push`, `oam_dma/reg_read`, `ppu/lcdon_timing-GS`, `ppu/lcdon_write_timing-GS`, `ppu/stat_lyc_onoff`; no result in 3 s for `oam_dma/sources-GS`, `ppu/intr_2_mode0_timing_sprites`. blargg `mem_timing-2` passes, `dmg_sound` fails $0A, `oam_bug` fails $02 (no OAM bug). A detector only. |
| Gambatte, mGBA, AGE (`c-sp/age`), GateBoy/LogicBoy | second detectors | not run here |
| Mealybug expected pictures, SameBoy-made blargg pictures | see above | — |
| daid's **GBEmulatorShootout** (`d8fe9674`) | a ready-made pass/fail matrix of emulators over these suites, with its own runners | not run here; useful to see which tests *no* emulator passes |

SingleStepTests `sm83` belongs to the CPU core, not here; sm83-python's
`docs/validation.md` covers it.

## What is not available

- A **hardware capture of DMG audio output** (DAC levels, filter): none
  pinned. The analogue stage is a labelled fit, as in famicom-python.
- A **DMG-CPU B hardware run of Gambatte or GBMicrotest**: both were
  captured on a DMG-CPU C (blob) unit (C1). dmg-sim (B) is the arbiter where
  B and C might differ.
- **OAM-bug determinism**: dmg-sim says some cases are not deterministic;
  blargg's 8 `oam_bug` tests pass on DMG-C. Judge the board on those 8 only.
- A **CGB die model**: none. CGB phases rest on Gambatte `cgb04c`, Mooneye
  C-group, SameSuite, Mealybug CGB C/D, c-sp's blargg/AGE runs.

## Local romsets (read in place, never copied into the repository)

`/data/emu/source/myrient.erista.me/files/No-Intro/Nintendo - Game Boy*`
(GB 1,958, GBC 1,960, plus Aftermarket and Private sets);
`/data/emu/roms/gb` and `/data/emu/roms/gbc` (frontend sets, with the
`[BIOS]` boot ROMs: DMG `4ed31ec6…`, DMG0, MGB, CGB revisions). MAME's
`hash/gameboy.xml` (1,743 entries) and `gbcolor.xml` (1,718) carry board
`slot` features. Counts in [cartridge.md](cartridge.md).

## Results: milestone 1 (2026-10-07)

- **Mooneye** acceptance, 56 of the 66 applicable ROMs pass (skip-boot); the other 10 need the
  dot-accurate PPU and are strict xfails (`tests/test_mooneye.py::NEEDS_PPU`). Real boot ROM: same,
  except 3 phase tests (xfail until milestone 2). dmg-sim quickboot: the same set.
- **blargg** cpu_instrs 11/11 (serial text), instr_timing, mem_timing, mem_timing-2 ($A000).
- **MAME trace** (`scripts/mame_compare.py`, blargg 01-special, SameBoy's open boot ROM on both
  sides from $0000): no divergence over 1,200,000 instructions ignoring `if` and `af` (the two
  fields that read PPU phase: IF.0 at instruction 39,939, an LY read at 513,158). MAME is a detector;
  both are PPU-phase leads for milestone 2.
- **PyPy 3.11**: the whole cpu_instrs.gb, 224,319,804 T (56.1 M M-cycles), 3,191 frames, 8.7 s wall (including start-up).
- Import boundaries: `cartridge/` and `apu/` import nothing else from the board
  (`tests/test_import_boundaries.py`).

## Results: milestone 2, in progress (2026-10-07)

The PPU is a real fetcher and two FIFOs (`ppu.py`): OAM scan, a background fetcher (tile, data low,
data high, push), a discarded first tile, a FIFO pop per dot, object fetches with Pan Docs' wait
rule, the window restart, and a pixel pipeline whose register samples (LCDC, BGP, OBP) and VRAM
reads come a fitted number of dots after the pop. Every fitted constant is marked FITTED.

- **dmg-acid2**: pixel-exact on the DMG picture from skip-boot (`tests/test_pictures.py`).
- **Mooneye**: all 66 applicable ROMs pass (skip-boot, quickboot and the real boot ROM), including
  `ppu/*` and the three boot-ROM phase tests.
- **Mealybug (DMG blob)**: 5 of 24 pixel-exact (`m2_win_en_toggle`, `m3_bgp_change`, `m3_obp0_change`,
  `m3_scx_high_5_bits`, `m3_scx_low_3_bits`; `scripts/mealybug_compare.py`, booted from the real boot
  ROM because the tests draw its (R) tile); about 34,000 differing pixels over the other 19. This is
  **not** the brief's acceptance (all DMG pictures): milestone 2 is open on it.
  The PPU is now two machines: the one that times STAT, IRQs and the stalls from register values at
  the pops, and a *shadow* of the same code (`SHADOW_LAG` = 2 dots behind, sharing VRAM and OAM)
  that sees the registers later and draws. The split fixed the WX comparator (it now sees WX 4 dots
  late in the shadow) and cost about 2x per dot. What it did not fix, per picture:
  `m3_wx_6_change` (13.8k: after the window has started, a new WX reached again changes what is
  drawn; Pan Docs' "colour-0 pixel" rule, tried as `WX_GLITCH`, made `m3_wx_4/5` worse), then
  `m3_lcdc_win_en_change_multiple` (8.3k) and `_wx` (4.0k), `m3_bgp_change_sprites` (2.1k),
  `m3_lcdc_win_map_change` (1.0k), `m3_scy_change` (1.0k), and a long tail under 800. Window
  re-trigger and LCDC.5 toggling mid-line are what is left; the Mealybug author's documentation in
  the pinned repository is a stub, so there is no source to follow beyond the pictures.
- **blargg `halt_bug`**: the screen matches the reference picture pixel for pixel (skip-boot and real
  boot ROM).
- **GBMicrotest**: 478 of 513 pass (`scripts/gbmicrotest.py`; the passing set is held by
  `tests/test_gbmicrotest.py`), SameBoy's count. 31 more report no result by protocol (screens,
  benches); 4 fail: `halt_op_dupe_delay` (expects DIV $55 after a HALT whose wake mine does not wait for: a halt-bug case I could not explain), `stat_write_glitch_l154_d`, `win0_b`, and `poweron_stat_006`
  passes only from the real boot ROM. The pieces that got here: the DMG STAT write glitch (seen as a
  read sees the mode), the line-start OAM pulse, LYC/HBlank/VBlank STAT interrupts that reach the
  CPU's dispatch a few dots before IF shows them, a halted wake 2 dots after the raise, line 153's
  comparator (LY seen as 153 for 8 dots; a LYC write in the last cycle still cancels the interrupt),
  IF writes that do not clear a bit raised in the same cycle, STAT showing mode 0 a dot after mode 3
  ends (4 on lines with objects or the window), OBP power-on $FF, and the skip-boot hand-off at dot
  396 (what the real boot ROM leaves; several ROMs are only right from that phase).
- **The interrupt-phase conflict, resolved in the board.** GBMicrotest's `int_oam_*` want the
  line-start OAM interrupt 4 dots earlier than Mooneye's halt-based `intr_2_*` allow. Both hold if
  the CPU's *dispatch* sees the interrupt a cycle early while reads of IF and the STAT line do not
  (`OAM_IRQ_EARLY`, the hidden IF bit in `board.py`), and a halted CPU wakes a cycle later for it
  (`HALT_OAM_DELAY`); line 0's interrupt stays on time (Mealybug's `line_0_fix` agrees). That moved
  the CPU 4 dots earlier against the PPU on lines 1 and up, so the Mealybug register delays were
  refit 4 dots shorter (BGP 3, OBP 6, LCDC 5, fetch reads 6, SCX latch 6) and the window comparator
  sees WX 4 dots late; one ROM (`oam_int_if_edge_c`) fell out.
- Not started: Mealybug's `dmg_b` pictures for `lcdc_bg_en_change` and
  `win_en_change_multiple_wx`.

## Results: milestone 3, the OAM bug (2026-10-09)

Implemented per Pan Docs `OAM_Corruption_Bug.md`: every M-cycle whose bus address is in
$FE00-$FEFF while the PPU scans (dots 0-79 of a visible line, not the first line after LCD on)
corrupts the row being read, with the write, read and read-plus-increment patterns, rows 0 and
1 spared; an idle cycle that steps BC, DE, HL, SP or PC into that range counts as a write
(`PPU.corrupt_oam`, `Board._bug`, DMG only: `Machine.oam_bug`). The scan reads row *n* at dot
4n (`OAM_BUG_START` = 0, fitted).

- **blargg `oam_bug`**: 1, 2, 3, 4, 5, 6 and 8 pass (`tests/test_blargg.py`); Mooneye
  `oam_dma/sources-GS` and `bits/mem_oam` were already in the 66.
- **`7-timing_effect` is open.** It corrupts OAM at every `inc de` offset across a scan, prints
  each changed OAM, and checksums the output. In the board every row 1-19 corrupts, which makes
  19 prints; the ROM's log lives in cartridge RAM ($A004-$BFFF, 8 KiB) and 15 prints overflow it into
  work RAM, so the ROM derails (no result). Capping the last corruptible row at 4-14 completes
  with a wrong checksum every time (none equals $7D792E7C), and so did the read and read-plus-
  increment patterns for the idle cycle. DMG-C therefore corrupts fewer or different iterations
  than any of these; the likely places are the end of the corruptible window and the first
  corruptible row. I stopped fitting by checksum without a second oracle: SameBoy's rule (rows
  8-bytes-aligned from index 0, 2 dots per object) agrees with the board on the first row, and
  the dmg-sim die model (default simplified OAM) does not model the bug.
- Not done: Gambatte `oam_access/*` and `oamdma/*` dmg08 results.
