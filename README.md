# gameboy-python

A readable, pure-Python emulator of **Nintendo's Game Boy**, to be built as a
board on [sm83-python](../sm83-python): sm83-python owns the instruction set;
this repository will own everything around it: the system counter and timer,
the picture processor dot by dot, the sound unit, OAM DMA, the serial port
and joypad, the cartridge connector and the MBCs behind it, and the clock
that ties them together.

**Status (2026-11-11):** DMG and CGB boards with sound, five MBC families and a play window. Gambatte's hardware verdicts: 1,695 of 1,784 DMG-08, 2,821 of 3,221 CGB-04c; all 24 of Mealybug Tearoom's DMG pictures and its 20 CPU CGB D ones match hardware (a DMG cartridge's picture is drawn by `dmg_pixels.py`, translated from docboy); the Emulator Shootout's list: 255 of 258; Mooneye, SameSuite, dmg-acid2, cgb-acid2 and cgb-acid-hell pass. Results and history in [docs/validation.md](docs/validation.md). Run `python -m gameboy_python play ROM.gb`. Earlier groundwork: The documents in
[`docs/`](docs/README.md) gather what the build needs, every fact with its
source and tier: the hardware, the timing, the cartridges, the quirks and
contradictions, the oracles (with the die-level model running here), a
verified MAME recipe, and the brief for the session that builds it
([docs/handoff-brief.md](docs/handoff-brief.md)).

## Scope

| Machine | Phase |
| --- | --- |
| DMG-01 with DMG-CPU B: the reference model | 1 |
| DMG-CPU 0 / A / C: as `revision` fields on the same board | 1 |
| Game Boy Color (CPU CGB 0–E), double speed | 2 (rows in the machine table from the start) |
| Game Boy Pocket / Light | later, as machine data |
| Super Game Boy, SGB2 | on a future SNES board, which embeds this one |

The APU is its own core, [gb-apu-python](../gb-apu-python), pinned by revision:
it was extracted with its history on 2026-11-06, when a second consumer (the GBA
board) needed it.
MBCs live here behind a signal-level connector ([docs/cartridge.md](docs/cartridge.md));
MBC1, MBC5, ROM-only, MBC2 and MBC3 run 98.9 % of the 3,064 licensed No-Intro
dumps.

## What is fetched

Nothing third-party is committed. `scripts/fetch_references.py` rebuilds
`reference/` and `tests/test_roms/` from `scripts/pinned_files.json` (the c-sp
test-ROM bundle v7.0, Gekkio's prebuilt Mooneye suite, GBCTR's PDF, RGBDS
1.0.4, pinned by SHA-256) and `scripts/pinned_repos.json` (35 repositories at
full commit SHAs: Pan Docs, GBCTR, the test suites, SameBoy, dmg-sim, GateBoy,
the die schematics, Icarus Verilog):

```sh
python scripts/fetch_references.py            # everything missing
python scripts/fetch_references.py --verify   # check what is present
```

It needs `git` and `curl`. Boot ROMs are never fetched or committed: the
harness uses the real ones by default, read in place from a configurable
path (`--boot`, `GAMEBOY_BOOT_ROM`, `GAMEBOY_NOINTRO_DIR`; local default and
hashes in [docs/start-here.md](docs/start-here.md) "Boot ROMs").

## Play

    pip install -e '.[frontend]'          # pygame-ce, on PyPy
    python -m gameboy_python play "Tetris (World) (Rev 1).zip"

A window with picture, sound, keyboard and gamepad (`src/gameboy_python/frontend.py`): a Game
Boy Color for a cartridge that asks for one, else the DMG, booted from your boot ROM when one is
found. Battery saves (and an MBC3's clock) are kept in `NAME.sav` beside the image. This is the
reference board, correct before fast: it runs below real time, shows every frame and plays the
sound at pitch with gaps.

## Scripts

| Script | What |
| --- | --- |
| `scripts/fetch_references.py` | the pinned references, tools and test ROMs |
| `scripts/sameboy_run.py` | a locally built SameBoy driven headless through ctypes, reading the Mooneye, blargg (serial and $A000) and GBMicrotest result protocols ([docs/validation.md](docs/validation.md)) |
| `scripts/mame_trace.py` | MAME 0.285 per-instruction SM83 trace, I/O log and test result ([docs/mame-oracle.md](docs/mame-oracle.md)); needs your boot ROMs |
| `scripts/compat_sweep.py` | the licensed No-Intro dumps against SameBoy, picture for picture at three frames: `--tier titles` (one dump per title), `all`, or `failures` (`tests/compat_differs.txt`, the loop between edits); `--model cgb` runs the Color games on the CGB against SameBoy's CGB E; results are kept per ROM and a rerun resumes |
| `scripts/smoke.py` | the curated gate between edits: the classics that must stay exact and the Gambatte ROMs that have flipped |
| `scripts/nursery.py` | gives PyPy a 1 MB nursery before a runner fans out over the cores (about five times the sweep throughput on a large shared cache) |
| `scripts/count_mbcs.py` | cartridge-type coverage over the local No-Intro sets, read in place, with the MBC1-multicart and MMM01 heuristics ([docs/cartridge.md](docs/cartridge.md)) |

## Licence

MIT (see `LICENSE`), for what is in this repository. The fetched material keeps
its own terms, recorded per entry in the pin lists.
