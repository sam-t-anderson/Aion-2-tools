"""Advice recommendations that need no recorded state: the Genus Insight lines to roll for per
slot (from the Global slot property tables) and the Pantheon board (colossus, statues,
artworks) by modeled damage per deity point."""
import json
from pathlib import Path

import pytest

from aion2calc.plan import genus as G
from aion2calc.plan.pantheon import SLOTS, plan_board

ROOT = Path(__file__).resolve().parent.parent / "aion2calc" / "data" / "global"


def test_the_slot_property_catalog_is_complete_and_percent_ranges_are_parsed():
    cat = json.loads((ROOT / "genus_properties.json").read_text(encoding="utf-8"))
    assert set(cat["genera"]) == {"Cogni", "Fera", "Natura", "Varian", "Special"}
    assert cat["genera"]["Cogni"]["properties"] == 393 and cat["genera"]["Special"]["properties"] == 490
    assert set(cat["genera"]["Cogni"]["slots"]) == {str(i) for i in range(1, 10)}
    boost = cat["genera"]["Cogni"]["slots"]["4"]["Cogni Damage Boost"]["Heroic"]
    assert boost[:3] == [2.4, 4.8, True]                                   # percent ranges keep their numbers
    assert "Cogni Damage Boost" not in cat["genera"]["Cogni"]["slots"]["7"]   # slot 7 is the tolerance mirror
    assert G.data()["genus_lines"]["damage_boost"]["slots"] == [4]
    for genus, g in cat["genera"].items():
        for slot, stats in g["slots"].items():
            for stat, grades in stats.items():
                assert all(row[0] is not None and row[1] is not None for row in grades.values()), (genus, slot, stat)


@pytest.fixture(scope="module")
def ctx():
    from aion2calc.plan.context import PlanContext
    return PlanContext.for_class("gladiator")


def test_roll_targets_rank_amplification_in_slot_4_and_never_recommend_unmodeled_lines(ctx):
    mix = {"Cogni": 0.25, "Fera": 0.25, "Natura": 0.25, "Varian": 0.25}
    rt = G.roll_targets(ctx, {}, "pve", mix)                               # nothing recorded at all
    cogni = rt["genera"]["Cogni"]
    slot4 = cogni["slots"][4]
    assert slot4["status"] == "Enter level" and slot4["aim"]
    assert slot4["aim"][0]["stat"] in {"PvE Damage Boost", "Damage Boost", "Cogni Damage Boost"}
    assert all(r["modeled"] and r["gain"] is not None and r["gain"] > 0 for s in cogni["slots"].values() for r in s["aim"])
    assert all("Defense" not in r["stat"] and "Resist" not in r["stat"] for s in cogni["slots"].values() for r in s["aim"])
    assert slot4["options"] > slot4["unmodeled"] > 0
    assert cogni["best"][0]["slot"] == 4                                   # the amplification slot is the biggest lever
    special = rt["genera"]["Special"]["slots"][4]["aim"]
    assert special[0]["stat"] in {"Double Chance", "Front Attack Damage Boost", "Damage Boost"}
    defensive = rt["genera"]["Cogni"]["slots"][2]["aim"]                  # the defense slot's only damage lines are genus-scoped
    assert defensive and all(r["conditional"] for r in defensive)
    assert rt["genera"]["Special"]["slots"][2]["aim"] == []                 # and the Special board's defense slot has none


def test_roll_targets_follow_the_recorded_state_and_pvp_mode(ctx):
    mix = {"Cogni": 0.25, "Fera": 0.25, "Natura": 0.25, "Varian": 0.25}
    state = {"Cogni": {"level": 5, "lines": [{"slot": 4, "stat": "Cogni Defense", "value": "54"},
                                              {"slot": 1, "stat": "Boss Attack", "value": "12"}]}}
    rt = G.roll_targets(ctx, state, "pve", mix)
    slots = rt["genera"]["Cogni"]["slots"]
    assert slots[4]["status"] == "Reroll candidate" and slots[1]["status"] in ("Keep", "Reroll candidate")
    assert slots[7]["status"] == "Unlock at Lv 7" and slots[7]["aim"]    # still says what to roll for later
    pvp = G.roll_targets(ctx, state, "pvp", mix)
    assert all(not r["conditional"] for s in pvp["genera"]["Cogni"]["slots"].values() for r in s["aim"])
    assert all(r["stat"] != "PvE Damage Boost" for s in pvp["genera"]["Cogni"]["slots"].values() for r in s["aim"])


def test_plan_genus_exposes_the_roll_targets(ctx):
    plan = G.plan_genus(ctx, {}, [], {"Cogni": 1.0}, fetch_missing=False)
    assert set(plan["roll_targets"]["genera"]) == {"Cogni", "Fera", "Natura", "Varian", "Special"}
    assert plan["roll_targets"]["genera"]["Cogni"]["slots"][4]["aim"][0]["gain"] > 0


