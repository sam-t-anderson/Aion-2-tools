"""The log review's words (0.2.457), as combat-review.js reads a combat log (an a2log document). A log is a recorded
session saved on this computer (``#/combat-log/local/<file>``) or one shared on the log server
(``#/combat-log/shared/<id>``).

These are the review's model and the frame's words:
- each encounter's roster (``segmentRefs``): its players and entities, their pets' owners, labels and profiles;
- its events and its players' totals (``data``): damage done and taken, healing, deaths and revives, and the DPS's
  active clock. A PvP opponent can be read from their own side;
- the summary table and its parses (``parseHTML``), and the notes around it: the PvP and arena match notes, an
  opponent's records, the heals left out or rebuilt, the sources, the capture quality and the run timing.
- Since 0.2.458 the rate chart (``graph``), the recorder's ping, the bosses' HP and the enemy encounters.
- Since 0.2.459 the Table, Timeline and Events views: the events' list with a spreadsheet's column filters
  (``efPass``, ``efColumn``), a page of a hundred at a time, and the recorded effect timeline (``timeline``).
- Since 0.2.460 the abilities and skills (``detailsHTML``): each player's abilities by amount, as bars and as a table;
  their skills' casts with cooldown usage (``skillsHTML``); and every press over the fight (``castTimeline``).
"""
from __future__ import annotations

import math
import re
import urllib.parse

from .account import parse_tier
from .character import js_number
from .combat import encode_component, js_string
from .combat_records import build_label
from .results import _dict, _list, _truthy, js_text
from . import theme

MODES = (("", "All recorded modes"), ("pve", "PvE"), ("pvp", "PvP"))
METRICS = (("summary", "Summary"), ("damage", "Damage Done"), ("taken", "Damage Taken"), ("healing", "Healing"),
           ("deaths", "Death recaps"))
PIECE_LABELS = {"after_kill": " (after the kill)", "opening_blow": " (the boss's opening blow)"}
MINIBOSS_CODES = {"2300907", "2310907", "2320907"}                 # Shining Mau Totem
UNKNOWN = "Unknown / not recorded"
LOADING = "Loading combat log…"
PVP_NOTE = ("PvP recording · matched by mode, arena/encounter, ruleset and game version. Opponents are outside the recorded "
            "Self/Party roster. Only observed combat effects are shown; match results, objectives and kill credit are not "
            "inferred.")
CHOOSE_OPPONENT = "Choose an opponent under Player to see the fight from their side."
NO_MODE_ENCOUNTERS = "No encounters recorded for this combat mode."
SHOW_ALL = "Show all recorded encounters"
PARSE_NOTE = (" Parse: percentile among every ranked run of the same class on this encounter, by every character (100 = "
              "above them all); dimmed when fewer than 5 runs compare.")
OLD_QUALITY = "This older log does not contain a capture-quality assessment. It remains available for review."
NO_RUNS = "Run timing and progression are unavailable in this older recording."
ARENA_NOTE = ("From the game's own arena records: the roster as the match opened, each round's result and the match result. "
              "A round's loser died; their death marker names the winner.")
OPPONENT_NOTE = ("The review below reads the fight from their side: the summary, graph, timeline and events, their abilities, "
                 "their deaths, and the buffs, debuffs and crowd control on and from them. Only what the recording holds of "
                 "them is shown.")
REFRESH = "Refresh rankings"
ELSEWHERE = ("The actions, death recaps, insights, rankings, reports, comparisons and movement replay of this log open in the "
             "web interface for now.")
OPEN_WEB = "Open the full review in the web interface"
SUMMARY_COLUMNS = ["Player / server", "Class", "Damage done", "DPS", "Damage taken", "Healing", "HPS", "Deaths"]


def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _amount(e: dict) -> float:
    return _num(e.get("amount")) or 0.0


def number(x) -> str:
    """``number``: a whole number grouped as the computer's language groups it, nothing as 0."""
    return theme.digits(_num(x) or 0.0)


def fixed(x, digits: int) -> str:
    value = _num(x)
    return "NaN" if value is None else theme.fixed(value, digits)


def seconds(x) -> str:
    """A length as m:ss.s (``seconds``), "Unavailable" for none."""
    value = _num(x)
    if x is None or value is None:
        return "Unavailable"
    return f"{math.floor(value / 60)}:{theme.fixed(value % 60, 1).rjust(4, '0')}"


def clock(t, precise: bool = False) -> str:
    """A moment of the fight as m:ss, or m:ss.ss (``clock``)."""
    value = max(0.0, _num(t) or 0.0)
    if precise:
        value = theme.js_round(value * 100) / 100
        return f"{math.floor(value / 60)}:{theme.fixed(value % 60, 2).rjust(5, '0')}"
    value = math.floor(value)
    return f"{value // 60}:{str(value % 60).rjust(2, '0')}"


def world(server_id, fallback=None) -> str:
    """A server's world name from the bundled list (``worldFor``), else the fallback or its number."""
    from .timers import world_for
    return world_for(server_id, js_text(fallback) if fallback is not None else js_string(server_id))


def actor_label(e) -> str:
    """An actor as the review names it (``actorLabel``): its name, a verified ✓, hidden by its player, its server."""
    if not isinstance(e, dict) or not e:
        return UNKNOWN
    name = js_text(e.get("name") or e.get("id"))
    if _truthy(e.get("verified")):
        name += " ✓"
    if _truthy(e.get("pseudonym")):
        name += " (hidden by its player)"
    if _truthy(e.get("server")):
        name += " · " + world(e.get("server"), e.get("server_name"))
    return name


def is_character(e, doc: dict) -> bool:
    """A player the review links to their build (``character``)."""
    if not isinstance(e, dict) or not e:
        return False
    return (any(_dict(p).get("id") == e.get("id") for p in _list(doc.get("players"))) or _truthy(e.get("is_player"))
            or e.get("kind") == "player")


# ------------------------------------------------------------------ the roster and the events
def segment_refs(doc: dict, segment: dict, everyone: bool) -> dict:
    """The actors of one fight (``segmentRefs``): those who took part in it, by id, with their profiles and their pets'
    classes; everyone when the fight names none."""
    active = set(_list(segment.get("party_members")))
    for e in _list(segment.get("events")):
        e = _dict(e)
        for key in ("source", "target"):
            if _truthy(e.get(key)):
                active.add(e[key])
    for h in _list(segment.get("hits")):
        h = _dict(h)
        for key in ("player", "source", "target", "pet"):
            if _truthy(h.get(key)):
                active.add(h[key])
    entities = [x for x in _list(segment.get("entities")) if isinstance(x, dict)]
    for _ in entities:
        for x in entities:
            if x.get("id") in active and _truthy(x.get("owner")):
                active.add(x["owner"])

    def keep(identifier) -> bool:
        return identifier in active if active else everyone

    r: dict = {}
    for x in [p for p in _list(doc.get("players")) if isinstance(p, dict) and keep(p.get("id"))] + \
             [x for x in entities if keep(x.get("id"))]:
        r[x.get("id")] = {**r.get(x.get("id"), {}), **x}
    for x in [p for p in _list(doc.get("players")) if isinstance(p, dict)] + \
             [x for s in _list(doc.get("segments")) for x in _list(_dict(s).get("entities")) if isinstance(x, dict)]:
        if _truthy(x.get("profile_snapshot")) and x.get("id") in r:
            r[x["id"]]["profile_snapshot"] = x["profile_snapshot"]
    for x in r.values():
        if _truthy(x.get("owner")):
            x["class"] = _dict(r.get(x["owner"])).get("class")
    return r


def root_owner(identifier, r: dict):
    """The actor at the top of a pet's owners (``rootOwner``)."""
    seen = set()
    while _truthy(_dict(r.get(identifier)).get("owner")) and identifier not in seen:
        seen.add(identifier)
        identifier = r[identifier]["owner"]
    return identifier


def mode_of(doc: dict, segment: dict) -> str:
    kind = js_text(_dict(segment).get("encounter_type") or _dict(doc.get("meta")).get("encounter_type") or "")
    return "pvp" if kind.startswith("pvp_") else "pve"


def segments(doc: dict) -> list[dict]:
    return [s if isinstance(s, dict) else {} for s in _list(doc.get("segments"))]


def matches_mode(doc: dict, segment: dict, mode: str) -> bool:
    return not mode or mode_of(doc, segment) == mode


def fresh_state(mode=None, segment=None) -> dict:
    """The review's choices as it opens (``state``)."""
    return {"mode": mode if mode in ("pve", "pvp") else "", "run": "", "segment": segment if isinstance(segment, int) else 0,
            "metric": "summary", "view": "table", "combine": True, "pets": True, "actor": "", "enemy": "", "graph": True,
            "graph_mode": "total", "hidden": set(), "timeline": True, "timeline_window": 30, "timeline_start": 0.0,
            "skills": True, "deaths": True, "heals": True, "page": 0, "ef": None, "ef_search": {}, "ef_open": "",
            "detail": "contribution", "hide_procs": True}


def settle_segment(doc: dict, state: dict) -> None:
    """The encounter shown kept within the combat mode chosen (``render``'s start)."""
    all_segments = segments(doc)
    current = all_segments[state["segment"]] if 0 <= state["segment"] < len(all_segments) else None
    if current is None or not matches_mode(doc, current, state["mode"]):
        state["segment"] = next((i for i, s in enumerate(all_segments) if matches_mode(doc, s, state["mode"])), -1)
        state["run"] = state["actor"] = state["enemy"] = ""


def refs(doc: dict, state: dict) -> dict:
    all_segments = segments(doc)
    segment = all_segments[state["segment"]] if 0 <= state["segment"] < len(all_segments) else {}
    return segment_refs(doc, segment, not state.get("run"))


