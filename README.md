# gameboy-python

A readable, pure-Python emulator of Nintendo's **Game Boy** and **Game Boy Color**, written as
a reference: every behaviour names its source, and correctness comes before speed. It is a
board built on two cores: [sm83-python](https://github.com/alewman/sm83-python) runs the
instruction set and [gb-apu-python](https://github.com/alewman/gb-apu-python) makes the sound.
This repository owns everything else: the system counter and timer, the picture processor dot
by dot, OAM and HDMA transfers, the serial port and joypad, the cartridge connector and the MBCs
behind it, and the clock that ties them together.

## Status (2026-11-12)

Judged against hardware captures, die models and other emulators
([docs/validation.md](docs/validation.md) has every result, its oracle and its history):

| Judge | Result |
| --- | --- |
| Gambatte's hardware verdicts, DMG-08 | 1,695 of 1,784 |
| Gambatte's hardware verdicts, CGB-04c (on the `cgb-c` machine) | 2,892 of 3,221 |
| Mealybug Tearoom, DMG pictures | 24 of 24 |
| Mealybug Tearoom, CPU CGB D pictures (`cgb`) | 20 of 21 |
| Mealybug Tearoom, CPU CGB C pictures (`cgb-c`) | 24 of 27 |
| Mooneye, blargg, SameSuite, dmg-acid2, cgb-acid2, cgb-acid-hell | pass |
| [GB Emulator Shootout](https://github.com/gbdev/GBEmulatorShootout) list | 257 of 258 |
| Licensed No-Intro dumps, picture for picture against SameBoy | most identical; the differences are listed and triaged in `tests/compat_differs*.txt` |

The picture is drawn by `pixels.py`, a translation of [docboy](https://github.com/Docheinstein/docboy)'s
pixel pipeline (MIT; notice in the module). It runs below real time on PyPy: speed is the job
of the Rust boards built from this one.

## Machines

`machines.py` holds one row per model and revision, each quirk with its source: DMG-CPU 0, A,
B (the reference) and C; MGB; SGB and SGB2 (the board exposes the line and joypad taps a Super
Game Boy needs; the family's SNES board embeds it); CPU CGB E (`cgb`, the reference Color revision) and
CPU CGB C (`cgb-c`, the revision Gambatte's captures match). Cartridges: ROM-only, MBC1 and its
multicarts, MBC2, MBC3 with the real-time clock, MBC30, MBC5 (with rumble) and MMM01, which
together cover 98.9 % of the licensed No-Intro dumps ([docs/cartridge.md](docs/cartridge.md)).

## Install and play

PyPy 3.11 is the intended interpreter; CPython works, more slowly.

    pip install -e '.[frontend]'          # pygame-ce, which ships PyPy wheels
    python -m gameboy_python play "Tetris (World) (Rev 1).zip"

A window with picture, sound, keyboard and gamepad (`frontend.py`): a Game Boy Color for a
cartridge that asks for one, else the DMG. Battery saves (and an MBC3's clock) are kept in
`NAME.sav` beside the image. Without a window:

    python -m gameboy_python rom.gb --frames 60          # run, print the serial text
    python -m gameboy_python rom.gb --protocol mooneye   # run to LD B,B, report pass/fail

Boot ROMs are bring-your-own and never committed. The board boots from the real one when it
finds it (`--boot`, `GAMEBOY_BOOT_ROM`, or a No-Intro `[BIOS]` directory in
`GAMEBOY_NOINTRO_DIR`; hashes in [docs/start-here.md](docs/start-here.md) "Boot ROMs"), and
otherwise starts from the state the boot ROM leaves.

## References and tests

Nothing third-party is committed. `scripts/fetch_references.py` rebuilds `reference/` and
`tests/test_roms/` from `scripts/pinned_files.json` (the c-sp test-ROM bundle, Gekkio's prebuilt
Mooneye suite, GBCTR, RGBDS, pinned by SHA-256) and `scripts/pinned_repos.json` (repositories at
full commit SHAs: Pan Docs, GBCTR, the test suites, SameBoy, docboy, dmg-sim, GateBoy, the die
schematics, Icarus Verilog). It needs `git` and `curl`.

    python scripts/fetch_references.py            # everything missing
    python scripts/fetch_references.py --verify   # check what is present
    python -m pytest -q                           # the suites, against the committed pass lists

| Script | What |
| --- | --- |
| `scripts/smoke.py` | the quick gate between edits: classics that must stay exact and Gambatte ROMs that have flipped |
| `scripts/compat_sweep.py` | the licensed No-Intro dumps against a locally built SameBoy, picture for picture; `--tier titles`, `all` or `failures`; `--model cgb` for the Color games |
| `scripts/gambatte_dmg08.py` | Gambatte's hardware verdicts; `--cgb --machine cgb-c` for the Color list |
| `scripts/shootout.py` | the Emulator Shootout's list, scored the way the leaderboard scores it |
| `scripts/sameboy_run.py` | SameBoy driven headless through ctypes, reading the Mooneye, blargg and GBMicrotest result protocols |
| `scripts/mame_trace.py` | MAME 0.285 per-instruction trace and I/O log ([docs/mame-oracle.md](docs/mame-oracle.md)) |
| `scripts/count_mbcs.py` | cartridge-type coverage over a local No-Intro set |
| `scripts/nursery.py` | gives PyPy a 1 MB nursery before a runner fans out over the cores (about five times the sweep throughput) |

The documents in [docs/](docs/README.md) hold the hardware facts with their sources and tiers,
the timing, the cartridges, the quirks and contradictions, and the oracles.

## Licence

MIT (see `LICENSE`) for what is in this repository; `pixels.py` keeps docboy's MIT notice. The
fetched material keeps its own terms, recorded per entry in the pin lists.
