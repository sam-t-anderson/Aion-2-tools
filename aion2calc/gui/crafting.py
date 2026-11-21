"""The Crafting workshop's arithmetic (0.2.432), as static/crafting.js (``A2Crafting``) works it out for the web page:
the recipes' proficiency tiers, the filters and the recipe list, where you stand against a recipe and its community
success rate, the item stats with an enhancement preview, a recipe's material plan, the combo checks and their
illustrative scenario, and the plan's export. The native page (``crafting_page.py``) draws it.

The catalog is the app's dated, source-attributed recipe snapshot (``static/crafting-catalog.json``) and the success
rates its optional community dataset (``static/crafting-success.json``); nothing here is guessed beyond what the web
page itself says it assumes.
"""
from __future__ import annotations

import html
import math
import re

from . import theme
from .news import when

GRADES = {11: "Common", 21: "Rare", 31: "Epic", 41: "Unique", 51: "Heroic"}
GRADE_ORDER = ("Common", "Rare", "Epic", "Unique", "Heroic")
#: A proficiency is one number in the source (a recipe's ``mastery_level``, e.g. 55) that reads in game as a tier and
#: a level within it, 50 levels a tier: Novice 1–50, Professional 51–100, Expert 101–150, Master 151–200.
TIERS = ("Novice", "Professional", "Expert", "Master")
TIER_SPAN = 50
TYPE_LABELS = {"Weapon": "Weapon", "Armor": "Armor", "Accessory": "Accessory", "ETC": "Material / other"}
SHOWN = 80                                       # recipes listed at once
MAX_CRAFTS, MAX_SEED, MAX_OWNED = 10000, 4294967295, 10 ** 12
SAFE = 2 ** 53 - 1                               # JavaScript's Number.MAX_SAFE_INTEGER
SOURCE_ICON = re.compile(r"^https://gamers4\.life/aion-2/database/icons/assets/Game/[A-Za-z0-9_/-]+\.webp$")
SOURCE_ITEM = re.compile(r"^https://gamers4\.life/aion-2/database/db/item/en/[1-9][0-9]{0,18}\.json$")
SOURCE_RECIPE = "https://gamers4.life/aion-2/database/en/recipe/{}/"
TYPE_IN_ICON = re.compile(r"/Item/([A-Za-z0-9]+)/")
COMBO_WARNING = ("Combo-capable intermediates remain shopping-list items because normal/combo replacement semantics "
                 "are unknown.")
TOO_DEEP = "Recipe expansion exceeds its bounded depth/work limit. Use direct materials."
CYCLE = "Recipe cycle detected. Use direct materials."
TOO_LARGE = "Material plan exceeds safe numeric limits."
ASSUMPTIONS = ("Materials/fees assume every planned craft completes and consumes the listed inputs. General success, "
               "failures/refunds and modifier rules are unavailable. Intermediate branches round separately to whole "
               "normal-output crafts; surplus is not credited. These are planning assumptions, not guaranteed shopping "
               "requirements.")
OWNED_NOTE = ("Entered owned quantities subtract only from final material rows; they do not change recipe counts or "
              "fees. Nothing is uploaded or persisted automatically.")
STATS_NOTE = ("Preview uses base stats plus the listed bonus for the selected enhancement. Random rolls and "
              "breakthrough bonuses are excluded. Source values follow the publisher's display units; unrecognized stat "
              "IDs remain raw.")
COMMUNITY = "community-measured (metabot.gg), not official"


class PlanError(Exception):
    """A material plan that cannot be worked out, in the web page's words."""


def n(value) -> str:
    """crafting.js ``n``: a count or amount in the computer's language, to at most three places."""
    return theme.number(value, 3)


def js_text(value) -> str:
    """A number as JavaScript writes it in a sentence (``${x}``): 99 rather than 99.0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


def _number(value) -> float:
    """JavaScript's ``Number(x)`` for what a catalog holds: NaN for what does not read as one."""
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def js_number(text: str) -> float:
    """JavaScript's ``Number(text)`` for what a field holds: blank reads 0, and what does not read is NaN."""
    text = str(text).strip()
    if not text:
        return 0.0
    if "_" in text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def _whole(x: float) -> bool:
    return math.isfinite(x) and x.is_integer()


