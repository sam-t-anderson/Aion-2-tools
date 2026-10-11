"""The opt-in, anonymous standalone boss-kill auto-report: off by default, sends
only placement context for a confirmed open-world kill, derives a stable per-install
reporter key that never reveals the salt, and reports each distinct kill at most once."""
import json
import re

import pytest

from aion2calc.combat import boss_report, heartbeat


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


class _FakeResp:
    def __init__(self, captured, req):
        captured.setdefault("reqs", []).append(req)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def read(self):
        return b"{}"


def _capture_urlopen(captured):
    def fake(req, timeout=None):
        return _FakeResp(captured, req)
    return fake


def _doc(**seg):
    base = {
        "killed": True, "encounter_type": "pve_open_world",
        "start": "2026-10-11T12:00:00+00:00", "duration": 90.0,
        "map_id": 310, "instance_id": 0, "boss": "Kromede",
        "entities": [{"id": "e1", "is_boss": True, "mob_code": "123456", "name": "Kromede"}],
        "events": [{"kind": "death", "t": 90.0, "target": "e1"}],
    }
    base.update(seg)
    return {"format": "a2log", "version": 1,
            "players": [{"id": "p:Siel:1", "name": "A", "server": "Siel"},
                        {"id": "p:Siel:2", "name": "B", "server": "Siel"}],
            "segments": [base]}


def test_reporter_key_is_stable_opaque_and_matches_server_shape(isolated_home):
    key = boss_report.reporter_key()
    assert re.fullmatch(r"[A-Za-z0-9]{8,64}", key)         # server's reporter regex
    assert boss_report.reporter_key() == key                # stable across calls on one install
    assert heartbeat._install_salt() not in key             # salt is never exposed
    assert key != heartbeat.daily_token()                   # distinct from the heartbeat token


def test_enabled_is_opt_in(isolated_home):
    assert boss_report.enabled({}) is False                 # default off
    assert boss_report.enabled({"meter_report_boss_kills": True}) is True
    assert boss_report.enabled({"meter_report_boss_kills": False}) is False


def test_defeats_extracts_open_world_kill_with_placement(isolated_home):
    reports = boss_report.defeats_from_doc(_doc())
    assert len(reports) == 1
    body = reports[0]
    assert body["outcome"] == "kill"
    assert body["npc_id"] == 123456                         # mob_code coerced to int
    assert body["server"] == "Siel"                         # majority party home server
    assert body["killed_at"] == pytest.approx(1791720000 + 90, abs=1)  # start + duration
    assert body["map_id"] == 310 and body["boss"] == "Kromede"
    assert body["reporter"] == boss_report.reporter_key()


def test_only_confirmed_open_world_boss_kills_qualify(isolated_home):
    assert boss_report.defeats_from_doc(_doc(killed=False)) == []        # not a kill
    assert boss_report.defeats_from_doc(_doc(encounter_type="pve_unverified")) == []  # not open world
    # Boss present but it did not die (no death event targeting it).
    assert boss_report.defeats_from_doc(_doc(events=[])) == []
    # No identified physical server on any party member → cannot be placed.
    doc = _doc()
    for p in doc["players"]:
        p["server"] = None
    assert boss_report.defeats_from_doc(doc) == []


def test_report_is_opt_in_and_sends_nothing_when_off(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(boss_report.urllib.request, "urlopen", _capture_urlopen(captured))
    assert boss_report.report(_doc(), ui={"meter_report_boss_kills": False}) == "disabled"
    assert "reqs" not in captured                           # no network when opted out


def test_report_posts_to_endpoint_and_dedupes_repeat_saves(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(boss_report.share, "effective",
                        lambda: {"url": "https://logs.example.com", "key": "k"})
    monkeypatch.setattr(boss_report.urllib.request, "urlopen", _capture_urlopen(captured))
    ui = {"meter_report_boss_kills": True}
    assert boss_report.report(_doc(), ui=ui) == "sent:1"
    req = captured["reqs"][0]
    assert req.full_url == "https://logs.example.com/api/v1/boss-kill"
    assert req.get_header("Authorization") == "Bearer k"
    body = json.loads(req.data.decode())
    assert body["outcome"] == "kill" and body["npc_id"] == 123456
    # A second save of the same fight reports nothing new (local dedup marker).
    captured.clear()
    assert boss_report.report(_doc(), ui=ui) == "already"
    assert "reqs" not in captured


def test_report_needs_a_server(isolated_home, monkeypatch):
    monkeypatch.setattr(boss_report.share, "effective", lambda: {})
    assert boss_report.report(_doc(), ui={"meter_report_boss_kills": True}) == "no-server"


def test_report_never_raises_on_network_error(isolated_home, monkeypatch):
    monkeypatch.setattr(boss_report.share, "effective",
                        lambda: {"url": "https://logs.example.com"})
    def boom(req, timeout=None):
        raise OSError("down")
    monkeypatch.setattr(boss_report.urllib.request, "urlopen", boom)
    # Best-effort: the per-kill POST fails, nothing is marked, report returns "error".
    assert boss_report.report(_doc(), ui={"meter_report_boss_kills": True}) == "error"
