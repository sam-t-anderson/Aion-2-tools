"""Stage a pinned upstream encounter catalog and its diff for release review."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

REPOSITORY = "taengu/A2Tools-DPS-Meter"
LOCALES = {"npcs": ("de", "en", "es", "fr", "ja", "ko", "pt", "ru", "zh-Hans", "zh-Hant"),
           "dungeons": ("en", "ko", "zh-Hans", "zh-Hant")}
MAX_BYTES = 2_000_000


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate catalog key: {key}")
        result[key] = value
    return result


def validate(raw, category):
    data = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(data, dict) or not 0 < len(data) <= 100_000:
        raise ValueError("Expected a nonempty bounded catalog object")
    strings = {"name", "difficulty"} if category == "dungeons" else {"name", "category", "tier"}
    allowed = strings if category == "dungeons" else strings | {"isBoss", "isDummy", "dungeonId"}
    for key, row in data.items():
        if not re.fullmatch(r"[1-9][0-9]{0,18}", key) or int(key) >= 2**63:
            raise ValueError(f"Invalid stable ID: {key}")
        if not isinstance(row, dict) or not set(row) <= allowed or "name" not in row:
            raise ValueError(f"Unexpected {category} schema at {key}; review upstream changes")
        for field, value in row.items():
            if field in strings:
                if not isinstance(value, str) or not value.strip() or len(value) > 500:
                    raise ValueError(f"Invalid {field} at {key}")
            elif field == "dungeonId":
                if type(value) is not int or not 0 < value < 2**63:
                    raise ValueError(f"Invalid dungeon ID at {key}")
            elif type(value) is not bool:
                raise ValueError(f"Invalid {field} flag at {key}")
    return data


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def stage(revision, output, *, log=print):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use the full lowercase 40-character upstream commit SHA")
    target = Path(output)
    if target.exists():
        raise ValueError("Choose a new staging directory; existing files are never overwritten")
    bundled = files("aion2calc.meter.a2parser").joinpath("data", "i18n")
    pending, records, diffs = {}, [], []
    for category, locales in LOCALES.items():
        ids = None
        for locale in locales:
            relative = f"{category}/{locale}.json"
            source = f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/src/data/i18n/{relative}"
            log(f"Reading {relative} at {revision[:12]}")
            request = Request(source, headers={"User-Agent": "aion2calc-catalog-audit"})
            with urlopen(request, timeout=30) as response:
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError(f"Oversized catalog: {relative}")
            data = validate(raw, category)
            if ids is not None and set(data) != ids:
                raise ValueError(f"Locale ID sets differ in {category}; review before promotion")
            ids = set(data)
            old = validate(bundled.joinpath(category, f"{locale}.json").read_bytes(), category)
            added, removed = sorted(data.keys()-old.keys()), sorted(old.keys()-data.keys())
            changed = sorted(key for key in data.keys() & old.keys() if data[key] != old[key])
            changes = ([{"id": key, "change": "added"} for key in added]
                       + [{"id": key, "change": "removed"} for key in removed]
                       + [{"id": key, "change": "changed", "fields": sorted(
                           field for field in data[key].keys() | old[key].keys()
                           if data[key].get(field) != old[key].get(field))} for key in changed])
            diffs.append({"file": relative, "added": len(added), "removed": len(removed),
                          "changed": len(changed), "changes": changes[:100], "omitted": max(0, len(changes)-100)})
            records.append({"file": relative, "records": len(data), "sha256": digest(data),
                            "source_sha256": hashlib.sha256(raw).hexdigest()})
            pending[relative] = raw
    manifest = {"format": "a2catalog-source", "version": 1, "repository": REPOSITORY,
                "revision": revision, "checked_at": datetime.now(timezone.utc).isoformat(),
                "game_build": None, "files": records,
                "note": "Community parser catalog, not an official game-build mapping. Broad boss flags may include minibosses. No inferred IDs, portraits or difficulty values."}
    audit = {"format": "a2catalog-audit", "version": 1, "source": manifest, "diffs": diffs,
             "note": "Staged only. Review all changes, especially removals and boss/dummy/dungeon/difficulty fields, before copying into a release."}
    target.mkdir(parents=True, exist_ok=False)
    for relative, raw in pending.items():
        path = target / "i18n" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    for name, data in (("catalog-source.json", manifest), ("catalog-audit.json", audit)):
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Staged {len(records)} tables; review {target / 'catalog-audit.json'} before release")
    return audit
