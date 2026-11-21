"""The Account page's words (0.2.447), as pages/account.js and account-view.js write them: the account offered when
signed out, the account's name and counts, Sign-in & security (the ways in, where it is signed in, what it did lately,
closing it), and since 0.2.448 My logs (filtered, paged, each with its visibility) and Top parses (the best run on each
boss for each character, with its parse). The app keeps the credential and talks to the server (combat/account.py);
the page asks the app.
"""
from __future__ import annotations

import math
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import theme
from .character import js_number
from .news import when as moment
from .results import _dict, _list, _truthy, js_text
from .timers import world_for

SITE = "https://sam-t-anderson.github.io/Aion-2-tools/"
INTRO = ("An account is optional. With one, your uploads from this app and the ones it made before are in one place, on "
         "the website too, under your name; you can share logs with your legion and see theirs.")
NO_PASSWORD = "There is no password: this app stays signed in, and it approves your sign-ins on the website."
NAME_HINT = "Your name (optional)"
CREATE = "Create my account"
HAVE_ONE = "I already have an account"
DISCORD = "Sign in with Discord"
DISCORD_NOTE = "if you linked Discord on the website"
CODE_HINT = "ABCD-EFGH"
LINK = "Link with a code"
LINK_NOTE = "Website: Sign-in & security → Link another computer's app"
RECOVER = "Recover with my uploads"
RECOVER_NOTE = "Uses the private credentials of three of the account's uploads (your ownership backup)"
DISCORD_WAIT = "Finish signing in with Discord in your browser…"
DISCORD_ENDED = "The Discord sign-in ended. Try again."
DISCORD_WAIT_S = 10 * 60
CHOOSE_SERVER = "Choose a log server in Settings first."
TABS = (("logs", "My logs"), ("parses", "Top parses"), ("legions", "Legions"), ("security", "Sign-in & security"))
APPROVE = "Approve a website sign-in"
WEBSITE = "Open the website signed in"
WAYS_NOTE = ("On the website, choose Sign in → Approve in the app, then enter the code it shows here. Passkeys and Discord "
             "are added on the website (Sign-in & security there), and another computer's app joins with a code from the "
             "website.")
CODE_ASK = "The code the website shows (eight letters and digits)"
RENAME_ASK = "Your account's name (2-24 letters or digits)"
END_ALL_ASK = "Sign out every other app and website?"
RECENT_NOTE = "Anything you do not recognise? Sign out everywhere else, then check how you sign in."
CLOSE = "Close the account"
CLOSE_NOTE = ("Your logs stay on the server and keep working with their upload credentials, unless you delete them too. You "
              "leave your legions; one you lead passes to an officer.")
CLOSE_LOGS = "Delete my logs as well"
CLOSE_WORDS = "delete my account"
CLOSE_TYPE = 'Type "delete my account" to close it.'
ACTIVITY = {"created": "Account created", "signed_in": "Signed in", "signed_out": "Signed out", "renamed": "Renamed",
            "logs_attached": "Logs added", "visibility": "Visibility changed", "retitled": "Log renamed",
            "log_deleted": "Log deleted", "log_detached": "Log removed from the account", "character_added": "Character added",
            "discord_linked": "Discord linked", "discord_unlinked": "Discord unlinked", "passkey_added": "Passkey added",
            "passkey_removed": "Passkey removed", "signin_approved": "Website sign-in approved",
            "signin_denied": "Website sign-in denied", "link_code": "Link code made", "legion_created": "Legion founded",
            "legion_joined": "Legion joined", "recovered": "Recovered", "disabled": "Disabled by the operator",
            "active": "Enabled by the operator"}
ON_THE_WEB = {"legions": "Legions open in the web interface for now."}


def when(t) -> str:
    """A moment the server gives in seconds, in the computer's clock (account-view.js ``when``); "—" for none."""
    if not _truthy(t):
        return "—"
    return moment(js_number(t) * 1000)


def many(n, one: str, other: str) -> str:
    """``many``: the words for one, or for any other count."""
    return (one if js_number(n) == 1 else other).replace("{0}", js_text(n))


def plain(message) -> str:
    """A refusal's words without the exception's name the app may put first."""
    return re.sub(r"^(ValueError|PermissionError|RuntimeError|LookupError|Error): ", "", js_text(message or ""))


def status_view(s) -> dict:
    """The app's account status (``accountStatus``): signed in on another server than Settings uses reads as signed
    out here, with that server said."""
    s = _dict(s)
    if s.get("signed_in") and s.get("here") is False:
        return {**s, "signed_in": False, "elsewhere": s.get("account_server")}
    return s


