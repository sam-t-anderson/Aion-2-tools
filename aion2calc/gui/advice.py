"""The advice's words (0.2.444), as pages/advice.js writes them: the top changes, the skill specialties, the paper doll
with each slot's way from what is worn to the best in slot, the upgrade path, and the fights and the model's
calibration. The view (``advice_view.py``) draws them; Gear & Advice shows it.
"""
from __future__ import annotations

import math
import re

from .character import js_number
from .news import when
from . import theme
from .results import (GENERA, _dict, _entries, _list, _number, _truthy, _whole_number, arcana_deity, cap, js_text,
                      n0, pct, sp)

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
# ------------------------------------------------------------------ arcana
ARCANA_SUB = "variant per slot, the skill options to chase (icons = target levels), and your arcana"
CATALOG_DEITY = "the variant's stat at this grade (catalog)"


def skill_icon(skill_id) -> str:
    """A skill's picture by its id (``SKILL_ICON``)."""
    return f"https://metabot.gg/web/aion2/skills/{js_text(skill_id)}.webp" if _truthy(skill_id) else ""


def _arcana_slots(a: dict) -> list[tuple[str, dict]]:
    """The arcana slots the advice holds, in the game's order."""
    slots = _dict(_dict(a.get("arcana")).get("slots"))
    return [(slot, _dict(slots[slot])) for slot in ARCANA_SLOTS if _truthy(slots.get(slot))]


def _enchant(x: dict) -> str:
    return js_text(0 if x.get("enchant") is None else x["enchant"])


def arcana_owned(o, ids: dict) -> dict:
    """A card you have, under YOURS (``arcanaOwned``): keep or replace with its gain, then what it holds: its deity
    stat (its own, or its variant's from the catalog), its other stats, its skill options and its facts."""
    o = _dict(o)
    keep = o.get("verdict") == "keep"
    mine = _dict(o.get("skill_ids"))
    options = _dict(o.get("options"))
    where = "equipped" if o.get("equipped") is True else "in your inventory" if o.get("equipped") is False else ""
    facts = [x for x in (js_text(o.get("grade") or ""),
                         f"{js_text(options.get('used'))} of {js_text(options.get('of'))} option levels"
                         if _truthy(o.get("options")) and _truthy(options.get("of")) else "", where) if x]
    deity = _dict(o.get("deity"))
    return {"item": o, "name": f"{js_text(o.get('name'))} +{_enchant(o)}", "gain": sp(o.get("gain")), "keep": keep,
            "deity": arcana_deity(deity) if _truthy(o.get("deity")) else "",
            "deity_tip": CATALOG_DEITY if deity.get("source") == "catalog" else "this card's stat",
            "stats": ", ".join(f"{js_text(row[0] if row else None)} {js_text(row[1] if len(row) > 1 else None)}"
                               for row in _list(o.get("stats")) if isinstance(row, list)),
            "options": [(js_text(k), js_text(lv), skill_icon(mine.get(k) or ids.get(k)))
                        for k, lv in _entries(_dict(o.get("skills")))],
            "facts": " · ".join(facts)}


def arcana_cards(a: dict) -> list[dict]:
    """Each arcana slot's card (``advArcana``): its variant with its deity stat and priority, the skill options to
    chase at their target levels, its ideal and average gains, and the cards you have."""
    priority = _list(_dict(a.get("arcana")).get("priority"))
    cards = []
    for slot, x in _arcana_slots(a):
        v = _dict(x.get("variant"))
        ids, ideal = _dict(x.get("skill_ids")), _dict(x.get("ideal"))
        cards.append({"slot": slot.replace("Arcana ", "", 1).upper(),
                      "priority": f"#{priority.index(slot) + 1 if slot in priority else 0}",
                      "grade": v.get("grade") or "Unique", "item": {**v, "enchant": 5}, "name": js_text(v.get("name") or ""),
                      "deity": f"{js_text(v.get('deity') or '')} +{js_text('' if v.get('points') is None else v['points'])}",
                      "options": [(js_text(k), js_text(lv), skill_icon(ids.get(k))) for k, lv in _entries(_dict(ideal.get("skills")))],
                      "ideal": sp(ideal.get("gain")), "average": sp(_dict(x.get("expected")).get("unique_5")),
                      "owned": [arcana_owned(o, ids) for o in _list(x.get("owned"))]})
    return cards


