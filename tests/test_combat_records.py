"""Combat-records settings on the live session: reset-after-battle signals the
fight is over once combat has been idle past the delay, and the segment list is
capped to the most recent records. Both leave the recorded data itself intact."""
import time

from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _session():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me"}
    engine.roster = {"Me": {}}
    return s, engine


def test_battle_over_only_after_the_reset_delay_when_enabled():
    s, engine = _session()
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    s.observe(engine, [_hit(5001, 9001, now - 9000, 500), _hit(5001, 9001, now - 8000, 500)], timestamp_ms=now - 8000)
    # Last damage was 8s ago, past the 5s delay → the fight reads as over.
    assert s.snapshot(scope="auto", segment_id=None)["battle_over"] is True
    # The data is untouched: the whole-session view still shows it.
    assert s.snapshot(scope="auto", segment_id="all")["total"] == 1000


def test_battle_not_over_within_the_delay_or_when_disabled():
    s, engine = _session()
    s.reset_after_battle = True
    s.reset_delay_seconds = 30
    now = int(time.time() * 1000)
    s.observe(engine, [_hit(5001, 9001, now - 3000, 500)], timestamp_ms=now - 3000)
    assert s.snapshot(scope="auto", segment_id=None)["battle_over"] is False   # only 3s idle

    s.reset_after_battle = False
    s.reset_delay_seconds = 1
    assert s.snapshot(scope="auto", segment_id=None)["battle_over"] is False   # disabled entirely


def test_save_records_flag_follows_the_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.paths import write_user_json
    from aion2calc.app.meter_runner import Runner
    r = Runner()
    assert r.save_records is True                       # default: auto-save on
    write_user_json({"meter_save_records": False}, "ui.json")
    r.apply_record_settings()
    assert r.save_records is False                       # the runner honors the setting


def test_segment_list_is_capped_to_max_records():
    s, engine = _session()
    s.gap_seconds = 1                       # force each pull into its own segment
    base = 0
    for i in range(6):
        base = i * 10_000                   # 10s apart → beyond the 1s gap
        s.observe(engine, [_hit(5001, 9001 + i, base, 500)], timestamp_ms=base)
    uncapped = s.snapshot(scope="auto", segment_id="all")
    assert len(uncapped["segments"]) >= 5   # several distinct combats recorded

    s.max_records = 3
    capped = s.snapshot(scope="auto", segment_id="all")
    assert len(capped["segments"]) == 3     # only the most recent are listed
    assert capped["segments"] == uncapped["segments"][-3:]
