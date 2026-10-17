"""Combat actions (0.2.306): the cast, cast-end, chain-window, effect and break-gauge records are
decoded, kept for the party, exported per segment, cleaned by the a2log validator, and summarised
into rotation, buff/debuff/crowd-control and break-gauge reviews. The layouts come from the
supplied diagnostic captures (docs/open-investigations.md)."""
from aion2calc.combat import a2log
from aion2calc.combat.actions import cc_state, stagger_value, summarize
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import scan_actions
from aion2calc.meter.session import CombatSession

ME, ALLY, BOSS = 4062, 4063, 51000
OVERHEAD_SLAM, RENDING_BLOW, RUINOUS_BLOW = 11170000, 11010000, 11100000
WAVE_BLOW, ICE_CHAIN, PROTECTION = 18080000, 15090000, 17410000


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


def _u32(v):
    return v.to_bytes(4, "little")


def _f32s(*values):
    import struct
    return b"".join(struct.pack("<f", v) for v in values)


def _cast(actor, skill, seq, target, *, aimed=True, cooldown=0):
    body = _varint(actor) + b"\x00" + _u32(skill) + bytes([seq, 2 if aimed else 0]) + _varint(target) + _f32s(173.2)
    if aimed:
        body += _f32s(13631.1, -9851.9, 93124.0)
    return _frame(b"\x02\x38", body + _varint(12609) + b"\x01" + _varint(cooldown))


# ------------------------------------------------------------------ decoder
def test_a_cast_record_carries_its_target_position_and_cooldown():
    [cast] = scan_actions(_cast(ME, RUINOUS_BLOW + 450, 8, BOSS, cooldown=40900))
    assert (cast["kind"], cast["actor"], cast["skill"], cast["seq"], cast["target"]) == ("cast", ME, RUINOUS_BLOW + 450, 8, BOSS)
    assert cast["at_target"] and cast["cooldown_ms"] == 40900 and cast["position"] == [13631.1, -9851.9, 93124.0]
    [proc] = scan_actions(_cast(ME, 11800007, 9, ME, aimed=False))
    assert not proc["at_target"] and proc["cooldown_ms"] == 0 and "position" not in proc


def test_cast_end_chain_effect_and_gauge_records_are_read():
    [end] = scan_actions(_frame(b"\x06\x38", _varint(ME) + _u32(OVERHEAD_SLAM + 350) + bytes([29, 12])))
    assert (end["kind"], end["actor"], end["skill"], end["seq"]) == ("cast_end", ME, OVERHEAD_SLAM + 350, 29)
    [opened] = scan_actions(_frame(b"\x18\x38", _u32(11020140) + b"\x01" + _u32(11030140)))
    assert (opened["kind"], opened["skill"], opened["next"]) == ("chain_open", 11020140, 11030140)
    [closed] = scan_actions(_frame(b"\x19\x38", b"\x01" + _u32(11030140)))
    assert (closed["kind"], closed["next"]) == ("chain_close", 11030140)
    effect_body = (_varint(BOSS) + b"\x13" + _varint(2634) + _u32(WAVE_BLOW * 10 + 1) + (3000).to_bytes(8, "little")
                   + (1792114870012).to_bytes(8, "little") + _varint(ME) + b"\x0c" + _u32(WAVE_BLOW) + b"\x01\x02"
                   + _f32s(74760.3, -22831.5, 3470.6))
    [effect] = scan_actions(_frame(b"\x2b\x38", effect_body))
    assert (effect["target"], effect["instance"], effect["duration_ms"], effect["source"], effect["skill"]) == (BOSS, 2634, 3000, ME, WAVE_BLOW)
    permanent = effect_body.replace((3000).to_bytes(8, "little"), b"\xff" * 8)
    assert scan_actions(_frame(b"\x2b\x38", permanent))[0]["duration_ms"] is None
    ends = scan_actions(_frame(b"\x2c\x38", _varint(BOSS) + b"\x02" + b"\x00" + _varint(2634) + b"\x01" + b"\x00" + _varint(7) + b"\x13"))
    assert [(e["instance"], e["reason"]) for e in ends] == [(2634, 1), (7, 19)]
    gauge = _varint(BOSS) + b"\x03\x01" + _u32(1200) + _u32(701) + b"\x02"
    assert scan_actions(_frame(b"\x05\xe0", gauge)) == [{"kind": "gauge", "entity": BOSS, "max": 1200, "current": 701, "state": 2}]


