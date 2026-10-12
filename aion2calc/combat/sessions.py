"""Full party logs on disk, separate from single-player analysis imports."""
import json
import os
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from ..paths import logs_dir, within


def path(name: str) -> Path:
    if not name.startswith("session-") or not name.endswith(".a2log.json") or Path(name).name != name:
        raise ValueError("Invalid session filename")
    # Containment barrier: the resolved file must stay inside the logs folder.
    return within(logs_dir(), name)


def save(doc: dict, name: str) -> Path:
    target = path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Unique sibling files make overlapping final/checkpoint saves safe.
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(doc, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def prune_logs(cap_bytes: int, keep=frozenset(), evict=None) -> dict:
    """Keep the combat-logs folder under ``cap_bytes`` by deleting the oldest
    ``session-*.a2log.json`` files first, so a very long or busy capture session
    (which can write hundreds of rollover parts) cannot grow the folder without
    bound. Files named in ``keep`` — the session currently being written — are
    never removed. Best-effort: returns what it did and never raises.

    Oldest-first by modification time means the oldest recordings (and the oldest
    archive parts, which share a timestamp) go first; newer recordings stay.

    ``evict``, when given, is called with each file's :class:`~pathlib.Path` just
    before it is deleted — a hook used to upload a recording to the share server so
    its data (boss kills and all) isn't lost when the size cap reclaims it. It must
    never raise, must not block for long, and never prevents the delete: the cap is
    honoured whether or not the hook succeeds."""
    result = {"removed": 0, "freed_bytes": 0, "total_bytes": 0, "cap_bytes": int(cap_bytes), "evicted": 0}
    if cap_bytes is None or cap_bytes <= 0:
        return result
    files = []
    total = 0
    try:
        candidates = list(logs_dir().glob("session-*.a2log.json"))
    except OSError:
        return result
    for target in candidates:
        try:
            stat = target.stat()
        except OSError:
            continue
        files.append((stat.st_mtime, stat.st_size, target))
        total += stat.st_size
    files.sort(key=lambda row: row[0])          # oldest first
    for _mtime, size, target in files:
        if total <= cap_bytes:
            break
        if target.name in keep:
            continue
        if evict is not None:
            # Upload before deleting, so the recording survives on the server. Best-effort:
            # a failure here must never keep the folder over its cap.
            try:
                if evict(target):
                    result["evicted"] += 1
            except Exception:
                pass
        try:
            target.unlink()
        except OSError:
            continue
        total -= size
        result["freed_bytes"] += size
        result["removed"] += 1
    result["total_bytes"] = total
    return result


_metadata_cache = OrderedDict()
_metadata_lock = threading.Lock()


def _row(target):
    stat = target.stat()
    signature = (str(target), stat.st_mtime_ns, stat.st_size)
    with _metadata_lock:
        if signature in _metadata_cache:
            _metadata_cache.move_to_end(signature)
            return _metadata_cache[signature]
    doc = json.loads(target.read_text(encoding="utf-8"))
    archive = doc.get("meta", {}).get("archive")
    if not (isinstance(archive,dict) and isinstance(archive.get("id"),str) and type(archive.get("part")) is int and 1 <= archive["part"] <= 2**53-1):
        archive = None
    row = {"file":target.name, "title":doc.get("meta", {}).get("title"),
           "contexts":[{k:segment.get(k) or doc.get("meta", {}).get(k) or "unknown" for k in ("encounter_type", "game_patch", "difficulty")} for segment in doc["segments"]],
           "unfinished":bool(doc.get("meta", {}).get("capture_active")),
           "archive":archive, "checkpoint_at":doc.get("meta", {}).get("checkpoint_at"),
           "updated":stat.st_mtime, "players":len(doc["players"]), "segments":len(doc["segments"]),
           "duration":sum(segment["duration"] for segment in doc["segments"])}
    with _metadata_lock:
        _metadata_cache[signature] = row
        while len(_metadata_cache)>2048:
            _metadata_cache.popitem(last=False)
    return row


def recent_page(offset: int = 0, limit: int = 25, archive: str = "") -> dict:
    if not 0 <= offset <= 10_000_000 or not 1 <= limit <= 100:
        raise ValueError("Invalid session page")
    if not isinstance(archive,str) or len(archive)>100:
        raise ValueError("Invalid recording ID")
    targets = []
    for target in logs_dir().glob("session-*.a2log.json"):
        try:
            targets.append((target.stat().st_mtime, target.name, target))
        except OSError:
            continue
    targets.sort(reverse=True)
    rows = []
    candidates = targets if archive else targets[offset:offset+limit]
    for _, _, target in candidates:
        try:
            row = _row(target)
            if not archive or isinstance(row.get("archive"),dict) and row["archive"].get("id")==archive:
                rows.append(row)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    if archive:
        from .archive import describe
        parts = {}
        for row in rows:
            parts.setdefault(row["archive"]["part"], []).append(row)
        rows = [{**row, "continuity_status":describe(row["archive"],
                 parts[row["archive"]["part"]-1][0]["archive"]
                 if len(parts.get(row["archive"]["part"]-1, [])) == 1 else None,
                 len(parts[row["archive"]["part"]]) > 1)} for row in rows]
        rows.sort(key=lambda row:(row["archive"].get("part",0), row["file"]))
        count = len(rows)
        rows = rows[offset:offset+limit]
    else:
        count = len(targets)
    return {"rows":rows, "offset":offset, "limit":limit, "has_more":offset+limit<count,
            "file_count":count, "archive":archive or None}


def recent() -> list[dict]:
    return recent_page(limit=100)["rows"]


def reconstruct(name, first, last):
    from .reconstruction import combine, part_range, MAX_BYTES
    selected = set(part_range(first, last))
    anchor = _row(path(name))
    archive = anchor.get("archive")
    if not archive:
        raise ValueError("This recording has no archive-part metadata")
    rows = recent_page(limit=100, archive=archive["id"])
    if rows["has_more"]:
        raise ValueError("Recording has too many files for an unambiguous combined review")
    chosen = [r for r in rows["rows"] if r["archive"]["part"] in selected]
    if len(chosen) != len(selected) or len({r["archive"]["part"] for r in chosen}) != len(selected):
        raise ValueError("Selected parts are missing or duplicated on this computer")
    sources, total = [], 0
    for row in chosen:
        with path(row["file"]).open("rb") as stream:
            raw = stream.read(MAX_BYTES-total+1)
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError("Combined review exceeds 64 MiB; choose a shorter range")
        doc = json.loads(raw)
        if (doc.get("meta", {}).get("archive", {}).get("id") != archive["id"] or doc.get("meta", {}).get("archive", {}).get("part") != row["archive"]["part"]):
            raise ValueError("A recording changed while loading; refresh and try again")
        sources.append(({"file":row["file"]}, doc))
    return combine(sources)
