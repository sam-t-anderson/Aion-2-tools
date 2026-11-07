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

Every class's defensives count since 0.2.386 (``kit.defensives``): its passives' HP, Max HP, Defense, Critical Hit
Resist and PvP Damage Tolerance, its timed buffs for the share of the fight they are up, its shields and heals as
the HP they absorb or restore (the healers' from ``kit.healing``, the lifesteal options at their recorded share of
maximum HP), immunity as the damage it keeps off, and Evasion above the attacker's Accuracy (0.06 % a point, up to
30 %). The crowd control your attackers land takes your time away: each lands the classes' typical rotation's
(8.6 s a minute), less your Status Effect Resist, less what Defiance breaks and its Tenacity and the immunity
stigmas keep off. ``score`` is then world DPS x the share of the fight you survive x the share you can act.

Every number in :data:`WORLD` is an assumption, returned with each result. Block (no source gives what a block
removes), movement and player reactions are not modelled.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import replace

from ..kit.defensives import Defensives, defensives as class_defensives, lifesteal_share, shield_on_press
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
    "incoming_control_s": 8.6,      # hard crowd control one attacker lands on you a minute: the mean of the eight
                                    # classes' typical PvP rotations (Stun, Knockdown, Airborne, Fear, Sleep, Frost)
    "incoming_control_cap": 0.5,    # the most of the fight you spend controlled
    "control_length_s": 2.5,        # a typical hard crowd control: a Defiance cuts one short by half of it
    "evasion_per_point": 0.0006,    # evade chance a point of Evasion above the attacker's Accuracy gives (a
    "evasion_cap": 0.30,            # Taiwanese duel test, 2026-05-21), and the global client's stated cap
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
        "gear the loadout gets the median level-45 gear HP and Defense of official profiles. Every class's "
        "defensive passives, buffs, shields and heals count as their tooltips state at the build's levels (shields "
        "and heals as the HP they absorb or restore, timed effects for the share of the fight they are up, the "
        "lifesteal options at the share of maximum HP the recorded heals show), and Evasion above the attacker's "
        "Accuracy evades {evade:.2%} of hits a point, up to {evade_cap:.0%}. Each attacker lands {in_ctl:g} s of hard "
        "crowd control a minute, less your Status Effect Resist and what Defiance and immunity keep off, and you "
        "act only while not controlled. Block, movement and player reactions are not modelled. These are "
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
                       cap=world["control_cap"], evade=world["evasion_per_point"], evade_cap=world["evasion_cap"],
                       in_ctl=world["incoming_control_s"])


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


def _ehp(cls: str, stats, attacker, world: dict) -> tuple[float, float, float]:
    """(effective HP, share of a reference hit you take, maximum HP) against the reference attacker."""
    from ..kit.base import ClassData
    d = stats.defenses(ClassData(cls).base_stats(stats.level))
    flat, coef = world["reference_hit"]
    ctx = HitContext(flat=flat, coef=coef, element=None, tags=(), mult=1.0)
    naked = Target(tolerance=0.0, is_boss=False, is_player=True)
    you = Target(tolerance=d.tolerance, defense=d.defense, crit_resist=d.crit_resist,
                 crit_dmg_tol=d.crit_dmg_tol, is_boss=False, is_player=True)
    base = expected_hit(attacker, {}, naked, ctx)
    taken = expected_hit(attacker, {}, you, ctx) / base if base > 0 else 1.0
    return (d.hp / taken if taken > 0 else math.inf), taken, d.hp


def defensive_absorb_share(cls: str, build, duration: float) -> float:
    """The shields a build's defensive skills grant over a fight of ``duration`` seconds, in shares of maximum HP,
    beside those its damage presses carry (``SimResult.absorb_share``): the Templar's Guarding Seal and Nezekan's
    Shield (``kit.templar.defensive_absorb_share``); no other class has one modelled."""
    if cls != "templar" or build is None:
        return 0.0
    from ..kit.templar import defensive_absorb_share as templar_defensive
    try:
        return templar_defensive(build, duration)
    except Exception:
        return 0.0


