"""The in-game Skill Macro presses hotbar keys, and a hotbar key holds up to four skills. Since 0.2.371 the macro is
built from such keys, the basic auto-attack stays on the held left mouse button, and the layout of one skill per
line is the alternative. The macro, held, casts a key's skills from first to last, each that can be cast, then moves
to the next line (0.2.377): the planner had a key cast only the first of its skills that was ready, so a key on two
lines in a row looked as if it cast two of them, where the game's macro casts them all on the first."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aion2calc.app import views
from aion2calc.kit.base import Build, ClassData
from aion2calc.opt.macro import MODEL_VERSION, STACK, MacroPolicy, _stacked, describe_plan, plan_macro
from aion2calc.run import Scenario, prepare
from aion2calc.sim.engine import Sim

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def templar():
    scen = Scenario(loadout="templar_l45_global_median")
    _, _, kit, stats = prepare(Build("templar"), scen)
    return scen, kit, stats.derived()


def _run(templar, policy):
    scen, kit, d = templar
    return Sim(d, kit.actions, policy, scen.target, scen.config, hooks=kit.hooks, cond_mods=kit.cond_mods).run()


def _pressed(lines, ready, n):
    """The first ``n`` skills the macro casts, with ``ready`` the skills that can be cast."""
    sim = SimpleNamespace(actions={k: SimpleNamespace(key=k, chain_of=None, requires_charge=False)
                                   for line in lines for k in line}, usable=lambda a: a.key in ready)
    policy = MacroPolicy([], lines)
    return [policy(sim).key for _ in range(n)]


def test_a_key_casts_its_skills_first_to_last_before_the_next_line():
    lines = [("a", "b", "c"), ("d",)]
    assert _pressed(lines, set("abcd"), 6) == ["a", "b", "c", "d", "a", "b"]
    assert _pressed(lines, set("acd"), 4) == ["a", "c", "d", "a"]               # one that cannot be cast is skipped
    assert _pressed([("a", "b"), ("a", "b"), ("c",)], set("abc"), 5) == ["a", "b", "a", "b", "c"]   # a key twice


def test_a_key_on_the_next_line_again_casts_nothing_more(templar):
    """The reported macro put one key on two lines in a row: the macro has cast its skills on the first, so the second
    finds them cooling down and adds nothing."""
    key = ("shield_smite", "warding_strike")
    once = _run(templar, MacroPolicy([], [key], fallback="vicious_strike"))
    twice = _run(templar, MacroPolicy([], [key, key], fallback="vicious_strike"))
    assert once.casts["shield_smite"] > 10 and once.casts.get("warding_strike")
    assert twice.casts == once.casts and twice.dps == pytest.approx(once.dps)
    # the basic attack first on a key no longer shuts out the skills after it, as a priority stack would
    basic_first = _run(templar, MacroPolicy([], [("vicious_strike", "shield_smite")]))
    assert basic_first.casts.get("shield_smite", 0) > 10


def test_the_held_auto_attack_fills_in_when_no_key_has_a_skill_ready(templar):
    held = _run(templar, MacroPolicy([], [("shield_smite",)], fallback="vicious_strike"))
    alone = _run(templar, MacroPolicy([], [("shield_smite",)]))
    assert held.casts.get("vicious_strike") and not alone.casts.get("vicious_strike")
    assert held.dps > alone.dps


@pytest.fixture(scope="module")
def plan(templar):
    scen, kit, d = templar
    return plan_macro(d, kit, list(kit.policy), scen.target, scen.config, evals=800)


def test_the_templars_macro_is_built_from_hotbar_keys(templar, plan):
    _, kit, _ = templar
    keys = list(dict.fromkeys(plan.macro_steps))
    assert keys and all(isinstance(k, tuple) and 1 <= len(k) <= STACK for k in keys)
    placed = [s for k in keys for s in k]
    assert len(placed) == len(set(placed))                           # a skill sits on one key only
    assert all(sum(kit.actions[s].is_filler for s in k) <= 1 and
               all(not kit.actions[s].is_filler for s in k[:-1]) for k in keys)   # a filler only on top
    assert plan.auto_attack == "vicious_strike"                      # held on the left mouse button
    assert all(len(k) == 1 for k in keys if "vicious_strike" in k)   # ... and if on a line, never stacked
    assert "punishing_strike" not in placed                          # Pummel's key presses its chain step
    manual = [m[0] if isinstance(m, tuple) else m for m in plan.manual]
    assert "punishment" in manual                                    # a charge skill: a macro only taps it
    assert all(kit.actions[m].requires_charge or (kit.actions[m].cooldown or 0) >= 30 for m in manual)
    assert "judgment" in placed
    # beats the best layout of one skill per line (by 1.03 % in 0.2.377 and 0.97 % in 0.2.378, whose search takes
    # another path through the smaller set of layouts with no key on two lines in a row)
    assert plan.dps_macro > plan.dps_alt
    assert all(isinstance(st, str) for st in plan.alt_steps)


def test_the_plan_saves_and_shows_its_keys(templar, plan):
    doc = json.loads(json.dumps(describe_plan(plan)))
    assert doc["model_version"] == MODEL_VERSION == 5
    assert all(isinstance(st, list) for st in doc["steps"]) and doc["steps"] == [list(k) for k in plan.macro_steps]
    view = views.rotation_view(ClassData("templar"), Build("templar"), {},
                               {"scenario": "boss", "policy": list(templar[1].policy), "macro": doc})
    steps = view["rotation"]["steps"]
    assert [[s["key"] for s in st["stack"]] for st in steps] == doc["steps"]
    for st in steps:                                                 # one hotbar key per stack, shared by its skills
        assert {s["binding"] for s in st["stack"]} == {st["binding"]} and st["binding"] != "Assign key"
        assert (st["binding"] == "LMB") == ([s["key"] for s in st["stack"]] == ["vicious_strike"])
    lines = {tuple(st) for st in doc["steps"]}
    keys = {st["binding"] for st in steps}
    assert len(keys) == len(lines)                                   # a key on two lines keeps its one binding
    stacks = [s for s in view["hotbar"]["slots"] if s.get("stack")]
    assert sorted(s["binding"] for s in stacks) == sorted(keys - {"LMB"})
    assert next(s for s in view["hotbar"]["slots"] if s["key"] == "punishment")["manual"]


def test_the_basic_attack_may_keep_a_line_of_its_own(templar):
    """The basic attack is held on the left mouse button, and a line of its own presses it even while a key has a
    skill ready, as the layouts of one skill per line did: a geared Sorcerer's Flame Arrow restores the MP its keys
    run short of. The search adds such a line when it plays better, and never stacks the basic attack on a key."""
    _, kit, _ = templar

    def run(pol):                                   # a stand-in for the simulation: the basic attack's line pays 5 %
        return 100.0 * (1.05 if ("vicious_strike",) in [tuple(line) for line in pol.steps] else 1.0)
    lines, _, dps = _stacked(run, kit, list(kit.policy), "vicious_strike", [], evals=5000)
    assert ("vicious_strike",) in lines and dps == pytest.approx(105.0)
    assert all(line == ("vicious_strike",) for line in lines if "vicious_strike" in line)


def test_no_key_sits_on_two_lines_in_a_row(templar):
    """A key on the line straight after its own casts nothing more (0.2.377): its skills cool down from the line
    before, and one without a cooldown runs again anyway each time the held macro comes back to the key (0.2.378).
    A stand-in simulation that pays for every such pair, the loop's last and first lines included, gets none, not even
    of the basic attack's own line, always ready."""
    _, kit, _ = templar

    def pairs(lines):
        lines = [tuple(line) for line in lines]
        return [a for a, b in zip(lines, lines[1:] + lines[:1]) if a == b] if len(lines) > 1 else []

    def run(pol):
        return 100.0 * (1 + 0.01 * len(pairs(pol.steps)) + 0.05 * (("vicious_strike",) in map(tuple, pol.steps)))
    lines, _, _ = _stacked(run, kit, list(kit.policy), "vicious_strike", [], evals=3000)
    assert ("vicious_strike",) in lines and not pairs(lines)


