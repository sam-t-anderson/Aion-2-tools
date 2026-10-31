"""The Gathering page (Game, 0.2.358): what this computer's Live Meter recorded, from its gathering log (gathers
and dungeon reward cubes), next to everyone's drop rates from the log server. The Dungeon materials tab lists the
crafting materials until every drop is asked for, Your log lists each record, and without the log server's rates
the page shows this computer's records and says why everyone's are missing. Synthetic characters only."""
import json
import time

import pytest

import community as stand_in
from apphelpers import go, on_page

ORE, FINE_ORE, REFINING, WILL, KINA = 610620013, 610620014, 610530001, 610511014, 930100031
ALTGARD = 1110


@pytest.fixture
def gathered(app_home):
    """This computer's gathering log: four gathers at an Orichalcum vein (one a better grade, one failed) in
    Altgard, then a reward cube in Ferocious Horn Den, all Alpha's."""
    from aion2calc.combat.gathering import normalize
    start = int(time.time() * 1000) - 600_000
    raw = [{"kind": "gather", "timestamp_ms": start + i * 1000, "item": item, "count": count, "result": result,
            "node": stand_in.ORE_VEIN, "position": [1.0, 2.0, 3.0], "map_id": ALTGARD, "instance_id": None,
            "character": "Alpha", "server_id": 2102}
           for i, (item, count, result) in enumerate([(ORE, 2, 0), (ORE, 1, 0), (FINE_ORE, 1, 1), (ORE, 0, 2)])]
    raw.append({"kind": "reward", "timestamp_ms": start + 60_000, "items": [[KINA, 800_000], [REFINING, 6], [WILL, 1]],
                "map_id": stand_in.DEN, "instance_id": stand_in.DEN, "character": "Alpha", "server_id": 2102})
    path = app_home / "data" / "gathering" / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(normalize(row)) + "\n" for row in raw), encoding="utf-8")
    yield
    path.unlink()


def texts(page, selector: str) -> list:
    """Each matching element's text as written (not as shown: a KPI's label is shown in capitals)."""
    return page.locator(selector).evaluate_all("els => els.map(el => el.textContent.replace(/\\s+/g, ' ').trim())")


def kpis(page) -> list:
    return page.locator(".gt-kpis .kpi").evaluate_all(
        "els => els.map(el => el.querySelector('.k').textContent + ' ' + el.querySelector('.v').textContent)")


def rows(page, card: str) -> list:
    """Each table row of the cards matching ``card``, as its cells' text."""
    return page.locator(f"{card} tbody tr").evaluate_all(
        "trs => trs.map(tr => [...tr.cells].map(td => td.textContent.replace(/\\s+/g, ' ').trim()))")


def test_the_page_sums_up_this_computers_gathering_next_to_everyones_rates(app_page, app_url, gathered):
    page = app_page
    go(page, app_url, "#/gathering")
    on_page(page, "Gathering")
    page.wait_for_selector(".gt-node")
    assert kpis(page) == ["Gathers 4", "Items gathered 4", "Better grade 1 (25.0%)", "Failed 1 (25.0%)",
                                            "Reward cubes 1"]
    assert "shares it for everyone's drop rates" in page.locator("#gathering-sharing").inner_text()
    assert page.get_by_role("tab", name="Gathering").get_attribute("aria-selected") == "true"
    # everyone's rates first, as the log server worked them out
    assert page.get_by_role("button", name="Everyone").get_attribute("aria-pressed") == "true"
    assert texts(page, ".gt-node h3") == ["Orichalcum Ore 40 gathers · 3 players"]
    assert "Normal 75.0% · Better grade 20.0% · Failed 5.0%" in page.locator(".gt-node").inner_text()
    assert rows(page, ".gt-node") == [["Orichalcum Ore", "Common", "75.0%", "1.00"], ["Fine Orichalcum Ore", "Rare", "20.0%", "1.00"]]
    # this computer's: two normal gathers gave three ore, the better grade gave Fine ore, the failed one nothing
    page.get_by_role("button", name="This computer").click()
    assert texts(page, ".gt-node h3") == ["Orichalcum Ore 4 gathers"]
    assert "Normal 50.0% · Better grade 25.0% · Failed 25.0%" in page.locator(".gt-node").inner_text()
    assert rows(page, ".gt-node") == [["Orichalcum Ore", "Common", "50.0%", "1.50"], ["Fine Orichalcum Ore", "Rare", "25.0%", "1.00"]]


