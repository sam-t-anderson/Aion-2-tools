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

from ..paths import read_json
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
    faction = None
    if systems and isinstance(systems.get("faction"), str):
        faction = systems["faction"]
    return {"per_point": rows, "current": cur, "share": {k: v / total for k, v in cur.items()},
            "best": best["deity"], "wasted_for_damage": wasted, "choices": choices,
            "board": plan_board(rows, faction=faction)}


SLOTS = {"colossus": 1, "statue": 4, "artwork": 12}


def catalog() -> dict:
    """The Pantheon decorations (``pantheon_items.json``): colossi, statues, artworks."""
    return read_json("global", "pantheon_items.json")


def _base_name(name: str) -> str:
    n = name.split(":", 1)[-1].strip()
    for suffix in (" (Bound)", " [Season 2]", " [Season 1]"):
        n = n.replace(suffix, "")
    return n.strip()


def plan_board(per_point: list[dict], faction: str | None = None, include_kr: bool = False, catalog_data: dict | None = None,
               alternatives: int = 4) -> dict:
    """The decorations to place: one colossus, four statues, twelve artworks, by modeled damage.

    Each decoration's value is its deity points times the damage per point of that deity on
    this character (``per_point`` from :func:`plan_pantheon`). The same decoration in several
    bindings or seasons counts once; items only in the Korea/Taiwan data are left out unless
    asked for; faction-bound items of the other faction are skipped when the faction is known.
    Ownership is not in any supported source, so every pick comes with where it is obtained.
    """
    data = catalog_data or catalog()
    value_per_point = {r["deity"]: r["gain_per_point"] for r in per_point}
    seen: dict = {}
    for it in data.get("items") or []:
        if not it.get("stats"):
            continue
        if not include_kr and it.get("global") is False:
            continue
        if faction and it.get("faction") and it["faction"] != faction:
            continue
        gain = sum(points * value_per_point.get(deity, 0.0) for deity, points in it["stats"].items())
        key = (it["kind"], _base_name(it["name"]))
        row = {"id": it["id"], "name": it["name"], "short": _base_name(it["name"]), "kind": it["kind"], "grade": it.get("grade"),
               "bound": it.get("bound"), "faction": it.get("faction"), "stats": it["stats"], "points": it.get("points") or sum(it["stats"].values()),
               "gain": gain, "sources": list(it.get("sources") or []), "drops": list(it.get("drops") or []),
               "damage_points": sum(p for d, p in it["stats"].items() if value_per_point.get(d, 0) > 0)}
        prev = seen.get(key)
        if prev is None:
            seen[key] = row
        else:
            # One decoration, several bindings: keep every way to get it on the one card.
            for src in row["sources"]:
                if src not in prev["sources"]:
                    prev["sources"].append(src)
            if not prev["sources"] and row["sources"]:
                prev["sources"] = row["sources"]
            if row["gain"] > prev["gain"]:
                prev.update({k: row[k] for k in ("id", "name", "grade", "bound", "faction", "stats", "points", "gain", "damage_points")})
    board, runners_up, totals = {}, {}, {}
    for kind, count in SLOTS.items():
        ranked = sorted((r for r in seen.values() if r["kind"] == kind), key=lambda r: (-r["gain"], -r["points"], r["short"]))
        board[kind] = ranked[:count]
        runners_up[kind] = ranked[count:count + alternatives]
        for r in board[kind]:
            for deity, points in r["stats"].items():
                totals[deity] = totals.get(deity, 0) + points
    placed = [r for rows in board.values() for r in rows]
    counts = {kind: sum(1 for r in seen.values() if r["kind"] == kind) for kind in SLOTS}
    return {"slots": SLOTS, "board": board, "runners_up": runners_up, "totals": totals,
            "gain": sum(r["gain"] for r in placed), "faction": faction, "include_kr": include_kr,
            "catalog": {"source": data.get("source"), "candidates": counts,
                        "unknown_effect": sum(1 for it in data.get("items") or [] if not it.get("stats"))},
            "note": "Modeled damage value per decoration = its deity points × this character's damage per point of each deity "
                    "(Life, Destiny and Space add nothing to damage). Your collection is not in the official profile, so the board shows "
                    "the best obtainable set and where each piece comes from; season rewards keep their effect only until the end of the "
                    "following season. Items only in the Korea/Taiwan client data are left out."}