def data(doc: dict, state: dict, foe: str = "") -> dict:
    """A fight's events and its players' totals (``data``). ``foe``, a PvP opponent's id, reads the fight from their
    side: their damage done and taken, healing and deaths."""
    all_segments = segments(doc)
    segment = all_segments[state["segment"]] if 0 <= state["segment"] < len(all_segments) else {"duration": 1, "hits": []}
    r = refs(doc, state)
    recorded = [e for e in _list(segment.get("events")) if isinstance(e, dict)]
    if recorded:
        events = list(recorded)
    else:
        events = [{"kind": "damage", "t": _dict(h).get("t"), "source": _dict(h).get("source") or _dict(h).get("player"),
                   "target": _dict(h).get("target"), "amount": _dict(h).get("damage"), "skill": _dict(h).get("skill"),
                   "skill_id": _dict(h).get("skill_id")} for h in _list(segment.get("hits"))]
    events.sort(key=lambda e: _num(e.get("t")) or 0.0)
    friendly = {_dict(p).get("id") for p in _list(doc.get("players"))}
    combine = state.get("combine", True)

    def owner(identifier):
        return root_owner(identifier, r) if combine else identifier

    def party(identifier) -> bool:
        return root_owner(identifier, r) in friendly

    if foe:
        def member(identifier):
            return identifier == foe

        def ours(identifier):
            return root_owner(identifier, r) == foe
        ours_root = ours
    else:
        def member(identifier):
            return identifier in friendly

        def ours(identifier):
            return identifier in friendly or _truthy(_dict(r.get(identifier)).get("owner"))
        ours_root = party

    def enemy_side(identifier) -> bool:
        root = root_owner(identifier, r)
        return root not in friendly and _dict(r.get(root)).get("kind") == "enemy"

    stored = _dict(segment.get("unattributed_heals"))
    unattributed = ({"count": stored.get("records"), "amount": _num(stored.get("amount")) or 0.0,
                     "skills": dict(_dict(stored.get("skills")))} if _truthy(stored.get("records")) else None)
    if mode_of(doc, segment) == "pvp":                  # a heal between the two sides is nobody's (0.2.399)
        kept = []
        for e in events:
            between = e.get("kind") == "heal" and (party(e.get("source")) and enemy_side(e.get("target"))
                                                   or enemy_side(e.get("source")) and party(e.get("target")))
            if not between:
                kept.append(e)
                continue
            if not foe or ours(e.get("source")) or ours(e.get("target")):
                unattributed = unattributed or {"count": 0, "amount": 0.0, "skills": {}}
                unattributed["count"] = int(_num(unattributed["count"]) or 0) + 1
                unattributed["amount"] += _amount(e)
                skill = js_text(e.get("skill") or e.get("skill_id") or "Unknown")
                unattributed["skills"][skill] = unattributed["skills"].get(skill, 0) + 1
        events = kept
    enemy = "" if foe else state.get("enemy", "")
    enemies = set(filter(None, js_text(enemy).split(","))) if enemy else set()
    seen_deaths = set()
    rows: dict = {}

    def row(identifier):
        key = owner(identifier)
        if not _truthy(key):
            return None
        if key not in rows:
            rows[key] = {**(r.get(key) or {"id": key, "name": key}), "damage": 0.0, "taken": 0.0, "healing": 0.0,
                         "deaths": 0, "revives": 0, "hits": 0, "struck": 0, "heals": 0}
        return rows[key]

    for e in events:
        kind, source, target = e.get("kind"), e.get("source"), e.get("target")
        if kind == "death":
            key = f"{js_text(target)}:{js_text(e.get('t'))}"
            if key in seen_deaths:
                continue
            seen_deaths.add(key)
            if member(target) or (not combine and ours(target) and _truthy(_dict(r.get(target)).get("owner"))):
                p = row(target)
                if p is not None:
                    p["deaths"] += 1
            continue
        if kind == "revive":
            if member(target):
                p = row(target)
                if p is not None:
                    p["revives"] += 1
            continue
        if kind == "damage":
            if ours(source) and (not enemies or target in enemies):
                p = row(source)
                if p is not None:
                    p["damage"] += _amount(e)
                    p["hits"] += 1
            if ours(target) and not ours_root(source) and (not enemies or source in enemies):
                p = row(target)
                if p is not None:
                    p["taken"] += _amount(e)
                    p["struck"] += 1
        if kind == "heal" and ours(source):
            p = row(source)
            if p is not None:
                p["healing"] += _amount(e)
                p["heals"] += 1
    outgoing = [e for e in events if e.get("kind") == "damage" and ours_root(e.get("source")) and not ours_root(e.get("target"))]
    first = (_num(outgoing[0].get("t")) or 0.0) if outgoing else 0.0
    dps_duration = max(1, len({math.floor(max(0.0, (_num(e.get("t")) or 0.0) - first)) for e in outgoing}))
    return {"segment": segment, "r": r, "events": events, "rows": list(rows.values()), "friendly": friendly,
            "dps_duration": dps_duration, "foe": foe, "ours": ours, "party": party, "owner": owner,
            "unattributed": unattributed}


def opponents_of(doc: dict, d: dict) -> list[dict]:
    """A PvP fight's opponents: the enemy players in it, offered under Player beside the party (``opponentsOf``)."""
    if mode_of(doc, d["segment"]) != "pvp":
        return []
    return [e for e in d["r"].values() if e.get("kind") == "enemy" and _truthy(e.get("is_player"))
            and e.get("id") not in d["friendly"]]


# ------------------------------------------------------------------ the frame
def title(doc: dict) -> str:
    return js_text(_dict(doc.get("meta")).get("title") or "Combat log")


def duration(d: dict) -> float:
    return max(1.0, _num(d["segment"].get("duration")) or 0.0)


def runs(doc: dict, state: dict) -> list[str]:
    """The runs of the encounters in the mode chosen, in their order (``runs``)."""
    seen: list[str] = []
    for s in segments(doc):
        if matches_mode(doc, s, state["mode"]):
            run = js_text(s.get("run_id") or "legacy")
            if run not in seen:
                seen.append(run)
    return seen


def run_line(d: dict) -> str:
    s = d["segment"]
    return (f"Run {js_text(s.get('run_id') or 'legacy')} · "
            f"{'Finished' if _truthy(s.get('run_complete')) else 'Unfinished / completion unverified'} · "
            f"{js_text(s.get('run_end_reason') or '')}")


def segment_choices(doc: dict, state: dict) -> list[tuple[int, str]]:
    """The encounters offered (``data-control="segment"``): those in the mode and run chosen, each by its label."""
    out = []
    for i, s in enumerate(segments(doc)):
        if not matches_mode(doc, s, state["mode"]) or (state["run"] and js_text(s.get("run_id") or "legacy") != state["run"]):
            continue
        words = js_text(s.get("label") or s.get("boss") or f"Combat {i + 1}")
        if isinstance(s.get("continued_in"), int) and not isinstance(s.get("continued_in"), bool):
            words += PIECE_LABELS.get(s.get("fragment"), " (piece of a cut fight)")
        out.append((i, words))
    return out


def first_of_run(doc: dict, state: dict) -> int:
    """The first encounter of the run chosen (``key==='run'``)."""
    for i, s in enumerate(segments(doc)):
        if matches_mode(doc, s, state["mode"]) and (not state["run"] or js_text(s.get("run_id") or "legacy") == state["run"]):
            return i
    return 0


def is_pvp(doc: dict, d: dict) -> bool:
    return mode_of(doc, d["segment"]) == "pvp"


def source_line(doc: dict, d: dict) -> str:
    """Where the encounter's version, zone, difficulty, type and region come from."""
    m, s = _dict(doc.get("meta")), d["segment"]
    parts = []
    if _truthy(m.get("installed_build")):
        parts.append(f"Installed game version: {js_text(m['installed_build'])} ({js_text(m.get('installed_build_source'))}). ")
    if _truthy(s.get("game_patch")) or _truthy(m.get("game_patch")):
        source = s.get("game_patch_source") or m.get("game_patch_source") or "source not recorded"
        parts.append(f"Version source: {build_label(source)}. ")
    if _truthy(s.get("zone")):
        parts.append(f"Zone: {js_text(s['zone'])} · {js_text(s.get('zone_source') or 'source not recorded')}. ")
    if _truthy(s.get("difficulty")):
        parts.append(f"Difficulty: {js_text(s['difficulty'])} · {js_text(s.get('difficulty_source') or 'source not recorded')}. ")
    if _truthy(s.get("encounter_type_source")):
        parts.append(f"Encounter type source: {js_text(s['encounter_type_source'])}. ")
    if _truthy(m.get("region_source")):
        parts.append(f"Region source: {js_text(m['region_source'])}.")
    return "".join(parts).strip()


def _counted(mapping: dict) -> str:
    return ", ".join(f"{js_text(skill)} ×{number(n)}" for skill, n in sorted(mapping.items(), key=lambda kv: -(_num(kv[1]) or 0)))


def unattributed_line(u) -> str:
    """The heals of a PvP fight left out as nobody's (``unattributedHTML``)."""
    if not u:
        return ""
    count = _num(u.get("count")) or 0
    return (f"Left out of everyone's healing: {number(count)} heal record{'' if count == 1 else 's'} between the two sides, "
            f"{number(u.get('amount'))} as recorded ({_counted(u.get('skills') or {})}). They are shields' absorbs, which a "
            "meter before 0.2.399 recorded as heals by the attacker, of what was left of the shield. The log does not name "
            "the shields' casters, so they count for no one.")


def rebuilt_line(h) -> str:
    """An older log's heals over time, rebuilt (``rebuiltHTML``)."""
    h = _dict(h)
    if not _truthy(h.get("records")):
        return ""
    count = _num(h.get("records")) or 0
    skills = _dict(h.get("skills"))
    return (f"Heals over time rebuilt: {number(count)} heal record{'' if count == 1 else 's'}"
            + (f" ({_counted(skills)})" if skills else "")
            + f", {number(h.get('amount'))} as recorded, now {number(h.get('rebuilt'))}. A meter before 0.2.399 recorded a heal "
            "over time whole when it was cast and then, at each tick, what was left of it; each record now heals what the ticks "
            "since the one before took.")


