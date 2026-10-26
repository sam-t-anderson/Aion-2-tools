"""Pages that read the app's own state: the Pet Tracker page and Settings → Pet Tracker say when a newer Pet
Tracker is out and hand its update over; the Raid Planner browses the log server's plans by boss; the Timers
page names the server and faction the live meter found and lists that server's field-boss kills; the Gear
page's item panel takes an item's enchant level, rolls and skill options when it is added or edited; and My
Character opens the character opened last, from its snapshot or afresh, when Settings asks it to."""
import json
import re

import pytest

from apphelpers import go, open_settings
from community import KILLS, PLANS

INSTALLED = {"supported": True, "installed": {"version": "1.4.0", "folder": "C:\\Games\\PetTracker"}, "enabled": True,
             "connected": False, "start": "waiting", "problem": "Waiting for Pet Tracker's update",
             "source": "https://github.com/0Fox2Give/PetTracker", "options": {}, "rows": [], "running": {}}
UPDATE_SAID = "Pet Tracker is open: its own updater installs 1.5.0."


def pet_tracker(page, kind: str) -> list:
    """Pet Tracker 1.4.0, installed as ``kind``, with 1.5.0 out; what is posted to it is listed."""
    sent = []

    def answer(route):
        state = {**INSTALLED, "update": {"available": True, "latest": "1.5.0", "installed": "1.4.0", "kind": kind}}
        if route.request.method == "POST":
            sent.append(json.loads(route.request.post_data))
            state["message"] = UPDATE_SAID
        route.fulfill(json=state)
    page.route(re.compile(r"/api/pettracker(\?|$)"), answer)
    return sent


def test_the_pet_tracker_page_says_a_newer_one_is_out_and_hands_the_update_over(app_page, app_url):
    page = app_page
    sent = pet_tracker(page, "installer")
    go(page, app_url, "#/pets")
    page.wait_for_selector("#pt-update")
    head = page.locator("#pt-head").inner_text()
    assert "Pet Tracker 1.4.0" in head and "C:\\Games\\PetTracker" in head and "Waiting for Pet Tracker's update" in head
    assert "Pet Tracker 1.5.0 is available (you have 1.4.0)." in head
    assert page.locator("#pt-update").inner_text() == "Update Pet Tracker"
    page.click("#pt-update")
    page.wait_for_function("t => document.querySelector('#pt-note').textContent === t", arg=UPDATE_SAID)
    assert sent == [{"action": "update"}]


def test_an_offline_copy_is_installed_over_and_a_copy_of_ones_own_links_to_the_releases(app_page, app_url):
    page = app_page
    pet_tracker(page, "offline")
    go(page, app_url, "#/pets")
    page.wait_for_selector("#pt-update")
    assert page.locator("#pt-update").inner_text() == "Install Pet Tracker 1.5.0"
    page.unroute(re.compile(r"/api/pettracker(\?|$)"))
    pet_tracker(page, "custom")
    go(page, app_url, "#/pets")
    link = page.get_by_role("link", name="Download it from Pet Tracker's releases")
    link.wait_for()
    assert link.get_attribute("href") == "https://github.com/0Fox2Give/PetTracker/releases"
    assert page.locator("#pt-update").count() == 0


def test_settings_says_so_too_and_its_button_hands_the_update_over(app_page, app_url):
    page = app_page
    sent = pet_tracker(page, "installer")
    open_settings(page, app_url, "pettracker")
    page.wait_for_selector("#pt-set-update")
    status = page.locator("#pt-set-status").inner_text()
    assert status.startswith("Installed: version 1.4.0, in C:\\Games\\PetTracker. Waiting for Pet Tracker's update")
    assert "Pet Tracker 1.5.0 is available (you have 1.4.0)." in status
    page.click("#pt-set-update")
    page.wait_for_function("t => document.querySelector('#pt-set-note').textContent === t", arg=UPDATE_SAID)
    assert sent == [{"action": "update"}]


