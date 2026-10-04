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
to be added (in the app's Gear page, or by editing the JSON file).
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


def add(inv: dict, slug: str, enchant: int = 0, rolls: list | None = None, skills: list | None = None,
        note: str | None = None) -> dict:
    it = catalog_item(slug)
    if not it:
        raise ValueError(f"unknown item {slug!r}; search the catalog (Database page) for its id")
    e = {"id": uuid.uuid4().hex[:10], "source": "inventory", "slug": it["slug"], "name": it["name"],
         "category": it.get("category"), "grade": it.get("grade"), "item_level": it.get("item_level"),
         "enchant": int(enchant), "rolls": rolls, "skills": skills or [], "note": note}
    inv["items"].append(e)
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
