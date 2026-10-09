"""Local SQLite store: game catalog, official item cache, characters, encounters.

The file lives in the user's data directory (``~/.aion2calc/aion2.db``).  A
fresh database is seeded from ``aion2calc/data/seed/items.json.gz`` when that
exists, so the planner has a full catalog before the first sync finishes.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import threading
import time
from pathlib import Path

from ..paths import PKG_DATA, home

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS pages (
  url TEXT PRIMARY KEY, kind TEXT, slug TEXT, lastmod TEXT, fetched_lastmod TEXT,
  fetched_at REAL, status TEXT);
CREATE TABLE IF NOT EXISTS items (
  slug TEXT PRIMARY KEY, name TEXT, grade TEXT, category TEXT, item_level INTEGER,
  class_name TEXT, icon TEXT, data TEXT, lastmod TEXT, fetched_at REAL);
CREATE INDEX IF NOT EXISTS items_cat ON items(category);
CREATE TABLE IF NOT EXISTS official_items (
  id INTEGER, enchant INTEGER, data TEXT, fetched_at REAL, PRIMARY KEY (id, enchant));
CREATE TABLE IF NOT EXISTS official_assets (
  region TEXT, kind TEXT, asset_id TEXT, name TEXT, icon TEXT, grade TEXT, observed_at REAL,
  reference_changes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(region,kind,asset_id));
CREATE TABLE IF NOT EXISTS characters (
  key TEXT PRIMARY KEY, region TEXT, server_id INTEGER, character_id TEXT, name TEXT,
  class_name TEXT, level INTEGER, combat_power INTEGER, data TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS encounters (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, ref TEXT, class_name TEXT, player TEXT,
  boss TEXT, duration REAL, dps REAL, total REAL, started_at TEXT, imported_at REAL, data TEXT,
  UNIQUE (source, ref));
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, name TEXT, class_name TEXT, taken_at REAL, data TEXT);
CREATE INDEX IF NOT EXISTS snapshots_name ON snapshots(name);
CREATE TABLE IF NOT EXISTS observations (
  encounter_id INTEGER PRIMARY KEY, snapshot_id INTEGER, class_name TEXT, player TEXT, data TEXT,
  computed_at REAL);
"""

_local = threading.local()
SEED = PKG_DATA / "seed" / "items.json.gz"


