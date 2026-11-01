"""The replay's shape catalog kept fresh from the log server (0.2.366): the app serves the newer of the server's copy
and the bundled one, fetches at most every twelve hours, and keeps the bundled catalog through every failure."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from aion2calc.app import aoe_catalog


def _catalog(stamp, shapes=None):
    return {"unit": "u", "meta": {"generated_at": stamp}, "shapes": shapes if shapes is not None else {"1": {"shape": "circle_aim", "radius": 500}}}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps(_catalog("2026-11-01T12:00:00Z")), encoding="utf-8")
    monkeypatch.setattr(aoe_catalog, "bundled_path", lambda: bundled)
    monkeypatch.setattr(aoe_catalog, "cache_path", lambda: tmp_path / "home" / "data" / "cache" / "aoe-shapes.json")
    return tmp_path


def test_the_newer_catalog_is_served_and_a_bad_cache_never_wins(home):
    assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-01T12:00:00Z"
    cache = aoe_catalog.cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_catalog("2026-11-02T04:00:00Z")), encoding="utf-8")
    assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-02T04:00:00Z"
    cache.write_text(json.dumps(_catalog("2026-10-30T04:00:00Z")), encoding="utf-8")       # a server behind this client
    assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-01T12:00:00Z"
    cache.write_text("{not json", encoding="utf-8")
    assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-01T12:00:00Z"
    cache.write_text(json.dumps(_catalog("2026-11-03T04:00:00Z", shapes={})), encoding="utf-8")   # empty: not a catalog
    assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-01T12:00:00Z"


def test_refresh_fetches_the_servers_copy_at_most_every_twelve_hours(home, monkeypatch):
    served = {"body": json.dumps(_catalog("2026-11-02T04:00:00Z")).encode(), "hits": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            served["hits"] += 1
            if self.path != "/static/aoe-shapes.json":
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(served["body"])

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        from aion2calc.combat import share
        monkeypatch.setattr(share, "effective", lambda: {"url": f"http://127.0.0.1:{srv.server_address[1]}"})
        assert aoe_catalog.refresh() == "updated" and served["hits"] == 1
        assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-02T04:00:00Z"
        assert aoe_catalog.refresh() == "fresh" and served["hits"] == 1                      # within twelve hours
        served["body"] = b"{\"shapes\": {}}"
        assert aoe_catalog.refresh(force=True) == "invalid" and served["hits"] == 2         # the good copy stays
        assert json.loads(aoe_catalog.current_bytes())["meta"]["generated_at"] == "2026-11-02T04:00:00Z"
        monkeypatch.setattr(share, "effective", lambda: {})
        assert aoe_catalog.refresh(force=True) == "no-server"
        monkeypatch.setattr(share, "effective", lambda: {"url": "http://127.0.0.1:9"})
        assert aoe_catalog.refresh(force=True).startswith("failed")
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_app_serves_the_catalog_route_from_the_module(home, monkeypatch):
    import urllib.request
    from aion2calc.app.server import Handler
    monkeypatch.setattr(aoe_catalog, "current_bytes", lambda: b'{"unit": "u", "shapes": {"x": {"shape": "ring"}}}')
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/static/aoe-shapes.json", timeout=10) as r:
            assert r.headers.get("Content-Type", "").startswith("application/json")
            assert json.load(r)["shapes"] == {"x": {"shape": "ring"}}
    finally:
        srv.shutdown()
        srv.server_close()
