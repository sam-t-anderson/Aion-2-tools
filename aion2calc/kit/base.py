"""Class data access and the :class:`Build` description shared by kits and optimizers."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

#: Skill-point price of each level (index = level-1); level 1 is free.
SP_COST = [0, 1, 1, 1, 2, 2, 2, 4, 4, 4]
#: Stigma-point price of each level (index = level-1).
STIGMA_COST = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 8, 8, 8, 8, 8]
#: Specialization slots open at these effective skill levels.
SPEC_SLOT_LEVELS = (8, 12, 20)
#: Stigma specializations switch on automatically at these stigma levels.
STIGMA_SPEC_LEVELS = (5, 10, 15, 20)


def sp_to_reach(level: int) -> int:
    return sum(SP_COST[:max(1, min(level, 10))])


def stigma_points_to_reach(level: int) -> int:
    return sum(STIGMA_COST[:max(0, min(level, 20))])


def spec_slots(level: int) -> int:
    return sum(1 for lv in SPEC_SLOT_LEVELS if level >= lv)


def valid_base_stats(rows, level_cap=45) -> bool:
    """Require finite source rows covering the supported character levels."""
    if not isinstance(rows, dict) or not rows:
        return False
    try:
        levels = []
        for key, row in rows.items():
            if not str(key).isascii() or not str(key).isdigit() or int(key) < 1:
                return False
            levels.append(int(key))
            for stat in ("hp", "defense", "attack"):
                value = row[stat]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    return False
            if row["hp"] <= 0 or row["attack"] <= 0:
                return False
        return min(levels) == 1 and max(levels) >= int(level_cap)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


@lru_cache(maxsize=None)
def _load_class(cls: str, bundled: bool) -> dict:
    from ..paths import PKG_DATA, read_json
    raw = (json.loads((PKG_DATA / "global" / "classes" / f"{cls}.json").read_text(encoding="utf-8"))
           if bundled else read_json("global", "classes", f"{cls}.json"))
    if not valid_base_stats(raw.get("base_stats"), raw.get("level_cap", 45)):
        # Recover already-synced empty tables without deleting the user's data.
        fallback = json.loads((PKG_DATA / "global" / "classes" / f"{cls}.json").read_text(encoding="utf-8"))
        if not valid_base_stats(fallback.get("base_stats"), raw.get("level_cap", 45)):
            raise ValueError(f"Base stats unavailable for {cls}; no complete bundled table covers this level cap")
        raw = {**raw, "base_stats": bundled["base_stats"], "base_stats_source": "bundled fallback"}
    return raw


@lru_cache(maxsize=None)
def _load_hit_profiles(cls: str, bundled: bool) -> dict:
    from ..paths import PKG_DATA, data_file
    p = PKG_DATA / "kr" / "hit_profiles" / f"{cls}.json" if bundled else data_file("kr", "hit_profiles", f"{cls}.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_class(cls: str) -> dict:
    from ..paths import bundled_model_data_enabled
    return _load_class(cls, bundled_model_data_enabled())


def load_hit_profiles(cls: str) -> dict:
    from ..paths import bundled_model_data_enabled
    return _load_hit_profiles(cls, bundled_model_data_enabled())


load_class.cache_clear = _load_class.cache_clear
load_hit_profiles.cache_clear = _load_hit_profiles.cache_clear


def clear_caches() -> None:
    """Forget cached class data (after the database sync wrote newer files)."""
    load_class.cache_clear()
    load_hit_profiles.cache_clear()


class ClassData:
    """Convenience wrapper around one class's global client data."""

    def __init__(self, cls: str):
        self.cls = cls
        self.raw = load_class(cls)
        self.skills = {s["id"]: s for s in self.raw["skills"]}
        self.by_name = {s["name"]: s for s in self.raw["skills"]}
        self.boards = self.raw["boards"]
        self.node_index = {}
        for b in self.boards:
            for n in b["nodes"]:
                self.node_index[n["id"]] = (b, n)
        self.hit_profiles = load_hit_profiles(cls)

    def budget(self, level: int) -> dict:
        best = {"skill": 0, "stigma": 0, "slots": 0}
        for row in self.raw["budget"]:
            if row["level"] <= level:
                best = row
        return best

    def base_stats(self, level: int) -> dict:
        rows = {int(k): v for k, v in self.raw["base_stats"].items()}
        if level in rows:
            return rows[level]
        if not rows or level < min(rows) or level > max(rows):
            raise ValueError(f"Base stats unavailable for {self.cls} at level {level}")
        lo = max(k for k in rows if k <= level)
        hi = min(k for k in rows if k >= level)
        if lo == hi:
            return rows[lo]
        f = (level - lo) / (hi - lo)
        return {k: rows[lo][k] + f * (rows[hi][k] - rows[lo][k]) for k in rows[lo]}

    def vals(self, sid: int, level: int):
        s = self.skills[sid]
        v = s.get("vals") or []
        if not v:
            return None
        return v[max(0, min(level, len(v)) - 1)]

    def cd(self, sid: int, level: int) -> float:
        cd = self.skills[sid].get("cd") or []
        if not cd:
            return 0.0
        x = cd[max(0, min(level, len(cd)) - 1)]
        return float(x or 0.0)

    def mp(self, sid: int, level: int) -> float:
        mp = self.skills[sid].get("mp") or []
        if not mp:
            return 0.0
        return float(mp[max(0, min(level, len(mp)) - 1)] or 0.0)

    def hits(self, sid: int, default: int = 1) -> int:
        prof = self.hit_profiles.get(str(sid), {}).get("hits", {})
        counts = [h["hits"] for k, h in prof.items() if "hits" in h]
        return max(counts) if counts else default

    def daevanion_levels(self, nodes) -> dict[int, int]:
        out: dict[int, int] = {}
        for nid in nodes:
            b, n = self.node_index.get(nid, (None, None))
            if n and n.get("skillId"):
                out[n["skillId"]] = out.get(n["skillId"], 0) + int(n.get("skillLevels", 1))
        return out

    def daevanion_stats(self, nodes) -> dict[str, float]:
        out: dict[str, float] = {}
        for nid in nodes:
            b, n = self.node_index.get(nid, (None, None))
            if n:
                for st in n.get("stats", []):
                    out[st["stat"]] = out.get(st["stat"], 0) + st["value"]
        return out


