"""Candidate marks (0.2.366): the scanner offers the moments that look like an evidence-gated item, only while raw
TCP is recorded; the player confirms or dismisses them, and both outcomes travel with the diagnostics."""

import pytest

from aion2calc.app.candidate_marks import CandidateScanner, COOLDOWN_MS
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent, SpecialDamage

BOSS, TANK, HEALER, DPS, DPS2 = 9001, 11, 12, 13, 14
BOSS_CODE = 600022001       # any catalog boss code: the scanner asks npc_info().isBoss, patched below
SWING, SLAM, HOT, SHIELD = 1600000, 1600680, 23010010, 24010010


class FakeSession:
    def __init__(self):
        self.epoch = 1
        self.identities = {1: {"names": {TANK: "Tanka", HEALER: "Healer", DPS: "Zapp", DPS2: "Pew"}, "owners": {},
                               "spawns": {BOSS: {"mobCode": BOSS_CODE}}, "local_id": TANK}}


class FakeEngine:
    def __init__(self, actions=(), telemetry=()):
        self.actions, self.telemetry = list(actions), list(telemetry)


@pytest.fixture(autouse=True)
def boss_lookup(monkeypatch):
    from aion2calc.app import candidate_marks
    monkeypatch.setattr(candidate_marks, "npc_info", lambda code, locale="en": {"isBoss": code == BOSS_CODE})
    monkeypatch.setattr(candidate_marks, "skill_name", lambda sid, locale="en": {SWING: "Swing", SLAM: "Ground Slam", HOT: "Healing Light",
                                                                                 SHIELD: "Nezekan's Shield"}.get(sid, f"Skill {sid}"))
    monkeypatch.setattr(candidate_marks, "normalize_skill", lambda sid: sid)


def hit(t, target, damage, skill=SWING, actor=BOSS, specials=frozenset()):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=damage, timestamp_ms=t, specials=specials)


def scan(scanner, session, t, events=(), actions=(), telemetry=()):
    return scanner.observe(session, FakeEngine(actions, telemetry), list(events), timestamp_ms=t)


def test_a_hit_on_a_shielded_player_whose_hp_did_not_move_is_a_shield_candidate():
    s, sess = CandidateScanner(), FakeSession()
    out = scan(s, sess, 1000, telemetry=[{"kind": "hp", "entity": TANK, "current": 50_000, "max": 50_000, "timestamp_ms": 1000}],
               actions=[{"kind": "effect", "target": TANK, "source": TANK, "skill": SHIELD, "effect": SHIELD * 10, "instance": 7,
                         "duration_ms": 3000, "timestamp_ms": 1000}])
    assert out == []
    out = scan(s, sess, 1500, events=[hit(1500, TANK, 8000)])
    assert out == []                                            # waits for an HP reading after the hit
    out = scan(s, sess, 1900, telemetry=[{"kind": "hp", "entity": TANK, "current": 50_000, "max": 50_000, "timestamp_ms": 1900}])
    assert [c["label"] for c in out] == ["shield"] and out[0]["kind"] == "candidate" and out[0]["status"] == "pending"
    assert "Nezekan's Shield" in out[0]["why"] and out[0]["context"]["player"] == "Tanka"
    # the same shield on the same player is not offered again within the cooldown
    scan(s, sess, 2500, events=[hit(2500, TANK, 8000)])
    assert scan(s, sess, 2900, telemetry=[{"kind": "hp", "entity": TANK, "current": 50_000, "max": 50_000, "timestamp_ms": 2900}]) == []
    # a hit that took its HP is no candidate at all
    s2 = CandidateScanner()
    scan(s2, sess, 1000, telemetry=[{"kind": "hp", "entity": TANK, "current": 50_000, "max": 50_000, "timestamp_ms": 1000}],
         actions=[{"kind": "effect", "target": TANK, "source": TANK, "skill": SHIELD, "effect": SHIELD * 10, "instance": 7,
                   "duration_ms": 3000, "timestamp_ms": 1000}])
    scan(s2, sess, 1500, events=[hit(1500, TANK, 8000)])
    assert scan(s2, sess, 1900, telemetry=[{"kind": "hp", "entity": TANK, "current": 42_000, "max": 50_000, "timestamp_ms": 1900}]) == []


