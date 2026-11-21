"""The community's combat log views' words (0.2.453), as logs-view.js writes them.

- **Community Combat Logs:** one row per fight of every public log on the log server, newest first, fifty to a page
  (the server's pages of fifty logs read until the page is full), PvE or PvP, filtered by the server's own facets:
  boss (mini-bosses hidden unless shown), difficulty, encounter, region, product and party size.
- **Completed-run speed:** the completed runs ranked by time among runs of the same instance, route, difficulty and
  party size.
- **Boss progression:** each boss's engagements by difficulty, region and product: attempts, kills, wipes, kill rate and
  the fastest kill.
- **Highest observed build points:** each class's highest reported skill, stigma, Daevanion and Ariel points.

Everything is read defensively, as the web page reads it: a field missing reads "—" and a list missing is empty.
"""
from __future__ import annotations

import functools
import math
import re
import urllib.parse

from .combat import encode_component, js_string, locale_key, secs
from .news import when as moment
from .results import _dict, _list, _truthy, cap, js_text, n0, pct

COMM_PER_PAGE = 50
SERVER_PAGE = 50
PVE_KEYS = ("boss", "difficulty", "encounter_type", "region", "game_patch", "party_size")
COMM_KEYS = ("boss", "difficulty", "region", "encounter_type", "game_patch", "party_size")
PVP_TYPES = {"pvp_open_world": "Open world", "pvp_arena": "Arena", "pvp_battleground": "Battlefield",
             "pvp_abyss": "Abyss", "pvp_rift": "Rift"}
PARTY_UNKNOWN = ("The game's party list was not captured in this fight: this counts the players recorded in it, which "
                 "can be fewer than the party.")
NOT_REACHED = "Could not reach the stats server."
FILTER_FIELDS = (("difficulty", "Difficulty"), ("encounter_type", "Encounter"), ("region", "Region"),
                 ("game_patch", "Product"), ("party_size", "Party"))
NO_COMM = "No encounters match these filters."
NO_SPEED_MATCH = "No completed runs match these filters."
NO_SPEED = ("No eligible speed clears yet. A completed run ranks here once its capture is clean and complete enough to "
            "qualify.")
NO_PROGRESSION = "No boss engagements match these filters."
NO_POINTS = "No build-point observations yet."
POINTS_NOTE = ("Highest observed skill / stigma / Daevanion / Ariel points per class, from optimization submissions "
               "(reported lower bounds, not verified game caps). Ariel is the Ariel board's own crystal, reported since "
               "client 0.2.381; — where a class has no report yet.")
SPEED_COLUMNS = ["Rank", "Boss / route", "Encounter", "Time", "Party", ""]
PROGRESSION_COLUMNS = ["Boss", "Difficulty", "Region", "Product", "Attempts", "Kills", "Wipes", "Kill rate", "Fastest"]
POINTS_COLUMNS = ["Class", "Skill", "Stigma", "Daevanion", "Ariel", "Total", "Region"]
CLASS_ART = "https://metabot.gg/web/aion2/classes/{}.webp"


def community_path(path: str) -> str:
    """A log server's public route through the app's proxy (``communityAPI``)."""
    return "/api/community?path=" + encode_component(path)


def shared_page(log_id, mode, segment=None) -> str:
    """A public log's page in the web interface, at one of its fights (``openShared``)."""
    page = f"combat-log/shared/{encode_component(log_id)}?mode={encode_component(mode or '')}"
    return page + (f"&segment={segment}" if isinstance(segment, int) and not isinstance(segment, bool) else "")


def patch_of(game_patch) -> str:
    """A product as the web page writes it (``patchOf``)."""
    return re.sub(r"^version:product:", "", js_string(game_patch) if _truthy(game_patch) else "")


def pretty_enc(kind) -> str:
    """An encounter type as words (``prettyEnc``): pve_daily -> "daily"."""
    return re.sub(r"^pve_|^pvp_", "", js_string(kind) if _truthy(kind) else "", count=1).replace("_", " ") or "—"


def pvp_type(kind) -> str:
    """What kind of PvP a fight was, from its recorded map; anything else "Other PvP"."""
    return PVP_TYPES.get(kind, "Other PvP") if isinstance(kind, str) else "Other PvP"


