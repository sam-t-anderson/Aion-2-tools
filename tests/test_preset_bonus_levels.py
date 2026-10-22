"""Bonus skill levels from gear rolls and arcana cards in the community presets (0.2.328).

The common planner loadout carries no skill options, so a community preset's skills stopped at level 14
(10 trained plus the Daevanion levels) and never reached the fifth supporting effect (16) or the third
selection slot (20). The point observation a collected character sends now carries the skill levels its
gear rolls and arcana cards give; the server publishes the highest total and per-skill count it saw as
the scoring policy's allowance; the search places that many and the preset names the skills to put them
on. The planner's catalog also offers arcana cards at +0..+5 (one more skill option a step).
"""
import json
import types

import pytest

from aion2calc.paths import resource_root

ALLOWANCE = {"levels": 20, "per_skill": 8}


def _summary():
    return json.loads((resource_root() / "results/sorcerer_l45/build.json").read_text(encoding="utf-8"))


def test_the_policy_carries_the_allowance_in_its_scope():
    from aion2calc.canonical_presets import scoring_policy
    from aion2calc.presets import InvalidPreset
    plain = scoring_policy("sorcerer", "pve")
    allowed = scoring_policy("sorcerer", "pve", None, ALLOWANCE)
    assert "bonus" not in plain and plain["version"] == 1
    assert allowed["bonus"] == ALLOWANCE and allowed["version"] == 2 and allowed["scope"] != plain["scope"]
    assert "arcana" in allowed["note"]
    for bad in ({"levels": 0, "per_skill": 4}, {"levels": 10}, {"levels": 10, "per_skill": 99}, {"levels": "10", "per_skill": 4}, [10, 4]):
        with pytest.raises(InvalidPreset):
            scoring_policy("sorcerer", "pve", None, bad)


def test_a_candidate_keeps_bonus_levels_within_the_allowance():
    from aion2calc.canonical_presets import candidate, candidate_bonus, scoring_policy
    from aion2calc.kit.base import ClassData
    cd = ClassData("sorcerer")
    summary = _summary()
    summary["build"]["bonus"] = {"Ice Chain": 6, "Firestorm": 3}
    allowed = candidate(summary, scoring_policy("sorcerer", "pve", None, ALLOWANCE))
    assert allowed["build"]["build"]["bonus"] == {"Ice Chain": 6, "Firestorm": 3}
    assert "bonus" not in candidate(summary, scoring_policy("sorcerer", "pve"))["build"]["build"]   # none allowed: none sent
    # A personal build carries its rolls in its loadout snapshot: folded in by skill name, cut to the allowance.
    personal = _summary()
    personal["loadout_snapshot"] = {"level": 45, "components": [
        {"slot": "Gear skill rolls", "item": "arcana, accessories and armor skill options",
         "stats": {"skill_bonus": {str(cd.by_name["Hellfire"]["id"]): 5, str(cd.by_name["Blaze"]["id"]): 3}}}]}
    assert candidate_bonus("sorcerer", personal, {"levels": 6, "per_skill": 4}) == {"Hellfire": 3, "Blaze": 3}
    assert candidate_bonus("sorcerer", personal, None) == {}


def test_parse_checks_bonus_levels_against_the_allowance():
    from aion2calc.kit.base import ClassData
    from aion2calc.presets import InvalidPreset, candidate as legacy, parse

    def doc(bonus):
        document = legacy(_summary())
        document["build"]["build"]["bonus"] = bonus          # as a tampered document would carry it
        return document

    build, _ = parse(doc({"Ice Chain": 6}), bonus=ALLOWANCE)
    assert build.bonus == {ClassData("sorcerer").by_name["Ice Chain"]["id"]: 6}
    with pytest.raises(InvalidPreset):
        parse(doc({"Ice Chain": 6}))                                                  # no allowance in this scope
    with pytest.raises(InvalidPreset):
        parse(doc({"Ice Chain": 9}), bonus=ALLOWANCE)                                  # over the per-skill cap
    with pytest.raises(InvalidPreset):
        parse(doc({"Ice Chain": 8, "Firestorm": 8, "Blaze": 8}), bonus=ALLOWANCE)      # over the total
    for bad in ({"Nope": 1}, {"Ice Chain": 0}, {"Ice Chain": "6"}, {"Ice Chain": 41}, ["Ice Chain"]):
        with pytest.raises(InvalidPreset):
            parse(doc(bad), bonus=ALLOWANCE)
    assert parse(doc({}), bonus=ALLOWANCE)[0].bonus == {}                            # an allowance needs no bonus
    assert "bonus" not in legacy({**_summary(), "build": {**_summary()["build"], "bonus": ["x"]}})["build"]["build"]   # not a map: dropped