def test_a_boss_cast_cut_short_after_a_party_effect_on_it_is_an_interrupt_candidate():
    s, sess = CandidateScanner(), FakeSession()
    t = 0
    for _ in range(3):                                          # three ordinary 2.0 s casts set the usual length
        scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": t}])
        scan(s, sess, t + 2000, actions=[{"kind": "cast_end", "actor": BOSS, "skill": SLAM, "seq": 1, "flag": 0, "timestamp_ms": t + 2000}])
        t += 10_000
    scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": t}])
    scan(s, sess, t + 300, actions=[{"kind": "effect", "target": BOSS, "source": DPS, "skill": 12345, "effect": 123450, "instance": 3,
                                     "duration_ms": 2000, "timestamp_ms": t + 300}])
    out = scan(s, sess, t + 600, actions=[{"kind": "cast_end", "actor": BOSS, "skill": SLAM, "seq": 1, "flag": 0, "timestamp_ms": t + 600}])
    assert [c["label"] for c in out] == ["interrupt"]
    assert "0.6 s" in out[0]["why"] and "2.0 s" in out[0]["why"] and out[0]["context"]["after"] == "Zapp"


def test_a_skill_that_hit_before_and_hits_nobody_now_is_a_miss_candidate_and_a_wide_hit_a_mechanic():
    s, sess = CandidateScanner(), FakeSession()
    t = 0
    for _ in range(2):
        scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": t}])
        scan(s, sess, t + 800, events=[hit(t + 800, TANK, 5000, SLAM)])
        t += 10_000
    scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": t}])
    out = scan(s, sess, t + 6000)                              # the window passed with no damage
    assert [c["label"] for c in out] == ["miss"] and "2 earlier casts" in out[0]["why"] and out[0]["context"]["target"] == "Tanka"
    t += 20_000
    scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": t}])
    scan(s, sess, t + 700, events=[hit(t + 700, p, 4000, SLAM) for p in (TANK, HEALER, DPS)])
    out = scan(s, sess, t + 6000)
    assert [c["label"] for c in out] == ["mechanic"] and out[0]["context"]["players_hit"] == 3


def test_a_hit_far_below_the_usual_is_a_mitigation_candidate_unless_it_was_a_parry():
    s, sess = CandidateScanner(), FakeSession()
    for i in range(4):
        assert scan(s, sess, 1000 * (i + 1), events=[hit(1000 * (i + 1), TANK, 10_000)]) == []
    assert scan(s, sess, 6000, events=[hit(6000, TANK, 9_000)]) == []                       # within the usual
    assert scan(s, sess, 7000, events=[hit(7000, TANK, 3_000, specials=frozenset({SpecialDamage.PARRY}))]) == []   # a decoded parry
    out = scan(s, sess, 8000, events=[hit(8000, TANK, 3_000)])
    assert [c["label"] for c in out] == ["mitigation"] and out[0]["context"]["usual"] == 10_000


def test_a_shield_block_or_endurance_is_neither_a_mitigation_candidate_nor_a_usual_hit():
    """0.2.407: the record says when the target blocked a hit with their shield or their Endurance halved it, as it
    says a parry: such a hit is a cut the meter reads, not one to ask about, and no measure of the usual hit."""
    s, sess = CandidateScanner(), FakeSession()
    for i in range(4):
        assert scan(s, sess, 1000 * (i + 1), events=[hit(1000 * (i + 1), TANK, 10_000)]) == []
    for i, flag in enumerate((SpecialDamage.SHIELD_BLOCK, SpecialDamage.ENDURANCE) * 2):
        t = 6000 + 1000 * i
        assert scan(s, sess, t, events=[hit(t, TANK, 4_600, specials=frozenset({flag}))]) == []
    out = scan(s, sess, 10_000, events=[hit(10_000, TANK, 3_000)])
    assert [c["label"] for c in out] == ["mitigation"] and out[0]["context"]["usual"] == 10_000


