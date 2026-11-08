"""The overlay's damage filters (0.2.390): Boss damage only counts the hits on bosses -- dungeon bosses, mini-bosses
(a curated boss role, or an enemy with a break gauge), field and world bosses -- and leaves out trash and, in the
open world, other players; Player (PvP) damage only counts the hits on other players; both count both. The rows,
totals, DPS and its clock, the target card and the player panel follow them; the enemies, healing and damage taken
do not. They are saved settings that the views following the latest fight (the overlay windows, RTSS) apply."""
import json

import pytest

from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.session import CombatSession, Record, target_filter

ME, ALLY, RIVAL = 101, 102, 640
BOSS, ELITE, TRASH = 9001, 9002, 9003
TALISRA, MOB = 2350709, 2920150                 # a catalog boss; a monster the catalog does not flag
NUKE = 15210000
PARTY = frozenset({"me", "ally"})          # a record carries its party by the members' folded names


def _session():
    s = CombatSession()
    s.pvp = False
    s.gap_seconds = 120
    s.identities[0] = {"names": {ME: "Me", ALLY: "Ally", RIVAL: "Rival"},
                       "spawns": {BOSS: {"mobCode": TALISRA}, ELITE: {"mobCode": MOB, "breakGauge": 240},
                                  TRASH: {"mobCode": MOB}},
                       "jobs": {}, "local_id": ME, "owners": {}, "roster": {"Me": {}, "Ally": {}},
                       "observed_players": {ME, ALLY, RIVAL}, "player_ids": {ME, ALLY, RIVAL}}
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1
    hits = [(ME, TRASH, 1000, 1000), (ME, BOSS, 2000, 3000), (ALLY, BOSS, 4000, 3000), (ME, ELITE, 5000, 500),
            (ME, RIVAL, 6000, 700), (ALLY, TRASH, 7000, 100), (TRASH, ME, 7500, 50), (BOSS, ALLY, 7600, 80)]
    s.records = [Record(0, DamageEvent(actor_id=a, target_id=t, skill_code=NUKE, damage=d, timestamp_ms=ms),
                        PARTY, ME, 0, 1, i)
                 for i, (a, t, ms, d) in enumerate(hits, start=1)]
    s.records.append(Record(0, HealEvent(actor_id=ALLY, skill_code=0, amount=900, timestamp_ms=7700, target_id=ME),
                            PARTY, ME, 0, 1, 99))
    return s


def _rows(snap):
    return {p["name"]: p for p in snap["players"]}


def test_without_a_filter_every_hit_counts():
    snap = _session().snapshot("party")
    rows = _rows(snap)
    assert rows["Me"]["damage"] == 1000 + 3000 + 500 + 700 and rows["Ally"]["damage"] == 3000 + 100
    assert snap["targets"] == []


def test_boss_damage_only_counts_bosses_and_enemies_with_a_break_gauge():
    s = _session()
    snap = s.snapshot("party", targets=["boss"])
    rows = _rows(snap)
    assert rows["Me"]["damage"] == 3000 + 500              # the boss and the elite, not the trash nor the rival
    assert rows["Ally"]["damage"] == 3000
    assert snap["total"] == 6500 and snap["targets"] == ["boss"]
    # its clock counts the seconds with kept damage only: 2, 4 and 5 s into the fight
    assert snap["duration"] == 3 and rows["Me"]["dps"] == pytest.approx(3500 / 3)
    # the enemies, healing and damage taken stay whole
    assert {e["name"] for e in snap["enemies"]} >= {"Talisra of the Void", "Rival"}
    assert next(e for e in snap["enemies"] if e["id"] == str(BOSS))["is_boss"] is True
    assert next(e for e in snap["enemies"] if e["id"] == str(TRASH))["is_boss"] is False
    assert rows["Ally"]["healing"] == 900 and rows["Me"]["incoming"]["damage"] == 50
    # the target card follows the boss-like enemy you struck last (the elite), not the rival you struck after it
    assert snap["current_target"]["entity_id"] == ELITE
    assert _session().snapshot("party")["current_target"]["entity_id"] == RIVAL


