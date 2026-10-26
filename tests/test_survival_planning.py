"""HP reserve and incoming-damage planning (aion2calc/opt/survival.py): the optimizer keeps enough flat
crystal-board HP for the incoming damage a player assumes, records from a fight or takes from a saved PvP
result. Every number it reports is that assumption worked through: no defence, heal, avoidance or
survival chance is inferred."""
import pytest

from aion2calc.kit.base import Build, ClassData
from aion2calc.opt import survival as SV

DEFIANCE, DEFIANCE_HEAL = 15240000, 15240030          # a Sorcerer active and one of its supporting effects
FIRE_MARK, SOUL_FREEZE = 15710000, 15130000           # a passive and a stigma


@pytest.fixture(scope="module")
def cd():
    return ClassData("sorcerer")


def hp_nodes(cd, board, count):
    return [nid for nid, (b, node) in cd.node_index.items() if b["name"] == board
            and any(s.get("stat") == "HPMax" for s in node.get("stats", []))][:count]


def build(cd, hp_node_count):
    return Build("sorcerer", daevanion=set(hp_nodes(cd, "Nezekan", hp_node_count)))


def test_only_the_four_crystal_boards_count_as_flat_hp(cd):
    nezekan, azphel = hp_nodes(cd, "Nezekan", 2), hp_nodes(cd, "Azphel", 1)
    assert azphel and SV.node_hp(cd, nezekan) == 200
    assert SV.node_hp(cd, nezekan + azphel + [1]) == 200          # Azphel's HP and unknown nodes are not counted


def test_pressure_minus_assumed_healing_peaks_where_the_deficit_is_largest():
    # 1000 DPS for 10 s, 400 HPS healing from 2 s to 6 s: the deficit only grows, slower while healed
    assert SV.pressure_deficit(1000, 10, 400, 2, 6) == (8400, 10)
    # healing beyond the pressure is not banked for later
    assert SV.pressure_deficit(1000, 10, 1500, 0, 5) == (5000, 10)
    # overlapping reductions: the strongest applies, they never add up or multiply
    windows = [{"start_s": 0, "end_s": 4, "reduction_pct": 50}, {"start_s": 2, "end_s": 6, "reduction_pct": 30}]
    assert SV.pressure_deficit(1000, 6, 0, 0, 0, windows) == (3400, 6)


def test_timed_hits_land_whole_and_healing_cannot_prepay_them():
    trace = SV.damage_trace({"version": 1, "duration_s": 10, "total": 3000, "events": [[2, 1000], [2, 500], [5, 1500]]})
    # same-time hits land together; healing before the first hit is wasted, not stored
    assert SV.timed_deficit(trace, 0, 10, 100, 0, 10) == (2700, 5)
    # reduction windows are half-open: the hits at its start are reduced, the hit at its end is not
    assert SV.timed_deficit(trace, 0, 10, 0, 0, 10, [{"start_s": 2, "end_s": 5, "reduction_pct": 50}]) == (2250, 5)


@pytest.mark.parametrize("trace, problem", [
    ({"version": 2, "duration_s": 10, "total": 1, "events": [[1, 1]]}, "unsupported timed damage trace"),
    ({"version": 1, "duration_s": 10, "total": 2, "events": [[5, 1], [1, 1]]}, "chronological"),
    ({"version": 1, "duration_s": 10, "total": 5, "events": [[1, 1]]}, "does not match its hits"),
    ({"version": 1, "duration_s": 10, "total": 1, "events": [[11, 1]]}, "Hit time must be a finite number from 0 to 10"),
    ({"version": 1, "duration_s": 10, "total": 1, "events": [[True, 1]]}, "Hit time"),
    ({"version": 1, "duration_s": 10, "total": 0, "events": []}, "1 to 50,000 complete hits"),
])
def test_a_damage_trace_is_checked_whole(trace, problem):
    with pytest.raises(ValueError, match=problem):
        SV.damage_trace(trace)