def arcana_copy(a: dict) -> str:
    lines = []
    for slot, x in _arcana_slots(a):
        v = _dict(x.get("variant"))
        deity = (f" ({js_text(v.get('deity'))} +{js_text('' if v.get('points') is None else v['points'])})"
                 if v.get("deity") else "")
        skills = ", ".join(f"{js_text(k)} +{js_text(lv)}" for k, lv in _entries(_dict(_dict(x.get("ideal")).get("skills"))))
        lines.append(f"{slot}: {js_text(v.get('name'))}{deity} — {skills}")
        for o in _list(x.get("owned")):
            o = _dict(o)
            held = ", ".join(f"{js_text(k)} +{js_text(lv)}" for k, lv in _entries(_dict(o.get("skills"))))
            deity_text = f", {arcana_deity(o['deity'])}" if _truthy(o.get("deity")) else ""
            lines.append(f"  yours: {js_text(o.get('name'))} +{_enchant(o)}{deity_text} — {held or 'no skill options'} "
                         f"({sp(o.get('gain'))}, {'keep' if o.get('verdict') == 'keep' else 'replace'})")
    return "\n".join(lines)


# ------------------------------------------------------------------ titles
TITLES_SUB = ("the equipped bonus of each slot's title, its owned bonus under it, and titles worth collecting for their "
              "owned bonus")
NO_DAMAGE_TITLE = "No title for this slot adds damage."
COLLECT_HEAD = "WORTH COLLECTING (owned bonus)"


def _cut(share) -> str:
    """The damage a Defense title takes off the attacker's hits."""
    x = _number(share)
    return f"−{'NaN' if x is None else f'{100 * x:.1f}'}% damage taken"


def title_plate(t, label: str, extra: list[tuple[str, str]] | None = None) -> dict:
    """A title's plate (``titlePlate``): its name, its equip bonus (only while in a slot) and owned bonus (as soon as
    it is yours), its gain (not for the one equipped), and how to earn it, shortened. ``extra`` holds a Defense title's
    cut (``cut``) and the owned chip (``owned``)."""
    if not _truthy(t):
        return {"label": label, "empty": True}
    t = _dict(t)
    how = js_text(t.get("how")) if t.get("how") else ""
    gain = t.get("gain")
    return {"label": label, "empty": False, "grade": t.get("grade") or "", "name": f"❖ {js_text(t.get('name'))} ❖",
            "equip": js_text(t["equip"]) if t.get("equip") and t["equip"] != "—" else "",
            "owned": js_text(t["owned_bonus"]) if t.get("owned_bonus") and t["owned_bonus"] != "—" else "",
            "gain": None if gain is None or label == "Equipped" else (sp(gain), not (_number(gain) is not None and _number(gain) < 0)),
            "how": re.split(r"\. How to get it", re.sub(r"^You earn it by ", "", how, count=1))[0][:110] if how else "",
            "how_full": how, "extra": list(extra or [])}


def _guard(t: dict, x: dict) -> dict:
    """A slot no title adds damage to (``guardCol``): ranked by what its titles take off a boss's (or another
    player's) hits."""
    g = x.get("guard")
    if not _truthy(g):
        return {"note": NO_DAMAGE_TITLE, "plates": []}
    g = _dict(g)
    kinds = [js_text(k) for k in _list(g.get("kinds"))]
    who = "another player's" if "PvP Damage Tolerance" in kinds else "a boss's"
    yours = f"; yours: {_cut(g['equipped']).replace(' damage taken', '')}" if g.get("equipped") is not None else ""
    plates = []
    if _truthy(t.get("owned_known")):
        best_owned = g.get("best_owned")
        plates.append(title_plate(best_owned, "Best you own", [("cut", _cut(_dict(best_owned).get("cut")))]
                                  if _truthy(best_owned) else []))
    for i, r in enumerate(_list(g.get("best"))):
        extra = [("cut", _cut(_dict(r).get("cut")))] + ([("owned", "owned")] if _dict(r).get("owned") else [])
        plates.append(title_plate(r, "" if i else "Best", extra))
    return {"note": f"{NO_DAMAGE_TITLE} Ranked by how much they cut {who} damage ({', '.join(kinds)}){yours}.",
            "plates": plates}


