"""The overlay's arena mode (0.2.395): the live view names the PvP match the shown fight is (the Arena of Solitude,
the Arena of Cooperation, a battlefield) and carries its fighters: the game's arena roster (name, class, server,
faction, level, arena rating) with each fighter's DPS, damage taken and HPS on the fight's clock, their HP and
deaths, and the rounds won and lost. The opponent's HP and own heals are kept in an arena match whatever the capture
scope. An opponent's combat power, which the game sends for your own party only, is looked up by the app on the
official character service in the background."""
import time

from aion2calc.app import pvp_profiles
from aion2calc.meter.a2parser.models import HealEvent
from aion2calc.meter.session import CombatSession
from test_arena_matches import (ARENA, FOE, FOE_ID, LOSS, ME, MY_ID, PET, SHARP_STRIKE, SHIELD_STRIKE, STREAM, _entered, _hit, _map, _roster,
                                _other, _result, _round, _self, _zone_load)

PET_OF_FOE = PET


def _fight(engine, s, t=110_000, seconds=10, mine=1200, theirs=900):
    for i in range(seconds):
        s.observe(engine, [_hit(ME, FOE, t + i * 1000, SHIELD_STRIKE, mine), _hit(FOE, ME, t + i * 1000 + 500, SHARP_STRIKE, theirs)],
                  timestamp_ms=t + i * 1000 + 600)
    return t + seconds * 1000


def _live(retain=None):
    engine, s = _entered(), CombatSession()
    s.begin_capture()
    if retain:
        s.retain_scope = retain
    s.observe(engine, [], timestamp_ms=101_000)
    return engine, s


def test_a_live_arena_match_gives_the_overlay_both_fighters_and_the_score():
    engine, s = _live()
    t = _fight(engine, s)
    s.observe(engine, [HealEvent(actor_id=FOE, skill_code=SHARP_STRIKE, amount=5_000, timestamp_ms=t - 300, target_id=FOE),
                       # a heal by the opponent on you is not theirs (before 0.2.398, your shield absorbing their hit)
                       HealEvent(actor_id=FOE, skill_code=SHIELD_STRIKE, amount=7_000, timestamp_ms=t - 200, target_id=ME)],
              timestamp_ms=t - 100)
    engine.telemetry = [{"kind": "hp", "entity": FOE, "current": 18_000, "max": 30_000, "timestamp_ms": t - 50}]
    s.observe(engine, [], timestamp_ms=t - 40)
    engine.consume(_round(MY_ID, FOE_ID), t + 100, STREAM)                  # you took the first round
    s.observe(engine, [], timestamp_ms=t + 200)
    snap = s.snapshot("party")
    arena = snap["arena"]
    assert (arena["kind"], arena["label"], arena["zone"], arena["map"]) == ("solitude", "Arena of Solitude", "Impetusium Arena", ARENA)
    assert (arena["round"], arena["won"], arena["lost"], arena["result"]) == (2, 1, 0, None)
    foe, me = arena["fighters"]
    assert (arena["opponent"], arena["you"], arena["target"]) == (foe["key"], me["key"], foe["key"]) == ("a:12981", "a:4423", "a:12981")
    assert {k: foe[k] for k in ("name", "class", "server", "faction", "level", "rating", "side", "self")} == {
        "name": "Testfoe", "class": "gladiator", "server": "1107", "faction": "elyos", "level": 45, "rating": 1530,
        "side": "enemy", "self": False}
    assert (foe["dps"], foe["dtps"], foe["hps"], foe["hp_pct"], foe["share_of_your_damage_taken"]) == (900, 1200, 500, 0.6, 1.0)
    assert foe["combat_power"] is None and foe["cp_source"] is None        # the game gives an opponent's none
    row = snap["players"][0]
    assert me["self"] and me["side"] == "ally" and (me["dps"], me["dtps"], me["hps"]) == (row["dps"], row["dtps"], row["hps"])


