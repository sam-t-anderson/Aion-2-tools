"""The native Timers page (0.2.428): the regional event timers, the field bosses' respawn reference, their kills by
server and the recorded boss defeats, as the web page shows them (pages/timers.js, and ``A2Timers`` in
static/timers.js).

Every time on it is a community forecast or a recorded observation, never live state, and says so as the web page
does. The event schedules are the bundled ``event-schedules.json``, worked out by the engine the overlay's events
strip uses (``events.occurrences``: every real wall-clock time in the region's zone). The respawn reference is the
bundled ``field-bosses.json``. The kills and the defeats come from the log server through the app's proxy, and the
live meter says which server and faction you play.

The arithmetic here is ``timers.js``'s, kept apart from the page that draws it (``timers_page``) and tested alone.
"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import math
import re
import urllib.parse

from PySide6.QtCore import QDateTime, QTimeZone

from . import events
from .news import when
from .theme import COLORS, js_round

DAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
#: The respawn reference's groups, in the web page's order.
BOSS_GROUPS = (("elyos", "Verteron · Elyos"), ("asmodian", "Altgard · Asmodian"),
               ("abyss", "Abyss · Chaotic Lower Reshanta"))
ZONE_NAMES = {"asmodian": "Altgard", "elyos": "Verteron"}
KILL_FACTIONS = (("mine", "Mine (from the live meter)"), ("elyos", "Elyos zones + Abyss"),
                 ("asmodian", "Asmodian zones + Abyss"), ("all", "Every zone"))
KILL_WINDOW = 172800                              # the kills asked for: the last two days, in seconds
MOST_DEFEATS = 25
SCHEDULE_SOURCE = "https://shugo.gg/timers"
RIFT_REPORT = "https://aion2codex.wiki/tools/rift-timer"
NO_REGION = "Select the region you play. Your device time zone is not used to guess the game region."
NO_GROUP = "Select your Korean matching group to calculate this forecast."
KILLS_NOTE = ("Kills the live meter observed: found in public Live Meter recordings, or sent by the opt-in auto-report "
              "once two installs agree, and placed on the home server of the recorded characters who fought the boss. "
              "A kill appears when a recording is uploaded, not when the boss dies. A visitor from another server "
              "reports its own server, so trust a kill more when several uploaders recorded it. The expected return is "
              "the community respawn reference after the kill (unverified), or a length measured from repeated kills "
              "when the reference has none. The Discord bot's manually entered timers never appear here.")
DEFEATS_NOTE = ("Submitted observations are separate from schedule forecasts. Region is recorded log metadata; it does "
                "not establish physical server or channel. Availability and respawn time remain unknown.")
LOG_ID = re.compile(r"[A-Za-z0-9]{6,16}")


def _text(value) -> str:
    """A value as the web page writes it with ``esc(x ?? '')``: nothing for none."""
    return "" if value is None else str(value)


def _number(value) -> float | None:
    """A finite number, or None (``Number.isFinite``)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _count(value) -> int | float:
    """``Number(x) || 0``: a number as it comes, nought for anything else."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or isinstance(value, bool):
        return 0
    return int(number) if number.is_integer() else number


def dur(minutes) -> str:
    """A respawn length in minutes as the web page writes it: 45m, 2h, 1h 30m."""
    if minutes is None:
        return ""
    whole = int(minutes) if float(minutes).is_integer() else minutes
    if whole >= 60:
        hours, rest = int(whole // 60), whole % 60
        return f"{hours}h {rest:g}m" if rest else f"{hours}h"
    return f"{whole:g}m"


def build_label(value) -> str:
    """A game build as the web page names it (timers.js ``build``)."""
    text = str(value or "Unknown game version")
    text = re.sub(r"version:product:([0-9.]+)", lambda m: "Product version " + ".".join(m.group(1).split(".")[:4]), text)
    text = re.sub(r"build:steam:[0-9]{1,12}:([0-9]{1,20})", r"Legacy build \1 · Steam", text)
    return re.sub(r"build:purple:A2_[A-Z0-9_]{1,80}_PURPLE:([0-9]{1,20})", r"Legacy build \1 · PURPLE", text)


def when_in(ms: float, zone: str) -> str:
    """``when`` in another time zone, the event's own (timers.js ``localIn``); in the computer's clock for a zone
    that does not read."""
    tz = QTimeZone(str(zone or "").encode())
    if not tz.isValid():
        return when(ms)
    return QDateTime.fromMSecsSinceEpoch(int(ms), tz).toString("yyyy-MM-dd HH:mm:ss")


def system_zone() -> str:
    """The computer's own time zone, by its IANA name."""
    return bytes(QTimeZone.systemTimeZoneId()).decode(errors="replace") or "UTC"


