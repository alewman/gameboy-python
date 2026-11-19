"""Give PyPy a small nursery before a script fans out over the cores.

PyPy sizes its nursery (where new objects are made) from the processor's largest cache: 36 MB on
the machine these sweeps run on, and that cache is shared by every core. One board alone then
runs 1.7 times slower than with a 1 MB nursery, and eight side by side run 3.3 times slower
again, each pushing the others' nursery out of the cache (measured 2026-11-11, Tetris for 960
frames: 43 s alone and 150 s eight at once by default; 27 s and 31 s at 1 MB). ``PYPY_GC_NURSERY``
is read when the interpreter starts, so the script starts itself again with it set.
"""

from __future__ import annotations

import os
import sys

SIZE = "1M"


def small() -> None:
    if sys.implementation.name == "pypy" and "PYPY_GC_NURSERY" not in os.environ:
        os.environ["PYPY_GC_NURSERY"] = SIZE
        os.execv(sys.executable, [sys.executable, *sys.argv])