def signed_out_notes(s: dict) -> list[tuple[str, str]]:
    """The notes over the account offered: a sign-in that ended, one on another server (``elsewhere``, with Sign out),
    and no log server chosen or none reached."""
    notes = []
    if s.get("ended"):
        notes.append(("ended", js_text(s["ended"])))
    if s.get("elsewhere"):
        notes.append(("elsewhere", f"This app is signed in on {js_text(s['elsewhere'])}, not on the server Settings uses now "
                                   f"({js_text(s.get('server') or '—')})."))
    if not s.get("server"):
        notes.append(("server", CHOOSE_SERVER))
    elif s.get("error") and not _truthy(s.get("config")):
        notes.append(("error", js_text(s["error"])))
    return notes


def can_create(s: dict) -> bool:
    """**Create my account** is offered on the server Settings uses once its account settings were read."""
    return not (s.get("elsewhere") or not s.get("server") or not _truthy(s.get("config")))


def discord_offered(s: dict) -> bool:
    return bool(_dict(_dict(s.get("config")).get("methods")).get("discord"))


def signed_in_as(result) -> str:
    return f"Signed in as {js_text(_dict(_dict(result).get('account')).get('name') or '')}"


def title_line(me: dict) -> tuple[str, str]:
    """The account's name, and how many logs and characters it holds."""
    logs = me.get("logs") if me.get("logs") is not None else 0
    return (js_text(me.get("name")), many(logs, "{0} log", "{0} logs") + " · "
            + many(len(_list(me.get("characters"))), "{0} character", "{0} characters"))


def ways_line(me: dict) -> str:
    """How else the account signs in: Discord, its passkeys and its desktop apps."""
    discord = _dict(me.get("discord"))
    passkeys, apps = me.get("passkeys") or 0, me.get("apps") or 0
    return (f"Discord: {js_text(discord.get('name'))}" if _truthy(me.get("discord")) else "Discord: not linked") + " · " + \
        many(passkeys, "{0} passkey", "{0} passkeys") + " · " + many(apps, "{0} desktop app", "{0} desktop apps")


def session_rows(answer) -> list[dict]:
    """Where the account is signed in: each app or website, since when, last used, and this one or Sign out."""
    return [{"where": js_text(s.get("label")), "kind": "desktop app" if s.get("kind") == "app" else "website",
             "since": when(s.get("created_at")), "used": when(s.get("last_used")), "current": bool(s.get("current")),
             "id": s.get("id")} for s in _list(_dict(answer).get("sessions")) if isinstance(s, dict)]


def activity_rows(answer) -> list[tuple[str, str, str]]:
    """What the account did lately: when, what, and its note."""
    return [(when(a.get("created_at")), ACTIVITY.get(a.get("action"), js_text(a.get("action"))), js_text(a.get("note") or ""))
            for a in _list(_dict(answer).get("activity")) if isinstance(a, dict)]


def lookup_path(code: str) -> str:
    return "/api/v1/account/signin/lookup?code=" + urllib.parse.quote(code, safe="")


def approve_question(seen) -> str:
    """The question before a website sign-in is approved (``approveWebsiteSignIn``): which browser asks, and whether
    it started on this computer's internet connection."""
    seen = _dict(seen)
    same = seen.get("same_network")
    network = ("It started on this computer's internet connection." if same is True else
               "It did NOT start on this computer's internet connection. If someone asked you for this code, deny it."
               if same is False else "The server cannot tell which internet connection it started on.")
    return (f"Sign in {js_text(seen.get('browser'))} on the website as your account?\n\n{network}\n\n"
            "Approve only a sign-in you started yourself.")


def revoked(result) -> str:
    return f"{js_text(_dict(result).get('signed_out'))} signed out"


def signed_out_answer(message: str) -> bool:
    """A refusal that means the app is no longer signed in (``accountCall``)."""
    return bool(re.search(r"sign in again|signed out|Sign in first", message or "", re.IGNORECASE))


# ------------------------------------------------------------------ my logs (0.2.448)
VISIBILITY = (("public", "Public"), ("unlisted", "Unlisted"), ("legion", "Legion only"), ("private", "Private"))
LOGS_NOTE = ("Legion only: the members of your legions open it; it is listed nowhere else. Private: only its secret link "
             "opens it.")
