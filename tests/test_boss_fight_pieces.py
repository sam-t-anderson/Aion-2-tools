"""A boss fight's stray pieces (0.2.355). In recent Krao Cave uploads each Ultimate Berk kill was followed
by an "Ultimate Berk" encounter of 8-18 s with no party damage: the dead boss, at zero health, still
striking the party (skill 1200015) after its death closed the run, past the run's end, which untimed
the run. And a boss's opening blow, struck a few milliseconds before the party's first hit, was an
encounter of its own when a zone load had already begun the boss room's segment: the boss split armed
by the previous kill still fired. 15 after-kill pieces and 4 opening blows in 75 recent public logs
(Ultimate Berk, Furious Feruk, Fortress Guardian Notun and others). Synthetic data only."""
from aion2calc.combat.rejoin import rejoin
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

RUTHILIS, TALISRA = 2350708, 2350709        # the catalog's boss and final boss of instance 600065
ME = 4062


def _engine(spawns):
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600065
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = ME
    engine.names, engine.known_players, engine.roster = {ME: "Me"}, {ME}, {"Me": {}}
    engine.spawn_info = {entity: {"mobCode": code} for entity, code in spawns.items()}
    return engine


def _hit(actor, target, t):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000 if actor == ME else 1200015,
                       damage=500, timestamp_ms=t)


def _die(s, engine, entity, t):
    engine.telemetry = [{"kind": "death", "entity": entity, "timestamp_ms": t}]
    s.observe(engine, [], timestamp_ms=t)
    engine.telemetry = []


def test_the_dead_final_boss_striking_on_opens_no_encounter():
    engine = _engine({51000: TALISRA})
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    for t in range(110_000, 230_001, 10_000):
        s.observe(engine, [_hit(ME, 51000, t)], timestamp_ms=t)
    _die(s, engine, 51000, 231_000)
    assert s.run_closed and s.runs[s.run]["end_reason"] == "configured_final_boss_death"
    for t in range(233_000, 250_001, 1_000):                    # its blows after its death
        s.observe(engine, [_hit(51000, ME, t)], timestamp_ms=t)
    segments = s.to_a2log("party")["segments"]
    assert len(segments) == 1 and segments[0]["boss"] and segments[0]["killed"]


def test_a_zone_load_into_the_boss_room_keeps_the_bosss_opening_blow_with_its_fight():
    engine = _engine({31000: RUTHILIS, 52000: TALISRA})
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    for t in range(110_000, 200_001, 10_000):
        s.observe(engine, [_hit(ME, 31000, t)], timestamp_ms=t)
    _die(s, engine, 31000, 201_000)
    engine.last_zone_reset_ms = 240_000                          # the boss room is a zone load
    s.observe(engine, [], timestamp_ms=240_100)
    s.observe(engine, [_hit(52000, ME, 250_000)], timestamp_ms=250_000)     # its opening blow
    for t in range(250_008, 330_009, 10_000):
        s.observe(engine, [_hit(ME, 52000, t)], timestamp_ms=t)
    labels = [seg["label"] for seg in s.to_a2log("party")["segments"]]
    assert len(labels) == 2, labels                              # Ruthilis, Talisra: no 8 ms piece between


def _segment(epoch, start, duration, hits, events, boss=None, dead=()):
    from datetime import datetime
    entities = [{"id": f"{epoch}:9", "name": "Boss", "kind": "enemy", "is_boss": True, "mob_code": TALISRA}] if boss else []
    events = list(events) + [{"kind": "death", "target": d, "t": duration} for d in dead]
    ms = int(datetime.fromisoformat(start).timestamp() * 1000)
    return {"id": f"{epoch}-{ms}-1", "run_id": "1", "start": start, "duration": duration, "hits": hits,
            "events": events, "entities": entities, "health": []}


def test_old_recordings_put_the_pieces_with_their_fight():
    boss = "7:9"
    blow = _segment(7, "2026-10-20T10:00:00.000+00:00", 0.008, [],
                    [{"kind": "damage", "source": boss, "target": "p:1", "t": 0.0, "amount": 900}])
    fight = _segment(7, "2026-10-20T10:00:00.008+00:00", 120.0,
                     [{"t": 1.0, "player": "p:1", "target": boss, "damage": 5000.0}], [], boss=True, dead=[boss])
    after = _segment(7, "2026-10-20T10:02:02.000+00:00", 17.0, [],
                     [{"kind": "damage", "source": boss, "target": "p:1", "t": 1.0, "amount": 900}])
    other = _segment(7, "2026-10-20T10:02:30.000+00:00", 10.0, [],
                     [{"kind": "damage", "source": "7:44", "target": "p:1", "t": 1.0, "amount": 50}])
    out = rejoin({"meta": {}, "segments": [blow, fight, after, other]})
    first, whole, kept, stranger = out["segments"]
    assert first["continued_in"] == 1 and first["fragment"] == "opening_blow"
    assert whole["start"] == blow["start"] and len(whole["events"]) == 2      # the blow joined the fight
    assert kept["continued_in"] == 1 and kept["fragment"] == "after_kill"
    assert "continued_in" not in stranger                     # struck by an enemy that did not die there
    assert out["meta"]["repairs"]["opening_blows"] == [[0, 1]] and out["meta"]["repairs"]["after_kills"] == [[1, 2]]
