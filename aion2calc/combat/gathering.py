"""Gathering tracker: what the player gathers and what dungeon reward cubes give, kept locally and shared.

The meter reads two of the game's records (``meter/a2parser/parser.py``): a gather's result (``33 8d``: the
node's kind, the item, how many and whether it came up a better grade or failed) and a reward cube's contents
(``15 57``: every item and count the run's cube gave). The app keeps each in a local log (``gathering/log.jsonl``
in its data folder) for the Gathering page, and unless "Share gathering and drop data" is off in Settings (on by
default) sends them to the log server, which turns everyone's into drop rates: for each kind of node, how often
each grade comes up and how many a gather gives; for each dungeon, how often a reward cube holds each material
and how many.

What a report carries: each gather's item, count, result, node kind, map and dungeon and its time; each cube's
items, map and dungeon and its time; an anonymous per-install reporter key. The character's name and server go
only with a report from a signed-in app, so the account's own Gathering page can list them; the server shows
them to nobody else and its drop rates never name anyone. ``report`` is best-effort and never raises: a record
the server has not taken stays queued for the next try.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
import threading
import time
import urllib.request

from .. import __version__
from ..paths import user_data, write_user_json
from . import beacon, heartbeat, share
from .items import base_material, is_material, item_info, item_name

_ENDPOINT = "/api/v1/gathering"
_DIR = "gathering"
#: Most records the local log keeps; the oldest go first.
_LOCAL_LIMIT = 50_000
#: Most records one report carries, and the server's cap.
_BATCH_MAX = 200
#: Ids the server took, so a record is sent once; old ones age out with the log.
_SENT_LIMIT = 60_000
#: A checkpoint reports at most this often; Stop reports at once.
_CHECKPOINT_EVERY_S = 120.0
RESULTS = ("normal", "better", "failed")
_BACKOFF = beacon.Backoff()
_lock = threading.Lock()
_send_lock = threading.Lock()
_last_report: float | None = None


def enabled(ui: dict | None = None) -> bool:
    """Opt-OUT: gathering and drop data are shared unless "Share gathering and drop data" is off."""
    if ui is None:
        try:
            from ..app import server
            ui = server.ui_settings()
        except Exception:
            ui = {}
    return ui.get("share_gathering", True) is not False


def reporter_key() -> str:
    """A stable, anonymous per-install key for gathering reports, from the local-only install salt and
    distinct from every other report's key."""
    salt = heartbeat._install_salt()
    return hashlib.sha256(f"{salt}:gathering-reporter".encode("utf-8")).hexdigest()[:32]


def _path():
    return user_data().joinpath(_DIR, "log.jsonl")


def _int(value) -> int | None:
    return value if type(value) is int else None


def normalize(raw: dict) -> dict | None:
    """A drained engine record (``MeterEngine.drain_gathering``) as the log keeps it, with a stable id."""
    if not isinstance(raw, dict) or raw.get("kind") not in ("gather", "reward") or _int(raw.get("timestamp_ms")) is None:
        return None
    out = {"kind": raw["kind"], "t": round(raw["timestamp_ms"] / 1000, 3), "map": _int(raw.get("map_id")),
           "instance": _int(raw.get("instance_id")), "character": raw.get("character") if isinstance(raw.get("character"), str) else None,
           "server": _int(raw.get("server_id"))}
    if raw["kind"] == "gather":
        if _int(raw.get("item")) is None or _int(raw.get("count")) is None or raw.get("result") not in (0, 1, 2):
            return None
        out.update(item=raw["item"], count=raw["count"], result=RESULTS[raw["result"]], node=_int(raw.get("node")))
        position = raw.get("position")
        if isinstance(position, list) and len(position) == 3 and all(isinstance(v, (int, float)) for v in position):
            out["pos"] = [round(float(v), 1) for v in position]
        key = (out["item"], out["count"], out["result"], out["node"])
    else:
        items = [entry for entry in raw.get("items") or [] if isinstance(entry, list) and len(entry) == 2
                 and all(_int(v) is not None for v in entry)]
        if not items:
            return None
        out["items"] = items
        key = tuple(map(tuple, items))
    seed = json.dumps([raw["kind"], raw["timestamp_ms"], out["character"], out["server"], key], default=str)
    out["id"] = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return out