NO_LOGS = "No logs yet. Uploads from your signed-in app join here, and the app adds the ones it uploaded before."
NO_LOGS_MATCH = "No logs match."
SYNC = "Add this app's uploads"
SYNC_TIP = "The uploads and characters this app holds"
DESCRIBE_ASK = "A new description for this log (1-80 characters)"
LOG_COLUMNS = ["Description", "Character", "Uploaded", "Duration", "Visibility", "Edit", "Delete"]


def fresh_filter() -> dict:
    """A log list's filter as it starts (``fresh``): the first page, no boss and no days."""
    return {"page": 1, "boss": "", "since": "", "until": ""}


def filtering(f: dict) -> bool:
    return bool(f.get("boss") or f.get("since") or f.get("until"))


def _midnight(day: str, plus: int) -> str:
    """The instant a day of the computer's calendar starts (``new Date(y, m - 1, d + plus).toISOString()``)."""
    y, m, d = (int(x) for x in day.split("-"))
    start = datetime(y, m, d) + timedelta(days=plus)
    return start.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def list_query(f: dict, limit: int = 50) -> str:
    """A log list's query (``listQuery``): its page, the boss, and the instants From and To span, From's midnight up to
    the midnight after To, in the computer's own days."""
    query = [("page", str(f.get("page") or 1)), ("limit", str(limit))]
    if f.get("boss"):
        query.append(("boss", f["boss"]))
    if f.get("since"):
        query.append(("since", _midnight(f["since"], 0)))
    if f.get("until"):
        query.append(("until", _midnight(f["until"], 1)))
    return urllib.parse.urlencode(query)


def length(seconds) -> str:
    """A fight's length (``length``): m:ss, or h:mm:ss from an hour; nothing readable is 0:00."""
    x = js_number(seconds)
    s = max(0, theme.js_round(x)) if math.isfinite(x) else 0
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def vis_label(value) -> str:
    return next((words for key, words in VISIBILITY if key == value), js_text(value))


def log_page(log: dict) -> str:
    """A log's page in the web interface (``logHref``): its shared log, at its encounter."""
    segment = log.get("segment")
    return ("combat-log/shared/" + urllib.parse.quote(js_text(log.get("id")), safe="")
            + (f"?segment={segment}" if isinstance(segment, int) and not isinstance(segment, bool) else ""))


def log_rows(answer) -> list[dict]:
    """The account's logs (``renderLogs``): each one's description (or boss, or id) and page, whether it is under
    review, its boss, character, upload time, length and visibility."""
    rows = []
    for log in _list(_dict(answer).get("logs")):
        if not isinstance(log, dict):
            continue
        rows.append({"id": log.get("id"), "title": js_text(log.get("title") or log.get("boss") or log.get("id")),
                     "page": log_page(log), "held": bool(log.get("held")), "boss": js_text(log.get("boss") or ""),
                     "uploader": js_text(log.get("uploader") or "—"), "uploaded": when(log.get("created_at")),
                     "duration": length(log.get("duration")), "visibility": log.get("visibility"),
                     "name": js_text(log.get("title") or log.get("id")), "describe": js_text(log.get("title") or "")})
    return rows


def logs_count(answer) -> str:
    return many(_dict(answer).get("total") or 0, "{0} log", "{0} logs")


def page_count(answer) -> int:
    answer = _dict(answer)
    return max(1, math.ceil((js_number(answer.get("total")) or 0) / (js_number(answer.get("limit")) or 50)))


def delete_question(row: dict) -> str:
    return f"Delete {row['name']} from the server for everyone? This cannot be undone."


def now_visible(row: dict, value: str) -> str:
    return f"{row['name']} is now {vis_label(value)}"


def synced(answer) -> str:
    answer = _dict(answer)
    return f"{js_text(answer.get('logs'))} logs and {js_text(answer.get('characters'))} characters added"


# ------------------------------------------------------------------ top parses (0.2.448)
PARSE_SORTS = {"parse": "desc", "dps": "desc", "date": "desc", "boss": "asc", "difficulty": "asc", "character": "asc",
               "class": "asc"}
PARSE_COLUMNS = (("boss", "Boss"), ("difficulty", "Difficulty"), ("character", "Character"), ("class", "Class"),
                 ("dps", "DPS"), ("parse", "Parse"), ("date", "Date"))
PER_PAGE = (25, 50, 100)
PARSES_NOTE = ("Your best DPS on each boss and difficulty for each of your characters, from the logs in this account (any "
               "visibility), in ranking-eligible PvE fights. The parse compares it with every ranked public run of the same "
               "boss, game version and difficulty by the same class: 100 is above them all.")
NO_PARSES = ("No ranked boss fights in your logs yet. Your best run on each boss shows here, with its parse against every "
             "public run of your class.")
