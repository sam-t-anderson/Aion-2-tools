"""Arena matches from the game's own records (0.2.361). The 31 October recording of six matches (maps 60 and 61)
showed the arena sending its roster as a match opens (``19 e3``), each round's winner and loser as it ends
(``25 e3``) and the recording player's result (``28 e3``), and a zone load on the same arena map each time the
recording player came back after losing a round, which kept every actor id. The meter used to reset there: the
opponent's name went (the game sends it once) and a match lost 0-3 was three fights. Now a match is one fight
whose segment carries the match, and each round's loser has a death marker that names the winner."""
import copy

from aion2calc.combat import a2log
from aion2calc.meter.a2parser.engine import ARENA_MATCH_MS, MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import scan_arena
from aion2calc.meter.session import CombatSession

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
ME, FOE, PET = 4423, 12981, 18043
MY_SERVER, FOE_SERVER = 2102, 1107
MY_ID, FOE_ID = (MY_SERVER << 48) | 300_001, (FOE_SERVER << 48) | 200_002
MATCH, ARENA, TOWN = 16_945_373, 61, 1110
TEMPLAR, GLADIATOR = 12, 6                                   # the roster's class codes
SHIELD_STRIKE, SHARP_STRIKE = 12010000, 11020000             # a Templar's and a Gladiator's skills
WIN, LOSS = 3, 2


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _frame(opcode, body):
    inner = opcode + body
    return _varint(len(inner) + 4) + inner


def _fighter(slot, dbid, name, class_code, faction, rating, *, level=45, wins=1, losses=0):
    raw = name.encode()
    return (bytes([slot]) + rating.to_bytes(8, "little") + rating.to_bytes(4, "little") + b"\x01" + bytes(8)
            + dbid.to_bytes(8, "little") + bytes([len(raw)]) + raw + class_code.to_bytes(4, "little") + bytes([faction])
            + level.to_bytes(4, "little") + bytes(4) + (dbid >> 48).to_bytes(2, "little") + rating.to_bytes(8, "little")
            + b"\x01" + rating.to_bytes(8, "little") + bytes([wins, losses, 0]) + rating.to_bytes(4, "little") + b"\x00")


FIGHTERS = (_fighter(1, FOE_ID, "Testfoe", GLADIATOR, 1, 1530), _fighter(2, MY_ID, "Testme", TEMPLAR, 2, 1530))


def _roster(*fighters, match=MATCH):
    fighters = fighters or FIGHTERS
    return _frame(b"\x19\xe3", match.to_bytes(4, "little") + bytes(3) + (22).to_bytes(4, "little") + bytes(4)
                  + (8).to_bytes(4, "little") + bytes([len(fighters)]) + b"".join(fighters))


def _round(winner, loser):
    return _frame(b"\x25\xe3", winner.to_bytes(8, "little") + loser.to_bytes(8, "little"))


def _result(result, rating, won, lost, dbid=MY_ID):
    return _frame(b"\x28\xe3", b"\x02" + rating.to_bytes(4, "little") + bytes([result, 1]) + dbid.to_bytes(8, "little")
                  + bytes([won, lost]) + b"\x00\x03")


def _map(map_id):
    return _frame(b"\x21\x36", bytes(4) + map_id.to_bytes(4, "little") + bytes(4))


def _zone_load():
    return _frame(b"\x23\x36", _varint(0) + bytes(8))


def _self(entity, name, server=MY_SERVER, class_code=TEMPLAR, level=45):
    raw = name.encode()
    return _frame(b"\x33\x36", _varint(entity) + bytes(4) + b"\x01" + bytes([len(raw)]) + raw + server.to_bytes(2, "little")
                  + class_code.to_bytes(4, "little") + b"\x00" + level.to_bytes(4, "little") + bytes(8))


def _other(entity, name):
    raw = name.encode()
    return _frame(b"\x45\x36", _varint(entity) + bytes(4) + b"\x01" + bytes([len(raw)]) + raw + bytes(12))


def _hit(actor, target, t, skill, damage=1000):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=damage, timestamp_ms=t)