def test_dungeon_materials_list_the_crafting_materials_until_every_drop_is_asked_for(app_page, app_url, gathered):
    page = app_page
    go(page, app_url, "#/gathering")
    page.wait_for_selector(".gt-node")
    page.get_by_role("tab", name="Dungeon materials").click()
    assert texts(page, ".gt-dungeon h3") == ["Ferocious Horn Den (Normal) 5 reward cubes · 2 players"]
    assert rows(page, ".gt-dungeon") == [["Refining Stone", "Common", "80.0%", "4.25"], ["Wrathful Will", "Unique", "20.0%", "1"]]
    page.get_by_label("Show every drop (equipment, currency)").check()
    assert rows(page, ".gt-dungeon")[0] == ["Kina", "Common", "100.0%", "600,000"]
    page.get_by_role("button", name="This computer").click()                 # the one cube this computer opened
    assert texts(page, ".gt-dungeon h3") == ["Ferocious Horn Den (Normal) 1 reward cubes"]
    assert [r[0] for r in rows(page, ".gt-dungeon")] == ["Kina", "Refining Stone", "Wrathful Will"]
    page.get_by_label("Show every drop (equipment, currency)").uncheck()
    assert rows(page, ".gt-dungeon") == [["Refining Stone", "Common", "100.0%", "6"], ["Wrathful Will", "Unique", "100.0%", "1"]]


def test_your_log_lists_each_record_and_the_page_reopens_on_the_tab_left(app_page, app_url, gathered):
    page = app_page
    go(page, app_url, "#/gathering")
    page.wait_for_selector(".gt-node")
    page.get_by_role("tab", name="Your log").click()
    logged = rows(page, ".gt-log")
    assert [r[1:] for r in logged] == [
        ["Ferocious Horn Den (Normal)", "Reward cube: Refining Stone ×6, Wrathful Will ×1 (3 drops)", "Alpha"],
        ["Altgard", "Orichalcum Ore Failed: nothing gathered", "Alpha"],
        ["Altgard", "Fine Orichalcum Ore ×1 Better grade", "Alpha"],
        ["Altgard", "Orichalcum Ore ×1 Normal", "Alpha"],
        ["Altgard", "Orichalcum Ore ×2 Normal", "Alpha"]]
    assert all(len(r[0]) == 19 for r in logged)                               # YYYY-MM-DD HH:MM:SS
    go(page, app_url, "#/gathering")
    page.wait_for_selector(".gt-log")
    assert page.get_by_role("tab", name="Your log").get_attribute("aria-selected") == "true"


def test_without_everyones_rates_the_page_shows_this_computers_and_says_why(app_page, app_url, gathered):
    page = app_page
    page.watch.allow("/api/community?path=%2Fapi%2Fv1%2Fgathering%2Fstats")   # the log server has no rates yet
    page.watch.allow("Failed to load resource")
    stats = stand_in.ANSWERS.pop("/api/v1/gathering/stats")
    try:
        go(page, app_url, "#/gathering")
        page.wait_for_selector(".gt-node")
        assert page.get_by_role("button", name="This computer").get_attribute("aria-pressed") == "true"
        assert texts(page, ".gt-node h3") == ["Orichalcum Ore 4 gathers"]
        page.get_by_role("button", name="Everyone").click()
        assert page.locator(".gt-body").inner_text().strip().endswith(
            "Everyone's drop rates are not available: the log server does not have them yet, or cannot be reached.")
    finally:
        stand_in.ANSWERS["/api/v1/gathering/stats"] = stats


def test_with_nothing_recorded_the_page_says_how_records_arrive(app_page, app_url):
    page = app_page
    go(page, app_url, "#/gathering")
    page.wait_for_selector(".gt-node")                                       # everyone's rates still show
    assert kpis(page)[0] == "Gathers 0"
    page.get_by_role("button", name="This computer").click()
    assert "No gathering recorded yet: run the Live Meter while you play" in page.locator(".gt-body").inner_text()
    page.get_by_role("tab", name="Your log").click()
    assert "Nothing recorded yet: run the Live Meter while you gather" in page.locator(".gt-body").inner_text()