def title_columns(a: dict) -> list[dict] | None:
    """The three title slots (``advTitles``): what is equipped, the best you own, and the best in slot; none when the
    advice has no titles."""
    t = a.get("titles")
    if not _truthy(t):
        return None
    t = _dict(t)
    columns = []
    for slot in ("Attack", "Defense", "Etc"):
        x = _dict(_dict(t.get("slots")).get(slot))
        best = _list(x.get("best"))
        plates = [title_plate(x.get("equipped"), "Equipped")]
        if _truthy(t.get("owned_known")) and best:
            plates.append(title_plate(x.get("best_owned"), "Best you own"))
        ranked = [title_plate(r, "" if i else "Best", [("owned", "owned")] if _dict(r).get("owned") else [])
                  for i, r in enumerate(best[:3])]
        columns.append({"title": f"{'Other' if slot == 'Etc' else slot} title".upper(), "plates": plates,
                        "guard": None if best else _guard(t, x), "best": ranked})
    return columns


def titles_collect(a: dict) -> list[dict]:
    """The titles worth collecting for their owned bonus."""
    return [title_plate({**_dict(c), "equip": ""}, "Collect") for c in _list(_dict(a.get("titles")).get("collect"))]


def titles_note(a: dict) -> str:
    note = _dict(a.get("titles")).get("note")
    return js_text(note) if note else ""


def titles_copy(a: dict) -> str:
    t = _dict(a.get("titles"))
    lines = []
    for slot in ("Attack", "Defense", "Etc"):
        x = _dict(_dict(t.get("slots")).get(slot))
        guard = _dict(x.get("guard"))
        best, guard_best = _list(x.get("best")), _list(guard.get("best"))
        pick = next((p for p in (x.get("best_owned"), best[0] if best else None, guard.get("best_owned"),
                                 guard_best[0] if guard_best else None) if _truthy(p)), {})
        lines.append(f"{slot}: {js_text(_dict(pick).get('name') or '-')}")
    return "\n".join(lines)


# ------------------------------------------------------------------ pantheon
LORDS = {"Destruction [Zikel]": ("Zikel", "#d9534f"), "Death [Triniel]": ("Triniel", "#9b59b6"),
         "Wisdom [Lumiel]": ("Lumiel", "#5bc0de"), "Time [Siel]": ("Siel", "#f0ad4e"),
         "Illusion [Kaisinel]": ("Kaisinel", "#8e7cc3"), "Justice [Nezekan]": ("Nezekan", "#e8cf8e"),
         "Freedom [Vaizel]": ("Vaizel", "#5cb85c"), "Life [Yustiel]": ("Yustiel", "#7fd6a8"),
         "Destiny [Marchutan]": ("Marchutan", "#c0a16b"), "Space [Israphel]": ("Israphel", "#6fa8dc")}
DEITY_FX = {"Destruction [Zikel]": "Attack, Perfect Resist", "Death [Triniel]": "Critical Hit, Regen Penetration",
            "Wisdom [Lumiel]": "Double chance, MP cost", "Time [Siel]": "Combat Speed, Double Resist",
            "Illusion [Kaisinel]": "Cooldown, Endurance Penetration", "Justice [Nezekan]": "Perfect chance, Defense",
            "Freedom [Vaizel]": "Accuracy, Evasion", "Life [Yustiel]": "HP, Regeneration",
            "Destiny [Marchutan]": "MP, Endurance", "Space [Israphel]": "Move Speed, Block"}
KIND_LABEL = {"colossus": "Colossus", "statue": "Statue", "artwork": "Artwork"}
PANTHEON_SUB = "deity stats: points you have, what 10 more points are worth, and the decorations to place"
BOARD_HEAD = "RECOMMENDED BOARD · colossus, statues, artworks"
BOARD_NOTE = ("The decorations worth placing, by modeled damage on your build (the collection itself is not in the official "
              "profile). Hover a stand for the piece's deity points and where it comes from.")
