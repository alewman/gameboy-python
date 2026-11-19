"""A small PNG reader for the reference pictures (non-interlaced, types 0/2/3/6, depth 1-8)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def read_shades(path: Path) -> tuple[bytes, int, int]:
    """Return (shades 0-3, 0 the lightest, width, height) of a DMG-grey picture."""
    pixels, width, height, depth, ctype = _decode(path)
    top = (1 << depth) - 1 if ctype == 0 else 255  # a grey sample's full-scale value
    shades = bytearray()
    for pixel in pixels:
        grey = pixel[0] * 255 // top
        assert len({*pixel[:3]}) == 1 and round(grey / 85) * 85 == grey, f"not a DMG grey: {pixel}"
        shades.append(3 - grey // 85)
    return bytes(shades), width, height


def read_rgb555(path: Path) -> tuple[list[int], int, int]:
    """Return (RGB555 words, width, height): each 8-bit channel scaled back to 5 bits the way the
    reference pictures were made (v * 255 / 31)."""
    pixels, width, height, depth, ctype = _decode(path)
    top = (1 << depth) - 1 if ctype == 0 else 255  # grey samples are not 8-bit scaled
    words = []
    for pixel in pixels:
        if len(pixel) == 1:
            pixel = (pixel[0] * 255 // top,) * 3
        r, g, b = (round(c * 31 / 255) for c in pixel[:3])
        words.append(r | (g << 5) | (b << 10))
    return words, width, height


def read_rgb888(path: Path) -> tuple[list[int], int, int]:
    """Return (0xRRGGBB pixels, width, height)."""
    pixels, width, height, depth, ctype = _decode(path)
    top = (1 << depth) - 1 if ctype == 0 else 255
    out = []
    for p in pixels:
        if len(p) == 1:
            p = (p[0] * 255 // top,) * 3
        out.append(p[0] << 16 | p[1] << 8 | p[2])
    return out, width, height


def _decode(path: Path) -> tuple[list[tuple[int, ...]], int, int, int, int]:
    data = path.read_bytes()
    pos = 8
    palette: list[tuple[int, ...]] = []
    idat = b""
    width = height = depth = ctype = 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            assert depth <= 8 and interlace == 0, "unsupported PNG"
        elif kind == b"PLTE":
            palette = [tuple(body[i : i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"IDAT":
            idat += body
    channels = {0: 1, 2: 3, 3: 1, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = (width * channels * depth + 7) // 8
    step = max(1, channels * depth // 8)  # filter distance in bytes
    rows: list[bytearray] = []
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        ft = raw[p]
        line = bytearray(raw[p + 1 : p + 1 + stride])
        p += 1 + stride
        for i in range(stride):
            a = line[i - step] if i >= step else 0
            b = prev[i]
            c = prev[i - step] if i >= step else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        rows.append(line)
        prev = line
    pixels = []
    for line in rows:
        for x in range(width):
            if depth < 8:
                per = 8 // depth
                value = (line[x // per] >> (8 - depth * (x % per + 1))) & ((1 << depth) - 1)
                pixels.append(palette[value] if ctype == 3 else (value,))
            elif ctype == 3:
                pixels.append(palette[line[x]])
            else:
                pixels.append(tuple(line[x * channels : x * channels + min(channels, 3)]))
    return pixels, width, height, depth, ctype
