"""End-to-end build optimizer (class agnostic; the kit supplies the mechanics).

Alternating optimization:

    specs  ->  rotation  ->  stigmas  ->  per-skill level curves + stat weights
           ->  Daevanion nodes + skill points (integer program)  ->  repeat

Each step keeps everything else fixed and only accepts improvements, so the
DPS is monotone across steps up to the noise-free simulator's resolution.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field, replace

from ..kit.base import Build, ClassData, sp_to_reach, spec_slots, stigma_points_to_reach
from ..run import Scenario, kit_module, prepare
from ..sim.engine import Sim
from . import daevanion as daev_opt
from .rotation import describe, materialize, optimize_rotation
from .statweights import node_values, stat_weights

_CTX: dict = {}


def _pmap(fn, items, workers: int | None = None):
    """Parallel map over a module-level worker using fork (falls back to serial)."""
    import multiprocessing as mp
    import os
    items = list(items)
    workers = workers or min(4, os.cpu_count() or 1)
    if workers <= 1 or len(items) < 4:
        return [fn(x) for x in items]
    try:
        ctx = mp.get_context("fork")
    except ValueError:
        return [fn(x) for x in items]
    with ctx.Pool(workers) as pool:
        return pool.map(fn, items, chunksize=max(1, len(items) // (workers * 4)))


def _curve_worker(sid):
    opt, build, policy, max_level = _CTX["curve"]
    return sid, opt._curve_for(build, policy, sid, max_level)


def _stigma_worker(job):
    opt, build, policy = _CTX["stigma"]
    combo, levels = job
    b2 = build.copy()
    b2.stigmas = dict(zip(combo, levels))
    return job, opt.evaluate(b2, policy)


def _sp_worker(moves):
    opt, build, policy = _CTX["sp"]
    cd = opt.cd
    b2 = build.copy()
    for sid, d in moves:
        b2.sp[sid] = b2.sp.get(sid, 1) + d
        if b2.sp[sid] <= 1:
            b2.sp.pop(sid)
    b2 = opt._clean_specs(b2)
    before = opt._with_gear(build).effective_levels(cd)
    after = opt._with_gear(b2).effective_levels(cd)
    if any(spec_slots(after.get(sid, 1)) > spec_slots(before.get(sid, 1)) for sid, _ in moves):
        b2 = opt.optimize_specs(b2, policy, passes=1)
    return moves, opt.evaluate(b2, policy), b2


#: Stigmas with no damage contribution (never chosen by the DPS optimizer).
DEFENSIVE_STIGMAS = {"Steel Barrier", "Arctic Armor", "Hibernation", "Curse: Tree"}


@dataclass
class OptResult:
    build: Build
    policy: list
    dps: float
    result: object
    weights: list
    history: list = field(default_factory=list)
    curves: dict = field(default_factory=dict)


class Optimizer:
    def __init__(self, cls: str, scenario: Scenario, daev_budget: int = 360,
                 stigma_points: int | None = None, sp_budget: int | None = None,
                 search_duration: float | None = None, verbose: bool = True, gear_bonus: dict | None = None):
        self.cls = cls
        self.cd = ClassData(cls)
        self.scenario = scenario
        self.daev_budget = daev_budget
        bud = self.cd.budget(45)
        self.sp_budget = sp_budget if sp_budget is not None else bud["skill"]
        self.stigma_points = stigma_points if stigma_points is not None else bud["stigma"] + 1
        self.slots = bud["slots"]
        self.search_cfg = replace(scenario.config, duration=search_duration or scenario.config.duration)
        self.verbose = verbose
        self.gear_bonus = gear_bonus or {}
        self.history: list = []
        self._rotation_keys: set = set()    # kit actions the last rotation search could use
        self.t0 = time.time()

    def log(self, msg: str):
        if self.verbose:
            print(f"[{time.time() - self.t0:6.0f}s] {msg}", flush=True)

    # ------------------------------------------------------------ evaluation
    def evaluate(self, build: Build, policy: list, cfg=None, filler=None):
        cd, b, kit, stats = prepare(build, self.scenario)
        pol = self._fit_policy(policy, kit)
        sim = Sim(stats.derived(), kit.actions, materialize(pol), self.scenario.target,
                  cfg or self.search_cfg, hooks=kit.hooks, cond_mods=kit.cond_mods)
        return sim.run().dps

    def _fit_policy(self, policy: list, kit) -> list:
        """Drop actions the kit lacks and append new ones before the filler."""
        keys = lambda e: e[0] if isinstance(e, tuple) else e
        pol = [e for e in policy if keys(e) in kit.actions]
        present = {keys(e) for e in pol}
        if any(k.startswith("hellfire_c") for k in present):
            present |= {k for k in kit.actions if k.startswith("hellfire_c")}
        # actions the rotation search already saw and dropped stay dropped;
        # only actions new since then (another stigma, a newly useful skill) are added
        seen = self._rotation_keys
        missing = [k for k in kit.policy if keys(k) not in present and keys(k) not in seen]
        is_last_filler = lambda e: kit.actions[keys(e)].is_filler and not isinstance(e, tuple)
        filler_idx = next((i for i, e in enumerate(pol) if is_last_filler(e)), len(pol))
        for k in missing:
            if kit.actions[keys(k)].is_filler:
                continue
            pol.insert(filler_idx, k)
            filler_idx += 1
        if not any(is_last_filler(e) for e in pol):
            pol.append(kit.filler)
        return pol

    # ---------------------------------------------------------------- steps
    def initial_build(self) -> Build:
        cd = self.cd
        tp = cd.raw.get("top_players", {})
        b = Build(self.cls)
        b.bonus = dict(self.gear_bonus)
        avg = {**tp.get("skills", {}), **tp.get("passives", {})}
        ranked = sorted(cd.skills.values(), key=lambda s: -(avg.get(s["name"], {}).get("avg_level") or 0))
        sp = self.sp_budget
        for s in ranked:
            if s["kind"] == "stigma":
                continue
            if sp >= 21:
                b.sp[s["id"]] = 10
                sp -= 21
        stig = [n for n in tp.get("stigmas", {}) if n not in DEFENSIVE_STIGMAS]
        stig_ids = [cd.by_name[n]["id"] for n in stig if n in cd.by_name][: self.slots]
        if len(stig_ids) < self.slots:
            for s in cd.skills.values():
                if s["kind"] == "stigma" and s["name"] not in DEFENSIVE_STIGMAS and s["id"] not in stig_ids:
                    stig_ids.append(s["id"])
                if len(stig_ids) >= self.slots:
                    break
        b.stigmas = self._distribute_stigma(stig_ids, [10] + [5] * (len(stig_ids) - 1))
        return b

    def _distribute_stigma(self, ids, levels):
        out = dict(zip(ids, levels))
        while sum(stigma_points_to_reach(l) for l in out.values()) > self.stigma_points:
            k = max(out, key=out.get)
            out[k] -= 1
        return out

    def optimize_specs(self, build: Build, policy: list, passes: int = 2) -> Build:
        mod = kit_module(self.cls)
        best = self.evaluate(build, policy)
        for _ in range(passes):
            changed = False
            opts = mod.spec_options(self.cd, self._with_gear(build))
            for sid, combos in opts.items():
                cur = build.specs.get(sid, ())
                for combo in combos:
                    if tuple(sorted(combo)) == tuple(sorted(cur)):
                        continue
                    b2 = build.copy()
                    b2.specs[sid] = tuple(combo)
                    v = self.evaluate(b2, policy)
                    # strictly better, or equal but filling an empty slot
                    fills = len(combo) > len(cur) and v >= best * (1 - 1e-9)
                    if v > best * (1 + 1e-7) or fills:
                        best, build, cur, changed = max(v, best), b2, tuple(combo), True
            if not changed:
                break
        return build

    def _with_gear(self, build: Build) -> Build:
        from ..model.character import load_loadout, loadout_stats
        lo = load_loadout(self.scenario.loadout) if isinstance(self.scenario.loadout, str) else self.scenario.loadout
        b = build.copy()
        for sid, lv in loadout_stats(lo).skill_bonus.items():
            b.bonus[sid] = b.bonus.get(sid, 0) + lv
        return b

    def optimize_rotation(self, build: Build, policy: list | None, restarts: int = 2):
        cd, b, kit, stats = prepare(build, self.scenario)
        start = None
        if policy:
            start = [e for e in self._fit_policy(policy, kit)
                     if isinstance(e, tuple) or not kit.actions[e].is_filler]
        r = optimize_rotation(stats.derived(), kit, self.scenario.target, self.scenario.config,
                              start=start, restarts=restarts,
                              search_duration=self.search_cfg.duration)
        self._rotation_keys = set(kit.actions)
        return r.policy, r.dps, r.result

    def optimize_stigmas(self, build: Build, policy: list) -> Build:
        cd = self.cd
        cands = [s["id"] for s in cd.skills.values()
                 if s["kind"] == "stigma" and s["name"] not in DEFENSIVE_STIGMAS]
        # level patterns that spend the stigma points (levels unlock specs at 5/10/15)
        patterns = []
        for lv in itertools.product([1, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15], repeat=self.slots):
            if sum(stigma_points_to_reach(l) for l in lv) <= self.stigma_points:
                patterns.append(lv)
        # keep only maximal patterns (no free point left to add a level)
        def maximal(p):
            spent = sum(stigma_points_to_reach(l) for l in p)
            return all(spent - stigma_points_to_reach(l) + stigma_points_to_reach(l + 1) > self.stigma_points
                       for l in p)
        patterns = sorted({tuple(sorted(p, reverse=True)) for p in patterns if maximal(p)})
        best_b, best = build, self.evaluate(build, policy)
        # stage 1: which set (uniform-ish pattern), stage 2: level assignment for top sets
        base_pat = max(patterns, key=lambda p: (p.count(10), -p.count(1)))
        _CTX["stigma"] = (self, build, policy)
        jobs = [(combo, base_pat) for combo in itertools.combinations(cands, self.slots)]
        scored = sorted(((v, job[0]) for job, v in _pmap(_stigma_worker, jobs)), reverse=True)
        jobs = []
        for _, combo in scored[:6]:
            for pat in patterns:
                for perm in set(itertools.permutations(pat)):
                    jobs.append((combo, perm))
        for (combo, perm), v in _pmap(_stigma_worker, jobs):
            if v > best * (1 + 1e-7):
                best = v
                best_b = build.copy()
                best_b.stigmas = dict(zip(combo, perm))
        return best_b

    def level_curves(self, build: Build, policy: list, max_level: int = 20) -> dict[int, list[float]]:
        """DPS as a function of each skill's effective level (best specs at each level)."""
        sids = [sid for sid, s in self.cd.skills.items() if s["kind"] != "stigma"]
        _CTX["curve"] = (self, build, policy, max_level)
        curves = {}
        for sid, curve in _pmap(_curve_worker, sids):
            # flat curves (no DPS effect) are dropped to keep the program small
            if max(curve[1:]) - min(curve[1:]) > 1e-6:
                curves[sid] = curve
        return curves

    def _curve_for(self, build: Build, policy: list, sid: int, max_level: int) -> list[float]:
        mod = kit_module(self.cls)
        cd = self.cd
        s = cd.skills[sid]
        L_now = self._with_gear(build).effective_levels(cd)
        curve = [0.0]
        for L in range(1, max_level + 1):
            b2 = build.copy()
            b2.bonus[sid] = b2.bonus.get(sid, 0) + (L - L_now.get(sid, 1))
            best = self.evaluate(b2, policy)
            if s["kind"] == "active" and s.get("specs"):
                opts = mod.spec_options(cd, self._with_gear(b2)).get(sid, [()])
                for combo in opts:
                    b3 = b2.copy()
                    b3.specs[sid] = tuple(combo)
                    best = max(best, self.evaluate(b3, policy))
            curve.append(best)
        return curve

    def allocate(self, build: Build, policy: list):
        curves = self.level_curves(build, policy)
        cd, b, kit, stats = prepare(build, self.scenario)
        weights = stat_weights(stats, kit, policy, self.scenario.target, self.search_cfg)
        nv = node_values(self.cd, weights)
        # bonus from gear stays outside the program; Daevanion/SP replace the build's
        gear = self._gear_bonus()
        bonus = dict(gear)
        for k, v in build.bonus.items():
            bonus[k] = bonus.get(k, 0) + v
        sol = daev_opt.solve(self.cd, curves, nv, daev_budget=self.daev_budget,
                             sp_budget=self.sp_budget, bonus=bonus)
        b2 = build.copy()
        b2.daevanion = sol["nodes"]
        b2.sp = {sid: lv for sid, lv in sol["sp"].items() if lv > 1}
        # skills without a value curve keep level 1 (no points)
        return b2, sol, curves, weights

    def polish_sp(self, build: Build, policy: list, rounds: int = 6) -> Build:
        """Full-simulation local search on skill points after the integer program.

        Moves: raise one skill by 1-2 levels from free points, or move 1-2
        levels from one skill to another.  Catches interactions the separable
        level curves miss (spec thresholds, buffs that scale other skills).
        """
        cd = self.cd
        trainable = sorted(sid for sid, s in cd.skills.items()
                           if s["kind"] in ("active", "passive") and s.get("buyMax", 10) > 1)
        best = self.evaluate(build, policy)
        for _ in range(rounds):
            slack = self.sp_budget - build.sp_spent()
            jobs = []
            for b in trainable:
                lb, top = build.sp.get(b, 1), cd.skills[b].get("buyMax", 10)
                for db in (1, 2):
                    if lb + db > top:
                        continue
                    cost = sp_to_reach(lb + db) - sp_to_reach(lb)
                    if cost <= slack:
                        jobs.append(((b, db),))
                        continue
                    for a in trainable:
                        la = build.sp.get(a, 1)
                        for da in (1, 2):
                            if a == b or la - da < 1:
                                continue
                            if cost <= slack + sp_to_reach(la) - sp_to_reach(la - da):
                                jobs.append(((a, -da), (b, db)))
                                break       # taking a further level from ``a`` only wastes points
            _CTX["sp"] = (self, build, policy)
            moves, v, b2 = max(_pmap(_sp_worker, jobs), key=lambda r: r[1], default=(None, 0, None))
            if not moves or v <= best * (1 + 1e-4):     # ignore noise-level moves
                break
            self.log("polish SP: " + ", ".join(f"{cd.skills[s]['name']} {d:+d}" for s, d in moves)
                     + f" -> {v:.0f} (was {best:.0f})")
            build, best = b2, v
        return build

    def _gear_bonus(self) -> dict:
        from ..model.character import load_loadout, loadout_stats
        lo = load_loadout(self.scenario.loadout) if isinstance(self.scenario.loadout, str) else self.scenario.loadout
        return dict(loadout_stats(lo).skill_bonus)

    def _clean_specs(self, build: Build) -> Build:
        """Drop specs that became illegal after a level change."""
        cd = self.cd
        L = self._with_gear(build).effective_levels(cd)
        b = build.copy()
        for sid in list(b.specs):
            s = cd.skills[sid]
            ok = [x for x in b.specs[sid] if any(sp["id"] == x and sp["unlock"] <= L.get(sid, 1)
                                                 for sp in s["specs"])]
            b.specs[sid] = tuple(ok[: spec_slots(L.get(sid, 1))])
        return b

    # ----------------------------------------------------------------- main
    def run(self, iterations: int = 3) -> OptResult:
        build = self.initial_build()
        policy = list(kit_module(self.cls).build_kit(self._with_gear(build), self.cd).policy)
        curves, weights = {}, []
        for it in range(iterations):
            build = self._clean_specs(build)
            build = self.optimize_specs(build, policy)
            self.log(f"iter {it}: specs -> {self.evaluate(build, policy):.0f}")
            policy, dps, _ = self.optimize_rotation(build, policy)
            self.log(f"iter {it}: rotation -> {dps:.0f}  {describe(policy)}")
            build = self.optimize_stigmas(build, policy)
            self.log(f"iter {it}: stigmas -> {self.evaluate(build, policy):.0f} "
                     f"{ {self.cd.skills[k]['name']: v for k, v in build.stigmas.items()} }")
            build2, sol, curves, weights = self.allocate(build, policy)
            build2 = self._clean_specs(build2)
            build2 = self.optimize_specs(build2, policy)
            v_old, v_new = self.evaluate(build, policy), self.evaluate(build2, policy)
            self.log(f"iter {it}: daevanion/SP ({sol['status']}, {sol['daev_cost']} pts, "
                     f"{sol['sp_cost']} SP) -> {v_new:.0f} (was {v_old:.0f})")
            if v_new >= v_old:
                build = build2
            self.history.append({"iter": it, "dps": max(v_old, v_new)})
        build = self.polish_sp(build, policy)
        build = self.optimize_specs(build, policy, passes=3)
        policy, dps, res = self.optimize_rotation(build, policy, restarts=4)
        cd, b, kit, stats = prepare(build, self.scenario)
        weights = stat_weights(stats, kit, policy, self.scenario.target, self.scenario.config)
        self.log(f"final: {dps:.0f} DPS  {describe(policy)}")
        return OptResult(build, policy, dps, res, weights, self.history, curves)
