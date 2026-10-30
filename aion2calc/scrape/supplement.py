"""Stage the name supplement: names for the NPC and dungeon ids the community catalog leaves out.

The community catalog (``catalog.py``, taengu/A2Tools-DPS-Meter) lists the monsters a DPS meter
meets and the dungeons it has names for. Recordings also hold friendly and neutral NPCs -- guards
fighting beside the party, merchants, objects -- and instances it has no name for (later
Transcendence tiers, the Ascension trials, the daily dungeons). DBAion2's id-keyed English tables
name them. The supplement takes, from those tables, only what the community catalog has no row
for: an NPC's name and type, a dungeon id's name, content type and difficulty label. It never adds
or changes a boss flag, category, tier, difficulty or dungeon link, so classification and ranking
read the community catalog alone; the supplement names what would otherwise show as a number.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = {"npcs": "https://dbaion2.ru/data-en/npcs.json", "dungeons": "https://dbaion2.ru/data-en/dungeons.json"}
MAX_BYTES = 16_000_000
NOTE = ("Names for NPC and dungeon ids the community catalog has no row for, from DBAion2's English "
        "tables (dbaion2.ru). Names, NPC types and content types only: boss flags, categories, tiers, "
        "difficulties and dungeon links stay the community catalog's. A community row always wins.")


def _text(value, limit=200):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _stable_id(value):
    return value if type(value) is int and 0 < value < 2**63 else None


def validate(category, data):
    """The rows of a DBAion2 table, or ``ValueError`` when its shape is not the one reviewed."""
    if not isinstance(data, list) or not 0 < len(data) <= 200_000:
        raise ValueError(f"Expected a nonempty bounded {category} list")
    for row in data:
        ok = isinstance(row, dict) and bool(_text(row.get("name")))
        if ok and category == "npcs":
            ok = _stable_id(row.get("id")) is not None
        if ok and category == "dungeons":
            levels = row.get("difficulties")
            ok = isinstance(levels, list) and all(isinstance(d, dict) and _stable_id(d.get("id")) is not None for d in levels)
        if not ok:
            raise ValueError(f"Unexpected {category} row; review the source before staging: {str(row)[:200]}")
    return data


def _unnamed(row):
    """A community row naming its NPC "???", as the game does for what it gives no name."""
    return isinstance(row, dict) and not str(row.get("name") or "").strip(" ?")


def build(npcs, dungeons, community_npcs, community_dungeons):
    """The supplement's rows: every source id the community tables lack, with its name, and the
    type of each id they name "???" (DBAion2's name for one is an internal one, never shown)."""
    out_npcs = {}
    for row in npcs:
        code = str(row["id"])
        if code in out_npcs:
            continue
        kind = _text(row.get("npcType"), 40)
        if code in community_npcs:
            if _unnamed(community_npcs[code]) and kind:
                out_npcs[code] = {"type": kind}
            continue
        entry = {"name": _text(row["name"])}
        if kind:
            entry["type"] = kind
        out_npcs[code] = entry
    out_dungeons = {}
    for group in dungeons:
        name, kind = _text(group["name"]), _text(group.get("type"), 40)
        for level in group.get("difficulties") or []:
            code = str(level["id"])
            if code in community_dungeons or code in out_dungeons:
                continue
            entry = {"name": name}
            if kind:
                entry["type"] = kind
            if (label := _text(level.get("name"), 40)) and label != "None":
                entry["difficulty_name"] = label
            out_dungeons[code] = entry
    order = lambda rows: dict(sorted(rows.items(), key=lambda kv: int(kv[0])))
    return {"npcs": order(out_npcs), "dungeons": order(out_dungeons)}


def _read(url):
    request = Request(url, headers={"User-Agent": "aion2calc-catalog-audit"})
    with urlopen(request, timeout=60) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"Oversized source table: {url}")
    return raw


def stage(output, *, log=print, fetch=_read):
    """Write ``catalog-supplement.json`` and a review audit (ids added and removed against the bundled
    supplement) into a new directory. Copy the file into ``aion2calc/meter/a2parser/data`` once reviewed."""
    target = Path(output)
    if target.exists():
        raise ValueError("Choose a new staging directory; existing files are never overwritten")
    from ..meter.a2parser.lookup import _table
    raws, tables = {}, {}
    for category, url in SOURCES.items():
        log(f"Reading {url}")
        raws[category] = fetch(url)
        tables[category] = validate(category, json.loads(raws[category]))
    rows = build(tables["npcs"], tables["dungeons"], _table("npcs", "en"), _table("dungeons", "en"))
    supplement = {"format": "a2catalog-supplement", "version": 1,
                  "source": {"name": "DBAion2", "urls": SOURCES, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                             "sha256": {k: hashlib.sha256(v).hexdigest() for k, v in raws.items()},
                             "records": {k: len(v) for k, v in tables.items()}, "note": NOTE},
                  **rows}
    try:
        bundled = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "catalog-supplement.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        bundled = {}
    diffs = {}
    for category in ("npcs", "dungeons"):
        new, old = rows[category], bundled.get(category) or {}
        diffs[category] = {"added": sorted(new.keys() - old.keys(), key=int)[:200], "removed": sorted(old.keys() - new.keys(), key=int)[:200],
                           "renamed": sorted((k for k in new.keys() & old.keys() if new[k] != old[k]), key=int)[:200],
                           "counts": {"rows": len(new), "added": len(new.keys() - old.keys()), "removed": len(old.keys() - new.keys())}}
    target.mkdir(parents=True)
    (target / "catalog-supplement.json").write_text(json.dumps(supplement, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (target / "catalog-supplement-audit.json").write_text(json.dumps(
        {"format": "a2catalog-supplement-audit", "version": 1, "source": supplement["source"], "diffs": diffs,
         "note": "Staged only. Review the added, removed and renamed ids before copying the file into a release."},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Staged {len(rows['npcs'])} NPC and {len(rows['dungeons'])} dungeon names; review {target / 'catalog-supplement-audit.json'}")
    return supplement
