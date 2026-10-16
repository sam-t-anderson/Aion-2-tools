"""Automatic uploads cover every recording of a launch, from every way the meter stops.

The upload after Stop used to live only in the Live Meter page's own script, so a Stop from the
overlay (or its hotkey) never uploaded; quit uploaded only the live document, only when capture
was still running, within eight seconds; a failed upload was never retried. The runner now keeps
the parts it wrote since launch and sends every one that is not on the server yet -- newest
first, serialised, recognised by recording key so nothing goes twice -- on Stop from the overlay,
on the page's Upload, on quit (bounded) and, for what a quit ran out of time for, at launch."""
import time
import uuid

import pytest

from aion2calc.combat import sessions, share
from aion2calc.app.meter_runner import Runner


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test", "key": "k", "visibility": "unlisted"})
    monkeypatch.setattr(share, "automatic_uploads_paused", lambda: False)
    return tmp_path


def _doc(archive_id, part, *, closed=True, active=False, title=None):
    return {"format": "a2log", "version": 1,
            "meta": {"title": title or f"Part {part}", "capture_scope": "party", "capture_active": active,
                     "archive": {"id": archive_id, "part": part, "closed": closed}},
            "players": [{"id": "p1", "name": "Me", "class": "gladiator", "server": "2102"}],
            "segments": [{"id": "1", "duration": 30.0, "hits": [{"t": 1.0, "player": "p1", "damage": 100.0}]}]}


def _runner(written, *, running=False, live=None):
    r = Runner.__new__(Runner)
    r._written_files = dict(written)
    r.session_file = "session-99999999-000000-live00.a2log.json"
    r.running = running
    r.has_data = lambda: live is not None
    r.to_a2log = lambda title=None: live
    r.apply_community_rank = lambda doc, result: None
    import threading
    r._upload_lock = threading.Lock()
    r._pending_upload_thread = None
    return r


def _save(name, doc, at):
    path = sessions.save(doc, name)
    import os
    os.utime(path, (at, at))
    return name


def test_pending_uploads_are_the_closed_parts_of_this_launch_not_yet_on_the_server(home):
    a, now = uuid.uuid4().hex, time.time()
    written = {}
    written[_save("session-20261016-000001-aaaaaa.a2log.json", _doc(a, 1), now - 400)] = now - 400
    written[_save("session-20261016-000002-bbbbbb.a2log.json", _doc(a, 2), now - 300)] = now - 300
    written[_save("session-20261016-000003-cccccc.a2log.json", _doc(a, 3, closed=False, active=True), now - 200)] = now - 200  # an open checkpoint
    uploaded = _doc(uuid.uuid4().hex, 1)
    written[_save("session-20261016-000004-dddddd.a2log.json", uploaded, now - 100)] = now - 100
    share.remember_uploaded(uploaded)                                                   # already on the server
    _save("session-20261015-000000-eeeeee.a2log.json", _doc(uuid.uuid4().hex, 1), now - 86400)  # an earlier launch's part
    r = _runner(written)
    files = [item["file"] for item in r.pending_uploads()]
    assert files == ["session-20261016-000002-bbbbbb.a2log.json", "session-20261016-000001-aaaaaa.a2log.json"]   # newest first
    # With catch-up, the earlier launch's closed part joins (oldest last); a stale one does not.
    old = _save("session-20261001-000000-ffffff.a2log.json", _doc(uuid.uuid4().hex, 1), time.time() - 30 * 86400)
    files = [item["file"] for item in r.pending_uploads(catch_up_days=7)]
    assert files[-1] == "session-20261015-000000-eeeeee.a2log.json" and old not in files


def test_the_live_part_comes_first_from_memory_and_its_checkpoint_is_skipped(home):
    a = uuid.uuid4().hex
    live = _doc(a, 2, closed=True)                                   # capture stopped: the final, closed part
    r = _runner({"session-20261016-000001-aaaaaa.a2log.json": 1000}, live=live)
    _save("session-20261016-000001-aaaaaa.a2log.json", _doc(a, 1), 1000)
    r.session_file = _save("session-99999999-000000-live00.a2log.json", live, 2000)
    r._written_files[r.session_file] = 2000
    items = r.pending_uploads(include_live=True)
    assert [i["live"] for i in items] == [True, False] and items[1]["file"] == "session-20261016-000001-aaaaaa.a2log.json"
    assert r.pending_uploads(include_live=False)[0]["file"] == r.session_file   # the checkpoint stands in when memory is not asked for