def world_for(server_id, fallback: str) -> str:
    """A server's world name from the bundled list (2102 -> Zikel), else ``fallback`` (``A2Servers.label``)."""
    from ..meter.a2parser.lookup import server_name
    key = str("" if server_id is None else server_id).strip()
    return (server_name(key) if key else None) or fallback


# ------------------------------------------------------------------ the event timers
def prepare(catalog: dict, region: str, group, now: float) -> list[dict] | None:
    """Each of the catalog's events in the region (timers.js ``prepare``): its form with the region's overrides and,
    for a matching-group event, the group's time; its zone; and its times from yesterday to eight days on. An event
    with group times and no group chosen is ``unavailable``. None while no region is chosen."""
    found = next((r for r in catalog.get("regions") or [] if isinstance(r, dict) and r.get("id") == region), None)
    if found is None:
        return None
    cache: dict = {}
    prepared = []
    for raw in catalog.get("events") or []:
        event = {**raw, **((catalog.get("overrides") or {}).get(region) or {}).get(raw.get("id"), {})}
        unavailable = bool(event.get("group_times")) and str(group) not in ("1", "2", "3")
        if event.get("group_times") and not unavailable:
            hour, minute = (int(part) for part in event["group_times"][int(group) - 1].split(":"))
            event["hours"], event["minute"] = [hour], minute
        zone = event.get("timezone") or found.get("timezone")
        prepared.append({"event": event, "zone": zone, "unavailable": unavailable,
                         "times": [] if unavailable else events.occurrences(event, zone, now, cache)})
    return prepared


def schedule_line(item: dict, group) -> str:
    """An event card's schedule: its days, its hours, its zone and, for a matching-group event, the group."""
    event = item["event"]
    days = ", ".join(DAY_NAMES[int(day)] for day in event["days"]) if event.get("days") else "Daily"
    minute = int(event.get("minute") or 0)
    if item["unavailable"]:
        hours = "group time unavailable"
    elif len(event.get("hours") or []) == 24:
        hours = f"hourly at :{minute:02d}"
    else:
        hours = ", ".join(f"{int(hour):02d}:{minute:02d}" for hour in event.get("hours") or [])
    line = f"{days} · {hours} · {item['zone']}"
    if event.get("group_times"):
        line += f" · matching group {group or 'unknown'}"
    return line


def forecast_note(event: dict) -> str:
    if event.get("disputed"):
        return "Conflicting community reports — confirm the rift anchor in game."
    return "Community forecast — not live status."


def card_state(item: dict, now: float) -> dict:
    """An event card's moving parts at ``now`` (timers.js ``tick``): the window it is in or the next start, the
    countdown to its end or to that start, the next start in the computer's clock and the event's zone, and the next
    three starts."""
    event, times = item["event"], item["times"]
    duration = float(event.get("duration_minutes") or 0) * 60_000
    running = [t for t in times if t <= now < t + duration]
    active = running[-1] if running else None
    following = next((t for t in times if t > now), None)
    entry = event.get("entry_minutes")
    entry_end = None if active is None else active + float(entry or 0) * 60_000
    if active is not None:
        if entry:
            status = "Forecast: entry window" if now < entry_end else "Forecast: event window; entry closed"
        else:
            status = "Forecast: scheduled window"
        end = entry_end if entry and now < entry_end else active + duration
    else:
        status, end = "Next scheduled start", following
    return {"status": status,
            "countdown": "No upcoming start in the calculated horizon" if end is None else events.countdown(end - now),
            "next": "" if following is None else
            f"Next: {when(following)} local · {when_in(following, item['zone'])} ({item['zone']})",
            "upcoming": "Upcoming local starts: " + " · ".join(when(t) for t in [t for t in times if t > now][:3])}


