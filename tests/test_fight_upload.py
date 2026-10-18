"""The per-fight upload: while capturing, once a fight has paused, the runner sends the current
part from a worker -- after a boss kill when the per-fight upload is on (the default, needing
automatic uploads), or after any new fight for the opt-in live community-rank refresh -- but only
when combat has gone idle, not more often than the throttle, and one at a time."""
import threading
import time

from aion2calc.app.meter_runner import Runner


def _armed_runner(monkeypatch, tmp_path, **ui):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.paths import write_user_json
    if ui:
        write_user_json(ui, "ui.json")
    r = Runner()
    r.running = True
    r._last_combat_at = time.monotonic() - 30        # a fight ended 30s ago (idle)
    r.session.records.append(object())               # one fight's worth of data
    calls = []
    monkeypatch.setattr(r, "_fight_upload", lambda reason="boss": (calls.append(reason), setattr(r, "_fight_upload_busy", False)))
    return r, calls


def _fired(r, calls):
    for _ in range(100):
        if calls:
            return True
        time.sleep(0.005)
    return False


def test_no_kill_yet_means_no_upload_by_default(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path)   # defaults: per-fight on, rank refresh off
    r._maybe_fight_upload()                          # trash only: boss_kills is still 0
    assert not _fired(r, calls) and r._fight_upload_key is None


def test_a_boss_kill_uploads_once_the_fight_paused(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path)
    r.session.boss_kills = 1
    r._maybe_fight_upload()
    assert _fired(r, calls) and calls == ["boss"]
    assert r._fight_upload_kills == 1                # that kill is now accounted for
    calls.clear()
    r._fight_upload_at = time.monotonic() - 999      # past the throttle, same kill count: nothing new
    r._maybe_fight_upload()
    assert not _fired(r, calls)
    r.session.boss_kills = 2                         # the next boss died
    r._maybe_fight_upload()
    assert _fired(r, calls)


def test_per_fight_upload_needs_automatic_uploads(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path, meter_auto_upload=False)
    r.session.boss_kills = 1
    r._maybe_fight_upload()
    assert not _fired(r, calls)


def test_per_fight_upload_can_be_turned_off(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path, meter_upload_per_fight=False)
    r.session.boss_kills = 3
    r._maybe_fight_upload()
    assert not _fired(r, calls)


def test_still_fighting_does_not_upload(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path)
    r.session.boss_kills = 1
    r._last_combat_at = time.monotonic()             # combat is happening right now, not idle
    r._maybe_fight_upload()
    assert not _fired(r, calls)


