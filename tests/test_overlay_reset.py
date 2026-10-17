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


def test_a_mid_fight_add_does_not_move_the_overlay_reset_point():
    # The overlay resets to a fight's *start*. While the boss is still alive, an add promoted to
    # "major" (sustained engagement) must NOT re-point the reset at the add — doing so dropped the
    # running boss's DPS from the overlay mid-combat (the reported regression).
    s = CombatSession()
    s._engage_major((0, 9001), 1000)            # boss pulled
    assert s._live_boss_reset_ms == 1000
    s._engage_major((0, 9500), 9000)            # an add crosses the sustained-engagement threshold mid-fight
    assert s._live_boss_reset_ms == 1000         # overlay still scoped to the boss pull, not the add


def test_a_fresh_fight_after_the_boss_dies_moves_the_reset_point():
    # Once the current boss is dead, the next major pull is a new fight and resets the overlay.
    s = CombatSession()
    s._engage_major((0, 9001), 1000)
    s._dead.add((0, 9001))                       # the boss dies
    s._engage_major((0, 9002), 50000)            # next boss pulled: fresh fight → overlay resets
    assert s._live_boss_reset_ms == 50000


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


def test_finishing_a_run_keeps_the_final_boss_on_the_overlay_until_the_next_run():
    # From a supplied Transcendence run (Talisra of the Void, recorded on 0.2.302): the final boss's
    # death finishes the run, and finishing used to clear the overlay's reset point, so the overlay
    # widened from the boss fight to the whole run (461 s, every pull since entry) the moment the
    # boss died -- which read as damage missing next to another meter still showing the boss fight.
    s = _session_two_bosses()
    s._live_boss_reset_ms = 50000
    s.finish_run("configured_final_boss_death", timestamp_ms=52000)
    live = s.snapshot(scope="self", segment_id=None)
    assert live["players"][0]["damage"] == 3000           # still the final boss fight, not the whole run
    s._next_run()                                         # new combat opens the next run
    assert s._live_boss_reset_ms is None and s._pull_ended_ms is None   # which starts unscoped


# -- majors that left the fight unseen must not hold the overlay on an old fight ------------------
# From a real capture (Deus Research Base, 2026-10-15): two trash mobs the party hit for a few
# seconds were promoted to major twelve seconds after first contact (by elapsed time, the inferred
# elite signal), then left alive with no death record. Eighty-eight seconds later the boss Nazmun
# was pulled and the overlay kept its old reset point: the stale "alive" trash blocked it.
TRASH_CODE, TRASH2_CODE, BOSS_CODE = 2300608, 2300603, 2300615   # Mudthorn, Warrior, Nazmun (catalog boss)


def test_a_major_the_party_left_long_ago_no_longer_blocks_the_next_boss_reset():
    s = CombatSession()
    s._engage_major((0, 20217), 375_000)                  # promoted trash (first contact 06:15)
    s._engage_major((0, 34567), 380_000)
    s._boss_hit_ms[(0, 20217)] = s._boss_hit_ms[(0, 34567)] = 381_000   # the party's last hits on them
    s._engage_major((0, 51000), 469_000)                  # the boss pulled 88 s later
    assert s._live_boss_reset_ms == 469_000


def test_a_major_still_being_fought_keeps_holding_the_reset():
    s = CombatSession()
    s._engage_major((0, 20217), 375_000)
    s._boss_hit_ms[(0, 20217)] = 460_000                  # still being hit 9 s before the boss joins
    s._engage_major((0, 51000), 469_000)
    assert s._live_boss_reset_ms == 375_000               # one fight: the pack and the boss together


def test_a_catalog_boss_holds_the_reset_through_a_long_untargetable_phase():
    s = CombatSession()
    s.identities[0] = {"names": {}, "spawns": {9001: {"mobCode": BOSS_CODE}}, "jobs": {}, "local_id": None,
                       "owners": {}, "roster": {}, "observed_players": set()}
    s._engage_major((0, 9001), 1_000)
    s._boss_hit_ms[(0, 9001)] = 10_000                    # last hit before it turned untargetable
    s._engage_major((0, 9500), 70_000)                    # an add promoted 60 s into the phase: same fight
    assert s._live_boss_reset_ms == 1_000
    s._engage_major((0, 9600), 140_000)                   # untouched for 130 s: no longer holding the fight
    assert s._live_boss_reset_ms == 140_000