NO_PARSES_MATCH = "No parses match."
NOT_LISTED = "The community server doesn't list top parses yet."
LOADING_PARSES = "Loading your top parses…"
# the parse's colour (combat-review.css ``.q-*``, WCL's): gold for the bracket's best run
TIER_COLOURS = {"gold": "#e5cc80", "pink": "#e577b1", "orange": "#ff8000", "purple": "#c67ef6", "blue": "#5c9eff",
                "green": "#1eff00", "grey": "#999ea9", "none": "#9a9ea9"}
NO_PARSE_TIP = "No parse yet: no other ranked run of this class on this encounter"


def fresh_parses(limit: int = 25) -> dict:
    return {"page": 1, "limit": limit, "sort": "parse", "order": "desc", "boss": "", "difficulty": "", "cls": "", "character": ""}


def parse_tier(parse, rank) -> str:
    p = js_number(parse)
    first = isinstance(rank, (int, float)) and not isinstance(rank, bool) and rank == 1       # ``rank === 1``
    return ("gold" if first or p >= 100 else "pink" if p >= 99 else "orange" if p >= 95 else "purple" if p >= 75
            else "blue" if p >= 50 else "green" if p >= 25 else "grey")


def parse_cell(row: dict) -> tuple[str, str, bool, str]:
    """A run's parse (``parseCell``): its rounded value, colour and whether it is provisional, and its tip; "·" without
    one."""
    if row.get("parse") is None:
        return "·", "none", False, NO_PARSE_TIP
    rank = row.get("parse_rank")
    tip = (f"Parse {js_text(row['parse'])}, rank {js_text('—' if rank is None else rank)} of {js_text(row.get('parse_runs'))} "
           "ranked runs of this class on this encounter") + (" Provisional: fewer than 5 runs." if row.get("provisional") else "")
    return str(theme.js_round(js_number(row["parse"]))), parse_tier(row["parse"], rank), bool(row.get("provisional")), tip


def cap(text) -> str:
    return js_text(text)[:1].upper() + js_text(text)[1:] if text else "—"


def world(server) -> str:
    return world_for(server, js_text(server)) or "—"


def pick(name, server) -> str:
    return f"{js_text(name)}|{js_text(server)}"


def unpick(value) -> tuple[str, str]:
    value = js_text(value)
    at = value.rfind("|")
    return (value, "") if at < 0 else (value[:at], value[at + 1:])


def _low(value) -> str:
    return js_text("" if value is None else value).lower()


def _tally(rows: list[dict], key) -> list[tuple]:
    seen: dict = {}
    for row in rows:
        seen[key(row)] = seen.get(key(row), 0) + 1
    return sorted(seen.items(), key=lambda kv: (_low(kv[0]), js_text(kv[0])))


def locally(all_rows: list, p: dict) -> dict:
    """An older log server's whole list (its best 500 by DPS), filtered, sorted and paged here as log server 0.2.171
    does it (``locally``), with its filter menus."""
    rows = [r for r in all_rows if isinstance(r, dict)]
    facets = {"bosses": [{"value": v, "count": n} for v, n in _tally(rows, lambda r: r.get("boss"))],
              "difficulties": [{"value": v, "count": n} for v, n in _tally(rows, lambda r: r.get("difficulty"))],
              "classes": [{"value": v, "count": n} for v, n in _tally(rows, lambda r: r.get("class"))],
              "characters": [{"character": unpick(v)[0], "server": unpick(v)[1], "count": n}
                             for v, n in _tally(rows, lambda r: pick(r.get("character"), r.get("server")))]}
    name, server = unpick(p.get("character"))
    kept = [r for r in rows if (not p.get("boss") or _low(r.get("boss")) == _low(p["boss"]))
            and (not p.get("difficulty") or _low(r.get("difficulty")) == _low(p["difficulty"]))
            and (not p.get("cls") or _low(r.get("class")) == _low(p["cls"]))
            and (not p.get("character") or (_low(r.get("character")) == _low(name) and js_text(r.get("server")) == server))]
    base = sorted(kept, key=lambda r: (_low(r.get("boss")), _low(r.get("difficulty")), _low(r.get("character"))))
    base = sorted(base, key=lambda r: -(js_number(r.get("dps")) or 0))
    ascending = p.get("order") == "asc"
    if p.get("sort") == "parse":
        ranked = [r for r in base if r.get("parse") is not None]
        ranked = sorted(ranked, key=lambda r: js_number(r["parse"]), reverse=not ascending)
        shown = ranked + [r for r in base if r.get("parse") is None]
    else:
        key = {"dps": lambda r: (js_number(r.get("dps")) or 0,), "date": lambda r: (js_number(r.get("uploaded_at")) or 0,),
               "boss": lambda r: (_low(r.get("boss")), _low(r.get("difficulty"))),
               "difficulty": lambda r: (_low(r.get("difficulty")), _low(r.get("boss"))),
               "character": lambda r: (_low(r.get("character")), js_text(r.get("server"))),
               "class": lambda r: (_low(r.get("class")),)}[p.get("sort") or "dps"]
        shown = sorted(base, key=key, reverse=not ascending)
    limit = int(p.get("limit") or 25)
    pages = max(1, math.ceil(len(shown) / limit))
    page = min(int(p.get("page") or 1), pages)
    return {"parses": shown[(page - 1) * limit: page * limit], "total": len(shown), "page": page, "limit": limit,
            "pages": pages, "all": len(rows), "facets": facets}


