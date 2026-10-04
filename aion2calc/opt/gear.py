"""Gear, title, arcana and enchant recommendations driven by simulated stat weights."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..model.character import LABEL_MAP, parse_bonus_text

DATA = Path(__file__).resolve().parent.parent / "data"

#: Arcana slots and their two deity-stat variants (global client).
ARCANA = {
    "Chalice / Grail": {"Vigor or Frenzy": ("time", 20), "Magic or Purity": ("space", 20)},
    "Parchment": {"Vigor or Frenzy": ("life", 20), "Magic or Purity": ("destiny", 20)},
    "Compass": {"Vigor or Frenzy": ("freedom", 20), "Magic or Purity": ("death", 20)},
    "Bell": {"Vigor or Frenzy": ("justice", 20), "Magic or Purity": ("destruction", 20)},
    "Mirror": {"Vigor or Frenzy": ("illusion", 20), "Magic or Purity": ("wisdom", 20)},
}


def per_unit(weights: list[dict]) -> dict[str, float]:
    pu = {w["stat"]: w["per_unit"] for w in weights}
    pu.setdefault("amp_all", pu.get("amp_pve", 0.0))
    pu.setdefault("amp_boss", pu.get("amp_pve", 0.0))
    pu.setdefault("front_atk", pu.get("pve_atk", 0.0))
    pu.setdefault("precision", pu.get("death", 0.0))
    pu.setdefault("weapon_min", pu.get("attack", 0.0) / 2)
    for k in ("accuracy", "freedom", "space", "life", "destiny"):
        pu.setdefault(k, 0.0)
    pu.setdefault("attack_pct", pu.get("might", 0.0) * 1000)
    return pu


def value_of(stats: dict, pu: dict) -> float:
    return sum(pu.get(k, 0.0) * v for k, v in stats.items())


def _avg_range(text: str) -> tuple[float, bool]:
    nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,.]+", text)]
    pct = "%" in text
    return (sum(nums) / len(nums) if nums else 0.0), pct


def roll_priorities(pu: dict, items: dict | None = None) -> dict[str, list[dict]]:
    items = items or json.loads((DATA / "global" / "items.json").read_text(encoding="utf-8"))
    out = {}
    for slug, it in items.items():
        rows = []
        for r in it.get("random", []):
            if r["stat"] not in LABEL_MAP:
                continue
            field, scale = LABEL_MAP[r["stat"]]
            avg, pct = _avg_range(r["range"])
            if pct and scale == 1:
                continue
            v = pu.get(field, 0.0) * avg * scale
            rows.append({"stat": r["stat"], "range": r["range"], "chance": r["chance"], "dps": v})
        rows.sort(key=lambda x: -x["dps"])
        if rows:
            out[slug] = rows
    return out


def title_ranking(pu: dict, titles: list | None = None, top: int = 12) -> list[dict]:
    titles = titles or json.loads((DATA / "global" / "titles.json").read_text(encoding="utf-8"))
    rows = []
    for t in titles:
        st = parse_bonus_text(t["equip"])
        v = value_of(st, pu)
        if v > 0:
            rows.append({**t, "dps": v})
    rows.sort(key=lambda x: -x["dps"])
    seen, out = set(), []
    for r in rows:
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        out.append(r)
        if len(out) >= top:
            break
    return out


def arcana_choice(pu: dict) -> dict[str, dict]:
    out = {}
    for slot, variants in ARCANA.items():
        scored = {name: pu.get(stat, 0.0) * pts for name, (stat, pts) in variants.items()}
        best = max(scored, key=scored.get)
        out[slot] = {"pick": best, "stat": variants[best][0], "dps": scored}
    return out


def enchant_value(pu: dict) -> list[dict]:
    """DPS of one enchant level per slot (global enchant tables)."""
    rows = [
        {"slot": "Weapon (Spiritforged / Rupture)", "per_level": {"weapon_min": 5.5, "weapon_max": 5.5}},
        {"slot": "Guard (off-hand)", "per_level": {"attack": 5}},
        {"slot": "Necklace / Earrings / Rings (Aulamus)", "per_level": {"attack": 4}},
        {"slot": "Bracelets", "per_level": {"attack": 3}},
        {"slot": "Revelation Amulet", "per_level": {"pen": 30}},
        {"slot": "Armor pieces", "per_level": {}},
    ]
    for r in rows:
        r["dps"] = value_of(r["per_level"], pu)
    rows.sort(key=lambda x: -x["dps"])
    return rows
