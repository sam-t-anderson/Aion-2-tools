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
from .solver import name as solver_name
from .statweights import node_values, stat_weights

_CTX: dict = {}
DAEV_SOLVER_TIME_LIMIT = 120


def _pool_init(ctx: dict) -> None:
    """Pool-worker setup for the ``spawn`` start method, where the child does not
    inherit the parent's ``_CTX`` (as it does with ``fork``)."""
    _CTX.update(ctx)


def _pmap(fn, items, workers: int | None = None, ctx: dict | None = None, progress=None,
          fallback=None):
    """Parallel map over a module-level worker.

    Uses ``fork`` where available (Linux, macOS) and ``spawn`` otherwise
    (Windows, where the earlier fork-only path silently ran serial and made
    "Optimize my build" take many minutes). ``ctx`` is the ``_CTX`` payload the
    workers need; with ``spawn`` it is handed to each worker through
    ``_pool_init`` since the child starts from a fresh import. Any problem
    starting the pool falls back to a correct serial run.
    """
    import multiprocessing as mp
    import os
    import sys
    items = list(items)
    workers = workers or min(4, os.cpu_count() or 1)
    def serial():
        results = []
        report_every = max(1, len(items) // 20)
        for index, item in enumerate(items, 1):
            results.append(fn(item))
            if progress and (index % report_every == 0 or index == len(items)):
                progress(index, len(items))
        return results

    if workers <= 1 or len(items) < 4:
        return serial()
    if getattr(sys, "frozen", False):
        # The packaged (windowed) app has no console, so spawn-based worker pools re-launch the bundle
        # with no stdio and deadlock ("Optimize my build" hangs). Run serial there: slower, but it finishes.
        return serial()
    methods = mp.get_all_start_methods()
    method = "fork" if "fork" in methods else "spawn" if "spawn" in methods else None
    if method is None:
        return serial()
    init, initargs = (None, ())
    if method == "spawn" and ctx is not None:          # fork inherits _CTX; spawn must be given it
        init, initargs = _pool_init, (ctx,)
    try:
        mpctx = mp.get_context(method)
        with mpctx.Pool(workers, initializer=init, initargs=initargs) as pool:
            results = []
            report_every = max(1, len(items) // 20)
            for index, result in enumerate(
                    pool.imap(fn, items, chunksize=max(1, len(items) // (workers * 4))), 1):
                results.append(result)
                if progress and (index % report_every == 0 or index == len(items)):
                    progress(index, len(items))
            return results
    except Exception as exc:                            # a pickling or start-up problem: stay correct, run serial
        if fallback:
            fallback(f"parallel workers unavailable ({type(exc).__name__}); continuing serially")
        return serial()


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
                 search_duration: float | None = None, verbose: bool = True, gear_bonus: dict | None = None,
                 progress=None, survival=None, skill_reserves=None):
        self.skill_reserves = skill_reserves
        self.min_sp = (skill_reserves or {}).get("sp", {})
        self.min_stigmas = (skill_reserves or {}).get("stigmas", {})
        self.survival = survival
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
        self.progress = progress            # optional callback(str): live phase updates for the app UI
        self.gear_bonus = gear_bonus or {}
        self.history: list = []
        self._rotation_keys: set = set()    # kit actions the last rotation search could use
        self.t0 = time.time()

    def log(self, msg: str):
        if self.verbose:
            print(f"[{time.time() - self.t0:6.0f}s] {msg}", flush=True)
        if self.progress:
            try:
                self.progress(f"[{time.time() - self.t0:.0f}s] {msg}")
            except Exception:
                pass

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
        b.sp = {sid:level for sid,level in self.min_sp.items() if level>1}
        sp = self.sp_budget-b.sp_spent()
        for s in ranked:
            if s["kind"] == "stigma":
                continue
            top = min(10, s.get("buyMax", 10))
            cost = sp_to_reach(top)-sp_to_reach(b.sp.get(s["id"],1))
            if top > 1 and sp >= cost:
                b.sp[s["id"]] = top
                sp -= cost
        stig = [n for n in tp.get("stigmas", {}) if n not in DEFENSIVE_STIGMAS]
        stig_ids = list(self.min_stigmas)
        stig_ids += [cd.by_name[n]["id"] for n in stig if n in cd.by_name and cd.by_name[n]["id"] not in stig_ids][:self.slots-len(stig_ids)]
        if len(stig_ids) < self.slots:
            for s in cd.skills.values():
                if s["kind"] == "stigma" and s["name"] not in DEFENSIVE_STIGMAS and s["id"] not in stig_ids:
                    stig_ids.append(s["id"])
                if len(stig_ids) >= self.slots:
                    break
        while self.min_stigmas and sum(stigma_points_to_reach(self.min_stigmas.get(sid,1)) for sid in stig_ids)>self.stigma_points:
            removable = [sid for sid in stig_ids if sid not in self.min_stigmas]
            if not removable:
                raise ValueError("Reserved stigmas exceed the stigma budget")
            stig_ids.remove(removable[-1])
        b.stigmas = self._distribute_stigma(stig_ids, [10] + [5] * (len(stig_ids) - 1))
        return b

    def _distribute_stigma(self, ids, levels):
        out = {sid:max(level,self.min_stigmas.get(sid,1)) for sid,level in zip(ids,levels)}
        while sum(stigma_points_to_reach(l) for l in out.values()) > self.stigma_points:
            choices = [sid for sid,level in out.items() if level>self.min_stigmas.get(sid,1)]
            if not choices:
                raise ValueError("No feasible stigma allocation fits the reserved levels and budget")
            k = max(choices, key=out.get)
            out[k] -= 1
        return out

    def optimize_specs(self, build: Build, policy: list, passes: int = 2) -> Build:
        build = self._clean_specs(build)  # levels/gear may have changed since the previous search
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
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
                 if s["kind"] == "stigma" and (s["name"] not in DEFENSIVE_STIGMAS or s["id"] in self.min_stigmas)]
        # level patterns that spend the stigma points (levels unlock specs at 5/10/15)
        patterns = []
        levels = sorted({1,3,5,6,7,8,10,11,12,13,15,*self.min_stigmas.values()})
        for lv in itertools.product(levels, repeat=self.slots):
            if sum(stigma_points_to_reach(l) for l in lv) <= self.stigma_points:
                patterns.append(lv)
        # keep only maximal patterns (no free point left to add a level)
        def maximal(p):
            spent = sum(stigma_points_to_reach(l) for l in p)
            return all(l>=20 or spent - stigma_points_to_reach(l) + stigma_points_to_reach(l + 1) > self.stigma_points
                       for l in p)
        patterns = sorted({tuple(sorted(p, reverse=True)) for p in patterns if maximal(p)})
        if not cands or not patterns or self.slots > len(cands):
            self.log("stigma search skipped: no legal candidate sets for this budget")
            return build
        best_b, best = build, self.evaluate(build, policy)
        # stage 1: which set (uniform-ish pattern), stage 2: level assignment for top sets
        base_pat = max(patterns, key=lambda p: (p.count(10), -p.count(1)))
        _CTX["stigma"] = (self, build, policy)
        combos = [combo for combo in itertools.combinations(cands,self.slots) if set(self.min_stigmas).issubset(combo)]
        if self.min_stigmas:
            jobs = []
            for combo in combos:
                try:
                    seed = self._distribute_stigma(combo,base_pat)
                    jobs.append((combo,tuple(seed[sid] for sid in combo)))
                except ValueError:
                    continue
        else:
            jobs = [(combo,base_pat) for combo in combos]
        self.log(f"stigma search: scoring {len(jobs)} stigma combinations")
        scored = sorted(((v, job[0]) for job, v in _pmap(
                            _stigma_worker, jobs, ctx={"stigma": _CTX["stigma"]},
                            progress=lambda done, total: self.log(
                                f"stigma combinations: {done}/{total}"),
                            fallback=self.log)),
                        reverse=True)
        jobs = []
        for _, combo in scored[:6]:
            for pat in patterns:
                for perm in set(itertools.permutations(pat)):
                    if all(level>=self.min_stigmas.get(sid,1) for sid,level in zip(combo,perm)):
                        jobs.append((combo, perm))
        self.log(f"stigma search: comparing {len(jobs)} level assignments across the top {min(6, len(scored))} combinations")
        for (combo, perm), v in _pmap(
                _stigma_worker, jobs, ctx={"stigma": _CTX["stigma"]},
                progress=lambda done, total: self.log(f"stigma levels: {done}/{total}"),
                fallback=self.log):
            if v > best * (1 + 1e-7):
                best = v
                best_b = build.copy()
                best_b.stigmas = dict(zip(combo, perm))
        self.log("stigma search complete")
        return best_b

    def level_curves(self, build: Build, policy: list, max_level: int = 20) -> dict[int, list[float]]:
        """DPS as a function of each skill's effective level (best specs at each level)."""
        sids = [sid for sid, s in self.cd.skills.items() if s["kind"] != "stigma"]
        _CTX["curve"] = (self, build, policy, max_level)
        self.log(f"skill curves: evaluating {len(sids)} skills through level {max_level}")
        curves = {}
        for sid, curve in _pmap(
                _curve_worker, sids, ctx={"curve": _CTX["curve"]},
                progress=lambda done, total: self.log(f"skill curves: {done}/{total} skills"),
                fallback=self.log):
            # flat curves (no DPS effect) are dropped to keep the program small
            if max(curve[1:]) - min(curve[1:]) > 1e-6 or sid in self.min_sp:
                curves[sid] = curve
        self.log(f"skill curves: retained {len(curves)} skills with measurable gains")
        return curves

    def _curve_for(self, build: Build, policy: list, sid: int, max_level: int) -> list[float]:
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
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

    def level_gains(self, build: Build, policy: list, sid: int, extra: int) -> list[float]:
        """DPS with ``sid`` raised by +1..+extra levels, best legal specs at each level."""
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
        s = self.cd.skills[sid]
        out = []
        for k in range(1, extra + 1):
            b2 = build.copy()
            b2.bonus = dict(b2.bonus)
            b2.bonus[sid] = b2.bonus.get(sid, 0) + k
            best = self.evaluate(b2, policy)
            if s["kind"] == "active" and s.get("specs"):
                for combo in mod.spec_options(self.cd, self._with_gear(b2)).get(sid, [()]):
                    b3 = b2.copy()
                    b3.specs[sid] = tuple(combo)
                    best = max(best, self.evaluate(b3, policy))
            out.append(best)
        return out

    def _stat_weights(self, build: Build, policy: list, *, final=False):
        _, _, kit, stats = prepare(build, self.scenario)
        return stat_weights(stats, kit, policy, self.scenario.target,
                            self.scenario.config if final else self.search_cfg,
                            progress=None if final else self.log)

    def allocate(self, build: Build, policy: list):
        curves = self.level_curves(build, policy)
        self.log("skill allocation: calculating stat weights")
        weights = self._stat_weights(build, policy)
        nv = node_values(self.cd, weights)
        # bonus from gear stays outside the program; Daevanion/SP replace the build's
        gear = self._gear_bonus()
        bonus = dict(gear)
        for k, v in build.bonus.items():
            bonus[k] = bonus.get(k, 0) + v
        # This is a mixed integer program and can be the longest single step.
        # Keep the UI's phase indicator current while the in-process HiGHS
        # solver works.
        self.log(f"skill allocation: solving Daevanion/SP with {solver_name()} (up to {DAEV_SOLVER_TIME_LIMIT} s)")
        solver_started = time.monotonic()
        sol = daev_opt.solve(self.cd, curves, nv, daev_budget=self.daev_budget,
                             sp_budget=self.sp_budget, bonus=bonus,
                             time_limit=DAEV_SOLVER_TIME_LIMIT,
                             min_node_hp=(self.survival or {}).get("minimum_node_hp", 0), min_sp=self.min_sp)
        self.log(f"skill allocation: solver finished ({sol['status']}, "
                 f"{time.monotonic() - solver_started:.1f} s)")
        self.log("skill allocation: applying the optimized points")
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
        for round_no in range(1, rounds + 1):
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
                            if a == b or la - da < self.min_sp.get(a,1):
                                continue
                            if cost <= slack + sp_to_reach(la) - sp_to_reach(la - da):
                                jobs.append(((a, -da), (b, db)))
                                break       # taking a further level from ``a`` only wastes points
            _CTX["sp"] = (self, build, policy)
            self.log(f"polish SP: round {round_no}/{rounds}, evaluating {len(jobs)} moves")
            moves, v, b2 = max(_pmap(
                _sp_worker, jobs, ctx={"sp": _CTX["sp"]},
                progress=lambda done, total: self.log(f"polish SP: {done}/{total} moves"),
                fallback=self.log), key=lambda r: r[1], default=(None, 0, None))
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

    def spend_remaining_sp(self, build: Build, policy: list) -> Build:
        """Spend all reachable remaining points, including DPS-neutral utility levels.

        The DPS search deliberately drops flat curves and ignores tiny gains. A
        final small knapsack fills that slack without taking away trained levels.
        Among equally full allocations, simulated marginal DPS breaks ties.
        """
        slack = max(0, self.sp_budget - build.sp_spent())
        if not slack:
            return build
        base = self.evaluate(build, policy)
        choices = []
        for sid, skill in sorted(self.cd.skills.items()):
            if skill["kind"] not in ("active", "passive"):
                continue
            level = build.sp.get(sid, 1)
            options = [(0, level, 0.0)]
            for new_level in range(level + 1, min(10, skill.get("buyMax", 10)) + 1):
                cost = sp_to_reach(new_level) - sp_to_reach(level)
                if cost > slack:
                    break
                trial = build.copy()
                trial.sp[sid] = new_level
                options.append((cost, new_level, self.evaluate(trial, policy) - base))
            if len(options) > 1:
                choices.append((sid, options))
        plans = {0: (0.0, {})}
        for sid, options in choices:
            updated = {}
            for spent, (value, levels) in plans.items():
                for cost, level, gain in options:
                    total = spent + cost
                    if total <= slack and (total not in updated or value + gain > updated[total][0]):
                        updated[total] = (value + gain, {**levels, sid: level})
            plans = updated
        spent = max(plans)
        out = build.copy()
        out.sp.update({sid: lv for sid, lv in plans[spent][1].items() if lv > 1})
        left = self.sp_budget - out.sp_spent()
        self.log(f"skill points: {out.sp_spent()}/{self.sp_budget} spent" +
                 (f"; {left} left because no further trained level fits the budget" if left else ""))
        return out

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
    def run(self, iterations: int = 3, *, initial_build: Build | None = None,
            initial_policy: list | None = None) -> OptResult:
        build = initial_build.copy() if initial_build is not None else self.initial_build()
        policy = (list(initial_policy) if initial_policy is not None else
                  list(kit_module(self.cls, pvp=self.scenario.target.is_player).build_kit(self._with_gear(build), self.cd).policy))
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
            from .survival import node_hp
            floor = (self.survival or {}).get("minimum_node_hp", 0)
            if v_new >= v_old or node_hp(self.cd, build.daevanion)+1e-6 < floor:
                build = build2
            self.history.append({"iter": it, "dps": self.evaluate(build, policy)})
        from .survival import node_hp
        if node_hp(self.cd, build.daevanion)+1e-6 < (self.survival or {}).get("minimum_node_hp", 0):
            raise ValueError("The optimized allocation does not meet the requested HP reserve")
        build = self.polish_sp(build, policy)
        build = self.spend_remaining_sp(build, policy)
        build = self.optimize_specs(build, policy, passes=3)
        policy, dps, res = self.optimize_rotation(build, policy, restarts=4)
        from .reserves import meets
        if not meets(build,self.skill_reserves):
            raise ValueError("The optimized build does not meet the requested trained skill reserves")
        weights = self._stat_weights(build, policy, final=True)
        self.log(f"final: {dps:.0f} DPS  {describe(policy)}")
        return OptResult(build, policy, dps, res, weights, self.history, curves)
