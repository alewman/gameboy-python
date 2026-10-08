"""Write the PPU's 160x144 shade buffer as a PNG (no dependencies)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

#: DMG shades 0-3 as grey levels, lightest first (a neutral grey ramp, not a colour fit).
GREYS = (0xFF, 0xAA, 0x55, 0x00)


def png_bytes(shades: bytes, width: int = 160, height: int = 144, palette=GREYS) -> bytes:
    rows = b"".join(
        b"\x00" + bytes(palette[v] for v in shades[y * width : (y + 1) * width])
        for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit greyscale
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )


def write_png(path: Path, shades: bytes) -> None:
    path.write_bytes(png_bytes(shades))
