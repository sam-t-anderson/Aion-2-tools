"""The opt-in per-fight community-rank refresh: while capturing, once a fight has paused,
the runner kicks a background upload+rank refresh — but only when the setting is on, a new
fight exists, combat has gone idle, and not more often than the throttle. Off by default."""
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
    monkeypatch.setattr(r, "_live_rank_upload", lambda: (calls.append(1), setattr(r, "_live_rank_busy", False)))
    return r, calls


def _fired(r, calls):
    for _ in range(100):
        if calls:
            return True
        time.sleep(0.005)
    return False


def test_off_by_default_never_refreshes(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path)   # no ui.json -> defaults (off)
    r._maybe_live_rank()
    assert not _fired(r, calls) and r._live_rank_key is None


def test_refreshes_once_a_ranked_fight_paused_when_enabled(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r._maybe_live_rank()
    assert _fired(r, calls)
    assert r._live_rank_key == (1, r.session.run)      # signature recorded so the same fight won't re-upload


def test_still_fighting_does_not_refresh(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r._last_combat_at = time.monotonic()               # combat is happening right now, not idle
    r._maybe_live_rank()
    assert not _fired(r, calls)


def test_throttled_and_deduped(monkeypatch, tmp_path):
    r, calls = _armed_runner(monkeypatch, tmp_path,
                             overlay_show_community_rank=True, overlay_live_community_rank=True)
    r._maybe_live_rank()
    assert _fired(r, calls)
    calls.clear()
    r._maybe_live_rank()                               # immediately again: throttled
    assert not _fired(r, calls)
    # Even past the throttle, the same fight (unchanged signature) must not re-upload.
    r._live_rank_last = time.monotonic() - 999
    r._maybe_live_rank()
    assert not _fired(r, calls)
    # A new fight (records grew) past the throttle does refresh again.
    r.session.records.append(object())
    r._maybe_live_rank()
    assert _fired(r, calls)
