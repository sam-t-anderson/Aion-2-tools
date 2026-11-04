"""End-to-end build optimizer (class agnostic; the kit supplies the mechanics).

Alternating optimization:

    specs  ->  rotation  ->  stigmas  ->  per-skill level curves + stat weights
           ->  Daevanion nodes + skill points (integer program)  ->  repeat

Each step keeps everything else fixed and only accepts improvements, so the
DPS is monotone across steps up to the noise-free simulator's resolution.
"""
from __future__ import annotations

import itertools
import re
import time
from dataclasses import dataclass, field, replace

from ..kit.base import Build, ClassData, sp_to_reach, spec_slots, stigma_points_to_reach, trainable_level
from ..run import Scenario, kit_module, prepare
from ..sim.engine import Sim
from . import daevanion as daev_opt
from .bonus import allocate_pool, valid_pool
from .rotation import describe, materialize, optimize_rotation
from .solver import name as solver_name, require as solver_require
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


def stigma_patterns(slots: int, points: int, min_levels=()) -> list[tuple]:
    """The level patterns the stigma search tries: ``slots`` levels that spend ``points``, each maximal (no free
    point left to raise a level), highest level first. With fewer than four slots to fill (a character below
    level 37, or few points) every level is tried, since the usual subset can leave no pattern that spends the
    few points there are; otherwise the levels that unlock specs (5, 10, 15, 20), the ones that spend an odd
    point between them, and every level from 16 up. The levels used to stop at 15 (0.2.367 and before): a
    level-45 character's observed stigmas (168 points) had no maximal pattern, the search was skipped, and
    the seed allocation (10/5/5/5, 30 points) was what the optimizer proposed."""
    levels = (range(1, 21) if slots < 4 else
              sorted({1, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, *min_levels}))
    patterns = [lv for lv in itertools.product(levels, repeat=slots)
                if sum(stigma_points_to_reach(l) for l in lv) <= points]

    def maximal(p):
        spent = sum(stigma_points_to_reach(l) for l in p)
        return all(l >= 20 or spent - stigma_points_to_reach(l) + stigma_points_to_reach(l + 1) > points
                   for l in p)
    return sorted({tuple(sorted(p, reverse=True)) for p in patterns if maximal(p)})


def _stigma_worker(job):
    opt, build, policy = _CTX["stigma"]
    combo, levels = job
    b2 = build.copy()
    b2.stigmas = dict(zip(combo, levels))
    return job, opt.evaluate(b2, policy)


