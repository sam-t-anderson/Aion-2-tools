"""Pages that read the app's own state: the Pet Tracker page and Settings → Pet Tracker say when a newer Pet
Tracker is out and hand its update over; the Raid Planner browses the log server's plans by boss, and shows what a
plan file holds only as text, numbers and colours; the Timers
page names the server and faction the live meter found and lists that server's field-boss kills; the Gear
page's item panel takes an item's enchant level, rolls and skill options when it is added or edited, and the page
opens on the advice kept from the last run, or runs it when none is kept; and My Character opens the character
opened last, from its snapshot or afresh, when Settings asks it to."""
import copy
import json
import pathlib
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


PLANTED = '"><img src=x id=planted>'


def test_a_plan_file_adds_no_markup_or_styles_to_the_raid_planner(app_page, app_url, tmp_path):
    """A plan from a file, a share code or the log server reaches the Raid Planner only as text, numbers and hex
    colours (0.2.360): a keyframe time, buff times and a colour that carry markup show as 0 and the default colours,
    and none of it is added to the page."""
    page = app_page
    token = {"id": "p1", "kind": "player", "label": "Tank", "cls": "Templar", "color": 'red" onmouseover="window.planted=1',
             "keyframes": [{"t": PLANTED, "x": 0.5, "y": 0.5}]}
    plan = {"format": "a2plan", "version": 1, "meta": {"name": "Planted plan"}, "duration": 60, "arena": {"kind": "square"},
            "tokens": [token], "buffs": [{"id": "b1", "name": "Shield", "by": "Tank", "start": PLANTED, "end": "5" + PLANTED}]}
    upload = tmp_path / "planted.a2plan"
    upload.write_text(json.dumps(plan), encoding="utf-8")
    try:
        go(page, app_url, "#/raid")
        page.wait_for_selector("#rimport", state="attached")
        page.set_input_files("#rimport", str(upload))
        page.wait_for_function("document.querySelector('#rname')?.value === 'Planted plan'")
        page.locator("#arena .rtoken").click()                     # the token's editor lists its keyframe
        page.wait_for_selector("#slabel")
        assert page.locator("#planted, [onmouseover]").count() == 0
        assert page.locator(".kfrow button").first.inner_text() == "0.0s"
        assert page.locator(".bufbar").get_attribute("data-start") == "0"
        assert page.locator('[data-bf="0"][data-k="start"]').input_value() == "0"
        tint = "e => e.style.getPropertyValue('--tc').trim()"
        assert page.locator("#arena .rtoken").evaluate(tint) == "#39c2e0"
        assert page.locator(".bufbar").evaluate(tint) == "var(--gold)"
    finally:
        page.goto("about:blank")


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


# Advice for the test character as the advisor wrote it (tests/test_advice.py's run, its lists cut short), kept
# from a run on 25 Oct 2026 by an earlier version, on gear the character has changed since.
KEPT = json.loads((pathlib.Path(__file__).parent / "kept_advice.json").read_text(encoding="utf-8"))
KEPT_AT = 1792951200.0
KEPT_LAST = {"advice": KEPT, "at": KEPT_AT, "version": "0.2.343", "inputs_changed": True, "version_changed": True}


def gear(page, last=None) -> list:
    """A character with one ring in the inventory, the ring's catalog options, and the inventory's saves; its kept
    advice is ``last`` (by default KEPT_LAST, so the page does not run the advice)."""
    saved = []
    page.route("**/api/characters", lambda route: route.fulfill(json=[CHARACTER]))
    page.route(re.compile(r"/api/advice/last\?character="), lambda route: route.fulfill(json=last or KEPT_LAST))
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


def advice_runs(page) -> list:
    """The advice runs the page asks for, each answered at once with KEPT as the result."""
    runs = []

    def run(route):
        runs.append(json.loads(route.request.post_data))
        route.fulfill(json={"job": "a1"})
    page.route(re.compile(r"/api/advice$"), run)
    page.route(re.compile(r"/api/jobs/a1$"), lambda route: route.fulfill(json={"id": "a1", "status": "done", "log": [], "result": KEPT}))
    return runs


