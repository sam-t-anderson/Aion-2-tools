"""Combat-records settings on the live session: reset-after-battle signals the
fight is over once combat has been idle past the delay, and the segment list is
capped to the most recent records. Both leave the recorded data itself intact."""
import time

from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _hp(entity, current, maximum, t):
    return {"entity": entity, "kind": "hp", "current": current, "max": maximum, "timestamp_ms": t}


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
    engine.telemetry = [_hp(9001, 500, 1000, now - 11000)]   # boss at 50% (below full) = live
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
    engine.telemetry = [_hp(9001, 500, 1000, now - 11000)]   # boss below full = live
    s.observe(engine, [_hit(5001, 9001, now - 10000, 500)], timestamp_ms=now - 10000)
    assert s.snapshot(scope="auto", segment_id=None)["boss_alive"] is True   # attacker alive

    # The sole attacker dies (full wipe): boss still up (below full), but fight is over.
    s._dead.add((s.epoch, 5001))
    wiped = s.snapshot(scope="auto", segment_id=None)
    assert wiped["boss_alive"] is False
    assert wiped["battle_over"] is True

    # They respawn and re-engage: the revive (HP > 0 telemetry) clears the death flag,
    # and their renewed damage on the still-wounded boss makes the pull read live again.
    s._dead.discard((s.epoch, 5001))
    engine.telemetry = [_hp(9001, 400, 1000, now - 1100)]
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
    engine.telemetry = [_hp(9001, 500, 1000, now - 130000)]
    s.observe(engine, [_hit(5001, 9001, now - 130000, 500)], timestamp_ms=now - 130000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is True                  # boss below full, attacker alive
    assert snap["battle_over"] is True                 # but 130s idle > 120s pull-gap


def test_boss_returning_to_full_hp_starts_a_fresh_attempt(monkeypatch):
    # The reliable encounter boundary: an engaged boss climbing back to full HP is a
    # leash/reset (party wiped out of range, or ran back to a no-lockout boss that
    # healed). It starts a new segment so damage doesn't accumulate across attempts,
    # and reads as not-live so the overlay clears — without relying on player deaths.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    engine.telemetry = [_hp(9001, 500, 1000, now - 20000)]   # engage, boss to 50%
    s.observe(engine, [_hit(5001, 9001, now - 20000, 500)], timestamp_ms=now - 20000)
    assert (s.epoch, 9001) in s._major_below
    assert s.snapshot(scope="auto", segment_id=None)["boss_alive"] is True
    split_before = s.manual_split

    # The boss leashes back to full HP (reset): a fresh attempt begins.
    engine.telemetry = [_hp(9001, 1000, 1000, now - 8000)]
    s.observe(engine, [], timestamp_ms=now - 8000)
    assert s.manual_split == split_before + 1
    assert s.reset_splits == 1
    assert (s.epoch, 9001) not in s._major_below
    done = s.snapshot(scope="auto", segment_id=None)
    assert done["boss_alive"] is False                 # reset boss is not a live fight
    assert done["battle_over"] is True                 # so the overlay clears after the delay


def _death(entity, t):
    return {"entity": entity, "kind": "death", "current": 0, "timestamp_ms": t}


def test_miniboss_held_through_a_lull_by_sustained_engagement(monkeypatch):
    # A mini-boss is NOT flagged isBoss in the catalog, so it is recognised instead by a
    # sustained engagement (>= MAJOR_ENGAGE_MS): once that long into the fight, a mechanic
    # pause must not clear the overlay, just like a boss.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": False})   # nothing is a boss
    s, engine = _session()
    engine.spawn_info = {9500: {"mobCode": 4242}}      # a mini-boss, not isBoss
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    span = session.MAJOR_ENGAGE_MS
    # Fight it from -(span+20s) to -(20s): a sustained engagement that crosses the threshold.
    engine.telemetry = [_hp(9500, 800, 1000, now - span - 20000)]
    s.observe(engine, [_hit(5001, 9500, now - span - 20000, 500)], timestamp_ms=now - span - 20000)
    assert (s.epoch, 9500) not in s._engaged_major     # not major on the first hit
    engine.telemetry = [_hp(9500, 300, 1000, now - 20000)]
    s.observe(engine, [_hit(5001, 9500, now - 20000, 500)], timestamp_ms=now - 20000)
    assert (s.epoch, 9500) in s._engaged_major         # sustained -> now a major engagement
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is True                  # held through the 20s mechanic lull
    assert snap["battle_over"] is False


def test_miniboss_held_when_the_mechanic_pause_comes_early(monkeypatch):
    # The refinement: "major" is elapsed time since first contact, not a hit span, so a
    # mini-boss whose mechanic pause lands before 12s of hits is still held — the
    # threshold is crossed during the lull (driven by HP packets that keep arriving).
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": False})
    s, engine = _session()
    engine.spawn_info = {9700: {"mobCode": 5151}}      # a mini-boss, not isBoss
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    span = session.MAJOR_ENGAGE_MS
    # First contact, boss wounded, then damage stops (an early mechanic) — only one hit.
    engine.telemetry = [_hp(9700, 700, 1000, now - span - 3000)]
    s.observe(engine, [_hit(5001, 9700, now - span - 3000, 500)], timestamp_ms=now - span - 3000)
    assert (s.epoch, 9700) not in s._engaged_major     # not major yet (span not reached)
    # During the lull only HP packets arrive (no damage); once >= MAJOR_ENGAGE_MS has
    # elapsed since first contact, it is promoted mid-lull and the overlay holds.
    engine.telemetry = [_hp(9700, 700, 1000, now - 1000)]
    s.observe(engine, [], timestamp_ms=now - 1000)
    assert (s.epoch, 9700) in s._engaged_major
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is True                  # held through the early mechanic lull


def test_quick_trash_still_clears_after_the_delay(monkeypatch):
    # A brief trash pull (well under the threshold) never becomes major, so reset-after-
    # battle still clears the overlay between pulls.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": False})
    s, engine = _session()
    engine.spawn_info = {9600: {"mobCode": 123}}
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    engine.telemetry = [_hp(9600, 400, 1000, now - 11000), _hp(9600, 100, 1000, now - 9000)]
    s.observe(engine, [_hit(5001, 9600, now - 11000, 500), _hit(5001, 9600, now - 9000, 500)], timestamp_ms=now - 9000)
    assert (s.epoch, 9600) not in s._engaged_major     # ~2s fight: never major
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["boss_alive"] is False
    assert snap["battle_over"] is True                 # 9s idle > 5s delay -> clears


def test_local_respawn_stages_a_reset_that_boss_full_hp_confirms(monkeypatch):
    # A local death+respawn mid boss engagement stages a POTENTIAL reset but never resets
    # on its own; it commits only once the engaged boss is seen back at full HP. A trash
    # mob fought on the runback must not confirm or clear it.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}       # 9001 boss; 8000 is trash (not a boss)
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    engine.telemetry = [_hp(9001, 500, 1000, now - 30000)]
    s.observe(engine, [_hit(5001, 9001, now - 30000, 500)], timestamp_ms=now - 30000)
    split0 = s.manual_split
    assert (s.epoch, 9001) in s._major_below

    # Local player dies to the boss then respawns (graveyard release).
    engine.telemetry = [_death(5001, now - 25000), _hp(5001, 300, 300, now - 20000)]
    s.observe(engine, [], timestamp_ms=now - 20000)
    assert s._pending_reset is True                    # staged, not committed
    assert s.manual_split == split0
    assert s.snapshot(scope="auto", segment_id=None)["potential_reset"] is True

    # An enemy hits them on the runback: a non-boss fight neither confirms nor clears it.
    engine.telemetry = []
    s.observe(engine, [_hit(5001, 8000, now - 12000, 400)], timestamp_ms=now - 12000)
    assert s._pending_reset is True
    assert s.manual_split == split0

    # Back on the boss, it is at full HP (it reset): now the staged reset commits.
    engine.telemetry = [_hp(9001, 1000, 1000, now - 4000)]
    s.observe(engine, [], timestamp_ms=now - 4000)
    assert s.manual_split == split0 + 1
    assert s.reset_splits == 1
    assert s._pending_reset is False


def test_battle_rez_mid_fight_never_resets(monkeypatch):
    # A death + combat rez right at the boss (which never returns to full) stages the
    # reset but must never commit it — the fight continues on the same attempt.
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, engine = _session()
    engine.spawn_info = {9001: {"mobCode": 777}}
    s.reset_after_battle = True
    s.reset_delay_seconds = 5
    now = int(time.time() * 1000)
    engine.telemetry = [_hp(9001, 600, 1000, now - 20000)]
    s.observe(engine, [_hit(5001, 9001, now - 20000, 500)], timestamp_ms=now - 20000)
    split0 = s.manual_split

    engine.telemetry = [_death(5001, now - 18000), _hp(5001, 300, 300, now - 17000)]  # die + battle rez
    s.observe(engine, [], timestamp_ms=now - 17000)
    assert s._pending_reset is True

    # The fight simply continues: the boss keeps taking damage and never hits full.
    engine.telemetry = [_hp(9001, 200, 1000, now - 3000)]
    s.observe(engine, [_hit(5001, 9001, now - 3000, 500)], timestamp_ms=now - 3000)
    assert s.manual_split == split0                    # no reset
    assert s.reset_splits == 0
    assert s.snapshot(scope="auto", segment_id=None)["boss_alive"] is True   # overlay still holds


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
