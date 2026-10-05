"""The integer-program solver used by the optimizers.

HiGHS (the ``highspy`` package) is preferred on every platform because it is an
in-process solver: the packaged, windowed app has no console, and PuLP's bundled
CBC runs as an external subprocess, which can stall there (the Daevanion solve
would hang). HiGHS has no subprocess, so it is reliable in the bundle; CBC stays
as the fallback when ``highspy`` is not installed.
"""
from __future__ import annotations

import pulp


def highs_available() -> bool:
    try:
        return pulp.HiGHS().available()
    except Exception:
        return False


def name() -> str:
    return "HiGHS" if highs_available() else "CBC"


def solver(msg: bool = False, time_limit: float | None = None, gap: float | None = None,
           threads: int | None = None):
    if name() == "HiGHS":
        return pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
    return pulp.PULP_CBC_CMD(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