def test_evaluation_with_bonus_levels_reaches_the_fifth_effect_and_third_slot():
    from aion2calc.app.views import build_view
    from aion2calc.canonical_presets import candidate, evaluate, scoring_policy
    from aion2calc.kit.base import ClassData
    cd = ClassData("sorcerer")
    policy = scoring_policy("sorcerer", "pve", None, ALLOWANCE)
    summary = _summary()
    fifth = next(x["text"] for x in cd.by_name["Ice Chain"]["specs"] if x["unlock"] == 16)
    summary["build"]["specs"]["Ice Chain"] = summary["build"]["specs"]["Ice Chain"][:2] + [fifth]
    plain = evaluate(candidate(summary, scoring_policy("sorcerer", "pve")))
    # without bonus levels the skill stays at 14: the level-16 effect and the third slot are stripped
    assert plain["build"]["effective_levels"]["Ice Chain"] == 14 and len(plain["build"]["specs"]["Ice Chain"]) == 2
    summary["build"]["bonus"] = {"Ice Chain": 6}
    boosted = evaluate(candidate(summary, policy), None, ALLOWANCE)
    assert boosted["build"]["effective_levels"]["Ice Chain"] == 20
    assert len(boosted["build"]["specs"]["Ice Chain"]) == 3 and boosted["build"]["specs"]["Ice Chain"][-1] == fifth
    assert boosted["build"]["bonus"] == {"Ice Chain": 6} and boosted["score"] > plain["score"]
    assert boosted["scoring_policy"]["bonus"] == ALLOWANCE and boosted["scoring_policy"]["scope"] == policy["scope"]
    view = build_view(boosted)
    assert view["bonus_levels"] == [{"name": "Ice Chain", "levels": 6, "arcana": ["Chalice", "Compass"]}]
    assert next(s for s in view["skills"]["active"] if s["name"] == "Ice Chain")["gear"] == 6


def test_the_pool_goes_where_the_level_curves_gain_most():
    from aion2calc.opt.bonus import allocate_pool, trim, valid_pool
    curves = {1: [0, 10, 20, 30, 30, 30], 2: [0, 5, 6, 7, 8, 50, 50]}
    assert allocate_pool(curves, {1: 1, 2: 1}, {"levels": 5, "per_skill": 4}) == {2: 4, 1: 1}   # the run to skill 2's jump wins
    assert allocate_pool(curves, {1: 1, 2: 1}, {"levels": 5, "per_skill": 3}) == {1: 2, 2: 3}   # the jump is out of reach
    assert allocate_pool(curves, {1: 3, 2: 5}, {"levels": 5, "per_skill": 3}) == {}             # nothing left to gain
    assert allocate_pool(curves, {1: 1, 2: 1}, {"levels": 5, "per_skill": 4}, max_level=2) == {1: 1, 2: 1}
    assert trim({"a": 9, "b": 2, "c": 0}, {"levels": 6, "per_skill": 5}) == {"a": 4, "b": 2} and trim({"a": 3}, None) == {}
    assert valid_pool({"levels": 10, "per_skill": 4}) and not valid_pool({"levels": 10, "per_skill": 0}) and not valid_pool([10, 4])


def test_the_optimizer_places_the_pool_and_solves_the_points_around_it(monkeypatch):
    """One skill with a steep curve: the pool fills it toward the curve's end (the third slot at 20), the
    points are solved again around the placement, and the build's bonus holds it."""
    from aion2calc.opt import pipeline
    from aion2calc.scenarios import SCENARIOS
    logged = []
    opt = pipeline.Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"), verbose=False,
                             progress=logged.append, bonus_pool={"levels": 10, "per_skill": 8})
    build = opt.initial_build()
    sid = opt.cd.by_name["Ice Chain"]["id"]
    monkeypatch.setattr(opt, "level_curves", lambda b, p: {sid: [0.0] + [10.0 * level for level in range(1, 21)]})
    monkeypatch.setattr(opt, "_stat_weights", lambda b, p, final=False: [])
    monkeypatch.setattr(pipeline, "DAEV_SOLVER_TIME_LIMIT", 20)
    allocated, _, _, _ = opt.allocate(build, [])
    placed = allocated.bonus[sid]
    assert 1 <= placed <= 8 and sum(allocated.bonus.values()) <= 10 and set(allocated.bonus) == {sid}
    effective = opt._with_gear(allocated).effective_levels(opt.cd)[sid]
    assert effective == 20 or placed == 8
    assert sum(1 for line in logged if "solver finished" in line) == 2
    assert any("bonus levels:" in line and "Ice Chain" in line for line in logged)
    with pytest.raises(ValueError):
        pipeline.Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"), verbose=False, bonus_pool={"levels": 0, "per_skill": 1})


