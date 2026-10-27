"""Reading the game's screen on Gear & Advice (aion2calc/screenread): a read of the Genus Insight panel, the
hotkey's included, fills the Genus editor's draft with the lines to check marked, and nothing is saved until Save
genus lines; the Title window pages read are listed with their "Show unacquired titles only" box, which the player
can correct, and the titles they say are owned go into the list only when the player puts them there. Where
Windows' text recognition is missing (these test machines), the row says why."""
import json
import re
import time
import urllib.parse

from apphelpers import go, until
from test_browser_pages import CHARACTER, gear

CHECK = "250 is outside what slot 2 rolls for Boss Defense"
FERA = {"id": 3, "at": time.time(), "source": "hotkey", "size": [1920, 1080], "kind": "genus", "genus": "Fera", "level": 8,
        "notes": [], "lines": [{"slot": i + 1, "stat": stat, "value": value, "read": f"{stat} {value}", "check": check}
                               for i, (stat, value, check) in enumerate([
                                   ("Fera Defense", "49", ""), ("Boss Defense", "250", CHECK),
                                   ("Power Shard Damage Bonus", "7", ""), ("MP", "18", ""), ("MP", "9", ""),
                                   ("MP", "6", ""), ("PvE Defense", "89", ""), ("PvE Defense", "79", "")])]}
OWNED, UNACQUIRED = ["Shaper of Heavens", "Pruning Expert"], ["Unbound by Genus"]
TITLES = {"pages": [{"id": 4, "at": time.time(), "titles": UNACQUIRED, "unacquired_only": None, "collection": None}],
          "unacquired": [], "seen": [], "owned": OWNED, "basis": "catalog", "faction": "elyos", "faction_titles": 359,
          "collection": {"owned": 2, "total": 359}, "notes": ["1 page did not show whether “Show unacquired titles only” was ticked: choose it for each in the list of pages."]}


def windows_reads(page, reads):
    """The screen-read API of a Windows computer whose hotkey has read ``reads``; what is posted is listed."""
    posted = []

    def answer(route):
        if route.request.method == "POST":
            posted.append(json.loads(route.request.post_data))
            return route.fulfill(json=TITLES)
        since = int(urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query).get("since", ["0"])[0])
        route.fulfill(json={"available": True, "message": "en-US", "latest": max(r["id"] for r in reads),
                            "reads": [r for r in reads if r["id"] > since]})
    page.route(re.compile(r"/api/screen-read(\?|$)"), answer)
    page.route(re.compile(r"/api/screen-read/titles\?character="), lambda route: route.fulfill(json=TITLES))
    return posted


def test_a_hotkey_read_of_the_genus_panel_fills_the_draft_for_the_player_to_check_and_save(app_page, app_url):
    page = app_page
    gear(page)
    windows_reads(page, [FERA])
    saved = []

    def save(route):
        saved.append(json.loads(route.request.post_data))
        route.fulfill(json={"genus": saved[-1]["genus"], "items": [], "titles_owned": []})
    page.route(re.compile(r"/api/inventory/genus$"), save)
    go(page, app_url, "#/gear")
    editor = page.locator("#genus-editor")
    editor.get_by_text("Read from the game: 8 lines of Fera Insight, level 8, 1 to check (marked).").wait_for()
    assert editor.locator('[data-genus-tab="Fera"]').get_attribute("aria-pressed") == "true"
    assert editor.locator("[data-genus-level]").input_value() == "8"
    assert editor.locator('[data-genus-slot="3"][data-genus-field="stat"]').input_value() == "Power Shard Damage Bonus"
    flagged = editor.locator(".gslot.gflag")
    assert flagged.count() == 1 and "Check: " + CHECK in flagged.inner_text()
    assert "Read Fera Insight Lv 8: 8 lines, 1 to check." in page.locator("#genus-read [data-sr-status]").inner_text()
    assert saved == []                                                       # nothing is saved by a read
    editor.locator('[data-genus-slot="2"][data-genus-field="value"]').fill("108")
    assert editor.locator(".gslot.gflag").count() == 0                       # the line the player corrected
    editor.locator("[data-genus-save]").click()
    until(page, lambda: saved)
    fera = saved[0]["genus"]["Fera"]
    assert saved[0]["character"] == CHARACTER["key"] and fera["level"] == 8
    assert [(line["slot"], line["stat"], line["value"]) for line in fera["lines"]][:3] == [
        (1, "Fera Defense", "49"), (2, "Boss Defense", "108"), (3, "Power Shard Damage Bonus", "7")]


def test_the_title_pages_read_are_listed_and_their_titles_go_into_the_list_when_asked(app_page, app_url):
    page = app_page
    gear(page)
    posted = windows_reads(page, [{**FERA, "id": 1}])
    go(page, app_url, "#/gear")
    summary = page.locator("#gtread-summary")
    summary.locator("[data-tuse]").wait_for()
    assert "Not acquired yet: 0 · you own: 2 · Elyos: 359 titles in the app's catalog · the game counts 2 of 359" in summary.inner_text()
    assert page.locator("#gtit").input_value() == ""                         # not in the list until asked
    summary.locator("[data-tuse]").click()
    assert page.locator("#gtit").input_value() == "\n".join(OWNED)
    page.locator("#gtit").fill("Unbound by Genus")
    summary.locator("[data-tadd]").click()
    assert page.locator("#gtit").input_value() == "\n".join(["Unbound by Genus", *OWNED])
    summary.locator('[data-tpage="4"]').select_option("true")
    until(page, lambda: posted)
    assert posted[0] == {"action": "page", "page": 4, "unacquired_only": True, "character": CHARACTER["key"]}


def test_without_windows_text_recognition_the_row_says_why(app_page, app_url):
    page = app_page
    gear(page)
    go(page, app_url, "#/gear")
    status = page.locator("#genus-read [data-sr-status]")
    page.wait_for_function("document.querySelector('#genus-read [data-sr-status]')?.textContent.includes('Windows')")
    assert "works on Windows only" in status.inner_text()
    assert page.locator("#genus-read [data-sr-screen]").is_disabled()
