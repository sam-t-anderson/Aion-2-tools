"""A dungeon clear's "entry" is its first combat after the zone load the recording captured -- never
a later in-instance reload -- and a fight is charged only with the capture loss that can have
touched it (its own window, or this archive part's share), not the whole session's counters.

The reported case (Ferocious Horn Den, archive part 2): the run's entry load fell in the previous
part during the pause before it, the boss-room teleport then re-stamped the run's start onto the
final-boss pull (elapsed time unusable), and a TCP reassembly restart from an hour earlier -- a
lifetime counter repeated on every part -- unranked every fight of the part."""
import json

from aion2calc.combat import a2log
from aion2calc.combat.quality import assess
from aion2calc.combat.runs import summarize as summarize_runs
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

ROSTER = {"Me": {"serverId": 2102, "dbid": 11, "job": "Gladiator", "combatPower": 100_000},
          "Ally": {"serverId": 2102, "dbid": 12, "job": "Cleric", "combatPower": 90_000}}


def _engine(local=5001, ally=5002, instance=600022):
    e = MeterEngine()
    e.names = {local: "Me", ally: "Ally"}
    e.known_players = {local, ally}
    e.roster = dict(ROSTER)
    e.roster_complete = True
    e.local_player_id = local
    e.local_identity_from_game = True
    e.map_id = e.dungeon_id = instance
    e.last_zone_reset_ms = None
    return e


def _hit(actor, t, target=9001):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=11010000, damage=500, timestamp_ms=t)


def _reload(e, t, local=6001, ally=6002):
    """The decoder on a revive / in-instance teleport: a zone load back into the same instance map."""
    e._reset_zone(t)
    e.names = {local: "Me", ally: "Ally"}
    e.known_players = {local, ally}
    e.local_player_id = local
    e.local_identity_from_game = True
    e._note_map(e._left_instance[0])


def _fight(s, e, actors, t0, target=9001, hits=6):
    for i in range(hits):
        s.observe(e, [_hit(actors[0], t0 + i * 1000, target), _hit(actors[1], t0 + i * 1000 + 100, target)],
                  timestamp_ms=t0 + i * 1000)


def test_a_reload_later_in_the_run_never_stamps_the_runs_start():
    # The capture joined this run in progress (no zone load seen before its first combat).
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)
    run = s.run
    assert not s.runs[run].get("start_observed") and s.runs[run].get("started_at") is None
    _reload(e, t0 + 60_000)                       # the boss-room teleport: a zone load, same instance
    s.observe(e, [], timestamp_ms=t0 + 61_000)
    _fight(s, e, (6001, 6002), t0 + 70_000, target=9002)
    assert s.run == run                           # the run continues (a reload, not a re-entry) ...
    assert not s.runs[run].get("start_observed")  # ... and the reload is still not its entry
    assert s.runs[run].get("started_at") is None


def test_an_observed_entry_keeps_its_timestamp_through_a_reload():
    s, e = CombatSession(), _engine()
    s.pvp = False
    s._zone_reset_seen = True                     # the entry's zone load was captured
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)
    run = s.run
    assert s.runs[run]["start_observed"] and s.runs[run]["started_at"] == t0
    _reload(e, t0 + 400_000)
    s.observe(e, [], timestamp_ms=t0 + 401_000)
    _fight(s, e, (6001, 6002), t0 + 420_000, target=9002)   # the final boss, seven minutes in
    assert s.run == run and s.runs[run]["started_at"] == t0  # the old bug: re-stamped to t0 + 420 s


def test_a_continuation_keeps_a_zone_load_captured_after_the_last_combat():
    s, e = CombatSession(), _engine()
    s.pvp = False
    s._zone_reset_seen = True
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)
    # The party leaves the instance after the clear; the storage rollover fires during the pause.
    e._reset_zone(t0 + 90_000)
    e.names, e.known_players, e.local_player_id = {7001: "Me", 7002: "Ally"}, {7001, 7002}, 7001
    e.map_id, e.dungeon_id = 600023, 600023       # the next dungeon
    s.observe(e, [], timestamp_ms=t0 + 91_000)
    part = s.continuation()
    assert part._zone_reset_seen is True          # the load is pending: the next run's entry evidence
    assert part.capture_losses == []
    _fight(part, e, (7001, 7002), t0 + 120_000, target=9003)
    new_run = part.runs[part.run]
    assert part.run != s.run and new_run["start_observed"] and new_run["started_at"] == t0 + 120_000


