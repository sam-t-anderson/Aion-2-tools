"""Gear planning on simulated DPS.

``best_equip``    the best set from your inventory (what to wear now)
``goal_gear``     the best catalog items per slot at a goal enchant with good rolls
``upgrade_path``  ordered upgrades from what you wear toward the goal: enchant
                  steps, rerolls and replacements, each with its DPS gain
"""
from __future__ import annotations

from ..db import store
from . import items as I
from .context import PlanContext
from .inventory import candidates, catalog_item, entry_stats

PAIRS = {"Earring1": "Earring2", "Ring1": "Ring2", "Bracelet1": "Bracelet2", "Rune1": "Rune2"}


def _label(e: dict | None) -> str | None:
    if not e:
        return None
    return f"{e.get('name')} +{e.get('enchant', 0)}" + (" (equipped)" if e.get("source") == "equipped" else "")


def best_equip(ctx: PlanContext, inv: dict, passes: int = 3) -> dict:
    """Choose an item per slot from ``inv`` by coordinate descent on simulated DPS.

    Each entry is used once (two identical rings need two entries).
    """
    cls = ctx.cls
    choice = dict(ctx.equipped)
    base = ctx.dps(choice)
    cands = {s: candidates(inv, s, cls) for s in I.SLOTS}
    val = ctx.value()
    for s, lst in cands.items():                       # strongest first: fewer evaluations to converge
        lst.sort(key=lambda e: -val(entry_stats(e, cls, value=val)[0]))
    best = base
    for _ in range(passes):
        improved = False
        for slot, lst in cands.items():
            if not lst:
                continue
            used = {id(e) for s, e in choice.items() if s != slot and e is not None}
            for e in lst[:12]:
                if id(e) in used or choice.get(slot) is e:
                    continue
                trial = {**choice, slot: e}
                d = ctx.dps(trial)
                if d > best * (1 + 1e-6):
                    best, choice, improved = d, trial, True
        if not improved:
            break
    changes = []
    for slot in I.SLOTS:
        new, old = choice.get(slot), ctx.equipped.get(slot)
        if new is not None and new is not old:
            alone = ctx.dps({**ctx.equipped, slot: new})
            changes.append({"slot": slot, "from": _label(old), "to": _label(new), "entry": new.get("id"),
                            "gain": alone / base - 1})
    return {"current_dps": base, "best_dps": best, "gain": best / base - 1 if base else 0.0,
            "changes": sorted(changes, key=lambda c: -c["gain"]),
            "choice": {s: (e.get("id") if e else None) for s, e in choice.items()},
            "empty_slots": [s for s in I.SLOTS if not cands[s] and s not in ctx.equipped]}


def _catalog_for(slot: str, cls: str, level: int) -> list[dict]:
    conn = store.connect()
    cats = I.SLOTS[slot]
    cat = I.WEAPON.get(cls) if "weapon" in cats else cats[0]
    rows = conn.execute("SELECT slug FROM items WHERE category=?", (cat,)).fetchall()
    out = []
    for (slug,) in rows:
        it = store.item(conn, slug)
        if not it:
            continue
        req = I._numbers((it.get("meta") or {}).get("Required Level", "0"))
        if req and req[0] > level:
            continue
        out.append(it)
    return out


def goal_gear(ctx: PlanContext, enchant: int | None = None, top: int = 3, prefilter: int = 25) -> dict:
    """Catalog items per slot, each at ``enchant`` (default: its max, up to +15)
    with good rolls, swapped alone into the current set.

    Per slot: ``best`` (highest gain) and ``next`` (the lowest item level that
    still gains at least 2%: the nearer goal). Arcana are planned by
    :mod:`aion2calc.plan.arcana` (their value is in the skill options).
    """
    cls, val = ctx.cls, ctx.value()
    base = ctx.dps(ctx.equipped)
    out = {}
    for slot in I.SLOTS:
        if slot in PAIRS.values() or slot in I.ARCANA_SLOTS:
            continue                                    # the pair's first slot stands for both
        rows, seen = [], set()
        for it in _catalog_for(slot, cls, ctx.level):
            if it["name"] in seen:
                continue
            seen.add(it["name"])
            lv = min(I.max_enchant(it), 15 if enchant is None else enchant)
            st = I.item_stats(it, lv, "good", val, main_hand=slot == "MainHand")
            rows.append((val(I.split_deity(st)[0]), it, lv))
        rows.sort(key=lambda r: -r[0])
        scored = []
        for _, it, lv in rows[:prefilter]:
            e = {"source": "goal", "slug": it["slug"], "name": it["name"], "category": it.get("category"),
                 "grade": it.get("grade"), "item_level": it.get("item_level"), "enchant": lv, "rolls": None}
            gear, deity, sb = entry_stats(e, cls, reroll=True, value=val)
            d = ctx.dps({**ctx.equipped, slot: e}, overrides={slot: (gear, deity, sb)})
            scored.append({"slot": slot, "slug": it["slug"], "name": it["name"], "grade": it.get("grade"),
                           "icon": it.get("icon"), "item_level": it.get("item_level"), "enchant": lv, "gain": d / base - 1,
                           "url": f"https://metabot.gg/en/aion-2/items/{it['slug']}", "entry": e,
                           "stats": gear, "deity": deity})
        scored.sort(key=lambda r: -r["gain"])
        if not scored:
            continue
        better = [r for r in scored if r["gain"] >= 0.02]
        nxt = min(better, key=lambda r: (r["item_level"] or 0, -r["gain"])) if better else None
        out[slot] = {"best": scored[:top], "next": nxt}
    return {"current_dps": base, "slots": out}


