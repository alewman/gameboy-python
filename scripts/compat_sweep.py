#!/usr/bin/env python3
"""Boot every licensed No-Intro Game Boy dump on the board and on SameBoy; compare the pictures.

    python scripts/compat_sweep.py [--stride N] [--frames F] [--jobs J] [--out results.json]

Reads the sets in place (zips, never extracted or copied): ``Nintendo - Game Boy`` and ``Nintendo -
Game Boy Color`` under ``GAMEBOY_NOINTRO_DIR`` (default /data/emu/source/myrient.erista.me/files/
No-Intro), licensed dumps only (no Unl, Proto, Beta, Demo, Sample, Aftermarket, Pirate, Program
or BIOS), CGB-only titles skipped (the board is a DMG until phase 2). Each runs from the real DMG
boot ROM for ``--frames`` LCD frames (default 960: about 336 of boot, then the game); the board's
last picture is compared with SameBoy (DMG-B, the same boot ROM) shade for shade. SameBoy is a
detector, not a judge (docs/validation.md): every difference is for triage.

Statuses: ``same`` (the last pictures are equal), ``near`` (equal to one of SameBoy's last 30: an
animation phase), ``differs`` (N pixels at best), ``error`` (the board raised),
``unsupported`` (a board not built yet: HuC1/HuC3/camera/MBC6/MBC7/TAMA5/...).
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import re
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.cartridge import parse_header  # noqa: E402

NOINTRO = Path(
    os.environ.get("GAMEBOY_NOINTRO_DIR", "/data/emu/source/myrient.erista.me/files/No-Intro")
)
KEEP = 30  # frames kept at the end to absorb an animation phase offset
SETS = ("Nintendo - Game Boy", "Nintendo - Game Boy Color")
EXCLUDE = re.compile(r"\((Unl|Proto|Beta|Demo|Sample|Aftermarket|Pirate|Program)|\[BIOS\]")

_spec = importlib.util.spec_from_file_location("sameboy_run", ROOT / "scripts" / "sameboy_run.py")
sb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sb)


def candidates(stride: int) -> list[Path]:
    files = []
    for name in SETS:
        files += sorted(p for p in (NOINTRO / name).glob("*.zip") if not EXCLUDE.search(p.name))
    return files[::stride]


FRAME_T = 70224


def sameboy_frames(rom: bytes, frames: int, boot: bytes, keep: int) -> list[bytes]:
    """SameBoy's last ``keep`` pictures as shades 0 (lightest) to 3."""
    lib = sb.load_library()
    gb = lib.GB_init(lib.GB_alloc(), sb.MODELS["dmg-b"][0])

    def encode(_gb, r, g, b):
        value = (r << 16) | (g << 8) | b
        return value

    callback = sb.RGB_CB(encode)
    lib.GB_set_log_callback(gb, sb.QUIET)
    lib.GB_set_rgb_encode_callback(gb, callback)
    pixels = (ctypes.c_uint32 * (256 * 224))()
    lib.GB_set_pixels_output(gb, pixels)
    lib.GB_load_boot_rom_from_buffer(gb, boot, len(boot))
    path = ROOT / "reference" / "build" / f"compat_rom_{os.getpid()}.tmp"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rom)
    lib.GB_load_rom(gb, str(path).encode())
    shots = []
    width, height = lib.GB_get_screen_width(gb), lib.GB_get_screen_height(gb)
    for n in range(frames):
        lib.GB_run_frame(gb)
        if n >= frames - keep:
            shots.append(list(pixels[: width * height]))
    lib.GB_free(gb)
    lib.GB_dealloc(gb)
    # the tester's DMG palette is the grey ramp 00/55/AA/FF: shade 0 is the lightest
    return [bytes(3 - ((v >> 16) & 255) // 85 for v in shot) for shot in shots]


def run(args: tuple[Path, int]) -> dict:
    path, frames = args
    out: dict = {"rom": path.name}
    try:
        with zipfile.ZipFile(path) as z:
            rom = z.read(z.namelist()[0])
    except Exception as e:
        return {**out, "status": "error", "detail": f"zip: {e!r}"}
    header = parse_header(rom)
    out["board"] = header.board
    if header.cgb_only:
        return {**out, "status": "skipped", "detail": "CGB only"}
    boot = find_boot_rom("DMG")[0]
    try:
        cart = load_cartridge(rom)
    except NotImplementedError:
        return {**out, "status": "unsupported"}
    except Exception as e:
        return {**out, "status": "error", "detail": repr(e)[:120]}
    try:
        gb = GameBoy(cart, boot_rom=boot)
        # SameBoy counts 70,224-cycle frames from power-on, LCD off or not; the board's
        # run_frames counts VBlanks, so line the two up by time instead
        mine = []
        for n in range(frames - KEEP, frames):
            while gb.t < (n + 1) * FRAME_T:
                gb.step()
            mine.append(bytes(gb.ppu.frame))
    except Exception as e:
        return {**out, "status": "error", "detail": repr(e)[:160]}
    try:
        theirs = sameboy_frames(rom, frames, boot, KEEP)
    except Exception as e:
        return {**out, "status": "error", "detail": f"sameboy: {e!r}"[:160]}
    # the last picture against SameBoy's last KEEP: an animation a frame or two apart is not a
    # difference, a picture SameBoy never shows is
    last = mine[-1]
    diffs = [sum(1 for a, b in zip(last, t, strict=False) if a != b) for t in theirs]
    best = min(diffs)
    out["pixels"] = diffs[-1]
    out["best"] = best
    out["status"] = "same" if diffs[-1] == 0 else "near" if best == 0 else "differs"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--frames", type=int, default=960)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    label = find_boot_rom("DMG")[1]
    if label != "real boot ROM":
        sys.exit(f"needs the real DMG boot ROM ({label})")
    files = candidates(args.stride)
    with Pool(args.jobs) as pool:
        results = pool.map(run, [(p, args.frames) for p in files], chunksize=2)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(results)} ROMs: {counts}")
    for r in results:
        if r["status"] in ("error", "differs"):
            print(
                f"  {r['status']:8s} {r['rom']}: {r.get('detail') or str(r.get('best')) + ' px at best'}"
            )
    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
