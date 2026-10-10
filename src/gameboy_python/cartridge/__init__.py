"""Cartridges: the connector protocol, the header, and the memory bank controllers.

This package imports nothing from the rest of the board (tests/test_boundaries.py).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from gameboy_python.cartridge.header import Header, parse_header
from gameboy_python.cartridge.mbc import MBC1, MBC2, MBC3, MBC5, MMM01, Cartridge


class CartridgeConnector(Protocol):
    """What the board calls on a cartridge (docs/cartridge.md "Proposed protocol")."""

    header: Header

    def read(self, address: int, t: int) -> int | None: ...
    def write(self, address: int, value: int, t: int) -> None: ...
    def tick_to(self, t: int) -> None: ...
    def vin(self, t: int) -> int: ...
    def save_ram(self) -> bytes | None: ...


def _has_logo_at(rom: bytes, offset: int) -> bool:
    return rom[offset : offset + 16] == bytes.fromhex("CEED6666CC0D000B03730083000C000D")


def load_cartridge(rom: bytes, clock: Callable[[], float] | None = None) -> Cartridge:
    """Identify the board from the header and build it.

    Two boards cannot be told from the header alone and are found by the Nintendo logo
    (docs/cartridge.md "Measured coverage"): an 8 Mbit MBC1 image with the logo again at $40104 is
    a multicart (MBC1M wiring), and a ROM whose last 32 KiB hold a header with the logo and an MMM01
    type byte is an MMM01 compilation (its first game's header says something else). ``clock`` is
    the MBC3 timer's time source (wall time by default).
    """
    header = parse_header(rom)
    if len(rom) >= 0x8000 and _has_logo_at(rom, len(rom) - 0x8000 + 0x104):
        menu = parse_header(rom[-0x8000:])
        if menu.board == "mmm01":
            return MMM01(rom, menu)
    if header.board == "rom":
        return Cartridge(rom, header)
    if header.board == "mbc1":
        multicart = len(rom) == 0x100000 and _has_logo_at(rom, 0x40104)
        return MBC1(rom, header, multicart=multicart)
    if header.board == "mbc2":
        return MBC2(rom, header)
    if header.board == "mbc3":
        return MBC3(rom, header, clock)
    if header.board == "mbc5":
        return MBC5(rom, header)
    raise NotImplementedError(
        f"cartridge board {header.board!r} (type ${header.cartridge_type:02X})"
    )


__all__ = [
    "MBC1",
    "MBC2",
    "MBC3",
    "MBC5",
    "MMM01",
    "Cartridge",
    "CartridgeConnector",
    "Header",
    "load_cartridge",
    "parse_header",
]
