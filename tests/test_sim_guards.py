"""Safety guards so a pathological build can never hang the optimizer UI.

Two independent protections:

* The simulator always terminates. A kit hook that lands another hit at the same instant can
  otherwise recurse (``delay=0`` lands inline) or spin the same-instant event queue forever; with
  extreme imported gear a proc can self-trigger, which used to freeze the PvE optimizer mid
  "stat weights: timing simulations". A depth/step/wall-clock cap turns that into a bounded,
  flagged result instead of a hang or RecursionError.
* The optimize fails fast when the in-process HiGHS solver is missing, with actionable guidance,
  instead of running the (solver-free) rotation and stat-weight search first and looking stuck.
"""
import time

from aion2calc.opt.rotation import materialize
from aion2calc.run import prepare
from aion2calc.scenarios import dummy, typical_build
from aion2calc.sim.engine import Sim


def _gladiator_sim(hooks):
    scen = dummy("gladiator_l45_global_median")
    _, _, kit, stats = prepare(typical_build("gladiator"), scen)
    policy = materialize(list(kit.actions)[:1])
    return Sim(stats.derived(), kit.actions, policy, scen.target, scen.config, hooks=hooks)


def test_self_scheduling_hook_terminates_and_is_flagged():
    # Every landed hit lands another at the same instant: an unbounded synchronous chain.
    def runaway(sim, t, info):
        sim.hit("runaway proc", 1.0, 0.0, delay=0.0)

    started = time.monotonic()
    result = _gladiator_sim([runaway]).run()
    assert time.monotonic() - started < 10            # bounded: no hang, no RecursionError
    assert result.dps >= 0                            # a usable (if degraded) result came back
    # The guard records that it tripped, so callers can tell the run was degenerate.
    sim = _gladiator_sim([runaway]); sim.run()
    assert sim._degenerate is True


def test_healthy_sim_is_not_flagged_degenerate():
    scen = dummy("gladiator_l45_global_median")
    _, _, kit, stats = prepare(typical_build("gladiator"), scen)
    policy = materialize(list(kit.policy))
    sim = Sim(stats.derived(), kit.actions, policy, scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    sim.run()
    assert sim._degenerate is False                   # normal fights never trip the caps


def test_solver_require_raises_with_guidance_when_unavailable(monkeypatch):
    from aion2calc.opt import solver
    monkeypatch.setattr(solver, "highs_available", lambda: False)
    try:
        solver.require()
    except RuntimeError as err:
        assert "highspy" in str(err).lower()          # tells the user exactly what to install
    else:
        raise AssertionError("solver.require() should raise when HiGHS is unavailable")


def test_optimizer_run_fails_fast_without_solver(monkeypatch):
    from aion2calc.opt import solver
    from aion2calc.opt.pipeline import Optimizer
    from aion2calc.scenarios import SCENARIOS
    monkeypatch.setattr(solver, "highs_available", lambda: False)
    opt = Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"), verbose=False)
    started = time.monotonic()
    try:
        opt.run(iterations=1)
    except RuntimeError as err:
        assert "highs" in str(err).lower()
    else:
        raise AssertionError("Optimizer.run() should fail fast when HiGHS is unavailable")
    # Fails up front (before the long rotation/stat-weight search), not after a stall.
    assert time.monotonic() - started < 5