def test_the_point_observation_carries_gear_and_arcana_skill_levels():
    from aion2calc.app import server
    imp = types.SimpleNamespace(cls="sorcerer", systems={
        "equipment": [{"slot": "Necklace", "skills": [["Ice Chain", 1], ["Hellfire", 2]]},
                      {"slot": "Ring1", "skills": [["Ice Chain", 1], ["Not A Skill", 3], ["Blaze", "x"]]}],
        "arcana": [{"slot": "Arcana1", "skills": [["Firestorm", 4], ["Ice Chain", 2]]}]})
    assert server._skill_bonus_observation(imp) == {"gear": {"Ice Chain": 2, "Hellfire": 2}, "arcana": {"Firestorm": 4, "Ice Chain": 2}}
    body = server._point_observation({"region": "nae", "game_patch": "2.0"}, imp,
                                     {"skill": 200, "stigma": 30, "daevanion": 360, "extra": 1}, "profile_lower_bound")
    assert body["points"] == {"skill": 200, "stigma": 30, "daevanion": 360} and body["source"] == "profile_lower_bound"
    assert body["skill_bonus"] == {"gear": {"Ice Chain": 2, "Hellfire": 2}, "arcana": {"Firestorm": 4, "Ice Chain": 2}}
    bare = types.SimpleNamespace(cls="sorcerer", systems={"equipment": [], "arcana": []})
    assert "skill_bonus" not in server._point_observation({}, bare, {"skill": 1, "stigma": 1, "daevanion": 1}, "user_reported")


def test_collecting_a_character_shares_its_gear_skill_levels(monkeypatch):
    from aion2calc import charopt
    from aion2calc.app import server
    from aion2calc.combat import share
    sent = []
    monkeypatch.setattr(server, "ui_settings", lambda: {})
    monkeypatch.setattr(charopt, "at_level_cap", lambda imp: True)
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://community.test"})
    monkeypatch.setattr(share, "community_request", lambda path, body: sent.append((path, body)) or {"accepted": True})
    imp = types.SimpleNamespace(cls="sorcerer", systems={"equipment": [{"slot": "Necklace", "skills": [["Ice Chain", 1]]}], "arcana": []})
    server._contribute_character_points({"region": "nae"}, imp, {"budgets": {"skill": 200, "stigma": 30, "daevanion": 360}}, lambda m: None)
    assert sent == [("/api/v1/progression", {"class": "sorcerer", "region": "nae", "game_patch": "", "source": "profile_lower_bound",
                                             "points": {"skill": 200, "stigma": 30, "daevanion": 360}, "skill_bonus": {"gear": {"Ice Chain": 1}}})]


def test_the_planner_catalog_offers_arcana_enhancement_to_plus_five():
    from pathlib import Path
    from aion2calc import build_drafts
    from aion2calc.kit.base import ClassData
    from aion2calc.plan import items as I
    catalog = json.loads((Path(build_drafts.__file__).parent / "app/static/build-catalog.json").read_text(encoding="utf-8"))
    assert catalog["arcana_max_enhance"] == 5
    arcana = [it for it in catalog["items"] if it["category"] in I.ARCANA_CATEGORIES]
    assert arcana and all(len(it["levels"]) == 6 and it["levels"][0] == it["levels"][5] for it in arcana)
    unique = next(it for it in arcana if it["grade"] == "Unique" and it["category"] == "Chalice")
    pool = catalog["arcana_pools"]["sorcerer"]["Arcana Chalice"]
    nine = {}
    for sk in pool["skills"]:
        if sum(nine.values()) >= 9:
            break
        nine[str(sk["id"])] = min(pool["max_level"], 9 - sum(nine.values()))
    doc = {"level": 45, "loadout": {"components": [{"slot": "Arcana Chalice", "catalog_slug": unique["slug"], "enchant": 5, "arcana_skills": nine}]}}
    assert sum(build_drafts.arcana_bonuses(doc, ClassData("sorcerer")).values()) == 9       # a Unique +5: nine options
    for enchant in (6, 4):                                                                   # past +5; nine options need +5
        doc["loadout"]["components"][0]["enchant"] = enchant
        with pytest.raises(ValueError):
            build_drafts.arcana_bonuses(doc, ClassData("sorcerer"))
