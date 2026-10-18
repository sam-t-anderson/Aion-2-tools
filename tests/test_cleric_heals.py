"""A Cleric's heals and basic chain (0.2.317), measured from the log server's uploads: in 61 boss fights 14
Clerics pressed a heal 4.6 times a minute at 0.45 s a press, and never pressed Earth's Retribution twice
running. The heals' time is spread over the other presses in a boss fight, never on a training dummy."""
from dataclasses import replace

import pytest

from aion2calc.kit import cleric
from aion2calc.opt.rotation import candidate_keys
from aion2calc.run import prepare
from aion2calc.scenarios import boss, dummy, typical_build
from aion2calc.sim.engine import Action, Sim, Target
from aion2calc.model.stats import Stats

LOADOUT = "cleric_l45_global_median"


def _sim(scen, policy=None, duration=180.0):
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(typical_build("cleric"), scen)
    sim = Sim(stats.derived(), kit.actions, policy or kit.policy, scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim, kit


def test_heals_take_their_recorded_share_of_a_boss_fight_and_none_on_a_dummy():
    fight, kit = _sim(boss(LOADOUT))
    heal = kit.actions["heals"]
    assert heal.heal and heal.cooldown == pytest.approx(60 / cleric.ASSUME["heals_per_minute"])
    assert fight.heal_share == pytest.approx((heal.cast / (1 + fight.base.combat_speed) + fight.cfg.latency) / heal.cooldown)
    assert 0.03 < fight.heal_share < 0.04                       # 4.6 heals a minute at 0.45 s each
    on_dummy, _ = _sim(dummy(LOADOUT))
    assert on_dummy.heal_share == 0.0                           # a dummy deals no damage: nobody heals
    condemnation = kit.actions["condemnation"]
    assert fight.action_time(condemnation) == pytest.approx(on_dummy.action_time(condemnation) / (1 - fight.heal_share))
    res = fight.run()
    assert "heals" not in res.casts                             # spread over the presses, never pressed itself


def test_a_cleric_doing_nothing_but_damage_is_the_old_ceiling(monkeypatch):
    fight, _ = _sim(boss(LOADOUT))
    share, with_heals = fight.heal_share, fight.run().dps
    monkeypatch.setitem(cleric.ASSUME, "heals_per_minute", 0)
    sim, kit = _sim(boss(LOADOUT))
    assert "heals" not in kit.actions and sim.heal_share == 0.0
    # Damage over time, auras and procs keep their own clocks, so the loss is about the share or less.
    assert 0.0 < 1 - with_heals / sim.run().dps < 1.5 * share


def test_a_heal_is_never_chosen_or_searched():
    heal = Action("heals", "Heals", 1, 0.45, cooldown=13.0, heal=True)
    hit = Action("hit", "Hit", 2, 1.0, is_filler=True, on_cast=lambda sim, a: None)
    derived = Stats().derived()
    for party, share in ((True, (0.45 / (1 + derived.combat_speed) + 0.03) / 13.0), (False, 0.0)):
        sim = Sim(derived, {"heals": heal, "hit": hit}, ["heals", "hit"], Target(party_damage=party))
        assert not sim.usable(heal) and sim.choose() is hit
        assert sim.heal_share == pytest.approx(share)
    kit = cleric.build_kit(typical_build("cleric"), cleric.ClassData("cleric"))
    others, _, fillers = candidate_keys(kit)
    assert "heals" in kit.actions and "heals" not in others + fillers and "heals" not in kit.policy


def test_earths_retribution_is_never_pressed_twice_running():
    # While its chain window is open the basic chain sits on Thunder and Lightning: in the uploads Earth's
    # Retribution never followed itself (880 presses) and came back 3.15 s or more later without that step.
    sim, _ = _sim(dummy(LOADOUT), ["earths_retribution"], duration=30.0)
    res = sim.run()
    times = [t for t, key in res.timeline if key == "earths_retribution"]
    assert len(times) > 3 and min(b - a for a, b in zip(times, times[1:])) >= sim.cfg.chain_window - 1e-9
    sim, _ = _sim(dummy(LOADOUT), ["thunder_and_lightning", "earths_retribution"], duration=30.0)
    keys = [key for _, key in sim.run().timeline]
    assert not any(a == b == "earths_retribution" for a, b in zip(keys, keys[1:]))
    assert keys.count("thunder_and_lightning") >= keys.count("earths_retribution") - 1
