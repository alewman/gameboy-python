"""Run test ROMs and read their result protocols (docs/validation.md).

* **Mooneye**: B, C, D, E, H, L = 3, 5, 8, 13, 21, 34 at ``LD B,B`` is a pass, all $42 a fail.
* **blargg serial** (``cpu_instrs``, ``instr_timing``, ``mem_timing``): text on the serial port
  ending ``Passed`` or ``Failed``.
* **blargg $A000** (``dmg_sound``, ``oam_bug``, ``mem_timing-2``): cartridge RAM $A001-$A003 =
  $DE $B0 $61, $A000 = $80 while running then the result code, text from $A004.
* **GBMicrotest**: $FF82 = $01 pass, $FF fail ($FF80 got, $FF81 expected) after about 2 frames.
"""

from __future__ import annotations

from dataclasses import dataclass

from gameboy_python.board import GameBoy

MOONEYE_PASS = (3, 5, 8, 13, 21, 34)
MOONEYE_FAIL = (0x42,) * 6


@dataclass(frozen=True, slots=True)
class RomResult:
    protocol: str  # "mooneye", "blargg-serial", "blargg-ram", "microtest", "timeout"
    passed: bool
    text: str
    registers: tuple[int, ...]
    t_cycles: int
    frames: int


def registers(gb: GameBoy) -> tuple[int, ...]:
    cpu = gb.cpu
    return (cpu.b, cpu.c, cpu.d, cpu.e, cpu.h, cpu.l)


def _serial_text(gb: GameBoy) -> str:
    return gb.serial.output.decode("ascii", "replace")


def run_mooneye(gb: GameBoy, max_frames: int = 600) -> RomResult:
    """Run until ``LD B,B`` with Mooneye's registers, or the frame budget runs out."""
    cpu = gb.cpu
    peek = gb.peek
    step = cpu.step
    ppu = gb.ppu
    limit = (ppu.frames + max_frames, gb.t + max_frames * 70224)
    while gb.t < limit[1]:
        if peek(cpu.pc) == 0x40 and not (cpu.halted or cpu.stopped):
            regs = registers(gb)
            if regs in (MOONEYE_PASS, MOONEYE_FAIL):
                return RomResult(
                    "mooneye", regs == MOONEYE_PASS, _serial_text(gb), regs, gb.t, ppu.frames
                )
        step()
    return RomResult("timeout", False, _serial_text(gb), registers(gb), gb.t, ppu.frames)


def run_blargg_serial(gb: GameBoy, max_frames: int = 6000) -> RomResult:
    """Run until the serial text ends with ``Passed`` or ``Failed``."""
    cpu = gb.cpu
    step = cpu.step
    serial = gb.serial
    limit = gb.t + max_frames * 70224
    check = 0
    while gb.t < limit:
        step()
        check += 1
        if check >= 2000:  # the text only changes on serial writes; look every so often
            check = 0
            text = serial.output.decode("ascii", "replace")
            if text.rstrip().endswith(("Passed", "Failed")) or "Passed all tests" in text:
                return RomResult(
                    "blargg-serial", "Passed" in text, text, registers(gb), gb.t, gb.ppu.frames
                )
    return RomResult("timeout", False, _serial_text(gb), registers(gb), gb.t, gb.ppu.frames)


def run_blargg_ram(gb: GameBoy, max_frames: int = 6000) -> RomResult:
    """Run until cartridge RAM holds blargg's signature and a result code other than $80."""
    cpu = gb.cpu
    step = cpu.step
    ram = gb.cartridge.ram
    limit = gb.t + max_frames * 70224
    check = 0
    while gb.t < limit:
        step()
        check += 1
        if check >= 5000:
            check = 0
            if len(ram) > 4 and bytes(ram[1:4]) == b"\xde\xb0\x61" and ram[0] != 0x80:
                text = bytes(ram[4:]).split(b"\0")[0].decode("ascii", "replace")
                return RomResult(
                    "blargg-ram", ram[0] == 0, text, registers(gb), gb.t, gb.ppu.frames
                )
    return RomResult("timeout", False, "", registers(gb), gb.t, gb.ppu.frames)


def run_microtest(gb: GameBoy, frames: int = 4) -> RomResult:
    """Run a GBMicrotest ROM for a few frames and read $FF82."""
    gb.run_frames(frames)
    result = gb.hram[0x82]
    return RomResult(
        "microtest",
        result == 1,
        f"got ${gb.hram[0]:02X} expected ${gb.hram[1]:02X}",
        registers(gb),
        gb.t,
        gb.ppu.frames,
    )
