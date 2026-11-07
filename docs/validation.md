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
- Import boundaries: `cartridge/` imports nothing else from the board, and the APU core
  (gb-apu-python, extracted 2026-11-06) imports no board (`tests/test_import_boundaries.py`).

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
Behavior" that the judges reach (since 2026-11-06 the gb-apu-python core, pinned by revision and
extracted with its history from `gameboy_python/apu/`; it imports nothing from the board). `take_samples()` returns interleaved 16-bit stereo at 44.1 kHz;
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
| SameSuite, the ROMs that apply to a CGB E (69; 2026-10-22) | **69** (APU 63 of 63) | `scripts/cgb_suites.py same-suite` |
| AGE, the ROMs verified on CGB E (28; 2026-10-22) | 8 | `scripts/cgb_suites.py age` |
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
* **SameSuite APU, 63 of 63 applicable** (2026-10-21): the pulse channels now count in
  2 MHz ticks with SameBoy's start-up rules (a trigger delay from the tick phase `lf_div`, a held
  first sample, the CGB D/E phantom duty step, the NRx4 frequency-change undo); the volume
  envelope is a 3-bit countdown clocked by DIV-APU's falling edge and reloaded and armed on the
  rising edge half a period later (`APU.secondary_tick`), with the NRx2 write glitches
  (separate DMG and CGB forms); the CGB sweep runs its calculation a few 1 MHz ticks after the
  event; the CGB noise channel steps a 14-bit counter in 2 MHz ticks and NR43 clock-select
  writes glitch the LFSR (the deterministic variants only). Duty 2 corrected to
  `1 0 0 0 0 1 1 1`. SameSuite ROMs whose device suffix does not name E (`-cgb0B`, `-cgb0BC`,
  `-A`, `-cgb0`, `-cgbB`) are no longer counted: they record other revisions.
* **An HBlank transfer started with the LCD off copies one block at once** (SameSuite
  `hdma_lcd_off`, `gdma_addr_mask`; Gambatte `hdma_disabled_display_1`): `$FF55` with bit 7 set
  runs its first block whenever STAT reads mode 0, which includes the LCD off (SameBoy starts
  it the same way); no further HBlank comes, so the rest waits. Gambatte CGB pass list 2,467
  (0 lost; 3 sweep ROMs from the APU rebuild and this one gained).
* **Halt-wake**: the DMG's fitted extra dots for a halted CPU also hold on the CGB for the STAT
  interrupts (Mooneye `intr_2_*` fail without them); an experiment that removed them was
  reverted.

