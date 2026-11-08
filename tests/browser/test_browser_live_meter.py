"""The Live Meter page (0.2.342): Start, the overlay, the session buttons, the view controls and the run's
status stay in view; the capture settings (network interface, game port, name override, game installation,
final boss) and the diagnostics sit under a closed "Advanced capture", which remembers being opened and
opens by itself when the player has a choice to make there. Npcap shows above it only when it needs doing.
Start asks for a capture and leaves recording raw game traffic to its saved setting; a capture catching up
on a heavy fight says so."""
import json
import urllib.request

from apphelpers import go, put_back, until


def visible(page, selector: str) -> bool:
    return page.locator(selector).first.is_visible()


def test_advanced_capture_starts_closed_and_holds_the_capture_settings(app_page, app_url):
    page = app_page
    go(page, app_url, "#/meter")
    advanced = page.locator("#madvanced")
    assert advanced.evaluate("d => d.open") is False
    for everyday in ("#msrc", "#mstart", "#mautooverlay", "#movl", "#mscope", "#msegments", "#mrun"):
        assert page.locator(everyday).evaluate("(n, d) => !d.contains(n)", advanced.element_handle()), everyday
    page.select_option("#msrc", "a2tools")
    for setting in ("#miface", "#mport", "#mchar", "#minstall", "#mfinalboss", "#mrecord", "#mautometa"):
        assert page.locator(setting).evaluate("(n, d) => d.contains(n)", advanced.element_handle()), setting
        assert not visible(page, setting), setting
    page.locator("#madvanced > summary").click()
    assert visible(page, "#miface") and visible(page, "#mfinalboss")
    page.wait_for_function("localStorage.getItem('meter-advanced-open') === '1'")   # the toggle event saves it
    go(page, app_url, "#/meter")                                             # remembered
    assert page.locator("#madvanced").evaluate("d => d.open") is True
    page.locator("#madvanced > summary").click()
    page.wait_for_function("localStorage.getItem('meter-advanced-open') === '0'")
    go(page, app_url, "#/meter")
    assert page.locator("#madvanced").evaluate("d => d.open") is False


def test_it_opens_by_itself_when_a_game_copy_must_be_chosen(app_page, app_url):
    page = app_page
    choice = {"installations": [{"id": "a", "label": "C:/Games/AION2"}, {"id": "b", "label": "D:/AION2"}],
              "selected": "", "selection_required": True}
    page.route("**/api/meter/installations", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                body=json.dumps(choice)))
    go(page, app_url, "#/meter")
    assert page.locator("#madvanced").evaluate("d => d.open") is True
    assert "choose the copy you play" in page.locator("#minstallstatus").inner_text()


def npcap(page, app_url, state: dict) -> None:
    page.route("**/api/npcap", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(state)))
    go(page, app_url, "#/meter")


def test_npcap_shows_above_the_meter_only_when_it_needs_doing(app_page, app_url):
    page = app_page
    npcap(page, app_url, {"supported": True, "installed": False, "detection_error": None, "status": "idle"})
    assert visible(page, "#npcap") and "Npcap is required for Live Capture" in page.locator("#npcap").inner_text()
    assert page.get_by_role("button", name="Install Npcap").is_visible()


def test_an_installed_npcap_is_a_line_under_advanced_capture(app_page, app_url):
    page = app_page
    npcap(page, app_url, {"supported": True, "installed": True, "detection_error": None, "status": "idle"})
    assert not visible(page, "#npcap")
    assert "Npcap is installed" in page.locator("#npcapinfo").text_content()


def test_the_maps_page_loads_the_provider_only_when_asked(app_page, app_url):
    page = app_page
    asked = []
    page.route("https://interactivemap.app/**", lambda r: (asked.append(r.request.url), r.abort()))
    go(page, app_url, "#/maps")
    assert not asked and page.locator("[data-map-frame]").is_hidden()
    page.get_by_role("button", name="Load the interactive map").click()
    page.locator("[data-map-frame]").wait_for(state="visible")
    assert until(page, lambda: asked)



