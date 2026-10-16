"""Part continuity is record-sequence continuity. A zone load (the record epoch advancing) within a
part or across the boundary is not a break -- the storage rollover fires in the pause between
dungeons, right after one -- so parts that connect exactly are "connected" (with the context change
noted), not kept apart; a context going backwards, a gap or an overlap still is a break."""
from aion2calc.combat.archive import describe


def _part(part, first, last, first_epoch, last_epoch, previous=None, closed=True):
    continuity = {"version": 1, "token": "%032x" % (0xa0 + part), "first_sequence": first, "last_sequence": last,
                  "retained_records": last - first + 1, "first_epoch": first_epoch, "last_epoch": last_epoch}
    if previous is not None:
        continuity.update(previous_token=previous["continuity"]["token"], previous_last_sequence=previous["continuity"]["last_sequence"])
    return {"id": "f" * 32, "part": part, "closed": closed, "continuity": continuity}


def test_zone_loads_within_and_between_parts_do_not_break_continuity():
    # The reported recording: part 1 spans epochs 2-10, part 2 starts at the next record in epoch 11.
    one = _part(1, 1, 34581, 2, 10)
    two = _part(2, 34582, 48688, 11, 13, previous=one, closed=False)
    assert describe(one)["code"] == "start" and describe(one)["context_changed"] is True
    verdict = describe(two, one)
    assert verdict["code"] == "connected" and verdict["context_changed"] is True
    assert "context changed" in verdict["label"]
    quiet = describe(_part(2, 34582, 40000, 10, 10, previous=one), one)
    assert quiet["code"] == "connected" and quiet["context_changed"] is False


def test_a_context_going_backwards_a_gap_or_an_overlap_is_still_a_break():
    one = _part(1, 1, 100, 2, 5)
    assert describe(_part(2, 101, 200, 4, 6, previous=one), one)["code"] == "context_change"
    assert describe(_part(2, 103, 200, 5, 6, previous=one), one)["code"] == "gap"
    assert describe(_part(2, 99, 200, 5, 6, previous=one), one)["code"] == "overlap"


def test_an_unfinished_predecessor_breaks_only_when_records_are_missing():
    snapshot = _part(1, 1, 100, 2, 5, closed=False)
    assert describe(_part(2, 101, 200, 5, 6, previous=snapshot), snapshot)["code"] == "connected"   # follows its last record
    assert describe(_part(2, 120, 200, 5, 6, previous=snapshot), snapshot)["code"] == "parent_open"  # its tail is missing
