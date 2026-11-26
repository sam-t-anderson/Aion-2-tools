"""The Maps page's words and geometry (0.2.433), as static/maps.js (``A2Maps``) works them out for the web page: the
Abyss PvP heat map from the log server (``/api/v1/pvp-heat``: its matchups, its status line, its five-step ramp, where
each square and boss is drawn and which one the pointer is over, its busiest squares), and the farming routes of the
bundled catalog (``static/farming-routes.json``). The native page (``maps_page.py``) draws them; the web page's
interactive maps (the provider's own page) are not part of it since 0.2.512.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
import html
import math
import re
import urllib.parse

from . import theme
from .news import when

HEAT_MAP_ID = 20
HEAT_CELLS = ((2000, "Normal squares (2,000)"), (1000, "Fine squares (1,000)"), (4000, "Coarse squares (4,000)"))
#: Where the web page keeps the square size and the matchup chosen (maps.js ``HEAT_DETAIL``, ``HEAT_MATCHUP``), with the
#: app's interface data since 0.2.482: the native page keeps them there too since 0.2.496.
CELL_KEY, MATCHUP_KEY = "aion2.maps.heatCell", "aion2.maps.heatMatchup"
HEAT_REGIONS = {"nae": "NA East", "naw": "NA West", "eu": "Europe", "la": "South America", "as": "Asia"}
HEAT_SHORT = {1800: "last 30 min", 7200: "last 2 h", 21600: "last 6 h", 86400: "last 24 h", 604800: "last 7 days"}
HEAT_WINDOWS = {1800: "the last 30 minutes", 7200: "the last 2 hours", 21600: "the last 6 hours",
                86400: "the last 24 hours", 604800: "the last 7 days"}
#: The heat ramp, few hits to many, and the ground and surface under it (workshop.css ``.heat-panel``, dark theme).
RAMP = ("#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4")
GROUND, SURFACE = "#1f2940", "#0f1524"
NOT_OFFERED = "The community server does not offer the PvP heat map yet."
BUSIEST = 25
PAD = 12


def num(value) -> str:
    """``Number(n || 0).toLocaleString('en-US')``: grouped by commas, to at most three places."""
    try:
        x = float(value or 0)
    except (TypeError, ValueError):
        return "NaN"
    if not math.isfinite(x):
        return "NaN" if math.isnan(x) else ("∞" if x > 0 else "-∞")
    rounded = Decimal(repr(x)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    whole, _, part = f"{abs(rounded):f}".partition(".")
    part = part.rstrip("0")
    return ("-" if rounded.is_signed() else "") + f"{int(whole):,}" + ("." + part if part else "")


def plural(value, one: str, many: str) -> str:
    try:
        single = float(value) == 1
    except (TypeError, ValueError):
        single = False
    return f"{num(value)} {one if single else many}"


# ------------------------------------------------------------------ the heat map
def kept_cell(text) -> int:
    """``rememberedCell``: the square size kept, else 2,000."""
    from .character import js_number
    value = js_number(text)
    return next((size for size, _words in HEAT_CELLS if size == value), 2000)


def kept_matchup(text) -> str:
    """``rememberedMatchup``: the matchup kept, else none (the busiest then)."""
    return text if isinstance(text, str) else ""


def heat_path(cell: int, matchup: str = "") -> str:
    """What the page asks the log server for: the Abyss map, the square size and the matchup."""
    query = f"map={HEAT_MAP_ID}&cell={urllib.parse.quote(str(cell), safe='')}"
    if matchup:
        query += "&matchup=" + urllib.parse.quote(matchup, safe="")
    return "/api/v1/pvp-heat?" + query


def heat_step(hits, top) -> int:
    """A square's step of the ramp (0–4) by its hits, on a log scale from one to the busiest square's (``heatStep``)."""
    if top <= 1:
        return 4
    return max(0, min(4, math.floor(5 * math.log(hits) / math.log(top + 1e-9) - 1e-9)))


def most_hits(data: dict) -> int:
    return max([1, *(cell[2] for cell in data.get("cells") or [])])


def matchup_name(matchup) -> str:
    """A matchup as the page names it: "Israphel vs Zikel (NA East)", or every server."""
    if not matchup:
        return "every server"
    region = HEAT_REGIONS.get(matchup.get("region"))
    return f"{matchup.get('label')}{f' ({region})' if region else ''}"


def matchup_groups(data: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """The matchups by region in NC's order, each with its window or that it has too few uploaders, then every
    server pooled (``listMatchups``)."""
    listed = [m for m in data.get("matchups") or [] if isinstance(m, dict)]
    groups = []
    for region, name in HEAT_REGIONS.items():
        mine = [m for m in listed if m.get("region") == region]
        if mine:
            groups.append((name, [(str(m.get("id")), f"{m.get('label')} · " + (
                HEAT_SHORT.get(m.get("window_seconds"), "recent") if m.get("available") else "too few uploaders yet"))
                for m in mine]))
    groups.append(("", [("all", "Every server, pooled")]))
    return groups


def matchups_key(data: dict) -> str:
    return repr([(m.get("id"), m.get("available"), m.get("window_seconds")) for m in data.get("matchups") or []
                 if isinstance(m, dict)])


def busiest(data: dict) -> str:
    """With no choice yet, the matchup with the most uploaders last week among those with a map, else every server."""
    open_ = sorted((m for m in data.get("matchups") or [] if isinstance(m, dict) and m.get("available")),
                   key=lambda m: (-(m.get("uploaders_7d") or 0), -(m.get("fights_7d") or 0)))
    return str(open_[0].get("id")) if open_ else "all"


def chosen(matchup: str, data: dict) -> str:
    """The matchup shown: the one chosen while the log server lists it (or every server), else every server."""
    ids = {str(m.get("id")) for m in data.get("matchups") or [] if isinstance(m, dict)}
    return matchup if matchup and (matchup == "all" or matchup in ids) else "all"


def status_line(data: dict, now_s: float) -> str:
    """What the map shows, or why there is none yet (``describe``)."""
    shown_at = when((data.get("generated_at") or now_s) * 1000)
    who = matchup_name(data.get("matchup"))
    if data.get("available"):
        cells = data.get("cells") or []
        hidden = data.get("hidden_cells")
        left_out = (f" ({plural(hidden, 'square', 'squares')} only one uploader recorded "
                    f"{'is' if hidden == 1 else 'are'} left out)") if hidden else ""
        return (f"{who[:1].upper() + who[1:]}, {HEAT_WINDOWS.get(data.get('window_seconds'), 'recent fights')}: "
                f"{plural(data.get('fights'), 'fight', 'fights')} from {plural(data.get('uploaders'), 'uploader', 'uploaders')}, "
                f"{plural(data.get('hits'), 'PvP hit', 'PvP hits')} and {plural(data.get('kills'), 'kill', 'kills')} in "
                f"{plural(len(cells), 'square', 'squares')}{left_out}. Updated {shown_at}.")
    week = next((w for w in data.get("windows") or [] if isinstance(w, dict) and w.get("seconds") == 604800),
                {"uploaders": 0})
    meanwhile = " Meanwhile the map shows the ground recordings have covered." if data.get("footprint") else ""
    return (f"Not enough recorded Abyss PvP for {who} yet: the map needs fights from at least "
            f"{data.get('min_uploaders') or 3} uploaders within 7 days, and has "
            f"{plural(week.get('uploaders'), 'uploader', 'uploaders')}. Public Live Meter logs of Abyss fights add to it."
            f"{meanwhile}")


def failure(why: str) -> str:
    """Why the map could not be read, as the web page says it."""
    if re.search(r"not found|404|not served", why or "", re.I):
        return NOT_OFFERED
    return f"The PvP heat map could not be loaded: {why}"


def described(data: dict) -> str:
    """The map's description for a screen reader (the canvas's ``aria-label``)."""
    cells = data.get("cells") or []
    if data.get("available") and cells:
        return (f"Abyss PvP heat map of {matchup_name(data.get('matchup'))}: {plural(len(cells), 'square', 'squares')} "
                f"with PvP over {HEAT_WINDOWS.get(data.get('window_seconds'), 'the window shown')}, the busiest with "
                f"{plural(most_hits(data), 'hit', 'hits')}. The table below lists them.")
    return "The ground recordings have covered in the Abyss, with no PvP squares to show."


def busiest_squares(data: dict) -> tuple[list[list[str]], str]:
    """The 25 busiest squares as the table's rows (its x and y ranges, hits and kills), and the line under them when
    there are more."""
    cell = data.get("cell_size") or 2000
    cells = sorted((c for c in data.get("cells") or []), key=lambda c: (-c[2], -c[3]))
    rows = [[f"{num(c[0] * cell)} to {num((c[0] + 1) * cell)}", f"{num(c[1] * cell)} to {num((c[1] + 1) * cell)}",
             num(c[2]), num(c[3])] for c in cells[:BUSIEST]]
    more = f"The {BUSIEST} busiest of {num(len(cells))} squares." if len(cells) > BUSIEST else ""
    return rows, more


def refresh_ms(data: dict | None) -> int:
    """How often the map is read again: what the log server says, at least five minutes."""
    try:
        seconds = float((data or {}).get("refresh_seconds") or 900)
    except (TypeError, ValueError):
        seconds = 900
    return int(max(300, seconds) * 1000)


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _square(square) -> tuple[int, int] | None:
    """A square's place (``[x, y, ...]``, in squares), or None where it has none."""
    if isinstance(square, (list, tuple)) and len(square) >= 2 and _number(square[0]) and _number(square[1]):
        return int(square[0]), int(square[1])
    return None


