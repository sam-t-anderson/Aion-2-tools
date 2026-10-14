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
    require()
    return pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads)


def require() -> None:
    """Fail fast, with actionable guidance, when the in-process solver is unavailable.

    Called at the start of an optimize so the user gets this immediately instead of after the
    rotation/stat-weight search (which does not need the solver) appears to stall.
    """
    if not highs_available():
        raise RuntimeError(
            "The HiGHS solver dependency is missing or unavailable. The installer and portable "
            "builds bundle it; if you installed from source, run 'pip install highspy' (or "
            "reinstall aion2calc with its dependencies) and restart the app."
        )
