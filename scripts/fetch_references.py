#!/usr/bin/env python3
"""Fetch the pinned documents, test ROMs, tools and source trees into reference/ and tests/test_roms/.

Nothing fetched here is committed (see .gitignore). Two pin files drive it:

- ``scripts/pinned_files.json``: one entry per file, with its URL, SHA-256 and
  kind. Kinds ``test-rom`` and ``tool`` must match their hash exactly; a
  mismatch is an error and the file is not kept. Kind ``live-document`` is a
  URL that always serves the newest revision (GBCTR's PDF); a mismatch is a
  warning and the new bytes are kept, because the docs cite the revision.
  Zip archives are unpacked next to themselves (the c-sp bundle into
  ``tests/test_roms/gbtr/``), and the RGBDS tarball into its directory.
- ``scripts/pinned_repos.json``: one entry per git repository, cloned shallow at
  the pinned revision (sparse where the entry lists paths).

Building SameBoy, Icarus Verilog (for dmg-sim) and GateBoy from these trees is
described in docs/validation.md; this script only fetches.

    python scripts/fetch_references.py            # everything missing
    python scripts/fetch_references.py --verify   # hash what is present, fetch nothing
    python scripts/fetch_references.py --no-repos # files only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "scripts" / "pinned_files.json"
REPOS = ROOT / "scripts" / "pinned_repos.json"
LIVE = {"live-document"}
USER_AGENT = "Mozilla/5.0 (gameboy-python reference fetch)"
# Where each archive is unpacked, relative to the archive's directory.
UNPACK = {"game-boy-test-roms-v7.0.zip": "gbtr"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str) -> bytes:
    # curl, as in famicom-python: some hosts refuse urllib whatever the User-Agent.
    result = subprocess.run(
        ["curl", "-sSfL", "--max-time", "300", "-A", USER_AGENT, url],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise OSError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def unpack(path: Path) -> None:
    if path.suffix == ".zip":
        target = path.parent / UNPACK.get(path.name, "")
        with zipfile.ZipFile(path) as archive:
            archive.extractall(target)
        print(f"  unpacked into {target.relative_to(ROOT)}")
    elif path.name.endswith(".tar.xz"):
        with tarfile.open(path) as archive:
            archive.extractall(path.parent, filter="data")
        print(f"  unpacked into {path.parent.relative_to(ROOT)}")


def fetch_files(verify_only: bool) -> int:
    problems = 0
    for entry in json.loads(FILES.read_text(encoding="utf-8")):
        path = ROOT / entry["path"]
        live = entry["kind"] in LIVE
        if path.exists():
            if sha256(path) != entry["sha256"]:
                level = "warning" if live else "ERROR"
                print(f"{level}: {entry['path']} does not match its pin")
                problems += not live
            continue
        if verify_only:
            print(f"missing: {entry['path']}")
            problems += 1
            continue
        try:
            data = download(entry["url"])
        except OSError as error:
            print(f"ERROR: {entry['url']}: {error}")
            problems += 1
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"] and not live:
            print(f"ERROR: {entry['url']} has SHA-256 {digest}, pinned {entry['sha256']}; not kept")
            problems += 1
            continue
        if digest != entry["sha256"]:
            print(f"warning: {entry['path']} is a newer revision than the one the docs cite")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            handle.write(data)
        Path(handle.name).replace(path)
        print(f"fetched {entry['path']}")
        unpack(path)
    return problems


def fetch_repos(verify_only: bool) -> int:
    problems = 0
    for entry in json.loads(REPOS.read_text(encoding="utf-8")):
        path = ROOT / entry["path"]
        if path.exists():
            head = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if head != entry["rev"]:
                print(f"ERROR: {entry['path']} is at {head}, pinned {entry['rev']}")
                problems += 1
            continue
        if verify_only:
            print(f"missing: {entry['path']}")
            problems += 1
            continue
        path.mkdir(parents=True)
        git = ["git", "-C", str(path)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "remote", "add", "origin", entry["url"]], check=True)
        if entry["sparse"]:
            subprocess.run(
                [*git, "sparse-checkout", "set", "--no-cone", *entry["sparse"]], check=True
            )
        subprocess.run(
            [*git, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", entry["rev"]],
            check=True,
        )
        subprocess.run([*git, "checkout", "-q", "FETCH_HEAD"], check=True)
        print(f"cloned {entry['path']} at {entry['rev'][:12]}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--verify", action="store_true", help="check what is present; fetch nothing"
    )
    parser.add_argument("--no-repos", action="store_true", help="skip the git repositories")
    args = parser.parse_args()
    problems = fetch_files(args.verify)
    if not args.no_repos:
        problems += fetch_repos(args.verify)
    print("all pins satisfied" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