def real_boss(boss) -> bool:
    """Not generic combat ("Combat 3"): a boss the filter can offer."""
    return not re.fullmatch(r"combat\s*\d*", js_string(boss).strip(), re.I)


def is_mini(name, roles) -> bool:
    """A mini-boss by the server's roles (an earlier boss of a dungeon whose final boss the catalog knows)."""
    return isinstance(roles, dict) and isinstance(name, str) and roles.get(name) == "mini"


def when(ts) -> str:
    """A moment the server gives in seconds, in the computer's clock (``day``)."""
    if ts is None or isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "—"
    return moment(ts * 1000)


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _sorted_text(values) -> list:
    """Values sorted as ``String(a).localeCompare(String(b))`` sorts them."""
    return sorted(_list(values), key=lambda v: locale_key(js_string(v)))


# ------------------------------------------------------------------ community combat logs
def community_query(f: dict, page: int) -> str:
    """A page of the server's logs (``commQuery``): its number, fifty, the mode and the filters chosen."""
    query = [("page", str(page)), ("limit", str(SERVER_PAGE))]
    if f.get("combat_mode"):
        query.append(("combat_mode", f["combat_mode"]))
    query += [(key, f[key]) for key in COMM_KEYS if f.get(key)]
    return urllib.parse.urlencode(query)


def members(players) -> list[dict]:
    """A fight's players with a name or a class (``toMembers``)."""
    return [{"name": p.get("name"), "class": p.get("class"), "verified": p.get("verified") is True,
             "pseudonym": p.get("pseudonym") is True}
            for p in _list(players) if isinstance(p, dict) and (_truthy(p.get("name")) or _truthy(p.get("class")))]


def community_page(answer, f: dict, mini: bool, facets) -> tuple[list[dict], float | None, int]:
    """A server page's fights as rows (``commFetchMore``), the server's total of logs when it says it, and how many
    logs the page held. Generic combat is left out in PvE, and a mini-boss unless shown."""
    d = _dict(answer)
    logs = [lg for lg in _list(d.get("logs")) if isinstance(lg, dict)]
    total = d.get("total") if isinstance(d.get("total"), (int, float)) and not isinstance(d.get("total"), bool) else None
    pvp = (f.get("combat_mode") or "pve") == "pvp"
    roles = _dict(facets).get("boss_roles")
    rows = []
    for lg in logs:
        icons = {b["name"]: b["icon"] for b in _list(lg.get("bosses"))
                 if isinstance(b, dict) and isinstance(b.get("name"), str) and _truthy(b.get("name")) and _truthy(b.get("icon"))}
        roster = members(lg.get("players"))
        uploader = lg.get("uploader") if isinstance(lg.get("uploader"), str) else None
        for c in _list(lg.get("contexts")):
            if not isinstance(c, dict):
                continue
            boss, role = c.get("boss"), c.get("boss_role")
            if not pvp and (not _truthy(boss) or not real_boss(boss)):
                continue
            if not pvp and not mini and (role == "mini" or ((not _truthy(role) or role == "unknown") and is_mini(boss, roles))):
                continue
            people = members(c.get("players")) if isinstance(c.get("players"), list) and c["players"] else roster
            start = c.get("start")
            at = start if isinstance(start, (int, float)) and not isinstance(start, bool) else lg.get("created_at")
            rows.append({"boss": c.get("zone") if f.get("combat_mode") == "pvp" and _truthy(c.get("zone")) else boss,
                         "icon": icons.get(boss) if isinstance(boss, str) else None, "difficulty": c.get("difficulty"),
                         "party": c.get("party_size") if _truthy(c.get("party_size")) else (len(people) or 0),
                         "known": _truthy(c.get("party_size")), "members": people, "duration": c.get("duration"),
                         "when": at, "type": c.get("encounter_type"), "patch": patch_of(c.get("game_patch")),
                         "id": lg.get("id"), "segment": c.get("segment"), "uploader": uploader})
    return rows, total, len(logs)


