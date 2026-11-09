"""A whole arena match is ranked (0.2.396). PvP has no difficulty, so its fights no longer need one, and an arena
match's start and end are verified by the game's own records: the meter saw the arena entered, and the fight holds
every round from the first and the match's result. Any other PvP fight, an arena fight cut short included, stays
unranked; a PvE fight still needs its difficulty."""
from aion2calc.combat.quality import arena_match_whole, assess


def _segment(**more):
    arena = {"match": 16951524, "result": "loss", "rounds_won": 1, "rounds_lost": 3, "rating": 1579,
             "fighters": [{"name": "Me", "class": "templar", "server": "2102", "self": True},
                          {"name": "Foe", "class": "ranger", "server": "1108"}],
             "rounds": [{"round": n, "t": t, "winner": w, "loser": 1 - w}
                        for n, t, w in ((1, 2.6, 1), (2, 41.5, 1), (3, 59.3, 0), (4, 91.9, 1))]}
    segment = {"duration": 91.9, "encounter_type": "pvp_arena", "zone": "Fire Temple Arena", "map_id": 60,
               "game_patch": "version:product:2.0.10.0", "run_start_observed": True, "arena": arena,
               "hits": [{"player": "p", "damage": 637, "t": 1.65}]}
    segment.update(more)
    return segment


def _reasons(segment):
    capture = {"decoder": "a2tools-python-v1", "app_version": "0.2.396", "transport_monitored": True}
    doc = {"meta": {"capture_scope": "party", "capture_quality": capture},
           "players": [{"id": "p", "name": "Me", "server": "2102", "class": "templar"}], "segments": [segment]}
    return assess(doc, segment)["reasons"]


def test_a_whole_arena_match_is_ranked_without_a_difficulty():
    assert arena_match_whole(_segment())
    assert _reasons(_segment()) == []


def test_an_arena_fight_that_is_not_the_whole_match_stays_unranked():
    no_result = _segment()
    del no_result["arena"]["result"]                                        # the match ended outside the fight
    late = _segment()
    late["arena"]["rounds"] = late["arena"]["rounds"][1:]                   # the fight began after the first round
    gap = _segment()
    del gap["arena"]["rounds"][1]                                           # a round missing in between
    unseen_entry = _segment(run_start_observed=False)                       # the arena entry was not seen
    no_records = _segment(arena=None)                                       # no arena records at all
    for segment in (no_result, late, gap, unseen_entry, no_records):
        assert not arena_match_whole(segment)
        assert "pvp_boundaries_unverified" in _reasons(segment)


def test_other_pvp_stays_unranked_and_pve_still_needs_its_difficulty():
    open_world = _segment(encounter_type="pvp_open_world", zone="Abyss", map_id=20)
    assert "pvp_boundaries_unverified" in _reasons(open_world)
    assert "missing_metadata" not in _reasons(open_world)                   # PvP has no difficulty
    assert "missing_metadata" in _reasons(_segment(game_patch=None))        # but it needs its game version
    pve = _segment(encounter_type="dungeon", arena=None)
    assert "missing_metadata" in _reasons(pve)
    assert "missing_metadata" not in _reasons({**pve, "difficulty": "normal"})
