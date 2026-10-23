"""The Abyss (map 20) is open world, and a hit taken from the other kind of foe is no new encounter.

Seen in an 18 October recording of the Abyss field bosses (Watcher Kaira, killed; Argo, the Spirit
King). Map 20 is missing from the bundled Map table's overworld maps, so every fight there was typed
unverified PvE or other PvP: the kill never reached the kill feed and no Abyss timer could run.
And there, enemy players and NPCs struck the recording player in turn as they died: each hit of the
other kind started a segment, ten of them in a third of a second.
"""
from aion2calc.combat import boss_report, sessions
from aion2calc.meter.a2parser.engine import OBSERVED_OPEN_WORLD_MAPS, OPEN_WORLD_MAPS
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.context import classify
from aion2calc.meter.session import CombatSession, Record

ME, RIVAL, MOB, BOSS = 101, 640, 7777, 9001
KAIRA = 2600089
NUKE, CLAW = 15210000, 1800000


def test_the_abyss_map_is_open_world_with_its_evidence():
    assert 20 in OPEN_WORLD_MAPS and "Watcher Kaira" in OBSERVED_OPEN_WORLD_MAPS[20]
    pve, pvp = classify(20, 0, False, []), classify(20, 0, True, [])
    assert pve["encounter_type"] == "pve_open_world" and pve["classification"]["status"] == "map_match"
    assert pvp["encounter_type"] == "pvp_open_world"


def test_an_abyss_field_boss_kill_reaches_the_kill_feed_and_groups_as_a_field_boss(monkeypatch):
    monkeypatch.setattr(boss_report, "reporter_key", lambda: "k" * 32)
    seg = {"id": "s1", "killed": True, "encounter_type": classify(20, 0, False, [])["encounter_type"],
           "boss": "Argo, the Spirit King", "map_id": 20, "instance_id": 0, "start": "2026-10-18T23:05:02+00:00",
           "duration": 124.7, "entities": [{"id": "e1", "name": "Argo, the Spirit King", "is_boss": True,
                                             "mob_code": "2600068"}],
           "events": [{"kind": "death", "t": 124.7, "target": "e1"}]}
    doc = {"format": "a2log", "version": 1, "segments": [seg],
           "players": [{"id": "p:Siel:1", "name": "A", "server": "Siel"}]}
    reports = boss_report.defeats_from_doc(doc)
    assert [r["npc_id"] for r in reports] == [2600068] and reports[0]["map_id"] == 20
    # The reference spells it "Argo the Spirit King": still a field boss, not a world boss.
    assert sessions._category(seg, {})["category"] == "field_boss"


def _session():
    s = CombatSession()
    s.pvp = False
    s.gap_seconds = 120
    s.identities[0] = {"names": {ME: "Me", RIVAL: "Rival"}, "spawns": {MOB: {"mobCode": 2920150}, BOSS: {"mobCode": KAIRA}},
                       "jobs": {}, "local_id": ME, "owners": {}, "roster": {}, "observed_players": {ME, RIVAL},
                       "player_ids": {ME, RIVAL}}      # Rival: a player of the other faction
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1
    return s


def _rec(event, seq):
    return Record(0, event, frozenset(), ME, 0, 1, seq)


def _dmg(actor, target, t, skill=NUKE):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=500, timestamp_ms=t)


def test_hits_taken_from_players_and_mobs_in_turn_stay_one_encounter():
    s = _session()
    s.records = [_rec(_dmg(MOB, ME, 1000, CLAW), 1), _rec(_dmg(RIVAL, ME, 1050), 2),
                 _rec(_dmg(MOB, ME, 1100, CLAW), 3), _rec(_dmg(RIVAL, ME, 1150), 4),
                 _rec(_dmg(ME, BOSS, 1300), 5), _rec(_dmg(RIVAL, ME, 1400), 6), _rec(_dmg(ME, BOSS, 2000), 7)]
    groups = s.groups("self")
    assert len(groups) == 1 and groups[0]["pvp"] is False and len(groups[0]["records"]) == 7


def test_the_hits_taken_before_your_first_belong_to_your_fight():
    s = _session()
    s.records = [_rec(_dmg(RIVAL, ME, 1000), 1), _rec(_dmg(ME, MOB, 1200), 2)]
    groups = s.groups("self")
    assert len(groups) == 1 and groups[0]["pvp"] is False and groups[0]["start"] == 1000


def test_turning_on_a_player_yourself_still_starts_a_pvp_encounter():
    s = _session()
    s.records = [_rec(_dmg(ME, MOB, 1000), 1),
                 _rec(_dmg(ME, RIVAL, 2000), 2),          # a second after your mob hit: still that fight
                 _rec(_dmg(ME, RIVAL, 7000), 3),          # on the player alone past the window: PvP
                 _rec(_dmg(MOB, ME, 7500, CLAW), 4),      # a mob's hit taken mid player fight joins it
                 _rec(_dmg(ME, RIVAL, 8000), 5),
                 _rec(_dmg(ME, MOB, 14000), 6)]           # back on the mobs, past the window: PvE again
    assert [(g["pvp"], len(g["records"])) for g in s.groups("self")] == [(False, 2), (True, 3), (False, 1)]


def test_your_area_skill_striking_players_and_mobs_at_once_is_one_fight():
    # 21 October, Watcher Kaira's crowd: each cast struck the other faction's players and the NPCs about
    # within the same fraction of a second, and every hit of the other kind cut a segment, 68 in a minute.
    s = _session()
    records, seq = [], 0
    for t in range(1000, 21000, 400):
        for target, offset in ((RIVAL, 0), (MOB, 150)):
            seq += 1
            records.append(_rec(_dmg(ME, target, t + offset), seq))
    s.records = list(records)
    groups = s.groups("self")
    assert [(g["pvp"], len(g["records"])) for g in groups] == [(True, len(records))]
    # Striking the boss starts its fight at once, whatever you struck a moment before, and the players you
    # keep hitting while it lives stay inside that fight.
    s.records = records + [_rec(_dmg(ME, BOSS, 21100), seq + 1), _rec(_dmg(ME, RIVAL, 21300), seq + 2),
                           _rec(_dmg(ME, BOSS, 22000), seq + 3)]
    assert [(g["pvp"], len(g["records"])) for g in s.groups("self")] == [(True, len(records)), (False, 3)]
