"""The log review's words (0.2.457), as combat-review.js reads a combat log (an a2log document). A log is a recorded
session saved on this computer (``#/combat-log/local/<file>``) or one shared on the log server
(``#/combat-log/shared/<id>``).

These are the review's model and the frame's words:
- each encounter's roster (``segmentRefs``): its players and entities, their pets' owners, labels and profiles;
- its events and its players' totals (``data``): damage done and taken, healing, deaths and revives, and the DPS's
  active clock. A PvP opponent can be read from their own side;
- the summary table and its parses (``parseHTML``), and the notes around it: the PvP and arena match notes, an
  opponent's records, the heals left out or rebuilt, the sources, the capture quality and the run timing.
"""
from __future__ import annotations

import math
import re
import urllib.parse

from .account import parse_tier
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
ELSEWHERE = ("The graph, timeline, events, abilities and skills, actions, death recaps, insights, rankings, reports, "
             "comparisons and movement replay of this log open in the web interface for now.")
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
            "metric": "summary", "view": "table", "combine": True, "pets": True, "actor": "", "enemy": ""}


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
