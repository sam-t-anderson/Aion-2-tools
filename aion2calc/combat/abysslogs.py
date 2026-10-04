"""AbyssLogs (abysslogs.com) fights -> canonical encounters.

AbyssLogs is a free AION 2 DPS meter: it captures the fight on the player's PC
and uploads it to abysslogs.com, where each fight gets a share link
(``https://abysslogs.com/e/<id>``, optionally ``?seg=<segment id>``). The site
reads its data from a public JSON API, used here the same way the site does:

    GET api.abysslogs.com/v1/encounters/<id>                       the fight and its segments
    GET api.abysslogs.com/v1/encounters/<id>/segments/<seg>/url    a short-lived link to the
                                                                   segment file (.json.gz)

A segment is one pull (a boss or a trash pack). It holds every player's totals
and, for boss pulls, a hit-by-hit timeline with crit / double / perfect /
multi-hit flags, the buffs that were up, and each skill's chosen
specializations, which the official character page does not show.

Uploading goes the other way and only through the AbyssLogs meter: the site has
no file upload, and its leaderboards rely on every fight having been recorded
by that meter.
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.parse

from ..kit.base import ClassData
from ..scrape.http import UA, _get, _throttle, fetch_json
from ..sources.official import CLASS_KEYS

API = "https://api.abysslogs.com/v1"
SITE = "https://abysslogs.com"
_HEADERS = {"Accept-Language": "en"}
_ID = re.compile(r"abysslogs\.com/e/([A-Za-z0-9_-]+)")


def is_ref(ref: str) -> bool:
    return bool(_ID.search(ref or ""))


def parse_ref(ref: str) -> tuple[str, str | None]:
    """``(encounter id, segment id or None)`` from a share link or a bare id."""
    m = _ID.search(ref)
    if m:
        seg = urllib.parse.parse_qs(urllib.parse.urlparse(ref if "://" in ref else "https://" + ref).query).get("seg")
        return m.group(1), seg[0] if seg else None
    if re.fullmatch(r"[A-Za-z0-9]{6,12}", ref.strip()):
        return ref.strip(), None
    raise ValueError("not an AbyssLogs link (https://abysslogs.com/e/<id>)")


def encounter(enc_id: str) -> dict:
    return fetch_json(f"{API}/encounters/{enc_id}", headers=_HEADERS)


def segment(enc_id: str, seg_id: str) -> dict:
    link = fetch_json(f"{API}/encounters/{enc_id}/segments/{seg_id}/url", headers=_HEADERS)["url"]
    _throttle(0.3)
    return load_bytes(_get(link, {"User-Agent": UA}))


def load_bytes(raw: bytes) -> dict:
    """A segment file as saved from the site (gzip or plain JSON)."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def is_segment(d) -> bool:
    return isinstance(d, dict) and "players" in d and ("bossTimeline" in d or "startTime" in d)


def pick_segment(enc: dict, seg_id: str | None = None) -> str:
    """The requested segment, else the boss pull with the most damage."""
    segs = enc.get("segments") or []
    if seg_id:
        if not any(s["segmentId"] == seg_id for s in segs):
            raise ValueError(f"segment {seg_id} is not part of fight {enc.get('id')}")
        return seg_id
    if not segs:
        raise ValueError("this fight has no segments")
    best = max(segs, key=lambda s: (bool(s.get("hasBoss")), s.get("totalDamage") or 0))
    return best["segmentId"]


def class_key(hint: str | None) -> str | None:
    return CLASS_KEYS.get((hint or "").strip().title())


def skill_base(code: int, cd: ClassData | None) -> int | None:
    """Class skill id behind a logged skill code.

    Codes are the class skill id plus a variant suffix (``16010130`` -> Cold
    Shock ``16010000``); damage-over-time ticks carry two more digits
    (``1614000011``).
    """
    if not cd or not code:
        return None
    c = int(code)
    if c >= 10 ** 9:
        c //= 100
    base = c // 10000 * 10000
    return base if base in cd.skills else None


