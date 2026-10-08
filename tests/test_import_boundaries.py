"""cartridge/ and apu/ must stay extractable: they import nothing else from this package."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "gameboy_python"


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_cartridge_and_apu_are_self_contained():
    for package in ("cartridge", "apu"):
        for path in (SRC / package).rglob("*.py"):
            for module in _imports(path):
                assert not module.startswith(
                    ("gameboy_python", "sm83_python")
                ) or module.startswith(f"gameboy_python.{package}"), f"{path.name} imports {module}"
