"""Local app server (standard library only).

    python -m aion2calc app          # opens http://127.0.0.1:8765

On launch it starts the database sync in the background (new items, skills,
classes), serves the game-styled UI from ``app/static`` and a small JSON API.
Long jobs (optimizing a character) run in worker threads; the UI polls them.
"""
from __future__ import annotations

import hashlib
from functools import wraps
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
_jobs_lock = threading.RLock()
_MODEL_LOCK = threading.RLock()
_COMPARISON_JOBS: dict[tuple[str, str], str] = {}


def _model_action(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        acquired = _MODEL_LOCK.acquire(blocking=False)
        if not acquired and kwargs.get("log"):
            kwargs["log"]("Waiting for another model calculation to finish")
        if not acquired:
            _MODEL_LOCK.acquire()
        try:
            return fn(*args, **kwargs)
        finally:
            _MODEL_LOCK.release()
    return run


# ----------------------------------------------------------------------- jobs
def start_job(kind: str, fn, *args, **kwargs) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "status": "running", "started": time.time(), "log": [], "result": None}
    with _jobs_lock:
        JOBS[jid] = job

    def run():
        try:
            job["result"] = fn(*args, log=job["log"].append, **kwargs)
            if kind in ("optimize-character", "optimize-class", "advice"):
                from .history import capture
                try:
                    job["history_id"] = capture(kind, job["result"])
                except (OSError, ValueError) as exc:
                    job["log"].append("Result completed, but could not save history: " + str(exc))
            job["status"] = "done"
        except Exception as err:
            job["status"] = "error"
            job["error"] = f"{type(err).__name__}: {err}"
            job["log"].append(traceback.format_exc())
        job["finished"] = time.time()

    threading.Thread(target=run, daemon=True, name=f"job-{kind}").start()
    return jid


def start_asset_reindex():
    from ..db.assets import reindex
    with _jobs_lock:
        for job in JOBS.values():
            if job["kind"] == "asset-reindex" and job["status"] == "running":
                return job["id"]
        return start_job("asset-reindex", reindex)


def start_sync(force: bool = False, budget_s: float | None = 900) -> None:
    from ..db.sync import Sync
    cur = SYNC.get("sync")
    if cur and cur.state.running:
        return
    s = Sync(force=force, budget_s=budget_s)
    SYNC["sync"], SYNC["thread"] = s, s.start_background()


# -------------------------------------------------------------------- actions
def _summary_at(path: str) -> dict:
    if path.startswith("community-v2:"):
        from ..combat.preset_sync import cached_presets
        for row in cached_presets():
            if path == f"community-v2:{row['class']}:{row['mode']}":
                return {**row["build"], "preset_checked_at": row["checked_at"], "preset_source": "community"}
        raise FileNotFoundError(path)
    if path.startswith("community:"):
        from ..paths import read_json
        cls = path.partition(":")[2]
        if cls not in list_names("global", "classes"):
            raise FileNotFoundError(path)
        return read_json("community_presets", f"{cls}.json")["build"]
    p = Path(path) / "build.json"
    if not any(p.resolve().is_relative_to(r.resolve()) for r in views.result_roots()) or not p.exists():
        raise FileNotFoundError(path)
    return json.loads(p.read_text(encoding="utf-8"))


@_model_action
def act_character_import(body: dict, log) -> dict:
    from ..charopt import evaluate_current, import_character
    log("importing from the official site")
    imp = import_character(body["character_id"], int(body["server_id"]), body.get("region", "nae"),
                           progress=log, use_cache=float(body.get("cache", 0)))
    log("scoring the build as it is")
    ev = evaluate_current(imp)
    return views.character_view(imp, ev)


