# The Super Game Boy, high-level (`sgb.py`)

Written 2026-11-13 for the Rust transcription (gameboy-rust, then the fast fork and the
browser player). The module is `src/gameboy_python/sgb.py`; its tests are `tests/test_sgb.py`.

A real Super Game Boy is a Game Boy (the `sgb`/`sgb2` machine rows) on a SNES cartridge. The
ICD2 chip hands the SNES each LCD line and each 16-byte command packet, and drives the Game
Boy's joypad lines. The SNES program (the "SGB BIOS", Nintendo's ROM) keeps palettes, an
attribute map and a border and draws the 256 x 224 picture. snes-python runs that program for
real (`snes_python/sgb.py`, low level). This module does the program's job directly from the
packets: a high-level emulation (HLE).

## Using it

```python
gb = GameBoy(cartridge, MACHINES["sgb"], boot_rom=sgb_boot_or_None)
sgb = SuperGameBoy(gb)            # optional: palette=(c0, c1, c2, c3) as SNES words
gb.run_frames(n)
words = sgb.render()              # array('H'), 256 * 224 SNES colours, rows top to bottom
rgb = rgb_bytes(words)            # 8-bit RGB, channels widened c << 3 | c >> 2
sgb.set_pressed("a", True, player=0)   # host input goes to the SGB, not to gb.joypad
blob = sgb.save_state(); sgb.load_state(blob)
```

Attaching is opt-in: `SuperGameBoy(gb)` sets three hooks that already exist on the board
(`gb.joypad.on_write`, `gb.ppu.line_out`, `gb.ppu.frame_start`) and drives
`gb.joypad.set_external`. Nothing in `board.py`, `ppu.py` or `joypad.py` changed for it; a
Game Boy without one behaves exactly as before. It raises `ValueError` on a non-SGB machine.

`scripts/sgb_picture.py GAME --frames N --png OUT.png [--boot sgb_boot.bin|mame] [--every K]
[--packets]` runs a game and writes the picture.

Colour format: SNES BGR555, `0bbbbbgggggrrrrr` (bit 15 zero). Colour 0 of every palette is
the backdrop `cgram[0]`.

## Structure

