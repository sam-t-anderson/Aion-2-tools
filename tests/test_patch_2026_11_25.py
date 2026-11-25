"""The 25 November 2026 patch notes (0.2.510), applied to the bundled global class data and the damage model:

* every class equips up to five stigmas, the fifth at level 45 (the notes do not say at which level it opens);
* Ranger: Marking Shot's Lv 8 specialization gives +10 % Perfect Chance (+5 % before); Bow of Blessing's cooldown is
  1 min 30 s (2 min before);
* Chanter: Incandescent Blow's (and its chain Bursting Blow's) and Spinning Strike's Lv 16 specializations no longer
  ignore Block and Evasion: they land as a Multi-Hit, and as a Critical Hit;
* Spiritmaster: Cold Shock's Lv 12 specialization gives +10 % Attack in one stack (+2 % a stack, up to five, before);
  Element Unification's Critical Damage is 5.5 % at level 1, +0.5 % a level, in one stack (1.1 %, +0.1 %, up to five).

A refresh of the class data from a source that has not caught up with the patch would undo these: these tests say so.
"""
import itertools
import json
from pathlib import Path

import pytest

from aion2calc.kit.base import ClassData, stigma_points_to_reach
from aion2calc.opt.pipeline import Optimizer, stigma_patterns
from aion2calc.run import prepare
from aion2calc.scenarios import SCENARIOS, typical_build

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer", "spiritmaster", "templar")
CATALOG = json.loads((ROOT / "aion2calc" / "app" / "static" / "build-catalog.json").read_text(encoding="utf-8"))


def _skill(cd: ClassData, name: str) -> dict:
    return cd.skills[cd.by_name[name]["id"]]


class _Sim:
    """What a kit's cast does: its hits and their tags, and the buffs it puts up."""

    def __init__(self):
        self.t, self.hits, self.buffs, self.kit_state = 0.0, [], {}, {}

    def hit(self, source, flat, coef, **kwargs):
        if not source.endswith("(woven)"):                     # the basic attacks woven after it, not its own
            self.hits.append((source, tuple(kwargs.get("tags") or ())))

    def buff(self, name, duration, stats=None, t=None):
        self.buffs[name] = dict(stats or {})

    def proc(self, key, chance, icd, t):
        return True

    def reduce_cd(self, group, seconds):
        pass

    def gain_mp(self, amount):
        pass


def _kit(cls: str, specs: dict[str, tuple[int, ...]], passives: dict[str, int] | None = None):
    """A level-45 build of ``cls`` with the named skills at level 16 (every specialization open) and ``specs``."""
    cd = ClassData(cls)
    build = typical_build(cls)
    for name, chosen in specs.items():
        sid = cd.by_name[name]["id"]
        build.sp[sid], build.bonus[sid] = 10, 6
        build.specs[sid] = tuple(sid + 10 * n for n in chosen)
    for name, level in (passives or {}).items():
        sid = cd.by_name[name]["id"]
        build.sp[sid], build.bonus[sid] = min(10, level), max(0, level - 10)
    _cd, _build, kit, _stats = prepare(build, SCENARIOS["boss"](f"{cls}_l45_global_median"))
    return cd, kit


def test_every_class_equips_five_stigmas_at_level_45():
    for cls in CLASSES:
        cd = ClassData(cls)
        assert cd.raw["stigma_slot_levels"] == [22, 27, 32, 37, 45]
        assert cd.budget(45)["slots"] == 5 and cd.budget(44)["slots"] == 4 and cd.budget(37)["slots"] == 4
        assert [row["slots"] for row in CATALOG["classes"][cls]["budget"] if row["level"] in (44, 45)] == [4, 5]


def test_the_rangers_marking_shot_and_bow_of_blessing():
    cd = ClassData("ranger")
    assert set(_skill(cd, "Bow of Blessing")["cd"]) == {90}                   # every level: 1 min 30 s
    assert _skill(cd, "Marking Shot")["specs"][0]["text"] == "+10% Perfect Chance for the duration"
    _cd, kit = _kit("ranger", {"Marking Shot": (1, 3, 5)})
    sim = _Sim()
    kit.actions["marking_shot"].on_cast(sim, kit.actions["marking_shot"])
    assert sim.buffs["precision"]["perfect"] == pytest.approx(0.10)
    assert sim.hits == [("Marking Shot", ("crit", "noparry"))]               # its Lv 16 option is as it was


