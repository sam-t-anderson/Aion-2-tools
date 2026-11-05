"""The bundled presets are optimized with each class's highest reported budgets (0.2.384): the skill, stigma and
Daevanion points and the bonus skill levels (gear rolls, arcana cards) the community server's contributors reported,
as its v2 preset policy gives them. ``optimize`` and ``compare`` take them with ``--reported-budgets``; an imported
character keeps its own points."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from aion2calc.__main__ import _run_budgets, compare_markdown
from aion2calc.combat import preset_sync

RESULTS = Path(__file__).resolve().parents[1] / "results"
CLASSES = ("assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer", "spiritmaster", "templar")
SORCERER = {"version": 2, "budgets": {"skill": 383, "stigma": 188, "daevanion": 417},
            "bonus": {"levels": 50, "per_skill": 6}}


def serve(monkeypatch, policy):
    """A community server whose preset policy is ``policy``; returns the paths asked for."""
    asked = []

    def request(base, path, body=None):
        asked.append(path)
        return policy
    monkeypatch.setattr(preset_sync, "_base", lambda: "https://community.test")
    monkeypatch.setattr(preset_sync, "_request", request)
    return asked


def test_the_reported_budgets_are_the_servers_preset_policy(monkeypatch):
    asked = serve(monkeypatch, SORCERER)
    assert preset_sync.reported_resources("sorcerer", "pvp") == (SORCERER["budgets"], SORCERER["bonus"])
    assert asked == ["/api/v2/presets/sorcerer/pvp/policy"]
    serve(monkeypatch, {"version": 2, "budgets": {"skill": 347, "stigma": 50, "daevanion": 305}})
    assert preset_sync.reported_resources("spiritmaster", "pve") == ({"skill": 347, "stigma": 50, "daevanion": 305}, None)


@pytest.mark.parametrize("policy", [
    {"version": 1, "budgets": {"skill": 203, "stigma": 30, "daevanion": 360}},      # a server before reported budgets
    {"version": 2, "budgets": {"skill": 383, "stigma": 188}},
    {"version": 2, "budgets": {"skill": 383, "stigma": -1, "daevanion": 417}},
    {"version": 2, "budgets": {"skill": 383, "stigma": 188.5, "daevanion": 417}},
    {**SORCERER, "bonus": {"levels": 0, "per_skill": 6}},
])
def test_a_policy_without_usable_budgets_is_refused(monkeypatch, policy):
    serve(monkeypatch, policy)
    with pytest.raises(ValueError):
        preset_sync.reported_resources("sorcerer", "pve")


def test_reported_budgets_need_a_server_and_a_known_class(monkeypatch):
    serve(monkeypatch, SORCERER)
    with pytest.raises(ValueError):
        preset_sync.reported_resources("../sorcerer", "pve")
    with pytest.raises(ValueError):
        preset_sync.reported_resources("sorcerer", "world")
    monkeypatch.setattr(preset_sync, "_base", lambda: "")
    with pytest.raises(ValueError):
        preset_sync.reported_resources("sorcerer", "pve")


def test_a_run_takes_the_points_given_or_the_reported_ones(monkeypatch):
    def args(**given):
        return SimpleNamespace(**{"skill_points": None, "stigma_points": None, "daevanion": None,
                                  "reported_budgets": False, **given})
    # nothing given: the level's own skill and stigma points, the global launch's 360 Daevanion, no bonus levels
    assert _run_budgets(args(), "sorcerer", "pve") == ({"skill": None, "stigma": None, "daevanion": 360}, None)
    assert _run_budgets(args(skill_points=383, daevanion=417), "sorcerer", "pve") == (
        {"skill": 383, "stigma": None, "daevanion": 417}, None)
    asked = serve(monkeypatch, SORCERER)
    assert _run_budgets(SimpleNamespace(reported_budgets=True), "sorcerer", "pvp") == (   # compare: no point options
        SORCERER["budgets"], SORCERER["bonus"])
    assert asked == ["/api/v2/presets/sorcerer/pvp/policy"]
    for given in ({"skill_points": 383}, {"stigma_points": 30}, {"daevanion": 360}):
        with pytest.raises(SystemExit):
            _run_budgets(args(reported_budgets=True, **given), "sorcerer", "pve")


def test_the_comparison_index_lists_each_classs_reported_budgets():
    rows = [("sorcerer", 30000.0, 25000.0, 0.8), ("spiritmaster", 20000.0, 19000.0, None)]
    budgets = {"sorcerer": (SORCERER["budgets"], SORCERER["bonus"]),
               "spiritmaster": ({"skill": 347, "stigma": 50, "daevanion": 305}, None)}
    md = compare_markdown(rows, "boss", 2, budgets)
    assert md.startswith("# Class comparison (boss, each class's reported budgets, 2 optimizer iterations per class)")
    assert "same budgets (203 SP" not in md and "the same points and bonus levels" in md
    assert ("| sorcerer | 30,000 | 25,000 | +20.0% | 80% | 383 / 188 / 417 | 50 (6) | [sorcerer](sorcerer/README.md) |"
            in md)
    assert "| spiritmaster | 20,000 | 19,000 | +5.3% | — | 347 / 50 / 305 | none reported |" in md
    # without them, every class had the same default budgets
    assert "same budgets (203 SP, 30 stigma points, 360 Daevanion)" in compare_markdown(rows, "boss", 2)


def _summary(*parts):
    return json.loads(RESULTS.joinpath(*parts, "build.json").read_text(encoding="utf-8"))


def _fits(summary, budgets, allowance):
    build = summary["build"]
    assert build["sp_spent"] <= budgets["skill"] and build["stigma_spent"] <= budgets["stigma"]
    assert build["daevanion_cost"] <= budgets["daevanion"]
    bonus = build.get("bonus") or {}
    assert not bonus or (allowance and sum(bonus.values()) <= allowance["levels"]
                         and max(bonus.values()) <= allowance["per_skill"])


def test_every_bundled_preset_has_its_classs_reported_budgets():
    """The class comparison's PvE builds, the Sorcerer example and the PvP builds: the presets the planner offers
    before a character is imported. Each class's PvE and PvP presets have the same points and bonus-level allowance,
    the ones the comparison index lists, and fit them."""
    index = (RESULTS / "compare" / "README.md").read_text(encoding="utf-8")
    for cls in CLASSES:
        pve, pvp = _summary("compare", cls), _summary("pvp", cls)
        budgets, allowance = pve["budgets"], pve.get("bonus_allowance")
        assert set(budgets) == {"skill", "stigma", "daevanion"} and budgets["stigma"] > 30, cls
        assert pvp["budgets"] == budgets and pvp["scoring_policy"]["budgets"] == budgets, cls
        assert pvp["scoring_policy"].get("bonus") == allowance and pvp["scoring_policy"]["version"] == 2, cls
        listed = (f"{budgets['skill']} / {budgets['stigma']} / {budgets['daevanion']} | "
                  + (f"{allowance['levels']} ({allowance['per_skill']})" if allowance else "none reported"))
        assert re.search(rf"^\| {cls} \|.* \| {re.escape(listed)} \| \[{cls}\]", index, re.M), cls
        _fits(pve, budgets, allowance)
        _fits(pvp, budgets, allowance)
    example, compared = _summary("sorcerer_l45"), _summary("compare", "sorcerer")
    assert {k: example["budgets"][k] for k in compared["budgets"]} == compared["budgets"]
    assert example.get("bonus_allowance") == compared.get("bonus_allowance")
    _fits(example, compared["budgets"], compared.get("bonus_allowance"))


def test_a_bundled_pve_preset_is_a_valid_candidate_under_its_policy():
    """What a community server does when it seeds its comparison from the bundled builds: each is a legal candidate
    under the reported budgets and bonus allowance, and scores."""
    from aion2calc.canonical_presets import candidate, evaluate, scoring_policy
    for parts in (("sorcerer_l45",), ("compare", "spiritmaster"), ("compare", "gladiator")):
        summary = _summary(*parts)
        budgets = {k: summary["budgets"][k] for k in ("skill", "stigma", "daevanion")}
        allowance = summary.get("bonus_allowance")
        scored = evaluate(candidate(summary, scoring_policy(summary["class"], "pve", budgets, allowance)),
                          budgets, allowance)
        assert scored["score"] > 0 and scored["build"]["bonus"] == (summary["build"].get("bonus") or {}), parts


def test_a_pvp_priority_keeps_to_the_pvp_kit():
    """A PvP build's priority was searched with the PvP kit, so reading it back adds none of the PvE kit's essential
    actions. The Templar's Punishing Strike is not in the PvP kit: added to the bundled Templar PvP preset's priority, it
    made the preset fail validation (0.2.384)."""
    from aion2calc.canonical_presets import candidate, evaluate, scoring_policy
    from aion2calc.report import build_from_summary
    summary = {"class": "templar", "level": 45, "policy": ["judgment", "pummel"],
               "build": {"sp": {}, "stigmas": {}, "specs": {}, "daevanion_nodes": []}}
    assert build_from_summary({**summary, "scenario": "boss"})[1] == ["punishing_strike", "judgment", "pummel"]
    assert build_from_summary({**summary, "scenario": "pvp"})[1] == ["judgment", "pummel"]
    preset = _summary("pvp", "templar")
    policy = scoring_policy("templar", "pvp", preset["budgets"], preset["scoring_policy"].get("bonus"))
    assert evaluate(candidate(preset, policy), preset["budgets"], policy.get("bonus"))["score"] > 0
