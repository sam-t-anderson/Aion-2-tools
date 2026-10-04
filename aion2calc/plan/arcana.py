"""Arcana planning: which variant per slot, which skill options to chase, and
whether the arcana you have are worth keeping.

Rules (global client): an arcana rolls ``base + enhancement`` skill options
(base by grade: Common 1, Rare 2, Legend 3, Unique 4; Unique +5 = 9 options).
Each option adds one level to a random skill of the slot's pool, a skill holds
at most ``max_level`` (4) options, and the variants of a slot (e.g. Parchment of
Magic / of Vigor) share the pool and differ only in their deity stat.
"""
from __future__ import annotations

import random

from ..db import store
from ..kit.base import ClassData
from ..paths import read_json
from . import items as I
from .context import PROFILE_DEITY, PlanContext

BASE_ROLLS = {"Common": 1, "Rare": 2, "Legend": 3, "Unique": 4}
TIMING = ("time", "illusion")


def skill_level_values(ctx: PlanContext, skills: set[str], max_level: int = 4) -> dict[str, list[float]]:
    """DPS gain (fraction) of +1..+max_level levels on each skill, simulated."""
    cd = ClassData(ctx.cls)
    base = ctx.dps(ctx.equipped)
    out = {}
    for nm in sorted(skills):
        sk = cd.by_name.get(nm)
        if not sk:
            continue
        row = []
        for lv in range(1, max_level + 1):
            b = ctx.build.copy()
            b.bonus[sk["id"]] = b.bonus.get(sk["id"], 0) + lv
            row.append(ctx.dps(ctx.equipped, build=b) / base - 1)
        # a level never costs damage once the rotation adapts; dips are timing artifacts of the
        # fixed priority list, so keep the curve non-decreasing
        for i in range(len(row)):
            row[i] = max(row[i], row[i - 1] if i else 0.0, 0.0)
        out[nm] = row
    return out


def deity_value(ctx: PlanContext, field: str | None, points: float) -> float:
    """DPS gain (fraction) of ``points`` of a deity stat on top of the current set."""
    if not field or not points:
        return 0.0
    if field in TIMING and ctx.weights:
        # tempo stats shift every cast time; with a fixed priority list single simulations
        # alias, so use the stat weights (re-optimized rotation slopes) for them
        w = next((x for x in ctx.weights if x.get("stat") == field and x.get("step")), None)
        if w:
            return w["pct"] / 100 * points / w["step"]
    lo = ctx.assemble(ctx.equipped)
    comp = next((c for c in lo["components"] if c.get("slot") == PROFILE_DEITY), None)
    if comp is None:
        comp = {"slot": PROFILE_DEITY, "item": "planner", "stats": {}}
        lo["components"].append(comp)
    comp["stats"] = I._add(dict(comp["stats"]), {field: points})
    return ctx.dps(loadout=lo) / ctx.dps(ctx.equipped) - 1


def _ideal(pool: dict, values: dict, rolls: int, cap: int) -> tuple[dict, float]:
    """Best possible options: greedy by the next level's marginal gain."""
    levels = {s: 0 for s in pool}
    total = 0.0
    for _ in range(rolls):
        best, gain = None, -1.0
        for s in levels:
            v = values.get(s)
            if not v or levels[s] >= cap:
                continue
            g = v[levels[s]] - (v[levels[s] - 1] if levels[s] else 0.0)
            if g > gain:
                best, gain = s, g
        if best is None:
            break
        levels[best] += 1
        total += gain
    return {s: lv for s, lv in levels.items() if lv}, total


def _value(levels: dict, values: dict) -> float:
    return sum(values[s][min(lv, len(values[s])) - 1] for s, lv in levels.items() if lv and s in values)


def _expected(pool: dict, values: dict, rolls: int, cap: int, samples: int = 2000, seed: int = 7) -> float:
    rng = random.Random(seed)
    names = list(pool)
    weights = [pool[s] or 1.0 for s in names]
    tot = 0.0
    for _ in range(samples):
        lv = dict.fromkeys(names, 0)
        for _ in range(rolls):
            open_ = [(s, w) for s, w in zip(names, weights) if lv[s] < cap]
            if not open_:
                break
            s = rng.choices([x for x, _ in open_], [w for _, w in open_])[0]
            lv[s] += 1
        tot += _value(lv, values)
    return tot / samples