#: A patch of recorded ground this share of all of it, or larger, is drawn whole even without PvP or a boss in it;
#: one of ``SPECK`` squares or fewer never is.
GROUND_PART, SPECK = 0.05, 3


def drawn_bounds(data: dict) -> dict | None:
    """The part of the Abyss the map shows (``drawnBounds``, 0.2.509): the log server's ``bounds``, less the ground
    squares lying apart from the rest with no PvP square and no boss in them. Its bounds take in every square recordings
    have covered; three recorded far off on the map's middle line (players' positions as they load in, as it seems)
    made the Abyss ten times wider than it is, and its map a thin strip. A patch of ground (squares touching, corners
    too) stays where it holds a PvP square or a boss, or is at least ``GROUND_PART`` of the ground and more than a
    ``SPECK``; with nothing left out, the bounds are the log server's as they are."""
    bounds = data.get("bounds")
    if not bounds:
        return None
    cell = data.get("cell_size") or 2000
    ground = {square for square in map(_square, data.get("footprint") or []) if square is not None}
    if not ground:
        return bounds
    heat = {square for square in map(_square, data.get("cells") or []) if square is not None}
    marks = [(boss["x"], boss["y"]) for boss in data.get("landmarks") or []
             if isinstance(boss, dict) and _number(boss.get("x")) and _number(boss.get("y"))]
    held = heat | {(math.floor(x / cell), math.floor(y / cell)) for x, y in marks}
    parts, seen = [], set()
    for start in sorted(ground):
        if start in seen:
            continue
        seen.add(start)
        part, waiting = [], [start]
        while waiting:
            x, y = waiting.pop()
            part.append((x, y))
            for near in ((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                if near in ground and near not in seen:
                    seen.add(near)
                    waiting.append(near)
        parts.append(part)
    least = max(GROUND_PART * len(ground), SPECK + 1)
    kept = [part for part in parts if len(part) >= least or held.intersection(part)] or [max(parts, key=len)]
    if sum(len(part) for part in kept) == len(ground):
        return bounds
    squares = [square for part in kept for square in part] + sorted(heat)
    x0, x1 = min(x for x, _ in squares) * cell, (max(x for x, _ in squares) + 1) * cell
    y0, y1 = min(y for _, y in squares) * cell, (max(y for _, y in squares) + 1) * cell
    for x, y in marks:
        x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
    return {"x": [x0, x1], "y": [y0, y1]}


def view(data: dict, width: float, window_height: float, bounds: dict | None = None) -> dict | None:
    """Where the map is drawn in a frame ``width`` wide (``layout``): its scale, padding and size, north up, over
    ``bounds`` (``drawn_bounds``, worked out here where not given)."""
    bounds = bounds or drawn_bounds(data)
    if not bounds:
        return None
    (x0, x1), (y0, y1) = bounds["x"], bounds["y"]
    width = max(240, width or 600)
    tallest = max(260, min(720, theme.js_round((window_height or 900) * .72)))
    s = min((width - 2 * PAD) / max(1, x1 - x0), (tallest - 2 * PAD) / max(1, y1 - y0))
    w, h = theme.js_round((x1 - x0) * s + 2 * PAD), theme.js_round((y1 - y0) * s + 2 * PAD)
    return {"cell": data.get("cell_size") or 2000, "x0": x0, "y1": y1, "s": s, "ox": theme.js_round((width - w) / 2),
            "w": w, "h": h, "width": width}


def box(v: dict, cx: int, cy: int) -> tuple[float, float, float]:
    """A square's corner and side on the map."""
    c = v["cell"]
    return v["ox"] + PAD + (cx * c - v["x0"]) * v["s"], PAD + (v["y1"] - (cy + 1) * c) * v["s"], c * v["s"]


def at(v: dict, x: float, y: float) -> tuple[float, float]:
    """A world position on the map."""
    return v["ox"] + PAD + (x - v["x0"]) * v["s"], PAD + (v["y1"] - y) * v["s"]


def under(v: dict, data: dict, px: float, py: float):
    """What the pointer is over (``pointer``): ``("cell", cell)``, ``("boss", landmark)`` or None."""
    x, y = v["x0"] + (px - v["ox"] - PAD) / v["s"], v["y1"] - (py - PAD) / v["s"]
    c = data.get("cell_size") or 2000
    cx, cy = math.floor(x / c), math.floor(y / c)
    found = next((cell for cell in data.get("cells") or [] if cell[0] == cx and cell[1] == cy), None)
    if found is not None:
        return "cell", found
    boss = next((b for b in data.get("landmarks") or [] if math.hypot(at(v, b["x"], b["y"])[0] - px,
                                                                      at(v, b["x"], b["y"])[1] - py) <= 9), None)
    return ("boss", boss) if boss is not None else None


def tip(data: dict, found) -> tuple[str, str, str]:
    """The tip under the pointer: its lead, its line and where it is."""
    kind, thing = found
    if kind == "cell":
        c = data.get("cell_size") or 2000
        return (plural(thing[2], "PvP hit", "PvP hits"), plural(thing[3], "kill", "kills") if thing[3] else "no kills",
                f"x {num(thing[0] * c)} to {num((thing[0] + 1) * c)} · y {num(thing[1] * c)} to {num((thing[1] + 1) * c)}")
    return str(thing.get("name") or ""), "a recorded boss", f"x {num(thing.get('x'))} · y {num(thing.get('y'))}"


# ------------------------------------------------------------------ the farming routes
def zone_label(zone: dict) -> str:
    faction = zone.get("faction")
    return f"{zone.get('name')}{f' ({faction})' if faction and faction != 'both' else ''}"


def route_summary(route: dict) -> str:
    """A route's title line (its ``<summary>``)."""
    legs = len(route.get("legs") or [])
    start = route.get("start") or {}
    where = (f" · starts in {start['area']}" + (" (near a teleport)" if start.get("near_teleport") else "")
             if start.get("area") else "")
    return f"{route.get('title')} · {route.get('count')} {route.get('item')} · {legs} leg{'' if legs == 1 else 's'}{where}"


def leg_line(route: dict, leg: dict) -> str:
    """A leg as rich text: its area, how many and its waypoints."""
    item = str(route.get("item"))
    one = item[:-1] if item.endswith("s") else item
    count = leg.get("count")
    points = f"waypoint {leg.get('from')}" if count == 1 else f"waypoints {leg.get('from')}–{leg.get('to')}"
    return (f"{html.escape(str(leg.get('area') or 'unnamed area'))} — {count} {html.escape(one if count == 1 else item)} "
            f"<span style='color: {theme.COLORS['muted']};'>({points})</span>")


def waypoint_line(point: dict) -> str:
    return (f"{html.escape(str(point.get('area') or '—'))} <span style='color: {theme.COLORS['muted']};'>"
            f"({point.get('x')}, {point.get('y')})</span>")


def source_line(route: dict, source) -> str:
    """Where the route's waypoints come from, with its links (rich text)."""
    if not isinstance(source, dict):
        return "Source: " + html.escape(str(route.get("source")))
    link = lambda href, words: (f"<a href='{html.escape(str(href), quote=True)}' "        # noqa: E731
                                f"style='color: {theme.COLORS['accent']};'>{html.escape(str(words))}</a>")
    return (f"Source: {link(source.get('url'), source.get('name'))} · {link(source.get('license_url'), source.get('license'))}"
            f" · {html.escape(str(source.get('attribution')))} · commit {html.escape(str(source.get('revision') or '')[:12])}")


def route_text(zone: dict, route: dict, source) -> str:
    """The route as plain text for the clipboard (``routeText``)."""
    where = (f"{source.get('name')} ({source.get('license')}, {source.get('url')}, commit "
             f"{str(source.get('revision') or '')[:12]})" if isinstance(source, dict) else str(route.get("source")))
    lines = [f"{zone.get('name')} · {route.get('title')} · {route.get('count')} {route.get('item')}", f"Source: {where}",
             str(route.get("method")), ""]
    lines += [f"{w.get('n')}. {w.get('area') or '—'} ({w.get('x')}, {w.get('y')})" for w in route.get("waypoints") or []]
    return "\n".join(lines)


def catalog_line(data: dict) -> str:
    return f"{data.get('note') or ''} Catalog built {when(data.get('generated_at'))}."