def test_the_raid_planner_browses_the_servers_plans_by_boss(app_page, app_url, community):
    page = app_page
    go(page, app_url, "#/raid")
    page.click("#rbrowse")
    page.wait_for_selector(".pcard")
    menu = page.locator("[data-boss]").all_inner_texts()
    assert menu == ["All"] + [f"{plan['boss']} (1)" for plan in PLANS]
    assert page.locator(".pcard .gname").all_inner_texts() == [plan["name"] for plan in PLANS]
    second = PLANS[1]
    page.locator(f'[data-boss="{second["npc_id"]}"]').click()
    page.wait_for_function("n => document.querySelectorAll('.pcard').length === n", arg=1)
    assert page.locator(".pcard .gname").all_inner_texts() == [second["name"]]
    assert ("GET", f"/api/v1/plans?npc={second['npc_id']}") in community.requests       # the filter reaches the server
    page.locator("[data-boss]", has_text="All").click()
    page.wait_for_function("n => document.querySelectorAll('.pcard').length === n", arg=len(PLANS))
    page.locator(f'.pcard:has-text("{PLANS[0]["name"]}") [data-open]').click()
    page.get_by_text("Plan opened").wait_for()
    assert page.locator("#rplan option:checked").inner_text() == f"{PLANS[0]['name']} — {PLANS[0]['boss']}"   # now its own plan


IDENTITY = {"server": 2102, "server_name": "Zikel", "faction": "asmodian", "character": "Testsorc"}


def test_the_timers_page_takes_the_server_and_faction_from_the_live_meter(app_page, app_url):
    page = app_page
    page.route(re.compile(r"/api/meter\?view=latest$"),
               lambda route: route.fulfill(json={"running": False, "snapshot": {"field_bosses": IDENTITY}}))
    go(page, app_url, "#/timers")
    identity = page.locator("[data-kill-identity]")
    identity.get_by_text("Identified from your live meter").wait_for()
    assert identity.inner_text().startswith("Identified from your live meter: Testsorc on Zikel · Asmodian.")
    assert page.locator("[data-kill-faction]").input_value() == "mine"
    page.wait_for_selector("[data-kill-rows] details")
    assert page.locator("[data-kill-server]").input_value() == "2102"
    shown = lambda: [s.split(" · ")[0] for s in page.locator("[data-kill-rows] summary").all_inner_texts()]
    alpha, beta = KILLS[0]["boss"], KILLS[1]["boss"]
    assert shown() == [alpha]                                                     # an Elyos zone's kill is not ours
    page.select_option("[data-kill-faction]", "all")
    assert shown() == [alpha, beta]
    page.select_option("[data-kill-faction]", "elyos")
    assert shown() == [beta]
    page.select_option("[data-kill-faction]", "mine")


CHARACTER = {"key": "nae-1101-Testsorc", "name": "Testsorc", "class_name": "Sorcerer", "region": "nae"}
RING = {"id": "e1", "slug": "test-ring", "name": "Test Ring", "slot": "Ring 1", "grade": "Epic", "enchant": 3,
        "rolls": [["Critical Hit", 40]], "skills": [["Hellfire", 2]], "source": "inventory", "note": ""}
OPTIONS = {"name": "Test Ring", "category": "Ring", "item_level": 40, "grade": "Epic", "max_enchant": 10, "enchant_known": True,
           "enchant_steps": [{"level": 1, "stats": "Attack +5"}, {"level": 5, "stats": "Attack +12"}], "roll_count": 2,
           "rolls": [{"stat": "Critical Hit", "range": "+30 – +50", "min": 30, "max": 50, "percent": False, "scored": True},
                     {"stat": "Accuracy", "range": "+20 – +40", "min": 20, "max": 40, "percent": False, "scored": True}],
           "skills": {"base": 3, "per_enchant": 0, "max_level": 3, "pool": ["Hellfire", "Blaze"], "others": ["Frost"]}, "arcana": False}


def gear(page) -> list:
    """A character with one ring in the inventory, the ring's catalog options, and the inventory's saves."""
    saved = []
    page.route("**/api/characters", lambda route: route.fulfill(json=[CHARACTER]))
    page.route(re.compile(r"/api/inventory\?character="), lambda route: route.fulfill(
        json={"class": "sorcerer", "items": [RING], "genus": {}, "titles_owned": []}))
    page.route(re.compile(r"/api/items/test-ring/options\?class=sorcerer$"), lambda route: route.fulfill(json=OPTIONS))
    page.route(re.compile(r"/api/items\?search="), lambda route: route.fulfill(
        json=[{"slug": "test-ring", "name": "Test Ring", "category": "Ring", "item_level": 40, "grade": "Epic"}]))

    def save(route):
        saved.append((route.request.url.rsplit("/", 1)[1], json.loads(route.request.post_data)))
        route.fulfill(json={"ok": True})
    page.route(re.compile(r"/api/inventory/(update|add)$"), save)
    return saved