def test_the_maps_page_draws_the_abyss_pvp_heat_map(app_page, app_url, community):
    """The log server's heat map (0.2.389): the busiest server matchup first, its window, fights and squares, a table
    of the busiest squares, a square's hits and kills under the pointer, and the square size asked again and kept."""
    page = app_page
    page.route("https://interactivemap.app/**", lambda r: r.abort())
    since = len(community.requests)
    go(page, app_url, "#/maps")
    assert community.reached(page, "/api/v1/pvp-heat?map=20&cell=2000&matchup=nae-1", since)
    status = page.locator("[data-heat-status]")
    status.filter(has_text="Israphel vs Zikel (NA East), the last 24 hours").wait_for()
    text = status.text_content()
    assert "9 fights from 4 uploaders, 57 PvP hits and 3 kills in 3 squares" in text
    assert "1 square only one uploader recorded is left out" in text
    choice = page.locator("[data-heat-matchup]")
    assert choice.input_value() == "nae-1"
    assert choice.locator("optgroup").get_attribute("label") == "NA East"
    assert choice.locator("option").all_text_contents() == ["Israphel vs Zikel · last 24 h", "Siel vs Nezekan · too few uploaders yet",
                                                            "Every server, pooled"]
    canvas = page.locator("[data-heat-canvas]")
    assert canvas.is_visible()
    assert "of Israphel vs Zikel (NA East): 3 squares with PvP over the last 24 hours, the busiest with 31 hits" in canvas.get_attribute("aria-label")
    legend = page.locator("[data-heat-legend]").text_content()
    assert "PvP hits per square" in legend and "31" in legend and "a square with a kill" in legend and "a recorded boss" in legend
    # the canvas is drawn: the busiest square is in the ramp's brightest step on the dark theme
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    s = (box["height"] - 24) / 12000                          # bounds 12,000 units each way, 12 px of padding a side
    ox = round((box["width"] - (12000 * s + 24)) / 2)
    x, y = box["x"] + ox + 12 + 5000 * s, box["y"] + 12 + (4000 + 3000) * s     # the middle of square (2, -2)
    colour = page.evaluate("""([x, y]) => { const c = document.querySelector('[data-heat-canvas]'), r = c.getBoundingClientRect(),
        d = window.devicePixelRatio || 1, p = c.getContext('2d').getImageData(Math.round((x - r.left + 18) * d), Math.round((y - r.top + 18) * d), 1, 1).data;
        return [p[0], p[1], p[2]]; }""", [x, y])
    assert colour == [0x9e, 0xc5, 0xf4]
    # under the pointer: the square's hits and kills, and where it is
    page.mouse.move(x, y)
    tip = page.locator("[data-heat-tip]")
    tip.wait_for(state="visible")
    assert tip.text_content() == "31 PvP hits2 killsx 4,000 to 6,000 · y -4,000 to -2,000"
    page.mouse.move(box["x"] + 2, box["y"] + 2)
    tip.wait_for(state="hidden")
    # the busiest squares as a table
    page.locator("[data-heat-table] summary").click()
    first = page.locator("[data-heat-rows] tbody tr").first.locator("td")
    assert first.all_text_contents() == ["4,000 to 6,000", "-4,000 to -2,000", "31", "2"]
    # another square size asks again, and is kept for the next visit
    since = len(community.requests)
    page.select_option("[data-heat-cell]", "4000")
    assert community.reached(page, "/api/v1/pvp-heat?map=20&cell=4000&matchup=nae-1", since)
    assert page.evaluate("localStorage.getItem('aion2.maps.heatCell')") == "4000"
    go(page, app_url, "#/maps")
    assert page.locator("[data-heat-cell]").input_value() == "4000"


def test_each_server_matchup_has_its_own_heat_map(app_page, app_url, community):
    """A matchup with too few uploaders says so, every server pooled is one choice, and the choice is kept."""
    page = app_page
    page.route("https://interactivemap.app/**", lambda r: r.abort())
    go(page, app_url, "#/maps")
    status = page.locator("[data-heat-status]")
    status.filter(has_text="Israphel vs Zikel").wait_for()
    since = len(community.requests)
    page.select_option("[data-heat-matchup]", "nae-2")
    assert community.reached(page, "/api/v1/pvp-heat?map=20&cell=2000&matchup=nae-2", since)
    status.filter(has_text="Not enough recorded Abyss PvP for Siel vs Nezekan (NA East) yet").wait_for()
    assert "at least 3 uploaders within 7 days, and has 1 uploader" in status.text_content()
    assert page.locator("[data-heat-table]").is_hidden()
    assert page.evaluate("localStorage.getItem('aion2.maps.heatMatchup')") == "nae-2"
    since = len(community.requests)
    page.select_option("[data-heat-matchup]", "all")
    assert community.reached(page, "/api/v1/pvp-heat?map=20&cell=2000&matchup=all", since)
    status.filter(has_text="Every server, the last 24 hours").wait_for()
    # the kept choice is asked for straight away on the next visit
    page.select_option("[data-heat-matchup]", "nae-2")
    since = len(community.requests)
    go(page, app_url, "#/maps")
    assert community.reached(page, "/api/v1/pvp-heat?map=20&cell=2000&matchup=nae-2", since)
    assert page.locator("[data-heat-matchup]").input_value() == "nae-2"
    assert not any(path.endswith("/api/v1/pvp-heat?map=20&cell=2000") for method, path in community.requests[since:])


