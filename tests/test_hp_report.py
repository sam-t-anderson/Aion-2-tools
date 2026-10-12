"""The opt-OUT, anonymous enemy effective-HP community report: on by default, sends
only the NPC id, the damage an enemy took to die, the raw packet HP and the game
build for a confirmed kill (enemies only, never players/pets), derives a stable
per-install reporter key distinct from the boss and heartbeat keys, and reports each
distinct kill at most once."""
import json
import re

import pytest

from aion2calc.combat import boss_report, heartbeat, hp_report


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


class _FakeResp:
    def __init__(self, captured, req):
        captured.setdefault("reqs", []).append(req)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def read(self):
        return b"{}"


def _capture_urlopen(captured):
    def fake(req, timeout=None):
        return _FakeResp(captured, req)
    return fake


def _doc(**seg):
    """A one-segment kill: enemy e1 (mob 56968) died after taking 6420 damage from
    two players; the game's raw packet max HP for it was 119700. A friendly player
    (p1) and a pet are present and must never be reported."""
    base = {
        "id": "seg-1", "killed": True, "encounter_type": "pve_open_world",
        "game_patch": "1.0.21", "region": "nae", "difficulty": "normal",
        "entities": [
            {"id": "e1", "kind": "enemy", "mob_code": "56968", "name": "Blades Ruins Explorer"},
            {"id": "pl1", "kind": "player", "is_player": True, "name": "Ally"},
            {"id": "pet1", "kind": "pet", "name": "Spirit"},
        ],
        "events": [
            {"kind": "damage", "t": 1.0, "source": "p1", "target": "e1", "amount": 4000},
            {"kind": "damage", "t": 2.0, "source": "p2", "target": "e1", "amount": 2420},
            {"kind": "damage", "t": 1.5, "source": "p1", "target": "pl1", "amount": 999},
            {"kind": "death", "t": 3.0, "target": "e1"},
        ],
        "hits": [
            {"t": 1.0, "player": "p1", "source": "p1", "target": "e1", "damage": 4000},
            {"t": 2.0, "player": "p2", "source": "p2", "target": "e1", "damage": 2420},
        ],
        # Full then dead, with no alive mid-HP packet -> the ratio can't be anchored, so
        # effective_hp falls back to the total observed damage (6420).
        "health": [
            {"t": 0.0, "entity": "e1", "current": 119700, "max": 119700},
            {"t": 2.0, "entity": "e1", "current": 0, "max": 119700},
        ],
    }
    base.update(seg)
    return {"format": "a2log", "version": 1,
            "meta": {"game_patch": "1.0.21"},
            "players": [{"id": "p1", "name": "Me"}, {"id": "p2", "name": "Mate"}],
            "segments": [base]}


def test_reporter_key_is_stable_opaque_and_distinct(isolated_home):
    key = hp_report.reporter_key()
    assert re.fullmatch(r"[A-Za-z0-9]{8,64}", key)          # server's reporter regex
    assert hp_report.reporter_key() == key                  # stable across calls on one install
    assert heartbeat._install_salt() not in key             # salt is never exposed
    assert key != heartbeat.daily_token()                   # distinct from the heartbeat token
    assert key != boss_report.reporter_key()                # distinct from the boss-kill key


def test_enabled_is_opt_out_on_by_default(isolated_home):
    assert hp_report.enabled({}) is True                    # default ON
    assert hp_report.enabled({"meter_report_enemy_hp": True}) is True
    assert hp_report.enabled({"meter_report_enemy_hp": False}) is False   # explicit opt-out


def test_extracts_effective_and_observed_hp_for_the_kill(isolated_home):
    reports = hp_report.observations_from_doc(_doc())
    assert len(reports) == 1                                 # only the dead enemy, not player/pet
    body = reports[0]
    assert body["npc_id"] == 56968                           # mob_code coerced to int
    assert body["effective_hp"] == 6420                      # total damage (fallback: no alive mid-HP packet)
    assert body["observed_hp"] == 119700                     # game's raw packet max HP
    assert body["game_build"] == "1.0.21"
    assert body["attackers"] == 2                            # two distinct attackers (party)
    assert body["region"] == "nae" and body["difficulty"] == "normal"
    assert body["reporter"] == hp_report.reporter_key()


def test_only_confirmed_kills_with_both_scales_qualify(isolated_home):
    assert hp_report.observations_from_doc(_doc(events=[
        {"kind": "damage", "t": 1.0, "source": "p1", "target": "e1", "amount": 4000}])) == []  # no death
    # Enemy died but no packet HP ever seen -> cannot calibrate the two scales.
    assert hp_report.observations_from_doc(_doc(health=[])) == []
    # No game build known -> cannot key the report; the whole doc is skipped.
    doc = _doc(game_patch=None)
    doc["meta"] = {}
    assert hp_report.observations_from_doc(doc) == []