@_model_action
def act_character_optimize(body: dict, log) -> dict:
    from ..charopt import import_character, optimize_character
    mode = body.get("mode", "pve")
    if mode not in ("pve", "pvp"):
        raise ValueError("Choose PvE or PvP optimization")
    scenario = "pvp" if mode == "pvp" else "boss"
    objective = body.get("objective", "primary")
    if objective not in ("primary", "balanced"):
        raise ValueError("Choose primary or balanced damage optimization")
    imp = import_character(body["character_id"], int(body["server_id"]), body.get("region", "nae"),
                           progress=log, use_cache=3600)
    out = results_dir() / "characters" / imp.loadout_name()[5:]
    if mode == "pvp":
        out = out / "pvp"
        from ..scenarios import PVP_NOTE
        log(PVP_NOTE)
    log(f"optimizing {mode.upper()} under the same resources (writes {out})")
    # One pass by default keeps the in-app optimize responsive (serial, no process pool when packaged);
    # the big gains are in pass 1 plus the final polish. The CLI can pass more for an exhaustive search.
    summ = optimize_character(imp, str(out), iterations=int(body.get("iterations", 1)), scenario_name=scenario, progress=log, budgets=body.get("budgets"), survival=body.get("survival", {"preserve_hp": True}), skill_reserves=body.get("skill_reserves"), genus=body.get("genus"), objective=objective)
    best = json.loads((out / "build.json").read_text(encoding="utf-8"))
    cur = json.loads((out / "current" / "build.json").read_text(encoding="utf-8"))
    from ..combat import share
    log("Submitting anonymous point observations…")
    try:
        points = share.community_request("/api/v1/progression", {"class": imp.cls, "region": body.get("region", ""),
            "game_patch": body.get("game_patch", ""), "points": summ["budgets"],
            "source": "user_reported" if body.get("budgets") else "profile_lower_bound"})
        log("Community point observations updated.")
    except Exception as exc:
        points = {"error": str(exc)}
        log("Could not submit point observations: " + str(exc))
    from ..combat.preset_sync import submit as submit_canonical
    preset = submit_canonical(best)
    if preset is None:
        preset = share.submit_preset(best)
    if preset.get("submitted"):
        log("Community preset updated." if preset.get("accepted") else preset.get("reason", "Current community preset retained."))
    elif preset.get("reason"):
        log("community preset was not submitted: " + preset["reason"])
    return {"summary": summ, "optimized": views.build_view(best), "current_build": cur["build"],
            "path": str(out), "diff": (out / "DIFF.md").read_text(encoding="utf-8"), "preset": preset, "point_observation": points}


def start_comparison(body: dict) -> str:
    from ..canonical_presets import scoring_policy
    cls, mode = body.get("class"), body.get("mode")
    scoring_policy(cls, mode)  # Reject unknown input before queuing a worker.
    key = (cls, mode)
    with _jobs_lock:
        previous = _COMPARISON_JOBS.get(key)
        if previous and JOBS.get(previous, {}).get("status") == "running":
            return previous
        jid = start_job("community-comparison", act_community_comparison, {"class": cls, "mode": mode})
        _COMPARISON_JOBS[key] = jid
        return jid


@_model_action
def act_community_comparison(body: dict, log) -> dict:
    from .community_comparison import generate
    from ..combat.preset_sync import submit
    summary, reused = generate(body["class"], body["mode"], progress=log)
    log("Common comparison saved; submitting anonymous allocations")
    submission = submit(summary)
    if submission is None:
        submission = {"submitted": False, "reason": "The configured server does not support mode-specific common comparisons"}
    log(submission.get("reason") or ("Community preset updated" if submission.get("accepted") else "Current community preset retained"))
    return {"class": body["class"], "mode": body["mode"], "score": summary["score"],
            "dps": summary["dps"], "model": summary["evaluation"]["model"],
            "reused": reused, "submission": submission}


def act_preset_refresh(body: dict, log) -> dict:
    from ..combat.preset_sync import sync, cached_presets
    log("Checking community presets")
    started = time.time()
    changed = sync()
    rows = cached_presets()
    checked = bool(rows) and max(row["checked_at"] for row in rows) >= started
    return {"changed": changed, "checked": checked}


