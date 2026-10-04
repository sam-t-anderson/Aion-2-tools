"""Tests for the installed app: launcher, bundled resources, settings, update check and downloads."""
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


def test_client_downloads_newest_version_first(tmp_path):
    from aion2calc.logserver.server import client_downloads
    for name in ("aion2calc-0.9.0-linux.tar.gz", "aion2calc-0.10.0-windows-portable.zip",
                 "aion2calc-setup-0.10.0.exe", "aion2calc-0.10.0-macos.zip", ".hidden"):
        (tmp_path / name).write_bytes(b"x" * 10)
    c = client_downloads(tmp_path, "https://logs.test")
    assert c["version"] == "0.10.0"                                 # numeric, not text, order
    assert [f["platform"] for f in c["files"]] == ["Windows installer", "Windows (portable)", "macOS", "Linux"]
    assert c["files"][0]["url"] == "https://logs.test/download/aion2calc-setup-0.10.0.exe"
    assert client_downloads(tmp_path / "missing", "https://logs.test") == {
        "version": None, "files": [], "page": "https://logs.test/download"}


def test_log_server_download_page_and_app_update_check(home, tmp_path):
    from aion2calc import __version__
    from aion2calc.app import server as app
    from aion2calc.combat import share
    from aion2calc.logserver import server as LS
    LS.CONFIG = LS.Config(str(tmp_path / "logs"))
    srv, base = _serve(LS.Handler)
    try:
        code, page = _get(base + "/download")
        assert code == 200 and b"No downloads yet" in page
        dl = tmp_path / "logs" / "downloads"
        dl.mkdir(parents=True)
        (dl / "aion2calc-setup-99.0.0.exe").write_bytes(b"MZ installer")
        code, page = _get(base + "/download")
        assert code == 200 and b"aion2calc-setup-99.0.0.exe" in page and b"99.0.0" in page
        assert _get(base + "/download/aion2calc-setup-99.0.0.exe") == (200, b"MZ installer")
        assert _get(base + "/download/missing.exe")[0] == 404
        assert _get(base + "/download/..%2Fstore.db")[0] == 404
        assert json.loads(_get(base + "/api/v1/client")[1])["version"] == "99.0.0"

        share.save_settings(base)
        app._UPDATE.clear()
        assert app.update_info(wait=True) == {"version": "99.0.0", "url": base + "/download"}
        (dl / "aion2calc-setup-99.0.0.exe").rename(dl / f"aion2calc-setup-{__version__}.exe")
        app._UPDATE.clear()
        assert app.update_info(wait=True) is None                   # same version: nothing to offer
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
