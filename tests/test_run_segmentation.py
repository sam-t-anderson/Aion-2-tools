"""Run segmentation across zone loads, verified from the signal a real capture
leaves behind: a genuine zone load (instance re-entry, port, revive into a new
instance) reassigns the local player's actor id, while an in-instance phase
teleport keeps it. So every re-entry must become its own run (no 17-players-in-
one-instance merge), the entries we witnessed must not read as partial capture,
and a same-identity phase split must stay one continuing run (0.2.121)."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=500):
    # A job-bearing skill code so observed players resolve without a roster.
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _zone(engine, *, local, members, reset_ms, t):
    """Model a fresh zone load: the engine clears identity and re-identifies the
    local player under a new actor id, then a roster for the new party arrives."""
    engine.last_zone_reset_ms = reset_ms
    engine.local_player_id = local
    engine.names = {local: "Me", **{pid: f"Mate{pid}" for pid in members}}
    engine.known_players = {local, *members}
    engine.roster = {name: {} for name in engine.names.values()}
    engine.map_id = 600002
    engine.dungeon_id = 600002


def test_each_zone_reentry_is_its_own_run_and_live_view_is_the_latest_party():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()

    # The capture joins while already inside the instance, mid-pull: no zone load
    # was witnessed, the local identity is not yet known.
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = None
    engine.names = {}
    engine.roster = {}
    s.observe(engine, [_hit(7001, 9001, 1000), _hit(7001, 9001, 2000)], timestamp_ms=2000)

    # Three genuine re-entries, each reassigning the local id and re-forming a party.
    for reset_ms, local, mates, base in ((100_000, 4062, (4063, 4064), 100_000),
                                         (300_000, 6758, (6759, 6760), 300_000),
                                         (500_000, 9925, (9926, 9927), 500_000)):
        _zone(engine, local=local, members=mates, reset_ms=reset_ms, t=base)
        # Identity packet lands before the next zone's first damage; it must bind
        # to the new run, never backfill the previous one.
        s.observe(engine, [], timestamp_ms=base + 1_000)
        s.observe(engine, [_hit(local, 9001, base + 5_000), _hit(mates[0], 9001, base + 6_000)],
                  timestamp_ms=base + 6_000)

    runs = s.runs
    assert len(runs) == 4, runs                          # one joined-mid-pull run + three re-entries
    assert runs[1].get("start_observed") is not True     # mid-pull join: entry not witnessed
    assert all(runs[r].get("start_observed") for r in (2, 3, 4))  # re-entries were witnessed

    live = s.snapshot(scope="auto", segment_id=None)
    names = {row["name"] for row in live["players"]}
    assert names == {"Me", "Mate9926"}                   # only the latest run's party, not all 3
    assert live["partial_capture"] is False              # a fully-witnessed run is rankable

    # The overlay confirms the re-acquired identity of the latest run, not an
    # earlier zone's actor id.
    assert live["identity_status"]["self_identified"] is True
    assert live["identity_status"]["local_id"] == 9925
    assert live["identity_status"]["local_name"] == "Me"


def test_partial_capture_only_when_the_capture_joined_mid_instance():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me", 5002: "Ally"}
    engine.roster = {"Me": {}, "Ally": {}}
    s.observe(engine, [_hit(5001, 9001, 1000), _hit(5001, 9001, 2000)], timestamp_ms=2000)
    live = s.snapshot(scope="auto", segment_id=None)
    assert live["partial_capture"] is True               # entry never observed -> unranked


def test_in_instance_phase_teleport_keeps_one_run():
    """A mechanic that reloads a sub-zone mid-fight (zone reset, DPS pause) but
    keeps the player's actor id must stay one run so the live meter does not reset."""
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = 10_000
    engine.local_player_id = 4062
    engine.names = {4062: "Me"}
    engine.roster = {"Me": {}}
    s.observe(engine, [_hit(4062, 9001, 11_000), _hit(4062, 9001, 12_000)], timestamp_ms=12_000)
    before = s.run

    # Phase teleport: a new zone reset fires, but the same actor id continues.
    engine.last_zone_reset_ms = 15_000
    s.observe(engine, [], timestamp_ms=15_000)
    s.observe(engine, [_hit(4062, 9001, 18_000), _hit(4062, 9001, 19_000)], timestamp_ms=19_000)

    assert s.run == before                               # still one run, not split
    live = s.snapshot(scope="auto", segment_id=None)
    assert sum(row["damage"] for row in live["players"]) == 2000  # totals carry across the pause