RINGS = (("colossus", "COLOSSUS · centre"), ("statue", "STATUES · inner ring"), ("artwork", "ARTWORKS · outer ring"))
NO_DECORATION = "No catalogued decoration with a known effect."
# a decoration's grade in its name's colour (``.prow[data-grade]``): the game's names for them are not the items'
DECORATION_COLOURS = theme.Shades({"Heroic": theme.Shade("g_epic"), "Unique": theme.Shade("g_unique"),
                                   "Epic": theme.Shade("g_legend"), "Rare": theme.Shade("g_rare")})   # app.css .prow[data-grade]
DECOR_ICON = re.compile(r"https://aion2hub\.com/api/icon/items/[0-9]{1,12}")


def deity_short(deity) -> str:
    return js_text(deity).split(" [")[0]


def decor_icon(r) -> str:
    """A decoration's picture (``decorIcon``): the game's item icon from aion2hub.com, by item id; none for anything
    else."""
    url = js_text(_dict(r).get("icon") or "")
    return url if DECOR_ICON.fullmatch(url) else ""


def _stats(r: dict, joiner: str = ", ") -> str:
    return joiner.join(f"{deity_short(k)} +{js_text(v)}" for k, v in _entries(_dict(r.get("stats"))))


def deity_tiles(a: dict) -> list[dict]:
    """The ten deities (``advPantheon``'s tiles): each one's sigil and lord, your points, its effects, what 10 more
    points are worth against the best, and whether it is the best for damage."""
    p = _dict(a.get("pantheon"))
    per_point = [r for r in _list(p.get("per_point")) if isinstance(r, dict)]
    values = [_number(r.get("gain_per_point")) for r in per_point]
    top = max([x for x in values if x is not None] + [1e-9])
    current = _dict(p.get("current"))
    tiles = []
    for deity, (lord, colour) in LORDS.items():
        r = next((x for x in per_point if x.get("deity") == deity), {})
        worth = _number(r.get("gain_per_point")) or 0.0
        tiles.append({"deity": deity.split(" [")[0], "lord": lord.upper(), "sigil": lord[0], "colour": colour,
                      "points": js_text(0 if current.get(deity) is None else current[deity]), "fx": DEITY_FX[deity],
                      "share": max(0.0, 100 * worth / top), "worth": f"{sp(10 * worth)} / 10",
                      "best": deity == p.get("best"), "dim": not r.get("field")})
    return tiles


def deity_choices(a: dict) -> list[dict]:
    """The arcana's deity choices: where from, the pick and its deity, and its gain."""
    return [{"source": js_text(c.get("source")), "pick": js_text(c.get("pick")), "deity": js_text(c.get("deity") or ""),
             "gain": sp(c.get("gain"))} for c in _list(_dict(a.get("pantheon")).get("choices")) if isinstance(c, dict)]


def stand_tip(r) -> str:
    """A stand's words when hovered (``tip``): the piece's kind and name, its deity points, its gain and its sources."""
    if not _truthy(r):
        return ""
    r = _dict(r)
    sources = "; ".join(js_text(x) for x in _list(r.get("sources"))) or "source unknown"
    return f"{KIND_LABEL.get(r.get('kind'), js_text(r.get('kind')))}: {js_text(r.get('short'))} — {_stats(r)} · {sp(r.get('gain'))} · {sources}"


def shortened(name, n: int) -> str:
    """A name cut to ``n`` characters with an ellipsis (``short``)."""
    name = js_text(name or "")
    return name[:n - 1] + "…" if len(name) > n else name


def board_stands(board: dict) -> dict:
    """The board's stands (``pantheonBoardHTML``): the colossus, the four statues and the twelve artworks, each with
    its piece (or none), picture, words and tip."""
    b = _dict(_dict(board).get("board"))

    def stand(r, kind: str, number: int, n: int, empty: str) -> dict:
        piece = _dict(r) if _truthy(r) else None
        return {"set": piece is not None, "icon": decor_icon(piece) if piece else "",
                "name": shortened(piece.get("short"), n) if piece else "",
                "points": f"+{js_text(piece.get('points'))}" if piece else empty,
                "tip": stand_tip(piece) if piece else f"{KIND_LABEL[kind]} stand{'' if kind == 'colossus' else ' ' + str(number)}: no candidate"}
    colossi, statues, artworks = _list(b.get("colossus")), _list(b.get("statue")), _list(b.get("artwork"))
    return {"colossus": stand(colossi[0] if colossi else None, "colossus", 1, 16, "Colossus"),
            "statues": [stand(statues[i] if i < len(statues) else None, "statue", i + 1, 14, f"stand {i + 1}") for i in range(4)],
            "artworks": [stand(artworks[i] if i < len(artworks) else None, "artwork", i + 1, 11, "") for i in range(12)]}


