"""The advice's words (0.2.444), as pages/advice.js writes them: the top changes, the skill specialties, the paper doll
with each slot's way from what is worn to the best in slot, the upgrade path, and the fights and the model's
calibration. The view (``advice_view.py``) draws them; Gear & Advice shows it.
"""
from __future__ import annotations

import math

from .character import js_number
from .news import when
from .results import _dict, _list, cap, js_text, n0, pct, sp

DOLL_LEFT = ("MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt")
DOLL_RIGHT = ("Necklace", "Earring1", "Earring2", "Ring1", "Ring2", "Bracelet1", "Bracelet2", "Amulet", "Rune1", "Rune2")
ARCANA_SLOTS = ("Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror")
SLOT_NAME = {"MainHand": "Main hand", "SubHand": "Off-hand", "Torso": "Chest", "Pants": "Legs", "Cape": "Cloak",
             "Earring1": "Earring", "Earring2": "Earring", "Ring1": "Ring", "Ring2": "Ring", "Bracelet1": "Bracelet",
             "Bracelet2": "Bracelet", "Rune1": "Rune", "Rune2": "Rune"}
AREA_MARKS = {"titles": "❖", "gear (inventory)": "▲", "gear (upgrade)": "⇧", "arcana": "✦", "pantheon": "☉",
              "genus insight": "❖", "rotation": "↻", "specializations": "◎", "community": "☷"}
KIND_MARKS = {"enchant": "＋1", "reroll": "⟳", "replace": "⇄"}
SOURCES = {"session": "live meter sessions", "abysslogs": "AbyssLogs", "a2log": "saved logs", "a2dil": "A2DIL", "csv": "CSV"}
EQUIPMENT_SUB = "click a slot: what you wear → better from your inventory → next goal → best in slot"
PATH_SUB = "one change at a time, biggest gain first, toward the next goals; a reroll names the stats to chase"
SPECIALTIES_SUB = "recommended for your imported equipped build"
SPECIALTIES_OLD = "This older saved advice has no specialty snapshot. Recalculate advice to include it."
SPECIALTIES_NOTE = ("Effective levels include trained, Daevanion and gear bonuses. These are simulated recommendations; the "
                    "official profile does not show your selected specialties. An effect marked <b>either</b> is one the model "
                    "cannot tell from the skill's other open effects (a shield, a resource, range): it fills the slot, and the "
                    "choice is yours. Stigma effects activate automatically. Recalculate after changing gear or points.")
CALIBRATION_SUB = "learned from fights matched to equipped gear"
NOT_COMPARED = "Your fights could not be compared with the optimal rotation yet (run Optimize for this class once)."
NO_FIGHTS = ("No saved fights for this character yet. Record a boss fight with the live meter (the party sessions it saves are "
             "picked up here automatically) or import an AbyssLogs link on Combat Logs, then run advice again.")


def slot_name(slot) -> str:
    return SLOT_NAME.get(slot, js_text(slot))


def roll_text(r) -> str:
    """A roll as the advice lists it (``rollText``): {stat, range} (a roll to chase), [stat, value] or text."""
    if isinstance(r, dict):
        return f"{js_text(r.get('stat') or '')}{' ' + js_text(r['range']) if r.get('range') else ''}".strip()
    if isinstance(r, list):
        return " ".join(js_text(x) for x in r)
    return "" if r is None else js_text(r)


# ------------------------------------------------------------------ top changes
def top_subtitle(a: dict) -> str:
    return "ranked by simulated DPS gain" + (" · model calibrated from fights" if a.get("calibrated") else "")


def top_rows(a: dict) -> list[tuple[str, str, str, str]]:
    """Each change: its area's mark, its area, what it is and its gain (none when unmodelled)."""
    return [(AREA_MARKS.get(r.get("area"), "•"), js_text(r.get("area")), js_text(r.get("text")),
             "" if r.get("gain") is None else sp(r["gain"])) for r in _list(a.get("top")) if isinstance(r, dict)]


def top_copy(a: dict) -> str:
    return "\n".join(f"{area}: {text} {gain}" for _mark, area, text, gain in top_rows(a))


# ------------------------------------------------------------------ skill specialties
def specialty_rows(a: dict) -> list[dict] | None:
    """Each skill: its effective level, its slots (or automatic), the effects recommended, all effects, and the next
    unlock; none for advice saved before the snapshot."""
    rows = a.get("skill_specialties")
    if not rows:
        return None
    shown = []
    for r in _list(rows):
        if not isinstance(r, dict):
            continue
        effects = [e for e in _list(r.get("effects")) if isinstance(e, dict)]
        chosen = [(js_text(e.get("number")), js_text(e.get("text")),
                   f"effect Lv {js_text(e.get('unlock'))}" + (" · either" if e.get("free") else "")) for e in effects if e.get("selected")]
        every = [f"#{js_text(e.get('number'))} · Lv {js_text(e.get('unlock'))} · "
                 + ("Either" if e.get("selected") and e.get("free") else "Recommended" if e.get("selected")
                    else "Available" if e.get("available") else "Locked") + f": {js_text(e.get('text'))}" for e in effects]
        unlock = f"Effect Lv {js_text(r['next_effect_level'])}" if r.get("next_effect_level") else "All effects unlocked"
        if r.get("next_slot_level"):
            unlock += f"\nSelection slot Lv {js_text(r['next_slot_level'])}"
        shown.append({"skill": f"{js_text(r.get('skill'))} · Lv {js_text(r.get('level'))}",
                      "slots": "Automatic stigma effects" if r.get("automatic") else f"{js_text(r.get('slots'))} selection slot(s)",
                      "chosen": chosen, "every": every, "unlock": unlock})
    return shown


