"""Immutable snapshots of the board, for debuggers, traces and tests.

``capture_board_state`` returns the CPU's own state (sm83-python's ``CPUState``) together with the
board-side registers the CPU cannot see. It excludes memory contents and the cartridge, so
restoring it is not offered: use it for comparison and reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from sm83_python import CPUState

from gameboy_python.board import GameBoy


@dataclass(frozen=True, slots=True)
class BoardState:
    cpu: CPUState
    t: int  # T-cycles since power-on
    div_counter: int  # the 16-bit system counter (DIV is its top byte)
    tima: int
    tma: int
    tac: int
    lcdc: int
    stat: int
    ly: int
    lyc: int
    dot: int  # the PPU's dot within the line
    dma_active: bool
    boot_mapped: bool
    serial_sb: int
    serial_sc: int

    def as_dict(self) -> dict[str, object]:
        out = {name: getattr(self, name) for name in self.__slots__ if name != "cpu"}  # type: ignore[attr-defined]
        out["cpu"] = {f: getattr(self.cpu, f) for f in self.cpu.__slots__}  # type: ignore[attr-defined]
        return out


def capture_board_state(gb: GameBoy) -> BoardState:
    ppu = gb.ppu
    return BoardState(
        cpu=gb.cpu.capture_state(),
        t=gb.t,
        div_counter=gb.timer.counter,
        tima=gb.timer.tima,
        tma=gb.timer.tma,
        tac=gb.timer.tac,
        lcdc=ppu.lcdc,
        stat=ppu.read_stat(),
        ly=ppu.visible_ly if ppu.lcd_on else 0,
        lyc=ppu.lyc,
        dot=ppu.dot,
        dma_active=gb.dma.active,
        boot_mapped=gb.boot_mapped,
        serial_sb=gb.serial.sb,
        serial_sc=gb.serial.sc,
    )
