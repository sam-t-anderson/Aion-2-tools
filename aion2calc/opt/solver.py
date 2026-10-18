"""The integer-program solver used by the optimizers.

HiGHS (the ``highspy`` package) is required because it runs in-process. PuLP's
bundled CBC runs as an external subprocess and can outlive the GUI optimizer
when a solve stalls, leaving the user with an apparent hang. ``highspy`` is a
required project dependency and is collected into packaged builds.
"""
from __future__ import annotations

import math

import pulp


class _HiGHS(pulp.HiGHS):
    """PuLP's in-process HiGHS, optionally starting from the variables' current values.

    PuLP 3.3 honours ``warmStart`` only in ``HiGHS_CMD``; the in-process class hands it to
    HiGHS as an unknown option, which HiGHS ignores. So pass the start to HiGHS directly.
    """

    def __init__(self, *args, warm_start: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.warm_start = warm_start

    def callSolver(self, lp):
        if self.warm_start:
            try:
                import highspy
                values = [0.0] * lp.solverModel.getNumCol()
                for var in lp.variables():
                    values[var.index] = float(var.varValue or 0.0)
                start = highspy.HighsSolution()
                start.col_value = values
                start.value_valid = True
                lp.solverModel.setSolution(start)   # HiGHS checks it and keeps it as the incumbent if feasible
            except Exception:
                pass                                # a start is only a hint
        super().callSolver(lp)


def highs_available() -> bool:
    try:
        return pulp.HiGHS().available()
    except Exception:
        return False


def name() -> str:
    return "HiGHS" if highs_available() else "HiGHS unavailable"


def solver(msg: bool = False, time_limit: float | None = None, gap: float | None = None,
           threads: int | None = None, warm_start: bool = False):
    require()
    return _HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap, threads=threads, warm_start=warm_start)


def outcome(prob) -> dict:
    """HiGHS's own account of the last solve of ``prob``.

    PuLP reports a run that stopped at its time limit with a solution as "Optimal". HiGHS
    knows better: ``time_limited`` says it stopped there, and ``bound`` is the best objective
    it could not rule out (None when it proved none, or when another solver ran).
    """
    try:
        import highspy
        model = prob.solverModel
        time_limited = model.getModelStatus() == highspy.HighsModelStatus.kTimeLimit
        bound = model.getInfo().mip_dual_bound
    except Exception:
        return {"time_limited": False, "bound": None}
    if prob.sense == pulp.LpMaximize:
        bound = -bound                      # PuLP hands HiGHS a maximization as a negated minimization
    return {"time_limited": time_limited, "bound": bound if math.isfinite(bound) else None}


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
