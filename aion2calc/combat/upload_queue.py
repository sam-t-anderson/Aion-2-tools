"""Bounded upload recovery metadata. Never stores upload or owner credentials."""
import json
import re
import threading
from urllib.parse import urlsplit

from ..paths import data_file, read_json, write_user_json

LOCK = threading.RLock()
FILE = ("upload-queue.json",)


def clean(value):
    if not isinstance(value, dict) or value.get("format") != "a2log-upload-checkpoint" or value.get("version") != 1:
        raise ValueError("Choose an upload recovery checkpoint")
    if len(json.dumps(value, ensure_ascii=False).encode()) > 256 * 1024:
        raise ValueError("Upload recovery checkpoint exceeds 256 KiB")
    server = str(value.get("server") or "").rstrip("/")
    url = urlsplit(server)
    if server and (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment):
        raise ValueError("Invalid checkpoint server")
    visibility = value.get("visibility", "unlisted")
    if visibility not in ("public", "unlisted", "private"):
        raise ValueError("Invalid checkpoint visibility")
    rows = value.get("parts")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("A recovery checkpoint supports at most 100 files")
    parts, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid recovery file")
        file = row.get("file")
        if not isinstance(file, str) or not file or len(file) > 1024 or file in seen:
            raise ValueError("Invalid or duplicate recovery filename")
        seen.add(file)
        fingerprint = row.get("fingerprint")
        if fingerprint is not None and (not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)):
            raise ValueError("Invalid file fingerprint")
        status = row.get("status", "pending")
        if status not in ("pending", "uploading", "unknown", "failed", "uploaded"):
            raise ValueError("Invalid recovery status")
        log_id = row.get("id")
        if log_id is not None and (not isinstance(log_id, str) or not re.fullmatch(r"[A-Za-z0-9]{6,16}", log_id)):
            raise ValueError("Invalid uploaded report ID")
        if status == "uploaded" and (not fingerprint or not log_id or not server):
            raise ValueError("Successful recovery records require a server, report ID and fingerprint")
        parts.append({"file": file, "name": str(row.get("name") or file)[:1024],
                      "title": str(row.get("title") or file)[:200], "fingerprint": fingerprint,
                      "status": status, "id": log_id})
    return {"format": "a2log-upload-checkpoint", "version": 1, "server": server,
            "visibility": visibility, "parts": parts}


def load():
    with LOCK:
        return clean(read_json(*FILE)) if data_file(*FILE).exists() else None


def save(value):
    value = clean(value)
    with LOCK:
        write_user_json(value, *FILE)
    return value
