"""MP, effective healing and boss casts (0.2.307), decoded from the diagnostic captures:

* ``00 8d`` entity ``01 01 01`` u32 is the recording player's MP (drops equal the skills' listed
  costs); the player's own ``33 36`` record carries its maximum HP and MP;
* ``09 38`` is an NPC's skill cast in the ``02 38`` layout; casts by bosses are kept per fight;
* a heal on a player restores at most the HP they are missing, read from the party HP feed.
"""
from pathlib import Path

from aion2calc.combat import a2log
from aion2calc.combat.actions import boss_casts, mp
from aion2calc.combat.healing import heal_kind, summarize as healing
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import scan_actions, scan_self_vitals
from aion2calc.meter.session import CombatSession

from test_combat_actions import ALLY, BOSS, ME, OVERHEAD_SLAM, _cast, _engine, _frame, _hit, _observe, _u32, _varint

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
TRAMPLE = 1800570


def _self_record(entity, hp, mp_max, pad=190):
    return _frame(b"\x33\x36", _varint(entity) + b"\x00" * pad + b"\x01" + _varint(hp) + _varint(hp) + _u32(mp_max) + _u32(mp_max))


def test_the_mp_feed_npc_casts_and_the_players_own_record_are_decoded():
    assert scan_actions(_frame(b"\x00\x8d", _varint(ME) + b"\x01\x01\x01" + _u32(2807) + b"\x00" * 4)) == [
        {"kind": "mp", "entity": ME, "current": 2807}]
    assert scan_actions(_frame(b"\x00\x8d", _varint(ME) + b"\x02\x01\x00" + _u32(23467) + b"\x00" * 4)) == []   # the HP feed
    [cast] = scan_actions(_cast(BOSS, TRAMPLE, 1, ME).replace(b"\x02\x38", b"\x09\x38", 1))
    assert (cast["kind"], cast["actor"], cast["skill"], cast["target"], cast["npc"]) == ("cast", BOSS, TRAMPLE, ME, True)
    assert scan_self_vitals(_self_record(ME, 23467, 3077)) == (ME, 23467, 3077)
    assert scan_self_vitals(_self_record(ME, 23467, 3077, pad=40)) is None          # not where the record carries it
    assert scan_self_vitals(_frame(b"\x33\x36", _varint(ME) + b"\x00" * 190 + b"\x01" + _varint(9000) + _varint(23467))) is None


def test_the_engine_takes_the_local_players_maximum_hp_and_mp_from_its_own_record():
    engine = MeterEngine()
    engine.local_player_id = ME
    engine.consume(_self_record(ALLY, 30000, 2000), 1_000, STREAM)
    assert "maxHp" not in engine.spawn_info.get(ALLY, {})                           # someone else's record
    engine.consume(_self_record(ME, 23467, 3077), 1_100, STREAM)
    assert {k: engine.spawn_info[ME][k] for k in ("maxHp", "reportedMaxHp", "maxMp")} == {"maxHp": 23467, "reportedMaxHp": 23467, "maxMp": 3077}


def test_a_segment_exports_the_recording_players_mp_and_the_bosses_casts():
    engine, s = _engine(), CombatSession()
    s.pvp = False
    engine.spawn_info[ME] = {"maxMp": 3077}
    _observe(s, engine, 101_000)
    _observe(s, engine, 105_000, actions=[{"kind": "mp", "entity": ME, "current": 2900},
                                          {"kind": "mp", "entity": ALLY, "current": 100}])        # only the local player's MP is sent
    _observe(s, engine, 110_000, events=[_hit(ME, OVERHEAD_SLAM, 110_000)],
             actions=[{"kind": "mp", "entity": ME, "current": 2780},
                      {"kind": "cast", "actor": BOSS, "skill": TRAMPLE, "seq": 1, "at_target": True, "target": ME, "npc": True},
                      {"kind": "cast", "actor": 77777, "skill": TRAMPLE, "seq": 1, "at_target": True, "target": ME}])  # not a boss
    _observe(s, engine, 111_000, events=[_hit(ALLY, OVERHEAD_SLAM, 111_000)],
             actions=[{"kind": "mp", "entity": ME, "current": 2780},                              # unchanged: one row
                      {"kind": "mp", "entity": ME, "current": 2830}])
    doc = s.to_a2log()
    segment = doc["segments"][-1]
    me = next(p["id"] for p in doc["players"] if p["name"] == "Me")
    boss = next(e["id"] for e in segment["entities"] if e.get("mob_code") == 2300615)
    assert [(r["t"], r["entity"], r["mp"], r.get("max")) for r in segment["resources"]] == [
        (0.0, me, 2900, 3077), (0.0, me, 2780, 3077), (1.0, me, 2830, 3077)]
    assert [(c["source"], c["skill_id"], c.get("target")) for c in segment["npc_casts"]] == [(boss, TRAMPLE, me)]
    clean = a2log.validate(doc)["segments"][-1]
    assert clean["resources"] == segment["resources"] and clean["npc_casts"] == segment["npc_casts"]


