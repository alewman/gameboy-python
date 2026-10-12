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

## Results: milestone 4, the APU (2026-10-09)

Four channels, DACs, NR50/NR51 mixing, NR52 power, a frame sequencer clocked by falling edges of the
system counter's bit 12 (DIV-APU; a DIV write ticks it), every DMG quirk in Pan Docs "Obscure
Behavior" that the judges reach (`gameboy_python/apu/__init__.py`, behind a boundary: it imports
nothing from the board). `take_samples()` returns interleaved 16-bit stereo at 44.1 kHz;
`--wav` saves it. **The mix is a labelled fit, not the analogue DMG**: DAC digital 0 maps to +1 and
15 to -1, an off DAC to 0, NR51 pans, NR50 scales by (volume + 1) / 8, the sum is divided by 4 and
passed through the DMG high-pass (charge 0.999958 per T), which is off while every DAC is off.

- **blargg `dmg_sound`**: 12 of 12 (`tests/test_apu.py`; SameBoy 12/12, dmg-sim 11/12). Fitted
  for 09, 10 and 12: `WAVE_TRIGGER_DELAY` = 6 T, `WAVE_WINDOW` = 2 T, the trigger-corruption age
  window `CORRUPT_LO/HI` = 1..3 T (test 10 accepts several windows; none was picked by a second
  oracle).
- **SameSuite** `div_write_trigger`, `div_write_trigger_10` (the two that pass on DMG-B): pass. The
  second needed one rule: the APU powered on while DIV's bit 12 is high starts at frame step 1.
- **Gambatte `_outaudio`** (87 ROMs with a DMG-08 result; `scripts/gambatte_audio.py`, from the real
  boot ROM, 15 frames, "audible in the last frame"): 76 agree, held by `tests/gambatte_audio_pass.txt`.
  The 11 that disagree are sub-M-cycle phase tests (duty position at a retrigger, envelope counter
  timing): `ch1_duty0_pos6_to_pos7_timing_1`, `ch1_duty0_to_duty3_pos3*`, `ch1_init_pos_1/5/7`,
  `ch1_init_reset_sweep_counter_timing_4`, `ch2_init_env_counter_timing_2/3/4`,
  `ch2_init_reset_env_counter_timing_3/4/5/11`. The APU ticks a whole M-cycle at a time.
- `audible()` is my reading of Gambatte's audio criterion (a routed channel, an enabled DAC, a
  non-zero digital value in the last frame), not the testrunner's code.

## Results: milestone 5, the cartridges (2026-10-09)

- **Mappers**: MBC1 (+ MBC1M multicart, detected by a second logo at $40104 in a 1 MiB image),
  MBC2 (A8 selects RAMG/ROMB, 512 x 4-bit RAM, upper nibble reads 1s), MBC3 (+ RTC on an injectable
  clock; registers raw 6/6/5/8/9-bit with the out-of-range counting rules; 48-byte BGB/SameBoy-style
  save trailer), MMM01 (menu in the last 32 KiB), MBC5 (+ rumble).
- **Mooneye `emulator-only`**: 28 of 28 (`mbc1` 13, `mbc2` 7, `mbc5` 8; `tests/test_cartridges.py`).
- **rtc3test** (a detector, not a judge): basic and range pictures exact. `sub-second-writes` shows
  TIMEOUT on every row; the clock logic was checked and the cause is not found.
- **Compatibility sweep** (`scripts/compat_sweep.py`; No-Intro GB set read in place, real DMG boot
  ROM, picture at frame 1500 against SameBoy DMG-B, last 30 frames window): the stride-100 sample is
  **25 of 25 identical**, 6 CGB-only skipped. An earlier run showed 11 "differences"; every one was
  the harness, not the board: `run_frames` counts VBlanks (the first call swallowed ~4.7 LCD-off
  boot frames) while SameBoy counts 70,224-cycle frames from power-on, so attract-mode games sat at
  different pages. The sweep now lines the two up by T-cycles. The stride-1 run is recorded
  separately once finished.