def record(raw_events) -> list[dict]:
    """Append drained engine records to the local log; returns them as kept. Never raises."""
    rows = [row for row in (normalize(e) for e in raw_events or ()) if row]
    if not rows:
        return []
    try:
        with _lock:
            path = _path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if path.stat().st_size > _LOCAL_LIMIT * 400:
                _trim(path)
    except OSError:
        return []
    return rows


def _trim(path) -> None:
    kept = read()[-_LOCAL_LIMIT:]
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def read() -> list[dict]:
    """Every record in the local log, oldest first; a damaged line is skipped."""
    path = _path()
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind") in ("gather", "reward") and isinstance(row.get("id"), str):
                out.append(row)
    return out


def place_name(instance=None, map_id=None) -> str:
    """A dungeon's name (with its difficulty when the catalog gives one) or the open-world zone of a map."""
    from ..meter.a2parser.lookup import _table, supplement_dungeon
    from ..meter.context import OBSERVED_ZONES, derived_zone_label, open_world_zone
    key = instance or map_id
    if key:
        row = _table("dungeons", "en").get(str(key)) or supplement_dungeon(key) or {}
        if row.get("name"):
            level = row.get("difficulty_name") or (row.get("difficulty") or "").title()
            return f"{row['name']} ({level})" if level else row["name"]
        if key in OBSERVED_ZONES:
            return OBSERVED_ZONES[key]["zone"]
        if instance and (label := derived_zone_label(instance)):
            return label
    zone = open_world_zone(map_id) if map_id else None
    return zone or (f"Map {map_id}" if map_id else "Unknown place")


def node_label(node, items) -> str:
    """What a node is called: the material it gives (the plainest grade's name), "Unknown node" without one."""
    names = Counter(base_material(item) for item in items)
    return names.most_common(1)[0][0] if names else "Unknown node"


def summary(rows=None, *, recent: int = 100) -> dict:
    """The Gathering page's view of the local log: totals, each kind of node with its grades and results,
    each item gathered, each dungeon's reward cubes with their materials, and the latest records."""
    rows = read() if rows is None else rows
    gathers = [r for r in rows if r.get("kind") == "gather"]
    rewards = [r for r in rows if r.get("kind") == "reward"]
    nodes: dict = defaultdict(lambda: {"gathers": 0, "results": Counter(), "items": Counter(), "counts": Counter()})
    for row in gathers:
        key = row.get("node") or f"item:{base_material(row['item'])}"
        node = nodes[key]
        node["gathers"] += 1
        node["results"][row["result"]] += 1
        if row["result"] != "failed":
            node["items"][row["item"]] += 1
            node["counts"][row["item"]] += row.get("count") or 0
    node_rows = []
    for key, node in nodes.items():
        items = [{"item": item, **_named(item), "gathers": n, "count": node["counts"][item],
                  "share": round(n / node["gathers"], 4)} for item, n in node["items"].most_common()]
        node_rows.append({"node": key if isinstance(key, int) else None, "name": node_label(key, node["items"]),
                          "gathers": node["gathers"], "results": {r: node["results"][r] for r in RESULTS}, "items": items})
    node_rows.sort(key=lambda r: (-r["gathers"], r["name"]))
    dungeons: dict = defaultdict(lambda: {"cubes": 0, "with": Counter(), "total": Counter()})
    for row in rewards:
        place = row.get("instance") or row.get("map") or 0
        cube = dungeons[place]
        cube["cubes"] += 1
        seen = set()
        for item, count in row["items"]:
            cube["total"][item] += count
            if item not in seen:
                cube["with"][item] += 1
                seen.add(item)
    dungeon_rows = []
    for place, cube in dungeons.items():
        items = [{"item": item, **_named(item), "material": is_material(item), "cubes": n,
                  "share": round(n / cube["cubes"], 4), "total": cube["total"][item], "average": round(cube["total"][item] / n, 2)}
                 for item, n in cube["with"].most_common()]
        dungeon_rows.append({"instance": place or None, "name": place_name(place), "cubes": cube["cubes"], "items": items})
    dungeon_rows.sort(key=lambda r: -r["cubes"])
    totals = Counter()
    for row in gathers:
        if row["result"] != "failed":
            totals[row["item"]] += row.get("count") or 0
    latest = []
    for row in rows[-recent:][::-1]:
        entry = {k: row.get(k) for k in ("id", "kind", "t", "map", "instance", "character", "server", "result", "count", "node")}
        entry["place"] = place_name(row.get("instance"), row.get("map"))
        if row["kind"] == "gather":
            entry.update(item=row["item"], **_named(row["item"]))
        else:
            entry["items"] = [{"item": item, "count": count, **_named(item), "material": is_material(item)} for item, count in row["items"]]
        latest.append(entry)
    return {"gathers": len(gathers), "gathered": sum(totals.values()), "cubes": len(rewards),
            "results": {r: sum(1 for g in gathers if g["result"] == r) for r in RESULTS},
            "nodes": node_rows, "items": [{"item": item, **_named(item), "count": n} for item, n in totals.most_common()],
            "dungeons": dungeon_rows, "recent": latest}


