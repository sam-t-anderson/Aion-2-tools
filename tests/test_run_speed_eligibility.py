"""A legitimate full dungeon clear ranks for speed even when intermediate bosses weren't observed
at exactly full HP at the pull, and when the opening pull's party-roster-complete flag arrived a
beat late — as long as the run's own start (instance entry) was observed, the party is a stable,
fully-identified set, and the final boss was killed. Genuinely incomplete runs are still gated.

This is the fix for a complete run showing unranked: the run's start is the observed instance
entry, not each boss's full-HP pull, and the roster need only be confirmed complete once during a
run whose membership never changes.
"""
from aion2calc.combat import runs
from aion2calc.meter.a2parser.lookup import server_name


def _seg(start, entity, code, roster_complete, full_hp, killed=True):
    health = [{"entity": entity, "t": 0.0 if full_hp else 2.0, "current": 1000 if full_hp else 700, "max": 1000},
              {"entity": entity, "t": 30.0, "current": 0, "max": 1000}]
    return {"run_id": "1", "start": start, "duration": 60.0,
            "run_started_at": "2026-10-15T00:00:00+00:00", "run_ended_at": "2026-10-15T00:10:00+00:00",
            "run_start_observed": True, "run_complete": killed,
            "run_end_reason": "configured_final_boss_death" if killed else "map_or_instance_change",
            "encounter_type": "expedition", "game_patch": "version:product:1.0.21.0", "difficulty": "normal",
            "instance_id": 600092, "map_id": 600092, "party_members": ["p1", "p2"],
            "party_roster_complete": roster_complete,
            "entities": [{"id": entity, "is_boss": True, "mob_code": code}],
            "hits": [{"player": "p1", "damage": 500, "t": 5.0, "target": entity}],
            "events": [{"kind": "death", "target": entity, "t": 30.0}] if killed else [],
            "health": health if killed else health[:1],
            "classification": {"status": "catalog_match"}}


def _doc(roster_first, full_hp, final_killed=True):
    # Two-boss dungeon run (mini-boss then the final boss), Ferocious Horn Den catalog bosses.
    return {"meta": {"capture_scope": "party", "region": "nae",
                     "capture_quality": {"decoder": "a2tools-python-v1", "app_version": "0.2.282", "transport_monitored": True}},
            "players": [{"id": "p1", "name": "Spirited", "class": "gladiator", "server": "2102"},
                        {"id": "p2", "name": "Mate", "class": "cleric", "server": "2102"}],
            "segments": [_seg("2026-10-15T00:00:10+00:00", 9001, 2300908, roster_first, full_hp, True),
                         _seg("2026-10-15T00:05:00+00:00", 9002, 2300910, True, final_killed, final_killed)]}


def _run(doc):
    return runs.summarize(doc)["runs"][0]


def test_complete_run_ranks_without_per_boss_full_hp_pull():
    # The reported bug: bosses killed but never seen at exactly 100% HP at the pull -> unranked.
    r = _run(_doc(roster_first=True, full_hp=False))
    assert r["speed_eligible"] is True, r["speed_reasons"]


def test_complete_run_ranks_when_only_the_opening_pull_roster_was_incomplete():
    # The opening encounter's roster-complete flag lagged, but the party set is stable + identified.
    r = _run(_doc(roster_first=False, full_hp=False))
    assert r["speed_eligible"] is True, r["speed_reasons"]


def test_run_without_a_final_kill_is_still_gated():
    r = _run(_doc(roster_first=True, full_hp=True, final_killed=False))
    assert r["speed_eligible"] is False
    assert "The final recorded boss attempt is not an observed kill." in r["speed_reasons"]


def test_run_with_a_changing_roster_is_still_gated():
    # Different party members between segments is not a stable roster -> gated.
    doc = _doc(roster_first=True, full_hp=True)
    doc["segments"][1]["party_members"] = ["p1", "p3"]
    r = _run(doc)
    assert r["speed_eligible"] is False
    assert "A complete, stable identified party roster is required." in r["speed_reasons"]


def test_run_whose_roster_is_never_confirmed_complete_is_gated():
    doc = _doc(roster_first=False, full_hp=True)
    for s in doc["segments"]:
        s["party_roster_complete"] = False
    r = _run(doc)
    assert r["speed_eligible"] is False
    assert "A complete, stable identified party roster is required." in r["speed_reasons"]


def test_bundled_server_name_resolves_world_name():
    # The world/server name falls back to the bundled table when the live source lacks it.
    assert server_name(2102) == "Zikel"
    assert server_name("2102") == "Zikel"
    assert server_name(99999999) is None


def _timed(final_start, final_duration, kill_t, run_end, extra=None):
    """A complete two-boss run whose final segment starts at ``final_start`` (seconds past 00:05)."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 10, 15, 0, 5, tzinfo=timezone.utc)
    iso = lambda s: (base + timedelta(seconds=s)).isoformat(timespec="microseconds")
    doc = _doc(roster_first=True, full_hp=True)
    final = doc["segments"][1]
    final.update(start=iso(final_start), duration=final_duration)
    final["hits"] = [{"player": "p1", "damage": 500, "t": kill_t, "target": 9002}]
    final["events"] = [{"kind": "death", "target": 9002, "t": final_duration}]
    final["health"] = [{"entity": 9002, "t": 0.0, "current": 1000, "max": 1000}, {"entity": 9002, "t": kill_t, "current": 0, "max": 1000}]
    for segment in doc["segments"]:
        segment["run_ended_at"] = iso(run_end)
    if extra:
        doc["segments"].append({**final, **extra})
    return doc


def test_a_run_ending_on_its_final_kill_is_timed_whatever_the_float_rounding():
    # HDZCQRmzp6's Talisra of the Void: 06:22:29.130 + 121.055 s lands 0.000 000 2 s past the run's end, 06:24:30.185.
    doc = _timed(0, 121.055, 121.055, 121.055)
    for segment in doc["segments"]:
        segment["run_ended_at"] = "2026-10-15T06:24:30.185000+00:00"
    doc["segments"][1]["start"] = "2026-10-15T06:22:29.130000+00:00"
    doc["segments"][0]["start"] = "2026-10-15T06:15:06.973000+00:00"
    for segment in doc["segments"]:
        segment["run_started_at"] = "2026-10-15T06:14:06.148000+00:00"
    r = _run(doc)
    assert r["speed_eligible"] is True, r["speed_reasons"]
    assert abs(r["elapsed_seconds"] - 624.037) < 0.001


def test_what_is_recorded_after_the_final_kill_does_not_untime_the_run():
    # the boss's death record 0.7 s after the killing hit (Gelcos, Divine Auldor)
    assert _run(_timed(0, 60.7, 60.0, 60.0))["speed_eligible"] is True
    # a stretch after Ultimate Berk's death: a mechanic striking the party and its heals, no party damage
    after = {"start": "2026-10-15T00:06:01+00:00", "duration": 19.0, "entities": [], "hits": [], "health": [],
             "events": [{"kind": "damage", "source": 9100, "target": "p1", "t": 2.0, "amount": 100}]}
    r = _run(_timed(0, 60.0, 60.0, 60.0, after))
    assert r["speed_eligible"] is True, r["speed_reasons"]


def test_party_damage_after_the_run_end_still_untimes_it():
    r = _run(_timed(0, 120.0, 100.0, 60.0))      # the party still fighting 40 s after the recorded end
    assert r["speed_eligible"] is False
    assert "Complete, consistent start/end timestamps are unavailable." in r["speed_reasons"]