def test_the_gear_pages_item_panel_takes_enchant_rolls_and_skill_options(app_page, app_url):
    page = app_page
    saved = gear(page)
    go(page, app_url, "#/gear")
    page.wait_for_selector('[data-edit="e1"]')
    assert page.locator("#ginv th").all_text_contents()[:4] == ["Slot", "Item", "Rolls", "Skill options"]
    assert page.locator("#ginv tr", has_text="Test Ring").locator("td").all_inner_texts()[2:4] == ["Critical Hit +40", "Hellfire +2"]
    page.click('[data-edit="e1"]')
    panel = page.locator("#gedit .gedit")
    panel.wait_for()
    assert "editing your inventory entry" in panel.inner_text()
    assert page.locator("[data-ge-enchant] option").all_inner_texts() == [f"+{i}" for i in range(11)]
    assert page.locator("[data-ge-enchant]").input_value() == "3"
    assert "+3: Attack +5" in panel.inner_text()                                    # what that enchant level gives
    assert page.locator('[data-ge-roll="0"]').input_value() == "Critical Hit" and page.locator('[data-ge-val="0"]').input_value() == "40"
    page.select_option('[data-ge-roll="1"]', "Accuracy")
    assert page.locator('[data-ge-val="1"]').input_value() == "20"                    # its lowest roll to start from
    page.fill('[data-ge-val="1"]', "")
    page.click("[data-ge-save]")
    assert page.locator("[data-ge-msg]").inner_text() == "Enter a value for every chosen roll."
    page.fill('[data-ge-val="1"]', "35")
    page.select_option("[data-ge-enchant]", "5")
    assert "+5: Attack +12" in panel.inner_text()
    page.click("[data-ge-skadd]")
    page.click("[data-ge-save]")
    assert page.locator("[data-ge-msg]").inner_text() == "Choose a skill on every option line, or remove the line."
    page.click('[data-ge-skrm="1"]')
    page.fill("[data-ge-note]", "warehouse")
    page.click("[data-ge-save]")
    page.get_by_text("Saved", exact=True).wait_for()
    assert saved == [("update", {"character": CHARACTER["key"], "enchant": 5, "rolls": [["Critical Hit", 40], ["Accuracy", 35]],
                                 "skills": [["Hellfire", 2]], "note": "warehouse", "id": "e1"})]
    page.fill("#gq", "test ring")
    page.click("#gsrch")
    page.click('[data-add="test-ring"]')
    panel.wait_for()
    assert "adding to your inventory" in panel.inner_text() and page.locator("[data-ge-enchant]").input_value() == "0"
    page.click("[data-ge-save]")
    page.get_by_text("Added", exact=True).wait_for()
    assert saved[1] == ("add", {"character": CHARACTER["key"], "enchant": 0, "rolls": [], "skills": [], "note": "", "slug": "test-ring"})


KNOWN = {"character_id": "c1", "server_id": 1101, "region": "nae", "name": "Testsorc", "class_name": "Sorcerer",
         "combat_power": 12345, "key": "nae-1101-Testsorc"}


def my_character(page, result: dict = None, **ui) -> list:
    """One character imported before, with these settings; the imports My Character asks for are listed. Each
    ends at once, the official site not asked: with ``result``, the character as the import makes it, or else
    an error."""
    asked = []
    page.route("**/api/characters", lambda route: route.fulfill(json=[KNOWN]))

    def settings(route):
        if route.request.method != "GET":
            return route.continue_()
        answer = route.fetch()
        route.fulfill(response=answer, json={**answer.json(), **ui})
    page.route("**/api/ui", settings)

    def start(route):
        asked.append(json.loads(route.request.post_data))
        route.fulfill(json={"job": "j1"})
    page.route("**/api/character/import", start)
    page.route("**/api/jobs/j1", lambda route: route.fulfill(json={"status": "done", "result": result, "log": []} if result else
                                                             {"status": "error", "error": "the test stops here", "log": []}))
    return asked


