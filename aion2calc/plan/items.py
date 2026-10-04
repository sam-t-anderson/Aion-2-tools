"""Equipment slots and the stats of a catalog item at an enchant level.

Slot names follow the official character page (``MainHand``, ``Earring1``…).
A catalog item (``aion2.db``, synced from metabot) gives its stats as text; this
module turns them into :class:`~aion2calc.model.stats.Stats` fields.
"""
from __future__ import annotations

import re

from ..model.character import LABEL_MAP

#: official slot -> catalog categories that fit it ("weapon" = the class weapon)
SLOTS: dict[str, tuple[str, ...]] = {
    "MainHand": ("weapon",), "SubHand": ("Guard",),
    "Helmet": ("Helm",), "Torso": ("Top",), "Shoulder": ("Pauldrons",), "Gloves": ("Gloves",),
    "Pants": ("Legs",), "Boots": ("Shoes",), "Cape": ("Cloak",), "Belt": ("Belt",),
    "Necklace": ("Necklace",), "Earring1": ("Earrings",), "Earring2": ("Earrings",),
    "Ring1": ("Ring",), "Ring2": ("Ring",), "Bracelet1": ("Bracelet",), "Bracelet2": ("Bracelet",),
    "Amulet": ("Amulet",), "Rune1": ("Rune",), "Rune2": ("Rune",),
    "Arcana Chalice": ("Chalice",), "Arcana Parchment": ("Parchment",), "Arcana Compass": ("Compass",),
    "Arcana Bell": ("Bell",), "Arcana Mirror": ("Mirror",),
}
ARCANA_SLOTS = tuple(s for s in SLOTS if s.startswith("Arcana "))
ARCANA_CATEGORIES = tuple(SLOTS[s][0] for s in ARCANA_SLOTS)
#: catalog weapon category per class
WEAPON = {"gladiator": "Greatsword", "templar": "Longsword", "assassin": "Dagger", "ranger": "Bow",
          "sorcerer": "Spellbook", "spiritmaster": "Orb", "cleric": "Mace", "chanter": "Staff"}

#: deity stat labels -> Stats field (None: no effect on damage)
DEITY_LABELS = {"Destruction [Zikel]": "destruction", "Death [Triniel]": "death", "Wisdom [Lumiel]": "wisdom",
                "Justice [Nezekan]": "justice", "Time [Siel]": "time", "Illusion [Kaisinel]": "illusion",
                "Freedom [Vaizel]": "freedom", "Life [Yustiel]": None, "Destiny [Marchutan]": None,
                "Space [Israphel]": None}
DEITY_FIELDS = ("destruction", "death", "wisdom", "justice", "time", "illusion", "freedom", "might", "precision")


def slot_of_category(category: str, cls: str) -> list[str]:
    cat = "weapon" if category == WEAPON.get(cls) else category
    return [s for s, cats in SLOTS.items() if cat in cats]


def fits(item: dict, slot: str, cls: str) -> bool:
    cats = SLOTS[slot]
    if "weapon" in cats:
        return item.get("category") == WEAPON.get(cls)
    return item.get("category") in cats


