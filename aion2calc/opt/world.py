"""World PvP: large fights against several players at once.

The damage side is the PvP kit in the World PvP scenario (``scenarios.pvp_world``): area skills land on
every enemy they reach, and for part of the fight no enemy is within reach, when only skills that reach
far enough can be used (melee classes lean on their gap closers and ranged skills then). The objective
weighs that damage by the share of the fight you live through::

    score = world DPS x (1 - exp(-x))
    x     = ln 2 x (EHP / typical EHP) x (ranged attackers / your attackers) / (1 - controlled)

Effective HP is your HP over the damage you take from a reference attacker (your class's typical build,
the same hit for every build) through the damage formula your own hits use, so Defense, Critical Hit
Resist, Critical Damage Tolerance and Damage Tolerance count. It is measured against your class's typical
build: that build, played by a ranged class with no crowd control, lives through half the fight. Melee
classes draw more attackers, so they survive less of it and every point of survival is worth more to them;
hard crowd control takes the attackers' time away (up to a cap). Defensive stats and crowd control
therefore score through survival, and the board solver values HP and Defense nodes.

Every number in :data:`WORLD` is an assumption, returned with each result. Block, Evasion, Status Effect
Resist, healing, shields, movement and player reactions are not modelled.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import replace

from ..model.damage import HitContext, expected_hit
from ..run import Scenario, prepare
from ..sim.engine import Sim, Target
from .pipeline import Optimizer
from .rotation import materialize, optimize_rotation
from .statweights import stat_weights

#: Classes that fight in melee range (the rest fight from 20 m or more).
MELEE = frozenset({"gladiator", "templar", "assassin", "chanter"})

#: The World PvP assumptions (explicit, returned with every result).
WORLD = {
    "enemies_in_reach": 3,          # enemies an area skill reaches in a large fight
    "out_of_reach_s": 3.0,          # the last ... of every
    "cycle_s": 10.0,                # seconds, no enemy is within reach_m of you
    "reach_m": 10.0,
    "attackers": {"melee": 3.0, "ranged": 1.5},   # players hitting you at once
    "typical_alive": 0.5,           # share of the fight a typical ranged build without crowd control survives
    "control_cap": 0.5,             # the most of the attackers' time your crowd control takes away
    "reference_hit": (1000.0, 2.0),  # the reference attacker's hit: flat damage and Attack coefficient
}

#: Defensive stats the board solver can buy, with a realistic single step for finite differences.
DEFENSIVE_STEPS = (("hp", 500.0), ("defense", 150.0), ("crit_resist", 50.0), ("dmg_tol", 0.03),
                   ("pvp_tol", 0.03), ("crit_dmg_tol", 0.03), ("pvp_defense", 150.0),
                   ("pvp_crit_resist", 50.0))

SOURCE = "survival-medians"

NOTE = ("World PvP proxy: area skills hit up to {enemies} enemies, and the last {out}s of every {cycle}s no "
        "enemy is within {reach:g} m, so only skills that reach that far can be used. The score is the damage "
        "weighted by the share of the fight you survive, measured against your class's typical build: played "
        "by a ranged class without crowd control it survives {alive:.0%} of the fight. A melee class draws "
        "{melee:g} attackers instead of {ranged:g}, effective HP comes from HP, Defense, Critical Hit Resist "
        "and Damage Tolerance against your class's typical hit, and hard crowd control (Stun, Knockdown, "
        "Airborne, Fear, Sleep, Frost) takes away up to {cap:.0%} of the attackers' time. Without recorded "
        "gear the loadout gets the median level-45 gear HP and Defense of official profiles. Block, Evasion, "
        "Status Effect Resist, healing, shields, movement and player reactions are not modelled. These are "
        "assumptions, not measurements.")


def is_world(scenario: Scenario) -> bool:
    return scenario.target.is_player and scenario.target.aoe_targets > 1


def windows(duration: float, world: dict = WORLD) -> tuple:
    """The out-of-reach windows: the last ``out_of_reach_s`` of every ``cycle_s``."""
    out, cycle = world["out_of_reach_s"], world["cycle_s"]
    if out <= 0:
        return ()
    rows, start = [], cycle - out
    while start < duration:
        rows.append((start, min(duration, start + out)))
        start += cycle
    return tuple(rows)


def note(world: dict = WORLD) -> str:
    return NOTE.format(enemies=world["enemies_in_reach"], out=f"{world['out_of_reach_s']:g}",
                       cycle=f"{world['cycle_s']:g}", reach=world["reach_m"], alive=world["typical_alive"],
                       melee=world["attackers"]["melee"], ranged=world["attackers"]["ranged"],
                       cap=world["control_cap"])


def survival_medians() -> dict:
    from ..paths import data_file
    return json.loads(data_file("global", "survival_medians.json").read_text(encoding="utf-8"))


def with_gear_survival(loadout, cls: str | None = None) -> dict:
    """A loadout with gear survival stats: its own when it records them (an imported character), else the
    median level-45 gear of official profiles (by class when the class has enough profiles)."""
    from ..model.character import load_loadout
    lo = copy.deepcopy(load_loadout(loadout) if isinstance(loadout, str) else loadout)
    comps = lo.setdefault("components", [])
    if any(c.get("source") == SOURCE or {"hp", "defense"} & set(c.get("stats") or {}) for c in comps):
        return lo
    cls = cls or next((c for c in MELEE | {"sorcerer", "ranger", "cleric", "spiritmaster"}
                       if str(lo.get("name", "")).startswith(c)), None)
    med = survival_medians()
    row = med["classes"].get(cls) or {}
    basis = med["pooled"] if row.get("pooled") or "hp" not in row else row
    stats = {k: basis[k] for k in ("hp", "defense", "crit_resist", "life", "constitution", "dexterity")}
    comps.append({"slot": "Gear survival stats", "source": SOURCE,
                  "item": f"median of {basis['n']} official level-45 profiles", "stats": stats})
    return lo


def _ehp(cls: str, stats, attacker, world: dict) -> tuple[float, float]:
    """(effective HP, share of a reference hit you take) against the reference attacker."""
    from ..kit.base import ClassData
    d = stats.defenses(ClassData(cls).base_stats(stats.level))
    flat, coef = world["reference_hit"]
    ctx = HitContext(flat=flat, coef=coef, element=None, tags=(), mult=1.0)
    naked = Target(tolerance=0.0, is_boss=False, is_player=True)
    you = Target(tolerance=d.tolerance, defense=d.defense, crit_resist=d.crit_resist,
                 crit_dmg_tol=d.crit_dmg_tol, is_boss=False, is_player=True)
    base = expected_hit(attacker, {}, naked, ctx)
    taken = expected_hit(attacker, {}, you, ctx) / base if base > 0 else 1.0
    return (d.hp / taken if taken > 0 else math.inf), taken


_REFERENCE: dict = {}


def reference(cls: str, scenario: Scenario, world: dict = WORLD) -> tuple:
    """(attacker, typical EHP): your class's typical build as the reference attacker, and its effective HP."""
    from ..scenarios import typical_build
    lo = scenario.loadout
    key = (cls, lo if isinstance(lo, str) else json.dumps(lo, sort_keys=True, default=str), world["reference_hit"])
    if key not in _REFERENCE:
        _, _, _, stats = prepare(typical_build(cls), scenario)
        attacker = stats.derived()
        _REFERENCE[key] = (attacker, _ehp(cls, stats, attacker, world)[0])
    return _REFERENCE[key]


