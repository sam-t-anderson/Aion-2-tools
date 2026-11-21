"""The featured encounters' words (0.2.455), as featured.js writes them. These are the encounters the log server's
operator puts at the top of Combat Logs. Each has its landing cards (progress, speed, execution, all stars and the
classes by role) and its pages: the race summary, progress, all reports, rankings and statistics.

Everything is read defensively, as the web page reads it. Where the web page would write a figure the server left out
as "undefined" or "NaN", these words write "—".
"""
from __future__ import annotations

import math
import re
import urllib.parse
from datetime import datetime

from .combat import encode_component, js_string
from .results import _dict, _list, _truthy, cap, js_text
from . import theme

VIEWS = (("race", "Race Summary"), ("progress", "Progress"), ("reports", "All Reports"), ("rankings", "Rankings"),
         ("statistics", "Statistics"))
ROLES = (("dps", "DPS"), ("tank", "Tank"), ("support", "Support"))
CLASSES = ("gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter")
REGIONS = {"nae": "NA", "na": "NA", "eu": "EU", "kr": "KR", "tw": "TW", "jp": "JP", "global": "Global"}
HEADING = "Featured encounters"
BACK = "← Back to combat logs"
LOADING = "Loading…"
NOT_REACHED = "Could not reach the log server."
NO_ADDRESS = "There is no featured encounter at this address."
NO_RECORDS = "No records yet."
MORE = "View more…"
OPEN_LOG = "Open its log"
NO_TEAM_YET = "No team yet"
NO_ATTEMPT = "No team has an attempt on record yet."
CLOSER = "A closer look"
ROLES_NOTE = ("Roles as the developers group the classes for party synergy: Gladiator and Templar tank, Cleric and Chanter "
              "support, the other four deal damage.")
RANKING_METRICS = (("dps", "DPS"), ("hps", "Healing per second"), ("speed", "Speed (teams)"))
RATE_METRICS = (("dps", "DPS"), ("hps", "Healing per second"))
ALL_REGIONS = "All regions"
ALL_CLASSES = "All classes"

PROGRESS_CAPTION = "Teams by progress"
PROGRESS_COLUMNS = ["Rank", "Team", "Progress", "Bosses killed", "Pulls", "Last progress"]
KILLS_CAPTION = "Final-boss kills, earliest first"
KILLS_COLUMNS = ["Rank", "Team", "Game version", "Party", "Date", "Duration", "Deaths", "Log"]
NO_KILL = "No kill on record yet."
REPORTS_CAPTION = "Public logs of this encounter, newest first"
REPORTS_COLUMNS = ["Uploaded", "Log", "Bosses", "Duration", "Players"]
NO_REPORT = "No public log yet."
SPEED_CAPTION = "Each team's fastest complete run"
SPEED_COLUMNS = ["Rank", "Team", "Time", "Game version", "Date", "Log"]
NO_SPEED = "No complete, speed-eligible run yet."
NO_RANKED = "No ranked player yet."
STATISTICS_COLUMNS = ["Class", "Role", "Samples", "25th", "Median", "75th", "95th", "Best", "Spread"]
NO_SAMPLE = "No ranked sample yet."


def _num(x):
    """A figure as JavaScript's ``+x`` reads it, or None for none (a missing, non-numeric or endless one)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _index(x) -> int | None:
    """A whole number (``Number.isInteger``), or None."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    return int(x) if isinstance(x, float) and x.is_integer() else None


def fig(x) -> str:
    """A figure written into a line (``${x}``); "—" when the server left it out."""
    return "—" if x is None else js_text(x)


def n0(x) -> str:
    value = _num(x)
    return "—" if value is None else f"{theme.js_round(value):,}"


def pct(x) -> str:
    value = _num(x)
    return "—" if value is None else theme.fixed(value, 1) + "%"


def clock(x) -> str:
    """A length as m:ss, or h:mm:ss from an hour; "—" for none."""
    value = _num(x)
    if value is None:
        return "—"
    s = theme.js_round(value)
    h, m, rest = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{rest:02d}" if h else f"{m}:{rest:02d}"