WHO = {key: KNOWN[key] for key in ("character_id", "server_id", "region", "name")}


def test_my_character_opens_the_last_character_from_its_snapshot_once_a_session(app_page, app_url):
    page = app_page
    asked = my_character(page, character_auto_open=True, character_auto_refresh=False)
    go(page, app_url, "#/character")
    page.locator("#cview").get_by_text("the test stops here").wait_for()
    assert asked == [{**WHO, "cache": 10 * 365 * 86400}]                         # its last snapshot, however old
    page.evaluate("location.hash = '#/meter'")
    page.wait_for_function("document.querySelector('#page-title').textContent === 'Live Meter'")
    page.evaluate("location.hash = '#/character'")
    page.wait_for_function("document.querySelector('#page-title').textContent === 'My Character'")
    page.wait_for_timeout(1500)
    assert len(asked) == 1                                                       # once while the app runs


def test_my_character_refreshes_it_from_the_official_site_or_waits_to_be_asked(app_page, app_url):
    page = app_page
    asked = my_character(page, character_auto_open=True, character_auto_refresh=True)
    go(page, app_url, "#/character")
    page.locator("#cview").get_by_text("the test stops here").wait_for()
    assert asked == [WHO]                                                        # no snapshot: fetched afresh
    page.unroute("**/api/ui")
    asked.clear()
    go(page, app_url, "#/character")                                             # the setting off: it waits
    page.locator('[data-known-character="0"]').wait_for()
    page.wait_for_timeout(1500)
    assert asked == []
    page.click('[data-known-character="0"]')
    page.locator("#cview").get_by_text("the test stops here").wait_for()
    assert asked == [WHO]


def character(page, level: int) -> dict:
    """A character of this level as the import shows it: a bundled Sorcerer build's windows, with what the
    official profile adds (name, world, level, points spent) and the points the player has."""
    presets = page.evaluate("() => api('/api/planner/presets')")
    path = next(p["path"] for p in presets if p["class"] == "sorcerer")
    view = page.evaluate("path => api('/api/build?path=' + encodeURIComponent(path))", path)
    return {**view, "name": "Testsorc", "level": level, "level_cap": 45, "server": "Zikel", "combat_power": 12345,
            "key": KNOWN["key"], "loadout": "1", "warnings": [], "dps": {"boss": 10000}, "progression": None,
            "points": {"skill": 90, "stigma": 10, "daevanion": 150}, "budgets": {"skill": 100, "stigma": 20, "daevanion": 200}}


@pytest.mark.parametrize("level, offered", [(45, {"skill": "130", "stigma": "25", "daevanion": "300"}),
                                            (30, {"skill": "100", "stigma": "20", "daevanion": "200"})])
def test_my_character_offers_the_reported_point_totals_only_at_the_level_cap(app_page, app_url, community, level, offered):
    # the highest reported totals come from level-45 characters: a level-24 Templar's were once offered to every Templar
    page = app_page
    go(page, app_url, "#/settings")
    view = character(page, level)
    my_character(page, view)
    page.route(re.compile(r"/api/inventory\?character="), lambda route: route.fulfill(     # imported, so it has one
        json={"class": "sorcerer", "items": [], "genus": {}, "titles_owned": []}))
    asked = len(community.requests)
    go(page, app_url, "#/character")
    page.click('[data-known-character="0"]')
    page.locator("#cview h2", has_text="Testsorc").wait_for()
    assert page.locator("#cview .wh .sub").first.inner_text() == f"Sorcerer · Lv {level} · Zikel · Combat Power 12,345"
    if level == 45:                                                              # the reported totals arrive
        page.wait_for_function("(document.querySelector('[data-character-budget=skill]') || {}).value === '130'")
    else:
        page.wait_for_timeout(800)                                               # as long as they would take to
    budgets = page.eval_on_selector_all("[data-character-budget]", "es => Object.fromEntries(es.map(e => [e.dataset.characterBudget, e.value]))")
    assert budgets == offered
    note = "Community point totals are not filled in below level 45: they come from characters at the level cap."
    asked_for = [path for _, path in community.requests[asked:] if path.startswith("/api/v1/progression?class=sorcerer")]
    assert (page.get_by_text(note).count(), len(asked_for)) == ((0, 1) if level == 45 else (1, 0))