def test_the_opponents_hp_and_own_heals_are_kept_under_the_party_scope():
    engine, s = _live(retain="party")
    t = _fight(engine, s)
    s.observe(engine, [HealEvent(actor_id=FOE, skill_code=SHARP_STRIKE, amount=5_000, timestamp_ms=t, target_id=FOE)], timestamp_ms=t + 10)
    engine.telemetry = [{"kind": "hp", "entity": FOE, "current": 6_000, "max": 30_000, "timestamp_ms": t + 20}]
    s.observe(engine, [], timestamp_ms=t + 30)
    foe = s.snapshot("party")["arena"]["fighters"][0]
    assert foe["hps"] == 500 and foe["hp_pct"] == 0.2
    # The rule a party's capture keeps them by (a party list filters the rest): a match fighter's heal on themselves,
    # their summon's, or on nobody named; not a heal another fighter received, nor anyone's outside a match.
    identity = {"owners": {PET_OF_FOE: FOE}}
    heal = lambda actor, target: HealEvent(actor_id=actor, skill_code=SHARP_STRIKE, amount=1, timestamp_ms=t, target_id=target)
    keep = lambda event, actors={FOE}: CombatSession._match_heal(event, identity, actors)
    assert keep(heal(FOE, FOE)) and keep(heal(FOE, None)) and keep(heal(PET_OF_FOE, FOE))
    assert not keep(heal(FOE, ME)) and not keep(heal(777, 777)) and not keep(heal(FOE, FOE), set())
    assert not keep(_hit(FOE, ME, t, SHARP_STRIKE))


def test_a_finished_match_gives_its_result_and_new_rating():
    engine, s = _live()
    t = _fight(engine, s)
    engine.consume(_round(FOE_ID, MY_ID) + _result(LOSS, 1505, 0, 1), t + 100, STREAM)
    s.observe(engine, [], timestamp_ms=t + 200)
    arena = s.snapshot("party")["arena"]
    assert (arena["result"], arena["won"], arena["lost"], arena["rating_after"], arena["round"]) == ("loss", 0, 1, 1505, 1)


def test_pvp_in_the_open_world_is_no_match_and_an_unknown_instanced_map_is_a_battlefield():
    for map_id, kind in ((20, None), (999_001, "battlefield")):
        engine = _entered()
        engine.consume(_round(MY_ID, FOE_ID) + _result(LOSS, 1505, 0, 1), 105_000, STREAM)   # the arena match is over
        engine.consume(_map(map_id), 106_000, STREAM)
        engine.consume(_zone_load(), 106_500, STREAM)
        engine.consume(_self(ME, "Testme") + _other(FOE, "Testfoe"), 106_600, STREAM)
        s = CombatSession()
        s.begin_capture()
        s.observe(engine, [], timestamp_ms=107_000)
        _fight(engine, s, t=110_000)
        arena = s.snapshot("party")["arena"]
        if kind is None:
            assert arena is None
            continue
        assert arena["kind"] == kind and arena["label"] == "Battlefield" and arena["zone"] is None and "match" not in arena
        sides = {f["name"]: f["side"] for f in arena["fighters"]}
        assert sides == {"Testme": "ally", "Testfoe": "enemy"} and arena["target"] == "a:12981"


def test_an_opponents_combat_power_is_looked_up_once_in_the_background(monkeypatch):
    asked = []

    def fetch(name, server, cls, region):
        asked.append((name, server, cls, region))
        return {"combat_power": 48_210, "level": 45} if name == "Testfoe" else None

    pvp_profiles.clear()
    monkeypatch.setattr(pvp_profiles, "fetch", fetch)
    assert pvp_profiles.known("Testfoe", "1107", "gladiator", "nae") is None    # asked now, answered on the worker
    for _ in range(100):
        found = pvp_profiles.known("Testfoe", "1107", "gladiator", "nae")
        if found:
            break
        time.sleep(0.01)
    assert found["combat_power"] == 48_210 and found["status"] == "ready"
    assert pvp_profiles.known("Testfoe", "1107") is found and asked == [("Testfoe", 1107, "gladiator", "nae")]
    assert pvp_profiles.known("Player #4423", "1107") is None and pvp_profiles.known("Testfoe", "") is None   # never asked
    pvp_profiles.known("Nobody", "1107")
    for _ in range(100):
        if pvp_profiles.known("Nobody", "1107"):
            break
        time.sleep(0.01)
    assert pvp_profiles.known("Nobody", "1107")["status"] == "unavailable" and len(asked) == 2   # not asked again at once
    pvp_profiles.clear()


def test_a_name_two_characters_share_on_a_server_gets_no_combat_power(monkeypatch):
    from aion2calc.sources import official
    twins = [{"name": "Testfoe", "server_id": 1107, "class": "gladiator", "character_id": "a"},
             {"name": "Testfoe", "server_id": 1107, "class": "gladiator", "character_id": "b"}]
    monkeypatch.setattr(official, "search", lambda name, region="nae", server_id=None, size=40: twins if region == "nae" else [])
    monkeypatch.setattr(official, "profile", lambda *a: {"characterName": "Testfoe", "combatPower": 1})
    assert pvp_profiles._official("Testfoe", 1107, "gladiator", None) is None
    monkeypatch.setattr(official, "search", lambda name, region="nae", server_id=None, size=40: twins[:1] if region == "eu" else [])
    monkeypatch.setattr(official, "profile", lambda cid, server, region: {"characterName": "Testfoe", "combatPower": 48_210, "characterLevel": 45})
    assert pvp_profiles._official("Testfoe", 1107, "gladiator", None) == {"combat_power": 48_210, "level": 45, "region": "eu"}


