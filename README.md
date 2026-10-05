# gameboy-python

A readable, pure-Python emulator of **Nintendo's Game Boy**, to be built as a
board on [sm83-python](../sm83-python): sm83-python owns the instruction set;
this repository will own everything around it: the system counter and timer,
the picture processor dot by dot, the sound unit, OAM DMA, the serial port
and joypad, the cartridge connector and the MBCs behind it, and the clock
that ties them together.

**Status (2026-10-05): groundwork only, no emulator code.** The documents in
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

The APU lives here, behind a pin-shaped boundary, until a second consumer (a
GBA board) needs it; then it is extracted with its history, never copied.
MBCs live here behind a signal-level connector ([docs/cartridge.md](docs/cartridge.md));
MBC1, MBC5, ROM-only, MBC2 and MBC3 run 98.9 % of the 3,064 licensed No-Intro
dumps.

## What is fetched

Nothing third-party is committed. `scripts/fetch_references.py` rebuilds
`reference/` and `tests/test_roms/` from `scripts/pinned_files.json` (the c-sp
test-ROM bundle v7.0, Gekkio's prebuilt Mooneye suite, GBCTR's PDF, RGBDS
1.0.4, pinned by SHA-256) and `scripts/pinned_repos.json` (34 repositories at
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

## Scripts

| Script | What |
| --- | --- |
| `scripts/fetch_references.py` | the pinned references, tools and test ROMs |
| `scripts/sameboy_run.py` | a locally built SameBoy driven headless through ctypes, reading the Mooneye, blargg (serial and $A000) and GBMicrotest result protocols ([docs/validation.md](docs/validation.md)) |
| `scripts/mame_trace.py` | MAME 0.285 per-instruction SM83 trace, I/O log and test result ([docs/mame-oracle.md](docs/mame-oracle.md)); needs your boot ROMs |
| `scripts/count_mbcs.py` | cartridge-type coverage over the local No-Intro sets, read in place, with the MBC1-multicart and MMM01 heuristics ([docs/cartridge.md](docs/cartridge.md)) |

## Licence

MIT (see `LICENSE`), for what is in this repository. The fetched material keeps
its own terms, recorded per entry in the pin lists.
