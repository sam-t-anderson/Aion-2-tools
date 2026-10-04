"""Pantheon (deity stat) planning.

The ten deity stats are named after the Lords; each point gives +0.1% to its
two effects. The ones that change damage:

    Destruction [Zikel]   Attack increase          Time [Siel]          Combat Speed
    Death [Triniel]       Critical Hit increase    Illusion [Kaisinel]  Cooldown reduction
    Wisdom [Lumiel]       Double chance, MP cost   Justice [Nezekan]    Perfect chance
    Freedom [Vaizel]      Accuracy (only matters below the hit cap)

Life, Destiny and Space do nothing for damage. Points come from fixed sources
(profile base, Monolith rewards) and from choices: the arcana variant per slot
(each slot offers two deity stats) and the deity roll of bracelets such as the
Abyssal Bracelet (any of the ten, +9 to +17).
"""
from __future__ import annotations

from .arcana import deity_value
from .context import PROFILE_DEITY, PlanContext

DEITIES = [("Destruction [Zikel]", "destruction"), ("Death [Triniel]", "death"), ("Wisdom [Lumiel]", "wisdom"),
           ("Time [Siel]", "time"), ("Illusion [Kaisinel]", "illusion"), ("Justice [Nezekan]", "justice"),
           ("Freedom [Vaizel]", "freedom"), ("Life [Yustiel]", None), ("Destiny [Marchutan]", None),
           ("Space [Israphel]", None)]
#: official profile stat type -> display label
PROFILE_TYPES = {"Destruction": "Destruction [Zikel]", "Death": "Death [Triniel]", "Wisdom": "Wisdom [Lumiel]",
                 "Time": "Time [Siel]", "Illusion": "Illusion [Kaisinel]", "Justice": "Justice [Nezekan]",
                 "Freedom": "Freedom [Vaizel]", "Life": "Life [Yustiel]", "Destiny": "Destiny [Marchutan]",
                 "Space": "Space [Israphel]"}
BRACELET_ROLL = (9, 17)


def current_points(ctx: PlanContext, systems: dict | None = None) -> dict[str, float]:
    """Deity points by label: the official profile when imported, else the loadout."""
    if systems and systems.get("profile_stats"):
        return {PROFILE_TYPES[t]: v.get("value") or 0 for t, v in systems["profile_stats"].items()
                if t in PROFILE_TYPES}
    comp = next((c for c in ctx.loadout.get("components", []) if c.get("slot") == PROFILE_DEITY), None)
    st = (comp or {}).get("stats", {})
    return {label: st.get(f, 0) for label, f in DEITIES if f}


def plan_pantheon(ctx: PlanContext, systems: dict | None = None, arcana: dict | None = None,
                  step: float = 20.0) -> dict:
    """DPS of each deity stat per point, the current split, and the choices that move it."""
    rows = []
    for label, field in DEITIES:
        g = deity_value(ctx, field, step)
        rows.append({"deity": label, "field": field, "gain_per_point": g / step, "gain_20": g})
    rows.sort(key=lambda r: -r["gain_per_point"])
    cur = current_points(ctx, systems)
    total = sum(cur.values()) or 1.0
    best = rows[0]
    wasted = {k: v for k, v in cur.items() if not dict(DEITIES).get(k)}
    lo, hi = BRACELET_ROLL
    choices = []
    for slot, a in ((arcana or {}).get("slots") or {}).items():
        v = a.get("variant")
        if v:
            choices.append({"source": slot, "pick": v["name"], "deity": v["deity"], "points": v["points"],
                            "gain": v["gain"],
                            "instead_of": [{"name": o["name"], "deity": o["deity"], "gain": o["gain"]}
                                           for o in v.get("other", [])]})
    choices.append({"source": "Bracelet deity roll (Abyssal Bracelet)", "pick": best["deity"],
                    "points": f"{lo}-{hi}", "gain": best["gain_per_point"] * (lo + hi) / 2})
    return {"per_point": rows, "current": cur, "share": {k: v / total for k, v in cur.items()},
            "best": best["deity"], "wasted_for_damage": wasted, "choices": choices}