def test_the_heaviest_window_of_a_saved_trace_is_taken_and_scaled():
    trace = SV.damage_trace({"version": 1, "duration_s": 20, "total": 1300, "events": [[1, 100], [8, 500], [9, 500], [15, 200]]})
    start, window = SV.peak_trace_window(trace, 5, 0.5)
    assert start == 4 and window == {"version": 1, "duration_s": 5, "total": 500, "events": [[4, 250], [5, 250]]}


def test_without_options_nothing_is_reserved_and_by_default_the_current_crystal_hp_is_kept(cd):
    current = build(cd, 2)
    assert SV.prepare(cd, current, None) is None
    assert SV.prepare(cd, current, {"preserve_hp": False}) is None       # nothing asked for
    plan = SV.prepare(cd, current, {})
    assert plan["reference_node_hp"] == plan["minimum_node_hp"] == 200 and plan["opponents"] == []
    with pytest.raises(ValueError, match="Preserve HP must be true or false"):
        SV.prepare(cd, current, {"preserve_hp": "yes"})


def test_an_incoming_damage_scenario_sets_the_crystal_hp_floor(cd):
    slam = {"name": "Boss slam", "burst_damage": 6000, "pressure_dps": 1000, "window_s": 5, "healing_hps": 200,
            "reserve_hp": 500}
    plan = SV.prepare(cd, build(cd, 2), {"current_hp": 10000, "opponents": [slam]})
    row = plan["opponents"][0]
    # burst 6000 + (1000 - 200) x 5 s of pressure + a 500 HP reserve
    assert (row["peak_pressure_hp"], row["peak_pressure_at_s"], row["required_hp"]) == (4000, 5, 10500)
    assert row["source"] == "user_assumption" and row["healing_active_s"] == 5
    assert plan["minimum_node_hp"] == 700                     # 200 HP of nodes now + the 500 HP short of 10500
    worn = SV.assessment(cd, build(cd, 2), plan)
    assert worn["estimated_total_hp_proxy"] == 10000 and worn["worst_headroom_hp"] == -500
    assert not worn["meets_node_floor"] and not worn["opponents"][0]["meets_assumed_pressure"]
    optimized = SV.assessment(cd, build(cd, 7), plan)
    assert optimized["meets_node_floor"] and optimized["opponents"][0]["headroom_hp"] == 0
    assert optimized["binding_opponents"] == ["Boss slam"]
    with pytest.raises(ValueError, match="Enter your current maximum HP"):
        SV.prepare(cd, build(cd, 2), {"opponents": [slam]})
    with pytest.raises(ValueError, match="exceeds the catalog's total"):
        SV.prepare(cd, build(cd, 2), {"current_hp": 1, "opponents": [{**slam, "burst_damage": 1e8}]})


def defiance(delay, **extra):
    return {"name": "Defiance", "kind": "defensive", "delay_s": delay, "duration_s": 4, "reduction_pct": 50,
            "skill_id": DEFIANCE, "cooldown_s": 12, **extra}


def test_reduction_windows_link_real_skills_and_check_only_the_assumed_cooldown(cd):
    burst = {"name": "Burst", "pressure_dps": 1000, "window_s": 20,
             "reductions": [defiance(0, effect_id=DEFIANCE_HEAL, min_trained=5), defiance(12)]}
    row = SV.prepare(cd, build(cd, 0), {"current_hp": 50000, "opponents": [burst]})["opponents"][0]
    assert row["reductions"][0]["skill_requirement"] == {
        "id": DEFIANCE, "name": "Defiance", "kind": "active", "minimum": 5, "effect_id": DEFIANCE_HEAL,
        "effect": cd.skills[DEFIANCE]["specs"][2]["text"]}
    assert row["cooldown_checks"] == [{"skill_id": DEFIANCE, "skill": "Defiance", "activation_starts_s": [0, 12],
                                       "cooldown_s": 12, "shortest_reuse_gap_s": 12,
                                       "status": "assumed_spacing_satisfied", "mixed_assumptions": False}]
    # halved pressure for 8 of the 20 seconds
    assert (row["unprotected_required_hp"], row["required_hp"], row["assumed_requirement_reduction_hp"]) == (20001, 16001, 4000)
    early = {**burst, "reductions": [defiance(0), defiance(10)]}
    with pytest.raises(ValueError, match="reuse the skill after 10s, before the assumed 12s cooldown"):
        SV.prepare(cd, build(cd, 0), {"current_hp": 50000, "opponents": [early]})