def arena(d: dict) -> dict | None:
    """An arena match from the game's own records (``arenaHTML``): the result and rating, the fighters and the rounds."""
    a = _dict(d["segment"].get("arena"))
    fighters = [f for f in _list(a.get("fighters")) if isinstance(f, dict)]
    if not fighters:
        return None
    rounds = [x for x in _list(a.get("rounds")) if isinstance(x, dict)]
    me = next((f for f in fighters if _truthy(f.get("self"))), None)

    def rate(x):
        return str(theme.js_round(x))
    if _truthy(a.get("result")):
        result = "Win" if a.get("result") == "win" else "Loss"
        if all(isinstance(a.get(k), int) and not isinstance(a.get(k), bool) for k in ("rounds_won", "rounds_lost")):
            result += f" {a['rounds_won']}–{a['rounds_lost']}"
    else:
        result = "Result not in this encounter"
    rating = ""
    now = _num(a.get("rating"))
    if now is not None:
        before = _num(_dict(me).get("rating"))
        rating = (f" · Rating {rate(before)} → {rate(now)} ({'+' if now >= before else '−'}{rate(abs(now - before))})"
                  if before is not None else f" · Rating {rate(now)}")
    factions = {"elyos": "Elyos", "asmodian": "Asmodian"}

    def who(i):
        f = fighters[i] if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(fighters) else None
        if f is None:
            return {"name": "Unknown", "class": "", "actor": None}
        actor = d["r"].get(f.get("ref")) if _truthy(f.get("ref")) else None
        return {"name": js_text(f.get("name") or "Unknown"), "class": js_text(f.get("class") or ""), "actor": actor}
    return {"title": f"Arena match · {result}{rating}",
            "fighters": [{**who(i), "self": _truthy(f.get("self")), "server": world(f.get("server")),
                          "faction": factions.get(f.get("faction"), ""),
                          "rating": rate(_num(f.get("rating"))) if _num(f.get("rating")) is not None else "—",
                          "won": str(sum(1 for x in rounds if x.get("winner") == i))} for i, f in enumerate(fighters)],
            "rounds": [{"round": js_text(x.get("round")) if isinstance(x.get("round"), int) else "", "at": clock(x.get("t"), True),
                        "winner": who(x.get("winner")), "loser": who(x.get("loser"))} for x in rounds]}


def opponent(d: dict) -> dict:
    """A PvP opponent chosen under Player (``opponentHTML``): whom they struck and who struck them, and what the
    recording holds of them."""
    foe, seg = d["foe"], d["segment"]
    ours, owner = d["ours"], d["owner"]
    dealt: dict = {}
    taken: dict = {}
    for x in d["events"]:
        if x.get("kind") != "damage":
            continue
        if ours(x.get("source")) and not ours(x.get("target")):
            into, who = dealt, x.get("target")
        elif ours(x.get("target")) and not ours(x.get("source")):
            into, who = taken, x.get("source")
        else:
            continue
        key = owner(who) or ""
        g = into.setdefault(key, {"id": key, "amount": 0.0, "hits": 0, "max": 0.0})
        g["amount"] += _amount(x)
        g["hits"] += 1
        g["max"] = max(g["max"], _amount(x))

    def lines(groups, per):
        rows = sorted(groups.values(), key=lambda g: -g["amount"])
        total = sum(g["amount"] for g in rows)
        return [{"actor": d["r"].get(g["id"]), "id": g["id"], "amount": number(g["amount"]),
                 "share": (theme.fixed(100 * g["amount"] / total, 1) if total else "0") + "%", "hits": number(g["hits"]),
                 "max": number(g["max"]), "rate": number(g["amount"] / per)} for g in rows]

    def count(items, test):
        return sum(1 for x in _list(items) if isinstance(x, dict) and test(x))
    deaths = count(d["events"], lambda x: x.get("kind") == "death" and x.get("target") == foe)
    kinds = [(count(d["events"], lambda x: x.get("kind") == "damage" and ours(x.get("source"))), "hit of theirs",
              "hits of theirs", "their hits"),
             (count(d["events"], lambda x: x.get("kind") == "damage" and ours(x.get("target")) and not ours(x.get("source"))),
              "hit on them", "hits on them", "hits on them"),
             (count(d["events"], lambda x: x.get("kind") == "heal" and ours(x.get("source"))), "heal", "heals", "their healing"),
             (count(seg.get("casts"), lambda c: c.get("source") == foe), "cast", "casts",
              "their casts (recorded by the live meter since 0.2.398)"),
             (count(seg.get("effects"), lambda x: ours(x.get("target")) or (_truthy(x.get("source")) and ours(x.get("source")))),
              "buff or debuff record", "buff and debuff records", "buffs and debuffs on or from them"),
             (count(seg.get("health"), lambda s: s.get("entity") == foe), "HP reading", "HP readings", "their HP"),
             (count(seg.get("movement"), lambda m: m.get("entity") == foe), "position", "positions", "their positions")]
    held = [f"{number(n)} {one if n == 1 else many}" for n, one, many, _missing in kinds if n]
    if deaths:
        held.append(f"{number(deaths)} death marker{'' if deaths == 1 else 's'}")
    missing = [words for n, _one, _many, words in kinds if not n]
    e = d["r"].get(foe) or {"id": foe}
    recorded = f"Recorded: {', '.join(held) or 'nothing of theirs'}." + (f" Not recorded: {', '.join(missing)}." if missing else "")
    return {"actor": e, "class": js_text(e.get("class") or ""), "recorded": recorded,
            "dealt": lines(dealt, d["dps_duration"]), "taken": lines(taken, max(1.0, _num(seg.get("duration")) or 0.0))}


# ------------------------------------------------------------------ the summary and its parses
def summary_note(d: dict, v: dict, foe: str, parse_column: bool) -> str:
    if foe:
        words = (f"An opponent's figures are the recording's records of them: their hits and heals, the hits on them and their "
                 f"death markers. DPS uses their own active damage time ({fixed(v['dps_duration'], 0)}s): one-second buckets "
                 "with damage of theirs; empty buckets are excluded. Graph rates use elapsed encounter time.")
    else:
        words = (f"DPS uses shared active damage time ({fixed(d['dps_duration'], 0)}s): one-second buckets with outgoing "
                 "player damage. Empty buckets are excluded; DPS holds while idle and resumes on the same totals. Deaths do not "
                 "reset players. Graph rates use elapsed encounter time.")
    return words + (PARSE_NOTE if parse_column else "")


def summary_columns(parse_column: bool) -> list[str]:
    return SUMMARY_COLUMNS[:1] + (["Parse"] if parse_column else []) + SUMMARY_COLUMNS[1:]


def summary_rows(d: dict, v: dict, state: dict) -> list[dict]:
    """The players' totals (``summary``), the one chosen alone when a player is chosen, by the metric shown."""
    metric = "damage" if state["metric"] == "summary" else state["metric"]
    foe = v["foe"]
    rows = [p for p in v["rows"] if not state["actor"] or p.get("id") == state["actor"]]
    rows.sort(key=lambda p: -(_num(p.get(metric)) or 0.0))
    total = duration(d)

    def held(p, count, words, none="Not recorded"):
        return none if foe and not p.get(count) else words
    out = []
    for p in rows:
        deaths = ("No markers" if not p.get("deaths") else
                  f"{p['deaths']}" + (f" (revived {p['revives']})" if p.get("revives") else ""))
        out.append({"id": p.get("id"), "actor": p, "class": js_text(p.get("class") or "Unknown"),
                    "damage": held(p, "hits", number(p["damage"])),
                    "dps": held(p, "hits", number(p["damage"] / v["dps_duration"]), "—"),
                    "taken": held(p, "struck", number(p["taken"])), "healing": held(p, "heals", number(p["healing"])),
                    "hps": held(p, "heals", number(p["healing"] / total), "—"), "deaths": deaths,
                    "revives": p.get("revives") or 0, "deaths_count": p.get("deaths") or 0})
    return out


def parse_badge(ranks, actor_id, cls) -> dict:
    """A player's parse (``parseHTML``): "·" while the rankings are read or without a comparable parse, else its
    rounded value in its tier's colour, provisional under five runs, with its words on hover."""
    if ranks is None:
        return {"text": "·", "tier": "none", "provisional": False, "tip": "Loading the community parse…"}
    ranks = _dict(ranks)
    players = [p for p in _list(ranks.get("players")) if isinstance(p, dict)]
    entry = next((p for p in players if p.get("id") == actor_id), None)
    if entry is None or entry.get("parse") is None or _num(entry.get("parse")) is None:
        tip = (js_text(ranks["error"]) if _truthy(ranks.get("error")) else
               "No comparable public parses for this class on this encounter yet" if players else
               js_text(ranks.get("note")) if _truthy(ranks.get("note")) else "Unranked encounter")
        return {"text": "·", "tier": "none", "provisional": False, "tip": tip}
    runs_count = entry.get("parse_runs") if entry.get("parse_runs") is not None else entry.get("parse_characters")
    runs_count = _num(runs_count) or 0
    few, rank = runs_count < 5, entry.get("parse_rank")
    tip = (f"Parse {js_text(entry['parse'])}{f' · rank {js_text(rank)} of' if _truthy(rank) else ' among'} {js_text(runs_count)} "
           f"ranked {js_text(cls or '')} run{'' if runs_count == 1 else 's'} on this encounter"
           + (" (provisional: fewer than 5 runs; small brackets read toward the middle)" if few else ""))
    return {"text": str(theme.js_round(_num(entry["parse"]))), "tier": parse_tier(entry["parse"], rank), "provisional": few,
            "tip": tip}


# ------------------------------------------------------------------ the capture's quality and the runs
def quality(ranks, d: dict) -> dict:
    """The capture's quality (``qualityHTML``): eligible for rankings or not, its messages and note, the capture driver's
    and processing's counts."""
    q = _dict(_dict(ranks).get("quality")) or _dict(d["segment"].get("quality"))
    summary = "Capture quality · " + ("Eligible for community rankings" if _truthy(q.get("eligible"))
                                      else "Unranked / completeness unverified")
    if not q:
        return {"summary": summary, "messages": [], "note": OLD_QUALITY, "driver": "", "processing": ""}
    driver = _dict(q.get("driver_monitoring"))
    driver_line = ""
    if driver:
        if _truthy(driver.get("sampled")):
            body = ((("partial coverage · " if _truthy(driver.get("partial")) else "")
                     + f"{number(driver.get('pcap_received'))} received · {number(driver.get('pcap_dropped'))} capture-buffer "
                     f"drops · {number(driver.get('pcap_if_dropped'))} interface/driver drops"))
        else:
            body = "unavailable / not recorded"
        driver_line = f"Capture driver: {body}. {js_text(driver.get('note') or '')}".strip()
    processing = _dict(q.get("capture_processing"))
    processing_line = ""
    if processing:
        def held(key):
            return "not recorded" if processing.get(key) is None else number(processing.get(key))
        processing_line = (f"Capture processing: {held('decoder_errors')} decoder failures · {held('recovered_frame_skips')} "
                           "recovered frame-skips (skipped and continued; a few do not affect ranking) · "
                           f"{held('shutdown_discarded_payloads')} payloads discarded at shutdown · "
                           f"{held('shutdown_drained_payloads')} payloads decoded during shutdown. Legacy combined error/discard "
                           f"count: {held('capture_errors')} (overlaps these counters; do not add them). Successfully drained "
                           "payloads are retained data, not capture loss.")
    return {"summary": summary, "messages": [js_text(x) for x in _list(q.get("messages"))], "note": js_text(q.get("note") or ""),
            "driver": driver_line, "processing": processing_line}


