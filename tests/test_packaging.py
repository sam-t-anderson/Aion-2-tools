"""Tests for the installed app: launcher, bundled resources, settings and the update check."""
import json
import sys
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.db import store
    monkeypatch.setattr(store, "SEED", tmp_path / "no-seed.json.gz")
    store._local.__dict__.clear()
    yield tmp_path / "home"
    store._local.__dict__.clear()


def _serve(handler):
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_resource_root_in_and_out_of_the_bundle(monkeypatch, tmp_path):
    from aion2calc import paths
    assert (paths.resource_root() / "aion2calc" / "paths.py").exists()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_root() == tmp_path


def test_bundled_results_are_listed_and_not_marked_mine(home):
    from aion2calc.app.views import list_results, result_roots
    from aion2calc.paths import resource_root
    assert resource_root() / "results" in result_roots()
    res = list_results()
    assert res and not any(r["mine"] for r in res)


def test_client_config_presets_the_log_server_once(home, monkeypatch, tmp_path):
    from aion2calc import launcher, paths
    from aion2calc.combat import share
    (tmp_path / "client.json").write_text(json.dumps({"logserver_url": "https://logs.test/",
                                                      "visibility": "public"}))
    monkeypatch.setattr(paths, "resource_root", lambda: tmp_path)
    cfg = launcher.client_config()
    assert cfg["logserver_url"] == "https://logs.test/"
    assert launcher.apply_client_config(cfg)
    assert share.settings() == {"url": "https://logs.test", "visibility": "public"}
    share.save_settings("https://mine.test")
    assert not launcher.apply_client_config(cfg)                    # the user's own choice is kept
    assert share.settings()["url"] == "https://mine.test"
    (tmp_path / "client.json").write_text("not json")
    assert launcher.client_config() == {}


def test_smoke_test_and_running_app(home, tmp_path):
    from aion2calc import __version__, launcher
    from aion2calc.app.server import make_server
    out = tmp_path / "smoke.txt"
    assert launcher.smoke_test(str(out)) == 0
    text = out.read_text()
    assert "solver OK" in text and f"aion2calc {__version__}: OK" in text
    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert launcher.running_app(srv.server_address[1])
    finally:
        srv.shutdown()
    assert not launcher.running_app(launcher.free_port(0))


def test_solver_choice(monkeypatch):
    from aion2calc.opt import solver
    monkeypatch.setattr(solver.sys, "platform", "linux")
    assert solver.name() == "CBC"
    monkeypatch.setattr(solver.sys, "platform", "darwin")
    monkeypatch.setattr(solver, "highs_available", lambda: False)
    assert solver.name() == "CBC"
    monkeypatch.setattr(solver, "highs_available", lambda: True)
    assert solver.name() == "HiGHS"


def test_update_check_reads_github_releases(home, monkeypatch):
    from http.server import BaseHTTPRequestHandler

    from aion2calc import __version__
    from aion2calc.app import server as app
    latest = {"tag": "v99.0.0"}

    class FakeGitHub(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"tag_name": latest["tag"],
                               "html_url": f"https://github.test/releases/tag/{latest['tag']}"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv, base = _serve(FakeGitHub)
    monkeypatch.setattr(app, "RELEASES_API", base + "/repos/x/y/releases/latest")
    try:
        app._UPDATE.clear()
        assert app.update_info(wait=True) == {"version": "99.0.0",
                                              "url": "https://github.test/releases/tag/v99.0.0"}
        latest["tag"] = f"v{__version__}"
        app._UPDATE.clear()
        assert app.update_info(wait=True) is None                   # same version: nothing to offer
        monkeypatch.setattr(app, "RELEASES_API", "http://127.0.0.1:9/unreachable")
        app._UPDATE.clear()
        assert app.update_info(wait=True) is None                   # offline: no error, no offer
    finally:
        srv.shutdown()
        app._UPDATE.clear()


def test_app_settings_routes(home):
    from aion2calc import __version__
    from aion2calc.app import server as app
    app._UPDATE.update({"at": 1e18, "info": None})                  # no update check in this test
    srv, base = _serve(app.Handler)

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        st = json.loads(_get(base + "/api/status")[1])
        assert st["app"] == "aion2calc" and st["version"] == __version__ and st["update"] is None
        assert json.loads(_get(base + "/api/ui")[1]) == {"app_window": True}
        post("/api/ui", {"app_window": False, "ignored": 1})
        assert json.loads(_get(base + "/api/ui")[1]) == {"app_window": False}
        assert post("/api/ping", {})["ok"]
        code, css = _get(base + "/static/fonts/cinzel-latin.woff2")
        assert code == 200 and css[:4] == b"wOF2"
        code, page = _get(base + "/")
        assert b'id="theme"' in page and b"localStorage" in page
    finally:
        srv.shutdown()
        app._UPDATE.clear()


def test_default_server_used_until_user_chooses(home, monkeypatch):
    from aion2calc.combat import share
    monkeypatch.setattr(share, "_remote_default", lambda *a, **k: {})      # no network in tests
    monkeypatch.setattr(share, "_bundled_default",
                        lambda: {"url": "https://default.test", "visibility": "unlisted"})
    eff = share.effective()
    assert eff["url"] == "https://default.test" and eff["is_default"] is True
    assert share.settings() == {}                                         # the default is not persisted
    share.save_settings("https://mine.test/", visibility="public")
    eff = share.effective()
    assert eff["url"] == "https://mine.test" and eff["is_default"] is False and eff["visibility"] == "public"