def test_malformed_action_records_are_ignored():
    assert scan_actions(_frame(b"\x02\x38", _varint(ME) + b"\x00" + _u32(42) + b"\x01\x02" + _varint(BOSS))) == []  # no skill id
    bad_kind = _varint(ME) + b"\x00" + _u32(OVERHEAD_SLAM) + b"\x01\xc2" + _varint(BOSS)
    assert scan_actions(_frame(b"\x02\x38", bad_kind)) == []
    assert scan_actions(_frame(b"\x2b\x38", _varint(BOSS) + b"\x13")) == []                 # truncated
    assert scan_actions(_frame(b"\x04\x38", b"\x00" * 20)) == []                             # not an action record


def test_the_engine_keeps_the_local_cooldowns_chain_windows_and_gauges():
    engine = MeterEngine()
    engine.local_player_id = ME
    stream = "1.2.3.4:13328->192.168.1.9:57424"
    engine.consume(_cast(ME, RUINOUS_BLOW + 450, 8, BOSS, cooldown=40900), 1_000, stream)
    assert engine.cooldowns[RUINOUS_BLOW] == {"skill": RUINOUS_BLOW + 450, "cast_ms": 1_000, "cooldown_ms": 40900}
    engine.consume(_cast(ALLY, OVERHEAD_SLAM, 3, BOSS, cooldown=9000), 1_100, stream)
    assert OVERHEAD_SLAM not in engine.cooldowns                  # another player's cooldown is not ours
    engine.consume(_frame(b"\x18\x38", _u32(11020140) + b"\x01" + _u32(11030140)), 1_200, stream)
    assert engine.chain_windows == {11030140: 1_200}
    engine.consume(_frame(b"\x19\x38", b"\x01" + _u32(11030140)), 1_900, stream)
    assert engine.chain_windows == {}
    engine.consume(_frame(b"\x05\xe0", _varint(BOSS) + b"\x03\x01" + _u32(1200) + _u32(990) + b"\x02"), 2_000, stream)
    assert engine.break_gauges[BOSS] == (1200, 990, 2_000)
    assert [a["kind"] for a in engine.actions] == ["gauge"]      # actions are per read


# ------------------------------------------------------------------ session export
def _engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600053
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = ME
    engine.names = {ME: "Me", ALLY: "Ally"}
    engine.known_players = {ME, ALLY}
    engine.roster = {"Me": {}, "Ally": {}}
    engine.spawn_info = {BOSS: {"mobCode": 2300615}}
    return engine


def _observe(session, engine, t, events=(), actions=()):
    engine.actions = [{**a, "timestamp_ms": t} for a in actions]
    session.observe(engine, list(events), timestamp_ms=t)
    engine.actions = []


def _hit(actor, skill, t, damage=1000):
    return DamageEvent(actor_id=actor, target_id=BOSS, skill_code=skill, damage=damage, timestamp_ms=t)