def stitched(ranks, d: dict, doc: dict) -> list[dict]:
    """How this fight was cut and joined (``stitchedHTML``): words, and the log or encounter that opens the rest."""
    ranks = _dict(ranks)
    out = []
    s, c = _dict(ranks.get("stitched")), _dict(ranks.get("continued_in"))

    def parts_label(p):
        p = _list(p)
        return f"{js_text(p[0])}–{js_text(p[-1])}" if p else ""
    if s:
        merged = _dict(s.get("merged"))
        if merged:
            first = seconds(max(0.0, (_num(merged.get("duration")) or 0.0) - (_num(d["segment"].get("duration")) or 0.0)))
            out.append({"words": f"This fight was cut by a storage rollover: its first {first} are in the previous recording part. "
                                 f"Rankings use the whole fight — {seconds(merged.get('duration'))}, {number(merged.get('damage'))} "
                                 f"damage. {js_text(s.get('note') or '')}".strip(),
                        "log": _dict(merged.get("previous")).get("log"), "action": "Open previous part"})
        else:
            out.append({"words": f"Part of a run stitched across recording parts {parts_label(s.get('parts'))}: the instance entry "
                                 "was observed in the first part, so this part's fights can rank. "
                                 f"{js_text(s.get('note') or '')}".strip(), "log": None, "action": ""})
    if c:
        out.append({"words": "This fight was cut by a storage rollover and continues in the next part of the recording"
                             + (f" (part {js_text(c['part'])})" if _truthy(c.get("part")) else "")
                             + ", where the whole fight is indexed and ranked.",
                    "log": c.get("log"), "action": "Open the whole fight"})
    whole = d["segment"].get("continued_in")
    all_segments = segments(doc)
    if isinstance(whole, int) and not isinstance(whole, bool) and 0 <= whole < len(all_segments):
        fragment = d["segment"].get("fragment")
        if fragment == "after_kill":
            out.append({"words": "What the fight's dead struck after it was won (no party damage): kept with the fight, not an "
                                 "encounter of its own.", "segment": whole, "action": "Open the fight"})
        elif fragment == "opening_blow":
            out.append({"words": "The boss's opening blow, struck just before the party's first hit: it belongs to the fight, "
                                 "where it is ranked.", "segment": whole, "action": "Open the fight"})
        else:
            out.append({"words": "The meter cut this boss fight in two. This is one piece of it; the whole fight is its own "
                                 "encounter, where it is ranked.", "segment": whole, "action": "Open the whole fight"})
    return out


def pieces(doc: dict, state: dict) -> list[int]:
    """The pieces a joined fight was made from, still listed on their own (``cut``)."""
    return [i for i, s in enumerate(segments(doc)) if s.get("continued_in") == state["segment"] and not _truthy(s.get("fragment"))]


def _miniboss(key) -> bool:
    return re.sub(r"^npc:", "", js_text(key or "")) in MINIBOSS_CODES


def run_tables(doc: dict, d: dict, state: dict, ranks) -> dict:
    """Run timing and boss progression (``runsHTML``)."""
    analysis = _dict(doc.get("run_analysis"))
    detail = _dict(ranks).get("run_detail")
    every = [x for x in _list(analysis.get("runs") or ([detail] if _truthy(detail) else [])) if isinstance(x, dict)]
    if not every:
        return {"kind": "none", "note": NO_RUNS}
    shown = [x for x in every if not state["run"] or x.get("id") == state["run"]]
    current = next((x for x in every if x.get("id") == (d["segment"].get("run_id") or "legacy")), None)
    if is_pvp(doc, d):
        note = ("These intervals contain observed combat effects."
                + (" The arena match above holds the rounds and the result, from the game's own records."
                   if _truthy(d["segment"].get("arena")) else
                   " They are not verified rounds or complete matches. Match score, round boundaries and player death "
                   "coverage remain unverified."))
        return {"kind": "pvp", "title": "PvP recorded timing", "note": note,
                "columns": ["Run", "Recorded span", "Recorded combat", "Gaps / downtime"],
                "rows": [[js_text(x.get("id")), seconds(x.get("recorded_span_seconds")), seconds(x.get("combat_seconds")),
                          seconds(x.get("downtime_seconds"))] for x in shown]}

    def status(x):
        if _truthy(x.get("speed_eligible")):
            words = "Eligible"
        else:
            words = " ".join(js_text(w) for w in _list(x.get("speed_reasons")))
        parts = _list(_dict(x.get("stitched")).get("parts"))
        if parts:
            words += f" (stitched across recording parts {js_text(parts[0])}–{js_text(parts[-1])})"
        return words
    out = {"kind": "pve", "title": "Run timing and boss progression", "note": js_text(analysis.get("note") or ""),
           "columns": ["Run", "Recorded span", "Entry → finish", "Recorded combat", "Gaps / downtime", "Speed status"],
           "rows": [[js_text(x.get("id")), seconds(x.get("recorded_span_seconds")), seconds(x.get("elapsed_seconds")),
                     seconds(x.get("combat_seconds")), seconds(x.get("downtime_seconds")), status(x)] for x in shown],
           "progression": None}
    progression = [p for p in _list(_dict(current).get("progression")) if isinstance(p, dict) and not _miniboss(p.get("boss_key"))]
    attempts = [a for a in _list(_dict(current).get("attempts")) if isinstance(a, dict) and not _miniboss(a.get("boss_key"))]

    def hp(x):
        value = _num(x)
        return "Unavailable" if x is None or value is None else theme.fixed(value, 1) + "%"
    if current is not None and progression:
        out["progression"] = {
            "title": f"Run {js_text(current.get('id'))} · boss attempts",
            "columns": ["Boss", "Recorded attempts", "Kills", "Observed wipes", "Unknown", "Attempts to first recorded clear",
                        "Best observed wipe HP", "Wipe → next pull"],
            "rows": [[js_text(p.get("boss")), js_text(p.get("attempts")), js_text(p.get("kills")), js_text(p.get("wipes")),
                      js_text(p.get("unknown")), "Unavailable" if p.get("attempts_to_first_clear") is None
                      else js_text(p["attempts_to_first_clear"]), hp(p.get("best_wipe_hp_pct")),
                      ", ".join(seconds(x) for x in _list(p.get("wipe_recovery_seconds"))) or "Unavailable"] for p in progression],
            "attempts_columns": ["Attempt", "Boss", "Outcome", "Recorded span", "Lowest observed HP", "Encounters"],
            "attempts": [[js_text(a.get("attempt")), js_text(a.get("boss")), js_text(a.get("outcome")),
                          seconds(a.get("recorded_seconds")), hp(a.get("best_remaining_hp_pct")),
                          ", ".join(js_text(x) for x in _list(a.get("segments")))] for a in attempts]}
    return out


# ------------------------------------------------------------------ the pages
def local_page(file: str, mode: str = "", segment=None) -> str:
    """A recorded log's page (``#/combat-log/local/<file>?mode=``)."""
    page = f"combat-log/local/{encode_component(file)}?mode={encode_component(mode or '')}"
    return page + (f"&segment={segment}" if isinstance(segment, int) and not isinstance(segment, bool) else "")


def read_page(page: str) -> dict | None:
    """A log page's address read (``pageCombatLog``): its kind (local or shared), its file or ID, the mode and the
    encounter it opens on; None for any other page."""
    match = re.fullmatch(r"combat-log/(local|shared)/([^?#]+)(?:\?([^#]*))?", page or "")
    if match is None:
        return None
    query = urllib.parse.parse_qs(match.group(3) or "")
    segment = (query.get("segment") or [""])[0]
    return {"kind": match.group(1), "value": urllib.parse.unquote(match.group(2)), "mode": (query.get("mode") or [""])[0],
            "segment": int(segment) if re.fullmatch(r"\d{1,6}", segment) else None}


def log_path(kind: str, value: str) -> tuple[str, bool]:
    """The question a log's page asks first: the app's recording, or the log server's raw log through the proxy."""
    if kind == "local":
        return "/api/sessions?file=" + encode_component(value), False
    return f"/api/v1/logs/{encode_component(value)}/raw", True


def rankings_question(kind: str, value: str, segment: int, doc: dict) -> tuple[str, dict | None]:
    """The rankings' question (``options.rankings``): a shared log's by its ID, a recorded one sent whole."""
    if kind == "shared":
        return f"/api/v1/logs/{encode_component(value)}/rankings?segment={segment}", None
    return "/api/v1/rankings", {"segment": segment, "log": doc}


def reconstructed(doc: dict) -> bool:
    """A combined review of several parts, which ranks nothing (``mount``'s first line)."""
    m = _dict(doc.get("meta"))
    return _truthy(m.get("reconstruction")) or _truthy(_dict(m.get("capture_quality")).get("reconstructed"))


# ------------------------------------------------------------------ the graph, the ping, the bosses and the enemies (0.2.458)
OPTIONS = (("graph", "Graph"), ("timeline", "Timeline"), ("skills", "Skills"), ("deaths", "Deaths"), ("heals", "Healing"),
           ("pets", "Pets"), ("combine", "Combine pets with owner"))
GRAPH_MODES = (("total", "Live style · bars + 10 s average"), ("players", "Player series"))
GRAPH_HINT = "Hover or click the graph for rates. In Timeline view, click a time to move the timeline window there."
KINDS = ("Damage done", "Healing", "Damage taken")
NO_PING = "Recorder ping: not recorded for this encounter."
HP_NOTE = "HP is observed, not inferred from damage. A last positive sample does not establish the final outcome."
ENEMY_COLUMNS = ["Enemy", "Creature type", "Damage received", "Observed lifespan"]
UNNAMED_NOTE = ("Unnamed summon and Unnamed NPC are entities the game data gives no name, labelled by their kind: mostly what a "
                "boss summons for its attacks. Each row counts every one of that name.")
ALL_ENEMIES = "All enemies"
_UNNAMED = re.compile(r"^(Unnamed (summon|NPC)|\?\?\?)$")


def is_boss(e) -> bool:
    """A boss the review marks (``bossEntity``): never a mini-boss the catalog once took for one."""
    e = _dict(e)
    return _truthy(e.get("is_boss")) and js_text(e.get("mob_code")) not in MINIBOSS_CODES


