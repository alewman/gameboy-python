# Handoff: build `gameboy-python`, the Game Boy board

## Context you are inheriting

The family's shape is **chips are cores, boards compose cores**. Each core is
certified on its own against its oracles and pinned by the boards that use
it; each board is validated against hardware-tier test programs, with MAME
and other emulators as detectors only. `sms-python` (Master System, on
z80-python), `megadrive-python` and `famicom-python` (NES, on 6502-python;
docs-only like this repository, `f93efa0`) are the boards to model this one
on. `sm83-python` (`/data/emu/sm83-python`) is the CPU core this board embeds;
it is being built from its own brief in parallel, and its bus contract was
agreed with this board in mind.

Read, in order, before writing code:

1. `README.md`: scope, what is fetched.
2. `docs/start-here.md`: the machines as data, clocks, memory map, I/O, PPU
   model and output format, APU, boot ROMs, the module shape.
3. `docs/timing.md`: the M-cycle callback design, the system counter, IF
   timing, the PPU dot schedule, OAM DMA, the OAM bug, CGB double speed.
4. `docs/cartridge.md`: the connector protocol, the header, the measured MBC
   coverage, per-MBC judges.
5. `docs/undocumented-behavior.md`: quirks, revisions, **contradictions
   C1–C10**, open items.
6. `docs/validation.md`: every oracle with its tier and pin; the result
   protocols; the die models and how to run dmg-sim; SameBoy and MAME as
   measured detectors.