def test_a_segment_exports_the_party_casts_effects_gauge_and_chains():
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 109_800, actions=[{"kind": "cast", "actor": ME, "skill": RUINOUS_BLOW + 450, "seq": 8, "at_target": True,
                                           "target": BOSS, "cooldown_ms": 40900}])
    _observe(s, engine, 110_000, events=[_hit(ME, RUINOUS_BLOW, 110_000)],
             actions=[{"kind": "cast_end", "actor": ME, "skill": RUINOUS_BLOW + 450, "seq": 8, "flag": 12},
                      {"kind": "cast", "actor": 9999, "skill": OVERHEAD_SLAM, "seq": 1, "at_target": True, "target": BOSS},  # a stranger
                      {"kind": "effect", "target": BOSS, "instance": 7, "effect": WAVE_BLOW * 10 + 1, "duration_ms": 3000,
                       "source": ME, "skill": WAVE_BLOW},
                      {"kind": "effect", "target": ALLY, "instance": 8, "effect": PROTECTION * 10 + 1, "duration_ms": 10000,
                       "source": ME, "skill": PROTECTION},
                      {"kind": "gauge", "entity": BOSS, "max": 1200, "current": 1175},
                      {"kind": "chain_open", "skill": 11020140, "next": 11030140}])
    _observe(s, engine, 111_000, events=[_hit(ALLY, OVERHEAD_SLAM, 111_000)],
             actions=[{"kind": "gauge", "entity": BOSS, "max": 1200, "current": 1175},          # unchanged: one reading
                      {"kind": "chain_close", "next": 11030140}])
    _observe(s, engine, 113_000, events=[_hit(ME, RENDING_BLOW, 113_000)],
             actions=[{"kind": "effect_end", "target": BOSS, "instance": 7, "reason": 1}])
    segment = s.to_a2log()["segments"][-1]
    me = next(p["id"] for p in s.to_a2log()["players"] if p["name"] == "Me")
    boss = next(e["id"] for e in segment["entities"] if e.get("mob_code") == 2300615)
    assert [(c["source"], c["skill_id"], c.get("cooldown_ms"), c.get("cast_ms"), c["t"]) for c in segment["casts"]] == [
        (me, RUINOUS_BLOW, 40900, 200, -0.2)]                           # the stranger's cast is not in the party log
    effects = {e["skill_id"]: e for e in segment["effects"]}
    assert (effects[WAVE_BLOW]["target"], effects[WAVE_BLOW]["source"], effects[WAVE_BLOW]["end"], effects[WAVE_BLOW]["ended"]) == (boss, me, 3.0, "expired")
    assert effects[PROTECTION]["end"] == segment["duration"]           # still running when the segment ends
    assert [(g["entity"], g["current"]) for g in segment["gauge"]] == [(boss, 1175)]
    assert [(c["player"], c["next_id"], c["end"]) for c in segment["chains"]] == [(me, 11030000, 1.0)]   # base skill ids, as hits


def test_a_held_effect_is_one_row_and_a_reused_instance_ends_the_earlier_one():
    # The game re-sends a held effect on its instance (an aura every second), sends no removal for
    # most expiries, and reuses instance numbers for other effects; a removal names only the instance.
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    aura = {"kind": "effect", "target": ALLY, "instance": 8, "effect": PROTECTION * 10 + 1, "duration_ms": 2400,
            "source": ME, "skill": PROTECTION}
    _observe(s, engine, 110_000, events=[_hit(ME, RUINOUS_BLOW, 110_000)], actions=[aura])
    for t in range(111_000, 120_000, 1_000):                            # refreshed every second for 10 s
        _observe(s, engine, t, events=[_hit(ME, RENDING_BLOW, t)], actions=[aura])
    _observe(s, engine, 130_000, events=[_hit(ME, RENDING_BLOW, 130_000)], actions=[aura])   # lapsed, then cast again
    slow = {"kind": "effect", "target": BOSS, "instance": 9, "effect": ICE_CHAIN * 10 + 1, "duration_ms": 5000,
            "source": ME, "skill": ICE_CHAIN}
    _observe(s, engine, 131_000, events=[_hit(ME, RENDING_BLOW, 131_000)], actions=[slow])
    knock = {"kind": "effect", "target": BOSS, "instance": 9, "effect": WAVE_BLOW * 10 + 1, "duration_ms": 3000,
             "source": ALLY, "skill": WAVE_BLOW}                         # the same instance, another effect
    _observe(s, engine, 133_000, events=[_hit(ALLY, OVERHEAD_SLAM, 133_000)], actions=[knock])
    _observe(s, engine, 134_000, events=[_hit(ME, RENDING_BLOW, 134_000)],
             actions=[{"kind": "effect_end", "target": BOSS, "instance": 9, "reason": 19}])
    _observe(s, engine, 140_000, events=[_hit(ME, RENDING_BLOW, 140_000)])
    segment = s.to_a2log()["segments"][-1]
    rows = [(e["skill_id"], e["t"], e["end"], e.get("ended")) for e in segment["effects"]]
    assert rows == [(PROTECTION, 0.0, 11.4, None),                       # the last refresh at 9 s + 2.4 s
                    (PROTECTION, 20.0, 22.4, None),
                    (ICE_CHAIN, 21.0, 23.0, None),                       # ended when the instance was reused
                    (WAVE_BLOW, 23.0, 24.0, "removed")]                  # the removal is the knockdown's
    assert [e.get("refreshes") for e in segment["effects"]] == [9, None, None, None]


