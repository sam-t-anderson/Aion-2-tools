"""The Builds page's drafts (0.2.486), as static/build-workspace.js (``A2BuildWorkspace.mount``) keeps and checks them
for the web page:

- **a draft** (``fresh``) and a document read as one (``normalize``): an ``a2build`` v1 document with a class the
  bundled catalog knows, its level and mode, its budgets, its allocations (trained and equipped levels, supporting
  effects, manual bonus levels, Daevanion nodes), its source and reference, its equipment, Genus lines and mix;
- **the arcana cards' skill levels** (``cardBonuses``), **the skills' effective levels** (``levels``) and **the
  catalog's and the entered budgets' checks** (``assessment``);
- **an optimizer's build or a community preset read as a draft** (``fromSummary``), **a file read**
  (``importFile``): a draft, an optimizer's ``build.json``, or an official profile kept as the draft's reference;
- **the drafts kept** (``a2-build-drafts-v1``): ten at most, 2 MiB in all. Since 0.2.482 they are the app's interface
  data, which the web page and the native window share.

The catalog is the app's bundled one (``static/build-catalog.json``): each class's skills, Daevanion boards and level
budgets, the skills' and stigmas' costs, the supporting effects' slot levels, the crystal boards, the items, the
arcana pools and the deities. Every function here takes it as read.

What the web page keeps is written as ``JSON.stringify`` writes it (``stringify``): an object's keys that are array
indices first, in their order, then the others as they came; a number as JavaScript writes it.
"""
from __future__ import annotations

import json
import math
import random
import re
import time

from .character import _number_text, js_number, js_string
from .settings_looks import _js_float, _no_constant, js_slice

MAX = 2 * 1024 * 1024                         # a draft, its reference and the drafts kept (``MAX``)
STORE = "a2-build-drafts-v1"
MOST_DRAFTS = 10
LOADOUT_MOST = 128 * 1024
GENUS_MOST = 32768
GENUS_MIX = {"Cogni": 25, "Fera": 25, "Natura": 25, "Varian": 25, "Special": 0}
KINDS = ("skill", "stigma", "daevanion")
_MISSING = object()                           # a property an object has not (``undefined``)


class BuildError(ValueError):
    """What the web page throws (``throw Error(...)``), its words as given."""


# ------------------------------------------------------------------ JavaScript's values
def is_object(value) -> bool:
    """``object(x)``: an object, not an array."""
    return isinstance(value, dict)


def truthy(value) -> bool:
    """A value read as a condition: an object or array is true even when empty; 0, NaN, "" and null false."""
    if isinstance(value, (dict, list)):
        return True
    if isinstance(value, float) and math.isnan(value):
        return False
    return bool(value)


def _or(value, fallback):
    """``value || fallback``."""
    return value if truthy(value) else fallback


def integer(value, least, most) -> bool:
    """``Number.isInteger(x) && x >= least && x <= most``."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and float(value).is_integer() and least <= value <= most)


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def same(a, b) -> bool:
    """``a === b`` for what JSON holds: numbers by value, true and false only as themselves, text as text; an object
    or array only as itself."""
    if a is _MISSING or b is _MISSING:
        return a is b
    if number(a) and number(b):
        return a == b
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return a is b
    return type(a) is type(b) and a == b


def _index_key(key: str) -> bool:
    """A key JavaScript keeps in an array index's place: a whole number written plainly, below 2³² − 1."""
    return key.isascii() and key.isdigit() and (key == "0" or not key.startswith("0")) and int(key) < 4294967295


def keys(value: dict) -> list:
    """``Object.keys``: the keys that are array indices first, in their order, then the others as they came."""
    first = sorted((k for k in value if isinstance(k, str) and _index_key(k)), key=int)
    return first + [k for k in value if not (isinstance(k, str) and _index_key(k))]


def entries(value) -> list:
    """``Object.entries`` of what JSON holds: an object's in ``keys`` order, an array's by index, a text's by
    character, nothing for anything else."""
    if isinstance(value, dict):
        return [(k, value[k]) for k in keys(value)]
    if isinstance(value, list):
        return [(str(i), x) for i, x in enumerate(value)]
    if isinstance(value, str):
        return [(str(i), ch) for i, ch in enumerate(value)]
    return []


def get(value, key, missing=None):
    """``value[key]`` of what JSON holds (``?.`` when ``value`` is none): an object's by ``String(key)``; else
    ``missing``."""
    if isinstance(value, dict):
        return value.get(js_string(key) if not isinstance(key, str) else key, missing)
    return missing


_SURROGATE = re.compile("[\ud800-\udfff]")


def _text(value: str) -> str:
    return _SURROGATE.sub(lambda m: "\\u%04x" % ord(m.group(0)), json.dumps(value, ensure_ascii=False))


