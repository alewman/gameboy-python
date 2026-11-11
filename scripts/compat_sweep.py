#!/usr/bin/env python3
"""Boot the licensed No-Intro Game Boy dumps on the board and on SameBoy; compare the pictures.

    python scripts/compat_sweep.py [--tier titles|all|failures] [--only FILE] [--jobs J] [--fresh]

Reads the sets in place (zips, never extracted or copied): ``Nintendo - Game Boy`` and ``Nintendo -
Game Boy Color`` under ``GAMEBOY_NOINTRO_DIR`` (default /data/emu/source/myrient.erista.me/files/
No-Intro), licensed dumps only (no Unl, Proto, Beta, Demo, Sample, Aftermarket, Pirate, Program
or BIOS), CGB-only titles skipped. Each runs from the real DMG boot ROM, and the board's picture
is compared with SameBoy's (DMG-B, the same boot ROM) shade for shade at each of ``CHECKS``
(frames 600, 960 and 1500: one run answers for all three). SameBoy is a detector, not a judge
(docs/validation.md): every difference is for triage.

A sweep is long (the board runs about 20 frames a second per core under PyPy), so it is made to
be run rarely and never twice for the same answer:

* ``--tier titles`` (the default) runs one dump per title, the newest revision of the most
  widespread region: the regional dumps of a game are the same program. ``--tier all`` runs every
  dump, for a release. ``--tier failures`` runs ``tests/compat_differs.txt``, the dumps that
  differed or raised last time: the loop between edits (minutes, not hours).
* Results are appended to ``reference/build/compat_sweep.jsonl`` as each ROM finishes, each with
  the board's git revision. A rerun skips the dumps already answered at this revision, so an
  interrupted sweep resumes; ``--fresh`` forgets them.
* After a ``titles`` or ``all`` sweep, ``tests/compat_differs.txt`` is rewritten. After a
  ``failures`` run, the list is left alone and the changes against it are printed.

* Each dump that differs leaves ``reference/build/compat/NAME.png``: the board's picture,
  SameBoy's nearest and where they differ, side by side at the worst checkpoint, so triage starts
  from pictures, not from another run.

Statuses: ``same`` (equal at every checkpoint), ``near`` (equal to one of SameBoy's pictures
within 30 frames of the checkpoint: an animation phase), ``differs`` (N pixels at best, at the
worst checkpoint), ``error`` (the board raised), ``unsupported`` (a board not built yet:
HuC1/HuC3/camera/MBC6/MBC7/TAMA5/...).
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from gameboy_python.cartridge import parse_header  # noqa: E402
from gameboy_python.image import png_bytes  # noqa: E402

NOINTRO = Path(
    os.environ.get("GAMEBOY_NOINTRO_DIR", "/data/emu/source/myrient.erista.me/files/No-Intro")
)
KEEP = 30  # SameBoy frames kept each side of a checkpoint to absorb an animation phase offset
SETS = ("Nintendo - Game Boy", "Nintendo - Game Boy Color")
EXCLUDE = re.compile(r"\((Unl|Proto|Beta|Demo|Sample|Aftermarket|Pirate|Program)|\[BIOS\]")

_spec = importlib.util.spec_from_file_location("sameboy_run", ROOT / "scripts" / "sameboy_run.py")
sb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sb)


CHECKS = (600, 960, 1500)
LOG = ROOT / "reference" / "build" / "compat_sweep.jsonl"
PICTURES = ROOT / "reference" / "build" / "compat"  # board | SameBoy | where they differ
DIFFERS = ROOT / "tests" / "compat_differs.txt"
REGIONS = ("(World", "(USA", "(Europe", "(Japan")


def _rank(path: Path) -> tuple[int, int, str]:
    """Lower is the better representative of a title: widest region, then the newest revision."""
    region = next((i for i, r in enumerate(REGIONS) if r in path.name), len(REGIONS))
    rev = re.search(r"\(Rev ([0-9A-Z]+)\)", path.name)
    return (region, -int(rev.group(1), 36) if rev else 0, path.name)


def candidates(tier: str = "all", stride: int = 1) -> list[Path]:
    files = []
    for name in SETS:
        files += sorted(p for p in (NOINTRO / name).glob("*.zip") if not EXCLUDE.search(p.name))
    if tier == "titles":
        best: dict[tuple[str, str], Path] = {}
        for p in files:
            key = (p.parent.name, p.name.split(" (")[0])
            if key not in best or _rank(p) < _rank(best[key]):
                best[key] = p
        files = sorted(best.values())
    return files[::stride]


def named(names: list[str]) -> list[Path]:
    """The dumps of a list of file names (``tests/compat_differs.txt``'s first column)."""
    found = []
    for name in names:
        hits = [NOINTRO / s / name for s in SETS if (NOINTRO / s / name).exists()]
        if not hits:
            print(f"  not in the sets: {name}")
        found += hits[:1]
    return found


def read_list(path: Path) -> list[str]:
    lines = (line.split("\t")[0].strip() for line in path.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


FRAME_T = 70224


def sameboy_checks(
    rom: bytes, checks: tuple[int, ...], boot: bytes, keep: int
) -> list[list[bytes]]:
    """SameBoy's pictures from ``keep`` frames before each frame of ``checks`` to ``keep`` after
    (the frame itself is at index ``keep - 1``), as shades 0 (lightest) to 3."""
    lib = _library()
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
    shots: list[list[bytes]] = [[] for _ in checks]
    width, height = lib.GB_get_screen_width(gb), lib.GB_get_screen_height(gb)
    for n in range(checks[-1] + keep):
        lib.GB_run_frame(gb)
        for i, c in enumerate(checks):
            if c - keep <= n < c + keep:
                # the tester's DMG palette is the grey ramp 00/55/AA/FF: shade 0 is the lightest
                shots[i].append(
                    bytes(3 - ((v >> 16) & 255) // 85 for v in pixels[: width * height])
                )
    lib.GB_free(gb)
    lib.GB_dealloc(gb)
    return shots


def sameboy_frames(rom: bytes, frames: int, boot: bytes, keep: int) -> list[bytes]:
    """SameBoy's last ``keep`` pictures as shades 0 (lightest) to 3."""
    return sameboy_checks(rom, (frames,), boot, keep)[0][:keep]


_lib = None


def _library():
    global _lib
    if _lib is None:
        _lib = sb.load_library()
    return _lib


def triptych(mine: bytes, theirs: bytes) -> bytes:
    """A 480x144 PNG: the board's picture, SameBoy's, and black where they differ."""
    rows = bytearray()
    for y in range(0, 160 * 144, 160):
        a, b = mine[y : y + 160], theirs[y : y + 160]
        rows += a + b + bytes(3 * (p != q) for p, q in zip(a, b, strict=True))
    return png_bytes(bytes(rows), 480, 144)


def run(args: tuple[Path, tuple[int, ...]]) -> dict:
    path, checks = args
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
        for c in checks:
            while gb.t < c * FRAME_T:
                gb.step()
            mine.append(bytes(gb.ppu.frame))
    except Exception as e:
        return {**out, "status": "error", "detail": repr(e)[:160]}
    try:
        theirs = sameboy_checks(rom, checks, boot, KEEP)
    except Exception as e:
        return {**out, "status": "error", "detail": f"sameboy: {e!r}"[:400]}
    # each picture against SameBoy's KEEP either side of it: an animation a frame or two apart
    # is not a difference (``offset`` says how far, in frames: negative when the board is
    # behind), a picture SameBoy never shows is
    exact, best, offset = [], [], []
    for picture, shots in zip(mine, theirs, strict=True):
        diffs = [sum(1 for a, b in zip(picture, t, strict=False) if a != b) for t in shots]
        low = min(diffs)
        exact.append(diffs[KEEP - 1])
        best.append(low)
        offset.append(
            min((abs(i - KEEP + 1), i - KEEP + 1) for i, d in enumerate(diffs) if d == low)[1]
        )
    out["pixels"] = exact
    out["best"] = best
    out["offset"] = offset
    out["status"] = "same" if not any(exact) else "near" if not any(best) else "differs"
    if out["status"] == "differs":
        worst = best.index(max(best))
        PICTURES.mkdir(parents=True, exist_ok=True)
        (PICTURES / f"{path.stem}.png").write_bytes(
            triptych(mine[worst], theirs[worst][KEEP - 1 + offset[worst]])
        )
    return out


def revision() -> str:
    def git(*a: str) -> str:
        return subprocess.run(
            ["git", "-C", str(ROOT), *a], capture_output=True, text=True
        ).stdout.strip()

    return git("rev-parse", "--short", "HEAD") + (
        "+" if git("status", "--porcelain", "src") else ""
    )


def line_of(r: dict) -> str:
    if r["status"] == "error":
        return f"{r['rom']}\terror\t{r.get('detail', '')}"
    return f"{r['rom']}\t{max(r['best'])} px\t{r['board']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tier", choices=("titles", "all", "failures"), default="titles")
    parser.add_argument("--only", type=Path, help="a list of dump names to run instead of a tier")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--frames", type=int, default=CHECKS[-1], help="stop at this checkpoint")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    parser.add_argument("--fresh", action="store_true", help="forget this revision's answers")
    args = parser.parse_args()
    label = find_boot_rom("DMG")[1]
    if label != "real boot ROM":
        sys.exit(f"needs the real DMG boot ROM ({label})")
    checks = tuple(c for c in CHECKS if c <= args.frames) or (args.frames,)
    listed = args.only or (DIFFERS if args.tier == "failures" else None)
    files = named(read_list(listed)) if listed else candidates(args.tier, args.stride)
    rev = revision()
    done: dict[str, dict] = {}
    if LOG.exists() and not args.fresh and not rev.endswith("+"):
        for line in LOG.read_text().splitlines():
            r = json.loads(line)
            if r.get("rev") == rev and tuple(r.get("checks", ())) == checks:
                done[r["rom"]] = r
    todo = [p for p in files if p.name not in done]
    print(f"{len(files)} dumps at {rev}, {len(files) - len(todo)} already answered", flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with Pool(args.jobs) as pool, LOG.open("a") as log:
        work = pool.imap_unordered(run, [(p, checks) for p in todo], chunksize=1)
        for n, r in enumerate(work, 1):
            r["rev"], r["checks"] = rev, checks
            log.write(json.dumps(r) + "\n")
            log.flush()
            done[r["rom"]] = r
            if n % 100 == 0:
                print(f"  {n} of {len(todo)}", flush=True)
    results = [done[p.name] for p in files]
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(results)} ROMs: {counts}")
    bad = [r for r in results if r["status"] in ("error", "differs")]
    for r in bad:
        print("  " + line_of(r).replace("\t", "  "))
    if listed:
        fixed = [r["rom"] for r in results if r["status"] in ("same", "near")]
        print(f"against {listed.name}: {len(fixed)} no longer differ, {len(bad)} still do")
    elif args.stride == 1:
        DIFFERS.write_text(
            f"# scripts/compat_sweep.py --tier {args.tier} at {rev}: {counts}\n"
            "# dump, pixels at best at the worst of frames "
            f"{', '.join(map(str, checks))}, board\n" + "".join(line_of(r) + "\n" for r in bad)
        )
    return 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