def _engine(spawns):
    from aion2calc.meter.a2parser.engine import MeterEngine
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600053
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = 4062
    engine.names = {4062: "Me"}
    engine.known_players = {4062}
    engine.roster = {"Me": {}}
    engine.spawn_info = {entity: {"mobCode": code} for entity, code in spawns.items()}
    return engine


def _hit(target, t):
    return DamageEvent(actor_id=4062, target_id=target, skill_code=15210000, damage=500, timestamp_ms=t)


def test_trash_left_alive_no_longer_keeps_the_overlay_on_the_old_fight():
    """The capture's sequence through the session: trash hit and left alive is promoted by elapsed
    time; the boss pull 88 s later resets the overlay, the boss's death ends the pull even though
    the trash was never seen dying, and the next combat starts the overlay fresh again."""
    trash, trash2, boss = 20217, 34567, 51000
    engine = _engine({trash: TRASH_CODE, trash2: TRASH2_CODE, boss: BOSS_CODE})
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [_hit(trash, 375_000)], timestamp_ms=375_000)
    s.observe(engine, [_hit(trash, 381_000)], timestamp_ms=381_000)   # the party moves on; no death record
    s.observe(engine, [], timestamp_ms=390_000)                         # 15 s after first contact
    assert (s.epoch, trash) in s._engaged_major                         # promoted, and never seen dying
    s.observe(engine, [_hit(boss, 469_000)], timestamp_ms=469_000)      # the boss pulled 88 s later
    assert s._live_boss_reset_ms == 469_000                             # the overlay starts on the boss
    engine.telemetry = [{"kind": "death", "entity": boss, "timestamp_ms": 500_000}]
    s.observe(engine, [], timestamp_ms=500_000)
    engine.telemetry = []
    assert s._pull_ended_ms == 500_000                                  # the stale trash does not keep it open
    s.observe(engine, [_hit(trash2, 520_000)], timestamp_ms=520_000)    # the next combat
    assert s._live_boss_reset_ms == 520_000


def test_the_overlay_stays_on_the_final_boss_when_its_death_finishes_the_run():
    """The supplied run's chain through ``observe()``: Ruthilis of Pain dies, Talisra of the Void
    (the dungeon's catalog final boss) is pulled at once and killed, its death finishes the run
    automatically -- and the overlay still shows the Talisra fight, not every pull since entry.
    The next combat opens a new run, which the overlay shows on its own."""
    ruthilis, talisra, trash = 31000, 25417, 40000
    engine = _engine({ruthilis: 2350708, talisra: 2350709, trash: TRASH_CODE})
    engine.map_id = engine.dungeon_id = 600065                      # their instance in the catalog
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    for t in range(110_000, 270_001, 20_000):                       # Ruthilis: a steady fight
        s.observe(engine, [_hit(ruthilis, t)], timestamp_ms=t)
    engine.telemetry = [{"kind": "death", "entity": ruthilis, "timestamp_ms": 278_000}]
    s.observe(engine, [], timestamp_ms=278_000)
    engine.telemetry = []
    talisra_hits = list(range(278_900, 450_001, 20_000))           # pulled within a second
    for t in talisra_hits:
        s.observe(engine, [_hit(talisra, t)], timestamp_ms=t)
    engine.telemetry = [{"kind": "death", "entity": talisra, "timestamp_ms": 453_900}]
    s.observe(engine, [], timestamp_ms=453_900)
    engine.telemetry = []
    assert s.run_closed and s.runs[s.run]["end_reason"] == "configured_final_boss_death"
    live = s.snapshot(scope="self", segment_id=None)
    assert live["players"][0]["damage"] == 500 * len(talisra_hits)  # the Talisra fight, not Ruthilis's too
    s.observe(engine, [_hit(trash, 600_000)], timestamp_ms=600_000)   # the next combat: a new run
    live = s.snapshot(scope="self", segment_id=None)
    assert not s.run_closed and live["players"][0]["damage"] == 500
