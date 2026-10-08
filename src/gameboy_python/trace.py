"""A JSON Lines trace of the board: sm83-python's record per boundary, with T-cycle times.

Each line is ``{"t": <T-cycles at the start of the step>, "record": <sm83-python trace record>,
"board": {...}}``. The record is exactly sm83-python's schema (docs/trace-schema.md there), with
every M-cycle's bus access, so a CPU trace of the board can be compared with a core-only trace;
``t`` and ``board`` add the board's time and the PPU/timer position after the step.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TextIO

from sm83_python.debug import DebugSession
from sm83_python.trace import step_record_to_dict

from gameboy_python.board import GameBoy


def iter_trace(gb: GameBoy, steps: int) -> Iterator[dict]:
    """Run ``steps`` boundaries, yielding one trace object per step (bus tracking on)."""
    session = DebugSession(gb, peek_byte=gb.peek, history_limit=0, track_accesses=True)
    try:
        for _ in range(steps):
            start = gb.t
            record = session.step()
            yield {
                "t": start,
                "record": step_record_to_dict(record),
                "board": {
                    "t": gb.t,
                    "div": gb.timer.counter,
                    "ly": gb.ppu.visible_ly if gb.ppu.lcd_on else 0,
                    "dot": gb.ppu.dot,
                    "if": gb.cpu.if_,
                },
            }
    finally:
        session.close()


def write_trace(gb: GameBoy, steps: int, stream: TextIO) -> int:
    """Write ``steps`` boundaries as JSON Lines; returns the count."""
    count = 0
    for item in iter_trace(gb, steps):
        stream.write(json.dumps(item, separators=(",", ":"), sort_keys=True) + "\n")
        count += 1
    return count