- Open from earlier milestones is unchanged (see their sections).

## Results: milestone 6, the hardware-captured sweep (2026-10-10)

**GBMicrotest** (513 ROMs; `scripts/gbmicrotest.py --sameboy`): **481 pass**, 3 fail, 29 report no result by
protocol. SameBoy beside it: 476 pass on both, 5 on the board only (`lyc1_int_if_edge_c`,
`poweron_oam_000/005/070`, `ppu_spritex_vs_scx`), 1 on SameBoy only that is real (`win0_b`; the board
fails it with $FF82 = $FF), and the rest silent. Two protocol fixes moved the count from 478: the run is
30 frames, not 12 (`is_if_set_during_ime0` takes ~380 ms), and two early-style ROMs
(`ppu_spritex_vs_scx`, `004-tima_boot_phase`) report not at $FF82 but as a flag byte written to
$8000 in a loop ($55 = the DMG value came out as expected; their sources), held by
`testrom.VRAM_FLAG_ROMS`. SameBoy's $FF82 on a silent bench is HRAM noise (it randomises HRAM: the
same ROM read $20 and $01 in two runs), so "SameBoy passes" is only believed for ROMs whose source reports there.
The 3 failures are the old ones: `halt_op_dupe_delay`, `stat_write_glitch_l154_d` (SameBoy fails
both too), `win0_b`.