def world_kit(cls: str, build, cd, kit):
    """The player-target kit with the shields its presses carry (``kit.defensives.shield_on_press``: Doom Shield,
    Poach's, Grapple's, Ambush Kick's and Siphon's), which the generic kit leaves out."""
    for a in kit.actions.values():
        if not a.absorb:
            a.absorb = shield_on_press(cls, build, cd, a.skill_id)
    return kit


def world_inputs(cls: str, build, cd, stats, res) -> dict:
    """What a build's defensives give over the simulated fight ``res``, for :func:`survival`: shields on top of the
    rotation's, the class's defensive skills, the lifesteal its presses carry, the healers' own healing, and the
    share of the fight a healer spends healing."""
    from ..kit.healing import heal_time_share, modelled_healing
    duration = res.duration
    casts = sum(res.casts.values())
    defense = class_defensives(cls, build, duration, casts_per_s=casts / duration if duration > 0 else 1.0)
    lifesteal = 0.0
    for key, n in res.casts.items():
        sid = getattr(res, "skill_ids", {}).get(key)
        if sid:
            lifesteal += n * lifesteal_share(cls, build, cd, sid)
    heal_hp, heal_time = 0.0, 0.0
    healing = modelled_healing(cls, build, cd, stats.derived())
    if healing:
        heal_hp = healing["self_per_minute"] * duration / 60.0
        heal_time = heal_time_share(cls)
    return {"absorb_share": res.absorb_share + defensive_absorb_share(cls, build, duration), "defense": defense,
            "heal_share": lifesteal, "heal_hp": heal_hp, "heal_time": heal_time}