# ------------------------------------------------------------------ decoder
def test_the_arena_roster_rounds_and_result_are_read():
    roster = scan_arena(_roster())
    assert roster["kind"] == "roster" and roster["match"] == MATCH
    assert roster["fighters"] == [
        {"slot": 1, "dbid": FOE_ID, "serverId": FOE_SERVER, "name": "Testfoe", "job": "Gladiator", "faction": "elyos",
         "level": 45, "rating": 1530, "wins": 1, "losses": 0},
        {"slot": 2, "dbid": MY_ID, "serverId": MY_SERVER, "name": "Testme", "job": "Templar", "faction": "asmodian",
         "level": 45, "rating": 1530, "wins": 1, "losses": 0}]
    assert scan_arena(_round(MY_ID, FOE_ID)) == {"kind": "round", "winner": MY_ID, "loser": FOE_ID}
    assert scan_arena(_result(WIN, 1560, 3, 0)) == {"kind": "result", "result": "win", "rating": 1560, "won": 3, "lost": 0, "dbid": MY_ID}
    assert scan_arena(_result(LOSS, 1525, 0, 3))["result"] == "loss"
    assert scan_arena(_result(7, 1525, 0, 3))["result"] is None                # a result byte the recordings never showed


def test_odd_arena_records_are_not_read():
    assert scan_arena(_roster()[:-1]) is None                                  # a fighter cut short
    assert scan_arena(_roster() + b"\x00") is None                             # a byte past the last fighter
    assert scan_arena(_roster(_fighter(1, FOE_ID, "Testfoe", 99, 1, 1530))) is None      # no such class code
    assert scan_arena(_roster(_fighter(1, FOE_ID, "Testfoe", GLADIATOR, 3, 1530))) is None   # no such faction
    assert scan_arena(_roster(_fighter(1, FOE_ID, "Testfoe", GLADIATOR, 1, 1530), _fighter(2, FOE_ID, "Testfoe", GLADIATOR, 1, 1530))) is None
    assert scan_arena(_round(MY_ID, FOE_ID) + b"\x00") is None
    assert scan_arena(_round(MY_ID, MY_ID)) is None
    assert scan_arena(_round(MY_ID, 0)) is None                                # not a character id
    assert scan_arena(_result(WIN, 1560, 3, 0)[:-1]) is None
    assert scan_arena(_frame(b"\x26\xe3", bytes(26))) is None                  # the scoreboard is not read


# ------------------------------------------------------------------ engine
def _entered(at=100_000):
    """An engine whose recording player came from Altgard into the arena and saw the match open."""
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_map(TOWN), at - 60_000, STREAM)
    engine.consume(_zone_load(), at - 59_000, STREAM)
    engine.consume(_map(ARENA), at - 5_000, STREAM)
    engine.consume(_zone_load(), at, STREAM)
    engine.consume(_self(ME, "Testme") + _roster(), at + 100, STREAM)
    engine.consume(_other(FOE, "Testfoe"), at + 1_000, STREAM)
    return engine


def test_the_fighters_are_bound_to_their_actors_and_the_roster_names_the_opponents_class():
    engine = _entered()
    assert [(f["name"], f["actor"]) for f in engine.arena["fighters"]] == [("Testfoe", FOE), ("Testme", ME)]
    assert engine.jobs[FOE] == "Gladiator" and engine.arena["entered"] and engine.arena["map"] == ARENA


def test_a_lost_rounds_zone_load_keeps_the_match_in_one_zone():
    engine = _entered()
    entered = engine.last_zone_reset_ms
    engine.consume(_round(FOE_ID, MY_ID), 130_000, STREAM)
    engine.consume(_map(ARENA), 135_000, STREAM)                              # brought back for round two
    engine.consume(_zone_load(), 135_600, STREAM)
    assert engine.last_zone_reset_ms == entered
    assert engine.names[FOE] == "Testfoe" and engine.local_player_id == ME
    engine.consume(_round(FOE_ID, MY_ID), 160_000, STREAM)
    engine.consume(_map(ARENA), 166_000, STREAM)
    engine.consume(_zone_load(), 166_600, STREAM)
    engine.consume(_round(FOE_ID, MY_ID) + _result(LOSS, 1505, 0, 3), 190_000, STREAM)
    assert engine.last_zone_reset_ms == entered
    assert [r["winner"] for r in engine.arena["rounds"]] == [FOE_ID] * 3
    assert engine.arena["result"]["result"] == "loss" and engine.arena["result"]["rating"] == 1505
    engine.consume(_map(TOWN), 197_000, STREAM)                               # leaving: a zone load as ever
    engine.consume(_zone_load(), 200_000, STREAM)
    assert engine.last_zone_reset_ms == 200_000 and FOE not in engine.names


def test_the_arenas_own_zone_load_after_its_roster_still_resets():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_map(ARENA), 1_000, STREAM)
    engine.consume(_roster(), 2_000, STREAM)                                  # the roster before the arena's own load
    assert not engine.arena["entered"]
    engine.consume(_zone_load(), 3_000, STREAM)
    assert engine.last_zone_reset_ms == 3_000 and engine.arena["entered"]
    engine.consume(_map(ARENA), 40_000, STREAM)
    engine.consume(_zone_load(), 40_600, STREAM)
    assert engine.last_zone_reset_ms == 3_000


