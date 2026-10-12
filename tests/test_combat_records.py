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


def test_battle_not_over_while_an_engaged_boss_is_still_alive(monkeypatch):
    # A boss mechanic that halts damage for several seconds must not clear the overlay:
    # while an engaged boss is alive, the fight is not over past the reset delay.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}       # target 9001 is a boss
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    s.observe(engine, [_hit(5001, 9001, now - 12000, 500), _hit(5001, 9001, now - 10000, 500)], timestamp_ms=now - 10000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is True
    assert snap["battle_over"] is False                # 10s idle > 5s delay, but the boss lives

    # Once that boss dies, the lull does end the fight after the delay.
    s._dead.add((s.epoch, 9001))
    after = s.snapshot(scope="auto", segment_id=None)
    assert after["boss_alive"] is False
    assert after["battle_over"] is True


def test_battle_over_on_a_wipe_even_though_the_boss_survives(monkeypatch):
    # A wipe ends the fight even if the boss lives: once every party attacker is dead,
    # the overlay must clear after the delay instead of holding the stale attempt. A
    # gradual wipe therefore holds only until the last member dies (one attacker alive
    # here keeps it live; killing them tips it over).
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    s.observe(engine, [_hit(5001, 9001, now - 10000, 500)], timestamp_ms=now - 10000)
    assert s.snapshot(scope="auto", segment_id=None)["boss_alive"] is True   # attacker alive

    # The sole attacker dies (full wipe): boss still up, but the fight is over.
    s._dead.add((s.epoch, 5001))
    wiped = s.snapshot(scope="auto", segment_id=None)
    assert wiped["boss_alive"] is False
    assert wiped["battle_over"] is True

    # They respawn and re-engage: the revive (HP > 0 telemetry) clears the death flag,
    # and their renewed damage makes the pull read live again.
    s._dead.discard((s.epoch, 5001))
    s.observe(engine, [_hit(5001, 9001, now - 1000, 500)], timestamp_ms=now - 1000)
    assert s.snapshot(scope="auto", segment_id=None)["boss_alive"] is True


def test_boss_fight_ends_when_truly_abandoned(monkeypatch):
    # A pull left for longer than the pull-gap is genuinely over even if the boss
    # never died (gave up / walked away), so the view is allowed to clear.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    s.gap_seconds = 120
    now = int(time.time() * 1000)
    s.observe(engine, [_hit(5001, 9001, now - 130000, 500)], timestamp_ms=now - 130000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is True                  # never recorded as dead
    assert snap["battle_over"] is True                 # but 130s idle > 120s pull-gap


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
