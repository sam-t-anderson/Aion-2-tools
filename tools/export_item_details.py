"""Collect ID-matched crafted-item details from the recipe publisher, without executing source code."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen

BASE = "https://gamers4.life/aion-2/database"
DETAIL = BASE + "/db/item/en/{id}.json"
FORMAT_PAGE = BASE + "/en/equipment-comparison/"
LIMIT = 256 * 1024
STAT = re.compile(r"[a-z][a-z0-9_]{0,79}")


def download(url, limit=LIMIT):
    with urlopen(Request(url, headers={"User-Agent": "aion2calc-catalog"}), timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Item detail source exceeds its collection limit")
    return raw


def formatting():
    """Read publisher display metadata as data; never evaluate downloaded JavaScript."""
    html = download(FORMAT_PAGE, 2 * 1024 * 1024).decode("utf-8")
    paths = re.findall(r'<script[^>]+src="([^"]+)"', html)
    paths = [p for p in paths if re.fullmatch(r"/aion-2/database/_next/static/chunks/app/%5Blang%5D/equipment-comparison/page-[a-z0-9]+\.js", p)]
    if len(paths) != 1:
        raise ValueError("Publisher stat formatting source changed; review before replacing the snapshot")
    raw = download("https://gamers4.life" + paths[0], 2 * 1024 * 1024)
    text = raw.decode("utf-8")
    units = re.search(r'new Set\((\["pveamplifydamage"[^\]]*\])\)', text)
    labels = re.search(r'let n=\{(weapondamage:"Max Attack".*?)\},i=new Set', text)
    if not units or not labels:
        raise ValueError("Publisher stat display metadata changed")
    percent = json.loads(units[1])
    names = {key: json.loads(value) for key, value in re.findall(r'([a-z][a-z0-9_]*):("(?:[^"\\]|\\.)*")', labels[1])}
    if len(names) < 20 or any(not STAT.fullmatch(key) for key in percent):
        raise ValueError("Invalid publisher stat display metadata")
    return {"labels": names, "percent": percent, "source": "https://gamers4.life" + paths[0],
            "source_sha256": hashlib.sha256(raw).hexdigest()}


def numbers(value):
    if not isinstance(value, dict) or len(value) > 200:
        raise ValueError("Invalid item stat table")
    result = {}
    for key, amount in value.items():
        if not isinstance(key, str) or not STAT.fullmatch(key):
            raise ValueError("Invalid stat identity")
        if isinstance(amount, dict):
            if amount.get("id") != key:
                raise ValueError("Stat identity differs from its table key")
            amount = amount.get("value")
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or abs(amount) > 1e12:
            raise ValueError("Invalid source stat value")
        result[key] = amount
    return result


def normalize(key, raw):
    if len(raw) > LIMIT:
        raise ValueError("Oversized item detail")
    row = json.loads(raw)
    if not isinstance(row, dict) or row.get("id") != key or row.get("language") != "en":
        raise ValueError("Item detail identity or language disagrees with its source URL")
    stats = row.get("itemStats")
    result = {"source": DETAIL.format(id=key), "source_sha256": hashlib.sha256(raw).hexdigest(),
              "name": str(row.get("name") or key)[:300], "status": "unavailable",
              "category": row.get("mainCategory"), "variant": row.get("itemTier"),
              "equipment": {k: v for k, v in (row.get("equipmentInfo") or {}).items() if k in ("itemLevel", "itemBasicLevel", "equipCategory")}}
    if not isinstance(stats, dict) or not isinstance(stats.get("mainStats"), dict):
        return result
    result["base"] = numbers(stats["mainStats"])
    result["enhancements"] = []
    for entry in stats.get("enchants") or []:
        if not isinstance(entry, dict):
            raise ValueError("Invalid source enhancement record")
        level = entry.get("level")
        if type(level) is not int or not 1 <= level <= 100:
            raise ValueError("Invalid source enhancement level")
        result["enhancements"].append({"level": level, "stats": numbers(entry.get("stats") or {})})
    if len(result["enhancements"]) > 100 or len({r["level"] for r in result["enhancements"]}) != len(result["enhancements"]):
        raise ValueError("Duplicate or oversized source enhancement table")
    result["enhancements"].sort(key=lambda entry: entry["level"])
    result["rolls"] = []
    for entry in stats.get("subStats") or []:
        if not isinstance(entry, dict) or entry.get("type") != "stat":
            continue
        identity = entry.get("id")
        values = numbers({identity: entry.get("minValue"), "range_max": entry.get("maxValue")})
        if values[identity] > values["range_max"]:
            raise ValueError("Reversed source roll range")
        result["rolls"].append({"id": identity, "min": values[identity], "max": values["range_max"]})
    if len(result["rolls"]) > 200:
        raise ValueError("Oversized source roll table")
    result["status"] = "available" if result["base"] or result["rolls"] or result["enhancements"] else "none_listed"
    # Missing consumable-effect coefficients remain unavailable, never 'no effect'.
    if row.get("useEffect") is not None:
        result["effect_reference"] = str(row["useEffect"])[:200]
    return result


def enrich(catalog, cache: Path | None = None, format_source: Path | None = None):
    ids = sorted({row[field] for row in catalog["recipes"].values() for field in ("output", "combo") if row[field]})
    def collect(key):
        raw = (cache / (key + ".json")).read_bytes() if cache is not None else download(DETAIL.format(id=key))
        return key, normalize(key, raw)
    with ThreadPoolExecutor(max_workers=4) as pool:
        details = dict(pool.map(collect, ids))
    catalog["item_details"] = details
    catalog["stat_display"] = json.loads(format_source.read_text(encoding="utf-8")) if format_source else formatting()
    catalog["item_details_retrieved_at"] = datetime.now(timezone.utc).isoformat()
    catalog["item_details_note"] = "Publisher item records, matched by numeric IDs in the same source namespace. Base, listed cumulative enhancement bonuses and possible random-roll ranges are separate. No random roll, breakthrough or ownership is assumed. Game version/region applicability is unverified. Missing effect data is not proof of no effect."
    return catalog
