"""The Game Boy: the bus that decodes the CPU's M-cycles and advances every unit inside them.

sm83-python makes one bus callback per M-cycle, internal cycles included. In each callback this
board first advances the system counter, timer, serial port, PPU and OAM DMA by one M-cycle (four
T-cycles), then completes the access; it never adds ``step()``'s return value on top
(docs/timing.md "The design"). "Advance, then access" is the starting point of the order within
the M-cycle; GBMicrotest and Mooneye settle it unit by unit and any change is recorded there.

IE ($FFFF) and IF ($FF0F) live in the core: the board raises an IF bit with
``cpu.request_interrupt(bit)`` from inside a callback, and answers CPU accesses to $FF0F from
``cpu.if_`` (the core already answers $FFFF).
"""

from __future__ import annotations

from sm83_python import SM83, CPUState, StopAction, StopResult

from gb_apu_python import APU, CGB, DMG
from gameboy_python import ppu as ppu_module
from gameboy_python.cartridge import Cartridge
from gameboy_python.dma import EXTERNAL, INTERNAL, VIDEO, OamDma, bus_of
from gameboy_python.joypad import Joypad
from gameboy_python.machines import DMG_B, Machine
from gameboy_python.ppu import PPU
from gameboy_python.serial import Serial
from gameboy_python.timer import Timer

#: post-boot register values for DMG-CPU A/B/C (Pan Docs Power_Up_Sequence.md "CPU registers",
#: confirmed by Mooneye boot_regs-dmgABC); F's Z is always set, H and C follow the header checksum
POST_BOOT_DMG = {"a": 0x01, "b": 0x00, "c": 0x13, "d": 0x00, "e": 0xD8, "h": 0x01, "l": 0x4D}
#: ... and for a CGB (Pan Docs Power_Up_Sequence.md): a CGB game, and a DMG game in compatibility mode
POST_BOOT_CGB = {"a": 0x11, "b": 0x00, "c": 0x00, "d": 0xFF, "e": 0x56, "h": 0x00, "l": 0x0D}
POST_BOOT_CGB_COMPAT = {"a": 0x11, "b": 0x00, "c": 0x00, "d": 0x00, "e": 0x08, "h": 0x99, "l": 0x1A}

#: the CGB boot ROM is $0000-$00FF and $0200-$08FF; $0100-$01FF is the cartridge header
CGB_BOOT_SIZE = 0x900
#: STOP's speed switch halts the CPU this many units (4 per M-cycle) unless an interrupt ends it
#: earlier (SameBoy ``speed_switch_halt_countdown``; Gambatte speedchange)
SPEED_SWITCH_HALT = 0x20008  # units, switching from double to single speed
SPEED_SWITCH_HALT_TO_DOUBLE = 0x20008  # ... and from single to double; FITTED
#: dots the LCD runs on its own when the speed switches to double, and to single (negative: it
#: stands still). FITTED on Gambatte speedchange/lcd_offset/lcdoffset1 (230 -> 264 of 357; -4/3,
#: -2/2, 1/2, -3/3 all lower). SameBoy's TODO has 2 PPU ticks single->double; Gambatte moves the
#: LCD a cycle ahead on double->single, which is -3 here with our one ds M-cycle longer halt.
SWITCH_LCD_DS = 2
SWITCH_LCD_SS = -3


IF_WRITE_PHASE = 0  # FITTED: IF bits raised in a write's own M-cycle survive the write


SERIAL_IF_HIDE = 4  # dots; fitted, see _serial_irq
SERIAL_DIV_EDGE = 1  # a DIV write's fall clocks the serial toggle (Gambatte serial/*_div_write_*)
# an SC write while the interrupt hides cancels it (Gambatte serial/*_sc80_*, *_stop_*)
SERIAL_SC_CANCEL = 1
# units (4 per M-cycle) a transfer takes after the opcode fetch before its first byte: SameBoy
# GB_hdma_run's 2, 4 in double speed
HDMA_START = 2
HDMA_START_DS = 4
# FITTED (Gambatte dma/hdma_start_*, hdma_cycles_*, gdma_cycles_* +30, nothing lost; SameBoy
# sets hdma_on 3 T after mode 0): dots into HBlank before an HBlank block falls due
HDMA_HBLANK_LAG = 4
HDMA_HBLANK_LAG_DS = 2
HDMA_END = 2  # ... and after its last, at single speed; FITTED
VBLANK_CGB_DELAY = 4  # FITTED (Mooneye misc/ppu/vblank_stat_intr-C)
TIMER_HALT_DELAY = 4  # FITTED (GBMicrotest int_timer_halt, int_timer_halt_div_b)
# HALT decides on IF at the end of its fetch for a STAT interrupt raised in that fetch, and
# samples IF at the start of its second cycle, so one raised there waits for the next cycle
# (SameBoy halt() and GB_cpu_run's just_halted; Gambatte halt/late_m0i*_scx2/3, both models)
HALT_SEES_STAT = 1
HALT_CYCLE_HALTED = 1
# a dispatch's low-byte push samples IF in its cycle's first dot, so an HBlank interrupt raised
# after that is not chosen and a pending one raised again stays set (Gambatte irq_precedence
# late_m0irq_vs_tima_*_2 and late_m0irq_retrigger_scx1_1; SameBoy reads IF at the push)
DISPATCH_SAMPLE_DOT = 1


