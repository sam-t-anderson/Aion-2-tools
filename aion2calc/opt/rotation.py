"""Search for the best priority list (and macro) for a fixed build.

A policy is an ordered list of action keys, optionally with a condition, and
always ends with a filler.  We hill-climb over insert / swap / drop moves with a
few restarts; the simulator is deterministic so plain comparisons are safe.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..sim.engine import Sim

# Conditions a policy entry can carry.  They receive the Sim.
CONDITIONS = {
    "sync_de": lambda s: s.has_debuff("delayed_explosion") or s.remaining_cd("delayed_explosion") > 3.0
    or "delayed_explosion" not in s.actions,
    "in_ee": lambda s: s.has_buff("element_enhancement") or s.remaining_cd("element_enhancement") > 4.0
    or "element_enhancement" not in s.actions,
    "mp_hi": lambda s: s.mp >= 0.6 * s.base.mp_max,
}


#: Only these entries are offered the sync conditions during the search.
CONDITIONAL_KEYS = {"fire_wall", "cold_storm", "firestorm", "blaze", "winters_shackles",
                    "glacial_smite", "divine_burst", "frost_burst", "bittercold_wind"}


def materialize(policy: list) -> list:
    out = []
    for e in policy:
        if isinstance(e, tuple):
            key, cname = e
            out.append((key, CONDITIONS[cname]) if cname else key)
        else:
            out.append(e)
    return out


def describe(policy: list) -> list[str]:
    out = []
    for e in policy:
        if isinstance(e, tuple):
            key, cname = e
            out.append(f"{key} [{cname}]" if cname else key)
        else:
            out.append(e)
    return out


@dataclass
class RotationResult:
    policy: list
    dps: float
    result: object


class Evaluator:
    def __init__(self, derived, kit, target, config):
        self.derived, self.kit, self.target, self.config = derived, kit, target, config
        self.cache: dict = {}
        self.evals = 0

    def __call__(self, policy: list):
        key = tuple(policy)
        if key in self.cache:
            return self.cache[key]
        sim = Sim(self.derived, self.kit.actions, materialize(policy), self.target, self.config,
                  hooks=self.kit.hooks, cond_mods=self.kit.cond_mods)
        res = sim.run()
        self.evals += 1
        self.cache[key] = (res.dps, res)
        return self.cache[key]


def candidate_keys(kit) -> tuple[list, list, list]:
    keys = [k for k, a in kit.actions.items() if not a.is_filler]
    hell = [k for k in keys if k.startswith("hellfire_c")]
    others = [k for k in keys if not k.startswith("hellfire_c")]
    fillers = [k for k, a in kit.actions.items() if a.is_filler]
    return others, hell, fillers


def optimize_rotation(derived, kit, target, config, start: list | None = None, restarts: int = 3,
                      seed: int = 7, max_passes: int = 6, allow_conditions: bool = True,
                      search_duration: float | None = None) -> RotationResult:
    from dataclasses import replace
    rng = random.Random(seed)
    scfg = replace(config, duration=search_duration) if search_duration else config
    ev = Evaluator(derived, kit, target, scfg)
    others, hell, fillers = candidate_keys(kit)

    def base_order():
        return [k for k in kit.policy if isinstance(k, tuple) or not kit.actions[k].is_filler]

    def score(pol):
        return ev(pol)[0]

    best_pol, best = None, -1.0
    seeds = []
    init = start or base_order()
    for f in fillers:
        seeds.append(list(init) + [f])
    for _ in range(restarts):
        pol = list(base_order())
        rng.shuffle(pol)
        seeds.append(pol + [rng.choice(fillers)])

    for pol in seeds:
        pol = _normalize(pol, hell, fillers)
        cur = score(pol)
        for _ in range(max_passes):
            improved = False
            for cand in _neighbours(pol, others, hell, fillers, allow_conditions):
                sc = score(cand)
                if sc > cur * (1 + 1e-6):
                    pol, cur, improved = cand, sc, True
            if not improved:
                break
        if cur > best:
            best_pol, best = pol, cur
    final = Evaluator(derived, kit, target, config)(best_pol)
    return RotationResult(best_pol, final[0], final[1])


def _key(e):
    return e[0] if isinstance(e, tuple) else e


def _normalize(pol, hell, fillers):
    seen, out = set(), []
    for e in pol:
        k = _key(e)
        if k in hell:
            k2 = "hellfire"
        else:
            k2 = k
        if k2 in seen:
            continue
        seen.add(k2)
        out.append(e)
    body = [e for e in out if _key(e) not in fillers or isinstance(e, tuple)]
    fill = [e for e in out if _key(e) in fillers and not isinstance(e, tuple)]
    return body + [fill[-1] if fill else fillers[0]]


def _neighbours(pol, others, hell, fillers, allow_conditions):
    body, filler = pol[:-1], pol[-1]
    n = len(body)
    # moves: relocate one entry (nearby positions, plus to the front / back)
    for i in range(n):
        for j in set(range(max(0, i - 3), min(n, i + 4))) | {0, n - 1}:
            if i == j:
                continue
            b = list(body)
            e = b.pop(i)
            b.insert(j, e)
            yield b + [filler]
    # drop an entry / add a missing one at each position
    present = {_key(e) for e in body}
    for i in range(n):
        yield body[:i] + body[i + 1:] + [filler]
    missing = [k for k in others if k not in present]
    if not any(_key(e) in hell for e in body) and hell:
        missing.append(hell[0])
    for k in missing:
        for j in range(n + 1):
            yield body[:j] + [k] + body[j:] + [filler]
    # weave the other filler(s) while MP is high
    for f in fillers:
        if f != _key(filler) and f not in present:
            for j in (max(0, n - 2), n):
                yield body[:j] + [(f, "mp_hi")] + body[j:] + [filler]
    # hellfire charge level
    for i, e in enumerate(body):
        if _key(e) in hell:
            for h in hell:
                if h != _key(e):
                    ne = (h, e[1]) if isinstance(e, tuple) else h
                    yield body[:i] + [ne] + body[i + 1:] + [filler]
    # filler choice
    for f in fillers:
        if f != filler:
            yield body + [f]
    # conditions
    if allow_conditions:
        for i, e in enumerate(body):
            k = _key(e)
            if not (k in hell or k in CONDITIONAL_KEYS):
                continue
            cur = e[1] if isinstance(e, tuple) else None
            for cname in (None, "sync_de", "in_ee", "mp_hi"):
                if cname != cur:
                    ne = (k, cname) if cname else k
                    yield body[:i] + [ne] + body[i + 1:] + [filler]