def test_the_validator_drops_unreferenced_or_malformed_action_rows():
    doc = {"format": "a2log", "version": 1, "meta": {}, "players": [{"id": "p1", "name": "Me"}],
           "segments": [{"duration": 10, "hits": [], "entities": [{"id": "b", "name": "Boss", "kind": "enemy", "is_boss": True}],
                         "casts": [{"t": 1, "source": "p1", "skill_id": OVERHEAD_SLAM, "cooldown_ms": 9000},
                                   {"t": 1, "source": "nobody", "skill_id": OVERHEAD_SLAM},
                                   {"t": 99, "source": "p1", "skill_id": OVERHEAD_SLAM}],
                         "effects": [{"t": 2, "end": 5, "target": "b", "source": "p1", "skill_id": WAVE_BLOW, "ended": "expired"},
                                     {"t": 5, "end": 2, "target": "b", "skill_id": WAVE_BLOW}],
                         "gauge": [{"t": 3, "entity": "b", "max": 1200, "current": 900},
                                   {"t": 3, "entity": "b", "max": 1200, "current": 1300}],
                         "chains": [{"t": 1, "player": "p1", "skill_id": 11020140, "next_id": 11030140, "end": 2}]}]}
    segment = a2log.validate(doc)["segments"][0]
    assert [c["source"] for c in segment["casts"]] == ["p1"]
    assert [e["ended"] for e in segment["effects"]] == ["expired"]
    assert [g["current"] for g in segment["gauge"]] == [900]
    assert len(segment["chains"]) == 1 and segment["validation"]["filtered"] == 4


# ------------------------------------------------------------------ summaries
def test_skill_descriptions_name_the_crowd_control_and_stagger_values():
    assert cc_state(WAVE_BLOW) == "Knockdown" and cc_state(ICE_CHAIN) == "Slow"
    assert cc_state(OVERHEAD_SLAM) is None          # "a target afflicted with Knockdown": a condition, not inflicted
    assert stagger_value(OVERHEAD_SLAM) == 5 and stagger_value(RENDING_BLOW) == 2