def _named(item) -> dict:
    info = item_info(item)
    return {"name": info.get("name") or item_name(item), "grade": info.get("grade") or ""}


def _sent() -> list[str]:
    try:
        data = json.loads(user_data().joinpath(_DIR, "sent.json").read_text(encoding="utf-8"))
        return [s for s in data.get("sent") or [] if isinstance(s, str)] if isinstance(data, dict) else []
    except (OSError, ValueError):
        return []


def _mark_sent(ids) -> None:
    merged = _sent()
    known = set(merged)
    merged += [i for i in ids if i not in known]
    try:
        write_user_json({"sent": merged[-_SENT_LIMIT:]}, _DIR, "sent.json")
    except OSError:
        pass


def _wire(row: dict, signed_in: bool) -> dict:
    """A record as a report carries it: the character only from a signed-in app."""
    body = {k: row[k] for k in ("id", "kind", "t", "map", "instance") if row.get(k) is not None}
    if row["kind"] == "gather":
        body.update({k: row[k] for k in ("item", "count", "result", "node") if row.get(k) is not None})
    else:
        body["items"] = row["items"]
    if signed_in:
        body.update({k: row[k] for k in ("character", "server") if row.get(k) is not None})
    return body


def _post(base: str, body: dict, key: str | None, account: str | None) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if account:
        headers["X-Account-Token"] = account
    request = urllib.request.Request(base + _ENDPOINT, json.dumps(body).encode("utf-8"), headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def report(ui: dict | None = None, final: bool | None = None) -> str:
    """Send the records the server does not have yet. Returns a short status and never raises.

    ``final`` is True at Stop, False at a checkpoint (at most every two minutes) and None to send now. A server
    that does not take gathering reports yet (no ``gathering`` in its capabilities) leaves the records queued;
    a 429 pauses reports for its Retry-After and a rejected batch (another 4xx) is marked done, not retried."""
    global _last_report
    try:
        if not enabled(ui):
            return "disabled"
        if _BACKOFF.paused():
            return "paused"
        now = time.monotonic()
        if final is False and _last_report is not None and now - _last_report < _CHECKPOINT_EVERY_S:
            return "throttled"
        with _send_lock:
            _last_report = now
            done = set(_sent())
            fresh = [row for row in read() if row["id"] not in done]
            if not fresh:
                return "nothing"
            server = share.effective()
            base = str(server.get("url") or "").rstrip("/")
            if not base:
                return "no-server"
            if not share.capabilities(base).get("gathering"):
                return "unsupported"
            from .account import token_for
            account = token_for(base)
            reporter = reporter_key()
            sent = 0
            for start in range(0, len(fresh), _BATCH_MAX):
                chunk = fresh[start:start + _BATCH_MAX]
                body = {"reporter": reporter, "client": __version__, "events": [_wire(row, bool(account)) for row in chunk]}
                try:
                    _post(base, body, server.get("key"), account)
                except Exception as exc:
                    if beacon.permanent_rejection(exc):
                        _mark_sent(row["id"] for row in chunk)
                    elif beacon.rate_limited(exc):
                        _BACKOFF.pause(getattr(exc, "headers", None))
                    return f"sent {sent}" if sent else "failed"
                _mark_sent(row["id"] for row in chunk)
                sent += len(chunk)
            return f"sent {sent}"
    except Exception:
        return "failed"


def report_async(ui: dict | None = None, final: bool | None = None) -> None:
    """Fire :func:`report` on a daemon thread so a checkpoint never waits on the network."""
    try:
        if enabled(ui):
            threading.Thread(target=report, args=(ui, final), daemon=True, name="aion2-gathering-report").start()
    except Exception:
        pass
