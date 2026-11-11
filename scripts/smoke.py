#!/usr/bin/env python3
"""The quick gate: a curated slice of the slow suites, in minutes rather than hours.

    python scripts/smoke.py [--jobs N] [--set MODULE.NAME=VALUE ...] [--only pytest|dmg|cgb]

``tests/smoke.txt`` lists what runs, one item a line:

``pytest NODE``
    a pytest node id, a test file, or an fnmatch pattern over node ids: the classics that must
    stay perfect (acid2, blargg, Mooneye, the exact Mealybug pictures, CGB acid2 and register tests).
``dmg PATH`` / ``cgb PATH``
    a Gambatte ROM (its path in the suite), judged from the skip-boot state as
    ``scripts/gambatte_dmg08.py --skip-boot`` judges it on the DMG-08 or the CGB-04c.

A Gambatte verdict is compared with ``tests/gambatte_dmg08_pass.txt`` or
``tests/gambatte_cgb04c_pass.txt``: a listed ROM that fails is a regression, an unlisted one that
passes a gain. The exit status is 1 on any regression or pytest failure.

This is the loop between edits. The whole lists, the slow pytest suites, Mealybug's scores, AGE and
GBMicrotest stay the gate before a commit (docs/validation.md): a timing constant is judged on all
of them.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gambatte_dmg08  # noqa: E402

LIST = ROOT / "tests/smoke.txt"
PASS_LISTS = {
    "dmg": ROOT / "tests/gambatte_dmg08_pass.txt",
    "cgb": ROOT / "tests/gambatte_cgb04c_pass.txt",
}
#: node ids that take minutes each (hundreds of frames from the real boot ROM): one task apiece
HEAVY = ("*mealybug*", "*cgb_acid2*", "*halt_bug*", "*dmg_acid2*")
CHUNK = 6


def read_list(path: Path = LIST) -> tuple[list[str], list[tuple[str, str]]]:
    patterns, roms = [], []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        kind, what = line.split(None, 1)
        if kind == "pytest":
            patterns.append(what)
        elif kind in PASS_LISTS:
            roms.append((kind, what))
        else:
            raise SystemExit(f"{path.name}: unknown kind {kind!r}")
    return patterns, roms


def pytest_nodes(patterns: list[str]) -> list[str]:
    files = sorted({p.split("::")[0] for p in patterns})
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "--collect-only", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    nodes = [line for line in out.splitlines() if "::" in line]
    return [
        n
        for n in nodes
        if any(
            n == p
            or n.startswith(p + "[")
            or fnmatch.fnmatchcase(n, p.replace("[", "[[]"))
            or n.split("::")[0] == p
            for p in patterns
        )
    ]


def run_pytest(args: tuple[list[str], list[str]]) -> tuple[str, list[str], list[str]]:
    """One pytest process over some node ids, with the --set overrides applied first."""
    nodes, sets = args
    code = (
        "import importlib, sys\n"
        f"for item in {sets!r}:\n"
        "    target, value = item.split('=')\n"
        "    module, name = target.rsplit('.', 1)\n"
        "    setattr(importlib.import_module(f'gameboy_python.{module}'), name, int(value, 0))\n"
        "import pytest\n"
        "sys.exit(pytest.main(sys.argv[1:]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, "-p", "no:cacheprovider", "-q", "-rfE", *nodes],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    failed = [
        line.split(" ", 1)[1].split(" - ")[0]
        for line in proc.stdout.splitlines()
        if line.startswith(("FAILED ", "ERROR "))
    ]
    if proc.returncode not in (0, 1) and not failed:
        failed = [f"(pytest exited {proc.returncode}) " + " ".join(nodes)]
    return "pytest", nodes, failed


def run_rom(args: tuple[str, str]) -> tuple[str, str, list[tuple[str, bool]]]:
    mode, path = args
    results = gambatte_dmg08.run((gambatte_dmg08.SUITE / path, True, False, mode == "cgb"))
    return mode, path, [(kind, ok) for _name, kind, ok, _sb in results]


def task(item):
    start = time.time()
    result = run_pytest(item[1]) if item[0] == "pytest" else run_rom(item[1])
    return result, time.time() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--list", type=Path, default=LIST, help="another list in the same format")
    parser.add_argument("--only", choices=("pytest", "dmg", "cgb"))
    parser.add_argument(
        "--slowest", type=int, default=0, metavar="N", help="list the N slowest tasks"
    )
    parser.add_argument("--set", action="append", default=[], metavar="MODULE.NAME=VALUE")
    args = parser.parse_args()
    for item in args.set:
        target, value = item.split("=")
        module, name = target.rsplit(".", 1)
        setattr(importlib.import_module(f"gameboy_python.{module}"), name, int(value, 0))
    patterns, roms = read_list(args.list)
    if args.only:
        patterns = patterns if args.only == "pytest" else []
        roms = [r for r in roms if r[0] == args.only]
    nodes = pytest_nodes(patterns) if patterns else []
    heavy = [n for n in nodes if any(fnmatch.fnmatchcase(n, h) for h in HEAVY)]
    light = [n for n in nodes if n not in heavy]
    # longest first, so the minutes-long pictures overlap everything else
    work = [("pytest", ([n], args.set)) for n in heavy]
    work += [("pytest", (light[i : i + CHUNK], args.set)) for i in range(0, len(light), CHUNK)]
    work += [("rom", r) for r in roms]
    passing = {
        m: {tuple(line.split()) for line in p.read_text().splitlines() if line.strip()}
        for m, p in PASS_LISTS.items()
    }

    start = time.time()
    took: list[tuple[float, list[str]]] = []
    failures, regressions, gains, tally = (
        [],
        [],
        [],
        {"pytest": [0, 0], "dmg": [0, 0], "cgb": [0, 0]},
    )
    with multiprocessing.get_context("fork").Pool(args.jobs) as pool:
        for result, seconds in pool.imap_unordered(task, work):
            took.append(
                (seconds, result[1] if result[0] == "pytest" else [f"{result[0]} {result[1]}"])
            )
            if result[0] == "pytest":
                _, ran, failed = result
                failures += failed
                tally["pytest"][0] += len(ran) - len(failed)
                tally["pytest"][1] += len(ran)
                for f in failed:
                    print(f"  pytest FAILED {f}", flush=True)
                continue
            mode, path, verdicts = result
            for kind, ok in verdicts:
                tally[mode][0] += ok
                tally[mode][1] += 1
                expected = (path, kind) in passing[mode]
                if expected and not ok:
                    regressions.append((mode, path, kind))
                    print(f"  {mode} REGRESSION {path} [{kind}]", flush=True)
                elif ok and not expected:
                    gains.append((mode, path, kind))
                    print(f"  {mode} gain {path} [{kind}]", flush=True)

    (pa, pn), (da, dn), (ca, cn) = tally["pytest"], tally["dmg"], tally["cgb"]
    print(
        f"smoke: pytest {pa}/{pn}, Gambatte DMG {da}/{dn}, CGB {ca}/{cn}; "
        f"{len(regressions)} regressions, {len(gains)} gains ({time.time() - start:.0f} s)"
    )
    if args.slowest:
        print(f"slowest {args.slowest} tasks:")
        for seconds, what in sorted(took, reverse=True)[: args.slowest]:
            print(
                f"  {seconds:6.0f} s  {what[0]}"
                + (f" (+{len(what) - 1} more)" if len(what) > 1 else "")
            )
    return 1 if failures or regressions else 0


if __name__ == "__main__":
    import nursery

    nursery.small()
    sys.exit(main())