def test_upload_pending_sends_newest_first_once_and_keeps_going_after_a_failure(home, monkeypatch):
    a = uuid.uuid4().hex
    r = _runner({_save("session-20261016-000001-aaaaaa.a2log.json", _doc(a, 1), 1000): 1000,
                 _save("session-20261016-000002-bbbbbb.a2log.json", _doc(a, 2), 2000): 2000,
                 _save("session-20261016-000003-cccccc.a2log.json", _doc(a, 3), 3000): 3000})
    sent = []

    def fake_upload(doc, visibility=None, **_):
        part = doc["meta"]["archive"]["part"]
        if part == 2:
            raise RuntimeError("upload refused (503): busy")
        sent.append(part)
        share.remember_uploaded(doc)
        return {"id": f"log{part}", "url": f"https://logs.test/log.html?id=log{part}"}
    monkeypatch.setattr(share, "upload", fake_upload)
    lines = []
    result = r.upload_pending(log=lines.append, include_live=False)
    assert sent == [3, 1] and result["uploaded"] == 2 and result["failed"] == 1
    assert result["url"] == "https://logs.test/log.html?id=log3"            # the newest upload's link
    # A second pass finds only the part that failed; nothing is sent twice.
    sent.clear()
    monkeypatch.setattr(share, "upload", lambda doc, visibility=None, **_: (sent.append(doc["meta"]["archive"]["part"]), share.remember_uploaded(doc), {"id": "x", "url": "u"})[2])
    r.upload_pending(include_live=False)
    assert sent == [2]
    assert r.upload_pending(include_live=False)["uploaded"] == 0


def test_a_bounded_pass_stops_in_time_and_an_automatic_pass_respects_the_pause(home, monkeypatch):
    a = uuid.uuid4().hex
    r = _runner({_save(f"session-20261016-00000{i}-aaaaa{i}.a2log.json", _doc(a, i), 1000 * i): 1000 * i for i in range(1, 4)})
    monkeypatch.setattr(share, "upload", lambda doc, visibility=None, **_: (share.remember_uploaded(doc), {"id": "x", "url": "u"})[1])
    clock = iter([0.0, 0.0, 100.0])
    monkeypatch.setattr("aion2calc.app.meter_runner.time.monotonic", lambda: next(clock, 100.0))
    result = r.upload_pending(include_live=False, budget_s=5)
    assert result["uploaded"] == 1 and result["pending"] == 2                 # out of time after the first
    monkeypatch.setattr(share, "automatic_uploads_paused", lambda: True)
    assert r.upload_pending(include_live=False, automatic=True)["uploaded"] == 0   # a 429 recently: stand down
    monkeypatch.setattr("aion2calc.app.meter_runner.time.monotonic", time.monotonic)
    assert r.upload_pending(include_live=False, automatic=False)["uploaded"] == 2  # the Upload button does not


def test_stop_from_the_overlay_and_quit_trigger_the_pending_pass(home, monkeypatch):
    from aion2calc.app import server
    calls = []

    class _R:
        running = False
        thread = None

        def stop(self):
            calls.append("stop")

        def status(self):
            return {"ok": True}

        def upload_pending_async(self, reason, **kw):
            calls.append(("async", reason))
            return True

        def upload_pending(self, **kw):
            calls.append(("sync", kw.get("budget_s"), kw.get("automatic")))
            return {"uploaded": 0, "failed": 0, "pending": 0, "url": None, "results": []}
    r = _R()
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: r)
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": True})
    server._auto_upload_on_quit()
    assert ("sync", Runner.QUIT_UPLOAD_BUDGET_S, True) in calls              # quit: bounded, even though capture was not running
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": False})
    calls.clear()
    server._auto_upload_on_quit()
    assert calls == []                                                        # the setting is honoured


def test_upload_pending_async_runs_one_worker_when_the_setting_is_on(home, monkeypatch):
    r = _runner({})
    monkeypatch.setattr("aion2calc.app.server.ui_settings", lambda: {"meter_auto_upload": True})
    done = []
    r.upload_pending = lambda **kw: done.append(kw) or {"uploaded": 0}
    assert r.upload_pending_async("stop") is True
    r._pending_upload_thread.join(timeout=5)
    assert done and done[0]["automatic"] is True
    monkeypatch.setattr("aion2calc.app.server.ui_settings", lambda: {"meter_auto_upload": False})
    assert r.upload_pending_async("stop") is False


def test_the_launch_catch_up_has_its_own_setting(home, monkeypatch):
    """The launch pass needs both switches; Stop and quit need only the upload switch."""
    r = _runner({})
    done = []
    r.upload_pending = lambda **kw: done.append(kw) or {"uploaded": 0}
    monkeypatch.setattr("aion2calc.app.server.ui_settings",
                        lambda: {"meter_auto_upload": True, "meter_catch_up_uploads": False})
    assert r.upload_pending_async("launch", include_live=False) is False      # catch-up off: no launch pass
    assert r.upload_pending_async("stop") is True                              # ... but Stop still uploads
    r._pending_upload_thread.join(timeout=5)
    assert len(done) == 1
    monkeypatch.setattr("aion2calc.app.server.ui_settings", lambda: {"meter_auto_upload": True})
    assert r.upload_pending_async("launch", include_live=False) is True       # default: on
    r._pending_upload_thread.join(timeout=5)
    assert len(done) == 2


def test_the_catch_up_setting_is_offered_accepted_and_on_by_default():
    import pathlib
    from aion2calc.app import server
    app_js = (pathlib.Path(server.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="rec-catchup"' in app_js and "meter_catch_up_uploads" in app_js
    src = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    assert '"meter_catch_up_uploads": True' in src                 # default on
    assert '"meter_auto_upload", "meter_catch_up_uploads"' in src   # accepted by /api/ui
