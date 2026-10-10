"""Deduplicating the same boss defeat across uploader perspectives."""
from aion2calc.combat import defeats as D


def _log(i, boss, players, duration, region="nae", **extra):
    return {"id": i, "boss": boss, "region": region, "duration": duration,
            "players": [{"id": p} for p in players], **extra}


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


def _doc(title, segments, players):
    return {"format": "a2log", "meta": {"title": title},
            "players": [{"id": p} for p in players],
            "segments": [{"id": sid, "boss": boss, "region": region, "duration": dur}
                         for (sid, boss, region, dur) in segments]}


def test_local_docs_flatten_to_rows_one_per_fight_segment():
    doc = _doc("myrun", [(0, "Talisra of the Void", "nae", 258.0),
                         (1, "Combat 2", "nae", 40.0)], ["p1", "p2", "p3"])
    rows = D.rows_from_docs([doc])
    assert len(rows) == 2                                               # one row per segment
    boss_row = next(r for r in rows if r["boss"] == "Talisra of the Void")
    assert boss_row["duration"] == 258.0 and boss_row["region"] == "nae"
    assert sorted(p["id"] for p in boss_row["players"]) == ["p1", "p2", "p3"]
    assert boss_row["id"] == "myrun#0"


def test_local_docs_dedupe_two_uploaders_of_one_defeat():
    a = _doc("alice", [(0, "Talisra of the Void", "nae", 258.0)], ["p1", "p2", "p3", "p4"])
    b = _doc("bob", [(0, "Talisra of the Void", "nae", 259.0)], ["p1", "p2", "p3", "p4"])
    r = D.dedupe_defeats(D.rows_from_docs([a, b]))
    assert r["named_logs"] == 2 and r["distinct_defeats"] == 1          # two local uploads, one defeat
    assert r["groups"][0]["perspectives"] == 2 and r["groups"][0]["confidence"] == "corroborated"


def test_rows_from_docs_ignores_junk_entries():
    assert D.rows_from_docs(["nope", 5, {"segments": "bad"}, {}]) == []


def test_defeats_never_merge_across_difficulty_or_instance():
    base = ["p1", "p2", "p3", "p4"]
    logs = [
        _log("a", "Fortress Guardian Notun", base, 300.0, difficulty="normal"),
        _log("b", "Fortress Guardian Notun", base, 301.0, difficulty="nightmare"),   # same party, harder mode
        _log("c", "Fortress Guardian Notun", base, 300.5, difficulty="normal"),      # merges with (a)
        _log("d", "Talisra of the Void", base, 120.0, instance_id=600072),
        _log("e", "Talisra of the Void", base, 120.5, instance_id=600073),           # a distinct recorded instance
    ]
    r = D.dedupe_defeats(logs)
    notun = [g for g in r["groups"] if g["boss"] == "Fortress Guardian Notun"]
    assert len(notun) == 2                                             # normal (a+c) stays apart from nightmare (b)
    normal = next(g for g in notun if g["difficulty"] == "normal")
    assert normal["perspectives"] == 2 and sorted(l["id"] for l in normal["logs"]) == ["a", "c"]
    talisra = [g for g in r["groups"] if g["boss"] == "Talisra of the Void"]
    assert len(talisra) == 2                                           # two different instances never merge


def test_defeats_never_merge_across_game_patch():
    base = ["p1", "p2", "p3", "p4"]
    logs = [
        _log("a", "Tiere", base, 150.0, game_patch="version:product:2.0.6.0"),
        _log("b", "Tiere", base, 150.5, game_patch="version:product:2.1.0.0"),   # a later balance patch
        _log("c", "Tiere", base, 150.2, game_patch="version:product:2.0.6.0"),   # merges with (a)
    ]
    r = D.dedupe_defeats(logs)
    assert r["distinct_defeats"] == 2
    old = next(g for g in r["groups"] if g["game_patch"] == "version:product:2.0.6.0")
    assert old["perspectives"] == 2 and sorted(l["id"] for l in old["logs"]) == ["a", "c"]


def test_defeats_reads_difficulty_and_instance_from_server_contexts():
    base = ["p1", "p2", "p3", "p4"]
    def row(i, dur, diff, iid):
        return {"id": i, "boss": "Tiere", "region": "nae", "duration": dur,
                "players": [{"id": p} for p in base],
                "contexts": [{"segment": 0, "difficulty": diff, "instance_id": iid}]}
    r = D.dedupe_defeats([row("a", 147.0, "normal", 600072), row("b", 147.5, "hard", 600072)])
    assert r["distinct_defeats"] == 2                                  # difficulty lifted from contexts blocks the merge
