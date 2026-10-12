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


def test_proficiency_tiers_are_named_and_banded_by_fifty():
    # The game reads proficiency as a tier plus a within-tier level, 50 per tier. The tier names must
    # be the in-game ones (Novice/Professional), not the source's coarse beginner/intermediate labels.
    assert "'Novice','Professional'" in JS
    # The old source-label tier array is gone (the word "intermediates" still appears in unrelated copy).
    assert "'beginner','intermediate'" not in JS and "MASTERY" not in JS
    assert "TIER_SPAN=50" in JS
    # The level field caps at 50 (per tier), never the old absolute 200.
    assert 'max="50"' in JS and 'max="200"' not in JS
    assert "function band" in JS and "tierLevelLabel" in JS


def _band(abs_level, span=50, tiers=("Novice", "Professional", "Expert", "Master")):
    rank = min(len(tiers) - 1, (max(1, abs_level) - 1) // span)
    return tiers[rank], max(1, abs_level) - span * rank


def test_star_dragon_lord_longsword_reads_as_professional_level_5():
    # The reference case from the report: absolute level 55 must present as Professional level 5
    # (55 - 50, since Novice fills the first 50 levels), not a bare "55".
    items = CATALOG["items"]
    recipe = next(r for r in CATALOG["recipes"].values()
                  if "star dragon lord longsword" in str(items.get(str(r.get("output")), {}).get("name", "")).lower())
    assert recipe["mastery_level"] == 55
    assert _band(recipe["mastery_level"]) == ("Professional", 5)
    # Every within-tier level the banding produces stays in 1..50.
    for r in CATALOG["recipes"].values():
        if isinstance(r.get("mastery_level"), int):
            _, within = _band(r["mastery_level"])
            assert 1 <= within <= 50, (r["mastery_level"], within)
