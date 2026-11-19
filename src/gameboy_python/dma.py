"""OAM DMA (docs/timing.md "OAM DMA").

Writing $FF46: one M-cycle of nothing, then at M+2 the transfer starts and OAM reads return $FF;
one byte per M-cycle for 160 M-cycles (Mooneye oam_dma_start header, all models; GBCTR dma.typ).
A write during a transfer restarts it, the old one running until the new one starts. During the
transfer the DMA owns the *source* bus: a CPU read on that bus gets the DMA's byte (Pan Docs
OAM_DMA_Transfer.md "OAM DMA bus conflicts"). Every source in $A000-$FFFF is an external-bus read
(GBCTR dma.typ "OAM DMA address decoding"; Mooneye oam_dma/sources-GS).
"""

from __future__ import annotations

from collections.abc import Callable

EXTERNAL, VIDEO, INTERNAL = "external", "video", "internal"


def bus_of(address: int) -> str:
    """Which bus an address is on: cartridge and WRAM share the external bus."""
    if address < 0x8000 or 0xA000 <= address < 0xFE00:
        return EXTERNAL
    if address < 0xA000:
        return VIDEO
    return INTERNAL


def source_bus(base: int) -> str:
    """The bus a DMA source page is read from ($E0 and above: the external bus, echoing WRAM)."""
    return bus_of(base << 8 if base < 0xE0 else 0xC000)


class OamDma:
    def __init__(self, read_source: Callable[[int], int], write_oam: Callable[[int, int], None]):
        self.read_source = read_source
        self.write_oam = write_oam
        self.register = 0xFF  # the last value written (the register reads it back)
        self.pending: int | None = None
        self.countdown = 0
        self.active = False
        self.base = 0
        self.index = 0
        self.byte = 0xFF  # the byte on the source bus this M-cycle
        self.bus = EXTERNAL
        self._finishing = False  # the last byte moved this M-cycle: still locked until the next

    def start(self, value: int) -> None:
        self.register = value
        self.pending = value
        self.countdown = 2  # the next M-cycle does nothing, the one after starts the transfer

    def tick(self) -> None:
        """One M-cycle."""
        if self._finishing:
            self._finishing = False
            self.active = False
        if self.pending is not None:
            self.countdown -= 1
            if self.countdown == 0:
                self.base = self.pending
                self.pending = None
                self.active = True
                self.index = 0
                self.bus = source_bus(self.base)
        if self.active:
            source = (self.base << 8) | self.index
            if self.base >= 0xE0:
                source -= 0x2000  # $E000-$FFFF reads WRAM through the echo
            self.byte = self.read_source(source)
            self.write_oam(self.index, self.byte)
            self.index += 1
            if self.index == 160:
                self._finishing = True
