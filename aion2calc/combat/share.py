"""Upload a saved fight to a log server (yours, or any server that speaks a2log).

The server address and upload key are kept in the user folder
(``data/logserver.json``); set them in the app (Combat Logs page) or with
``python -m aion2calc share --server https://logs.example.com --key a2l_...``.
"""
from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request

from ..db import store
from ..logserver.format import from_encounter, validate
from ..paths import data_file, read_json, write_user_json

_FILE = ("logserver.json",)


def settings() -> dict:
    return read_json(*_FILE) if data_file(*_FILE).exists() else {}


def save_settings(url: str | None = None, key: str | None = None, visibility: str | None = None) -> dict:
    s = settings()
    if url is not None:
        s["url"] = url.rstrip("/")
    if key is not None:
        s["key"] = key
    if visibility is not None:
        s["visibility"] = visibility
    write_user_json(s, *_FILE)
    return s


def discover(url: str) -> dict:
    """The server's /.well-known/a2log.json (upload URL, auth, limits)."""
    with urllib.request.urlopen(url.rstrip("/") + "/.well-known/a2log.json", timeout=20) as r:
        return json.load(r)


def upload(doc: dict, url: str | None = None, key: str | None = None, visibility: str | None = None) -> dict:
    s = settings()
    url = (url or s.get("url") or "").rstrip("/")
    key = key or s.get("key")
    vis = visibility or s.get("visibility") or "unlisted"
    if not url:
        raise ValueError("no log server set: pass --server (or set it on the Combat Logs page)")
    doc = validate(doc)
    try:
        target = discover(url).get("upload_url") or url + "/api/v1/logs"
    except Exception:
        target = url + "/api/v1/logs"
    body = gzip.compress(json.dumps(doc, separators=(",", ":")).encode())
    headers = {"Content-Type": "application/json", "Content-Encoding": "gzip", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(f"{target}?visibility={vis}", body, headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(msg).get("error", msg)
        except ValueError:
            pass
        raise RuntimeError(f"upload refused ({e.code}): {msg}") from None


def share_encounter(enc_id: int, **kw) -> dict:
    enc = store.encounter(store.connect(), enc_id)
    if not enc:
        raise FileNotFoundError(f"no encounter {enc_id}")
    res = upload(from_encounter(enc), **kw)
    links = settings().get("shared", {})
    links[str(enc_id)] = res.get("url")
    s = settings()
    s["shared"] = links
    write_user_json(s, *_FILE)
    return res