7. `docs/mame-oracle.md`: the verified MAME 0.285 recipe and its traps.
8. sm83-python's `docs/start-here.md` ("The bus as the SoC sees it",
   "Interrupts", "HALT", "STOP") and `docs/handoff-brief.md` ("The bus
   contract"): the contract you embed.
9. sms-python's and famicom-python's board conventions (machines as data,
   `take_samples`, `frontend.py`, the MAME trace scripts).

Then `python scripts/fetch_references.py` (or `--verify`) to rebuild
`reference/` and `tests/test_roms/`, and the two local builds the brief
relies on (validation.md): SameBoy (`libsameboy.so`, seconds) and dmg-sim
(Icarus Verilog from source, under a minute).

## Decisions already made (Aubrey, 2026-10-05)

- **Two repositories**: the CPU is `sm83-python` (SM83 is the CPU core;
  LR35902 / DMG-CPU is the whole SoC); this board is `gameboy-python`.
  Local git until sm83-python passes its rung 3, then private GitHub
  repositories (Aubrey, 2026-10-05).
- **DMG first.** Reference model **DMG-01 with DMG-CPU B** (start-here.md
  "Why DMG-CPU B"; C1 is the caveat). CGB with double speed is a machine-table
  row from day one and a later phase; MGB/MGL rows later; **SGB proper is
  deferred to a future SNES board**, which would embed this board.
- **The APU stays in this board**, behind a pin-shaped interface (registers
  and the DIV-APU tick in, per-T channel levels or samples out) with a test
  that forbids `apu/` from importing the rest of the board. Its judges are
  ROMs that need the whole board, and its frame sequencer is clocked by the
  timer's counter, so it is not a core today. It is **extracted with its
  history when a second consumer appears** (a GBA board); it is **never
  copied** into another repository (the family rule since the PSG diverged).
- **MBCs live in this repository** behind the connector protocol, with an
  import-boundary test (cartridge.md).
- **The PPU is dot-accurate**: OAM scan, fetcher, FIFOs, mode-3 length from
  SCX, window and objects; no scanline renderer.
- **Boot ROMs are bring-your-own, and the real one is the default.** Order:
  a configured path (`--boot` / `GAMEBOY_BOOT_ROM`, raw or No-Intro `.zip`),
  then the documented local default (Aubrey's No-Intro `[BIOS]` zips, read in
  place and checked by SHA-256: table in start-here.md "Boot ROMs"), then
  dmg-sim's `quickboot.bin`, then SameBoy's open ROM, labelled, because it
  fails three Mooneye boot-state tests (C7). Never copy a boot ROM into the
  repository. `scripts/sameboy_run.py` implements this order.
- **Output**: frames as data (DMG: 160×144 2-bit shades plus a "blank" state;
  CGB: 15-bit RGB), audio as `take_samples()` floats; pygame-ce frontend
  optional; the board runs headless.
- **Python floor 3.11** (the newest PyPy supports), CPython and PyPy;
  `requires-python = ">=3.11"`, ruff `target-version = "py311"`.
- **Reference boards are correct, not fast.** Speed is a later `-fast`
  project's job.

## What the board needs from sm83-python

Against sm83-python's agreed contract (`SM83(read_byte, write_byte, idle,
stop=…)`, its handoff-brief "The bus contract"):

1. **One callback per M-cycle, in chip order, including internal cycles**,
   each with the address the CPU drives (the IDU's register, or $0000). The
   board advances every unit inside these callbacks and never adds `step()`'s
   return value on top.
2. **`cpu.idu`** (+1, −1, 0) readable inside the callback: the OAM bug's
   corruption pattern differs for read, write, IDU-only and read-plus-
   increment (timing.md "The OAM corruption bug").
3. **IE and IF live in the core** as attributes (`ie`, `if_`; decided by
   Aubrey 2026-10-05). The board raises an IF bit through a core method
   callable from inside a bus callback (`request_interrupt(bit)` here;
   **sm83-python's handoff-brief is authoritative for the name**), and the
   core services CPU accesses to $FF0F and $FFFF itself. The core samples
   them at its own exact cycles, including the late vector choice of the
   IE-push cancellation; the board owns *when* each IF bit rises (timing.md
   "Interrupts").
4. **`halted`, `stopped`, `locked` readable**, and a halted or locked CPU's
   `step()` making exactly one `idle(PC)` and returning 1, so time passes
   M-cycle by M-cycle and the board finds the wake-up cycle.
5. **The STOP hook**: the core reports `stop(pending)` and the board decides:
   DMG low-power stop with DIV reset, behave as HALT, 1-byte NOP, or (CGB)
   speed switch, then runs the 2050-M pause itself.
6. **Double speed is the board's**: the core does not change; the board
   advances 2 T instead of 4 per callback.
7. **`capture_state()` / `restore_state()`** and the disassembler and
   `DebugSession`, as the family cores have, so `state.py` and the debugger
   reuse them.

**Rungs this board depends on** (sm83-python `docs/validation.md` "The
plan"): milestone 1 here needs core rungs 0–3 passed (bus schedule,
SingleStepTests, `cpu_instrs`, Mooneye board-free subset); milestone 3 (the
OAM bug) leans on rung 5 (internal-cycle addresses settled from the die).
This board's milestones 1–3 *are* the core's rung 6.

**The family rule**: a board that finds a corner of its core raises it **on
the core** (an issue or a PR from a branch off `origin/main`, with a failing
core-level test and a seeded fault shown to fail it; the user merges),
never as a workaround here. Pin a git revision of sm83-python in
`pyproject.toml`, never a local path.

## Your task

Build `src/gameboy_python/`. The module shape in start-here.md is a
suggestion; the requirements are:

- **Machines as data**: DMG-01 (DMG-CPU B), with `revision` (0/A/B/C), and the
  rows MGB, SGB, SGB2, CGB (0–E), AGB present as data marked "not certified".
  Every quirk field carries a comment naming its source and tier.
- **One T-cycle timeline**, advanced inside the core's callbacks; the system
  counter is the single source of DIV, the timer, DIV-APU and the serial clock.
- **The cartridge connector protocol** of cartridge.md, settled in milestone
  1, changed only with a reason recorded there; the import boundary enforced
  by a test. Identification: header first, MAME's `hash/gameboy.xml` /
  `gbcolor.xml` `slot` feature as the secondary source (read at runtime from
  `/usr/share/games/mame/hash/`), the MBC1M and MMM01 heuristics of
  `scripts/count_mbcs.py`.
- **Boot**: a real boot ROM path, a named open replacement, or skip-boot with
  the post-boot state of Pan Docs `Power_Up_Sequence.md` and the counter phase
  from Mooneye `boot_div-dmgABCmgb`.
- **A test-ROM harness** that reads every protocol in validation.md: Mooneye
  registers at `LD B,B`; blargg serial and $A000; GBMicrotest $FF82;
  Gambatte's `_out<hex>` screen digits (testrunner.cpp's pattern table) and
  `_outaudio0/1`; picture comparison with the suites' exact shades.
- **Tooling at the family bar**: `state.py`, a debugger reusing sm83-python's
  `DebugSession` with board watchpoints (I/O registers, VRAM, OAM, MBC
  registers), a JSONL trace in sm83-python's schema plus bus events with
  T-cycle times, `py.typed`, `python -m gameboy_python ROM --frames N --png
  out.png --wav out.wav`.

### Milestones, each with its acceptance test, in oracle-tier order

Numbers in brackets are what SameBoy (the reference detector) scored here on
2026-10-05; a board result below SameBoy's must be explained case by case.

1. **The CPU on the board: bus, timer, interrupts, serial, OAM DMA, ROM-only
   and MBC1, boot.** Memory map and echo, unused bits, IF/IE, the system
   counter with every timer quirk, serial with nothing attached, OAM DMA with
   its start delay and source decoding, boot ROM mapping, skip-boot. The PPU
   may be a **timing skeleton** (LY, modes with a fixed 172-dot mode 3, STAT
   line, VBlank IRQ; no pixels). **Acceptance**: blargg `cpu_instrs` (11/11,
   serial), `instr_timing`, `mem_timing`, `mem_timing-2` ($A000); Mooneye
   acceptance minus `ppu/*`: every test whose header verifies it on DMG ABC
   passes, booted with the real DMG boot ROM *and* with `quickboot.bin`
   [SameBoy: all] (a test that turns out to need exact mode-3 timing moves to
   milestone 2, with the reason written here); the MAME trace of `cpu_instrs` matches the board's per-
   instruction registers from $0100 for the first 100,000 instructions (MAME
   T ÷ 4 = M). Instruction counts and wall time recorded under PyPy.
   Needs core rungs 0–3.
2. **The PPU, dot by dot.** OAM scan, fetcher, both FIFOs, SCX fine scroll,
   window (WY latch, WX compare, the WX=0/166 cases), object penalties, VRAM
   and OAM locking edges, STAT quirks 2–5 (undocumented-behavior.md), LCD
   on/off. **Acceptance**: dmg-acid2 pixel-exact (DMG picture); Mooneye
   `ppu/*` (12, those verified on DMG); Mealybug DMG pictures, using the
   `DMG-CPU B` pair for the two tests where B differs (C2) [SameBoy: not run
   here; run it first and record]; blargg `halt_bug` (screen); GBMicrotest
   PPU, timer and interrupt families at least SameBoy's pass set
   [476/513], every miss run on dmg-sim before it is called a board bug.
3. **The OAM bug and the remaining CPU/SoC corners.** IDU addresses reaching
   OAM in mode 2, the three corruption patterns, DMA bus conflicts.
   **Acceptance**: blargg `oam_bug` 1–8 [SameBoy: pass]; Mooneye
   `oam_dma/sources-GS`, `bits/mem_oam`; Gambatte `oamdma/*` and `oam_access/*`
   `dmg08` results. Leans on core rung 5.
4. **The APU, behind its boundary.** Four channels, DACs, mixer, NR52 power,
   frame sequencer on DIV-APU, every DMG quirk in `Audio_details.md`
   "Obscure Behavior"; `take_samples()` with a labelled analogue fit.
   **Acceptance**: blargg `dmg_sound` 01–12 [SameBoy: 12/12; dmg-sim 11/12,
   not 10]; SameSuite `div_write_trigger`, `div_write_trigger_10` (the two
   that pass on DMG-B); Gambatte's `dmg08` `_outaudio` tests; the import-
   boundary test.
5. **Cartridges.** MBC1 (+multicart), MBC2, MBC3 (+RTC on wall time), MBC5
   (+rumble), battery saves through the frontend. **Acceptance**: Mooneye
   `emulator-only/mbc1/*` (13), `mbc2/*` (7), `mbc5/*` (8); rtc3test as a
   detector; a **compatibility sweep** over the licensed No-Intro GB set
   (phase-1 boards: 98.9 % of 3,064 dumps): each boots and runs N frames
   without an exception, frame hash compared with SameBoy at fixed frames;
   every difference triaged, as sms-python's sweep was.
6. **The full hardware-captured sweep.** Gambatte's 1,747 `dmg08` tests and
   all 513 GBMicrotest ROMs, results tabulated with SameBoy's beside them;
   joypad (Gambatte `jpadirq`), serial timing, the DMG revision fields (DMG0
   boot ROM and `stat_irq_blocking`). **Acceptance**: every failure either
   fixed, shown to be a C1 B/C difference on dmg-sim, or listed as an open
   item with its evidence.
7. **Phase 2, CGB.** Double speed and the speed switch, HDMA/GDMA, VRAM/WRAM
   banks, CGB palettes and priority, KEY0 compatibility mode, the CGB PPU and
   APU differences. **Acceptance**: cgb-acid2; Mooneye C-group and `misc/`;
   Gambatte `cgb04c` (C3); SameSuite (CGB E); Mealybug CPU CGB C/D pictures;
   blargg `cgb_sound`; cgb-acid-hell; AGE (CGB).

## Constraints

- No ROMs, boot ROMs, DATs or fetched references are committed; the
  `.gitignore` already excludes `reference/`, `tests/test_roms/`,
  `tests/mame_traces/`, `*.sav`, `coverage.json`.
- No `rm -rf`, `sed -i`, `ln -sfn` one-liners; edit with the editor tool.
- Commit in logical steps with the family's attribution line; do not push or
  create the GitHub repository before sm83-python passes rung 3, and then
  only as a private repository with the user's go-ahead.
- Every number in a document says where it came from and when it was measured.

## Decisions made by Aubrey (2026-10-05)

1. **Reference revision DMG-CPU B**, with dmg-sim as tie-breaker against the
   DMG-CPU C (blob) hardware results (C1).
2. **The harness boots with the real boot ROM**, else `quickboot.bin`;
   SameBoy's open ROM is no longer a default, only a labelled last fallback
   (C7).
3. **CGB reference revision: CPU CGB E.**
4. **No GateBoy test driver.** Its `GateBoyTests` builds (30 s) but ships with
   every suite disabled; dmg-sim is the die judge (its CPU is from the die,
   GateBoy's is a guess). GateBoy stays pinned as reading material only.

5. **IE and IF are core attributes**; the board raises IF bits through the
   core's method from inside bus callbacks; the core services $FF0F/$FFFF
   ("What the board needs from sm83-python" 3).
6. **Publishing**: local until sm83-python passes rung 3, then private GitHub.