def _safe(value) -> bool:
    """``Number.isSafeInteger``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not value.is_integer():
        return False
    return abs(value) <= SAFE


# ------------------------------------------------------------------ tiers and levels
def band(absolute) -> tuple[int, str, int]:
    """A proficiency as its tier's rank, its tier and its level within the tier (``band``): 55 is Professional 5."""
    x = _number(absolute)
    a = max(1, theme.js_round(x if x and not math.isnan(x) else 1))
    rank = min(len(TIERS) - 1, (a - 1) // TIER_SPAN)
    return rank, TIERS[rank], a - TIER_SPAN * rank


def tier_level(absolute) -> str:
    """``tierLevelLabel``: "Professional level 45"."""
    _rank, tier, level = band(absolute)
    return f"{tier} level {level}"


def tier_rank(name) -> int:
    return TIERS.index(name) if name in TIERS else 0


def my_proficiency(my_tier: str, my_level: str):
    """Your one proficiency number from the tier and level entered (``myAbs``), or None while no level is entered
    (nothing to compare); a tier left blank reads as Novice."""
    if my_level == "":
        return None
    return TIER_SPAN * tier_rank(my_tier or TIERS[0]) + int(js_number(my_level))


# ------------------------------------------------------------------ items
def item(catalog: dict, item_id) -> dict:
    found = (catalog.get("items") or {}).get(item_id)
    return found if isinstance(found, dict) else {"name": item_id}


def item_name(catalog: dict, item_id) -> str:
    return str(item(catalog, item_id).get("name") or "")


def grade_name(catalog: dict, item_id) -> str:
    return GRADES.get(item(catalog, item_id).get("grade"), "")


def type_of(catalog: dict, item_id) -> str:
    """The item's kind from its icon's path (``typeOf``): Weapon, Armor, Accessory or ETC."""
    found = TYPE_IN_ICON.search(str(item(catalog, item_id).get("icon") or ""))
    return found.group(1) if found else ""


def type_label(kind: str) -> str:
    return TYPE_LABELS.get(kind, kind)


def icon(catalog: dict, item_id) -> str:
    """The item's picture's address when it is one of the source's own (the web page draws ◇ otherwise)."""
    url = str(item(catalog, item_id).get("icon") or "")
    return url if SOURCE_ICON.match(url) else ""


def faction_name(faction) -> str:
    return "Elyos" if faction == "light" else "Asmodian"


def can_craft(recipe: dict, mine) -> bool:
    """Whether a crafter at your proficiency can attempt the recipe; with no level entered, every recipe."""
    return True if mine is None else mine >= _number(recipe.get("mastery_level"))


# ------------------------------------------------------------------ the filters and the list
def professions(catalog: dict) -> list[str]:
    return sorted({str(r.get("profession")) for r in (catalog.get("recipes") or {}).values()})


def kinds(catalog: dict) -> list[str]:
    return sorted({kind for r in (catalog.get("recipes") or {}).values() if (kind := type_of(catalog, r.get("output")))})


def profession_meta(catalog: dict, profession: str = "") -> dict:
    """What the profession makes (every recipe's when none is chosen), so the filters offer only that: its rarities,
    item kinds, tiers, and each tier's highest level (``profMeta``)."""
    grades, types, tier_max = set(), set(), {}
    for r in (catalog.get("recipes") or {}).values():
        if profession and r.get("profession") != profession:
            continue
        if grade := grade_name(catalog, r.get("output")):
            grades.add(grade)
        if kind := type_of(catalog, r.get("output")):
            types.add(kind)
        level = r.get("mastery_level")
        if isinstance(level, int) and not isinstance(level, bool):
            _rank, tier, within = band(level)
            tier_max[tier] = max(tier_max.get(tier, 0), within)
    return {"grades": [g for g in GRADE_ORDER if g in grades], "types": sorted(types),
            "tiers": [t for t in TIERS if t in tier_max], "tier_max": tier_max}


def level_cap(meta: dict, my_tier: str) -> int:
    """The highest level to enter for the tier: the profession's own highest there, else the tier's 50."""
    return meta["tier_max"].get(my_tier) or TIER_SPAN if my_tier else TIER_SPAN


def fit_filters(meta: dict, rarity: str, kind: str, my_tier: str, my_level: str) -> tuple[str, str, str, str]:
    """The choices the profession still offers (``renderFilters``): a rarity, kind or tier it does not make is
    dropped, and the level kept within the tier's cap."""
    rarity = rarity if rarity in meta["grades"] else ""
    kind = kind if kind in meta["types"] else ""
    my_tier = my_tier if my_tier in meta["tiers"] else ""
    cap = level_cap(meta, my_tier)
    if my_level != "" and js_number(my_level) > cap:
        my_level = str(cap)
    return rarity, kind, my_tier, my_level


def level_entry(text: str, cap: int, previous: str) -> str:
    """The level field after a keystroke: blank, or a whole number from 1 to the cap; anything else keeps what was
    there."""
    x = js_number(text)
    return text if text == "" or (_whole(x) and 1 <= x <= cap) else previous


def matching(catalog: dict, search: str = "", profession: str = "", faction: str = "", rarity: str = "", kind: str = "",
             craftable_only: bool = False, mine=None) -> list[tuple[str, dict]]:
    """The recipes the filters and search let through, in the catalog's order (``results``)."""
    term = search.lower()
    rows = []
    for recipe_id, r in (catalog.get("recipes") or {}).items():
        if profession and r.get("profession") != profession or faction and r.get("faction") != faction:
            continue
        if rarity and grade_name(catalog, r.get("output")) != rarity or kind and type_of(catalog, r.get("output")) != kind:
            continue
        if craftable_only and not can_craft(r, mine):
            continue
        if search in recipe_id or term in item_name(catalog, r.get("output")).lower():
            rows.append((recipe_id, r))
    return rows


def recipe_line(catalog: dict, recipe: dict, my_level: str, mine) -> str:
    """A listed recipe's line under its name."""
    line = (f"{grade_name(catalog, recipe.get('output')) or '—'} · {recipe.get('profession')} · "
            f"{faction_name(recipe.get('faction'))} · {tier_level(recipe.get('mastery_level'))}")
    if my_level != "":
        line += " · ✓ you can craft" if can_craft(recipe, mine) else " · locked for you"
    return line


def count_line(count: int) -> str:
    return f"{count} matching recipes; showing up to {SHOWN}. Filter or search to narrow the list."


def heading(catalog: dict, recipe_id: str, recipe: dict) -> str:
    """The line under the recipe's name: rarity, kind, profession, faction, proficiency and recipe."""
    kind = type_of(catalog, recipe.get("output"))
    return (f"{grade_name(catalog, recipe.get('output')) or '—'} · {type_label(kind) or 'item'} · {recipe.get('profession')}"
            f" · {faction_name(recipe.get('faction'))} · {tier_level(recipe.get('mastery_level'))} · recipe {recipe_id}")


def source_line(catalog: dict) -> str:
    """The catalog's counts, date and fingerprint, with its source's link (rich text)."""
    page = str(catalog.get("source_page") or "")
    link = (f" · <a href='{html.escape(page, quote=True)}' style='color: {theme.COLORS['accent']};'>Gamers4Life source</a>"
            if page.startswith("https://") else "")
    return html.escape(f"{len(catalog.get('recipes') or {})} recipes · {len(catalog.get('items') or {})} source item "
                       f"references · retrieved {when(catalog.get('retrieved_at'))} · source SHA256 "
                       f"{str(catalog.get('source_sha256') or '')[:16]}") + link + "."


# ------------------------------------------------------------------ where you stand
def standing(recipe: dict, my_tier: str, my_level: str, mine) -> tuple[str, str]:
    """Whether you can make the recipe and by how much (rich text), and how it reads: "muted", "ok" or "note"."""
    if mine is None:
        return "muted", "Enter your crafting tier and level above to see whether you can make this and your level margin."
    need = html.escape(tier_level(recipe.get("mastery_level")))
    you = html.escape(f"{my_tier or TIERS[0]} level {my_level}")
    margin = mine - _number(recipe.get("mastery_level"))
    if margin >= 0:
        by = "exactly at" if margin == 0 else f"+{js_text(margin)} above"
        return "ok", (f"You can craft this: your {you} is {by} the required <b>{need}</b>. The exact success rate isn't "
                      "published in the source; a larger margin is typically easier.")
    short = -margin
    return "note", (f"You're {js_text(short)} level{'' if short == 1 else 's'} short: this needs <b>{need}</b> and you "
                    f"entered {you}.")


def success_line(catalog: dict, recipe: dict, success, mine) -> tuple[str, str]:
    """The recipe's community-measured success rate, and how it rises as you out-level it (``successLine``): rich text
    and how it reads ("muted" when the dataset has none)."""
    rates = success.get("recipes") if isinstance(success, dict) else None
    measured = rates.get(item_name(catalog, recipe.get("output")).lower()) if isinstance(rates, dict) else None
    if not isinstance(measured, dict):
        return "muted", "Success rate: not available for this recipe in the community dataset."
    source = f"<span style='color: {theme.COLORS['muted']};'>{COMMUNITY}</span>"
    base = _number(measured.get("base_success"))
    cap = 99 if base >= 90 else 96.8 if base >= 78 else 94.6 if base >= 75 else 93.1
    need = _number(measured.get("mastery"))
    need_label = html.escape(tier_level(measured.get("mastery")))
    shown = js_text(measured.get("base_success"))
    if mine is None or mine < need:
        return "", (f"Success rate: <b>{shown}%</b> at the required proficiency ({need_label}), rising toward "
                    f"~{js_text(cap)}% as you out-level it. {source}.")
    diff = mine - need
    if diff == 0:
        return "", f"Success rate: <b>{shown}%</b> at your proficiency. {source}."
    projected = min(cap, base + (cap - base) * min(diff, 42) / 42)
    return "", (f"Success rate: <b>{shown}%</b> at the requirement ({need_label}); <b>~{theme.fixed(projected, 1)}%</b> "
                f"estimated at your +{js_text(diff)} proficiency (projected toward the ~{js_text(cap)}% cap). Base "
                f"{source}; the projection is an estimate.")


# ------------------------------------------------------------------ item stats
def stat_label(catalog: dict, stat: str) -> str:
    return str(((catalog.get("stat_display") or {}).get("labels") or {}).get(stat) or stat)


def stat_value(catalog: dict, stat: str, value) -> str:
    """A stat as the source displays it: a percent stat in hundredths."""
    percent = (catalog.get("stat_display") or {}).get("percent") or []
    return n(_number(value) / 100) + "%" if stat in percent else n(value)


def item_stats(catalog: dict, item_id, level: int = 0):
    """An item's stats as the source lists them (``outputStats``), with the enhancement preview at ``level``; None
    where the source record is unavailable."""
    details = (catalog.get("item_details") or {}).get(item_id)
    if not isinstance(details, dict) or details.get("status") == "unavailable":
        return None
    levels = [row for row in details.get("enhancements") or [] if isinstance(row, dict)]
    bonus = next((row.get("stats") or {} for row in levels if row.get("level") == level), {})
    base = details.get("base") or {}
    keys = list(dict.fromkeys([*base, *bonus]))
    rows = [(stat_label(catalog, key), stat_value(catalog, key, base.get(key) or 0),
             stat_value(catalog, key, bonus.get(key) or 0),
             stat_value(catalog, key, _number(base.get(key) or 0) + _number(bonus.get(key) or 0))) for key in keys]
    rolls = [(stat_label(catalog, row.get("id")), f"{stat_value(catalog, row.get('id'), row.get('min'))} – "
              f"{stat_value(catalog, row.get('id'), row.get('max'))}") for row in details.get("rolls") or [] if isinstance(row, dict)]
    item_level = (details.get("equipment") or {}).get("itemLevel")
    source = str(details.get("source") or "")
    return {"title": "Item stats" + (f" · item level {n(item_level)}" if item_level else ""),
            "variant": details.get("variant") or "", "levels": [row.get("level") for row in levels], "level": level,
            "rows": rows, "rolls": rolls, "effect": details.get("effect_reference") or "",
            "source": source if SOURCE_ITEM.match(source) else ""}


def enhancement_levels(catalog: dict, item_id) -> list:
    details = (catalog.get("item_details") or {}).get(item_id)
    return [row.get("level") for row in (details or {}).get("enhancements") or [] if isinstance(row, dict)]


# ------------------------------------------------------------------ the material plan
def plan(catalog: dict, selected: str, count: int, expand: bool = False, stock: dict | None = None) -> dict:
    """The recipe's materials for ``count`` completed crafts (``plan``): each final material with what you own and
    what remains, the listed fees, the recipe branches and the warnings. With ``expand``, an input made by a recipe of
    the same faction without combo outcomes is planned through that recipe. Raises ``PlanError`` past its bounds."""
    recipes, stock = catalog.get("recipes") or {}, stock or {}
    leaves: dict = {}
    steps, warnings = [], []
    state = {"fee": 0, "visits": 0}

    def walk(recipe_id, times, path):
        state["visits"] += 1
        if state["visits"] > 5000 or len(path) > 20:
            raise PlanError(TOO_DEEP)
        if recipe_id in path:
            raise PlanError(CYCLE)
        r = recipes[recipe_id]
        fee = r.get("fee")
        state["fee"] = state["fee"] + fee * times if _safe(fee) else math.nan
        steps.append({"recipe": recipe_id, "crafts": times})
        if not _safe(state["fee"]):
            raise PlanError(TOO_LARGE)
        for entry in r.get("inputs") or []:
            quantity = entry.get("quantity")
            amount = quantity * times if _safe(quantity) else math.nan
            if not _safe(amount):
                raise PlanError(TOO_LARGE)
            sub = recipes.get(entry.get("recipe")) if entry.get("recipe") is not None else None
            if (expand and sub and sub.get("output") == entry.get("item") and sub.get("faction") == r.get("faction")
                    and sub.get("combo_chance") == 0):
                walk(entry.get("recipe"), _crafts_for(amount, sub.get("quantity")), [*path, recipe_id])
            else:
                leaves[entry.get("item")] = leaves.get(entry.get("item"), 0) + amount
                if expand and sub and _number(sub.get("combo_chance")) > 0 and COMBO_WARNING not in warnings:
                    warnings.append(COMBO_WARNING)

    walk(selected, count, [])
    if any(not _safe(quantity) for quantity in leaves.values()):
        raise PlanError(TOO_LARGE)
    materials = [{"id": item_id, "quantity": quantity, "owned": stock.get(item_id) or 0,
                  "remaining": max(0, quantity - (stock.get(item_id) or 0))} for item_id, quantity in leaves.items()]
    return {"materials": materials, "fee": state["fee"], "steps": steps, "warnings": warnings}


def _crafts_for(amount, quantity):
    """``Math.ceil(amount / quantity)``: the crafts that make ``amount``; past what one recipe makes (none, or what
    does not read) it is no number, which the plan then refuses as too large."""
    q = _number(quantity)
    if math.isnan(q):
        return math.nan
    if q == 0:
        return math.copysign(math.inf, amount) if amount else math.nan
    share = amount / q
    return math.ceil(share) if math.isfinite(share) else share


def plan_heading(expand: bool) -> str:
    return "Material plan " + ("(expanded where supported)" if expand else "(direct)")


def fees_line(planned: dict) -> str:
    return f"Listed fees: {n(planned['fee'])} Kinah · {len(planned['steps'])} recipe branches."


def output_line(recipe: dict, count: int) -> str:
    """The normal product's card line."""
    quantity = _number(recipe.get("quantity"))
    return f"{n(quantity)} per listed normal output · {n(quantity * count)} for the planned normal-output crafts"


def material_line(material: dict) -> str:
    return f"Required {n(material['quantity'])} · remaining {n(material['remaining'])}"


def owned_entry(text: str, previous: int) -> int:
    """An owned quantity entered: a whole number from 0 to a trillion; blank or anything else keeps what was there."""
    x = js_number(text)
    return int(x) if text.strip() and _whole(x) and 0 <= x <= MAX_OWNED else previous


# ------------------------------------------------------------------ combo checks
def chance_text(chance: float) -> str:
    """The combo rate in percent as its field shows it: ``String(Number((chance * 100).toFixed(4)))``."""
    return js_text(float(theme.fixed(chance * 100, 4)))


def chance_entry(text: str):
    """The assumed effective combo rate entered in percent, as a chance from 0 to 1; None for blank or what is not
    one."""
    x = js_number(text)
    return x / 100 if text.strip() and math.isfinite(x) and 0 <= x <= 100 else None


def crafts_entry(text: str, previous: int) -> int:
    """The planned completed crafts entered: a whole number from 1 to 10,000; anything else keeps what was there."""
    x = js_number(text)
    return int(x) if _whole(x) and 1 <= x <= MAX_CRAFTS else previous


def seed_entry(text: str, previous: int) -> int:
    """The scenario's seed entered: a whole number from 0 to 4,294,967,295 (a blank field reads 0, as on the web
    page); anything else keeps what was there."""
    x = js_number(text)
    return int(x) if _whole(x) and 0 <= x <= MAX_SEED else previous


def at_least_one(count: int, chance: float) -> float:
    """The chance that at least one of ``count`` independent checks triggers a combo."""
    if chance >= 1:
        return 1.0
    return -math.expm1(count * math.log1p(-chance))


def combo_line(count: int, chance: float) -> str:
    return (f"Conditional on {n(count)} independent completed-craft checks with a fixed {n(chance * 100)}% combo rate: "
            f"expected checks triggering combo {n(count * chance)}; probability of at least one "
            f"{n(at_least_one(count, chance) * 100)}%.")


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _imul(a: int, b: int) -> int:
    return _i32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))


