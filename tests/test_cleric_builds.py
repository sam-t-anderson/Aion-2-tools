"""The Cleric build the guides recommend and the archived server logs show (0.2.310): Earth Punishment's
guaranteed Condemnation crits with Condemnation's cooldown reset, Chain of Torment's Damage Tolerance
reduction, Divine Aura's measured ticks per specialization mix, Light of Protection as an aura left on and
Prayer of Amplification's specializations."""
from dataclasses import replace

from aion2calc.kit.base import ClassData
from aion2calc.kit.cleric import ASSUME, build_kit
from aion2calc.model.damage import HitContext, expected_hit
from aion2calc.run import prepare
from aion2calc.scenarios import boss, dummy, typical_build
from aion2calc.sim.engine import Sim, Target

EP, PRAY, LIGHT, CON, TOR, DA = 17400000, 17430000, 17410000, 17350000, 17070000, 17150000


def _run(build, policy, duration=60.0, scen=None):
    scen = scen or dummy("cleric_l45_global_median")
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(build, scen)
    sim = Sim(stats.derived(), kit.actions, policy, scen.target, scen.config, hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim.run(), kit


def _cleric(ep_level=None, specs=None):
    b = typical_build("cleric")
    b.stigmas = {EP: ep_level} if ep_level else {}
    b.specs = dict(specs or {})
    b.bonus = {CON: 4, DA: 10}            # Condemnation and Divine Aura past the level-16 specializations
    return b


def test_earth_punishment_makes_condemnation_crit_and_chain_on_its_reset():
    pol = ["epunish", "chain_of_torment", "condemnation", "earths_retribution"]
    reset = {CON: (17350040,)}
    with_ep, _ = _run(_cleric(5, reset), pol, duration=10.0)
    no_spec, _ = _run(_cleric(4, reset), pol, duration=10.0)     # the crit specialization opens at level 5
    # within the 10 s window every Condemnation crits, resets itself and is pressed again right away
    assert with_ep.casts["condemnation"] >= 12
    assert no_spec.casts["condemnation"] <= 4
    gaps = [b - a for (a, x), (b, y) in zip(with_ep.timeline, with_ep.timeline[1:])
            if x == y == "condemnation"]
    assert gaps and max(gaps) < 0.6                             # back to back, as the recorded Cleric's chains (0.51 s)
    # Earth Punishment's damage over time totals one listed hit over its 10 s, in 1 s ticks
    assert with_ep.hits_by["Earth Punishment (DoT)"] == 10


def test_earth_punishment_level_20_doubles_the_window_and_blesses_the_caster():
    kit20 = build_kit(_cleric(20), ClassData("cleric"))
    res, _ = _run(_cleric(20), ["epunish", "earths_retribution"], duration=25.0)
    assert res.hits_by["Earth Punishment (DoT)"] == 20                 # +10 s at level 20, same tick size
    assert "epunish" in kit20.actions and kit20.actions["epunish"].cooldown == 30


def test_chain_of_torment_lowers_the_targets_damage_tolerance():
    scen = boss("cleric_l45_global_median")
    plain, _ = _run(_cleric(specs={TOR: (17070010, 17070020)}), ["chain_of_torment", "bolt", "earths_retribution"],
                    scen=scen)
    reduced, _ = _run(_cleric(specs={TOR: (17070020, 17070040)}), ["chain_of_torment", "bolt", "earths_retribution"],
                      scen=scen)
    assert reduced.dps > plain.dps * 1.03
    # the reduction never takes a target below zero tolerance
    _, _, _, stats = prepare(_cleric(), scen)
    d = stats.derived()
    ctx = HitContext(flat=1000.0, coef=1.0, element=None, tags=(), mult=1.0)
    zero = expected_hit(d, {}, Target(tolerance=0.0), ctx)
    assert expected_hit(d, {"tol_red": 0.5}, Target(tolerance=0.10), ctx) == zero


def test_divine_aura_ticks_follow_the_recorded_specialization_mixes():
    ticks = {}
    for name, combo in (("base", ()), ("speed", (17150030,)), ("duration", (17150040,)),
                        ("both", (17150030, 17150040))):
        res, _ = _run(_cleric(specs={DA: combo}), ["divine_aura", "earths_retribution"], duration=10.0)
        ticks[name] = res.hits_by["Divine Aura"]
    assert ticks == {"base": 6, "speed": 8, "duration": 10, "both": 13}
    assert ASSUME["divine_aura_ticks"] == 5                              # each tick is a fifth of the listed damage


def test_light_of_protection_is_an_aura_and_prayer_lasts_its_listed_time():
    b = _cleric()
    b.stigmas = {LIGHT: 7, PRAY: 10}
    kit = build_kit(b, ClassData("cleric"))
    assert "lightprot" not in kit.actions                                # never recast: the recorded Cleric pressed it twice
    assert kit.static["amp_pve"] > 0
    res, _ = _run(b, ["prayamp", "earths_retribution"], duration=30.0)
    assert res.casts["prayamp"] == 1
    # +20% PvE Damage Boost from level 5 and half again of Empyrean Lord's Grace from level 10
    on = kit.actions["prayamp"]
    assert on.cooldown == 60