_CHAINS: dict = {}
#: follow-ups no tooltip names (basic-attack chains); verified against logs
CHAIN_STEPS = {"sorcerer": {"Burst": "Flame Arrow"}}


def chain_parent(name: str | None, cd: ClassData | None) -> int | None:
    """Class skill a chain follow-up belongs to (Cold Wave -> Ice Chain).

    Follow-ups are not learnable skills, so they are missing from the skill
    tables. Most are named in their parent's tooltip ("on landing [Cold
    Wave]"); the rest are listed in :data:`CHAIN_STEPS`. Anything else keeps its
    own row.
    """
    if not cd or not name:
        return None
    if cd.cls not in _CHAINS:
        known = {s["name"] for s in cd.skills.values()}
        named: dict = {}
        for sid, s in cd.skills.items():
            for t in [s.get("tip") or ""] + [x.get("text", "") for x in s.get("specs", [])]:
                for n in re.findall(r"\[([^\]]+)\]", str(t)):
                    if n not in known:
                        named.setdefault(n, sid)
        for step, parent in CHAIN_STEPS.get(cd.cls, {}).items():
            if parent in cd.by_name:
                named[step] = cd.by_name[parent]["id"]
        _CHAINS[cd.cls] = named
    return _CHAINS[cd.cls].get(name)


def players(seg: dict) -> list[dict]:
    out = [{"id": p.get("entityId"), "name": p.get("name"), "class": class_key(p.get("classHint")),
            "class_name": p.get("classHint"), "damage": p.get("totalDamage") or 0,
            "combat_power": p.get("combatPower")} for p in (seg.get("players") or {}).values()]
    return sorted(out, key=lambda p: -p["damage"])