def test_the_runner_fills_in_server_names_and_an_opponents_combat_power(monkeypatch):
    from aion2calc.app.meter_runner import Runner as MeterRunner

    class Metadata:
        def snapshot(self, server=None):
            return {"server_name": {"1107": "Zikel", "2102": "Siel"}.get(str(server)), "region": "nae"}

    runner = MeterRunner.__new__(MeterRunner)
    runner.capture_metadata = Metadata()
    monkeypatch.setattr(pvp_profiles, "known", lambda name, server, cls=None, region=None:
                        {"combat_power": 48_210, "level": 45, "status": "ready"} if name == "Testfoe" else None)
    arena = {"fighters": [{"name": "Testfoe", "server": "1107", "class": "gladiator", "self": False, "combat_power": None},
                          {"name": "Testme", "server": "2102", "class": "templar", "self": True, "combat_power": 46_870, "cp_source": "party"}]}
    runner._arena_profiles(arena, {"overlay_arena_mode": True})
    foe, me = arena["fighters"]
    assert (foe["server_name"], foe["combat_power"], foe["cp_source"]) == ("Zikel", 48_210, "official")
    assert (me["server_name"], me["combat_power"], me["cp_source"]) == ("Siel", 46_870, "party")
    arena["fighters"][0].update(combat_power=None, cp_source=None)
    runner._arena_profiles(arena, {"overlay_arena_mode": False})          # arena mode off: nothing is looked up
    assert arena["fighters"][0]["combat_power"] is None


def test_a_roster_before_the_arenas_map_record_keeps_the_whole_match():
    """The 9 November recording: queued in Altgard, the match's roster came while the meter still held Altgard's map,
    the first round was fought before the arena's map record came, and the record that then named map 60 was taken
    for leaving the match: the rest of it lost its fighters, rounds and result, and its first round was typed
    open-world PvP in Altgard. Now the match moves to the arena's map and every fight in it is the match's."""
    from test_arena_matches import TOWN, WIN
    from aion2calc.meter.a2parser.engine import MeterEngine
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_map(TOWN), 40_000, STREAM)
    engine.consume(_zone_load(), 41_000, STREAM)
    engine.consume(_self(ME, "Testme") + _roster(), 100_000, STREAM)               # the roster, still in town
    engine.consume(_zone_load(), 100_500, STREAM)                                  # the arena's load, no map record
    engine.consume(_other(FOE, "Testfoe"), 101_000, STREAM)
    assert engine.arena["map"] == TOWN and engine.arena_in_progress()
    s = CombatSession()
    s.begin_capture()
    s.observe(engine, [], timestamp_ms=101_500)
    t = _fight(engine, s, t=110_000)                                               # round one
    engine.consume(_round(FOE_ID, MY_ID), t + 100, STREAM)
    s.observe(engine, [], timestamp_ms=t + 200)
    engine.consume(_map(ARENA), t + 5_000, STREAM)                                 # the arena's map, named at last
    engine.consume(_zone_load(), t + 5_600, STREAM)
    s.observe(engine, [], timestamp_ms=t + 5_700)
    assert engine.arena["map"] == ARENA and engine.arena.get("left_ms") is None and engine.arena_in_progress()
    for _ in range(2):                                                              # rounds two and three, won
        t = _fight(engine, s, t=t + 8_000)
        engine.consume(_round(MY_ID, FOE_ID), t + 100, STREAM)
        s.observe(engine, [], timestamp_ms=t + 200)
    engine.consume(_result(WIN, 1560, 2, 1), t + 300, STREAM)
    s.observe(engine, [], timestamp_ms=t + 400)
    assert [r["winner"] for r in engine.arena["rounds"]] == [FOE_ID, MY_ID, MY_ID] and engine.arena["result"]["result"] == "win"
    doc = s.to_a2log("party")
    fights = [seg for seg in doc["segments"] if seg["events"]]
    assert fights and all(seg["encounter_type"] == "pvp_arena" and seg["zone"] == "Impetusium Arena" and seg.get("arena") for seg in fights)
    rounds = [r["round"] for seg in fights for r in seg["arena"]["rounds"]]
    assert sorted(rounds) == [1, 2, 3] and fights[-1]["arena"]["result"] == "win"
    assert s.snapshot("party")["arena"]["result"] == "win"
