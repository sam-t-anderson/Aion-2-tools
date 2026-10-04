"""Turn an optimized priority list into an AION 2 in-game Skill Macro + manual keys.

The in-game Skill Macro (added in the KR 2026-01-28 patch) runs while its key
is held, trying each step in order with a per-step delay; manual presses always
take priority.  We put the short-cooldown core in the macro (fillers last) and
leave long-cooldown burst skills on their own keys, then simulate the macro's
round-robin behaviour to measure how close it gets to the ideal priority.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..sim.engine import Sim
from .rotation import CONDITIONS


@dataclass
class MacroPlan:
    macro_steps: list
    manual: list
    dps_macro: float
    dps_priority: float
    alt_steps: list | None = None       # the other layout (one-button or macro + manual keys)
    alt_manual: list | None = None
    dps_alt: float = 0.0


class MacroPolicy:
    """Manual keys first (priority order), then the macro steps round-robin."""

    def __init__(self, manual: list, steps: list):
        self.manual = manual
        self.steps = steps
        self.ptr = 0

    def __call__(self, sim: Sim):
        for e in self.manual:
            key, cond = (e if isinstance(e, tuple) else (e, None))
            a = sim.actions.get(key)
            if a and sim.usable(a) and (cond is None or CONDITIONS[cond](sim)):
                return a
        n = len(self.steps)
        for k in range(n):
            key = self.steps[(self.ptr + k) % n]
            a = sim.actions.get(key)
            if a and sim.usable(a):
                self.ptr = (self.ptr + k + 1) % n
                return a
        return None


def plan_macro(derived, kit, policy: list, target, config, macro_cd_limit: float = 20.0) -> MacroPlan:
    keyf = lambda e: e[0] if isinstance(e, tuple) else e
    policy = [e for e in policy if keyf(e) in kit.actions]
    manual, steps = [], []
    for e in policy:
        a = kit.actions[keyf(e)]
        if a.is_filler or (a.cooldown and a.cooldown * (1 - derived.cdr) <= macro_cd_limit
                           and not isinstance(e, tuple)):
            steps.append(keyf(e))
        else:
            manual.append(e)
    def run(pol):
        return Sim(derived, kit.actions, pol, target, config, hooks=kit.hooks,
                   cond_mods=kit.cond_mods).run().dps
    from .rotation import materialize
    dps_pri = run(materialize(policy))
    best_steps, best = steps, run(MacroPolicy(manual, steps))
    # the macro cycles, so a filler that sits first would starve the core: try orders
    fillers = [s for s in steps if kit.actions[s].is_filler]
    core = [s for s in steps if not kit.actions[s].is_filler]
    import itertools
    if len(core) <= 6:
        for perm in itertools.permutations(core):
            cand = list(perm) + fillers
            v = run(MacroPolicy(manual, cand))
            if v > best:
                best, best_steps = v, cand
    # one-button alternative: everything in the macro; adjacent-swap search on the order
    order = [keyf(e) for e in policy if not kit.actions[keyf(e)].is_filler] + \
        [keyf(e) for e in policy if kit.actions[keyf(e)].is_filler]
    one, one_v = order, run(MacroPolicy([], order))
    improved = True
    while improved:
        improved = False
        for i in range(len(one) - 1):
            cand = one[:i] + [one[i + 1], one[i]] + one[i + 2:]
            v = run(MacroPolicy([], cand))
            if v > one_v * (1 + 1e-6):
                one, one_v, improved = cand, v, True
    split = (best_steps, manual, best)
    single = (one, [], one_v)
    first, second = (single, split) if one_v >= best else (split, single)
    return MacroPlan(first[0], first[1], first[2], dps_pri, second[0], second[1], second[2])