def source_line(catalog: dict) -> str:
    """Where the schedule comes from and when it was checked."""
    return (f"{_text(catalog.get('source_name'))} · source updated {_text(catalog.get('source_updated_at'))} · "
            f"checked {_text(catalog.get('checked_at'))} · review after {_text(catalog.get('review_after'))}.")


def clock_line(catalog: dict, now: float) -> str:
    """The computer's time and zone, and a warning once the schedule's review date has passed."""
    line = f"Device time: {when(now)} · local zone {system_zone()}."
    try:
        review = datetime.fromisoformat(str(catalog.get("review_after")) + "T00:00:00+00:00")
    except ValueError:
        return line
    if review.timestamp() * 1000 <= now:
        line += " Schedule review is overdue; forecasts may be stale."
    return line


def utc_day(now: float) -> str:
    """The UTC date at ``now``: the schedule is worked out again when it changes."""
    return datetime.fromtimestamp(now / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ the respawn reference
def boss_groups(field_catalog: dict | None, query: str = "") -> list[tuple[str, str, list[dict], bool]]:
    """The reference's bosses by zone, those matching ``query`` (name or zone): each group's key, its title, its
    bosses and whether it starts open (the Abyss, or any while searching). A group with none is left out."""
    if not isinstance(field_catalog, dict):
        return []
    term = query.strip().lower()
    bosses = [b for b in field_catalog.get("bosses") or [] if isinstance(b, dict)]

    def matches(boss) -> bool:
        return not term or term in f"{boss.get('name')} {boss.get('zone')}".lower()
    groups = []
    for faction, title in BOSS_GROUPS:
        rows = [boss for boss in bosses if boss.get("faction") == faction and matches(boss)]
        if rows:
            groups.append((faction, title, rows, faction == "abyss" or bool(term)))
    return groups


def group_title(title: str, rows: list) -> str:
    return f"{title} · {len(rows)} boss{'' if len(rows) == 1 else 'es'}"


def respawn_line(boss: dict) -> str:
    """A boss's respawn: after a kill, or its schedule; whether it was checked in game."""
    if boss.get("respawn_minutes") is not None:
        line = f"Respawn ~{dur(boss['respawn_minutes'])} after kill"
    else:
        line = boss.get("schedule") or "Schedule unknown"
    return line + (" · checked in game" if boss.get("checked_in_game") else "")


# ------------------------------------------------------------------ the kills by server
def name_key(name) -> str:
    """A boss's name to compare by: lower case, letters, digits and spaces ("Argo, the Spirit King" is "Argo the
    Spirit King")."""
    return "".join(c for c in str(name or "").lower() if c.isalnum() or c == " ").strip()


def map_faction(map_id) -> str | None:
    """Whose zone a map is: Altgard's maps are the Asmodians', Verteron's the Elyos'; else None."""
    try:
        m = float(map_id)
    except (TypeError, ValueError):
        return None
    if m in (1100, 1110, 1111) or 110001 <= m < 112000:
        return "asmodian"
    if m in (1000, 1010, 1011) or 100001 <= m < 102000:
        return "elyos"
    return None


def boss_entry(kill: dict, field_catalog: dict | None) -> dict:
    """A kill's boss in the reference (timers.js ``bossEntry``): its faction, zone and respawn. Where the kill was
    recorded decides whose it is; a name listed in both Verteron and Altgard has one row each, and an Abyss
    namesake of a zone boss is not taken for it."""
    mf = map_faction(kill.get("map_id"))
    bosses = field_catalog.get("bosses") or [] if isinstance(field_catalog, dict) else []
    rows = [b for b in bosses if isinstance(b, dict) and name_key(b.get("name")) == name_key(kill.get("boss"))]
    if len(rows) <= 1:
        row = rows[0] if rows else None
    else:
        row = (mf and next((b for b in rows if b.get("faction") == mf), None)) or {
            **rows[0], "faction": "abyss", "zone": " / ".join(str(b.get("zone")) for b in rows), "respawn_minutes": None}
    if row and mf and row.get("faction") != mf:
        row = None
    respawn = row.get("respawn_minutes") if row else None
    return {"faction": mf or (row.get("faction") if row else None) or None,
            "zone": (row.get("zone") if row else None) or (ZONE_NAMES[mf] if mf else ""),
            "respawn_minutes": respawn}


def wanted_faction(kill_faction: str, identified: dict | None) -> str:
    """The faction whose zones to show: yours from the live meter, one chosen, or every one ("")."""
    if kill_faction == "mine":
        return (identified or {}).get("faction") or ""
    return "" if kill_faction == "all" else kill_faction


def server_label(kill: dict) -> str:
    """A kill's server: its world name and region."""
    name = kill.get("server_name") or world_for(kill.get("server"), f"Server {_text(kill.get('server'))}")
    return name + (f" · {str(kill['region']).upper()}" if kill.get("region") else "")


def kills_of(kill_data) -> list[dict]:
    """The kills with a server and a time."""
    kills = kill_data.get("kills") if isinstance(kill_data, dict) else None
    return [k for k in kills or [] if isinstance(k, dict) and k.get("server") is not None
            and _number(k.get("killed_at")) is not None]


def servers(kills: list[dict], kill_server: str) -> list[tuple[str, str]]:
    """The servers with kills, by name, and the one chosen even without any."""
    found: dict[str, str] = {}
    for kill in kills:
        found.setdefault(str(kill["server"]), server_label(kill))
    if kill_server and kill_server not in found:
        found[kill_server] = f"Server {kill_server} · no recent kills"
    return sorted(found.items(), key=lambda pair: pair[1].casefold())


def kill_rows(kills: list[dict], kill_server: str, faction: str, field_catalog: dict | None) -> list[dict]:
    """The chosen server's kills, in the faction's zones and the Abyss when a faction is wanted."""
    rows = [k for k in kills if str(k["server"]) == kill_server]
    if faction:
        rows = [k for k in rows if boss_entry(k, field_catalog)["faction"] in (faction, "abyss")]
    return rows


def kills_status(kill_data: dict, kill_server: str, rows: list, server_count: int) -> str:
    if kill_server:
        hours = js_round(float(kill_data.get("window_seconds") or 0) / 3600)
        return (f"{len(rows)} bosses with a recorded kill in the last {hours} hours. "
                f"Snapshot {when(float(kill_data.get('generated_at') or 0) * 1000)}.")
    return f"{server_count} servers have recorded kills. Choose yours."


def kill_summary(kill: dict, entry: dict) -> str:
    reports = _count(kill.get("reports"))
    uploaders = "1 uploader" if reports == 1 else f"{reports} uploaders"
    zone = f" · {entry['zone']}" if entry.get("zone") else ""
    return f"{_text(kill.get('boss'))}{zone} · killed {when(kill['killed_at'] * 1000)} · {uploaders}"


def kill_back(kill: dict, entry: dict) -> float | None:
    """When a killed boss is expected back (seconds since 1970): its kill plus the reference's respawn, else the
    log server's own estimate from repeated kills; None when neither is known."""
    if entry["respawn_minutes"] is not None:
        return kill["killed_at"] + entry["respawn_minutes"] * 60
    return _number(kill.get("respawn_at"))


def kill_basis(kill: dict, entry: dict) -> str:
    """What the expected return rests on."""
    if entry["respawn_minutes"] is not None:
        return f"community respawn reference {dur(entry['respawn_minutes'])} (unverified)"
    return (f"respawn about {events.countdown(float(kill.get('respawn_seconds') or 0) * 1000)}, measured from "
            f"{_count(kill.get('respawn_samples'))} gaps between kills")


UNKNOWN_RESPAWN = ("Respawn length unknown: no community reference, and it needs repeated kills of this boss in "
                   "uploaded logs.")


def back_text(back: float, now: float) -> str:
    """The expected return as it counts down (timers.js ``tickKills``)."""
    at = back * 1000
    return f"Expected back within {events.countdown(at - now)} ({when(at)})" if at > now else f"Expected back since {when(at)}"


def no_kills(kill_server: str, rows: list, faction: str) -> str:
    if not kill_server or rows:
        return ""
    return (f"No kills recorded for this server{f' in {faction} zones or the Abyss' if faction else ''} yet. "
            "They come from public Live Meter logs uploaded by players there.")


def identity_line(identified: dict | None, kill_faction: str) -> str:
    """Who the live meter says you are, or how to let it say so."""
    if identified and identified.get("server"):
        who = f"{identified['character']} on " if identified.get("character") else ""
        server = identified.get("server_name") or world_for(identified["server"], f"server {identified['server']}")
        faction = identified.get("faction")
        side = f" · {faction[:1].upper()}{faction[1:]}" if faction else " · faction not resolved yet"
        return (f"Identified from your live meter: {who}{server}{side}. Kills come from Live Meter recordings and "
                "corroborated auto-reports only; the Discord bot's manual timers are never used.")
    if kill_faction == "mine":
        return "Start the live meter so your server and faction are identified, or choose a faction and server here."
    return ""


def log_page(log_id, segment=None) -> str:
    """The web interface's page for a shared log (pages/timers.js ``logURL``), or "" for an id that is not one."""
    if not isinstance(log_id, str) or not LOG_ID.fullmatch(log_id):
        return ""
    page = f"combat-log/shared/{urllib.parse.quote(log_id, safe='')}?mode=pve"
    if isinstance(segment, int) and not isinstance(segment, bool):
        page += f"&segment={segment}"
    return page


def source_link(log_id, segment=None) -> str:
    """A link to the log a kill or defeat was recorded in, as rich text; "Source unavailable" without one."""
    page = log_page(log_id, segment)
    if not page:
        return "Source unavailable"
    words = "Source log" + (f" · encounter {segment + 1}" if isinstance(segment, int) and not isinstance(segment, bool) else "")
    return f'<a href="web:{html.escape(page)}" style="color: {COLORS["accent"]};">{html.escape(words)}</a>'


def kill_sources(kill: dict) -> str:
    """A kill's previous kill and its first three logs, as rich text."""
    previous = kill.get("previous_killed_at")
    head = "" if previous is None else f"Previous kill {html.escape(when(previous * 1000))} · "
    return head + " · ".join(source_link(log_id) for log_id in (kill.get("logs") or [])[:3])


# ------------------------------------------------------------------ the recorded defeats
def defeat_rows(boss_data: dict | None, term: str = "") -> list[dict]:
    """The returned groups matching ``term`` (a boss's name or NPC id), at most 25."""
    groups = boss_data.get("groups") if isinstance(boss_data, dict) else None
    needle = term.strip().lower()
    return [g for g in groups or [] if isinstance(g, dict)
            and needle in f"{g.get('boss')} {g.get('npc_id')}".lower()][:MOST_DEFEATS]


def defeats_status(boss_data: dict, rows: list) -> str:
    capped = "Server results capped. " if boss_data.get("truncated") else ""
    return (f"{len(rows)} displayed groups (up to {MOST_DEFEATS}). Snapshot "
            f"{when(float(boss_data.get('generated_at') or 0) * 1000)}. {capped}Search filters the returned snapshot.")


def defeat_summary(group: dict) -> str:
    last = group.get("last_defeat_at")
    return (f"{_text(group.get('boss'))} · {group.get('region') or 'Unknown region'} · "
            f"{'Time unavailable' if last is None else when(last * 1000)}")


def defeat_detail(group: dict) -> str:
    """A group's observations, build, NPC, map and source, as rich text."""
    return (f"{_count(group.get('observed_defeats'))} observations · {html.escape(build_label(group.get('game_patch')))} · "
            f"NPC {html.escape(_text(group.get('npc_id')))} · map {html.escape(str(group.get('map_id') or 'unknown'))} / "
            f"instance {html.escape(str(group.get('instance_id') or 'unknown'))}. "
            + source_link(group.get("last_log_id"), group.get("last_segment")))


def omitted_line(group: dict) -> str:
    return f"{_count(group.get('omitted_history'))} earlier observations omitted."


def defeat_history(group: dict) -> list[str] | None:
    """The group's recent observations, each as rich text; None from a log server too old to send them."""
    recent = group.get("recent_defeats")
    if not isinstance(recent, list):
        return None
    lines = []
    for defeat in recent:
        if not isinstance(defeat, dict):
            continue
        at = defeat.get("defeated_at")
        basis = defeat.get("timing_basis")
        lines.append(f"{'Time unavailable' if at is None else html.escape(when(at * 1000))} · "
                     f"{_count(defeat.get('engaged_roster_members'))} engaged · "
                     f"{html.escape(str(defeat.get('evidence') or 'Evidence unavailable'))}"
                     + (f" · {html.escape(str(basis))}" if basis and basis != "recorded_clock" else "")
                     + " · " + source_link(defeat.get("log_id"), defeat.get("segment")))
    return lines
