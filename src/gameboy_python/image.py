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


def rgb_png_bytes(frame: bytes, width: int = 160, height: int = 144) -> bytes:
    """A CGB frame (RGB555, 16 bits little-endian per pixel) as a 24-bit PNG; channels are scaled
    ``v * 255 / 31`` as the reference pictures (cgb-acid2, Mealybug) were made."""
    scale = [round(v * 255 / 31) for v in range(32)]
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            i = (y * width + x) * 2
            word = frame[i] | (frame[i + 1] << 8)
            rows += bytes((scale[word & 31], scale[(word >> 5) & 31], scale[(word >> 10) & 31]))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def rgb24_png_bytes(rgb: bytes, width: int, height: int) -> bytes:
    """8-bit RGB, 3 bytes per pixel, rows top to bottom (a Super Game Boy picture: sgb.py)."""
    stride = width * 3
    rows = b"".join(b"\x00" + rgb[y * stride : (y + 1) * stride] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )


def write_rgb_png(path: Path, frame: bytes) -> None:
    path.write_bytes(rgb_png_bytes(frame))


def write_png(path: Path, shades: bytes) -> None:
    path.write_bytes(png_bytes(shades))