def npc_name(e, names: dict | None = None) -> str:
    """An NPC's name (``npcName``): the catalog's, else the community's for a code the catalog names "#<code>"."""
    e = _dict(e)
    name = js_text(e["name"]) if e.get("name") not in (None, "") else js_text(e.get("id") if e.get("id") is not None else "")
    if e.get("mob_code") is not None and re.fullmatch(r"#\d+", name) and names:
        found = names.get(js_text(e["mob_code"]))
        if found:
            return js_text(found)
    return name


def community_names(answer) -> dict:
    """The community's NPC names by code (``A2CommunityNames``, npc-portraits.js), from the log server's map."""
    answer = _dict(answer)
    rows = answer.get("portraits") if isinstance(answer.get("portraits"), dict) else answer
    return {js_text(code): row["name"] for code, row in _dict(rows).items()
            if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"]}


def enemy_ids(state: dict) -> set:
    return set(filter(None, js_text(state.get("enemy") or "").split(",")))


def visible_events(d: dict, state: dict) -> list[dict]:
    """The events the review shows (``visibleEvents``): a player's, the enemies chosen, pets or not, the metric's."""
    owner, ours, r, enemies = d["owner"], d["ours"], d["r"], enemy_ids(state)
    metric = state["metric"]
    out = []
    for e in d["events"]:
        kind, source, target = e.get("kind"), e.get("source"), e.get("target")
        if state["actor"] and owner(source) != state["actor"] and owner(target) != state["actor"]:
            continue
        if state.get("enemy") and not d["foe"] and kind == "damage" and target not in enemies and source not in enemies:
            continue
        if not state.get("pets", True) and (_truthy(_dict(r.get(source)).get("owner")) or _truthy(_dict(r.get(target)).get("owner"))):
            continue
        if not (metric == "summary" or (metric == "damage" and kind == "damage" and ours(source))
                or (metric == "taken" and kind == "damage" and ours(target)) or (metric == "healing" and kind == "heal")
                or (metric == "deaths" and kind == "death")):
            continue
        out.append(e)
    return out


def _locale_key(text: str):
    from .combat import locale_key
    return locale_key(text)


def graph(d: dict, events: list[dict], state: dict, hidden: set) -> dict:
    """The rate chart (``graph``): each player's damage done, healing and damage taken a second in buckets of a second
    or more, the metric's total with its trailing ten-second average, and the bosses' HP (an opponent's own, or the
    enemies chosen)."""
    duration = max(_num(d["segment"].get("duration")) or 0.0, 1.0)
    step = max(1, math.ceil(duration / 1200))
    count = math.ceil(duration / step)
    metric = state["metric"]
    primary = "Healing" if metric == "healing" else "Damage taken" if metric == "taken" else "Damage done"
    owner, ours = d["owner"], d["ours"]
    series: dict = {}
    for e in events:
        kind = e.get("kind")
        if kind == "death":
            continue
        if kind == "heal":
            actor, line_kind = owner(e.get("source")), "Healing"
        elif ours(e.get("source")):
            actor, line_kind = owner(e.get("source")), "Damage done"
        elif ours(e.get("target")):
            actor, line_kind = owner(e.get("target")), "Damage taken"
        else:
            continue
        key = f"{js_text(actor)}:{line_kind}"
        if key in hidden:
            continue
        line = series.setdefault(key, {"key": key, "actor": actor, "kind": line_kind, "values": [0.0] * count})
        i = max(0, min(count - 1, math.floor((_num(e.get("t")) or 0.0) / step)))
        line["values"][i] += _amount(e) / max(0.001, min(step, duration - i * step))
    r = d["r"]
    lines = sorted(series.values(), key=lambda s: (_locale_key(actor_label(r.get(s["actor"]))), js_text(s["actor"]),
                                                  KINDS.index(s["kind"])))
    total = [0.0] * count
    for s in lines:
        if s["kind"] == primary:
            for i, v in enumerate(s["values"]):
                total[i] += v
    roll = []
    for i in range(count):
        amount = spent = 0.0
        j = i
        while j >= 0 and (i - j) * step < 10:
            span = min(step, duration - j * step, 10 - (i - j) * step)
            amount += total[j] * span
            spent += span
            j -= 1
        roll.append(amount / max(0.001, spent))
    maximum = max([1.0] + total + roll)
    if state.get("graph_mode") == "players":
        maximum = max([maximum] + [v for s in lines for v in s["values"]])
    enemies = enemy_ids(state)

    def counts(s):
        if not (0 <= (_num(s.get("t")) if _num(s.get("t")) is not None else -1) <= duration):
            return False
        if d["foe"]:
            return s.get("entity") == d["foe"]
        if state.get("enemy"):
            return s.get("entity") in enemies
        return is_boss(r.get(s.get("entity")))
    health = [s for s in _list(d["segment"].get("health")) if isinstance(s, dict) and counts(s)]
    hp_max = max([1.0] + [(_num(s.get("max")) or _num(s.get("current")) or 0.0) for s in health])
    hp_of = "their HP" if d["foe"] else "boss HP"
    line_words = (f"{primary} per second · {step}s buckets"
                  + (f" · red: {hp_of}, right scale" if health else f" · {'Their' if d['foe'] else 'Boss'} HP: not recorded"))
    return {"duration": duration, "step": step, "count": count, "total": total, "roll": roll, "lines": lines,
            "health": health, "hp_max": hp_max, "hp_of": hp_of, "primary": primary, "maximum": maximum,
            "mode": "players" if state.get("graph_mode") == "players" else "total", "words": line_words}


def graph_detail(model: dict, t: float, r: dict, foe: str) -> dict:
    """The rates at a moment of the graph (``inspect``): the totals, each player's three rates, and each boss's latest HP."""
    t = max(0.0, min(model["duration"], t))
    i = min(model["count"] - 1, math.floor(t / model["step"]))

    def rate(x):
        return "—" if x is None else number(x) + "/s"
    rates: dict = {}
    for s in model["lines"]:
        rates.setdefault(s["actor"], {})[s["kind"]] = s["values"][i]
    head = (f"{clock(t, True)} · Total {model['primary'].lower()}: {rate(model['total'][i])} · 10 s average: "
            f"{rate(model['roll'][i])}")
    rows = [{"actor": actor, "label": actor_label(r.get(actor)), "cells": [rate(row.get(k)) for k in KINDS]}
            for actor, row in rates.items()]
    hp = []
    for entity in dict.fromkeys(s.get("entity") for s in model["health"]):
        samples = sorted((s for s in model["health"] if s.get("entity") == entity and (_num(s.get("t")) or 0.0) <= t),
                         key=lambda s: -(_num(s.get("t")) or 0.0))
        if samples:
            s = samples[0]
            hp.append([actor_label(r.get(entity)), number(s.get("current")),
                       number(s.get("max")) if _truthy(s.get("max")) else "Unavailable", clock(s.get("t"), True)])
    return {"at": t, "head": head, "rows": rows, "hp": hp, "hp_head": ["Opponent" if foe else "Boss", "Remaining HP",
                                                                       "Observed maximum", "Sample time"]}


def latency(d: dict) -> dict | None:
    """The recorder's ping (``latencyHTML``): its samples, average, least and most, the source, and the points drawn;
    None when the encounter recorded none."""
    seg = d["segment"]
    end = _num(seg.get("duration")) or 0.0
    samples = []
    for p in _list(seg.get("ping")):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            continue
        t, ms = _num(p[0]), _num(p[1])
        if t is None or ms is None or isinstance(p[0], bool) or isinstance(p[1], bool):
            continue
        if 0 <= t <= end and 0 <= ms <= 60000:
            samples.append((t, ms))
    if not samples:
        return None
    values = [ms for _t, ms in samples]
    every = max(1, math.ceil(len(samples) / 1500))
    recorder = d["r"].get(seg.get("ping_recorder"))
    return {"title": "Recorder ping" + (f" · {actor_label(recorder)}" if recorder else ""),
            "figures": (f"Average {theme.fixed(sum(values) / len(values), 1)} ms · Minimum {theme.fixed(min(values), 1)} ms · "
                        f"Maximum {theme.fixed(max(values), 1)} ms · {number(len(samples))} samples"),
            "source": ("Passive TCP acknowledgement RTT" if seg.get("ping_source") == "passive_tcp_ack"
                       else "Recorded latency; measurement source unavailable")
                      + ". These samples describe the recording connection, not every party member or game action latency. "
                        "Gaps have no samples; the average weights recorded samples equally.",
            "duration": max(0.001, end), "scale": max(1.0, max(values)),
            "points": [p for i, p in enumerate(samples) if i % every == 0 or i == len(samples) - 1]}


def boss_hp(d: dict, state: dict) -> list[list[str]]:
    """Each boss's latest recorded HP (``bossHPHTML``), the enemies chosen only."""
    seg, enemies = d["segment"], enemy_ids(state)
    end = _num(seg.get("duration")) or 0.0
    rows = []
    for b in _list(seg.get("entities")):
        if not is_boss(b) or (state.get("enemy") and b.get("id") not in enemies):
            continue
        samples = sorted((h for h in _list(seg.get("health")) if isinstance(h, dict) and h.get("entity") == b.get("id")
                          and (_num(h.get("t")) or 0.0) <= end), key=lambda h: -(_num(h.get("t")) or 0.0))
        hp = samples[0] if samples else None
        top, now = (_num(hp.get("max")), _num(hp.get("current"))) if hp else (None, None)
        rows.append([js_text(b.get("name") or b.get("id")), number(now) if hp else "Not recorded",
                     number(top) if hp and top else "Not recorded",
                     theme.fixed(100 * now / top, 1) + "%" if hp and top and now is not None and now <= top else "Unavailable",
                     clock(hp.get("t"), True) if hp else "—"])
    return rows


def enemy_encounters(d: dict, state: dict, names: dict | None = None) -> dict:
    """The enemies (``encounters``): one row per name, a boss's forms and every spawn of an add together, a PvP opponent
    its own; the unnamed summons nobody struck folded away."""
    groups: dict = {}
    of: dict = {}
    for e in _list(d["segment"].get("entities")):
        if not isinstance(e, dict) or e.get("kind") != "enemy":
            continue
        key = f"id:{js_text(e.get('id'))}" if _truthy(e.get("is_player")) else f"name:{npc_name(e, names)}"
        g = groups.setdefault(key, {"entity": e, "ids": [], "codes": [], "boss": False, "damage": 0.0, "struck": 0,
                                    "first": math.inf, "last": -math.inf})
        g["ids"].append(e.get("id"))
        if e.get("mob_code") is not None and e["mob_code"] not in g["codes"]:
            g["codes"].append(e["mob_code"])
        g["boss"] = g["boss"] or is_boss(e)
        of[e.get("id")] = g
    for x in d["events"]:
        t = _num(x.get("t")) or 0.0
        for identifier in (x.get("source"), x.get("target")):
            g = of.get(identifier)
            if g is not None:
                g["first"], g["last"] = min(g["first"], t), max(g["last"], t)
        if x.get("kind") != "damage":
            continue
        hit, by = of.get(x.get("target")), of.get(x.get("source"))
        if hit is not None:
            hit["damage"] += _amount(x)
        if by is not None and hit is None:
            by["struck"] += 1

    def unnamed(g):
        return not _truthy(g["entity"].get("is_player")) and _UNNAMED.match(npc_name(g["entity"], names)) is not None
    ordered = sorted(groups.values(), key=lambda g: (-int(g["boss"]), -g["damage"], g["first"]))
    folded = [g for g in ordered if unnamed(g) and not g["damage"]]
    shown = [g for g in ordered if g not in folded]

    def row(g):
        e = g["entity"]
        return {"ids": ",".join(js_text(i) for i in g["ids"]), "entity": e, "player": _truthy(e.get("is_player")),
                "name": actor_label(e) if _truthy(e.get("is_player")) else npc_name(e, names), "count": len(g["ids"]),
                "code": e.get("mob_code"),
                "filter": "Filter" + (" (opponent)" if _truthy(e.get("is_player")) else " (boss)" if g["boss"] else ""),
                "types": ", ".join(js_text(c) for c in g["codes"]) or "Unknown", "damage": number(g["damage"]),
                "lifespan": (f"{theme.fixed(g['first'], 1)}–{theme.fixed(g['last'], 1)}s" if g["first"] <= g["last"] else "—")}
    hidden = None
    if folded:
        n = sum(len(g["ids"]) for g in folded)
        hits = sum(g["struck"] for g in folded)
        one = n == 1
        summons = all(npc_name(g["entity"], names) == "Unnamed summon" for g in folded)
        noun = ("unnamed summon" if one else "unnamed summons") if summons else ("unnamed entity" if one else "unnamed entities")
        hidden = {"title": f"{number(n)} {noun} the party never struck",
                  "note": (f"The game data gives {'it' if one else 'these'} no name. {'It' if one else 'They'} took no damage"
                           + (f" and struck the party {number(hits)} time{'' if hits == 1 else 's'}" if hits else "")
                           + ": part of the boss's attacks rather than enemies to fight."),
                  "rows": [row(g) for g in folded]}
    return {"rows": [row(g) for g in shown], "named_note": any(unnamed(g) for g in shown), "folded": hidden}


# ------------------------------------------------------------------ the views: the events' list and the timeline (0.2.459)
VIEWS = (("table", "Table"), ("timeline", "Timeline"), ("events", "Events"))
FILTERS = (("kind", "Event"), ("source", "Caster / attacker"), ("target", "Recipient / target"), ("skill", "Ability"))
RANGES = ("t0", "t1", "a0", "a1")
SORTS = (("time", "by time"), ("amount", "by amount, largest first"))
EVENT_COLUMNS = ["Time", "Event", "Caster / attacker", "Recipient / target", "Ability", "Amount"]
NO_MATCH = "No event matches these filters."
PAGE = 100
WINDOWS = (15, 30, 60, 120, 0)
LANE_NOTE = "Display only; graphs, tables and recorded totals are unchanged. Preferences reset when changing encounters."
NO_LANES = "No timeline effects recorded for these filters."
NO_EFFECTS = "No effects in this window"
EFFECT_HINT = "Hover, focus or click a skill icon to inspect its effect."
DEATH, HEALED, TAKEN = "#ef6262", "#58d68d", "#ed9863"
_ABSENT = object()


def _first(*values):
    """``a || b || …``: the first value JavaScript reads as true, else the last."""
    for value in values[:-1]:
        if _truthy(value):
            return value
    return values[-1]


def _joined(value) -> str:
    """A value joined to text (``'' + x``): ``undefined`` for a field the record hasn't."""
    return "undefined" if value is _ABSENT else js_string(value)


def filter_value(key: str, e: dict) -> str:
    """An event's value in a filter's column (``efKeys``)."""
    if key == "kind":
        return _joined(e.get("kind", _ABSENT))
    if key in ("source", "target"):
        return "" if e.get(key) is None else js_string(e.get(key))
    return js_string(_first(e.get("skill"), e.get("skill_id"), "—"))


def fresh_filters(segment: int) -> dict:
    return {"seg": segment, "sel": {}, "t0": "", "t1": "", "a0": "", "a1": "", "sort": "time"}


def filters_of(state: dict) -> dict:
    """The events' filters (``state.ef``): kept while the page shows the encounter, fresh for another."""
    ef = state.get("ef")
    if not isinstance(ef, dict) or ef.get("seg") != state["segment"]:
        ef = state["ef"] = fresh_filters(state["segment"])
    return ef


def bound(x) -> float | None:
    """A range's bound as typed (``efNum``): none for an empty field or one that reads as no number."""
    if x is None or x == "":
        return None
    value = js_number(x)
    return value if math.isfinite(value) else None


def filtered(ef: dict) -> bool:
    """Whether any filter narrows the events: a column's values chosen, or a bound typed."""
    return any(v is not None for v in ef["sel"].values()) or any(bound(ef.get(k)) is not None for k in RANGES)


def passes(ef: dict, e: dict, skip: str = "", values: dict | None = None, bounds: tuple | None = None) -> bool:
    """Whether the filters keep an event (``efPass``); ``skip`` leaves one column's own choice out, for its counts.
    ``values`` (the event's value in each column) and ``bounds`` (the ranges read) can be given worked out already."""
    for key, _name in FILTERS:
        chosen = ef["sel"].get(key)
        if key != skip and chosen is not None and (values[key] if values else filter_value(key, e)) not in chosen:
            return False
    t0, t1, a0, a1 = bounds if bounds is not None else (bound(ef.get(k)) for k in RANGES)
    t = _num(e.get("t"))
    if t is not None and ((t0 is not None and t < t0) or (t1 is not None and t > t1)):
        return False
    if (a0 is not None or a1 is not None) and e.get("kind") == "death":
        return False
    amount = _amount(e)
    return not ((a0 is not None and amount < a0) or (a1 is not None and amount > a1))


def _filter_name(key: str, value: str, raw, r: dict) -> str:
    """A value's name in its column (``efLabel``): an actor's label, or the value itself."""
    if key not in ("source", "target"):
        return value
    if not value:
        return UNKNOWN
    try:
        ref = r.get(raw)                         # the actor by the id as the log holds it (a number or a text)
    except TypeError:
        ref = None
    return actor_label(ref if ref is not None else r.get(value))


def _spread(values: list) -> tuple[str, str]:
    """``Math.min(...)`` and ``Math.max(...)`` of the events' times, to three places."""
    if any(v is None for v in values):
        return "NaN", "NaN"
    return theme.fixed(min(values), 3), theme.fixed(max(values), 3)


def event_list(d: dict, events: list[dict], state: dict) -> dict:
    """The events' list (``eventTable``): the events the filters keep, sorted, a page of a hundred; each column's values
    with their counts among the events the other filters keep; and the kept events' count, total, average, smallest and
    largest, and their span."""
    ef = filters_of(state)
    r = d["r"]
    bounds = tuple(bound(ef.get(k)) for k in RANGES)
    rows = [(e, {key: filter_value(key, e) for key, _name in FILTERS}) for e in events]
    shown = [e for e, values in rows if passes(ef, e, "", values, bounds)]
    if ef.get("sort") == "amount":
        shown.sort(key=lambda e: (-_amount(e), _num(e.get("t")) or 0.0))
    columns = []
    for key, name in FILTERS:
        counts: dict = {}
        raw: dict = {}
        for e, values in rows:
            if passes(ef, e, key, values, bounds):
                value = values[key]
                counts[value] = counts.get(value, 0) + 1
                raw.setdefault(value, e.get(key))
        chosen = ef["sel"].get(key)
        for value in chosen or []:
            counts.setdefault(value, 0)
        values = [{"value": value, "count": n, "name": _filter_name(key, value, raw.get(value), r)}
                  for value, n in counts.items()]
        values.sort(key=lambda o: (-o["count"], _locale_key(o["name"])))
        columns.append({"key": key, "name": name, "values": values, "chosen": chosen,
                        "caption": name + (f" · {len(chosen)} of {len(values)}" if chosen is not None else "")})
    kept = [e for e in shown if e.get("kind") != "death"]
    total = sum(_amount(e) for e in kept)
    narrowed = filtered(ef)
    if shown:
        first, last = _spread([_num(e.get("t")) for e in shown])
        summary = (f"<b>{number(len(shown))}</b>{f' of {number(len(events))}' if narrowed else ''} events · total "
                   f"<b>{number(total)}</b>")
        if kept:
            amounts = [_amount(e) for e in kept]
            summary += (f" · average {number(total / len(kept))} · smallest {number(min(amounts))} · largest "
                        f"{number(max(amounts))}")
        summary += f" · {first}s to {last}s"
    else:
        summary = ""
    pages = max(1, math.ceil(len(shown) / PAGE))
    state["page"] = page = max(0, min(int(state.get("page") or 0), pages - 1))
    lines = [{"time": f"{fixed(e.get('t'), 3)}s", "kind": "" if e.get("kind") is None else js_string(e.get("kind")),
             "source": e.get("source"), "target": e.get("target"),
             "skill": js_string(_first(e.get("skill"), e.get("skill_id"), "—")),
             "amount": "—" if e.get("kind") == "death" else number(e.get("amount"))}
            for e in shown[page * PAGE:(page + 1) * PAGE]]
    return {"columns": columns, "count": len(shown), "summary": summary, "rows": lines, "page": page, "pages": pages,
            "pager": f"{page + 1} / {pages} · {len(shown)} events", "filtered": narrowed,
            "clear": narrowed or ef.get("sort") != "time", "ef": ef}


def skill_icon(skill_id) -> str:
    """A skill's icon on the timeline (``skillSource``): its family's, for a whole number above nought."""
    n = js_number(skill_id)
    if not (math.isfinite(n) and n.is_integer() and 0 < n <= 2 ** 53 - 1):
        return ""
    from .combat_analysis import SKILL_ART
    return SKILL_ART.format(math.floor(n / 10000) * 10000)


def timeline(d: dict, events: list[dict], state: dict, hidden: set, collapsed: set, colours: dict | None = None) -> dict:
    """The recorded effect timeline (``timeline``): a lane per player of the party (or the opponent) in view, each hit,
    heal and death in its window as a marker, three stacks deep, and the window's ruler. A crowded marker no stack has
    room for is left out and counted."""
    from .combat_records import class_colour
    duration = max(_num(d["segment"].get("duration")) or 0.0, 1.0)
    window = js_number(state.get("timeline_window"))
    span = min(duration, window if _truthy(window) else duration)
    start = max(0.0, min(_num(state.get("timeline_start")) or 0.0, duration - span))
    state["timeline_start"] = start
    end = start + span
    width = max(900.0, min(8000.0, span * 32))
    owner, ours, r, metric = d["owner"], d["ours"], d["r"], state["metric"]

    def at(e):
        return _num(e.get("t"))
    shown = [e for e in events if at(e) is not None and at(e) >= start and (at(e) < end or (end == duration and at(e) <= end))]
    ids = list(dict.fromkeys(x for e in events for x in (owner(e.get("source")), owner(e.get("target")))
                             if _truthy(x) and ours(x)))
    omitted = 0
    lanes = []
    for actor in ids:
        if actor in hidden:
            continue
        ref = r.get(actor)
        lane = {"id": actor, "actor": ref, "label": actor_label(ref), "collapsed": actor in collapsed, "marks": []}
        lanes.append(lane)
        if lane["collapsed"]:
            continue
        occupied = [-100.0, -100.0, -100.0]
        for e in shown:
            kind = e.get("kind")
            if kind == "death":
                keep = (state.get("deaths", True) and owner(e.get("target")) == actor
                        and (not state.get("combine", True) or not _truthy(_dict(r.get(e.get("target"))).get("owner"))))
            elif kind == "heal":
                keep = state.get("heals", True) and owner(e.get("source")) == actor
            else:
                keep = state.get("skills", True) and owner(e.get("target") if metric == "taken" else e.get("source")) == actor
            if not keep:
                continue
            x = max(0.0, min(width - 24, (at(e) - start) * width / span))
            row = next((i for i, last in enumerate(occupied) if x >= last + 25), -1)
            death = kind == "death"
            if not death and row < 0:
                omitted += 1
                continue
            if not death:
                occupied[row] = x
            fill = (DEATH if death else HEALED if kind == "heal" else TAKEN if metric == "taken"
                    else class_colour(_dict(ref).get("class"), colours or {}))
            detail = (f"{clock(at(e), True)} · {actor_label(r.get(e.get('source')))} → {actor_label(r.get(e.get('target')))} · "
                      f"{_joined(e['skill'] if _truthy(e.get('skill')) else e.get('kind', _ABSENT))} · {number(e.get('amount'))}")
            tag = _joined(e["skill_id"] if _truthy(e.get("skill_id")) else e.get("kind", _ABSENT))[-3:]
            lane["marks"].append({"x": x, "y": 2 if death else 3 + row * 27, "death": death, "fill": fill, "detail": detail,
                                  "tag": tag, "icon": "" if death else skill_icon(e.get("skill_id"))})
    tick = 1 if span <= 30 else 5 if span <= 120 else math.ceil(span / 120)
    major = tick * 5
    ticks = []
    t = math.ceil(start / tick) * tick
    while t <= end:
        x = (t - start) * width / span
        long = abs(t / major - theme.js_round(t / major)) < 0.001
        ticks.append({"x": x, "long": long, "text": clock(t) if long else "", "at": max(22.0, min(width - 22, x))})
        t += tick
    note = ("Icons are recorded hits/heals, not cast starts or durations. Three stacks separate nearby effects. Green: "
            "healing; red: deaths; orange: damage taken. "
            + (f"{number(omitted)} crowded markers omitted in this window; zoom in or use Events for every effect. " if omitted else "")
            + "Unavailable skill images keep an ID tile.")
    return {"duration": duration, "span": span, "start": start, "end": end, "width": width, "lanes": lanes,
            "players": [{"id": i, "label": actor_label(r.get(i)), "shown": i not in hidden} for i in ids],
            "visibility": f"Player timeline visibility · {len([i for i in ids if i not in hidden])} / {len(ids)} shown",
            "windows": [(v, f"{v} seconds" if v else "Full encounter") for v in WINDOWS], "window": window,
            "latest": max(0.0, duration - span), "earlier": start > 0, "later": end < duration,
            "range": f"{clock(start)}–{clock(end)}", "ticks": ticks, "omitted": omitted, "note": note}


def moved_window(state: dict, duration, direction: int) -> None:
    """The timeline's window an earlier or a later one (``data-time-prev``, ``data-time-next``)."""
    window = js_number(state.get("timeline_window"))
    step = window if _truthy(window) else js_number(duration)
    state["timeline_start"] = (_num(state.get("timeline_start")) or 0.0) + step * direction


def centred_window(state: dict, t: float, duration: float) -> None:
    """The timeline's window around a moment the graph was clicked at, in Timeline view."""
    window = js_number(state.get("timeline_window"))
    state["timeline_start"] = max(0.0, t - (window if _truthy(window) else duration) / 2)


def notes_line(d: dict) -> str:
    """What the encounter's records leave out (the note under the review's views)."""
    events, seg = d["events"], d["segment"]
    return (("Some healing recipients are not carried by their packet variant. "
             if any(e.get("kind") == "heal" and not _truthy(e.get("target")) for e in events) else "")
            + ("No death markers recorded; zero counts do not establish a deathless run. "
               if not any(e.get("kind") == "death" for e in events) else "")
            + ("Movement replay is unavailable: no positions were recorded (recordings made before 0.2.350 have none)."
               if not _list(seg.get("positions")) and not _list(seg.get("movement")) else ""))


# ------------------------------------------------------------------ the abilities and skills (0.2.460)
DETAILS = (("contribution", "Ability contribution"), ("abilities", "Abilities"), ("skills", "Skills"),
           ("casts", "Cast timeline"), ("", "Hide"))
ABILITY_COLUMNS = ["Player / server", "Ability", "Effects", "Amount", "Share", "Per second", "Average", "Minimum", "Maximum"]
SKILL_COLUMNS = ["Player", "Skill", "Casts", "Average gap", "Cooldown", "Cooldown usage", "Cast time", "First → last"]
NO_ABILITIES = "No abilities were recorded for this view."
DEATHS_ABILITIES = "Choose Summary, Damage Done, Damage Taken or Healing above to see each ability."
SKILLS_NOTE = ("Casts are the game's own cast records. Cooldown usage compares the casts made with how many fit between the "
               "first cast and the end of the fight at the cooldown the game sent (cooldown reduction included). It does not "
               "judge priorities or account for mechanics that stop you casting.")
CASTS_NOTE = ("Each skill press across the fight; hover a cast for its time, target and cooldown. The line under a cast is how "
              "long it locked the caster, recorded for the player who made the recording only. Casts before the pull show at "
              "negative times.")
HIDE_PROCS = "Hide procs and passive effects"
NO_FOE_CASTS = ("Their casts are not recorded in this log: the live meter records an opponent's casts since 0.2.398, once the "
                "game has named them. <i>Abilities</i> lists each skill they hit with, and the Timeline view each hit.")
COMBINED_CASTS = ("This combined review leaves out the casts: across these parts they exceed what one review can hold. Open a "
                  "single part to see them.")
NO_PLAYER_CASTS = "No skill casts by the selected player in this encounter."
PROC = "#8a93a6"


def abilities(d: dict, v: dict, events: list[dict], state: dict) -> dict:
    """Each player's abilities by amount (``skillRows``): a row per player, kind and ability with its effects, amount,
    least and most; the metric's: damage done by the party in the Summary, else the events the review shows. ``d`` is
    the encounter's records, ``v`` the view (an opponent's own)."""
    metric, owner = state["metric"], d["owner"]
    rows: dict = {}
    for e in events:
        kind = e.get("kind")
        if kind in ("death", "revive") or (metric == "summary" and (kind != "damage" or not v["ours"](e.get("source")))):
            continue
        actor = owner(e.get("target") if metric == "taken" else e.get("source"))
        skill = _first(e.get("skill_id"), e.get("skill"), None)
        key = (js_string(actor) if actor is not None else "", js_string(kind), js_string(skill) if skill is not None else "")
        row = rows.get(key)
        if row is None:
            row = rows[key] = {"actor": actor, "kind": kind, "skill": js_string(_first(e.get("skill"), e.get("skill_id"), "Unknown")),
                               "amount": 0.0, "hits": 0, "min": math.inf, "max": 0.0}
        amount = _amount(e)
        row["amount"] += amount
        row["hits"] += 1
        row["min"], row["max"] = min(row["min"], amount), max(row["max"], amount)
    ordered = sorted(rows.values(), key=lambda r: -r["amount"])
    return {"rows": ordered, "total": sum(r["amount"] for r in ordered)}


def ability_table(found: dict, v: dict, state: dict, duration: float) -> list[dict]:
    """The abilities' table (``breakdown``): each one's effects, amount, share, rate, average, least and most. A player's
    damage done runs on the active clock (DPS), the rest on the encounter's length."""
    total = found["total"]
    out = []
    for s in found["rows"]:
        per = v["dps_duration"] if s["kind"] == "damage" and state["metric"] != "taken" else duration
        out.append({"actor": s["actor"], "cells": [
            s["skill"] + (" (heal)" if s["kind"] == "heal" else ""), str(s["hits"]), number(s["amount"]),
            (theme.fixed(100 * s["amount"] / total, 1) if total else "0") + "%", number(s["amount"] / per),
            number(s["amount"] / s["hits"]), number(s["min"]), number(s["max"])]})
    return out


def contribution(found: dict, r: dict, state: dict) -> dict:
    """The abilities as bars (``skillChart``): the top twenty rows, each against the largest."""
    rows = found["rows"]
    if not rows:
        return {"note": NO_ABILITIES, "bars": []}
    metric = state["metric"]
    word = "Healing" if metric == "healing" else "Damage taken" if metric == "taken" else "Damage done"
    top = max(1.0, rows[0]["amount"])
    bars = [{"actor": s["actor"], "name": f"{actor_label(r.get(s['actor']))} · {s['skill']}", "value": number(s["amount"]),
             "share": float(theme.fixed(100 * s["amount"] / top, 2))} for s in rows[:20]]
    return {"note": (f"{word} by player and ability, the top 20 rows; <i>Abilities</i> lists every one. Select a player to "
                     "see only theirs."), "bars": bars}


def family(skill_id):
    """A skill's family (``family``): the rank and specialization digits nought; a class's own action (dodge, a weapon
    put on: ``xx00``) whole."""
    n = _num(skill_id)
    if n is None:
        return skill_id
    return n if math.floor(n / 10000) % 100 == 0 else math.floor(n / 10000) * 10000


def signed_clock(t) -> str:
    """A moment, before the pull with a minus (``signedClock``)."""
    value = _num(t) or 0.0
    return ("−" if value < 0 else "") + clock(abs(value), True)


def cooldown_text(ms) -> str:
    value = _num(ms)
    return "—" if ms is None or value is None else theme.fixed(value / 1000, 1 if value < 10000 else 0) + "s"


def percent(x) -> str:
    value = _num(x)
    return "—" if x is None or value is None else theme.fixed(value, 1) + "%"


def presses(casts: list[dict]) -> list[dict]:
    """The presses among cast records (``presses``): one press can send several records of a skill. The ones with the
    skill's cooldown count when it has one, else its aimed ones; a skill with neither is a proc or passive effect.
    Records within a quarter second of the one before are the same press."""
    groups: dict = {}
    for c in casts:
        groups.setdefault((js_string(c.get("source")), js_string(family(c.get("skill_id")))), []).append(c)
    out = []
    for rows in groups.values():
        rows = sorted(rows, key=lambda c: _num(c.get("t")) or 0.0)
        timed = [c for c in rows if _truthy(c.get("cooldown_ms"))]
        aimed = [c for c in rows if _truthy(c.get("target"))]
        kind = "skill" if timed or aimed else "proc"
        pick = timed or aimed or rows
        for i, c in enumerate(pick):
            if i == 0 or (_num(c.get("t")) or 0.0) - (_num(pick[i - 1].get("t")) or 0.0) > 0.25:
                out.append({**c, "kind": kind})
    return sorted(out, key=lambda c: _num(c.get("t")) or 0.0)


def _median(values: list):
    values = sorted(values)
    return values[len(values) >> 1] if values else None


def rotation_of(segment: dict, actor) -> dict:
    """An opponent's casts summarised as the analyzer summarises the party's (``rotationOf``): each skill's presses, the
    cooldown the game sent, how many fit from the first press to the end, the gaps and the cast time."""
    duration = max(0.001, _num(segment.get("duration")) or 0.0)
    groups: dict = {}
    for c in presses([c for c in _list(segment.get("casts")) if isinstance(c, dict) and c.get("source") == actor]):
        groups.setdefault(js_string(family(c.get("skill_id"))), []).append(c)
    skills, dodges = [], []
    casts = procs = 0
    for rows in groups.values():
        times = [_num(c.get("t")) or 0.0 for c in rows]
        gaps = [b - a for a, b in zip(times, times[1:])]
        cooldown = _median([_num(c.get("cooldown_ms")) for c in rows if _truthy(c.get("cooldown_ms"))])
        possible = (math.floor(max(0.0, duration - max(0.0, times[0]) - 0.5) / (cooldown / 1000)) + 1
                    if cooldown is not None and cooldown >= 1000 else None)
        skill = js_string(rows[0]["skill"]) if _truthy(rows[0].get("skill")) else js_string(rows[0].get("skill_id"))
        if rows[0]["kind"] == "skill":
            casts += len(rows)
        else:
            procs += len(rows)
        if skill == "Dodge":
            dodges.append({"source": actor, "count": len(rows)})
        skills.append({"source": actor, "skill_id": rows[0].get("skill_id"), "skill": skill, "kind": rows[0]["kind"],
                       "casts": len(rows), "first": times[0], "last": times[-1],
                       "average_gap": sum(gaps) / len(gaps) if gaps else None, "cooldown_ms": cooldown, "possible": possible,
                       "usage_pct": min(100.0, 100 * len(rows) / possible) if possible else None,
                       "cast_ms": _median([_num(c["cast_ms"]) for c in rows if c.get("cast_ms") is not None
                                           and _num(c["cast_ms"]) is not None])})
    return {"totals": [{"source": actor, "casts": casts, "procs": procs, "per_minute": 60 * casts / duration}] if skills else [],
            "skills": sorted(skills, key=lambda k: -k["casts"]), "chains": [], "dodges": dodges}


def actions_of(doc: dict, state: dict):
    """The actions the analyzer read from the encounter's records (``actionsOf``), or None for an older log."""
    for s in _list(_dict(doc.get("encounter_insights")).get("segments")):
        if isinstance(s, dict) and s.get("segment") == state["segment"]:
            return s.get("actions")
    return None


def casts_missing(doc: dict, d: dict, state: dict) -> str:
    """Why the encounter's casts can't be shown (``castsMissing``), or nothing when they can. Rich text."""
    if _list(_dict(_dict(doc.get("meta")).get("reconstruction")).get("omitted_actions")):
        return COMBINED_CASTS
    casts = _list(d["segment"].get("casts"))
    if d["foe"]:
        return "" if any(isinstance(c, dict) and c.get("source") == d["foe"] for c in casts) else NO_FOE_CASTS
    s = actions_of(doc, state)
    if not _truthy(s) or not casts:
        return ("Skill casts are not recorded for this encounter. The live meter records them since 0.2.306"
                + ("" if _truthy(s) else "; reopen the file with the updated app, or update the sharing server, to see them")
                + ".")
    return ""


def rotation_for(doc: dict, d: dict, state: dict) -> dict:
    """The casts behind the Skills table and the cast timeline (``rotationFor``): an opponent's summarised here, the
    party's as the analyzer summarised them."""
    if d["foe"]:
        return rotation_of(d["segment"], d["foe"])
    return _dict(_dict(actions_of(doc, state)).get("rotation"))


def skill_rows(doc: dict, d: dict, state: dict) -> list[dict]:
    """The Skills table's rows (``skillsHTML``): the player chosen's, the procs left out while they are hidden."""
    out = []
    for k in _list(rotation_for(doc, d, state).get("skills")):
        if not isinstance(k, dict) or (state["actor"] and k.get("source") != state["actor"]):
            continue
        if state.get("hide_procs", True) and k.get("kind") != "skill":
            continue
        possible = k.get("possible")
        out.append({"source": k.get("source"), "skill_id": k.get("skill_id"),
                    "skill": js_string(_first(k.get("skill"), k.get("skill_id"), "Unknown skill")), "proc": k.get("kind") == "proc",
                    "cells": [number(k.get("casts")),
                              "—" if k.get("average_gap") is None else theme.fixed(_num(k["average_gap"]) or 0.0, 1) + "s",
                              cooldown_text(k.get("cooldown_ms")),
                              f"{number(k.get('casts'))} of {number(possible)} · {percent(k.get('usage_pct'))}" if _truthy(possible) else "—",
                              "—" if k.get("cast_ms") is None else number(k["cast_ms"]) + " ms",
                              f"{signed_clock(k.get('first'))} → {signed_clock(k.get('last'))}"]})
    return out


def cast_timeline(doc: dict, d: dict, state: dict, colours: dict | None = None) -> dict | None:
    """Every press over the fight (``castTimeline``): a lane per player (or the opponent), three stacks deep, each press
    its skill's tile with the line of its cast time under it; None when no one in view cast."""
    from .combat_records import class_colour
    seg, r = d["segment"], d["r"]
    players = {d["foe"]} if d["foe"] else {_dict(p).get("id") for p in _list(doc.get("players"))}
    actor = state["actor"]
    shown = [c for c in presses([c for c in _list(seg.get("casts")) if isinstance(c, dict) and c.get("source") in players
                                 and (not actor or c.get("source") == actor)])
             if not state.get("hide_procs", True) or c["kind"] == "skill"]
    ids = [i for i in dict.fromkeys(_dict(t).get("source") for t in _list(rotation_for(doc, d, state).get("totals")))
           if not actor or i == actor]
    if not ids:
        return None
    times = [_num(c.get("t")) or 0.0 for c in shown]
    start = min([0.0] + times)
    end = max([_num(seg.get("duration")) or 0.0] + times)
    span = max(1.0, end - start)
    width = theme.js_round(max(900.0, min(24000.0, span * 36)))

    def x(t):
        return (t - start) * (width - 20) / span
    lanes = []
    for who in ids:
        occupied = [-100.0, -100.0, -100.0]
        marks, omitted = [], 0
        colour = class_colour(_dict(r.get(who)).get("class"), colours or {})
        for c in shown:
            if c.get("source") != who:
                continue
            left = x(_num(c.get("t")) or 0.0)
            row = next((i for i, last in enumerate(occupied) if left >= last + 17), -1)
            if row < 0:
                omitted += 1
                continue
            occupied[row] = left
            proc = c["kind"] == "proc"
            parts = [signed_clock(c.get("t")), _first(c.get("skill"), c.get("skill_id"), ""),
                     ("→ " + actor_label(r.get(c.get("target")))) if _truthy(c.get("target")) else "",
                     ("cooldown " + cooldown_text(c.get("cooldown_ms"))) if _truthy(c.get("cooldown_ms")) else "",
                     f"cast {js_string(c['cast_ms'])} ms" if c.get("cast_ms") is not None else "",
                     "proc or passive" if proc else ""]
            cast = (max(2.0, (_num(c["cast_ms"]) or 0.0) / 1000 * (width - 20) / span)
                    if c.get("cast_ms") is not None else None)
            marks.append({"x": left, "y": 4 + row * 19, "cast": cast, "fill": PROC if proc else colour, "style": "cast",
                          "detail": " · ".join(js_string(p) for p in parts if _truthy(p)), "icon": skill_icon(c.get("skill_id"))})
        lanes.append({"id": who, "actor": r.get(who), "label": actor_label(r.get(who)), "collapsed": False, "marks": marks,
                      "omitted": omitted})
    tick = 5 if span <= 120 else 10 if span <= 600 else 30
    ticks = []
    t = math.ceil(start / tick) * tick
    while t <= end:
        px = x(t)
        ticks.append({"x": px, "top": 18, "text": re.sub(r"\.\d+$", "", signed_clock(t)), "at": max(18.0, min(width - 18.0, px))})
        t += tick
    return {"width": float(width), "lanes": lanes, "ticks": ticks, "ruler": 33, "lane": 65, "bottom": 30, "corner": "",
            "empty": "No casts recorded"}
