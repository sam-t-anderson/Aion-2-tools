"""A character's recorded healing, pooled per skill from the fights saved on this computer (0.2.368).

The simulator models no healing amounts (a heal is time off the damage rotation), so the My Character
overview's *Healing share* comes from the recordings instead: every ``session-*.a2log.json`` in the logs
folder in which the character healed, each fight's heal events by the character summed per skill. The
pooled result is cached per file (name, size, modification time), so opening the page again reads only
the recordings that are new.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..paths import home, logs_dir

CACHE = "healing-share-cache.json"
#: fights shorter than this are not pooled (a stray heal between pulls says nothing about the share)
MIN_SECONDS = 20.0


def _load(path: Path) -> dict | None:
    try:
        with open(path, "rb") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _player(doc: dict, name: str, server: str | None) -> dict | None:
    want = (name or "").strip().lower()
    for p in doc.get("players") or []:
        if str(p.get("name") or "").strip().lower() != want:
            continue
        if server and p.get("server") and str(p["server"]).lower() != str(server).lower():
            continue
        return p
    return None


def _pool(doc: dict, pid: str) -> dict:
    """One recording's heals by ``pid``: per-skill amounts, total, the seconds of the fights it healed in."""
    from .healing import drop_restores, unattributed_heals
    skills: dict[str, float] = {}
    total = seconds = 0.0
    fights = 0
    players = {p.get("id") for p in doc.get("players") or [] if isinstance(p, dict)}
    for seg in doc.get("segments") or []:
        if not isinstance(seg, dict) or float(seg.get("duration") or 0) < MIN_SECONDS:
            continue
        seg = {**seg, "events": [dict(e) for e in (seg.get("events") or []) if isinstance(e, dict)]}
        try:
            drop_restores(seg)                 # MP and stamina restores are recorded as heals too
            unattributed_heals(seg, players)   # and before 0.2.398 an opponent's shield as your heal on them
        except Exception:                      # noqa: BLE001 - a malformed segment is pooled as it is
            pass
        healed = 0.0
        for e in seg["events"]:
            if e.get("kind") != "heal" or e.get("source") != pid:
                continue
            amount = float(e.get("amount") or 0)
            if amount <= 0:
                continue
            name = str(e.get("skill") or e.get("skill_id") or "Unknown")
            skills[name] = skills.get(name, 0.0) + amount
            healed += amount
        if healed > 0:
            total += healed
            seconds += float(seg["duration"])
            fights += 1
    return {"skills": skills, "total": total, "seconds": seconds, "fights": fights}


def recorded_healing(name: str, server: str | None = None, limit: int = 400) -> dict | None:
    """The character's pooled healing: ``{"hps", "healing", "fights", "seconds", "recordings", "shares"}`` with
    the shares per skill (largest first), or None when no saved recording has the character healing."""
    if not name:
        return None
    files = sorted(logs_dir().glob("session-*.a2log.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    cache_path = home() / CACHE
    cache = _load(cache_path) if cache_path.exists() else None
    cache = cache if isinstance(cache, dict) else {}
    key_of = lambda p, st: f"{p.name}|{st.st_size}|{int(st.st_mtime)}|{name.lower()}|{(server or '').lower()}"  # noqa: E731
    pooled: dict[str, float] = {}
    total = seconds = 0.0
    fights = recordings = 0
    fresh: dict = {}
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        key = key_of(path, st)
        row = cache.get(key)
        if row is None:
            doc = _load(path)
            p = _player(doc, name, server) if doc else None
            row = _pool(doc, p["id"]) if p else {"skills": {}, "total": 0.0, "seconds": 0.0, "fights": 0}
        fresh[key] = row
        if row["total"] > 0:
            recordings += 1
            total += row["total"]
            seconds += row["seconds"]
            fights += row["fights"]
            for k, v in row["skills"].items():
                pooled[k] = pooled.get(k, 0.0) + v
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(fresh), encoding="utf-8")
            os.replace(tmp, cache_path)
        except OSError:
            pass
    if total <= 0:
        return None
    shares = {k: v / total for k, v in sorted(pooled.items(), key=lambda kv: -kv[1])}
    return {"hps": total / seconds if seconds else 0.0, "healing": total, "fights": fights, "seconds": seconds,
            "recordings": recordings, "shares": shares}
