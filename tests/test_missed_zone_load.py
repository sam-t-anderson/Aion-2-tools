"""A zone load the capture missed: the recorder keeps its name and the party keeps its damage.

Entering an instance moves the game to a new connection, and the zone load at its start names every player.
When the capture loses that start (three Krao Cave runs of 4-6 November, client 0.2.380 and 0.2.384), no zone
reset follows: the recorder's MP records move it to its new actor and the party's new actors have no names. Up to
0.2.384 the recorder then fought the rest of the zone as "Player #N" while its name stayed on the abandoned actor,
and under the party scope the unnamed members' hits were dropped as out of scope -- the recorder alone in every
boss fight of the log. Since 0.2.385 the name moves with the MP record, and an unnamed actor striking with a
player's class skills stands in for a party-list member of that class that no named actor accounts for.
"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

from test_combat_actions import BOSS, _observe
from test_local_identity_from_mp import STREAM, _mp, _self_record

OLD, ME = 3829, 9278                       # the recorder's actor before and after the missed zone load
CLERIC, RANGER, PET, SPAWNED = 7101, 7102, 7150, 7160
TEMPLAR, CLERIC_SKILL, RANGER_SKILL, NPC_SKILL = 12010000, 17010000, 14010000, 1800000
ROSTER = {"Recorder": {"dbid": 11, "serverId": 2102, "job": "Templar", "level": 45, "gearScore": 0},
          "Healer": {"dbid": 12, "serverId": 2102, "job": "Cleric", "level": 45, "gearScore": 0},
          "Archer": {"dbid": 13, "serverId": 2102, "job": "Ranger", "level": 45, "gearScore": 0}}


def _hit(actor, skill, t, damage=1000):
    return DamageEvent(actor_id=actor, target_id=BOSS, skill_code=skill, damage=damage, timestamp_ms=t)


def _instance(instance=600004):
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.map_id = engine.dungeon_id = instance
    engine.last_zone_reset_ms = 100_000
    engine.roster = {name: dict(info) for name, info in ROSTER.items()}
    engine.roster_complete, engine.roster_source = True, "packet"
    engine.spawn_info = {BOSS: {"mobCode": 2300615}}
    session = CombatSession()
    session.pvp = False
    session.retain_scope = "party"
    return engine, session


def _missed_load(engine, session):
    """The zone load named the recorder; the next connection's start, with its new actors' records, was lost."""
    engine.consume(_self_record(OLD, "Recorder"), 100_100, STREAM)
    engine.local_profile = {"serverId": 2102, "job": "Templar", "level": 45}
    _observe(session, engine, 100_200)
    engine.consume(_mp(ME), 101_000, STREAM)
    engine.consume(_mp(ME, 2700), 103_000, STREAM)
    _observe(session, engine, 103_100)


def _players(session):
    doc = session.to_a2log("party")
    hits = {}
    for segment in doc["segments"]:
        for hit in segment["hits"]:
            hits[hit["player"]] = hits.get(hit["player"], 0) + hit["damage"]
    return {p["id"]: p for p in doc["players"]}, hits


def test_the_recorder_keeps_its_name_and_the_party_its_damage():
    engine, session = _instance()
    _missed_load(engine, session)
    assert engine.local_player_id == ME and engine.names[ME] == "Recorder" and engine.local_name_carried == 1
    _observe(session, engine, 110_000, events=[_hit(ME, TEMPLAR, 110_000, 5000), _hit(CLERIC, CLERIC_SKILL, 110_100, 3000),
                                               _hit(RANGER, RANGER_SKILL, 110_200, 4000)])
    _observe(session, engine, 112_000, events=[_hit(ME, TEMPLAR, 112_000, 5000), _hit(CLERIC, CLERIC_SKILL, 112_100, 3000),
                                               _hit(RANGER, RANGER_SKILL, 112_200, 4000)])
    players, hits = _players(session)
    assert hits == {"p:2102:11": 10000, f"{session.epoch}:{CLERIC}": 6000, f"{session.epoch}:{RANGER}": 8000}
    assert players["p:2102:11"]["name"] == "Recorder" and players["p:2102:11"]["server"] == "2102"
    assert players[f"{session.epoch}:{CLERIC}"]["name"] == f"Player #{CLERIC}"
    assert players[f"{session.epoch}:{CLERIC}"]["class"] == "cleric" and players[f"{session.epoch}:{RANGER}"]["class"] == "ranger"
    assert not any(pid.endswith(f":{ME}") for pid in players)          # no unnamed recorder beside its name
    assert session.out_of_scope == 0


def test_a_member_fighting_under_a_named_actor_is_not_counted_twice():
    engine, session = _instance()
    engine.consume(_self_record(ME, "Recorder"), 100_100, STREAM)
    engine.names.update({CLERIC + 100: "Healer", RANGER + 100: "Archer"})   # every member named
    _observe(session, engine, 100_200)
    _observe(session, engine, 110_000, events=[_hit(ME, TEMPLAR, 110_000), _hit(RANGER + 100, RANGER_SKILL, 110_050),
                                               _hit(RANGER, RANGER_SKILL, 110_100),                # a stray unnamed id
                                               _hit(PET, CLERIC_SKILL, 110_200),                   # a pet with no owner link
                                               _hit(CLERIC + 100, CLERIC_SKILL, 110_300)])
    _observe(session, engine, 112_000, events=[_hit(RANGER + 100, RANGER_SKILL, 112_000), _hit(CLERIC + 100, CLERIC_SKILL, 112_100)])
    players, hits = _players(session)
    assert set(hits) == {"p:2102:11", "p:2102:12", "p:2102:13"}
    assert not any(pid.endswith((f":{RANGER}", f":{PET}")) for pid in players)


def test_a_name_left_on_the_id_from_before_the_missed_load_accounts_for_nothing():
    # the zone load before the instance named every member under the ids they had there; those ids fight no more
    engine, session = _instance()
    engine.consume(_self_record(OLD, "Recorder"), 100_100, STREAM)
    engine.names.update({CLERIC + 100: "Healer", RANGER + 100: "Archer"})
    engine.local_profile = {"serverId": 2102, "job": "Templar", "level": 45}
    _observe(session, engine, 100_200, events=[_hit(RANGER + 100, RANGER_SKILL, 100_200)])   # some trash on the way in
    engine.consume(_mp(ME), 130_000, STREAM)
    engine.consume(_mp(ME, 2700), 132_000, STREAM)
    _observe(session, engine, 140_000, events=[_hit(ME, TEMPLAR, 140_000), _hit(CLERIC, CLERIC_SKILL, 140_100),
                                               _hit(RANGER, RANGER_SKILL, 140_200)])
    players, hits = _players(session)
    assert {f"{session.epoch}:{CLERIC}", f"{session.epoch}:{RANGER}", "p:2102:11"} <= set(hits)


def test_a_healer_keeps_its_class_when_its_hits_fall_in_another_fight():
    from aion2calc.meter.a2parser.models import HealEvent
    engine, session = _instance()
    _missed_load(engine, session)
    _observe(session, engine, 105_000, events=[_hit(CLERIC, CLERIC_SKILL, 105_000, 200)])        # its one strike, on trash
    _observe(session, engine, 900_000, events=[_hit(ME, TEMPLAR, 900_000)])                   # a later fight
    _observe(session, engine, 900_500, events=[HealEvent(CLERIC, 17090000, 900, 900_500, False, ME)])
    last = session.to_a2log("party", segment_id=None)                   # the boss fight alone: the healer only heals there
    players = {p["id"]: p for p in last["players"]}
    assert len(last["segments"]) == 1 and players[f"{session.epoch}:{CLERIC}"]["class"] == "cleric"


def test_npcs_spawned_actors_and_summons_are_never_members():
    engine, session = _instance()
    _missed_load(engine, session)
    engine.spawn_info[SPAWNED] = {"mobCode": 2100001}
    engine.summon_owners[PET] = ME
    engine.summons.add(PET)
    _observe(session, engine, 110_000, events=[_hit(CLERIC, NPC_SKILL, 110_000), _hit(CLERIC, CLERIC_SKILL, 110_100),
                                               _hit(SPAWNED, CLERIC_SKILL, 110_200), _hit(PET, TEMPLAR, 110_300)])
    players, hits = _players(session)
    assert f"{session.epoch}:{CLERIC}" not in hits and f"{session.epoch}:{SPAWNED}" not in hits   # struck with an NPC skill
    assert hits.get("p:2102:11") == 1000                               # the recorder's linked pet lands on the recorder


def test_an_unnamed_recorder_accounts_for_its_own_entry():
    # a meter started inside the zone: the recorder is known from its MP records only, and has no name
    engine, session = _instance()
    engine.consume(_mp(ME), 100_100, STREAM)
    _observe(session, engine, 100_200)
    _observe(session, engine, 110_000, events=[_hit(ME, TEMPLAR, 110_000), _hit(PET, TEMPLAR, 110_100),
                                               _hit(CLERIC, CLERIC_SKILL, 110_200)])
    players, hits = _players(session)
    assert set(hits) == {f"{session.epoch}:{ME}", f"{session.epoch}:{CLERIC}"}   # the Templar slot is the recorder's


def test_the_open_world_is_unchanged():
    engine, session = _instance(instance=0)
    engine.map_id = 1110
    _missed_load(engine, session)
    _observe(session, engine, 110_000, events=[_hit(ME, TEMPLAR, 110_000), _hit(CLERIC, CLERIC_SKILL, 110_100)])
    players, hits = _players(session)
    assert set(hits) == {"p:2102:11"}                                  # strangers nearby are no party
