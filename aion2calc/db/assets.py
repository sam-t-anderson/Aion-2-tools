"""Region-scoped official asset references, independent of character identity/stats."""
from __future__ import annotations

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


def record(conn, character):
    region = character.get("region")
    if region not in REGIONS:
        return
    groups = {"item": (character.get("equipment") or {}).get("equipmentList", []),
              "skill": (character.get("skill") or {}).get("skillList", []),
              "title": (character.get("title") or {}).get("titleList", []),
              "board": (character.get("daevanion") or {}).get("boardList", [])}
    for kind in ("pet", "wing"):
        groups[kind] = [(character.get("petwing") or {}).get(kind)]
    now = time.time()
    for kind, rows in groups.items():
        if not isinstance(rows, list):
            continue
        for row in rows[:500]:
            if not isinstance(row, dict) or not (item_id := identifier(row.get("id"))):
                continue
            icon = image_url(row.get("icon"))
            conn.execute("""INSERT INTO official_assets(region,kind,asset_id,name,icon,grade,observed_at,reference_changes)
                VALUES (?,?,?,?,?,?,?,0) ON CONFLICT(region,kind,asset_id) DO UPDATE SET
                name=excluded.name, grade=excluded.grade, observed_at=excluded.observed_at,
                reference_changes=official_assets.reference_changes + CASE
                  WHEN excluded.icon IS NOT NULL AND official_assets.icon IS NOT NULL
                  AND excluded.icon != official_assets.icon THEN 1 ELSE 0 END,
                icon=COALESCE(excluded.icon,official_assets.icon)""",
                (region, kind, item_id, str(row.get("name") or "")[:200], icon,
                 str(row.get("grade") or "")[:40], now))


def lookup(conn, region, kind, asset_id):
    asset_id = identifier(asset_id)
    if region not in REGIONS or kind not in KINDS or not asset_id:
        return {}
    row = conn.execute("SELECT icon,grade FROM official_assets WHERE region=? AND kind=? AND asset_id=? AND reference_changes=0",
                       (region, kind, asset_id)).fetchone()
    if not row or not image_url(row[0]):
        return {}
    return {"icon": row[0], "grade": row[1], "visual_source": "Official region/item ID reference"}


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
    return {"format": "a2assets", "version": 1, "generated_at": time.time(), "official": groups,
            "unresolved": missing, "unresolved_limit": 200, "catalog_items": catalog,
            "note": "References observed during fresh official profile imports, scoped by region and asset kind. No character identities, gear stats or credentials are included. URL presence is not an HTTP availability check. Changed references are excluded from ID fallback. Older imports need refreshing. Catalog slugs, official IDs and combat NPC IDs are separate namespaces; this report does not map NPC portraits or infer missing URLs."}