def _run(cls: str, build, scenario: Scenario, policy=None):
    """Simulate a build in a World PvP scenario: (prepared build, kit, stats, result, world inputs)."""
    cd, b, kit, stats = prepare(build, scenario)
    world_kit(cls, b, cd, kit)
    pol = kit.policy if policy is None else [e for e in policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    res = Sim(stats.derived(), kit.actions, materialize(pol), scenario.target, scenario.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods).run()
    res.skill_ids = {k: a.skill_id for k, a in kit.actions.items()}
    return b, kit, stats, res, world_inputs(cls, b, cd, stats, res)


_REFERENCE: dict = {}


def reference(cls: str, scenario: Scenario, world: dict = WORLD) -> tuple:
    """(attacker, typical EHP): your class's typical build as the reference attacker, and its effective HP with its
    own defensives, shields and heals over the scenario's fight, so the typical build scores 1."""
    from ..scenarios import typical_build
    lo = scenario.loadout
    key = (cls, lo if isinstance(lo, str) else json.dumps(lo, sort_keys=True, default=str),
           json.dumps(world, sort_keys=True, default=str), scenario.config.duration)
    if key not in _REFERENCE:
        b, kit, stats, res, inputs = _run(cls, typical_build(cls), scenario)
        attacker = stats.derived()
        total = _effective(cls, stats, attacker, world, **{k: v for k, v in inputs.items() if k != "heal_time"})
        _REFERENCE[key] = (attacker, total["effective_hp"])
    return _REFERENCE[key]


def evasion_chance(evasion: float, accuracy: float, world: dict = WORLD) -> float:
    """The chance an attacker's hit is evaded: 0.06 % a point of Evasion above its Accuracy, up to 30 % (a
    Taiwanese duel test measured 0.055-0.067 % a point; the global client caps Evasion at 30 %). Both are what gear,
    boards, Genus lines and skills add, the character's base values taken as equal."""
    return max(0.0, min(world["evasion_cap"], world["evasion_per_point"] * (evasion - accuracy)))


def _effective(cls: str, stats, attacker, world: dict, absorb_share: float = 0.0, defense: Defensives | None = None,
               heal_share: float = 0.0, heal_hp: float = 0.0) -> dict:
    """Effective HP against the reference attacker, with the defensives' stats, the share of hits evaded and the
    damage kept off, and the shields and heals over the fight as the HP they stand in for."""
    d = defense or Defensives()
    st = stats
    if d.stats:
        st = stats.copy()
        st.add(d.stats)
    ehp, taken, hp = _ehp(cls, st, attacker, world)
    evade = evasion_chance(st.evasion, attacker.accuracy, world)
    taken_eff = taken * (1 - evade) * (1 - d.reduction)
    plain = hp / taken_eff if taken_eff > 0 else math.inf
    shield_hp = max(0.0, absorb_share + d.shield_share) * hp
    healed = max(0.0, d.heal_share + heal_share) * hp + d.heal_hp + heal_hp
    total = plain + ((shield_hp + healed) / taken_eff if taken_eff > 0 else 0.0)
    return {"effective_hp": total, "effective_hp_without_shields": plain, "max_hp": hp, "damage_taken": taken_eff,
            "evade_chance": evade, "damage_kept_off": d.reduction, "shield_hp": shield_hp, "healed_hp": healed,
            "status_resist": min(1.0, d.status_resist + max(0.0, getattr(st, "cc_resist", 0.0)))}


def survival(cls: str, stats, control_s: float, duration: float, ref: tuple, world: dict = WORLD,
             absorb_share: float = 0.0, defense: Defensives | None = None, heal_share: float = 0.0,
             heal_hp: float = 0.0, heal_time: float = 0.0) -> dict:
    """Effective HP, the share of the fight survived relative to the class's typical build, and the share of it
    you can act in.

    ``absorb_share`` is what the rotation's and the passives' shields absorb over the fight, in shares of
    maximum HP (the Templar's: Doom Shield 5 % and Poach's specialization 10 % a cast, Nezekan's Shield
    41-50 %, Guarding Seal 21-30 % once a minute below half HP, as the tooltips state and the recordings
    measure). A shield absorbs the damage that reaches it as HP does, so under the pressure assumed each
    counts as the HP it absorbs; a shield that lapses unspent would count for less. ``defense`` holds the class's
    defensive skills (``kit.defensives``), ``heal_share`` and ``heal_hp`` the lifesteal and the healers' own
    healing over the fight, ``heal_time`` the share of it a healer spends healing."""
    attacker, typical = ref
    e = _effective(cls, stats, attacker, world, absorb_share, defense, heal_share, heal_hp)
    d = defense or Defensives()
    total = e["effective_hp"]
    attackers = world["attackers"]["melee" if cls in MELEE else "ranged"]
    controlled = min(world["control_cap"], (control_s / duration) / attackers if duration > 0 else 0.0)
    x = (-math.log(1 - world["typical_alive"]) * (total / typical if typical > 0 else 1.0)
         * (world["attackers"]["ranged"] / attackers) / (1 - controlled))
    # the crowd control the attackers land: less what Status Effect Resist and Evasion stop, less what Tenacity and
    # immunity keep off and what Defiance cuts short
    landing = min(world["incoming_control_cap"], attackers * world["incoming_control_s"] / 60.0
                  * (1 - e["status_resist"]) * (1 - e["evade_chance"]))
    kept_off = (landing * d.tenacity_s + d.breaks * world["control_length_s"] / 2) / duration if duration > 0 else 0.0
    taken_control = max(0.0, landing - kept_off)
    shown = stats.defenses({})                     # gear and boards only, for display
    return {"effective_hp": total, "effective_hp_without_shields": e["effective_hp_without_shields"],
            "shield_share": absorb_share + d.shield_share, "shield_hp": e["shield_hp"], "healed_hp": e["healed_hp"],
            "heal_share": d.heal_share + heal_share, "typical_effective_hp": typical,
            "relative_ehp": total / typical if typical > 0 else None, "damage_taken": e["damage_taken"],
            "evade_chance": e["evade_chance"], "damage_kept_off": e["damage_kept_off"],
            "status_resist": e["status_resist"], "attackers": attackers,
            "control_s_per_min": 60 * control_s / duration if duration else 0.0, "controlled": controlled,
            "alive_share": 1 - math.exp(-x), "control_landing": landing, "controlled_self": taken_control,
            "heal_time": heal_time, "acting_share": (1 - taken_control) * (1 - heal_time),
            "defensives": [r for r in d.rows if r.get("counted")],
            "survival_stats": {"tolerance": shown.tolerance, "crit_dmg_tol": shown.crit_dmg_tol}}


def assess(cls: str, build, scenario: Scenario, policy, world: dict = WORLD) -> dict:
    """The World PvP score of a build and priority, with everything it is made of."""
    b, kit, stats, res, inputs = _run(cls, build, scenario, policy)
    surv = survival(cls, stats, res.control, res.duration, reference(cls, scenario, world), world, **inputs)
    return {"score": res.dps * surv["alive_share"] * surv["acting_share"], "dps": res.dps, **surv,
            "assumptions": copy.deepcopy(world), "note": note(world)}


class WorldOptimizer(Optimizer):
    """The pipeline's searches, scored by the World PvP objective instead of DPS."""

    #: the defensive stigmas (Steel Barrier, Arctic Armor, Hibernation, ...) score through survival since 0.2.386
    excluded_stigmas = frozenset()

    def __init__(self, cls, scenario, **kwargs):
        super().__init__(cls, scenario, **kwargs)
        self.world = WORLD
        self.ref = reference(cls, self.scenario, self.world)

    def _ref(self, duration: float) -> tuple:
        """The typical build's reference over a fight as long as the one scored (its shields and heals scale with
        the fight, so a search's shorter fights compare against the same length)."""
        if abs(duration - self.scenario.config.duration) < 1e-9:
            return self.ref
        return reference(self.cls, replace(self.scenario, config=replace(self.scenario.config, duration=duration)),
                         self.world)

    def _score(self, build, cd, stats, res) -> float:
        surv = survival(self.cls, stats, res.control, res.duration, self._ref(res.duration), self.world,
                        **world_inputs(self.cls, build, cd, stats, res))
        return res.dps * surv["alive_share"] * surv["acting_share"]

    def _evaluator(self, build, cfg=None):
        cd, b, kit, stats = prepare(build, self.scenario)
        world_kit(self.cls, b, cd, kit)
        derived, cache = stats.derived(), {}
        config = cfg or self.search_cfg
        ids = {k: a.skill_id for k, a in kit.actions.items()}

        def score(policy):
            key = tuple(policy)
            if key not in cache:
                res = Sim(derived, kit.actions, materialize(policy), self.scenario.target, config,
                          hooks=kit.hooks, cond_mods=kit.cond_mods).run()
                res.skill_ids = ids
                cache[key] = (self._score(b, cd, stats, res), res)
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
        """Damage stats at their DPS gain times the share of the fight survived and acted in; defensive stats at
        the survival they add times the DPS (both in score per unit, the board solver's currency)."""
        cd, b, kit, stats = prepare(build, self.scenario)
        world_kit(self.cls, b, cd, kit)
        config = self.scenario.config if final else self.search_cfg
        pol = self._fit_policy(policy, kit)
        res = Sim(stats.derived(), kit.actions, materialize(pol), self.scenario.target, config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods).run()
        res.skill_ids = {k: a.skill_id for k, a in kit.actions.items()}
        inputs = world_inputs(self.cls, b, cd, stats, res)
        ref = self._ref(res.duration)
        surv = survival(self.cls, stats, res.control, res.duration, ref, self.world, **inputs)
        alive, acting = surv["alive_share"], surv["acting_share"]
        rows = stat_weights(stats, kit, pol, self.scenario.target, config, progress=None if final else self.log)
        for row in rows:
            row["dps_gain"] *= alive * acting
            row["per_unit"] *= alive * acting
        for field, step in DEFENSIVE_STEPS:
            s2 = stats.copy()
            s2.add({field: step})
            more = survival(self.cls, s2, res.control, res.duration, ref, self.world, **inputs)
            gain = res.dps * (more["alive_share"] * more["acting_share"] - alive * acting)
            rows.append({"stat": field, "label": _LABELS[field].format(step=step), "step": step,
                         "dps_gain": gain, "per_unit": gain / step})
        base = res.dps * alive * acting
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