**Gambatte `dmg08`** (1,784 ROMs, 1,784 verdicts: screen-digit and `_dmg08.png` picture tests with
testrunner.cpp's rules; `scripts/gambatte_dmg08.py`, tabulated by `scripts/gambatte_table.py`). The
`_outaudio` tests are `scripts/gambatte_audio.py`'s (76 of 87). The first run, from the real boot ROM,
passed **1,322** (SameBoy 1,642: 1,288 on both, 34 board only, 354 SameBoy only, 108 neither). Skip-boot gave
the same 1,322, so the post-boot hand-off is a faithful start and later runs use it (15 frames, minutes
instead of hours). After the fixes below the skip-boot run passes **1,418** against SameBoy's 1,642:

| all | tests | board | SameBoy |
|---|---|---|---|
|---|---|---|---|
| arg | 50 | 43 | 50 |
| bgtiledata | 16 | 0 | 8 |
| bgtilemap | 16 | 0 | 12 |
| dmgpalette_during_m3 | 13 | 7 | 7 |
| enable_display | 68 | 63 | 67 |
| halt | 82 | 71 | 80 |
| irq_precedence | 20 | 14 | 20 |
| lcdirq_precedence | 31 | 28 | 31 |
| ly0 | 33 | 32 | 31 |
| lyc153int_m2irq | 6 | 5 | 5 |
| lycEnable | 78 | 67 | 74 |
| m0enable | 68 | 53 | 64 |
| m1 | 61 | 50 | 56 |
| m2enable | 43 | 37 | 36 |
| m2int_m0irq | 32 | 30 | 32 |
| m2int_m2irq | 6 | 5 | 6 |
| miscmstatirq | 139 | 132 | 137 |
| oamdma | 393 | 293 | 326 |
| on_screen | 18 | 2 | 12 |
| scx | 8 | 7 | 8 |
| scx_0363c0 | 36 | 0 | 24 |
| scx_during_m3 | 8 | 3 | 7 |
| scy | 24 | 9 | 20 |
| serial | 36 | 28 | 36 |
| sound | 50 | 48 | 49 |
| sprites | 96 | 74 | 95 |
| tima | 113 | 112 | 112 |
| window | 135 | 100 | 132 |

Fixed by this pass (each shown by a Gambatte group, none by tuning to a single ROM):

- **OAM DMA bus reads**: while a DMA owns OAM, CPU reads of the whole $FExx page (not just $FE00-$FE9F)
  return $FF (`oamdma_src*_busypopFE9F/FEFF`, 26 ROMs).
- **DMG DMA/CPU write conflict**: a CPU write on the bus the DMA is reading is ANDed into the byte the DMA
  just moved into OAM, DMG only (`oamdma_src*_busypush0001/8001/A001_2/FEA1/FF01/FF81`).
- **Serial**: the interrupt reaches dispatch on time but IF, the final shift of SB and the clearing of SC
  bit 7 show one M-cycle later (`SERIAL_IF_HIDE`, `SERIAL_FINISH_DELAY`): 20 to 28 of 36.
- **SCY write lag** 4 dots (`SCY_LAG`, fitted; `scy_during_m3` 0 to 5 of 18, most of the rest within 8 to 16 pixels).
- **WY == LY compared when WY is written**, not only at line start: `window/arg` 20 to 43 of 50.
- **DMG 0**: the STAT line stops blocking (`Machine.stat_blocking`, now wired in the PPU): Mooneye
  `stat_irq_blocking` fails on the DMG 0 machine as its header says and passes on DMG-B; the three DMG 0
  boot tests (`boot_div/hwio/regs-dmg0`) pass from the DMG0 boot ROM (`tests/test_dmg0.py`).

Open, with what is known (none is a C1 B/C difference on dmg-sim; those cannot be shown without a
second DMG oracle and none was claimed):

- **Pictures that differ by one tile column** (`bgtilemap` 0/16, `bgtiledata` 0/16, `scx_0363c0` 0/36,
  `on_screen` 2/18, `scy` 9/24): the board's image matches except for a column of 8 by 128 pixels; the map
  and data fetch reads against a mid-line VRAM write are about a dot off. `MAP_SHIFT` 2 to 6 changes none of
  `bgtilemap`, so it is not that constant. SameBoy passes 12 of 16 of `bgtilemap`.
- **`oamdma`** (293 of 393; SameBoy 326): the remaining `busypush*` ROMs (C001/E001/F001/A001/FE01, an MBC5
  cartridge with RAM) read back values that are neither the DMA's nor the CPU's byte (`e = $12` from a
  disabled RAM page after a push before the DMA; an open-bus value); `*rombankchange*`, `*srambankchange*`,
  `busyread*` and the sprite-DMA `late_sp*` ROMs.
- **Interrupt phase**, one M-cycle either way (`m0enable`, `m1`, `halt`, `lycEnable`, `irq_precedence`,
  `enable_display`, `miscmstatirq`, `lcdirq_precedence`): the same family the Mooneye/GBMicrotest conflict of
  milestone 2 was, fitted against those two; the Gambatte ROMs want the opposite of the fit for some.
- **Window and sprites mode-3 length** (`window` 100/135, `sprites` 74/96, `scx_during_m3` 3/8): WX and
  SCX edge cases of the fetcher.
- **Serial** 8 ROMs: the DIV-write variants (`start_late_div_write_*`) and `start_wait_stop/sc80/clear_if`.
- Where SameBoy fails too (104 ROMs, mostly `oamdma`, `bgtiledata`, `on_screen`, `dmgpalette_during_m3`) the
  expected file may rest on a hardware revision the DMG-B model does not cover.

## Results: milestone 7, the CGB (2026-10-10, first pass)

The CGB board is the `cgb` machine row (CPU CGB E, decided 2026-10-05). It boots from the real CGB
boot ROM (No-Intro "World (Rev 1)", read in place and SHA-checked) or from a skip-boot state
measured by running that ROM on this board (DIV counter `$1E9C`, line 144 dot 164, white
background palettes). Everything below is a first pass with the fitting still to do; numbers are
from the dates in the headings, SameBoy is not tabulated beside the CGB runs yet.

| Suite | Result | How |
|---|---|---|
| Mooneye acceptance + misc, the ROMs whose `pass:` list names CGB (58) | **58 of 58** | `scripts/mooneye_cgb.py` (acceptance from skip-boot, `misc/boot_*` from the real boot ROM) |
| cgb-acid2 | **pixel-exact** (0 of 23,040) | `scripts/cgb_picture.py`, real boot ROM, 300 frames |
| blargg `cgb_sound` | **12 of 12** | `run_blargg_ram` |
| cgb-acid-hell | 2 pixels differ | same |
| Gambatte `cgb04c` (the testrunner's CGB verdicts, 3,221) | **2,120** (65.8 %) | `scripts/gambatte_dmg08.py --cgb --skip-boot` |
| SameSuite (76) | 23 | `scripts/cgb_suites.py same-suite` |
| AGE, the ROMs verified on CGB E (28) | 7 | `scripts/cgb_suites.py age` |
| Mealybug CGB D pictures (21) | 3 pixel-exact | `scripts/cgb_pictures.py` |

### What was built

CGB registers (KEY0/KEY1, VBK, SVBK, HDMA1-5, RP, BCPS/BCPD/OCPS/OCPD, OPRI, the undocumented
`$FF72-$FF75`, PCM12/PCM34); two VRAM banks and eight WRAM banks; BG attributes (palette, bank,
flips, BG-to-OAM priority), object palettes and bank, LCDC.0 as master priority, object
priority by OAM index (OPRI) with the DMG-compatible mode on top (the boot ROM sets it through
KEY0); HDMA and GDMA; the STOP speed switch (CPU, timer, DMA at twice the rate, PPU and APU at the
single-speed rate, the DIV-APU bit moving from 12 to 13); the CGB boot ROM at `$0000-$00FF` and
`$0200-$08FF`; the serial port's fast clock; the APU's CGB differences. The picture is RGB555,
two bytes a pixel in `PPU.frame` on CGB hardware.

### Found by the tests and fixed

* **OPRI starts at 0 on a CGB** (the boot ROM never writes it for a CGB game): cgb-acid2's mole
  was drawn with the DMG's X-ordered priority. Fixed: 12 pixels to 0.
* **The TAC-disable glitch exists on the CGB E** (Mooneye `timer/rapid_toggle`, verified on CGB;
  Pan Docs says it does not). The `tac_disable_glitch` field of the machine row is now True.
* **The CGB's VBlank interrupt is 4 dots after the line-144 OAM one** (Mooneye
  `misc/ppu/vblank_stat_intr-C` against the `-GS` ROM): `VBLANK_CGB_DELAY`, FITTED.
* **LY reads 153 for 8 dots on a CGB E, not 4** (AGE `ly-cgbE`, `ly-ncmE`: the extra M-cycle in
  both speeds; 6 dots in double speed because of where the read lands).
* **The speed switch** halts the CPU for `0x20008` units unless an interrupt wakes it first
  (SameBoy `stop()`); the first version cancelled the halt at once and hung 50 SameSuite ROMs.
* **HDMA/GDMA timing**: a byte takes 2 units at single speed and 4 at double (an M-cycle is 4);
  the start-up is fitted at 6 units in both speeds (`HDMA_START`; Gambatte `gdma_cycles_*`,
  `hdma_cycles_*` pairs all pass at 6 at single speed). dma 127 to 134 of 229.
* **APU on CGB** (blargg `cgb_sound` 7 to 12 of 12): powering off clears the length counters
  and keeps them read-only; wave RAM is reachable at any time while CH3 plays; a CH3 trigger
  corrupts nothing.
* **Halt-wake**: the DMG's fitted extra dots for a halted CPU also hold on the CGB for the STAT
  interrupts (Mooneye `intr_2_*` fail without them); an experiment that removed them was
  reverted.

### Open items, with the evidence

* **SameSuite APU, 47 ROMs** (`channel_1` 21 of 21, `channel_2` 15 of 17, `channel_4` 9 of 13,
  `channel_3` 4 of 17, `div_trigger_volume_10`, `div_write_trigger_volume_10`): they read PCM12 and
  PCM34 at M-cycle resolution and expect the CGB E's 2 MHz-tick behaviour. `channel_1_delay` and
  `channel_2_delay` show the first duty sample arriving a few ticks early (ours `80 80 80 80 80 00
  00 80`, expected `00 80 80 80 80 80 80 00`). SameBoy models this with a per-channel countdown
  in 2 MHz ticks, a trigger delay of 4 or 6 ticks by the divider phase (`lf_div`), a suppressed
  first sample and revision branches (`apu.c`, NR14 write); this board's pulse channel is a 4-T
  counter with none of that. The next step is an APU at that resolution (a milestone of its own).
* **SameSuite DMA**: `gdma_addr_mask` and `hdma_lcd_off` fail; not looked at.
* **AGE, 21 ROMs**: the `oam`, `vram`, `stat-mode*`, `speed-switch` and `halt-m0-interrupt` ROMs.
  `oam-read-ncmE` raw timing rows (`scripts/age_diag.py --timing`) show our OAM lock agreeing with
  the expected rows up to the E-only positions (`EFF` in the ROM's table): on an E the OAM stays
  locked one M-cycle longer after mode 3 for particular SCX alignments. Not modelled.
* **Gambatte `cgb04c`, 1,101 failing verdicts.** The reference is a CPU CGB C and the board is a
  CGB E, so some are expected differences, but the large groups are real: `oamdma` 142 of 418 (the
  CGB's OAM-DMA bus rules are not written: the DMG's AND conflict is switched off and nothing
  replaces it), `speedchange` 129 of 206 (`speedchange*_div_*`, `tima*`, `ch2_nr52` and the
  `ly44_m3` ones), `dma` 134 of 229 (the late/halt/speedchange HDMA variants), `space` 145 of
  226, `window` 145 of 195, `sprites` 114 of 151, `scx_0761c0` 0 of 84, `bgtilemap` and
  `bgtiledata` 0 of 42 (the DMG's own tile-column offset, still open), `lycEnable` 109 of 147,
  `halt` 59 of 80, `enable_display` 88 of 116, `scy` 12 of 43, `cgbpal_m3` 29 of 44 (palette RAM
  reads and writes at the end of mode 3).
* **Update (2026-10-11): CGB OAM-DMA bus rules written** from Gambatte's conflict map
  (`memptrs.cpp`, `memory.cpp` `nontrivial_read/write`): a CGB source has its own conflict regions
  (ROM/SRAM: everything but VRAM; VRAM: $8000-$9FFF; WRAM: $C000 up), a CPU read in them gets the
  byte the DMA just moved (from $C000 up and a non-WRAM source: WRAM, in the half named by bit 4
  of the DMA page), a CPU write lands in OAM (0 from a VRAM source) or in WRAM, and sources from
  $E0 up are invalid ($FF). Gambatte `oamdma` 142 -> 369 of 418; whole `cgb04c` 2,120 -> 2,355+.
  The remaining 49 `oamdma` are `late_sp*` / speedchange timing (not looked at) and
  `busypushFEA1/FF01`, which are a **revision difference**: Gambatte's CGB C has RAM at
  $FEA0-$FEFF (address bits 3-4 ignored), the board's CGB E reads a nibble pattern there.
* **GDMA start-up conflict.** The start-up that fits Gambatte's `gdma_cycles_*_2` pairs (6 units)
  moves the real boot ROM's hand-off DIV counter 12 units late (its three GDMAs, all in VBlank
  from WRAM) and fails Mooneye `misc/boot_div-cgbABCDE` (hardware, all CGB revisions), which
  passed before the fit. Neither VBlank nor a WRAM source separates the cases (both tried; the
  Gambatte tests also read from WRAM and run in VBlank). `HDMA_START` is back to 2: the
  Gambatte `dma` group is then 132 of 229 instead of 134 (13 `gdma/hdma_*_2` ROMs lost, 11
  `hdma_*late*/m3halt*` gained). Open: what the real start-up depends on.
* **Compatibility sweep, stride 1 (DMG board, real boot ROM, frame 1500, vs SameBoy DMG-B)**:
  3,064 ROMs: 1,822 same, 60 near, **249 differ**, 19 unsupported, 914 skipped (CGB only). Not
  triaged. Largest cluster: 14 Pokemon Gold/Silver ROMs at 215 px, all on lines 0-1 and 65-80
  (a mid-frame scroll-register effect, i.e. mode-3 timing; SameBoy is a detector, so which side is
  right is open). 15 ROMs differ by one pixel.
* **Speed switch (Gambatte `speedchange`, CGB C)**: STOP now resets DIV, taking the group from
  129 to 132 of 206. The halt length is 0x20008 units; a timer lag of 8 units gains 2 more ROMs
  but fails AGE `spsw-stop-prefetch` (CGB E), so `SPEED_SWITCH_TIMER_LAG` stays 0 (a revision
  difference or an open item). Remaining 74: APU timing (`ch2_nr52`), `tima`, `ly44_m3` STAT,
  `m2int`.
* **LCDC.3/LCDC.4 at the background fetcher**: the map select and tile-data select reach the
  fetcher 4 dots late (`BG_MAP_LAG`, `BG_DATA_LAG`, fitted). Gambatte `bgtilemap` goes from 0 to
  16 of 24 on CGB (DMG 4 of 16); the sweep over 2/4/6/8 peaks sharply at 4. `bgtiledata` stays
  mixed on the sprite lines (rows 0-15 fetch a mixed tile): the fetch phase is open.
* **First-object cost in double speed**: the first object on a line costs 3 fewer dots than the
  full fetch (`FIRST_OBJECT_DISCOUNT`, Mooneye). In double speed Gambatte's CGB ROMs want 2
  (`FIRST_OBJECT_DISCOUNT_DS`): `sprites` + `space` go from 261 to 346 of 380, all of the
  gain in the `_ds_` ROMs (111 of the 119 earlier failures; they failed for odd sprite counts).
  The same value in single speed breaks AGE `stat-mode-sprites` (CGB B/C/E) and DMG prefers 3
  (74 of 96 against 69), hence the split. Why double speed differs is open. The regenerated
  pass list is 2,458 (was 2,355): 25 earlier passes were lost (`speedchange*_tima`/`ch2_nr52`,
  `late_sizechange_sp*`, a few `hdma_late_*m3halt*`) and 128 gained.
* **Window comparator lag (timing PPU)**: `WX_LAG` 4 -> 1. Gambatte CGB `window` 143 -> 148 of
  193 (0 and 1 tie; 2: 146, 3: 144, 6: 141); `WIN_LAG` 2 and 4 are worse (136, 129). The
  Mealybug fit is carried by `SHADOW_WX_LAG`, unchanged, and GBMicrotest, Mooneye (DMG, CGB),
  the pictures and both Gambatte lists pass. Pass list 2,463 (2 lost, 7 gained).
* **`OBJ_SIZE_LAG`** 1 and 3 change nothing on the CGB `sprites` group; the three
  `late_sizechange_sp*_ds_1` ROMs lost to the double-speed discount stay open.
* **Mealybug CGB D, 18 of 21 differ** by 10 to 8,300 pixels, mostly the mode-3 register-change
  tests; the DMG board's fits are used unchanged and CGB has its own latencies.
* **cgb-acid-hell**: 2 pixels.
* **Not done**: SameBoy columns for the CGB runs, the SGB and AGB rows, DMG0/CGB0 revisions of
  the CGB, the real-boot and skip-boot equivalence check for CGB (the DMG's was identical), and
  the CGB speed-switch's PPU "odd mode".