def specialties_copy(a: dict) -> str:
    lines = []
    for r in _list(a.get("skill_specialties")):
        if not isinstance(r, dict):
            continue
        chosen = [f"#{js_text(e.get('number'))}: {js_text(e.get('text'))} (effect Lv {js_text(e.get('unlock'))}"
                  f"{', either' if e.get('free') else ''})" for e in _list(r.get("effects")) if isinstance(e, dict) and e.get("selected")]
        lines.append(f"{js_text(r.get('skill'))} · effective Lv {js_text(r.get('level'))}: "
                     + ("; ".join(chosen) or "None unlocked/selected"))
    return "\n".join(lines)


# ------------------------------------------------------------------ the paper doll
def doll_tile(a: dict, slot: str) -> dict:
    """A slot's tile: the item worn (or the one to wear), its badge (a better item from the inventory, or the next
    goal's gain), and its first upgrade path step."""
    x = _dict(_dict(a.get("doll")).get(slot))
    item = x.get("worn") or x.get("wear") or None
    badge = None
    if x.get("wear") and x.get("wear_gain"):
        badge = ("up", f"▲ {sp(x['wear_gain'])}")
    elif x.get("next") and isinstance(_dict(x["next"]).get("gain"), (int, float)) and x["next"]["gain"] > 0.02:
        badge = ("goal", f"◆ {sp(x['next']['gain'])}")
    steps = _list(x.get("steps"))
    return {"slot": slot, "slot_name": slot_name(slot), "item": item, "name": js_text(_dict(item).get("name") or "empty"),
            "badge": badge, "step": f"#{js_text(steps[0])}" if steps else ""}


def doll_copy(a: dict) -> str:
    lines = []
    for slot, x in _dict(a.get("doll")).items():
        x = _dict(x)
        if not (x.get("wear") or x.get("next")):
            continue
        wear = f"wear {js_text(x['wear'].get('name'))} +{js_text(x['wear'].get('enchant'))}; " if x.get("wear") else ""
        nxt = ""
        if x.get("next"):
            rolls = _list(x["next"].get("rolls"))
            nxt = (f"next goal {js_text(x['next'].get('name'))}"
                   + (f" (roll toward {', '.join(roll_text(r) for r in rolls)})" if rolls else ""))
        lines.append(f"{slot}: {wear}{nxt}")
    return "\n".join(lines)


def first_slot(a: dict) -> str:
    """The slot shown first: one with a better item to wear, else one with a next goal, else the main hand."""
    doll = _dict(a.get("doll"))
    return (next((s for s, x in doll.items() if _dict(x).get("wear")), None)
            or next((s for s, x in doll.items() if _dict(x).get("next")), None) or "MainHand")


def item_card(item, label: str, gain=None) -> dict:
    """A card of the slot's way (``itemCard``): its label, the item's name (and page), level and enchant, and gain."""
    if not item:
        return {"label": label, "empty": True}
    item = _dict(item)
    meta = (f"iLv {js_text(item['item_level'])} · " if item.get("item_level") else "") + f"+{js_text(item.get('enchant') or 0)}"
    return {"label": label, "empty": False, "item": item, "name": js_text(item.get("name")), "url": item.get("url") or "",
            "meta": meta, "gain": None if gain is None else sp(gain), "down": isinstance(gain, (int, float)) and gain < 0}


def chips(item) -> list[tuple[str, bool]]:
    """An item's skill options (gold) and rolls, as chips."""
    if not item:
        return []
    item = _dict(item)
    return ([(f"{js_text(s[0] if isinstance(s, list) and s else None)} +{js_text(s[1] if isinstance(s, list) and len(s) > 1 else None)}", True)
             for s in _list(item.get("skills"))] + [(roll_text(r), False) for r in _list(item.get("rolls"))])


def chase(item) -> list[str]:
    """A goal's rolls to chase (its best roll stats, not rolls it has)."""
    return [roll_text(r) for r in _list(_dict(item).get("rolls"))] if item else []


