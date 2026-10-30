"""Fights the meter of 0.2.353 and earlier cut wrongly, put right in recordings already made (rejoin):
a segment a later death stretched across the next fight is clipped where that fight began, a boss
fight cut in two is one encounter at the second half's index, and a boss seen at zero health is its
kill. Synthetic documents only."""
from datetime import datetime, timedelta, timezone

from aion2calc.combat.a2log import validate
from aion2calc.combat.quality import assess
from aion2calc.combat.rejoin import merge_segments, rejoin, same_fight
from aion2calc.combat.runs import summarize

T0 = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)
MAX = 1_000_000.0
DOC_META = {"capture_scope": "party", "capture_quality": {}}
PLAYERS = [{"id": "p1", "name": "Me", "class": "gladiator", "server": "2102"}]


def _segment(seq, start, duration, hits=(), health=(), events=(), boss="b", run="7", **extra):
    """One segment of meter session 1700000000000: the party (p1) striking ``boss`` at the given
    times (``start`` seconds after T0), with the boss's health readings ``(t, current)``."""
    return {"id": f"1700000000000-{int(start * 1000)}-{seq}", "run_id": run, "label": "Gelcos", "boss": "Gelcos",
            "start": (T0 + timedelta(seconds=start)).isoformat(), "duration": duration, "killed": False,
            "encounter_type": "transcendence", "game_patch": "version:product:1.0.21.0", "difficulty": "stage 3",
            "party_members": ["p1"], "party_roster_complete": True, "run_start_observed": True,
            "entities": [{"id": boss, "name": "Gelcos", "kind": "enemy", "is_boss": True, "mob_code": 2343616}],
            "hits": [{"t": t, "player": "p1", "target": boss, "damage": damage} for t, damage in hits],
            "health": [{"t": t, "entity": boss, "current": current, "max": MAX} for t, current in health],
            "events": list(events), **extra}


def _doc(*segments):
    return {"meta": dict(DOC_META), "players": list(PLAYERS), "segments": list(segments)}


def _halves(resume_hp=590_000.0, gap=1.0, run="7"):
    """A boss fight cut at 40 s: the boss falls from full to 60%, then (``gap`` s later) carries on
    from ``resume_hp`` to its death."""
    first = _segment(0, 0, 40.0, hits=[(t, 10_000.0) for t in range(0, 40)],
                     health=[(0.0, MAX), (20.0, 800_000.0), (39.5, 600_000.0)])
    second = _segment(1, 40.0 + gap, 60.0, run=run, hits=[(t, 10_000.0) for t in range(0, 60)],
                      health=[(0.5, resume_hp), (59.0, 0.0)], events=[{"kind": "death", "t": 59.5, "target": "b"}])
    second["killed"] = True
    return first, second


def test_a_boss_fight_cut_in_two_is_one_ranked_encounter_at_the_second_index():
    doc = rejoin(_doc(*_halves()))
    first, whole = doc["segments"]
    assert first["continued_in"] == 1 and len(first["hits"]) == 40           # the first half keeps its own data
    assert whole["duration"] == 101.0 and whole["killed"] is True
    assert len(whole["hits"]) == 100 and whole["hits"][-1]["t"] == 41.0 + 59   # one clock: the first half's
    assert [s["t"] for s in whole["health"]] == [0.0, 20.0, 39.5, 41.5, 100.0]
    assert whole["events"] == [{"kind": "death", "t": 100.5, "target": "b"}]
    assert whole["id"].endswith("-1") and whole["start"] == first["start"]
    assert doc["meta"]["repairs"]["rejoined"] == [[0, 1]] and doc["meta"]["repairs"]["version"] == 2
    reasons = assess(doc, whole)["reasons"]
    assert "start_unverified" not in reasons and "end_unverified" not in reasons
    assert "continued" in assess(doc, first)["reasons"]                      # never ranked on its own


def test_a_boss_back_at_full_or_healed_or_long_gone_is_a_new_pull():
    assert not same_fight(*_halves(resume_hp=MAX))                 # reset to full: a wipe, then a new pull
    assert not same_fight(*_halves(resume_hp=650_000.0))           # healed above where it was cut
    assert not same_fight(*_halves(gap=45.0))                      # resumed too long after
    assert not same_fight(*_halves(run="8"))                       # another run
    assert same_fight(*_halves(resume_hp=605_000.0))               # a regeneration tick within 1% of max
    first, second = _halves()
    first["events"] = [{"kind": "death", "t": 39.0, "target": "b"}]
    assert not same_fight(first, second)                           # it died in the first half
    second["id"] = "1700000099999-41000-1"
    assert not same_fight(_halves()[0], second)                    # another meter session
    doc = _doc(*_halves(resume_hp=MAX))
    assert rejoin(doc) is doc                                      # nothing to repair: the document itself


