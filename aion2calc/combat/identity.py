"""Identity credentials for claimed characters, kept outside exported documents.

The log server issues one credential per claimed character (see the server's identity module);
it proves nothing by itself beyond "this device may act for that claim". Recovery never needs
it: the claim is re-proven from the recordings' own private credentials (the ownership backup).
"""
import re
import threading
import urllib.parse

from ..paths import data_file, read_json, write_user_json

FILE = ("identity-claims.json",)
LOCK = threading.RLock()
LIMIT = 200
TOKEN = re.compile(r"a2id_[A-Za-z0-9_-]{20,128}")


def clean(row):
    if not isinstance(row, dict):
        raise ValueError("Invalid identity credential")
    server = str(row.get("server") or "").rstrip("/")
    url = urllib.parse.urlsplit(server)
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Invalid server address")
    name = " ".join(str(row.get("name") or "").split())[:60]
    token = row.get("token")
    if not name or not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ValueError("Invalid character name or identity credential")
    claimed_at = row.get("claimed_at")
    return {"server": server, "name": name, "server_name": str(row.get("server_name") or "").strip()[:40],
            "token": token, "status": str(row.get("status") or "")[:20],
            "claimed_at": float(claimed_at) if isinstance(claimed_at, (int, float)) and not isinstance(claimed_at, bool) else 0.0}


def entries():
    with LOCK:
        rows = read_json(*FILE) if data_file(*FILE).exists() else []
        return [clean(row) for row in rows] if isinstance(rows, list) else []


def replace(rows):
    """Store the given credentials (the panel sends its whole list after every change)."""
    if not isinstance(rows, list) or len(rows) > LIMIT:
        raise ValueError(f"Identity storage holds at most {LIMIT} credentials")
    validated = [clean(row) for row in rows]
    with LOCK:
        write_user_json(validated, *FILE)
        return validated