@_model_action
def act_optimize_class(body: dict, log) -> dict:
    from ..report import run_report
    cls = body["class"]
    mode = body.get("mode", "pve")
    if mode not in ("pve", "pvp"):
        raise ValueError("Choose PvE or PvP optimization")
    scenario = "pvp" if mode == "pvp" else "boss"
    out = results_dir() / (body.get("out") or (f"{cls}_l45_pvp" if mode == "pvp" else f"{cls}_l45"))
    if not out.resolve().is_relative_to(results_dir().resolve()):
        raise ValueError("out must stay inside the results folder")
    log(f"optimizing {cls} (this takes several minutes)")
    run_report(cls, str(out), scenario_name=scenario, iterations=int(body.get("iterations", 2)), loadout=body.get("loadout"),
               sp_budget=body.get("skill_points"), stigma_points=body.get("stigma_points"),
               daev_budget=int(body.get("daevanion", 360)), verbose=False, progress=log)
    summary = _summary_at(str(out))
    from ..combat.preset_sync import submit as submit_canonical
    from ..combat.share import submit_preset
    log("Submitting eligible anonymous allocations for common-loadout comparison")
    submission = submit_canonical(summary)
    if submission is None:
        submission = submit_preset(summary)
    return {**views.build_view(summary), "preset_submission": submission}


@_model_action
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


@_model_action
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


