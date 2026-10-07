"""The machines, as data: one row per model and revision.

DMG-01 with a DMG-CPU B is the reference model (decided 2026-10-05; docs/start-here.md "Why
DMG-CPU B"): it is the only revision with die-level models and it is in Mooneye's fleet. Every
other row is present so that adding it later is data, not a refactor, and is marked
``certified=False`` until a suite has judged it. Each quirk field names its source and tier.

Revision letters follow Mooneye's naming (``mooneye-test-suite/README.markdown``).
"""

from __future__ import annotations

from dataclasses import dataclass

#: 4.194304 MHz crystal (2**22 Hz); a dot (PPU clock) is one T-cycle, an M-cycle is four.
CLOCK_HZ = 4_194_304
DOTS_PER_LINE = 456
LINES_PER_FRAME = 154
DOTS_PER_FRAME = DOTS_PER_LINE * LINES_PER_FRAME  # 70,224 (Pan Docs Rendering.md)


@dataclass(frozen=True, slots=True)
class Machine:
    """One Game Boy model and revision."""

    name: str
    model: str  # "dmg", "mgb", "sgb", "sgb2", "cgb", "agb"
    revision: str  # "0", "A", "B", "C"; CGB "0".."E"
    #: which No-Intro boot ROM image boots it (docs/start-here.md "Boot ROMs")
    boot_rom: str
    #: monochrome PPU model; CGB hardware runs a DMG-compatible mode (KEY0) on top
    cgb_hardware: bool = False
    #: the OAM corruption bug (DMG/MGB/SGB yes, CGB/AGB no: Pan Docs OAM_Corruption_Bug.md;
    #: hardware-tested by blargg oam_bug on DMG-C, hardware-verified)
    oam_bug: bool = True
    #: disabling the timer while the selected counter bit is 1 ticks TIMA (DMG yes, CGB no:
    #: Pan Docs Timer_Obscure_Behaviour.md; Mooneye timer/ tests, hardware-verified)
    tac_disable_glitch: bool = True
    #: on monochrome models a STAT write acts as if $FF were written for one M-cycle (Pan Docs
    #: STAT.md "Spurious STAT interrupts"; research documentation)
    stat_write_glitch: bool = True
    #: wave RAM readable/writable only on the cycle the channel reads it while on (DMG yes, CGB
    #: no: blargg dmg_sound 09/12 vs cgb_sound, hardware-verified)
    wave_ram_while_on_glitch: bool = True
    #: what $FEA0-$FEFF read: "zero_when_free" (DMG/MGB/SGB), "revision_masked_ram" (CGB 0-D),
    #: "high_nibble_twice" (CGB E): Pan Docs Memory_Map.md "FEA0-FEFF range"
    fea0_read: str = "zero_when_free"
    #: stat_irq_blocking (Mooneye ppu/stat_irq_blocking) fails on DMG 0: the STAT line is
    #: re-triggered while another source holds it (hardware-verified in the test's header)
    stat_blocking: bool = True
    #: the boot ROM writes $FF (MGB) or $01 (DMG) to $FF50 (docs/start-here.md machines table)
    boot_disable_value: int = 0x01
    #: has the machine been judged by a suite? Rows below are data only until then.
    certified: bool = False


def _dmg(revision: str, **kwargs) -> Machine:
    boot = "DMG0" if revision == "0" else "DMG"
    return Machine(
        f"DMG-CPU {revision}", "dmg", revision, boot, stat_blocking=revision != "0", **kwargs
    )


DMG_B = _dmg("B", certified=True)

MACHINES: dict[str, Machine] = {
    "dmg": DMG_B,
    "dmg-b": DMG_B,
    "dmg-0": _dmg("0"),
    "dmg-a": _dmg("A"),
    "dmg-c": _dmg("C"),
    "mgb": Machine("MGB", "mgb", "-", "MGB", boot_disable_value=0xFF),
    "sgb": Machine("SGB", "sgb", "-", "SGB"),
    "sgb2": Machine("SGB2", "sgb2", "-", "SGB2"),
    # CGB hardware: no OAM bug, no TAC-disable glitch, no STAT write glitch. Reference revision
    # CGB E (Aubrey 2026-10-05; SameSuite's APU suite passes in full only on E). Phase 2.
    "cgb": Machine(
        "CPU CGB E",
        "cgb",
        "E",
        "CGB",
        cgb_hardware=True,
        oam_bug=False,
        tac_disable_glitch=False,
        stat_write_glitch=False,
        wave_ram_while_on_glitch=False,
        fea0_read="high_nibble_twice",
    ),
}

__all__ = [
    "CLOCK_HZ",
    "DMG_B",
    "DOTS_PER_FRAME",
    "DOTS_PER_LINE",
    "LINES_PER_FRAME",
    "MACHINES",
    "Machine",
]