def _variants(category: str) -> list[dict]:
    conn = store.connect()
    out = []
    for (slug,) in conn.execute("SELECT slug FROM items WHERE category=?", (category,)).fetchall():
        it = store.item(conn, slug)
        if not it:
            continue
        deity = {}
        for label, v in (it.get("fixed") or {}).items():
            if label in I.DEITY_LABELS:
                deity = {"label": label, "field": I.DEITY_LABELS[label], "points": I._numbers(v)[0]}
        out.append({"slug": slug, "name": it["name"], "grade": it.get("grade"), "deity": deity})
    return out


def plan_arcana(ctx: PlanContext, inv: dict | None = None, enhance: int = 5) -> dict:
    """Per arcana slot: the variant to use, the options to chase, the ideal and
    expected gain of a Unique +``enhance``, and advice on the arcana you own."""
    pools_all = read_json("global", "arcana_skill_pools.json")
    cls = ctx.cls
    slots = {}
    want = set()
    for slot in I.ARCANA_SLOTS:
        cat = I.SLOTS[slot][0]
        pool = next((p[cls] for slug, p in pools_all.items() if slug.startswith(cat.lower()) and cls in p), None)
        if pool:
            slots[slot] = pool
            want |= set(pool.get("skills", []))
    values = skill_level_values(ctx, want)
    owned = [e for e in (inv or {}).get("items", []) if e.get("category") in I.ARCANA_CATEGORIES]
    out = {}
    for slot, pool in slots.items():
        cat = I.SLOTS[slot][0]
        cap = pool.get("max_level", 4)
        chances = pool.get("chances") or {s: 1.0 for s in pool.get("skills", [])}
        uniques = [v for v in _variants(cat) if v["grade"] == "Unique"] or _variants(cat)
        for v in uniques:
            v["dps"] = deity_value(ctx, v["deity"].get("field"), v["deity"].get("points", 0))
        variant = max(uniques, key=lambda v: v["dps"]) if uniques else None
        rolls = BASE_ROLLS["Unique"] + enhance
        ideal, ideal_gain = _ideal(chances, values, rolls, cap)
        exp0 = _expected(chances, values, BASE_ROLLS["Unique"], cap)
        exp5 = _expected(chances, values, rolls, cap)
        ranked = sorted(((s, values[s][0]) for s in chances if s in values), key=lambda x: -x[1])
        mine = []
        for e in owned:
            if e.get("category") != cat:
                continue
            lv = {}
            for nm, n in e.get("skills") or []:
                lv[nm] = lv.get(nm, 0) + int(n)
            r = BASE_ROLLS.get(e.get("grade") or "", 4) + int(e.get("enchant") or 0)
            have = _value(lv, values)
            mine.append({"name": e.get("name"), "grade": e.get("grade"), "enchant": e.get("enchant"),
                         "equipped": e.get("source") == "equipped", "skills": lv, "gain": have,
                         "expected_same_grade": _expected(chances, values, r, cap),
                         "verdict": "keep" if have >= _expected(chances, values, r, cap) else
                         "below average for its grade and level: replace when a better roll comes"})
        out[slot] = {"variant": variant and {"name": variant["name"], "deity": variant["deity"].get("label"),
                                             "points": variant["deity"].get("points"), "gain": variant["dps"],
                                             "other": [{"name": v["name"], "deity": v["deity"].get("label"),
                                                        "gain": v["dps"]} for v in uniques if v is not variant]},
                     "chase": [{"skill": s, "gain_per_level": g} for s, g in ranked[:4]],
                     "ideal": {"rolls": rolls, "skills": ideal, "gain": ideal_gain},
                     "expected": {"unique_0": exp0, f"unique_{enhance}": exp5},
                     "owned": mine}
    order = sorted(out, key=lambda s: -out[s]["ideal"]["gain"])
    return {"slots": out, "priority": order, "values": values}
