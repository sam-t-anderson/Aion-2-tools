"""The README.md written next to every optimized build (aion2calc/report_md.py). Each section shows the
build's own numbers. The optional sections appear only when the run used them, and show its assumptions
as they were entered: the HP reserve, the action-time pauses, trained-skill reserves, Genus lines and the
point budgets' provenance. Names a player typed cannot break a table."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aion2calc.report_md import write_markdown

ROOT = Path(__file__).resolve().parents[1]
DEFIANCE, DEFIANCE_HEAL = 15240000, 15240030


@pytest.fixture(scope="module")
def summary():
    return json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sorcerer(summary):
    from aion2calc.kit.base import ClassData
    from aion2calc.model.character import load_loadout
    from aion2calc.report import build_from_summary
    build, policy = build_from_summary(summary)
    return SimpleNamespace(cd=ClassData("sorcerer"), build=build, policy=policy, loadout=load_loadout(summary["loadout"]))


def render(summary, tmp_path, extra=None):
    path = write_markdown(summary, str(tmp_path), extra)
    assert path == str(tmp_path / "README.md")
    return Path(path).read_text(encoding="utf-8")


def lines(text):
    return [line for line in text.splitlines() if line.strip()]


def test_a_build_report_shows_the_builds_own_numbers(summary, tmp_path):
    text = render(summary, tmp_path, {"gear_lines": ["Main hand: Rupture Tome +10"], "loadout_name": "Test loadout",
                                      "weapon_compare": [{"name": "Ludra's Grimoire", "dps": 21000.4, "gain": -0.012}]})
    assert text.startswith(f"# Sorcerer — level {summary['level']} global build, rotation and macro\n")
    scen, other = summary["scenario"], next(k for k in summary["dps"] if k != summary["scenario"])
    assert f"| **Optimized (this report)** | **{summary['dps'][scen]:,.0f}** | **{summary['dps'][other]:,.0f}** |" in text
    gain = summary["dps"][scen] / summary["baseline"]["community_optimized_rotation"] - 1
    assert f"**{100 * gain:+.1f}%** over the typical top global build" in text
    for number, entry in enumerate(summary["policy"], 1):
        assert f"{number}. `{entry}`" in text                              # the priority list, in order
    macro = summary["macro"]
    assert f"reaches **{100 * macro['dps_macro'] / macro['dps_priority']:.1f}%** of the ideal priority list" in text
    assert text.count("\n| ") >= len(macro["steps"])
    build = summary["build"]
    for stigma, level in build["stigmas"].items():
        assert f"{stigma} Lv {level}" in text and f"| {stigma} |" not in text   # stigmas listed apart from trained skills
    assert f"Daevanion **{build['daevanion_cost']} / {summary['daevanion_budget']}**" in text
    assert summary["links"]["metabot_daevanion"] in text
    for row in summary["weights"]:
        assert f"| {row['label']} | {row['pct']:+.2f}% |" in text
    assert "Loadout: **Test loadout**" in text and "* Main hand: Rupture Tome +10" in text
    assert "| Ludra's Grimoire | 21,000 | -1.2% |" in text
    assert f"## Damage objective: {summary['objective']['label']}" in text
    for absent in ("## HP reserve", "## Outgoing action-time assumptions", "## Trained skill reserves",
                   "## Pet Genus Insight", "## Point budget provenance"):
        assert absent not in text                                          # this run used none of them


def hp_reserve(sorcerer):
    """An HP reserve as the optimizer reports it: an entered scenario with a linked Defiance, a fight recorded
    by the meter and a saved PvP benchmark, assessed on the build."""
    from aion2calc.opt import survival as SV
    from test_survival_planning import fight_log, pvp_result
    entered = {"name": "Boss slam | phase\n2", "burst_damage": 6000, "pressure_dps": 1000, "window_s": 20,
               "healing_hps": 200, "healing_delay_s": 2, "healing_duration_s": 3, "reserve_hp": 500,
               "reductions": [{"name": "Defiance", "delay_s": 0, "duration_s": 4, "reduction_pct": 50, "skill_id": DEFIANCE,
                               "effect_id": DEFIANCE_HEAL, "min_trained": 5, "cooldown_s": 12},
                              {"name": "Defiance", "delay_s": 12, "duration_s": 4, "reduction_pct": 50, "skill_id": DEFIANCE,
                               "cooldown_s": 12},
                              {"name": "Sidestep", "kind": "movement", "delay_s": 6, "duration_s": 1, "reduction_pct": 100}]}
    recorded = SV.recorded_pressure(fight_log(), 0, "tank", 2)["scenario"]
    benchmark = SV.opponent_pressure(pvp_result(), "pvp", 0.5, 5, "timed")["scenario"]
    plan = SV.prepare(sorcerer.cd, sorcerer.build, {"current_hp": 30000, "opponents": [entered, recorded, benchmark]})
    return plan, SV.assessment(sorcerer.cd, sorcerer.build, plan)


def test_an_hp_reserve_report_shows_the_assumptions_the_build_was_optimized_under(summary, sorcerer, tmp_path):
    plan, survival = hp_reserve(sorcerer)
    text = render({**summary, "survival": survival}, tmp_path)
    assert (f"Crystal-board HP: {survival['selected_node_hp']:,.0f}; minimum {survival['minimum_node_hp']:,.0f}; "
            f"previous {survival['reference_node_hp']:,.0f}.") in text
    slam = survival["opponents"][0]
    assert f"| Boss slam  /  phase 2 | {slam['required_hp']:,.0f} | {slam['headroom_hp']:,.0f} |" in text   # a typed | or newline stays in its cell
    assert "Strictest incoming requirement: Boss slam | phase 2." in text
    assert "- Timed expected hits: 6; scaled damage 6,500; source 6.0–11.0s. Complete hit schedule retained in build JSON." in text
    assert (f"- Boss slam | phase 2: assumed HPS 200; delay 2s; duration 3s; peak ongoing pressure "
            f"{slam['peak_pressure_hp']:,.0f} HP at 20s.") in lines(text)
    effect = sorcerer.cd.skills[DEFIANCE]["specs"][2]["text"]
    reductions = lines(text)[lines(text).index(
        f"- Boss slam | phase 2, same healing without added reductions: {slam['unprotected_required_hp']:,.0f} HP required; "
        f"assumed reduction {slam['assumed_requirement_reduction_hp']:,.0f} HP. Initial hit unchanged; strongest overlap only."):][1:7]
    assert reductions == ["  - Defiance (defensive): assumed 50% pressure reduction from 0s to 4s.",
                          f"    Retained skill: Defiance (trained minimum 5); supporting effect: {effect}.",
                          "  - Defiance (defensive): assumed 50% pressure reduction from 12s to 16s.",
                          "    Retained skill: Defiance (trained minimum 1).",
                          "  - Sidestep (movement): assumed 100% pressure reduction from 6s to 7s.",
                          "    Unlinked timing assumption."]
    assert ("- Boss slam | phase 2 / Defiance: starts 0s, 12s; Assumed effective cooldown 12s; shortest reuse gap 12s; "
            "assumed spacing satisfied.") in lines(text)
    assert "Imported recording context (editable assumption): title: Practice pull; recipient: Tank;" in text
    assert "Optimized opponent benchmark (editable pressure assumption, not measured incoming damage): title: Assassin duel;" in text
    assert text.count("DPS is optimized subject to this reserve.") == 1


def test_action_time_pauses_are_reported_per_damage_scenario_with_their_reservations(summary, sorcerer, tmp_path):
    from aion2calc.opt import survival as SV
    from aion2calc.report import _sim
    from aion2calc.scenarios import SCENARIOS
    hellfire = sorcerer.cd.by_name["Hellfire"]["id"]
    plan = SV.prepare(sorcerer.cd, sorcerer.build, {"preserve_hp": False, "action_windows": [
        {"name": "Dodge the\nwave", "start_s": 10, "duration_s": 3},
        {"name": "Hold Hellfire", "start_s": 60, "duration_s": 1, "skill_id": hellfire, "cooldown_s": 30, "reserve_cooldown": True},
        {"name": "Hold Defiance", "start_s": 90, "duration_s": 1, "skill_id": DEFIANCE, "cooldown_s": 20, "reserve_cooldown": True,
         "effect_id": DEFIANCE_HEAL}]})
    scenarios = {name: SV.with_action_timing(SCENARIOS[name](sorcerer.loadout), plan) for name in ("boss", "dummy")}
    results = {name: _sim(sorcerer.build, scenario, sorcerer.policy)[0] for name, scenario in scenarios.items()}
    text = render({**summary, "action_timing": SV.action_timing_summary(plan, scenarios, results)}, tmp_path)
    section = lines(text)[lines(text).index("## Outgoing action-time assumptions"):]
    effect = sorcerer.cd.skills[DEFIANCE]["specs"][2]["text"]
    assert section[2:10] == ["- Dodge the wave: 10–13s.", "  Unlinked timing assumption.",
                             "- Hold Hellfire: 60–61s.", "  Rotation cooldown reservation requested.",
                             "  Requested retention: Hellfire (trained minimum 1).",
                             "- Hold Defiance: 90–91s.", "  Rotation cooldown reservation requested.",
                             f"  Requested retention: Defiance (trained minimum 1); supporting effect: {effect}."]
    boss = section.index("- boss: 5s unavailable for new actions in 180s; clipped interval union "
                         "[(10.0, 13.0), (60.0, 61.0), (90.0, 91.0)].")
    assert section[boss + 1:boss + 5] == [
        "  - Hellfire: starts 60s; Assumed effective cooldown 30s; assumed spacing satisfied; no repeated assumed use.",
        "  - Defiance: starts 90s; Assumed effective cooldown 20s; assumed spacing satisfied; no repeated assumed use.",
        f"  - Skill #{hellfire}: assumed use 60s; entered cooldown 30s; Reserved in modeled groups hellfire; "
        "matching actions: hellfire_c1, hellfire_c2, hellfire_c3.",
        f"  - Skill #{DEFIANCE}: assumed use 90s; entered cooldown 20s; Unavailable: no matching modeled action; "
        "no rotation cooldown reserved."]
    assert section[boss + 5].startswith("- dummy: 5s unavailable")        # each damage scenario has its own clock


def test_trained_skill_reserves_genus_lines_and_point_budgets_are_reported(summary, sorcerer, tmp_path):
    from aion2calc.opt.genus import assess, prepare as prepare_genus
    from aion2calc.opt.reserves import describe, include_survival
    from aion2calc.scenarios import SCENARIOS
    plan, survival = hp_reserve(sorcerer)
    reserves = describe(sorcerer.cd, sorcerer.build, include_survival(sorcerer.cd, None, plan, summary["budgets"]))
    genus = assess(prepare_genus({"Fera": {"level": 2, "lines": [{"slot": 1, "stat": "Fera Attack", "value": "30"},
                                                                  {"slot": 2, "stat": "Max Attack", "value": "10"}]}},
                                 "pve", {"mix": {"Fera": 3, "Natura": 1}}),
                   sorcerer.build, SCENARIOS["boss"](sorcerer.loadout), sorcerer.policy)
    progression = {"note": "Remaining points are the selected budget minus observed spend.", "resources": [
        {"resource": "skill", "observed_spent": 180, "available_assumption": 203, "assumed_unspent": 23,
         "source": "Level-based example / observed minimum", "verified_maximum": None}]}
    report = copy.deepcopy(summary) | {"skill_reserves": reserves, "genus": genus, "progression": progression,
                                       "model_note": "Stationary boss target."}
    text = render(report, tmp_path)
    defiance = next(row for row in reserves["skills"] if row["id"] == DEFIANCE)
    assert f"| Defiance | 5 | {defiance['selected']} |" in text
    assert ("Reserve met." if reserves["met"] else "Reserve not met.") in text
    assert any(line.startswith("- Reserved supporting effect: Defiance · ") for line in text.splitlines())
    assert "Saved manual lines included." in text and "User-assumed enemy mix: Fera 75.0%, Natura 25.0%" in text
    fera, max_attack = genus["lines"]
    assert f"| Fera / 1 | Fera Attack | 30 | {fera['gain']:.2%} | Included |" in text
    assert f"| Fera / 2 | Max Attack | 10 | — | {max_attack['reason']} |" in text
    assert "| skill | 180 | 203 | 23 | Level-based example / observed minimum | Unknown |" in text
    assert "Stationary boss target." in text
    off = assess(prepare_genus({}, "pve", {"enabled": False}), sorcerer.build, SCENARIOS["boss"](sorcerer.loadout), sorcerer.policy)
    assert "Genus scoring disabled." in render({**summary, "genus": off}, tmp_path)
