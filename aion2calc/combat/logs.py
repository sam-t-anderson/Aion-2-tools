"""Encounter history on disk: every imported combat log is also written as a file.

Files go to the ``logs`` folder of the user folder (on Windows
``%LOCALAPPDATA%\\aion2calc\\logs``), one JSON file per encounter in the
canonical format of :mod:`aion2calc.combat.adapters`, so a log can be opened,
kept, shared or analyzed again (``python -m aion2calc analyze <file>``)::

    2026-10-04_194657_sorcerer_Name_Gatekeeper-Pinopi_abysslogs-12.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ..db import store
from ..paths import logs_dir


def _safe(text, limit: int = 40) -> str:
    """A file-name part that is valid on Windows too."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", str(text or "")).strip()
    s = re.sub(r"\s+", "-", s).strip(".-")
    return s[:limit] or "unknown"


def file_name(enc: dict, enc_id: int) -> str:
    m = enc.get("meta", {})
    when = None
    if m.get("started_at"):
        try:
            when = datetime.fromisoformat(str(m["started_at"]).replace("Z", "+00:00")).astimezone()
        except ValueError:
            when = None
    when = when or datetime.fromtimestamp(m.get("imported_at") or time.time())
    parts = [when.strftime("%Y-%m-%d_%H%M%S"), _safe(m.get("class"), 16), _safe(m.get("player"), 24),
             _safe(m.get("target"), 32), f"{_safe(m.get('source'), 12)}-{enc_id}"]
    return "_".join(parts) + ".json"


def path_of(enc_id: int, folder: Path | None = None) -> Path | None:
    folder = folder or logs_dir()
    return next(folder.glob(f"*-{enc_id}.json"), None)


def write(enc: dict, enc_id: int, folder: Path | None = None) -> Path:
    folder = folder or logs_dir()
    old = path_of(enc_id, folder)
    path = folder / file_name(enc, enc_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(enc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    if old and old != path:
        old.unlink(missing_ok=True)
    return path


def save(enc: dict, conn=None) -> tuple[int, Path]:
    """Store ``enc`` in the encounter history and write its file."""
    conn = conn or store.connect()
    m = enc.setdefault("meta", {})
    m.setdefault("imported_at", time.time())
    prev = conn.execute("SELECT id FROM encounters WHERE source=? AND ref=?", (m.get("source"), m.get("ref"))).fetchone()
    eid = store.put_encounter(conn, enc)          # a re-import replaces the old row under a new id
    if prev and prev[0] != eid and (old := path_of(prev[0])):
        old.unlink(missing_ok=True)
    return eid, write(enc, eid)


def backfill(conn=None) -> int:
    """Write files for encounters stored before the logs folder existed."""
    conn = conn or store.connect()
    folder = logs_dir()
    n = 0
    for row in store.encounters(conn):
        if path_of(row["id"], folder) is None:
            enc = store.encounter(conn, row["id"])
            if enc:
                enc["meta"].setdefault("imported_at", row.get("imported_at"))
                write(enc, row["id"], folder)
                n += 1
    return n


def open_folder(path: Path | None = None) -> Path:
    """Show the logs folder in Explorer / Finder / the file manager."""
    path = path or logs_dir()
    if sys.platform == "win32":
        os.startfile(path)                                    # noqa: S606 - local folder only
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path