def test_steady_equal_heals_of_one_skill_are_a_heal_over_time_candidate_once():
    s, sess = CandidateScanner(), FakeSession()
    out = []
    for i in range(4):
        out += scan(s, sess, 2000 * i, events=[HealEvent(actor_id=HEALER, skill_code=HOT, amount=1200, timestamp_ms=2000 * i, target_id=DPS)])
    assert [c["label"] for c in out] == ["hot"] and out[0]["context"]["tick"] == 1200
    assert scan(s, sess, 9000, events=[HealEvent(actor_id=HEALER, skill_code=HOT, amount=1200, timestamp_ms=9000, target_id=DPS)]) == []


def test_candidates_are_capped_per_fight_and_per_capture():
    s, sess = CandidateScanner(per_fight=2, per_capture=3), FakeSession()
    out = []
    t = 0
    for i in range(6):                                          # six different skills hit the whole party
        skill = 1600100 + i
        scan(s, sess, t, actions=[{"kind": "cast", "actor": BOSS, "skill": skill, "seq": 1, "target": TANK, "timestamp_ms": t}])
        scan(s, sess, t + 500, events=[hit(t + 500, p, 3000, skill) for p in (TANK, HEALER, DPS, DPS2)])
        out += scan(s, sess, t + 6000)
        t += COOLDOWN_MS + 7000
    assert len(out) == 2                                        # the fight's cap


def test_runner_marks_candidates_and_decides_them_only_with_recording_enabled(monkeypatch):
    from aion2calc.app import meter_runner
    r = meter_runner.Runner()
    monkeypatch.setattr(r, "_record_packets_setting", lambda: False)
    assert r.marking_enabled() is False and r.recording_active() is False
    monkeypatch.setattr(r, "_record_packets_setting", lambda: True)
    assert r.marking_enabled() is True
    marks = r.mark("shield", "saw it", source="button")
    assert marks[-1]["kind"] == "mark" and marks[-1]["status"] == "confirmed" and marks[-1]["id"] == 1
    # a candidate the scanner raised, confirmed with another label, and one dismissed
    r.candidates = CandidateScanner()
    sess = FakeSession()
    r.session = sess
    engine = FakeEngine(actions=[{"kind": "cast", "actor": BOSS, "skill": SLAM, "seq": 1, "target": TANK, "timestamp_ms": 0}])
    r._scan_candidates(engine, [], 0)
    r._scan_candidates(FakeEngine(), [hit(700, p, 4000, SLAM) for p in (TANK, HEALER, DPS)], 700)
    r._scan_candidates(FakeEngine(), [], 6000)
    pending = [m for m in r.marks if m["kind"] == "candidate"]
    assert len(pending) == 1 and pending[0]["status"] == "pending" and pending[0]["label"] == "mechanic"
    decided = r.decide_mark(pending[0]["id"], True, label="other", note="the slam that hits the whole room")
    row = next(m for m in decided if m["id"] == pending[0]["id"])
    assert row["kind"] == "mark" and row["status"] == "confirmed" and row["label"] == "other" and row["source"] == "auto-confirmed"
    r.marks.append({"id": 99, "kind": "candidate", "status": "pending", "label": "miss", "at": "x", "t_ms": 0})
    assert next(m for m in r.decide_mark(99, False) if m["id"] == 99)["status"] == "dismissed"
    with pytest.raises(ValueError):
        r.decide_mark(12345, True)
    # Label the latest labels the latest ordinary mark, never a candidate
    r.marks.append({"id": 100, "kind": "candidate", "status": "pending", "label": "miss", "at": "x", "t_ms": 0})
    relabelled = r.relabel(-1, "interrupt", "it was the cast")
    assert next(m for m in relabelled if m["id"] == row["id"])["label"] == "interrupt"
    assert next(m for m in relabelled if m["id"] == 100)["label"] == "miss"