def test_mp_read_before_the_recording_player_is_known_is_kept_for_that_player():
    engine, s = _engine(), CombatSession()
    s.pvp = False
    engine.local_player_id = None                    # not known yet (a capture started mid-instance)
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, OVERHEAD_SLAM, 110_000)], actions=[{"kind": "mp", "entity": ME, "current": 2500}])
    engine.local_player_id = ME
    _observe(s, engine, 111_000, events=[_hit(ALLY, OVERHEAD_SLAM, 111_000)], actions=[{"kind": "mp", "entity": ME, "current": 2400}])
    doc = s.to_a2log()
    me = next(p["id"] for p in doc["players"] if p["name"] == "Me")
    assert [(r["entity"], r["mp"]) for r in doc["segments"][-1]["resources"]] == [(me, 2500), (me, 2400)]


def test_the_validator_drops_bad_mp_rows_and_casts_by_non_entities():
    doc = {"format": "a2log", "version": 1, "players": [{"id": "p1", "name": "Me"}],
           "segments": [{"duration": 10.0, "hits": [{"t": 1.0, "player": "p1", "damage": 1.0}],
                         "entities": [{"id": "b1", "name": "Boss", "is_boss": True}],
                         "resources": [{"t": 1.0, "entity": "p1", "mp": 500, "max": 400},     # max below the reading: dropped
                                       {"t": 2.0, "entity": "b1", "mp": 5},                  # not a player
                                       {"t": 3.0, "entity": "p1", "mp": -1}],
                         "npc_casts": [{"t": 1.0, "source": "b1", "skill_id": TRAMPLE, "target": "p1"},
                                       {"t": 2.0, "source": "p1", "skill_id": TRAMPLE},       # a player is not an NPC
                                       {"t": 99.0, "source": "b1", "skill_id": TRAMPLE}]}]}
    clean = a2log.validate(doc)["segments"][0]
    assert clean["resources"] == [{"t": 1.0, "entity": "p1", "mp": 500}]
    assert clean["npc_casts"] == [{"t": 1.0, "source": "b1", "skill_id": TRAMPLE, "target": "p1"}]


def test_mp_spent_restored_and_time_low_are_summarised():
    segment = {"duration": 60.0, "resources": [
        {"t": 0.0, "entity": "p1", "mp": 3000, "max": 3077}, {"t": 10.0, "entity": "p1", "mp": 400, "max": 3077},
        {"t": 30.0, "entity": "p1", "mp": 900, "max": 3077}, {"t": 50.0, "entity": "p1", "mp": 600, "max": 3077}]}
    [row] = mp(segment)
    assert (row["start"], row["end"], row["lowest"], row["max"], row["max_from_record"]) == (3000, 600, 400, 3077, True)
    assert (row["spent"], row["restored"]) == (2900, 500)
    assert row["seconds_low"] == 20.0 + 10.0                                             # 400 for 20 s, 600 for the last 10 s
    [row] = mp({"duration": 10.0, "resources": [{"t": 0.0, "entity": "p1", "mp": 1000}, {"t": 5.0, "entity": "p1", "mp": 900}]})
    assert (row["max"], row["max_from_record"]) == (1000, False)                         # no record: the highest reading


def test_boss_casts_are_grouped_by_skill_with_their_targets():
    segment = {"npc_casts": [{"t": 5.0, "source": "b1", "skill_id": TRAMPLE, "skill": "Trample", "target": "p1"},
                             {"t": 1.0, "source": "b1", "skill_id": 1800655, "skill": "Wave of Death"},
                             {"t": 9.0, "source": "b1", "skill_id": TRAMPLE, "skill": "Trample", "target": "p2"},
                             {"t": 12.0, "source": "b1", "skill_id": TRAMPLE, "skill": "Trample", "target": "p1"}]}
    result = boss_casts(segment)
    assert [(k["skill"], k["casts"], k["first"], k["last"]) for k in result["skills"]] == [("Wave of Death", 1, 1.0, 1.0), ("Trample", 3, 5.0, 12.0)]
    assert result["skills"][1]["targets"] == [{"target": "p1", "casts": 2}, {"target": "p2", "casts": 1}]
    assert [(c["t"], c["casts"]) for c in result["timeline"]] == [(1.0, 1), (5.0, 1), (9.0, 1), (12.0, 1)]
    # A channelled skill sends a cast every few hundredths of a second: quick repeats fold into one row.
    spin = [{"t": 20.0 + 0.05 * i, "source": "b1", "skill_id": 1800551} for i in range(45)]
    result = boss_casts({"npc_casts": segment["npc_casts"] + spin})
    folded = result["timeline"][-1]
    assert (folded["t"], folded["skill_id"], folded["casts"], round(folded["end"], 6)) == (20.0, 1800551, 45, 22.2)
    assert next(k for k in result["skills"] if k["skill_id"] == 1800551)["casts"] == 45 and result["omitted_timeline"] == 0