def test_gear_and_advice_opens_on_the_advice_kept_from_the_last_run(app_page, app_url):
    """The advice kept from the last run, an earlier session of the app included, shows at once under a line that
    says when it was calculated and what has changed since. It is calculated again only when Run advice is pressed."""
    page = app_page
    gear(page)
    runs = advice_runs(page)
    go(page, app_url, "#/gear")
    page.locator("#gout .pdoll").wait_for()
    stamp = page.evaluate("at => whenAt(at * 1000)", KEPT_AT)
    assert page.locator("#gkept").inner_text() == (
        f"Your last advice, calculated {stamp}. Your gear, inventory, Genus lines or titles have changed since. "
        "Version 0.2.343 of the app calculated it. Run advice calculates it again with your current gear and fights.")
    assert "TestSorc" in page.locator("#gout .pdoll").inner_text() and runs == []
    page.click("#gadv")
    page.get_by_text("Advice complete.", exact=True).wait_for()
    assert runs == [{"character": CHARACTER["key"]}] and page.locator("#gkept").is_hidden()


@pytest.mark.parametrize("last", [{"advice": None}, {**KEPT_LAST, "advice": {"character": KEPT["character"]}}],
                         ids=["none kept", "kept but not drawable"])
def test_gear_and_advice_runs_the_advice_when_none_is_kept(app_page, app_url, last):
    """With no advice kept for the character, or one this version cannot draw (an older version's), the page runs
    the advice as it opens."""
    page = app_page
    gear(page, last)
    runs = advice_runs(page)
    go(page, app_url, "#/gear")
    page.get_by_text("Advice complete.", exact=True).wait_for()
    assert runs == [{"character": CHARACTER["key"]}]
    assert page.locator("#gout .pdoll").is_visible() and page.locator("#gkept").is_hidden()


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


@pytest.mark.parametrize("level", [45, 30])
def test_my_characters_budgets_are_its_own_points_and_the_reported_totals_only_a_note(app_page, app_url, community, level):
    """The point fields start at the character's own totals, what its profile shows spent or what was typed for it
    (0.2.371). The community's highest reported totals are other players': at the level cap they show in a note and
    never fill the fields, which had the optimizer spend points the character did not have; below it they are not
    asked for (a level-24 Templar's were once offered to every Templar)."""
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
    if level == 45:                                                              # the reported totals arrive as a note
        page.locator("[data-community-points]").wait_for()
        assert page.locator("[data-community-points]").inner_text().startswith(
            "Highest totals reported for the class: skill 130, stigma 25, daevanion 300.")
    else:
        page.wait_for_timeout(800)                                               # as long as they would take to
        assert page.locator("[data-community-points]").count() == 0
    budgets = page.eval_on_selector_all("[data-character-budget]", "es => Object.fromEntries(es.map(e => [e.dataset.characterBudget, e.value]))")
    assert budgets == {"skill": "100", "stigma": "20", "daevanion": "200"}
    asked_for = [path for _, path in community.requests[asked:] if path.startswith("/api/v1/progression?class=sorcerer")]
    assert len(asked_for) == (1 if level == 45 else 0)


def test_my_characters_overview_shows_the_healing_recorded_in_its_own_fights(app_page, app_url):
    """The overview's Healing share (0.2.368) is the character's recorded healing, pooled per skill from the
    fights saved on this computer, with its HPS and how many fights it rests on; without any it says so."""
    page = app_page
    go(page, app_url, "#/settings")
    healed = {**character(page, 45), "healing": {"hps": 4321.0, "healing": 1_000_000, "fights": 7, "seconds": 1200.0, "recordings": 3,
                                                 "shares": {"Healing Light": 0.6, "Radiant Cure": 0.3, "Grace": 0.1}}}
    my_character(page, result=healed, character_auto_open=True, character_auto_refresh=True)
    page.route(re.compile(r"/api/inventory\?character="), lambda route: route.fulfill(
        json={"class": "sorcerer", "items": [], "genus": {}, "titles_owned": []}))
    go(page, app_url, "#/character")
    box = page.locator("#cview h4", has_text="HEALING SHARE")
    box.wait_for()
    text = box.locator("xpath=..").inner_text()
    assert "Recorded: 4,321 HPS over 7 fights (20 min) in 3 recordings" in text
    assert text.index("Healing Light") < text.index("Radiant Cure") < text.index("Grace") and "60.0%" in text
    assert page.locator("#cview h4", has_text="DAMAGE SHARE").count() == 1
    page.unroute("**/api/jobs/j1")
    page.route("**/api/jobs/j1", lambda route: route.fulfill(json={"status": "done", "result": {**healed, "healing": None}, "log": []}))
    go(page, app_url, "#/character")
    page.locator('[data-known-character="0"]').wait_for()
    page.click('[data-known-character="0"]')
    page.locator("#cview", has_text="No recorded healing by this character yet").wait_for()