def when(t) -> str:
    """A moment in seconds, to the minute in the computer's clock (2026-10-23 15:04); "—" for none."""
    value = _num(t)
    if not _truthy(t) or value is None:
        return "—"
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


def world(server_id) -> str:
    """A server's world name from the bundled list (``A2Servers.label``), else its number."""
    if not _truthy(server_id):
        return ""
    from .timers import world_for
    return world_for(server_id, js_string(server_id))


def region(r) -> str:
    return (REGIONS.get(js_string(r).lower()) or js_string(r).upper()) if _truthy(r) else ""


def patch(p) -> str:
    return re.sub(r"^version:product:", "", js_string(p) if _truthy(p) else "")


def npc_code(key) -> str | None:
    """A boss's code in its key (npc:2400001 -> 2400001), for its bundled portrait."""
    match = re.match(r"npc:([0-9]+)", js_string(key) if _truthy(key) else "")
    return match.group(1) if match else None


def valid_id(fid) -> bool:
    return isinstance(fid, str) and re.fullmatch(r"fe_[0-9a-f]{10}", fid) is not None


def log_page(log_id, segment=None) -> str:
    """A public log's page in the web interface, at one of its fights when ``segment`` is one (``sharedLogLink``)."""
    index = _index(segment)
    return f"combat-log/shared/{encode_component(log_id)}" + (f"?segment={index}" if index is not None else "")


def where(team: dict) -> str:
    """Where a team plays: its server, "several servers" for a party across them, and its region."""
    first = world(team.get("server")) if _truthy(team.get("server")) else ("several servers" if team.get("kind") == "party" else "")
    return " · ".join(part for part in (first, region(team.get("region"))) if part)


def _class(cls) -> str:
    return js_string(cls) if _truthy(cls) else ""


def team_view(team) -> dict:
    """A team as ``teamHTML`` draws it: its name (a legion's gold), where it plays, and its members on hover."""
    team = _dict(team)
    legion = team.get("kind") == "legion"
    members = [m for m in _list(team.get("members")) if isinstance(m, dict)]
    return {"name": js_text(team.get("name")), "sub": where(team), "legion": legion, "kind": team.get("kind"),
            "tip": "Legion" if legion else ", ".join(js_string(m.get("name")) for m in members),
            "members": [{"name": js_text(m.get("name")), "class": _class(m.get("class"))} for m in members]}


def player_view(p) -> dict:
    """A character as ``playerHTML`` draws it: its name in its class's colour, and its server."""
    p = _dict(p)
    return {"name": js_text(p.get("name")), "class": _class(p.get("class")), "sub": world(p.get("server"))}


def progress_text(t: dict) -> str:
    """How far a team got (``progressText``): bosses killed of the phases, and its best try at the next one."""
    base = f"{fig(t.get('killed'))}/{fig(t.get('phases'))}"
    if _truthy(t.get("complete")) or t.get("best_hp") is None:
        return base
    return f"{base} · {pct(t.get('best_hp'))}"


def featured_page(view, metric=None) -> tuple[str, str]:
    """A featured page's view and metric, as ``page`` reads them: an unknown view is the race; only the rankings rank
    by speed."""
    view = view if view in dict(VIEWS) else "race"
    metric = metric if metric in ("dps", "hps", "speed") and (view == "rankings" or metric != "speed") else "dps"
    return view, metric