def test_a_continuation_cut_mid_run_does_not_claim_the_open_runs_entry():
    s, e = CombatSession(), _engine()
    s.pvp = False
    s._zone_reset_seen = True
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)                # combat after the only zone load ...
    part = s.continuation()                       # ... then a hard rollover mid-run
    assert part._zone_reset_seen is False
    assert part.runs[part.run]["start_observed"] is False and part.runs[part.run]["recorded_entry"] == t0
    _reload(e, t0 + 60_000)
    part.observe(e, [], timestamp_ms=t0 + 61_000)
    _fight(part, e, (6001, 6002), t0 + 70_000, target=9002)
    assert part.runs[part.run]["start_observed"] is False   # combat_seen carried: no re-stamp


def test_losses_are_charged_to_the_fight_they_happened_in():
    s, e = CombatSession(), _engine()
    s.pvp = False
    s.capture_evidence.update(transport_monitored=True, tcp_discarded_payloads=203)   # the lifetime total
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)                                   # fight 1: t0 .. t0+5.1 s
    s.note_capture_loss("tcp_discarded_payloads", 200, t0 - 1_800_000)   # half an hour earlier: not these fights'
    _fight(s, e, (5001, 5002), t0 + 300_000, target=9002)            # fight 2 after a long lull
    s.note_capture_loss("tcp_discarded_payloads", 3, t0 + 302_000)   # a TCP restart inside fight 2
    doc = s.to_a2log("party")
    assert doc["meta"]["capture_quality"]["loss_attribution"] == "segment"
    first, second = doc["segments"][0], doc["segments"][1]
    assert first["capture_loss"] == {} and second["capture_loss"] == {"tcp_discarded_payloads": 3}
    assert "capture_loss" not in assess(doc, first)["reasons"]       # the old bug: 203 > 0 unranked both
    assert "capture_loss" in assess(doc, second)["reasons"]
    assert assess(doc, first)["loss_attribution"] == "segment"
    # The stamps survive the validator's round trip (the log server re-validates uploads).
    again = a2log.validate(json.loads(json.dumps(doc)))
    assert again["segments"][0]["capture_loss"] == {} and again["segments"][1]["capture_loss"] == {"tcp_discarded_payloads": 3}


def _reasons(capture, seg=None):
    cap = {"decoder": "a2tools-python-v1", "app_version": "0.2.292", "transport_monitored": True, **capture}
    doc = {"meta": {"capture_scope": "party", "capture_quality": cap}, "players": [], "segments": []}
    segment = {"duration": 60.0, "hits": [{"player": "p", "damage": 100, "t": 1.0}]}
    segment.update(seg or {})
    return assess(doc, segment)["reasons"]


def test_an_archive_part_is_charged_only_with_its_own_share_of_lifetime_counters():
    # Part 2 repeats the capture's running totals; its baseline says 200 of them predate the part.
    assert "capture_loss" not in _reasons({"tcp_discarded_payloads": 200, "part_baseline": {"tcp_discarded_payloads": 200}})
    assert "capture_loss" in _reasons({"tcp_discarded_payloads": 201, "part_baseline": {"tcp_discarded_payloads": 200}})
    assert "capture_loss" in _reasons({"tcp_discarded_payloads": 1})                    # no baseline: as before
    # The packet-drop budget is likewise the part's own: 600 drops over 20k packets in the capture's
    # lifetime, of which 580 drops and 19k packets came before this part.
    assert "capture_loss" in _reasons({"pcap_dropped": 600, "pcap_received": 20_000})
    assert "capture_loss" not in _reasons({"pcap_dropped": 600, "pcap_received": 20_000,
                                           "part_baseline": {"pcap_dropped": 580, "pcap_received": 19_000}})


