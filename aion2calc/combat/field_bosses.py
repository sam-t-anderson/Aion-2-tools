"""Observed field-boss kills for the player's own server and faction.

The log server's public kill feed (``/api/v1/boss-kills``) carries the field and world boss
kills found in uploaded Live Meter recordings and in the opt-in standalone auto-reports (a kill
seen only by auto-reports needs two installs to agree): observations from the live meter only.
The Fera Discord bot reads that same feed; the kill times people type into the bot
(``/timers killed``) live in the bot's own database and never reach the feed, and this module
reads nothing else -- so a manually entered time can never move a timer here.

Who sees what: a kill is placed by the server on the home server of the characters who fought
the boss, and the bundled reference (``field-bosses.json``) says which faction's zone each boss
stands in. The overlay and the Timers page show the kills for the player's identified server and
faction only (the Abyss bosses, reachable by both factions, for either). The faction is resolved
once from the official character search for the recorded character name and server, and cached.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import aion2calc

REFERENCE_FILE = Path(aion2calc.__file__).resolve().parent / "app" / "static" / "field-bosses.json"
FEED_WINDOW_S = 48 * 3600          # kills this old are still worth a timer (the feed's maximum)
DUE_GRACE_S = 30 * 60              # keep a boss listed this long after its expected return
FACTION_CACHE = ("community", "factions.json")
FACTION_POSITIVE_TTL_S = 30 * 86400
FACTION_NEGATIVE_TTL_S = 86400
BOTH = "abyss"                     # the reference's faction value for the Abyss bosses

NOTE = ("Kills observed by the live meter (uploaded recordings and corroborated auto-reports) on your "
        "server, for your faction's zones and the Abyss. Kill times use the recorder clock and arrive "
        "when a recording is uploaded; the expected return is the community respawn reference, "
        "unverified. Manual Discord timers are never used.")

_reference: dict | None = None

# Open-world map ids per faction zone, for the three bosses the reference lists in both Verteron
# and Altgard under one name (Silent Dartan, Soul Ruler Kashapa, High Commander Lagta) with
# different respawns. Altgard's ids come from the live kill feed (every Altgard boss kill sits on
# map 1110, one on the 1100 base map); Verteron takes the paired numbering of the bundled
# open-world map table (1000/1010/1011 beside 1100/1110/1111) and is unverified by a kill yet.
# A kill of an ambiguous name on any other map keeps both zones' faction and no reference respawn.
ZONE_MAPS = {"asmodian": frozenset({1100, 1110, 1111}) | frozenset(range(110001, 112000)),
             "elyos": frozenset({1000, 1010, 1011}) | frozenset(range(100001, 102000))}
ZONE_NAMES = {"asmodian": "Altgard", "elyos": "Verteron"}


def faction_of_map(map_id) -> str | None:
    """The faction whose zone an open-world map belongs to (``elyos`` / ``asmodian``), else None."""
    if isinstance(map_id, bool) or not isinstance(map_id, int):
        return None
    for faction, maps in ZONE_MAPS.items():
        if map_id in maps:
            return faction
    return None


def _key(name: str) -> str:
    """Boss names as the catalog and the reference spell them differ in punctuation
    ("Argo, the Spirit King" / "Argo the Spirit King"): compare without it."""
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum() or ch == " ").strip()


def reference(path: Path | None = None) -> dict:
    """The bundled respawn reference keyed by lower-case boss name: ``{name: [boss, ...]}``
    (a name the reference lists in both factions' zones has two rows)."""
    global _reference
    if path is None and _reference is not None:
        return _reference
    table: dict = {}
    try:
        data = json.loads((path or REFERENCE_FILE).read_text(encoding="utf-8"))
        rows = data.get("bosses") if isinstance(data, dict) else None
        for b in rows or []:
            if isinstance(b, dict) and b.get("name"):
                table.setdefault(_key(b["name"]), []).append(b)
    except (OSError, ValueError, TypeError, KeyError):
        table = {}
    if path is None:
        _reference = table
    return table


def boss_entry(name: str, table: dict | None = None, map_id=None) -> dict | None:
    """The reference row for ``name``; with two rows (one per faction zone) the map the kill was
    recorded on picks the zone, else a merged row that belongs to both factions and carries no
    reference respawn (the two zones' respawns differ)."""
    rows = (table if table is not None else reference()).get(_key(name)) or []
    if len(rows) == 1:
        return rows[0]
    if not rows:
        return None
    if isinstance(map_id, int) and not isinstance(map_id, bool):
        for faction, maps in ZONE_MAPS.items():
            if map_id in maps:
                for row in rows:
                    if str(row.get("faction") or "").casefold() == faction:
                        return row
    merged = dict(rows[0])
    merged["faction"] = BOTH
    merged["zone"] = " / ".join(str(r.get("zone") or "") for r in rows)
    merged["respawn_minutes"] = rows[0].get("respawn_minutes") if len({r.get("respawn_minutes") for r in rows}) == 1 else None
    return merged


def faction_of_boss(name: str, table: dict | None = None, map_id=None) -> str | None:
    """``elyos`` / ``asmodian`` / ``abyss`` (both factions) from the reference, else None."""
    entry = boss_entry(name, table, map_id)
    return str(entry.get("faction")).casefold() if entry and entry.get("faction") else None


def relevant(kills: list, faction: str | None, now: float | None = None, table: dict | None = None) -> list[dict]:
    """The feed's kills that concern ``faction`` (its zones plus the Abyss), each with the
    expected return: the reference respawn after the kill when the reference knows one, else
    the feed's measured respawn, else none. Ordered by the return (unknown last). A boss whose
    expected return passed more than ``DUE_GRACE_S`` ago is dropped; a kill older than the feed
    window is dropped."""
    now = time.time() if now is None else now
    wanted = str(faction or "").casefold()
    out = []
    for kill in kills or ():
        if not isinstance(kill, dict):
            continue
        name = str(kill.get("boss") or "")
        killed_at = kill.get("killed_at")
        if not name or not isinstance(killed_at, (int, float)) or killed_at < now - FEED_WINDOW_S:
            continue
        map_id = kill.get("map_id")
        entry = boss_entry(name, table, map_id) or {}
        # Where the kill was recorded decides whose timer it is: a kill on an Altgard map is an
        # Asmodian timer whatever the reference says of the name (names the catalog and the
        # reference spell differently, or a boss the reference does not list yet, still count).
        # The reference's faction serves when the map is not a known faction zone.
        map_faction = faction_of_map(map_id)
        ref_faction = str(entry.get("faction") or "").casefold() or None
        if map_faction and ref_faction not in (None, map_faction):
            entry = {}   # the row describes another zone's copy (or an Abyss namesake): keep nothing of it
        boss_faction = map_faction or ref_faction
        if wanted and boss_faction not in (wanted, BOTH):
            continue
        zone = entry.get("zone") or (ZONE_NAMES.get(map_faction) if map_faction else None)
        minutes = entry.get("respawn_minutes")
        if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0:
            expected, basis = killed_at + minutes * 60, "reference"
        elif isinstance(kill.get("respawn_at"), (int, float)):
            expected, basis = kill["respawn_at"], "measured"
        else:
            expected, basis = None, None
        if expected is not None and expected < now - DUE_GRACE_S:
            continue
        out.append({"boss": name, "npc_id": kill.get("npc_id"), "map_id": map_id, "zone": zone,
                    "faction": boss_faction, "killed_at": killed_at, "expected_at": expected,
                    "respawn_basis": basis, "respawn_minutes": minutes if basis == "reference" else None,
                    "reports": kill.get("reports"), "server": kill.get("server"),
                    "server_name": kill.get("server_name"), "logs": list(kill.get("logs") or [])[:3]})
    out.sort(key=lambda k: (k["expected_at"] is None, k["expected_at"] or 0, -k["killed_at"]))
    return out


def fetch(server_id) -> dict:
    """The feed for one game server, through the configured log server (read-only)."""
    from . import share
    return share.community_request(f"/api/v1/boss-kills?server={int(server_id)}&window={FEED_WINDOW_S}")


def _cache_read() -> dict:
    try:
        from ..paths import read_json, data_file
        rows = read_json(*FACTION_CACHE) if data_file(*FACTION_CACHE).exists() else {}
        return rows if isinstance(rows, dict) else {}
    except Exception:
        return {}


def _cache_write(rows: dict) -> None:
    try:
        from ..paths import write_user_json
        write_user_json(rows, *FACTION_CACHE)
    except Exception:
        pass


def faction_from_race(value) -> str | None:
    """``elyos`` / ``asmodian`` from an official race value, else None (never guessed from
    a code we have not seen spelled out)."""
    from ..sources.character import faction_of
    return faction_of({"race": value}) if isinstance(value, str) else None


def faction_for(name: str, server_id, region: str | None = None, *, search=None, now: float | None = None) -> str | None:
    """The faction of the character ``name`` on ``server_id``: cached, else resolved once from
    the official character search (the region the server resolves to, or every region when it
    is unknown). A failed or empty lookup is remembered for a day so the search is not repeated
    on every refresh; a resolved faction is kept for a month."""
    name = str(name or "").strip()
    if not name or not server_id:
        return None
    now = time.time() if now is None else now
    key = f"{server_id}:{name.casefold()}"
    rows = _cache_read()
    cached = rows.get(key)
    if isinstance(cached, dict):
        ttl = FACTION_POSITIVE_TTL_S if cached.get("faction") else FACTION_NEGATIVE_TTL_S
        if isinstance(cached.get("checked_at"), (int, float)) and now - cached["checked_at"] < ttl:
            return cached.get("faction") or None
    if search is None:
        from ..sources.official import search as _search
        search = _search
    from ..meter.metadata import REGIONS
    regions = [region] if region in REGIONS else list(REGIONS)
    faction, source = None, None
    for code in regions:
        try:
            found = search(name, code, int(server_id))
        except Exception:
            continue
        exact = [c for c in found or () if isinstance(c, dict) and str(c.get("name") or "").casefold() == name.casefold()
                 and str(c.get("server_id") or "") == str(server_id)]
        if exact:
            faction = faction_from_race(exact[0].get("race"))
            source = f"official character search ({code})" if faction else None
            break
    rows[key] = {"faction": faction, "source": source, "checked_at": now, "name": name, "server": str(server_id)}
    _cache_write({k: v for k, v in list(rows.items())[-200:]})
    return faction


def document(server_id, name: str, faction: str | None, kills: list, *, server_name: str | None = None,
             now: float | None = None) -> dict:
    """What the overlay and the Timers page read from the meter snapshot."""
    now = time.time() if now is None else now
    return {"server": str(server_id), "server_name": server_name, "character": name, "faction": faction,
            "fetched_at": now, "kills": relevant(kills, faction, now) if faction else [],
            "source": "live meter observations (uploaded recordings and corroborated auto-reports)",
            "note": NOTE}