# ------------------------------------------------------------------ the landing cards
def zone_cards(f: dict) -> list[dict]:
    """A featured encounter's cards (``zone``), each with its title, its rows and the page it leads to. A row is
    (kind, who, value), its kind "team", "player" or "class"."""
    s = _dict(_dict(f).get("summary"))

    def team_rows(rows, value):
        return [("team", team_view(r.get("team")), value(r)) for r in _list(rows) if isinstance(r, dict)]

    def deaths(r):
        d = r.get("deaths")
        return f"{fig(d)} {'death' if d == 1 and not isinstance(d, bool) else 'deaths'} · {clock(r.get('seconds'))}"

    def points(p):
        value = _num(p.get("points"))
        return "—" if value is None else theme.fixed(value, 1)

    cards = [
        {"title": "Progress", "rows": team_rows(s.get("progress"), lambda t: "Complete" if _truthy(t.get("complete"))
                                                 else progress_text(t)), "more": ("progress", None)},
        {"title": "Speed", "rows": team_rows(s.get("speed"), lambda r: clock(r.get("elapsed"))), "more": ("rankings", "speed")},
        {"title": "Execution", "rows": team_rows(s.get("execution"), deaths), "more": ("progress", None)},
    ]
    for role, label in ROLES:
        rows = [("player", player_view(p), points(p)) for p in _list(_dict(s.get("all_stars")).get(role)) if isinstance(p, dict)]
        cards.append({"title": f"All Stars ({label})", "rows": rows, "more": ("rankings", None)})
    for role, label in ROLES:
        rows = [("class", {"class": _class(c.get("class")), "name": cap(_class(c.get("class")))}, n0(c.get("median")))
                for c in _list(_dict(s.get("classes")).get(role)) if isinstance(c, dict)]
        cards.append({"title": "DPS" if role == "dps" else f"{label} Damage", "rows": rows, "more": ("statistics", None)})
    return cards


def zone_note(f: dict) -> str:
    s = _dict(_dict(f).get("summary"))
    return (f"{n0(s.get('teams'))} teams · {n0(s.get('complete'))} cleared · {n0(s.get('pulls'))} recorded pulls. Speed is a "
            "team's fastest complete run; execution its final-boss kill with the fewest deaths; all stars a character's best "
            "parse on each boss, added up; the class cards the median recorded DPS.")


def featured_list(answer) -> list[dict]:
    return [f for f in _list(_dict(answer).get("featured")) if isinstance(f, dict)]


def note(answer) -> str:
    """The server's note under a list (``note``), or nothing."""
    d = _dict(answer)
    return js_text(d["note"]) if _truthy(d.get("note")) else ""


def title_line(f: dict) -> str:
    """A featured encounter's line under its title on its card: the boss and the difficulty."""
    return f"{js_text(f.get('boss'))} · {js_text(f.get('difficulty'))}"


def header_line(d: dict) -> str:
    """A featured page's line under its title: the boss, the difficulty and when the race runs."""
    line = title_line(d)
    if _truthy(d.get("starts_at")):
        line += f" · race from {when(d['starts_at'])}"
    if _truthy(d.get("ends_at")):
        line += f" to {when(d['ends_at'])}"
    return line


# ------------------------------------------------------------------ the pages
def featured_path(fid: str, view: str, state: dict) -> str:
    """A page's question to the server (``pathFor``)."""
    query = []
    if view in ("progress", "reports"):
        query.append(("page", str(state["page"])))
    if view in ("rankings", "statistics"):
        query.append(("metric", state["metric"]))
        if state.get("boss") and state["metric"] != "speed":
            query.append(("boss", state["boss"]))
        if state.get("cls") and view == "rankings" and state["metric"] != "speed":
            query.append(("class", state["cls"]))
    if state.get("region") and view != "reports":
        query.append(("region", state["region"]))
    text = urllib.parse.urlencode(query)
    return f"/api/v1/featured/{encode_component(fid)}/{view}" + (f"?{text}" if text else "")


def pager(answer, size) -> dict | None:
    """A page's pager when there is more than one page (``pager``): its words and which way it can turn."""
    d = _dict(answer)
    size = _num(size) or 30
    pages = max(1, math.ceil((_num(d.get("total")) or 0) / size))
    if pages <= 1:
        return None
    page = _index(d.get("page"))
    page = page if page is not None else 1
    return {"page": page, "pages": pages, "words": f"Page {page} of {pages}", "previous": page > 1, "next": page < pages}


def regions_offered(answer) -> list[tuple[str, str]]:
    """The regions the encounter was fought in, as the server lists them (``regionSelect``)."""
    return [(js_string(r), region(r)) for r in _list(_dict(answer).get("regions"))]


def boss_choices(f) -> list[tuple[str, str]]:
    return [(js_string(p.get("boss_key")), js_text(p.get("boss"))) for p in _list(_dict(f).get("phases")) if isinstance(p, dict)]


