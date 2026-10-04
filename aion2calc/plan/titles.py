"""Title planning: which title to equip in each slot, and which titles are worth collecting.

A title has an **equip** bonus (only while it sits in one of the three title
slots: Attack, Defense, Etc) and an **owned** bonus (added to the title
collection as soon as you have it). The slot of each title comes from its
metabot page ("Role: Offensive" -> Attack). The official profile shows only the
equipped titles, so the titles you own are listed in the inventory
(``"titles_owned": ["Unbound by Genus", ...]``, or on the Gear & Advice page).
"""
from __future__ import annotations

from ..model.character import parse_bonus_text
from ..paths import read_json
from .context import PlanContext

SLOTS = ("Attack", "Defense", "Etc")
#: loadout component names per slot (official import, median loadouts)
COMP = {"Attack": ("Title (Attack)", "Attack title"), "Defense": ("Title (Defense)", "Defense title"),
        "Etc": ("Title (Etc)", "Other title", "Etc title")}
OWNED_COMP = "Owned titles"
OFFENSIVE = {"attack", "crit", "crit_dmg", "crit_atk", "amp_all", "amp_pve", "amp_boss", "pen", "pve_atk", "boss_atk",
             "weapon_amp", "double", "perfect", "multihit", "accuracy", "attack_pct"}


def catalog() -> list[dict]:
    out = []
    for t in read_json("global", "titles.json"):
        eq = parse_bonus_text(t.get("equip") or "")
        slot = t.get("slot") or ("Attack" if set(eq) & OFFENSIVE else "Etc")
        out.append({**t, "slot": slot, "equip_stats": eq, "owned_stats": parse_bonus_text(t.get("owned") or "")})
    return out


def _with_title(ctx: PlanContext, slot: str, stats: dict, label: str) -> dict:
    lo = ctx.assemble(ctx.equipped)
    comps = [c for c in lo["components"] if c.get("slot") not in COMP[slot]]
    comps.append({"slot": COMP[slot][0], "item": label, "stats": stats})
    lo["components"] = comps
    return lo


def _with_owned(ctx: PlanContext, extra: dict) -> dict:
    lo = ctx.assemble(ctx.equipped)
    comp = next((c for c in lo["components"] if c.get("slot") == OWNED_COMP), None)
    if comp is None:
        comp = {"slot": OWNED_COMP, "item": "planner", "stats": {}}
        lo["components"].append(comp)
    st = dict(comp["stats"])
    for k, v in extra.items():
        st[k] = st.get(k, 0.0) + v
    comp["stats"] = st
    return lo


def plan_titles(ctx: PlanContext, systems: dict | None = None, owned: list[str] | None = None,
                top: int = 5) -> dict:
    cat = catalog()
    by_name = {t["name"]: t for t in cat}
    base = ctx.dps(ctx.equipped)
    equipped = {}
    for t in (systems or {}).get("titles", []):
        s = {"Etc": "Etc", "Attack": "Attack", "Defense": "Defense"}.get(t.get("slot"), t.get("slot"))
        equipped[s] = by_name.get(t["name"]) or {"name": t["name"], "grade": t.get("grade"),
                                                 "equip": ", ".join(t.get("equip") or [])}
    if not equipped:
        for slot in SLOTS:
            comp = next((c for c in ctx.loadout.get("components", []) if c.get("slot") in COMP[slot]), None)
            if comp:
                first = comp.get("item", "").split(" / ")[0]
                equipped[slot] = by_name.get(first) or {"name": comp.get("item"), "equip": ""}
    owned_set = set(owned or [])
    slots = {}
    for slot in SLOTS:
        rows = []
        for t in cat:
            if t["slot"] != slot or not t["equip_stats"]:
                continue
            d = ctx.dps(loadout=_with_title(ctx, slot, t["equip_stats"], t["name"]))
            rows.append({"name": t["name"], "grade": t.get("grade"), "equip": t.get("equip"), "owned_bonus": t.get("owned"),
                         "how": t.get("earn") or t.get("how"), "category": t.get("category"), "slug": t.get("slug"),
                         "gain": d / base - 1, "owned": t["name"] in owned_set})
        rows.sort(key=lambda r: -r["gain"])
        cur = equipped.get(slot)
        cur_gain = next((r["gain"] for r in rows if cur and r["name"] == cur.get("name")), 0.0)
        for r in rows:                                  # gains against the equipped title
            r["gain"] -= cur_gain
        best_owned = next((r for r in rows if r["owned"]), None) if owned_set else None
        slots[slot] = {"equipped": cur and {"name": cur.get("name"), "grade": cur.get("grade"), "equip": cur.get("equip"),
                                             "gain": 0.0},
                       "best_owned": best_owned, "best": rows[:top]}
    collect = []
    for t in cat:
        if t["name"] in owned_set or not t["owned_stats"]:
            continue
        d = ctx.dps(loadout=_with_owned(ctx, t["owned_stats"]))
        if d > base * (1 + 1e-5):
            collect.append({"name": t["name"], "grade": t.get("grade"), "owned_bonus": t.get("owned"),
                            "how": t.get("earn") or t.get("how"), "category": t.get("category"), "gain": d / base - 1})
    collect.sort(key=lambda r: -r["gain"])
    return {"slots": slots, "collect": collect[:12], "owned_known": bool(owned_set),
            "note": None if owned_set else "List the titles you own (Gear & Advice page) to see the best one you can "
                                              "equip now; the official page shows only equipped titles."}