@_model_action
def act_advice(body: dict, log) -> dict:
    from ..plan.advisor import advise, write_markdown
    imp, inv = _inventory(body["character"])
    adv = advise(imp, inv, progress=log, genus_mix=body.get("genus_mix"))
    out = results_dir() / "characters" / imp.loadout_name()[5:]
    adv["inventory_snapshot"] = {"genus": inv.get("genus", {})}
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
        from ..plan.genus import validate_state
        inv["genus"] = validate_state(body.get("genus", {}))
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
        else:
            self.send_header("Cache-Control", "no-store")
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
        if path == "/overlay":
            return self._static("overlay.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/status":
            from ..db.sync import status
            s = SYNC.get("sync")
            from .. import __version__
            return self._json({"sync": s.state.as_dict() if s else None, "db": status(), "home": str(home()),
                               "app": "aion2calc", "version": __version__, "update": update_info(),
                               "update_prompt": ui_settings().get("auto_update", True)})
        if path == "/api/assets":
            from ..db.assets import report
            from .image_health import report as image_report
            data = report()
            data["desktop_image_proxy"] = image_report()
            return self._json(data)
        if path == "/api/classes":
            return self._json(list_names("global", "classes"))
        if path == "/api/history":
            from .history import discover_legacy, recent, path as history_path
            if q.get("id"):
                return self._json(json.loads(history_path(q["id"]).read_text(encoding="utf-8")))
            discover_legacy()
            return self._json(recent())
        if path == "/api/planner/presets":
            return self._json(views.planner_presets())
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
        if path == "/api/community":
            from ..combat.share import community_request
            return self._json(community_request(q.get("path", "")))
        if path == "/api/sessions":
            from ..combat.sessions import recent, recent_page, path as session_path
            if q.get("fingerprint"):
                return self._json({"fingerprint": hashlib.sha256(session_path(q["fingerprint"]).read_bytes()).hexdigest()})
            if q.get("file"):
                return self._json(json.loads(session_path(q["file"]).read_text(encoding="utf-8")))
            if q.get("paged"):
                return self._json(recent_page(int(q.get("offset", 0)), int(q.get("limit", 25)), q.get("archive", "")))
            return self._json(recent())
        if path == "/api/meter/log":
            from .meter_runner import runner
            return self._json(runner().review_log())
        if path == "/api/inventory":
            return self._json(_inventory(q["character"])[1])
        if path == "/api/ui":
            return self._json(ui_settings())
        if path == "/api/update":
            from .. import __version__
            from .. import update
            return self._json({"current": __version__, "info": update.available(), "kind": update.install_kind()})
        if path == "/api/npcap":
            from . import npcap
            return self._json(npcap.status())
        if path == "/api/capture/setup":
            from . import capture_setup
            return self._json(capture_setup.status())
        if path == "/api/meter/installations":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Game installations are available only on this computer")
            from ..meter.metadata import installation_options
            return self._json(installation_options())
        if path == "/api/meter/interfaces":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("capture interfaces are available only on this computer")
            from ..meter.a2parser.capture import interface_details
            rows = interface_details()
            return self._json({"interfaces": [row["name"] for row in rows], "devices": rows})
        if path == "/api/upload-queue":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Upload recovery is local to this computer")
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                raise PermissionError("Upload recovery requires the local application origin")
            from ..combat import upload_queue
            return self._json(upload_queue.load())
        if path == "/api/log-ownership":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Private upload credentials are local to this computer")
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                raise PermissionError("Upload credentials require the local application origin")
            from ..combat.ownership import entries
            return self._json(entries())
        if path == "/api/logserver":
            from ..combat import share
            st = share.effective()
            return self._json({k: v for k, v in st.items() if k != "key"} | {"has_key": bool(st.get("key"))})
        if path == "/api/plans":
            from ..combat.share import plan_request
            return self._json(plan_request(plan_id=q.get("id")))
        if path == "/api/meter/diagnostics":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("diagnostics are available only on this computer")
            name = q.get("name", "")
            folder = (home() / "diagnostics").resolve()
            target = folder / name
            if (not name.startswith("meter-") or not name.endswith(".zip")
                    or Path(name).name != name or target.resolve().parent != folder or not target.is_file()):
                raise FileNotFoundError(name)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/logserver/check":
            # Probe the server from this computer (not the browser): no CORS or https/http limits, and it
            # tests the path uploads actually use, so the answer is honest.
            from ..combat import share
            url = q.get("url") or share.effective().get("url") or ""
            if not url:
                return self._json({"ok": False, "detail": "no log server is set"})
            try:
                info = share.discover(url)
                return self._json({"ok": True, "name": info.get("name"),
                                   "auth_required": bool((info.get("auth") or {}).get("required"))})
            except Exception as err:           # noqa: BLE001 - report the reason to the user
                return self._json({"ok": False, "url": url, "detail": f"{type(err).__name__}: {err}"})
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
        if path == "/api/meter":
            from .meter_runner import runner
            current = runner()
            try:
                overlay = q.get("view") == "latest"
                return self._json(current.status(follow_latest=overlay, compact=overlay))
            except Exception as exc:
                current.record_status_failure(exc)
                raise
        if path == "/api/icon":
            return self._icon(q.get("u", ""))
        raise FileNotFoundError(path)

    # --------------------------------------------------------------- POST
    def route_post(self, path: str, body: dict):
        if path == "/api/upload-queue":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Upload recovery is local to this computer")
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                raise PermissionError("Upload recovery requires the local application origin")
            from ..combat import upload_queue
            return self._json(upload_queue.save(body))
        if path == "/api/log-ownership":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Private upload credentials are local to this computer")
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlsplit(origin).netloc != self.headers.get("Host"):
                raise PermissionError("Upload management requires the local application origin")
            from ..combat import ownership
            action = body.get("action")
            if action == "import":
                return self._json(ownership.merge(body.get("owners")))
            row = ownership.clean(body.get("owner"))
            if action == "forget":
                return self._json(ownership.forget(row["server"],row["id"]))
            return self._json(ownership.request(row,action,body.get("visibility")))
        if path == "/api/history":
            from .history import save
            return self._json({"id": save(body)})
        if path == "/api/sessions/share":
            from ..combat.sessions import path as session_path
            from ..combat.share import upload, effective
            raw = session_path(body["file"]).read_bytes()
            if body.get("fingerprint") and hashlib.sha256(raw).hexdigest() != body["fingerprint"]:
                raise ValueError("File changed since fingerprint verification; clear the queue and review it again.")
            doc = json.loads(raw)
            if body.get("completed_only"):
                from .meter_runner import runner
                current = runner()
                with current.lock:
                    active = current.running and current.session_file == body["file"]
                if active or doc.get("meta", {}).get("capture_active"):
                    raise ValueError("Active or unfinished checkpoints are excluded from batch upload; stop capture or review and publish this part individually.")
                settings = effective()
                if body.get("server") != settings.get("url"):
                    raise ValueError("Upload server changed. Start a new batch with the intended server.")
                return self._json(upload(doc, url=settings["url"], key=settings.get("key"), visibility=body.get("visibility", "unlisted"), request_id=body.get("request_id")))
            return self._json(upload(doc, visibility=body.get("visibility", "unlisted")))
        if path == "/api/community":
            from ..combat.share import community_request
            return self._json(community_request(body.get("path", ""), body.get("body")))
        if path == "/api/sessions":
            from ..combat.sessions import save
            from ..combat.a2log import validate
            doc = validate(body["log"])
            save(doc, body["file"])
            return self._json(doc)
        if path == "/api/plans":
            from ..combat.share import plan_request
            return self._json(plan_request(body.get("plan"), body.get("visibility", "unlisted"), body.get("id"), body.get("owner")))
        if path == "/api/assets/reindex":
            return self._json({"job": start_asset_reindex()})
        if path == "/api/sync":
            start_sync(force=bool(body.get("force")), budget_s=body.get("budget", 900))
            return self._json({"ok": True})
        if path == "/api/character/profile":
            from ..sources.profile_snapshot import lookup
            return self._json(lookup(body.get("player") or {},body.get("region")))
        if path == "/api/character/import":
            return self._json({"job": start_job("import", act_character_import, body)})
        if path == "/api/character/opponent-pressure":
            from ..opt.survival import opponent_pressure
            return self._json(opponent_pressure(body.get("result"), body.get("metric"), body.get("scale"), body.get("window_s")))
        if path == "/api/character/pressure":
            from ..opt.survival import recorded_pressure
            return self._json(recorded_pressure(body.get("log"), body.get("segment"), body.get("target"), body.get("window_s", 5)))
        if path == "/api/character/optimize":
            return self._json({"job": start_job("optimize-character", act_character_optimize, body)})
        if path == "/api/planner/presets/contribute":
            return self._json({"job": start_comparison(body)})
        if path == "/api/planner/presets/refresh":
            return self._json({"job": start_job("preset-refresh", act_preset_refresh, body)})
        if path == "/api/optimize":
            return self._json({"job": start_job("optimize-class", act_optimize_class, body)})
        if path == "/api/encounters/import":
            return self._json({"job": start_job("encounter", act_encounter_import, body)})
        if path == "/api/log-ownership":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Private upload credentials are local to this computer")
            from ..combat.ownership import entries
            return self._json(entries())
        if path == "/api/logserver":
            from ..combat import share
            st = share.save_settings(body.get("url"), body.get("key"), body.get("visibility"))
            return self._json({k: v for k, v in st.items() if k != "key"} | {"has_key": bool(st.get("key"))})
        if path == "/api/overlay":
            from .overlay_launch import launch, close
            if body.get("action") == "hide":
                close()
                return self._json({"hidden": True})
            port = self.server.server_address[1]
            return self._json(launch(f"http://127.0.0.1:{port}/overlay"))
        if path.startswith("/api/encounters/") and path.endswith("/share"):
            from ..combat import share
            return self._json(share.share_encounter(int(path.split("/")[3]), visibility=body.get("visibility")))
        if path == "/api/advice":
            return self._json({"job": start_job("advice", act_advice, body)})
        if path.startswith("/api/inventory/"):
            return self._json(inventory_post(path, body))
        if path == "/api/meter/decoder":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Decoder files can only be imported on this computer")
            from ..meter.decoder import import_decoder
            return self._json(import_decoder(body.get("name", ""), body.get("source", "")))
        if path == "/api/meter":
            from .meter_runner import runner
            r = runner()
            action = body.get("action")
            if action == "start":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("Packet capture runs only on this computer")
                return self._json(r.start(body.get("source", "a2tools"), path=body.get("path"),
                                          speed=body.get("speed", 1.0), decoder=body.get("decoder"),
                                          iface=body.get("iface"), host=body.get("host"), port=body.get("port"),
                                          auto_port=body.get("auto_port", body.get("source", "a2tools") == "a2tools"),
                                          record_packets=bool(body.get("record_packets")),
                                          character_name=body.get("character_name"),
                                          scope=body.get("scope", "party"), segment_gap=body.get("segment_gap", 10),
                                          automatic_splits=body.get("automatic_splits", True),
                                          auto_finish=body.get("auto_finish",True), final_boss_ids=body.get("final_boss_ids",[]),
                                          target_mode=body.get("target_mode", "bossTargets")))
            if action == "installation":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("Game installation selection is local to this computer")
                return self._json(r.select_installation(body.get("id", "")))
            if action == "view":
                return self._json(r.configure_view(body))
            if action == "finish-run":
                return self._json(r.finish_run())
            if action == "split":
                return self._json(r.split_now())
            if action == "clear":
                return self._json(r.clear_session())
            if action == "stop":
                r.stop()
                return self._json(r.status())
            if action == "diagnostics-folder":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("diagnostics folders open only on this computer")
                from ..meter.diagnostics import open_folder
                return self._json(open_folder())
            if action == "diagnostics":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("diagnostics run only on this computer")
                return self._json(r.export_diagnostics())
            if action == "save":
                if not r.has_data():
                    raise ValueError("nothing to save yet")
                return self._json(act_encounter_import({"text": json.dumps(r.to_a2log(title=body.get("title"))),
                                                        "name": body.get("title") or "Live meter session"}, log=lambda *a: None))
            if action == "export":
                if not r.has_data():
                    raise ValueError("nothing to export yet")
                stamp = time.strftime("%Y%m%d-%H%M%S")
                path = logs_dir() / f"live-meter-{stamp}.a2log.json"
                path.write_text(json.dumps(r.to_a2log(title=body.get("title")), ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
                return self._json({"file": str(path)})
            if action == "upload":
                if not r.has_data():
                    raise ValueError("nothing to upload yet")
                def upload_snapshot(*, log):
                    from ..combat import share
                    log("Preparing a copy of the session; capture can continue.")
                    doc = r.to_a2log(title=body.get("title"))
                    log("Uploading session snapshot…")
                    return share.upload(doc, visibility=body.get("visibility"))
                return self._json({"job": start_job("meter-upload", upload_snapshot)})
            if action == "screenshot":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    raise PermissionError("screenshots run only on this computer")
                from PIL import ImageGrab
                folder = home() / "screenshots"
                folder.mkdir(exist_ok=True)
                path = folder / f"live-meter-{time.strftime('%Y%m%d-%H%M%S')}.png"
                ImageGrab.grab(all_screens=True).save(path, "PNG")
                return self._json({"file": str(path)})
            raise ValueError("action must be start, stop, diagnostics, save, export, upload or screenshot")
        if path == "/api/ping":
            PING["at"] = time.time()
            return self._json({"ok": True})
        if path == "/api/ui":
            from ..paths import write_user_json
            cur = ui_settings()
            cur.update({k: v for k, v in body.items() if k in ("app_window", "auto_update", "combat_colors")})
            write_user_json(cur, "ui.json")
            return self._json(cur)
        if path == "/api/update":                 # manual "Install update now" (localhost only)
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("updates run only on the computer running the app")
            from .. import update
            status = update.install_now()
            if status == "launching":
                schedule_shutdown()
            return self._json({"status": status})
        if path == "/api/npcap":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("Npcap setup runs only on the computer running the app")
            if body.get("action") != "install":
                raise ValueError('Npcap action must be "install"')
            from . import npcap
            return self._json(npcap.begin_install())
        if path == "/api/capture/setup":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("capture setup runs only on the computer running the app")
            if body.get("action") != "install":
                raise ValueError('capture setup action must be "install"')
            from . import capture_setup
            return self._json(capture_setup.begin_install())
        if path == "/api/open":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("folders open only on the computer running the app")
            from ..combat.logs import open_folder
            target = {"data": home(), "logs": logs_dir(), "results": results_dir()}.get(body.get("what"), home())
            return self._json({"folder": str(open_folder(target))})
        if path == "/api/quit":
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                raise PermissionError("only the computer running the app can stop it")
            schedule_shutdown()
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
        from .image_health import record
        host = urllib.parse.urlparse(u).hostname or ""
        if not any(host == h or host.endswith("." + h) for h in ICON_HOSTS):
            raise FileNotFoundError(u)
        cache = home() / "icons"
        cache.mkdir(exist_ok=True)
        f = cache / (hashlib.sha1(u.encode()).hexdigest() + Path(urllib.parse.urlparse(u).path).suffix)
        if not f.exists():
            from ..scrape.http import fetch_bytes
            data = fetch_bytes(u, observe=lambda outcome, status: record(host, outcome, status))
            if not data:
                raise FileNotFoundError(u)
            f.write_bytes(data)
        else:
            record(host, "cache_hit")
        self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "image/png", cache=86400 * 7)


HTTPD: dict = {}
PING: dict = {"at": time.time()}
APP_WINDOW: dict = {}


def schedule_shutdown() -> None:
    """Let the response finish, stop capture, close native windows, then stop serving."""
    HTTPD["closing"] = True
    def stop():
        time.sleep(0.5)
        from . import overlay_launch
        from .meter_runner import runner
        from .windows import close_app_browser
        for close in (close_app_browser, runner().stop, overlay_launch.close):
            try:
                close()
            except Exception:
                traceback.print_exc()
        proc = APP_WINDOW.get("process")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        if HTTPD.get("server"):
            HTTPD["server"].shutdown()
    threading.Thread(target=stop, daemon=True, name="desktop-shutdown").start()


def ui_settings() -> dict:
    from ..paths import data_file, read_json
    defaults = {"app_window": True, "auto_update": True}
    return {**defaults, **(read_json("ui.json") if data_file("ui.json").exists() else {})}


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    HTTPD["server"] = httpd
    HTTPD["closing"] = False
    return httpd


def serve(port: int = 8765, open_browser: bool = True, sync: bool = True, host: str = "127.0.0.1",
          httpd: ThreadingHTTPServer | None = None):
    if sync:
        start_sync()
    # This is independent of the game-data sync: it is fast, optional, and never delays the UI.
    from ..combat.share import sync_presets
    if sync:
        threading.Thread(target=sync_presets, daemon=True, name="community-preset-sync").start()
        from ..combat.preset_sync import sync as sync_canonical
        threading.Thread(target=sync_canonical, daemon=True, name="canonical-preset-sync").start()
    httpd = httpd or make_server(host, port)
    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/"
    try:                                      # record the live URL so `python -m aion2calc.overlay` can find the app
        (home() / "app_url.txt").write_text(url, encoding="utf-8")
    except Exception:
        pass
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
        try:
            from . import overlay_launch
            from .meter_runner import runner
            runner().stop()
            overlay_launch.close()
        except Exception:
            pass
        httpd.server_close()