Two layers in one class, `SuperGameBoy` (33 instance attributes, under PyPy's 80):

1. **ICD2** (hardware). The same rules as snes-python's ICD2 model, which passes Mooneye's SGB
   boot tests:
   - `p1_write(select)`: called with bits 5-4 of every P1 write. Ignore a write that does not
     change them. `00` = start pulse: clear the packet, `receiving = wait_high = True`,
     `bit_count = 0`. Else if `wait_high`: clear it; if the write is not `30` (both high),
     abandon the packet. Else if `receiving`: `10` (P15 low) is a 1 bit, `20` a 0 bit; bits go
     LSB first into `packet[bit_count >> 3]`; after 128 bits the next bit is the stop bit,
     and a 0 there delivers the packet (`receive_packet`), a 1 drops it; set `wait_high` after
     each data bit. Else (no packet coming) a P15 low-to-high edge selects the next player:
     `player = (player + 1) & PLAYER_MASK[players]`. Finally `_update_lines()`.
   - `_update_lines()`: with both lines high (`30`) the input nibble is `0xF - player`, else
     `0xF`; P14 low ANDs in the pad's low nibble (directions), P15 low ANDs in its high nibble
     (buttons). Pad bytes are `Start Select B A Down Up Left Right`, 0 = pressed.
2. **BIOS** (HLE). `receive_packet` gathers packets into a command: the first packet's low 3
   bits are the packet count (0 = ignore the packet); header packets (code `>= $1E`, i.e.
   `$F1, $F3 ... $FB`) are always one packet (their low bits are an index). When the last
   packet arrives, `execute(command)` runs it at once.

LCD side: `lcd_line(shades)` stores the 160 shades of the line that just ended at row
`ppu.ly` of `lcd` (the PPU calls `line_out` before LY advances). `lcd_frame()` (line 0
starts) copies `lcd` to `shown` unless `mask == FREEZE`, then counts down a pending VRAM
transfer. An LCD that is off draws no lines and starts no frames, so the picture freezes by
itself (Pan Docs: the SGB freezes when the LCD is turned off).

## The data (all of it is the save state)

`save_state()` brings the fade up to `gb.t` (`run_fade`), then writes a version byte (2) and
these fields in this order (`STATE_LAYOUT`); u8 = one byte (bools as 0/1), words =
little-endian u16s, u64 = one little-endian 8-byte integer. Version 1 (before the fade) is
refused:

| Field | Kind | Size | Meaning |
| --- | --- | --- | --- |
| p1 | u8 | | last select bits written ($00, $10, $20, $30); at attach the board's own select when a boot ROM is mapped, else $30 (what the SGB boot ROM leaves) |
| receiving, wait_high, bit_count | u8 | | packet receiver state |
| packet | bytes | 16 | the packet being received |
| players | u8 | | MLT_REQ byte 1 & 3 |
| player | u8 | | selected player 0-3 |
| pads | bytes | 4 | per player, 0 = pressed |
| command | bytes | 112 | the command being gathered (7 packets) |
| packets_due, packets_got | u8 | | gathering state |
| header | bytes | 84 | $0104-$0157 from the boot ROM's header packets |
| enabled | u8 | | commands obeyed (header SGB flag $0146 = 3 and licensee $014B = $33) |
| lcd | bytes | 23040 | LCD shades as lines end |
| shown | bytes | 23040 | the picture shown (last whole frame, or frozen) |
| mask | u8 | | MASK_EN mode 0-3 |
| transfer, transfer_wait | u8 | | pending VRAM transfer kind and frames left |
| cgram | words | 128 | SNES palettes 0-7 x 16: 0-3 Game Boy (colours 0-3), 4-6 border, 7 unused |
| system_palettes | words | 2048 | PAL_TRN's 512 palettes x 4 colours |
| attr_map | bytes | 360 | palette 0-3 per 8 x 8 cell, 20 x 18, row-major |
| attr_files | bytes | 4050 | ATTR_TRN's 45 files x 90 bytes |
| tiles | bytes | 8192 | border tiles shown (256 x 32-byte 4bpp SNES tiles) |
| tiles_pending | bytes | 8192 | CHR_TRN's tiles, shown from the next PCT_TRN |
| border_map | words | 928 | PCT_TRN's map, 29 rows x 32 entries |
| border_loaded | u8 | | false until the first PCT_TRN's border is shown |
| border_map_pending | words | 928 | PCT_TRN's map, shown at fade tick 38 |
| border_colors_pending | words | 48 | PCT_TRN's palettes 4-6, into `cgram[64..111]` at tick 38 |
| fading | u8 | | a border fade is running |
| fade_tick | u8 | | the fade's last step, 0-69 (0: none yet) |
| fade_due | u64 | | `gb.t` (the board's T-cycle clock) of the next step: restore the board's state with this one |

`enabled` starts from the cartridge's header bytes at attach (the skip-boot case); with a
boot ROM running, the header packets decide it again after `$FB`.

## Commands

Byte 0 is `code * 8 + packets`; `c[n]` is byte n of the gathered command.

| Code | Name | Effect here |
| --- | --- | --- |
| $00-$03 | PAL01, PAL23, PAL03, PAL12 | `c[1..2]` is colour 0: written to `cgram[0, 16, 32, 48]`; `c[3..8]` colours 1-3 of the first palette, `c[9..14]` of the second (pairs 0-1, 2-3, 0-3, 1-2) |
| $04 | ATTR_BLK | `min(c[1], 18)` data sets of 6 bytes from `c[2]`: control (bit 0 inside, 1 edge, 2 outside), palettes (bits 1-0 inside, 3-2 edge, 5-4 outside), x1 y1 x2 y2 (& 31, inclusive). Inside = strictly inside, edge = on the rectangle's border, outside = beyond it. Only-inside or only-outside also sets the edge to that palette |
| $05 | ATTR_LIN | `c[1]` bytes from `c[2]`: bits 4-0 line, 6-5 palette, bit 7 horizontal (a row) else a column; out-of-range lines skipped; later win |
| $06 | ATTR_DIV | `c[1]` bits 1-0 after the line, 3-2 before it, 5-4 on it, bit 6 split by rows (else columns); `c[2] & 31` the line |
| $07 | ATTR_CHR | start `(c[1], c[2])` (off-screen: nothing), count `c[3] | c[4] << 8` (cap 360), `c[5]` 0 rightwards / 1 downwards, 2-bit palettes from `c[6]`, first in bits 7-6; wraps at the edge, stops after the last cell |
| $0A | PAL_SET | palettes 0-3 = system palettes `(c[1+2p] | c[2+2p] << 8) & $1FF` (colours 1-3); colour 0 from palette 0's system palette into all four; `c[9]` bit 7 apply ATF `c[9] & $3F`, bit 6 cancel mask |
| $0B | PAL_TRN | VRAM transfer -> `system_palettes` (2048 words) |
| $11 | MLT_REQ | `players = c[1] & 3`; `player &= PLAYER_MASK[players]`; update lines |
| $13 | CHR_TRN | VRAM transfer -> `tiles_pending[0:4096]` (`c[1]` bit 0 = 0) or `[4096:8192]` |
| $14 | PCT_TRN | VRAM transfer: bytes $000-$73F -> `border_map_pending`, $800-$85F -> `border_colors_pending`; starts the border fade, which shows them (and `tiles_pending`) at tick 38 |
| $15 | ATTR_TRN | VRAM transfer: bytes $000-$FD1 -> `attr_files` |
| $16 | ATTR_SET | ATF `c[1] & $3F` (above $2C: nothing) -> `attr_map` (each byte 4 cells, first in bits 7-6); `c[1]` bit 6 cancels the mask |
| $17 | MASK_EN | `mask = c[1] & 3`: 0 off, 1 freeze, 2 black, 3 colour 0 |
| $1E-$1F | header packets | while the boot ROM is mapped: index `c[0] >> 1 & 7` (0-5) -> `header[14i:14i+14] = c[2:16]`; after `$FB`, `enabled` = flag and licensee check |
| others | | no effect (see "Out of scope") |

**VRAM transfer.** The command sets `transfer` and `transfer_wait = 2`. Each frame start
counts down; at 0 the data is read from `lcd`, which then holds the first whole frame drawn
after the command: 256 tiles, tile n from cell `(n mod 20, n div 20)`, 16 bytes each, per row
a low-plane byte then a high-plane byte, leftmost pixel in bit 7 (shade bit 0 / bit 1). That is
the 4 KiB at $8000-$8FFF when the game shows them with BGP $E4 (Pan Docs SGB_VRAM_Transfer.md).

## The border fade

Measured on snes-python running the real BIOS (2026-11-13: Donkey Kong, Pokemon Red, Kirby's
Dream Land 2, Mario's Picross, Wario Land II; every SNES frame logged: INIDISP writes, CGRAM
after each frame, packets: `scripts/sgb_lle_run.py --log`). The BIOS never touches the master
brightness for it (INIDISP stays at 15, apart from one-frame force blanks, see below); it
rewrites CGRAM palettes 4-6, the border's, every other SNES frame:

- **Fade-out**, writes 1-32: each 5-bit channel of each colour is `max(c - n, 0)` for write n,
  c the old border's colour (at power-on the BIOS's own border, not reproduced here).
- **Pause**: 12 SNES frames from write 32 to write 33 (the new border's map and tiles go in).
- **Fade-in**, writes 1-33: each channel `min(c, n)`, c the new border's colour.

All 65 writes of all five games fit these formulas with 0 exceptions (48 colours x 3 channels
each). Palettes 0-3 (the Game Boy's) and colour 0 (the backdrop) are not faded, so the Game Boy
window and the transparent border pixels keep their colours. MASK_EN starts no fade (MASK_EN
packets in Kirby's Dream Land 2 and Pokemon Red: no CGRAM writes beyond the 65).

The first write comes 5 or 6 SNES frames after the PCT_TRN packet (the data is read ~2 frames
after the packet); a picture shows a write from the next frame on. The 2-frame cadence slips
while the BIOS handles other commands: PAL_TRN and ATTR_TRN hold the next write up by 3
frames, SOU_TRN by 7 or 9, PAL_SET, ATTR_BLK and MASK_EN by 1; DATA_SND, SOUND, PAL_PRI,
MLT_REQ, ICON_EN and ATRC_EN by none.

The model (`run_fade`, `shown_cgram`), on the Game Boy's clock `gb.t`, because a game may keep
its LCD off (no frame starts) for many frames of a fade (Donkey Kong does):

- One SNES frame is `SNES_FRAME_T` = 71,473 T-cycles (the SGB's Game Boy runs at the SNES
  master clock / 5; an NTSC frame averages 357,366 master clocks).
- When PCT_TRN's data has been read (`_finish_transfer`), unless a fade is still before tick
  38: `fading = True`, `fade_tick = 0`, `fade_due = gb.t + 4 frames` (`FADE_DELAY_FRAMES`,
  fitted: 3 and 5 each lose 4-5 of 9 consecutive Donkey Kong pictures that 4 matches). During a
  fade-out a newer PCT_TRN only replaces the pending border.
- `run_fade()`: while `fading` and `gb.t >= fade_due`: `fade_tick += 1`, `fade_due += 2
  frames`; at tick 38 (`FADE_IN_TICK`) the pending map and palettes and `tiles_pending` become
  the border (`border_loaded = True`); at tick 70 (`FADE_END_TICK`) the fade ends (`fading =
  False`, `fade_tick = 0`). It runs at each frame start, before each command, in `render()` and
  in `save_state()`: the state at a given `gb.t` is the same however often it is called.
- Each command obeyed while `fading` adds `COMMAND_FRAMES[code]` frames to `fade_due` (the
  measured holds; SOU_TRN 8, CHR_TRN and PCT_TRN 3 as the other transfers, unmeasured).
- Drawing: for tick t in 1-37 each channel of `cgram[64..111]` shows `max(c - t, 0)`, for t in
  38-69 `min(c, t - 37)`; at tick 0 (fade scheduled, no step yet) the colours as they are.

**Skip-boot and power-on** start alike: no fade, no border (black around the window) until
the first PCT_TRN, which then runs the whole timeline, fading out the black (the real BIOS
fades out its own border there), then the game's border fading in from ~1.3 s after the
packet, whole by ~2.4 s. Not
shortening the fade when no border is loaded keeps the two starts and the timing the same as a
real SGB's.

Not modelled: the one-frame force blanks (INIDISP left at $80 through a frame, so presumably
a black SNES picture; no such picture was looked at) the BIOS shows now and then, likely when
its main loop runs late (Donkey Kong at SNES frames 646, 666,
733, ...; Pokemon Red 597, 692, ...): timing of the BIOS's own work, not of the packets.

## The picture

The border layer is 256 x 232 (29 map rows); the Game Boy window sits at layer (48, 40),
cells 6-25 x 5-22. **Screen line y shows layer line y + 1** (`FIRST_LINE`: the BIOS leaves
BG1VOFS at 0 and the S-PPU draws lines VOFS+1..VOFS+224), and the **last screen line is
black** (`BLANK_LINES`: the BIOS force-blanks it). For each other pixel:

1. Border index: map entry at `(y >> 3) * 32 + (x >> 3)`; entries with bits 9-8 set (tile
   256+) are transparent; tile `entry & $FF`, row `y & 7` (flipped by bit 15), column bit
   `7 - (x & 7)` (flipped by bit 14); colour = plane bits from bytes `row*2`, `row*2+1`,
   `16+row*2`, `17+row*2`. If colour != 0, the pixel is `cgram[(entry >> 10 & 7) * 16 + colour]`
   (the border covers the Game Boy window).
2. Else inside the window: mask 2 -> 0 (black); mask 3 -> `cgram[0]`; else shade s of
   `shown`, palette p of the cell: `cgram[0]` if s == 0 else `cgram[p * 16 + s]`.
3. Else (border area, transparent): `cgram[0]` once a border is loaded, black before.

Border colours (`entry >> 10 & 7` = 4-6) go through the fade (`shown_cgram()`); the rest of
`cgram` is drawn as it is.

Power-on: all four Game Boy palettes are a grey ramp (`$7FFF, $56B5, $294A, $0000`, or the
`palette` argument), the attribute map 0, no border (black around the window).

## Validated against

Judge: **snes-python running the real SGB BIOS** (Super Game Boy (World) (Rev 2), the SGB
boot ROM from MAME's `sns_rom_sgb`, MAME's SNES IPL) with gameboy-python as its Game Boy:
`scripts/sgb_lle_run.py`, then `scripts/sgb_compare.py --lle`. Detector: **SameBoy's HLE SGB**
(`scripts/sgb_sameboy.py`, colour correction off), `scripts/sgb_compare.py --sameboy`. Both
sides boot the same SGB boot ROM. Pictures compared at 5 bits per channel over all 256 x 224
pixels; each judge picture against the closest HLE frame within 3 Game Boy frames (while the
LCD is off, also every SNES frame's worth of Game Boy time). The full tables are in
validation.md "Super Game Boy, HLE (2026-11-13)" and "Super Game Boy, the border fade".

In short: **every settled picture, and every picture of the border's fade-in, is pixel-exact
against the real BIOS** except for: the fade-out of the BIOS's own border before the game's
first border (its artwork is not reproduced: black here), one 8-line row of the Game Boy
picture that the low-level SGB occasionally shows from the next row (a row-buffer race on the
SNES side), and games that never send a palette (Tetris DX), whose window keeps the BIOS's
built-in palette 1-A. The packet stream is identical to the low-level run (same packets, same
Game Boy frames).

**From skip-boot** (no boot ROM, as play-gb runs): the ICD2 starts at $30, where the boot ROM's
header packets leave it. Starting from the board's skip-boot select ($00) lost each game's first
packet, a $00 start pulse taken for no change; for Pokemon Red that is its MLT_REQ check, so it
never sent a border (found by the gameboy-rust transcription, 2026-11-13). With the fix, Pokemon
Red (900 frames) and Pokemon Yellow, Kirby's Dream Land 2, Link's Awakening DX, Wario Land II and
Tetris DX (1,500) all load their borders from skip-boot; Donkey Kong and Mario's Picross did
before and still do. The border then fades in as after the boot ROM ("The border fade").

## Out of scope (not done, on purpose)

- The BIOS's own artwork and data: the default border, the built-in palettes (1-A ... 4-H,
  and the per-title palettes for non-SGB games), menus, the boot animation. They are
  Nintendo's ROM contents. A frontend may pass `palette=` to `SuperGameBoy`.
- SOUND ($08), SOU_TRN ($09): SNES sound. DATA_SND ($0F), DATA_TRN ($10), JUMP ($12): SNES code
  and data (games use DATA_SND to patch the BIOS; ignored). OBJ_TRN ($18): SNES sprites.
- ICON_EN ($0E), ATRC_EN ($0C), TEST_EN ($0D), PAL_PRI ($19): accepted, no effect.
- Header packet checksums are not checked.

## Open items, unverified details

- **Timing.** Commands act at the stop bit of their last packet; the real BIOS acts frames
  later and drops a packet if the next arrives before it has read the previous one (the ICD2
  holds one). The multiplayer change of MLT_REQ is immediate (the BIOS writes `$6003` later).
  No game in the eight tested diverged because of it (identical packet streams).
- **Border change.** Measured only for the first border after power-on (every game tested sends
  one). A second border later in a game, PCT_TRN during a fade-in, CHR_TRN during a fade: the
  model's rules above, unverified. CHR_TRN tiles are shown only from the next PCT_TRN
  (SameBoy's rule, Core/sgb.c, Expat); not checked against the BIOS with a CHR_TRN-only game.
- Tile numbers 256+ in the border map, palette numbers 0-3 or 7 in border entries: taken as
  transparent / as `cgram` palettes 0-3 and 7. Unverified.
- ATTR_CHR's stop at the last cell and its off-screen start; ATTR_BLK/ATTR_LIN counts above
  what fits: unverified against the BIOS.
- SGB2 is the same module; only `sgb` was run against the low-level SGB.
- The PyPy frontend (`python -m gameboy_python play`) does not use it yet.
