"""The update prompt at launch. The page prompts once ``/api/status`` reports a newer release, and
that came from a background check whose failure -- no network yet right after Windows starts, GitHub
unreachable or rate-limited -- read as "no update" for six hours; a window reopened from the tray (the
same process) never re-checked; and Settings said "up to date" either way. A failed check is now
retried within minutes and keeps what an earlier one found, a fresh window re-checks a stale result,
the page polls quickly while a check runs, and Settings says what the last check actually found."""
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from aion2calc.app import server as app

APP_JS = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
UNREACHABLE = "http://127.0.0.1:9/unreachable"


@pytest.fixture()
def github(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    latest = {"tag": "v99.0.0"}

    class FakeGitHub(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"tag_name": latest["tag"], "html_url": f"https://github.test/releases/tag/{latest['tag']}"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/repos/x/y/releases/latest"
    calls = []
    real = app._check_update
    monkeypatch.setattr(app, "_check_update", lambda: (calls.append(1), real())[-1])
    app._UPDATE.clear()
    yield {"url": url, "latest": latest, "calls": calls, "monkeypatch": monkeypatch}
    srv.shutdown()
    app._UPDATE.clear()


def _age(seconds):
    app._UPDATE["at"] -= seconds


def test_a_check_that_failed_at_startup_is_retried_within_minutes(github):
    mp = github["monkeypatch"]
    mp.setattr(app, "RELEASES_API", UNREACHABLE)                   # the network is not up yet
    assert app.update_info(wait=True) is None
    state = app.update_state()
    assert state["error"] and state["checked_at"] and state["checking"] is False
    assert app.update_info(wait=True) is None and len(github["calls"]) == 1   # not hammered
    mp.setattr(app, "RELEASES_API", github["url"])                 # ... and now it is
    _age(app.UPDATE_RETRY_S)
    assert app.update_info(wait=True)["version"] == "99.0.0"       # minutes later, not six hours
    assert app.update_state()["error"] is None


def test_a_failed_check_keeps_the_release_an_earlier_one_found(github):
    mp = github["monkeypatch"]
    mp.setattr(app, "RELEASES_API", github["url"])
    assert app.update_info(wait=True)["version"] == "99.0.0"
    mp.setattr(app, "RELEASES_API", UNREACHABLE)
    _age(app.UPDATE_MAX_AGE_S)
    assert app.update_info(wait=True)["version"] == "99.0.0"       # a blip does not hide the update
    assert app.update_state()["error"]


def test_a_freshly_opened_window_rechecks_a_stale_result(github):
    from aion2calc import __version__
    mp = github["monkeypatch"]
    github["latest"]["tag"] = f"v{__version__}"                    # up to date when the app started
    mp.setattr(app, "RELEASES_API", github["url"])
    assert app.update_info(wait=True) is None
    github["latest"]["tag"] = "v99.0.0"                            # a release goes out meanwhile
    _age(app.UPDATE_FRESH_S)
    assert app.update_info(wait=True) is None and len(github["calls"]) == 1   # periodic polls still trust it
    assert app.update_info(wait=True, fresh=True)["version"] == "99.0.0"     # a reopened window asks again


def test_check_now_and_status_report_the_check(github):
    github["monkeypatch"].setattr(app, "RELEASES_API", github["url"])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        req = urllib.request.Request(base + "/api/update/check", b"{}", {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            checked = json.loads(r.read())
        assert checked["update"]["version"] == "99.0.0"
        assert checked["update_state"]["checking"] is False and checked["update_state"]["checked_at"]
        with urllib.request.urlopen(base + "/api/status?fresh=1", timeout=30) as r:
            status = json.loads(r.read())
        assert status["update"]["version"] == "99.0.0" and "update_state" in status
    finally:
        srv.shutdown()


def test_the_page_prompts_soon_after_launch_and_settings_reports_failures():
    assert '"/api/status" + (syncPillFirst ? "?fresh=1" : "")' in APP_JS      # first poll asks for a fresh check
    assert "checking ? 2000 : 20000" in APP_JS                                # quick re-poll while checking
    assert "could not check for updates" in APP_JS                           # a failure is not "up to date"
    assert 'api("/api/update/check", {})' in APP_JS and 'id="chkupd"' in APP_JS
