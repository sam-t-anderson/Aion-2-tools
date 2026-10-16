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