def test_routine_validator_filtering_is_not_capture_loss():
    # Older documents: one whole-document count that also covered routine filtering.
    assert "capture_loss" not in _reasons({"validation_discarded": 8})
    assert "capture_loss" in _reasons({"validation_discarded": 101})
    # Current documents say per fight what was a size-cap overflow (evidence dropped) and what was filtered.
    assert "capture_loss" not in _reasons({"validation_discarded": 500}, seg={"validation": {"capped": 0, "filtered": 40}})
    assert "capture_loss" in _reasons({}, seg={"validation": {"capped": 1, "filtered": 0}})


def test_the_validator_accounts_capped_and_filtered_entries_apart():
    doc = {"format": "a2log", "version": 1, "meta": {"capture_scope": "party", "capture_quality": {
               "decoder": "a2tools-python-v1", "app_version": "0.2.292", "transport_monitored": True,
               "loss_attribution": "segment", "part_baseline": {"tcp_discarded_payloads": 200, "bogus": 5}}},
           "players": [{"id": "p1", "name": "Me", "class": "gladiator", "server": "2102"}],
           "segments": [{"duration": 10.0, "hits": [{"t": 1.0, "player": "p1", "damage": 10.0, "target": "b"}],
                         "entities": [{"id": "b", "name": "Boss", "kind": "enemy", "is_boss": True, "mob_code": 2343616}],
                         "health": [{"t": 0.0, "entity": "b", "current": 100.0, "max": 100.0},
                                    {"t": 12.5, "entity": "b", "current": 50.0, "max": 100.0},      # past the segment: filtered
                                    {"t": 2.0, "entity": "ghost", "current": 1.0, "max": 1.0}],     # unreferenced: filtered
                         "capture_loss": {"tcp_discarded_payloads": 2, "pcap_dropped": 9, "x": True}}]}
    out = a2log.validate(doc)
    seg = out["segments"][0]
    assert seg["validation"] == {"capped": 0, "filtered": 2}
    assert seg["capture_loss"] == {"tcp_discarded_payloads": 2}                 # only timed loss counters
    quality = out["meta"]["capture_quality"]
    assert quality["validation_filtered"] == 2 and "validation_discarded" not in quality
    assert quality["loss_attribution"] == "segment" and quality["part_baseline"] == {"tcp_discarded_payloads": 200}
    # Idempotent across the upload round trip: nothing more is filtered, counts are kept.
    again = a2log.validate(json.loads(json.dumps(out)))
    assert again["segments"][0]["validation"] == {"capped": 0, "filtered": 2}
    assert again["meta"]["capture_quality"]["validation_filtered"] == 2


def test_run_analysis_uses_the_same_full_health_rule_as_the_ranking_gate():
    doc = {"format": "a2log", "version": 1, "meta": {"capture_scope": "party", "game_patch": "version:product:1.0.21.0",
               "difficulty": "normal", "capture_quality": {"decoder": "a2tools-python-v1", "app_version": "0.2.292", "transport_monitored": True}},
           "players": [{"id": "p1", "name": "Me", "class": "gladiator", "server": "2102"}],
           "segments": [{"duration": 224.0, "killed": True, "encounter_type": "expedition", "instance_id": 600092, "map_id": 600092,
                         "run_id": "7", "run_start_observed": True, "run_complete": True, "run_end_reason": "configured_final_boss_death",
                         "start": "2026-10-16T06:53:06.028000+00:00", "run_started_at": "2026-10-16T06:46:04.482000+00:00",
                         "run_ended_at": "2026-10-16T06:56:50.038000+00:00", "party_members": ["p1"], "party_roster_complete": True,
                         "hits": [{"t": 0.0, "player": "p1", "damage": 10.0, "target": "b"}, {"t": 223.0, "player": "p1", "damage": 10.0, "target": "b"}],
                         "entities": [{"id": "b", "name": "Ferocious Horn Nuakum", "kind": "enemy", "is_boss": True, "mob_code": 2300910}],
                         "events": [{"kind": "death", "t": 224.0, "target": "b"}],
                         "health": [{"t": 0.0, "entity": "b", "current": 15_496_590.0, "max": 15_504_000.0},   # 99.95% as the opening hit lands
                                    {"t": 224.0, "entity": "b", "current": 0.0, "max": 15_504_000.0}]}]}
    out = a2log.validate(doc)
    run = summarize_runs(out)["runs"][0]
    assert run["attempts"][0]["start_observed"] is True
    assert run["elapsed_seconds"] == 645.556 or abs(run["elapsed_seconds"] - 645.556) < 0.01