def test_a_curated_boss_role_counts_as_a_boss(monkeypatch):
    from aion2calc.meter import session as module
    s = _session()
    s.identities[0]["spawns"][TRASH] = {"mobCode": 2300907}           # Shining Mau Totem: isBoss false, role miniboss
    assert module.npc_info(2300907).get("isBoss") is False and module.npc_info(2300907).get("role") == "miniboss"
    rows = _rows(s.snapshot("party", targets=["boss"]))
    assert rows["Me"]["damage"] == 1000 + 3000 + 500 and rows["Ally"]["damage"] == 3000 + 100


def test_player_damage_only_counts_the_hits_on_other_players():
    snap = _session().snapshot("party", targets=["player"])
    rows = _rows(snap)
    assert rows["Me"]["damage"] == 700 and rows.get("Ally", {}).get("damage", 0) == 0
    assert snap["duration"] == 1 and snap["targets"] == ["player"]
    assert snap["current_target"]["name"] == "Rival" and snap["current_target"]["is_player"] is True


def test_both_filters_count_bosses_and_players_but_not_trash():
    snap = _session().snapshot("party", targets=["player", "boss", "nonsense"])
    rows = _rows(snap)
    assert rows["Me"]["damage"] == 3000 + 500 + 700 and rows["Ally"]["damage"] == 3000
    assert snap["targets"] == ["boss", "player"]
    assert target_filter(["boss", "x", None]) == frozenset({"boss"}) and target_filter(None) == frozenset()


def test_the_player_panel_follows_the_filter():
    s = _session()
    snap = s.snapshot("party", targets=["boss"])
    key = _rows(snap)["Me"]["key"]
    detail = s.player_detail(key, "party", None, True, ["boss"])
    assert detail["damage"] == 3500 and {sk["damage"] for sk in detail["skills"]} == {3500}
    assert s.player_detail(key, "party", None, True)["damage"] == 5200


def test_a_hit_on_another_players_summon_is_player_damage():
    s = _session()
    pet = 777
    s.identities[0]["spawns"][pet] = {"mobCode": MOB}
    s.identities[0]["owners"][pet] = RIVAL
    s.records.append(Record(0, DamageEvent(actor_id=ME, target_id=pet, skill_code=NUKE, damage=250, timestamp_ms=6500),
                            PARTY, ME, 0, 1, 50))
    assert _rows(s.snapshot("party", targets=["player"]))["Me"]["damage"] == 700 + 250
    assert _rows(s.snapshot("party", targets=["boss"]))["Me"]["damage"] == 3500


# -- the settings and the runner ------------------------------------------------------------------

def test_the_filters_are_saved_settings_that_the_latest_views_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app import server, settings_backup
    from aion2calc.app.meter_runner import Runner
    from aion2calc.paths import write_user_json
    defaults = server.ui_settings()
    assert defaults["overlay_boss_only"] is False and defaults["overlay_pvp_only"] is False
    assert {"overlay_boss_only", "overlay_pvp_only"} <= set(settings_backup._BOOL_KEYS)
    write_user_json({"overlay_boss_only": True}, "ui.json")
    r = Runner()
    r.apply_record_settings()
    assert r.overlay_targets == frozenset({"boss"})
    write_user_json({"overlay_boss_only": True, "overlay_pvp_only": True}, "ui.json")
    r.apply_record_settings()
    assert r.overlay_targets == frozenset({"boss", "player"})


def test_the_overlay_reading_is_filtered_and_the_apps_is_not(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app.meter_runner import Runner
    from aion2calc.meter.a2parser.engine import MeterEngine
    r = Runner()
    r.packet_engine, r.scope, r.session = MeterEngine(), "party", _session()
    r.overlay_targets = frozenset({"boss"})
    overlay = r.status(follow_latest=True, compact=True)
    assert overlay["targets"] == ["boss"] and _rows(overlay["snapshot"])["Me"]["damage"] == 3500
    assert r.player_detail(_rows(overlay["snapshot"])["Me"]["key"], follow_latest=True)["damage"] == 3500
    app = r.status(follow_latest=False, compact=True)
    assert app["targets"] == [] and _rows(app["snapshot"])["Me"]["damage"] == 5200
    json.dumps(overlay)                                  # the reading still serialises
