"""Full party logs on disk, separate from single-player analysis imports."""
import json
import os
import tempfile
from pathlib import Path

from ..paths import logs_dir


def path(name: str) -> Path:
    if not name.startswith("session-") or not name.endswith(".a2log.json") or Path(name).name != name:
        raise ValueError("Invalid session filename")
    return logs_dir() / name


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


def recent_page(offset: int = 0, limit: int = 25) -> dict:
    if not 0 <= offset <= 10_000_000 or not 1 <= limit <= 100:
        raise ValueError("Invalid session page")
    targets = []
    for target in logs_dir().glob("session-*.a2log.json"):
        try:
            targets.append((target.stat().st_mtime, target.name, target))
        except OSError:
            continue
    targets.sort(reverse=True)
    rows = []
    for _, _, target in targets[offset:offset + limit]:
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
            rows.append({"file": target.name, "title": doc.get("meta", {}).get("title"),
                         "contexts": [{k: segment.get(k) or doc.get("meta", {}).get(k) or "unknown" for k in ("encounter_type", "game_patch", "difficulty")} for segment in doc["segments"]],
                         "unfinished": bool(doc.get("meta", {}).get("capture_active")),
                         "archive": doc.get("meta", {}).get("archive"),
                         "checkpoint_at": doc.get("meta", {}).get("checkpoint_at"),
                         "updated": target.stat().st_mtime, "players": len(doc["players"]),
                         "segments": len(doc["segments"]), "duration": sum(s["duration"] for s in doc["segments"])})
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return {"rows":rows, "offset":offset, "limit":limit, "has_more":offset + limit < len(targets), "file_count":len(targets)}


def recent() -> list[dict]:
    return recent_page(limit=100)["rows"]