def stringify(value, indent: int = 0) -> str:
    """``JSON.stringify(value)`` (``JSON.stringify(value, null, indent)`` with an indent): keys in ``keys`` order,
    numbers as JavaScript writes them, a number that is not finite as null."""
    def write(v, depth: int) -> str:
        if v is None or v is _MISSING:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v) if abs(v) < 10 ** 21 else _number_text(float(v))
        if isinstance(v, float):
            return _number_text(v) if math.isfinite(v) else "null"
        if isinstance(v, str):
            return _text(v)
        if isinstance(v, dict):
            parts = [(_text(k), write(v[k], depth + 1)) for k in keys(v) if v[k] is not _MISSING]
            if not parts:
                return "{}"
            if not indent:
                return "{" + ",".join(f"{k}:{x}" for k, x in parts) + "}"
            inner, outer = "\n" + " " * (indent * (depth + 1)), "\n" + " " * (indent * depth)
            return "{" + ",".join(f"{inner}{k}: {x}" for k, x in parts) + outer + "}"
        if isinstance(v, (list, tuple)):
            if not v:
                return "[]"
            parts = [write(x, depth + 1) for x in v]
            if not indent:
                return "[" + ",".join(parts) + "]"
            inner, outer = "\n" + " " * (indent * (depth + 1)), "\n" + " " * (indent * depth)
            return "[" + ",".join(inner + x for x in parts) + outer + "]"
        return "null"
    return write(value, 0)


def size(value) -> int:
    """``bytes(x)``: its JSON's length in UTF-8."""
    return len(stringify(value).encode("utf-8", "surrogatepass"))


def parse(text: str):
    """``JSON.parse(text)``: a number with a fraction or an exponent whole when it is, no NaN or Infinity; ValueError
    when it is not JSON."""
    return json.loads(text, parse_float=_js_float, parse_constant=_no_constant)


def copy(value):
    """``JSON.parse(JSON.stringify(value))``."""
    return parse(stringify(value))


# ------------------------------------------------------------------ a draft
def classes(catalog: dict) -> dict:
    return catalog.get("classes") if isinstance(catalog.get("classes"), dict) else {}


def class_of(catalog: dict, name) -> dict | None:
    """``catalog.classes[name]``: a class the catalog knows, else none."""
    found = get(classes(catalog), name)
    return found if isinstance(found, dict) else None


def fresh(catalog: dict, name, mode: str = "pve", level=45) -> dict:
    """An empty draft for a class (``fresh``), named after its class, level and mode."""
    return {"format": "a2build", "version": 1, "name": f"{js_string(name)}_{js_string(level)}_{js_string(mode).upper()}",
            "class": name, "level": level, "mode": mode, "notes": "", "catalog_revision": catalog.get("revision"),
            "budgets": {"skill": 0, "stigma": 0, "daevanion": 0, "boards": {}},
            "build": {"sp": {}, "stigmas": {}, "specs": {}, "bonus": {}, "daevanion_nodes": []},
            "reference": None, "source": {}, "loadout": {"components": []}, "genus": {}, "genus_mix": dict(GENUS_MIX)}


def _distinct(values: list) -> bool:
    """``new Set(values).size === values.length`` for numbers."""
    return len({float(v) for v in values}) == len(values)


def normalize(catalog: dict, value) -> dict:
    """A document read as a draft (``normalize``), each part checked against the catalog; BuildError says what does
    not fit, as the web page says it."""
    cd = class_of(catalog, get(value, "class")) if is_object(value) else None
    if (not is_object(value) or not same(value.get("format", _MISSING), "a2build")
            or not same(value.get("version", _MISSING), 1) or cd is None):
        raise BuildError("Choose an a2build v1 document with a known class.")
    if not integer(value.get("level"), 1, 45) or value.get("mode") not in ("pve", "pvp") or not isinstance(value.get("mode"), str):
        raise BuildError("Choose level 1–45 and PvE or PvP.")
    level = int(value["level"])
    out = fresh(catalog, value["class"], value["mode"], level)
    skills = {js_string(s.get("id")): s for s in cd.get("skills") or []}
    out["name"] = js_slice(js_string(_or(value.get("name"), out["name"])), 120)
    out["notes"] = js_slice(js_string(_or(value.get("notes"), "")), 4000)
    out["catalog_revision"] = js_slice(js_string(_or(value.get("catalog_revision"), "unknown")), 64)
    budgets, build = value.get("budgets"), value.get("build")
    if not is_object(budgets) or not is_object(build):
        raise BuildError("Missing budgets or allocations.")
    for key in KINDS:
        if not integer(budgets.get(key), 0, 10000):
            raise BuildError("Invalid " + key + " budget.")
        out["budgets"][key] = int(budgets[key])
    boards = _or(budgets.get("boards"), {})
    if not is_object(boards) or len(boards) > len(cd.get("boards") or []):
        raise BuildError("Invalid board budgets.")
    for key, n in entries(boards):
        if not any(b.get("name") == key for b in cd.get("boards") or []) or not integer(n, 0, 10000):
            raise BuildError("Unknown board budget.")
        out["budgets"]["boards"][key] = int(n)
    for field in ("sp", "stigmas", "bonus", "specs"):
        values = _or(build.get(field), {})
        if not is_object(values) or len(values) > len(cd.get("skills") or []):
            raise BuildError("Invalid " + field + " allocation.")
        for key, v in entries(values):
            sk = skills.get(key)
            if sk is None:
                raise BuildError("Unknown skill ID " + key + ".")
            if field == "specs":
                ids = [e.get("id") for e in sk.get("specs") or []]
                if (sk.get("kind") != "active" or not isinstance(v, list) or len(v) > 5
                        or not all(integer(n, 1, 999999999) for n in v) or not _distinct(v)
                        or any(not any(same(i, n) for i in ids) for n in v)):
                    raise BuildError("Invalid supporting effects for " + js_string(sk.get("name")) + ".")
                out["build"]["specs"][key] = [int(n) for n in v]
            else:
                cap = min(10, _or(sk.get("buyMax"), 10)) if field == "sp" else 20 if field == "stigmas" else 30
                if (not integer(v, 0 if field == "bonus" else 1, cap)
                        or (field == "sp" and sk.get("kind") not in ("active", "passive"))
                        or (field == "stigmas" and sk.get("kind") != "stigma")
                        or (field == "bonus" and sk.get("kind") == "stigma")):
                    raise BuildError("Invalid " + field + " level for " + js_string(sk.get("name")) + ".")
                out["build"][field][key] = int(v)
    nodes = build.get("daevanion_nodes")
    known = {n.get("id") for b in cd.get("boards") or [] for n in b.get("nodes") or []}
    if (not isinstance(nodes, list) or len(nodes) > 2048 or not all(integer(n, -math.inf, math.inf) for n in nodes)
            or not _distinct(nodes) or any(int(n) not in known for n in nodes)):
        raise BuildError("Unknown or duplicate Daevanion nodes.")
    out["build"]["daevanion_nodes"] = [int(n) for n in nodes]
    if value.get("reference") is not None:
        if not is_object(value["reference"]) or size(value["reference"]) > MAX:
            raise BuildError("Reference is too large or invalid.")
        out["reference"] = copy(value["reference"])
    if is_object(value.get("source")):
        given = value["source"]
        out["source"] = {"log": js_slice(js_string(_or(given.get("log"), "")), 16),
                         "actor": js_slice(js_string(_or(given.get("actor"), "")), 80),
                         "basis": js_slice(js_string(_or(given.get("basis"), "")), 200)}
    if value.get("loadout") is not None:
        loadout = value["loadout"]
        parts = loadout.get("components") if is_object(loadout) else None
        if (not is_object(loadout) or not isinstance(parts, list) or len(parts) > 64
                or any(not is_object(c) or not is_object(c.get("stats")) for c in parts) or size(loadout) > LOADOUT_MOST):
            raise BuildError("Equipment input must contain at most 64 components / 128 KiB.")
        out["loadout"] = copy(loadout)
    for key in ("genus", "genus_mix"):
        if value.get(key) is not None:
            if not is_object(value[key]) or size(value[key]) > GENUS_MOST:
                raise BuildError("Invalid " + key + " input.")
            out[key] = copy(value[key])
    card_bonuses(catalog, out)
    return out


