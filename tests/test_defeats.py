"""Deduplicating the same boss defeat across uploader perspectives."""
from aion2calc.combat import defeats as D


def _log(i, boss, players, duration, region="nae"):
    return {"id": i, "boss": boss, "region": region, "duration": duration,
            "players": [{"id": p} for p in players]}


def test_same_defeat_groups_shared_roster_and_duration():
    logs = [
        _log("a", "Talisra of the Void", ["p1", "p2", "p3", "p4"], 258.0),   # one defeat, two perspectives
        _log("b", "Talisra of the Void", ["p1", "p2", "p3", "p4"], 259.5),
        _log("c", "Talisra of the Void", ["p1", "p2", "p3", "p4"], 72.0),    # a different, shorter clear
        _log("d", "Fortress Guardian Notun", ["p9", "p8", "p7"], 600.0),     # different boss
        _log("e", "Combat 1", ["p1", "p2"], 100.0),                          # generic name: ignored
    ]
    r = D.dedupe_defeats(logs)
    assert r["named_logs"] == 4 and r["duplicate_logs"] == 1            # the 'Combat 1' row is not named
    talisra = [g for g in r["groups"] if g["boss"] == "Talisra of the Void"]
    assert len(talisra) == 2                                            # the two long runs merge; the 72s stays apart
    merged = next(g for g in talisra if g["perspectives"] == 2)
    assert merged["confidence"] == "corroborated" and sorted(l["id"] for l in merged["logs"]) == ["a", "b"]
    assert any(g["perspectives"] == 1 and g["duration"] == 72.0 for g in talisra)


def test_defeats_never_merge_across_region_or_disjoint_roster():
    logs = [
        _log("a", "Ruthilis of Pain", ["p1", "p2", "p3", "p4"], 50.0, region="nae"),
        _log("b", "Ruthilis of Pain", ["p1", "p2", "p3", "p4"], 50.2, region="eu"),   # region differs
        _log("c", "Ruthilis of Pain", ["x1", "x2", "x3", "x4"], 50.1, region="nae"),  # disjoint roster
    ]
    r = D.dedupe_defeats(logs)
    assert r["distinct_defeats"] == 3 and r["duplicate_logs"] == 0      # none merged
