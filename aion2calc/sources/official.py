"""Client for the official AION 2 character pages (aion2.plaync.com "Character Info").

These are the JSON endpoints the official site itself calls from the browser.
They are public (no login) but undocumented, so every response is treated as
best-effort and requests are throttled and cached.

Endpoints (global service; region codes nae/eu/as/la, from the site bundle)
    search      api-search.plaync.com/aion2global/search/v2/character
    servers     aion2.plaync.com/en-us/api/gameinfo/servers
    info        aion2.plaync.com/api/character/info          profile, stats, titles, Daevanion boards
    equipment   aion2.plaync.com/api/character/equipment     gear, skins, pet/wings, skill levels
    item        aion2.plaync.com/api/character/equipment/item  one equipped item with its rolls
    daevanion   aion2.plaync.com/api/character/daevanion/detail  nodes of one board
    gameconst   aion2.plaync.com/en-us/api/gameconst/item    any item by id (no character)
"""
from __future__ import annotations

import re
import time
import urllib.parse

from ..db import store
from ..scrape.http import fetch_json

SITE = "https://aion2.plaync.com"
SEARCH = "https://api-search.plaync.com/aion2global/search/v2/character"
REFERER = SITE + "/en-us/characters/index"
REGIONS = {"nae": "North America", "eu": "Europe", "as": "Asia", "la": "Latin America"}
#: official className -> aion2calc class key
CLASS_KEYS = {"Gladiator": "gladiator", "Templar": "templar", "Assassin": "assassin", "Ranger": "ranger",
              "Sorcerer": "sorcerer", "Elementalist": "spiritmaster", "Spiritmaster": "spiritmaster",
              "Cleric": "cleric", "Chanter": "chanter"}


def _get(path: str, **params):
    url = path if path.startswith("http") else SITE + path
    return fetch_json(url, {"lang": "en-US", **params}, referer=REFERER)


def servers(region: str = "nae") -> list[dict]:
    return _get("/en-us/api/gameinfo/servers", region=region).get("serverList", [])


def classes(region: str = "nae") -> list[dict]:
    return _get("/en-us/api/gameinfo/classes", region=region).get("classList", [])


def search(name: str, region: str = "nae", server_id: int | None = None, page: int = 1,
           size: int = 40) -> list[dict]:
    """Characters whose name matches ``name`` (official search, global regions)."""
    d = fetch_json(SEARCH, {"keyword": name, "region": region, "localeInfo": "en-US", "serverId": server_id,
                            "page": page, "size": size}, referer=REFERER)
    out = []
    for c in d.get("list", []):
        out.append({"character_id": urllib.parse.unquote(c["characterId"]),
                    "name": re.sub(r"<[^>]+>", "", c.get("name", "")), "level": c.get("level"),
                    "server_id": c.get("serverId"), "server": c.get("serverName"), "race": c.get("race"),
                    "pc_id": c.get("pcId"), "region": c.get("region") or region})
    out.sort(key=lambda c: -(c["level"] or 0))
    return out


def key_of(region: str, server_id: int, character_id: str) -> str:
    return f"{region}:{server_id}:{character_id}"


def fetch_character(character_id: str, server_id: int, region: str = "nae", details: bool = True,
                    use_cache: float = 0, progress=None) -> dict:
    """Everything the official profile shows, in one dict (stored in the local DB)."""
    conn = store.connect()
    key = key_of(region, server_id, character_id)
    if use_cache:
        row = conn.execute("SELECT fetched_at FROM characters WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] < use_cache:
            return store.character(conn, key)
    say = progress or (lambda msg: None)
    base = {"characterId": character_id, "serverId": server_id, "region": region}
    say("profile")
    info = _get("/api/character/info", **base)
    say("equipment")
    eq = _get("/api/character/equipment", **base)
    ch = {"region": region, "fetched_at": time.time(), **info, **eq, "items": {}, "daevanion_detail": {}}
    if details:
        for e in (eq.get("equipment") or {}).get("equipmentList", []):
            say(f"item {e.get('slotPosName')}")
            try:
                ch["items"][str(e["slotPos"])] = _get("/api/character/equipment/item", id=e["id"],
                                                      enchantLevel=e.get("enchantLevel", 0),
                                                      slotPos=e["slotPos"], **base)
            except Exception as err:   # one bad item should not lose the whole profile
                ch["items"][str(e["slotPos"])] = {"error": str(err), **e}
        for b in (info.get("daevanion") or {}).get("boardList", []):
            if not b.get("open"):
                continue
            say(f"daevanion {b.get('name')}")
            try:
                ch["daevanion_detail"][str(b["id"])] = _get("/api/character/daevanion/detail",
                                                            boardId=b["id"], **base)
            except Exception as err:
                ch["daevanion_detail"][str(b["id"])] = {"error": str(err)}
    store.put_character(conn, key, ch)
    return ch


def game_item(item_id: int, enchant: int = 0) -> dict:
    """Official item constants (stats at an enchant level, roll counts, sets)."""
    conn = store.connect()
    cached = store.official_item(conn, item_id, enchant)
    if cached:
        return cached
    d = _get("/en-us/api/gameconst/item", id=item_id, enchantLevel=enchant)
    store.put_official_item(conn, item_id, enchant, d)
    return d