def test_differing_cooldown_assumptions_use_the_largest_and_idle_windows_are_not_uses(cd):
    windows = SV.reduction_windows(cd, {"reductions": [defiance(0), defiance(30, cooldown_s=20),
                                                      defiance(5, reduction_pct=0, skill_id=SOUL_FREEZE, cooldown_s=None)]}, 60)
    defiance_check, soul_freeze = SV.cooldown_checks(windows)
    assert defiance_check["cooldown_s"] == 20 and defiance_check["mixed_assumptions"]
    assert soul_freeze == {"skill_id": SOUL_FREEZE, "skill": "Soul Freeze", "activation_starts_s": [], "cooldown_s": None,
                           "shortest_reuse_gap_s": None, "status": "no_active_windows", "mixed_assumptions": False}


@pytest.mark.parametrize("window, problem", [
    ({"skill_id": 1}, "Link a known skill from your class"),
    ({"effect_id": DEFIANCE_HEAL}, "Choose a skill before linking its supporting effect"),
    ({"skill_id": FIRE_MARK, "effect_id": DEFIANCE_HEAL}, "Link a supporting effect belonging to the selected active skill"),
    ({"skill_id": DEFIANCE, "min_trained": 11}, "trained minimum must fit its purchasable range"),
    ({"cooldown_s": 10}, "Link a skill before entering its cooldown"),
    ({"kind": "magic"}, "Choose defensive, control or movement"),
    ({"reduction_pct": 101}, "Assumed pressure reduction percent"),
])
def test_a_reduction_window_that_cannot_be_honoured_is_refused(cd, window, problem):
    with pytest.raises(ValueError, match=problem):
        SV.reduction_windows(cd, {"reductions": [window]}, 10)


def test_at_most_eight_windows_and_eight_scenarios(cd):
    with pytest.raises(ValueError, match="at most eight pressure-reduction windows"):
        SV.reduction_windows(cd, {"reductions": [{}] * 9}, 10)
    with pytest.raises(ValueError, match="at most eight incoming-damage scenarios"):
        SV.prepare(cd, build(cd, 0), {"current_hp": 1000, "opponents": [{}] * 9})
    with pytest.raises(ValueError, match="at most eight outgoing action-time windows"):
        SV.prepare(cd, build(cd, 0), {"action_windows": [{}] * 9})


def scenario():
    from aion2calc.model.character import load_loadout
    from aion2calc.scenarios import SCENARIOS
    return SCENARIOS["boss"](load_loadout("sorcerer_l45_global_median"))


