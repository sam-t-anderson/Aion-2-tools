"""Stage item names: what the game's numeric item ids are called, for the gathering and loot records.

The meter reads items by number: what a gathering node gave (``33 8d``) and what a dungeon's reward cube
held (``15 57``). The crafting catalog names the 1,466 items crafting uses; a reward cube also holds the
run's equipment, currencies and other drops. DBAion2's id-keyed English item table names all of them, with
the game's category (``GATHERRESOURCE`` a gathered material, ``CRAFTRESOURCE`` a crafting material, ...) and
grade (Common, Rare, Epic, Unique, ...). The staged table keeps the name, category and grade of each, nothing
else, and reads as names only: no stat, price or drop data comes from it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
from pathlib import Path

from .supplement import _read, _stable_id, _text

SOURCE = "https://dbaion2.ru/data-en/items.json"
NOTE = ("Names, categories and grades for the game's item ids, from DBAion2's English item table (dbaion2.ru). "
        "Names only: what the meter records (gathered items, reward cube contents) comes from the game.")


def validate(data):
    """The rows of DBAion2's item table, or ``ValueError`` when its shape is not the one reviewed."""
    if not isinstance(data, list) or not 0 < len(data) <= 200_000:
        raise ValueError("Expected a nonempty bounded item list")
    for row in data:
        if not (isinstance(row, dict) and _stable_id(row.get("id")) is not None and _text(row.get("name"))
                and (row.get("category") is None or isinstance(row.get("category"), str))):
            raise ValueError(f"Unexpected item row; review the source before staging: {str(row)[:200]}")
    return data


def build(rows):
    """``{id: [name, category, grade]}``: the item's name, the game's category (or its type for one without,
    such as a currency) and the grade the game shows."""
    out = {}
    for row in rows:
        code = str(row["id"])
        if code in out:
            continue
        category = _text(row.get("category"), 40) or _text(row.get("itemType"), 40) or ""
        out[code] = [_text(row["name"]), category, _text(row.get("gradeName"), 20) or ""]
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def stage(output, *, log=print, fetch=_read):
    """Write ``item-names.json`` and a review audit (ids added, removed and renamed against the bundled table)
    into a new directory. Copy the file into ``aion2calc/meter/a2parser/data`` once reviewed."""
    target = Path(output)
    if target.exists():
        raise ValueError("Choose a new staging directory; existing files are never overwritten")
    log(f"Reading {SOURCE}")
    raw = fetch(SOURCE)
    rows = build(validate(json.loads(raw)))
    table = {"format": "a2item-names", "version": 1,
             "source": {"name": "DBAion2", "url": SOURCE, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": hashlib.sha256(raw).hexdigest(), "records": len(rows), "note": NOTE},
             "items": rows}
    try:
        bundled = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "item-names.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        bundled = {}
    old = bundled.get("items") or {}
    diff = {"added": sorted(rows.keys() - old.keys(), key=int)[:200], "removed": sorted(old.keys() - rows.keys(), key=int)[:200],
            "renamed": sorted((k for k in rows.keys() & old.keys() if rows[k] != old[k]), key=int)[:200],
            "counts": {"rows": len(rows), "added": len(rows.keys() - old.keys()), "removed": len(old.keys() - rows.keys())}}
    target.mkdir(parents=True)
    (target / "item-names.json").write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (target / "item-names-audit.json").write_text(json.dumps(
        {"format": "a2item-names-audit", "version": 1, "source": table["source"], "diff": diff,
         "note": "Staged only. Review the added, removed and renamed ids before copying the file into a release."},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Staged {len(rows)} item names; review {target / 'item-names-audit.json'}")
    return table