def simulate(seed: int, count: int, chance: float) -> int:
    """How many of ``count`` checks trigger a combo in the seed's scenario: the web page's own generator, so a seed
    gives the same count on both."""
    state, hits = seed, 0
    for _ in range(count):
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        x = _imul(state ^ (state >> 15), state | 1)
        x = _i32(x ^ _i32(x + _imul(x ^ ((x & 0xFFFFFFFF) >> 7), x | 61)))
        if ((x ^ ((x & 0xFFFFFFFF) >> 14)) & 0xFFFFFFFF) / 4294967296 < chance:
            hits += 1
    return hits


def simulation_line(seed: int, hits: int, count: int) -> str:
    return (f"Illustrative scenario, seed {seed}: {n(hits)} of {n(count)} combo checks triggered. This does not predict "
            "game outcomes or output quantities.")


def rate_line(recipe: dict, effective) -> tuple[str, str]:
    """The combo note's head and its line on which rate is used."""
    return (f"Published combo trigger rate: {n(_number(recipe.get('combo_chance')) * 100)}%",
            "Craft success rate is shown above (community-measured where available) · "
            + ("Using the published combo rate." if effective is None else
               "Using your assumed effective combo rate; no modifier formula is verified."))


# ------------------------------------------------------------------ the export
def plan_document(catalog: dict, selected: str, enhancements: dict, count: int, chance: float, seed: int,
                  expand: bool, planned: dict) -> dict:
    """The material plan as the web page exports it (``a2craft-plan``, version 1)."""
    recipe = (catalog.get("recipes") or {})[selected]
    products = [item_id for item_id in (recipe.get("output"), recipe.get("combo")) if item_id]
    return {"format": "a2craft-plan", "version": 1, "source": catalog.get("source"),
            "source_sha256": catalog.get("source_sha256"), "source_retrieved_at": catalog.get("retrieved_at"),
            "game_build": None, "recipe": selected,
            "products": [{"id": item_id, "enhancement_preview": enhancements.get(item_id) or 0,
                          "reference": (catalog.get("item_details") or {}).get(item_id)} for item_id in products],
            "item_details_retrieved_at": catalog.get("item_details_retrieved_at"), "completed_crafts": count,
            "assumed_effective_combo_chance": chance, "seed": seed, "expand_intermediates": expand, **planned,
            "note": catalog.get("note")}