@dataclass
class Build:
    cls: str
    level: int = 45
    sp: dict = field(default_factory=dict)          # skill id -> trained level (1..10)
    daevanion: set = field(default_factory=set)     # node ids
    bonus: dict = field(default_factory=dict)       # skill id -> extra levels (gear / arcana)
    specs: dict = field(default_factory=dict)       # skill id -> tuple of spec ids
    stigmas: dict = field(default_factory=dict)     # stigma id -> stigma level
    hellfire_charge: int = 1

    def copy(self) -> "Build":
        return Build(self.cls, self.level, dict(self.sp), set(self.daevanion), dict(self.bonus),
                     {k: tuple(v) for k, v in self.specs.items()}, dict(self.stigmas),
                     self.hellfire_charge)

    def effective_levels(self, cd: ClassData) -> dict[int, int]:
        dv = cd.daevanion_levels(self.daevanion)
        out = {}
        for sid, s in cd.skills.items():
            if s["kind"] == "stigma":
                if sid in self.stigmas:
                    out[sid] = self.stigmas[sid]
                continue
            base = self.sp.get(sid, 1)
            out[sid] = base + dv.get(sid, 0) + self.bonus.get(sid, 0)
        return out

    def sp_spent(self) -> int:
        return sum(sp_to_reach(lv) for lv in self.sp.values())

    def stigma_spent(self) -> int:
        return sum(stigma_points_to_reach(lv) for lv in self.stigmas.values())

    def daevanion_cost(self, cd: ClassData) -> int:
        return sum(cd.node_index[n][1]["cost"] for n in self.daevanion if n in cd.node_index)

    def validate(self, cd: ClassData, daev_budget: int | None = None) -> list[str]:
        errs = []
        bud = cd.budget(self.level)
        if self.sp_spent() > bud["skill"]:
            errs.append(f"skill points {self.sp_spent()} > {bud['skill']}")
        if self.stigma_spent() > bud["stigma"] + 1:   # +1 from the 3rd Ascension reward
            errs.append(f"stigma points {self.stigma_spent()} > {bud['stigma'] + 1}")
        if len(self.stigmas) > bud["slots"]:
            errs.append(f"{len(self.stigmas)} stigmas > {bud['slots']} slots")
        lv = self.effective_levels(cd)
        for sid, chosen in self.specs.items():
            s = cd.skills[sid]
            if s["kind"] != "active":
                continue
            if len(chosen) > spec_slots(lv.get(sid, 1)):
                errs.append(f"{s['name']}: {len(chosen)} specs > {spec_slots(lv.get(sid, 1))} slots")
            for spid in chosen:
                spec = next((x for x in s["specs"] if x["id"] == spid), None)
                if spec is None or spec["unlock"] > lv.get(sid, 1):
                    errs.append(f"{s['name']}: spec {spid} not unlocked")
        if daev_budget is not None and self.daevanion_cost(cd) > daev_budget:
            errs.append(f"daevanion cost {self.daevanion_cost(cd)} > {daev_budget}")
        return errs
