"""cartridge/ must stay extractable, and the APU core (gb-apu-python) must stay a core: neither
imports the board."""

from __future__ import annotations

import ast
from pathlib import Path

import gb_apu_python

SRC = Path(__file__).resolve().parents[1] / "src" / "gameboy_python"


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_cartridge_is_self_contained():
    for path in (SRC / "cartridge").rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith(("gameboy_python", "sm83_python")) or module.startswith(
                "gameboy_python.cartridge"
            ), f"{path.name} imports {module}"


def test_the_apu_core_imports_no_board():
    for path in Path(gb_apu_python.__file__).parent.rglob("*.py"):
        for module in _imports(path):
            board = module.startswith(("gameboy_python", "sm83_python"))
            assert not board, f"{path} imports {module}"


def test_the_board_uses_the_apu_core():
    assert "gb_apu_python" in _imports(SRC / "board.py")
    assert not (SRC / "apu" / "__init__.py").exists()
