"""The integer-program solver used by the optimizers.

PuLP's bundled CBC works on Windows and Linux. On macOS it ships only an
Intel (x86_64) CBC, which an Apple Silicon Mac can run only through Rosetta, so
there HiGHS (the ``highspy`` package, a dependency on macOS) is used when
installed.
"""
from __future__ import annotations

import sys

import pulp


def highs_available() -> bool:
    try:
        return pulp.HiGHS().available()
    except Exception:
        return False


def name() -> str:
    return "HiGHS" if sys.platform == "darwin" and highs_available() else "CBC"


def solver(msg: bool = False, time_limit: float | None = None, gap: float | None = None,
           threads: int | None = None):
    if name() == "HiGHS":
        return pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
    return pulp.PULP_CBC_CMD(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
