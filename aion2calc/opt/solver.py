"""The integer-program solver used by the optimizers.

HiGHS (the ``highspy`` package) is required because it runs in-process. PuLP's
bundled CBC runs as an external subprocess and can outlive the GUI optimizer
when a solve stalls, leaving the user with an apparent hang. ``highspy`` is a
required project dependency and is collected into packaged builds.
"""
from __future__ import annotations

import pulp


def highs_available() -> bool:
    try:
        return pulp.HiGHS().available()
    except Exception:
        return False


def name() -> str:
    return "HiGHS" if highs_available() else "HiGHS unavailable"


def solver(msg: bool = False, time_limit: float | None = None, gap: float | None = None,
           threads: int | None = None):
    if not highs_available():
        raise RuntimeError(
            "The HiGHS solver dependency is missing or unavailable. "
            "Reinstall aion2calc with its required dependencies."
        )
    return pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)
