"""Your inventory: the items the gear planner may equip.

Saved per character in the user folder (``inventory/<profile>.json``). Items
come from two places:

* **equipped**: read from the official character page on import, with their
  exact rolls, manastones and skill options;
* **added by you**: any catalog item, with its enchant level and, if you know
  them, its rolls (``[["Critical Hit", 41], ...]``) and skill options
  (``[["Hellfire", 2], ...]``). Without rolls the planner uses the expected
  value of the item's roll pool.

The official page shows only what is equipped, so bag and warehouse items have
to be added (in the app's Gear page, or by editing the JSON file). The Gear page's
item panel offers what the catalog allows (:func:`options`) and what it sends is
checked against the catalog (:func:`check`): the enchant level up to the item's
limit, distinct rolls from the item's pool inside their ranges, skill options of
the character's class within what the item holds.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from ..db import store
from ..kit.base import ClassData
from ..paths import home
from . import items as I

OFFICIAL_ARCANA = re.compile(r"^Arcana\d*$")
#: skill option levels an item holds at most: a Unique +5 arcana card's nine; no other gear holds more
MAX_SKILL_LEVELS = 9
#: enchant levels offered when the catalog lists no "Max enhance" for an item
UNKNOWN_MAX_ENCHANT = 20


def folder() -> Path:
    d = home() / "inventory"
    d.mkdir(exist_ok=True)
    return d


def profile_name(cls: str, character: str | None = None) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (character or f"default_{cls}").lower()).strip("_")


def load(profile: str, cls: str | None = None) -> dict:
    p = folder() / f"{profile}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"profile": profile, "class": cls, "items": []}


def save(inv: dict) -> Path:
    p = folder() / f"{inv['profile']}.json"
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def catalog_item(slug: str | None = None, name: str | None = None) -> dict | None:
    conn = store.connect()
    if slug:
        it = store.item(conn, slug)
        if it:
            return it
    if name:
        row = conn.execute("SELECT slug FROM items WHERE lower(name)=lower(?) ORDER BY item_level DESC",
                           (name,)).fetchone()
        return store.item(conn, row[0]) if row else None
    return None


def _arcana_rules() -> tuple[int, dict]:
    from .arcana import ARCANA_MAX_ENHANCE, BASE_ROLLS
    return ARCANA_MAX_ENHANCE, BASE_ROLLS


def options(item: dict, cls: str | None = None) -> dict:
    """What the Gear page's item panel can set on ``item`` for a character of ``cls``.

    ``max_enchant`` is the catalog's "Max enhance" limit (``+15 (+20)`` -> 20), +5 for an arcana card
    and :data:`UNKNOWN_MAX_ENCHANT` when the catalog lists none (``enchant_known`` says which);
    ``enchant_steps`` the catalog's cumulative stats per level. ``rolls`` is the item's random-roll
    pool with each stat's range as numbers (``percent`` for a percentage range) and whether the
    damage model scores it (``scored``). ``skills`` lists the item's option pool for the class
    (``pool``), then the class's other skills (``others``, stigmas aside), the highest level one
    option reaches (``max_level``) and how many option levels the item holds: ``base`` plus
    ``per_enchant`` per enchant level (an arcana card: its grade's base rolls plus one per level;
    other gear: :data:`MAX_SKILL_LEVELS` whatever the level).
    """
    arcana_max, base_rolls = _arcana_rules()
    arcana = item.get("category") in I.ARCANA_CATEGORIES
    listed = I.max_enchant(item)
    steps = []
    for e in item.get("enchant") or []:
        nums = I._numbers(e.get("step", ""))
        if len(nums) >= 2:
            steps.append({"level": int(nums[1]), "stats": e.get("stats", "")})
    cls = cls if cls in I.WEAPON else None
    pool = ((item.get("skill_pools") or {}).get(cls) or {}) if cls else {}
    known = ClassData(cls).by_name if cls else {}
    in_pool = [n for n in pool.get("skills") or [] if n in known]
    others = [n for n, sk in known.items() if n not in in_pool and sk.get("kind") != "stigma"]
    return {"slug": item.get("slug"), "name": item.get("name"), "category": item.get("category"),
            "grade": item.get("grade"), "item_level": item.get("item_level"), "icon": item.get("icon"),
            "arcana": arcana, "max_enchant": arcana_max if arcana else (listed or UNKNOWN_MAX_ENCHANT),
            "enchant_known": arcana or bool(listed), "enchant_steps": steps, "roll_count": I.roll_count(item),
            "rolls": [{"stat": o["stat"], "range": o["range"], "min": o["min"], "max": o["max"],
                       "percent": o["percent"], "scored": bool(o["fields"])} for o in I.roll_options(item)],
            "skills": {"pool": in_pool, "others": others, "max_level": int(pool.get("max_level") or (4 if arcana else 1)),
                       "base": base_rolls.get(item.get("grade") or "", 4) if arcana else MAX_SKILL_LEVELS,
                       "per_enchant": 1 if arcana else 0}}


def check(item: dict, cls: str | None, enchant, rolls, skills) -> dict:
    """Check an entry's enchant level, rolls and skill options against the catalog item and the
    class, as the Gear page sends them, and return them normalised: ``{"enchant": int, "rolls":
    [[stat, number], …] or None, "rolls_text": "Critical Hit +41, Damage Boost +1.5%" or None,
    "skills": [[name, level], …]}``. Raises ``ValueError`` with the reason to show."""
    opt = options(item, cls)
    name = item.get("name") or item.get("slug")
    try:
        lv = int(enchant or 0)
    except (TypeError, ValueError):
        raise ValueError("the enchant level must be a whole number") from None
    if not 0 <= lv <= opt["max_enchant"]:
        raise ValueError(f"{name} enhances to +{opt['max_enchant']}" if opt["enchant_known"]
                         else f"choose an enchant level from +0 to +{opt['max_enchant']}")
    out_rolls, text = None, None
    if rolls:
        if not isinstance(rolls, list):
            raise ValueError("rolls must be a list of [stat, value] pairs")
        pool = {o["stat"]: o for o in opt["rolls"]}
        if not opt["roll_count"]:
            raise ValueError(f"{name} rolls no random stats")
        out_rolls, parts, seen = [], [], set()
        for r in rolls:
            if not isinstance(r, (list, tuple)) or len(r) != 2:
                raise ValueError("each roll is a [stat, value] pair")
            stat, raw = str(r[0]), r[1]
            o = pool.get(stat)
            if not o:
                raise ValueError(f"{name} cannot roll {stat}; its pool is {', '.join(pool)}")
            if stat in seen:
                raise ValueError(f"{stat} is entered twice; each roll is a different stat")
            try:
                v = float(str(raw).replace("%", "").replace(",", "").strip())
            except ValueError:
                raise ValueError(f"enter a number for {stat}") from None
            if not o["min"] <= v <= o["max"]:
                raise ValueError(f"{stat} rolls {o['range']} on {name}")
            seen.add(stat)
            v = int(v) if v == int(v) else v
            out_rolls.append([stat, v])
            parts.append(f"{stat} +{v:g}{'%' if o['percent'] else ''}")
        if len(out_rolls) > opt["roll_count"]:
            raise ValueError(f"{name} rolls {opt['roll_count']} random stat{'s' if opt['roll_count'] != 1 else ''}")
        text = ", ".join(parts)
    out_skills = []
    if skills:
        if not isinstance(skills, list):
            raise ValueError("skill options must be a list of [skill, level] pairs")
        sk = opt["skills"]
        allowed = set(sk["pool"]) | set(sk["others"])
        slots = sk["base"] + sk["per_enchant"] * lv
        seen, total = set(), 0
        for s in skills:
            if not isinstance(s, (list, tuple)) or len(s) != 2:
                raise ValueError("each skill option is a [skill, level] pair")
            nm = str(s[0]).strip()
            try:
                n = int(s[1])
            except (TypeError, ValueError):
                raise ValueError(f"enter a whole level for {nm}") from None
            if allowed and nm not in allowed:
                raise ValueError(f"{nm} is not a {cls} skill")
            if nm in seen:
                raise ValueError(f"{nm} is entered twice; give it one line with its total level")
            if not 1 <= n <= sk["max_level"]:
                raise ValueError(f"a skill option on {name} reaches +{sk['max_level']}")
            seen.add(nm)
            total += n
            out_skills.append([nm, n])
        if total > slots:
            raise ValueError(f"{name} holds {slots} option levels at +{lv}: {sk['base']} for a "
                             f"{item.get('grade') or 'card of its grade'} and one more per enchant level"
                             if opt["arcana"] else f"{name} holds at most {slots} skill options")
    return {"enchant": lv, "rolls": out_rolls, "rolls_text": text, "skills": out_skills}


def add(inv: dict, slug: str, enchant: int = 0, rolls: list | None = None, skills: list | None = None,
        note: str | None = None, strict: bool = False) -> dict:
    """Add a catalog item. ``strict`` (the Gear page) checks the enchant level, rolls and skill
    options against the catalog with :func:`check`; the CLI and older callers take them as given."""
    it = catalog_item(slug)
    if not it:
        raise ValueError(f"unknown item {slug!r}; search the catalog (Database page) for its id")
    if strict:
        fields = check(it, inv.get("class"), enchant, rolls, skills) | {"note": str(note or "").strip()[:200] or None}
    else:
        fields = {"enchant": int(enchant or 0), "rolls": rolls, "skills": skills or [], "note": note}
    e = {"id": uuid.uuid4().hex[:10], "source": "inventory", "slug": it["slug"], "name": it["name"],
         "category": it.get("category"), "grade": it.get("grade"), "item_level": it.get("item_level"),
         "icon": it.get("icon"), **fields}
    inv["items"].append(e)
    return e


def update(inv: dict, entry_id: str, enchant=None, rolls: list | None = None, skills: list | None = None,
           note: str | None = None) -> dict:
    """Change an added entry's enchant level, rolls, skill options or note, checked against the
    catalog as :func:`check` does; ``None`` keeps a field, ``[]`` clears the rolls (the planner then
    assumes the expected rolls again) or the skill options, ``""`` the note. Equipped entries are read
    from the official page and are not edited; a rejected change leaves the entry as it was."""
    e = next((x for x in inv["items"] if x.get("id") == entry_id), None)
    if not e:
        raise ValueError(f"no inventory entry {entry_id!r}")
    if e.get("source") != "inventory":
        raise ValueError(f"{e.get('name')} is read from the official page; add a copy from the catalog to plan "
                         "it with other rolls")
    it = catalog_item(e.get("slug"), e.get("name"))
    if not it:
        raise ValueError(f"{e.get('name')} is no longer in the catalog")
    new = check(it, inv.get("class"), e.get("enchant", 0) if enchant is None else enchant,
                e.get("rolls") if rolls is None else rolls, e.get("skills") if skills is None else skills)
    new["note"] = e.get("note") if note is None else (str(note).strip()[:200] or None)
    e.update(new)
    return e


def remove(inv: dict, entry_id: str) -> bool:
    n = len(inv["items"])
    inv["items"] = [e for e in inv["items"] if e["id"] != entry_id]
    return len(inv["items"]) < n


def from_character(imp, keep: dict | None = None) -> dict:
    """Inventory of an imported character: its equipped items (replacing older
    equipped entries) plus anything added before."""
    prof = profile_name(imp.cls, imp.loadout_name())
    inv = keep or load(prof, imp.cls)
    inv["class"], inv["character"] = imp.cls, {"name": imp.name, "server": imp.server, "key": imp.key,
                                               "loadout": imp.loadout_name()}
    inv["items"] = [e for e in inv["items"] if e.get("source") != "equipped"]
    for row in imp.systems.get("equipment", []) + imp.systems.get("arcana", []):
        it = catalog_item(name=row.get("name"))
        cat = (it or {}).get("category")
        slot = row["slot"]
        if OFFICIAL_ARCANA.match(slot) and cat in I.ARCANA_CATEGORIES:
            slot = f"Arcana {cat}"
        inv["items"].append({
            "id": f"eq-{row['slot']}", "source": "equipped", "slot": slot, "base_slot": row["slot"],
            "slug": (it or {}).get("slug"), "name": row.get("name"), "category": cat, "grade": row.get("grade"),
            "item_level": (it or {}).get("item_level"), "enchant": row.get("enchant") or 0,
            "icon": row.get("icon") or (it or {}).get("icon"),
            "stats": row.get("stats") or {}, "deity": row.get("deity") or {},
            "skills": [list(x) for x in row.get("skills") or []],
            "rolls_text": row.get("rolls"), "manastones": row.get("manastones")})
    return inv


def skill_bonus(skills: list, cls: str) -> dict:
    cd = ClassData(cls)
    out: dict = {}
    for nm, lv in skills or []:
        sk = cd.by_name.get(nm)
        if sk:
            out[sk["id"]] = out.get(sk["id"], 0) + int(lv)
    return out


def _stones(e: dict) -> dict:
    out: dict = {}
    for nm, v in e.get("manastones") or []:
        I._add(out, I._label_value(str(nm), str(v), False))
    return out


def entry_stats(e: dict, cls: str, mode: str = "expected", value=None, enchant: int | None = None,
                reroll: bool = False) -> tuple[dict, dict, dict]:
    """(gear stats, deity/primary points, skill bonus) of an inventory entry.

    ``enchant`` evaluates the item at another enchant level; ``reroll`` with
    good random rolls (the most valuable stats of its pool, scored by ``value``).
    """
    sb = skill_bonus(e.get("skills"), cls)
    mh = e.get("slot") == "MainHand" or e.get("category") in I.WEAPON.values()
    it = catalog_item(e.get("slug"), None if e.get("source") == "equipped" else e.get("name"))
    if e.get("source") == "equipped" and e.get("stats") is not None:
        gear, deity = dict(e["stats"]), dict(e.get("deity") or {})
        if it and reroll:
            st = I.item_stats(it, (e.get("enchant") or 0) if enchant is None else enchant, "good", value,
                              main_hand=mh)
            gear, deity = I.split_deity(I._add(st, _stones(e)))
        elif it and enchant is not None and enchant != (e.get("enchant") or 0):
            g1, d1 = I.split_deity(I.enchant_stats(it, enchant, mh))
            g0, d0 = I.split_deity(I.enchant_stats(it, e.get("enchant") or 0, mh))
            I._add(I._add(gear, g1), g0, -1)
            I._add(I._add(deity, d1), d0, -1)
        return gear, deity, sb
    if not it:
        return {}, {}, sb
    lv = e.get("enchant", 0) if enchant is None else enchant
    if reroll:
        st = I.item_stats(it, lv, "good", value, main_hand=mh)
    else:
        st = I.item_stats(it, lv, mode, value, e.get("rolls"), main_hand=mh)
    gear, deity = I.split_deity(st)
    return gear, deity, sb


def candidates(inv: dict, slot: str, cls: str) -> list[dict]:
    out = []
    for e in inv["items"]:
        cat = e.get("category")
        if cat is None:
            if e.get("slot") == slot:
                out.append(e)
            continue
        if I.fits({"category": cat}, slot, cls):
            out.append(e)
    return out