def card_bonuses(catalog: dict, doc: dict) -> dict:
    """The arcana cards' skill levels (``cardBonuses``), by skill; BuildError where a card or its options do not fit
    its slot, grade and enhancement, or the levels with the manual bonus pass 30."""
    totals: dict = {}
    seen: list = []
    for c in doc["loadout"]["components"]:
        values = c.get("arcana_skills")
        values = {} if values is None else values
        if not is_object(values):
            raise BuildError("Card options must be a skill-level map.")
        if not values:
            continue
        slot = c.get("slot", _MISSING)
        pool = get(get(catalog.get("arcana_pools"), doc["class"]), slot) if slot is not _MISSING else None
        slug = c.get("catalog_slug", _MISSING)
        item = next((it for it in catalog.get("items") or [] if same(it.get("slug", _MISSING), slug)), None)
        base = get(catalog.get("arcana_base_rolls"), item.get("grade")) if item is not None and "grade" in item else None
        allowed = get(catalog.get("equipment_slots"), slot) if slot is not _MISSING else None
        if (not truthy(pool) or item is None or any(same(s, slot) for s in seen)
                or not isinstance(allowed, list) or not any(same(a, item.get("category")) for a in allowed)
                or item.get("required_level", 0) > doc["level"]
                or not integer(c.get("enchant"), 0, len(item.get("levels") or []) - 1) or base is None):
            raise BuildError("Choose distinct compatible catalog cards and valid enhancement levels.")
        seen.append(slot)
        count = 0
        for key, n in entries(values):
            if (not any(js_string(sk.get("id")) == key for sk in pool.get("skills") or [])
                    or not integer(n, 0, pool.get("max_level"))):
                raise BuildError("Card skill is outside the bundled pool or per-skill cap.")
            count += n
            totals[key] = _or(totals.get(key), 0) + n
        if count > base + c["enchant"]:
            raise BuildError("Card options exceed the grade/enhancement budget.")
    for key, n in entries(totals):
        if n + _or(get(doc["build"]["bonus"], key), 0) > 30:
            raise BuildError("Combined manual and card skill bonuses exceed 30.")
    return totals


def safe_card_bonuses(catalog: dict, doc: dict) -> dict:
    try:
        return card_bonuses(catalog, doc)
    except BuildError:
        return {}


def levels(catalog: dict, draft: dict) -> dict:
    """Each skill's effective level (``levels``), by its id as a key: the trained level (1 untrained) and the manual
    bonus, or the equipped stigma's level; the arcana cards' levels; the Daevanion nodes' ranks taken."""
    cd = class_of(catalog, draft["class"]) or {}
    build = draft["build"]
    result: dict = {}
    selected = set(build["daevanion_nodes"])
    for s in cd.get("skills") or []:
        key = js_string(s.get("id"))
        if s.get("kind") == "stigma":
            result[key] = _or(build["stigmas"].get(key), 0)
        else:
            result[key] = _or(build["sp"].get(key), 1) + _or(build["bonus"].get(key), 0)
    for key, value in entries(safe_card_bonuses(catalog, draft)):
        result[key] = result.get(key, math.nan) + value
    for b in cd.get("boards") or []:
        for n in b.get("nodes") or []:
            if n.get("id") in selected and truthy(n.get("skillId")):
                key = js_string(n["skillId"])
                result[key] = _or(result.get(key), 1) + _or(n.get("skillLevels"), 1)
    return result


