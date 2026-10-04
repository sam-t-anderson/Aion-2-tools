"""Monster genus (Cogni, Fera, Natura, Varian, Special) by name.

metabot's boss and monster pages show the genus as the monster's "Type". A
name is looked up once (``data/global/monster_genus.json`` in the user folder
caches the answers), so fights from AbyssLogs and A2DIL can be grouped by genus
for Genus Insight planning.
"""
from __future__ import annotations

import html
import re

from ..paths import data_file, read_json, write_user_json

GENERA = ("Cogni", "Fera", "Natura", "Varian", "Special")
_FILE = ("global", "monster_genus.json")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")


def known() -> dict:
    return read_json(*_FILE) if data_file(*_FILE).exists() else {}


def parse_type(page: str) -> str | None:
    body = re.sub(r"<(script|style).*?</\1>", "", page, flags=re.S)
    lines = [x.strip() for x in html.unescape(re.sub(r"<[^>]+>", "\n", body)).splitlines() if x.strip()]
    for i, line in enumerate(lines[:-1]):
        if line == "Type" and lines[i + 1] in GENERA:
            return lines[i + 1]
    return None


def genus_of(name: str | None, fetch_missing: bool = True) -> str | None:
    if not name:
        return None
    cache = known()
    if name in cache:
        return cache[name]
    if "scarecrow" in name.lower() or "dummy" in name.lower():
        return None
    if not fetch_missing:
        return None
    from ..scrape import metabot
    from ..scrape.http import fetch
    slug = slugify(name)
    urls = []
    for sm in ("aion-2",):
        try:
            urls = [u for u in metabot.sitemap(sm) if re.search(rf"/(bosses|monsters)/{re.escape(slug)}(-lv\d+)?$", u)]
        except Exception:
            urls = []
    genus = None
    for u in sorted(urls, key=lambda u: "/bosses/" not in u):
        try:
            genus = parse_type(fetch(u, max_age=30 * 86400))
        except Exception:
            genus = None
        if genus:
            break
    cache[name] = genus
    write_user_json(cache, *_FILE)
    return genus