def test_true_hp_strips_the_killing_blow_overkill():
    # Enemy at 10% HP after 900 observed damage; a 500 finisher lands (only 100 needed,
    # 400 overkill) then it dies. Total damage = 1400, but true HP = 900 / (1 - 0.10) = 1000.
    timeline = [(1.0, 900.0), (2.5, 500.0)]
    samples = [(0.0, 1000, 1000), (2.0, 100, 1000)]          # (t, current, max); scales cancel in the ratio
    assert round(hp_report._true_hp(timeline, samples)) == 1000


def test_true_hp_ignores_the_zero_reading_and_uses_the_last_alive_sample():
    # The current==0 packet is NOT used (its damage sum includes the lethal blow's
    # overkill). The deepest ALIVE packet (60% after 400 damage) gives 400 / 0.6... no:
    # 400 removed 40% so true HP = 400 / 0.4 = 1000; the later 600 damage is ignored.
    timeline = [(1.0, 400.0), (2.0, 600.0)]
    samples = [(0.0, 500, 500), (1.0, 300, 500), (2.0, 0, 500)]
    assert hp_report._true_hp(timeline, samples) == 1000.0


def test_true_hp_extrapolates_from_a_partial_last_sample():
    # Deepest packet is 25% remaining after 1500 damage -> true HP = 1500 / 0.75 = 2000.
    assert hp_report._true_hp([(1.0, 1500.0)], [(1.0, 250, 1000)]) == 2000.0


def test_true_hp_is_none_without_usable_samples():
    assert hp_report._true_hp([(1.0, 500.0)], []) is None            # no HP packets
    assert hp_report._true_hp([(1.0, 500.0)], [(0.0, 500, 500)]) is None  # only full-HP samples
    assert hp_report._true_hp([(1.0, 500.0)], [(2.0, 0, 500)]) is None    # only a dead (0 HP) sample
    assert hp_report._true_hp([], [(1.0, 100, 500)]) is None          # no damage timeline


def test_observation_falls_back_to_total_damage_without_max_hp(isolated_home):
    # No usable packet max -> can't compute the ratio, so effective_hp falls back to the
    # total observed damage (and the report is skipped anyway when observed_hp is 0).
    assert hp_report.observations_from_doc(_doc(health=[
        {"t": 2.0, "entity": "e1", "current": 500, "max": 0}])) == []  # observed_hp 0 -> skipped


def test_overkill_is_stripped_end_to_end(isolated_home):
    # A recorded overkill finisher must not inflate the reported effective HP.
    reports = hp_report.observations_from_doc(_doc(
        events=[
            {"kind": "damage", "t": 1.0, "source": "p1", "target": "e1", "amount": 90000},
            {"kind": "damage", "t": 2.5, "source": "p1", "target": "e1", "amount": 40000},  # overkill finisher
            {"kind": "death", "t": 3.0, "target": "e1"},
        ],
        health=[
            {"t": 0.0, "entity": "e1", "current": 119700, "max": 119700},
            {"t": 2.0, "entity": "e1", "current": 11970, "max": 119700},   # 10% left after 90000 dmg
        ]))
    # True HP = 90000 / (1 - 0.10) = 100000, not the 130000 total damage dealt.
    assert reports[0]["effective_hp"] == 100000.0


def test_report_is_opt_out_and_sends_nothing_when_off(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _capture_urlopen(captured))
    assert hp_report.report(_doc(), ui={"meter_report_enemy_hp": False}) == "disabled"
    assert "reqs" not in captured                           # no network when opted out


def test_report_posts_to_endpoint_and_dedupes_repeat_saves(isolated_home, monkeypatch):
    captured = {}
    monkeypatch.setattr(hp_report.share, "effective",
                        lambda: {"url": "https://logs.example.com", "key": "k"})
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", _capture_urlopen(captured))
    ui = {"meter_report_enemy_hp": True}
    assert hp_report.report(_doc(), ui=ui) == "sent:1"
    req = captured["reqs"][0]
    assert req.full_url == "https://logs.example.com/api/v1/enemy-hp"
    body = json.loads(req.data.decode())
    assert body["npc_id"] == 56968 and body["effective_hp"] == 6420
    assert "_sig" not in body                                # internal dedup key never leaves the client
    # A second save of the same fight reports nothing new (local dedup marker).
    captured.clear()
    assert hp_report.report(_doc(), ui=ui) == "already"
    assert "reqs" not in captured


def test_report_never_raises_on_network_error(isolated_home, monkeypatch):
    monkeypatch.setattr(hp_report.share, "effective",
                        lambda: {"url": "https://logs.example.com"})
    def boom(req, timeout=None):
        raise OSError("down")
    monkeypatch.setattr(hp_report.urllib.request, "urlopen", boom)
    assert hp_report.report(_doc(), ui={"meter_report_enemy_hp": True}) == "error"