def _review_segment():
    casts = [{"t": t, "source": "me", "skill_id": RUINOUS_BLOW + 450, "skill": "Ruinous Blow", "target": "boss", "cooldown_ms": 40000, "cast_ms": 380}
             for t in (0.0, 40.0, 81.0)]
    casts += [{"t": t + 0.35, "source": "me", "skill_id": RUINOUS_BLOW + 68, "skill": "Ruinous Blow", "target": "boss"} for t in (0.0, 40.0, 81.0)]
    casts += [{"t": t, "source": "me", "skill_id": 11800007, "skill": "Murderous Burst"} for t in (1.0, 2.0, 3.0)]
    casts += [{"t": 10.0, "source": "me", "skill_id": 11020140, "skill": "Keen Strike", "target": "boss"},
              {"t": 11.0, "source": "me", "skill_id": 11030140, "skill": "Rupture Strike", "target": "boss"},
              {"t": 20.0, "source": "me", "skill_id": 11000100, "skill": "Dodge", "cooldown_ms": 500}]
    return {"duration": 120.0, "entities": [{"id": "boss", "name": "Boss", "kind": "enemy", "is_boss": True}],
            "casts": casts,
            "chains": [{"t": 10.0, "end": 11.0, "player": "me", "skill_id": 11020140, "next_id": 11030140, "next": "Rupture Strike"},
                       {"t": 50.0, "end": 52.0, "player": "me", "skill_id": 11020140, "next_id": 11030140, "next": "Rupture Strike"}],
            "effects": [{"t": 0.0, "end": 30.0, "target": "ally", "source": "me", "skill_id": PROTECTION, "skill": "Light of Protection"},
                        {"t": 20.0, "end": 60.0, "target": "ally", "source": "me", "skill_id": PROTECTION, "skill": "Light of Protection"},
                        {"t": 5.0, "end": 8.0, "target": "boss", "source": "me", "skill_id": WAVE_BLOW, "skill": "Wave Blow", "ended": "expired"},
                        {"t": 30.0, "end": 31.0, "target": "boss", "source": "ally", "skill_id": WAVE_BLOW, "skill": "Wave Blow", "ended": "removed"}],
            "gauge": [{"t": 1.0, "entity": "boss", "max": 100, "current": 100},
                      {"t": 2.0, "entity": "boss", "max": 100, "current": 93},       # one hit alone: Overhead Slam's 5... read 7
                      {"t": 3.0, "entity": "boss", "max": 100, "current": 2},        # shared read: split 5 : 2
                      {"t": 9.0, "entity": "boss", "max": 100, "current": 100}],     # refilled: a 6 s break
            "hits": [{"t": 2.0, "player": "me", "target": "boss", "skill_id": OVERHEAD_SLAM, "damage": 100},
                     {"t": 3.0, "player": "me", "target": "boss", "skill_id": OVERHEAD_SLAM, "damage": 100},
                     {"t": 3.0, "player": "ally", "target": "boss", "skill_id": RENDING_BLOW, "damage": 100},
                     {"t": 5.0, "player": "ally", "target": "boss", "skill_id": RENDING_BLOW, "damage": 400}]}


def test_the_rotation_counts_presses_cooldown_use_chains_and_dodges():
    result = summarize(_review_segment(), {"me", "ally"}, {"me", "ally"}, {"boss": {"is_boss": True}})
    rows = {r["skill"]: r for r in result["rotation"]["skills"]}
    ruinous = rows["Ruinous Blow"]                    # the follow-up part of each press is not a second cast
    assert (ruinous["kind"], ruinous["casts"], ruinous["cooldown_ms"], ruinous["possible"], ruinous["usage_pct"], ruinous["cast_ms"]) == (
        "skill", 3, 40000, 3, 100.0, 380)
    assert rows["Murderous Burst"]["kind"] == "proc" and rows["Murderous Burst"]["casts"] == 3
    [chain] = result["rotation"]["chains"]
    assert (chain["opened"], chain["used"], chain["used_pct"]) == (2, 1, 50.0)
    assert result["rotation"]["dodges"] == [{"source": "me", "count": 1, "times": [20.0]}]
    totals = result["rotation"]["totals"][0]
    assert (totals["casts"], totals["procs"]) == (6, 3)


def test_buff_uptime_merges_overlaps_and_crowd_control_is_listed_by_state():
    result = summarize(_review_segment(), {"me", "ally"}, {"me", "ally"}, {"boss": {"is_boss": True}})
    [buff] = result["buffs"]
    assert (buff["skill"], buff["seconds"], buff["uptime_pct"], buff["applications"]) == ("Light of Protection", 60.0, 50.0, 2)
    [debuff] = result["debuffs"]
    assert (debuff["skill"], debuff["seconds"], debuff["applications"]) == ("Wave Blow", 4.0, 2)
    assert [(c["state"], c["source"], c["seconds"], c["ended"]) for c in result["crowd_control"]] == [
        ("Knockdown", "me", 3.0, "expired"), ("Knockdown", "ally", 1.0, "removed")]
    by = {r["source"]: r for r in result["crowd_control_by_source"]}
    assert by["ally"]["broken_early"] == 1 and by["me"]["hard"] == 1


def test_the_break_gauge_is_shared_by_skill_stagger_values_with_its_breaks():
    [boss] = summarize(_review_segment(), {"me", "ally"}, {"me", "ally"}, {"boss": {"is_boss": True}})["stagger"]
    shares = {p["player"]: p["amount"] for p in boss["players"]}
    assert shares == {"me": 7 + 91 * 5 / 7, "ally": 91 * 2 / 7} or all(abs(shares[k] - v) < 0.06 for k, v in
                                                                         {"me": 7 + 91 * 5 / 7, "ally": 91 * 2 / 7}.items())
    assert boss["breaks"] == [{"t": 3.0, "end": 9.0, "seconds": 6.0}]
    assert {p["player"]: p["break_damage"] for p in boss["players"]} == {"me": 100, "ally": 500}