def test_the_heat_map_says_when_too_few_uploaders_recorded_abyss_pvp(app_page, app_url):
    page = app_page
    page.route("https://interactivemap.app/**", lambda r: r.abort())
    from community import HEAT
    sparse = {**HEAT, "available": False, "window_seconds": None, "fights": 0, "uploaders": 0, "hits": 0, "kills": 0,
              "hidden_cells": 0, "cells": [], "matchups": [],          # a log server before 0.2.169: one pooled map
              "windows": [{**w, "uploaders": min(w["uploaders"], 2)} for w in HEAT["windows"]]}
    page.route("**/api/community?path=%2Fapi%2Fv1%2Fpvp-heat*", lambda r: r.fulfill(json=sparse))
    go(page, app_url, "#/maps")
    status = page.locator("[data-heat-status]")
    status.filter(has_text="Not enough recorded Abyss PvP for every server yet").wait_for()
    assert "at least 3 uploaders within 7 days, and has 2 uploaders" in status.text_content()
    assert "Meanwhile the map shows the ground recordings have covered." in status.text_content()
    assert page.locator("[data-heat-canvas]").is_visible() and page.locator("[data-heat-table]").is_hidden()
    assert "no PvP squares" in page.locator("[data-heat-canvas]").get_attribute("aria-label")
    assert page.locator("[data-heat-matchup] option").all_text_contents() == ["Every server, pooled"]


def meter_says(page, snapshot: dict = None, **status) -> None:
    """The app's meter status (GET /api/meter, which the page polls) with these fields set."""
    def answer(route):
        if route.request.method != "GET":
            return route.continue_()
        body = route.fetch().json()
        body.update(status)
        if snapshot is not None:
            body["snapshot"] = {**(body.get("snapshot") or {}), **snapshot}
        route.fulfill(json=body)
    page.route("**/api/meter", answer)
    page.route("**/api/meter?*", answer)
    if snapshot and snapshot.get("players"):
        page.route("**/api/meter/log*", lambda r: r.abort())         # the review panel's log of a fight the app never had


def test_the_scope_choice_is_kept_between_visits(app_page, app_url):
    page = app_page
    go(page, app_url, "#/meter")
    first = page.locator("#mscope").input_value()
    assert first == "party"                                               # the page's default
    page.select_option("#mscope", "self")
    assert page.evaluate("localStorage.getItem('meter-scope')") == "self"
    go(page, app_url, "#/meter")
    assert page.locator("#mscope").input_value() == "self"
    page.evaluate("localStorage.setItem('meter-scope', 'everyone')")      # not a scope: ignored
    go(page, app_url, "#/meter")
    assert page.locator("#mscope").input_value() == first


PLAYER = {"id": 7, "key": "7", "name": "Sorc", "class": "sorcerer", "dps": 12000, "share": 1.0, "server_name": "Zikel",
          "total": 120000, "hits": 40}


def test_odyle_energy_shugo_keys_and_nightmare_tickets_show_under_the_players(app_page, app_url):
    page = app_page
    meter_says(page, {"players": [PLAYER], "duration": 10, "dps": 12000, "odyle": {"regular": 145, "bonus": 50},
                      "shugo_keys": {"regular": 3, "bonus": 0}, "nightmare_tickets": {"regular": 2, "bonus": 1}})
    go(page, app_url, "#/meter")
    page.wait_for_selector("#mview .pmeters")
    lines = page.locator("#mview p.odyle").all_inner_texts()
    assert [line.split("  ")[0].strip() for line in lines] == ["Odyle Energy 195 (145 + 50 bonus)", "Shugo Keys 3",
                                                               "Nightmare Tickets 3 (2 + 1 bonus)"]
    icon = page.locator("#mview p.odyle img")                        # the app's own copy of the game's icon
    assert "/static/game-assets/" in icon.get_attribute("src") and icon.evaluate("i => i.complete && i.naturalWidth > 0")
    assert page.locator("#mview p.odyle i.keyicon").count() == 1 and page.locator("#mview p.odyle i.ticketicon").count() == 1