def _numbers(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", text or "")]


def _label_value(label: str, value: str, main_hand: bool) -> dict:
    """One 'Label' + 'value text' pair -> Stats fields."""
    label = label.strip()
    nums = _numbers(value)
    if not nums:
        return {}
    pct = "%" in value
    if len(nums) >= 2:
        nums = [abs(x) for x in nums]
    if label in ("Max Attack", "Attack") and len(nums) >= 2:       # weapon damage range "206–229"
        return {"weapon_min": nums[0], "weapon_max": nums[1]} if main_hand else {"attack": sum(nums) / 2}
    if label == "Max Attack":
        return {"weapon_min": nums[0], "weapon_max": nums[0]} if main_hand else {"attack": nums[0]}
    if label in DEITY_LABELS:
        f = DEITY_LABELS[label]
        return {f: nums[0]} if f else {}
    if label not in LABEL_MAP:
        return {}
    field, scale = LABEL_MAP[label]
    if pct and scale == 1:
        return {}
    return {field: nums[0] * scale}


def parse_stat_text(text: str, main_hand: bool = False) -> dict:
    """'Attack +39, Defense +99, Damage Boost +1%' or 'Max Attack 50' -> Stats fields."""
    out: dict = {}
    for part in re.split(r",\s*", text or ""):
        m = re.match(r"(.+?)\s*([+-]?\d[\d,.]*%?)$", part.strip())
        if m:
            _add(out, _label_value(m.group(1), m.group(2), main_hand))
    return out


def _add(dst: dict, src: dict, k: float = 1.0) -> dict:
    for key, v in src.items():
        dst[key] = dst.get(key, 0.0) + v * k
    return dst


def enchant_stats(item: dict, level: int, main_hand: bool = False) -> dict:
    """Stats an item gains at ``+level`` (the catalog lists cumulative totals per step;
    steps past +15 restart from the +15 total)."""
    if level <= 0:
        return {}
    steps = {}
    for e in item.get("enchant") or []:
        nums = _numbers(e.get("step", ""))
        if len(nums) >= 2:
            steps[int(nums[1])] = e.get("stats", "")
    out: dict = {}
    if level > 15 and 15 in steps:
        _add(out, parse_stat_text(steps[15], main_hand))
    lv = max((k for k in steps if k <= level and (level <= 15 or k > 15)), default=None)
    if lv is not None:
        _add(out, parse_stat_text(steps[lv], main_hand))
    return out


def max_enchant(item: dict) -> int:
    nums = _numbers((item.get("meta") or {}).get("Max enhance", ""))
    return int(max(nums)) if nums else 0


def roll_count(item: dict) -> int:
    m = re.search(r"rolls (\d+) random", item.get("description") or "")
    return int(m.group(1)) if m else 0


def roll_options(item: dict) -> list[dict]:
    """Random roll pool: [{stat, fields (at the middle of the range), chance}]."""
    out = []
    for r in item.get("random") or []:
        nums = _numbers(r.get("range", ""))
        if not nums:
            continue
        mid = sum(nums) / len(nums)
        val = f"{mid}{'%' if '%' in r.get('range', '') else ''}"
        f = _label_value(r["stat"], val, False)
        ch = _numbers(r.get("chance", "0"))
        out.append({"stat": r["stat"], "range": r.get("range"), "fields": f, "chance": ch[0] / 100 if ch else 0.0})
    return out


def roll_stats(item: dict, mode: str = "expected", value=None, rolls: list | None = None) -> dict:
    """Stats from random rolls.

    ``rolls`` (``[[stat, value], …]``) are the item's actual rolls. Otherwise
    ``mode`` is ``expected`` (average over the pool), ``good`` (the most
    valuable distinct stats at mid range, scored by ``value(fields)``) or ``none``.
    Items that roll 0 random stats list fixed sub-stats in the pool; those always count.
    """
    if rolls is not None:
        out: dict = {}
        for stat, v in rolls:
            _add(out, _label_value(str(stat), str(v), False))
        return out
    opts = roll_options(item)
    n = roll_count(item)
    if n == 0:
        out = {}
        for o in opts:
            _add(out, o["fields"])
        return out
    if mode == "none" or not opts:
        return {}
    if mode == "good" and value is not None:
        best = sorted(opts, key=lambda o: -value(o["fields"]))
        out, seen = {}, set()
        for o in best:
            if o["stat"] in seen:
                continue
            seen.add(o["stat"])
            _add(out, o["fields"])
            if len(seen) >= n:
                break
        return out
    tot = sum(o["chance"] for o in opts) or float(len(opts))
    out = {}
    for o in opts:
        _add(out, o["fields"], n * (o["chance"] or 1.0) / tot)
    return out


def item_stats(item: dict, enchant: int = 0, mode: str = "expected", value=None, rolls: list | None = None,
               main_hand: bool | None = None) -> dict:
    """Fixed + enchant + random-roll stats of a catalog item (deity points included)."""
    if main_hand is None:
        main_hand = item.get("category") in WEAPON.values()
    out: dict = {}
    for label, v in (item.get("fixed") or {}).items():
        _add(out, _label_value(label, str(v), main_hand))
    _add(out, enchant_stats(item, enchant, main_hand))
    _add(out, roll_stats(item, mode, value, rolls))
    return out


def split_deity(stats: dict) -> tuple[dict, dict]:
    """(stats without deity/primary points, the deity/primary points)."""
    gear = {k: v for k, v in stats.items() if k not in DEITY_FIELDS}
    deity = {k: v for k, v in stats.items() if k in DEITY_FIELDS}
    return gear, deity
