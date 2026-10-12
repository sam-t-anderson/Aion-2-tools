"""Browsing published raid plans by boss: plan_request builds the right server URL for
an npc / boss filter and for the bosses menu, the client /api/plans route forwards the
filters, and the raid planner's browse view offers a boss filter menu."""
import io
import json
import pathlib

from aion2calc.combat import share

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
RAID = (STATIC / "raid.js").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
SERVER = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _capture(monkeypatch, payload):
    seen = {}
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test"})

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url if hasattr(req, "full_url") else req
        return _Resp(json.dumps(payload).encode())
    monkeypatch.setattr(share.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_browse_url_filters_by_npc_then_boss(monkeypatch):
    seen = _capture(monkeypatch, {"plans": []})
    share.plan_request(npc="2300471")
    assert seen["url"] == "https://logs.test/api/v1/plans?npc=2300471"

    share.plan_request(boss="Bakarma")
    assert seen["url"] == "https://logs.test/api/v1/plans?boss=Bakarma"

    # npc wins when both are given (it is the exact match key).
    share.plan_request(npc="2300471", boss="Bakarma")
    assert seen["url"] == "https://logs.test/api/v1/plans?npc=2300471"

    # No filter -> the plain public list.
    share.plan_request()
    assert seen["url"] == "https://logs.test/api/v1/plans"


def test_bosses_menu_url(monkeypatch):
    seen = _capture(monkeypatch, {"bosses": []})
    share.plan_request(bosses=True)
    assert seen["url"] == "https://logs.test/api/v1/plans/bosses"


def test_client_route_and_io_forward_the_filter():
    assert 'path == "/api/plans/bosses"' in SERVER
    assert "plan_request(plan_id=q.get(\"id\"), boss=q.get(\"boss\"), npc=q.get(\"npc\"))" in SERVER
    assert "bosses: async () =>" in APP and '"/api/plans/bosses"' in APP
    assert "npc=" in APP and "boss=" in APP               # browse() forwards the filter


def test_browse_view_offers_a_boss_filter_menu():
    assert "function doBrowse" in RAID
    assert "st.browseBosses" in RAID
    assert "data-boss=" in RAID                            # filter buttons
    assert "io.bosses" in RAID
