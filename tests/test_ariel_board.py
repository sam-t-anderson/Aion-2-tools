"""The Ariel Daevanion board (0.2.381): the level-45 PvE board, paid with a crystal of its own (Daevanion Crystal: Ariel)
as Azphel's PvP board is. Its damage stats count in the model, its points are a budget of their own through the
optimizer, the app and the totals shared with the server, and community comparisons stay on the crystal boards."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import aion2calc
from aion2calc.kit.base import ARIEL, CRYSTAL_BOARDS, Build, ClassData
from aion2calc.scenarios import boss, typical_build

CLASSES = ("gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter")


def board(cd, name):
    return next(b for b in cd.boards if b["name"] == name)


def connected_nodes(cd, name, count):
    """``count`` nodes of a board in the order a walk from its centre finds them: connected by construction."""
    b = board(cd, name)
    pos = {(n["row"], n["col"]): n for n in b["nodes"]}
    start = next(n for n in b["nodes"] if n["type"] == "Start")
    order, seen, queue = [], {start["id"]}, [start]
    while queue and len(order) < count:
        n = queue.pop(0)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = pos.get((n["row"] + dr, n["col"] + dc))
            if m and m["id"] not in seen:
                seen.add(m["id"])
                order.append(m["id"])
                queue.append(m)
    return set(order[:count])


def cost(cd, nodes):
    return sum(cd.node_index[n][1]["cost"] for n in nodes)


@pytest.mark.parametrize("cls", CLASSES)
def test_every_class_has_the_ariel_board(cls):
    """Board x5 between Triniel and Azphel, opening at level 45: 152 stat nodes, no skill node, 232 points."""
    cd = ClassData(cls)
    names = [b["name"] for b in cd.boards]
    assert names == ["Nezekan", "Zikel", "Vaizel", "Triniel", ARIEL, "Azphel"]
    b = board(cd, ARIEL)
    assert b["id"] % 10 == 5 and b["needLevel"] == 45
    nodes = [n for n in b["nodes"] if n["type"] != "Start"]
    assert len(nodes) == 152 and cost(cd, {n["id"] for n in nodes}) == 232
    assert not any(n.get("skillId") for n in nodes)
    assert all(s["stat"] in cd.raw["stat_labels"] for n in nodes for s in n["stats"])


def test_the_ariel_boards_damage_stats_count():
    """The whole board gives PvE Damage Boost +6 %, Boss Damage Boost +4 %, PvE and Boss Attack +72 and Critical Hit +40
    (with Critical Hit Resist, HP and MP), and PvE Accuracy +120, which counts against a boss's Block (0.2.386); its PvE
    and Boss Defense, Damage Tolerance and Evasion change nothing the model simulates and are not mapped."""
    from aion2calc.model.character import daevanion_to_stats
    from aion2calc.run import simulate
    cd = ClassData("sorcerer")
    full = {n["id"] for n in board(cd, ARIEL)["nodes"] if n["type"] != "Start"}
    assert daevanion_to_stats(cd.daevanion_stats(full)) == pytest.approx(
        {"amp_pve": 0.06, "amp_boss": 0.04, "pve_atk": 72, "boss_atk": 72, "crit": 40, "crit_resist": 40,
         "hp": 400, "mp_max": 200, "pve_accuracy": 120})
    b = typical_build("sorcerer")
    with_board = b.copy()
    with_board.daevanion |= full
    scen = boss("sorcerer_l45_global_median")
    assert simulate(with_board, scen).dps > 1.05 * simulate(b, scen).dps


def test_daevanion_points_are_the_crystal_boards_and_ariel_its_own():
    """``daevanion_cost`` is the Daevanion Crystal of the four crystal boards; Ariel's and Azphel's take their own."""
    cd = ClassData("gladiator")
    crystal, ariel, azphel = (connected_nodes(cd, name, 3) for name in ("Nezekan", ARIEL, "Azphel"))
    b = Build("gladiator", daevanion=crystal | ariel | azphel)
    assert b.daevanion_cost(cd) == cost(cd, crystal)
    assert b.ariel_cost(cd) == cost(cd, ariel) and b.board_cost(cd, "Azphel") == cost(cd, azphel)
    assert any(e.startswith("Ariel cost") for e in b.validate(cd, ariel_budget=0))
    assert not any(e.startswith("Ariel cost") for e in b.validate(cd, ariel_budget=cost(cd, ariel)))


def test_ariel_nodes_are_worth_their_pve_weights_and_nothing_in_pvp():
    """Boss Damage Boost and Boss Attack share PvE Damage Boost's and PvE Attack's buckets against a boss."""
    from aion2calc.opt.statweights import node_values
    cd = ClassData("sorcerer")
    nodes = [n for n in board(cd, ARIEL)["nodes"] if n["type"] != "Start"]
    pve = node_values(cd, [{"stat": "amp_pve", "per_unit": 100.0}, {"stat": "pve_atk", "per_unit": 2.0}])

    def only(stat):
        return next(n["id"] for n in nodes if [s["stat"] for s in n["stats"]] == [stat])
    assert pve[only("PvEAmplifyDamage")] == pytest.approx(100.0 * 0.015)
    assert pve[only("BossNpcAmplifyDamage")] == pytest.approx(100.0 * 0.01)
    assert pve[only("BossNpcAddDamage")] == pytest.approx(2.0 * 3)
    assert only("PvEAccuracy") not in pve and only("BossNpcDefense") not in pve
    pvp = node_values(cd, [{"stat": "amp_pvp", "per_unit": 100.0}, {"stat": "pvp_atk", "per_unit": 2.0}])
    assert not any(n["id"] in pvp for n in nodes)


def test_the_optimizer_places_the_ariel_budget_on_its_own_board(monkeypatch):
    """With an Ariel budget the Ariel board is solved on that budget alone, connected from its centre; without one a
    build's Ariel nodes stay as they are; nodes on boards the search does not allocate (Azphel's) are kept, where the
    search used to drop every node off the crystal boards."""
    from aion2calc.opt import daevanion as dv, pipeline
    from aion2calc.opt.pipeline import Optimizer
    from aion2calc.opt.statweights import node_values
    monkeypatch.setattr(pipeline, "ARIEL_SOLVER_TIME_LIMIT", 5)
    cd = ClassData("sorcerer")
    nv = node_values(cd, [{"stat": "amp_pve", "per_unit": 100.0}, {"stat": "pve_atk", "per_unit": 1.0},
                          {"stat": "crit", "per_unit": 0.5}])
    scen = boss("sorcerer_l45_global_median")
    crystal, azphel, mine = connected_nodes(cd, "Nezekan", 2), connected_nodes(cd, "Azphel", 2), connected_nodes(cd, ARIEL, 4)
    opt = Optimizer("sorcerer", scen, verbose=False, ariel_budget=60)
    kept = opt._other_boards(crystal | azphel | mine, nv)
    placed = {n for n in kept if cd.node_index[n][0]["name"] == ARIEL}
    assert not kept & crystal and azphel <= kept                      # the crystal boards are the main program's
    assert 50 <= cost(cd, placed) <= 60 and dv.connected(cd, placed)
    assert sum(nv.get(n, 0.0) for n in placed) > sum(nv.get(n, 0.0) for n in mine)
    unbudgeted = Optimizer("sorcerer", scen, verbose=False)
    assert unbudgeted._other_boards(crystal | azphel | mine, nv) == azphel | mine
    assert Optimizer("sorcerer", scen, verbose=False, ariel_budget=0)._other_boards(mine | azphel, nv) == azphel
    assert not Optimizer("sorcerer", scen, verbose=False, ariel_budget=60, level=40).ariel_open
    with pytest.raises(ValueError):
        Optimizer("sorcerer", scen, verbose=False, ariel_budget=-1)


def test_the_board_view_counts_each_crystal_on_its_own():
    from aion2calc.app.views import daevanion_view
    cd = ClassData("sorcerer")
    crystal, mine = connected_nodes(cd, "Nezekan", 3), connected_nodes(cd, ARIEL, 6)
    v = daevanion_view(cd, crystal | mine, 360, 120)
    assert v["used"] == cost(cd, crystal) and v["budget"] == 360
    assert v["ariel_used"] == cost(cd, mine) and v["ariel_budget"] == 120
    assert [b["name"] for b in v["boards"] if not b["crystal"]] == [ARIEL, "Azphel"]
    full = {n["id"] for n in board(cd, ARIEL)["nodes"] if n["type"] != "Start"}
    texts = {s["label"]: s["text"] for s in daevanion_view(cd, full)["stats"]}
    assert texts["PvE Damage Boost"] == "+6.0%" and texts["Boss Damage Boost"] == "+4.0%"
    assert texts["PvE Damage Tolerance"] == "+6.0%" and texts["Boss Attack"] == "+72"


def test_community_comparisons_stay_on_the_crystal_boards():
    """The comparison budgets are skill, stigma and Daevanion Crystal: a candidate leaves its Ariel and Azphel nodes."""
    from aion2calc.presets import candidate
    cd = ClassData("sorcerer")
    crystal, mine, azphel = (sorted(connected_nodes(cd, name, 2)) for name in ("Nezekan", ARIEL, "Azphel"))
    summary = {"class": "sorcerer", "policy": [],
               "build": {"sp": {}, "stigmas": {}, "specs": {}, "daevanion_nodes": crystal + mine + azphel}}
    assert candidate(summary)["build"]["build"]["daevanion_nodes"] == crystal


def test_a_class_optimization_takes_the_ariel_budget_from_the_body_or_the_server(monkeypatch):
    """The body's Ariel total, else the highest the server reports; a server from before 0.2.381 reports none, and then
    none is spent. The server is needed only for the totals the body lacks."""
    from aion2calc.app import server
    from aion2calc.combat import share
    rows = [{"class_name": "sorcerer", "skill": 200, "stigma": 30, "daevanion": 360, "ariel": 96},
            {"class_name": "sorcerer", "skill": 210, "stigma": 31, "daevanion": 380, "ariel": None}]
    monkeypatch.setattr(share, "community_request", lambda path, body=None: {"observations": rows})
    assert server._class_point_budgets({"class": "sorcerer"}) == {"skill": 210, "stigma": 31, "daevanion": 380, "ariel": 96}
    given = {"class": "sorcerer", "skill_points": 1, "stigma_points": 2, "daevanion": 3}
    assert server._class_point_budgets({**given, "ariel": 4})["ariel"] == 4
    monkeypatch.setattr(share, "community_request", lambda path, body=None: {"observations": rows[1:]})
    assert server._class_point_budgets({"class": "sorcerer"})["ariel"] == 0

    def offline(path, body=None):
        raise OSError("offline")
    monkeypatch.setattr(share, "community_request", offline)
    assert server._class_point_budgets(given) == {"skill": 1, "stigma": 2, "daevanion": 3, "ariel": 0}
    with pytest.raises(OSError):
        server._class_point_budgets({"class": "sorcerer"})
    with pytest.raises(ValueError):
        server._class_point_budgets({**given, "ariel": -5})


def test_the_shared_totals_carry_the_ariel_crystal():
    from aion2calc.app import server
    imp = SimpleNamespace(cls="sorcerer", systems={})
    obs = server._point_observation({"region": "nae"}, imp, {"skill": 1, "stigma": 2, "daevanion": 3, "ariel": 4},
                                    "profile_lower_bound")
    assert obs["points"] == {"skill": 1, "stigma": 2, "daevanion": 3, "ariel": 4}
    obs = server._point_observation({"region": "nae"}, imp, {"skill": 1, "stigma": 2, "daevanion": 3}, "user_reported")
    assert obs["points"] == {"skill": 1, "stigma": 2, "daevanion": 3}


def test_an_imported_characters_ariel_points_are_its_ariel_budget(tmp_path, monkeypatch):
    from aion2calc import charopt
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    cd = ClassData("sorcerer")
    mine, crystal = connected_nodes(cd, ARIEL, 5), connected_nodes(cd, "Zikel", 2)
    imp = SimpleNamespace(cls="sorcerer", key="k1",
                          build=SimpleNamespace(sp_spent=lambda: 90, stigma_spent=lambda: 10, daevanion=mine | crystal))
    assert charopt.budgets_of(imp) == {"skill": 90, "stigma": 10, "daevanion": cost(cd, crystal), "ariel": cost(cd, mine)}
    rows = {r["resource"]: r for r in charopt.progression_of(imp, charopt.budgets_of(imp))["resources"]}
    assert rows["ariel"]["observed_spent"] == cost(cd, mine)


def test_the_build_catalog_has_the_ariel_board_on_its_own_budget():
    """The allocation workspace (app and GitHub page) gives every board outside ``crystal_boards`` its own budget."""
    catalog = json.loads((Path(aion2calc.__file__).parent / "app/static/build-catalog.json").read_text(encoding="utf-8"))
    assert catalog["crystal_boards"] == list(CRYSTAL_BOARDS)
    for cls in CLASSES:
        boards = {b["name"]: b for b in catalog["classes"][cls]["boards"]}
        assert boards[ARIEL]["needLevel"] == 45 and sum(n["cost"] for n in boards[ARIEL]["nodes"]) == 232


def test_the_highest_observed_points_show_the_ariel_total():
    """Combat Logs' Highest observed build points (the website's and the app's) and the community panel's totals show
    each row's reported Ariel total (a log server from 0.2.166 keeps it; ``—`` where no client has reported one)."""
    root = Path(aion2calc.__file__).resolve().parent.parent
    for path in (root / "site/logs.js", root / "aion2calc/app/static/logs-view.js"):
        text = path.read_text(encoding="utf-8")
        assert '<th class="r">Ariel</th>' in text and "${n0(o.ariel)}" in text, path
        assert "(o.daevanion || 0) + (o.ariel || 0)" in text, path         # the row's total counts it
    community = (root / "aion2calc/app/static/community.js").read_text(encoding="utf-8")
    assert "'PvE Daevanion','Ariel','Observations'" in community
    assert "Number.isInteger(x.ariel)?x.ariel:'—'" in community
