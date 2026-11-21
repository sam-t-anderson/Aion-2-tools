"""The Personal records view's words (0.2.454), as community.js writes them for the app's "Personal records" tab: the
filters every part shares (mode, metric, encounter type, game version, boss, difficulty, region, party size), the
recorded boss defeats, each class's performance as a distribution, a character's best records and every matching
attempt, and the character's consistency and trends.

Everything is read defensively, as the web page reads it: a field missing reads as the web page says it ("Unavailable",
"Unknown", "—").
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import urllib.parse

from .combat import TYPES, js_string
from .news import when as moment
from .results import _dict, _list, _truthy, js_text
from . import theme

RECORDS_NOTE = ("Public submissions only. Filters also apply to class performance and personal records. Product versions "
                "are recorded or submitted metadata; the latest submitted version may differ from the installed version. "
                "Older captures can retain legacy launcher metadata.")
FILTER_KEYS = ("combat_mode", "metric", "encounter_type", "game_patch", "boss", "difficulty", "region", "party_size")
BOSSES_NOTE = ("Public defeat observations, filtered by game game version and region. Other combat-log filters do not apply "
               "here. A recorded defeat does not establish whether a boss is currently available.")
BOSSES_WAITING = "Expand to load recorded defeats."
BOSSES_LOADING = "Loading recorded boss defeats…"
BOSSES_FAILED = ("Boss observations could not be loaded. Refresh to retry; this requires an updated community server.")
BOSSES_FOOT = ("Counts describe submitted observations, not verified unique kills or kill credit. Exact duplicate encounters "
               "count once; different perspectives can still repeat a defeat. Defeat times use the recording computer clock. "
               "Boss roles may include minibosses. Physical server/channel and respawn times are unavailable.")
BOSS_COLUMNS = ["Boss / NPC ID", "Region · build", "Map / instance", "Last recorded defeat (local time)",
                "Defeat / party observations", "Latest engagement / roster", "Current availability", "Source log"]
PERFORMANCE_NOTE = ("Recorded rates, separate PvE/PvP distributions for each boss, difficulty, encounter type and build. "
                    "Sample size and gear can affect these comparisons.")
CONSISTENCY_WAITING = "Search a character above to compare matched recordings."
CONSISTENCY_LOADING = "Loading matched character trends…"
NO_SUBMISSIONS = "No matching public submissions."
HISTORY_TITLE = "All matching public attempts"
SAMPLES_NOTE = ("Latest up to 50 samples in upload order; this is not a real-time fight timeline. {omitted} earlier samples "
                "omitted from this view. {markers} recorded player death markers across {with_markers} recordings with "
                "markers; other recordings do not establish zero deaths.")
RECORDS_PAGE = 50
REGION_NAMES = {"nae": "North America", "eu": "Europe", "as": "Asia", "la": "Latin America"}
#: The log review's class colours (combat-review.js ``defaults``), which the user's palette can replace.
CLASS_COLOURS = {"gladiator": "#c69b6d", "templar": "#f58cba", "assassin": "#fff468", "ranger": "#aad372",
                 "sorcerer": "#3fc7eb", "spiritmaster": "#8788ee", "cleric": "#ffffff", "chanter": "#ff7c0a",
                 "brawler": "#00c98d"}
GOLD = "#e8cf8e"
SERVERS = pathlib.Path(__file__).resolve().parents[1] / "meter" / "a2parser" / "data" / "servers.json"


def build_label(value) -> str:
    """A game version as words (``buildLabel``): Product version 2.1.0.3, Legacy build 123 · Steam or PURPLE."""
    text = js_string(value) if value is not None else ""
    text = re.sub(r"version:product:([0-9.]+)", lambda m: "Product version " + ".".join(m.group(1).split(".")[:4]), text)
    text = re.sub(r"build:steam:[0-9]{1,12}:([0-9]{1,20})", r"Legacy build \1 · Steam", text)
    return re.sub(r"build:purple:A2_[A-Z0-9_]{1,80}_PURPLE:([0-9]{1,20})", r"Legacy build \1 · PURPLE", text)


def n(value) -> str:
    """``Math.round(x || 0).toLocaleString()``: a whole number grouped by commas, none as 0."""
    x = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0
    return f"{theme.js_round(x):,}"


def _when(ts) -> str:
    """``whenAt(t * 1000)``: "—" for none."""
    return moment(ts * 1000) if _valid_time(ts) else "—"


def value_or_unavailable(value) -> str:
    return "Unavailable" if value is None else n(value)


def filter_name(key: str) -> str:
    return "game version" if key == "game_patch" else key.replace("_", " ")


def filter_choices(key: str, facets) -> list[tuple[str, str]]:
    """A filter's choices (``data-filters``): mode and metric without "All", the encounter types by name, the game
    versions as words, the rest as the facets give them."""
    if key == "combat_mode":
        return [("pve", "pve"), ("pvp", "pvp")]
    if key == "metric":
        return [("dps", "dps"), ("hps", "hps"), ("dtps", "dtps")]
    if key == "encounter_type":
        return [("", "All")] + [(k, v) for k, v in TYPES.items()]
    values = _list(_dict(facets).get(key))
    return [("", "All")] + [(js_string(v), build_label(v) if key == "game_patch" else js_string(v)) for v in values]


def query_after(query: dict, key: str, value: str) -> dict:
    """The filters after one changed: an encounter type sets its mode; a mode clears the encounter type."""
    query = dict(query)
    query[key] = value
    if key == "encounter_type" and value:
        query["combat_mode"] = "pvp" if value.startswith("pvp_") else "pve"
    if key == "combat_mode":
        query["encounter_type"] = ""
    return query


def params(query: dict, extra: list | None = None) -> str:
    """The filters chosen as a query (``params``), then ``extra``."""
    return urllib.parse.urlencode([(k, v) for k, v in query.items() if v] + list(extra or []))


def server_groups(path: pathlib.Path = SERVERS) -> list[tuple[str, list[tuple[str, str]]]]:
    """The records search's servers (``serverPicker``): each global region's, by faction, by name."""
    from .timers import world_for
    try:
        table = json.loads(path.read_text(encoding="utf-8")).get("global_servers")
    except (OSError, ValueError, AttributeError):
        return []
    groups = []
    for region, ids in (table.items() if isinstance(table, dict) else []):
        ids = sorted((str(i) for i in _list(ids) if str(i).isdigit()), key=int)
        for side, first in (("Elyos", "1"), ("Asmodian", "2")):
            mine = [(i, world_for(i, i)) for i in ids if i.startswith(first)]
            if mine:
                groups.append((f"{REGION_NAMES.get(region, region)} · {side}", mine))
    return groups


def class_colour(cls, preference) -> str:
    """A class's colour (combat-review.js ``color``): the user's palette, else the log review's own, gold when class
    colours are turned off."""
    pref = _dict(preference)
    if pref.get("enabled") is False:
        return GOLD
    key = js_string(cls).lower() if _truthy(cls) else ""
    candidate = _dict(pref.get("colors")).get(key) or CLASS_COLOURS.get(key) or GOLD
    return candidate if isinstance(candidate, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", candidate) else GOLD


def _valid_time(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def local_time(x) -> str:
    return moment(x * 1000) if _valid_time(x) else "Timestamp unavailable"


def age(x) -> str:
    """How long ago, in words (``age``)."""
    if not _valid_time(x):
        return "Age unavailable"
    if x < 60:
        return "Less than a minute ago"
    if x < 3600:
        return f"{math.floor(x / 60)} minutes ago"
    if x < 86400:
        return f"{math.floor(x / 3600)} hours ago"
    return f"{math.floor(x / 86400)} days ago"


# ------------------------------------------------------------------ recorded boss defeats
def bosses_path(query: dict) -> str:
    return "/api/v1/boss-status?" + urllib.parse.urlencode([(k, query[k]) for k in ("game_patch", "region") if query.get(k)])


def boss_groups(answer, term: str) -> list[dict]:
    """The boss/context groups a search lets through (``renderBosses``)."""
    term = term.strip().lower()
    return [g for g in _list(_dict(answer).get("groups")) if isinstance(g, dict)
            and term in f"{js_string(g.get('boss') or '')} {js_string(g.get('npc_id') or '')}".lower()]


def bosses_message(answer, shown: int) -> str:
    d = _dict(answer)
    return (f"{shown} displayed boss/context groups. Snapshot {local_time(d.get('generated_at'))} (local time)."
            + (" Results capped; search filters only the displayed groups." if d.get("truncated") else ""))


def boss_row(g: dict) -> dict:
    """A boss/context group's words: who, where, when it was last defeated, its observations, its source log."""
    last = _dict(g.get("latest_observation"))
    log_id = js_string(g.get("last_log_id") or "")
    segment = g.get("last_segment")
    basis = last.get("timing_basis")
    roster = last.get("recorded_roster_members")
    return {"boss": js_text(g.get("boss")) if _truthy(g.get("boss")) else "Unnamed boss",
            "npc": js_text(g.get("npc_id")) if _truthy(g.get("npc_id")) else "ID unavailable",
            "region": js_text(g.get("region")) if _truthy(g.get("region")) else "Unknown region",
            "build": build_label(g.get("game_patch") if _truthy(g.get("game_patch")) else "Unknown game version"),
            "place": f"{js_text(g.get('map_id')) if _truthy(g.get('map_id')) else 'Unknown'} / "
                     f"{js_text(g.get('instance_id')) if _truthy(g.get('instance_id')) else 'Unknown'}",
            "defeated": local_time(g.get("last_defeat_at")), "age": age(g.get("seconds_since_defeat")),
            "basis": basis.replace("_", " ") if isinstance(basis, str) and basis and basis != "recorded_clock" else "",
            "observations": f"{n(g.get('observed_defeats'))} / {n(g.get('party_observations'))}",
            "engaged": f"{n(last.get('engaged_roster_members'))} engaged",
            "roster": (f"{n(roster)} recorded roster members" + (" (complete)" if last.get("party_roster_complete") else " (partial)")
                       if _truthy(roster) else "Party roster unavailable"),
            "log": log_id if re.fullmatch(r"[A-Za-z0-9]{6,16}", log_id) else None,
            "source": ("Open log" + (f" · encounter {segment + 1}" if isinstance(segment, int) and not isinstance(segment, bool) else ""))
            if re.fullmatch(r"[A-Za-z0-9]{6,16}", log_id) else "Source unavailable"}


