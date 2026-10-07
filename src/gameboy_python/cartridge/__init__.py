"""Cartridges: the connector protocol, the header, and the memory bank controllers.

This package imports nothing from the rest of the board (tests/test_boundaries.py).
"""

from __future__ import annotations

from typing import Protocol

from gameboy_python.cartridge.header import Header, parse_header
from gameboy_python.cartridge.mbc import MBC1, Cartridge


class CartridgeConnector(Protocol):
    """What the board calls on a cartridge (docs/cartridge.md "Proposed protocol")."""

    header: Header

    def read(self, address: int, t: int) -> int | None: ...
    def write(self, address: int, value: int, t: int) -> None: ...
    def tick_to(self, t: int) -> None: ...
    def vin(self, t: int) -> int: ...
    def save_ram(self) -> bytes | None: ...


def load_cartridge(rom: bytes) -> Cartridge:
    """Identify the board from the header and build it."""
    header = parse_header(rom)
    if header.board == "rom":
        return Cartridge(rom, header)
    if header.board == "mbc1":
        return MBC1(rom, header)
    raise NotImplementedError(
        f"cartridge board {header.board!r} (type ${header.cartridge_type:02X})"
    )


__all__ = ["MBC1", "Cartridge", "CartridgeConnector", "Header", "load_cartridge", "parse_header"]