def test_importing_another_character_after_an_optimization_shows_that_character(app_page, app_url):
    """An optimization's result belongs to the character it ran on (0.2.387). It stayed on the page and was drawn over
    the next character imported, under that character's name; the import now shows the character as imported."""
    page = app_page
    go(page, app_url, "#/settings")
    first = character(page, 45)
    second = {**first, "name": "Otherchar", "key": "nae-1101-Otherchar", "combat_power": 23456}
    other = {**KNOWN, "character_id": "c2", "name": "Otherchar", "combat_power": 23456, "key": second["key"]}
    page.route("**/api/characters", lambda route: route.fulfill(json=[KNOWN, other]))
    page.route("**/api/character/import", lambda route: route.fulfill(
        json={"job": "import-" + json.loads(route.request.post_data)["character_id"]}))
    def done(view):                       # a handler of one argument: Playwright passes the request to a second
        return lambda route: route.fulfill(json={"status": "done", "result": view, "log": []})
    for job, view in (("import-c1", first), ("import-c2", second)):
        page.route(f"**/api/jobs/{job}", done(view))
    page.route(re.compile(r"/api/inventory\?character="), lambda route: route.fulfill(
        json={"class": "sorcerer", "items": [], "genus": {}, "titles_owned": []}))
    page.route("**/api/character/optimize", lambda route: route.fulfill(json={"job": "opt"}))
    page.route("**/api/jobs/opt", lambda route: route.fulfill(json={"status": "done", "log": [], "result": {
        "summary": {"gain": 0.1, "scenario": "boss"}, "optimized": {**first, "objective": None, "dps": {"boss": 77777}},
        "diff": "a change"}}))
    go(page, app_url, "#/character")
    page.click('[data-known-character="0"]')
    page.locator("#cview h2", has_text="Testsorc").wait_for()
    page.click('[data-opt-mode="pve"]')
    page.locator("#optres", has_text="77,777").wait_for()                     # the first character, optimized
    assert page.evaluate("S.character.v.dps.boss") == 77777
    page.click('[data-known-character="1"]')
    page.locator("#cview h2", has_text="Otherchar").wait_for()
    page.wait_for_timeout(800)                                               # as long as a redraw would take
    assert page.evaluate("[S.character.v.name, S.character.v.dps.boss]") == ["Otherchar", 10000]
    assert "77,777" not in page.locator("#cview").inner_text()
    assert page.locator('[data-opt-mode="pve"]').is_enabled()


def test_the_macro_window_shows_each_line_as_a_hotbar_key_with_its_skills(app_page, app_url):
    """The suggested macro is built from hotbar keys of up to four skills (0.2.371): each line shows its key's
    skills in the order the macro casts them (0.2.377) under the key's binding, and the hotbar shows each key as one
    slot."""
    page = app_page
    go(page, app_url, "#/settings")
    presets = page.evaluate("() => api('/api/planner/presets')")
    path = next(p["path"] for p in presets if p["class"] == "templar")
    view = page.evaluate("path => api('/api/build?path=' + encodeURIComponent(path))", path)
    steps = view["rotation"]["steps"]
    assert steps and all(s.get("stack") for s in steps) and not view["macro"]["needs_refresh"]
    page.evaluate("""v => { const host = document.createElement('div'); host.id = 'macro-host';
                     document.body.append(host); renderWindows(v, {win: 'macro'}, host); }""", view)
    lines = page.locator("#macro-host .macro-step")
    assert lines.count() == len(steps)
    for i, step in enumerate(steps):              # every line, each key once
        line = lines.nth(i)
        assert line.locator(".macro-key-label kbd").inner_text() == step["binding"]
        assert line.locator(".macro-stack > div > b").all_inner_texts() == [s["name"] for s in step["stack"]]
    several = next(i for i, s in enumerate(steps) if len(s["stack"]) > 1)
    assert "cast first, skipped if it cannot be cast" in lines.nth(several).inner_text()
    assert "then this one, skipped if it cannot be cast" in lines.nth(several).inner_text()
    assert "put them on that key in the order listed" in page.locator("#macro-host .macro-instructions").inner_text()
    # Each key is on one line (0.2.388): held, the macro cycles through its lines. A macro saved with a key on two lines
    # shows the key once, on its first line, and copies it once (0.2.376 named the line it repeated, 0.2.387 drew it again)
    again = {**view, "rotation": {**view["rotation"], "steps": steps[:several + 1] + [steps[several]] + steps[several + 1:]}}
    page.evaluate("v => renderWindows(v, {win: 'macro'}, document.getElementById('macro-host'))", again)
    shown = page.locator("#macro-host .macro-step")
    assert shown.count() == len(steps)
    assert [shown.nth(i).locator(".macro-key-label kbd").inner_text() for i in range(len(steps))] == \
        [s["binding"] for s in steps]
    assert "pressed again" not in page.locator("#macro-host").inner_text()
    assert "each once: held, the macro cycles through them" in page.locator("#macro-host .macro-instructions").inner_text()
    page.evaluate("v => renderWindows(v, {win: 'hotbar'}, document.getElementById('macro-host'))", view)
    labels = page.locator("#macro-host .hotbar-slot.automatic small").all_inner_texts()
    assert any(label.endswith("skills, cast in order") for label in labels)


