"""Durable local result snapshots; imported documents never execute a job."""
import hashlib
import json
import os
import time
import uuid

from ..paths import home, results_dir

KINDS = ("optimize-character", "optimize-class", "advice", "advice-text")
MAX_BYTES = 20 * 1024 * 1024


def folder():
    target = home() / "history"
    target.mkdir(parents=True, exist_ok=True)
    return target


def path(identifier):
    if not isinstance(identifier, str) or len(identifier) != 24 or any(c not in "0123456789abcdef" for c in identifier):
        raise ValueError("Invalid history ID")
    return folder() / (identifier + ".json")


def validate(doc):
    if not isinstance(doc, dict) or doc.get("format") != "a2result" or doc.get("version") != 1 or doc.get("kind") not in KINDS or not isinstance(doc.get("result"), dict):
        raise ValueError("Choose an exported Aion 2 Calc result JSON")
    result = doc["result"]
    if doc["kind"] == "optimize-character" and not isinstance(result.get("optimized"), dict):
        raise ValueError("Missing optimized build")
    if doc["kind"] == "optimize-class" and not isinstance(result.get("skills"), dict):
        raise ValueError("Missing build skill view")
    if doc["kind"] == "advice" and not all(k in result for k in ("character", "doll", "rotation", "genus", "calibration")):
        raise ValueError("Missing advice data")
    return {"format": "a2result", "version": 1, "kind": doc["kind"], "title": str(doc.get("title") or doc["kind"])[:200],
            "created": doc.get("created") if isinstance(doc.get("created"), (int, float)) else time.time(), "result": result}


def save(doc, identifier=None):
    doc = validate(doc)
    identifier = identifier or uuid.uuid4().hex[:24]
    target = path(identifier)
    raw = json.dumps(doc, ensure_ascii=False, allow_nan=False)
    if len(raw.encode()) > MAX_BYTES:
        raise ValueError("Result exceeds 20 MiB")
    tmp = target.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, target)
    return identifier


def capture(kind, result):
    character = result.get("character") or result.get("summary", {}).get("character") or {}
    mode = (result.get("summary") or {}).get("scenario", result.get("scenario", "boss"))
    title = (character.get("name") or result.get("class") or "Build") + " · " + ("PvP (experimental)" if mode == "pvp" else "PvE") + " · " + kind.replace("-", " ")
    return save({"format": "a2result", "version": 1, "kind": kind, "title": title, "created": time.time(), "result": result})


def recent():
    rows = []
    for target in folder().glob("*.json"):
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
            rows.append({"id": target.stem, **{k: doc[k] for k in ("kind", "title", "created")}})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(rows, key=lambda r: r["created"], reverse=True)


def discover_legacy():
    """Recover the latest old build/advice files that were written before snapshots."""
    from .views import build_view
    for target in results_dir().glob("**/build.json"):
        identifier = hashlib.sha256(str(target).encode()).hexdigest()[:24]
        if path(identifier).exists():
            continue
        try:
            summary = json.loads(target.read_text(encoding="utf-8"))
            if summary.get("kind") == "current" or not summary.get("class"):
                continue
            save({"format": "a2result", "version": 1, "kind": "optimize-class", "title": summary["class"] + " · recovered build",
                  "created": target.stat().st_mtime, "result": build_view(summary)}, identifier)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    advice_sources = set(results_dir().glob("**/ADVICE.md"))
    advice_sources.update(p.with_name("ADVICE.md") for p in results_dir().glob("**/advice.json"))
    for target in sorted(advice_sources):
        identifier = hashlib.sha256(str(target).encode()).hexdigest()[:24]
        existing = None
        try:
            if path(identifier).exists():
                existing = json.loads(path(identifier).read_text(encoding="utf-8"))
                if existing.get("kind") != "advice-text":
                    continue
            structured = target.with_name("advice.json")
            if structured.exists():
                result = json.loads(structured.read_text(encoding="utf-8"))
                save({"format":"a2result", "version":1, "kind":"advice",
                      "title":target.parent.name + " · recovered advice",
                      "created":existing["created"] if existing else structured.stat().st_mtime,
                      "result":result}, identifier)
                continue
        except (OSError, ValueError, KeyError, TypeError):
            pass  # Keep a readable legacy report if its sidecar is absent or damaged.
        if not path(identifier).exists() and target.exists():
            try:
                save({"format": "a2result", "version": 1, "kind": "advice-text", "title": target.parent.name + " · recovered advice",
                      "created": target.stat().st_mtime, "result": {"text": target.read_text(encoding="utf-8")}}, identifier)
            except (OSError, ValueError):
                continue
