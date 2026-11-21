"""The overlay's events strip in the native interface (0.2.419): the next rift, Shugo Festival, invasion, siege and
field-boss windows for the region picked on the Timers page, and the field bosses the meter has seen killed.

``occurrences``, ``upcoming`` and ``short_countdown`` are ``event-schedule.js``'s, the engine the Timers page and the
web overlay share: every real wall-clock time of an event in its region's zone, a missing hour of a spring-forward
night skipped and a repeated one of an autumn night kept. The zones are Qt's (``QTimeZone``), which knows the IANA
names on every system, Windows included. A scheduled window is a community forecast, never live status, and is
named so.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
import html
import math

from PySide6.QtCore import QDateTime, QTimeZone

EVENT_LEAD_MS = 15 * 60_000               # an event joins the strip 15 minutes before it starts
OBSERVED_GRACE_MS = 30 * 60_000           # an observed kill stays listed this long past its expected return
_ZONES: dict[str, QTimeZone] = {}


def _zone(name: str) -> QTimeZone:
    if name not in _ZONES:
        _ZONES[name] = QTimeZone(name.encode())
    return _ZONES[name]


def _wall(zone: QTimeZone, ms: float) -> tuple[int, int, int, int, int]:
    """The wall clock in ``zone`` at an instant (ms since the epoch), to the minute."""
    moment = QDateTime.fromMSecsSinceEpoch(int(ms), zone)
    day, clock = moment.date(), moment.time()
    return day.year(), day.month(), day.day(), clock.hour(), clock.minute()


def _utc_ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    """``Date.UTC``: a wall-clock time read as UTC, in ms; a day past the month's end runs into the next."""
    return calendar.timegm((year, month, 1, hour, minute, 0)) * 1000 + (day - 1) * 86_400_000


def occurrences(event: dict, zone: str, now: float, cache: dict | None = None) -> list[int]:
    """Every real wall-clock time of ``event`` in ``zone`` from yesterday to eight days on (ms since the epoch)."""
    cache = {} if cache is None else cache
    tz = _zone(zone)
    if not tz.isValid():
        return []
    year, month, day, _hour, _minute = _wall(tz, now)
    found = set()
    for delta in range(-1, 9):
        base = _utc_ms(year, month, day + delta)
        weekday = (calendar.weekday(*_ymd(base)) + 1) % 7      # JavaScript's getUTCDay: Sunday is 0
        if event.get("days") and weekday not in event["days"]:
            continue
        key = (zone, base)
        if key not in cache:                  # the zone's offsets about that day: one, or two across a change
            offsets = set()
            for hours in (-24, 0, 12, 24, 48):
                moment = base + hours * 3_600_000
                offsets.add(_utc_ms(*_wall(tz, moment)) - moment)
            cache[key] = offsets
        offsets = cache[key]
        for hour in event.get("hours") or []:
            wall = base + (int(hour) * 60 + int(event.get("minute") or 0)) * 60_000
            for offset in offsets:
                moment = wall - offset
                # One offset all about the day: every wall time is one instant, as the check below would find; on
                # a day the clocks change, a skipped wall time has no instant and a repeated one has two.
                if len(offsets) == 1 or _utc_ms(*_wall(tz, moment)) == wall:
                    found.add(moment)
    return sorted(found)