def cost(chosen: dict, prices: list) -> float:
    """``cost``: each level's price up to the level chosen, all added."""
    def taken(n) -> list:
        end = js_number(n)
        end = 0 if math.isnan(end) else int(end) if math.isfinite(end) else (len(prices) if end > 0 else 0)
        return prices[:end]
    return sum(sum(taken(n)) for _key, n in entries(chosen))


def budget_row(cd: dict, level) -> dict:
    """The catalog's budget row for the level (``cls().budget.filter(b => b.level <= draft.level).at(-1)``)."""
    rows = [b for b in cd.get("budget") or [] if b.get("level", 0) <= level]
    return rows[-1] if rows else {"slots": 0}


def assessment(catalog: dict, draft: dict) -> dict:
    """The draft checked (``assessment``): what does not pass the catalog's rules or the entered budgets, in the web
    page's order and words; the skill, stigma and crystal costs; each board's cost; the effective levels."""
    cd = class_of(catalog, draft["class"]) or {}
    build, budgets = draft["build"], draft["budgets"]
    errors: list[str] = []
    lv = levels(catalog, draft)
    selected = set(build["daevanion_nodes"])
    sp = cost(build["sp"], catalog.get("skill_cost") or [])
    stigma = cost(build["stigmas"], catalog.get("stigma_cost") or [])
    board_costs: dict = {}
    try:
        card_bonuses(catalog, draft)
    except BuildError as problem:
        errors.append(str(problem))
    if sp > budgets["skill"]:
        errors.append(f"Skill cost {js_string(sp)} exceeds entered budget {js_string(budgets['skill'])}.")
    if stigma > budgets["stigma"]:
        errors.append(f"Stigma cost {js_string(stigma)} exceeds entered budget {js_string(budgets['stigma'])}.")
    row = budget_row(cd, draft["level"])
    if len(build["stigmas"]) > row.get("slots", 0):
        errors.append(f"Equipped stigmas exceed the catalog's {js_string(row.get('slots'))} slots at this level.")
    spec_levels = catalog.get("spec_slot_levels") or []
    for s in cd.get("skills") or []:
        key, name, stigmatic = js_string(s.get("id")), js_string(s.get("name")), s.get("kind") == "stigma"
        trained = _or(build["stigmas"].get(key), 0) if stigmatic else _or(build["sp"].get(key), 1)
        if stigmatic:
            need = s.get("unlock")
        else:
            needs = s.get("need")
            at = trained - 1 if number(trained) else None
            need = needs[int(at)] if (isinstance(needs, list) and at is not None and float(at).is_integer()
                                      and 0 <= at < len(needs)) else None
            need = s.get("unlock") if need is None else need
        if (trained > 1 or stigmatic and trained > 0) and draft["level"] < _or(need, 1):
            errors.append(name + ": character level gate not reached.")
        if truthy(s.get("max")) and lv.get(key, math.nan) > s["max"]:
            errors.append(name + ": effective level exceeds the catalog maximum.")
        if s.get("kind") == "active":
            choices = _or(build["specs"].get(key), [])
            slots = sum(1 for n in spec_levels if lv.get(key, math.nan) >= n)
            if choices and draft["level"] < _or(s.get("unlock"), 1):
                errors.append(name + ": character level gate not reached.")
            if len(choices) > slots:
                errors.append(name + ": too many supporting effects for the effective level.")
            effects = s.get("specs") or []
            if any((e := next((e for e in effects if same(e.get("id"), i)), None)) is not None
                   and e.get("unlock", 0) > lv.get(key, math.nan) for i in choices):
                errors.append(name + ": selected supporting effect is locked.")
    crystal_boards = catalog.get("crystal_boards") or []
    for b in cd.get("boards") or []:
        nodes = b.get("nodes") or []
        taken = [n for n in nodes if n.get("id") in selected]
        board_costs[b.get("name")] = sum(_or(n.get("cost"), 0) for n in taken)
        if not taken:
            continue
        need = b.get("needLevel", 0)
        if draft["level"] < need or any(draft["level"] < _or(n.get("needLevel"), need) for n in taken):
            errors.append(js_string(b.get("name")) + ": character level gate not reached.")
        start = next((n for n in nodes if n.get("type") == "Start"), None)
        seen = {start.get("id")} if start is not None else set()
        stack = [start] if start is not None else []
        positions = {f"{js_string(n.get('row'))}:{js_string(n.get('col'))}": n for n in nodes}
        while stack:
            n = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                found = positions.get(f"{js_string(n.get('row', 0) + dr)}:{js_string(n.get('col', 0) + dc)}")
                if found is not None and found.get("id") in selected and found.get("id") not in seen:
                    seen.add(found.get("id"))
                    stack.append(found)
        if any(n.get("id") not in seen for n in taken):
            errors.append(js_string(b.get("name")) + ": selected nodes must connect to the centre through selected nodes.")
        if b.get("name") not in crystal_boards and board_costs[b.get("name")] > _or(budgets["boards"].get(b.get("name")), 0):
            errors.append(js_string(b.get("name")) + ": cost exceeds its separate entered board budget.")
    crystal = sum(_or(board_costs.get(b), 0) for b in crystal_boards)
    if crystal > budgets["daevanion"]:
        errors.append(f"Daevanion cost {js_string(crystal)} exceeds entered budget {js_string(budgets['daevanion'])}.")
    return {"errors": errors, "sp": sp, "stigma": stigma, "crystal": crystal, "boardCosts": board_costs, "levels": lv}