def _phase_at(phases: list[dict], index) -> dict:
    i = _index(index)
    return phases[i] if i is not None and 0 <= i < len(phases) else {}


def race(d, f) -> dict:
    """The race (``raceHTML``): the phases side by side over one bar, filled as far as the leading team got; each
    phase's teams and figures; the teams complete; and a closer look at the leading teams."""
    d, f = _dict(d), _dict(f)
    phases = [p for p in _list(d.get("phases")) if isinstance(p, dict)]
    teams = [t for t in _list(d.get("teams")) if isinstance(t, dict)]
    n = len(phases) or 1
    done = [t for t in teams if _truthy(t.get("complete"))]
    lead = max([0.0] + [(_num(t.get("position")) or 0.0) for t in teams])

    def standing(rows):
        return [{"rank": f"{fig(t.get('rank'))}.", "name": js_text(_dict(t.get("team")).get("name")),
                 "small": when(t.get("first_kill_at")) if _truthy(t.get("complete")) else (
                     pct(t.get("best_hp")) if t.get("best_hp") is not None else "pulling")} for t in rows[:10]]

    stats = []
    for p in phases:
        first = _dict(p.get("first_kill")) if _truthy(p.get("first_kill")) else None
        stats.append({"line": f"{n0(p.get('teams'))} reached · {n0(p.get('killed_by'))} killed",
                      "first": f"First: {js_text(_dict(first.get('team')).get('name'))}, {when(first.get('at'))}" if first else ""})
    furthest = "a team has completed it" if done else f"the leading team is {theme.js_round(100 * lead)}% of the way"
    closers = []
    for t in teams[:8]:
        team = team_view(t.get("team"))
        complete = _truthy(t.get("complete"))
        next_boss = js_text(_phase_at(phases, t.get("next_phase")).get("boss") or "")
        closers.append({"team": team, "rank": fig(t.get("rank")),
                        "members": team["members"] if team["kind"] == "party" else [],
                        "progress": f"{fig(t.get('killed'))}/{fig(t.get('phases'))}", "pulls": f"Pulls: {n0(t.get('pulls'))}",
                        "complete": complete, "state": "Complete!" if complete else "Working on",
                        "detail": when(t.get("first_kill_at")) if complete else (
                            next_boss + (f" · {pct(t.get('best_hp'))}" if t.get("best_hp") is not None else "")),
                        "log": t.get("log")})
    return {"phases": [{"key": p.get("boss_key"), "icon": p.get("icon"), "boss": js_text(p.get("boss")),
                        "title": f"Phase {i + 1}"} for i, p in enumerate(phases)],
            "fills": [theme.js_round(100 * max(0.0, min(1.0, lead * n - i))) for i in range(len(phases))],
            "done_fill": 100 if done else 0, "stats": stats, "complete": f"{n0(len(done))} complete",
            "lists": [standing([t for t in teams if not _truthy(t.get("complete")) and _index(t.get("next_phase")) == i])
                      for i in range(len(phases))],
            "done": standing(done), "label": f"{len(phases)} phases: {furthest}", "closers": closers}


def progress_rows(d, f) -> list[dict]:
    """Teams by progress (``progressHTML``): each team's rank, progress, the bosses it killed, pulls and last
    progress."""
    phases = [p for p in _list(_dict(f).get("phases")) if isinstance(p, dict)]
    rows = []
    for t in _list(_dict(d).get("progress")):
        if not isinstance(t, dict):
            continue
        killed = [p for p in (_phase_at(phases, i) for i in _list(t.get("killed_bosses"))) if p]
        rows.append({"rank": fig(t.get("rank")), "team": team_view(t.get("team")), "progress": progress_text(t),
                     "killed": [(p.get("boss_key"), p.get("icon"), js_text(p.get("boss"))) for p in killed],
                     "pulls": n0(t.get("pulls")), "at": when(t.get("progress_at"))})
    return rows


