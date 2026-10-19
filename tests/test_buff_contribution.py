"""The estimated buff contribution (0.2.307): buff-adjusted DPS and an rDPS split per player, built
from the recorded effect windows and kept out of rankings until it has been checked against real data.

A +X % PvE Damage Boost adds X to the hit's additive boost bucket, so ``X / (1 + B + X - tolerance)``
of a hit made with it came from the buff; that share moves from the hitter to the buff's caster.
"""
import json
import math

import pytest

from aion2calc.combat import a2log as F
from aion2calc.combat import contribution as C

MANTRA, LOP, FURY, CHAIN, PROMISE = 18190000, 17410000, 12780000, 17070000, 18780000
PLAYERS = [{"id": "sor", "name": "Sorc", "class": "sorcerer"}, {"id": "cha", "name": "Chant", "class": "chanter"},
           {"id": "cle", "name": "Cleric", "class": "cleric"}, {"id": "cha2", "name": "Chant2", "class": "chanter"}]


def _doc(effects, hits, encounter_type=None, players=PLAYERS):
    segment = {"duration": 20.0, "hits": hits, "effects": effects,
               "entities": [{"id": "boss", "is_boss": True}, {"id": "mob"}]}
    doc = {"format": "a2log", "version": 1, "players": [dict(p) for p in players], "segments": [segment]}
    if encounter_type:
        doc["meta"] = {"encounter_type": encounter_type}
    return doc


def _effect(skill, source, target, t=0.0, end=20.0, effect_id=None):
    return {"t": t, "end": end, "skill_id": skill, "source": source, "target": target, "effect_id": effect_id}


def _hits(player, n=5, damage=1000.0, target="boss", start=1.0, **flags):
    return [{"t": start + i, "player": player, "damage": damage, "target": target, "skill_id": 15210000, **flags}
            for i in range(n)]


def _share(cls, value, tolerance=C.BOSS_TOLERANCE):
    return value / (1 + C.typical_boost(cls) + value - tolerance)


def test_an_aura_moves_its_share_of_each_hit_to_the_caster_and_keeps_the_total():
    effects = [_effect(MANTRA, "cha", "sor", effect_id=181900411), _effect(MANTRA, "cha", "cha", effect_id=181900411)]
    hits = _hits("sor") + _hits("cha", n=2, damage=500.0)
    result = C.summarize(_doc(effects, hits), 0)
    rows = {r["player"]: r for r in result["players"]}
    value = C.value_pct(MANTRA, 22) / 100                      # band 4 -> level 20-24, taken at 22
    assert value == pytest.approx(0.21)
    expected = 5000 * _share("sorcerer", value)
    assert rows["sor"]["received"] == round(expected) and rows["sor"]["adjusted_damage"] == round(5000 - expected)
    assert rows["cha"]["received"] == 0                       # the caster's own Mantra is its own damage
    assert rows["cha"]["given"] == round(expected) and rows["cha"]["contribution_damage"] == round(1000 + expected)
    assert sum(r["contribution_damage"] for r in rows.values()) == pytest.approx(sum(r["damage"] for r in rows.values()), abs=2)
    assert result["given"][0] == {"source": "cha", "recipient": "sor", "skill_id": MANTRA,
                                  "skill": "Undefeated Mantra", "damage": round(expected)}
    [buff] = [b for b in result["buffs"] if b["source"] == "cha"]
    assert (buff["level"], buff["basis"], buff["value_pct"]) == (22, "effect", 21.0)
    assert result["assumptions"]["ranked"] is False


def test_auras_that_do_not_stack_credit_only_the_strongest_and_ties_share():
    effects = [_effect(MANTRA, "cha", "sor", effect_id=181900411),          # 21 %
               _effect(LOP, "cle", "sor", effect_id=174100311)]             # 18.5 %: does not stack
    result = C.summarize(_doc(effects, _hits("sor")), 0)
    given = {r["player"]: r["given"] for r in result["players"]}
    assert given.get("cle", 0) == 0 and given["cha"] > 0
    # Two Chanters' Mantras at the same level apply once; the credit is shared.
    effects = [_effect(MANTRA, "cha", "sor", effect_id=181900411), _effect(MANTRA, "cha2", "sor", effect_id=181900411)]
    rows = {r["player"]: r for r in C.summarize(_doc(effects, _hits("sor")), 0)["players"]}
    assert rows["cha"]["given"] == rows["cha2"]["given"] == pytest.approx(rows["sor"]["received"] / 2, abs=1)
    assert rows["sor"]["received"] == round(5000 * _share("sorcerer", 0.21))


def test_a_tolerance_cut_on_the_boss_credits_its_caster_for_every_hit_on_that_boss():
    effects = [_effect(CHAIN, "cle", "boss"), _effect(PROMISE, "cha", "boss", effect_id=187800091)]
    hits = _hits("sor") + _hits("sor", n=3, target="mob")      # hits on another enemy are not covered
    rows = {r["player"]: r for r in C.summarize(_doc(effects, hits), 0)["players"]}
    assert C.value_pct(CHAIN, 1) == C.value_pct(CHAIN, 30) == 5   # the same 5 % at every level
    assert rows["sor"]["received"] == round(5000 * _share("sorcerer", 0.05))
    assert rows["cle"]["given"] == rows["sor"]["received"]
    assert rows.get("cha", {}).get("given", 0) == 0           # Earth's Promise yields to Chain of Torment


def test_pet_hits_crits_and_pvp_are_handled_conservatively():
    effects = [_effect(MANTRA, "cha", "sor", effect_id=181900411)]
    pets = [dict(h, pet="Fire Spirit") for h in _hits("sor")]
    rows = {r["player"]: r for r in C.summarize(_doc(effects, pets), 0)["players"]}
    assert rows["sor"]["damage"] == 5000 and rows["sor"]["received"] == 0      # pet hits stay unadjusted
    assert C.summarize(_doc(effects, _hits("sor"), encounter_type="pvp_arena"), 0) is None
    assert C.summarize(_doc([], _hits("sor")), 0) is None       # nothing recorded, nothing estimated


