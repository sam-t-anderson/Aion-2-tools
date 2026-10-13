"""Ranking eligibility tolerates recovered frame-skips (0.2.258).

A perfect frame/packet stream is not achievable, so a decoder that skips a malformed or
over-limit frame and *continues* must not void a whole session's ranking. Those recovered
skips are tracked in their own `recovered_frame_skips` counter (not `decoder_errors` /
`capture_errors`), and only a *material* amount of them counts as capture loss. Genuine loss
(dropped packets, abandoned payloads, a fatal decoder failure) still gates ranking.
"""
from aion2calc.combat.quality import RECOVERED_SKIP_FLOOR, assess


def _reasons(capture, pcap_received=0):
    cap = {"decoder": "a2tools-python-v1", "app_version": "0.2.258",
           "transport_monitored": True, "pcap_received": pcap_received, **capture}
    doc = {"meta": {"capture_scope": "party", "capture_quality": cap}, "players": [], "segments": []}
    seg = {"duration": 60.0, "hits": [{"player": "p", "damage": 100, "t": 1.0}]}
    return assess(doc, seg)["reasons"]


def test_a_handful_of_recovered_skips_does_not_trip_capture_loss():
    reasons = _reasons({"recovered_frame_skips": 3})
    assert "capture_loss" not in reasons          # the old bug: one recovered skip unranked everything
    assert "frame_skips_material" not in reasons


def test_recovered_skips_are_not_counted_as_decoder_or_capture_errors():
    # The loss counters stay zero for a clean-but-imperfect capture, so the gate passes.
    reasons = _reasons({"recovered_frame_skips": 50})
    assert "capture_loss" not in reasons


def test_a_material_share_of_skips_still_counts_as_loss():
    assert "frame_skips_material" in _reasons({"recovered_frame_skips": RECOVERED_SKIP_FLOOR + 1})
    # The budget scales with packets received: 1.5% of 200k is under 2%, 3% is over.
    assert "frame_skips_material" not in _reasons({"recovered_frame_skips": 3000}, pcap_received=200000)
    assert "frame_skips_material" in _reasons({"recovered_frame_skips": 6000}, pcap_received=200000)


def test_genuine_capture_loss_still_gates_ranking():
    assert "capture_loss" in _reasons({"decoder_errors": 1})      # fatal decoder failure
    assert "capture_loss" in _reasons({"capture_errors": 1})      # abandoned payloads / interruption
    assert "capture_loss" in _reasons({"pcap_dropped": 1})        # driver dropped packets