def test_a_fight_cut_three_ways_is_whole_in_its_last_piece():
    first, second = _halves()
    second["killed"], second["events"] = False, []
    second["health"] = [(h if h["t"] < 59 else {**h, "current": 300_000.0}) for h in second["health"]]
    third = _segment(2, 102.0, 30.0, hits=[(t, 10_000.0) for t in range(0, 30)],
                     health=[(0.2, 295_000.0), (29.0, 0.0)], events=[{"kind": "death", "t": 29.5, "target": "b"}])
    doc = rejoin(_doc(first, second, third))
    a, b, whole = doc["segments"]
    assert a["continued_in"] == 2 and b["continued_in"] == 2
    assert len(a["hits"]) == 40 and len(b["hits"]) == 60 and b["start"] == second["start"]   # pieces as recorded
    assert len(whole["hits"]) == 130 and whole["duration"] == 132.0 and whole["killed"] is True
    assert doc["meta"]["repairs"]["rejoined"] == [[0, 1], [1, 2]]


def test_a_death_that_stretched_a_fight_across_the_next_is_clipped_off():
    trash = _segment(0, 0, 100.0, boss="m", hits=[(t, 1_000.0) for t in range(0, 16)],
                     events=[{"kind": "death", "t": 15.0, "target": "m"}, {"kind": "death", "t": 95.0, "target": "p1"}],
                     health=[(50.0, 400_000.0)], movement=[{"t": 10.0, "x": 1}, {"t": 70.0, "x": 2}],
                     effects=[{"t": 12.0, "end": 90.0, "target": "p1", "skill_id": 1, "source": "p1"}])
    trash["entities"][0].update(is_boss=False, name="Guard")
    boss = _segment(1, 20.0, 80.0, hits=[(t, 10_000.0) for t in range(0, 80)], health=[(0.0, MAX), (30.0, 400_000.0)],
                    events=[{"kind": "death", "t": 75.0, "target": "p1"}])
    doc = rejoin(_doc(trash, boss))
    clipped = doc["segments"][0]
    assert clipped["duration"] == 15.0 and [e["t"] for e in clipped["events"]] == [15.0]
    assert clipped["health"] == [] and clipped["movement"] == [{"t": 10.0, "x": 1}]
    assert clipped["effects"][0]["end"] == 15.0
    assert doc["segments"][1] == boss and doc["meta"]["repairs"]["clipped"] == [0]


def test_a_boss_seen_at_zero_health_is_its_kill():
    seg = _segment(0, 0, 60.0, hits=[(t, 20_000.0) for t in range(0, 50)], health=[(0.0, MAX), (49.5, 0.0)])
    doc = rejoin(_doc(seg))
    assert doc["segments"][0]["killed"] is True and doc["meta"]["repairs"]["killed_at_zero_health"] == [0]
    assert seg["killed"] is False                                    # the source document is left alone
    assert "end_unverified" not in assess(doc, doc["segments"][0])["reasons"]


def test_paired_samples_and_movement_move_onto_the_whole_fights_clock():
    first, second = _halves()
    first.update(ping=[[1.0, 40]], hp=[[2.0, 0.9]], movement=[{"t": 3.0, "x": 1}])
    second.update(ping=[[1.0, 50]], hp=[[2.0, 0.5]], movement=[{"t": 3.0, "x": 2}],
                  effects=[{"t": 0.0, "end": 10.0, "target": "b", "skill_id": 9, "source": "p1", "before": True}])
    first["effects"] = [{"t": 30.0, "end": 40.0, "target": "b", "skill_id": 9, "source": "p1"}]
    whole = merge_segments(first, second)
    assert whole["ping"] == [[1.0, 40], [42.0, 50]] and whole["hp"] == [[2.0, 0.9], [43.0, 0.5]]
    assert whole["movement"] == [{"t": 3.0, "x": 1}, {"t": 44.0, "x": 2}]
    assert whole["effects"] == [{"t": 30.0, "end": 51.0, "target": "b", "skill_id": 9, "source": "p1"}]   # held across the cut: one row


def test_a_continued_piece_is_neither_a_boss_attempt_nor_counted_in_its_run():
    run = summarize(rejoin(_doc(*_halves())))["runs"][0]
    assert run["segments"] == [1] and run["duration"] == 101.0                # the piece's time is not counted twice
    assert len(run["attempts"]) == 1 and run["attempts"][0]["segments"] == [1] and run["attempts"][0]["outcome"] == "kill"


def test_repairing_twice_changes_nothing_and_an_upload_cannot_claim_a_repair():
    once = rejoin(_doc(*_halves()))
    assert rejoin(once) is once
    upload = {"format": "a2log", "version": 1, "meta": {"repairs": {"version": 1}}, "players": PLAYERS,
              "segments": [dict(s, continued_in=1) for s in _halves()]}
    clean = validate(upload)                       # what the server stores: neither mark survives
    assert "repairs" not in clean["meta"] and all("continued_in" not in s for s in clean["segments"])
    assert rejoin(clean)["segments"][0]["continued_in"] == 1
