"""The anonymous daily-active-meters heartbeat: an opt-out, PII-free, once-per-day
beacon whose token rotates every day and cannot be traced to a machine."""
import json
import re

import pytest

from aion2calc.combat import heartbeat


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


class _FakeResp:
    def __init__(self, captured, req):
        captured["req"] = req
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


def test_daily_token_rotates_by_utc_day_and_is_opaque(isolated_home):
    a = heartbeat.daily_token("2026-10-11")
    b = heartbeat.daily_token("2026-10-12")
    assert re.fullmatch(r"[0-9a-f]{24}", a) and re.fullmatch(r"[0-9a-f]{24}", b)
    assert a != b                                   # a different token each day
    assert heartbeat.daily_token("2026-10-11") == a  # stable within a day
    # The salt stays local and is never part of the token output.
    assert heartbeat._install_salt() not in a


def test_payload_is_anonymous_and_minimal(isolated_home):
    p = heartbeat.payload("2026-10-11")
    assert set(p) == {"token", "date", "client"}      # nothing else — no PII
    assert p["date"] == "2026-10-11"
    assert p["token"] == heartbeat.daily_token("2026-10-11")


def test_enabled_is_opt_out(isolated_home):
    assert heartbeat.enabled({}) is True                     # default on
    assert heartbeat.enabled({"community_heartbeat": True}) is True
    assert heartbeat.enabled({"community_heartbeat": False}) is False


def test_send_respects_opt_out_and_sends_nothing(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", _capture_urlopen(captured))
    assert heartbeat.send(ui={"community_heartbeat": False}) == "disabled"
    assert "req" not in captured                              # no network when opted out


def test_send_needs_a_server(isolated_home, monkeypatch):
    monkeypatch.setattr(heartbeat.share, "effective", lambda: {})
    assert heartbeat.send(ui={}) == "no-server"


def test_send_posts_once_per_day_to_the_heartbeat_endpoint(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(heartbeat.share, "effective",
                        lambda: {"url": "https://logs.example.com", "key": "k"})
    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", _capture_urlopen(captured))
    assert heartbeat.send(ui={}) == "sent"
    req = captured["req"]
    assert req.full_url == "https://logs.example.com/api/v1/heartbeat"
    assert req.get_header("Authorization") == "Bearer k"
    body = json.loads(req.data.decode())
    assert set(body) == {"token", "date", "client"}
    # A second call the same day does not post again.
    captured.clear()
    assert heartbeat.send(ui={}) == "already"
    assert "req" not in captured


def test_send_never_raises_on_network_error(isolated_home, monkeypatch):
    monkeypatch.setattr(heartbeat.share, "effective",
                        lambda: {"url": "https://logs.example.com"})
    def boom(req, timeout=None):
        raise OSError("down")
    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", boom)
    assert heartbeat.send(ui={}).startswith("error:")   # swallowed, not raised