# ------------------------------------------------------------------ an optimizer's build, a file
def from_summary(catalog: dict, summary) -> dict:
    """An optimizer's build or a community preset read as a draft (``fromSummary``): the skills by name, the bonus
    levels worked back from its effective levels, its frozen equipment and Genus lines; its stats and scores kept as
    the draft's reference only."""
    build = summary.get("build") if is_object(summary) else None
    if not is_object(summary) or class_of(catalog, summary.get("class")) is None or not is_object(build):
        raise BuildError("Unsupported optimizer summary.")
    scenario = js_string(_or(summary.get("scenario"), ""))
    out = fresh(catalog, summary["class"], "pvp" if scenario.startswith("pvp") else "pve", _or(summary.get("level"), 45))
    cd = class_of(catalog, out["class"]) or {}
    by_name = {s.get("name"): s for s in cd.get("skills") or []}
    for field in ("sp", "stigmas"):
        for name, n in entries(_or(build.get(field), {})):
            s = by_name.get(name)
            if s is None:
                raise BuildError("Unknown imported skill " + js_string(name))
            out["build"][field][js_string(s.get("id"))] = n
    for name, texts in entries(_or(build.get("specs"), {})):
        s = by_name.get(name)
        if s is None or not isinstance(texts, list) or (texts and s.get("kind") != "active"):
            raise BuildError("Unknown imported specialties.")
        if not texts:
            continue
        ids = []
        for text in texts:
            effect = next((e for e in s.get("specs") or [] if same(e.get("text"), text)), None)
            if effect is None:
                raise BuildError("Unknown specialty for " + js_string(name))
            ids.append(effect.get("id"))
        out["build"]["specs"][js_string(s.get("id"))] = ids
    nodes = _or(build.get("daevanion_nodes"), [])
    out["build"]["daevanion_nodes"] = nodes
    for key in KINDS:
        if integer(get(summary.get("budgets"), key), 0, 10000):
            out["budgets"][key] = summary["budgets"][key]
    additions: dict = {}
    for b in cd.get("boards") or []:
        for n in b.get("nodes") or []:
            if _includes(nodes, n.get("id")) and truthy(n.get("skillId")):
                key = js_string(n["skillId"])
                additions[key] = _or(additions.get(key), 0) + _or(n.get("skillLevels"), 1)
    for name, n in entries(_or(build.get("effective_levels"), {})):
        s = by_name.get(name)
        if s is None or s.get("kind") == "stigma":
            continue
        key = js_string(s.get("id"))
        extra = js_number(n) - js_number(_or(out["build"]["sp"].get(key), 1)) - js_number(_or(additions.get(key), 0))
        if not integer(extra, 0, 30):
            raise BuildError("Effective level cannot be decomposed for " + js_string(name))
        out["build"]["bonus"][key] = int(extra)
    if is_object(summary.get("loadout_snapshot")):
        loadout = copy(summary["loadout_snapshot"])
        parts = _or(loadout.get("components"), [])
        if not isinstance(parts, list):
            raise BuildError("(out.loadout.components || []).filter is not a function")
        kept = []
        for c in parts:
            if c is None:
                raise BuildError("Cannot read properties of null (reading 'source')")
            if is_object(c) and same(c.get("source", _MISSING), "manual-genus-insight"):
                continue
            c = copy(c)
            if is_object(c) and is_object(c.get("stats")):
                c["stats"].pop("skill_bonus", None)
            kept.append(c)
        loadout["components"] = kept
        out["loadout"] = loadout
    genus = summary.get("genus")
    if is_object(get(genus, "state")):
        out["genus"] = copy(genus["state"])
    if is_object(get(genus, "mix")) and genus["mix"]:
        out["genus_mix"] = copy(genus["mix"])
    optimizer = {key: summary[key] for key in ("class", "scenario", "dps", "stats", "genus", "progression")
                 if key in summary}
    out["reference"] = {"optimizer": optimizer}
    out["source"] = {"basis": "Imported optimizer allocation. Bonus levels are reconstructed from exported effective "
                              "levels; original stats/scores are reference only."}
    return normalize(catalog, out)


def _includes(nodes, node_id) -> bool:
    """``nodes.includes(id)``: an array's items, or a text's (a node's id written in it)."""
    if isinstance(nodes, list):
        return any(same(n, node_id) for n in nodes)
    if isinstance(nodes, str):
        return js_string(node_id) in nodes
    raise BuildError("out.build.daevanion_nodes.includes is not a function")


PROFILE_BASIS = "Imported profile reference; allocations are not inferred from total skill levels."
NOT_IMPORTABLE = "Choose an a2build draft, optimizer build.json or exported official profile JSON."


