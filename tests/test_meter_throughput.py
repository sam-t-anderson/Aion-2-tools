"""Live-meter throughput under a heavy fight (0.2.260).

A major world/abyss boss with a full raid enqueues packets faster than the single
decode thread drains them. The runner now drains each burst in a batch so the
per-burst bookkeeping (run-save / rollover / checkpoint) and its lock traffic happen
once per batch instead of once per packet, reports the backlog so the live view can
show it is catching up instead of looking frozen, and lets the costly live-snapshot
recompute step aside while backlogged so the decoder reclaims the shared lock.

This also pins a fix to a latent collision: ``diagnostics["processing_errors"]`` is a
numeric counter (the per-item handler increments it; ``diag_report`` forwards it only
when numeric), but a recovered decode skip used the same key as a *list*. After any
routine skip the next transient item error hit ``list + 1`` and stopped capture. The
error history now lives under its own key, so a skip can no longer poison the counter.
"""
import pathlib
import queue as _queue
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER_SRC = (ROOT / "aion2calc" / "app" / "meter_runner.py").read_text(encoding="utf-8")
OVERLAY_JS = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")


class _RaisingEngine:
    """Stands in for the packet engine: every decode raises, exercising the recovered
    (non-fatal) skip path. ``reset_stream`` is called by that path."""
    last_framing_errors = 0

    def consume(self, *a, **k):
        raise ValueError("truncated frame")

    def reset_stream(self, *a, **k):
        pass


def _runner(monkeypatch, tmp_path):
    from aion2calc.app import meter_runner as MR
    from aion2calc.meter.session import CombatSession
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(MR, "capture_packets", lambda *a, **k: None)   # no real sniffer
    r = MR.Runner()
    r.session = CombatSession()
    r.diagnostics = {"state": "starting", "decoded_events": 0}
    r.packet_stop = threading.Event()
    r.packet_queue = _queue.Queue()
    monkeypatch.setattr(r, "_checkpoint_session", lambda: None)
    return r


def test_constants_and_wiring_are_present():
    for name in ("_DECODE_BATCH_MAX", "_DECODE_BACKLOG_QUEUE", "_SNAPSHOT_BACKLOG_DUTY"):
        assert name in RUNNER_SRC
    # Batching is gated on an actual backlog: shallow queue -> cap 1 (one at a time).
    assert "_DECODE_BATCH_MAX if behind >= _DECODE_BACKLOG_QUEUE else 1" in RUNNER_SRC
    # The snapshot steps aside only while the queue is backed up...
    assert "qsize() >= _DECODE_BACKLOG_QUEUE" in RUNNER_SRC
    assert "_SNAPSHOT_BACKLOG_DUTY if busy else 1.0" in RUNNER_SRC
    # ...and the backlog is surfaced on the snapshot both views read.
    assert '"decode_backlog"' in RUNNER_SRC and '"catching_up"' in RUNNER_SRC


def test_both_views_render_a_catching_up_indicator():
    for js in (OVERLAY_JS, APP_JS):
        assert "decode_backlog" in js and "catching up" in js


def test_recovered_decode_skip_does_not_poison_the_numeric_counter(monkeypatch, tmp_path):
    r = _runner(monkeypatch, tmp_path)
    out = r._decode_packet(_RaisingEngine(), None, 0, b"\x00\x01", 1000)
    assert out == []                                                  # skipped, not fatal
    # The error history is its own list key...
    assert isinstance(r.diagnostics.get("processing_error_log"), list)
    assert r.diagnostics["processing_error_log"]
    # ...and must NOT have turned the numeric counter into a list (which would crash the
    # per-item handler's `count + 1` and stop capture after the next transient error).
    assert not isinstance(r.diagnostics.get("processing_errors"), list)
    assert r.session.capture_evidence.get("recovered_frame_skips") == 1


def test_a_transient_item_error_after_a_recovered_skip_stays_non_fatal(monkeypatch, tmp_path):
    r = _runner(monkeypatch, tmp_path)
    r.packet_engine = _RaisingEngine()

    def boom(_data):
        raise RuntimeError("zone transition hiccup")
    monkeypatch.setattr(r, "_record_capture_stats", boom)

    r.packet_queue.put(("packet", 0, b"\x00\x01", 1000))   # recovered skip -> history list
    r.packet_queue.put(("capture_stats", {"packets": 1}))  # handler raises -> counter + 1
    r.packet_queue.put(("capture_stopped",))
    r._run_a2tools(None, 0, None, None, True)

    assert r.error is None                                 # capture survived both
    assert r.diagnostics.get("processing_errors") == 1     # int counter, no `list + 1` crash
    assert r.session.capture_evidence.get("recovered_frame_skips") == 1


def test_a_normal_encounter_is_processed_one_item_at_a_time(monkeypatch, tmp_path):
    # Shallow queue (well under the backlog threshold): batching must NOT engage, so the
    # proven per-packet path and full-cadence snapshot are kept for ordinary content.
    r = _runner(monkeypatch, tmp_path)
    r.packet_engine = _RaisingEngine()
    seen = []
    monkeypatch.setattr(r, "_record_capture_stats", lambda d: seen.append(d))

    for i in range(3):
        r.packet_queue.put(("capture_stats", {"packets": i}))
    r.packet_queue.put(("capture_stopped",))
    r._run_a2tools(None, 0, None, None, True)

    assert len(seen) == 3                                  # all processed
    assert r.diagnostics.get("last_batch") == 1            # one at a time — no batching


def test_a_heavy_backlog_engages_batching_and_is_reported(monkeypatch, tmp_path):
    from aion2calc.app import meter_runner as MR
    r = _runner(monkeypatch, tmp_path)
    r.packet_engine = _RaisingEngine()
    seen = []
    monkeypatch.setattr(r, "_record_capture_stats", lambda d: seen.append(d))

    burst = MR._DECODE_BACKLOG_QUEUE + 12                  # enough queued to cross the threshold
    for i in range(burst):
        r.packet_queue.put(("capture_stats", {"packets": i}))
    r.packet_queue.put(("capture_stopped",))
    r._run_a2tools(None, 0, None, None, True)

    assert len(seen) == burst                              # every queued item was processed
    assert r.diagnostics.get("queue_depth") == 0          # fully drained
    assert r.diagnostics.get("last_batch", 0) >= MR._DECODE_BACKLOG_QUEUE   # batching engaged
    assert r.diagnostics.get("queue_depth_peak", 0) >= burst               # the burst depth was recorded
