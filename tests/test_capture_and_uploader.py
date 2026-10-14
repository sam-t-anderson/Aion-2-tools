"""Capture-buffer sizing and uploader attribution (0.2.269).

At the old 8 MiB kernel capture buffer, busy fights dropped a quarter to a half of their packets —
which unranked them and left enemies unidentified (their spawn packets were among the dropped). The
capture now requests a much larger buffer, stepping down until the backend accepts one. Separately,
a public log now records the uploading (local) player so community logs can show who shared it;
when the local player isn't established the log stays anonymous.
"""
import pathlib

from aion2calc.meter.a2parser.capture_stats import CAPTURE_BUFFER_BYTES, _BUFFER_CANDIDATES

ROOT = pathlib.Path(__file__).resolve().parents[1]
METER_RUNNER = (ROOT / "aion2calc" / "app" / "meter_runner.py").read_text(encoding="utf-8")


def test_capture_buffer_is_much_larger_than_the_old_8mib():
    assert CAPTURE_BUFFER_BYTES >= 64 * 1024 * 1024    # old default was 8 MiB; raids need far more


def test_buffer_candidates_descend_to_the_old_default():
    assert _BUFFER_CANDIDATES[0] == CAPTURE_BUFFER_BYTES
    assert list(_BUFFER_CANDIDATES) == sorted(_BUFFER_CANDIDATES, reverse=True)
    assert _BUFFER_CANDIDATES[-1] == 8 * 1024 * 1024    # still falls back to the previous size


def test_metadata_stamps_the_uploader_from_the_local_player():
    # The export chokepoint (_metadata, used by both the live-save and upload paths) records the
    # local/recording player as meta.uploader, best-effort, so public logs can attribute uploads.
    assert 'doc["meta"]["uploader"]' in METER_RUNNER
    assert "local_player_id" in METER_RUNNER
    assert '"verified"' in METER_RUNNER     # marks whether the identity came from the game


def test_validate_keeps_the_capture_filter_diagnostics():
    # The active BPF filter and whether the game flow was located survive validation, so an uploaded
    # log reveals whether the capture fell back to the broad "tcp" filter (the packet-loss culprit).
    from aion2calc.combat import a2log
    from aion2calc.meter import Meter, replay_source

    demo = ROOT / "aion2calc" / "meter" / "demo_session.jsonl"
    meter = Meter()
    for event in replay_source(demo):
        meter.add(event)
    doc = meter.to_a2log(title="Demo")
    doc["meta"].setdefault("capture_quality", {}).update(
        {"capture_filter": "tcp", "auto_port": True, "flow_detected": False})
    cq = a2log.validate(doc)["meta"]["capture_quality"]
    assert cq["capture_filter"] == "tcp" and cq["auto_port"] is True and cq["flow_detected"] is False


def test_capture_records_the_active_filter_and_flow_detection():
    # The capture thread stamps the real filter and flips flow_detected when it locks the game flow.
    cap = (ROOT / "aion2calc" / "meter" / "a2parser" / "capture.py").read_text(encoding="utf-8")
    assert 'stats["capture_filter"] = new_filter' in cap     # the active filter is recorded as it changes
    assert 'stats["flow_detected"] = True' in cap


def test_capture_narrows_to_the_detected_flow_then_falls_back_to_broad():
    # The root packet-loss fix: in auto mode the kernel filter starts broad ("tcp" floods the buffer),
    # and once the game flow is located the capture is reopened narrowed to just that connection so the
    # kernel discards everything else. It must never leave capture dark -- a failed narrow, or a flow
    # that goes silent, widens back to the broad filter so a new flow can be re-detected.
    cap = (ROOT / "aion2calc" / "meter" / "a2parser" / "capture.py").read_text(encoding="utf-8")
    assert "def switch_filter" in cap and "def flow_filter" in cap
    assert '"tcp and host ' in cap                            # narrowed to the one connection's host+port
    assert 'open_all(broad_filter)' in cap                   # fallback: reopen broad if the narrow fails
    assert "NARROW_IDLE_WIDEN" in cap                         # a silent narrowed flow widens to re-detect
    # The reopen must happen off the callback lock, or joining the sniffer threads would deadlock.
    assert cap.index("switch_filter(desired_filter)") > cap.index("emit(\"capture_stats\", dict(stats))")


def test_uploader_prefers_the_in_fight_roster_name_over_the_live_actor_id():
    # Heavy packet loss can leave the live local actor an unnamed combat entity (#number), which the
    # stamp rejects. Resolve the name from the log's own roster by official character id instead, so
    # the uploader is a real in-fight name (and therefore passes the server's roster check).
    assert 'f"p:{profile[\'serverId\']}:{profile[\'dbid\']}"' in METER_RUNNER
    assert 'p.get("id") == want' in METER_RUNNER
    assert "doc.get(\"players\")" in METER_RUNNER


def test_validate_keeps_a_cleaned_uploader_through_the_schema():
    # meta.uploader is an object, not one of the allowlisted string meta keys, so validate() has to
    # preserve it explicitly -- otherwise the server strips it and every public log stays anonymous.
    from aion2calc.combat import a2log
    from aion2calc.meter import Meter, replay_source

    demo = ROOT / "aion2calc" / "meter" / "demo_session.jsonl"
    meter = Meter()
    for event in replay_source(demo):
        meter.add(event)
    doc = meter.to_a2log(title="Demo")                       # a valid document ("Zikel" is in the roster)
    doc["meta"]["uploader"] = {"name": "  Zikel  ", "verified": True, "server": "Israphel", "spoofed": {"x": 1}}
    uploader = a2log.validate(doc)["meta"]["uploader"]
    assert uploader["name"] == "Zikel" and uploader["verified"] is True   # trimmed, bounded, kept
    assert uploader["server"] == "Israphel"
    assert "spoofed" not in uploader                                      # only known fields survive