def imported(catalog: dict, draft: dict, value) -> tuple[dict, bool]:
    """A file's JSON read as the next draft (``importFile``): a draft, an optimizer's build, or an official profile
    kept as an empty draft's reference; and whether the Source character tab is to show (a profile). BuildError for
    anything else."""
    if value is None:
        raise BuildError("Cannot read properties of null (reading 'format')")
    if same(get(value, "format", _MISSING), "a2build"):
        return normalize(catalog, value), False
    if truthy(get(value, "class")) and truthy(get(value, "build")):
        return from_summary(catalog, value), False
    nested = is_object(get(get(value, "data"), "profile"))
    if nested or is_object(get(value, "profile")):
        nxt = fresh(catalog, draft["class"], draft["mode"])
        nxt["reference"] = {"snapshot": value if nested else {"status": "imported", "data": value}}
        nxt["source"] = {"basis": PROFILE_BASIS}
        return normalize(catalog, nxt), True
    raise BuildError(NOT_IMPORTABLE)


def export_name(name: str) -> str:
    """The exported file's name (``draft.name.replace(/[^a-z0-9_-]/gi, '_') || 'build'``, then ``.a2build.json``):
    each other character a "_", one for each of its UTF-16 units."""
    plain = "".join(ch if re.fullmatch(r"[A-Za-z0-9_-]", ch) else "_" * (2 if ord(ch) > 0xFFFF else 1) for ch in name)
    return (plain or "build") + ".a2build.json"


# ------------------------------------------------------------------ the drafts kept
def saved(text) -> list:
    """The drafts kept (``saved``): the first ten of the list, or none when it is not one."""
    try:
        value = parse(text or "[]")
    except (ValueError, RecursionError):
        return []
    return value[:MOST_DRAFTS] if isinstance(value, list) else []


def row_id(row):
    """A kept row's ``id`` (``x.id``), ``_MISSING`` when it has none; TypeError's words for a null row."""
    if row is None:
        raise BuildError("Cannot read properties of null (reading 'id')")
    return row.get("id", _MISSING) if isinstance(row, dict) else _MISSING


def row_name(row) -> str:
    """A kept draft's name in the list (``x.draft?.name || 'Unnamed draft'``)."""
    return js_string(_or(get(get(row, "draft"), "name"), "Unnamed draft"))


def row_key(row) -> str:
    """The row's id as its buttons carry it (``esc(x.id)``)."""
    found = row.get("id") if isinstance(row, dict) else None
    return "" if found is None else js_string(found)


def new_id(now_ms: int | None = None, pick=None) -> str:
    """A kept draft's id: the time in milliseconds, then six random letters and digits (``Math.random()`` in base
    36)."""
    pick = pick or random.SystemRandom().choice
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return f"{now_ms}-" + "".join(pick("0123456789abcdefghijklmnopqrstuvwxyz") for _ in range(6))


def saved_with(catalog: dict, draft: dict, reference, source, kept_text, now_ms: int | None = None, pick=None):
    """The kept drafts with this one first (``save``), and its id: BuildError for ten kept already or 2 MiB passed.
    A draft kept before keeps its id and takes the first place."""
    doc = normalize(catalog, {**draft, "reference": reference, "source": source})
    mine = draft.get("local_id", _MISSING)
    rows = [x for x in saved(kept_text) if not same(row_id(x), mine)]
    if len(rows) >= MOST_DRAFTS:
        raise BuildError("Ten local drafts are saved. Remove one before saving a new draft.")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    ident = mine if truthy(mine) and mine is not _MISSING else new_id(now_ms, pick)
    rows.insert(0, {"id": ident, "updated_at": now_ms, "draft": doc})
    if size(rows) > MAX:
        raise BuildError("Saved drafts exceed 2 MiB. Export a build or remove an older draft.")
    return rows, ident


def without(kept_text, key: str) -> list:
    """The kept drafts without the one whose id its button carries (``data-remove``)."""
    return [x for x in saved(kept_text) if not same(row_id(x), key)]


def find_row(kept_text, key: str):
    """The kept draft whose id its button carries (``data-load``), or none."""
    return next((x for x in saved(kept_text) if same(row_id(x), key)), None)


# ------------------------------------------------------------------ equipment and arcana cards (0.2.487)
NO_ITEM_RULES = "Catalog rules unavailable."
MOST_COMPONENTS = 64
SHOWN_ITEMS = 80
ITEM_SOURCE = "Bundled catalog fixed stats, enhancement and entered source-pool rolls"
FULL = "The draft already has 64 components. Remove an imported contribution first."
OVER_CARD = ("Arcana skill options exceed the source pool or grade/enhancement budget. Adjust options before lowering "
             "enhancement.")
MANY_ROLLS = "Too many random rolls for the bundled item rule."
BAD_ROLL = "Invalid imported roll metadata. Reselect the catalog item."
OUT_OF_RANGE = "Choose distinct source-pool rolls with values inside their listed ranges."


def component_kind(c) -> str:
    """Where a component shows (``componentKind``): an arcana card, a deity's points, or equipment, by its slot."""
    slot = js_string(_or(get(c, "slot"), ""))
    if re.search("arcana", slot, re.I):
        return "arcana"
    return "pantheon" if re.search("pantheon|deity", slot, re.I) else "equipment"


def slots_for(catalog: dict, kind: str) -> list:
    """The catalog's slots for the tab: the arcana cards', or the equipment's, in the catalog's order."""
    slots = catalog.get("equipment_slots") if isinstance(catalog.get("equipment_slots"), dict) else {}
    return [s for s in slots if s.startswith("Arcana ") == (kind == "arcana")]


