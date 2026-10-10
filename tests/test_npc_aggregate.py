"""Aggregating the bounded NPC decoder evidence across uploaded logs."""
from aion2calc.combat import npc_aggregate as A


def _doc(doc_id, records):
    return {"id": doc_id, "meta": {"npc_diagnostics": {"version": 1, "omitted_epochs": 0,
            "epochs": [{"epoch": 1, "records": [
                {"entity": e, "opcode": op, "mob_code": mc, "timestamp_ms": 1000 + i, "status": st}
                for i, (e, op, mc, st) in enumerate(records)]}]}}}


def test_aggregate_promotes_cross_upload_codes_and_flags_variants():
    # 2300802 (Earth Spirit, a real catalog NPC) seen across two uploads;
    # 2920655 ("???" placeholder) seen across two uploads; opcode 64 mostly fails to decode.
    a = _doc("A", [(10, 65, 2300802, "type_decoded"), (10, 65, 2300802, "type_decoded"),
                   (11, 65, 2920655, "type_decoded"), (12, 64, 0, "type_marker_missing")])
    b = _doc("B", [(20, 65, 2300802, "type_decoded"), (20, 65, 2300802, "type_decoded"),
                   (21, 65, 2920655, "type_decoded"), (21, 65, 2920655, "type_decoded"),
                   (22, 64, 0, "type_marker_missing")])
    agg = A.aggregate([a, b, {"meta": {}}])          # third upload has no diagnostics
    assert agg["uploads"] == 3 and agg["uploads_with_diagnostics"] == 2
    cand = A.candidates(agg, min_logs=2, min_records=3, min_decoded=0.8)
    named = {c["mob_code"] for c in cand["named"]}
    needs = {c["mob_code"] for c in cand["needs_name"]}
    assert 2300802 in named                          # catalog names it -> decoder-confirmed
    assert 2920655 in needs                           # observed + stable but catalog says "???"
    assert all(c["mob_code"] != 0 for group in ("named", "needs_name") for c in cand[group])

    v = A.variants(agg)
    op64 = next(r for r in v["opcodes"] if r["opcode"] == 64)
    op65 = next(r for r in v["opcodes"] if r["opcode"] == 65)
    assert op64["decoded_fraction"] == 0.0 and op65["decoded_fraction"] > 0.8   # 64 is the unclassified variant
    assert v["marker_missing_observations"] >= 2


def test_aggregate_abstains_without_support_and_ignores_untrusted_shapes():
    # one upload, one record: not enough support to promote anything
    agg = A.aggregate([_doc("solo", [(1, 65, 2300802, "type_decoded")]),
                       {"meta": {"npc_diagnostics": {"version": 9, "epochs": "bogus"}}},   # invalid -> cleaned out
                       "not a dict"])
    cand = A.candidates(agg, min_logs=2, min_records=5)
    assert not cand["named"] and not cand["needs_name"]
    assert any(c["mob_code"] == 2300802 for c in cand["abstain"])
    assert agg["uploads_with_diagnostics"] == 1       # the invalid and non-dict inputs are skipped safely
