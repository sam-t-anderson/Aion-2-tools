"""Storage for the log server: SQLite for the index, one gzip file per log."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, token_hash TEXT UNIQUE, created_at REAL,
  revoked INTEGER DEFAULT 0, uploads INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS logs (
  id TEXT PRIMARY KEY, created_at REAL, key_id INTEGER, uploader_ip TEXT, visibility TEXT, view_token TEXT,
  delete_token_hash TEXT, title TEXT, boss TEXT, region TEXT, source TEXT, duration REAL, players TEXT,
  top_dps REAL, segments INTEGER, size INTEGER);
CREATE INDEX IF NOT EXISTS logs_public ON logs(visibility, created_at);
CREATE TABLE IF NOT EXISTS observations (
  log_id TEXT, segment INTEGER, player TEXT, class_name TEXT, boss TEXT, combat_power REAL, dps REAL,
  created_at REAL, data TEXT, PRIMARY KEY (log_id, segment, player));
CREATE INDEX IF NOT EXISTS obs_class ON observations(class_name, boss);
CREATE TABLE IF NOT EXISTS hits_rate (bucket TEXT PRIMARY KEY, n INTEGER, until REAL);
"""
_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "logs.db"
        self._local = threading.local()
        self.conn().executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.db_path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            self._local.c = c
        return c

    # ------------------------------------------------------------ keys
    def create_key(self, name: str) -> tuple[int, str]:
        token = "a2l_" + secrets.token_urlsafe(24)
        cur = self.conn().execute("INSERT INTO keys(name, token_hash, created_at) VALUES (?,?,?)",
                                  (name, _hash(token), time.time()))
        self.conn().commit()
        return cur.lastrowid, token

    def key_of(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.conn().execute("SELECT * FROM keys WHERE token_hash=? AND revoked=0", (_hash(token),)).fetchone()
        return dict(row) if row else None

    def keys(self) -> list[dict]:
        return [dict(r) for r in self.conn().execute("SELECT id, name, created_at, revoked, uploads FROM keys")]

    def revoke(self, key_id: int) -> bool:
        cur = self.conn().execute("UPDATE keys SET revoked=1 WHERE id=?", (key_id,))
        self.conn().commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------ rate limits
    def allow(self, bucket: str, limit: int, window: float = 3600.0) -> bool:
        c = self.conn()
        now = time.time()
        row = c.execute("SELECT n, until FROM hits_rate WHERE bucket=?", (bucket,)).fetchone()
        if not row or row["until"] < now:
            c.execute("INSERT OR REPLACE INTO hits_rate(bucket, n, until) VALUES (?,?,?)", (bucket, 1, now + window))
            c.commit()
            return True
        if row["n"] >= limit:
            return False
        c.execute("UPDATE hits_rate SET n=n+1 WHERE bucket=?", (bucket,))
        c.commit()
        return True

    # ------------------------------------------------------------ logs
    def _path(self, log_id: str) -> Path:
        return self.root / "logs" / log_id[:2] / f"{log_id}.json.gz"

    def new_id(self) -> str:
        while True:
            i = "".join(secrets.choice(_ALPHABET) for _ in range(10))
            if not self.conn().execute("SELECT 1 FROM logs WHERE id=?", (i,)).fetchone():
                return i

    def put(self, doc: dict, summary: dict, visibility: str, key_id: int | None, ip: str | None) -> dict:
        log_id = self.new_id()
        raw = gzip.compress(json.dumps(doc, separators=(",", ":")).encode())
        p = self._path(log_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, p)
        delete_token = secrets.token_urlsafe(18)
        view_token = secrets.token_urlsafe(12) if visibility == "private" else None
        self.conn().execute(
            "INSERT INTO logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (log_id, time.time(), key_id, ip, visibility, view_token, _hash(delete_token), summary["title"],
             summary["boss"], summary["region"], summary["source"], summary["duration"],
             json.dumps(summary["players"]), summary["top_dps"], summary["segments"], len(raw)))
        if key_id:
            self.conn().execute("UPDATE keys SET uploads=uploads+1 WHERE id=?", (key_id,))
        self.conn().commit()
        return {"id": log_id, "delete_token": delete_token, "view_token": view_token}

    def row(self, log_id: str) -> dict | None:
        r = self.conn().execute("SELECT * FROM logs WHERE id=?", (log_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["players"] = json.loads(d["players"] or "[]")
        return d

    def doc(self, log_id: str) -> dict:
        return json.loads(gzip.decompress(self._path(log_id).read_bytes()))

    def public(self, page: int = 1, limit: int = 30, boss: str | None = None) -> tuple[list[dict], int]:
        q, args = "FROM logs WHERE visibility='public'", []
        if boss:
            q += " AND boss LIKE ?"
            args.append(f"%{boss}%")
        total = self.conn().execute("SELECT COUNT(*) " + q, args).fetchone()[0]
        rows = self.conn().execute(
            "SELECT id, created_at, title, boss, region, source, duration, players, top_dps, segments "
            + q + " ORDER BY created_at DESC LIMIT ? OFFSET ?", args + [limit, (page - 1) * limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["players"] = json.loads(d["players"] or "[]")
            out.append(d)
        return out, total

    # ------------------------------------------------------------ observations
    version = 0

    def put_observations(self, log_id: str, rows: list[dict]) -> None:
        c = self.conn()
        c.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?)",
                      [(log_id, r["segment"], r["player"], r["class"], r.get("boss"), r.get("combat_power"),
                        r["dps"], time.time(), json.dumps(r)) for r in rows])
        c.commit()
        Store.version += 1

    def observations(self, cls: str | None = None, boss: str | None = None) -> list[dict]:
        q, args = "SELECT data FROM observations WHERE 1=1", []
        if cls:
            q += " AND class_name=?"
            args.append(cls)
        if boss:
            q += " AND boss=?"
            args.append(boss)
        return [json.loads(r[0]) for r in self.conn().execute(q, args)]

    def class_counts(self) -> list[dict]:
        return [dict(r) for r in self.conn().execute(
            "SELECT class_name AS class, COUNT(*) AS observations, COUNT(DISTINCT log_id) AS logs, "
            "MAX(dps) AS best_dps FROM observations GROUP BY class_name ORDER BY observations DESC")]

    def delete(self, log_id: str) -> bool:
        self.conn().execute("DELETE FROM observations WHERE log_id=?", (log_id,))
        Store.version += 1
        cur = self.conn().execute("DELETE FROM logs WHERE id=?", (log_id,))
        self.conn().commit()
        self._path(log_id).unlink(missing_ok=True)
        return cur.rowcount > 0

    def check_delete(self, log_id: str, token: str | None, key: dict | None) -> bool:
        r = self.row(log_id)
        if not r:
            return False
        if key and r["key_id"] == key["id"]:
            return True
        return bool(token) and _hash(token) == r["delete_token_hash"]