# ------------------------------------------------------------------ class performance
def performance_note(answer) -> str:
    d = _dict(answer)
    return (f"{js_text(d.get('note'))} {js_text(d.get('samples') or 0)} samples; "
            f"{js_text(d.get('excluded_unknown_metadata') or 0)} excluded for missing metadata."
            + (" Coverage capped." if d.get("truncated") else ""))


def _joined(parts) -> str:
    return " · ".join("" if p is None else js_string(p) for p in parts)


def performance_buckets(answer) -> list[tuple[str, list[dict]]]:
    """The classes' distributions by encounter (boss, its key, type, version, difficulty, party, instance), each
    bucket's classes by median, highest first."""
    buckets: dict[str, list] = {}
    for g in _list(_dict(answer).get("groups")):
        if not isinstance(g, dict):
            continue
        key = _joined([g.get("boss"), g.get("boss_key"), g.get("encounter_type"), g.get("game_patch"), g.get("difficulty"),
                       "Party " + (js_string(g["party_size"]) if _truthy(g.get("party_size")) else "unknown"),
                       "Instance " + (js_string(g["instance_id"]) if _truthy(g.get("instance_id")) else "unknown")])
        buckets.setdefault(key, []).append(g)
    return [(build_label(key), sorted(groups, key=lambda g: -_number(g.get("median")))) for key, groups in buckets.items()]