def db_path() -> Path:
    return home() / "aion2.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """One connection per thread (SQLite objects are not shared across threads)."""
    key = str(path or db_path())
    cache = getattr(_local, "conns", None)
    if cache is None:
        cache = _local.conns = {}
    if key in cache:
        return cache[key]
    conn = sqlite3.connect(key, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0 and SEED.exists():
            with conn:
                import_seed(conn)
    except BaseException:
        # Failed initialization must not poison the thread cache or retain a lock.
        conn.close()
        raise
    cache[key] = conn
    return conn


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(conn, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, json.dumps(value)))
    conn.commit()


# ------------------------------------------------------------------ items
def upsert_item(conn, it: dict, lastmod: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO items(slug, name, grade, category, item_level, class_name, icon, data, "
        "lastmod, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (it["slug"], it.get("name"), it.get("grade"), it.get("category"), it.get("item_level"),
         (it.get("meta") or {}).get("Class"), it.get("icon"), json.dumps(it, ensure_ascii=False),
         lastmod, time.time()))


def item(conn, slug: str) -> dict | None:
    row = conn.execute("SELECT data FROM items WHERE slug=?", (slug,)).fetchone()
    return json.loads(row[0]) if row else None


def items(conn, category: str | None = None, class_name: str | None = None, search: str | None = None,
          limit: int = 500) -> list[dict]:
    q, args = "SELECT slug, name, grade, category, item_level, class_name, icon FROM items WHERE 1=1", []
    if category:
        q += " AND category=?"
        args.append(category)
    if class_name:
        q += " AND (class_name IS NULL OR class_name LIKE ?)"
        args.append(f"%{class_name}%")
    if search:
        q += " AND name LIKE ?"
        args.append(f"%{search}%")
    q += " ORDER BY item_level DESC, name LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(q, args)]


def categories(conn) -> list[tuple[str, int]]:
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT category, COUNT(*) FROM items GROUP BY category ORDER BY COUNT(*) DESC")]


def import_seed(conn, path: Path = SEED) -> int:
    rows = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    for r in rows:
        upsert_item(conn, r["data"], r.get("lastmod"))
    conn.commit()
    return len(rows)


def export_seed(conn, path: Path = SEED) -> int:
    rows = [{"data": json.loads(r[0]), "lastmod": r[1]}
            for r in conn.execute("SELECT data, lastmod FROM items ORDER BY slug")]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()))
    return len(rows)


# ---------------------------------------------------------- official cache
def official_item(conn, item_id: int, enchant: int, max_age: float = 7 * 86400) -> dict | None:
    row = conn.execute("SELECT data, fetched_at FROM official_items WHERE id=? AND enchant=?",
                       (item_id, enchant)).fetchone()
    if row and time.time() - row[1] < max_age:
        return json.loads(row[0])
    return None


def put_official_item(conn, item_id: int, enchant: int, data: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO official_items(id, enchant, data, fetched_at) VALUES (?,?,?,?)",
                 (item_id, enchant, json.dumps(data, ensure_ascii=False), time.time()))
    conn.commit()


# -------------------------------------------------------------- characters
def put_character(conn, key: str, ch: dict) -> None:
    p = ch.get("profile", {})
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO characters(key, region, server_id, character_id, name, class_name, level, "
            "combat_power, data, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (key, ch.get("region"), p.get("serverId"), p.get("characterId"), p.get("characterName"),
             p.get("className"), p.get("characterLevel"), p.get("combatPower"),
             json.dumps(ch, ensure_ascii=False), time.time()))
        from .assets import record
        conn.execute("SAVEPOINT asset_import")
        try:
            record(conn, ch)
        except (sqlite3.Error, TypeError, ValueError, AttributeError):
            conn.execute("ROLLBACK TO asset_import")
        finally:
            conn.execute("RELEASE asset_import")



def character(conn, key: str) -> dict | None:
    row = conn.execute("SELECT data FROM characters WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def characters(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT key, region, server_id, character_id, name, class_name, level, combat_power, fetched_at FROM characters "
        "ORDER BY fetched_at DESC")]


# -------------------------------------------------------------- equipment snapshots
def put_snapshot(conn, key: str, name: str, cls: str, data: dict, taken_at: float | None = None) -> int:
    """What a character had equipped at one import (fights are matched to the nearest earlier one)."""
    cur = conn.execute("INSERT INTO snapshots(key, name, class_name, taken_at, data) VALUES (?,?,?,?,?)",
                       (key, name, cls, taken_at or time.time(), json.dumps(data, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def snapshot_for(conn, name: str, cls: str | None, at: float | None = None) -> dict | None:
    """The snapshot of ``name`` closest before ``at`` (else the earliest after it)."""
    q = "SELECT id, key, name, class_name, taken_at, data FROM snapshots WHERE lower(name)=lower(?)"
    args: list = [name]
    if cls:
        q += " AND class_name=?"
        args.append(cls)
    rows = [dict(r) for r in conn.execute(q + " ORDER BY taken_at", args)]
    if not rows:
        return None
    at = at or time.time()
    before = [r for r in rows if r["taken_at"] <= at]
    r = before[-1] if before else rows[0]
    return {**r, "data": json.loads(r["data"])}


def snapshots(conn, name: str | None = None) -> list[dict]:
    q = "SELECT id, key, name, class_name, taken_at FROM snapshots"
    args = []
    if name:
        q += " WHERE lower(name)=lower(?)"
        args.append(name)
    return [dict(r) for r in conn.execute(q + " ORDER BY taken_at DESC", args)]


def put_observation(conn, encounter_id: int, snapshot_id: int | None, cls: str, player: str, data: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO observations(encounter_id, snapshot_id, class_name, player, data, "
                 "computed_at) VALUES (?,?,?,?,?,?)",
                 (encounter_id, snapshot_id, cls, player, json.dumps(data), time.time()))
    conn.commit()


def observations(conn, cls: str | None = None, player: str | None = None) -> list[dict]:
    q, args = "SELECT encounter_id, snapshot_id, class_name, player, data FROM observations WHERE 1=1", []
    if cls:
        q += " AND class_name=?"
        args.append(cls)
    if player:
        q += " AND lower(player)=lower(?)"
        args.append(player)
    return [{**dict(r), "data": json.loads(r["data"])} for r in conn.execute(q, args)]


# -------------------------------------------------------------- encounters
def put_encounter(conn, enc: dict) -> int:
    m = enc["meta"]
    cur = conn.execute(
        "INSERT OR REPLACE INTO encounters(source, ref, class_name, player, boss, duration, dps, total, "
        "started_at, imported_at, data) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (m.get("source"), m.get("ref"), m.get("class"), m.get("player"), m.get("target"),
         m.get("duration"), m.get("dps"), m.get("total"), m.get("started_at"), time.time(),
         json.dumps(enc, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def encounter(conn, enc_id: int) -> dict | None:
    row = conn.execute("SELECT data FROM encounters WHERE id=?", (enc_id,)).fetchone()
    return json.loads(row[0]) if row else None


def encounters(conn, class_name: str | None = None) -> list[dict]:
    q = "SELECT id, source, ref, class_name, player, boss, duration, dps, total, started_at, imported_at FROM encounters"
    args: list = []
    if class_name:
        q += " WHERE class_name=?"
        args.append(class_name)
    return [dict(r) for r in conn.execute(q + " ORDER BY imported_at DESC", args)]
