# Timing: one clock, the M-cycle callback, and what happens on which dot

Units: **T** = one system clock (4.194304 MHz) = one PPU dot. **M** = one CPU
machine cycle = 4 T (2 T in CGB double speed). Pan Docs and MAME count T;
GBCTR, Mooneye's comments and SingleStepTests count M. Every number here says
which.

## The design: the board advances inside the CPU's M-cycles

sm83-python makes **one bus callback per M-cycle**, including the internal
cycles, each carrying its address (sm83-python `docs/start-here.md` "The bus
as the SoC sees it": read, write, internal; the IDU's address on internal
cycles; $0000 when neither IDU nor memory drives the bus). That property is
what lets this board be exact, the way 6502-python's one-callback-per-cycle
lets famicom-python be:

- In each callback the board advances the system counter, timer, PPU, APU,
  serial and DMA by **one M-cycle's worth of T** (4, or 2 in double speed),
  then completes the access. It never adds `step()`'s return value on top.
- Internal cycles still go through the board: their address reaches the PPU's
  OAM-bug logic (DMG) and costs time.
- IE and IF live in the core; the board decides *when* each IF bit rises and
  raises it through the core's method from inside the callback (see
  [handoff-brief.md](handoff-brief.md) "What the board needs from
  sm83-python" 3). The core samples `IE & IF` at its fetch cycles.
- HALT and STOP are visible states: the core keeps calling the board once per
  M-cycle while halted (so time passes and the wake-up is found on the right
  M-cycle), and reports STOP through a hook so the board can do the DMG
  low-power stop, the DIV reset and the CGB speed switch.

### Where in the M-cycle

The order of "units advance" and "the access lands" inside one M-cycle is the
single most consequential choice in the board. GBCTR's external-bus diagrams
(`gb-ctr/appendix/external-bus.typ`) and GateBoy's eight clock phases A–H
(`metroboy/README.md` "Why is GateBoy so slow?") show a read is sampled late in
the M-cycle and a write's data is driven in its second half. Mooneye's
`*_timing` tests and blargg `mem_timing` measure the consequences in M-cycles;
GBMicrotest measures them at single-T granularity (each test checks "one
register or memory address at one specific cycle after boot":
`GBMicrotest/README.md`). The procedure for the build session:

1. Start with "advance 4 T, then perform the access" for reads and writes.
2. Run GBMicrotest's `*_a/_b/_c/_d` families (the same test at successive
   T offsets) and Mooneye `ppu/*`, `timer/*`; where they disagree with the
   model, move that unit's sample point within the M-cycle, and record it here.
**Settled in milestone 1 (2026-10-07):** every M-cycle is *tick the units (+4 T), perform
the access, then `timer.finish()`*. `finish()` applies the TIMA reload and raises IF at the end
of the overflow cycle, so the CPU's next decision (the next fetch, or an interrupt check) sees
it; with the reload inside `tick()` Mooneye `timer/rapid_toggle` is one instruction late. The
PPU and serial both tick before the access. Two constants are fitted, not read off the die: the
counter's power-on phase (4 T) and `SERIAL_PHASE_T` (4 T; serial/boot_sclk_align with boot_div).

3. Settle residual T-level questions on the die: `dmg-sim` runs any small test
   ROM through the whole DMG-CPU B including the SM83, with transistor-derived
   delays ([validation.md](validation.md) "Die-level models").

Do not settle it by matching SameBoy's source: SameBoy is the reference
*detector*, its code states its own timing model, and that model is not
evidence.

## The system counter

One 16-bit counter, incremented every T (in double speed: every T as well,
but the CPU sees twice as many M-cycles per counter step). DIV ($FF04) reads
its top 8 bits; any write clears all 16 (`pandocs/Timer_and_Divider_Registers.md`).
Everything periodic hangs off its bits through **falling-edge detectors**, so
writing DIV can produce an extra edge:

| Consumer | Bit (normal speed) | Rate | Source |
| --- | --- | --- | --- |
| TIMA, TAC=00 | 9 | 4096 Hz | `Timer_and_Divider_Registers.md` |
| TIMA, TAC=01 | 3 | 262144 Hz | same |
| TIMA, TAC=10 | 5 | 65536 Hz | same |
| TIMA, TAC=11 | 7 | 16384 Hz | same |
| DIV-APU (frame sequencer) | 12 (DIV bit 4); 13 (DIV bit 5) in double speed | 512 Hz | `Audio_details.md` "DIV-APU" |
| serial internal clock | from the counter (bit not stated) | 8192 Hz | Mooneye `boot_sclk_align` comments |