def _newest_first(a: dict, b: dict) -> int:
    """``(b.when - a.when) || ((b.segment || 0) - (a.segment || 0))``: newest first, the later fight first within an
    upload."""
    a_when, b_when = _number(a.get("when")), _number(b.get("when"))
    step = b_when - a_when if a_when is not None and b_when is not None else 0.0
    if not step:
        step = (_number(b.get("segment")) or 0.0) - (_number(a.get("segment")) or 0.0)
    return -1 if step < 0 else 1 if step > 0 else 0


def newest_first(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=functools.cmp_to_key(_newest_first))


def community_done(logs: int, total, pages: int) -> bool:
    """Whether the server has no more logs to give: an empty page, or as many as its total."""
    return not logs or bool(total and pages * SERVER_PAGE >= total)


def community_row(r: dict, mode: str) -> dict:
    """A row's words: the boss (a PvP fight's zone), its difficulty (a PvP fight's kind), the party with ``?`` when its
    list was not captured, the time, who uploaded it, when and the product."""
    return {"boss": js_text(r["boss"]) if _truthy(r.get("boss")) else "—",
            "kind": pvp_type(r.get("type")) if mode == "pvp" else (js_text(r["difficulty"]) if _truthy(r.get("difficulty")) else "—"),
            "party": n0(r.get("party")), "unknown": not r.get("known"), "time": secs(r.get("duration")),
            "uploader": r["uploader"] if r.get("uploader") else "Anonymous", "date": when(r.get("when")),
            "patch": r.get("patch") or "—"}


def member_tip(m: dict) -> str:
    """A class icon's words (``classIcon``): the player and class, verified, or hidden by its player."""
    cls = js_string(m.get("class")).lower() if _truthy(m.get("class")) else ""
    name = js_string(m.get("name")) if _truthy(m.get("name")) else ""
    return ((f"{name} · {cap(cls)}" if name else cap(cls)) + (" · verified" if m.get("verified") else "")
            + (" · hidden by its player" if m.get("pseudonym") else ""))


def pager_line(page: int, start: int, count: int) -> str:
    return f"Page {page} · encounters {n0(start + 1)}–{n0(start + count)}"


def community_choices(facets, f: dict, mini: bool) -> dict:
    """The community filters' choices from the server's facets (``renderCommunity``): the encounter types of the mode
    chosen, real bosses (a mini-boss when they are shown)."""
    facets = _dict(facets)
    pvp = f.get("combat_mode") == "pvp"
    kinds = [t for t in _list(facets.get("encounter_type")) if pvp == js_string(t).startswith("pvp_")]
    return {"boss": _bosses(facets, mini), "difficulty": [(d, js_string(d)) for d in _sorted_text(facets.get("difficulty"))],
            "encounter_type": [(t, pvp_type(t) if pvp else pretty_enc(t)) for t in kinds],
            "region": [(r, js_string(r)) for r in _list(facets.get("region"))],
            "game_patch": [(g, patch_of(g)) for g in _list(facets.get("game_patch"))],
            "party_size": [(p, js_string(p)) for p in _list(facets.get("party_size"))]}


def _bosses(facets: dict, mini: bool) -> list[tuple]:
    roles = facets.get("boss_roles")
    return [(b, js_string(b)) for b in _list(facets.get("boss")) if real_boss(b) and (mini or not is_mini(b, roles))]


def pve_choices(facets, mini: bool) -> dict:
    """The PvE filters' choices (``pveFilters``), for run speed and boss progression too."""
    facets = _dict(facets)
    kinds = [t for t in _list(facets.get("encounter_type")) if not js_string(t).startswith("pvp_")]
    return {"boss": _bosses(facets, mini), "difficulty": [(d, js_string(d)) for d in _sorted_text(facets.get("difficulty"))],
            "encounter_type": [(t, pretty_enc(t)) for t in kinds],
            "region": [(r, js_string(r)) for r in _list(facets.get("region"))],
            "game_patch": [(g, patch_of(g)) for g in _list(facets.get("game_patch"))],
            "party_size": [(p, js_string(p)) for p in _list(facets.get("party_size"))]}


def source_note(answer) -> str:
    """The server's note under a view (``srcNote``)."""
    note = _dict(answer).get("note")
    return js_text(note) if _truthy(note) else ""


