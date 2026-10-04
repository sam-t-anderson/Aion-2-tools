"""What the planners optimize against: a class, a build, a rotation and a loadout.

``PlanContext.dps(choice)`` swaps inventory entries into the loadout and
simulates the fight (about 15 ms), so every planner compares real simulated DPS
rather than linear stat weights.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..kit.base import Build
from ..model.character import load_loadout
from . import items as I
from .inventory import entry_stats

#: median-loadout components and the planner slots they stand for
MEDIAN_GROUPS = {
    "Main hand": ["MainHand"], "Off-hand": ["SubHand"],
    "Armor x7": ["Helmet", "Torso", "Shoulder", "Gloves", "Pants", "Boots", "Cape"],
    "Necklace": ["Necklace"], "Earrings x2": ["Earring1", "Earring2"], "Rings x2": ["Ring1", "Ring2"],
    "Accessory rolls": ["Necklace", "Earring1", "Earring2", "Ring1", "Ring2"],
    "Bracelets x2": ["Bracelet1", "Bracelet2"], "Amulet": ["Amulet"], "Rune": ["Rune1", "Rune2"],
    "Arcana x5": list(I.ARCANA_SLOTS),
}
PROFILE_DEITY = "Primary/deity stats"
GEAR_SKILLS = "Gear skill rolls"


@dataclass
class PlanContext:
    cls: str
    build: Build
    policy: list
    loadout: dict
    scenario: str = "boss"
    level: int = 45
    character: dict | None = None
    equipped: dict = field(default_factory=dict)      # planner slot -> equipped inventory entry
    weights: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------ building
    @classmethod
    def from_summary(cls_, summary: dict, scenario: str = "boss") -> "PlanContext":
        from ..report import build_from_summary
        build, policy = build_from_summary(summary)
        lo = load_loadout(summary["loadout"]) if summary.get("loadout") else load_loadout(
            f"{summary['class']}_l45_global_median")
        return cls_(summary["class"], build, policy, lo, scenario, summary.get("level", 45),
                    weights=summary.get("weights") or [])

    @classmethod
    def from_result(cls_, path: str | Path, scenario: str = "boss") -> "PlanContext":
        summary = json.loads((Path(path) / "build.json").read_text(encoding="utf-8"))
        return cls_.from_summary(summary, scenario)

    @classmethod
    def for_class(cls_, cls: str, scenario: str = "boss") -> "PlanContext":
        """The class's optimized report (user runs first, then the bundled results)."""
        from ..app.views import result_roots
        for root in result_roots():
            for p in (root / f"{cls}_l45", root / "compare" / cls):
                if (p / "build.json").exists():
                    return cls_.from_result(p, scenario)
        raise FileNotFoundError(f"no optimized build for {cls}; run `python -m aion2calc optimize {cls}`")

    @classmethod
    def from_character(cls_, imp, inv: dict, evaluation: dict | None = None,
                       scenario: str = "boss") -> "PlanContext":
        """An imported character: its gear and points, best specs for its levels,
        the class's optimized priority list."""
        from ..charopt import evaluate_current
        ev = evaluation or evaluate_current(imp, scenario)
        b = imp.build.copy()
        b.bonus = {}
        from ..kit.base import ClassData
        cd = ClassData(imp.cls)
        for name, texts in (ev.get("build") or {}).get("specs", {}).items():
            sk = cd.by_name.get(name)
            if sk:
                b.specs[sk["id"]] = tuple(x["id"] for x in sk.get("specs", []) if x["text"] in texts)
        ctx = cls_(imp.cls, b, _policy_of(ev), copy.deepcopy(imp.loadout), scenario, imp.level or 45,
                   character={"name": imp.name, "server": imp.server, "key": imp.key,
                              "loadout": imp.loadout_name()}, weights=ev.get("weights") or [])
        ctx.equipped = {e["slot"]: e for e in inv["items"] if e.get("source") == "equipped"}
        return ctx

    # ------------------------------------------------------------ helpers
    def value(self):
        """Linear DPS value of a stats dict (stat weights; used only to pre-sort candidates)."""
        from ..opt.gear import per_unit, value_of
        pu = per_unit(self.weights) if self.weights else {}
        return lambda st: value_of(st, pu)

    def assemble(self, choice: dict, overrides: dict | None = None) -> dict:
        """Loadout with ``choice`` (slot -> entry) equipped.

        ``overrides`` (slot -> (gear, deity, skill_bonus)) replace an entry's
        stats, for upgrade what-ifs.
        """
        lo = copy.deepcopy(self.loadout)
        comps = lo["components"]
        overrides = overrides or {}
        deity_delta: dict = {}
        skill_delta: dict = {}
        changed = {s: e for s, e in choice.items() if e is not None and
                   (self.equipped.get(s) is not e or s in overrides)}
        if self.equipped:
            # imported character: one component per official slot
            for slot, e in changed.items():
                old = self.equipped.get(slot)
                if old is not None:
                    base = old.get("base_slot", slot)
                    comps[:] = [c for c in comps if c.get("slot") != base]
                    _, d0, s0 = entry_stats(old, self.cls)
                    I._add(deity_delta, d0, -1)
                    I._add(skill_delta, s0, -1)
                gear, d1, s1 = overrides.get(slot) or entry_stats(e, self.cls, value=self.value())
                comps.append({"slot": slot, "item": f"{e.get('name')} +{e.get('enchant', 0)}", "stats": gear})
                I._add(deity_delta, d1)
                I._add(skill_delta, s1)
        else:
            # median loadout: a component per slot group, scaled by the share still unchosen
            chosen = set(changed)
            keep = []
            for c in comps:
                grp = MEDIAN_GROUPS.get(c.get("slot"))
                if grp and chosen & set(grp):
                    left = len([s for s in grp if s not in chosen]) / len(grp)
                    if left <= 0:
                        continue
                    c = {**c, "stats": {k: (v * left if k != "skill_bonus" else v)
                                        for k, v in c["stats"].items()}}
                keep.append(c)
            comps[:] = keep
            for slot, e in changed.items():
                gear, d1, s1 = overrides.get(slot) or entry_stats(e, self.cls, value=self.value())
                comps.append({"slot": slot, "item": f"{e.get('name')} +{e.get('enchant', 0)}", "stats": gear})
                I._add(deity_delta, d1)
                I._add(skill_delta, s1)
        if any(deity_delta.values()):
            comp = next((c for c in comps if c.get("slot") == PROFILE_DEITY), None)
            if comp is None:
                comp = {"slot": PROFILE_DEITY, "item": "planner", "stats": {}}
                comps.append(comp)
            comp["stats"] = I._add(dict(comp["stats"]), deity_delta)
        if any(skill_delta.values()):
            comp = next((c for c in comps if c.get("slot") == GEAR_SKILLS), None)
            if comp is None:
                comp = {"slot": GEAR_SKILLS, "item": "planner", "stats": {"skill_bonus": {}}}
                comps.append(comp)
            sb = {int(k): v for k, v in (comp["stats"].get("skill_bonus") or {}).items()}
            for k, v in skill_delta.items():
                sb[int(k)] = sb.get(int(k), 0) + v
            comp["stats"] = {**comp["stats"], "skill_bonus": {str(k): int(round(v)) for k, v in sb.items()
                                                               if round(v) > 0}}
        return lo

    def dps(self, choice: dict | None = None, overrides: dict | None = None, build: Build | None = None,
            loadout: dict | None = None) -> float:
        from ..opt.rotation import materialize
        from ..run import prepare
        from ..scenarios import SCENARIOS
        from ..sim.engine import Sim
        lo = loadout or self.assemble(choice or {}, overrides)
        key = json.dumps([lo["components"], (build or self.build).__dict__ if build else None],
                         sort_keys=True, default=str)
        if key in self._cache:
            return self._cache[key]
        scen = SCENARIOS[self.scenario](lo)
        _, _, kit, stats = prepare(build or self.build, scen)
        pol = [e for e in self.policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
        res = Sim(stats.derived(), kit.actions, materialize(pol), scen.target, scen.config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods).run()
        self._cache[key] = res.dps
        return res.dps


def _policy_of(ev: dict) -> list:
    """Priority list of an evaluation: its own, else the class's optimized one."""
    pol = ev.get("policy_raw")
    if pol:
        return [tuple(e) if isinstance(e, list) else e for e in pol]
    from ..app.views import result_roots
    for root in result_roots():
        p = root / f"{ev['class']}_l45" / "build.json"
        if p.exists():
            from ..report import build_from_summary
            return build_from_summary(json.loads(p.read_text(encoding="utf-8")))[1]
    from ..kit.base import ClassData
    from ..run import kit_module
    return list(kit_module(ev["class"]).build_kit(Build(ev["class"]), ClassData(ev["class"])).policy)
