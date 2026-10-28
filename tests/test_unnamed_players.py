"""An actor the capture has no name or spawn record for is exported by what it did (0.2.354): one that
struck only with a player's own class skills is a player of that class (an arena opponent, a stranger
in the Abyss), not an enemy of unknown NPC type; one that struck with an NPC's skill stays an enemy.
A class skill's heal is no evidence: a draining skill's heal record names the enemy as its actor.
Recordings of 0.2.353 and earlier carry such players as untyped enemies; the catalog coverage counts
them as unnamed players, not as NPCs whose type is missing."""
from aion2calc.combat.catalog import coverage
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, skill):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=500, timestamp_ms=t)


def test_an_unnamed_actor_striking_with_class_skills_is_a_player_of_that_class():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id, engine.last_zone_reset_ms, engine.local_player_id = 20, None, 5001
    engine.names, engine.roster = {5001: "Me"}, {"Me": {}}
    t0 = 1_000_000
    events = [_hit(7001, 5001, t0, 14340000), _hit(7001, 5001, t0 + 900, 14050000),      # Tempest Shot, Drill Dart
              _hit(7002, 5001, t0 + 500, 1800000),                                       # an NPC's Attack
              _hit(7003, 5001, t0 + 700, 1800000), _hit(7003, 5001, t0 + 800, 14340000),  # both: stays an enemy
              _hit(5001, 7004, t0 + 600, 15210000),
              HealEvent(actor_id=7004, skill_code=12750001, amount=300, timestamp_ms=t0 + 650, target_id=5001)]
    s.observe(engine, events, timestamp_ms=t0 + 1000)
    entities = {e["id"].split(":")[1]: e for seg in s.to_a2log("party")["segments"] for e in seg["entities"]}
    assert entities["7001"]["is_player"] is True and entities["7001"]["class"] == "Ranger"
    assert entities["7001"]["name"] == "Player #7001" and not entities["7001"].get("mob_code")
    for npc in ("7002", "7003", "7004"):        # an NPC's strike, mixed evidence, a heal only: enemies as before
        assert entities[npc]["kind"] == "enemy" and not entities[npc]["is_player"]


def test_coverage_counts_an_old_recordings_class_striker_as_a_player_not_a_missing_npc_type():
    damage = lambda source, skill: {"kind": "damage", "t": 1.0, "source": source, "target": "p:1", "skill_id": skill, "amount": 10}
    segment = {"map_id": 60, "instance_id": 0,
               "entities": [{"id": f"3:{n}", "kind": "enemy", "is_player": False} for n in (7001, 7002, 7003, 7005)],
               "events": [damage("3:7001", 14340000), damage("3:7002", 1800000), damage("3:7003", 1800000),
                          damage("3:7003", 14340000), {"kind": "heal", "t": 1.0, "source": "3:7005", "target": "p:1",
                                                       "skill_id": 12750001, "amount": 5}]}
    report = coverage(segment)
    assert report["unnamed_players"] == 1
    assert [r["entity"] for r in report["unidentified_entities"]] == ["3:7002", "3:7003", "3:7005"]
    assert report["npc_entities_without_type"] == 3
