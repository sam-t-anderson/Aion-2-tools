"""World PvP (0.2.310): area skills on several players, windows with no enemy in melee reach, crowd control
and a survival-weighted objective that values defensive stats."""
import copy
import math
from dataclasses import replace

import pytest

from aion2calc.kit.base import ClassData
from aion2calc.kit.generic import control_of, reach_of, targets_of
from aion2calc.kit.pvp import build_kit as pvp_kit
from aion2calc.opt import world as W
from aion2calc.run import prepare
from aion2calc.scenarios import SCENARIOS, comparison_scenario, pvp, pvp_world, typical_build
from aion2calc.sim.engine import Sim


def test_tooltips_give_targets_reach_and_crowd_control():
    assert targets_of("Deals {0}-{1} damage to up to 4 enemies within 4m.") == 4
    assert targets_of("deal {0}-{1} damage to up to {2} enemies nearby", [1, 2, 4]) == 4
    assert targets_of("Deals {0}-{1} damage to a target within 20m.") == 1
    assert reach_of("Selects a target within 20m and deals damage to up to 4 enemies within 4m") == 20
    assert reach_of("Rushes to a target within 7.5m to deal damage") == 7.5
    assert reach_of("Increases the caster's Attack by {0}%") is None
    # guaranteed, by chance, extended by a specialization; cleanses and NPC-only clauses never count
    assert control_of("X", "Deals damage and inflicts Knockdown for {2}.", [0, 0, {"ms": 3000}], []) == 3
    assert control_of("X", "Deals damage with a {2}% chance to inflict Stun for {3}.", [0, 0, 60, {"ms": 2000}],
                      ["+1s Stun duration", "+20% Stun Chance"]) == pytest.approx(0.8 * 3)
    assert control_of("X", "Removes Stun, Knockdown and Fear from the caster.", [], []) == 0
    assert control_of("X", "100% chance to inflict Stun on NPC targets for {0}.", [{"ms": 2000}], []) == 0
    assert control_of("Bolt", "Deals damage.", [], ["30% chance to inflict Stun for 3s when fully charged"]) \
        == pytest.approx(0.9)
    assert control_of("X", "Deals damage.", [], ["[Blade Dance] has 30% chance to inflict Knockdown for 3s"]) == 0


def test_the_pvp_kits_mark_melee_ranged_and_area_skills():
    glad = pvp_kit(typical_build("gladiator"), ClassData("gladiator"))
    assert glad.actions["keen_strike"].reach == 4 and glad.actions["rush_strike"].reach >= 10
    assert glad.actions["ruinous_blow"].targets == 4 and glad.actions["mocking_blade"].control == 3
    sorc = pvp_kit(typical_build("sorcerer"), ClassData("sorcerer"))
    assert all(a.reach is None or a.reach >= 10 for a in sorc.actions.values())


def _run(cls, scen, policy=None):
    _, _, kit, stats = prepare(typical_build(cls), scen)
    return Sim(stats.derived(), kit.actions, policy or kit.policy, scen.target, scen.config,
               hooks=kit.hooks, cond_mods=kit.cond_mods).run(), kit


def test_area_skills_hit_every_enemy_in_reach_and_melee_loses_reach_in_the_windows():
    single, _ = _run("sorcerer", pvp("sorcerer_l45_global_median"))
    world_scen = replace(pvp_world("sorcerer_l45_global_median"), target=replace(
        pvp_world("sorcerer_l45_global_median").target, out_of_reach=()))
    many, kit = _run("sorcerer", world_scen)
    assert many.dps > single.dps
    # an area skill lands on all three enemies in reach, a single-target one on one
    aoe = next(a for a in kit.actions.values() if a.targets >= 4 and single.casts.get(a.key) and many.casts.get(a.key))
    per_cast = lambda r: r.damage_by[aoe.name] / r.casts[aoe.key]           # noqa: E731
    assert per_cast(many) / per_cast(single) == pytest.approx(3.0, rel=0.25)
    one = next(a for a in kit.actions.values() if a.targets == 1 and single.casts.get(a.key) and many.casts.get(a.key)
               and a.name in single.damage_by)
    assert many.damage_by[one.name] / many.casts[one.key] == pytest.approx(
        single.damage_by[one.name] / single.casts[one.key], rel=0.05)
    # a melee class can only use what reaches 10 m in the out-of-reach windows
    scen = pvp_world("gladiator_l45_global_median")
    res, kit = _run("gladiator", scen)
    windows = scen.target.out_of_reach
    assert windows and windows[0] == (7.0, 10.0)
    for t, key in res.timeline:
        a = kit.actions[key]
        if any(s <= t < e for s, e in windows):
            assert a.reach is None or a.reach >= 10, (t, key)