def upgrade_path(ctx: PlanContext, goals: dict | None = None, steps: int = 12, enchant_cap: int = 15,
                 target: str = "next") -> dict:
    """Greedy upgrade order from the equipped set: at every step the single change
    (one enchant level, a reroll to good rolls, or the slot's goal item) with
    the biggest simulated gain. ``target`` picks the goal per slot: ``next``
    (nearer) or ``best``."""
    cls, val = ctx.cls, ctx.value()
    goals = goals or goal_gear(ctx)["slots"]
    goals = {s: ([g["next"]] if g.get("next") else []) if target == "next" else g["best"][:1]
             for s, g in goals.items()}
    state = {s: {"entry": e, "enchant": e.get("enchant") or 0, "reroll": False}
             for s, e in ctx.equipped.items()}
    for s, g in goals.items():
        for slot in (s, PAIRS.get(s)):
            if slot and slot not in state:
                state[slot] = None

    def overrides(st):
        ov, ch = {}, {}
        for slot, x in st.items():
            if not x:
                continue
            ch[slot] = x["entry"]
            if x["enchant"] != (x["entry"].get("enchant") or 0) or x["reroll"] or x["entry"].get("source") == "goal":
                ov[slot] = entry_stats(x["entry"], cls, enchant=x["enchant"], reroll=x["reroll"], value=val)
        return ch, ov

    ch, ov = overrides(state)
    start = cur = ctx.dps(ch, ov)
    path = []
    for _ in range(steps):
        options = []
        for slot, x in state.items():
            if x:
                it = catalog_item(x["entry"].get("slug"))
                if it and x["enchant"] < min(I.max_enchant(it), enchant_cap):
                    options.append((slot, {**x, "enchant": x["enchant"] + 1, "kind": "enchant"},
                                    f"enchant {x['entry']['name']} to +{x['enchant'] + 1}"))
                if it and not x["reroll"] and I.roll_count(it) > 0 and x["entry"].get("source") != "goal":
                    options.append((slot, {**x, "reroll": True, "kind": "reroll"},
                                    f"reroll {x['entry']['name']} toward good rolls"))
            g = (goals.get(slot) or goals.get(next((k for k, v in PAIRS.items() if v == slot), ""), []) or [None])[0]
            if g and (not x or x["entry"].get("slug") != g["slug"]):
                e = dict(g["entry"])
                start_lv = min(x["enchant"] if x else 0, g["enchant"])
                options.append((slot, {"entry": {**e, "icon": g.get("icon")}, "enchant": start_lv, "reroll": True,
                                       "kind": "replace"},
                                f"replace with {g['name']} (+{start_lv}, good rolls)"))
        best = None
        for slot, nx, label in options:
            trial = {**state, slot: nx}
            c, o = overrides(trial)
            d = ctx.dps(c, o)
            if best is None or d > best[0]:
                best = (d, slot, nx, label)
        if not best or best[0] <= cur * (1 + 1e-5):
            break
        d, slot, nx, label = best
        state[slot] = nx
        ent = nx["entry"]
        path.append({"step": len(path) + 1, "slot": slot, "action": label, "gain": d / cur - 1,
                     "total_gain": d / start - 1, "dps": d, "kind": nx.get("kind"),
                     "item": {"name": ent.get("name"), "grade": ent.get("grade"), "icon": ent.get("icon"),
                              "enchant": nx["enchant"], "slug": ent.get("slug")}})
        cur = d
    return {"start_dps": start, "end_dps": cur, "steps": path}