def parses_query(p: dict) -> str:
    """The top parses' query (``fetchParses``): the page, its size, the order and the filters."""
    query = [("page", str(p["page"])), ("limit", str(p["limit"])), ("sort", p["sort"]), ("order", p["order"])]
    for key, name in (("boss", "boss"), ("difficulty", "difficulty"), ("cls", "class")):
        if p.get(key):
            query.append((name, p[key]))
    if p.get("character"):
        name, server = unpick(p["character"])
        query.append(("character", name))
        if server:
            query.append(("server", server))
    return urllib.parse.urlencode(query)


def whole_list(answer) -> bool:
    """An older log server (0.2.170) answers with its whole list, unpaged and without filter menus."""
    answer = _dict(answer)
    return "page" not in answer or not _truthy(answer.get("facets"))


def parse_menus(facets, p: dict) -> list[tuple[str, str, str, list[tuple[str, str]]]]:
    """The filter menus (``menu``): each one's key, label, the word for all, and its choices with their counts."""
    f = _dict(facets)
    def items(key, shown):
        return [(js_text(x.get("value")), f"{shown(x)} ({js_text(x.get('count'))})") for x in _list(f.get(key)) if isinstance(x, dict)]
    return [("boss", "Boss", "All bosses", items("bosses", lambda x: js_text(x.get("value")))),
            ("difficulty", "Difficulty", "All difficulties", items("difficulties", lambda x: cap(x.get("value")))),
            ("cls", "Class", "All classes", items("classes", lambda x: cap(x.get("value")))),
            ("character", "Character", "All characters",
             [(pick(x.get("character"), x.get("server")), f"{js_text(x.get('character'))} ({world(x.get('server'))}) "
               f"({js_text(x.get('count'))})") for x in _list(f.get("characters")) if isinstance(x, dict)])]


def parse_rows(answer) -> list[dict]:
    """The runs shown: boss, difficulty, character and world, class, DPS (best of how many), parse, date and log."""
    rows = []
    for x in _list(_dict(answer).get("parses")):
        if not isinstance(x, dict):
            continue
        rows.append({"boss": js_text(x.get("boss") or "—"), "difficulty": cap(x.get("difficulty")),
                     "character": js_text(x.get("character") or "—"), "world": world(x.get("server")),
                     "class": cap(x.get("class")), "dps": f"{theme.js_round(js_number(x.get('dps')) or 0):,}",
                     "attempts": many(x.get("attempts") or 1, "Best of {0} ranked run", "Best of {0} ranked runs"),
                     "parse": parse_cell(x), "date": when(x.get("uploaded_at")),
                     "page": log_page({"id": x.get("log"), "segment": x.get("segment")})})
    return rows


def parses_status(answer) -> str:
    answer = _dict(answer)
    return f"Page {js_text(answer.get('page'))} of {js_text(answer.get('pages'))} · " + many(answer.get("total") or 0,
                                                                                         "{0} parse", "{0} parses")


def sort_arrow(p: dict, key: str) -> str:
    return ("▲" if p.get("order") == "asc" else "▼") if p.get("sort") == key else ""


def sorted_by(p: dict, key: str) -> dict:
    """A column's head clicked: the other way round for the column sorted, else its own first direction."""
    if p.get("sort") == key:
        return {**p, "order": "desc" if p.get("order") == "asc" else "asc", "page": 1}
    return {**p, "sort": key, "order": PARSE_SORTS[key], "page": 1}


def missing_parses(message: str) -> bool:
    """A server without top parses (``missing``)."""
    return bool(re.search(r"not found|404|does not send that request", message or "", re.IGNORECASE))