def test_a_match_left_without_its_result_or_past_its_length_holds_no_zone():
    engine = _entered()
    engine.consume(_map(TOWN), 150_000, STREAM)                               # left with no result (a lost record)
    assert engine.arena["left_ms"] == 150_000
    engine.consume(_map(ARENA), 160_000, STREAM)
    engine.consume(_zone_load(), 160_600, STREAM)
    assert engine.last_zone_reset_ms == 160_600
    engine = _entered()
    engine.consume(_map(ARENA), 100_000 + ARENA_MATCH_MS + 5_000, STREAM)
    engine.consume(_zone_load(), 100_000 + ARENA_MATCH_MS + 6_000, STREAM)
    assert engine.last_zone_reset_ms == 100_000 + ARENA_MATCH_MS + 6_000


def test_an_unnamed_actor_striking_with_the_opponents_class_is_the_opponents_summon():
    engine = _entered()
    engine._link_arena_pets([_hit(PET, ME, 120_000, SHARP_STRIKE), _hit(9999, ME, 120_000, 1800000)])
    assert engine.summon_owners == {PET: FOE}                                 # an NPC's skill names no fighter


def test_a_class_two_fighters_share_names_no_summons_owner():
    """Templar against Templar, the opponent's name never decoded: their own unnamed hits are not the recording
    player's summon."""
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_map(ARENA), 1_000, STREAM)
    engine.consume(_zone_load(), 2_000, STREAM)
    twins = (_fighter(1, FOE_ID, "Testfoe", TEMPLAR, 1, 1530), _fighter(2, MY_ID, "Testme", TEMPLAR, 2, 1530))
    engine.consume(_self(ME, "Testme") + _roster(*twins), 2_100, STREAM)
    assert [f["actor"] for f in engine.arena["fighters"]] == [None, ME]
    engine._link_arena_pets([_hit(FOE, ME, 30_000, SHIELD_STRIKE)])
    assert engine.summon_owners == {}


def test_a_new_matchs_roster_replaces_the_last_and_an_engine_restart_keeps_it():
    engine = _entered()
    engine.consume(_round(MY_ID, FOE_ID), 130_000, STREAM)
    later = MeterEngine()
    later.adopt_identity(engine)
    assert later.arena == engine.arena and later.arena is not engine.arena
    engine.consume(_roster(match=MATCH + 9), 400_000, STREAM)
    assert engine.arena["match"] == MATCH + 9 and engine.arena["rounds"] == []


# ------------------------------------------------------------------ the session and the log
def _match(won=(False, False, False), death_samples=True):
    """A recorded match: the opponent and the recording player trade hits; each round ends with its loser's death
    (the engine's death marker for the recording player when ``death_samples``) and the game's round record."""
    engine, s = _entered(), CombatSession()
    s.begin_capture()
    s.observe(engine, [], timestamp_ms=101_000)
    t = 110_000
    for number, mine in enumerate(won, 1):
        for i in range(10):
            s.observe(engine, [_hit(ME, FOE, t + i * 1000, SHIELD_STRIKE), _hit(FOE, ME, t + i * 1000 + 500, SHARP_STRIKE)],
                      timestamp_ms=t + i * 1000 + 600)
        t += 10_000
        loser = FOE if mine else ME
        engine.telemetry = [{"kind": "death", "entity": loser, "timestamp_ms": t}] if death_samples or mine else []
        s.observe(engine, [], timestamp_ms=t)
        engine.consume(_round(MY_ID if mine else FOE_ID, FOE_ID if mine else MY_ID), t + 100, STREAM)
        if number == len(won):
            wins = sum(won)
            engine.consume(_result(WIN if wins > len(won) / 2 else LOSS, 1530 + 30 * (wins * 2 - len(won)), wins, len(won) - wins), t + 100, STREAM)
        s.observe(engine, [], timestamp_ms=t + 100)
        engine.telemetry = [{"kind": "hp", "entity": loser, "current": 30_000, "max": 30_000, "timestamp_ms": t + 6_000}]
        s.observe(engine, [], timestamp_ms=t + 6_000)
        if not mine and number < len(won):                                    # the recording player brought back
            engine.consume(_map(ARENA), t + 5_500, STREAM)
            engine.consume(_zone_load(), t + 6_100, STREAM)
            s.observe(engine, [], timestamp_ms=t + 6_100)
        t += 8_000
    return engine, s


