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
    assert 'stats["capture_filter"] = bpf_filter' in cap
    assert 'stats["flow_detected"] = True' in cap


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


def test_uploader_is_resolved_from_the_recordings_own_recorder_evidence():
    # The live engine no longer knows the local actor's name once a zone load has reassigned the
    # actor id, so a finished session used to upload as "Anonymous" even with the character set.
    # The log's own segments name their recorder (the local player's roster id): use that first.
    from types import SimpleNamespace
    from aion2calc.app.meter_runner import uploader_of
    me = {"id": "p:2102:591660401046103017", "name": "Spirited", "class": "gladiator", "server": "2102",
          "character_id": "591660401046103017"}
    mate = {"id": "p:2101:591378926069464783", "name": "HanWol", "class": "chanter", "server": "2101"}
    roster = [mate, me]
    engine = SimpleNamespace(local_player_id=None, names={}, local_character_name="", local_identity_from_game=False)
    up = uploader_of({"players": roster, "segments": [{"ping_recorder": None}, {"ping_recorder": me["id"]}]},
                     {"serverId": 2102, "job": "gladiator"}, engine)
    assert up == {"name": "Spirited", "verified": True, "server": "2102", "character_id": "591660401046103017"}
    # No recorder evidence: the configured character name picks the roster entry (case-insensitive).
    engine.local_character_name = " spirited "
    up = uploader_of({"players": roster, "segments": []}, {}, engine)
    assert up["name"] == "Spirited" and up["server"] == "2102" and up["verified"] is False
    # Nothing identifies the recorder: left unset, so the server shows Anonymous rather than a guess.
    engine.local_character_name = ""
    assert uploader_of({"players": roster, "segments": []}, {}, engine) is None
    # An unnamed combat actor (#number) is never an uploader name.
    engine.local_player_id, engine.names = 77, {77: "Player #77"}
    assert uploader_of({"players": roster, "segments": []}, {}, engine) is None