# ------------------------------------------------------------------ completed-run speed
def filter_query(f: dict, extra: tuple = ()) -> str:
    """The PvE filters chosen as a query, after ``extra``."""
    return urllib.parse.urlencode(list(extra) + [(key, f[key]) for key in PVE_KEYS if f.get(key)])


def route_of(run: dict) -> str:
    """A run's bosses in the order it met them, by name (``routeOf``)."""
    names = {}
    for a in [*_list(run.get("attempts")), *_list(run.get("progression"))]:
        if isinstance(a, dict) and _truthy(a.get("boss_key")) and _truthy(a.get("boss")):
            names[js_string(a["boss_key"])] = a["boss"]
    route = run.get("boss_route") if isinstance(run.get("boss_route"), list) else []
    return " → ".join(js_string(names.get(js_string(k), k)) for k in route)


def run_kind(run: dict) -> str:
    """A run's encounter and difficulty (``runKind``)."""
    parts = [cap(pretty_enc(run.get("encounter_type"))), run.get("difficulty")]
    return " · ".join(js_string(p) for p in parts if _truthy(p) and p != "—") or "—"


def speed_rows(answer) -> list[dict]:
    rows = []
    for r in _list(_dict(answer).get("entries")):
        if not isinstance(r, dict):
            continue
        count = _number(r.get("count"))
        rows.append({"rank": n0(r.get("rank")), "of": f"of {n0(r.get('count'))}" if count is not None and count > 1 else "",
                     "route": route_of(r) or "—", "kind": run_kind(r), "time": secs(r.get("elapsed_seconds")),
                     "party": n0(r.get("party_size")), "log": r.get("log")})
    return rows


# ------------------------------------------------------------------ boss progression
def progression_rows(answer, f: dict, mini: bool, facets) -> list[dict]:
    """Each boss's engagements (``renderProgression``), a mini-boss's hidden with the mini-bosses, by boss then
    difficulty."""
    roles = _dict(facets).get("boss_roles")
    groups = [g for g in _list(_dict(answer).get("groups")) if isinstance(g, dict)
              and (mini or f.get("boss") == g.get("boss") or not is_mini(g.get("boss"), roles))]
    groups.sort(key=lambda g: (locale_key(js_string(g.get("boss") or "")), locale_key(js_string(g.get("difficulty") or ""))))
    rows = []
    for g in groups:
        rate = g.get("observed_kill_rate")
        rows.append({"boss": js_text(g["boss"]) if _truthy(g.get("boss")) else "—", "icon": g.get("icon"),
                     "difficulty": js_text(g["difficulty"]) if _truthy(g.get("difficulty")) else "—",
                     "region": js_text(g["region"]) if _truthy(g.get("region")) else "—",
                     "patch": patch_of(g.get("game_patch")) or "—", "attempts": n0(g.get("attempts")),
                     "kills": n0(g.get("kills")), "wipes": n0(g.get("wipes")),
                     "rate": "—" if rate is None else pct(rate, 0),
                     "fastest": secs(g["fastest_kill_seconds"]) if _truthy(g.get("fastest_kill_seconds")) else "—"})
    return rows


# ------------------------------------------------------------------ highest observed build points
def points_rows(answer) -> list[dict]:
    """Each class's highest reported points (``renderPoints``), the highest total first."""
    best: dict[str, dict] = {}
    for o in _list(_dict(answer).get("observations")):
        if not isinstance(o, dict):
            continue
        total = sum((_number(o.get(key)) or 0.0) if _truthy(o.get(key)) else 0.0
                    for key in ("skill", "stigma", "daevanion", "ariel"))
        key = js_string(o.get("class_name")) if _truthy(o.get("class_name")) else "?"
        if key not in best or total > best[key]["_t"]:
            best[key] = {**o, "_t": total}
    rows = sorted(best.values(), key=lambda o: -o["_t"])
    return [{"class": cap(o.get("class_name")), "skill": n0(o.get("skill")), "stigma": n0(o.get("stigma")),
             "daevanion": n0(o.get("daevanion")), "ariel": n0(o.get("ariel")), "total": n0(o["_t"]),
             "region": js_text(o["region"]) if _truthy(o.get("region")) else ""} for o in rows]