def _merge(windows: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for a, b in sorted(windows):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _duration(seg: dict) -> float | None:
    from datetime import datetime
    try:
        a, b = (datetime.fromisoformat(seg[k].replace("Z", "+00:00")) for k in ("startTime", "endTime"))
        return max(1.0, (b - a).total_seconds())
    except (KeyError, ValueError, AttributeError):
        return None


def from_segment(seg: dict, player: str | None = None, enc_id: str | None = None) -> dict:
    """One player's side of a segment, in the canonical encounter format."""
    from .adapters import normalize
    roster = seg.get("players") or {}
    if not roster:
        raise ValueError("this segment has no players")
    want = (player or seg.get("recorderName") or "").strip().lower()
    p = next((v for v in roster.values() if (v.get("name") or "").lower() == want), None)
    if p is None and player:
        raise ValueError(f"{player} is not in this fight; players: "
                         + ", ".join(x["name"] for x in players(seg)))
    p = p or max(roster.values(), key=lambda v: v.get("totalDamage") or 0)
    pid = p.get("entityId")
    cls = class_key(p.get("classHint"))
    try:
        cd = ClassData(cls) if cls else None
    except Exception:
        cd = None
    tl = seg.get("bossTimeline") or {}
    names = {int(k): v.get("skillName") for k, v in (tl.get("skills") or {}).items()}

    def label(code: int, base: int | None) -> str:
        nm = names.get(code) or (names.get(base) if base else None)
        return nm if nm and not nm.startswith("[") else str(base or code)

    events = [e for e in tl.get("events") or [] if e.get("playerId") == pid]
    if not events:
        raise ValueError("this pull has no hit timeline for that player (AbyssLogs records timelines for "
                         "boss pulls); pick a boss segment")
    hits = []
    for e in events:
        code = int(e.get("skillCode") or 0)
        base = skill_base(code, cd)
        name = label(code, base)
        step = None
        if base is None and (parent := chain_parent(name, cd)):
            base, step = parent, name          # shown as "Ice Chain (Cold Wave)"
        hits.append({"t": (e.get("timeMs") or 0) / 1000, "skill_id": base or code, "skill": name, "step": step,
                     "damage": e.get("damage") or 0, "crit": e.get("isCrit"), "double": e.get("isDouble"),
                     "perfect": e.get("isPerfect"), "multi": max(0, int(e.get("hitCount") or 1) - 1),
                     "dot": e.get("isDot"), "front": e.get("isFront"), "back": e.get("isBack")})
    dur = _duration(seg) or max(h["t"] for h in hits) or 1.0

    spans: dict[int, list] = {}
    for b in tl.get("buffSpans") or []:
        if b.get("targetId") == pid and b.get("endMs", 0) > b.get("startMs", 0):
            spans.setdefault(int(b["skillCode"]), []).append([b["startMs"] / 1000, b["endMs"] / 1000])
    buffs = []
    for code, ws in spans.items():
        ws = _merge(ws)
        base = skill_base(code, cd)
        buffs.append({"name": label(code, base), "skill_id": base or code,
                      "uptime": min(1.0, sum(b - a for a, b in ws) / dur), "windows": ws})
    buffs.sort(key=lambda b: -b["uptime"])

    specs: dict[str, str] = {}
    for tgt in (p.get("targets") or {}).values():
        for code, sk in (tgt.get("skills") or {}).items():
            slots = sorted({int(x["slot"]) for x in sk.get("specialities") or [] if x.get("slot")})
            if not slots:
                continue
            base = skill_base(int(code), cd)
            name = cd.skills[base]["name"] if base else (sk.get("skillName") or str(code))
            specs.setdefault(name, ", ".join(map(str, slots)))

    boss = next((t for t in (seg.get("targets") or {}).values() if t.get("isBoss")), None)
    seg_id = seg.get("id")
    boss_dmg = sum(h["damage"] for h in hits)
    notes = [f"AbyssLogs fight recorded by {seg.get('recorderName') or 'the AbyssLogs meter'}"]
    if (p.get("totalDamage") or 0) > boss_dmg * 1.02:
        notes.append(f"boss damage only ({boss_dmg / p['totalDamage']:.0%} of this player's damage in the pull)")
    enc = {"meta": {"source": "abysslogs", "ref": f"{enc_id or 'file'}/{seg_id}/{p.get('name')}",
                    "url": f"{SITE}/e/{enc_id}?seg={seg_id}" if enc_id else None,
                    "class": cls, "class_name": p.get("classHint"), "player": p.get("name"),
                    "target": (boss or {}).get("name") or seg.get("label"), "duration": dur,
                    "started_at": seg.get("startTime"), "combat_power": p.get("combatPower"),
                    "gear_score": p.get("gearScore"), "region": seg.get("region"), "server_id": p.get("serverId"),
                    "boss_killed": bool(boss and boss.get("isDead")),
                    "party": [{"name": x["name"], "class": x["class_name"], "damage": x["damage"]}
                              for x in players(seg)],
                    "notes": notes},
           "hits": hits, "buffs": buffs, "specs": {}}
    enc = normalize(enc)
    enc["specs"] = specs
    return enc


def from_ref(ref: str, player: str | None = None) -> dict:
    """An AbyssLogs share link (or id) -> canonical encounter for ``player``
    (default: whoever recorded the fight)."""
    enc_id, seg_id = parse_ref(ref)
    enc = encounter(enc_id)
    seg_id = pick_segment(enc, seg_id)
    out = from_segment(segment(enc_id, seg_id), player=player, enc_id=enc_id)
    out["meta"]["fight"] = {"name": enc.get("dungeonName") or enc.get("bossName"),
                            "tier": enc.get("dungeonTier"), "category": enc.get("dungeonCategory"),
                            "segments": [{"id": s["segmentId"], "label": s.get("label"), "boss": s.get("hasBoss"),
                                          "duration": s.get("duration")} for s in enc.get("segments") or []]}
    return out