def test_encounter_insights_keep_imported_buff_windows_beside_the_action_summaries():
    from aion2calc.combat.insights import summarize as insights
    segment = {**_review_segment(), "buffs": [{"player": "me", "name": "Imported Buff", "start": 0.0, "end": 12.0}]}
    doc = {"players": [{"id": "me", "name": "Me"}, {"id": "ally", "name": "Ally"}], "segments": [segment]}
    [result] = insights(doc)["segments"]
    assert [(b["player"], b["name"], b["seconds"]) for b in result["buffs"]] == [("me", "Imported Buff", 12.0)]
    assert result["actions"]["buffs"][0]["skill"] == "Light of Protection"
    assert result["actions"]["rotation"]["totals"][0]["casts"] == 6 and result["actions"]["stagger"][0]["breaks"]


def test_calibrate_measures_cooldowns_cast_lock_and_next_press_from_recorded_casts():
    from aion2calc.calibrate import recorded_timings
    casts = []
    for i in range(12):                                   # a chained filler pair, 0.3 s apart
        t = 2.0 * i
        casts += [{"t": t, "source": "me", "skill_id": RENDING_BLOW + 30, "skill": "Rending Blow", "target": "boss", "cast_ms": 300},
                  {"t": t + 0.3, "source": "me", "skill_id": 11200000, "skill": "Smashing Blow", "target": "boss", "cast_ms": 320}]
    casts += [{"t": 1.0 + 15 * i, "source": "me", "skill_id": 11040000, "skill": "Leaping Slam", "target": "boss",
               "cooldown_ms": 13600, "cast_ms": 440} for i in range(2)]
    casts.append({"t": 3.0, "source": "ally", "skill_id": RENDING_BLOW, "skill": "Rending Blow", "target": "boss"})
    rows = {r["skill"]: r for r in recorded_timings({"duration": 30.0, "casts": casts}, "me", "gladiator")}
    rending = rows["Rending Blow"]
    assert (rending["casts"], rending["cast_lock_s"], rending["next_press_median_s"]) == (12, 0.3, 0.3)
    from aion2calc.run import kit_module
    assert rending["kit_key"] == "rending_blow" and rending["kit_action_s"] == kit_module("gladiator").TIMING["rending_blow"]
    assert rending["kit_value_s"] == 0.29        # (0.30 s - 30 ms latency) at the typical build's ~8% Combat Speed
    leap = rows["Leaping Slam"]
    assert (leap["cooldown_s"], leap["table_cooldown_s"], leap["cooldown_reduction_pct"]) == (13.6, 15, 9.3)
    assert rows["Smashing Blow"]["kit_key"] is None             # no TIMING knob for it


def test_class_system_actions_are_not_folded_into_one_skill():
    from aion2calc.meter.a2parser.lookup import skill_family
    assert skill_family(11000100) == 11000100 and skill_family(11000000) == 11000000   # Dodge, weapon equip
    assert skill_family(11020140) == 11020000 and skill_family(11170000) == 11170000
    casts = [{"t": 1.0, "source": "me", "skill_id": 11000000, "skill": "Equip Gladiator Weapon", "cooldown_ms": 500},
             {"t": 5.0, "source": "me", "skill_id": 11000100, "skill": "Dodge", "cooldown_ms": 500},
             {"t": 9.0, "source": "me", "skill_id": 11000100, "skill": "Dodge", "cooldown_ms": 500}]
    result = summarize({"duration": 20.0, "casts": casts}, {"me"}, {"me"}, {})
    assert {r["skill"]: r["casts"] for r in result["rotation"]["skills"]} == {"Equip Gladiator Weapon": 1, "Dodge": 2}
    assert result["rotation"]["dodges"] == [{"source": "me", "count": 2, "times": [5.0, 9.0]}]