### Open items, with the evidence

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
* **Speed switch, the DIV reset (2026-10-22)**: SameBoy (`cgb-c` and `cgb-e` alike) passes 62 of
  the 74, so they are not revision differences, and AGE `spsw-stop-prefetch` (verified on CGB B,
  C and E) rules out the end-of-halt lag. The switch now clears DIV at the end of STOP's operand
  read, not at its opcode (Gambatte `speedchange*_tima` `_1`/`_2` pairs move STOP by one M-cycle
  and count the falling edge of a still-high timer bit), and with IME off the counter then stands
  still one M-cycle (SameBoy `enter_stop_mode` holds the CPU's DIV-reset signal). The lag is
  gone. `speedchange` 132 -> 141 of 206, AGE 7 -> 8 (`spsw-div`), Gambatte CGB pass list 2,480
  (26 gained, 13 lost, all in this group). The 13 are the other halves of pairs that straddle
  one M-cycle: `ch2_nr52_*_2b` (before: the `_2a` halves failed; length expiry against the
  DIV-APU edge lands inside an M-cycle) and four `tima0[1-3]` variants. They need sub-M-cycle
  phase between the counter and the CPU, which the board does not model.
* **Mode 3's end in double speed (2026-10-23)**: of the 394 failing ROMs whose names mark double
  speed or a speed change, SameBoy `cgb-e` passes 296, so most are not revision differences. In
  double speed STAT now shows mode 0 with no extra lag (`MODE0_READ_LAG_DS` 0; single speed keeps
  1), and the CGB palettes stay locked 2 dots longer than STAT shows mode 3 (`PAL_HOLD_DS`;
  SameBoy also frees the palettes after STAT and VRAM). Swept over those 1,186 ROMs: lag 0/1/2
  give 839/817/802 and the palette hold 0/1/2/3/4/6 on top gives 839/841/843/841/839/837.
  Gambatte CGB pass list 2,480 -> 2,506 (28 gained: `*_ds` m3stat, `vramw_m3end`,
  `gdma/hdma_cycles`, pre/postread/write, two `speedchange*_ly44`; 2 lost, both passed by SameBoy:
  `gdma_cycles_2xshort_ds_1`, `offset1_lyc99int_m0stat_count_scx2_ds_1`). SameSuite 69, Mooneye
  CGB 58, AGE 8 unchanged. Tried and rejected: shifting the PPU by whole dots at the switch
  (+-1 dot loses about 115; +-2 swaps which half of each `ly44` pair passes). The `ly44_m3` pairs
  left (about 13) want mode 0 one dot earlier than any read lag gives; in double speed that is
  inside an M-cycle, the same sub-M-cycle phase as the `tima`/`ch2_nr52` pairs. The largest group
  SameBoy passes, `scx_during_m3`, fails in single speed and on DMG too (fetcher, above).
* **SCX in mode 3 (2026-10-25)**: the map column is now SameBoy's, `(SCX + position + 8 - (cgb
  && !during_object_fetch)) / 8`. The position is taken at the map step's first dot, and SCX
  `SCX_COL_DOT` (2) dots later; once an object has been fetched on the line it is
  `SCX_COL_DOT_OBJ` (5), because our fetches after one run 3 dots early against SameBoy's
  (instrumented SameBoy fetch logs). Column 0 takes `SCX >> 3` at its step's first dot. The
  fine scroll is no longer latched at the start of the line: pixels are dropped until their count
  matches `SCX & 7`, seen `SKIP_LAG` (7) dots late (SameBoy compares from dot 89; ours compares
  later). The CGB's -1 is skipped for a map step begun during an object fetch, which cgb-acid2
  needs (120 pixels off without it). Gambatte `scx_during_m3`: DMG 3 -> 37 of 44, CGB 58 of 97.
  Gambatte DMG pass list 1,426 -> 1,462 and CGB 2,506 -> 2,565, nothing lost. The gains outside
  the group are `m2int_m3stat/scx` `late_scx4_*` and `enable_display`
  `ly0_late_scx7_m3stat_scx0_1`. dmg-acid2, cgb-acid2 and Mealybug `m3_scx_high_5_bits` and
  `m3_scx_low_3_bits` stay exact (all 24 Mealybug scores unchanged), and Mooneye, blargg,
  GBMicrotest 481 and AGE 8 are unchanged. Sweeps: `SKIP_LAG` 2-5 give 30-31 of the DMG group, 6
  gives 35 but breaks `m3_scx_low_3_bits`, 7 gives 37 and 8 gives 36. `SCX_COL_DOT`/`_OBJ` at
  2/5 is the only pair that keeps both Mealybug SCX pictures (2/4 and 2/6 break `high_5_bits`).
  SameBoy fails 3 of the DMG group too (`scx_0761c0` v2 and v3, `scx_m3_extend`). Of the 7 the
  board fails, 4 differ only on row 0 (line-0 interrupt timing, open) and the rest are `spx0/1/2`.
* **Pass lists keyed by path (2026-10-25)**: `scripts/gambatte_dmg08.py` named results by file name,
  and the `scx_during_m3/scx_*` subdirectories repeat names, so verdicts collided. Results and both
  pass lists are now keyed by the ROM's path in the suite. The DMG list was also stale: regenerated
  at f31b320 it held 1,426, not 1,418 (+9 `bgtilemap`/`late_wx`, -1 `late_wx_wx03_2`).
* **The smoke gate**: `scripts/smoke.py` runs `tests/smoke.txt`, a curated slice for the loop
  between edits. It holds the classics that must stay exact (acid2, the exact Mealybug pictures,
  Mooneye, blargg timing and OAM bug, cgb-acid2, AGE and SameSuite register tests) and 315 Gambatte
  ROMs: per directory, up to 10 whose verdict flipped across the fitting sweeps and the pass lists'
  history, plus 2 stable passes. It reports regressions and gains against the pass lists. The whole
  lists and slow suites stay the gate before a commit; with `--list`, the same runner spreads the
  pytest suites over cores (5.3 hours of wall clock here; the serial run reached a third in 7).
* **PyPy and the PPU's attributes (2026-10-25)**: the PPU had 86 attributes at f31b320 (90 after
  the SCX work), past the 79 PyPy keeps in a fixed layout, so it and its shadow were dicts.
  `__slots__` lifts the limit: dmg-acid2 runs 3.1 -> 9.3 frames per CPU-second and cgb-acid2
  0.88 -> 7.3. The smoke gate went from 8 minutes to under 4. `tests/test_pypy_layout.py` fails
  if any object of the board reaches 80 attributes without slots.
* **SCX in mode 3, the rest (2026-11-04)**: four changes, checked against instrumented SameBoy
  DMG and CGB E fetch logs. (1) When the fine-scroll drop has passed `SCX & 7` and will wrap, the
  map column's position is the drop count minus 8 (SameBoy's position goes back by 8; Gambatte
  `scx_0360c0`). (2) A map step begun during an object fetch reads SCX at the read itself, since
  SameBoy reads after the fetch. (3) In double speed the drawing PPU sees SCX `DS_SCX_LAG` (4) dots
  late: SCX writes reach ours 4 dots before SameBoy's. (4) In double speed line 0's OAM interrupt
  also comes early, by `EARLY_LINE0_DS` (2) dots (SameBoy's line-0 writes land one M-cycle after
  line 1's, ours two); the same rule in single speed broke 16 ROMs and was dropped. Gambatte
  `scx_during_m3`: DMG 37 -> 41 of 44, CGB 58 -> 84 of 97. Pass lists DMG 1,462 -> 1,466 (nothing
  lost) and CGB 2,565 -> 2,591 (31 gained, 5 lost). Of the losses SameBoy CGB E fails 3
  (`lyc153int_m2irq_ifw_ds_1_out2`, `scy_during_m3_ds_5`,
  `late_enable_afterVblank_ds_lcdoffset1_2`); the other 2 (`late_enable_afterVblank_ds_2`,
  `late_enable_ly0_ds_2`) trade with their `_1` halves, which now pass, so those window line-0
  pairs straddle one double-speed M-cycle (open; a line-0 window lag did not settle them).
  Telling the shadow PPU it runs in double speed was tried and is wrong: it took the timing PPU's
  first-object discount (2) and lost `bgtilemap_spx08_ds_2/3`. Mealybug, dmg-acid2, cgb-acid2,
  pytest, GBMicrotest 481 and AGE 8 are unchanged. Open: DMG `scx_0761c0` v4 (SameBoy passes; v2
  and v3 SameBoy fails too), and on CGB the `spx2_ds` variants and `scx_0761c0` ds 3-6.
* **OAM DMA write conflicts on DMG (2026-11-04)**: a CPU write on the bus the DMA is reading never
  reaches memory; the byte lands in OAM at the DMA's current index, as written when the source is
  the cartridge (ROM or SRAM) and ANDed with the DMA's byte when it is WRAM. We stored the write
  and ANDed every source. The `busypush` ROMs push $55AA during the transfer and print the two OAM
  bytes and the stack's memory, which shows both rules. Gambatte DMG `oamdma` 293 -> 377 of 393
  (all 156 `busypush` pass), pass list 1,466 -> 1,550, nothing lost.
* **CGB DMA after the opcode fetch**: SameBoy (`GB_cpu_run`) runs a pending HDMA/GDMA block after
  the next instruction's opcode fetch, not before it, and never on a dispatch's discarded fetch;
  the board now does the same, with SameBoy's start-up (2 units, 4 in double speed). Gambatte CGB
  `dma` +4 (`gdma_cycles_2xshort_ds_1` x2, `hdma_pc_7ffe`, a `halt_late_unhalt` HDMA) and
  `irq_precedence` -4 (`*hdma_vs_*`; SameBoy CGB E fails those four too). Mooneye `boot_div`
  holds. Tried and dropped: one more unit at the end of a GDMA passes the nine
  `gdma_cycles_*_2`/`gdma_weird_2` from the real boot ROM but does nothing from the skip-boot state
  the pass lists use, so it fits the phase the boot leaves, not the transfer (open).
* **WY and LYC writes on CGB**: SameBoy compares a written WY at the next 4-dot boundary, on CGB a
  phase later than on DMG, and lands a CGB single-speed LYC write a T-cycle later than DMG's
  (`cgb_conflict_map`). On CGB the board compares WY `WY_WAIT_CGB` (5) dots after the write (DMG
  keeps the immediate compare) and lands LYC `LYC_WAIT_CGB` (1) dot late. Gambatte `window`
  207 -> 217 of 273 (the `late_wy_*_2` halves whose DMG and CGB answers differ; 4 gives 216, 6
  loses the `_1` halves) and `lycEnable` 109 -> 111 (1-3 agree; 4 gains 7 and loses the three
  `lcdoffset1` ones). With the DMA order, the CGB pass list goes 2,591 -> 2,603 (16 gained, the 4
  `irq_precedence` ones lost); pytest, Mooneye CGB from the real boot ROM (58/58) and AGE 8 hold.
* **A window after an object in double speed**: SameBoy's fetch log of `10spritesPrLine_wx1_m3stat_ds`
  puts its mode 3 about 4 dots past ours. When the window starts after an object has been fetched
  on the line, in double speed the pipeline now stalls `WIN_OBJ_STALL_DS` (4) dots (FITTED: 3 loses
  the gains, 5 loses a `_2` half). Gambatte `sprites` 346 -> 355 of 380 (`9pos8_wx*_m3stat_ds_1`,
  `1pos8_8pos9_wx08`), CGB pass list 2,603 -> 2,612, nothing lost. Open: the
  `10spritesPrLine_wx1-7_m3stat_ds_1` ROMs, whose window starts at x = 0 before any object; a
  stall on any line with objects gains them but loses `wx0`-`wx2` `_2`. SameBoy starts a window
  with WX 1-6 at position WX - 7 (during the first tile's discarded pixels), which the board
  folds into x = 0; that is the likely mechanism.
* **Tried and dropped (CGB)**: SameBoy's two-step STAT write (one enable kept for a T-cycle),
  modelled as a zero-length step, loses 9 in `lycEnable`/`miscmstatirq` and gains none. A
  CGB-only early HBlank interrupt (0 instead of 2) gains 15 in `halt`/`m0enable` but loses 12 in
  `m2int_m0irq`; splitting the STAT line's rise from the dispatch's early view moves the
  trade, so the `*_m0stat_scx3/4_2` pairs (DMG and CGB answers differ) stay open.
* **VRAM read lock on CGB at single speed**: the lock follows STAT's lagged mode (4 dots late) instead
  of locking the dot mode 3 starts. Gambatte `vram_m3/preread_2` (DMG and CGB answers differ) and
  `preread_lcdoffset1_1` pass, and `dma/late_gdma_pc_7ffe_1` with them: CGB 2,612 -> 2,615, nothing
  lost. In double speed the same rule loses `preread_ds_2`, so it stays at once there; the OAM
  read lock moved the same way loses 3 and is unchanged. Also tried: a CGB-only early OAM
  interrupt (2 or 0 instead of 4) loses over 40 in the STAT groups.
* **A halted CGB wakes later (2026-11-05)**: SameBoy's `GB_cpu_run` samples IF before a halted
  CGB's 4 T (a DMG's halfway), so `HALT_LATE_CGB` adds 2 dots to the HBlank and LY=LYC
  interrupts' wake on CGB. Gambatte `halt` +8, among them the `*_m0stat_scx3/4_2` pairs the
  early-HBlank probe could not settle, and `dma/hdma_start` +7. Applied to the line-start OAM
  interrupt too it fails Mooneye `intr_2_*` from the skip-boot state, so that one, already
  raised early, is left alone; timer wakes showed no evidence (`tima` passes either way). A
  longer wake in double speed (6) passes the `halt` ds pairs with a 2-dot STAT lag below but
  loses 12 double-speed `dma` ROMs, so it stays 2.
* **Mode 2 in STAT at double speed**: a line's mode 2 shows in STAT from the line's first dot
  instead of after `MODE_READ_LAG` (`M2_READ_LAG_DS` 0). `halt/m0i*_m0stat_scx2/3_ds_2` +4,
  `ly0/lycint152_lyc0flag_ds_4` and `oam_access/prewrite_ds_lcdoffset1_2` pass;
  `lycint_lycflag`/`lycint_m0stat` ds trade their `_1` for their other halves, since
  `lycint_lycflag_ds_1` reads at the same dot as the halt pairs and wants mode 0. A lag of 2
  scores one fewer over the ds groups, none (4) five fewer.
* **HBlank HDMA at the fetch**: an HBlank block now falls due `HDMA_HBLANK_LAG` dots into mode 0
  (4; 2 in double speed; SameBoy sets `hdma_on` 3 T after mode 0) and is checked when the
  opcode fetch completes, not when the instruction starts. Gambatte `dma` +30 over b96c9b1 with the
  halt change, nothing lost: every `hdma_start_*`, `hdma_cycles_*_2` and `gdma_cycles_*_2` (which
  had passed only from the real boot ROM). Either half alone trades.
* **CGB STAT writes and the line-start OAM interrupt**: the DMG's write glitch raises the OAM
  interrupt for a write that clears bit 5 in the last dots of a line; a CGB has no glitch and
  its source rises 2 dots before the line ends (SameBoy `mode_for_interrupt = 2` at
  `LINE_LENGTH - 2`), so a CGB write before then cancels the interrupt we raise early for the
  dispatch (on line 0, a write in its first dot). In double speed the source is 2 dots wide,
  not 4, except on line 0. Gambatte `m2enable` +7, `m1` +1; `lyc1_late_m2enable_lycdisable_ds_3`
  lost. SameBoy's CGB-E rule that the LY=LYC interrupt line holds while LY changes at a line's
  start was tried as a hold of 1, 2 or 4 dots and loses more than it gains in `lycEnable`.
* **WY needs the window enabled (2026-11-05)**: WY==LY only counts while LCDC.5 is set (SameBoy
  `wy_check`), at a line's start, at LCD on and on a WY write, and setting LCDC.5 runs the compare
  again (`WIN_EN_WAIT` 4 dots later on CGB, 2 in double speed; at once on DMG, where 0 scored
  best). Gambatte `window` CGB +6, DMG +2 (`late_enable_afterVblank_*`, `late_enable_ly0_ds_2`);
  `late_enable_afterVblank_lcdoffset1_1` lost. The `lcdoffset1` ROMs move the LCD half an M-cycle
  against the CPU with two speed switches, which the board does not model: the write lands at the
  same dot as in the plain `_2` ROM that wants the other answer, so one of each pair stays out of
  reach. Lining the compare up with the LCD's own 4-dot grid did not split them either. The
  picture PPU now takes the timing PPU's `wy_hit` every dot (one comparator); with its own
  line-start compare it never saw the LCDC.5 compare, and Mealybug `m2_win_en_toggle` went from
  pixel-exact to 9,030 pixels with the head change below.
* **Window head in single speed**: SameBoy's mode-0 entry (an instrumented `display.c`) has the
  window cost 6 dots at WX 0, 3 and 7; ours cost 5 at WX 0 and 2 at WX >= 3, and the m3stat reads
  want WX 0 a dot shorter and WX 3/7 at SCX 2 a dot longer. `WINDOW_HEAD` 4 -> 3 in single speed
  (double speed keeps 4: 3 there loses the `m2int_wx*_m3stat_ds_2` halves) gains the SCX 2 window
  ROMs: CGB +6 -2 (`late_disable_scx2_0/1` lost), DMG +7 -2 (`late_disable_scx2_0`,
  `m2int_wxA6_scx2_m3stat_3`). GBMicrotest `win*` unchanged; Mealybug `m3_window_timing` 47 -> 40,
  `m3_lcdc_win_map_change` 1,014 -> 374, `m3_lcdc_tile_sel_win_change` 1,584 -> 1,456.
  `WINDOW_EDGE_HEAD` 7 or 8 (WX < 7) only trades.
* **CGB LYC writes one M-cycle later**: at single speed several CGB ROMs print the DMG answer for a
  write 4 dots earlier (`ff45_enable_weirdpoint_2`, `late_ff45_enable_2`, `lyc153_late_ff45_*`,
  `lyc0_late_ff45_enable_2`), so `LYC_WAIT_CGB` is 4 (was 1). Over the whole CGB list +8 -4 (also
  `m0enable/lycdisable_ff45_2`, `_scx3_2`, `m2enable/lyc1_m2irq_late_lyc255_2`), losing the three
  `lycEnable` `lcdoffset1_1` halves and `m0enable/lycdisable_ff45_scx1_1`.
* **Double speed: a write cancels the early LY=LYC interrupt**: the interrupt raised
  `LYC_IRQ_EARLY` dots before the flag is withdrawn by a STAT write clearing bit 6 or a LYC write
  away from LY in the same M-cycle. Gambatte `lycEnable` `ff41_disable_ds_1`, `ff45_disable_ds_1`,
  `lyc_ff45_disable2_ds_1`, nothing lost. Tried and dropped: an early lead of 0-3 dots in double
  speed (it moves the interrupt that starts the test too) and counting the IF-read hide in dots
  (it only swaps an `lcdoffset1` pair).
* **Totals**: Gambatte CGB 2,670 -> 2,686, DMG 1,550 -> 1,557.
* **The speed switch moves the LCD against the CPU (2026-11-06)**: Gambatte's `lcdoffset1`,
  `lcd_offset` and `speedchange` ROMs switch speed with the LCD on, which leaves the CPU's M-cycles
  at a new phase to the dots; the board kept the old one, so one ROM of each `lcdoffset1` pair
  failed. Now the LCD runs `SWITCH_LCD_DS` 2 dots on its own at a switch to double speed and stands
  still `SWITCH_LCD_SS` 3 dots at a switch back (SameBoy's TODO: 2 PPU ticks single->double;
  Gambatte moves the LCD a cycle on double->single, which is -3 here with our halt one double-speed
  M-cycle longer); over `speedchange|lcd_offset|lcdoffset` -4/3, -2/2, 1/2 and -3/3 all score lower.
  A skew alone changed almost nothing, since every PPU interrupt was raised in the last dot of its
  window and the dispatch re-synced to it; so in single speed the PPU now runs `IRQ_LEAD` 1 dot of
  each M-cycle after the CPU's access, before the dispatch looks (reads and writes see the same dot
  as before). The HBlank and mode 2 interrupts raised in that dot keep their old dispatch cycle and
  IF timing (`irq_defer`, with a halted CPU's wake delay decided when they land): their dots are
  pinned by the SCX ROMs. Gambatte CGB 2,686 -> 2,719 (+43 -10: `speedchange` +25 -1,
  `lcdoffset1` +12 -3, `lcd_offset` +5 -6); DMG 1,557 unchanged. Open: the
  `oam_access`/`vram_m3` `lcdoffset1_2` halves and `lcd_offset` `_2` halves want line-start
  changes seen by reads 1-3 dots sooner, and double speed (a lead there loses 11 `ds_lcdoffset1`).
* **Line-start reads 1 dot sooner in single speed**: a line's mode 2 shows in STAT and locks OAM
  `M2_READ_LAG_SS` 3 dots into the line (was 4), and on CGB VRAM locks `VRAM_LOCK_SS` 3 dots into
  mode 3 (before STAT shows mode 3; the palette lock keeps STAT's timing, as moving STAT's mode 3
  instead loses `cgbpal_m3/*_lcdoffset1_1`). Aligned ROMs read only every 4th dot, so they cannot
  tell; with the speed switch's skew `oam_access/prewrite_lcdoffset1_2`,
  `vram_m3/preread_lcdoffset1_2`, `vram_m3/prewrite_lcdoffset1_2` and
  `speedchange2_ly44_m3_stat_4` pass: CGB 2,719 -> 2,723, nothing lost; DMG unchanged. 2 and 1
  score the same or lose one; moving line 153's LY change (8 -> 5-7) changes nothing.
* **LCD on in double speed**: line 0 starts `LCD_ON_DS` 2 dots further back (an even step: 1 or
  -1 breaks 43 `scx_during_m3` ROMs), which passes the `enable_display` frame0/frame1
  m0irq/m2irq/m2stat `_ds_1` halves, `ly0_m0irq_*_ds_1`, `ly0_late_cgbp*_ds_1` and the
  `speedchange2_*lcdoff*` ROMs, all of which SameBoy passes. The LY register keeps its place:
  after such an LCD-on, until the next speed switch, LY shows the next line `LY_LEAD_DS` 2 dots
  early (and line 153 reads 0 2 dots sooner); without that AGE `ly-cgbE` fails, its double-speed
  half reading LY at each line edge 0-4 M-cycles after the LCD-on, and the `frame0/1_ly_count_ds_2`
  halves with it. CGB 2,723 -> 2,741 (+20 -2: `ly0_oambusy_read_ds_2` and `ly0_late_vramr_ds_2`,
  lock reads against the LCD-on moment).
* **CGB: a STAT write can cancel the mode 1 interrupt**: a write clearing bit 4 in the M-cycle the
  mode 1 source rises (line 144's first dot) cancels that STAT interrupt, as one clearing bit 5
  does the OAM one: Gambatte `m1irq_disable_1`, `m1irq_disable_ds_1` (CGB 2,741 -> 2,743, nothing
  lost). The CGB VBlank delay stays 4: 0 passes two `lycint_vblank*` ROMs but fails Mooneye
  `vblank_stat_intr-C`; `MODE1_IRQ_DOT` and `VBLANK_IF_LATE` move nothing in `m1`.
* **CGB: the window can be undone just after it starts**: LCDC.5 cleared in the first 6 dots of a
  window start puts the background's fetcher state back and gives back 3 of the dots the start took
  (`WIN_UNDO_DOTS`, `WIN_UNDO_REFUND`, fitted), as Gambatte's `StartWindowDraw` falls back to
  plotting on CGB; DMG keeps the window. Gambatte `window/late_disable_*` CGB halves: CGB 2,743 ->
  2,757 (+16 -2: `late_disable_late_scx00_wx10_ds_2`, `late_disable_late_scx03_wx12_2`). The sweep
  over refund 1-6 and 3-12 dots peaks at 3 and 6; a refund of 4 trades the two back for four others.
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
* **`LYC_IRQ_EARLY` tried and rejected**: 3 (or 2) gains 4 of 147 in Gambatte `lycEnable` but, over
  the whole CGB list, loses 319 and gains 121; on DMG it breaks GBMicrotest `int_lyc_*`. Stays 4.
  Lesson: judge a timing constant on the whole list, not on the group it was swept on.
* **`LINE0_START_DOT` re-swept on the whole CGB list** (2026-10-12): 2 gives 2,430, 6 gives 2,438,
  the fitted 4 gives 2,463 (`enable_display` 88 of 116 at 4, 81 at 2 and 6). 4 stays.
* **Mealybug CGB D, 18 of 21 differ** by 10 to 8,300 pixels, mostly the mode-3 register-change
  tests; the DMG board's fits are used unchanged and CGB has its own latencies.
* **cgb-acid-hell**: 2 pixels.
* **Not done**: SameBoy columns for the CGB runs, the SGB and AGB rows, DMG0/CGB0 revisions of
  the CGB, the real-boot and skip-boot equivalence check for CGB (the DMG's was identical), and
  the CGB speed-switch's PPU "odd mode".