def chosen_in(draft: dict, slot):
    """The draft's component in a slot (``find(c => c.slot === gearSlot)``), or none."""
    return next((c for c in draft["loadout"]["components"] if same(get(c, "slot", _MISSING), slot)), None)


def _fits(catalog: dict, draft: dict, slot, item: dict) -> bool:
    allowed = get(catalog.get("equipment_slots"), slot)
    allowed = allowed if isinstance(allowed, list) else []
    weapon = get(catalog.get("class_weapons"), draft["class"])
    category = item.get("category", _MISSING)
    return ((any(same(a, category) for a in allowed) or ("weapon" in allowed and same(category, weapon)))
            and item.get("required_level", 0) <= draft["level"])


def available(catalog: dict, draft: dict, slot, search: str) -> list:
    """The catalog's items for a slot (``available``): its categories (a weapon slot the class's weapon), the level,
    the name searched for."""
    wanted = search.lower()
    return [c for c in catalog.get("items") or [] if _fits(catalog, draft, slot, c)
            and (not search or wanted in js_string(c.get("name")).lower())]


def catalog_item(catalog: dict, draft: dict, slot, chosen):
    """The chosen component's catalog item, when it fits the slot and level and its enhancement is one of the
    item's (``catalogItem``); else none."""
    if not isinstance(chosen, dict):
        return None
    slug = chosen.get("catalog_slug", _MISSING)
    return next((c for c in catalog.get("items") or [] if same(c.get("slug", _MISSING), slug) and _fits(catalog, draft, slot, c)
                 and integer(chosen.get("enchant"), 0, len(c.get("levels") or []) - 1)), None)


def stats_line(c) -> str:
    """A component's stats (``key: value · …``)."""
    stats = get(c, "stats")
    return " · ".join(f"{js_string(k)}: {'' if v is None else js_string(v)}" for k, v in entries(stats if truthy(stats) else {}))


def card_note(catalog: dict, item: dict, enchant) -> str:
    """What each enhancement step adds to a card."""
    base = get(catalog.get("arcana_base_rolls"), item.get("grade"))
    base = 0 if base is None else base
    top = len(item.get("levels") or []) - 1
    return (f"Each enhancement step adds one skill option: {js_string(base + enchant)} at +{js_string(enchant)}, "
            f"{js_string(base + top)} at +{js_string(top)}. The bundled catalog lists no stat change per step.")


def with_item(catalog: dict, draft: dict, slot, item: dict, level, rolls=None, arcana_skills=None) -> list:
    """The draft's components with a catalog item in the slot (``apply``): its fixed stats at the enhancement, the
    entered rolls added through their units, the card's skill levels; at the end of the list, as the web page puts
    it. BuildError says what does not fit."""
    components = draft["loadout"]["components"]
    rolls = [] if rolls is None else rolls
    arcana_skills = {} if arcana_skills is None else arcana_skills
    if len(components) >= MOST_COMPONENTS and not any(same(get(c, "slot", _MISSING), slot) for c in components):
        raise BuildError(FULL)
    comp = {"slot": slot, "item": f"{js_string(item.get('name'))} +{js_string(level)}"}
    for key in ("icon", "grade"):
        if key in item:
            comp[key] = item[key]
    comp.update(enchant=level, catalog_slug=item.get("slug"), source=ITEM_SOURCE, rolls=[], arcana_skills=copy(arcana_skills),
                stats=copy(item["levels"][int(level)]))
    pool = get(get(catalog.get("arcana_pools"), draft["class"]), slot)
    base = get(catalog.get("arcana_base_rolls"), item["grade"]) if "grade" in item else None
    if not is_object(arcana_skills) or any(
            not (is_object(pool) and any(js_string(s.get("id")) == key for s in pool.get("skills") or []))
            or not integer(n, 0, pool.get("max_level")) for key, n in entries(arcana_skills)) \
            or sum(n for _key, n in entries(arcana_skills)) > (0 if base is None else base) + level:
        raise BuildError(OVER_CARD)
    if not isinstance(rolls, list) or len(rolls) > _or(item.get("roll_count"), 0):
        raise BuildError(MANY_ROLLS)
    used: list = []
    for roll in rolls:
        if not is_object(roll):
            raise BuildError(BAD_ROLL)
        stat = roll.get("stat", _MISSING)
        option = next((o for o in item.get("roll_options") or [] if same(o.get("stat", _MISSING), stat)), None)
        value = js_number(roll["value"]) if "value" in roll else math.nan
        if (option is None or any(same(u, stat) for u in used) or not math.isfinite(value)
                or value < option.get("min") or value > option.get("max")):
            raise BuildError(OUT_OF_RANGE)
        used.append(stat)
        comp["rolls"].append({"stat": stat, "value": value})
        for key, scale in entries(option.get("unit") or {}):
            comp["stats"][key] = _or(comp["stats"].get(key), 0) + value * scale
    return [c for c in components if not same(get(c, "slot", _MISSING), slot)] + [comp]


def without_slot(draft: dict, slot) -> list:
    """The draft's components with the slot cleared (``data-unequip``)."""
    return [c for c in draft["loadout"]["components"] if not same(get(c, "slot", _MISSING), slot)]


# ------------------------------------------------------------------ Pantheon and evaluation (0.2.488)
PANTHEON_SLOT = "Pantheon"
PANTHEON_ITEM = "Draft deity contributions"
BAD_POINTS = "Enter a finite point total from 0 to 1,000,000."
PANTHEON_FULL = "Remove an imported contribution before adding Pantheon points (64 component limit)."
EVALUATION_MOST = 128 * 1024


