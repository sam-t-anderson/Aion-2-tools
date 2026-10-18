"""The community beacons and automatic uploads back off instead of storming the log server.

Background: the server's dashboard showed 10,000+ rejected (4xx) requests. The enemy-HP reporter
posted one request per killed enemy on *every* 15-second checkpoint save and, once the server's
hourly per-IP bucket was spent (240), re-sent every pending kill on each later save — hundreds of
429s a minute from one client. Keyless uploads (live-rank refresh, upload-before-prune, every part
of a long session) shared a 12-per-hour cap and kept trying through it. Now: a 429 pauses that
sender for the server's Retry-After, a body the server refuses (other 4xx) is never retried,
observations go out in one batched request where the server accepts it, checkpoint-time reports
are throttled, and a finished recording the server already holds is not uploaded again.
"""
import email.message
import io
import json
import urllib.error

import pytest

from aion2calc.combat import beacon, boss_report, hp_report, share


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    hp_report._BACKOFF.clear()
    hp_report._last_checkpoint_report = None
    boss_report._BACKOFF.clear()
    share._UPLOAD_BACKOFF.clear()
    share._CAPABILITIES.clear()
    share._DISCOVERED.clear()
    return tmp_path


def _http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://logs.example.com/x", code, "refused", headers, io.BytesIO(b'{"error":"no"}'))


def _fake_urlopen(captured, fail=None):
    """``fail(request) -> exception | None`` decides per request; bare-URL (well-known) reads answer {}."""
    class _Resp:
        def __init__(self, req):
            captured.append(req)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self, *a):
            return b"{}"

    def fake(req, timeout=None):
        if hasattr(req, "get_method") and fail is not None:
            exc = fail(req)
            if exc is not None:
                captured.append(req)
                raise exc
        return _Resp(req)
    return fake


def _kills(n):
    """One segment with ``n`` distinct killed enemies, each with both HP scales."""
    entities, events, health = [], [], []
    for i in range(n):
        eid = f"e{i}"
        entities.append({"id": eid, "kind": "enemy", "mob_code": str(50000 + i)})
        events += [{"kind": "damage", "t": 1.0, "source": "p1", "target": eid, "amount": 1000},
                   {"kind": "death", "t": 2.0, "target": eid}]
        health += [{"t": 0.0, "entity": eid, "current": 5000, "max": 5000},
                   {"t": 1.5, "entity": eid, "current": 0, "max": 5000}]
    seg = {"id": "seg-1", "killed": True, "encounter_type": "pve_open_world", "game_patch": "1.0.21",
           "entities": entities, "events": events, "health": health,
           "hits": [{"t": 1.0, "player": "p1", "source": "p1", "target": e["id"], "damage": 1000} for e in entities]}
    return {"format": "a2log", "version": 1, "meta": {"game_patch": "1.0.21"},
            "players": [{"id": "p1", "name": "Me"}], "segments": [seg]}


# ---------------------------------------------------------------- the back-off itself
def test_retry_after_is_parsed_and_bounded():
    h = email.message.Message()
    h["Retry-After"] = "120"
    assert beacon.retry_after_seconds(h) == 120
    h.replace_header("Retry-After", "5")
    assert beacon.retry_after_seconds(h) == beacon.MIN_PAUSE_S          # never hammer every few seconds
    h.replace_header("Retry-After", "99999")
    assert beacon.retry_after_seconds(h) == beacon.MAX_PAUSE_S          # and never park for a day
    h.replace_header("Retry-After", "soon")
    assert beacon.retry_after_seconds(h) == beacon.DEFAULT_PAUSE_S      # malformed -> default
    assert beacon.retry_after_seconds(None) == beacon.DEFAULT_PAUSE_S


def test_backoff_pauses_until_the_server_says_so():
    now = [1000.0]
    b = beacon.Backoff(clock=lambda: now[0])
    assert not b.paused()
    assert b.pause(None) == beacon.DEFAULT_PAUSE_S
    assert b.paused() and b.remaining() == beacon.DEFAULT_PAUSE_S
    now[0] += beacon.DEFAULT_PAUSE_S - 1
    assert b.paused()
    now[0] += 2
    assert not b.paused()
    assert beacon.rate_limited(_http_error(429)) and not beacon.permanent_rejection(_http_error(429))
    assert beacon.permanent_rejection(_http_error(400)) and not beacon.permanent_rejection(_http_error(503))
    assert not beacon.permanent_rejection(OSError("down"))