def _number(value) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0.0


def performance_row(g: dict) -> dict:
    comparison = _dict(g.get("comparison"))
    coverage = ("Sufficient sample" if comparison.get("status") == "available"
                else " ".join(js_string(r) for r in (_list(comparison.get("reasons")) or ["Coverage unavailable"])))
    identities = comparison.get("identities")
    return {"class": js_text(g.get("class")), "median": n(g.get("median")), "range": f"{n(g.get('min'))} – {n(g.get('max'))}",
            "parses": f"{js_text(g.get('count'))} · {js_text(identities) if identities is not None else 'Unavailable'}",
            "coverage": coverage, "box": {k: _number(g.get(k)) for k in ("min", "q1", "median", "q3", "max")},
            "tip": (f"Min {n(g.get('min'))}; lower quartile {n(g.get('q1'))}; median {n(g.get('median'))}; upper quartile "
                    f"{n(g.get('q3'))}; max {n(g.get('max'))}; {js_text(g.get('count'))} parses")}


def bucket_maximum(groups: list[dict]) -> float:
    return max([1.0] + [_number(g.get("max")) for g in groups])


# ------------------------------------------------------------------ personal records
def records_query(query: dict, identity: dict, page: int) -> str:
    """The records' query: the filters, the character searched and the page."""
    return params(query, [(k, v) for k, v in identity.items()] + [("page", str(page))])


def record_rows(answer, metric: str) -> list[dict]:
    rows = []
    for x in _list(_dict(answer).get("records")):
        if not isinstance(x, dict):
            continue
        party = js_text(x["party_size"]) if _truthy(x.get("party_size")) else "unknown"
        instance = js_text(x["instance_id"]) if _truthy(x.get("instance_id")) else "unknown"
        kind = TYPES.get(x.get("encounter_type")) if isinstance(x.get("encounter_type"), str) else None
        rows.append({"boss": js_text(x.get("boss")), "log": x.get("log"),
                     "context": f"{kind or ''} · {build_label(x.get('game_patch') or 'Unknown')} · "
                                f"{js_text(x['difficulty']) if _truthy(x.get('difficulty')) else 'Unknown'} · party {party} · "
                                f"instance {instance}",
                     "class": js_text(x["class"]) if _truthy(x.get("class")) else "Unknown",
                     "best": n(x.get("best_score") if x.get("best_score") is not None else x.get("best_dps")),
                     "attempts": js_text(x.get("attempts"))})
    return rows