def test_action_windows_pause_the_rotation_and_may_reserve_a_cooldown(cd):
    plan = SV.prepare(cd, build(cd, 0), {"preserve_hp": False, "action_windows": [
        {"name": "Dodge the wave", "start_s": 10, "duration_s": 3},
        {"name": "Save Defiance", "start_s": 60, "duration_s": 1, "skill_id": DEFIANCE, "cooldown_s": 30,
         "reserve_cooldown": True}]})
    dodge, saved = plan["action_windows"]
    assert dodge["end_s"] == 13 and dodge["skill_requirement"] is None and not dodge["reserve_cooldown"]
    assert saved["skill_requirement"]["name"] == "Defiance" and saved["reserve_cooldown"]
    timed = SV.with_action_timing(scenario(), plan)
    assert timed.config.action_blocks == ((10, 13), (60, 61))
    assert timed.config.tactical_uses == ((DEFIANCE, 60, 30),)
    case = SV.action_timing_summary(plan, {"boss": timed})["cases"]["boss"]
    assert case["paused_s"] == 4 and case["cooldown_checks"][0]["status"] == "assumed_spacing_satisfied"
    assert SV.with_action_timing(scenario(), None).config.action_blocks == ()
    assert SV.action_timing_summary(None, {}) is None
    whole = SV.prepare(cd, build(cd, 0), {"action_windows": [{"start_s": 0, "duration_s": 120}, {"start_s": 120, "duration_s": 60}]})
    with pytest.raises(ValueError, match="cover the entire damage scenario"):
        SV.with_action_timing(scenario(), whole)


@pytest.mark.parametrize("window, problem", [
    ({"skill_id": FIRE_MARK}, "need an active skill or stigma, not a passive"),
    ({"reserve_cooldown": "yes"}, "must be true or false"),
    ({"skill_id": DEFIANCE, "reserve_cooldown": True}, "enter an assumed effective cooldown before reserving"),
    ({"duration_s": 121}, "Action-time duration"),
])
def test_an_action_window_that_cannot_be_honoured_is_refused(cd, window, problem):
    with pytest.raises(ValueError, match=problem):
        SV.prepare_action_windows(cd, {"action_windows": [{"start_s": 5, "duration_s": 2, **window}]})


def fight_log(deaths=True):
    hits = [(1, 500), (2, 700), (3, 300), (4, 900), (5, 900)]
    events = [{"kind": "damage", "t": t, "source": "boss", "target": "tank", "amount": amount} for t, amount in hits]
    events.append({"kind": "damage", "t": 2, "source": "tank", "target": "boss", "amount": 99999})   # dealt, not taken
    if deaths:
        events.append({"kind": "death", "t": 3.5, "target": "tank"})
    return {"format": "a2log", "version": 1, "meta": {"title": "Practice pull"},
            "players": [{"id": "tank", "name": "Tank", "class": "templar"}, {"id": "heal", "name": "Healer", "class": "cleric"}],
            "segments": [{"label": "Boss", "duration": 10, "hits": [], "entities": [{"id": "boss", "name": "Boss"}],
                          "events": events}]}


def test_a_recorded_fight_gives_the_players_worst_window_and_a_death_starts_a_new_life(cd):
    assert SV.recorded_pressure(fight_log()) == {"encounters": [
        {"index": 0, "label": "Boss", "mode": "pve", "targets": [{"id": "tank", "name": "Tank"}]}]}   # no damage to the healer
    row = SV.recorded_pressure(fight_log(), 0, "tank", 2)["scenario"]
    assert row["name"] == "Tank · Boss" and row["burst_damage"] == 1800 and row["pressure_dps"] == 0
    evidence = row["recorded_evidence"]
    assert (evidence["start_s"], evidence["end_s"], evidence["largest_hit"], evidence["damage_events"]) == (4, 5, 900, 5)
    # without the death, the 2 s windows (both ends included) run across it
    assert SV.recorded_pressure(fight_log(deaths=False), 0, "tank", 2)["scenario"]["burst_damage"] == 2100
    plan = SV.prepare(cd, build(cd, 0), {"current_hp": 5000, "preserve_hp": False, "opponents": [row]})
    assert plan["opponents"][0]["required_hp"] == 1801
    assert plan["opponents"][0]["recorded_evidence"]["recipient"] == "Tank"     # kept as text, for the report