def pantheon_rows(draft: dict) -> list:
    """The draft's deity contributions (``componentKind(c) === 'pantheon'``)."""
    return [c for c in draft["loadout"]["components"] if component_kind(c) == "pantheon"]


def deity_total(rows: list, field) -> float:
    """A deity's points over the rows (``Number(c.stats?.[field]) || 0``, added)."""
    total = 0
    for c in rows:
        stats = get(c, "stats")
        key = js_string(field)
        n = js_number(stats[key]) if isinstance(stats, dict) and key in stats else math.nan
        total += n if truthy(n) else 0
    return total


def deity_words(deity: dict) -> tuple[str, str, str]:
    """A deity tile's sigil letter, name and lord (``Destruction [Zikel]``: Z, Destruction, Zikel)."""
    name = js_string(deity.get("name"))
    found = re.search(r"\[([^\]]+)\]", name)
    lord = found.group(1) if found else name
    return (js_slice(lord, 1) if lord else ""), name.split(" [")[0], lord


def recorded_stat(source_stats, deity: dict):
    """The source profile's total for a deity, when it records one (``statList``), else none."""
    if not isinstance(source_stats, list):
        return None
    for s in source_stats:
        if not is_object(s):
            continue
        kind = s.get("type", _MISSING)
        if (same(kind, deity.get("field", _MISSING)) or same(kind, deity.get("profile_type", _MISSING))
                or js_string(_or(s.get("name"), "")) == deity.get("name")):
            return s
    return None


def with_deity_points(draft: dict, rows: list, deity: dict, value) -> None:
    """A deity's draft points kept (the ``data-deity`` change): its field taken off every deity row, then put on the
    draft's own Pantheon contribution, made when it has none. ``rows`` gains it, as the web page's list does."""
    components = draft["loadout"]["components"]
    if len(components) >= MOST_COMPONENTS and not any(same(get(c, "slot", _MISSING), PANTHEON_SLOT) for c in components):
        raise BuildError(PANTHEON_FULL)
    field = deity.get("field")
    for c in rows:
        if truthy(get(c, "stats")) and is_object(c["stats"]):
            c["stats"].pop(js_string(field), None)
    comp = next((c for c in components if same(get(c, "slot", _MISSING), PANTHEON_SLOT)), None)
    if comp is None:
        comp = {"slot": PANTHEON_SLOT, "item": PANTHEON_ITEM, "stats": {}}
        components.append(comp)
        rows.append(comp)
    comp["stats"][js_string(field)] = value


def input_text(draft: dict, key: str) -> str:
    """An advanced input as its text area shows it (``JSON.stringify(draft[key], null, 2)``)."""
    return stringify(draft[key], 2)


def evaluation_request(draft: dict, search: bool) -> dict:
    """What the evaluation is sent (``request``): the allocation, budgets, loadout and Genus input, no reference."""
    return {"search_priority": search, "format": draft["format"], "version": draft["version"], "class": draft["class"],
            "mode": draft["mode"], "level": draft["level"], "build": copy(draft["build"]), "budgets": copy(draft["budgets"]),
            "loadout": copy(draft["loadout"]), "genus": copy(draft["genus"]), "genus_mix": copy(draft["genus_mix"])}


def dps(value) -> str:
    """``Number(x).toLocaleString(undefined, {maximumFractionDigits: 1})`` in English: grouped, a tenth at most."""
    x = js_number(value)
    if not math.isfinite(x):
        return "NaN" if math.isnan(x) else ("∞" if x > 0 else "-∞")
    tenths = math.floor(abs(x) * 10 + 0.5) / 10            # half away from zero, as Intl rounds
    whole, _, fraction = f"{tenths:,.1f}".partition(".")
    text = whole if fraction == "0" else f"{whole}.{fraction}"
    return ("-" if x < 0 and tenths else "") + text


def evaluation_words(output: dict) -> dict:
    """An evaluation's words (``data-evaluation``): who evaluated which input, each scenario's modelled DPS, each
    priority search, the note."""
    sha = get(output, "input_sha256")
    scenarios = entries(get(output, "scenarios") or {}) if truthy(get(output, "scenarios")) else []
    searches = []
    for name, r in scenarios:
        search = get(r, "priority_search")
        if not truthy(search):
            continue
        actions = [js_string(get(a, "name")) + (f" ({js_string(get(a, 'condition'))})" if truthy(get(a, "condition")) else "")
                   for a in (get(search, "actions") or [])]
        searches.append({"title": f"{name} priority search",
                         "line": (f"{js_string(get(search, 'evaluations'))} evaluated priorities · "
                                  f"{js_string(get(search, 'stop_reason'))} · default {dps(get(search, 'baseline_dps'))} DPS"),
                         "actions": actions, "note": js_string(_or(get(search, "note"), ""))})
    return {"source": (f"Evaluator {'' if get(output, 'evaluator') is None else js_string(get(output, 'evaluator'))} · input "
                       f"{js_slice(js_string(sha), 16) if isinstance(sha, str) else ''}"),
            "scenarios": [f"{name}: {dps(get(r, 'dps'))} modeled DPS" for name, r in scenarios],
            "searches": searches, "note": "" if get(output, "note") is None else js_string(get(output, "note")),
            "detail": stringify(output, 2)}
