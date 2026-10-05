"""Local SQLite fight history and user settings."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LocalStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path.home() / ".a2tools-dps-meter" / "meter.sqlite3"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS fights (id INTEGER PRIMARY KEY, saved_ms INTEGER NOT NULL, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_fight(self, snapshot: dict) -> int:
        with self._db() as db:
            cur = db.execute("INSERT INTO fights(saved_ms,data) VALUES (?,?)", (time.time_ns() // 1_000_000, json.dumps(snapshot)))
            return int(cur.lastrowid)

    def fights(self, limit: int = 100) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT id,saved_ms,data FROM fights ORDER BY saved_ms DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": row[0], "savedMs": row[1], **json.loads(row[2])} for row in rows]

    def fight(self, fight_id: int) -> dict | None:
        """Load one saved encounter by its local database id."""
        with self._db() as db:
            row = db.execute("SELECT id,saved_ms,data FROM fights WHERE id=?", (int(fight_id),)).fetchone()
        return {"id": row[0], "savedMs": row[1], **json.loads(row[2])} if row else None

    def delete_fight(self, fight_id: int) -> bool:
        """Delete one saved encounter; return whether a row was removed."""
        with self._db() as db:
            cursor = db.execute("DELETE FROM fights WHERE id=?", (int(fight_id),))
            return cursor.rowcount > 0

    def setting(self, key: str, default=None):
        with self._db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value) -> None:
        with self._db() as db:
            db.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