def _ymd(ms: int) -> tuple[int, int, int]:
    moment = datetime.fromtimestamp(ms // 1000, tz=timezone.utc)
    return moment.year, moment.month, moment.day


def countdown(ms: float) -> str:
    """The Timers page's countdown (event-schedule.js ``countdown``): 05:03:02, the days before it when there are
    any (1d 05:03:02)."""
    seconds = max(0, math.ceil(ms / 1000))
    days = seconds // 86400
    return (f"{days}d " if days else "") + f"{seconds // 3600 % 24:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def short_countdown(ms: float) -> str:
    """The overlay's countdown: 45s, 5m, 1h 05m."""
    seconds = max(0, math.ceil(ms / 1000))
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds // 60 % 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def resolve_events(catalog: dict, region: str, group) -> list[tuple[dict, str]]:
    """Each event of the region in its catalog form, with the region's overrides and, for a matching-group event,
    the group's time; an event with group times and no group picked is left out."""
    found = next((r for r in catalog.get("regions") or [] if r.get("id") == region), None)
    if found is None:
        return []
    out = []
    for raw in catalog.get("events") or []:
        event = {**raw, **((catalog.get("overrides") or {}).get(region) or {}).get(raw.get("id"), {})}
        if event.get("group_times"):
            if str(group) not in ("1", "2", "3"):
                continue
            hour, minute = (int(part) for part in event["group_times"][int(group) - 1].split(":"))
            event["hours"], event["minute"] = [hour], minute
        out.append((event, event.get("timezone") or found.get("timezone")))
    return out


def upcoming(catalog: dict, region: str, group, now: float) -> list[dict]:
    """Each event's state for display, the running ones first, then the soonest: ``id``, ``name``, ``disputed``,
    ``zone``, ``active``, ``entry_open``, ``ends_at``, ``next`` and ``starts_in_ms``."""
    cache: dict = {}
    states = []
    for event, zone in resolve_events(catalog, region, group):
        times = occurrences(event, zone, now, cache)
        duration = float(event.get("duration_minutes") or 0) * 60_000
        running = [t for t in times if t <= now < t + duration]
        active = running[-1] if running else None
        following = next((t for t in times if t > now), None)
        entry = float(event.get("entry_minutes") or 0) * 60_000
        entry_end = None if active is None else active + entry
        entry_open = (now < entry_end if entry else True) if active is not None else False
        if active is None:
            ends_at = None
        elif entry and now < entry_end:
            ends_at = entry_end
        else:
            ends_at = active + duration
        states.append({"id": event.get("id"), "name": event.get("name"), "disputed": bool(event.get("disputed")),
                       "zone": zone, "active": active is not None, "entry_open": entry_open, "ends_at": ends_at,
                       "next": following, "starts_in_ms": None if following is None else following - now})

    def order(state):
        if state["active"]:
            return (0, state["ends_at"] or 0)
        return (1, math.inf if state["starts_in_ms"] is None else state["starts_in_ms"])
    return sorted(states, key=order)


def observed_kills(field_bosses, now: float, show: bool = True) -> list[dict]:
    """The field bosses the meter's uploaders saw killed, from 15 minutes before each is expected back until half an
    hour after (overlay.js ``observedBossEvents``)."""
    if not show or not isinstance(field_bosses, dict) or not field_bosses.get("faction"):
        return []
    out = []
    for kill in field_bosses.get("kills") or []:
        expected = kill.get("expected_at") if isinstance(kill, dict) else None
        if not isinstance(expected, (int, float)) or isinstance(expected, bool) or not math.isfinite(expected):
            continue
        at = expected * 1000
        starts_in = at - now
        if starts_in > EVENT_LEAD_MS or starts_in < -OBSERVED_GRACE_MS:
            continue
        ago = short_countdown(max(0.0, now - float(kill.get("killed_at") or 0) * 1000))
        reports = int(kill.get("reports") or 0)
        who = "1 uploader" if reports == 1 else f"{reports} uploaders"
        server = field_bosses.get("server_name") or f"server {field_bosses.get('server')}"
        basis = kill.get("respawn_basis")
        respawn = (f"; community respawn reference {kill.get('respawn_minutes')} min, unverified" if basis == "reference"
                   else "; respawn measured from repeated kills" if basis == "measured" else "")
        zone = kill.get("zone") or ""
        out.append({"id": f"fb:{kill.get('boss')}:{round(float(kill.get('killed_at') or 0))}", "name": kill.get("boss"),
                    "zone": zone, "observed": True, "active": starts_in <= 0, "starts_in_ms": starts_in,
                    "ends_at": at + OBSERVED_GRACE_MS,
                    "tip": f"{kill.get('boss')} — observed kill {ago} ago by {who} on {server} (live meter recordings, "
                           f"not Discord timers){respawn}{' · ' + zone if zone else ''}"})
    return out


def strip(catalog: dict | None, region: str, group, field_bosses, now: float, show_bosses: bool = True) -> list[dict]:
    """The strip's three soonest: the observed kills and the forecast windows running or starting within 15 minutes,
    the running ones first. Each carries its ``text`` and ``tip``; empty when there is nothing to show."""
    observed = observed_kills(field_bosses, now, show_bosses)
    if not region and not observed:
        return []
    forecast = [state for state in (upcoming(catalog, region, group, now) if region and catalog else [])
                if state["active"] or (state["starts_in_ms"] is not None and state["starts_in_ms"] <= EVENT_LEAD_MS)]
    shown = sorted(observed + forecast, key=lambda e: -1 if e["active"] else e["starts_in_ms"])[:3]
    for event in shown:
        if event.get("observed"):
            event["when"] = "now" if event["active"] else f"back in {short_countdown(event['starts_in_ms'])}"
        else:
            if event["active"]:
                event["when"] = (f"entry {short_countdown(event['ends_at'] - now)}" if event["entry_open"] and event["ends_at"]
                                 else f"ends {short_countdown(event['ends_at'] - now)}" if event["ends_at"] else "now")
            else:
                event["when"] = f"in {short_countdown(event['starts_in_ms'])}"
            event["tip"] = (f"{event['name']} — community forecast ({event['zone']}), not live status"
                            f"{'; conflicting community reports, confirm in game' if event['disputed'] else ''}")
        event["text"] = f"{event['name']} {event['when']}"
    return shown


def strip_html(shown: list[dict], label: str | None = None) -> str:
    """The strip as the overlay draws it (overlay.css ``.ovevents``): a forecast's time grey, green while it runs;
    an observed kill's amber, gold once the boss is due. ``label`` is the "Events" label as rich text, in the
    overlay's label look."""
    parts = []
    for event in shown:
        if event.get("observed"):
            name, when = "#b5bfd0", "#f0c36a" if event["active"] else "#e3ad7f"
        else:
            name, when = "#9aa3b5", "#8fd0a0" if event["active"] else "#cdd6e6"
        parts.append(f"<span style='color:{name}'>{html.escape(str(event['name']))} "
                     f"<b style='color:{when}'>{html.escape(event['when'])}</b></span>")
    return (label or '<span style="color:#e8cf8e; font-weight:600">Events</span>') + " " + " · ".join(parts)
