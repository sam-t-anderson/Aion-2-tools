"""A saved log must not record the Shining Mau Totem (a miniboss) as a boss:
its entity carries is_boss=False and it never becomes the segment's headline
boss. This keeps it out of the logs page's boss list and boss progression at the
source; the viewer also suppresses it for older logs (combat-review.js)."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _doc_for_target(mob_code):
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me"}
    engine.roster = {"Me": {}}
    engine.spawn_info = {9001: {"mobCode": mob_code}}
    s.observe(engine, [DamageEvent(actor_id=5001, target_id=9001, skill_code=15210000, damage=500, timestamp_ms=1000),
                       DamageEvent(actor_id=5001, target_id=9001, skill_code=15210000, damage=500, timestamp_ms=2000)],
              timestamp_ms=2000)
    return s.to_a2log(scope="party")


def _entities(doc):
    return [e for seg in doc["segments"] for e in seg.get("entities", [])]


def test_shining_mau_totem_is_not_recorded_as_a_boss():
    doc = _doc_for_target(2300907)
    totem = next(e for e in _entities(doc) if str(e.get("mob_code")) == "2300907")
    assert totem["is_boss"] is False
    # A totem-only fight has no headline boss (it is a miniboss, not the boss).
    assert all(seg.get("boss") != "Shining Mau Totem" for seg in doc["segments"])
