"""The overlay's player panel (0.2.364): one player of the live view in depth — the row's totals and special-hit
shares, each skill's crit, back and parry shares, the seconds they dealt damage, and the buffs on them with their
uptime from the fight's effect records — and the overlay look settings behind it (background mode, row effects)."""
import pytest

from aion2calc.app import settings_backup
from aion2calc.meter.a2parser.models import DamageEvent, SpecialDamage
from aion2calc.meter.session import CombatSession

from test_combat_actions import ALLY, BOSS, ME, OVERHEAD_SLAM, RUINOUS_BLOW, _engine, _observe


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path

PROTECTION, MANTRA = 17200000, 18300000


def _hit(actor, skill, t, damage=1000, specials=()):
    return DamageEvent(actor_id=actor, target_id=BOSS, skill_code=skill, damage=damage, timestamp_ms=t,
                       specials=frozenset(specials))


def test_the_panel_reads_one_players_shares_skills_and_buff_uptime():
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, RUINOUS_BLOW, 110_000, 1200, {SpecialDamage.CRITICAL, SpecialDamage.BACK})],
             actions=[{"kind": "effect", "target": ME, "instance": 8, "effect": PROTECTION * 10 + 1, "duration_ms": 10_000,
                       "source": ALLY, "skill": PROTECTION},
                      {"kind": "effect", "target": ME, "instance": 9, "effect": MANTRA * 10 + 1, "duration_ms": None,
                       "source": ME, "skill": MANTRA}])
    _observe(s, engine, 112_000, events=[_hit(ME, RUINOUS_BLOW, 112_000, 800), _hit(ME, OVERHEAD_SLAM, 112_000, 500, {SpecialDamage.PARRY}),
                                         _hit(ALLY, OVERHEAD_SLAM, 112_000, 300)])
    _observe(s, engine, 114_000, events=[_hit(ME, RUINOUS_BLOW, 114_000, 1000, {SpecialDamage.CRITICAL})],
             actions=[{"kind": "effect_end", "target": ME, "instance": 9, "reason": 1}])          # the mantra ends at 14 s
    _observe(s, engine, 130_000, events=[_hit(ALLY, OVERHEAD_SLAM, 130_000, 300)])
    snap = s.snapshot()
    me = next(p for p in snap["players"] if p["id"] == str(ME))
    # the snapshot's row now carries each skill's special-hit shares beside the row's
    ruinous = next(k for k in me["skills"] if k["skill_id"] == RUINOUS_BLOW)
    assert ruinous["hits"] == 3 and ruinous["crit"] == pytest.approx(2 / 3) and ruinous["back"] == pytest.approx(1 / 3) and ruinous["parry"] == 0
    slam = next(k for k in me["skills"] if k["skill_id"] == OVERHEAD_SLAM)
    assert slam["parry"] == 1.0 and slam["crit"] == 0
    assert me["crit"] == pytest.approx(0.5) and me["back"] == pytest.approx(0.25) and me["parry"] == pytest.approx(0.25)

    detail = s.player_detail(me["key"])
    assert detail["name"] == me["name"] and detail["damage"] == 3500 and detail["hits"] == 4 and "timeline" not in detail
    assert detail["active_seconds"] == 3                                   # 110, 112 and 114 s
    assert detail["duration"] == snap["duration"] and detail["share"] == pytest.approx(3500 / 4100)
    assert [k["skill_id"] for k in detail["skills"]] == [RUINOUS_BLOW, OVERHEAD_SLAM]
    buffs = {b["skill_id"]: b for b in detail["buffs"]}
    duration = snap["recorded_duration"]
    assert set(buffs) == {PROTECTION, MANTRA}
    # the 10 s protection from 110 s, the mantra from 110 s to its removal at 114 s, both clipped to the fight
    assert buffs[PROTECTION]["seconds"] == pytest.approx(min(10.0, duration - 9.0), abs=0.11) and not buffs[PROTECTION]["self"]
    assert buffs[MANTRA]["seconds"] == pytest.approx(4.0, abs=0.11) and buffs[MANTRA]["self"] and buffs[MANTRA]["applications"] == 1
    assert buffs[PROTECTION]["uptime_pct"] == pytest.approx(100 * buffs[PROTECTION]["seconds"] / duration, abs=0.2)
    assert detail["buffs"][0]["skill_id"] == PROTECTION                     # the longest first
    # another row, and one that is not in the view
    ally = s.player_detail(next(p["key"] for p in snap["players"] if p["id"] == str(ALLY)))
    assert ally["buffs"] == [] and ally["hits"] == 2
    assert s.player_detail("nobody") is None


def test_the_overlay_look_settings_round_trip_and_validate(isolated_home):
    s = settings_backup.import_settings({"overlay_bg_mode": "top", "overlay_me_cosmetic": "gold", "overlay_top_cosmetic": "rainbow"})["settings"]
    assert (s["overlay_bg_mode"], s["overlay_me_cosmetic"], s["overlay_top_cosmetic"]) == ("top", "gold", "rainbow")
    for key, bad in (("overlay_bg_mode", "glass"), ("overlay_me_cosmetic", "platinum"), ("overlay_top_cosmetic", 3)):
        with pytest.raises(ValueError):
            settings_backup.import_settings({key: bad})
