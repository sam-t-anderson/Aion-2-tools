"""Item names for the gathering and loot records: what a numeric item id is called, its category and grade.

The meter reads items by number (``33 8d`` gathers, ``15 57`` reward cubes). The bundled ``item-names.json``
(staged from DBAion2's English item table by ``aion2calc item-names``, see ``scrape/item_names.py``) names
them; the crafting catalog names a few it may lack.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
import re

#: Categories of crafting materials: a reward cube's materials, as the Gathering page lists them.
MATERIAL_CATEGORIES = frozenset({"GATHERRESOURCE", "CRAFTRESOURCE", "MATERIAL"})
#: The game's grades from plain to best, as the items show them; a gather's "better" result gives a later one.
GRADES = ("Common", "Rare", "Epic", "Unique", "Heroic", "Special")
_GRADE_WORDS = re.compile(r"^(Fine|Pure|Radiant)\s+")
_BOUND = re.compile(r"\s*\(Bound\)$")


@lru_cache(maxsize=1)
def _table() -> dict:
    try:
        data = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "item-names.json").read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, dict) else {}
    except (OSError, ValueError, ModuleNotFoundError):
        return {}


@lru_cache(maxsize=1)
def _crafting() -> dict:
    try:
        data = json.loads(files("aion2calc.app").joinpath("static", "crafting-catalog.json").read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, dict) else {}
    except (OSError, ValueError, ModuleNotFoundError):
        return {}


def item_info(item) -> dict:
    """``{"name", "category", "grade"}`` for an item id, as far as it is known; ``{}`` for an unknown one."""
    key = str(item)
    row = _table().get(key)
    if isinstance(row, list) and row and isinstance(row[0], str):
        return {"name": row[0], "category": row[1] if len(row) > 1 else "", "grade": row[2] if len(row) > 2 else ""}
    crafted = _crafting().get(key)
    if isinstance(crafted, dict) and isinstance(crafted.get("name"), str):
        return {"name": crafted["name"], "category": "", "grade": ""}
    return {}


def item_name(item) -> str:
    """An item's name, or "Item <id>" for one the tables do not know."""
    return item_info(item).get("name") or f"Item {item}"


def is_material(item) -> bool:
    """Whether an item is a crafting material (gathered, crafting or special material)."""
    return item_info(item).get("category") in MATERIAL_CATEGORIES


def base_material(item) -> str:
    """The material a gathering node gives, whatever the grade: "Orichalcum Ore" for a Fine Orichalcum Ore."""
    return _BOUND.sub("", _GRADE_WORDS.sub("", item_name(item)))