def survival(cls: str, stats, control_s: float, duration: float, ref: tuple, world: dict = WORLD) -> dict:
    """Effective HP and the share of the fight survived, relative to the class's typical build."""
    attacker, typical = ref
    ehp, taken = _ehp(cls, stats, attacker, world)
    attackers = world["attackers"]["melee" if cls in MELEE else "ranged"]
    controlled = min(world["control_cap"], (control_s / duration) / attackers if duration > 0 else 0.0)
    x = (-math.log(1 - world["typical_alive"]) * (ehp / typical if typical > 0 else 1.0)
         * (world["attackers"]["ranged"] / attackers) / (1 - controlled))
    d = stats.defenses({})                     # gear and boards only, for display
    return {"effective_hp": ehp, "typical_effective_hp": typical, "relative_ehp": ehp / typical if typical > 0 else None,
            "damage_taken": taken, "attackers": attackers, "control_s_per_min": 60 * control_s / duration if duration else 0.0,
            "controlled": controlled, "alive_share": 1 - math.exp(-x),
            "survival_stats": {"tolerance": d.tolerance, "crit_dmg_tol": d.crit_dmg_tol}}


def assess(cls: str, build, scenario: Scenario, policy, world: dict = WORLD) -> dict:
    """The World PvP score of a build and priority, with everything it is made of."""
    _, _, kit, stats = prepare(build, scenario)
    pol = [e for e in policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    res = Sim(stats.derived(), kit.actions, materialize(pol), scenario.target, scenario.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods).run()
    surv = survival(cls, stats, res.control, res.duration, reference(cls, scenario, world), world)
    return {"score": res.dps * surv["alive_share"], "dps": res.dps, **surv,
            "assumptions": copy.deepcopy(world), "note": note(world)}


class WorldOptimizer(Optimizer):
    """The pipeline's searches, scored by the World PvP objective instead of DPS."""

    def __init__(self, cls, scenario, **kwargs):
        super().__init__(cls, scenario, **kwargs)
        self.world = WORLD
        self.ref = reference(cls, self.scenario, self.world)

    def _score(self, stats, res) -> float:
        return res.dps * survival(self.cls, stats, res.control, res.duration, self.ref, self.world)["alive_share"]

    def _evaluator(self, build, cfg=None):
        _, _, kit, stats = prepare(build, self.scenario)
        derived, cache = stats.derived(), {}
        config = cfg or self.search_cfg

        def score(policy):
            key = tuple(policy)
            if key not in cache:
                res = Sim(derived, kit.actions, materialize(policy), self.scenario.target, config,
                          hooks=kit.hooks, cond_mods=kit.cond_mods).run()
                cache[key] = (self._score(stats, res), res)
            return cache[key]
        return score

    def evaluate(self, build, policy, cfg=None, filler=None):
        _, _, kit, _ = prepare(build, self.scenario)
        return self._evaluator(build, cfg)(self._fit_policy(policy, kit))[0]

    def optimize_rotation(self, build, policy=None, restarts=2):
        _, _, kit, stats = prepare(build, self.scenario)
        start = None
        if policy:
            start = [e for e in self._fit_policy(policy, kit)
                     if isinstance(e, tuple) or not kit.actions[e].is_filler]
        result = optimize_rotation(stats.derived(), kit, self.scenario.target, self.scenario.config,
                                   start=start, restarts=restarts, evaluator=self._evaluator(build))
        self._rotation_keys = set(kit.actions)
        return result.policy, result.dps, result.result

    def _stat_weights(self, build, policy, *, final=False):
        """Damage stats at their DPS gain times the share of the fight survived; defensive stats at the
        survival they add times the DPS (both in score per unit, the board solver's currency)."""
        _, _, kit, stats = prepare(build, self.scenario)
        config = self.scenario.config if final else self.search_cfg
        pol = self._fit_policy(policy, kit)
        res = Sim(stats.derived(), kit.actions, materialize(pol), self.scenario.target, config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods).run()
        alive = survival(self.cls, stats, res.control, res.duration, self.ref, self.world)["alive_share"]
        rows = stat_weights(stats, kit, pol, self.scenario.target, config, progress=None if final else self.log)
        for row in rows:
            row["dps_gain"] *= alive
            row["per_unit"] *= alive
        for field, step in DEFENSIVE_STEPS:
            s2 = stats.copy()
            s2.add({field: step})
            more = survival(self.cls, s2, res.control, res.duration, self.ref, self.world)["alive_share"]
            gain = res.dps * (more - alive)
            rows.append({"stat": field, "label": _LABELS[field].format(step=step), "step": step,
                         "dps_gain": gain, "per_unit": gain / step})
        base = res.dps * alive
        attack = next((r["per_unit"] for r in rows if r["stat"] == "attack"), 0.0)
        for row in rows:
            row["pct"] = 100 * row["dps_gain"] / base if base > 0 else 0.0
            row["attack_equiv"] = row["dps_gain"] / attack if attack > 0 else None
        return sorted(rows, key=lambda r: -r["dps_gain"])


_LABELS = {"hp": "HP +{step:g}", "defense": "Defense +{step:g}", "crit_resist": "Critical Hit Resist +{step:g}",
           "dmg_tol": "Damage Tolerance +3%", "pvp_tol": "PvP Damage Tolerance +3%",
           "crit_dmg_tol": "Critical Damage Tolerance +3%", "pvp_defense": "PvP Defense +{step:g}",
           "pvp_crit_resist": "PvP Critical Hit Resist +{step:g}"}


def with_world(scenario: Scenario, world: dict = WORLD) -> Scenario:
    """A PvP scenario turned into the World PvP one: several enemies, out-of-reach windows, and gear
    survival stats on the loadout."""
    target = replace(scenario.target, aoe_targets=world["enemies_in_reach"], reach_m=world["reach_m"],
                     out_of_reach=windows(scenario.config.duration, world))
    return replace(scenario, target=target, loadout=with_gear_survival(scenario.loadout))
