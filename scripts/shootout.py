#!/usr/bin/env python3
"""Run gbdev's GBEmulatorShootout test list on the board and score it as the leaderboard does.

    python scripts/shootout.py [--jobs N] [--only SUITE] [--json FILE] [--skip-boot]

The list and the expected pictures come from ``reference/src/GBEmulatorShootout-gbdev``
(https://gbdev.io/GBEmulatorShootout/). Its test modules are plain data (``Test(...)`` calls):
they are loaded with a stub ``Test`` class, and none of the shootout's own code runs. Judged as
its ``emulator.py`` and ``util.compareImage`` judge a screenshot:

* the board boots the real boot ROM (DMG or CGB, by the test's model) and runs for the test's
  ``runtime`` + 5 s + the emulator's startup time, looking at the picture every 0.1 s. The
  shootout tunes each emulator's startup time by hand to cover its boot (SameBoy: 6.5 s DMG,
  3.5 s CGB); here it is measured, as the time ``startup_time_test.gb`` takes to show its picture;
* a picture matches when every pixel's grey (PIL's ``L``: 0.299 R + 0.587 G + 0.114 B) is within
  50 of the expected one; the first match with a ``.png`` is a PASS, with a ``.fail.png`` a FAIL;
* with neither by the deadline it is a FAIL, or "no result" for a test with no expected picture;
* SGB tests are skipped (no SGB here), as the shootout skips them for a DMG/CGB emulator.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from gameboy_python import MACHINES, GameBoy, load_cartridge  # noqa: E402
from gameboy_python.boot import find_boot_rom  # noqa: E402
from tests.pngread import read_rgb888  # noqa: E402

SHOOTOUT = ROOT / "reference/src/GBEmulatorShootout-gbdev"
SUITES = ("acid", "blargg", "daid", "ax6", "mooneye", "samesuite", "ashiepaws", "cpp", "mealybug")
FRAME_T = 70224  # dots per frame
SECOND_T = 4194304  # dots per second
POLL_T = SECOND_T // 10  # the shootout looks every 0.1 s
EXTRA_S = 5.0  # its wait beyond the runtime and the startup time
TOLERANCE = 50  # util.compareImage: a grey difference above this fails the pixel
GREYS = (0xFF, 0xAA, 0x55, 0x00)  # DMG shades, as gameboy_python.image writes them
SCALE = [round(v * 255 / 31) for v in range(32)]  # RGB555 channels to 8 bits


class _Test:
    """The fields of the shootout's ``test.Test`` that the board needs."""

    def __init__(self, name, *, runtime, rom=None, result=None, model="DMG", **_):
        rom = rom or name
        if result is None:
            result = rom.rsplit(".", 1)[0] + ".png"
        self.name, self.rom, self.model, self.runtime = name, rom, model, runtime
        self.results = result if isinstance(result, list) else [result]


def load_tests(only: str | None = None) -> list[_Test]:
    stub = types.ModuleType("test")
    stub.Test, stub.DMG, stub.CGB, stub.SGB, stub.PCM = _Test, "DMG", "CGB", "SGB", "PCM"
    stub.PASS, stub.FAIL, stub.INFO = "PASS", "FAIL", "INFO"
    tests = []
    for suite in SUITES:
        if only and suite != only:
            continue
        namespace = {"__name__": f"testroms.{suite}"}
        sys.modules["test"] = stub
        source = (SHOOTOUT / "testroms" / f"{suite}.py").read_text()
        exec(
            compile(source.replace("from test import *", ""), suite, "exec"),
            {**vars(stub), **namespace},
            namespace,
        )
        tests += namespace["all"]
    return tests


def _grey(r: int, g: int, b: int) -> int:
    return (r * 19595 + g * 38470 + b * 7471 + 0x8000) >> 16  # PIL's L conversion


def _expected(name: str) -> bytes | None:
    path = SHOOTOUT / "testroms" / name
    if not path.exists():
        return None
    pixels, width, height = read_rgb888(path)
    if (width, height) != (160, 144):
        return None
    return bytes(_grey(p >> 16, (p >> 8) & 255, p & 255) for p in pixels)


