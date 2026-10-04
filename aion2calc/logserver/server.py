"""aion2calc log server: upload fights in the open a2log format, share them by link.

Run it on your own server (see ``docs/logserver.md`` for Ubuntu + nginx)::

    python -m aion2calc.logserver keys create "my meter"      # prints an upload key once
    python -m aion2calc.logserver serve --data /var/lib/aion2calc-logs --public-url https://logs.example.com

Endpoints

    GET  /.well-known/a2log.json          discovery: upload URL, schema, auth, limits
    GET  /schema/a2log-v1.json            JSON Schema of an upload
    GET  /docs                            the format and the API for other apps' developers
    POST /api/v1/logs                     upload (Authorization: Bearer <key>; JSON, optionally gzip)
    GET  /api/v1/logs                     public logs (page, limit, boss)
    GET  /api/v1/logs/<id>                a log's summary        (?t=<token> for private logs)
    GET  /api/v1/logs/<id>/raw            the a2log document
    GET  /api/v1/logs/<id>/analysis       one player's breakdown (?segment=0&player=<id>)
    DELETE /api/v1/logs/<id>              delete (the uploader's key, or ?token=<delete token>)
    GET  /l/<id>                          the log viewer page anyone with the link can open
"""
from __future__ import annotations

import gzip
import html
import io
import json
import os
import re
import threading
import urllib.parse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import format as F
from .store import Store

STATIC = Path(__file__).resolve().parent / "static"
APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "app.css"
ID = re.compile(r"^[A-Za-z0-9]{6,16}$")


class Config:
    def __init__(self, data: str, public_url: str = "", allow_anonymous: bool = False,
                 max_bytes: int = 25 * 1024 * 1024, uploads_per_hour: int = 120, trust_proxy: bool = False,
                 name: str = "aion2calc logs"):
        self.store = Store(data)
        self.public_url = public_url.rstrip("/")
        self.allow_anonymous = allow_anonymous
        self.max_bytes = max_bytes
        self.uploads_per_hour = uploads_per_hour
        self.trust_proxy = trust_proxy
        self.name = name


CONFIG: Config | None = None
_ANALYSIS: OrderedDict = OrderedDict()
_LOCK = threading.Lock()


def summarize(doc: dict) -> dict:
    segs = doc["segments"]
    names = {p["id"]: p for p in doc["players"]}
    main = max(range(len(segs)), key=lambda i: (bool(segs[i].get("boss")), segs[i]["duration"]))
    per = {}
    for h in segs[main]["hits"]:
        per[h["player"]] = per.get(h["player"], 0.0) + h["damage"]
    dur = segs[main]["duration"]
    players = sorted(({"id": pid, "name": names[pid]["name"], "class": names[pid].get("class"),
                       "damage": per.get(pid, 0.0), "dps": per.get(pid, 0.0) / dur} for pid in names),
                     key=lambda p: -p["damage"])
    boss = segs[main].get("boss") or segs[main].get("label")
    meta = doc.get("meta") or {}
    return {"title": meta.get("title") or boss or "Fight", "boss": boss, "region": meta.get("region"),
            "source": meta.get("source"), "duration": dur, "players": players,
            "top_dps": players[0]["dps"] if players else 0.0, "segments": len(segs), "main_segment": main}


def analysis(log_id: str, doc: dict, segment: int, player: str) -> dict:
    key = (log_id, segment, player)
    with _LOCK:
        if key in _ANALYSIS:
            _ANALYSIS.move_to_end(key)
            return _ANALYSIS[key]
    from ..combat.analyze import analyze
    enc = F.to_encounter(doc, player, segment)
    a = analyze(enc)
    a["specs"] = enc.get("specs", {})
    a = json.loads(json.dumps(a, default=str))
    with _LOCK:
        _ANALYSIS[key] = a
        while len(_ANALYSIS) > 256:
            _ANALYSIS.popitem(last=False)
    return a


