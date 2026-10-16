"""Overload safeguard: the live snapshot the app and overlay poll is memoized for
a short, self-tuning interval, so two pollers running together (each ~2x/second)
cannot drive the costly full-session recompute several times a second and starve
the capture thread — which is what froze the meter in a very large fight."""
import time

from aion2calc.app.meter_runner import Runner


class _StubSession:
    def __init__(self):
        self.calls = 0

    def snapshot(self, scope, segment_id, enemy_id, combine_pets):
        self.calls += 1
        return {"players": [], "call": self.calls}

    def __deepcopy__(self, memo):
        return self       # a recompute off the lock counts on this same stub


def test_live_snapshot_dedupes_rapid_overlapping_polls():
    r = Runner()
    r.session = _StubSession()
    first = r._live_snapshot(True)
    second = r._live_snapshot(True)        # within the TTL → served from cache, no recompute
    assert r.session.calls == 1
    assert second is first                 # the identical object is reused


def test_changing_the_view_recomputes():
    r = Runner()
    r.session = _StubSession()
    r._live_snapshot(True)
    r.scope = "all"                        # a different scope is a different view
    r._live_snapshot(True)
    assert r.session.calls == 2


def test_snapshot_recomputes_after_the_adaptive_interval():
    r = Runner()
    r.session = _StubSession()
    r._live_snapshot(True)
    assert r.session.calls == 1
    time.sleep(0.27)                       # past the 250ms floor → a fresh reading, on a worker
    r._live_snapshot(True)
    r._snap_thread.join(2)
    assert r.session.calls == 2


def test_starting_a_capture_drops_the_previous_snapshot_cache():
    r = Runner()
    r.session = _StubSession()
    r._live_snapshot(True)
    assert r._snap_cache is not None
    # _start clears it so a new capture never briefly shows the old session's table.
    with r.lock:
        r._snap_cache = None
    assert r._snap_cache is None
