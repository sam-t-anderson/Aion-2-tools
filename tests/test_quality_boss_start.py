"""A boss fight starts "whole" when the boss was seen at (essentially) full health before the
party's first hit: the opening hit lands with the first HP sample (a hair below max at t=0),
and a boss first seen at full health before a merged trash pull still started from the top."""
from aion2calc.combat.quality import assess


def _segment(samples, first_hit=0.0):
    return {"label": "Gelcos", "boss": "Gelcos", "duration": 135.0, "killed": True, "encounter_type": "transcendence",
            "game_patch": "version:product:1.0.21.0", "difficulty": "stage 3",
            "entities": [{"id": "b", "name": "Gelcos", "kind": "enemy", "is_boss": True, "mob_code": 2343616}],
            "hits": [{"t": first_hit, "player": "p1", "target": "b", "damage": 2434.0}, {"t": first_hit + 1, "player": "p1", "target": "b", "damage": 1.0}],
            "events": [{"kind": "death", "t": 130.0, "target": "b"}],
            "health": samples}


DOC = {"meta": {"capture_scope": "party", "capture_quality": {}}, "players": [{"id": "p1", "name": "Me", "class": "gladiator", "server": "2102"}]}


def test_the_opening_hit_landing_with_the_first_sample_is_a_full_health_start():
    seg = _segment([{"t": 0.0, "entity": "b", "current": 9685166.0, "max": 9687600.0}])
    assert "start_unverified" not in assess(DOC, seg)["reasons"]


def test_a_boss_seen_full_before_the_pull_counts_even_after_trash():
    seg = _segment([{"t": 63.6, "entity": "b", "current": 9687600.0, "max": 9687600.0},
                    {"t": 120.5, "entity": "b", "current": 9633181.0, "max": 9687600.0}], first_hit=119.45)
    assert "start_unverified" not in assess(DOC, seg)["reasons"]


def test_a_boss_first_seen_well_into_the_fight_is_still_unverified():
    seg = _segment([{"t": 40.0, "entity": "b", "current": 6000000.0, "max": 9687600.0}])
    assert "start_unverified" in assess(DOC, seg)["reasons"]
    seg = _segment([{"t": 10.0, "entity": "b", "current": 9687600.0, "max": 9687600.0}], first_hit=0.0)   # seen full only after the pull
    assert "start_unverified" in assess(DOC, seg)["reasons"]
    seg = _segment([{"t": 0.0, "entity": "b", "current": 9500000.0, "max": 9687600.0}])                   # 2% gone at the first sample
    assert "start_unverified" in assess(DOC, seg)["reasons"]


def test_a_sparse_first_reading_counts_when_the_damage_before_it_makes_up_full_health():
    # the opening burst (5% of max) lands before the boss's first reading at 95%: it started whole
    seg = _segment([{"t": 3.0, "entity": "b", "current": 9203220.0, "max": 9687600.0}])
    seg["hits"] = [{"t": t, "player": "p1", "target": "b", "damage": 160000.0} for t in (0.0, 1.0, 2.0)] + seg["hits"][1:]
    assert "start_unverified" not in assess(DOC, seg)["reasons"]
    seg["hits"] = [{"t": 0.0, "player": "p1", "target": "b", "damage": 100000.0}]           # 1% recorded: 4% unexplained
    assert "start_unverified" in assess(DOC, seg)["reasons"]


def test_a_reconstructed_start_stops_at_a_heal_a_reset_or_after_half_a_minute():
    burst = [{"t": t, "player": "p1", "target": "b", "damage": 160000.0} for t in (0.0, 1.0, 2.0)]
    seg = _segment([{"t": 35.0, "entity": "b", "current": 9203220.0, "max": 9687600.0}])
    seg["hits"] = burst
    assert "start_unverified" in assess(DOC, seg)["reasons"]                                 # first read 35 s in
    seg = _segment([{"t": 2.5, "entity": "b", "current": 8000000.0, "max": 9687600.0},       # 17% gone, 3% explained
                    {"t": 3.0, "entity": "b", "current": 9600000.0, "max": 9687600.0}])      # then higher: a heal
    seg["hits"] = burst
    assert "start_unverified" in assess(DOC, seg)["reasons"]


def test_a_boss_flagged_entity_the_party_never_struck_neither_starts_nor_ends_the_fight():
    seg = _segment([{"t": 0.0, "entity": "b", "current": 9687600.0, "max": 9687600.0}])
    seg["entities"].append({"id": "copy", "name": "Atiel", "kind": "enemy", "is_boss": True, "mob_code": 2920445})
    seg["health"].append({"t": 50.0, "entity": "copy", "current": 100.0, "max": 1000.0})
    reasons = assess(DOC, seg)["reasons"]
    assert "start_unverified" not in reasons and "end_unverified" not in reasons


def test_a_boss_seen_at_zero_health_ends_the_fight_without_a_death_record():
    seg = _segment([{"t": 0.0, "entity": "b", "current": 9687600.0, "max": 9687600.0},
                    {"t": 130.0, "entity": "b", "current": 0.0, "max": 9687600.0}])
    seg["events"], seg["killed"] = [], False
    assert "end_unverified" not in assess(DOC, seg)["reasons"]
    seg["health"].pop()
    assert "end_unverified" in assess(DOC, seg)["reasons"]


def test_a_map_that_is_its_own_instance_is_entry_evidence_when_the_entry_was_seen():
    seg = _segment([{"t": 0.0, "entity": "b", "current": 9687600.0, "max": 9687600.0}])
    seg.update(run_start_observed=True, classification={"basis": "recorded_map", "catalog_instance_id": 910011,
                                                        "recorded_instance_id": 0, "npc_instance_ids": [910011]})
    assert "classification_map_only" not in assess(DOC, seg)["reasons"]
    seg["run_start_observed"] = False                                       # the recording may have begun mid-run
    assert "classification_map_only" in assess(DOC, seg)["reasons"]
    seg["run_start_observed"] = True
    seg["classification"]["npc_instance_ids"] = [910011, 600058]            # bosses of more than one instance
    assert "classification_map_only" in assess(DOC, seg)["reasons"]
