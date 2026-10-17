"""Packet-sourced combat info the overlay shows: the local player's contribution
(share of the shown encounter) and the current target (the enemy the local player
hits most) with each contributor's damage/DPS. Both are derived from recorded
damage only — never invented."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _session():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me", 5002: "Ally"}
    engine.roster = {"Me": {}, "Ally": {}}
    return s, engine


def test_contribution_is_the_local_players_share():
    s, engine = _session()
    # Me deals 3000 to the boss, Ally deals 1000 → Me's share is 75%.
    s.observe(engine, [_hit(5001, 9001, 1000, 2000), _hit(5001, 9001, 2000, 1000),
                       _hit(5002, 9001, 2000, 1000)], timestamp_ms=2000)
    snap = s.snapshot(scope="auto", segment_id=None)
    c = snap["contribution"]
    assert c is not None
    assert c["name"] == "Me"
    assert c["damage"] == 3000
    assert round(c["share"], 2) == 0.75


def test_current_target_follows_the_most_recently_hit_enemy():
    # The overlay target must follow a target switch — not stick to whichever enemy
    # accumulated the most damage earlier (e.g. a boss you just left or killed).
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 1000, 5000),   # me → boss, earlier, huge damage
                       _hit(5001, 9002, 1500, 200),    # me → new mob, most recent
                       _hit(5002, 9002, 1600, 100)],   # ally → the new mob too
              timestamp_ms=2000)
    snap = s.snapshot(scope="auto", segment_id=None)
    target = snap["current_target"]
    assert target is not None
    assert str(9002) in target["key"]                 # the enemy hit most recently, not 9001
    assert target["is_player"] is False
    names = [c["name"] for c in target["contributors"]]
    assert "Me" in names and "Ally" in names           # contributors to that target
    me = next(c for c in target["contributors"] if c["name"] == "Me")
    assert me["damage"] == 200 and me["dps"] > 0


def test_target_dps_runs_on_the_fight_clock_through_an_untargetable_phase():
    # A boss hit for two seconds, untargetable for twenty, then hit for two more: its DPS is
    # damage over the 23 s from the first hit to the last, as other meters and the log page
    # measure a boss fight -- not over the four seconds in which it was hit (Talisra of the
    # Void read about 8% high next to another meter this way).
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 1000, 1000), _hit(5001, 9001, 2000, 1000)], timestamp_ms=2000)
    s.observe(engine, [_hit(5001, 9001, 22000, 1000), _hit(5001, 9001, 23000, 1000)], timestamp_ms=23000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    me = next(c for c in target["contributors"] if c["name"] == "Me")
    assert me["damage"] == 4000
    assert round(me["dps"], 2) == round(4000 / 23, 2)


def test_ttk_uses_the_observed_hp_decline_rate_not_only_our_dps():
    # Time-to-kill must reflect how fast the enemy is really dying (all damage
    # sources), not just the observed party's DPS. A mob we only tag for a little
    # damage, but whose HP drops fast because others are hitting it, should show a
    # short TTK — not the long one our small DPS alone would imply.
    s, engine = _session()
    engine.telemetry = [
        {"kind": "hp", "entity": 9001, "current": 100000, "max": 100000, "timestamp_ms": 1000},
        {"kind": "hp", "entity": 9001, "current": 50000, "max": 100000, "timestamp_ms": 6000},
    ]
    # We deal only 2000 total to 9001 across the 5 seconds (others do the rest).
    s.observe(engine, [_hit(5001, 9001, 1000, 1000), _hit(5001, 9001, 6000, 1000)], timestamp_ms=6000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target is not None and target["current_hp"] == 50000
    # Observed decline: 50000 HP over 5s = 10000 HP/s -> TTK = 50000/10000 = 5s.
    # The party-DPS-only estimate (2000 dmg over the duration) would be far larger.
    assert target["ttk"] is not None and abs(target["ttk"] - 5.0) < 0.6


def test_players_get_a_stable_party_number():
    s, engine = _session()
    engine.names = {5001: "Me", 5002: "Ally", 5003: "Bob"}
    engine.roster = {"Me": {}, "Ally": {}, "Bob": {}}
    s.observe(engine, [_hit(5001, 9001, 1000, 300), _hit(5002, 9001, 1000, 900), _hit(5003, 9001, 1000, 100)],
              timestamp_ms=1000)
    rows = s.snapshot(scope="auto", segment_id=None)["players"]
    numbers = {row["name"]: row["party_number"] for row in rows}
    # Numbered by key (stable), not by damage rank; every player gets a distinct 1..N.
    assert sorted(numbers.values()) == [1, 2, 3]
    # Re-snapshotting keeps the same assignment.
    again = {r["name"]: r["party_number"] for r in s.snapshot(scope="auto", segment_id=None)["players"]}
    assert numbers == again


def test_no_target_or_contribution_before_any_damage():
    s, engine = _session()
    s.observe(engine, [], timestamp_ms=1000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["current_target"] is None
    assert snap["contribution"] is None


def test_enemy_hp_and_ttk_from_observed_hp():
    s, engine = _session()
    # The game reports the boss at 5000/10000 HP; Me lands one 5000 hit in one
    # second → DPS 5000 → remaining 5000 → TTK 1s, HP 50%.
    engine.telemetry = [{"kind": "hp", "entity": 9001, "current": 5000, "max": 10000, "timestamp_ms": 2000}]
    s.observe(engine, [_hit(5001, 9001, 2000, 5000)], timestamp_ms=2000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target["current_hp"] == 5000
    assert target["max_hp"] == 10000
    assert target["hp_pct"] == 0.5
    assert round(target["ttk"], 2) == 1.0


def test_target_hp_and_ttk_blank_without_observed_hp():
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 2000, 5000)], timestamp_ms=2000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target["current_hp"] is None       # never captured -> never guessed
    assert target["hp_pct"] is None
    assert target["ttk"] is None
    assert target["ttk_fraction"] is None     # the TTK bar stays blank with no TTK


def test_also_targets_names_enemies_struck_in_the_same_instant():
    # AOE/cleave: the local player hits two enemies within the same ~1s bucket, so
    # the single "most-hit" target is genuinely one of several — name the other too.
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 2000, 500),    # me -> mob A, bucket 2
                       _hit(5001, 9002, 2100, 400)],   # me -> mob B, same bucket 2, most recent
              timestamp_ms=2100)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target is not None
    assert "9002" in target["key"]                     # primary is the most-recently hit
    assert target["also_targets"] == ["Enemy #9001"]   # the other one struck in the same instant


def test_also_targets_empty_on_a_sequential_target_switch():
    # Hitting mob A, then switching to mob B a few seconds later, is not simultaneous:
    # A's last hit is in an earlier second, so it must not be listed as also-target.
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 2000, 500),    # me -> mob A, bucket 2
                       _hit(5001, 9002, 5000, 400)],   # me -> mob B, bucket 5 (switch)
              timestamp_ms=5000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target is not None and "9002" in target["key"]
    assert target["also_targets"] == []


def test_ttk_fraction_tracks_elapsed_over_estimated_whole_kill():
    # The time-based TTK bar fills by engaged time so far over (engaged + remaining).
    # Same scenario as the HP-decline TTK test: 50000 HP left, dropping 10000/s ->
    # TTK 5s; we have been fighting it 6 s on the fight clock (first hit at t=1000, latest
    # at t=6000), so the fraction is ~6/(6+5) -- half the HP gone, about half the kill's time
    # elapsed -- and must stay in (0, 1): never guessed, never out of range.
    s, engine = _session()
    engine.telemetry = [
        {"kind": "hp", "entity": 9001, "current": 100000, "max": 100000, "timestamp_ms": 1000},
        {"kind": "hp", "entity": 9001, "current": 50000, "max": 100000, "timestamp_ms": 6000},
    ]
    s.observe(engine, [_hit(5001, 9001, 1000, 1000), _hit(5001, 9001, 6000, 1000)], timestamp_ms=6000)
    target = s.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target["ttk"] is not None and target["ttk_fraction"] is not None
    assert 0.0 < target["ttk_fraction"] < 1.0
    assert abs(target["ttk_fraction"] - 6.0 / (6.0 + 5.0)) < 0.1


def test_local_combat_power_is_surfaced_when_captured():
    s, engine = _session()
    # The game's character-info scan records combat power in the local player's spawn.
    engine.spawn_info = {5001: {"combatPower": 48213}}
    s.observe(engine, [_hit(5001, 9001, 1000, 500)], timestamp_ms=1000)
    assert s.snapshot(scope="auto", segment_id=None)["identity_status"]["local_combat_power"] == 48213


def test_local_combat_power_is_none_without_data():
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 1000, 500)], timestamp_ms=1000)
    assert s.snapshot(scope="auto", segment_id=None)["identity_status"]["local_combat_power"] is None


def test_dummy_parse_appears_only_against_a_training_dummy():
    s, engine = _session()
    s.dummy_record_seconds = 60
    # 2000000 (Punching Bag) is a training dummy in the catalog; isDummy is true.
    engine.spawn_info = {9001: {"mobCode": 2000000}}
    s.observe(engine, [_hit(5001, 9001, 1000, 1000), _hit(5001, 9001, 2000, 1000)], timestamp_ms=2000)
    snap = s.snapshot(scope="auto", segment_id=None)
    parse = snap["dummy_parse"]
    assert parse is not None
    assert snap["current_target"]["is_dummy"] is True
    assert parse["window_seconds"] == 60
    assert parse["window_reached"] is False          # only ~1s of parse so far
    assert parse["your_dps"] and parse["your_dps"] > 0


def test_dummy_parse_absent_against_a_normal_enemy():
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 2702071}}   # a plain mob, not a dummy
    s.observe(engine, [_hit(5001, 9001, 1000, 1000)], timestamp_ms=1000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["dummy_parse"] is None
    assert snap["current_target"]["is_dummy"] is False


def test_party_member_death_indicator():
    s, engine = _session()
    # Both party members fight the boss; Ally (5002) then dies with no recovery.
    engine.telemetry = [{"kind": "death", "entity": 5002, "timestamp_ms": 3000}]
    s.observe(engine, [_hit(5001, 9001, 2000, 1000), _hit(5002, 9001, 2000, 1000)], timestamp_ms=3000)
    players = {row["name"]: row for row in s.snapshot(scope="auto", segment_id=None)["players"]}
    assert players["Ally"]["dead"] is True
    assert players["Me"]["dead"] is False


def test_death_indicator_clears_when_the_member_recovers():
    s, engine = _session()
    engine.telemetry = [{"kind": "death", "entity": 5002, "timestamp_ms": 3000},
                        {"kind": "hp", "entity": 5002, "current": 1200, "max": 4000, "timestamp_ms": 4000}]
    s.observe(engine, [_hit(5001, 9001, 2000, 1000), _hit(5002, 9001, 2000, 1000)], timestamp_ms=4000)
    players = {row["name"]: row for row in s.snapshot(scope="auto", segment_id=None)["players"]}
    assert players["Ally"]["dead"] is False   # a later HP>0 sample revives the row


def test_latest_hp_prefers_max_observed_at_full_hp():
    # Max HP is taken from a sample seen at full (current >= max); a later mid-fight
    # sample carrying a spuriously larger max must NOT inflate the reported max.
    s = CombatSession()
    eid = 9001
    for cur, mx, ts in [(120000, 120000, 1000), (60000, 120000, 2000),
                        (30000, 999999, 3000), (0, 120000, 4000)]:
        s.telemetry.append({"kind": "hp", "entity": eid, "current": cur, "max": mx,
                            "timestamp_ms": ts, "epoch": 0})
    current, maximum = s._latest_hp(eid, {0})
    assert current == 0            # most recent sample
    assert maximum == 120000       # full-HP max, not the spurious 999999


def test_latest_hp_falls_back_to_largest_when_never_seen_at_full():
    # Joined mid-fight (never current >= max): fall back to the largest max seen.
    s = CombatSession()
    eid = 9002
    for cur, mx, ts in [(40000, 120000, 1000), (20000, 120000, 2000)]:
        s.telemetry.append({"kind": "hp", "entity": eid, "current": cur, "max": mx,
                            "timestamp_ms": ts, "epoch": 0})
    _, maximum = s._latest_hp(eid, {0})
    assert maximum == 120000
