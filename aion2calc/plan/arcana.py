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

#: the third grade is "Legend" in the game's data and "Epic" in the catalog (its slugs end in "-legend")
BASE_ROLLS = {"Common": 1, "Rare": 2, "Legend": 3, "Epic": 3, "Legendary": 3, "Unique": 4}
#: An arcana enhances to +5; every step adds one skill option (a Unique +5 holds nine).
ARCANA_MAX_ENHANCE = 5
TIMING = ("time", "illusion")
#: a grade's other names, for finding a card's variant in the catalog
_GRADE_ALIASES = {"Legend": ("Epic", "Legendary"), "Epic": ("Legend", "Legendary"), "Legendary": ("Epic", "Legend")}


def _deity_label(text) -> str | None:
    """The deity stat a card carries, as the catalog labels it ("Time [Siel]"), from that label or from the official
    API's stat id or name ("Time", "Destiny")."""
    key = str(text or "").strip().casefold()
    if not key:
        return None
    for label in I.DEITY_LABELS:
        if key in (label.casefold(), label.split(" [")[0].casefold()):
            return label
    return None


def _points(text) -> float:
    nums = I._numbers(str(text if text is not None else ""))
    return nums[0] if nums else 0.0


def _catalog_variant(e: dict) -> dict | None:
    """The catalog entry of a card's variant at the card's grade: a card read from the official page is matched by
    name, which the catalog shares across grades."""
    conn = store.connect()
    by_slug = store.item(conn, e["slug"]) if e.get("slug") else None
    grade = e.get("grade")
    if by_slug and (e.get("source") != "equipped" or not grade or by_slug.get("grade") == grade):
        return by_slug
    name = e.get("name") or (by_slug or {}).get("name")
    if not name:
        return by_slug
    want = (grade, *_GRADE_ALIASES.get(grade or "", ()))
    for (slug,) in conn.execute("SELECT slug FROM items WHERE lower(name)=lower(?) ORDER BY item_level DESC",
                                (name,)).fetchall():
        it = store.item(conn, slug)
        if it and (not grade or it.get("grade") in want):
            return it
    return None if grade else by_slug


def card_deity(e: dict) -> dict | None:
    """The deity stat an arcana card carries: ``{"label": "Time [Siel]", "points": 20.0, "source": ...}``.

    ``source`` is ``"card"`` when the card's own stats say it (an imported card's main stats; the official API names
    it by its type, "Time") and ``"catalog"`` when it is its variant's fixed stat at the card's grade (a card added
    from the catalog, or one imported before 0.2.389). None when neither knows it."""
    for x in e.get("main_stats") or []:
        label = _deity_label(x.get("name")) or _deity_label(x.get("id"))
        if label:
            return {"label": label, "points": _points(x.get("value")) + _points(x.get("extra")), "source": "card"}
    fields = {f: label for label, f in I.DEITY_LABELS.items() if f}
    mine = [(fields[f], v) for f, v in (e.get("deity") or {}).items() if f in fields and v]
    if len(mine) == 1:
        return {"label": mine[0][0], "points": float(mine[0][1]), "source": "card"}
    it = _catalog_variant(e)
    for label, value in ((it or {}).get("fixed") or {}).items():
        if label in I.DEITY_LABELS:
            return {"label": label, "points": _points(value), "source": "catalog"}
    return None


def card_stats(e: dict) -> list[list]:
    """A card's other stats as the official page lists them (``[[label, value], …]``): its main stats besides the
    deity stat, then its random rolls. An arcana card usually has none."""
    out = []
    for x in e.get("main_stats") or []:
        if _deity_label(x.get("name")) or _deity_label(x.get("id")):
            continue
        label = x.get("name") or x.get("id")
        if label and x.get("value") not in (None, ""):
            extra = f" (+{x['extra']})" if x.get("extra") not in (None, "", "0", 0) else ""
            out.append([str(label), f"{x['value']}{extra}"])
    # an imported item keeps its rolls as the page shows them ("rolls_text"); one added from the catalog keeps the
    # values set on the Gear page ("rolls"), its "rolls_text" being one line of text
    pairs = e.get("rolls_text") if e.get("source") == "equipped" else e.get("rolls")
    for p in pairs if isinstance(pairs, list) else []:
        if isinstance(p, (list, tuple)) and len(p) == 2 and p[0] and p[1] not in (None, ""):
            value = f"+{p[1]:g}" if isinstance(p[1], (int, float)) and not isinstance(p[1], bool) else str(p[1])
            out.append([str(p[0]), value])
    return out


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


def pool_slots(cls: str) -> dict[str, list[str]]:
    """Which arcana cards can roll each skill: ``{skill name: ["Chalice", "Bell", …]}`` from the bundled
    option pools, so a preset's bonus levels can say where to look for them."""
    pools_all = read_json("global", "arcana_skill_pools.json")
    out: dict[str, list[str]] = {}
    for slot in I.ARCANA_SLOTS:
        cat = I.SLOTS[slot][0]
        pool = next((p[cls] for slug, p in pools_all.items() if slug.startswith(cat.lower()) and cls in p), None)
        for name in (pool or {}).get("skills", []):
            if cat not in out.setdefault(name, []):
                out[name].append(cat)
    return out


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
        out.append({"slug": slug, "name": it["name"], "grade": it.get("grade"), "deity": deity, "icon": it.get("icon")})
    return out


def plan_arcana(ctx: PlanContext, inv: dict | None = None, enhance: int = ARCANA_MAX_ENHANCE) -> dict:
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
    cd_ = ClassData(cls)
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
            same_grade = _expected(chances, values, r, cap)
            # what the card itself holds (0.2.389): its deity stat, any other stats, and how many of its option
            # levels its skill options fill
            mine.append({"name": e.get("name"), "grade": e.get("grade"), "enchant": e.get("enchant"), "icon": e.get("icon"),
                         "equipped": e.get("source") == "equipped", "skills": lv, "gain": have,
                         "deity": card_deity(e), "stats": card_stats(e),
                         "options": {"used": sum(lv.values()), "of": r},
                         "skill_ids": {nm: (cd_.by_name.get(nm) or {}).get("id") for nm in lv},
                         "expected_same_grade": same_grade,
                         "verdict": "keep" if have >= same_grade else
                         "below average for its grade and level: replace when a better roll comes"})
        sid = {nm: (cd_.by_name.get(nm) or {}).get("id") for nm in chances}
        out[slot] = {"skill_ids": sid,
                     "variant": variant and {"name": variant["name"], "deity": variant["deity"].get("label"),
                                             "icon": variant.get("icon"), "grade": variant.get("grade"),
                                             "points": variant["deity"].get("points"), "gain": variant["dps"],
                                             "other": [{"name": v["name"], "deity": v["deity"].get("label"),
                                                        "gain": v["dps"]} for v in uniques if v is not variant]},
                     "chase": [{"skill": s, "gain_per_level": g} for s, g in ranked[:4]],
                     "ideal": {"rolls": rolls, "skills": ideal, "gain": ideal_gain},
                     "expected": {"unique_0": exp0, f"unique_{enhance}": exp5},
                     "owned": mine}
    order = sorted(out, key=lambda s: -out[s]["ideal"]["gain"])
    return {"slots": out, "priority": order, "values": values}
