"""The party scope in the open world after a dungeon, with no zone load between (0.2.412).

Inside a group instance every named player fighting is a party member, since only the party is inside
(``test_party_roster``). That allowance was kept per zone context, which a zone load used to close between the
dungeon and the open world. Since the game's 18 November 2026 patch a recording can go from one to the other
without a zone load the meter recognises: the context stayed the dungeon's, and with the scope set to the party,
every named player fighting nearby in the open world was counted a member. The allowance now follows the run
each effect was recorded in, and runs end at every change of map or instance."""
from aion2calc.meter.a2parser.engine import OPEN_WORLD_MAPS
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession
from test_party_roster import _engine, _fight

DUNGEON, FIELD = 600001, 111035                        # Krao Cave, and an open-world map
ME, ALLY, STRANGERS = 5001, 5002, (5003, 5004)         # the roster names only the ally (decoded short)


def _field_fight(session, engine, start):
    """A mob in the open world, fought by the player and the ally with two strangers nearby."""
    engine.spawn_info[9002] = {"mobCode": 2300171}
    for i in range(5):
        t = start + i * 1000
        session.observe(engine, [DamageEvent(a, 9002, 11010000, 10 * (a - 5000), t + a - 5000)
                                 for a in (ME, ALLY, *STRANGERS)], timestamp_ms=t + 10)


def test_after_a_dungeon_the_open_world_goes_by_the_roster_without_a_zone_load():
    assert FIELD in OPEN_WORLD_MAPS
    session, engine = CombatSession(), _engine(DUNGEON, DUNGEON)
    session.pvp, session.retain_scope = False, "party"
    _fight(session, engine)                                           # the dungeon: everyone present is the party
    assert session.out_of_scope == 0
    epoch = session.epoch
    engine.map_id, engine.dungeon_id = FIELD, 0                       # out into the open world: no zone load
    _field_fight(session, engine, 1_300_000)
    assert session.epoch == epoch and engine.last_zone_reset_ms is None
    assert session.out_of_scope == 10                                 # the strangers' hits are not the party's
    field = [r for r in session.records if r.run == session.run]
    assert {r.event.actor_id for r in field} == {ME, ALLY}
    assert {r["name"] for r in session.snapshot("party")["players"]} == {"Me", "Ally"}
    dungeon_segment, field_segment = session.to_a2log("party")["segments"]
    assert len(dungeon_segment["party_members"]) == 4                 # the dungeon's fight keeps all four
    assert len(field_segment["party_members"]) == 2
    assert sum(h["damage"] for h in field_segment["hits"]) == 5 * (10 + 20)


def test_a_dungeon_entered_from_the_open_world_without_a_zone_load_counts_everyone_present():
    session, engine = CombatSession(), _engine(FIELD, 0)
    session.pvp, session.retain_scope = False, "party"
    _field_fight(session, engine, 1_000_000)                          # the open world first: by the roster
    assert session.out_of_scope == 10
    engine.map_id, engine.dungeon_id = DUNGEON, DUNGEON               # into the dungeon: no zone load
    _fight(session, engine, t0=1_300_000)
    assert session.run == 2 and session.out_of_scope == 10            # nobody's hits dropped inside
    rows = {r["name"]: r["damage"] for r in session.snapshot("party")["players"]}
    assert rows == {"Me": 5000, "Ally": 10000, "Third": 15000, "Fourth": 20000}