@pytest.mark.parametrize("segment, target, problem", [
    (1, "tank", "Choose an encounter"), (True, "tank", "Choose an encounter"),
    (0, "boss", "Choose a recorded player recipient"), (0, "heal", "No damage with this player as recipient"),
])
def test_a_recorded_window_needs_a_real_encounter_and_player(segment, target, problem):
    with pytest.raises(ValueError, match=problem):
        SV.recorded_pressure(fight_log(), segment, target, 2)


def pvp_result(kind="optimize-class", scenario="pvp", trace=True):
    hits = [[t, 5500.0 if t in (10, 11) else 500.0] for t in range(20)]       # 20000 damage in 20 s: 1000 DPS
    result = {"skills": {}, "class": "assassin", "scenario": scenario, "dps": {"pvp": 1000.0, "pvp_burst": 2000.0},
              "objective": {"durations": {"pvp": 20, "pvp_burst": 10}}, "model_note": "Modeled duel"}
    if trace:
        result["damage_traces"] = {"pvp": {"version": 1, "duration_s": 20, "total": 20000, "events": hits}}
    return {"format": "a2result", "version": 1, "kind": kind, "title": "Assassin duel", "created": 1.0e9, "result": result}


def test_a_saved_pvp_result_becomes_an_average_or_timed_pressure_assumption(cd):
    average = SV.opponent_pressure(pvp_result(), "pvp", 0.5, 5)["scenario"]
    assert average["pressure_dps"] == 500 and average["window_s"] == 5 and "damage_trace" not in average
    benchmark = average["opponent_benchmark"]
    assert (benchmark["class"], benchmark["modeled_dps"], benchmark["source_duration_s"], benchmark["duration_source"]) == (
        "assassin", 1000, 20, "saved objective")
    timed = SV.opponent_pressure(pvp_result(), "pvp", 0.5, 5, "timed")["scenario"]
    # the heaviest 5 s of the saved fight (both ends included), at half the damage
    assert timed["pressure_dps"] == 0 and timed["opponent_benchmark"]["source_start_s"] == 6
    assert timed["damage_trace"]["events"] == [[0, 250], [1, 250], [2, 250], [3, 250], [4, 2750], [5, 2750]]
    plan = SV.prepare(cd, build(cd, 0), {"current_hp": 9000, "preserve_hp": False, "opponents": [timed]})
    assert plan["opponents"][0]["required_hp"] == 6501
    legacy = pvp_result(trace=False)
    del legacy["result"]["objective"]
    assert SV.opponent_pressure(legacy, "pvp", 1, 5)["scenario"]["opponent_benchmark"]["duration_source"] == "legacy scenario default"


def test_a_saved_result_that_is_not_a_consistent_pvp_benchmark_is_refused():
    advice = {**pvp_result(kind="advice"), "result": {k: {} for k in ("character", "doll", "rotation", "genus", "calibration")}}
    with pytest.raises(ValueError, match="optimized PvP result, not advice or a combat log"):
        SV.opponent_pressure(advice, "pvp", 1, 5)
    with pytest.raises(ValueError, match="not an optimized PvP build"):
        SV.opponent_pressure(pvp_result(scenario="boss"), "pvp", 1, 5)
    with pytest.raises(ValueError, match="Assumed incoming damage scale"):
        SV.opponent_pressure(pvp_result(), "pvp", 11, 5)
    with pytest.raises(ValueError, match="cannot exceed the source benchmark duration"):
        SV.opponent_pressure(pvp_result(), "pvp", 1, 25)
    with pytest.raises(ValueError, match="Choose average or timed"):
        SV.opponent_pressure(pvp_result(), "pvp", 1, 5, "guess")
    skewed = pvp_result()
    skewed["result"]["dps"]["pvp"] = 900.0
    with pytest.raises(ValueError, match="Trace damage does not match the saved DPS estimate"):
        SV.opponent_pressure(skewed, "pvp", 1, 5, "timed")
    with pytest.raises(ValueError, match="re-optimize this opponent"):
        SV.opponent_pressure(pvp_result(trace=False), "pvp", 1, 5, "timed")