def _screen(gb: GameBoy) -> bytes:
    frame = gb.ppu.frame
    if not gb.cgb:
        return bytes(_grey(v, v, v) for v in (GREYS[s] for s in frame))
    out = bytearray()
    for i in range(0, len(frame), 2):
        word = frame[i] | (frame[i + 1] << 8)
        out.append(_grey(SCALE[word & 31], SCALE[(word >> 5) & 31], SCALE[(word >> 10) & 31]))
    return bytes(out)


def _matches(screen: bytes, want: bytes) -> bool:
    return all(abs(a - b) <= TOLERANCE for a, b in zip(screen, want, strict=True))


def startup_time(model: str, skip_boot: bool) -> float:
    """Seconds until ``startup_time_test.gb`` shows ``startup_time_test.png`` (``model``)."""
    cgb = model == "CGB"
    boot = None if skip_boot else find_boot_rom("CGB" if cgb else "DMG")[0]
    rom = (SHOOTOUT / "startup_time_test.gb").read_bytes()
    gb = GameBoy(load_cartridge(rom), MACHINES["cgb" if cgb else "dmg-b"], boot_rom=boot)
    pixels, _, _ = read_rgb888(SHOOTOUT / "startup_time_test.png")
    want = bytes(_grey(p >> 16, (p >> 8) & 255, p & 255) for p in pixels)
    step = gb.cpu.step
    while gb.t < 60 * SECOND_T:
        target = gb.t + FRAME_T
        while gb.t < target:
            step()
        if _matches(_screen(gb), want):
            return gb.t / SECOND_T
    raise RuntimeError(f"startup_time_test.gb never showed its picture ({model})")


def run(job: tuple[_Test, bool, dict[str, float]]) -> tuple[str, str, str]:
    test, skip_boot, startup = job
    if test.model == "SGB":
        return test.name, test.model, "skipped (SGB)"
    passes = [p for p in (_expected(r) for r in test.results) if p]
    fails = [p for p in (_expected(r.rsplit(".", 1)[0] + ".fail.png") for r in test.results) if p]
    cgb = test.model == "CGB"
    boot = None if skip_boot else find_boot_rom("CGB" if cgb else "DMG")[0]
    rom = (SHOOTOUT / "testroms" / test.rom).read_bytes()
    box: list[GameBoy] = []
    try:
        # a cartridge clock runs on emulated time here: the board is slower than the wall clock
        cart = load_cartridge(rom, clock=lambda: (box[0].t if box else 0) / SECOND_T)
        gb = GameBoy(cart, MACHINES["cgb" if cgb else "dmg-b"], boot_rom=boot)
        box.append(gb)
    except Exception as exc:  # an unsupported cartridge type
        return test.name, test.model, f"FAIL (load: {exc})"
    end = int((startup[test.model] + test.runtime + EXTRA_S) * SECOND_T)
    step = gb.cpu.step
    next_poll = POLL_T
    while gb.t < end:
        while gb.t < next_poll:
            step()
        next_poll += POLL_T
        screen = _screen(gb)
        if any(_matches(screen, p) for p in passes):
            return test.name, test.model, "PASS"
        if any(_matches(screen, f) for f in fails):
            return test.name, test.model, "FAIL"
    return test.name, test.model, "FAIL" if passes else "no result"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--only", choices=SUITES)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--skip-boot", action="store_true", help="start from the skip-boot state")
    args = parser.parse_args()
    tests = load_tests(args.only)
    startup = {m: startup_time(m, args.skip_boot) for m in ("DMG", "CGB")}
    print(f"startup time: DMG {startup['DMG']:.2f} s, CGB {startup['CGB']:.2f} s")
    jobs = [(t, args.skip_boot, startup) for t in tests]
    with Pool(args.jobs) as pool:
        results = pool.map(run, jobs, chunksize=1)
    by_suite: dict[str, list[int]] = {}
    for name, model, verdict in results:
        print(f"{verdict:14s} {model:4s} {name}")
        tally = by_suite.setdefault(name.split("/")[0], [0, 0])
        if not verdict.startswith(("skipped", "no result")):  # info-only tests do not score
            tally[0] += verdict == "PASS"
            tally[1] += 1
    for suite, (won, total) in by_suite.items():
        print(f"{suite:24s} {won:4d} of {total}")
    won = sum(v[0] for v in by_suite.values())
    total = sum(v[1] for v in by_suite.values())
    print(f"shootout: {won} of {total} pass")
    if args.json:
        args.json.write_text(json.dumps(results, indent=0))
    return 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