def test_the_chanters_blows_and_spinning_strike_no_longer_ignore_block_and_evasion():
    cd = ClassData("chanter")
    assert _skill(cd, "Incandescent Blow")["specs"][4]["text"] == "Lands as Multi-Hit"
    assert _skill(cd, "Spinning Strike")["specs"][4]["text"] == "Lands as a Critical Hit"
    _cd, kit = _kit("chanter", {"Incandescent Blow": (1, 3, 5), "Spinning Strike": (1, 3, 5)})
    sim = _Sim()
    kit.actions["incandescent_blow"].on_cast(sim, kit.actions["incandescent_blow"])
    kit.actions["spinning_strike"].on_cast(sim, kit.actions["spinning_strike"])
    assert sim.hits == [("Incandescent Blow", ("multi",)), ("Bursting Blow", ("multi",)),
                        ("Spinning Strike", ("crit",))]
    texts = {(row["name"], spec["text"]) for row in CATALOG["classes"]["chanter"]["skills"] for spec in row["specs"]}
    assert ("Incandescent Blow", "Lands as Multi-Hit") in texts and ("Spinning Strike", "Lands as a Critical Hit") in texts


def test_the_spiritmasters_element_unification_is_one_stack_of_five_times_the_value():
    cd = ClassData("spiritmaster")
    eu = _skill(cd, "Element Unification")
    assert [row[0] for row in eu["vals"][:3]] == [5.5, 6, 6.5] and eu["vals"][-1][0] == 25
    assert all(row[0] == pytest.approx(5.5 + 0.5 * i) for i, row in enumerate(eu["vals"]))
    assert "Stacks" not in eu["tip"]
    assert _skill(cd, "Cold Shock")["specs"][3]["text"] == "+10% Attack on landing [Earth Tremor]"
    # one stack of the new value is what the model held of five stacks of the old: from level 1 to 20, the five stacks
    # of 1.1 % to 3.0 % rose 9.5 points, as one of 5.5 % to 15 % does
    _cd, first = _kit("spiritmaster", {}, {"Element Unification": 1})
    _cd, twentieth = _kit("spiritmaster", {}, {"Element Unification": 20})
    assert twentieth.static["crit_dmg"] - first.static["crit_dmg"] == pytest.approx(5 * (0.1 * 19) / 100)


def test_the_stigma_patterns_are_the_same_unordered_and_fill_a_fifth_slot():
    def ordered(slots, points):                                    # the search before 0.2.510
        levels = sorted({1, 3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20})
        found = [lv for lv in itertools.product(levels, repeat=slots)
                 if sum(stigma_points_to_reach(level) for level in lv) <= points]
        spent = lambda p: sum(stigma_points_to_reach(level) for level in p)              # noqa: E731
        return sorted({tuple(sorted(p, reverse=True)) for p in found
                       if all(level >= 20 or spent(p) - stigma_points_to_reach(level)
                              + stigma_points_to_reach(level + 1) > points for level in p)})
    for points in (12, 30, 75):
        assert stigma_patterns(4, points) == ordered(4, points)
    five = stigma_patterns(5, 30)
    assert five and all(len(p) == 5 and sum(stigma_points_to_reach(level) for level in p) <= 30 for p in five)


def test_the_stigma_search_also_leaves_the_fifth_slot_empty(monkeypatch):
    tried = []

    def search(self, build, policy, cands, slots, patterns, best_b, best):
        tried.append(slots)
        return best_b, best
    monkeypatch.setattr(Optimizer, "_search_stigmas", search)
    monkeypatch.setattr(Optimizer, "evaluate", lambda self, build, policy: 1.0)
    scenario = SCENARIOS["boss"]("sorcerer_l45_global_median")
    opt = Optimizer("sorcerer", scenario, verbose=False)
    opt.optimize_stigmas(typical_build("sorcerer"), [])
    assert opt.stigma_slots == 5 and tried == [5, 4]                # five stigmas, and four with the fifth slot empty
    tried.clear()
    young = Optimizer("sorcerer", scenario, verbose=False, level=40)
    young.optimize_stigmas(typical_build("sorcerer", level=40), [])
    assert young.stigma_slots == 4 and tried == [4]                 # four slots: searched as before


def test_the_typical_build_wears_as_many_stigmas_as_the_top_players(monkeypatch):
    """Four, as the top players' picks (from before the patch) add up to: a fifth most-picked stigma would stand in
    for what they will wear in the fifth slot. Once their picks add up to five, five."""
    for cls in CLASSES:
        assert len(typical_build(cls).stigmas) == 4, cls
    cd = ClassData("ranger")
    picks = {name: dict(row) for name, row in cd.raw["top_players"]["stigmas"].items()}
    for row in picks.values():
        row["pick"] = row["pick"] * 5 / 4                              # each player wears five
    raw = dict(cd.raw, top_players=dict(cd.raw["top_players"], stigmas=picks))
    original = ClassData.__init__

    def init(self, cls, *args, **kwargs):
        original(self, cls, *args, **kwargs)
        if cls == "ranger":
            self.raw = raw
    monkeypatch.setattr(ClassData, "__init__", init)
    assert len(typical_build("ranger").stigmas) == 5
