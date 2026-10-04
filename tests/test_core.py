import base64
import json

import pytest

from aion2calc.kit.base import (Build, ClassData, sp_to_reach, spec_slots,
                                stigma_points_to_reach)
from aion2calc.model.damage import HitContext, expected_hit
from aion2calc.model.stats import Stats, crit_chance
from aion2calc.sim.engine import Action, Sim, SimConfig, Target


def test_point_costs_match_client_tables():
    assert sp_to_reach(10) == 21          # Lv 2-4: 1, 5-7: 2, 8-10: 4
    assert sp_to_reach(7) == 9
    assert stigma_points_to_reach(20) == 75
    assert stigma_points_to_reach(10) == 15
    assert [spec_slots(l) for l in (7, 8, 11, 12, 19, 20)] == [0, 1, 1, 2, 2, 3]


def test_crit_curve_matches_community_points():
    # TW measurements: 1048 -> 56%, 1220 -> 80% (capped), 1326 -> 90% (capped at 80%)
    assert crit_chance(1048) == pytest.approx(0.56, abs=0.03)
    assert crit_chance(1220) == pytest.approx(0.80, abs=0.01)
    assert crit_chance(2000) == 0.80


def _derived(**kw):
    s = Stats(weapon_min=100, weapon_max=100, attack=900)
    s.add(kw)
    return s.derived()


def test_expected_hit_plain():
    d = _derived()
    t = Target(tolerance=0.0)
    # Attack 1000, 50% coefficient + 100 flat, no crit stat -> crit chance ~0
    dmg = expected_hit(d, {}, t, HitContext(flat=100, coef=0.5))
    assert dmg == pytest.approx(600 * (1 + crit_chance(0) * 0.5), rel=1e-6)


def test_double_and_perfect_are_exclusive_and_dot_ignores_them():
    d = _derived(double=1.0, perfect=1.0)
    t = Target(tolerance=0.0)
    direct = expected_hit(d, {}, t, HitContext(flat=0, coef=1.0, tags=("crit",)))
    # double always -> 2x, crit guaranteed -> 1.5x ; perfect cannot stack with double
    assert direct == pytest.approx(1000 * 2 * 1.5, rel=1e-6)
    dot = expected_hit(d, {}, t, HitContext(flat=0, coef=1.0, tags=("dot",)))
    assert dot == pytest.approx(1000, rel=1e-6)


def test_boost_bucket_is_additive_and_element_multiplicative():
    d = _derived(amp_pve=0.2, amp_all=0.1, fire_amp=0.2)
    t = Target(tolerance=0.1)
    fire = expected_hit(d, {}, t, HitContext(flat=0, coef=1.0, element="fire", tags=("dot",)))
    assert fire == pytest.approx(1000 * (1 + 0.3 - 0.1) * 1.2, rel=1e-6)


def _toy_actions():
    def nuke(sim, a):
        sim.hit("Nuke", 0, 1.0)

    def poke(sim, a):
        sim.hit("Poke", 0, 0.2)

    def burn(sim, a):
        sim.dot("burn", "Burn", 0, 0.1, 1.0, 5.0)
    return {
        "nuke": Action("nuke", "Nuke", 1, 1.0, cooldown=10.0, on_cast=nuke),
        "burn": Action("burn", "Burn", 2, 1.0, cooldown=30.0, on_cast=burn),
        "poke": Action("poke", "Poke", 3, 1.0, on_cast=poke, is_filler=True),
    }


def test_engine_respects_cooldowns_and_ticks_dots():
    d = _derived()
    sim = Sim(d, _toy_actions(), ["nuke", "burn", "poke"], Target(tolerance=0.0),
              SimConfig(duration=30.0, latency=0.0))
    r = sim.run()
    assert r.casts["nuke"] == 3            # t = 0, 10, 20
    assert r.casts["burn"] == 1
    assert r.hits_by["Burn"] == 5          # 5 ticks of 1 s
    assert r.idle == 0.0