def decoration_row(r) -> dict:
    """A decoration in the board's list (``pantheonListHTML``'s ``row``)."""
    r = _dict(r)
    sources = "; ".join(js_text(x) for x in _list(r.get("sources"))) or "source not listed in the catalog"
    return {"icon": decor_icon(r), "name": js_text(r.get("short")), "grade": js_text(r.get("grade") or ""),
            "colour": DECORATION_COLOURS.get(r.get("grade"), ""), "faction": js_text(r.get("faction") or ""),
            "stats": [(deity_short(k), f"+{js_text(v)}") for k, v in _entries(_dict(r.get("stats")))],
            "gain": sp(r.get("gain")), "sources": sources}


def board_list(board: dict) -> dict:
    """The board's list: its deity totals, its gain against an empty board, each ring's pieces and next best, and the
    catalog's note."""
    b = _dict(board)
    placed, slots, runners = _dict(b.get("board")), _dict(b.get("slots")), _dict(b.get("runners_up"))
    totals = sorted(_entries(_dict(b.get("totals"))), key=lambda kv: -(_number(kv[1]) or 0))
    rings = [{"kind": kind, "head": f"{title} · {len(_list(placed.get(kind)))}/{js_text(slots.get(kind))}",
              "rows": [decoration_row(r) for r in _list(placed.get(kind))],
              "next_head": f"Next best {KIND_LABEL[kind].lower()}s", "next": [decoration_row(r) for r in _list(runners.get(kind))]}
             for kind, title in RINGS]
    catalog = _dict(b.get("catalog"))
    candidates = _dict(catalog.get("candidates"))
    count = {k: js_text(0 if candidates.get(k) is None else candidates[k]) for k in KIND_LABEL}
    faction = (f" (your faction: {js_text(b['faction'])})" if b.get("faction")
               else " (faction unknown: both factions' pieces shown)")
    note = (f"{js_text(b.get('note') or '')} {js_text(catalog['images']) + '.' if catalog.get('images') else ''} Candidates: "
            f"{count['colossus']} colossi, {count['statue']} statues, {count['artwork']} artworks with a known effect{faction}.")
    return {"totals": [(deity_short(k), js_text(v), js_text(k)) for k, v in totals], "gain": sp(b.get("gain")),
            "rings": rings, "note": note}


def pantheon_copy(a: dict) -> str:
    p = _dict(a.get("pantheon"))
    lines = [f"{js_text(r.get('deity'))}: {sp(10 * (_number(r.get('gain_per_point')) or 0))} per 10"
             for r in _list(p.get("per_point")) if isinstance(r, dict)]
    board = p.get("board")
    if _truthy(board):
        lines.append("")
        placed = _dict(_dict(board).get("board"))
        for kind in KIND_LABEL:
            for r in _list(placed.get(kind)):
                r = _dict(r)
                sources = "; ".join(js_text(x) for x in _list(r.get("sources")))
                lines.append(f"{KIND_LABEL[kind]}: {js_text(r.get('short'))} ({_stats(r)}) {sp(r.get('gain'))} — {sources}")
    return "\n".join(lines)


# ------------------------------------------------------------------ genus insight
GENUS_SUB = ("pet genus lines: what each slot can roll, what to roll for, and your saved lines weighted by your fight time "
             "per genus")
GENUS_NOTE = ("Genus levels and analysis lines are manual inputs; they are not included in the official profile. Enter and "
              "save them in the Genus Insight editor above, then run advice again. Blank slots are not recorded, not evidence "
              "of a locked Insight. \"Roll for\" lines come from the Global slot property tables and are modeled damage on your "
              "build, whether or not you recorded anything.")
ROLLS_FOLD = "All slots · what each can roll and what to aim for"
ROLLS_COLUMNS = ["Slot", "Roll for (best listed grade)", "Then", "Options"]
NO_CANDIDATE = "No modeled candidate for this genus."
CHASE_NOTE = "Damage-only candidate; confirm the defensive tradeoff in game."


