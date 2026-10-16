"""The per-fight upload: while capturing, once a fight has paused, the runner sends the current
part from a worker -- after a boss kill when the per-fight upload is on (the default, needing
automatic uploads), or after any new fight for the opt-in live community-rank refresh -- but only
when combat has gone idle, not more often than the throttle, and one at a time."""
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
