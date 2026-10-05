#!/usr/bin/env python3
"""Count cartridge types (header byte $0147) across the local No-Intro Game Boy sets.

Read-only: opens each zip, reads the first $150 bytes of each .gb/.gbc member,
never extracts to disk. Results are in docs/cartridge.md.

    nice python3 scripts/count_mbcs.py > coverage.txt    # also writes coverage.json

The header type byte is what a loader sees; it is not proof of the board.
Two kinds of cartridge lie, and are detected here by the heuristics the
hardware references give:

- MBC1 multicarts ("MBC1M"): an 8 Mbit MBC1 image with the Nintendo logo again
  at physical $40104 (gb-ctr chapter/cartridges/mbc1.typ "Detecting multicarts");
- MMM01: the menu's header is in the *last* 32 KiB, with type $0B-$0D there
  and the Nintendo logo with it (Pan Docs MMM01.md); the first bank's header
  names the first game.
"""

from __future__ import annotations

import collections
import json
import re
import zipfile
from pathlib import Path

BASE = Path("/data/emu/source/myrient.erista.me/files/No-Intro")
SETS = [
    "Nintendo - Game Boy",
    "Nintendo - Game Boy Color",
    "Nintendo - Game Boy (Aftermarket)",
    "Nintendo - Game Boy Color (Aftermarket)",
    "Nintendo - Game Boy (Private)",
    "Nintendo - Game Boy Color (Private)",
]
CLASS_TAGS = ["Pirate", "Unl", "Aftermarket", "Proto", "Beta", "Sample", "Demo", "Program"]

# Pan Docs "The Cartridge Header", $0147 (pandocs 0191af06).
TYPES = {
    0x00: "ROM ONLY", 0x01: "MBC1", 0x02: "MBC1+RAM", 0x03: "MBC1+RAM+BATTERY",
    0x05: "MBC2", 0x06: "MBC2+BATTERY", 0x08: "ROM+RAM", 0x09: "ROM+RAM+BATTERY",
    0x0B: "MMM01", 0x0C: "MMM01+RAM", 0x0D: "MMM01+RAM+BATTERY",
    0x0F: "MBC3+TIMER+BATTERY", 0x10: "MBC3+TIMER+RAM+BATTERY", 0x11: "MBC3",
    0x12: "MBC3+RAM", 0x13: "MBC3+RAM+BATTERY", 0x19: "MBC5", 0x1A: "MBC5+RAM",
    0x1B: "MBC5+RAM+BATTERY", 0x1C: "MBC5+RUMBLE", 0x1D: "MBC5+RUMBLE+RAM",
    0x1E: "MBC5+RUMBLE+RAM+BATTERY", 0x20: "MBC6", 0x22: "MBC7+SENSOR+RUMBLE+RAM+BATTERY",
    0x101: "MBC1M (multicart wiring)", 0x10B: "MMM01 (menu header at end)",
    0xFC: "POCKET CAMERA", 0xFD: "BANDAI TAMA5", 0xFE: "HuC3", 0xFF: "HuC1+RAM+BATTERY",
}  # fmt: skip


def family(kind: int) -> str:
    name = TYPES.get(kind, f"unknown ${kind:02X}")
    return name.split("+")[0] if name != "ROM ONLY" else "ROM"


def classify(name: str) -> str:
    tags = re.findall(r"\(([^)]*)\)", name)
    for wanted in CLASS_TAGS:
        if any(t == wanted or t.startswith(wanted + " ") for t in tags):
            return wanted
    return "BIOS" if name.startswith("[BIOS]") else "licensed"


def main() -> None:
    rows = []
    for set_name in SETS:
        for path in sorted((BASE / set_name).glob("*.zip")):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if not member.filename.lower().endswith((".gb", ".gbc")):
                        continue
                    with archive.open(member) as handle:
                        image = handle.read()
                    if len(image) < 0x8000:
                        continue
                    header = image[:0x150]
                    kind = header[0x147]
                    menu = image[-0x8000 : -0x8000 + 0x150]
                    if (
                        len(image) >= 0x10000
                        and menu[0x147] in (0x0B, 0x0C, 0x0D)
                        and menu[0x104:0x134] == header[0x104:0x134]
                    ):  # logo there too
                        kind = 0x10B  # MMM01 menu in the last 32 KiB
                    elif (
                        kind in (1, 2, 3)
                        and len(image) == 0x100000
                        and image[0x40104:0x40134] == image[0x104:0x134]
                    ):
                        kind = 0x101  # MBC1 multicart wiring
                    rows.append({
                        "set": set_name, "name": member.filename, "class": classify(path.stem),
                        "type": kind, "cgb": header[0x143], "sgb": header[0x146],
                        "rom": header[0x148], "ram": header[0x149], "size": member.file_size,
                    })  # fmt: skip
    Path("coverage.json").write_text(json.dumps(rows, indent=0), encoding="utf-8")
    for label, chosen in [
        ("licensed (GB + GBC sets)", [r for r in rows if r["class"] == "licensed"
                                      and "(" not in r["set"]]),
        ("everything", rows),
    ]:  # fmt: skip
        families = collections.Counter(family(r["type"]) for r in chosen)
        total = len(chosen)
        print(f"\n{label}: {total} dumps")
        running = 0
        for name, count in families.most_common():
            running += count
            print(
                f"  {name:14s} {count:5d} {100 * count / total:5.1f} %  cumulative {100 * running / total:5.1f} %"
            )
        cgb = collections.Counter(
            {0x80: "CGB-enhanced", 0xC0: "CGB-only"}.get(r["cgb"], "DMG") for r in chosen
        )
        print("  header $0143:", dict(cgb), " SGB flag $03:", sum(r["sgb"] == 3 for r in chosen))
    types = collections.Counter(
        TYPES.get(r["type"], f"${r['type']:02X}") for r in rows if r["class"] == "licensed"
    )
    print("\nlicensed, by exact type byte:")
    for name, count in types.most_common():
        print(f"  {name:32s} {count:5d}")


if __name__ == "__main__":
    main()