def genus_state(a: dict, inventory=None) -> dict:
    """The genus lines the advice used (``g.state``), else those of the inventory it was given or the page's."""
    g = _dict(a.get("genus"))
    if _truthy(g.get("state")):
        return _dict(g["state"])
    inv = a.get("inventory_snapshot") if _truthy(a.get("inventory_snapshot")) else inventory
    return _dict(_dict(inv).get("genus")) if _truthy(inv) and _truthy(_dict(inv).get("genus")) else {}


def genus_tab(a: dict, chosen=None) -> str:
    """The genus shown (``S.gear.genusTab``): the one chosen, else the first to level, else Cogni."""
    if chosen:
        return chosen
    order = _list(_dict(a.get("genus")).get("level_order"))
    first = _dict(order[0]).get("genus") if order and _truthy(order[0]) else None
    return first or "Cogni"


def _known(state: dict, genus) -> int | None:
    return _whole_number(_dict(state.get(genus)).get("level"))


def genus_tabs(state: dict) -> list[tuple[str, str]]:
    """The five genera's tabs, each with its recorded level."""
    return [(x, "Not recorded" if _known(state, x) is None else f"Lv {js_text(state[x]['level'])}") for x in GENERA]


def _rolls(a: dict, genus: str):
    rolls = _dict(_dict(_dict(a.get("genus")).get("roll_targets")).get("genera")).get(genus)
    return _dict(rolls) if _truthy(rolls) else None


def _aim(row) -> tuple[str, str, str] | None:
    """A roll's stat, grade and range, and gain."""
    row = _dict(row)
    return js_text(row.get("stat")), f"{js_text(row.get('grade'))} {js_text(row.get('range'))}", sp(row.get("gain"))


def genus_cells(a: dict, state: dict, genus: str) -> list[dict]:
    """The chosen genus's nine slots (``advGenus``'s ``cells``): locked (and what to roll for once open), not recorded
    (what to roll for, or the line to chase in slot 4), or the line saved with its modeled gain and whether it is the
    best line for its slot."""
    g = _dict(a.get("genus"))
    group = state.get(genus)
    st = _dict(group) if _truthy(group) else {"level": 0, "lines": []}
    scored = {}
    for line in _list(g.get("lines")):
        if isinstance(line, dict) and line.get("genus") == genus:
            scored[js_text(line.get("slot"))] = line
    chase = next((c for c in _list(g.get("chase")) if isinstance(c, dict) and c.get("genus") == genus), None)
    rolls = _rolls(a, genus)
    known = _known(state, genus) is not None
    cells = []
    for n in range(1, 10):
        line = next((x for x in _list(st.get("lines")) if isinstance(x, dict) and js_number(x.get("slot")) == n), None)
        score = scored.get(str(n))
        x = _dict(_dict(rolls.get("slots")).get(str(n))) if rolls else {}
        aims = _list(x.get("aim"))
        aim = _dict(aims[0]) if aims and _truthy(aims[0]) else None
        more = ", ".join(f"{js_text(_dict(r).get('stat'))} ({js_text(_dict(r).get('grade'))} {js_text(_dict(r).get('range'))}, "
                         f"{sp(_dict(r).get('gain'))})" for r in aims[1:3])
        title = (f"Roll for: {js_text(aim.get('stat'))} {js_text(aim.get('grade'))} {js_text(aim.get('range'))} "
                 f"({sp(aim.get('gain'))})" + (f"; then {more}" if more else "")) if aim is not None else ""
        cell = {"n": str(n), "special": n == 4, "title": title}
        level = _number(st.get("level"))
        if known and level is not None and n > level:
            cell.update(kind="locked", text=f"opens at Lv {n}",
                        aim=f"then roll for {js_text(aim.get('stat'))}" if aim is not None else "")
        elif line is None:
            cell.update(kind="empty", aimed=aim is not None, text="Not recorded" if known else "Level not entered",
                        aim=_aim(aim) if aim is not None else None,
                        possible=f"Possible line: {js_text(chase.get('line'))}" if aim is None and n == 4 and chase else "")
        else:
            gain = _number(_dict(score).get("gain")) if score is not None and score.get("gain") is not None else None
            dead = gain is not None and gain <= 1e-6
            if gain is None:
                shown = ("note", js_text(_dict(score).get("reason") or "Not modeled"))
            elif dead:
                shown = ("down", "No modeled damage gain")
            else:
                shown = ("up", f"+{theme.fixed(100 * gain, 2)}%" if gain < 0.001 else sp(gain))
            verdict = None
            if aim is not None:
                verdict = (("keep", "✓ best modeled line for this slot") if line.get("stat") == aim.get("stat")
                           else ("reroll", _aim(aim)))
            cell.update(kind="filled", stat=js_text(line.get("stat")), value=js_text(line.get("value")), gain=shown, dead=dead,
                        verdict=verdict)
        cells.append(cell)
    return cells