def test_the_identity_line_names_the_world_and_the_game_version_note_stays_folded(app_page, app_url):
    page = app_page
    meter_says(page, identity={"id": 31, "name": "Sorc", "verified": True, "serverId": 2102},
               automatic_metadata={"installed_build": "2.0.6.0", "installed_build_source": "game files", "status": "ready"})
    go(page, app_url, "#/meter")
    page.wait_for_function("(document.querySelector('#midentity') || {}).textContent.includes('Sorc')")
    identity = page.locator("#midentity").inner_text()
    assert identity.startswith("Detected automatically: Sorc · Zikel · combat entity #31") and "server 2102" not in identity
    page.locator("#madvanced > summary").click()
    note = page.locator("details:has(> summary#mautometa-sum)")
    assert note.evaluate("d => d.open") is False
    assert page.locator("#mautometa-sum").inner_text().startswith("Installed game version: 2.0.6.0 (game files) · ")
    diagnostics = page.locator("details.note:has(> summary b:text('Capture diagnostics'))")
    assert diagnostics.count() == 1 and diagnostics.evaluate("d => d.open") is False


def test_a_capture_catching_up_on_a_heavy_fight_says_so(app_page, app_url):
    page = app_page
    meter_says(page, snapshot={"decode_backlog": {"catching_up": True, "queue_depth": 4200}})
    go(page, app_url, "#/meter")
    page.wait_for_function("(document.querySelector('#mdiagerror') || {}).textContent.includes('catching up')")
    assert ("Live view is catching up (4200 packets queued) during a heavy fight; final totals are unaffected."
            in page.locator("#mdiagerror").text_content())                      # under Advanced capture


def test_start_asks_for_a_capture_and_leaves_recording_to_its_saved_setting(app_page, app_url):
    page = app_page
    sent = []

    def meter(route):
        if route.request.method != "POST":
            return route.continue_()
        sent.append(json.loads(route.request.post_data))
        with urllib.request.urlopen(app_url + "api/meter", timeout=10) as answer:          # as it is, not started
            status = json.load(answer)
        route.fulfill(json={**status, "running": False, "error": "the test stops here"})
    page.route("**/api/meter", meter)
    go(page, app_url, "#/meter")
    page.select_option("#msrc", "replay")
    page.click("#mstart")
    page.wait_for_function("document.querySelector('#mnotice').textContent === 'the test stops here'")
    start, = [body for body in sent if body.get("action") == "start"]
    assert (start["source"], start["scope"]) == ("replay", "party") and "record_packets" not in start


def test_a_moment_can_be_marked_and_the_latest_mark_labelled_afterwards(app_page, app_url):
    """Labelled moments (0.2.365): Mark stamps what the player saw on the capture's clock, the list shows it, and
    Label the latest gives the newest mark (a hotkey press, say) its label and note."""
    page = app_page
    go(page, app_url, "#/meter")
    page.locator("#madvanced").evaluate("d => d.open = true")
    page.locator("#madvanced details").last.evaluate("d => d.open = true")
    # the marking controls show only with Record TCP payloads enabled (0.2.366): a mark is only useful with the payloads
    assert page.locator("#mmarkbox").is_hidden() and not page.is_checked("#mrecord")
    try:
        page.check("#mrecord")
        page.wait_for_function("!document.querySelector('#mmarkbox').hidden")
        _mark_and_relabel(page, app_url)
        page.uncheck("#mrecord")
        page.wait_for_function("document.querySelector('#mmarkbox').hidden")
    finally:
        put_back(page, {"meter_record_packets": False})


def _mark_and_relabel(page, app_url):
    page.select_option("#mmarklabel", "shield")
    page.fill("#mmarknote", "the templar's shield took the whole hit")
    page.click("#mmark")
    page.wait_for_function("document.querySelector('#mmarks').textContent.includes('shield')")
    assert "the templar's shield took the whole hit" in page.locator("#mmarks").inner_text()
    assert page.input_value("#mmarknote") == ""
    page.select_option("#mmarklabel", "interrupt")
    page.fill("#mmarknote", "it was the cast that got cut")
    page.click("#mrelabel")
    page.wait_for_function("document.querySelector('#mmarks').textContent.includes('interrupt')")
    text = page.locator("#mmarks").inner_text()
    assert "it was the cast that got cut" in text and "shield" not in text          # relabelled, not added
    with urllib.request.urlopen(app_url + "api/meter/marks", timeout=10) as answer:
        marks = json.load(answer)["marks"]
    assert [m["label"] for m in marks] == ["interrupt"] and marks[0]["source"] == "button"