OAM_IDLE_KIND = "write"  # the OAM-bug pattern an IDU step without an access causes


class GameBoy:
    """One console: a machine row, a cartridge, an optional boot ROM, and all the units."""

    def __init__(
        self,
        cartridge: Cartridge,
        machine: Machine = DMG_B,
        boot_rom: bytes | None = None,
    ) -> None:
        self.machine = machine
        self.cartridge = cartridge
        self.t = 0  # PPU dots (4.19 MHz T-cycles of real time) since power-on
        cgb = self.cgb = machine.cgb_hardware
        self.wram = bytearray(0x8000 if cgb else 0x2000)
        self.svbk = 1  # the WRAM bank at $D000 (CGB mode: SVBK, 0 reads as 1)
        self.hram = bytearray(0x7F)
        self.boot_rom = bytes(boot_rom) if boot_rom is not None else None
        self.boot_mapped = self.boot_rom is not None
        size = CGB_BOOT_SIZE if cgb else 0x100
        if self.boot_rom is not None and len(self.boot_rom) != size:
            raise ValueError(f"a {machine.model.upper()} boot ROM is {size} bytes")
        self.double_speed = False
        self.key1 = 0  # bit 0: a speed switch is armed
        self._switch_wait = 0  # units left of the speed switch's halt
        self._lcd_freeze = 0  # dots the PPU skips (a speed switch's negative skew)
        self._div_reset_due = False  # a speed switch's STOP clears DIV in its operand read
        self._div_hold = 0  # M-cycles the counter then stands still for
        self._switch_halted = False
        self.key0 = 0
        self.rp = 0
        self.undocumented = [0, 0, 0, 0]  # $FF72-$FF75
        self.svbk_register = self.opri_register = 0
        self.hdma_src = self.hdma_dst = 0
        self.hdma_blocks = 0  # 16-byte blocks left
        self.hdma_hblank = False  # an HBlank transfer is armed
        self.hdma_due = False  # a block is to run before the next instruction
        self._hdma_at_fetch = False  # ... at the end of this step's opcode fetch
        self._idle_units = 0
        self._last_mode = 0
        self._hdma_mode = 0

        self.cpu = SM83(self._read, self._write, self._idle, stop=self._stop)
        raise_irq = self.cpu.request_interrupt
        self.timer = Timer(self._timer_irq, machine.tac_disable_glitch)
        # The counter's power-on phase: DIV reads in Mooneye boot_div-dmgABCmgb need the counter
        # 4 T ahead of the M-cycle count since reset (fitted; the only phase that passes it)
        self.timer.counter = 4
        self.serial = Serial(self._serial_irq)
        self.joypad = Joypad(raise_irq)
        self._late_bits = 0  # IF bits raised in the last dots of the current M-cycle
        self._hide = 0  # IF bits raised early for the CPU's dispatch, not yet readable
        self._hide_left = 0
        self._halt_cycle = False  # this M-cycle is HALT's own second one
        self._late: list[list[int]] = []  # OAM interrupts held back while the CPU is halted
        self.ppu = PPU(
            self._ppu_irq, machine.stat_write_glitch, stat_blocking=machine.stat_blocking, cgb=cgb
        )
        self.ppu.cgb_mode = cgb  # the boot ROM runs in CGB mode and picks compatibility by KEY0
        self.apu = APU(model=CGB if cgb else DMG)
        self.dma = OamDma(self._dma_source, self._dma_write)
        self._cpu_step = self.cpu.step
        if cgb:
            self.cpu.step = self.step  # instruction boundaries are where HDMA blocks run
        if self.boot_rom is None:
            self._skip_boot()

    # ----- power-on -----------------------------------------------------------------------

    def _skip_boot(self) -> None:
        """The state the DMG boot ROM leaves at $0100 (Pan Docs Power_Up_Sequence.md)."""
        header = self.cartridge.header
        f = 0x80 | (0x30 if header.header_checksum != 0 else 0)
        if self.cgb:
            self._skip_boot_cgb()
            return
        self.cpu.restore_state(CPUState(**POST_BOOT_DMG, f=f, sp=0xFFFE, pc=0x0100, if_=0x01))
        # DIV $AB; the low byte is the counter phase at handoff: what dmg-sim's
        # quickboot leaves on this board and the only phase that passes Mooneye boot_div-dmgABCmgb
        self.timer.counter = 0xABC8
        self.serial.sc = 0
        self.dma.register = 0xFF
        self.ppu.bgp = 0xFC
        self.ppu.write_lcdc(0x91)
        self.ppu.stat_select = 0
        # the PPU is late in line 153 (LY reads 0, mode 1, STAT $85) at handoff, as quickboot
        # leaves it
        self.ppu.place(153, 396, 1)
        self.apu.skip_boot()
        self.boot_mapped = False

    def _skip_boot_cgb(self) -> None:
        """The state the CGB boot ROM leaves at $0100 (Pan Docs Power_Up_Sequence.md). A DMG game
        is left in compatibility mode with the boot ROM's default palettes (white to black)."""
        header = self.cartridge.header
        cgb_game = header.cgb_enhanced
        regs = POST_BOOT_CGB if cgb_game else POST_BOOT_CGB_COMPAT
        self.cpu.restore_state(
            CPUState(**regs, f=0x80, sp=0xFFFE, pc=0x0100, if_=0x01)
        )
        ppu = self.ppu
        ppu.cgb_mode = cgb_game
        ppu.opri = self.opri_register = 0 if cgb_game else 1
        self.key0 = header.cgb_flag if cgb_game else 0x04
        # measured by running the real CGB boot ROM on this board (2026-10-10, cgb-acid2): DIV
        # counter $1E9C, the PPU at line 144 dot 164, white background palettes. FITTED to that
        # run for a CGB game; the compatibility-mode values are the same, unmeasured.
        self.timer.counter = 0x1E9C
        self.serial.sc = 0
        self.dma.register = 0xFF
        ppu.bgp = 0xFC
        for entry in range(8):
            ppu.bg_pal[entry * 8 : entry * 8 + 8] = b"\xff\x7f" * 4
        ppu.bcps, ppu.ocps = 0x80, 0x81
        ppu.write_lcdc(0x91)
        ppu.stat_select = 0
        ppu.place(144, 164, 1)
        self.apu.skip_boot()
        self.boot_mapped = False

    # ----- time ---------------------------------------------------------------------------

    def _timer_irq(self, bit: int) -> None:
        """The timer's interrupt wakes a halted CPU TIMER_HALT_DELAY dots late (GBMicrotest
        int_timer_halt*)."""
        if TIMER_HALT_DELAY and self.cpu.halted:
            self._late.append([TIMER_HALT_DELAY, bit])
        else:
            self.cpu.request_interrupt(bit)

    def _serial_irq(self, bit: int) -> None:
        """The serial interrupt reaches the CPU's dispatch on time while IF shows it
        SERIAL_IF_HIDE dots later (FITTED: Gambatte serial/*_read_if_*)."""
        self.cpu.request_interrupt(bit)
        if SERIAL_IF_HIDE:
            self._hide |= 1 << bit
            self._hide_left = SERIAL_IF_HIDE

    def _ppu_irq(self, bit: int) -> None:
        """A PPU interrupt. A halted CPU sees the STAT ones a fitted number of dots after the PPU
        raises them (``ppu.irq_halt_delay``); the line-start OAM one reaches the CPU's dispatch a
        cycle before its IF bit shows."""
        if bit == 0 and self.cgb and VBLANK_CGB_DELAY:
            # CGB: the VBlank interrupt comes this many dots after the line-144 OAM one (Mooneye
            # misc/ppu/vblank_stat_intr-C; the DMG's are simultaneous)
            self._late.append([VBLANK_CGB_DELAY, 0])
            return
        delay = self.ppu.irq_halt_delay if bit == 1 and self.cpu.halted else 0
        # the dot within the M-cycle as it would be without the PPU's lead (IRQ_LEAD)
        sub = self.ppu.sub + (0 if self.double_speed else ppu_module.IRQ_LEAD)
        if bit == 1 and self.ppu.irq_defer:
            # raised in the dots after the access: the dispatch sees it a cycle later, as if the
            # PPU had no lead (IRQ_LEAD)
            self.ppu.irq_defer = False
            self._late.append([sub, bit, self.ppu.irq_early_by, self.ppu.irq_halt_delay])
            return
        if delay and sub + delay >= 4:
            self._late.append([sub + delay, bit])
            return
        if bit == 1 and self._halt_cycle:
            self._late.append([4, bit])  # HALT's second cycle sampled IF at its start
            return
        late = self._dispatch_late(bit, self.ppu.irq_early_by)
        self._m0_cancellable(bit, self.ppu.irq_early_by, deferred=False)
        self.cpu.request_interrupt(bit, halt_sees=bit == 1 and HALT_SEES_STAT, late=late)
        if self.ppu.sub >= IF_WRITE_PHASE:
            self._late_bits |= 1 << bit
        if bit in (0, 1) and self.ppu.irq_early_by:
            # the dispatch decision sees this interrupt a cycle early; reads of IF do not
            self._hide |= 1 << bit
            self._hide_left = self.ppu.irq_early_by

    def _dispatch_late(self, bit: int, early: int) -> bool:
        """An HBlank interrupt raised after the dot where a dispatch's low-byte push samples IF."""
        hblank = bit == 1 and early == ppu_module.HBLANK_IRQ_EARLY
        return hblank and self.ppu.sub >= DISPATCH_SAMPLE_DOT

    def _m0_cancellable(self, bit: int, early: int, deferred: bool) -> None:
        """An HBlank interrupt reaching IF before its source rises: a STAT write clearing bit 3
        later in this M-cycle cancels it (``ppu.M0_CANCEL_DMG``, ``ppu.M0_CANCEL_CGB``)."""
        if bit != 1 or early != ppu_module.HBLANK_IRQ_EARLY:
            return
        if self.cgb:
            sub = self.ppu.sub >= ppu_module.M0_CANCEL_CGB and not deferred
            self.ppu.m0_early = bool(ppu_module.M0_CANCEL_CGB) and sub
        else:
            self.ppu.m0_early = bool(ppu_module.M0_CANCEL_DMG)

    def _tick(self) -> None:
        """One M-cycle of the whole board."""
        dots = 2 if self.double_speed else 4  # the PPU and APU run at the single-speed rate
        self.t += dots
        self._late_bits = 0
        self.ppu.m0_early = False  # only a write in the M-cycle of the raise cancels it
        self.ppu.m0_hidden = 3 if self.ppu.m0_hidden == 2 else 0
        self.ppu.stat_fell = False
        if self._switch_wait:
            self._switch_wait -= 4
            if self.cpu.halted:
                self._switch_halted = True
            if self._switch_wait <= 0:
                self.cpu.halted = False
                self._switch_wait = 0
            elif self._switch_halted and not self.cpu.halted:
                self._switch_wait = 0  # an interrupt woke it first
        else:
            self._switch_halted = False
        if self._hide:
            self._hide_left -= 4
            if self._hide_left <= 0:
                self._hide = 0
        if self._late:
            held = []
            for item in self._late:
                item[0] -= 4
                if len(item) > 2:  # deferred past the lead: raised now, at dot item[0]
                    sub, bit, early, halt_delay = item
                    delay = halt_delay if self.cpu.halted else 0
                    if self._halt_cycle:
                        delay = 4 - sub  # HALT's second cycle sampled IF at its start
                    if sub + delay >= 4:
                        held.append([sub + delay, bit])  # a halted CPU sees it later still
                        continue
                    late = self._dispatch_late(bit, early)
                    self._m0_cancellable(bit, early, deferred=True)
                    halt_sees = bit == 1 and HALT_SEES_STAT
                    self.cpu.request_interrupt(bit, halt_sees=halt_sees, late=late)
                    self._late_bits |= 1 << bit
                    if early:
                        self._hide |= 1 << bit
                        self._hide_left = early
                elif item[0] < 4:
                    self.cpu.request_interrupt(item[1])
                else:
                    held.append(item)
            self._late = held
        timer = self.timer
        if self._div_reset_due:
            self._div_reset_due = False
            timer.tick()
            self._write_div()
            timer.previous = timer.counter  # the reset's falling edges were counted by _write_div
        elif self._div_hold:
            self._div_hold -= 1
            timer.tick(0)
        else:
            timer.tick()
        apu_bit = 0x2000 if self.double_speed else 0x1000
        if timer.previous & apu_bit and not timer.counter & apu_bit:
            self.apu.frame_tick()  # DIV-APU: a falling edge of the system counter's bit 12 (13)
        elif not timer.previous & apu_bit and timer.counter & apu_bit:
            self.apu.secondary_tick()  # and the rising edge half a period later
        self.apu.tick(dots)
        self.serial.tick(timer.previous, timer.counter)
        if self._lcd_freeze:
            held = min(dots, self._lcd_freeze)
            self._lcd_freeze -= held
            self.ppu.tick(dots - held)
        else:
            self.ppu.tick(dots)
        self.dma.tick()
        if self.hdma_hblank:
            mode = self.ppu.mode
            lag = HDMA_HBLANK_LAG_DS if self.double_speed else HDMA_HBLANK_LAG
            if mode == 0 and self.ppu.mode0_dots < lag:
                mode = 3
            if mode == 0 and self._last_mode != 0 and self.ppu.lcd_on:
                self.hdma_due = True  # an HBlank transfer's next block
            self._last_mode = mode

    def _idle(self, address: int) -> None:
        self._tick()
        self._bug(address, OAM_IDLE_KIND if self.cpu.idu else None)
        self.ppu.after_access()
        self.timer.finish()

    def _write_div(self) -> None:
        """Writing DIV clears the counter: a high bit 12 falls, which ticks DIV-APU."""
        if self.timer.counter & (0x2000 if self.double_speed else 0x1000):
            self.apu.frame_tick()
        if SERIAL_DIV_EDGE:
            self.serial.div_reset(self.timer.counter)
        self.timer.write_div()

    def _stop(self, pending: bool):
        """STOP on a DMG: it stops the oscillator and clears DIV; an interrupt that is already
        pending makes it a one-byte no-op (SonoSooS "NOP and STOP"; SameBoy stop()). The joypad
        interrupt wakes it. On a CGB in CGB mode with KEY1 bit 0 set (and no button held) it
        switches speed instead: the CPU halts for SPEED_SWITCH_HALT units unless an interrupt
        wakes it first (SameBoy stop())."""
        if self.cgb and self.ppu.cgb_mode and self.key1 & 1 and self.joypad.read() & 0x0F == 0x0F:
            # the switch clears DIV like any STOP (Gambatte stop(), SameBoy), at the end of STOP's
            # operand read: a counter bit that is still high there makes its falling edge
            # (Gambatte speedchange*_tima _1/_2 pairs move STOP by one M-cycle). With IME off the
            # CPU then holds the reset one M-cycle more (SameBoy enter_stop_mode;
            # Gambatte speedchange*_div pairs).
            if pending:
                self._write_div()
            else:
                self._div_reset_due = True
            self._div_hold = not self.cpu.ime
            self.double_speed = not self.double_speed
            self.ppu.double_speed = self.double_speed
            self.ppu.ly_lead = False
            self.key1 = 0
            # the PPU runs IRQ_LEAD dots ahead of the access in single speed, none in double
            lead = ppu_module.IRQ_LEAD
            skew = SWITCH_LCD_DS - lead if self.double_speed else SWITCH_LCD_SS + lead
            if skew > 0:
                self.ppu.run_dots(skew)
            elif skew < 0:
                self._lcd_freeze = -skew  # the LCD stands still this many dots
            if pending:
                return StopResult(StopAction.NOP, consume_operand=False)
            self._switch_wait = SPEED_SWITCH_HALT if not self.double_speed else SPEED_SWITCH_HALT_TO_DOUBLE
            return StopResult(StopAction.HALT)
        if pending:
            return StopResult(StopAction.NOP, consume_operand=False)
        self._write_div()
        return StopResult(StopAction.STOP)

    # ----- the bus ------------------------------------------------------------------------

    def _bug(self, address: int, kind: str | None) -> None:
        if kind and self.machine.oam_bug and 0xFE00 <= address <= 0xFEFF:
            self.ppu.corrupt_oam(kind)

    def _read(self, address: int) -> int:
        cpu = self.cpu
        self._halt_cycle = bool(HALT_CYCLE_HALTED and not cpu.idu and address == cpu.pc
                                and self.peek((address - 1) & 0xFFFF) == 0x76)
        self._tick()
        self._halt_cycle = False
        self._bug(address, "readinc" if self.cpu.idu else "read")
        value = self._load(address)
        self.ppu.after_access()
        self.timer.finish()
        if self._hdma_at_fetch:
            self._hdma_at_fetch = False
            if self.hdma_due:
                self._hdma_run()
        return value

    def _write(self, address: int, value: int) -> None:
        self._tick()
        self._bug(address, "write")
        dma = self.dma
        if dma.active and dma.index and self.machine.cgb_hardware:
            if self._cgb_dma_conflict(address):
                self._cgb_dma_write(address, value)
                self.ppu.after_access()
                self.timer.finish()
                return
        elif dma.active and dma.index:
            if address < 0xFE00 and bus_of(address) == dma.bus != INTERNAL:
                # a CPU write on the bus the DMA is reading never reaches memory; the byte lands
                # in OAM instead: as written from a cartridge source, ANDed with the DMA's byte
                # from WRAM (DMG; Gambatte oamdma_src*_busypush*)
                if dma.base < 0xC0:
                    self.ppu.oam[dma.index - 1] = value
                else:
                    self.ppu.oam[dma.index - 1] &= value
                self.ppu.after_access()
                self.timer.finish()
                return
        self._store(address, value)
        self.ppu.after_access()
        self.timer.finish()

    def _load(self, address: int) -> int:
        """What the CPU reads at ``address`` this M-cycle."""
        dma = self.dma
        if dma.active and self.machine.cgb_hardware:
            if self._cgb_dma_conflict(address):
                return self._cgb_dma_read(address)
        if dma.active:
            if 0xFE00 <= address < 0xFF00:
                # reads of the whole $FExx page return $FF while the DMA owns OAM (Gambatte
                # oamdma_src*_busypopFE9F/FEFF read $FEA0 and $FEFF as $FF, DMG-08)
                return 0xFF
            if (address < 0xFE00 and bus_of(address) == dma.bus != INTERNAL
                    and not self.machine.cgb_hardware):
                return dma.byte  # bus conflict: the CPU gets the DMA's byte
        return self.peek(address)

    def _boot_at(self, address: int) -> bool:
        """The boot ROM covers $0000-$00FF, and on a CGB $0200-$08FF too."""
        return self.boot_mapped and (address < 0x100 or (self.cgb and 0x200 <= address < 0x900))

    def _wram_index(self, address: int) -> int:
        """Offset into WRAM; $D000-$DFFF (and its echo) is the SVBK bank in CGB mode."""
        index = address & 0x0FFF
        if address & 0x1000:
            return (self.svbk << 12) | index
        return index

    def peek(self, address: int) -> int:
        """The byte at ``address`` as the CPU would read it now, with no side effects and no
        DMA conflict (debuggers, harnesses)."""
        if address < 0x8000:
            if self._boot_at(address):
                return self.boot_rom[address]  # type: ignore[index]
            value = self.cartridge.read(address, self.t)
            return 0xFF if value is None else value
        if address < 0xA000:
            if self.ppu.vram_locked:
                return 0xFF
            return self.ppu.vram[address - 0x8000 + (self.ppu.vram_bank << 13)]
        if address < 0xC000:
            value = self.cartridge.read(address, self.t)
            return 0xFF if value is None else value
        if address < 0xFE00:
            return self.wram[self._wram_index(address)]
        if address < 0xFEA0:
            return 0xFF if self.ppu.oam_locked else self.ppu.oam[address - 0xFE00]
        if address < 0xFF00:
            if self.ppu.oam_locked:
                return 0xFF
            return self._fea0(address)
        if address < 0xFF80:
            return self._io_read(address)
        if address < 0xFFFF:
            return self.hram[address - 0xFF80]
        return self.cpu.ie

    def _fea0(self, address: int) -> int:
        """$FEA0-$FEFF with OAM free: $00 on a DMG; on CGB E the high nibble of the low address
        byte twice; before E a RAM area masked per revision (not modelled: reads as that)."""
        kind = self.machine.fea0_read
        if kind == "high_nibble_twice":
            nibble = (address >> 4) & 0xF
            return nibble | (nibble << 4)
        return 0x00

    def _store(self, address: int, value: int) -> None:
        if address < 0x8000:
            self.cartridge.write(address, value, self.t)
        elif address < 0xA000:
            if not self.ppu.vram_write_locked:
                self.ppu.vram[address - 0x8000 + (self.ppu.vram_bank << 13)] = value
        elif address < 0xC000:
            self.cartridge.write(address, value, self.t)
        elif address < 0xFE00:
            self.wram[self._wram_index(address)] = value
        elif address < 0xFEA0:
            if not self.ppu.oam_write_locked and not self.dma.active:
                self.ppu.oam[address - 0xFE00] = value
        elif address < 0xFF00:
            pass  # unusable
        elif address < 0xFF80:
            self._io_write(address, value)
        elif address < 0xFFFF:
            self.hram[address - 0xFF80] = value
        # $FFFF: the core owns IE and has already stored it

    # ----- DMA hooks ----------------------------------------------------------------------

    # Gambatte's CGB conflict map (memptrs.cpp): which 4 KiB regions the CPU shares with the DMA
    # by the kind of source; bit n = region $n000.
    _CGB_CONFLICT = {"rom": 0xFCFF, "sram": 0xFCFF, "vram": 0x0300, "wram": 0xF000, "bad": 0xFCFF}

    def _cgb_dma_kind(self) -> str:
        page = self.dma.base
        if page < 0x80:
            return "rom"
        if page < 0xA0:
            return "vram"
        if page < 0xC0:
            return "sram"
        return "wram" if page < 0xE0 else "bad"

    def _cgb_dma_conflict(self, address: int) -> bool:
        return address < 0xFE00 and bool(self._CGB_CONFLICT[self._cgb_dma_kind()] >> (address >> 12) & 1)

    def _dma_wram_index(self, address: int) -> int:
        # the WRAM half is named by bit 4 of the DMA page, not by SVBK's bank at $C000
        if (self.dma.base >> 4) & 1:
            return (self.svbk << 12) | (address & 0xFFF)
        return address & 0xFFF

    def _cgb_dma_read(self, address: int) -> int:
        # the CPU gets the byte the DMA just moved; from $C000 up and a non-WRAM source it reads
        # WRAM instead (Gambatte nontrivial_read)
        kind = self._cgb_dma_kind()
        if kind != "wram" and address >= 0xC000:
            return self.wram[self._dma_wram_index(address)]
        value = self.ppu.oam[self.dma.index - 1]
        if kind == "vram":
            self.ppu.oam[self.dma.index - 1] = 0
        return value

    def _cgb_dma_write(self, address: int, value: int) -> None:
        kind = self._cgb_dma_kind()
        if address < 0xC000:
            self.ppu.oam[self.dma.index - 1] = 0 if kind == "vram" else value
        elif kind != "wram":
            self.wram[self._dma_wram_index(address)] = value

    def _dma_source(self, address: int) -> int:
        """A DMA source read, on the bus the source page is on (no locks apply)."""
        if self.cgb and self.dma.base >= 0xE0:
            return 0xFF  # CGB: sources from $E0 up are invalid (Gambatte oam_dma_src_invalid)
        if self._boot_at(address):
            value = self.boot_rom[address]  # type: ignore[index]
        elif address < 0x8000 or 0xA000 <= address < 0xC000:
            value = self.cartridge.read(address, self.t)
            value = 0xFF if value is None else value
        elif address < 0xA000:
            value = self.ppu.vram[address - 0x8000 + (self.ppu.vram_bank << 13)]
        else:
            value = self.wram[self._wram_index(address)]
        return value

    def _dma_write(self, index: int, value: int) -> None:
        self.ppu.oam[index] = value

    # ----- I/O registers ------------------------------------------------------------------

    def _io_read(self, address: int) -> int:
        low = address & 0xFF
        if low >= 0x10 and low <= 0x3F:
            return self.apu.read(address)
        ppu = self.ppu
        if low == 0x00:
            return self.joypad.read()
        if low == 0x01:
            return self.serial.sb
        if low == 0x02:
            self.serial.cgb_mode = self.ppu.cgb_mode
            return self.serial.read_sc()
        if low == 0x04:
            return self.timer.read_div()
        if low == 0x05:
            return self.timer.tima
        if low == 0x06:
            return self.timer.tma
        if low == 0x07:
            return 0xF8 | self.timer.tac
        if low == 0x0F:
            return 0xE0 | (self.cpu.if_ & ~self._hide)
        if low == 0x40:
            return ppu.lcdc
        if low == 0x41:
            return ppu.read_stat()
        if low == 0x42:
            return ppu.scy
        if low == 0x43:
            return ppu.scx
        if low == 0x44:
            return ppu.read_ly()
        if low == 0x45:
            return ppu.lyc
        if low == 0x46:
            return self.dma.register
        if low == 0x47:
            return ppu.bgp
        if low == 0x48:
            return ppu.obp0
        if low == 0x49:
            return ppu.obp1
        if low == 0x4A:
            return ppu.wy
        if low == 0x4B:
            return ppu.wx
        if self.cgb:
            return self._cgb_io_read(low)
        return 0xFF  # unmapped registers read 1 (Mooneye bits/unused_hwio-GS)

    def _cgb_io_read(self, low: int) -> int:
        """The registers only a CGB has (SameBoy ``GB_read_memory``, Pan Docs CGB_Registers.md);
        outside CGB mode most read $FF."""
        ppu = self.ppu
        mode = ppu.cgb_mode
        if low == 0x4D:
            return (self.key1 & 1) | 0x7E | (0x80 if self.double_speed else 0) if mode else 0xFF
        if low == 0x4F:
            return 0xFE | ppu.vram_bank
        if low == 0x50:
            return 0xFE | (not self.boot_mapped)
        if low == 0x55:
            active = self.hdma_blocks and (self.hdma_hblank or self.hdma_due)
            return ((0 if active else 0x80) | ((self.hdma_blocks - 1) & 0x7F)) if mode else 0xFF
        if low == 0x56:
            return (self.rp & 0xC1) | 0x3E if mode else 0xFF
        if low in (0x68, 0x6A):
            return (ppu.ocps if low == 0x6A else ppu.bcps) | 0x40
        if low in (0x69, 0x6B):
            if not mode and not self.boot_mapped:
                return 0xFF
            return ppu.read_palette(low == 0x6B)
        if low == 0x6C:
            return 0xFE | self.opri_register
        if low == 0x70:
            return 0xF8 | self.svbk_register if mode else 0xFF
        if low in (0x72, 0x73):
            return self.undocumented[low - 0x72]
        if low == 0x74:
            return self.undocumented[2] if mode else 0xFF
        if low == 0x75:
            return self.undocumented[3] | 0x8F
        if low in (0x76, 0x77):
            return self.apu.pcm(low - 0x76)
        return 0xFF

    def _io_write(self, address: int, value: int) -> None:
        low = address & 0xFF
        if low >= 0x10 and low <= 0x3F:
            self.apu.frame_clock_high = bool(self.timer.counter & 0x1000)
            self.apu.write(address, value)
        elif low == 0x00:
            self.joypad.write(value)
        elif low == 0x01:
            self.serial.write_sb(value)
        elif low == 0x02:
            self.serial.cgb_mode = self.ppu.cgb_mode
            if SERIAL_SC_CANCEL and self._hide & 8:
                # the transfer has not ended yet: the write stops it before its interrupt
                self.cpu.if_ &= ~8
                self._hide &= ~8
                self.serial.cancel_finish()
            self.serial.write_sc(value)
        elif low == 0x04:
            self._write_div()
        elif low == 0x05:
            self.timer.write_tima(value)
        elif low == 0x06:
            self.timer.write_tma(value)
        elif low == 0x07:
            self.timer.write_tac(value)
        elif low == 0x0F:
            # an interrupt raised late in this very cycle is not cleared by the write
            # nor is a serial interrupt still hidden: it has not happened yet (Gambatte flags it
            # at the end of the hiding)
            self.cpu.if_ = (value & 0x1F) | self._late_bits | (self.cpu.if_ & self._hide & 8)
        elif low == 0x40:
            self.ppu.write_lcdc(value)
        elif low == 0x41:
            if self.ppu.write_stat(value):  # cancelled an interrupt raised early
                self.cpu.if_ &= ~2
                self._hide &= ~2
        elif low == 0x42:
            self.ppu.scy = value
        elif low == 0x43:
            self.ppu.scx = value
        elif low == 0x45:
            if self.ppu.write_lyc(value):  # cancelled an LY=LYC interrupt raised early
                self.cpu.if_ &= ~2
                self._hide &= ~2
        elif low == 0x46:
            self.dma.start(value)
        elif low == 0x47:
            self.ppu.write_bgp(value)
        elif low == 0x48:
            self.ppu.obp0 = value
        elif low == 0x49:
            self.ppu.obp1 = value
        elif low == 0x4A:
            self.ppu.wy = value
            self.ppu.compare_wy()
        elif low == 0x4B:
            self.ppu.wx = value
        elif low == 0x50 and value & 1 and self.boot_mapped:
            self.boot_mapped = False  # the boot ROM switches itself off; it cannot come back
        elif self.cgb:
            self._cgb_io_write(low, value)

    def _cgb_io_write(self, low: int, value: int) -> None:
        ppu = self.ppu
        mode = ppu.cgb_mode
        if low == 0x4C:
            if self.boot_mapped:
                ppu.cgb_mode = not value & 0xC  # the boot ROM tells the PPU which mode to be in
                self.key0 = value
        elif low == 0x4D:
            if mode:
                self.key1 = value & 1
        elif low == 0x4F:
            if mode:
                ppu.vram_bank = value & 1
        elif 0x51 <= low <= 0x54:
            if mode:
                self._hdma_address(low, value)
        elif low == 0x55:
            if mode:
                self._hdma_control(value)
        elif low == 0x56:
            self.rp = value
        elif low in (0x68, 0x6A):
            if low == 0x6A:
                ppu.ocps = value
            else:
                ppu.bcps = value
        elif low in (0x69, 0x6B):
            if mode or self.boot_mapped:
                ppu.write_palette(low == 0x6B, value)
        elif low == 0x6C:
            if self.boot_mapped or self.key0 & 8:
                self.opri_register = value & 1
                ppu.opri = value & 1
            elif mode:
                self.opri_register = value & 1
        elif low == 0x70:
            if mode or self.boot_mapped:
                self.svbk_register = value & 7
                self.svbk = value & 7 or 1
        elif low in (0x72, 0x73):
            self.undocumented[low - 0x72] = value
        elif low == 0x74:
            if mode:
                self.undocumented[2] = value
        elif low == 0x75:
            self.undocumented[3] = value & 0x70

    def _hdma_address(self, low: int, value: int) -> None:
        if low == 0x51:
            self.hdma_src = (self.hdma_src & 0x00F0) | (value << 8)
            if self.hdma_src >= 0xE000:
                self.hdma_src |= 0xF000
        elif low == 0x52:
            self.hdma_src = (self.hdma_src & 0xFF00) | (value & 0xF0)
        elif low == 0x53:
            self.hdma_dst = (self.hdma_dst & 0x00F0) | ((value & 0x1F) << 8)
        else:
            self.hdma_dst = (self.hdma_dst & 0xFF00) | (value & 0xF0)

    def _hdma_control(self, value: int) -> None:
        """$FF55: bit 7 chooses HBlank (1) or general (0); bits 6-0 are the length in 16-byte blocks
        minus one. Clearing bit 7 while an HBlank transfer runs stops it. An HBlank transfer
        armed in mode 0 runs its first block at once, also with the LCD off, where no further
        HBlank comes (SameSuite ``hdma_lcd_off``, ``gdma_addr_mask``)."""
        self.hdma_blocks = (value & 0x7F) + 1
        if not value & 0x80 and self.hdma_hblank:
            self.hdma_hblank = False
            return
        self.hdma_hblank = bool(value & 0x80)
        if not self.hdma_hblank or self.ppu.read_mode == 0:
            self.hdma_due = True

    # ----- running ------------------------------------------------------------------------

    def step(self) -> int:
        """Execute one CPU boundary; returns the M-cycles it took (the units have already
        advanced inside the callbacks)."""
        cpu = self.cpu
        if self.hdma_due or self.hdma_hblank:
            pending = cpu.interrupt_pending
            # SameBoy GB_cpu_run: the transfer runs after the next opcode fetch, not on a
            # dispatch's discarded one; an HBlank block that falls due during the fetch included
            self._hdma_at_fetch = (not cpu.halted or pending) and not (cpu.ime and pending)
        return self._cpu_step()

    # ----- CGB DMA (HDMA/GDMA) --------------------------------------------------------------

    def _hdma_run(self) -> None:
        """Run the armed transfer's current block with the CPU stopped: 16 bytes at one byte per
        2 dots (SameBoy ``GB_hdma_run``: one M-cycle of start-up, 8 M-cycles a block at single
        speed, 16 at double). A general-purpose transfer runs every block back to back; an HBlank
        one a block per HBlank."""
        dma_dots = 4 if self.double_speed else 2  # units a byte takes: 4 make an M-cycle
        self.hdma_due = False
        self._hdma_wait(HDMA_START_DS if self.double_speed else HDMA_START)
        while self.hdma_blocks:
            for _ in range(16):
                byte = self._hdma_source(self.hdma_src)
                self._hdma_wait(dma_dots)
                self.ppu.vram[(self.ppu.vram_bank << 13) + (self.hdma_dst & 0x1FFF)] = byte
                self.hdma_src = (self.hdma_src + 1) & 0xFFFF
                self.hdma_dst = (self.hdma_dst + 1) & 0xFFFF
            self.hdma_blocks -= 1
            if not self.hdma_blocks:
                self.hdma_hblank = False
            if self.hdma_hblank:
                break
        if not self.double_speed:
            self._hdma_wait(HDMA_END)

    def _hdma_wait(self, units: int) -> None:
        """Advance the board ``units`` CPU units (4 per M-cycle) with the CPU stopped."""
        self._idle_units += units
        while self._idle_units >= 4:
            self._idle_units -= 4
            self._tick()
            self.ppu.after_access()
            self.timer.finish()

    def _hdma_source(self, address: int) -> int:
        """HDMA reads cartridge, VRAM-less sources only: ROM, cartridge RAM and WRAM (else $FF)."""
        if address < 0x8000 or 0xA000 <= address < 0xE000:
            return self._dma_source(address)
        return 0xFF

    def capture_state(self) -> CPUState:
        """The CPU's state, so a ``DebugSession`` can drive the board as its target; the
        board's own registers are in ``state.capture_board_state``."""
        return self.cpu.capture_state()

    def run_frames(self, frames: int, max_steps: int = 50_000_000) -> None:
        """Run until the PPU has completed ``frames`` more VBlanks."""
        target = self.ppu.frames + frames
        steps = 0
        while self.ppu.frames < target and steps < max_steps:
            self.cpu.step()
            steps += 1


__all__ = ["EXTERNAL", "INTERNAL", "VIDEO", "GameBoy"]