def test_a_lost_match_is_one_fight_with_its_rounds_result_and_kill_credit():
    engine, s = _match()
    doc = s.to_a2log("party")
    [fight] = [seg for seg in doc["segments"] if seg["encounter_type"] == "pvp_arena"]
    assert fight["zone"] == "Impetusium Arena"
    arena = fight["arena"]
    me, foe = next(p["id"] for p in doc["players"]), next(e["id"] for e in fight["entities"] if e.get("is_player"))
    assert arena["match"] == MATCH and (arena["result"], arena["rounds_won"], arena["rounds_lost"], arena["rating"]) == ("loss", 0, 3, 1440)
    assert arena["fighters"] == [
        {"name": "Testfoe", "class": "gladiator", "server": "1107", "faction": "elyos", "level": 45, "rating": 1530, "ref": foe},
        {"name": "Testme", "class": "templar", "server": "2102", "faction": "asmodian", "level": 45, "rating": 1530, "ref": me, "self": True}]
    assert [(r["round"], r["winner"], r["loser"]) for r in arena["rounds"]] == [(1, 0, 1), (2, 0, 1), (3, 0, 1)]
    deaths = [e for e in fight["events"] if e["kind"] == "death"]
    assert [(d["target"], d.get("source")) for d in deaths] == [(me, foe)] * 3
    assert all(abs(d["t"] - r["t"]) <= 0.2 for d, r in zip(deaths, arena["rounds"]))     # the engine's own markers
    opponent = next(e for e in fight["entities"] if e["id"] == foe)
    assert opponent["name"] == "Testfoe" and opponent["server"] == "1107"


def test_a_round_whose_loser_has_no_death_marker_gets_one_at_its_end():
    engine, s = _match(won=(True, False, False), death_samples=False)
    [fight] = [seg for seg in s.to_a2log("party")["segments"] if seg["encounter_type"] == "pvp_arena"]
    rounds, deaths = fight["arena"]["rounds"], [e for e in fight["events"] if e["kind"] == "death"]
    assert len(deaths) == 3 and all(d.get("source") for d in deaths)
    # made at the rounds' ends, the last one no later than the fight's last record (the killing blow)
    assert [d["t"] for d in deaths[1:]] == [min(r["t"], fight["duration"]) for r in rounds[1:]]
    assert deaths[2]["t"] < rounds[2]["t"]
    assert fight["arena"]["result"] == "loss" and fight["arena"]["rounds_won"] == 1


def test_a_fight_outside_any_match_has_no_arena_block_and_an_open_match_goes_on_in_the_next_part():
    engine, s = _match()
    for i in range(12):                                                        # a fight long after the match ended
        s.observe(engine, [_hit(ME, 7777, 900_000 + i * 1000, SHIELD_STRIKE)], timestamp_ms=900_000 + i * 1000)
    *match, later = s.to_a2log("party")["segments"]
    assert [seg.get("arena", {}).get("match") for seg in match] == [MATCH] and "arena" not in later
    engine = _entered()
    s = CombatSession()
    s.observe(engine, [], timestamp_ms=101_000)
    assert MATCH in s.continuation().arena_matches                             # no result yet
    engine, s = _match()
    assert s.continuation().arena_matches == {}


def test_the_validator_keeps_a_clean_arena_block_and_drops_what_does_not_fit():
    engine, s = _match()
    doc = s.to_a2log("party")
    fight = next(seg for seg in doc["segments"] if seg.get("arena"))
    again = a2log.validate(copy.deepcopy(doc))
    assert next(seg for seg in again["segments"] if seg.get("arena"))["arena"] == fight["arena"]
    bad = copy.deepcopy(doc)
    arena = next(seg for seg in bad["segments"] if seg.get("arena"))["arena"]
    arena.update(result="draw", rating=-5, match="x")
    arena["fighters"][0] = {"name": "<b>", "class": "mage", "server": "11a", "faction": "balaur", "level": 300, "ref": "nobody", "self": "yes"}
    arena["rounds"] += [{"t": 1.0, "winner": 0, "loser": 0}, {"t": 1.0, "winner": 0, "loser": 5}, {"t": -1, "winner": 0, "loser": 1}]
    cleaned = next(seg for seg in a2log.validate(bad)["segments"] if seg.get("arena"))["arena"]
    assert cleaned["fighters"][0] == {"name": "<b>"}                          # keeps its place: rounds name fighters by index
    assert "result" not in cleaned and "rating" not in cleaned and "match" not in cleaned
    assert len(cleaned["rounds"]) == 3
    assert "arena" not in a2log.validate({**doc, "segments": [{**fight, "arena": {"fighters": []}}]})["segments"][0]
