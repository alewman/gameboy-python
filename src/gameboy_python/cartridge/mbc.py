"""Memory bank controllers behind the connector protocol (docs/cartridge.md).

``read``/``write`` take the full 16-bit external-bus address and the board's T-cycle count; a
read returns ``None`` for an open bus. These classes import nothing from the rest of the board
(a test enforces it).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from gameboy_python.cartridge.header import Header


class Cartridge:
    """A cartridge with a plain ROM and optional RAM, and no banking: the base of every MBC.

    ROM-only boards ignore writes to ROM space; ``mapper`` boards override :meth:`write`.
    """

    def __init__(self, rom: bytes, header: Header) -> None:
        self.header = header
        self.rom = bytes(rom) + bytes(max(0, 0x8000 - len(rom)))
        self.ram = bytearray(header.ram_bytes)

    def read(self, address: int, t: int) -> int | None:
        if address < 0x8000:
            return self.rom[address]
        if 0xA000 <= address < 0xC000 and self.ram:
            return self.ram[(address - 0xA000) % len(self.ram)]
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if 0xA000 <= address < 0xC000 and self.ram:
            self.ram[(address - 0xA000) % len(self.ram)] = value

    def tick_to(self, t: int) -> None:
        """Clocked parts (the MBC3 RTC) catch up lazily; none here."""

    def vin(self, t: int) -> int:
        """The audio-in pin: no licensed board here drives it."""
        return 0

    def save_ram(self) -> bytes | None:
        """Battery-backed RAM to persist, or None."""
        return bytes(self.ram) if self.header.has_battery and self.ram else None

    def load_ram(self, data: bytes) -> None:
        self.ram[: len(data)] = data[: len(self.ram)]


class MBC1(Cartridge):
    """MBC1 (GBCTR mbc1 chapter, Pan Docs MBC1.md; Mooneye emulator-only/mbc1/* verify).

    Registers: RAMG ($0000-$1FFF, enable on low nibble $A), BANK1 ($2000-$3FFF, 5 bits, 0 reads
    as 1), BANK2 ($4000-$5FFF, 2 bits), MODE ($6000-$7FFF, 1 bit). The ROM address is
    ``BANK2:BANK1:A13..A0`` for $4000-$7FFF and ``BANK2:00000`` for $0000-$3FFF in mode 1.
    """

    def __init__(self, rom: bytes, header: Header, multicart: bool = False) -> None:
        super().__init__(rom, header)
        self.rom_mask = max(1, len(self.rom) // 0x4000) - 1
        self.ram_enabled = False
        self.bank1 = 1
        self.bank2 = 0
        self.mode = 0
        #: MBC1M wiring: BANK1's bit 4 is not connected and BANK2 sits at address bit 18
        self.multicart = multicart

    def _rom_bank(self, upper: bool) -> int:
        shift = 4 if self.multicart else 5
        bank1 = (self.bank1 & 0x0F) if self.multicart else self.bank1
        high = self.bank2 << shift if (upper or self.mode) else 0
        return (high | (bank1 if upper else 0)) & self.rom_mask

    def _ram_offset(self, address: int) -> int:
        bank = self.bank2 if self.mode else 0
        return ((bank << 13) | (address & 0x1FFF)) % len(self.ram)

    def read(self, address: int, t: int) -> int | None:
        if address < 0x4000:
            return self.rom[(self._rom_bank(False) << 14) | address]
        if address < 0x8000:
            return self.rom[(self._rom_bank(True) << 14) | (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            if self.ram_enabled and self.ram:
                return self.ram[self._ram_offset(address)]
            return 0xFF
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if address < 0x2000:
            self.ram_enabled = value & 0x0F == 0x0A
        elif address < 0x4000:
            self.bank1 = (value & 0x1F) or 1
        elif address < 0x6000:
            self.bank2 = value & 0x03
        elif address < 0x8000:
            self.mode = value & 1
        elif 0xA000 <= address < 0xC000 and self.ram_enabled and self.ram:
            self.ram[self._ram_offset(address)] = value


class MBC5(Cartridge):
    """MBC5 (Pan Docs MBC5.md; Mooneye emulator-only/mbc5/* verify on a genuine chip).

    RAMG ($0000-$1FFF, enabled only by exactly $0A), ROMB0 ($2000-$2FFF, 8 bits), ROMB1
    ($3000-$3FFF, bit 0 = bank bit 8), RAMB ($4000-$5FFF, 4 bits; bit 3 drives the rumble motor
    on rumble boards). Unlike MBC1, bank 0 can be selected for $4000-$7FFF.
    """

    def __init__(self, rom: bytes, header: Header) -> None:
        super().__init__(rom, header)
        self.rom_mask = max(1, len(self.rom) // 0x4000) - 1
        self.ram_enabled = False
        self.romb0 = 1
        self.romb1 = 0
        self.ramb = 0
        self.rumble = False

    def read(self, address: int, t: int) -> int | None:
        if address < 0x4000:
            return self.rom[address]
        if address < 0x8000:
            bank = ((self.romb1 << 8) | self.romb0) & self.rom_mask
            return self.rom[(bank << 14) | (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            if self.ram_enabled and self.ram:
                return self.ram[((self.ramb << 13) | (address & 0x1FFF)) % len(self.ram)]
            return 0xFF
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if address < 0x2000:
            self.ram_enabled = value == 0x0A
        elif address < 0x3000:
            self.romb0 = value
        elif address < 0x4000:
            self.romb1 = value & 1
        elif address < 0x6000:
            self.ramb = value & (0x07 if self.header.has_rumble else 0x0F)
            if self.header.has_rumble:
                self.rumble = bool(value & 0x08)
        elif 0xA000 <= address < 0xC000 and self.ram_enabled and self.ram:
            self.ram[((self.ramb << 13) | (address & 0x1FFF)) % len(self.ram)] = value


class MBC2(Cartridge):
    """MBC2 (Pan Docs MBC2.md; Mooneye emulator-only/mbc2/* verify on a genuine MBC2A chip).

    One register file for $0000-$3FFF, told apart by address bit 8: clear = RAMG (enable on low
    nibble $A), set = ROMB (4 bits, 0 reads as 1). Built-in 512 x 4-bit RAM at $A000-$A1FF,
    echoed through $BFFF; the upper nibble of a read is undefined (here: 1s).
    """

    def __init__(self, rom: bytes, header: Header) -> None:
        super().__init__(rom, header)
        self.ram = bytearray(512)
        self.rom_mask = max(1, len(self.rom) // 0x4000) - 1
        self.ram_enabled = False
        self.romb = 1

    def read(self, address: int, t: int) -> int | None:
        if address < 0x4000:
            return self.rom[address]
        if address < 0x8000:
            return self.rom[((self.romb & self.rom_mask) << 14) | (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            return (self.ram[address & 0x1FF] | 0xF0) if self.ram_enabled else 0xFF
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if address < 0x4000:
            if address & 0x100:
                self.romb = (value & 0x0F) or 1
            else:
                self.ram_enabled = value & 0x0F == 0x0A
        elif 0xA000 <= address < 0xC000 and self.ram_enabled:
            self.ram[address & 0x1FF] = value & 0x0F

    def save_ram(self) -> bytes | None:
        return bytes(self.ram) if self.header.has_battery else None


RTC_TRAILER = 48


class MBC3(Cartridge):
    """MBC3 with an optional real-time clock (Pan Docs MBC3.md; rtc3test and MBC3-Tester are
    detectors only: docs/cartridge.md).

    RAMG ($0000, $0A enables RAM *and* the clock registers), ROMB ($2000, 7 bits, 0 reads as 1),
    RAMB/RTC select ($4000, 4 bits: $0-$3 a RAM bank, $8-$C a clock register; on a clock board
    $4-$7 and $D-$F select nothing and read $FF), LATCH ($6000: any write copies the running
    clock into the readable registers; Pan Docs asks for 0 then 1, but CasualPokePlayer's
    latch-rtc-test latches with one write and rtc-invalid-banks-test gives the select's width and
    holes, both as the Emulator Shootout expects them and as SameBoy does). The clock runs on
    ``clock()`` (wall time by default; tests pass a fake) and stops while the halt bit is set.
    """

    def __init__(
        self, rom: bytes, header: Header, clock: Callable[[], float] | None = None
    ) -> None:
        super().__init__(rom, header)
        self.rom_mask = max(1, len(self.rom) // 0x4000) - 1
        self.ram_enabled = False
        self.romb = 1
        self.select = 0
        # the highest RAM bank the select reaches: on a clock board with up to four banks, 4-7
        # select nothing (an MBC30's eight banks are all there; without a clock they mirror)
        self.top_bank = 3 if header.has_timer and len(self.ram) <= 0x8000 else 7
        self.clock = clock or time.time
        # the five clock registers as the chip holds them (they can hold out-of-range values)
        self.live = [0, 0, 0, 0, 0]  # seconds, minutes, hours, day low, control (bits 0, 6, 7)
        self.stamp = self.clock()  # a tick boundary: the clock ticks at stamp + 1, + 2, ...
        self.frozen = 0.0  # the sub-second position kept while halted
        self.latched = (0, 0, 0, 0, 0)

    # ----- the clock ----------------------------------------------------------------------

    @property
    def halted(self) -> bool:
        return bool(self.live[4] & 0x40)

    def _tick_once(self) -> None:
        """One second. Valid fields carry as usual; an out-of-range field counts on to its bit
        limit and wraps *without* carrying (rtc3test "Invalid rollovers")."""
        live = self.live
        if live[0] == 59:
            live[0] = 0
        elif live[0] == 63:
            live[0] = 0
            return
        else:
            live[0] += 1
            return
        if live[1] == 59:
            live[1] = 0
        elif live[1] == 63:
            live[1] = 0
            return
        else:
            live[1] += 1
            return
        if live[2] == 23:
            live[2] = 0
        elif live[2] == 31:
            live[2] = 0
            return
        else:
            live[2] += 1
            return
        days = (live[3] | (live[4] & 1) << 8) + 1
        if days == 512:
            days = 0
            live[4] |= 0x80  # the overflow flag stays set until a write clears it
        live[3] = days & 0xFF
        live[4] = (live[4] & ~1) | (days >> 8)

    def _advance(self) -> None:
        if self.halted:
            return
        now = self.clock()
        ticks = int(now - self.stamp)
        if ticks <= 0:
            return
        live = self.live
        if live[0] < 60 and live[1] < 60 and live[2] < 24 and ticks > 3600:
            days = live[3] | (live[4] & 1) << 8
            total = ((days * 24 + live[2]) * 60 + live[1]) * 60 + live[0] + ticks
            days = total // 86400
            if days >= 512:
                live[4] |= 0x80
                days %= 512
            live[0], live[1], live[2] = total % 60, total // 60 % 60, total // 3600 % 24
            live[3] = days & 0xFF
            live[4] = (live[4] & ~1) | (days >> 8)
        else:
            for _ in range(min(ticks, 10_000_000)):
                self._tick_once()
        self.stamp += ticks

    def _registers(self) -> tuple[int, int, int, int, int]:
        self._advance()
        live = self.live
        return live[0], live[1], live[2], live[3], live[4]

    def _set_register(self, register: int, value: int) -> None:
        self._advance()
        live = self.live
        if register == 0x08:
            live[0] = value & 0x3F
            self.stamp = self.clock()  # a seconds write restarts the sub-second counter
        elif register == 0x09:
            live[1] = value & 0x3F
        elif register == 0x0A:
            live[2] = value & 0x1F
        elif register == 0x0B:
            live[3] = value
        else:
            was_halted = self.halted
            live[4] = value & 0xC1
            if self.halted and not was_halted:
                self.frozen = self.clock() - self.stamp
            elif was_halted and not self.halted:
                self.stamp = self.clock() - self.frozen

    # ----- the bus ------------------------------------------------------------------------

    def read(self, address: int, t: int) -> int | None:
        if address < 0x4000:
            return self.rom[address]
        if address < 0x8000:
            return self.rom[((self.romb & self.rom_mask) << 14) | (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            if not self.ram_enabled:
                return 0xFF
            if self.select <= self.top_bank:
                if self.ram:
                    return self.ram[((self.select << 13) | (address & 0x1FFF)) % len(self.ram)]
                return 0xFF
            if 0x08 <= self.select <= 0x0C and self.header.has_timer:
                return self.latched[self.select - 0x08]
            return 0xFF
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if address < 0x2000:
            self.ram_enabled = value & 0x0F == 0x0A
        elif address < 0x4000:
            self.romb = (value & 0x7F) or 1
        elif address < 0x6000:
            self.select = value & 0x0F
        elif address < 0x8000:
            if self.header.has_timer:
                self.latched = self._registers()
        elif 0xA000 <= address < 0xC000 and self.ram_enabled:
            if self.select <= self.top_bank:
                if self.ram:
                    self.ram[((self.select << 13) | (address & 0x1FFF)) % len(self.ram)] = value
            elif 0x08 <= self.select <= 0x0C and self.header.has_timer:
                self._set_register(self.select, value)

    # ----- persistence --------------------------------------------------------------------

    def save_ram(self) -> bytes | None:
        """RAM, then (with a timer) the 48-byte clock trailer BGB, SameBoy and mGBA share."""
        if not (self.header.has_battery and (self.ram or self.header.has_timer)):
            return None
        data = bytes(self.ram)
        if self.header.has_timer:
            live, latched = self._registers(), self.latched
            data += b"".join(v.to_bytes(4, "little") for v in live + latched)
            data += int(self.clock()).to_bytes(8, "little")
        return data

    def load_ram(self, data: bytes) -> None:
        super().load_ram(data[: len(self.ram)])
        if self.header.has_timer and len(data) >= len(self.ram) + RTC_TRAILER:
            raw = data[len(self.ram) : len(self.ram) + RTC_TRAILER]
            words = [int.from_bytes(raw[i : i + 4], "little") for i in range(0, 40, 4)]
            self.live = [w & 0xFF for w in words[:5]]
            self.latched = (words[5], words[6], words[7], words[8], words[9])
            saved_at = int.from_bytes(raw[40:48], "little")
            self.stamp = self.clock()
            self.frozen = 0.0
            if not self.halted:  # the battery kept it running while the console was off
                self.stamp -= max(0, self.stamp - saved_at)
                self._advance()


class MMM01(Cartridge):
    """MMM01 multi-game boards (Pan Docs MMM01.md; no judge is pinned: documents only).

    Starts "unmapped": the last 32 KiB of the ROM (the menu) sits at $0000-$7FFF. The menu writes
    the game-select bits and the masks, then sets the Mapping Enable bit, after which the chip acts
    as an MBC1 over the selected game and ignores the extra bits. Multiplex wiring is included.
    """

    def __init__(self, rom: bytes, header: Header) -> None:
        super().__init__(rom, header)
        self.banks = max(2, len(self.rom) // 0x4000)
        self.mapped = False
        self.ram_enabled = False
        self.ram_mask = 0  # RAM Bank Mask (2 bits)
        self.rom_low = 0  # 5 bits, reads as 1 when 0 after masking
        self.rom_mid = 0  # 2 bits
        self.rom_high = 0  # 2 bits
        self.ram_low = 0  # 2 bits
        self.ram_high = 0  # 2 bits
        self.mode_lock = False
        self.rom_mask_bits = 0  # ROM Bank Mask (5 bits, bit 0 always 0)
        self.multiplex = False
        self.mode = 0

    def _bank_low(self) -> int:
        masked = self.rom_low & ~self.rom_mask_bits & 0x1F
        return self.rom_low | 1 if masked == 0 else self.rom_low

    def _rom_bank(self, upper: bool) -> int:
        if not self.mapped:
            return (self.banks - 2 + (1 if upper else 0)) % self.banks
        if self.multiplex:
            mid = self.ram_low if upper or self.mode else self.ram_low & ~self.ram_mask & 3
            if not upper and not self.mode:
                mid = self.ram_low & ~self.ram_mask & 3
            low = self._bank_low() if upper else (self.rom_low & ~self.rom_mask_bits & 0x1F)
        else:
            mid = self.rom_mid
            low = self._bank_low() if upper else (self.rom_low & ~self.rom_mask_bits & 0x1F)
        return ((self.rom_high << 7) | (mid << 5) | low) % self.banks

    def _ram_offset(self, address: int) -> int:
        if self.multiplex:
            bank = (self.ram_high << 2) | self.rom_mid
        else:
            low = self.ram_low if self.mode else self.ram_low & ~self.ram_mask & 3
            bank = (self.ram_high << 2) | low
        return ((bank << 13) | (address & 0x1FFF)) % len(self.ram)

    def read(self, address: int, t: int) -> int | None:
        if address < 0x4000:
            return self.rom[(self._rom_bank(False) << 14) | address]
        if address < 0x8000:
            return self.rom[(self._rom_bank(True) << 14) | (address & 0x3FFF)]
        if 0xA000 <= address < 0xC000:
            if self.ram_enabled and self.ram:
                return self.ram[self._ram_offset(address)]
            return 0xFF
        return None

    def write(self, address: int, value: int, t: int) -> None:
        if address < 0x2000:
            self.ram_enabled = value & 0x0F == 0x0A
            if not self.mapped:
                self.ram_mask = (value >> 4) & 3
                self.mapped = bool(value & 0x40)
        elif address < 0x4000:
            keep = self.rom_mask_bits
            self.rom_low = (self.rom_low & keep) | (value & 0x1F & ~keep)
            if not self.mapped:
                self.rom_mid = (value >> 5) & 3
        elif address < 0x6000:
            lock = ~self.ram_mask & 3
            self.ram_low = (self.ram_low & ~lock & 3) | (value & 3 & lock)
            if not self.mapped:
                self.ram_high = (value >> 2) & 3
                self.rom_high = (value >> 4) & 3
                self.mode_lock = bool(value & 0x40)
        elif address < 0x8000:
            if not self.mode_lock or not self.mapped:
                self.mode = value & 1
            if not self.mapped:
                self.rom_mask_bits = value & 0x3E
                self.multiplex = bool(value & 0x40)
        elif 0xA000 <= address < 0xC000 and self.ram_enabled and self.ram:
            self.ram[self._ram_offset(address)] = value