TIMA's input is `selected_bit AND TAC.2`; a falling edge of that AND
increments TIMA. Consequences (`pandocs/Timer_Obscure_Behaviour.md`):

- writing DIV while the selected bit is 1 ticks TIMA (and DIV-APU, if bit 12
  was 1);
- writing TAC to select a bit that is 0 when the old one was 1 ticks TIMA;
- **DMG only**: disabling the timer while the selected bit is 1 ticks TIMA;
  on CGB it does not, and enabling may or may not tick "varying between
  individual consoles";
- overflow: TIMA reads $00 for one M-cycle, then TMA is loaded and IF bit 2 is
  set. A TIMA write during that M-cycle cancels the reload and the interrupt;
  a TIMA write during the reload M-cycle is ignored (TMA wins); a TMA write
  during the reload M-cycle is loaded too.

Judges: Mooneye `acceptance/timer/*` (13 tests, verified on DMG, MGB, SGB,
SGB2, CGB, AGB, AGS where their headers say so), Gambatte `hwtests/tima/*`
and `div/*` (DMG and CGB outcomes in the file names), GBMicrotest `div_*`,
`timer_*`, `tima_*`.

## Interrupts: when each IF bit rises

| Bit | Source | Rises when | Judges |
| --- | --- | --- | --- |
| 0 | VBlank | LY becomes 144 (mode 1 entry) | Mooneye `ppu/vblank_stat_intr-GS` ("vblank and stat_m2_144 are triggered at the same time", G/S only) |
| 1 | STAT | the STAT line (OR of the enabled conditions) goes 0→1 | Mooneye `ppu/stat_irq_blocking`, `ppu/stat_lyc_onoff`; Gambatte `m*int_*`, `lyc*` |
| 2 | Timer | one M-cycle after TIMA overflows | Mooneye `timer/tima_reload` |
| 3 | Serial | the 8th bit has shifted | Mooneye `serial/boot_sclk_align` |
| 4 | Joypad | any selected input goes high→low | Gambatte `hwtests/jpadirq_*` |

STAT is a **single line**, and the interrupt fires only on its rising edge:
while one condition holds, another becoming true does not fire again ("STAT
blocking", `pandocs/Interrupt_Sources.md`; Mooneye `stat_irq_blocking`
verified on DMG ABC, MGB, CGB, AGB, AGS, fails on DMG 0: the first revision
row in [undocumented-behavior.md](undocumented-behavior.md)). The mode-2
condition is also true at the start of line 144 on DMG (the
`vblank_stat_intr` test), and the LY=LYC comparison is not continuous: on
line 153, LY reads 153 for only a few dots and then 0, and LYC=0 matches
there (`pandocs/STAT.md`; Gambatte `hwtests/ly0`, `lyc153int_m2irq`).

## The PPU, dot by dot

One line = 456 dots; 144 visible lines, 10 VBlank lines (`pandocs/Rendering.md`).

| Dots of a visible line | Mode | Notes |
| --- | --- | --- |
| 0–79 | 2 (OAM scan) | 2 dots per OAM entry, up to 10 objects selected, in OAM order |
| 80 – 80+L₃ | 3 (transfer) | L₃ = 172 … 289: 12 for the two initial tile fetches, + SCX mod 8, + 6 when the window starts, + 6…11 per object |
| … – 455 | 0 (HBlank) | |

Mooneye's measured consequences, all on hardware:

- `ppu/intr_2_0_timing`: mode 2 IRQ to mode 0 IRQ with no objects, scroll or
  window (all models);
- `ppu/hblank_ly_scx_timing-GS`: LY increments 51 / 50 / 49 M-cycles after
  the mode-0 IRQ for SCX mod 8 = 0 / 1–4 / 5–7 (G/S only; CGB differs);
- `ppu/intr_2_mode0_timing_sprites`: the object penalties;
- `ppu/lcdon_timing-GS`: after LCDC.7 is set, **line 0 starts in mode 0 and
  goes straight to mode 3, and is late by 2 T**; lines 1 and 2 are normal
  (G/S only; CGB fails it);
- `ppu/lcdon_write_timing-GS`: when VRAM/OAM become writable after LCD on.

