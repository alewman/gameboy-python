"""The cartridge header at $0100-$014F (Pan Docs The_Cartridge_Header.md)."""

from __future__ import annotations

from dataclasses import dataclass

#: header byte $0147 -> (board, has RAM, has battery, has timer, has rumble); Pan Docs table.
CARTRIDGE_TYPES: dict[int, tuple[str, bool, bool, bool, bool]] = {
    0x00: ("rom", False, False, False, False),
    0x01: ("mbc1", False, False, False, False),
    0x02: ("mbc1", True, False, False, False),
    0x03: ("mbc1", True, True, False, False),
    0x05: ("mbc2", False, False, False, False),
    0x06: ("mbc2", False, True, False, False),
    0x08: ("rom", True, False, False, False),
    0x09: ("rom", True, True, False, False),
    0x0B: ("mmm01", False, False, False, False),
    0x0C: ("mmm01", True, False, False, False),
    0x0D: ("mmm01", True, True, False, False),
    0x0F: ("mbc3", False, True, True, False),
    0x10: ("mbc3", True, True, True, False),
    0x11: ("mbc3", False, False, False, False),
    0x12: ("mbc3", True, False, False, False),
    0x13: ("mbc3", True, True, False, False),
    0x19: ("mbc5", False, False, False, False),
    0x1A: ("mbc5", True, False, False, False),
    0x1B: ("mbc5", True, True, False, False),
    0x1C: ("mbc5", False, False, False, True),
    0x1D: ("mbc5", True, False, False, True),
    0x1E: ("mbc5", True, True, False, True),
}

#: header byte $0149 -> cartridge RAM bytes (Pan Docs)
RAM_SIZES = {0: 0, 1: 0x800, 2: 0x2000, 3: 0x8000, 4: 0x20000, 5: 0x10000}

NINTENDO_LOGO_START = bytes.fromhex("CEED6666CC0D000B03730083000C000D")


@dataclass(frozen=True, slots=True)
class Header:
    """The parts of the header a board needs."""

    title: str
    cartridge_type: int
    board: str  # "rom", "mbc1", ... or "unknown"
    rom_banks: int  # 16 KiB banks
    ram_bytes: int
    has_battery: bool
    has_timer: bool
    has_rumble: bool
    cgb_flag: int
    sgb_flag: int
    header_checksum: int  # the byte stored at $014D
    checksum_ok: bool  # the boot ROM locks up if this is wrong
    logo_ok: bool

    @property
    def cgb_only(self) -> bool:
        return self.cgb_flag == 0xC0

    @property
    def cgb_enhanced(self) -> bool:
        return self.cgb_flag in (0x80, 0xC0)


def parse_header(rom: bytes) -> Header:
    """Decode the header of ``rom``; a ROM shorter than $0150 gets a zero header."""
    data = bytes(rom[:0x150]) + bytes(max(0, 0x150 - len(rom)))
    cartridge_type = data[0x147]
    board, _ram, battery, timer, rumble = CARTRIDGE_TYPES.get(
        cartridge_type, ("unknown", False, False, False, False)
    )
    size_code = data[0x148]
    banks = 2 << size_code if size_code <= 8 else 2
    checksum = 0
    for byte in data[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 0xFF
    title = data[0x134:0x144].split(b"\0")[0].decode("ascii", "replace")
    return Header(
        title=title,
        cartridge_type=cartridge_type,
        board=board,
        rom_banks=banks,
        ram_bytes=RAM_SIZES.get(data[0x149], 0),
        has_battery=battery,
        has_timer=timer,
        has_rumble=rumble,
        cgb_flag=data[0x143],
        sgb_flag=data[0x146],
        header_checksum=data[0x14D],
        checksum_ok=checksum == data[0x14D],
        logo_ok=data[0x104:0x114] == NINTENDO_LOGO_START,
    )