def test_the_casters_level_comes_from_the_profile_then_the_effect_record_then_the_typical_player():
    profile = {"status": "ready", "data": {"skill": {"skillList": [{"id": MANTRA, "skillLevel": 25, "category": "Dp"}]}}}
    players = [dict(p, profile_snapshot=profile) if p["id"] == "cha" else p for p in PLAYERS]
    effects = [_effect(MANTRA, "cha", "sor", effect_id=181900211)]
    [buff] = C.summarize(_doc(effects, _hits("sor"), players=players), 0)["buffs"]
    assert (buff["level"], buff["basis"], buff["value_pct"]) == (25, "profile", 22.5)
    [buff] = C.summarize(_doc(effects, _hits("sor")), 0)["buffs"]
    assert (buff["level"], buff["basis"]) == (12, "effect")    # band 2 -> 10-14
    [buff] = C.summarize(_doc([_effect(MANTRA, "cha", "sor")], _hits("sor")), 0)["buffs"]
    assert (buff["level"], buff["basis"]) == (C.typical_level(MANTRA), "typical")
    # A passive's effect id does not name its level: Fury's is 01 whatever level the caster's profile lists.
    [buff] = C.summarize(_doc([_effect(FURY, "cle", "sor", effect_id=127800011)], _hits("sor")), 0)["buffs"]
    assert (buff["level"], buff["basis"]) == (C.typical_level(FURY), "typical")


def test_effect_ids_name_a_level_band_for_auras_but_not_a_passives_level():
    assert C.level_from_effect(MANTRA, 181900411) == (22, 20, 24)
    assert C.level_from_effect(MANTRA, 181900111) == (7, 5, 9)
    assert C.level_from_effect(LOP, 174100011) == (2, 1, 4)
    assert C.level_from_effect(FURY, 127800011) is None
    assert C.level_from_effect(PROMISE, 187800011) is None
    assert C.level_from_effect(MANTRA, 174100311) is None      # another skill's id
    assert C.level_from_effect(CHAIN, 170700011) is None       # a fixed value needs no level
    assert C.level_from_effect(MANTRA, None) is None


def test_the_check_compares_plain_hits_with_and_without_the_buff_and_pools_across_fights():
    effects = [_effect(MANTRA, "cha", "sor", t=10.0, end=20.0, effect_id=181900411)]
    hits = _hits("sor", n=6, damage=1000.0, start=1.0) + _hits("sor", n=6, damage=1200.0, start=11.0)
    hits += [dict(h, crit=True, damage=99999.0) for h in _hits("sor", n=3, start=12.5)]   # crits are left out
    [check] = C.summarize(_doc(effects, hits), 0)["checks"]
    assert check["group"] == "aura" and (check["hits_on"], check["hits_off"]) == (6, 6)
    assert check["measured_pct"] == 20.0
    expected = 100 * (1 + C.typical_boost("sorcerer") + 0.21 - 0.3) / (1 + C.typical_boost("sorcerer") - 0.3) - 100
    assert check["estimated_pct"] == round(expected, 1)
    pooled = C.pool_checks([{"checks": [check]}, {"checks": [check]}, None])
    assert pooled == [{"group": "aura", "fights": 2, "pairs": 2, "hits_on": 12, "hits_off": 12,
                       "measured_pct": 20.0, "estimated_pct": round(expected, 1)}]
    assert math.isclose(pooled[0]["measured_pct"], check["measured_pct"])


def test_the_check_compares_a_skills_hits_on_the_same_target_only():
    # A skill hits a boss (30 % Damage Tolerance, its own Defense) harder or softer than its adds, so hits
    # with the buff on the boss are not set against hits without it on an add.
    effects = [_effect(MANTRA, "cha", "sor", t=10.0, end=20.0, effect_id=181900411)]
    hits = _hits("sor", n=6, damage=1000.0, start=1.0) + _hits("sor", n=6, damage=1200.0, start=11.0)
    hits += _hits("sor", n=6, damage=3000.0, target="mob", start=1.5)        # an add, only without it
    [check] = C.summarize(_doc(effects, hits), 0)["checks"]
    assert (check["pairs"], check["hits_on"], check["hits_off"]) == (1, 6, 6) and check["measured_pct"] == 20.0


def test_the_estimate_reaches_the_review_and_the_cli_but_never_the_ranking(tmp_path):
    doc = _doc([_effect(MANTRA, "cha", "sor", effect_id=181900411)], _hits("sor") + _hits("cha", n=1))
    clean = F.validate(json.loads(json.dumps(doc)))
    segment = clean["encounter_insights"]["segments"][0]
    assert clean["encounter_insights"]["version"] == 5 and segment["contribution"]["players"]
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")
    assert '["contribution","Buff contribution"]' in js and "not used for rankings or parses" in js
    assert "encounter_insights?.segments?.find(x=>x.segment===state.segment)?.contribution" in js
    path = tmp_path / "fight.a2log.json"
    hits = _hits("sor", n=6, start=1.0) + _hits("sor", n=6, damage=1200.0, start=11.0)
    path.write_text(json.dumps(_doc([_effect(MANTRA, "cha", "sor", t=10.0, end=20.0, effect_id=181900411)], hits)))
    from aion2calc.calibrate import buff_checks
    report = buff_checks([str(tmp_path)])
    assert report["files"] == 1 and report["pooled"][0]["group"] == "aura" and report["pooled"][0]["hits_off"] == 6
