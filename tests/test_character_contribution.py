"""Collecting a character in My Character shares its observed point totals with the
community "highest observed build points" (on by default). Previously only running an
Optimize submitted anything, so a plain collect never appeared in the server totals."""
import types

import pytest

from aion2calc.app import server
from aion2calc.combat import share


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def _imp():
    return types.SimpleNamespace(cls="sorcerer")


def _ev(skill=120, stigma=24, daevanion=36):
    return {"budgets": {"skill": skill, "stigma": stigma, "daevanion": daevanion}}


def _capture(monkeypatch, *, on=True, server_url="https://logs.example.com"):
    sent = []
    monkeypatch.setattr(server, "ui_settings", lambda: {"community_contribute_character": on})
    monkeypatch.setattr(share, "effective", lambda: ({"url": server_url} if server_url else {}))
    monkeypatch.setattr(share, "community_request", lambda path, body=None: (sent.append((path, body)) or {"accepted": True}))
    return sent


def test_default_setting_is_on(home):
    assert server.ui_settings()["community_contribute_character"] is True


def test_collect_submits_profile_lower_bound(home, monkeypatch):
    sent = _capture(monkeypatch)
    server._contribute_character_points({"region": "nae", "game_patch": "2.0.6.0"}, _imp(), _ev(), lambda *a: None)
    assert len(sent) == 1
    path, body = sent[0]
    assert path == "/api/v1/progression"
    assert body["class"] == "sorcerer" and body["source"] == "profile_lower_bound"
    assert body["region"] == "nae" and body["game_patch"] == "2.0.6.0"
    assert body["points"] == {"skill": 120, "stigma": 24, "daevanion": 36}


def test_opt_out_sends_nothing(home, monkeypatch):
    sent = _capture(monkeypatch, on=False)
    server._contribute_character_points({"region": "nae"}, _imp(), _ev(), lambda *a: None)
    assert sent == []


def test_no_server_sends_nothing(home, monkeypatch):
    sent = _capture(monkeypatch, server_url="")
    server._contribute_character_points({"region": "nae"}, _imp(), _ev(), lambda *a: None)
    assert sent == []


def test_invalid_budgets_send_nothing(home, monkeypatch):
    sent = _capture(monkeypatch)
    # Missing daevanion, and a non-int value: nothing should be submitted.
    server._contribute_character_points({}, _imp(), {"budgets": {"skill": 10, "stigma": "x"}}, lambda *a: None)
    server._contribute_character_points({}, _imp(), {}, lambda *a: None)
    assert sent == []


def test_a_failed_submit_never_raises(home, monkeypatch):
    def boom(path, body=None):
        raise RuntimeError("server down")
    monkeypatch.setattr(server, "ui_settings", lambda: {"community_contribute_character": True})
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(share, "community_request", boom)
    logged = []
    server._contribute_character_points({"region": "nae"}, _imp(), _ev(), lambda m: logged.append(m))
    assert any("Could not share" in m for m in logged)
