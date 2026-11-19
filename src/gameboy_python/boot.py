"""Boot ROMs are bring-your-own, and the real one is the default (docs/start-here.md "Boot ROMs").

Order: a configured path (``override`` or ``GAMEBOY_BOOT_ROM``, a raw image or a No-Intro
``.zip``), then Aubrey's local No-Intro ``[BIOS]`` zips read in place and checked by SHA-256
(``GAMEBOY_NOINTRO_DIR`` moves the directory), then dmg-sim's ``quickboot.bin``, then SameBoy's
open ROM, labelled, because it fails three Mooneye boot-state tests (C7). Nothing is ever copied
into this repository.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOINTRO = Path(
    os.environ.get("GAMEBOY_NOINTRO_DIR") or os.environ.get("NO_INTRO_DIR") or "No-Intro"
)
#: boot ROM name (machines.Machine.boot_rom) -> (zip under NOINTRO, SHA-256 of the image)
LOCAL = {
    "DMG": (
        "Nintendo - Game Boy/[BIOS] Nintendo Game Boy Boot ROM (World) (Rev 1).zip",
        "cf053eccb4ccafff9e67339d4e78e98dce7d1ed59be819d2a1ba2232c6fce1c7",
    ),
    "DMG0": (
        "Nintendo - Game Boy/[BIOS] Nintendo Game Boy Boot ROM (Japan) (En).zip",
        "26e71cf01e301e5dc40e987cd2ecbf6d0276245890ac829db2a25323da86818e",
    ),
    "CGB": (
        "Nintendo - Game Boy Color/[BIOS] Nintendo Game Boy Color Boot ROM (World) (Rev 1).zip",
        "b4f2e416a35eef52cba161b159c7c8523a92594facb924b3ede0d722867c50c7",
    ),
    "MGB": (
        "Nintendo - Game Boy/[BIOS] Nintendo Game Boy Pocket Boot ROM (World).zip",
        "a8cb5f4f1f16f2573ed2ecd8daedb9c5d1dd2c30a481f9b179b5d725d95eafe2",
    ),
}
QUICKBOOT = ROOT / "reference" / "src" / "dmg-sim" / "boot" / "quickboot.bin"
SAMEBOY_OPEN = (
    ROOT / "reference" / "src" / "SameBoy" / "build" / "bin" / "BootROMs" / "dmg_boot.bin"
)


def read_image(path: Path) -> bytes:
    """A boot image from a raw file or the first member of a zip."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return archive.read(archive.infolist()[0])
    return path.read_bytes()


def find_boot_rom(name: str = "DMG", override: Path | None = None) -> tuple[bytes | None, str]:
    """The boot image for ``name`` and a label saying where it came from (None: skip boot)."""
    chosen = override or (
        Path(os.environ["GAMEBOY_BOOT_ROM"]) if "GAMEBOY_BOOT_ROM" in os.environ else None
    )
    if chosen:
        return read_image(chosen), f"boot ROM {chosen.name}"
    if name in LOCAL:
        relative, digest = LOCAL[name]
        path = NOINTRO / relative
        if path.exists():
            image = read_image(path)
            if hashlib.sha256(image).hexdigest() == digest:
                return image, "real boot ROM"
    if name == "DMG" and QUICKBOOT.exists():
        return QUICKBOOT.read_bytes(), "quickboot (dmg-sim)"
    if name == "DMG" and SAMEBOY_OPEN.exists():
        return SAMEBOY_OPEN.read_bytes(), "SameBoy open boot ROM: boot-state tests unreliable"
    return None, "none found: skip-boot state"
