# The cartridge: connector, header, MBCs, coverage

## Why the MBCs live in this repository

Same decision as famicom-python, for the same reasons: a mapper is a few
dozen lines that only make sense against this board's bus; no second
consumer exists (a GBA board would embed this board whole for GB mode, so it
would reuse `cartridge/` through the board, not copy it); and keeping them
here lets one test enforce the boundary. `gameboy_python/cartridge/` imports
nothing from the rest of the board, and a test fails if it ever does
([handoff-brief.md](handoff-brief.md)).

## The connector

The 32-pin cartridge edge carries (`pandocs/External_Connectors.md`; GBCTR's
`appendix/pinouts.typ` has the SoC and MBC chip pinouts, not the edge): VCC, PHI (the CPU clock, 1 MiHz),
/WR, /RD, /CS (RAM select: low for $A000–$FDFF), A0–A15, D0–D7, /RES, VIN
(audio *into* the console's mixer), GND. What it means for the protocol:

- **The cartridge sees the external bus**, which also carries WRAM: every
  CPU or OAM-DMA access to $0000–$7FFF (A15 low) and $A000–$FDFF (/CS low)
  appears on it, boot-ROM accesses do not (`gb-ctr/appendix/external-bus.typ`
  "a)" and "b)"). A cartridge that decodes only A13–A15 and /CS cannot tell a
  WRAM write at $C000 from an SRAM write at $A000 except by A14/A13, which is
  why sloppy flash carts misbehave on DMA from WRAM (`dma.typ` warning).
- **PHI** is the only clock the cartridge gets; the MBC3 RTC, HuC3 and TAMA5
  have their own 32.768 kHz crystals, so they need *wall time*, which on an
  emulated board is the board's T-cycle count converted at 4.194304 MHz
  (plus an optional host-clock mode for real play).
- **VIN** is an audio input (NR50 bits 3 and 7 route it). No licensed
  cartridge in the census below is known to drive it; keep the pin in the
  protocol as "always 0" until one does.
- **/RES** lets a cartridge reset the console (unused by licensed MBCs) and the
  console reset clears MBC state on some chips: model the MBC's power-on state,
  not a reset input, until a test says otherwise.

### Protocol (settled in milestone 1, 2026-10-07: as proposed, implemented in `cartridge/__init__.py`; change only with a reason here)

```python
class Cartridge(Protocol):
    def read(self, address: int, t: int) -> int | None: ...   # None = open bus
    def write(self, address: int, value: int, t: int) -> None: ...
    def tick_to(self, t: int) -> None: ...      # RTC and other clocked parts catch up lazily
    def vin(self, t: int) -> int: ...           # audio in; 0 for every MBC here
    def save_ram(self) -> bytes | None: ...     # battery-backed RAM (+ RTC) to persist
    # optional, by capability: rumble(), set_tilt(), camera_frame()
```

`address` is the full 16-bit external-bus address; `t` the board's T-cycle
count when the access lands. The board calls `read`/`write` for **every**
external-bus access, including WRAM-range ones, because that is what the pins
show; the cartridge ignores what it does not decode. famicom-python's
`cartridge.md` has the longer argument for putting every bus event on the
connector with its time; the Game Boy needs less of it (no PPU bus on the
connector), so this protocol is that one minus the PPU side.

## The header ($0100–$014F)

`pandocs/The_Cartridge_Header.md`: entry point $0100; logo $0104–$0133 (the
DMG boot ROM locks up if it differs; the CGB checks only the first half);
title; CGB flag $0143 ($80 enhanced, $C0 only); SGB flag $0146 ($03);
**type $0147**; ROM size $0148 (32 KiB << n); RAM size $0149; header checksum
$014D (checked by the boot ROM); global checksum (never checked).

## Measured coverage (local No-Intro sets, 2026-10-05)

`scripts/count_mbcs.py` reads the header of every dump in
`/data/emu/source/myrient.erista.me/files/No-Intro/Nintendo - Game Boy*`
(read in place, never extracted or committed) and applies the two
multicart heuristics GBCTR and Pan Docs give. **3,064 licensed dumps** (GB
and GBC main sets; not Aftermarket, Private, Unl, Pirate, Proto, Beta,
Sample, Demo, Program):

| Board | Dumps | % | Cumulative | Phase |
| --- | --- | --- | --- | --- |
| MBC1 | 1,404 | 45.8 | 45.8 | 1 |
| MBC5 (12 + 16 with rumble) | 1,385 | 45.2 | 91.0 | 1 (DMG-compatible titles) / 2 |
| ROM only | 92 | 3.0 | 94.0 | 1 |
| MBC2 | 91 | 3.0 | 97.0 | 1 |
| MBC3 (47 with RTC) | 58 | 1.9 | 98.9 | 1 (RTC: 3) |
| HuC1 | 9 | 0.3 | 99.2 | later |
| MBC1M (multicart wiring, header says MBC1) | 8 | 0.3 | 99.4 | 3 |
| HuC3 | 7 | 0.2 | 99.7 | later |
| Pocket Camera | 3 | 0.1 | 99.8 | later |
| MBC7 (tilt) | 3 | 0.1 | 99.9 | later |
| MMM01 (menu header in the last 32 KiB) | 2 | 0.1 | 99.9 | later |
| TAMA5, MBC6 | 1 each | | 100.0 | later |

Header $0143 over the same set: 1,636 DMG-only, 514 CGB-enhanced, 914
CGB-only; 689 carry the SGB flag. So **the five boards of phase 1 run 98.9 %
of licensed cartridges**, and DMG mode alone reaches every dump that is not
CGB-only (2,150 of 3,064).

Heuristic results agree with MAME's software list where they overlap: MAME
`hash/gameboy.xml` marks 6 `rom_mmm01` entries (we find the two licensed ones,
*Momotarou Collection 2* and *Taito Variety Pack*), and the 8 MBC1M titles
are the known ones (*Bomberman Collection*, *Genjin Collection*, *Momotarou
Collection*, *Mortal Kombat & Mortal Kombat II* ×2, *Super Chinese Land
1-2-3'*, *Bomberman Selection*, and the unlicensed-looking *Mani 4 in 1*
that No-Intro files as licensed). A first, looser MMM01 test (type byte in
the last bank only) produced 30 false positives (*Balloon Kid*, *Operation C*
…): the logo check is required.

Not detectable from the header at all: **MBC30** (the 64 KiB-RAM MBC3 of the
Japanese *Pocket Monsters Crystal*, `pandocs/MBC3.md`, `gb-ctr/chapter/cartridges/mbc30.typ`)
and the Japanese mobile-adapter wiring. Identification needs a table: MAME's
`hash/gameboy.xml` / `gbcolor.xml` `slot` feature (read at runtime from
`/usr/share/games/mame/hash/`, never committed) is the secondary source, with
the override order "explicit user choice > MAME slot > header heuristics".
MAME also lists unlicensed boards we do not count (`rom_sachen1/2`,
`rom_sintax`, `rom_licheng`, `rom_rocket`, `rom_wisdom`, …).

## Per-MBC table and judges

| MBC | Registers (GBCTR / Pan Docs) | Judges | Tier |
| --- | --- | --- | --- |
| ROM only (+RAM) | none | any test ROM | — |
| MBC1 | RAMG $0000, BANK1 $2000 (5 bits, 0→1), BANK2 $4000 (2 bits), MODE $6000 | Mooneye `emulator-only/mbc1/*` (13): "verified using a flash cartridge with a genuine MBC1B1 chip" | hardware-corrected |
| MBC1M | BANK1 bit 4 unconnected; BANK2 = game number | Mooneye `mbc1/multicart_rom_8Mb` (same flash cart) | hardware-corrected |
| MBC2 | one register file selected by A8; built-in 512 × 4-bit RAM, upper nibble undefined | Mooneye `emulator-only/mbc2/*` (7), "genuine MBC2A chip" | hardware-corrected |
| MBC3 | RAMG, ROMB (7 bits), RAMB/RTC select, latch $6000 | rtc3test (expected pictures in the c-sp bundle; no hardware claim found in its README or `tests.md`), MBC3-Tester ("untested on real hardware", c-sp) | detector until the pictures' origin is known |
| MBC5 | RAMG, ROMB low $2000, ROMB bit 8 $3000, RAMB $4000 (bit 3 = rumble) | Mooneye `emulator-only/mbc5/*` (8), "genuine MBC5 chip" | hardware-corrected |
| HuC1, HuC3, MMM01, MBC6, MBC7, TAMA5, Camera | `pandocs/*.md`; GBCTR chapters are stubs (5–9 lines each) | none pinned | documents only |

GBCTR's MBC1 chapter (327 lines) is the authority for MBC1 corner cases
(zero-adjustment of BANK1, banks $20/$40/$60 reachable only through $0000 in
mode 1, RAM banking in mode 0); Pan Docs `MBC1.md` agrees and is easier to
read.

## Save data

Battery RAM (`+BATTERY` types; MBC2's internal RAM) and the MBC3 RTC are
persisted by the frontend, not the board: `save_ram()` returns the bytes,
the frontend writes `<rom>.sav`. For the RTC, use the de facto 48-byte
trailer layout that SameBoy, BGB and mGBA share (SameBoy
`Core/save_state.c`/`mbc.c`; UNVERIFIED which emulators agree byte for byte:
check before promising compatibility).
