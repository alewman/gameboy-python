"""Memory bank controllers behind the connector protocol (docs/cartridge.md).

``read``/``write`` take the full 16-bit external-bus address and the board's T-cycle count; a
read returns ``None`` for an open bus. These classes import nothing from the rest of the board
(a test enforces it).
"""

from __future__ import annotations

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
