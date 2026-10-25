"""PyPy keeps an instance's attributes in a fixed layout only up to 79: the 80th turns the
instance into a dict and every ``self.x`` in the hot loops into a dict lookup. Each object of the
board must have slots or stay under that."""

import pytest

from gameboy_python import MACHINES, GameBoy, load_cartridge

LIMIT = 80


def objects(root):
    seen, stack = set(), [("gb", root)]
    while stack:
        name, obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        yield name, obj
        state = getattr(obj, "__dict__", None)
        if state is None:
            state = {s: getattr(obj, s) for s in type(obj).__slots__ if hasattr(obj, s)}
        for key, value in state.items():
            if type(value).__module__.startswith(("gameboy_python", "sm83_python")):
                stack.append((f"{name}.{key}", value))


@pytest.mark.parametrize("machine", ["dmg-b", "cgb"])
def test_no_object_outgrows_pypy_layout(machine):
    rom = bytearray(0x8000)
    rom[0x100:0x104] = b"\x00\xc3\x00\x01"  # nop; jp $0100
    gb = GameBoy(load_cartridge(bytes(rom)), MACHINES[machine])
    gb.run_frames(2)
    big = [(n, len(vars(o))) for n, o in objects(gb) if hasattr(o, "__dict__")]
    assert [b for b in big if b[1] >= LIMIT] == []
    assert any(n == "gb.ppu" for n, _o in objects(gb))  # the walk reaches the PPU
