"""A zone load back into the instance the party is already in (a revive after a wipe, an
in-instance teleport) continues the run and keeps the party's identities: the instance id is
restored by the decoder, the run is not split into a second run without entry evidence, and
the roster entries ride along so the next fights export under the same character ids."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

ROSTER = {"Me": {"serverId": 2102, "dbid": 11, "job": "Gladiator", "combatPower": 100_000},
          "Ally": {"serverId": 2102, "dbid": 12, "job": "Cleric", "combatPower": 90_000}}


def _engine(local=5001, ally=5002):
    e = MeterEngine()
    e.names = {local: "Me", ally: "Ally"}
    e.known_players = {local, ally}
    e.roster = dict(ROSTER)
    e.roster_complete = True
    e.local_player_id = local
    e.local_identity_from_game = True
    e.map_id = e.dungeon_id = 600022
    e.last_zone_reset_ms = None
    return e


def _hit(actor, t, target=9001):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=11010000, damage=500, timestamp_ms=t)


def _revive(e, t, local=6001, ally=6002, same_map=True):
    """What the decoder does on the revive's zone load, then on the zone state that follows."""
    e._reset_zone(t)
    e.names = {local: "Me", ally: "Ally"}
    e.known_players = {local, ally}
    e.local_player_id = local
    e.local_identity_from_game = True
    if same_map:
        e._note_map(600022)                                   # the zone state names the same instance map
    else:
        e._note_map(600023)


def test_a_revive_inside_the_instance_continues_the_run_with_the_same_identities():
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    for i in range(6):
        s.observe(e, [_hit(5001, t0 + i * 1000), _hit(5002, t0 + i * 1000 + 100)], timestamp_ms=t0 + i * 1000)
    run_before = s.run
    _revive(e, t0 + 60_000)
    assert e.dungeon_id == 600022 and e.instance_restored   # restored from the pre-reset instance
    s.observe(e, [], timestamp_ms=t0 + 61_000)             # the first observe after the load bumps the epoch
    for i in range(6):
        s.observe(e, [_hit(6001, t0 + 70_000 + i * 1000, target=9002), _hit(6002, t0 + 70_000 + i * 1000 + 100, target=9002)],
                  timestamp_ms=t0 + 70_000 + i * 1000)
    assert s.run == run_before and s.runs[s.run].get("end_reason") is None     # not split as a re-entry
    assert s.runs[s.run]["instance_id"] == 600022
    doc = s.to_a2log("party")
    ids = {p["id"] for p in doc["players"]}
    assert ids == {"p:2102:11", "p:2102:12"}                # the same character ids before and after the load
    assert all(p.get("class") and p.get("server") for p in doc["players"])
    for seg in doc["segments"]:
        assert seg["instance_id"] == 600022 and seg["party_roster_complete"] is True
        assert set(seg["party_members"]) == {"p:2102:11", "p:2102:12"}


def test_a_load_into_another_map_still_closes_the_run():
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    for i in range(4):
        s.observe(e, [_hit(5001, t0 + i * 1000)], timestamp_ms=t0 + i * 1000)
    run_before = s.run
    _revive(e, t0 + 60_000, same_map=False)
    s.observe(e, [], timestamp_ms=t0 + 61_000)
    for i in range(4):
        s.observe(e, [_hit(6001, t0 + 70_000 + i * 1000, target=9002)], timestamp_ms=t0 + 70_000 + i * 1000)
    assert s.run == run_before + 1
    assert s.runs[run_before]["end_reason"] in ("zone_reentry", "map_or_instance_change")


def test_a_re_entry_that_brings_its_own_roster_packet_is_a_new_run():
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    for i in range(4):
        s.observe(e, [_hit(5001, t0 + i * 1000)], timestamp_ms=t0 + i * 1000)
    run_before = s.run
    _revive(e, t0 + 60_000)                                 # the reload restores the instance...
    e._update_roster({"Me": ROSTER["Me"], "Other": {"serverId": 2102, "dbid": 99, "job": "Ranger"}}, True, 600022)
    assert not e.instance_restored                          # ...but a roster packet named it afresh: a real entry
    s.observe(e, [], timestamp_ms=t0 + 61_000)
    for i in range(4):
        s.observe(e, [_hit(6001, t0 + 70_000 + i * 1000, target=9002)], timestamp_ms=t0 + 70_000 + i * 1000)
    assert s.run == run_before + 1 and s.runs[run_before]["end_reason"] == "zone_reentry"