def slot_way(a: dict, slot: str) -> dict:
    """A slot's way (``bindDoll``'s ``show``): what is worn, the better item from the inventory, the next goal (or why
    the item worn is kept), the best in slot, and its upgrade path steps."""
    x = _dict(_dict(a.get("doll")).get(slot))
    keep = None
    if not x.get("next") and x.get("keep"):
        keep = ("No replacement beats yours enchanted to +15 and rerolled toward good rolls "
                f"({sp(_dict(x['keep']).get('gain'))}): enchant and reroll it, as the upgrade path says.")
    steps = _list(x.get("steps"))
    return {"title": slot_name(slot).upper(),
            "worn": (item_card(x.get("worn"), "Wearing"), chips(x.get("worn"))),
            "wear": (item_card(x.get("wear"), "From your inventory", x.get("wear_gain")), chips(x.get("wear"))),
            "next": (item_card(x.get("next"), "Next goal", _dict(x.get("next")).get("gain") if x.get("next") else None),
                     chase(x.get("next"))),
            "keep": keep,
            "best": (item_card(x.get("best"), "Best in slot", _dict(x.get("best")).get("gain") if x.get("best") else None),
                     chase(x.get("best"))),
            "steps": f"Upgrade path steps for this slot: {', '.join('#' + js_text(n) for n in steps)}" if steps else ""}


# ------------------------------------------------------------------ the upgrade path
def path_steps(a: dict) -> list[dict]:
    steps = [s for s in _list(_dict(a.get("upgrade_path")).get("steps")) if isinstance(s, dict)]
    last = steps[-1].get("total_gain") if steps else 0
    top = max(0.0001, last if isinstance(last, (int, float)) else 0)
    shown = []
    for s in steps:
        total = s.get("total_gain") if isinstance(s.get("total_gain"), (int, float)) else 0
        shown.append({"step": f"#{js_text(s.get('step'))}", "slot": slot_name(s.get("slot")), "item": s.get("item") or None,
                      "mark": KIND_MARKS.get(s.get("kind"), ""), "kind": js_text(s.get("kind") or ""),
                      "name": js_text(_dict(s.get("item")).get("name") or ""), "action": js_text(s.get("action")),
                      "rolls": [roll_text(r) for r in _list(s.get("rolls"))], "gain": sp(s.get("gain")),
                      "total": sp(s.get("total_gain")), "share": min(100.0, 100 * total / top)})
    return shown


def path_copy(a: dict) -> str:
    return "\n".join(f"{js_text(s.get('step'))}. {js_text(s.get('slot'))}: {js_text(s.get('action'))} ({sp(s.get('gain'))})"
                     for s in _list(_dict(a.get("upgrade_path")).get("steps")) if isinstance(s, dict))


# ------------------------------------------------------------------ the fights and the calibration
def fights(a: dict) -> dict:
    """``fightsHTML``: how many fights were saved and from where, the rotation compared (idle time, what was cast too
    little, specialties that differ) or why not, the recent fights (each with its analysis's page on Combat Logs, when
    it was fought or else imported), and the note."""
    r, f = _dict(a.get("rotation")), _dict(a.get("fights")) if a.get("fights") else {"count": 0, "sources": {}, "recent": []}
    summary = ""
    if f.get("count"):
        sources = ", ".join(f"{js_text(n)} from {SOURCES.get(k, k)}" for k, n in _dict(f.get("sources")).items())
        synced = f" · {js_text(f['synced'])} new from your recorded sessions" if f.get("synced") else ""
        summary = f"{js_text(f['count'])} saved fight(s): {sources}{synced}."
    tips, compared, missing = [], "", ""
    if r.get("fights"):
        compared = (f"{js_text(r['fights'])} fight(s) compared with the optimal rotation; idle "
                    f"{pct(r.get('idle_share'), 0)} of the time.")
        tips = [js_text(t.get("text")) for t in _list(r.get("under_cast"))[:6] if isinstance(t, dict)]
        tips += [f"{js_text(d.get('skill'))}: specs {js_text(d.get('yours'))} in your fights, {js_text(d.get('optimal'))} "
                 "in the optimized build" for d in _list(r.get("specs")) if isinstance(d, dict)]
    else:
        missing = NOT_COMPARED if f.get("count") else NO_FIGHTS
    recent = []
    for x in _list(f.get("recent")):
        if not isinstance(x, dict):
            continue
        duration, dps = x.get("duration") or 0, x.get("dps") or 0
        started, imported = x.get("started_at"), x.get("imported_at")
        recent.append({"id": x.get("id"), "boss": js_text(x.get("boss") or "fight"),
                       "page": "" if x.get("id") is None else f"combat-log/analysis/{js_text(x['id'])}",
                       "length": f"{_round(duration)} s", "dps": f"{_round(dps):,}",
                       "source": SOURCES.get(x.get("source"), js_text(x.get("source") or "")),
                       "when": when(started) if started else when(js_number(imported) * 1000) if imported else ""})
    return {"summary": summary, "compared": compared, "tips": tips, "missing": missing, "recent": recent,
            "note": js_text(f.get("note")) if f.get("note") else ""}


def _round(x) -> int:
    """``Math.round``: halves up."""
    try:
        return math.floor(float(x) + 0.5)
    except (TypeError, ValueError):
        return 0


def calibration(a: dict) -> list[str]:
    return [js_text(x) for x in _list(a.get("calibration"))]


def character_lines(a: dict) -> tuple[str, str, str]:
    """The doll's middle: the class, who and where, and the boss DPS."""
    c = _dict(a.get("character"))
    return cap(c.get("class")), f"{js_text(c.get('name'))} · {js_text(c.get('server'))}", n0(a.get("dps"))
