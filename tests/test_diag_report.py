"""The anonymous diagnostics beacons: unknown-id detection, the capture-health
counter whitelist, dedup per build/session, and the opt-out gate. No network — the
POST is monkeypatched; these guard what the client would send and that it carries
nothing identifying."""
import pytest

from aion2calc.combat import diag_report
from aion2calc.meter.a2parser import lookup


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def catalog(monkeypatch):
    # 2000002 is a known NPC; skill family 1011xxxx is known. Everything else is a gap.
    monkeypatch.setattr(lookup, "npc_info", lambda code, locale="en": {"name": "Known"} if int(code) == 2000002 else {})
    monkeypatch.setattr(lookup, "has_skill", lambda sid, locale="en": (sid - sid % 10_000) == 10_110_000)


DOC = {
    "meta": {"game_patch": "2.0.6.0", "archive": {"id": "sess-abc"}},
    "players": [{"id": "p1", "region": "NA"}],
    "segments": [{
        "duration": 100.0,
        "region": "NA",
        "entities": [
            {"id": "e1", "kind": "enemy", "mob_code": 2951001},                 # unmapped -> report
            {"id": "e2", "kind": "enemy", "mob_code": 2000002},                 # catalogued -> skip
            {"id": "p1", "kind": "player", "is_player": True, "mob_code": 9},   # a player -> never
        ],
        "hits": [
            {"t": 1.0, "player": "p1", "damage": 5.0, "skill_id": 30_999_999},  # unknown family -> report
            {"t": 2.0, "player": "p1", "damage": 5.0, "skill_id": 10_110_001},  # known family -> skip
        ],
    }],
}


def test_enabled_is_opt_out():
    assert diag_report.enabled({}) is True                       # default on
    assert diag_report.enabled({"meter_report_diagnostics": True}) is True
    assert diag_report.enabled({"meter_report_diagnostics": False}) is False


def test_reporter_key_is_stable_and_distinct(home):
    from aion2calc.combat import hp_report
    assert diag_report.reporter_key() == diag_report.reporter_key()          # stable per install
    assert diag_report.reporter_key() != hp_report.reporter_key()            # distinct from other beacons
    assert len(diag_report.reporter_key()) == 32


def test_unknown_from_doc_finds_only_catalog_gaps(catalog):
    out = diag_report.unknown_from_doc(DOC)
    assert out == {"npc": [2951001], "skill": [30_999_999]}                  # known npc/skill + the player excluded


def test_health_payload_whitelists_numeric_counters(home):
    diagnostics = {"archive_parts_saved": 997, "decoder_errors": 3, "pcap_received": 1000,
                   "state": "stopped", "decoder_warning": "x", "flag": True, "neg": -1}
    body = diag_report.health_payload(DOC, diagnostics)
    assert body["counters"] == {"archive_parts_saved": 997, "decoder_errors": 3, "pcap_received": 1000}
    assert body["os"] and body["client"] and body["game_build"] == "2.0.6.0"
    assert body["session_seconds"] == 100.0 and body["region"] == "NA"
    assert "reporter" in body and "character" not in body and "account" not in body


def test_report_posts_both_then_dedups(home, catalog, monkeypatch):
    posts = []
    monkeypatch.setattr(diag_report.share, "effective", lambda: {"url": "https://logs.example"})
    monkeypatch.setattr(diag_report, "_post", lambda base, endpoint, body, key: posts.append((endpoint, body)))

    first = diag_report.report(DOC, {"archive_parts_saved": 997})
    assert first.startswith("sent:")
    endpoints = {e for e, _ in posts}
    assert diag_report._UNKNOWN_ENDPOINT in endpoints and diag_report._HEALTH_ENDPOINT in endpoints
    unknown_body = next(b for e, b in posts if e == diag_report._UNKNOWN_ENDPOINT)
    assert unknown_body["npc"] == [2951001] and unknown_body["skill"] == [30_999_999]

    # Second run of the same session/build: ids already reported, health sig already sent -> nothing.
    posts.clear()
    assert diag_report.report(DOC, {"archive_parts_saved": 997}) == "nothing"
    assert posts == []


def test_report_disabled_sends_nothing(home, monkeypatch):
    monkeypatch.setattr(diag_report.share, "effective", lambda: {"url": "https://logs.example"})
    called = []
    monkeypatch.setattr(diag_report, "_post", lambda *a, **k: called.append(a))
    assert diag_report.report(DOC, {}, ui={"meter_report_diagnostics": False}) == "disabled"
    assert called == []