# ---------------------------------------------------------------- enemy-HP reporter
def test_enemy_hp_batches_when_the_server_accepts_batches(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {"enemy_hp_batch": 100})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured))
    assert hp_report.report(_kills(150), ui={"meter_report_enemy_hp": True}, final=True) == "sent:150"
    posts = [r for r in captured if hasattr(r, "get_method")]
    assert len(posts) == 2                                          # 150 kills -> two requests, not 150
    first = json.loads(posts[0].data.decode())
    assert set(first) == {"reporter", "client", "observations"} and len(first["observations"]) == 100
    assert all({"npc_id", "effective_hp", "observed_hp", "game_build"} <= set(o) for o in first["observations"])
    assert not any("_sig" in o or "reporter" in o for o in first["observations"])
    assert len(json.loads(posts[1].data.decode())["observations"]) == 50
    # Everything is marked reported: the next save sends nothing.
    captured.clear()
    assert hp_report.report(_kills(150), ui={"meter_report_enemy_hp": True}, final=True) == "already"
    assert not captured or not any(hasattr(r, "get_method") for r in captured)


def test_enemy_hp_posts_one_per_kill_on_an_older_server(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {})      # no enemy_hp_batch
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured))
    assert hp_report.report(_kills(3), ui={"meter_report_enemy_hp": True}, final=True) == "sent:3"
    posts = [r for r in captured if hasattr(r, "get_method")]
    assert len(posts) == 3 and all("observations" not in json.loads(p.data.decode()) for p in posts)


def test_enemy_hp_pauses_after_a_429_instead_of_retrying_every_checkpoint(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen",
                        _fake_urlopen(captured, fail=lambda req: _http_error(429, retry_after=1800)))
    ui = {"meter_report_enemy_hp": True}
    assert hp_report.report(_kills(20), ui=ui, final=True) == "paused"
    assert len([r for r in captured if hasattr(r, "get_method")]) == 1    # stopped at the first 429
    assert hp_report._BACKOFF.paused() and 1700 < hp_report._BACKOFF.remaining() <= 1800
    captured.clear()
    assert hp_report.report(_kills(20), ui=ui, final=True) == "paused"     # no network while paused
    assert not any(hasattr(r, "get_method") for r in captured)
    # Nothing was marked reported, so the kills go out once the pause is over.
    hp_report._BACKOFF.clear()
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured))
    assert hp_report.report(_kills(20), ui=ui, final=True) == "sent:20"


def test_enemy_hp_never_retries_a_body_the_server_refuses(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured, fail=lambda req: _http_error(400)))
    ui = {"meter_report_enemy_hp": True}
    assert hp_report.report(_kills(2), ui=ui, final=True) == "rejected"
    captured.clear()
    assert hp_report.report(_kills(2), ui=ui, final=True) == "already"     # marked done, not re-sent
    assert not any(hasattr(r, "get_method") for r in captured)


def test_enemy_hp_checkpoint_reports_are_throttled_but_the_final_save_always_reports(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured))
    ui = {"meter_report_enemy_hp": True}
    assert hp_report.report(_kills(1), ui=ui, final=False) == "sent:1"     # first checkpoint reports
    doc = _kills(2)
    assert hp_report.report(doc, ui=ui, final=False) == "throttled"        # 15 s later: wait
    assert hp_report.report(doc, ui=ui, final=True) == "sent:1"            # Stop: the new kill goes out
    assert hp_report.report(_kills(3), ui=ui) == "sent:1"                  # unknown kind: report now


def test_enemy_hp_network_failure_stops_the_round_without_marking(isolated_home, monkeypatch):
    captured = []
    monkeypatch.setattr(hp_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(hp_report.share, "capabilities", lambda base: {})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _fake_urlopen(captured, fail=lambda req: OSError("down")))
    assert hp_report.report(_kills(5), ui={"meter_report_enemy_hp": True}, final=True) == "error"
    assert len([r for r in captured if hasattr(r, "get_method")]) == 1    # one attempt, not five
    assert not hp_report._BACKOFF.paused()


