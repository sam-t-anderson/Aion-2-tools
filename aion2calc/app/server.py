"""Local app server (standard library only).

    python -m aion2calc app          # opens http://127.0.0.1:8765

On launch it starts the database sync in the background (new items, skills,
classes), serves the game-styled UI from ``app/static`` and a small JSON API.
Long jobs (optimizing a character) run in worker threads; the UI polls them.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..paths import home, list_names, logs_dir, results_dir
from . import views

STATIC = Path(__file__).resolve().parent / "static"
mimetypes.add_type("font/woff2", ".woff2")
ICON_HOSTS = ("metabot.gg", "assets.playnccdn.com", "profileimg.plaync.com", "a2dil.com")

SYNC = {"sync": None, "thread": None}
JOBS: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ----------------------------------------------------------------------- jobs
def start_job(kind: str, fn, *args, **kwargs) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "status": "running", "started": time.time(), "log": [], "result": None}
    with _jobs_lock:
        JOBS[jid] = job

    def run():
        try:
            job["result"] = fn(*args, log=job["log"].append, **kwargs)
            job["status"] = "done"
        except Exception as err:
            job["status"] = "error"
            job["error"] = f"{type(err).__name__}: {err}"
            job["log"].append(traceback.format_exc())
        job["finished"] = time.time()

    threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
    return jid


def start_sync(force: bool = False, budget_s: float | None = 900) -> None:
    from ..db.sync import Sync
    cur = SYNC.get("sync")
    if cur and cur.state.running:
        return
    s = Sync(force=force, budget_s=budget_s)
    SYNC["sync"], SYNC["thread"] = s, s.start_background()


# -------------------------------------------------------------------- actions
def _summary_at(path: str) -> dict:
    p = Path(path) / "build.json"
    if not any(p.resolve().is_relative_to(r.resolve()) for r in views.result_roots()) or not p.exists():
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


def act_character_import(body: dict, log) -> dict:
    from ..charopt import evaluate_current, import_character
    log("importing from the official site")
    imp = import_character(body["character_id"], int(body["server_id"]), body.get("region", "nae"),
                           progress=log, use_cache=float(body.get("cache", 0)))
    log("scoring the build as it is")
    ev = evaluate_current(imp)
    return views.character_view(imp, ev)


def act_character_optimize(body: dict, log) -> dict:
    from ..charopt import import_character, optimize_character
    imp = import_character(body["character_id"], int(body["server_id"]), body.get("region", "nae"),
                           progress=log, use_cache=3600)
    out = results_dir() / "characters" / imp.loadout_name()[5:]
    log(f"optimizing under the same resources (writes {out})")
    summ = optimize_character(imp, str(out), iterations=int(body.get("iterations", 2)))
    best = json.loads((out / "build.json").read_text(encoding="utf-8"))
    cur = json.loads((out / "current" / "build.json").read_text(encoding="utf-8"))
    return {"summary": summ, "optimized": views.build_view(best), "current_build": cur["build"],
            "path": str(out), "diff": (out / "DIFF.md").read_text(encoding="utf-8")}


def act_optimize_class(body: dict, log) -> dict:
    from ..report import run_report
    cls = body["class"]
    out = results_dir() / (body.get("out") or f"{cls}_l45")
    if not out.resolve().is_relative_to(results_dir().resolve()):
        raise ValueError("out must stay inside the results folder")
    log(f"optimizing {cls} (this takes several minutes)")
    run_report(cls, str(out), iterations=int(body.get("iterations", 2)), loadout=body.get("loadout"),
               sp_budget=body.get("skill_points"), stigma_points=body.get("stigma_points"),
               daev_budget=int(body.get("daevanion", 360)), verbose=False)
    return views.build_view(_summary_at(str(out)))


def encounter_view(enc_id: int) -> dict:
    from ..combat.analyze import analyze, vs_optimal, vs_top
    from ..db import store
    enc = store.encounter(store.connect(), enc_id)
    if not enc:
        raise FileNotFoundError(enc_id)
    a = analyze(enc)
    try:
        a["vs_optimal"] = vs_optimal(enc)
    except Exception as err:
        a["vs_optimal"] = {"error": str(err)}
    try:
        a["vs_top"] = vs_top(enc)
    except Exception as err:
        a["vs_top"] = {"error": str(err)}
    a["id"] = enc_id
    from ..combat.logs import path_of
    f = path_of(enc_id)
    a["file"] = str(f) if f else None
    return a


def act_encounter_import(body: dict, log) -> dict:
    from ..combat import adapters, logs
    player = body.get("player") or None
    if body.get("ref"):
        log("reading the log")
        enc = adapters.load(body["ref"].strip(), player=player)
    elif body.get("text"):
        enc = adapters.from_text(body["text"], name=body.get("name"), player=player)
    else:
        raise ValueError("send a log link (ref) or file contents (text)")
    eid, path = logs.save(enc)
    log(f"saved to {path}")
    try:
        from .. import learn
        learn.update(eid)
    except Exception as err:                  # learning never blocks an import
        log(f"not used for calibration: {err}")
    log("analyzing")
    return encounter_view(eid)


_UPDATE: dict = {}
#: the latest published release of the app (GitHub's public API, no account needed)
RELEASES_API = "https://api.github.com/repos/sam-t-anderson/Aion-2-tools/releases/latest"


def update_info(wait: bool = False) -> dict | None:
    """A newer release of the app, checked in the background every 6 hours so a slow or
    unreachable network never holds up the page."""
    if time.time() - _UPDATE.get("at", 0) >= 6 * 3600:
        _UPDATE["at"] = time.time()
        t = threading.Thread(target=_check_update, daemon=True)
        t.start()
        if wait:
            t.join()
    return _UPDATE.get("info")


def _check_update() -> None:
    info = None
    try:
        from .. import __version__
        req = urllib.request.Request(RELEASES_API, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": f"aion2calc/{__version__}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            rel = json.load(r)
        version = str(rel.get("tag_name") or "").lstrip("v")
        if version and _vt(version) > _vt(__version__):
            info = {"version": version, "url": rel.get("html_url")}
    except Exception:
        info = None
    _UPDATE["info"] = info


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in str(v).split(".")[:3] if x.isdigit())


def _imported(key: str):
    from ..db import store
    from ..sources.character import from_profile
    ch = store.character(store.connect(), key)
    if not ch:
        raise FileNotFoundError(f"character {key} is not imported")
    return from_profile(ch)


def _inventory(key: str) -> tuple:
    from ..plan import inventory as INV
    imp = _imported(key)
    inv = INV.from_character(imp)
    INV.save(inv)
    return imp, inv


def act_advice(body: dict, log) -> dict:
    from ..plan.advisor import advise, write_markdown
    imp, inv = _inventory(body["character"])
    adv = advise(imp, inv, progress=log, genus_mix=body.get("genus_mix"))
    out = results_dir() / "characters" / imp.loadout_name()[5:]
    adv["file"] = str(write_markdown(adv, out))
    return json.loads(json.dumps(adv, default=str))


def inventory_post(path: str, body: dict) -> dict:
    from ..plan import inventory as INV
    imp, inv = _inventory(body["character"])
    if path.endswith("/add"):
        INV.add(inv, body["slug"], int(body.get("enchant") or 0), body.get("rolls") or None,
                body.get("skills") or [], body.get("note"))
    elif path.endswith("/remove"):
        INV.remove(inv, body["id"])
    elif path.endswith("/genus"):
        inv["genus"] = body.get("genus") or {}
    elif path.endswith("/titles"):
        inv["titles_owned"] = [t.strip() for t in body.get("titles") or [] if t and t.strip()]
    INV.save(inv)
    return inv


# --------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "aion2calc"

    def log_message(self, fmt, *args):  # quiet console
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json", cache: int = 0):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", f"max-age={cache}")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, default=str, ensure_ascii=False).encode("utf-8"))

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            self.route_get(url.path, q)
        except FileNotFoundError:
            self._json({"error": "not found"}, 404)
        except Exception as err:
            self._json({"error": f"{type(err).__name__}: {err}"}, 500)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        try:
            self.route_post(url.path, self._body())
        except Exception as err:
            self._json({"error": f"{type(err).__name__}: {err}"}, 500)

    # ---------------------------------------------------------------- GET
    def route_get(self, path: str, q: dict):
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/status":
            from ..db.sync import status
            s = SYNC.get("sync")
            from .. import __version__
            return self._json({"sync": s.state.as_dict() if s else None, "db": status(), "home": str(home()),
                               "app": "aion2calc", "version": __version__, "update": update_info()})
        if path == "/api/classes":
            return self._json(list_names("global", "classes"))
        if path == "/api/results":
            return self._json(views.list_results())
        if path == "/api/build":
            return self._json(views.build_view(_summary_at(q["path"])))
        if path == "/api/character/search":
            from ..sources import official
            return self._json(official.search(q["name"], region=q.get("region", "nae")))
        if path == "/api/characters":
            from ..db import store
            return self._json(store.characters(store.connect()))
        if path == "/api/encounters":
            from ..db import store
            return self._json(store.encounters(store.connect(), q.get("class")))
        if path == "/api/inventory":
            return self._json(_inventory(q["character"])[1])
        if path == "/api/ui":
            return self._json(ui_settings())
        if path == "/api/logserver":
            from ..combat import share
            st = share.settings()
            return self._json({k: v for k, v in st.items() if k != "key"} | {"has_key": bool(st.get("key"))})
        if path == "/api/calibration":
            from .. import learn
            cal = learn.calibration(q.get("class", ""))
            return self._json({"calibration": cal, "summary": learn.summary(cal)})
        if path == "/api/logs":
            return self._json({"folder": str(logs_dir()), "files": len(list(logs_dir().glob("*.json")))})
        if path.startswith("/api/encounters/"):
            return self._json(encounter_view(int(path.rsplit("/", 1)[1])))
        if path == "/api/items":
            from ..db import store
            return self._json(store.items(store.connect(), q.get("category"), q.get("class"), q.get("search"),
                                          int(q.get("limit", 200))))
        if path.startswith("/api/items/"):
            from ..db import store
            return self._json(store.item(store.connect(), path.rsplit("/", 1)[1]) or {})
        if path.startswith("/api/jobs/"):
            job = JOBS.get(path.rsplit("/", 1)[1])
            if not job:
                raise FileNotFoundError
            return self._json({k: v for k, v in job.items() if k != "log"} | {"log": job["log"][-12:]})
        if path == "/api/icon":
            return self._icon(q.get("u", ""))
        raise FileNotFoundError(path)

    # --------------------------------------------------------------- POST
    def route_post(self, path: str, body: dict):
        if path == "/api/sync":
            start_sync(force=bool(body.get("force")), budget_s=body.get("budget", 900))
            return self._json({"ok": True})
        if path == "/api/character/import":
            return self._json({"job": start_job("import", act_character_import, body)})
        if path == "/api/character/optimize":
            return self._json({"job": start_job("optimize-character", act_character_optimize, body)})
        if path == "/api/optimize":
            return self._json({"job": start_job("optimize-class", act_optimize_class, body)})
        if path == "/api/encounters/import":
            return self._json({"job": start_job("encounter", act_encounter_import, body)})
        if path == "/api/logserver":
            from ..combat import share
            st = share.save_settings(body.get("url"), body.get("key"), body.get("visibility"))
            return self._json({k: v for k, v in st.items() if k != "key"} | {"has_key": bool(st.get("key"))})
        if path.startswith("/api/encounters/") and path.endswith("/share"):
            from ..combat import share
            return self._json(share.share_encounter(int(path.split("/")[3]), visibility=body.get("visibility")))
        if path == "/api/advice":
            return self._json({"job": start_job("advice", act_advice, body)})
        if path.startswith("/api/inventory/"):
            return self._json(inventory_post(path, body))
        if path == "/api/ping":
            PING["at"] = time.time()
            return self._json({"ok": True})
        if path == "/api/ui":
            from ..paths import write_user_json
            cur = ui_settings()
            cur.update({k: v for k, v in body.items() if k in ("app_window",)})
            write_user_json(cur, "ui.json")
            return self._json(cur)
        if path == "/api/open":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("folders open only on the computer running the app")
            from ..combat.logs import open_folder
            target = {"data": home(), "logs": logs_dir(), "results": results_dir()}.get(body.get("what"), home())
            return self._json({"folder": str(open_folder(target))})
        if path == "/api/quit":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("only the computer running the app can stop it")
            srv = HTTPD.get("server")
            if srv:
                threading.Thread(target=srv.shutdown, daemon=True).start()
            return self._json({"stopping": True})
        if path == "/api/logs/open":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("the logs folder opens only on the computer running the app")
            from ..combat.logs import open_folder
            return self._json({"folder": str(open_folder())})
        raise FileNotFoundError(path)

    # -------------------------------------------------------------- files
    def _static(self, rel: str):
        p = (STATIC / rel).resolve()
        if not p.is_relative_to(STATIC) or not p.is_file():
            raise FileNotFoundError(rel)
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        self._send(200, p.read_bytes(), ctype)

    def _icon(self, u: str):
        """Fetch and cache game icons locally so the UI keeps working offline."""
        host = urllib.parse.urlparse(u).hostname or ""
        if not any(host == h or host.endswith("." + h) for h in ICON_HOSTS):
            raise FileNotFoundError(u)
        cache = home() / "icons"
        cache.mkdir(exist_ok=True)
        f = cache / (hashlib.sha1(u.encode()).hexdigest() + Path(urllib.parse.urlparse(u).path).suffix)
        if not f.exists():
            from ..scrape.http import fetch_bytes
            data = fetch_bytes(u)
            if not data:
                raise FileNotFoundError(u)
            f.write_bytes(data)
        self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "image/png", cache=86400 * 7)


HTTPD: dict = {}
PING: dict = {"at": time.time()}


def ui_settings() -> dict:
    from ..paths import data_file, read_json
    return read_json("ui.json") if data_file("ui.json").exists() else {"app_window": True}


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    HTTPD["server"] = httpd
    return httpd


def serve(port: int = 8765, open_browser: bool = True, sync: bool = True, host: str = "127.0.0.1",
          httpd: ThreadingHTTPServer | None = None):
    if sync:
        start_sync()
    httpd = httpd or make_server(host, port)
    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/"
    try:
        from ..combat.logs import backfill
        backfill()
    except Exception as err:                  # the app still works without the files
        print("could not write the logs folder:", err)
    print(f"aion2calc app on {url}  (Ctrl+C to stop)")
    print(f"data folder: {home()}   combat logs: {logs_dir()}")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
