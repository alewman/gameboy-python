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

from gameboy_python.apu import APU
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
        self.t = 0  # T-cycles since power-on
        self.wram = bytearray(0x2000)
        self.hram = bytearray(0x7F)
        self.boot_rom = bytes(boot_rom) if boot_rom is not None else None
        self.boot_mapped = self.boot_rom is not None
        if self.boot_rom is not None and len(self.boot_rom) != 0x100:
            raise ValueError("a DMG boot ROM is 256 bytes")

        self.cpu = SM83(self._read, self._write, self._idle, stop=self._stop)
        raise_irq = self.cpu.request_interrupt
        self.timer = Timer(raise_irq, machine.tac_disable_glitch)
        # The counter's power-on phase: DIV reads in Mooneye boot_div-dmgABCmgb need the counter
        # 4 T ahead of the M-cycle count since reset (fitted; the only phase that passes it)
        self.timer.counter = 4
        self.serial = Serial(raise_irq)
        self.joypad = Joypad(raise_irq)
        self.ppu = PPU(raise_irq, machine.stat_write_glitch)
        self.apu = APU()
        self.dma = OamDma(self._dma_source, self._dma_write)
        if self.boot_rom is None:
            self._skip_boot()

    # ----- power-on -----------------------------------------------------------------------

    def _skip_boot(self) -> None:
        """The state the DMG boot ROM leaves at $0100 (Pan Docs Power_Up_Sequence.md)."""
        header = self.cartridge.header
        f = 0x80 | (0x30 if header.header_checksum != 0 else 0)
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
        self.ppu.place(153, 392, 1)
        for address, value in (
            (0x10, 0x80), (0x11, 0xBF), (0x12, 0xF3), (0x13, 0xFF), (0x14, 0xBF),
            (0x16, 0x3F), (0x17, 0x00), (0x18, 0xFF), (0x19, 0xBF),
            (0x1A, 0x7F), (0x1B, 0xFF), (0x1C, 0x9F), (0x1D, 0xFF), (0x1E, 0xBF),
            (0x20, 0xFF), (0x21, 0x00), (0x22, 0x00), (0x23, 0xBF),
            (0x24, 0x77), (0x25, 0xF3), (0x26, 0xF1),
        ):  # fmt: skip
            self.apu.power = True
            self.apu.write(0xFF00 | address, value)
        self.boot_mapped = False

    # ----- time ---------------------------------------------------------------------------

    def _tick(self) -> None:
        """One M-cycle of the whole board."""
        self.t += 4
        timer = self.timer
        timer.tick()
        self.serial.tick(timer.previous, timer.counter)
        self.ppu.tick()
        self.dma.tick()

    def _idle(self, address: int) -> None:
        self._tick()
        self.timer.finish()

    def _stop(self, pending: bool):
        """STOP on a DMG: it stops the oscillator and clears DIV; an interrupt that is already
        pending makes it a one-byte no-op (SonoSooS "NOP and STOP"; SameBoy stop()). The joypad
        interrupt wakes it. CGB speed switching is phase 2."""
        if pending:
            return StopResult(StopAction.NOP, consume_operand=False)
        self.timer.write_div()
        return StopResult(StopAction.STOP)

    # ----- the bus ------------------------------------------------------------------------

    def _read(self, address: int) -> int:
        self._tick()
        value = self._load(address)
        self.timer.finish()
        return value

    def _write(self, address: int, value: int) -> None:
        self._tick()
        self._store(address, value)
        self.timer.finish()

    def _load(self, address: int) -> int:
        """What the CPU reads at ``address`` this M-cycle."""
        dma = self.dma
        if dma.active:
            if 0xFE00 <= address < 0xFEA0:
                return 0xFF  # OAM reads return $FF while the DMA owns it
            if address < 0xFE00 and bus_of(address) == dma.bus != INTERNAL:
                return dma.byte  # bus conflict: the CPU gets the DMA's byte
        return self.peek(address)

    def peek(self, address: int) -> int:
        """The byte at ``address`` as the CPU would read it now, with no side effects and no
        DMA conflict (debuggers, harnesses)."""
        if address < 0x8000:
            if address < 0x100 and self.boot_mapped:
                return self.boot_rom[address]  # type: ignore[index]
            value = self.cartridge.read(address, self.t)
            return 0xFF if value is None else value
        if address < 0xA000:
            return 0xFF if self.ppu.vram_locked else self.ppu.vram[address - 0x8000]
        if address < 0xC000:
            value = self.cartridge.read(address, self.t)
            return 0xFF if value is None else value
        if address < 0xFE00:
            return self.wram[address & 0x1FFF]
        if address < 0xFEA0:
            return 0xFF if self.ppu.oam_locked else self.ppu.oam[address - 0xFE00]
        if address < 0xFF00:
            return 0xFF if self.ppu.oam_locked else 0x00  # DMG: $00 when OAM is free
        if address < 0xFF80:
            return self._io_read(address)
        if address < 0xFFFF:
            return self.hram[address - 0xFF80]
        return self.cpu.ie

    def _store(self, address: int, value: int) -> None:
        if address < 0x8000:
            self.cartridge.write(address, value, self.t)
        elif address < 0xA000:
            if not self.ppu.vram_write_locked:
                self.ppu.vram[address - 0x8000] = value
        elif address < 0xC000:
            self.cartridge.write(address, value, self.t)
        elif address < 0xFE00:
            self.wram[address & 0x1FFF] = value
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

    def _dma_source(self, address: int) -> int:
        """A DMA source read, on the bus the source page is on (no locks apply)."""
        if address < 0x100 and self.boot_mapped:
            value = self.boot_rom[address]  # type: ignore[index]
        elif address < 0x8000 or 0xA000 <= address < 0xC000:
            value = self.cartridge.read(address, self.t)
            value = 0xFF if value is None else value
        elif address < 0xA000:
            value = self.ppu.vram[address - 0x8000]
        else:
            value = self.wram[address & 0x1FFF]
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
            return 0xE0 | self.cpu.if_
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
        return 0xFF  # unmapped registers read 1 (Mooneye bits/unused_hwio-GS)

    def _io_write(self, address: int, value: int) -> None:
        low = address & 0xFF
        if low >= 0x10 and low <= 0x3F:
            self.apu.write(address, value)
        elif low == 0x00:
            self.joypad.write(value)
        elif low == 0x01:
            self.serial.write_sb(value)
        elif low == 0x02:
            self.serial.write_sc(value)
        elif low == 0x04:
            self.timer.write_div()
        elif low == 0x05:
            self.timer.write_tima(value)
        elif low == 0x06:
            self.timer.write_tma(value)
        elif low == 0x07:
            self.timer.write_tac(value)
        elif low == 0x0F:
            self.cpu.if_ = value & 0x1F
        elif low == 0x40:
            self.ppu.write_lcdc(value)
        elif low == 0x41:
            self.ppu.write_stat(value)
        elif low == 0x42:
            self.ppu.scy = value
        elif low == 0x43:
            self.ppu.scx = value
        elif low == 0x45:
            self.ppu.write_lyc(value)
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
        elif low == 0x4B:
            self.ppu.wx = value
        elif low == 0x50 and value and self.boot_mapped:
            self.boot_mapped = False  # the boot ROM switches itself off; it cannot come back

    # ----- running ------------------------------------------------------------------------

    def step(self) -> int:
        """Execute one CPU boundary; returns the M-cycles it took (the units have already
        advanced inside the callbacks)."""
        return self.cpu.step()

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