def test_rank_refresh_off_by_default_and_on_when_enabled(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path, meter_upload_per_fight=False)
    r._maybe_fight_upload()                          # no kill, refresh off: nothing
    assert not _fired(r, calls)
    r, calls = _armed_runner(monkeypatch, tmp_path, meter_upload_per_fight=False,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r._maybe_fight_upload()
    assert _fired(r, calls) and calls == ["rank"]
    assert r._fight_upload_key == (1, r.session.run)   # signature recorded so the same fight won't re-send


def test_throttled_and_deduped(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r._maybe_fight_upload()
    assert _fired(r, calls)
    calls.clear()
    r._maybe_fight_upload()                          # immediately again: throttled
    assert not _fired(r, calls)
    # Even past the throttle, the same fight (unchanged signature, no new kill) must not re-send.
    r._fight_upload_at = time.monotonic() - 999
    r._maybe_fight_upload()
    assert not _fired(r, calls)
    # A new fight (records grew) past the throttle refreshes the rank again.
    r.session.records.append(object())
    r._maybe_fight_upload()
    assert _fired(r, calls)


def test_a_new_capture_forgets_the_kill_count(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path)
    r._fight_upload_kills, r._fight_upload_at = 5, time.monotonic()
    r.session.boss_kills = 5
    r._maybe_fight_upload()
    assert not _fired(r, calls)


def test_session_counts_major_kills_and_carries_them_across_parts():
    from aion2calc.meter.session import CombatSession
    s = CombatSession()
    assert s.boss_kills == 0 and s.snapshot().get("boss_kills") == 0
    s.boss_kills = 2
    assert s.continuation().boss_kills == 2


def test_setting_is_whitelisted_with_default_on(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app import server
    assert server.ui_settings().get("meter_upload_per_fight") is True


# -- the live status path: the check runs inside ``status()``, which holds the runner lock --------

class _ReentryGuard:
    """Stands in for the runner's plain ``threading.Lock``: an acquire by the thread that already
    holds it is recorded and refused instead of hanging the test the way it hung the app."""

    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None
        self.reentries = []

    def acquire(self, blocking=True, timeout=-1):
        if self._owner == threading.get_ident():
            self.reentries.append(threading.current_thread().name)
            raise RuntimeError("runner lock re-acquired by the thread that holds it")
        if not self._lock.acquire(blocking, timeout):
            return False
        self._owner = threading.get_ident()
        return True

    def release(self):
        self._owner = None
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def _status_in_thread(r, compact, wait=5.0):
    done = []
    worker = threading.Thread(target=lambda: done.append(r.status(compact=compact)), daemon=True)
    worker.start()
    worker.join(wait)
    return done


def test_status_returns_once_a_fight_has_paused(monkeypatch, tmp_path):
    """The reported freeze: five seconds into the first pause after combat, with automatic and
    per-fight uploads on (the defaults), ``status()`` took the runner lock a second time from the
    thread already holding it. The request never returned, the decoder waited on the lock for good
    (the meter froze) and every Stop timed out waiting for the decoder. A 1 s trash pull is enough."""
    r, calls = _armed_runner(monkeypatch, tmp_path)
    for compact in (True, False):          # the overlay's compact view and the app's full view
        assert _status_in_thread(r, compact), "status() blocked holding the runner lock"
        assert r.lock.acquire(timeout=1.0), "the runner lock was left held: the decoder would starve"
        r.lock.release()


def test_status_never_retakes_the_runner_lock(monkeypatch, tmp_path):
    """Every optional step ``status()`` runs under the lock -- the per-fight upload after a kill, the
    live rank refresh, the observed field bosses, the rank badges -- armed at once: none may take the
    lock again, and the per-fight upload still fires from the real call site."""
    r, calls = _armed_runner(monkeypatch, tmp_path,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r.session.boss_kills = 1
    r._field_bosses = {"character": "Spirited", "server": "2102", "faction": "asmodian", "kills": []}
    monkeypatch.setattr(r, "_field_bosses_refresh", lambda *a: setattr(r, "_field_bosses_busy", False))
    r._community_rank = {7: {"text": "95th", "scope": "class", "percentile": 95}}
    guard = r.lock = _ReentryGuard()
    for compact in (True, False):
        r._fight_upload_at, r._field_bosses_at = float("-inf"), float("-inf")   # re-arm both gates
        assert _status_in_thread(r, compact), "status() blocked"
    assert guard.reentries == []
    assert _fired(r, calls) and calls[0] == "boss"



# -- what the per-fight upload sends after a storage rollover ------------------------------------

def _recording_runner(monkeypatch, tmp_path):
    from aion2calc.combat import share
    from aion2calc.meter.a2parser.engine import MeterEngine
    from aion2calc.meter.a2parser.models import DamageEvent
    from aion2calc.meter.session import CombatSession
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    e = MeterEngine()
    e.names, e.known_players = {5001: "Me", 5002: "Ally"}, {5001, 5002}
    e.roster, e.roster_complete = {"Me": {}, "Ally": {}}, True
    e.local_player_id, e.local_identity_from_game = 5001, True
    e.map_id = e.dungeon_id = 600001
    e.last_zone_reset_ms = None
    r = Runner()
    r.running, r.scope, r.save_records, r.packet_engine = True, "party", True, e
    r.session = CombatSession()
    r.session.pvp = False
    now = int(time.time() * 1000)
    for i in range(3):
        r.session.observe(e, [DamageEvent(5001, 9001, 15210000, 500, now - 300_000 + i * 1000)],
                          timestamp_ms=now - 300_000 + i * 1000)
    sent, badges = [], []
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test"})
    monkeypatch.setattr(share, "automatic_uploads_paused", lambda: False)
    monkeypatch.setattr(share, "upload", lambda doc, **kw: (sent.append(doc), {"id": "log"})[1])
    monkeypatch.setattr(r, "apply_community_rank", lambda doc, result: badges.append(doc["meta"]["archive"]["part"]))
    return r, e, sent, badges


def test_after_a_rollover_the_kill_goes_up_not_its_empty_aftermath(monkeypatch, tmp_path):
    # Ultimate Berk: the final boss's death let a due storage rollover fire, so the kill was in the
    # part the rollover closed, and the live part held nine seconds of aftermath. The per-fight
    # upload sent only the live part (a "partial capture" with no damage); the kill stayed off the
    # server until Stop.
    from aion2calc.meter.a2parser.models import DamageEvent
    r, e, sent, badges = _recording_runner(monkeypatch, tmp_path)
    r.session._storage_groups["party"] = 100           # the part is due
    r._rollover_session()
    r._flush_thread.join(5)
    now = int(time.time() * 1000)
    r.session.observe(e, [DamageEvent(9001, 5001, 1200015, 399, now)], timestamp_ms=now)   # the dead boss's DoT
    r._fight_upload("boss")
    assert [(d["meta"]["archive"]["part"], d["meta"]["archive"]["closed"]) for d in sent] == [(1, True)]
    assert badges == [1] and r._parts_to_share == [] and r._fight_upload_busy is False
    # Once the live part holds player damage of its own, the next kill sends it, and only it.
    sent.clear()
    r.session.observe(e, [DamageEvent(5001, 9002, 15210000, 500, now + 1000)], timestamp_ms=now + 1000)
    r._fight_upload("boss")
    assert [(d["meta"]["archive"]["part"], d["meta"]["archive"]["closed"]) for d in sent] == [(2, False)]
    assert sent[0]["meta"]["title"].endswith(" · Part 2")


def test_a_closed_part_already_on_the_server_is_not_sent_again(monkeypatch, tmp_path):
    from aion2calc.combat import share
    r, e, sent, badges = _recording_runner(monkeypatch, tmp_path)
    r.session._storage_groups["party"] = 100
    r._rollover_session()
    r._flush_thread.join(5)
    monkeypatch.setattr(share, "already_uploaded", lambda doc: True)   # a Stop pass sent it meanwhile
    r._fight_upload("boss")
    assert sent == [] and r._parts_to_share == []