# ---------------------------------------------------------------- boss-kill reporter
def _boss_doc():
    return {"format": "a2log", "version": 1, "meta": {},
            "players": [{"id": "p1", "name": "Me", "server": "1101"}],
            "segments": [{"id": "s1", "killed": True, "encounter_type": "pve_open_world",
                          "start": "2026-10-15T12:00:00+00:00", "duration": 30.0,
                          "entities": [{"id": "b1", "kind": "enemy", "is_boss": True, "mob_code": 2300218}],
                          "events": [{"kind": "death", "t": 30.0, "target": "b1"}]}]}


def test_boss_kill_report_pauses_after_a_429(isolated_home, monkeypatch):
    import time
    captured = []
    doc = _boss_doc()
    doc["segments"][0]["start"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 60))
    monkeypatch.setattr(boss_report.share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(boss_report.urllib.request, "urlopen", _fake_urlopen(captured, fail=lambda req: _http_error(429)))
    ui = {"meter_report_boss_kills": True}
    assert boss_report.report(doc, ui=ui) == "paused"
    captured.clear()
    assert boss_report.report(doc, ui=ui) == "paused"
    assert not captured


# ---------------------------------------------------------------- automatic uploads
_CLOSED = {"id": "1762b0bdfe0f4054a832464f6e9fdb05", "part": 1, "closed": True}


def _upload_doc(archive=_CLOSED):
    return {"format": "a2log", "version": 1, "meta": {"source": "meter", "archive": dict(archive)},
            "players": [{"id": "p1", "name": "Sorc", "class": "sorcerer"}], "segments": []}


def _upload_env(monkeypatch, captured, fail=None):
    monkeypatch.setattr(share, "validate", lambda d: d)
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test", "visibility": "unlisted", "is_default": False})
    monkeypatch.setattr(share.urllib.request, "urlopen", _fake_urlopen(captured, fail))


def test_a_429_on_upload_pauses_the_automatic_senders(isolated_home, monkeypatch):
    captured = []
    _upload_env(monkeypatch, captured, fail=lambda req: _http_error(429, retry_after=600))
    assert not share.automatic_uploads_paused()
    with pytest.raises(RuntimeError, match="upload refused \\(429\\)"):
        share.upload(_upload_doc())
    assert share.automatic_uploads_paused()
    assert 500 < share._UPLOAD_BACKOFF.remaining() <= 600


def test_a_finished_part_the_server_holds_is_remembered(isolated_home, monkeypatch):
    captured = []
    _upload_env(monkeypatch, captured)
    doc = _upload_doc()
    assert not share.already_uploaded(doc)
    share.upload(doc)
    assert share.already_uploaded(doc)
    assert share.already_uploaded(_upload_doc({**_CLOSED, "part": 2})) is False     # another part: not yet
    assert share.already_uploaded(_upload_doc({**_CLOSED, "closed": False})) is False  # open parts have no stable identity


def test_upload_before_prune_skips_what_is_already_on_the_server_and_a_paused_server(isolated_home, monkeypatch):
    from aion2calc.app import meter_runner, server
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_upload_before_prune": True})
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.example.com"})
    uploads = []
    monkeypatch.setattr(share, "upload", lambda doc, **kw: uploads.append(doc) or {"id": "abc123"})
    evict = meter_runner.upload_evictor()
    target = isolated_home / "session-x.a2log.json"
    target.write_text(json.dumps(_upload_doc()), encoding="utf-8")
    share.remember_uploaded(_upload_doc())
    assert evict(target) is True and uploads == []          # already there: delete without uploading
    fresh = isolated_home / "session-y.a2log.json"
    fresh.write_text(json.dumps(_upload_doc({**_CLOSED, "part": 2})), encoding="utf-8")
    share._UPLOAD_BACKOFF.pause(None)
    assert evict(fresh) is False and uploads == []          # bucket spent: no attempt at all
    share._UPLOAD_BACKOFF.clear()
    assert evict(fresh) is True and len(uploads) == 1       # otherwise uploads as before