def test_the_runner_dates_a_tcp_restarts_loss(monkeypatch, tmp_path):
    from aion2calc.app import meter_runner as MR
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    r = MR.Runner()
    r.session = CombatSession()
    r.diagnostics = {}
    r._capture_loss_baseline = {k: 0 for k in MR.CAPTURE_COUNTERS}
    r._loss_seen = {}
    r._record_capture_stats({"tcp_discarded_payloads": 0, "tcp_unresolved_flows": 0})
    assert r.session.capture_losses == []
    r._record_capture_stats({"tcp_discarded_payloads": 200, "tcp_unresolved_flows": 0})    # the restart's report
    r._record_capture_stats({"tcp_discarded_payloads": 200, "tcp_unresolved_flows": 0})    # a periodic repeat: no new loss
    assert [(k, n) for _, k, n in r.session.capture_losses] == [("tcp_discarded_payloads", 200)]
    assert r.session.capture_evidence["tcp_discarded_payloads"] == 200


def test_a_zone_load_decoded_with_the_runs_first_damage_still_counts_as_its_entry():
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    e.last_zone_reset_ms = t0 - 5_000                 # the entry load, decoded in the same batch as the first hit
    s.observe(e, [_hit(5001, t0), _hit(5002, t0 + 100)], timestamp_ms=t0)
    run = s.runs[s.run]
    assert run["start_observed"] and run["started_at"] == t0 and run["combat_seen"]
    _fight(s, e, (5001, 5002), t0 + 1000)
    assert s.runs[s.run]["started_at"] == t0


KRAO_CAVE, BERK = 600001, 2300171


def test_the_dead_final_boss_still_ticking_on_a_player_opens_no_run():
    # Ultimate Berk (Krao Cave, archive part 4): the final boss's death closed the run and the due
    # storage rollover fired; its damage-over-time still ticking on a player then opened a run of
    # its own in the new part, with no entry seen -- a "partial capture" holding no damage.
    s, e = CombatSession(), _engine(instance=KRAO_CAVE)
    s.pvp = False
    s._zone_reset_seen = True
    e.spawn_info = {9001: {"mobCode": BERK}}
    t0 = 1_000_000
    _fight(s, e, (5001, 5002), t0)
    e.telemetry = [{"entity": 9001, "kind": "death", "timestamp_ms": t0 + 6_000}]
    s.observe(e, [], timestamp_ms=t0 + 6_000)
    e.telemetry = []
    run = s.run
    assert s.runs[run]["end_reason"] == "configured_final_boss_death"
    part = s.continuation()
    for i in range(5):                            # the corpse's DoT on a player, every two seconds
        t = t0 + 8_000 + i * 2_000
        part.observe(e, [DamageEvent(actor_id=9001, target_id=5001, skill_code=1200015, damage=399,
                                     timestamp_ms=t)], timestamp_ms=t)
    assert part.run == run and part.run_closed
    assert not any(seg.get("partial_capture") for seg in part.to_a2log("party", "Part 2")["segments"])
    part.observe(e, [_hit(5001, t0 + 30_000, target=9002)], timestamp_ms=t0 + 30_000)
    assert part.run == run + 1                    # a new fight in the instance still opens the next run