def kill_rows(d) -> list[dict]:
    """The final-boss kills, earliest first: each team, game version, party, date, duration, deaths and log."""
    rows = []
    for k in _list(_dict(d).get("kills")):
        if not isinstance(k, dict):
            continue
        rows.append({"rank": fig(k.get("rank")), "team": team_view(k.get("team")), "patch": patch(k.get("patch")),
                     "composition": [(js_string(c), fig(count)) for c, count in _dict(k.get("composition")).items()],
                     "at": when(k.get("at")), "time": clock(k.get("seconds")), "deaths": n0(k.get("deaths")),
                     "log": k.get("log")})
    return rows


def report_rows(d) -> list[dict]:
    """The encounter's public logs, newest first (``reportsHTML``)."""
    rows = []
    for log in _list(_dict(d).get("logs")):
        if not isinstance(log, dict):
            continue
        bosses = [js_text(c.get("boss")) for c in _list(log.get("contexts")) if isinstance(c, dict) and _truthy(c.get("boss"))]
        rows.append({"at": when(log.get("created_at")), "id": log.get("id"),
                     "title": js_text(log.get("title") or log.get("boss") or log.get("id")),
                     "uploader": js_text(log.get("uploader")) if _truthy(log.get("uploader")) else "Anonymous",
                     "bosses": ", ".join(bosses[:4]), "time": clock(log.get("duration")),
                     "players": [player_view(p) for p in _list(log.get("players"))[:8] if isinstance(p, dict)]})
    return rows


def speed_rows(d) -> list[dict]:
    """Each team's fastest complete run (the rankings by speed)."""
    return [{"rank": fig(r.get("rank")), "team": team_view(r.get("team")), "time": clock(r.get("elapsed")),
             "patch": patch(r.get("patch")), "at": when(r.get("at")), "log": r.get("log")}
            for r in _list(_dict(d).get("entries")) if isinstance(r, dict)]


def ranking_rows(d) -> list[dict]:
    """The ranked characters (``rankingsHTML``): each one's rate, parse, the fight's duration, date and log."""
    rows = []
    for i, r in enumerate(r for r in _list(_dict(d).get("entries")) if isinstance(r, dict)):
        parse = _num(r.get("parse"))
        rows.append({"rank": str(i + 1), "player": player_view(r), "class": _class(r.get("class")), "score": n0(r.get("score")),
                     "parse": "—" if parse is None else str(theme.js_round(parse)), "time": clock(r.get("duration")),
                     "at": when(r.get("created_at")), "log": r.get("log"), "segment": _index(r.get("segment"))})
    return rows


def ranking_columns(metric: str) -> list[str]:
    return ["Rank", "Player", "Class", "HPS" if metric == "hps" else "DPS", "Parse", "Duration", "Date", "Log"]


def ranking_caption(f, state: dict) -> str:
    phases = [p for p in _list(_dict(f).get("phases")) if isinstance(p, dict)]
    boss = next((p.get("boss") for p in phases if p.get("boss_key") == state.get("boss")), None) or _dict(f).get("boss")
    return f"{'Healing per second' if state.get('metric') == 'hps' else 'Damage per second'} · {js_text(boss)}"


def statistics_caption(metric: str) -> str:
    return f"Recorded {'healing' if metric == 'hps' else 'damage'} per second by class"


def statistics_rows(d) -> tuple[list[dict], float]:
    """Each class's figures, and its middle half and median as shares of the best 95th percentile
    (``statisticsHTML``). A share the server gave no figure for is None, and is not drawn."""
    classes = [c for c in _list(_dict(d).get("classes")) if isinstance(c, dict)]
    top = max([1.0] + [(_num(c.get("p95")) or _num(c.get("max")) or 0.0) for c in classes])
    rows = []
    for c in classes:
        p25, median, p75 = (_num(c.get(k)) for k in ("p25", "median", "p75"))
        rows.append({"class": _class(c.get("class")), "name": cap(_class(c.get("class"))),
                     "role": next((label for role, label in ROLES if role == c.get("role")), ""),
                     "count": n0(c.get("count")), "p25": n0(c.get("p25")), "median": n0(c.get("median")),
                     "p75": n0(c.get("p75")), "p95": n0(c.get("p95")), "max": n0(c.get("max")),
                     "box": (p25 / top, max(0.0, p75 - p25) / top) if p25 is not None and p75 is not None else None,
                     "mark": median / top if median is not None else None})
    return rows, top