def test_effective_healing_is_capped_by_the_missing_hp_and_checked_against_the_next_reading():
    health = [{"t": 1.0, "entity": "p2", "current": 15000.0, "max": 20000.0},
              {"t": 2.0, "entity": "p2", "current": 16000.0, "max": 20000.0},     # after the first heal: exact
              {"t": 3.0, "entity": "p2", "current": 20000.0, "max": 20000.0},     # after the second: capped
              {"t": 5.0, "entity": "p3", "current": 9000.0}]                        # no maximum known
    events = [{"kind": "heal", "t": 2.0, "source": "p1", "target": "p2", "amount": 1000.0},
              {"kind": "heal", "t": 3.0, "source": "p1", "target": "p2", "amount": 6000.0},
              {"kind": "heal", "t": 3.0, "source": "p1", "target": "p2", "amount": 500.0},      # same read: nothing left to restore
              {"kind": "heal", "t": 6.0, "source": "p1", "target": "p3", "amount": 700.0},
              {"kind": "heal", "t": 0.5, "source": "p1", "target": "p2", "amount": 300.0},      # before any reading
              {"kind": "heal", "t": 4.0, "source": "p1", "target": "pet1", "amount": 50.0}]     # not a player
    result = healing({"events": events, "health": health}, {"p1", "p2", "p3"})
    [healer] = result["healers"]
    assert (healer["amount"], healer["effective"], healer["overheal"], healer["unknown"], healer["heals"]) == (8500, 5000, 2500, 1000, 5)
    assert healer["overheal_pct"] == round(100 * 2500 / 7500, 1)
    # Per read: t=2 rose by its heal in full; t=3 topped up to the maximum (both heals in that read);
    # p3 has no maximum and the t=0.5 heal no earlier reading.
    assert result["check"] == {"reads": 4, "exact": 1, "capped": 1, "other": 0, "unchecked": 2}
    assert healing({"events": [], "health": health}, {"p1"}) is None
    boss_heal = [{"kind": "heal", "t": 2.0, "source": "boss", "target": "p2", "amount": 900.0}]
    assert healing({"events": boss_heal, "health": health}, {"p1", "p2"}, healers={"p1", "p2"}) is None   # not the party's healing


def test_heals_over_time_and_shields_are_listed_apart_not_measured():
    assert heal_kind(17090001, "Light of Regeneration") == "over_time"       # "restores ... HP every 1s for 14s"
    assert heal_kind(18240001, "Impeding Authority") == "shield"             # "a Protective Shield that blocks damage"
    assert heal_kind(17100001, "Healing Light") == "instant"
    assert heal_kind(None, "Life Potion") == "over_time"                      # potions heal over time
    health = [{"t": 1.0, "entity": "p2", "current": 15000.0, "max": 20000.0}]
    events = [{"kind": "heal", "t": 2.0, "source": "p1", "target": "p2", "amount": 6000.0, "skill_id": 17090001},
              {"kind": "heal", "t": 2.0, "source": "p1", "target": "p2", "amount": 3000.0, "skill_id": 18240001},
              {"kind": "heal", "t": 2.0, "source": "p1", "target": "p2", "amount": 1000.0, "skill_id": 17100001}]
    [healer] = healing({"events": events, "health": health}, {"p1", "p2"})["healers"]
    assert (healer["amount"], healer["effective"], healer["over_time"], healer["shield"], healer["overheal"]) == (10000, 1000, 6000, 3000, 0)


def test_the_review_shows_mp_boss_casts_and_effective_healing():
    js = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")
    assert '["boss","Boss casts"]' in js and "s.boss_casts" in js
    assert "<h4>MP</h4>" in js and "s.mp" in js
    assert "Effective healing and overheal" in js and "s.healing_effect" in js