def _bonus_worker(moves):
    """One bonus-level move: a level taken from one skill and given to another, or placed from the
    pool's slack. The raised skill's supporting effects are chosen again when the move crosses an
    effect's unlock level or opens a slot."""
    opt, build, policy = _CTX["bonus"]
    cd = opt.cd
    b2 = build.copy()
    for sid, d in moves:
        b2.bonus[sid] = b2.bonus.get(sid, 0) + d
        if b2.bonus[sid] <= 0:
            b2.bonus.pop(sid)
    b2 = opt._clean_specs(b2)
    before = opt._with_gear(build).effective_levels(cd)
    after = opt._with_gear(b2).effective_levels(cd)
    crossed = [sid for sid, d in moves if d > 0 and (
        spec_slots(after.get(sid, 1)) > spec_slots(before.get(sid, 1))
        or any(before.get(sid, 1) < x["unlock"] <= after.get(sid, 1) for x in cd.skills[sid].get("specs", [])))]
    if crossed:
        b2, v = opt._respec(b2, policy, crossed)
    else:
        v = opt.evaluate(b2, policy)
    return moves, v, b2


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
                 progress=None, survival=None, skill_reserves=None, level: int = 45,
                 bonus_pool: dict | None = None):
        """``bonus_pool`` = ``{"levels", "per_skill"}``: bonus skill levels from gear rolls and arcana cards
        the search may place itself (a community comparison's allowance); the result's ``Build.bonus``
        then holds where they go. Without it, ``Build.bonus`` is the fixed ``gear_bonus`` only."""
        from .survival import with_action_timing
        scenario = with_action_timing(scenario, survival)
        self.survival = survival
        self.cls = cls
        self.cd = ClassData(cls)
        self.scenario = scenario
        self.daev_budget = daev_budget
        # The character's level gates what it can have: stigma slots, how far each skill trains with
        # points (its ``need`` levels) and which Daevanion boards are open. A level-45 character
        # has all of it.
        self.level = level
        bud = self.cd.budget(level)
        self.sp_budget = sp_budget if sp_budget is not None else bud["skill"]
        self.stigma_points = stigma_points if stigma_points is not None else bud["stigma"] + 1
        self.slots = bud["slots"]
        self.sp_caps = {sid: trainable_level(s, level) for sid, s in self.cd.skills.items() if s["kind"] != "stigma"}
        self.boards = tuple(b["name"] for b in self.cd.boards
                            if b["name"] in daev_opt.CRYSTAL_BOARDS and (b.get("needLevel") or 1) <= level)
        self.search_cfg = replace(scenario.config, duration=search_duration or scenario.config.duration)
        self.verbose = verbose
        self.progress = progress            # optional callback(str): live phase updates for the app UI
        self.gear_bonus = gear_bonus or {}
        if bonus_pool is not None and not valid_pool(bonus_pool):
            raise ValueError("The bonus-level allowance needs whole-number levels and per_skill from 1 up")
        self.bonus_pool = dict(bonus_pool) if bonus_pool else None
        self._curve_sids: set = set()      # skills whose level curves showed a measurable gain
        from .reserves import include_survival
        skill_reserves = include_survival(self.cd, skill_reserves, survival,
                                         {"skill": self.sp_budget, "stigma": self.stigma_points})
        self.skill_reserves = skill_reserves
        self.required_specs = (skill_reserves or {}).get("specs", {})
        self.min_effective = (skill_reserves or {}).get("effective", {})
        self.min_sp = (skill_reserves or {}).get("sp", {})
        self.min_stigmas = (skill_reserves or {}).get("stigmas", {})
        self.history: list = []
        self._rotation_keys: set = set()    # kit actions the last rotation search could use
        self._links = None                  # the class's linked supporting effects (_spec_links)
        self._probes: dict = {}             # linked-effect probes by group and closed levels (_linked_probe_terms)
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
    @property
    def stigma_slots(self) -> int:
        """The slots the stigma points can fill: a stigma costs a point at level 1, so a character
        with fewer points than open slots leaves the rest empty (all of them at 0 points)."""
        return max(0, min(self.slots, self.stigma_points))

    def _top(self, sid: int) -> int:
        """The highest level skill points can train ``sid`` to at the character's level."""
        return min(10, self.cd.skills[sid].get("buyMax", 10), self.sp_caps.get(sid, 10))

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
        b = Build(self.cls, self.level)
        b.bonus = dict(self.gear_bonus)
        avg = {**tp.get("skills", {}), **tp.get("passives", {})}
        ranked = sorted(cd.skills.values(), key=lambda s: -(avg.get(s["name"], {}).get("avg_level") or 0))
        b.sp = {sid:level for sid,level in self.min_sp.items() if level>1}
        sp = self.sp_budget-b.sp_spent()
        for s in ranked:
            if s["kind"] == "stigma":
                continue
            top = self._top(s["id"])
            cost = sp_to_reach(top)-sp_to_reach(b.sp.get(s["id"],1))
            if top > 1 and sp >= cost:
                b.sp[s["id"]] = top
                sp -= cost
        stig = [n for n in tp.get("stigmas", {}) if n not in DEFENSIVE_STIGMAS]
        slots = self.stigma_slots
        stig_ids = list(self.min_stigmas)
        stig_ids += [cd.by_name[n]["id"] for n in stig if n in cd.by_name and cd.by_name[n]["id"] not in stig_ids][:slots-len(stig_ids)]
        if len(stig_ids) < slots:
            for s in cd.skills.values():
                if s["kind"] == "stigma" and s["name"] not in DEFENSIVE_STIGMAS and s["id"] not in stig_ids:
                    stig_ids.append(s["id"])
                if len(stig_ids) >= slots:
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
                    if not set(self.required_specs.get(sid, ())) <= set(combo):
                        continue
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

    def _spec_links(self) -> tuple[list, dict]:
        """The supporting effects that act on another skill's cooldown, read from their text (0.2.376): one that
        shortens or resets a named skill's cooldown ("-3s [Wish of Concentration] cooldown on hit", "Reset [Blaze]
        cooldown on landing [Pyroclasm]") or every skill's ("-10s all skill cooldowns"). Returns the groups of
        skills such effects tie together (a skill, the skills it names, and so on) and each skill's linking
        effects. Every class has some: a Sorcerer's Flame Arrow resets Blaze, Blaze shortens Wish of
        Concentration's cooldown, and Wish's own effect shortens every cooldown."""
        if self._links is None:
            skills = self.cd.skills
            byname = {s["name"]: sid for sid, s in skills.items()}
            links, edges = {}, []
            for sid, s in skills.items():
                if s["kind"] != "active":
                    continue
                for x in s.get("specs") or []:
                    text = x.get("text") or ""
                    if "cooldown" not in text.lower():
                        continue
                    named = [byname[r] for r in re.findall(r"\[([^\]]+)\]", text) if byname.get(r, sid) != sid]
                    if named or re.search(r"\ball (?:skill )?cooldowns?\b", text, re.I):
                        links.setdefault(sid, set()).add(x["id"])
                        edges += [(sid, other) for other in named]
            parent = {sid: sid for sid in links}

            def root(x):
                while parent.setdefault(x, x) != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for a, b in edges:
                parent[root(a)] = root(b)
            groups = {}
            for sid in parent:
                groups.setdefault(root(sid), []).append(sid)
            self._links = ([tuple(sorted(g)) for g in groups.values()], {k: frozenset(v) for k, v in links.items()})
        return self._links

    def _linked_choices(self, build: Build, sid: int, opts: dict, cap: int | None = None) -> list:
        """``sid``'s combinations of supporting effects that hold one of its linking effects, other than the
        build's own (empty when the build already holds them all or the skill has none)."""
        mine = self._spec_links()[1].get(sid, frozenset())
        current = set(build.specs.get(sid, ()))
        if not mine or mine <= current:
            return []
        need = set(self.required_specs.get(sid, ()))
        return [tuple(sorted(c)) for c in opts.get(sid, [()])
                if set(c) & mine and need <= set(c) and set(c) != current][:cap]

    def _linked_builds(self, build: Build, sid: int) -> list:
        """``build`` with ``sid``'s linking effects and a linked skill's, for the level curves: two effects that act
        on each other's cooldowns (Blaze shortening Wish of Concentration's, Wish shortening every skill's) pay
        off together, and judged one skill at a time neither does, so the curves never valued the level that opens
        them (0.2.376)."""
        groups, _ = self._spec_links()
        group = next((g for g in groups if sid in g), ())
        if len(group) < 2:
            return []
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
        opts = mod.spec_options(self.cd, self._with_gear(build))
        out = []
        for mine in self._linked_choices(build, sid, opts) or [tuple(sorted(build.specs.get(sid, ())))]:
            for other in group:
                if other == sid:
                    continue
                for theirs in self._linked_choices(build, other, opts):
                    b3 = build.copy()
                    b3.specs[sid], b3.specs[other] = mine, theirs
                    out.append(b3)
        return out

    def optimize_linked_specs(self, build: Build, policy: list, keep: int = 2, per_skill: int = 4,
                              margin: float = 0.9, groups: list | None = None, quiet: bool = False) -> tuple[Build, list]:
        """The linking supporting effects of each group (:meth:`_spec_links`) tried together, each candidate's
        rotation searched again (0.2.376). :meth:`optimize_specs` changes one skill at a time under a fixed priority
        list, which misses what these effects need: the effect on one skill pays off through another skill's
        cooldown, and the rotation that uses it differs from the one searched without it. A Sorcerer's Wish of
        Concentration (-10 s every cooldown) with Blaze's -3 s to Wish was 13 % above the effects the optimizer
        kept, and each alone fell short under the old rotation. Every combination that adds a linking effect is
        scored under the current rotation; the best ``keep`` within ``margin`` of the build's own score (Wish's
        effect alone fell 6 % under the old rotation and gained 2 % under its own) have their rotation searched
        again, and one is taken only when it beats the build as it is. Returns ``(build, policy)``."""
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
        build = self._clean_specs(build)
        best = self.evaluate(build, policy)
        for group in self._spec_links()[0] if groups is None else groups:
            opts = mod.spec_options(self.cd, self._with_gear(build))
            choices = []
            for sid in group:
                alts = self._linked_choices(build, sid, opts)
                if len(alts) > per_skill:                   # the skill's best few, judged on their own
                    def alone(c, sid=sid):
                        b2 = build.copy()
                        b2.specs[sid] = c
                        return self.evaluate(b2, policy)
                    alts = sorted(alts, key=alone, reverse=True)[:per_skill]
                choices.append([tuple(sorted(build.specs.get(sid, ())))] + alts)
            same = tuple(c[0] for c in choices)
            scored = []
            for combo in itertools.product(*choices):
                if combo == same:
                    continue
                b2 = build.copy()
                for sid, c in zip(group, combo):
                    b2.specs[sid] = c
                scored.append((self.evaluate(b2, policy), len(scored), b2))
            for v, _, b2 in sorted(scored, key=lambda x: (-x[0], x[1]))[:keep]:
                if v < best * margin:
                    break
                pol2, v2, _ = self.optimize_rotation(b2, policy, restarts=0)
                if v2 > best * (1 + 1e-4):
                    names = ", ".join(self.cd.skills[sid]["name"] for sid in group
                                      if set(b2.specs.get(sid, ())) != set(build.specs.get(sid, ())))
                    if not quiet:
                        self.log(f"linked effects: {names} -> {v2:.0f} (was {best:.0f})")
                    build, policy, best = b2, pol2, v2
                    break
        return build, policy

    def _respec(self, build: Build, policy: list, sids) -> tuple[Build, float]:
        """The best supporting effects for ``sids`` alone (their levels just changed), everything else
        as it is: cheaper than :meth:`optimize_specs` over every skill."""
        mod = kit_module(self.cls, pvp=self.scenario.target.is_player)
        best = self.evaluate(build, policy)
        for sid in sids:
            s = self.cd.skills[sid]
            if s["kind"] != "active" or not s.get("specs"):
                continue
            for combo in mod.spec_options(self.cd, self._with_gear(build)).get(sid, [()]):
                if not set(self.required_specs.get(sid, ())) <= set(combo):
                    continue
                if tuple(sorted(combo)) == tuple(sorted(build.specs.get(sid, ()))):
                    continue
                b3 = build.copy()
                b3.specs[sid] = tuple(combo)
                v = self.evaluate(b3, policy)
                if v > best * (1 + 1e-9):
                    best, build = v, b3
        return build, best

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
        slots = self.stigma_slots
        if not slots:
            self.log("stigma search skipped: no stigma slot is open at this level, or no stigma point to fill one")
            return build
        patterns = stigma_patterns(slots, self.stigma_points, self.min_stigmas.values())
        if not cands or not patterns or slots > len(cands):
            self.log("stigma search skipped: no legal candidate sets for this budget")
            return build
        best_b, best = build, self.evaluate(build, policy)
        # stage 1: which set (uniform-ish pattern), stage 2: level assignment for top sets
        base_pat = max(patterns, key=lambda p: (p.count(10), -p.count(1)))
        _CTX["stigma"] = (self, build, policy)
        combos = [combo for combo in itertools.combinations(cands,slots) if set(self.min_stigmas).issubset(combo)]
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

    def _linked_probe_terms(self, build: Build, policy: list) -> list[tuple[dict, float]]:
        """For each group whose linking effects (:meth:`_spec_links`) its skills' levels keep closed: the levels that
        open them and the gain the group's linking effects bring there with their own rotation, the closed skills
        raised to those levels for free (0.2.376). The allocation counts each gain only when every one of those
        skills reaches its level (``daev_opt.solve(joint=...)``): the level curves judge one skill at a time under a
        fixed rotation, which never shows effects that pay off only together. At a median Sorcerer's budget, Wish of
        Concentration and Blaze raised to 16 gained 4 % with their best effects alone and 9 % with Blaze's -3 s to
        Wish and Wish's -10 s to every cooldown. Each probe is searched once per group and closed levels."""
        groups, links = self._spec_links()
        L = self._with_gear(build).effective_levels(self.cd)
        out = []
        for group in groups:
            closed = {}
            for sid in group:
                opens = [x["unlock"] for x in self.cd.skills[sid].get("specs") or [] if x["id"] in links.get(sid, ())]
                if opens and L.get(sid, 1) < min(opens) <= 20:
                    closed[sid] = min(opens)
            if not closed:
                continue
            key = (group, tuple(sorted((sid, L.get(sid, 1), lvl) for sid, lvl in closed.items())))
            if key not in self._probes:
                probe = build.copy()
                for sid, lvl in closed.items():
                    probe.bonus[sid] = probe.bonus.get(sid, 0) + lvl - L.get(sid, 1)
                probe, base = self._respec(self._clean_specs(probe), policy, list(closed))
                linked, linked_policy = self.optimize_linked_specs(probe, policy, keep=1, groups=[group], quiet=True)
                # what the searched rotation gains without the linking effects is not theirs to claim
                base = max(base, self.evaluate(probe, linked_policy))
                gain = self.evaluate(linked, linked_policy) - base
                self._probes[key] = max(0.0, gain)
                if gain > 0:
                    self.log(f"linked effects at their levels: {', '.join(self.cd.skills[s]['name'] for s in closed)} "
                             f"-> +{gain:.0f} DPS with their own rotation, if each reaches its level")
            if self._probes[key] > 0:
                out.append((dict(closed), self._probes[key]))
        return out

    def level_curves(self, build: Build, policy: list, max_level: int = 20, keep=()) -> dict[int, list[float]]:
        """DPS as a function of each skill's effective level (best specs at each level). ``keep``: skills whose curve
        is kept even when flat (the members of a joint gain, :meth:`_linked_probe_terms`)."""
        sids = [sid for sid, s in self.cd.skills.items()
                if s["kind"] != "stigma" and (s.get("unlock") or 1) <= self.level]
        _CTX["curve"] = (self, build, policy, max_level)
        self.log(f"skill curves: evaluating {len(sids)} skills through level {max_level}")
        curves = {}
        for sid, curve in _pmap(
                _curve_worker, sids, ctx={"curve": _CTX["curve"]},
                progress=lambda done, total: self.log(f"skill curves: {done}/{total} skills"),
                fallback=self.log):
            # flat curves (no DPS effect) are dropped to keep the program small
            if max(curve[1:]) - min(curve[1:]) > 1e-6 or sid in self.min_sp or sid in self.min_effective or sid in keep:
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
                    if not set(self.required_specs.get(sid, ())) <= set(combo):
                        continue
                    b3 = b2.copy()
                    b3.specs[sid] = tuple(combo)
                    best = max(best, self.evaluate(b3, policy))
                for b3 in self._linked_builds(self._clean_specs(b2), sid):   # with a linked skill's effect too
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
                    if not set(self.required_specs.get(sid, ())) <= set(combo):
                        continue
                    b3 = b2.copy()
                    b3.specs[sid] = tuple(combo)
                    best = max(best, self.evaluate(b3, policy))
                for b3 in self._linked_builds(self._clean_specs(b2), sid):   # with a linked skill's effect too
                    best = max(best, self.evaluate(b3, policy))
            out.append(best)
        return out

    def _stat_weights(self, build: Build, policy: list, *, final=False):
        _, _, kit, stats = prepare(build, self.scenario)
        return stat_weights(stats, kit, policy, self.scenario.target,
                            self.scenario.config if final else self.search_cfg,
                            progress=None if final else self.log)

    def allocate(self, build: Build, policy: list):
        joint = self._linked_probe_terms(build, policy)
        curves = self.level_curves(build, policy, keep={sid for levels, _ in joint for sid in levels})
        self.log("skill allocation: calculating stat weights")
        weights = self._stat_weights(build, policy)
        nv = node_values(self.cd, weights)
        self._curve_sids = set(curves)
        # bonus from gear stays outside the program; Daevanion/SP replace the build's. With a bonus pool
        # the build's own bonus is the pool's last placement, re-placed below: only the fixed gear bonus stays.
        gear = self._gear_bonus()
        fixed = dict(gear)
        for k, v in (self.gear_bonus if self.bonus_pool else build.bonus).items():
            fixed[k] = fixed.get(k, 0) + v

        def solve(bonus, start):
            # This is a mixed integer program and can be the longest single step.
            # Keep the UI's phase indicator current while the in-process HiGHS
            # solver works.
            self.log(f"skill allocation: solving Daevanion/SP with {solver_name()} (up to {DAEV_SOLVER_TIME_LIMIT} s)")
            solver_started = time.monotonic()
            # Start from the current allocation, so a solve cut short by its time limit (likely on a
            # busy machine) never returns a board worth less to the program than the one it has.
            sol = daev_opt.solve(self.cd, curves, nv, daev_budget=self.daev_budget,
                                 sp_budget=self.sp_budget, bonus=bonus,
                                 time_limit=DAEV_SOLVER_TIME_LIMIT,
                                 min_node_hp=(self.survival or {}).get("minimum_node_hp", 0), min_sp=self.min_sp, min_effective=self.min_effective,
                                 start=start, spend_all=True, boards=self.boards, max_sp=self.sp_caps, joint=joint)
            self.log(f"skill allocation: solver finished ({sol['status']}, "
                     f"{time.monotonic() - solver_started:.1f} s"
                     f"{'; started from the current allocation' if sol['warm_start'] else ''})")
            if sol["filled"]:
                self.log(f"skill allocation: filled {sol['filled']} Daevanion point{'s' if sol['filled'] != 1 else ''} "
                         "the solver left unspent")
            return sol

        sol = solve(fixed, (build.daevanion, build.sp))
        pool: dict = {}
        if self.bonus_pool:
            # The bonus levels gear rolls and arcana cards can add (the comparison's allowance) go on the
            # same curves, by the run of levels that gains most; then the points are solved again around them.
            dv = self.cd.daevanion_levels(sol["nodes"])
            eff = {sid: sol["sp"].get(sid, 1) + dv.get(sid, 0) + fixed.get(sid, 0) for sid in curves}
            pool = allocate_pool(curves, eff, self.bonus_pool,
                                 max_level={sid: self.cd.skills[sid].get("max") or 40 for sid in curves})
            placed = ", ".join(f"{self.cd.skills[sid]['name']} +{n}"
                               for sid, n in sorted(pool.items(), key=lambda kv: (-kv[1], kv[0])))
            self.log(f"bonus levels: {sum(pool.values())} of {self.bonus_pool['levels']} from gear rolls and arcana "
                     f"cards placed ({placed or 'none worth a level'}); solving the points around them")
            with_pool = {k: fixed.get(k, 0) + pool.get(k, 0) for k in set(fixed) | set(pool)}
            sol = solve(with_pool, (sol["nodes"], sol["sp"]))
        self.log("skill allocation: applying the optimized points")
        b2 = build.copy()
        b2.daevanion = sol["nodes"]
        b2.sp = {sid: lv for sid, lv in sol["sp"].items() if lv > 1}
        if self.bonus_pool:
            b2.bonus = {k: v for k, v in ((k, self.gear_bonus.get(k, 0) + pool.get(k, 0))
                                          for k in set(self.gear_bonus) | set(pool)) if v > 0}
        # skills without a value curve keep level 1 (no points)
        return b2, sol, curves, weights

    def polish_bonus(self, build: Build, policy: list, rounds: int = 4) -> Build:
        """Full-simulation local search on the pool's bonus levels after the integer program: move one
        level from one skill to another, or place one the program left unspent, keeping the single move
        that gains most, round after round, until none does. Moves go between the skills whose level
        curves showed a gain."""
        pool = self.bonus_pool
        if not pool:
            return build
        cd = self.cd
        skills = sorted(sid for sid, s in cd.skills.items()
                        if s["kind"] in ("active", "passive") and (s.get("unlock") or 1) <= self.level
                        and (not self._curve_sids or sid in self._curve_sids))
        best = self.evaluate(build, policy)
        for round_no in range(1, rounds + 1):
            placed = {sid: n - self.gear_bonus.get(sid, 0) for sid, n in build.bonus.items()
                      if n - self.gear_bonus.get(sid, 0) > 0}
            slack = pool["levels"] - sum(placed.values())
            eff = self._with_gear(build).effective_levels(cd)
            jobs = []
            for b in skills:
                if (placed.get(b, 0) >= pool["per_skill"] or eff.get(b, 1) < 1
                        or eff.get(b, 1) >= (cd.skills[b].get("max") or 40)):
                    continue
                if slack > 0:
                    jobs.append(((b, 1),))
                jobs += [((a, -1), (b, 1)) for a in sorted(placed) if a != b]
            if not jobs:
                break
            _CTX["bonus"] = (self, build, policy)
            self.log(f"polish bonus levels: round {round_no}/{rounds}, evaluating {len(jobs)} moves")
            moves, v, b2 = max(_pmap(
                _bonus_worker, jobs, ctx={"bonus": _CTX["bonus"]},
                progress=lambda done, total: self.log(f"polish bonus levels: {done}/{total} moves"),
                fallback=self.log), key=lambda r: r[1], default=(None, 0, None))
            if not moves or v <= best * (1 + 1e-4):     # ignore noise-level moves
                break
            self.log("polish bonus levels: " + ", ".join(f"{cd.skills[s]['name']} {d:+d}" for s, d in moves)
                     + f" -> {v:.0f} (was {best:.0f})")
            build, best = b2, v
        return build

    def polish_sp(self, build: Build, policy: list, rounds: int = 6) -> Build:
        """Full-simulation local search on skill points after the integer program.

        Moves: raise one skill by 1-2 levels from free points, or move 1-2
        levels from one skill to another.  Catches interactions the separable
        level curves miss (spec thresholds, buffs that scale other skills).
        """
        cd = self.cd
        trainable = sorted(sid for sid, s in cd.skills.items()
                           if s["kind"] in ("active", "passive") and self._top(sid) > 1)
        best = self.evaluate(build, policy)
        for round_no in range(1, rounds + 1):
            slack = self.sp_budget - build.sp_spent()
            effective = self._with_gear(build).effective_levels(cd)
            jobs = []
            for b in trainable:
                lb, top = build.sp.get(b, 1), self._top(b)
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
                            if (a == b or la - da < self.min_sp.get(a,1)
                                    or effective.get(a,1)-da < self.min_effective.get(a,1)):
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
            for new_level in range(level + 1, self._top(sid) + 1):
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
        for sid, chosen in self.required_specs.items():
            skill = cd.skills[sid]
            available = {effect["id"] for effect in skill.get("specs", []) if effect["unlock"] <= L.get(sid, 1)}
            slots = spec_slots(L.get(sid, 1))
            if not set(chosen) <= available or len(chosen) > slots:
                raise ValueError(f"{skill['name']}: reserved supporting effects are unavailable at the proposed level")
            extras = [effect for effect in b.specs.get(sid, ()) if effect not in chosen]
            b.specs[sid] = tuple(chosen) + tuple(extras[:slots-len(chosen)])
        return b

    # ----------------------------------------------------------------- main
    def run(self, iterations: int = 3, *, initial_build: Build | None = None,
            initial_policy: list | None = None) -> OptResult:
        # The Daevanion/SP allocation needs the in-process solver. Check it up front so a missing
        # dependency fails immediately with guidance, rather than after the long rotation and
        # stat-weight search (which don't use the solver) and looks like a hang at that phase.
        solver_require()
        build = initial_build.copy() if initial_build is not None else self.initial_build()
        # A given starting build (an imported character's own) is a result the search must not fall below (0.2.376):
        # a Sorcerer's search, started from a typical top player's build, lowered Wish of Concentration below the level
        # that opens its cooldown effect and ended 13 % under the character as it was.
        seed = (self._clean_specs(build), list(initial_policy)) if initial_build is not None and initial_policy else None
        if self.min_effective:
            # Establish a legal seed before specialty search. Joint feasibility
            # includes board connectivity, SP/Daevanion budgets and any HP floor.
            self.log("skill reserves: finding a feasible trained/Daevanion allocation")
            curves = {sid: [0.0]*21 for sid,s in self.cd.skills.items()
                      if s["kind"] in ("active", "passive")}
            sol = daev_opt.solve(self.cd, curves, {}, daev_budget=self.daev_budget,
                                 sp_budget=self.sp_budget, bonus=self._with_gear(build).bonus,
                                 time_limit=DAEV_SOLVER_TIME_LIMIT, min_sp=self.min_sp,
                                 min_effective=self.min_effective,
                                 min_node_hp=(self.survival or {}).get("minimum_node_hp", 0),
                                 boards=self.boards, max_sp=self.sp_caps)
            build.sp, build.daevanion = sol["sp"], sol["nodes"]
            build = self._clean_specs(build)
        policy = (list(initial_policy) if initial_policy is not None else
                  list(kit_module(self.cls, pvp=self.scenario.target.is_player).build_kit(self._with_gear(build), self.cd).policy))
        curves, weights = {}, []
        for it in range(iterations):
            build = self._clean_specs(build)
            build = self.optimize_specs(build, policy)
            self.log(f"iter {it}: specs -> {self.evaluate(build, policy):.0f}")
            policy, dps, _ = self.optimize_rotation(build, policy)
            self.log(f"iter {it}: rotation -> {dps:.0f}  {describe(policy)}")
            # Effects that act on each other's cooldowns, tried together with their own rotation, before the stigmas
            # and the skill levels are chosen for the build (0.2.376).
            build, policy = self.optimize_linked_specs(build, policy)
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
        build = self.polish_bonus(build, policy)
        build = self.optimize_specs(build, policy, passes=3)
        build, policy = self.optimize_linked_specs(build, policy)
        policy, dps, res = self.optimize_rotation(build, policy, restarts=4)
        from .reserves import meets
        if seed is not None and meets(self._with_gear(seed[0]), self.skill_reserves, self.cd) \
                and node_hp(self.cd, seed[0].daevanion) + 1e-6 >= (self.survival or {}).get("minimum_node_hp", 0):
            seed_policy, seed_dps, seed_res = self.optimize_rotation(seed[0], seed[1], restarts=0)
            if seed_dps > dps * (1 + 1e-6):
                self.log(f"final: the starting build ({seed_dps:.0f}) beats the search's ({dps:.0f}); it is kept")
                build, policy, dps, res = seed[0], seed_policy, seed_dps, seed_res
        if not meets(self._with_gear(build),self.skill_reserves,self.cd):
            raise ValueError("The optimized build does not meet the requested skill and supporting-effect reserves")
        weights = self._stat_weights(build, policy, final=True)
        self.log(f"final: {dps:.0f} DPS  {describe(policy)}")
        return OptResult(build, policy, dps, res, weights, self.history, curves)
