"""The overlay community-rank badge helper (aion2calc.combat.community_rank).

Pure interpretation of a log server rankings payload into a compact per-player badge.
It must prefer the most specific populated scope, degrade gracefully on partial or
unexpected payloads (showing nothing rather than raising), and phrase a percentile as a
"top N%" finish.
"""
from aion2calc.combat import community_rank as cr


def _rankings(server=None, region=None, world=None, pid="p1"):
    def scope(pct):
        return None if pct is None else {"percentile": pct, "rank": 1, "count": 10}
    return {"players": [{"id": pid, "name": "Me", "server": scope(server),
                         "region": scope(region), "world": scope(world)}]}


def test_prefers_the_most_specific_available_scope():
    summary = cr.for_player(_rankings(server=90.0, region=80.0, world=70.0), "p1")
    assert summary["best"]["scope"] == "server" and summary["best"]["percentile"] == 90.0
    assert summary["scopes"] == {"server": 90.0, "region": 80.0, "world": 70.0}


def test_falls_back_to_region_then_world_when_narrower_scopes_abstain():
    assert cr.for_player(_rankings(server=None, region=82.0, world=61.0), "p1")["best"]["scope"] == "region"
    assert cr.for_player(_rankings(server=None, region=None, world=61.0), "p1")["best"]["scope"] == "world"


def test_returns_none_when_no_scope_ranks_or_player_absent():
    assert cr.for_player(_rankings(), "p1") is None                      # every scope None
    assert cr.for_player(_rankings(world=50.0), "someone-else") is None  # no such player


def test_defensive_against_partial_and_unexpected_payloads():
    assert cr.for_player(None, "p1") is None
    assert cr.for_player({}, "p1") is None
    assert cr.for_player({"players": "nope"}, "p1") is None
    assert cr.for_player({"players": [{"id": "p1", "world": {"percentile": "high"}}]}, "p1") is None
    assert cr.for_player({"players": [{"id": "p1", "world": {"percentile": 150}}]}, "p1") is None


def test_confident_only_excludes_provisional_or_thin_cohorts():
    # The server marks a too-thin or incomparable standing with a non-"available"
    # status; such a scope must not produce a badge even though it carries a number.
    rankings = {"players": [{"id": "p1", "name": "Me",
                             "server": {"percentile": 95.0, "status": "unavailable"},
                             "region": {"percentile": 88.0, "status": "available"},
                             "world": {"percentile": 70.0, "status": "available"}}]}
    summary = cr.for_player(rankings, "p1")
    assert summary["best"]["scope"] == "region"          # the provisional server scope is skipped
    assert "server" not in summary["scopes"]


def test_badges_maps_each_player_with_a_confident_standing():
    rankings = {"players": [
        {"id": "me", "world": {"percentile": 90.0, "status": "available"}},
        {"id": "friend", "region": {"percentile": 60.0, "status": "available"}},
        {"id": "nobody", "world": {"percentile": 50.0, "status": "unavailable"}}]}
    out = cr.badges(rankings, ["me", "friend", "nobody", "absent"])
    assert set(out) == {"me", "friend"}                  # thin + absent players omitted
    assert out["me"]["best"]["scope"] == "world" and out["friend"]["best"]["scope"] == "region"
    assert cr.badges(rankings, []) == {}


def test_badge_text_phrases_percentile_as_a_top_finish():
    assert cr.badge_text(cr.for_player(_rankings(world=92.0), "p1")) == "World Top 8%"
    assert cr.badge_text(cr.for_player(_rankings(server=99.5), "p1")) == "Server Top 0.5%"
    assert cr.badge_text(None) == ""
    assert cr.badge_text({"best": {}}) == ""
