"""Title planning: which title to equip in each slot, and which titles are worth collecting.

A title has an **equip** bonus (only while it sits in one of the three title
slots: Attack, Defense, Etc) and an **owned** bonus (added to the title
collection as soon as you have it). The slot of each title comes from its
metabot page ("Role: Offensive" -> Attack). The official profile shows only the
equipped titles, so the titles you own are listed in the inventory
(``"titles_owned": ["Unbound by Genus", ...]``, or on the Gear & Advice page).
"""
from __future__ import annotations

import json
import re

from ..model.character import parse_bonus_text
from ..paths import PKG_DATA, read_json
from .context import PlanContext

SLOTS = ("Attack", "Defense", "Etc")
#: loadout component names per slot (official import, median loadouts)
COMP = {"Attack": ("Title (Attack)", "Attack title"), "Defense": ("Title (Defense)", "Defense title"),
        "Etc": ("Title (Etc)", "Other title", "Etc title")}
OWNED_COMP = "Owned titles"
OFFENSIVE = {"attack", "crit", "crit_dmg", "crit_atk", "amp_all", "amp_pve", "amp_boss", "pen", "pve_atk", "boss_atk",
             "weapon_amp", "double", "perfect", "multihit", "accuracy", "attack_pct"}


ROLE_SLOTS = {"Offensive": "Attack", "Defensive": "Defense", "Utility": "Etc"}
#: Equip-bonus stats that cut the damage the character takes, per kind of fight. Damage Tolerance lowers the
#: attacker's damage boost (the damage model's boost bucket, ``1 + boosts - tolerance``), so +3 % takes about 3 %
#: off a boss's hits. Every Defense title carries only defensive bonuses (Defense, Block, Evasion, resists and
#: these), so none adds damage and the slot is ranked by this cut instead (0.2.371). Block counts only against an
#: attacker's Accuracy, which a title slot does not know (0.2.386), and Defense and Evasion have no formula in the
#: model, so they are not ranked.
GUARD = {"pve": ("Damage Tolerance", "PvE Damage Tolerance", "Boss Damage Tolerance"),
         "pvp": ("Damage Tolerance", "PvP Damage Tolerance")}


def guard_of(text: str, kinds: tuple[str, ...]) -> float:
    """The damage cut an equip bonus gives in a fight ``kinds`` (a :data:`GUARD` entry) applies to: its summed
    tolerances as a fraction ("PvE Damage Tolerance +3%, Block +100" -> 0.03 in PvE)."""
    total = 0.0
    for part in re.split(r",\s*", text or ""):
        m = re.match(r"(.+?)\s*\+([\d.]+)%$", part.strip())
        if m and m.group(1).strip() in kinds:
            total += float(m.group(2)) / 100
    return total


def shifted(title: dict) -> bool:
    """A title the app's database sync stored one column off (0.2.36x to 0.2.370): metabot's titles table gained a
    Role column before the bonuses, so the role landed where the equip bonus belongs, the equip bonus where the
    owned bonus belongs, and the owned bonus was lost. Gear & Advice then showed "equipped: Offensive" over the
    equip bonus labelled as owned, and ranked titles worth collecting by their equip bonus."""
    return title.get("equip") in ROLE_SLOTS


def repaired(titles: list[dict]) -> list[dict]:
    """``titles`` with every shifted row put back: its role, the equip bonus where it belongs and the owned bonus
    from the copy the app ships (which matches the site for every title they share), else from the title page's
    "Owning it adds ..." sentence, else unknown ("—")."""
    if not any(shifted(t) for t in titles):
        return titles
    shipped = {t["name"]: t for t in json.loads((PKG_DATA / "global" / "titles.json").read_text(encoding="utf-8"))}
    out = []
    for t in titles:
        if shifted(t):
            said = re.search(r"Owning it adds (.+?) to your title collection bonus", t.get("earn") or "")
            owned = (shipped.get(t["name"]) or {}).get("owned") or (said.group(1) if said else None) or "—"
            t = {**t, "role": t.get("role") or t["equip"], "slot": t.get("slot") or ROLE_SLOTS[t["equip"]],
                 "equip": t.get("owned") or "—", "owned": owned}
        out.append(t)
    return out


def titles_data() -> list[dict]:
    """The title list the planners read: the user's synced copy (else the shipped one), shifted rows repaired."""
    return repaired(read_json("global", "titles.json"))


def catalog() -> list[dict]:
    out = []
    for t in titles_data():
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
    kinds = GUARD["pvp" if str(ctx.scenario).startswith("pvp") else "pve"]
    slots = {}
    for slot in SLOTS:
        rows, empty = [], None
        for t in cat:
            if t["slot"] != slot or not t["equip_stats"]:
                continue
            d = ctx.dps(loadout=_with_title(ctx, slot, t["equip_stats"], t["name"]))
            rows.append({"name": t["name"], "grade": t.get("grade"), "equip": t.get("equip"), "owned_bonus": t.get("owned"),
                         "how": t.get("earn") or t.get("how"), "category": t.get("category"), "slug": t.get("slug"),
                         "gain": d / base - 1, "owned": t["name"] in owned_set})
        if rows:
            empty = ctx.dps(loadout=_with_title(ctx, slot, {}, "no title")) / base - 1
        if not any(abs(r["gain"] - empty) > 1e-6 for r in rows):
            rows = []                                   # no title adds damage over an empty slot: +0 % says nothing
        rows.sort(key=lambda r: -r["gain"])
        cur = equipped.get(slot)
        cur_gain = next((r["gain"] for r in rows if cur and r["name"] == cur.get("name")), 0.0)
        for r in rows:                                  # gains against the equipped title
            r["gain"] -= cur_gain
        best_owned = next((r for r in rows if r["owned"]), None) if owned_set else None
        slots[slot] = {"equipped": cur and {"name": cur.get("name"), "grade": cur.get("grade"), "equip": cur.get("equip"),
                                             "owned_bonus": cur.get("owned"), "gain": 0.0},
                       "best_owned": best_owned, "best": rows[:top], "guard": None}
        if not rows:
            # No title of the slot adds damage (every Defense title): rank them by the damage they take off instead.
            guard = [{"name": t["name"], "grade": t.get("grade"), "equip": t.get("equip"), "owned_bonus": t.get("owned"),
                      "how": t.get("earn") or t.get("how"), "category": t.get("category"), "slug": t.get("slug"),
                      "cut": guard_of(t.get("equip"), kinds), "owned": t["name"] in owned_set}
                     for t in cat if t["slot"] == slot]
            guard = sorted((g for g in guard if g["cut"] > 0), key=lambda g: (-g["cut"], g["name"]))
            if guard:
                slots[slot]["guard"] = {
                    "kinds": list(kinds), "best": guard[:top],
                    "best_owned": next((g for g in guard if g["owned"]), None) if owned_set else None,
                    "equipped": guard_of((cur or {}).get("equip") or "", kinds) if cur else None}
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
