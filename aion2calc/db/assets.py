"""Region-scoped official asset references, independent of character identity/stats."""
from __future__ import annotations

import json
import math
import time
from urllib.parse import urlsplit, urlunsplit

REGIONS = {"nae", "eu", "as", "la", "kr", "tw"}
KINDS = {"item", "skill", "pet", "wing", "title", "board"}
HOSTS = {"assets.playnccdn.com", "profileimg.plaync.com"}


def identifier(value):
    if isinstance(value, bool):
        return None
    text = str(value)
    return text if text.isascii() and text.isdigit() and 0 < len(text) <= 20 else None


def image_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or url.hostname not in HOSTS or url.username or url.password
                or url.port not in (None, 443) or not url.path.lower().endswith((".png", ".webp", ".jpg", ".jpeg", ".gif"))):
            return None
        return urlunsplit(("https", url.hostname, url.path, "", ""))
    except ValueError:
        return None


def record(conn, character, *, observed_at=None, cached=False):
    region = character.get("region")
    if region not in REGIONS:
        return
    groups = {"item": (character.get("equipment") or {}).get("equipmentList", []),
              "skill": (character.get("skill") or {}).get("skillList", []),
              "title": (character.get("title") or {}).get("titleList", []),
              "board": (character.get("daevanion") or {}).get("boardList", [])}
    for kind in ("pet", "wing"):
        groups[kind] = [(character.get("petwing") or {}).get(kind)]
    now = time.time() if observed_at is None else float(observed_at)
    if not math.isfinite(now) or now <= 0:
        raise ValueError("Invalid profile observation time")
    count = 0
    for kind, rows in groups.items():
        if not isinstance(rows, list):
            continue
        for row in rows[:500]:
            if not isinstance(row, dict) or not (item_id := identifier(row.get("id"))):
                continue
            icon = image_url(row.get("icon"))
            count += 1
            if cached:
                conn.execute("""INSERT INTO official_assets(region,kind,asset_id,name,icon,grade,observed_at,reference_changes)
                    VALUES (?,?,?,?,?,?,?,0) ON CONFLICT(region,kind,asset_id) DO UPDATE SET
                    name=CASE WHEN excluded.observed_at>=official_assets.observed_at THEN excluded.name ELSE official_assets.name END,
                    grade=CASE WHEN excluded.observed_at>=official_assets.observed_at THEN excluded.grade ELSE official_assets.grade END,
                    reference_changes=MAX(official_assets.reference_changes, CASE
                      WHEN excluded.icon IS NOT NULL AND official_assets.icon IS NOT NULL
                      AND excluded.icon!=official_assets.icon THEN 1 ELSE 0 END),
                    icon=CASE WHEN excluded.observed_at>=official_assets.observed_at
                      THEN COALESCE(excluded.icon,official_assets.icon)
                      ELSE COALESCE(official_assets.icon,excluded.icon) END,
                    observed_at=MAX(excluded.observed_at,official_assets.observed_at)""",
                    (region, kind, item_id, str(row.get("name") or "")[:200], icon,
                     str(row.get("grade") or "")[:40], now))
                continue
            conn.execute("""INSERT INTO official_assets(region,kind,asset_id,name,icon,grade,observed_at,reference_changes)
                VALUES (?,?,?,?,?,?,?,0) ON CONFLICT(region,kind,asset_id) DO UPDATE SET
                name=excluded.name, grade=excluded.grade, observed_at=excluded.observed_at,
                reference_changes=official_assets.reference_changes + CASE
                  WHEN excluded.icon IS NOT NULL AND official_assets.icon IS NOT NULL
                  AND excluded.icon != official_assets.icon THEN 1 ELSE 0 END,
                icon=COALESCE(excluded.icon,official_assets.icon)""",
                (region, kind, item_id, str(row.get("name") or "")[:200], icon,
                 str(row.get("grade") or "")[:40], now))

    return count


def lookup(conn, region, kind, asset_id):
    asset_id = identifier(asset_id)
    if region not in REGIONS or kind not in KINDS or not asset_id:
        return {}
    row = conn.execute("SELECT icon,grade FROM official_assets WHERE region=? AND kind=? AND asset_id=? AND reference_changes=0",
                       (region, kind, asset_id)).fetchone()
    if not row or not image_url(row[0]):
        return {}
    return {"icon": row[0], "grade": row[1], "visual_source": "Official region/item ID reference"}


def reindex(*, log=lambda message: None):
    """Backfill cached official references without fetching or rewriting profiles."""
    from . import store
    conn = store.connect()
    total = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
    result = {"profiles": 0, "skipped": 0, "references": 0, "total": total}
    log(f"Re-indexing references from {total} cached official profiles")
    # Keyset batches avoid loading every profile blob into memory at once.
    cursor = ""
    while True:
        rows = conn.execute("SELECT key,data,fetched_at FROM characters WHERE key>? ORDER BY key LIMIT 50",
                            (cursor,)).fetchall()
        if not rows:
            break
        with conn:
            for row in rows:
                cursor = row["key"]
                conn.execute("SAVEPOINT asset_reindex")
                try:
                    profile = json.loads(row["data"])
                    if not isinstance(profile, dict) or profile.get("region") not in REGIONS:
                        raise ValueError("Missing official region")
                    count = record(conn, profile, observed_at=row["fetched_at"], cached=True)
                except (TypeError, ValueError, AttributeError):
                    conn.execute("ROLLBACK TO asset_reindex")
                    result["skipped"] += 1
                else:
                    result["profiles"] += 1
                    result["references"] += count or 0
                finally:
                    conn.execute("RELEASE asset_reindex")
        log(f"Processed {result['profiles'] + result['skipped']} profiles; {result['references']} references examined")
    result["finished_at"] = time.time()
    store.set_meta(conn, "asset_reindex", result)
    log("Reference re-index complete. Reopen the affected view to reload its icons.")
    return result


def report():
    from . import store
    conn = store.connect()
    groups = [dict(row) for row in conn.execute("""SELECT region,kind,COUNT(*) AS records,
        SUM(CASE WHEN icon IS NOT NULL THEN 1 ELSE 0 END) AS with_reference,
        SUM(CASE WHEN icon IS NULL THEN 1 ELSE 0 END) AS missing_reference,
        SUM(CASE WHEN reference_changes>0 THEN 1 ELSE 0 END) AS changed_reference_ids,
        MAX(observed_at) AS last_observed FROM official_assets GROUP BY region,kind ORDER BY region,kind""")]
    missing = [dict(row) for row in conn.execute("""SELECT region,kind,asset_id,name,reference_changes
        FROM official_assets WHERE icon IS NULL OR reference_changes>0 ORDER BY region,kind,asset_id LIMIT 200""")]
    catalog = dict(conn.execute("""SELECT COUNT(*) AS records,
        SUM(CASE WHEN icon IS NULL OR icon='' THEN 1 ELSE 0 END) AS missing_reference FROM items""").fetchone())
    return {"format": "a2assets", "version": 2, "generated_at": time.time(), "official": groups,
            "unresolved": missing, "unresolved_limit": 200, "catalog_items": catalog,
            "last_reindex": store.get_meta(conn, "asset_reindex"),
            "note": "References observed in official profile imports and cached-profile re-indexing, scoped by region and asset kind. No character identities, gear stats or credentials are included. URL presence is not an HTTP availability check. Changed references are excluded from ID fallback. Re-indexing uses original import times; conflicting cached references are excluded from fallback. Re-import a character to fetch new data. Catalog slugs, official IDs and combat NPC IDs are separate namespaces; this report does not map NPC portraits or infer missing URLs."}
