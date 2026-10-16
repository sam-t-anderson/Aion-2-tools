"""Your recorded fights as encounter history.

The live meter writes whole-party session logs (``session-*.a2log.json`` in the logs
folder); the planner's "Your fights", the rotation findings and the model calibration
read the single-player *encounter history* (the ``encounters`` table, one row per fight
of one player). Nothing moved fights from one to the other, so a character whose only
logs came from the live meter had no fights at all in its advice.

:func:`sync_sessions` turns the recording player's boss fights from the saved sessions
into encounter rows (source ``session``, ref ``<file>#<segment>``), once each, and lets
the calibration observe the new ones. It is cheap to call before every advice run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..db import store
from ..paths import logs_dir

SOURCE = "session"
MIN_DURATION = 20.0          # a boss fight shorter than this is a pull reset, not a fight
MIN_HITS = 10                # the player's own hits in the fight


def _candidates(doc: dict, pid: str) -> list[int]:
    """Indexes of the recording player's boss fights in one session, best first."""
    out = []
    for index, seg in enumerate(doc.get("segments") or []):
        if not seg.get("boss") or str(seg.get("encounter_type") or "").startswith("pvp_"):
            continue
        if (seg.get("duration") or 0) < MIN_DURATION:
            continue
        mine = sum(1 for h in seg.get("hits") or [] if h.get("player") == pid and (h.get("damage") or 0) > 0)
        if mine < MIN_HITS:
            continue
        out.append(index)
    return out


def sync_sessions(name: str | None = None, cls: str | None = None, limit: int = 300, conn=None,
                  folder: Path | None = None, progress=None) -> dict:
    """Import the recording player's boss fights from the saved live-meter sessions.

    ``name``/``cls`` restrict the import to one character (the one being advised), so
    another character's sessions on the same computer are left for their own advice run.
    Returns ``{"files", "added", "ids", "skipped"}``; never raises on a bad file.
    """
    from . import a2log
    from .. import learn
    say = progress or (lambda m: None)
    conn = conn or store.connect()
    folder = folder or logs_dir()
    known = {r[0] for r in conn.execute("SELECT ref FROM encounters WHERE source=?", (SOURCE,))}
    try:
        files = sorted(folder.glob("session-*.a2log.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
    added, skipped, touched = [], 0, 0
    for path in files:
        if len(added) >= limit:
            break
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            skipped += 1
            continue
        if not a2log.is_document(doc) or (doc.get("meta") or {}).get("capture_active") is True:
            continue                      # an open checkpoint is re-saved; import it once it is final
        pid = a2log.recording_player(doc)
        player = next((p for p in doc.get("players") or [] if p.get("id") == pid), None) if pid else None
        if not player or not player.get("name"):
            continue
        if name and str(player["name"]).strip().casefold() != str(name).strip().casefold():
            continue
        if cls and str(player.get("class") or "").lower() != str(cls).lower():
            continue
        wanted = [i for i in _candidates(doc, pid) if f"{path.name}#{i}" not in known]
        if not wanted:
            continue
        touched += 1
        try:
            doc = a2log.validate(doc)
        except Exception:                 # noqa: BLE001 - a corrupt session must not block advice
            skipped += 1
            continue
        for index in wanted:
            ref = f"{path.name}#{index}"
            try:
                enc = a2log.to_encounter(doc, pid, index)
            except Exception:             # noqa: BLE001
                skipped += 1
                continue
            m = enc.setdefault("meta", {})
            m.update(source=SOURCE, ref=ref, imported_at=time.time())
            eid = store.put_encounter(conn, enc)
            known.add(ref)
            added.append(eid)
            say(f"fight {m.get('target')} ({path.name} #{index + 1}) added to your history")
    if added:
        classes = set()
        for eid in added:
            try:
                obs = learn.observe(eid, conn)
            except Exception:             # noqa: BLE001 - learning never blocks the import
                obs = None
            if obs:
                classes.add(obs["class"])
        for c in classes:
            try:
                learn.fit(c, conn)
            except Exception:             # noqa: BLE001
                pass
    return {"files": touched, "added": len(added), "ids": added, "skipped": skipped}
