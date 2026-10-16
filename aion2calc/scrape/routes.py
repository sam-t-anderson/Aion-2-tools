"""Farming-route catalog from permitted sources, attributed, never invented.

The Maps page shows ordered waypoint loops beside the embedded map. Every waypoint comes from a
source whose terms allow reuse (today: the AION 2 Interactive Map's marker data, CC BY-NC 4.0),
and the loop order is computed here (nearest-neighbour plus 2-opt) and said to be computed. A
zone with no permitted source gets no route, only links to guides, and says so.

    python -m aion2calc routes-build --source <clone>/public/data --revision <commit> [--out FILE]
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path

SOURCES = {
    "aion2-interactive-map": {
        "name": "AION 2 Interactive Map (tc-imba)",
        "url": "https://aion2-interactive-map.github.io/aion2-interactive-map/",
        "repository": "https://github.com/aion2-interactive-map/aion2-interactive-map",
        "license": "CC BY-NC 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "attribution": "Marker data © 2025 Yihao Liu (tc-imba), CC BY-NC 4.0 (non-commercial use with credit)",
        "what": "marker positions under public/data (collection points, teleports, named areas)",
    },
}
# Source map -> the zone it shows. Starter and later maps carry no markers in the source yet.
MAPS = {
    "World_L_A": {"id": "verteron", "name": "Verteron", "faction": "elyos", "provider_map": "verteron"},
    "World_D_A": {"id": "altgard", "name": "Altgard", "faction": "asmodian", "provider_map": "altgard"},
    "Abyss_Reshanta_A": {"id": "reshanta", "name": "Chaotic Lower Reshanta (Abyss)", "faction": "both", "provider_map": None},
}
EMPTY_ZONES = [
    {"id": "poeta", "name": "Poeta", "faction": "elyos", "provider_map": "poeta"},
    {"id": "ishalgen", "name": "Ishalgen", "faction": "asmodian", "provider_map": "ishalgen"},
]
COLLECTIONS = {
    "hiddenCube": ("Hidden Cube loop", "Hidden Cubes", "Hidden Cubes respawn, so a loop over every known cube is a repeatable farm."),
    "monolithMaterial": ("Monolith material loop", "Monolith materials", "Monolith material pickups, grouped by named area."),
}
# Guides without reuse terms are linked, never copied. Keyed by zone id; "topic" says what each covers.
GUIDES = {
    "verteron": [
        {"title": "Best Diamond Farming Route in Aion 2 (Game Rant)", "url": "https://gamerant.com/aion-2-where-to-get-diamonds-farming-guide/", "topic": "Diamond nodes (Elun River Marsh)"},
        {"title": "Aion 2 Sapphire Farming: Best Routes and Node Locations (allthings.how)", "url": "https://allthings.how/aion-2-sapphire-farming-best-routes-and-node-locations/", "topic": "Sapphire nodes (Scarlet Forest, Pilgrim's Ridge, Ellun River Midstream)"},
        {"title": "Aion 2 Diamond Farming: Best Routes in Verteron and Altgard (allthings.how)", "url": "https://allthings.how/aion-2-diamond-farming-best-routes-in-verteron-and-altgard/", "topic": "Diamond nodes"},
        {"title": "Where to Farm Orichalcum Ore in AION 2 (allthings.how)", "url": "https://allthings.how/where-to-farm-orichalcum-ore-in-aion-2-plus-the-best-gathering-spots/", "topic": "Orichalcum ore (Eastern Cantas Valley)"},
        {"title": "How to Farm Odyle in AION 2: Best Gathering Spots (allthings.how)", "url": "https://allthings.how/how-to-farm-odyle-in-aion-2-best-gathering-spots/", "topic": "Odyle (flying nodes, Ellun River Midstream)"},
        {"title": "Aion 2 Gathering Guide: Sapphire routes (retrogems.fr)", "url": "https://retrogems.fr/en/aion-2-sapphire-farming-routes-guide/", "topic": "Sapphire nodes"},
        {"title": "AION 2 Orichalcum Farm Guide (gamerblurb)", "url": "https://gamerblurb.com/guides/aion-2-orichalcum-farm-guide", "topic": "Orichalcum ore"},
        {"title": "Leather Farm Routes, Respawns, and Cooking (aion2.website)", "url": "https://aion2.website/progression/leather-farm", "topic": "Mob loops for leather (Stone Beak Crest, Pilgrim's Rest, Verteron Fortress Valley)"},
        {"title": "AION 2 Hidden Cube Locations, Respawn Time, Rewards & Farm Route (aoeah)", "url": "https://www.aoeah.com/news/4890--aion-2-hidden-cube-locations-map-respawn-time-rewards-sound-keys--farm-route", "topic": "Hidden Cubes"},
        {"title": "Aion 2 Best Solo Farming Spots by Gear Level (2UpSkill)", "url": "https://2upskill.com/aion-2-best-solo-farming-spots-gold-and-materials-guide-by-gear-level-2026/", "topic": "Mob farming spots by gear level"},
    ],
    "altgard": [
        {"title": "Aion 2 Diamond Farming: Best Routes in Verteron and Altgard (allthings.how)", "url": "https://allthings.how/aion-2-diamond-farming-best-routes-in-verteron-and-altgard/", "topic": "Diamond nodes (Fafnite Deposit, Uruthumheim, Nameless Cemetery)"},
        {"title": "Aion 2 Sapphire Farming: Best Routes and Node Locations (allthings.how)", "url": "https://allthings.how/aion-2-sapphire-farming-best-routes-and-node-locations/", "topic": "Sapphire nodes (southwest of Sanctum Outpost)"},
        {"title": "Where to Farm Orichalcum Ore in AION 2 (allthings.how)", "url": "https://allthings.how/where-to-farm-orichalcum-ore-in-aion-2-plus-the-best-gathering-spots/", "topic": "Orichalcum ore (Basfelt Ruins)"},
        {"title": "How to Farm Odyle in AION 2: Best Gathering Spots (allthings.how)", "url": "https://allthings.how/how-to-farm-odyle-in-aion-2-best-gathering-spots/", "topic": "Odyle (Nameless Cemetery)"},
        {"title": "AION 2 Hidden Cube Locations, Respawn Time, Rewards & Farm Route (aoeah)", "url": "https://www.aoeah.com/news/4890--aion-2-hidden-cube-locations-map-respawn-time-rewards-sound-keys--farm-route", "topic": "Hidden Cubes"},
        {"title": "Aion 2 Best Solo Farming Spots by Gear Level (2UpSkill)", "url": "https://2upskill.com/aion-2-best-solo-farming-spots-gold-and-materials-guide-by-gear-level-2026/", "topic": "Mob farming spots by gear level"},
    ],
    "reshanta": [
        {"title": "Aion 2: What to Do in Chaotic Lower Reshanta (allthings.how)", "url": "https://allthings.how/aion-2-what-to-do-in-chaotic-lower-reshanta-abyss-guide/", "topic": "Abyss orientation, Command Scrolls, Odyle"},
        {"title": "AION 2 Abyss Guide: Points, Ranks, Sieges & Corridor (aion2builds.org)", "url": "https://aion2builds.org/guides/abyss/", "topic": "Abyss Points, corridors"},
        {"title": "Aion 2 Abyss Points and Currency Farming Guide (PixelNitro)", "url": "https://pixelnitro.com/aion-2-abyss-points-and-currency-farming-guide-best-locations-methods-and-mechanics/", "topic": "AP farming locations and methods"},
        {"title": "AION 2 Abyss Guide: Unlock, Abyss Points & Artifact Siege (metabot.gg)", "url": "https://metabot.gg/en/aion-2/guides/abyss-pvp-guide", "topic": "Entry, AP, sieges"},
        {"title": "AION 2 Abyss Points Guide: How to Farm AP Fast (timesaver.gg)", "url": "https://timesaver.gg/blog/aion-2-abyss-points-guide", "topic": "AP farming"},
    ],
}
GATHERING_NOTE = ("Gathering-node routes (ore, gems, logs, herbs, Odyle) and mob-farming loops: no source with reuse "
                  "terms publishes node or camp positions for this zone yet, so none is listed here; the guides "
                  "below describe them and are linked only.")


def pretty(camel: str) -> str:
    """'WesternCantasValley' -> 'Western Cantas Valley'; connectors and possessives repaired."""
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(camel or ""))
    text = re.sub(r"\b(\w+?)ofthe\b", r"\1 of the", text)
    text = re.sub(r"\b(\w+?)of\b", r"\1 of", text)
    text = re.sub(r"\b(Pilgrim|Idun|Siel)s\b", r"\1's", text)
    return " ".join(text.split())


def _inside(x: float, y: float, polygon) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            cross = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1
            if x < cross:
                inside = not inside
    return inside


def region_of(regions, x: float, y: float):
    """The named area containing the point, else the one whose border centroid is nearest."""
    best, best_d = None, None
    for region in regions:
        for polygon in region.get("borders") or []:
            points = [(float(p[0]), float(p[1])) for p in polygon if isinstance(p, (list, tuple)) and len(p) >= 2]
            if len(points) >= 3 and _inside(x, y, points):
                return region["name"]
            if points:
                cx = sum(p[0] for p in points) / len(points)
                cy = sum(p[1] for p in points) / len(points)
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best_d is None or d < best_d:
                    best, best_d = region["name"], d
    return best


def loop(points, start_index=0):
    """A short closed tour: nearest neighbour from ``start_index``, then 2-opt until no gain."""
    n = len(points)
    if n <= 2:
        return list(range(n))
    dist = lambda a, b: math.hypot(points[a][0] - points[b][0], points[a][1] - points[b][1])
    order, left = [start_index], set(range(n)) - {start_index}
    while left:
        last = order[-1]
        nxt = min(left, key=lambda i: (dist(last, i), i))
        order.append(nxt)
        left.remove(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[(j + 1) % n]
                if dist(a, c) + dist(b, d) < dist(a, b) + dist(c, d) - 1e-9:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
    return order


def _markers(data_dir: Path, map_name: str):
    import yaml
    markers = (yaml.safe_load((data_dir / "markers" / f"{map_name}.yaml").read_text(encoding="utf-8")) or {}).get("markers") or []
    regions_file = data_dir / "regions" / f"{map_name}.yaml"
    regions = (yaml.safe_load(regions_file.read_text(encoding="utf-8")) or {}).get("regions") or [] if regions_file.exists() else []
    return [m for m in markers if isinstance(m, dict) and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float))], regions


def build_route(subtype, markers, regions, teleports):
    rows = [m for m in markers if m.get("subtype") == subtype]
    if not rows:
        return None
    points = [(float(m["x"]), float(m["y"])) for m in rows]
    # Start at the point nearest a teleport (a loop you can reach quickly), else the north-west-most one.
    if teleports:
        start = min(range(len(points)), key=lambda i: min(math.hypot(points[i][0] - t[0], points[i][1] - t[1]) for t in teleports))
    else:
        start = min(range(len(points)), key=lambda i: (points[i][0] + points[i][1], i))
    order = loop(points, start)
    waypoints = []
    for n, i in enumerate(order, 1):
        region = rows[i].get("region") or region_of(regions, *points[i])
        waypoints.append({"n": n, "x": round(points[i][0]), "y": round(points[i][1]), "area": pretty(region) if region else None})
    legs = []
    for w in waypoints:
        if legs and legs[-1]["area"] == w["area"]:
            legs[-1]["to"] = w["n"]
            legs[-1]["count"] += 1
        else:
            legs.append({"area": w["area"], "from": w["n"], "to": w["n"], "count": 1})
    title, item, note = COLLECTIONS[subtype]
    length = sum(math.hypot(points[order[k]][0] - points[order[(k + 1) % len(order)]][0],
                            points[order[k]][1] - points[order[(k + 1) % len(order)]][1]) for k in range(len(order)))
    return {"id": subtype, "title": title, "item": item, "kind": "collection", "count": len(waypoints),
            "source": "aion2-interactive-map", "note": note,
            "method": "Waypoints are the source's marker positions on its map (8192-pixel map space, north-west origin); "
                      "the order is a computed nearest-neighbour loop with 2-opt, starting near a teleport. "
                      "It is a computed loop, not a community-verified route.",
            "start": {"area": waypoints[0]["area"], "near_teleport": bool(teleports)},
            "loop_length_px": round(length), "legs": legs, "waypoints": waypoints}


def build(data_dir, revision: str, checked_at: str | None = None) -> dict:
    data_dir = Path(data_dir)
    if not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ValueError("Use the full 40-character source commit SHA")
    zones = []
    for map_name, zone in MAPS.items():
        markers, regions = _markers(data_dir, map_name)
        teleports = [(float(m["x"]), float(m["y"])) for m in markers if m.get("subtype") == "teleport"]
        routes = [r for r in (build_route(sub, markers, regions, teleports) for sub in COLLECTIONS) if r]
        entry = {**zone, "routes": routes, "guides": GUIDES.get(zone["id"], []),
                 "notes": [GATHERING_NOTE] + ([] if routes else ["The source carries no markers for this zone yet; no route is listed."])}
        zones.append(entry)
    for zone in EMPTY_ZONES:
        zones.append({**zone, "routes": [], "guides": GUIDES.get(zone["id"], []),
                      "notes": ["No source with reuse terms covers this zone yet, so no route is listed; none is invented."
                                + ("" if GUIDES.get(zone["id"]) else " No guide links were found for it either.")]})
    return {"format": "a2routes", "version": 1,
            "generated_at": checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": {key: {**value, "revision": revision} for key, value in SOURCES.items()},
            "zones": zones,
            "note": "Every waypoint comes from a source whose terms allow reuse, credited above; loop order is computed and "
                    "labelled as such. Zones without such a source list guide links only. Map positions are the source's, "
                    "not in-game coordinates; open the source map to see them drawn."}


def write(data_dir, revision: str, out) -> dict:
    catalog = build(data_dir, revision)
    Path(out).write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return catalog