def history_rows(answer) -> list[dict]:
    from .account import world
    rows = []
    for x in _list(_dict(answer).get("history")):
        if not isinstance(x, dict):
            continue
        rows.append({"boss": js_text(x.get("boss")), "log": x.get("log_id"), "name": js_text(x.get("name")),
                     "verified": bool(x.get("verified")), "pseudonym": bool(x.get("pseudonym")),
                     "server": world(x.get("server")) if _truthy(x.get("server")) else "",
                     "score": n(x.get("score") if x.get("score") is not None else x.get("dps")),
                     "ranking": "Eligible" if x.get("ranking_eligible") else "Unranked / unverified",
                     "recorded": _when(x.get("created_at"))})
    return rows


def records_pager(answer, page: int) -> dict:
    total = _dict(answer).get("total")
    total_n = _number(total)
    return {"line": f"Page {page} · {js_text(total)} attempts", "previous": page > 1, "next": page * RECORDS_PAGE < total_n}


# ------------------------------------------------------------------ consistency and trends
def consistency_note(answer) -> str:
    c = _dict(answer)
    return (f"{js_text(c.get('note'))} {js_text(c.get('identity'))}. {js_text(c.get('excluded_missing_evidence') or 0)} "
            "samples excluded for missing cohort/metric evidence."
            + (" Dataset capped; variation/trends unavailable." if c.get("truncated") else "")
            + (f" Additional groups omitted: {js_text(c['omitted_groups'])}" if _truthy(c.get("omitted_groups")) else ""))


def _percent(value, signed: bool = False) -> str:
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return "Unavailable"
    return ("+" if signed and value > 0 else "") + theme.fixed(value, 1) + "%"


def consistency_group(g: dict, metric: str) -> dict:
    """A character's group of matched recordings: its title, its spread and trend, its samples' words and points."""
    title = (f"{js_text(g.get('boss'))} · {js_text(g.get('class_name'))} · {build_label(g.get('game_patch'))} · "
             f"{js_text(g.get('difficulty'))} · party {js_text(g.get('party_size'))} · instance {js_text(g.get('instance_id'))} · "
             f"{js_text(g.get('samples'))} recordings")
    spread = (f"Median {value_or_unavailable(g.get('median'))} {metric.upper()} · range {value_or_unavailable(g.get('min'))}–"
              f"{value_or_unavailable(g.get('max'))} · relative variation {_percent(g.get('coefficient_of_variation_pct'))} · "
              f"median absolute deviation {value_or_unavailable(g.get('median_absolute_deviation'))} · standard deviation "
              f"{value_or_unavailable(g.get('standard_deviation'))}")
    trend = (f"Recent 5 median {value_or_unavailable(g.get('recent_five_median'))} · preceding 5 "
             f"{value_or_unavailable(g.get('previous_five_median'))} · change {_percent(g.get('change_pct'), signed=True)}"
             + ("" if g.get("variation_available") else " · At least 5 uncapped recordings required for variation.")
             + ("" if g.get("trend_available") else " · At least 10 uncapped recordings required for trend."))
    samples = SAMPLES_NOTE.format(omitted=js_text(g.get("omitted_history")), markers=js_text(g.get("observed_death_markers")),
                                  with_markers=js_text(g.get("samples_with_death_markers")))
    history = [x for x in _list(g.get("history")) if isinstance(x, dict)]
    rows = [{"uploaded": local_time(x.get("uploaded_at")), "score": n(x.get("score")),
             "deaths": "Unavailable (no markers)" if x.get("recorded_deaths") is None else js_text(x.get("recorded_deaths")),
             "log": x.get("log"), "open": f"Open encounter {js_text(_number(x.get('segment')) + 1)}",
             "segment": x.get("segment")} for x in history]
    return {"title": title, "spread": spread, "trend": trend, "samples": samples, "rows": rows,
            "points": trend_points(history)}


def trend_points(history: list[dict]) -> list[tuple[float, float, str]]:
    """The samples' points on a 600 × 115 chart (``polyline``), each with its words."""
    maximum = max([1.0] + [_number(x.get("score")) for x in history])
    count = len(history)
    return [((i * 600 / (count - 1)) if count > 1 else 300.0, 100 - 90 * _number(x.get("score")) / maximum,
             f"{local_time(x.get('uploaded_at'))}: {n(x.get('score'))}") for i, x in enumerate(history)]
