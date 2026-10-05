#!/usr/bin/env python3
"""Run Game Boy test ROMs headless on a locally built SameBoy and report each result.

SameBoy is a detector here, not a judge (docs/validation.md): it is the most
test-complete emulator we can drive, so it tells the board session what a
test *should* look like when no hardware-tier result is to hand, and it is
the reference the board's own harness is checked against before the board
exists.

Build it once (no root needed; see docs/validation.md "SameBoy built here"):

    make -C reference/src/SameBoy lib tester CONF=release \
        RGBDS=$PWD/reference/build-rgbds/

which leaves ``build/lib/libsameboy.so`` and SameBoy's own boot ROMs in
``build/bin/tester/``. This script loads the library with ctypes, runs whole
frames, and after each frame checks the result protocols:

- mooneye: B/C/D/E/H/L = 3/5/8/13/21/34 (pass) or all 0x42 (fail), with the
  CPU parked on ``JR -2`` (``18 FE``) after ``LD B,B``;
- blargg: text sent over the serial port, ending in "Passed" or "Failed",
  or the cartridge-RAM block at $A000 (signature DE B0 61, status, text);
- GBMicrotest (``--microtest``): after the run, $FF82 = $01 pass, $FF fail
  (only $FF82 is reliable, per the suite's own notes). Give it
  ``--seconds 0.5``: the boot ROM must finish first (quickboot takes under
  0.2 s, the real DMG ROM about 1.4 s, so use ``--seconds 2`` with that);
- timeout: none of these within ``--seconds``; the screen may still carry the
  answer (``--png`` saves it).

Boot with ``--boot``: for timing tests use your DMG boot ROM or
``reference/src/dmg-sim/boot/quickboot.bin``; SameBoy's own open boot ROM
fails Mooneye's boot-state tests (docs/undocumented-behavior.md C7).

    python scripts/sameboy_run.py ROM [ROM ...] [--model dmg-b|cgb-e|...]
        [--seconds 30] [--boot DMG_BOOT.bin] [--microtest] [--png out.png]
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMEBOY = ROOT / "reference" / "src" / "SameBoy" / "build"
LIB = SAMEBOY / "lib" / "libsameboy.so"
BOOT = SAMEBOY / "bin" / "tester"

# Core/model.h (SameBoy c458e7c5): the revision is part of the model number.
MODELS = {
    "dmg-b": (0x002, "dmg_boot.bin"),
    "mgb": (0x100, "mgb_boot.bin"),
    "sgb-ntsc": (0x004, "sgb_boot.bin"),
    "cgb-c": (0x203, "cgb_boot.bin"),
    "cgb-d": (0x204, "cgb_boot.bin"),
    "cgb-e": (0x205, "cgb_boot.bin"),
    "agb-a": (0x207, "agb_boot.bin"),
}
FIBONACCI = (3, 5, 8, 13, 21, 34)
FRAMES_PER_SECOND = 4194304 / 70224

RGB_CB = ctypes.CFUNCTYPE(
    ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8
)
SERIAL_START_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_bool)
LOG_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int)
QUIET = LOG_CB(lambda _gb, _text, _attributes: None)


class Registers(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint16) for name in ("af", "bc", "de", "hl", "sp", "pc")]


def load_library() -> ctypes.CDLL:
    # The shared library is built with -O3 and leaves glibc's vector maths
    # (_ZGVbN2v_sin) unresolved; load libmvec globally first.
    ctypes.CDLL("libmvec.so.1", mode=ctypes.RTLD_GLOBAL)
    lib = ctypes.CDLL(str(LIB))
    lib.GB_alloc.restype = ctypes.c_void_p
    lib.GB_init.restype = ctypes.c_void_p
    lib.GB_init.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.GB_load_boot_rom.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.GB_load_rom.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.GB_run_frame.restype = ctypes.c_uint64
    lib.GB_run_frame.argtypes = [ctypes.c_void_p]
    lib.GB_get_registers.restype = ctypes.POINTER(Registers)
    lib.GB_get_registers.argtypes = [ctypes.c_void_p]
    lib.GB_safe_read_memory.restype = ctypes.c_uint8
    lib.GB_safe_read_memory.argtypes = [ctypes.c_void_p, ctypes.c_uint16]
    lib.GB_set_pixels_output.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.GB_set_rgb_encode_callback.argtypes = [ctypes.c_void_p, RGB_CB]
    lib.GB_set_serial_transfer_bit_start_callback.argtypes = [ctypes.c_void_p, SERIAL_START_CB]
    lib.GB_set_log_callback.argtypes = [ctypes.c_void_p, LOG_CB]
    lib.GB_serial_set_data_bit.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    lib.GB_get_screen_width.argtypes = [ctypes.c_void_p]
    lib.GB_get_screen_height.argtypes = [ctypes.c_void_p]
    lib.GB_free.argtypes = [ctypes.c_void_p]
    lib.GB_dealloc.argtypes = [ctypes.c_void_p]
    return lib


def write_png(path: Path, width: int, height: int, pixels) -> None:
    rows = b"".join(
        b"\0" + b"".join(struct.pack(">I", pixels[y * width + x])[1:] for x in range(width))
        for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def run(
    lib: ctypes.CDLL,
    rom: Path,
    model: str,
    seconds: float,
    png: Path | None,
    boot_rom: Path | None,
    microtest: bool = False,
) -> str:
    number, boot = MODELS[model]
    boot_path = boot_rom or BOOT / boot
    gb = lib.GB_init(lib.GB_alloc(), number)
    rgb = RGB_CB(lambda _gb, r, g, b: (r << 16) | (g << 8) | b)
    serial_bits: list[int] = []

    def serial_start(_gb, bit):
        serial_bits.append(1 if bit else 0)
        lib.GB_serial_set_data_bit(gb, True)  # nothing attached: the line floats high

    serial = SERIAL_START_CB(serial_start)
    lib.GB_set_log_callback(gb, QUIET)  # SameBoy's debugger warnings would drown the results
    lib.GB_set_rgb_encode_callback(gb, rgb)
    lib.GB_set_serial_transfer_bit_start_callback(gb, serial)
    pixels = (ctypes.c_uint32 * (256 * 224))()
    lib.GB_set_pixels_output(gb, pixels)
    if lib.GB_load_boot_rom(gb, str(boot_path).encode()) or lib.GB_load_rom(gb, str(rom).encode()):
        return "error: could not load"
    verdict = "timeout"
    if microtest:
        for _ in range(int(seconds * FRAMES_PER_SECOND)):
            lib.GB_run_frame(gb)
        result = lib.GB_safe_read_memory(gb, 0xFF82)
        verdict = {0x01: "pass", 0xFF: "fail"}.get(result, f"no result ({result:02X})") + (
            f" (microtest: got {lib.GB_safe_read_memory(gb, 0xFF80):02X},"
            f" expected {lib.GB_safe_read_memory(gb, 0xFF81):02X})"
        )
    for _ in range(0 if microtest else int(seconds * FRAMES_PER_SECOND)):
        lib.GB_run_frame(gb)
        regs = lib.GB_get_registers(gb).contents
        pc = regs.pc
        if (lib.GB_safe_read_memory(gb, pc), lib.GB_safe_read_memory(gb, (pc + 1) & 0xFFFF)) == (
            0x18,
            0xFE,
        ) and lib.GB_safe_read_memory(gb, (pc - 1) & 0xFFFF) == 0x40:
            found = (
                regs.bc >> 8,
                regs.bc & 0xFF,
                regs.de >> 8,
                regs.de & 0xFF,
                regs.hl >> 8,
                regs.hl & 0xFF,
            )
            if found == FIBONACCI:
                verdict = "pass (mooneye)"
                break
            if found == (0x42,) * 6:
                verdict = "fail (mooneye)"
                break
        text = bytes(
            int("".join(map(str, serial_bits[i : i + 8])), 2)
            for i in range(0, len(serial_bits) - 7, 8)
        ).decode("latin-1")
        if "Passed" in text:
            verdict = "pass (blargg serial)"
            break
        if "Failed" in text:
            verdict = "fail (blargg serial): " + " ".join(text.split())[-200:]
            break
        # blargg's cartridge-RAM protocol: $A001-$A003 = DE B0 61 once the
        # test has started, $A000 = $80 while running, then the result code.
        if [lib.GB_safe_read_memory(gb, a) for a in (0xA001, 0xA002, 0xA003)] == [0xDE, 0xB0, 0x61]:
            status = lib.GB_safe_read_memory(gb, 0xA000)
            if status != 0x80:
                message = bytearray()
                address = 0xA004
                while len(message) < 400 and (byte := lib.GB_safe_read_memory(gb, address)):
                    message.append(byte)
                    address += 1
                tail = " ".join(message.decode("latin-1").split())[-200:]
                verdict = ("pass" if status == 0 else f"fail {status:02X}") + " ($A000): " + tail
                break
    if png:
        write_png(png, lib.GB_get_screen_width(gb), lib.GB_get_screen_height(gb), pixels)
    lib.GB_free(gb)
    lib.GB_dealloc(gb)
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("roms", nargs="+", type=Path)
    parser.add_argument("--model", default="dmg-b", choices=sorted(MODELS))
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument(
        "--boot", type=Path, help="a boot ROM you own instead of SameBoy's open one (BYOR)"
    )
    parser.add_argument(
        "--microtest", action="store_true", help="GBMicrotest protocol: read $FF82 after the run"
    )
    parser.add_argument("--png", type=Path, help="save the last frame (one ROM only)")
    args = parser.parse_args()
    if not LIB.exists():
        print(f"{LIB} is missing; build SameBoy first (see this script's docstring)")
        return 2
    lib = load_library()
    failures = 0
    for rom in args.roms:
        verdict = run(lib, rom, args.model, args.seconds, args.png, args.boot, args.microtest)
        failures += not verdict.startswith("pass")
        print(f"{rom}: {verdict}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