def test_combat_speed_shortens_actions():
    slow = Sim(_derived(), _toy_actions(), ["poke"], Target(), SimConfig(duration=20.0, latency=0.0)).run()
    fast = Sim(_derived(combat_speed=1.0), _toy_actions(), ["poke"], Target(),
               SimConfig(duration=20.0, latency=0.0)).run()
    assert fast.casts["poke"] == pytest.approx(2 * slow.casts["poke"], abs=1)


@pytest.fixture(scope="module")
def sorc():
    return ClassData("sorcerer")


def test_sorcerer_data_loaded(sorc):
    assert sorc.budget(45)["skill"] == 203
    assert sorc.budget(45)["stigma"] == 29
    assert {b["name"] for b in sorc.boards} >= {"Nezekan", "Zikel", "Vaizel", "Triniel"}
    crystal = sum(n["cost"] for b in sorc.boards if b["name"] != "Azphel" for n in b["nodes"])
    assert crystal == 570                  # 134 * 3 + 168


def test_daevanion_program_respects_budget_and_connectivity(sorc):
    from aion2calc.opt import daevanion as dv
    values = {nid: 1.0 for nid, (b, n) in sorc.node_index.items() if n["type"] == "Stat"}
    sol = dv.solve(sorc, {}, values, daev_budget=40, sp_budget=0, time_limit=60)
    assert sol["daev_cost"] <= 40
    assert dv.connected(sorc, sol["nodes"])
    assert len(sol["nodes"]) >= 30         # cheap Common nodes are worth 1 each


def test_links_round_trip(sorc):
    from aion2calc.render.links import gamers4life_daevanion_url, metabot_daevanion_hash
    nodes = {610034, 610035}
    url = gamers4life_daevanion_url("sorcerer", nodes)
    b = url.split("?b=")[1]
    payload = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    assert payload == {"c": "sorcerer", "d": sorted(nodes)}
    h = metabot_daevanion_hash(sorc, nodes)
    board_id, idx = h.split("-")
    board = next(x for x in sorc.boards if str(x["id"]) == board_id)
    decoded = {board["nodes"][int(i, 36)]["id"] for i in idx.split(".")}
    assert decoded == nodes


def test_sorcerer_kit_mechanics(sorc):
    from aion2calc.kit.sorcerer import SID
    from aion2calc.run import Scenario, simulate
    b = Build("sorcerer", sp={SID["FA"]: 10, SID["BLAZE"]: 10})
    b.bonus = {SID["FA"]: 6, SID["BLAZE"]: 6}          # level 16 -> spec 5 available
    b.specs = {SID["FA"]: (SID["FA"] + 50,)}           # Pyroclasm resets Blaze
    base = simulate(Build("sorcerer", sp={SID["FA"]: 10, SID["BLAZE"]: 10}), Scenario(),
                    policy=["blaze", "flame_arrow"])
    reset = simulate(b, Scenario(), policy=["blaze", "flame_arrow"])
    assert reset.casts["blaze"] > base.casts["blaze"]
    assert base.casts["blaze"] > 0                      # Fire Mark from Flame Arrow enables Blaze


@pytest.mark.parametrize("cls", ["gladiator", "templar", "assassin", "ranger",
                                 "sorcerer", "spiritmaster", "cleric", "chanter"])
def test_every_class_simulates(cls):
    """The same pipeline runs for any class: community build -> kit -> simulation."""
    from aion2calc.run import simulate
    from aion2calc.scenarios import SCENARIOS, community_build
    res = simulate(community_build(cls), SCENARIOS["boss"](f"{cls}_l45_global_median"))
    assert res.dps > 1000
    assert sum(res.casts.values()) > 30


def test_arcana_pools_are_passives():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "aion2calc" / "data" / "global" / "arcana_skill_pools.json"
    pools = json.loads(path.read_text(encoding="utf-8"))
    sorc = ClassData("sorcerer")
    assert pools["sorcerer"]["max_level"] == 4
    assert all(sorc.by_name[n]["kind"] == "passive" for n in pools["sorcerer"]["skills"])
