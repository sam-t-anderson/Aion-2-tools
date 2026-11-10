"""A hit's shield block and its target's Endurance are read and counted, as its parry is (0.2.407).

A hit's modifiers carry the target's defensive procs as bits of their own, and each one that cuts a hit cuts its
value (docs/open-investigations.md, from the 14 archived captures): bit 0x01 a shield block, only on Templars and
Clerics (31.9 % and 14.2 % of monsters' hits on them) and about half the hit; bit 0x02 the parry, about half; bit 0x10
Endurance, a player's only and raised on Templars by Ironclad Defense (20.7 % of monsters' hits on them), half the hit
("Reduces Damage by half", the client's text). The meter read the parry alone, so a Templar's or a Cleric's shield
blocks were missing from the hits they turned and Endurance was not read at all. Synthetic records only."""
import pytest

from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent, SkillStats, SpecialDamage
from aion2calc.meter.a2parser.parser import ENDURANCE, SHIELD_BLOCK
from aion2calc.meter.session import CombatSession
from test_combat_actions import BOSS, ME, OVERHEAD_SLAM, RUINOUS_BLOW, _engine, _observe
from test_regeneration import RANGER, TEMPLAR, _event, _hit, _regeneration

PARRY = 0x02
SWING = 2300100


def test_the_shield_block_and_endurance_bits_are_read():
    assert (SHIELD_BLOCK, ENDURANCE) == (0x01, 0x10)
    assert SpecialDamage.SHIELD_BLOCK in _event(_hit(460, mods=SHIELD_BLOCK)).specials
    assert SpecialDamage.ENDURANCE in _event(_hit(500, mods=ENDURANCE)).specials
    parried = _event(_hit(450, mods=PARRY)).specials
    assert SpecialDamage.PARRY in parried and not {SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE} & parried
    assert not {SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE, SpecialDamage.PARRY} & _event(_hit(1_000)).specials
    # together, and with Regeneration's fifth of what the shield block left
    both = _event(_hit(230, mods=SHIELD_BLOCK | ENDURANCE)).specials
    assert {SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE} <= both
    frame = _hit(460, regenerated=92, mods=SHIELD_BLOCK)
    assert SpecialDamage.SHIELD_BLOCK in _event(frame).specials and _event(frame).total_damage == 460
    assert _regeneration(frame).amount == 92


def test_a_skills_stats_count_them_beside_its_parries():
    stats = SkillStats(SWING)
    for specials in ({SpecialDamage.SHIELD_BLOCK}, {SpecialDamage.ENDURANCE}, {SpecialDamage.PARRY},
                     {SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE}, set()):
        stats.add(DamageEvent(BOSS, ME, SWING, 500, 1, specials=frozenset(specials)))
    assert (stats.hits, stats.parries, stats.shield_blocks, stats.endurance) == (5, 1, 2, 2)


def test_the_engines_skill_stats_export_them():
    engine = MeterEngine()
    engine.set_server_port(13328)
    stream = "1.2.3.4:13328->192.168.1.9:57424"
    for t, mods in ((10_000, SHIELD_BLOCK), (11_000, ENDURANCE), (12_000, PARRY), (13_000, 0)):
        engine.consume(_hit(500, mods=mods), t, stream)
    [actor] = [a for a in engine.snapshot()["actors"] if a["actorId"] == RANGER]
    [skill] = actor["skills"]
    assert (skill["hits"], skill["parry"], skill["shieldBlock"], skill["endurance"]) == (4, 1, 1, 1)
    assert engine.targets[TEMPLAR].actors[RANGER].skills


def test_the_live_view_counts_the_shield_blocks_and_endurance_a_player_took():
    """The player's row counts, beside the hits they parried, the hits they blocked with their shield and the hits
    their Endurance halved; and the share of their own hits a target turned so (in PvP, an opponent's)."""
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    incoming = [({SpecialDamage.SHIELD_BLOCK}, 460), ({SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE}, 230),
                ({SpecialDamage.ENDURANCE}, 500), ({SpecialDamage.PARRY}, 450), (set(), 1_000)]
    for i, (specials, damage) in enumerate(incoming):
        t = 110_000 + 1_000 * i                 # the player strikes first: the fight starts with the party's first hit
        _observe(s, engine, t, events=[DamageEvent(ME, BOSS, RUINOUS_BLOW, 1_200, t,
                                                   specials=frozenset({SpecialDamage.SHIELD_BLOCK} if i == 0 else ())),
                                       DamageEvent(BOSS, ME, SWING, damage, t + 10, specials=frozenset(specials))])
    _observe(s, engine, 116_000, events=[DamageEvent(ME, BOSS, OVERHEAD_SLAM, 600, 116_000,
                                                     specials=frozenset({SpecialDamage.ENDURANCE}))])
    me = next(p for p in s.snapshot()["players"] if p["id"] == str(ME))
    inc = me["incoming"]
    assert (inc["hits"], inc["parries"], inc["shield_blocks"], inc["endurance"]) == (5, 1, 2, 2)
    assert inc["damage"] == 460 + 230 + 500 + 450 + 1_000
    assert me["hits"] == 6
    assert me["shield_block"] == pytest.approx(1 / 6) and me["endurance"] == pytest.approx(1 / 6) and me["parry"] == 0


def test_the_overlay_and_the_meters_defense_panel_show_them():
    from pathlib import Path
    static = Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
    overlay = (static / "overlay.js").read_text(encoding="utf-8")
    assert '["Shield blocks",String(p.incoming&&p.incoming.shield_blocks||0)]' in overlay
    assert '["Endurance",String(p.incoming&&p.incoming.endurance||0)]' in overlay
    parse = (static / "pages" / "parse.js").read_text(encoding="utf-8")
    assert 'rc("Shield blocks", n0(defense.shield_blocks))' in parse and 'rc("Endurance", n0(defense.endurance))' in parse
