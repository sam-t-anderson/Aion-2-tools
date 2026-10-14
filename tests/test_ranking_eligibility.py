"""Ranking eligibility tolerates recovered frame-skips (0.2.258) and attributes
storage-boundary / packet-drop loss per fight rather than per whole session (0.2.268).

A perfect frame/packet stream is not achievable, so a decoder that skips a malformed or
over-limit frame and *continues* must not void a whole session's ranking. Those recovered
skips are tracked in their own `recovered_frame_skips` counter (not `decoder_errors` /
`capture_errors`), and only a *material* amount of them counts as capture loss. Genuine loss
(a fatal decoder failure, abandoned payloads, discarded TCP payloads) still gates ranking.

Two counters are *cumulative, whole-session* facts stamped onto every fight: `storage_boundary`
(set on every rolled-over archive part and its continuation) and `pcap_dropped`/`pcap_if_dropped`
(kernel-buffer drops since capture start). Applied bluntly, one unavoidable storage rollover or
one early buffer overflow unranked every fight in the session — including fights that were wholly
captured and lost nothing. 0.2.268 attributes both per fight: a self-contained fight (its own start
and verified end both observed) is not boundary-incomplete, and a handful of dropped packets is
within budget. A genuinely truncated fight, or a materially lossy capture, is still gated.
"""
from aion2calc.combat.quality import RECOVERED_SKIP_FLOOR, PCAP_DROP_FLOOR, assess


def _reasons(capture, pcap_received=0, seg=None):
    cap = {"decoder": "a2tools-python-v1", "app_version": "0.2.258",
           "transport_monitored": True, "pcap_received": pcap_received, **capture}
    doc = {"meta": {"capture_scope": "party", "capture_quality": cap}, "players": [], "segments": []}
    segment = {"duration": 60.0, "hits": [{"player": "p", "damage": 100, "t": 1.0}]}
    if seg:
        segment.update(seg)
    return assess(doc, segment)["reasons"]


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


def test_small_packet_drops_are_tolerated():
    # pcap_dropped is a cumulative whole-session counter; a handful of routine kernel-buffer drops
    # must not unrank fights that lost nothing material (the old bug: any nonzero drop unranked all).
    assert "capture_loss" not in _reasons({"pcap_dropped": 400})                     # under the floor
    assert "capture_loss" not in _reasons({"pcap_dropped": 1000}, pcap_received=200000)  # 0.5% < 2%
    assert "capture_loss" not in _reasons({"pcap_if_dropped": 300})


def test_material_packet_drops_still_gate_ranking():
    assert "capture_loss" in _reasons({"pcap_dropped": PCAP_DROP_FLOOR + 1})            # over the floor
    assert "capture_loss" in _reasons({"pcap_dropped": 50000}, pcap_received=100000)    # 50% dropped


def test_genuine_capture_loss_still_gates_ranking():
    assert "capture_loss" in _reasons({"decoder_errors": 1})          # fatal decoder failure
    assert "capture_loss" in _reasons({"capture_errors": 1})          # abandoned payloads / interruption
    assert "capture_loss" in _reasons({"tcp_discarded_payloads": 1})  # undecodable TCP payloads lost


def test_storage_boundary_spares_a_self_contained_fight():
    # A fight that observed its own start and reached its own verified end (a kill, or a cleanly
    # completed run) is wholly within this part; the part rolling over at its edges must not unrank it.
    assert "storage_boundary" not in _reasons({"storage_boundary": True},
                                              seg={"run_start_observed": True, "killed": True})
    assert "storage_boundary" not in _reasons({"storage_boundary": True},
                                              seg={"run_start_observed": True, "run_complete": True})


def test_storage_boundary_still_gates_a_truncated_fight():
    # Start not observed (the fight began in a previous part) -> could be truncated -> still gated.
    assert "storage_boundary" in _reasons({"storage_boundary": True},
                                          seg={"run_start_observed": False, "killed": True})
    # No verified end (the fight could continue into the next part) -> still gated.
    assert "storage_boundary" in _reasons({"storage_boundary": True},
                                          seg={"run_start_observed": True, "killed": False})