def test_gear_and_advice_arcana_cards_keep_their_option_names_apart(app_page, app_url):
    """Each arcana card's target options are rows, the skill's icon beside its name (0.2.372): the names sat in a 64 px
    column under each icon, so a long one ran into the next."""
    kept = copy.deepcopy(KEPT)
    chalice = kept["arcana"]["slots"]["Arcana Chalice"]
    long_names = {"Wish of Concentration": 2, "Revitalization Contract": 3, "Grace of Enhancement": 4, "Vitality Evaporation": 1}
    for slot in ("Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"):
        kept["arcana"]["slots"][slot] = {**copy.deepcopy(chalice), "ideal": {**chalice["ideal"], "skills": long_names}}
    kept["arcana"]["priority"] = list(kept["arcana"]["slots"])
    page = app_page
    gear(page, last={**KEPT_LAST, "advice": kept})
    page.set_viewport_size({"width": 1280, "height": 900})
    go(page, app_url, "#/gear")
    page.locator("#gout .acard").first.wait_for()
    clashes = """cards => cards.flatMap(card => {
        const box = card.getBoundingClientRect(), names = [...card.querySelectorAll('.sk .small')].map(n => n.getBoundingClientRect());
        return names.flatMap((a, i) => [a.left < box.left - 0.5 || a.right > box.right + 0.5 ? 'outside its card' : '',
            ...names.slice(i + 1).map(b => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom ? 'overlap' : '')]).filter(Boolean);
    })"""
    cards = page.locator("#gout .acard")
    assert cards.count() == 5 and cards.first.locator(".sk").all_inner_texts()[0].split() == ["+2", "Wish", "of", "Concentration"]
    assert cards.evaluate_all(clashes) == []
    page.set_viewport_size({"width": 2200, "height": 900})                      # five cards in a row on a wide screen
    assert cards.evaluate_all(clashes) == []


