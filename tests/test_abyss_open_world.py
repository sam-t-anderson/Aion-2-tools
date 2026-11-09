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
    # The reference names it as the patch notes do, "Argo, the Spirit King": still a field boss, not a world boss.
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


def _on_map(map_id):
    s = _session()
    s.runs[1]["map_id"] = map_id
    return s


def test_a_mixed_open_world_fight_is_pvp_unless_it_holds_a_field_or_world_boss():
    """9 November, a player's rule for the Abyss: a fight with players in it is PvP, mobs or not, unless it includes a
    field or world boss; mobs alone stay PvE. A party's 380-second Abyss fight of 4 November, where the other
    faction's players dealt 98% of the damage it took while it struck mobs and players in turn, was typed PvE."""
    def kinds(map_id, *events):
        s = _on_map(map_id)
        s.records = [_rec(event, seq) for seq, event in enumerate(events, 1)]
        return [(g["pvp"], len(g["records"])) for g in s.groups("self")]
    mixed = (_dmg(ME, MOB, 1000), _dmg(RIVAL, ME, 1500), _dmg(ME, MOB, 2000))
    assert kinds(20, *mixed) == [(True, 3)]                                                   # a player's hit taken
    assert kinds(20, _dmg(ME, MOB, 1000), _dmg(ME, RIVAL, 1500), _dmg(ME, MOB, 2000)) == [(True, 3)]   # or dealt
    assert kinds(20, _dmg(ME, MOB, 1000), _dmg(MOB, ME, 1500, CLAW), _dmg(ME, MOB, 2000)) == [(False, 3)]   # mobs alone
    assert kinds(20, _dmg(MOB, ME, 1000, CLAW), _dmg(RIVAL, ME, 1050), _dmg(ME, BOSS, 1300), _dmg(RIVAL, ME, 1400),
                 _dmg(ME, BOSS, 2000)) == [(False, 5)]                                         # the field boss's fight
    assert kinds(23, *mixed) == [(True, 3)]                                                   # Upper Reshanta too
    assert kinds(None, *mixed) == [(False, 3)]                # off the open world your own first hit still decides


def test_a_mixed_fight_saved_from_the_abyss_lists_only_its_players_as_enemies():
    from aion2calc.meter.a2parser.engine import MeterEngine
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id, engine.last_zone_reset_ms, engine.local_player_id = 20, None, ME
    engine.names, engine.roster = {ME: "Me", RIVAL: "Rival"}, {"Me": {}}
    engine.spawn_info = {MOB: {"mobCode": 2920150}}
    t0 = 1_000_000
    s.observe(engine, [_dmg(ME, MOB, t0), _dmg(RIVAL, ME, t0 + 300, 14340000), _dmg(RIVAL, ME, t0 + 900, 14050000),
                       _dmg(ME, RIVAL, t0 + 500), _dmg(MOB, ME, t0 + 600, CLAW), _dmg(ME, MOB, t0 + 1500)],
              timestamp_ms=t0 + 2000)
    [segment] = [seg for seg in s.to_a2log("party")["segments"] if seg["hits"]]
    assert segment["encounter_type"] == "pvp_open_world" and segment["zone"] == "Abyss"
    kinds = {e["id"].split(":")[1]: (e["kind"], e["is_player"]) for e in segment["entities"]}
    assert kinds[str(RIVAL)] == ("enemy", True) and kinds[str(MOB)] == ("enemy", False)


def test_upper_reshanta_is_map_23_and_stored_logs_are_retyped():
    assert 23 in OBSERVED_OPEN_WORLD_MAPS and 23 in OPEN_WORLD_MAPS
    pvp, pve = classify(23, 0, True, []), classify(23, 0, False, [])
    assert (pvp["encounter_type"], pvp["zone"]) == ("pvp_open_world", "Upper Reshanta") and pve["encounter_type"] == "pve_open_world"
    from aion2calc.meter.context import enrich
    doc = {"meta": {}, "players": [{"id": "p", "name": "A"}], "segments": [
        {"map_id": 23, "instance_id": 0, "encounter_type": "pvp_other", "hits": [], "events": [], "entities": []},
        {"map_id": 23, "instance_id": 0, "encounter_type": "pve_unverified", "hits": [], "events": [], "entities": []}]}
    first, second = enrich(doc)["segments"]
    assert (first["encounter_type"], first["zone"]) == ("pvp_open_world", "Upper Reshanta") and second["encounter_type"] == "pve_open_world"