The fetcher, the two FIFOs, object fetch timing, window triggering (WY
latched per frame, WX compared per dot, the WX=0 and WX=166 cases) and
mid-mode-3 register effects are in `pandocs/pixel_fifo.md` and Mealybug's
`the-comprehensive-game-boy-ppu-documentation.md`. The latter is written by
the Mealybug author from his emulator, which was checked against photos of
real units; treat its *descriptions* as hypotheses and its *test pictures* as
the judge. Several Pan Docs passages are marked unconfirmed (e.g.
`pixel_fifo.md` l.158–160 on when the SCX penalty is paid).

What the CPU sees: VRAM reads return $FF and writes are dropped in mode 3;
OAM likewise in modes 2 and 3 (`pandocs/Accessing_VRAM_and_OAM.md`). The
lock edges are a few T off the mode change on DMG (Mooneye
`ppu/intr_2_oam_ok_timing`, `lcdon_write_timing-GS`; Gambatte `oam_access/*`,
`vram_m3/*`, `vramw_m3end/*`).

## OAM DMA

Writing $FF46: **M+1 nothing, M+2 the transfer starts and OAM reads return
$FF**; a restart keeps the old transfer running through M+1 (Mooneye
`oam_dma_start.s` header, all models). One byte per M-cycle for 160 M-cycles
(`gb-ctr/chapter/peripherals/dma.typ`). During the transfer the DMA owns the
*source* bus: CPU reads on that bus get the DMA's byte (a conflict), HRAM and
the other bus stay usable (`pandocs/OAM_DMA_Transfer.md` "OAM DMA bus
conflicts"; GBCTR's section is TODO). Source decoding is simplified: every
source in $A000–$FFFF is an *external-bus* read, so $FExx and $FFxx sources
read the cartridge/WRAM side, not OAM or I/O (`dma.typ` "OAM DMA address
decoding"; Mooneye `oam_dma/sources-GS`, verified G/S). Judges: Mooneye
`oam_dma_*`, `oam_dma/*`; Gambatte `oamdma/*`; GBMicrotest `dma_*`.

## The OAM corruption bug (DMG, MGB, SGB only)

Two triggers (`pandocs/OAM_Corruption_Bug.md` "Accurate Description"): any CPU
read or write of $FE00–$FEFF while the PPU is in mode 2, and any IDU
increment/decrement of BC, DE, HL, SP or PC while its value is in
$FE00–$FEFF in mode 2, **with or without a memory access** (the IDU drives
the address bus). The corruption pattern depends on read, write, or
read-plus-increment, and on the OAM row the PPU is scanning. Judges: blargg
`oam_bug` (8 tests, verified on DMG-C by c-sp), Gambatte `oam_access/*`.

Caveat on the judges: dmg-sim's README says its default simplified OAM model
omits the bug, and with the full SRAM model "oam_bug tests depend on small
differences in signal delays which could change with temperature … some edge
cases indeed behave nondeterministic on real hardware" (citing SameBoy's
`memory.c`). So blargg `oam_bug` is a judge of the deterministic cases only;
the brief scopes it that way.

## The APU on the clock

Channels count in T (pulse period `(2048 − freq) × 4` T, wave `× 2` T, noise
from its divisor and shift: `pandocs/Audio_details.md`). The frame sequencer
steps on DIV-APU (above). Trigger, length and sweep quirks (the
"extra length clock" when enabling length in the first half of a period, the
sweep "negate then positive" disable, zombie-mode envelope writes, DMG wave
RAM access only when the channel reads it) are in `Audio_details.md`
"Obscure Behavior" and are each covered by a blargg `dmg_sound` test.
Mixing: output samples at whatever rate the board likes from the
per-T DAC levels; `take_samples()` box-filters to the host rate, as
famicom-python and sms-python do.

## CGB double speed and the speed switch (phase 2)

KEY1 bit 0 arms, `STOP` performs the switch; the CPU then stops for **2050 M
(8200 T)** during which DIV does not tick and VRAM/OAM locking is frozen in
the state of the current PPU mode (`pandocs/CGB_Registers.md` l.189–197; the
"TODO: confirm whether interrupts can occur" there is open). In double speed
the CPU, timer, serial, OAM DMA and DIV-APU's input bit change; the PPU, HDMA
transfer rate and APU frequencies do not (same section). Judges: Gambatte
`hwtests/speedchange/*` (CGB outcomes), SameSuite `ppu/*`, `dma/*`,
`interrupt/*` (CGB).

HDMA ($FF51–$FF55): general-purpose (all at once, CPU halted) or 16 bytes per
HBlank; timing per `pandocs/CGB_Registers.md` and SameSuite `dma/`.