def test_a_saved_one_skill_per_line_macro_still_shows():
    summary = {"scenario": "boss", "policy": ["judgment", "pummel", "vicious_strike"],
               "macro": {"model_version": 3, "steps": ["judgment", "pummel", "vicious_strike"], "manual": []}}
    view = views.rotation_view(ClassData("templar"), Build("templar"), {}, summary)
    assert [s["key"] for s in view["rotation"]["steps"]] == ["judgment", "pummel", "vicious_strike"]
    assert all("stack" not in s for s in view["rotation"]["steps"]) and view["macro"]["needs_refresh"]


def test_the_readme_lists_each_lines_key(tmp_path):
    from aion2calc.report_md import write_markdown
    summary = copy.deepcopy(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))
    summary["macro"].update(model_version=MODEL_VERSION, auto_attack="flame_arrow",
                            steps=[["blaze", "frost"], ["hellfire"], ["flame_arrow"]])
    text = Path(write_markdown(summary, str(tmp_path), None)).read_text(encoding="utf-8")
    assert "| 1 | blaze › frost |" in text and "| 2 | hellfire |" in text
    assert "| 3 | flame_arrow (the basic attack, on the left mouse button) |" in text
    assert "Hotbar key holds (cast in this order)" in text and "a key listed twice added twice" in text
    assert "The macro casts a key's skills from first to last, skipping any that cannot be cast" in text


def test_the_readme_lists_a_repeated_keys_skills_on_each_of_its_lines(tmp_path):
    """A key the search put on two lines is pressed twice per round: each line lists the skills its key holds, with no
    note that it repeats an earlier line (0.2.387; 0.2.376 named the earlier line instead)."""
    from aion2calc.report_md import write_markdown
    summary = copy.deepcopy(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))
    summary["macro"].update(model_version=MODEL_VERSION, auto_attack="flame_arrow",
                            steps=[["blaze"], ["cold_storm", "firestorm", "frost"], ["cold_storm", "firestorm", "frost"]])
    text = Path(write_markdown(summary, str(tmp_path), None)).read_text(encoding="utf-8")
    assert "| 2 | cold_storm › firestorm › frost |" in text
    assert "| 3 | cold_storm › firestorm › frost |" in text
    assert "pressed again" not in text and "tried twice" not in text