def test_world_scenario_adds_median_gear_survival_once():
    scen = pvp_world("cleric_l45_global_median")
    comps = [c for c in scen.loadout["components"] if c.get("source") == W.SOURCE]
    assert len(comps) == 1 and comps[0]["stats"]["hp"] > 3000 and comps[0]["stats"]["defense"] > 5000
    again = W.with_world(scen)
    assert len([c for c in again.loadout["components"] if c.get("source") == W.SOURCE]) == 1
    # an imported loadout with its own HP / Defense keeps them
    own = copy.deepcopy(scen.loadout)
    own["components"] = [c for c in own["components"] if c.get("source") != W.SOURCE]
    own["components"].append({"slot": "Chest", "stats": {"hp": 900.0, "defense": 800.0}})
    assert not any(c.get("source") == W.SOURCE for c in W.with_gear_survival(own)["components"])
    assert comparison_scenario("pvp_world") == "pvp" and "pvp_world" in SCENARIOS


def test_survival_rewards_defense_crowd_control_and_weighs_melee_harder():
    scen = pvp_world("gladiator_l45_global_median")
    b = typical_build("gladiator")
    _, _, kit, stats = prepare(b, scen)
    ref = W.reference("gladiator", scen)
    base = W.survival("gladiator", stats, 0.0, 180.0, ref)
    assert base["relative_ehp"] == pytest.approx(1.0)
    assert base["alive_share"] == pytest.approx(1 - 2 ** -(1.5 / 3))      # twice the attackers of a ranged class
    tough = stats.copy()
    tough.add({"hp": 3000.0, "defense": 2000.0})
    assert W.survival("gladiator", tough, 0.0, 180.0, ref)["alive_share"] > base["alive_share"]
    controlled = W.survival("gladiator", stats, 180.0, 180.0, ref)        # one enemy controlled at all times
    assert controlled["controlled"] == pytest.approx(1 / 3)
    assert controlled["alive_share"] > base["alive_share"]
    capped = W.survival("gladiator", stats, 10_000.0, 180.0, ref)
    assert capped["controlled"] == W.WORLD["control_cap"]
    ranged = W.survival("sorcerer", *[prepare(typical_build("sorcerer"), pvp_world("sorcerer_l45_global_median"))[3]],
                        0.0, 180.0, W.reference("sorcerer", pvp_world("sorcerer_l45_global_median")))
    assert ranged["alive_share"] == pytest.approx(W.WORLD["typical_alive"])


def test_the_world_optimizer_values_defensive_nodes():
    from aion2calc.opt.statweights import node_values
    scen = pvp_world("templar_l45_global_median")
    opt = W.WorldOptimizer("templar", scen, verbose=False, search_duration=60.0)
    b = typical_build("templar")
    _, _, kit, _ = prepare(b, scen)
    rows = {r["stat"]: r for r in opt._stat_weights(b, kit.policy)}
    assert rows["hp"]["per_unit"] > 0 and rows["defense"]["per_unit"] > 0
    nv = node_values(ClassData("templar"), list(rows.values()))
    cd = ClassData("templar")
    hp_nodes = [nid for nid, (bd, n) in cd.node_index.items()
                if bd["name"] != "Azphel" and any(s["stat"] == "HPMax" for s in n.get("stats", []))]
    assert hp_nodes and all(nv.get(nid, 0) > 0 for nid in hp_nodes)
    score = opt.evaluate(b, kit.policy)
    direct = W.assess("templar", b, replace(scen, config=replace(scen.config, duration=60.0)), kit.policy)
    assert score == pytest.approx(direct["score"], rel=1e-6)
    assert math.isfinite(score) and 0 < score < direct["dps"]