PER_POINT = [{"deity": "Wisdom [Lumiel]", "gain_per_point": 0.00096}, {"deity": "Illusion [Kaisinel]", "gain_per_point": 0.00076},
             {"deity": "Time [Siel]", "gain_per_point": 0.00063}, {"deity": "Destruction [Zikel]", "gain_per_point": 0.0005},
             {"deity": "Death [Triniel]", "gain_per_point": 0.0002}, {"deity": "Justice [Nezekan]", "gain_per_point": 0.00001},
             {"deity": "Freedom [Vaizel]", "gain_per_point": 0.0}, {"deity": "Life [Yustiel]", "gain_per_point": 0.0},
             {"deity": "Destiny [Marchutan]", "gain_per_point": 0.0}, {"deity": "Space [Israphel]", "gain_per_point": 0.0}]


def _catalog():
    return {"source": "test", "items": [
        {"id": 1, "name": "Colossus: Nahma", "kind": "colossus", "grade": "Heroic", "bound": False, "faction": None, "global": True,
         "stats": {"Destruction [Zikel]": 55, "Justice [Nezekan]": 55, "Time [Siel]": 55}, "points": 165, "sources": ["Drops from Nahma"]},
        {"id": 2, "name": "Colossus: Nahma (Bound)", "kind": "colossus", "grade": "Heroic", "bound": True, "faction": None, "global": True,
         "stats": {"Destruction [Zikel]": 55, "Justice [Nezekan]": 55, "Time [Siel]": 55}, "points": 165, "sources": ["Achievement reward"]},
        {"id": 3, "name": "Colossus: Atheron (Bound)", "kind": "colossus", "grade": "Unique", "bound": True, "faction": None, "global": False,
         "stats": {"Wisdom [Lumiel]": 50, "Time [Siel]": 50, "Destruction [Zikel]": 50}, "points": 150, "sources": ["Token shop"]},
        {"id": 4, "name": "Statue: Life", "kind": "statue", "grade": "Rare", "bound": True, "faction": None, "global": True,
         "stats": {"Life [Yustiel]": 12, "Space [Israphel]": 12}, "points": 24, "sources": []},
        {"id": 5, "name": "Statue: Wise", "kind": "statue", "grade": "Rare", "bound": True, "faction": "elyos", "global": True,
         "stats": {"Wisdom [Lumiel]": 8}, "points": 8, "sources": ["Quest: A"]},
        {"id": 6, "name": "Statue: Wise Asmo", "kind": "statue", "grade": "Rare", "bound": True, "faction": "asmodian", "global": True,
         "stats": {"Wisdom [Lumiel]": 8}, "points": 8, "sources": ["Quest: B"]},
        {"id": 7, "name": "Statue: Unknown", "kind": "statue", "grade": "Rare", "bound": True, "faction": None, "global": True,
         "stats": {}, "points": 0, "sources": []},
    ] + [{"id": 100 + i, "name": f"Artwork: Piece {i}", "kind": "artwork", "grade": "Epic", "bound": True, "faction": None, "global": True,
          "stats": {"Illusion [Kaisinel]": 5 if i < 3 else 2, "Life [Yustiel]": 5}, "points": 10 if i < 3 else 7, "sources": ["drop"]} for i in range(14)]}


def test_the_board_picks_by_damage_value_and_dedupes_bindings():
    b = plan_board(PER_POINT, faction="asmodian", catalog_data=_catalog())
    assert b["slots"] == SLOTS
    col = b["board"]["colossus"]
    assert len(col) == 1 and col[0]["short"] == "Nahma" and col[0]["gain"] == pytest.approx(55 * (0.0005 + 0.00001 + 0.00063))
    assert sorted(col[0]["sources"]) == ["Achievement reward", "Drops from Nahma"]     # both bindings on one card
    assert all(r["short"] != "Atheron" for r in col + b["runners_up"]["colossus"])       # Korea/Taiwan-only left out
    statues = [r["short"] for r in b["board"]["statue"]]
    assert statues[0] == "Wise Asmo" and "Wise" not in statues and "Unknown" not in statues   # faction + unknown effect
    assert "Life" in statues                                                              # zero-value piece still fills a free stand
    art = b["board"]["artwork"]
    assert len(art) == 12 and [r["points"] for r in art][:3] == [10, 10, 10] and len(b["runners_up"]["artwork"]) == 2
    assert b["totals"]["Illusion [Kaisinel]"] == 3 * 5 + 9 * 2 and b["gain"] > 0
    assert b["catalog"]["unknown_effect"] == 1 and b["catalog"]["candidates"]["colossus"] == 1
    both = plan_board(PER_POINT, faction=None, include_kr=True, catalog_data=_catalog())
    assert both["board"]["colossus"][0]["short"] == "Atheron"                            # Wisdom-heavy colossus wins when allowed
    assert {r["short"] for r in both["board"]["statue"]} >= {"Wise", "Wise Asmo"}


def test_the_bundled_catalog_yields_a_full_board_for_a_class():
    from aion2calc.plan.pantheon import catalog
    cat = catalog()
    assert cat["slots"] == SLOTS and len(cat["items"]) >= 250
    b = plan_board(PER_POINT, faction="asmodian", catalog_data=cat)
    assert len(b["board"]["colossus"]) == 1 and len(b["board"]["statue"]) == 4 and len(b["board"]["artwork"]) == 12
    assert b["board"]["colossus"][0]["short"] == "Guardian Lord Nahma" and b["board"]["colossus"][0]["sources"]
    assert all(r["stats"] and r["gain"] >= 0 for rows in b["board"].values() for r in rows)
