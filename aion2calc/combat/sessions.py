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


def recent() -> list[dict]:
    rows = []
    for target in sorted(logs_dir().glob("session-*.a2log.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
            rows.append({"file": target.name, "title": doc.get("meta", {}).get("title"),
                         "contexts": [{k: segment.get(k) or doc.get("meta", {}).get(k) or "unknown" for k in ("encounter_type", "game_patch", "difficulty")} for segment in doc["segments"]],
                         "unfinished": bool(doc.get("meta", {}).get("capture_active")),
                         "archive": doc.get("meta", {}).get("archive"),
                         "checkpoint_at": doc.get("meta", {}).get("checkpoint_at"),
                         "updated": target.stat().st_mtime, "players": len(doc["players"]),
                         "segments": len(doc["segments"]), "duration": sum(s["duration"] for s in doc["segments"])})
        except (OSError, ValueError, KeyError):
            continue
    return rows
