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


def _session_two_bosses():
    """One run: a first boss (1000 dmg), then a second boss pulled ~48s later (3000 dmg).
    Same epoch/run and under the gap, so without a boss-start reset it is one live encounter."""
    s = CombatSession()
    s.pvp = False
    s.gap_seconds = 120
    player, boss1, boss2 = 101, 9001, 9002
    s.identities[0] = {"names": {player: "Me"}, "spawns": {}, "jobs": {}, "local_id": player,
                       "owners": {}, "roster": {}, "observed_players": {player}}
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1

    def hit(t, target, dmg, seq):
        ev = DamageEvent(actor_id=player, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)
        return Record(0, ev, frozenset(), player, 0, 1, seq)
    s.records = [hit(1000, boss1, 500, 1), hit(2000, boss1, 500, 2),       # first boss: 1000
                 hit(50000, boss2, 1000, 3), hit(51000, boss2, 2000, 4)]   # second boss pull: 3000
    return s


def test_reset_on_boss_start_defaults_on():
    assert CombatSession().reset_on_boss_start is True


def test_engaging_a_major_marks_the_live_reset_point():
    # Every major engagement (boss / mini-boss / field / world boss) records where the overlay resets to.
    s = CombatSession()
    s._engage_major((0, 9001), 12345)
    assert s._live_boss_reset_ms == 12345


def test_live_meter_resets_to_the_current_boss_pull_when_enabled():
    s = _session_two_bosses()
    s._live_boss_reset_ms = 50000                 # the second boss was engaged at t=50000
    s.reset_on_boss_start = True                  # the default
    live = s.snapshot(scope="self", segment_id=None)
    assert live["players"][0]["damage"] == 3000   # only the current boss fight, not the earlier boss's 1000


def test_live_meter_keeps_the_whole_run_when_the_setting_is_off():
    s = _session_two_bosses()
    s._live_boss_reset_ms = 50000
    s.reset_on_boss_start = False
    live = s.snapshot(scope="self", segment_id=None)
    assert live["players"][0]["damage"] == 4000   # both bosses retained


def test_finishing_a_run_clears_the_live_reset_point():
    s = _session_two_bosses()
    s._live_boss_reset_ms = 50000
    s.finish_run("test")
    assert s._live_boss_reset_ms is None           # a new run's overlay starts unscoped
