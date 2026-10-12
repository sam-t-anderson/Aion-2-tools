"""The crafting workshop must let players filter below Unique (the catalog already carries
Common/Rare/Epic recipes), filter by item type, and enter their mastery tier/level to see
what they can make. This guards the data coverage and the UI wiring."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
CATALOG = json.loads((STATIC / "crafting-catalog.json").read_text(encoding="utf-8"))
JS = (STATIC / "crafting.js").read_text(encoding="utf-8")

_GRADES = {11: "Common", 21: "Rare", 31: "Epic", 41: "Unique", 51: "Heroic"}


def test_catalog_has_recipes_below_unique():
    items = CATALOG["items"]
    tiers = {_GRADES.get(items.get(str(r.get("output")), {}).get("grade")) for r in CATALOG["recipes"].values()}
    # The data isn't Unique-only — lower tiers exist and must be reachable through the UI.
    assert {"Common", "Rare", "Epic"} <= tiers, tiers


def test_catalog_items_expose_a_derivable_type():
    import re
    types = set()
    for it in CATALOG["items"].values():
        m = re.search(r"/Item/([A-Za-z0-9]+)/", it.get("icon") or "")
        if m:
            types.add(m.group(1))
    assert {"Weapon", "Armor", "Accessory"} <= types, types


def test_recipes_carry_mastery_tier_and_level():
    sample = next(iter(CATALOG["recipes"].values()))
    assert "mastery_group" in sample and "mastery_level" in sample


def test_crafting_ui_wires_the_new_filters():
    # Rarity (tier) and item-type filters, and the "your mastery" tier/level inputs + craftable gate.
    for hook in ("data-tier", "data-type", "data-mytier", "data-mylevel", "data-craftable"):
        assert hook in JS, hook
    # The craftability check compares the player's tier/level to the recipe's requirement.
    assert "function canCraft" in JS and "mastery_level" in JS
    # Rarity options cover the full ladder, not just Unique+.
    assert "Common" in JS and "Rare" in JS and "Epic" in JS