class Handler(BaseHTTPRequestHandler):
    server_version = "aion2calc-logs"

    def log_message(self, fmt, *args):
        pass

    # ------------------------------------------------------------ plumbing
    @property
    def cfg(self) -> Config:
        return CONFIG

    def _ip(self) -> str:
        if self.cfg.trust_proxy and self.headers.get("X-Forwarded-For"):
            return self.headers["X-Forwarded-For"].split(",")[0].strip()
        return self.client_address[0]

    def _base(self) -> str:
        if self.cfg.public_url:
            return self.cfg.public_url
        host = self.headers.get("Host") or "localhost"
        proto = self.headers.get("X-Forwarded-Proto", "http") if self.cfg.trust_proxy else "http"
        return f"{proto}://{host}"

    def _send(self, code: int, body: bytes, ctype: str, cache: int = 0, cors: bool = False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; "
                                                         "style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", f"public, max-age={cache}" if cache else "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200, cache: int = 0):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json", cache, cors=True)

    def _err(self, code: int, msg: str):
        self._json({"error": msg}, code)

    def _token(self) -> str | None:
        a = self.headers.get("Authorization") or ""
        return a[7:].strip() if a.lower().startswith("bearer ") else None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Content-Encoding")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            self.route_get(url.path, q)
        except FileNotFoundError:
            self._err(404, "not found")
        except PermissionError as e:
            self._err(403, str(e) or "forbidden")
        except Exception as e:                       # noqa: BLE001 - report, keep serving
            self._err(500, f"{type(e).__name__}: {e}")

    def do_POST(self):
        try:
            if urllib.parse.urlparse(self.path).path != "/api/v1/logs":
                return self._err(404, "not found")
            self.upload()
        except F.Invalid as e:
            self._err(400, str(e))
        except Exception as e:                       # noqa: BLE001
            self._err(500, f"{type(e).__name__}: {e}")

    def do_DELETE(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        m = re.fullmatch(r"/api/v1/logs/([A-Za-z0-9]+)", url.path)
        if not m:
            return self._err(404, "not found")
        st = self.cfg.store
        if not st.check_delete(m.group(1), q.get("token"), st.key_of(self._token())):
            return self._err(403, "send the uploader's key or the delete token")
        st.delete(m.group(1))
        self._json({"deleted": m.group(1)})

    # ------------------------------------------------------------ upload
    def upload(self):
        st = self.cfg.store
        key = st.key_of(self._token())
        if key is None and not self.cfg.allow_anonymous:
            return self._err(401, "an upload key is required: Authorization: Bearer <key>")
        bucket = f"key:{key['id']}" if key else f"ip:{self._ip()}"
        if not st.allow(bucket, self.cfg.uploads_per_hour if key else max(5, self.cfg.uploads_per_hour // 10)):
            return self._err(429, "too many uploads, try again later")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self._err(411, "Content-Length is required")
        if n > self.cfg.max_bytes:
            return self._err(413, f"the upload is larger than {self.cfg.max_bytes} bytes")
        raw = self.rfile.read(n)
        if (self.headers.get("Content-Encoding") or "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
            d = gzip.GzipFile(fileobj=io.BytesIO(raw))
            raw = d.read(self.cfg.max_bytes * 4 + 1)
            if len(raw) > self.cfg.max_bytes * 4:
                return self._err(413, "the decompressed upload is too large")
        try:
            doc = json.loads(raw)
        except ValueError:
            return self._err(400, "the body is not valid JSON")
        doc = F.validate(doc)
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        vis = q.get("visibility") or doc["meta"].get("visibility") or "unlisted"
        if vis not in ("public", "unlisted", "private"):
            return self._err(400, "visibility must be public, unlisted or private")
        summary = summarize(doc)
        r = st.put(doc, summary, vis, key and key["id"], self._ip())
        learned = 0
        if vis != "private" and doc["meta"].get("contribute") != "no":
            try:                                       # community statistics never block an upload
                from .learn import observe_doc
                rows = observe_doc(doc)
                st.put_observations(r["id"], rows)
                learned = len(rows)
            except Exception:
                learned = 0
        base = self._base()
        suffix = f"?t={r['view_token']}" if r["view_token"] else ""
        self._json({"id": r["id"], "visibility": vis, "url": f"{base}/l/{r['id']}{suffix}",
                    "json_url": f"{base}/api/v1/logs/{r['id']}/raw{suffix}",
                    "delete_url": f"{base}/api/v1/logs/{r['id']}?token={r['delete_token']}",
                    "delete_token": r["delete_token"], "summary": summary, "learned_from": learned}, 201)

    # ------------------------------------------------------------ reads
    def _visible(self, log_id: str, q: dict) -> dict:
        if not ID.match(log_id):
            raise FileNotFoundError(log_id)
        r = self.cfg.store.row(log_id)
        if not r:
            raise FileNotFoundError(log_id)
        if r["visibility"] == "private":
            key = self.cfg.store.key_of(self._token())
            if q.get("t") != r["view_token"] and not (key and key["id"] == r["key_id"]):
                raise PermissionError("this log is private")
        return r

    def route_get(self, path: str, q: dict):
        st = self.cfg.store
        if path in ("/", "/index.html"):
            return self._page("index.html", {"TITLE": self.cfg.name, "DESC": "AION 2 combat logs"})
        if path == "/docs":
            return self._page("docs.html", {"TITLE": f"{self.cfg.name}: upload format", "BASE": self._base(),
                                            "ANON": "allowed" if self.cfg.allow_anonymous else "not allowed",
                                            "MAXMB": str(self.cfg.max_bytes // (1024 * 1024)),
                                            "DESC": "The a2log format and upload API"})
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            if name == "app.css":
                return self._send(200, APP_CSS.read_bytes(), "text/css; charset=utf-8", 3600)
            p = (STATIC / name).resolve()
            if not p.is_relative_to(STATIC) or not p.is_file() or p.suffix not in (".js", ".css", ".svg"):
                raise FileNotFoundError(name)
            ctype = {"js": "text/javascript", "css": "text/css", "svg": "image/svg+xml"}[p.suffix[1:]]
            return self._send(200, p.read_bytes(), ctype + "; charset=utf-8", 3600)
        if path == "/.well-known/a2log.json":
            b = self._base()
            return self._json({"name": self.cfg.name, "format": "a2log", "versions": [F.VERSION],
                               "upload_url": f"{b}/api/v1/logs", "method": "POST",
                               "schema_url": f"{b}/schema/a2log-v1.json", "docs_url": f"{b}/docs",
                               "auth": {"type": "bearer", "header": "Authorization",
                                        "required": not self.cfg.allow_anonymous},
                               "content_types": ["application/json"], "content_encodings": ["gzip"],
                               "max_bytes": self.cfg.max_bytes, "visibility": ["public", "unlisted", "private"],
                               "view_url": f"{b}/l/{{id}}", "list_url": f"{b}/api/v1/logs",
                               "stats_url": f"{b}/api/v1/stats/{{class}}",
                               "calibration_url": f"{b}/api/v1/calibration/{{class}}"}, cache=300)
        if path == "/stats":
            return self._page("stats.html", {"TITLE": f"{self.cfg.name}: class statistics",
                                             "DESC": "What uploaded AION 2 fights show, per class"})
        if path == "/api/v1/stats":
            return self._json({"classes": st.class_counts()}, cache=60)
        m = re.fullmatch(r"/api/v1/(stats|calibration)/([a-z]+)", path)
        if m:
            from . import learn as L
            cls, boss = m.group(2), q.get("boss") or None
            key = (m.group(1), cls, boss, st.version)
            with _LOCK:
                hit = _ANALYSIS.get(key)
            if hit is None:
                rows = st.observations(cls, boss)
                hit = L.aggregate(rows) if m.group(1) == "stats" else L.calibration(cls, rows, self._base())
                if m.group(1) == "stats":
                    hit["class"], hit["boss"] = cls, boss
                with _LOCK:
                    _ANALYSIS[key] = hit
            return self._json(hit, cache=300)
        if path == "/schema/a2log-v1.json":
            return self._json({**F.SCHEMA, "$id": f"{self._base()}/schema/a2log-v1.json"}, cache=3600)
        if path == "/api/v1/logs":
            page = max(1, int(q.get("page", 1)))
            limit = min(100, max(1, int(q.get("limit", 30))))
            rows, total = st.public(page, limit, q.get("boss"))
            return self._json({"logs": rows, "total": total, "page": page, "limit": limit})
        m = re.fullmatch(r"/api/v1/logs/([A-Za-z0-9]+)(/raw|/analysis)?", path)
        if m:
            r = self._visible(m.group(1), q)
            if m.group(2) == "/raw":
                return self._json(st.doc(r["id"]), cache=86400)
            if m.group(2) == "/analysis":
                doc = st.doc(r["id"])
                seg = int(q.get("segment", 0))
                if not 0 <= seg < len(doc["segments"]):
                    raise FileNotFoundError("segment")
                pid = q.get("player") or doc["players"][0]["id"]
                if pid not in {p["id"] for p in doc["players"]}:
                    raise FileNotFoundError("player")
                return self._json(analysis(r["id"], doc, seg, pid), cache=86400)
            doc = st.doc(r["id"])
            segs = [{"index": i, "id": s["id"], "label": s.get("label"), "boss": s.get("boss"),
                     "duration": s["duration"], "killed": s.get("killed"),
                     "players": _seg_players(doc, s)} for i, s in enumerate(doc["segments"])]
            return self._json({k: r[k] for k in ("id", "created_at", "visibility", "title", "boss", "region",
                                                  "source", "duration", "players", "top_dps")}
                              | {"meta": doc.get("meta"), "segments": segs,
                                 "roster": doc["players"]}, cache=60)
        m = re.fullmatch(r"/l/([A-Za-z0-9]+)", path)
        if m:
            r = self._visible(m.group(1), q)
            top = r["players"][0] if r["players"] else {}
            desc = (f"{r['boss'] or ''} · {r['duration']:.0f}s · top {top.get('name', '')} "
                    f"{top.get('dps', 0):,.0f} DPS · {len(r['players'])} players")
            return self._page("view.html", {"TITLE": f"{r['title']} — {self.cfg.name}", "DESC": desc,
                                            "URL": f"{self._base()}/l/{r['id']}"})
        raise FileNotFoundError(path)

    def _page(self, name: str, values: dict):
        t = (STATIC / name).read_text(encoding="utf-8")
        for k, v in values.items():
            t = t.replace("{{" + k + "}}", html.escape(str(v), quote=True))
        self._send(200, t.encode(), "text/html; charset=utf-8")


def _seg_players(doc: dict, seg: dict) -> list[dict]:
    names = {p["id"]: p for p in doc["players"]}
    per: dict = {}
    for h in seg["hits"]:
        d = per.setdefault(h["player"], {"damage": 0.0, "hits": 0, "crit": 0})
        d["damage"] += h["damage"]
        d["hits"] += 1
        d["crit"] += 1 if h.get("crit") else 0
    total = sum(d["damage"] for d in per.values()) or 1.0
    return sorted(({"id": pid, "name": names[pid]["name"], "class": names[pid].get("class"),
                    "combat_power": names[pid].get("combat_power"), "damage": d["damage"],
                    "dps": d["damage"] / seg["duration"], "share": d["damage"] / total,
                    "crit": d["crit"] / d["hits"] if d["hits"] else 0.0} for pid, d in per.items()),
                  key=lambda p: -p["damage"])


def serve(data: str, host: str = "127.0.0.1", port: int = 8780, **kw) -> None:
    global CONFIG
    CONFIG = Config(data, **kw)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"aion2calc log server on http://{host}:{port}/  data: {Path(data).resolve()}"
          f"  anonymous uploads: {'on' if CONFIG.allow_anonymous else 'off'}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def env_defaults() -> dict:
    """Settings from the environment (used by the systemd unit)."""
    e = os.environ
    return {"data": e.get("A2LOGS_DATA", "./a2logs-data"), "host": e.get("A2LOGS_HOST", "127.0.0.1"),
            "port": int(e.get("A2LOGS_PORT", "8780")), "public_url": e.get("A2LOGS_PUBLIC_URL", ""),
            "allow_anonymous": e.get("A2LOGS_ALLOW_ANONYMOUS", "0") == "1",
            "max_bytes": int(e.get("A2LOGS_MAX_MB", "25")) * 1024 * 1024,
            "uploads_per_hour": int(e.get("A2LOGS_UPLOADS_PER_HOUR", "120")),
            "trust_proxy": e.get("A2LOGS_TRUST_PROXY", "0") == "1", "name": e.get("A2LOGS_NAME", "aion2calc logs")}