def test_gear_and_advice_shows_what_each_arcana_card_you_have_holds(app_page, app_url):
    """Under YOURS a card you have showed only its name, level and keep / replace. It now shows its deity stat, its
    skill options at their levels laid out as the target options are, and how many of its option levels they fill
    (0.2.389); the copied text has them. A card in advice kept before 0.2.389 shows its skill options alone."""
    kept = copy.deepcopy(KEPT)
    chalice = kept["arcana"]["slots"]["Arcana Chalice"]
    chalice["owned"] = [
        {"name": "Chalice of Vigor", "grade": "Unique", "enchant": 3, "icon": None, "equipped": True,
         "skills": {"Flame Arrow": 2, "Hellfire": 1, "Robe of Flame": 4}, "gain": 0.017, "verdict": "keep",
         "deity": {"label": "Time [Siel]", "points": 20.0, "source": "card"}, "stats": [["HP", "+100"]],
         "options": {"used": 7, "of": 7}, "skill_ids": {"Flame Arrow": 15210000, "Hellfire": 15060000, "Robe of Flame": 15740000}},
        {"name": "Chalice of Magic", "grade": "Rare", "enchant": 1, "icon": None, "skills": {"Blaze": 1}, "gain": 0.004,
         "verdict": "below average for its grade and level: replace when a better roll comes"}]
    page = app_page
    gear(page, last={**KEPT_LAST, "advice": kept})
    go(page, app_url, "#/gear")
    card = page.locator("#gout .acard").first
    card.wait_for()
    mine = card.locator("[data-arcana-mine]")
    assert mine.count() == 2
    first, second = mine.nth(0), mine.nth(1)
    assert first.locator(".deity").inner_text() == "Time [Siel] +20"
    assert [t.split() for t in first.locator(".sk").all_inner_texts()] == [
        ["+2", "Flame", "Arrow"], ["+1", "Hellfire"], ["+4", "Robe", "of", "Flame"]]
    assert "15210000" in first.locator(".sk img").first.get_attribute("src")
    assert "HP +100" in first.inner_text() and "Unique · 7 of 7 option levels · equipped" in first.inner_text()
    assert second.locator(".deity").count() == 0 and second.locator(".sk").all_inner_texts()[0].split() == ["+1", "Blaze"]
    assert "15050000" in second.locator(".sk img").first.get_attribute("src")         # from the slot's pool ids
    rows = card.locator(".owned")
    assert rows.nth(0).locator(".small").all_inner_texts() == ["Chalice of Vigor +3", "+1.7%"]
    assert rows.nth(0).locator(".chip").inner_text() == "keep" and rows.nth(1).locator(".chip").inner_text() == "replace"
    text = page.evaluate("() => window.__copy['adv-arcana']")
    assert "Arcana Chalice: Chalice of Vigor (Time [Siel] +20) — " in text
    assert "  yours: Chalice of Vigor +3, Time [Siel] +20 — Flame Arrow +2, Hellfire +1, Robe of Flame +4 (+1.7%, keep)" in text
    assert "  yours: Chalice of Magic +1 — Blaze +1 (+0.4%, replace)" in text


def test_gear_and_advice_ranks_defense_titles_and_says_when_to_keep_the_worn_item(app_page, app_url):
    """Every Defense title is purely defensive, so the slot said only "No title for this slot adds damage"; it is
    ranked by the damage its titles take off a boss's hits (0.2.371), the best one owned first. A slot whose worn
    item no replacement beats (enchanted to +15 and rerolled) says so where the next goal would be."""
    kept = copy.deepcopy(KEPT)
    kept["titles"]["owned_known"] = True
    kept["titles"]["slots"]["Defense"] = {"equipped": None, "best_owned": None, "best": [], "guard": {
        "kinds": ["Damage Tolerance", "PvE Damage Tolerance", "Boss Damage Tolerance"], "equipped": None,
        "best": [{"name": "Wall of Test", "grade": "Epic", "equip": "PvE Damage Tolerance +4.5%", "owned_bonus": "HP +100",
                  "cut": 0.045, "owned": False}],
        "best_owned": {"name": "Small Test Wall", "grade": "Rare", "equip": "Damage Tolerance +3%", "owned_bonus": "—",
                       "cut": 0.03, "owned": True}}}
    kept["doll"]["Shoulder"] = {"worn": {"name": "Test Pauldrons", "grade": "Unique", "icon": None, "item_level": 86,
                                         "enchant": 11, "skills": [], "rolls": None, "source": "equipped"},
                                "wear": None, "wear_gain": None, "next": None, "best": None, "steps": [],
                                "keep": {"item_level": 86, "gain": 0.0576}}
    page = app_page
    gear(page, last={**KEPT_LAST, "advice": kept})
    go(page, app_url, "#/gear")
    page.locator("#gout .pdoll").wait_for()
    defense = page.locator("#gout .tcol", has_text="Defense title")
    assert "No title for this slot adds damage. Ranked by how much they cut a boss's damage" in defense.inner_text()
    assert "Wall of Test" in defense.inner_text() and "−4.5% damage taken" in defense.inner_text()
    assert defense.locator(".tplate", has_text="Best you own").locator(".gname").inner_text() == "❖ Small Test Wall ❖"
    page.click('[data-dslot="Shoulder"]')
    card = page.locator("#dslotinfo")
    assert "iLv 86 · +11" in card.inner_text()
    assert card.locator("[data-keep] .small").inner_text() == (
        "No replacement beats yours enchanted to +15 and rerolled toward good rolls (+5.8%): enchant and reroll it, "
        "as the upgrade path says.")