def genus_side(a: dict, state: dict, genus: str) -> dict:
    """The genus's side (``.gside``): what to roll for first, the basis, your fight time per genus, the line to chase,
    and the order to level the genera in."""
    g = _dict(a.get("genus"))
    rolls = _rolls(a, genus)
    best = None
    if rolls is not None and _truthy(rolls.get("best")):
        best = [(js_text(_dict(r).get("slot")),) + _aim(r) for r in _list(rolls.get("best"))]
    basis = f"{js_text(_dict(g.get('roll_targets')).get('basis') or '')}. Gains are not additive across slots."
    mix = [(js_text(k), _number(v) or 0.0, f"{js_text(k)} {pct(v, 0)}") for k, v in _entries(_dict(g.get("mix")))]
    chase = next((c for c in _list(g.get("chase")) if isinstance(c, dict) and c.get("genus") == genus), None)
    shown_chase = None
    if chase is not None:
        shown_chase = {"line": f"{js_text(chase.get('line'))} · slot {js_text(chase.get('slot'))}", "value": js_text(chase.get("value")),
                       "gain": sp(chase.get("gain")), "note": f"{js_text(chase.get('assumption'))}. {CHASE_NOTE}"}
    order = []
    for i, r in enumerate(_list(g.get("level_order"))[:5]):
        r = _dict(r)
        nxt = _dict(r.get("next"))
        step = ("" if not _truthy(r.get("next")) else f" · next opens slot {js_text(nxt['opens_slot'])}" if nxt.get("opens_slot")
                else " · next changes grade chances")
        level = js_text(r.get("level")) if _known(state, r.get("genus")) is not None else "not recorded"
        order.append((f"{i + 1}. {js_text(r.get('genus'))}", f"Lv {level} · {pct(r.get('share'), 0)} of fights{step}"))
    return {"best": best, "basis": basis, "mix": mix, "chase": shown_chase, "order": order}


def genus_rolls_table(a: dict, genus: str) -> list[dict] | None:
    """Every slot of the genus (``.grolls``): what to roll for, the next two, and how many options it has."""
    rolls = _rolls(a, genus)
    if rolls is None:
        return None
    rows = []
    for n, x in _entries(_dict(rolls.get("slots"))):
        x = _dict(x)
        aims = _list(x.get("aim"))
        rows.append({"slot": js_text(n), "amp": js_number(n) == 4, "aim": _aim(aims[0]) if aims and _truthy(aims[0]) else None,
                     "then": [(js_text(_dict(y).get("stat")), sp(_dict(y).get("gain"))) for y in aims[1:3]],
                     "options": f"{js_text(x.get('options'))} ({js_text(x.get('unmodeled'))} unmodeled)"})
    return rows


def genus_copy(a: dict, genus: str) -> str:
    g = _dict(a.get("genus"))
    lines = []
    for row in genus_rolls_table(a, genus) or []:
        aim = row["aim"]
        lines.append(f"{genus} slot {row['slot']}: roll for "
                     + (f"{aim[0]} ({aim[1]}, {aim[2]})" if aim else "no modeled line"))
    for line in _list(g.get("lines")):
        line = _dict(line)
        gain = line.get("gain")
        lines.append(f"{js_text(line.get('genus'))} slot {js_text(line.get('slot'))}: {js_text(line.get('stat'))} "
                     f"{js_text(line.get('value'))} ({js_text(line.get('reason') or 'Not modeled') if gain is None else sp(gain)})")
    return "\n".join(lines)


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
