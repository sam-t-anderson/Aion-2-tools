"""A mid-fight self zone-transition (a mechanic that pauses DPS) must not reset
the live meter/overlay: the continuing run's epochs re-join in the latest view."""
from aion2calc.meter.session import CombatSession, Record
from aion2calc.meter.a2parser.models import DamageEvent


def _session_two_epochs():
    """A player hits one boss, a mechanic splits the run into epoch 0 and 1
    (same run, ~3s pause), then the player keeps hitting the same boss."""
    s = CombatSession()
    s.pvp = False
    s.gap_seconds = 120
    player, boss = 101, 9001
    for epoch in (0, 1):
        s.identities[epoch] = {"names": {player: "Me"}, "spawns": {}, "jobs": {}, "local_id": player,
                               "owners": {}, "roster": {}, "observed_players": {player}}
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1
    def hit(epoch, t, dmg, seq):
        ev = DamageEvent(actor_id=player, target_id=boss, skill_code=15210000, damage=dmg, timestamp_ms=t)
        return Record(epoch, ev, frozenset(), player, 0, 1, seq)
    s.records = [hit(0, 1000, 500, 1), hit(0, 2000, 500, 2),      # first phase: 1000 damage
                 hit(1, 5000, 700, 3), hit(1, 6000, 300, 4)]       # after a ~3s mechanic pause: 1000 damage
    return s, player, boss


def test_latest_view_merges_the_continuing_run_across_the_epoch_split():
    s, player, boss = _session_two_epochs()
    live = s.snapshot(scope="self", segment_id=None)
    assert len(live["players"]) == 1                      # one person, not two
    assert live["players"][0]["name"] == "Me"
    assert live["players"][0]["damage"] == 2000           # totals carry across the mechanic, not reset to 1000
    # two segments are still listed, so the user can still inspect each phase separately
    assert len(live["segments"]) == 2


def test_explicit_segment_selection_still_shows_one_phase():
    s, s_player, s_boss = _session_two_epochs()
    live = s.snapshot(scope="self", segment_id=None)
    latest_id = live["segments"][-1]["id"]
    one = s.snapshot(scope="self", segment_id=latest_id)
    assert one["players"][0]["damage"] == 1000            # a specific segment stays epoch-scoped (post-pause only)
