"""The overlay keeps the finished fight through a storage rollover (0.2.390).

The live session rolls its records over into a closed archive part once it has grown past its bounds (100 fights,
100,000 records, ...). While the party is fighting the rollover waits, and a final boss's death closes the run,
which lets it fire at once: the kill moved into the closed part and the overlay, reading the fresh continuation,
showed nothing the moment the boss died. Long Transcendence runs reach the bounds within a few runs, so Talisra of
the Void's kill was where it showed: the uploaded parts of those sessions end exactly at her death. The latest view
now shows the carried fight until the continuation has combat of its own: the next run's first fight after a
closed run, the next outgoing hit after an open one, or New."""
import time

import pytest

from aion2calc.app.meter_runner import Runner
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

ME, ALLY, BOSS, NEXT = 5001, 5002, 9001, 9002
NUKE, DOT = 15210000, 1200015


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.combat import hp_db, share
    monkeypatch.setattr(share, "effective", lambda: {})
    monkeypatch.setattr(share, "automatic_uploads_paused", lambda: True)
    monkeypatch.setattr(hp_db, "refresh_async", lambda *a, **k: None)
    e = MeterEngine()
    e.names, e.known_players = {ME: "Me", ALLY: "Ally"}, {ME, ALLY}
    e.roster, e.roster_complete = {"Me": {}, "Ally": {}}, True
    e.local_player_id, e.local_identity_from_game = ME, True
    e.map_id = e.dungeon_id = 600065
    e.last_zone_reset_ms = None
    r = Runner()
    r.running, r.scope, r.save_records, r.packet_engine = True, "party", True, e
    r.session = CombatSession()
    r.session.pvp = False
    monkeypatch.setattr(r, "_maybe_fight_upload", lambda: None)
    monkeypatch.setattr(r, "_maybe_field_bosses", lambda: None)
    return r, e


def _fight(r, e, start, hits=5, target=BOSS):
    for i in range(hits):
        t = start + i * 1000
        r.session.observe(e, [DamageEvent(ME, target, NUKE, 1000, t)], timestamp_ms=t)


def _shown(r, latest=True):
    """The latest view's rows by name: the overlay's reading, or the app's with no segment chosen."""
    snap = r.status(follow_latest=latest, compact=True)["snapshot"]
    return {p["name"]: p["damage"] for p in snap["players"] if p["damage"]}


def _roll_over(r):
    r.session._storage_groups["party"] = 100            # the part is due
    r._rollover_session()
    if r._flush_thread is not None:
        r._flush_thread.join(10)


def test_the_final_boss_fight_stays_on_the_overlay_after_a_rollover_at_the_kill(runner):
    r, e = runner
    now = int(time.time() * 1000)
    _fight(r, e, now - 8000)
    assert _shown(r) == {"Me": 5000}
    # The final boss dies: its death closes the run, and the rollover the fight held off fires at once.
    r.session._dead.add((r.session.epoch, BOSS))
    r.session.finish_run("configured_final_boss_death", timestamp_ms=now - 3500)
    _roll_over(r)
    assert r.archive_part == 2 and not r.session.records          # the kill went into the closed part
    assert _shown(r) == {"Me": 5000}                               # ... and the overlay still shows it
    assert _shown(r, latest=False) == {"Me": 5000}                 # so does the app's latest view
    key = next(p["key"] for p in r.status(follow_latest=True, compact=True)["snapshot"]["players"] if p["name"] == "Me")
    assert r.player_detail(key, follow_latest=True)["damage"] == 5000
    # Neither the dead boss's DoT on a player nor a hit on its corpse opens the next run: still the kill.
    r.session.observe(e, [DamageEvent(BOSS, ME, DOT, 399, now - 2000)], timestamp_ms=now - 2000)
    r.session.observe(e, [DamageEvent(ME, BOSS, DOT, 120, now - 1500)], timestamp_ms=now - 1500)
    assert r.session.run_closed and _shown(r) == {"Me": 5000}
    # The next run's first fight, a couple of minutes on, takes over, alone.
    r.session.observe(e, [DamageEvent(ME, NEXT, NUKE, 700, now + 150_000)], timestamp_ms=now + 150_000)
    assert not r.session.run_closed and _shown(r) == {"Me": 700}
    assert r._carry is None


def test_new_clears_the_carried_fight(runner):
    r, e = runner
    now = int(time.time() * 1000)
    _fight(r, e, now - 8000)
    r.session._dead.add((r.session.epoch, BOSS))
    r.session.finish_run("configured_final_boss_death", timestamp_ms=now - 3500)
    _roll_over(r)
    assert _shown(r) == {"Me": 5000}
    r.split_now()
    assert _shown(r) == {}


def test_an_idle_rollover_mid_run_keeps_the_last_fight_until_the_next_outgoing_hit(runner):
    r, e = runner
    now = int(time.time() * 1000)
    _fight(r, e, now - 300_000)                                    # five minutes ago: nothing holds the rollover off
    _roll_over(r)
    assert not r.session.run_closed and r.archive_part == 2
    assert _shown(r) == {"Me": 5000}
    r.session.observe(e, [DamageEvent(NEXT, ME, NUKE, 300, now - 1000)], timestamp_ms=now - 1000)   # struck first
    assert _shown(r) == {"Me": 5000}
    r.session.observe(e, [DamageEvent(ME, NEXT, NUKE, 700, now)], timestamp_ms=now)
    assert _shown(r) == {"Me": 700}


def test_a_filter_changed_after_the_rollover_reads_the_carried_fight_again(runner):
    r, e = runner
    now = int(time.time() * 1000)
    _fight(r, e, now - 8000, hits=3)
    _fight(r, e, now - 5000, hits=2, target=NEXT)
    r.session.identities[r.session.epoch]["spawns"][BOSS] = {"mobCode": 2350709}   # Talisra of the Void
    r.session._dead.add((r.session.epoch, BOSS))
    r.session.finish_run("configured_final_boss_death", timestamp_ms=now - 3500)
    _roll_over(r)
    assert _shown(r) == {"Me": 5000}
    r.overlay_targets = frozenset({"boss"})
    assert _shown(r) == {"Me": 3000}


def test_the_live_meter_page_can_still_pick_a_fight_of_the_carried_part(runner):
    r, e = runner
    now = int(time.time() * 1000)
    _fight(r, e, now - 200_000, hits=2, target=NEXT)                # an earlier pull of the run
    _fight(r, e, now - 8000)                                        # the final boss
    r.session._dead.add((r.session.epoch, BOSS))
    r.session.finish_run("configured_final_boss_death", timestamp_ms=now - 3500)
    _roll_over(r)
    snap = r.status(follow_latest=False, compact=True)["snapshot"]
    ids = [segment["id"] for segment in snap["segments"]]
    assert len(ids) == 2 and _shown(r, latest=False) == {"Me": 5000}
    r.segment_id = ids[0]
    assert _shown(r, latest=False) == {"Me": 2000}
    key = snap["players"][0]["key"]
    assert r.player_detail(key)["damage"] == 2000
    r.segment_id = "all"                                            # the whole session is the new part's
    assert _shown(r, latest=False) == {}
