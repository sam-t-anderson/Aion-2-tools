"""The Templar kit measured from the log server's uploads (0.2.315): Punishing Strike as Pummel's
chain press, the basic-attack chain one step a press, Doom Shield's Judgment window and knockdown,
and the trigger windows read from the tooltips."""
from dataclasses import replace

import pytest

from aion2calc.kit import templar
from aion2calc.kit.base import ClassData
from aion2calc.opt.rotation import with_essentials
from aion2calc.run import prepare
from aion2calc.scenarios import dummy, typical_build
from aion2calc.sim.engine import Sim


def _sim(policy=None, *, build=None, duration=120.0):
    scen = dummy("templar_l45_global_median")
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(build or typical_build("templar"), scen)
    sim = Sim(stats.derived(), kit.actions, policy or kit.policy, scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim.run(), kit


def test_punishing_strike_follows_pummel_once_per_press():
    res, _ = _sim(["punishing_strike", "vicious_strike"])
    assert res.casts.get("punishing_strike", 0) == 0             # nothing opens it without Pummel
    res, kit = _sim(["punishing_strike", "pummel", "vicious_strike"])
    pummels, strikes = res.casts["pummel"], res.casts["punishing_strike"]
    assert 0.9 * pummels <= strikes <= pummels                  # one per Pummel: the press spends the window
    # its measured share of Pummel's press (three strikes for the tooltip's damage)
    per = res.damage_by["Punishing Strike"] / res.hits_by["Punishing Strike"]
    assert per == pytest.approx(templar.ASSUME["punishing_frac"] * res.damage_by["Pummel"] / res.hits_by["Pummel"], rel=0.15)
    assert kit.actions["punishing_strike"].skill_id == templar.PUNISHING_STRIKE


def test_the_basic_chain_is_one_step_a_press():
    res, kit = _sim(["vicious_strike"], duration=30.0)
    steps = [res.hits_by.get(name, 0) for name, _, _ in templar.WEAVE["steps"]]
    assert sum(steps) == res.casts["vicious_strike"]
    assert max(steps) - min(steps) <= 1                         # Vicious -> Decisive -> Desperate in turn
    assert kit.actions["vicious_strike"].cast == templar.TIMING["vicious_strike"]


def test_the_rotation_fires_judgment_and_punishing_strike():
    # the kit dealt all three chain steps in one 0.8 s action, which outdamaged everything: the
    # optimized rotation pressed nothing else and never fired Judgment
    res, _ = _sim()
    for key in ("judgment", "punishing_strike", "pummel", "punishment"):
        assert res.casts.get(key, 0) > 0, key
    shares = res.shares()
    basic = sum(v for k, v in shares.items() if k.split(" (")[0] in {n for n, _, _ in templar.WEAVE["steps"]})
    assert basic < 0.35
    assert any(k.endswith("(woven)") for k in shares)


def test_doom_shield_opens_judgment_and_knocks_down():
    build = typical_build("templar")
    assert templar.SID["DOOM"] in build.stigmas
    res, _ = _sim(["judgment", "doom", "vicious_strike"], build=build, duration=60.0)
    assert res.casts.get("judgment", 0) > 0                     # the only trigger in the list
    res, _ = _sim(["annihilate", "doom", "vicious_strike"], build=build, duration=60.0)
    assert res.casts.get("annihilate", 0) > 0                   # its knockdown opens Annihilate


def test_trigger_windows_come_from_the_tooltips():
    cd = ClassData("templar")
    assert templar._judgment_window(cd, templar.SID["SMITE"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["WARD"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["SRUSH"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["DOOM"], 6) == pytest.approx(3.0)
    assert templar._judgment_window(cd, templar.SID["PUM"], 10) == templar.ASSUME["judgment_window"]


def test_pummel_costs_mp_and_vicious_strikes_fourth_spec_cuts_warding_strike():
    cd = ClassData("templar")
    build = typical_build("templar")
    kit = templar.build_kit(build, cd)
    level = build.effective_levels(cd)[templar.SID["PUM"]]
    assert kit.actions["pummel"].mp == pytest.approx(cd.mp(templar.SID["PUM"], level))
    cheaper = typical_build("templar")
    cheaper.specs = {templar.SID["PUM"]: (templar.SID["PUM"] + 10,)}
    assert templar.build_kit(cheaper, cd).actions["pummel"].mp == pytest.approx(0.8 * kit.actions["pummel"].mp)
    # "-2s [Warding Strike] cooldown on hit" is Vicious Strike's fourth spec; the second absorbs HP
    pol = ["warding_strike", "vicious_strike"]
    wardings = {}
    for idx in (2, 4):
        b = typical_build("templar")
        b.specs = {templar.SID["VIC"]: (templar.SID["VIC"] + 10 * idx,)}
        wardings[idx] = _sim(pol, build=b)[0].casts["warding_strike"]
    assert wardings[4] > wardings[2]


def test_a_saved_list_from_before_punishing_strike_gets_it():
    kit = templar.build_kit(typical_build("templar"), ClassData("templar"))
    old = ["afury", "punishment", "annihilate", "judgment", "pummel", "vicious_strike"]
    assert with_essentials(old, kit)[0] == "punishing_strike"
    assert with_essentials(kit.policy, kit) == kit.policy
