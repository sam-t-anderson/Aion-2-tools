"""The Combat Logs page: the website's tabs (browse, speed, boss progression, build points) and the app's own
Personal records tab, each showing its panel alone; the log server's fights, newest first with mini-bosses
hidden until asked for, each opening at its own fight; the recordings saved on this computer, by type; and
the panels for the player's uploads (with the appeal against a moderator's hold) and characters; and a fight's
review: its details tabs, its enemies by name, a comparison from a pasted link, the fight combined from every
recording of it, an arena match's result and rounds, and a PvP opponent's side of the fight; and an analyzed fight's
breakdown."""
import json

import pytest

from apphelpers import axe_findings, close_context, go, open_context, watched_page
from community import FIGHTS, LOG_ID, PART_LOG_ID

TABS = ("community", "speed", "progression", "points", "extras")


def test_each_tab_shows_its_own_panel(app_page, app_url, community):
    page = app_page
    since = len(community.requests)
    go(page, app_url, "#/combat")
    for tab in TABS:
        page.click(f'#logs-tabs [data-tab="{tab}"]')
        shown = page.eval_on_selector_all("[data-logs-panel]", "ps => ps.filter(p => !p.hidden).map(p => p.dataset.logsPanel)")
        assert shown == [tab], f"{tab}: shows {shown}"
        assert page.locator(f'#logs-tabs [data-tab="{tab}"]').get_attribute("aria-selected") == "true"
    page.wait_for_function("document.querySelector('#records-extra h3')")         # the app's extras, sectioned
    assert "Personal records" in page.locator("#records-extra").inner_text()
    for route in ("/api/v1/run-leaderboard", "/api/v1/encounter-progression", "/api/v1/progression", "/api/v1/performance"):
        assert community.reached(page, route, since), f"no {route} request reached the log server"


def test_the_speed_tab_names_each_runs_bosses_and_shows_its_time(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat")
    page.click('#logs-tabs [data-tab="speed"]')
    page.wait_for_selector("#speed-body table")
    cells = page.locator("#speed-body tr").nth(1).locator("td").all_inner_texts()
    assert cells[:5] == ["1 of 2", "Gelcos → Ereshkigal", "Transcendence · stage 2", "2:31", "5"]


def test_speed_and_progression_take_the_community_logs_filters(app_page, app_url, community):
    """Completed-run speed and Boss progression filter as the community logs do, the log server applying the filter,
    with mini-bosses out of the boss list until shown (0.2.372)."""
    page = app_page
    go(page, app_url, "#/combat")
    for tab, prefix, route in (("speed", "sf", "/api/v1/run-leaderboard"), ("progression", "pf", "/api/v1/encounter-progression")):
        page.click(f'#logs-tabs [data-tab="{tab}"]')
        page.wait_for_selector(f"#{prefix}-boss")
        bosses = lambda: page.locator(f"#{prefix}-boss option").all_inner_texts()
        assert "Gatekeeper Testlord" in bosses() and "Watcher Testling" not in bosses()     # the mini-boss is hidden
        page.check(f"#{prefix}-mini")
        page.wait_for_function(f"[...document.querySelectorAll('#{prefix}-boss option')].some(o => o.textContent === 'Watcher Testling')")
        page.uncheck(f"#{prefix}-mini")
        for facet in ("difficulty", "encounter_type", "region", "game_patch", "party_size"):
            assert page.locator(f"#{prefix}-{facet}").count() == 1, f"{tab}: no {facet} filter"
        since = len(community.requests)
        page.select_option(f"#{prefix}-difficulty", "Normal")
        assert community.reached(page, route, since), f"{tab}: no request after choosing a difficulty"
        assert any(path.startswith(route) and "difficulty=Normal" in path for _, path in community.requests[since:]), tab
        page.click(f"#{prefix}-clear")
        page.wait_for_function(f"document.querySelector('#{prefix}-difficulty').value === ''")


def test_the_extras_tab_holds_only_the_apps_own_sections(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat")
    page.click('#logs-tabs [data-tab="extras"]')
    page.wait_for_function("document.querySelector('#records-extra h3')")
    extras = page.locator("#records-extra")
    assert extras.locator("h3").all_inner_texts() == ["Class performance", "Personal records", "Character consistency and trends"]
    assert extras.locator("summary").first.inner_text() == "Recorded boss defeats"    # what the website's tabs do not show


def test_the_lists_tabs_show_the_servers_logs_the_uploads_and_the_saved_logs(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat")
    shown = lambda: page.eval_on_selector_all("[data-log-panel]", "ps => ps.filter(p => !p.hidden).map(p => p.dataset.logPanel)")
    assert shown() == ["community"]
    for tab in ("owned", "saved", "identities", "community"):
        page.click(f"#log-tab-{tab}")
        assert shown() == [tab] and page.locator(f"#log-tab-{tab}").get_attribute("aria-selected") == "true"
    assert page.locator("#log-tab-identities").inner_text() == "My Character Identities"
    assert page.locator("#log-panel-owned #my-characters").count() == 0                # its own tab, not under My Uploads
    page.focus("#log-tab-community")
    page.keyboard.press("ArrowRight")                                                 # the arrow keys move along them
    assert shown() == ["owned"] and page.evaluate("document.activeElement.id") == "log-tab-owned"
    page.keyboard.press("End")
    assert shown() == ["identities"]
    page.keyboard.press("ArrowLeft")
    assert shown() == ["saved"]
    saved = page.locator("#log-panel-saved")
    for words in ("Recorded encounters by type", "Upload recordings", "Analyzed encounters"):
        assert saved.locator("h3", has_text=words).count() == 1, words
    assert saved.locator("#ref").is_visible()                                         # an AbyssLogs link to analyze


def test_the_saved_logs_share_row_offers_public_first_and_saves_with_the_server(app_page, app_url, community):
    page = app_page
    sent = []

    def logserver(route):
        if route.request.method != "POST":
            return route.continue_()
        sent.append(json.loads(route.request.post_data))                              # kept from the app: the tests share it
        route.fulfill(json={"url": community.url, "visibility": "private", "has_key": True})
    page.route("**/api/logserver", logserver)
    go(page, app_url, "#/combat")
    page.click("#log-tab-saved")
    page.wait_for_selector("#lsvis")
    assert page.eval_on_selector_all("#lsvis option", "os => os.map(o => o.value)") == ["public", "unlisted", "legion", "private"]
    assert page.locator("#lsvis").input_value() == "public" and page.locator("#lsurl").input_value() == community.url
    page.select_option("#lsvis", "private")
    page.click("#lssave")
    page.get_by_text("Saved", exact=True).wait_for()
    assert sent == [{"url": community.url, "key": None, "visibility": "private"}]


def test_the_servers_fights_open_at_their_own_fight(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat")
    page.wait_for_selector("#comm-table table.t")
    final, mini = FIGHTS[0][1], FIGHTS[1][1]
    listed = page.locator("#comm-table").inner_text()
    assert final in listed and mini not in listed                                    # a mini-boss only when asked for
    page.check("#cf-mini")
    page.wait_for_function("name => document.querySelector('#comm-table').innerText.includes(name)", arg=mini)
    page.uncheck("#cf-mini")
    page.wait_for_function("name => !document.querySelector('#comm-table').innerText.includes(name)", arg=mini)
    page.locator(f'[data-logs-open="{LOG_ID}"]').first.click()
    page.wait_for_function("location.hash.startsWith('#/combat-log/shared/')")
    assert page.evaluate("location.hash") == f"#/combat-log/shared/{LOG_ID}?mode=pve&segment={FIGHTS[0][0]}"


def recording(name="Testsorc"):
    local = "p:1101:1"
    hits = [{"t": float(t), "player": local, "target": "boss", "skill_id": 15210000, "damage": 2000.0} for t in range(30)]
    return {"format": "a2log", "version": 1, "meta": {"title": "Test session", "capture_scope": "party",
                                                      "uploader": {"name": name, "verified": True}},
            "players": [{"id": local, "name": name, "class": "Sorcerer", "server": "1101"}],
            "segments": [{"label": "Trash", "duration": 8.0, "hits": [{"t": 0.0, "player": local, "skill_id": 15210000, "damage": 10.0}]},
                         {"label": "Gatekeeper Testlord", "boss": "Gatekeeper Testlord", "duration": 30.0, "killed": True,
                          "encounter_type": "dungeon", "ping_recorder": local,
                          "entities": [{"id": "boss", "name": "Gatekeeper Testlord", "kind": "enemy", "is_boss": True}],
                          "hits": hits}]}


def test_saved_recordings_are_listed_by_type_and_open_at_their_fight(app_page, app_url, app_home):
    page = app_page
    name = "session-20261020-200000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(recording()), encoding="utf-8")
    try:
        go(page, app_url, "#/combat")
        page.click("#log-tab-saved")
        page.wait_for_selector("#saved-browse [data-open]")
        assert page.locator("h3", has_text="Recorded encounters by type").count() == 1
        assert "Gatekeeper Testlord" in page.locator("#saved-browse").inner_text()
        page.locator("#saved-browse [data-open]").first.click()
        page.wait_for_function("location.hash.startsWith('#/combat-log/local/')")
        assert page.evaluate("location.hash") == f"#/combat-log/local/{name}?segment=1"
        page.wait_for_function("document.querySelector('#page-title').textContent !== 'Combat Logs'")
    finally:
        page.goto("about:blank")                          # the review page reads the file while it is open
        path.unlink()


def test_saved_logs_filter_by_boss_and_day(app_page, app_url, app_home):
    """Saved logs take a boss, type, role, difficulty and a day range (0.2.372)."""
    page = app_page
    other = recording()
    other["segments"][1].update(label="Watcher Testling", boss="Watcher Testling")
    other["segments"][1]["entities"][0]["name"] = "Watcher Testling"
    files = {"session-20261020-200000-abcdef.a2log.json": recording(), "session-20261021-200000-bcdefa.a2log.json": other}
    for name, doc in files.items():
        (app_home / "logs").mkdir(exist_ok=True)
        (app_home / "logs" / name).write_text(json.dumps(doc), encoding="utf-8")
    try:
        go(page, app_url, "#/combat")
        page.click("#log-tab-saved")
        page.wait_for_selector('#saved-browse [data-slf="boss"]')
        rows = lambda: page.locator("#saved-browse tr:has([data-open])").all_inner_texts()
        page.wait_for_function("document.querySelectorAll('#saved-browse tr [data-open]').length >= 2")
        assert any("Gatekeeper Testlord" in r for r in rows()) and any("Watcher Testling" in r for r in rows())
        page.select_option('#saved-browse [data-slf="boss"]', "Watcher Testling")
        page.wait_for_function("![...document.querySelectorAll('#saved-browse tr')].some(r => r.querySelector('[data-open]') && r.textContent.includes('Gatekeeper Testlord'))")
        assert rows() and all("Watcher Testling" in r for r in rows())
        page.fill('#saved-browse [data-slf="from"]', "2099-01-01")
        page.dispatch_event('#saved-browse [data-slf="from"]', "change")
        page.wait_for_function("document.querySelectorAll('#saved-browse tr [data-open]').length === 0")
        page.click("#saved-browse [data-slf-clear]")
        page.wait_for_function("document.querySelectorAll('#saved-browse tr [data-open]').length >= 2")
    finally:
        page.goto("about:blank")
        for name in files:
            (app_home / "logs" / name).unlink()


def test_my_uploads_filter_by_title_and_visibility(app_page, app_url):
    """My uploads take a search, the original server and the visibility (0.2.372)."""
    page = app_page
    uploads = [{"server": "https://logs.example", "id": f"Upload{n}0000", "title": title, "delete_token": "t" * 32,
                "created_at": 1793000000 + n} for n, title in enumerate(("Testlord clear", "Testling wipe"))]

    def ownership(route):
        if route.request.method == "GET":
            return route.fulfill(json=uploads)
        body = json.loads(route.request.post_data)
        public = body["owner"]["id"] == uploads[0]["id"]
        route.fulfill(json={"visibility": "public" if public else "private", "url": "https://logs.example/l/" + body["owner"]["id"]})
    page.route("**/api/log-ownership", ownership)
    go(page, app_url, "#/combat")
    page.click("#log-tab-owned")
    page.wait_for_selector('#owned-logs [data-owf="q"]')
    titles = lambda: [r for r in page.locator("#owned-logs tbody tr").all_inner_texts() if "Upload" in r]
    assert len(titles()) == 2
    page.fill('#owned-logs [data-owf="q"]', "wipe")
    page.wait_for_function("document.querySelector('#owned-logs').innerText.includes('1 of 2 uploads match')")
    assert len(titles()) == 1 and "Testling wipe" in titles()[0]
    assert page.evaluate("document.activeElement.dataset.owf") == "q"                  # typing stays in the box
    page.click("#owned-logs [data-owf-clear]")
    for button in page.locator('#owned-logs [data-action="refresh"]').all():
        button.click()
    page.wait_for_function("document.querySelector('#owned-logs').innerText.includes('public')")
    page.select_option('#owned-logs [data-owf="visibility"]', "private")
    page.wait_for_function("document.querySelector('#owned-logs').innerText.includes('1 of 2 uploads match')")
    assert "Testling wipe" in titles()[0]


HELD = {"server": "https://logs.example", "id": "Held12345", "title": "Held run", "delete_token": "t" * 32, "created_at": 1793000000}


def test_a_held_upload_can_be_appealed_once_with_a_reason(app_page, app_url):
    page = app_page
    sent = []

    def ownership(route):
        if route.request.method == "GET":
            return route.fulfill(json=[HELD])
        body = json.loads(route.request.post_data)
        sent.append(body)
        status = {"visibility": "private", "url": "https://logs.example/l/Held12345",
                  "moderation": {"note": "reported as not a real fight"}}
        if body.get("action") == "appeal" or any(b.get("action") == "appeal" for b in sent[:-1]):
            status["appeal"] = {"status": "open", "created_at": 1793000100}
        route.fulfill(json=status)
    page.route("**/api/log-ownership", ownership)
    go(page, app_url, "#/combat")
    page.click("#log-tab-owned")
    page.locator('#owned-logs [data-action="refresh"]').first.click()
    page.wait_for_function("document.querySelector('#owned-logs').innerText.includes('Moderator review: reported as not a real fight')")
    page.locator("#owned-logs summary", has_text="Appeal this hold").click()
    page.fill('#owned-logs [data-statement="0"]', "too short")
    page.click('#owned-logs [data-appeal="0"]')
    assert "at least 10 characters" in page.locator("#owned-logs [data-message]").inner_text()
    assert not [b for b in sent if b.get("action") == "appeal"]
    page.fill('#owned-logs [data-statement="0"]', "It was a real boss fight; the recording shows the kill.")
    page.click('#owned-logs [data-appeal="0"]')
    page.wait_for_function("document.querySelector('#owned-logs').innerText.includes('Appeal sent')")
    appeal, = [b for b in sent if b.get("action") == "appeal"]
    assert appeal == {"owner": HELD, "action": "appeal", "statement": "It was a real boss fight; the recording shows the kill."}
    assert page.locator('#owned-logs [data-appeal="0"]').count() == 0                     # one appeal per hold


def test_your_characters_reads_the_claims_kept_by_the_app(app_page, app_url):
    page = app_page
    with page.expect_response(lambda r: r.url.endswith("/api/identity-claims") and r.request.method == "GET") as answer:
        go(page, app_url, "#/combat")
        page.click("#log-tab-identities")
    assert answer.value.ok
    page.wait_for_function("document.querySelector('#log-panel-identities #my-characters').children.length > 0")


def test_a_link_opens_my_character_identities_directly(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat/identities")
    page.wait_for_selector("#log-panel-identities:not([hidden])")
    assert page.locator("#log-tab-identities").get_attribute("aria-selected") == "true"


def moving_recording(casts=False):
    """A boss fight with recorded movement (0.2.350): the boss walks east, the party member moves and once shows
    up far away (back at a respawn point), and the recording player is placed only by the effects they apply. The
    trash fight before it has the recording player's movement and no boss. With ``casts`` (0.2.363) the boss casts
    twice, at the party member and on the ground away from everyone, and an add appears mid-fight."""
    doc = recording()
    me, ally = "p:1101:1", "p:1101:2"
    if casts:
        fight = doc["segments"][1]
        fight["entities"].append({"id": "add1", "name": "Summoned Spike", "kind": "enemy"})
        fight["npc_casts"] = [{"t": 4.0, "source": "boss", "skill_id": 123, "skill": "Trample", "target": ally, "pos": [900.0, 940.0, 50.0], "facing": 90.0},
                              {"t": 14.0, "source": "boss", "skill_id": 124, "skill": "Meteor", "target": ally, "pos": [1500.0, 1300.0, 50.0], "facing": 45.0}]
        fight["movement"] = [{"t": float(t), "entity": "add1", "x": 1300.0, "y": 1100.0, "z": 50.0, "src": "move"} for t in range(12, 30, 2)]
    doc["players"].append({"id": ally, "name": "Testally", "class": "Cleric", "server": "1101"})
    fight = doc["segments"][1]
    fight["movement"] = fight.get("movement", []) + (
        [{"t": float(t), "entity": "boss", "x": 1000.0 + 20 * t, "y": 1000.0, "z": 50.0, "src": "move", "heading": 90.0} for t in range(30)]
        + [{"t": float(t), "entity": ally, "x": 900.0, "y": 900.0 + 10 * t, "z": 50.0, "src": "move"} for t in range(0, 30, 2) if t != 20]
        + [{"t": 20.0, "entity": ally, "x": 50000.0, "y": 50000.0, "z": 50.0, "src": "party"}]
        + [{"t": float(t), "entity": me, "x": 1100.0, "y": 950.0 + 5 * t, "z": 50.0, "src": "applied"} for t in range(0, 30, 3)])
    fight["movement"].sort(key=lambda m: m["t"])
    doc["segments"][0]["movement"] = [{"t": float(t), "entity": me, "x": 30.0 * t, "y": 0.0, "z": 50.0, "src": "applied"} for t in range(8)]
    return doc


def test_the_movement_replay_plays_the_recorded_positions(app_page, app_url, app_home):
    page = app_page
    name = "session-20261027-200000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moving_recording()), encoding="utf-8")
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        note = box.locator("p").first.inner_text()
        assert "of 3 players and enemies" in note and "does not send the recording player's own movement" in note
        assert box.locator("[data-tokens] circle").count() == 3
        assert box.locator("[data-tokens] circle[stroke-dasharray]").count() == 1          # the recording player is marked
        # the key below the replay: the kinds of token this fight holds, then its players in their class colours
        key = box.locator(".cr-key")
        assert key.locator('ul[aria-label="Key"] li').all_inner_texts() == [
            "Boss", "Recording player", "Movement in the last 6 seconds",
            "Faded: last seen over 8 seconds ago, or outside the fight area; gone once unseen for 20 seconds (a minute for players and bosses)", "Arena"]
        players = key.locator('ul[aria-label="Players"] li')
        texts = players.all_inner_texts()
        assert [t.split(" ")[0] for t in texts] == ["Testsorc", "Testally"], texts       # the recording player first
        assert texts[0].endswith("Sorcerer") and texts[1].endswith("Cleric")
        assert players.nth(0).locator("circle[stroke-dasharray]").count() == 1            # ringed as on the replay
        assert players.nth(1).locator("circle[stroke-dasharray]").count() == 0
        # unticking an entry hides it: the party member, then the boss and the trails; Show all brings them back
        assert key.locator("[data-key-showall]").is_hidden()
        players.nth(1).locator("input").uncheck()
        assert box.locator("[data-tokens] circle").count() == 2 and key.locator("[data-key-showall]").is_visible()
        key.locator('[data-key-toggle="boss"]').uncheck()
        key.locator('[data-key-toggle="trail"]').uncheck()
        assert box.locator("[data-tokens] circle").count() == 1 and box.locator("[data-tokens] polyline").count() == 0
        key.locator("[data-key-showall]").click()
        assert box.locator("[data-tokens] circle").count() == 3 and key.locator("[data-key-showall]").is_hidden()

        def scrub(t):
            page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
        scrub(20.5)                  # the party member's far position is drawn faded at the edge, not stretching the view
        far = box.locator("[data-tokens] circle", has=page.locator("title", has_text="outside the fight area"))
        assert far.count() == 1 and far.get_attribute("fill-opacity") == "0.35"
        scrub(10)
        assert box.locator("[data-tokens] circle", has=page.locator("title", has_text="outside the fight area")).count() == 0
        page.click("[data-play]")
        page.wait_for_function("parseFloat(document.querySelector('[data-clock]').textContent) >= 10.5")
        page.click("[data-play]")                                               # pauses
        assert page.locator("[data-play]").inner_text() == "Play"
    finally:
        page.goto("about:blank")
        path.unlink()


INSIDE_THE_ARENA = """() => {
    // every token not marked outside the fight area, at the scrubbed time, against the drawn arena
    const room = document.querySelector('[data-room] .cr-room');
    const box = room.tagName === 'circle'
        ? {x: +room.getAttribute('cx'), y: +room.getAttribute('cy'), r: +room.getAttribute('r')}
        : {x: +room.getAttribute('x') + room.getAttribute('width') / 2, y: +room.getAttribute('y') + room.getAttribute('height') / 2,
           r: room.getAttribute('width') / 2};
    return [...document.querySelectorAll('[data-tokens] circle')].filter(c => !c.textContent.includes('outside the fight area'))
        .map(c => [+c.getAttribute('cx'), +c.getAttribute('cy')])
        .every(([x, y]) => room.tagName === 'circle' ? Math.hypot(x - box.x, y - box.y) <= box.r + 0.01
                                                     : Math.abs(x - box.x) <= box.r + 0.01 && Math.abs(y - box.y) <= box.r + 0.01);
}"""


def test_a_boss_fights_replay_draws_its_arena_as_a_circle_or_a_square(app_page, app_url, app_home):
    """The replay draws the boss room around the ground the fight covered (0.2.353): a circle unless the viewer
    picks a square, which is remembered, and the Raid Planner gets the same arena. A fight without a boss has none."""
    page = app_page
    name = "session-20261027-210000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moving_recording()), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        assert box.locator("[data-room-shape]").input_value() == "circle"
        assert box.locator("[data-room] circle.cr-room").count() == 1 and box.locator("[data-room] rect").count() == 0
        for t in (0, 9.5, 20.5, 29):                     # at 20.5 s the party member far away is left out, faded
            scrub(t)
            assert page.evaluate(INSIDE_THE_ARENA), f"a token outside the circle at {t} s"
        assert box.locator(".cr-key [data-key-room] circle").count() == 1                 # the key's arena follows the shape
        box.locator("[data-room-shape]").select_option("square")
        assert box.locator("[data-room] rect.cr-room").count() == 1 and box.locator("[data-room] circle").count() == 0
        assert box.locator(".cr-key [data-key-room] rect").count() == 1
        box.locator('.cr-key [data-key-toggle="arena"]').uncheck()
        assert box.locator("[data-room] *").count() == 0
        box.locator('.cr-key [data-key-toggle="arena"]').check()
        assert box.locator("[data-room] rect.cr-room").count() == 1
        for t in (0, 9.5, 29):
            scrub(t)
            assert page.evaluate(INSIDE_THE_ARENA), f"a token outside the square at {t} s"
        # the choice holds for the next log opened on this computer
        page.reload()
        box.locator("[data-tokens] circle").first.wait_for()
        assert box.locator("[data-room-shape]").input_value() == "square" and box.locator("[data-room] rect.cr-room").count() == 1
        # the Raid Planner's map is the arena, with every position on it; a token hidden on the replay comes hidden
        box.locator('.cr-key [data-key-toggle="id:p:1101:2"]').uncheck()
        box.locator("[data-plan]").click()
        page.wait_for_function("location.hash === '#/raid'")
        plans = page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans')))")
        plan, = [p for p in plans if p.get("meta", {}).get("name") == "Gatekeeper Testlord"]
        assert plan["arena"] == {"kind": "square"}
        frames = [k for token in plan["tokens"] for k in token["keyframes"]]
        assert frames and all(0 <= k["x"] <= 1 and 0 <= k["y"] <= 1 for k in frames)
        boss, = [token for token in plan["tokens"] if token["id"] == "boss"]
        assert boss["keyframes"][-1]["x"] - boss["keyframes"][0]["x"] > 0.1                 # the boss walks east
        assert [t["id"] for t in plan["tokens"] if t.get("hidden")] == ["p:1101:2"]
        # the trash fight before it has movement but no boss, so no arena
        go(page, app_url, f"#/combat-log/local/{name}?segment=0")
        box.locator("[data-tokens] circle").first.wait_for()
        assert box.locator("[data-room-shape]").count() == 0 and box.locator("[data-room] *").count() == 0
        assert box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts() == [             # no boss, no arena
            "Movement in the last 6 seconds", "Faded: last seen over 8 seconds ago, or outside the fight area; gone once unseen for 20 seconds (a minute for players and bosses)"]
    finally:
        page.goto("about:blank")
        path.unlink()


def test_the_raid_planner_imports_a_saved_fights_movement(app_page, app_url, app_home, tmp_path):
    """Raid Planner → Import recorded movement (0.2.353): the saved recordings with movement, their fights, and one of
    them as a new plan with a token per player, pet and enemy that moved; Import file takes a recording too."""
    page = app_page
    name = "session-20261027-220000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moving_recording()), encoding="utf-8")
    try:
        go(page, app_url, "#/raid")
        logs = page.locator("#rmovelog")
        logs.wait_for()
        option, = [o for o in logs.locator("option").all() if o.get_attribute("value") == name]
        assert "Gatekeeper Testlord" in option.inner_text()
        logs.select_option(name)
        page.wait_for_selector("#rmovefight")
        assert page.locator("#rmovefight option").all_inner_texts() == ["Trash · 8 s", "Gatekeeper Testlord · 30 s"]
        page.locator("#rmovefight").select_option("1")
        page.click("#rmoveimport")
        page.wait_for_function("document.querySelector('#rname') && document.querySelector('#rname').value === 'Gatekeeper Testlord'")
        assert page.locator("#arena .rtoken").count() == 3 and page.locator("#arena.circle").count() == 1
        plans = page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans')))")
        plan, = [p for p in plans if p.get("meta", {}).get("name") == "Gatekeeper Testlord"]
        assert sorted(t["kind"] for t in plan["tokens"]) == ["enemy", "player", "player"] and plan["duration"] == 30.0
        # tokens can be hidden by kind or one by one; the plan keeps them, marked hidden
        visible = lambda: page.locator("#arena .rtoken:visible").count()          # noqa: E731
        page.locator('[data-showkind="enemy"]').uncheck()
        assert visible() == 2
        page.locator("#rshowlist summary").click()
        player = page.locator("[data-showtok]:checked").first.get_attribute("data-showtok")   # the boss is hidden
        page.locator(f'[data-showtok="{player}"]').uncheck()
        assert visible() == 1 and page.locator('[data-showkind="player"]').evaluate("c => c.indeterminate")
        plans = page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans')))")
        plan, = [p for p in plans if p.get("meta", {}).get("name") == "Gatekeeper Testlord"]
        assert sorted(t["kind"] for t in plan["tokens"] if t.get("hidden")) == ["enemy", "player"]
        page.locator('[data-showkind="enemy"]').check()
        page.locator('[data-showkind="player"]').check()
        assert visible() == 3 and page.locator("#rshowlist").get_attribute("open") is not None   # the list stays open
        # Import file: a recording file lists its fights the same way
        upload = tmp_path / "fight.a2log.json"
        upload.write_text(json.dumps(moving_recording()), encoding="utf-8")
        page.set_input_files("#rimport", str(upload))
        page.wait_for_selector("#rmovefight")
        assert page.locator("#rmovefight option").count() == 2
    finally:
        page.goto("about:blank")
        path.unlink()


def test_a_shared_fights_replay_adds_the_other_recordings_of_it(app_page, app_url, community):
    """Log server 0.2.144 merges a fight's movement from every public recording of it: the recording player's own
    path comes from a party member's upload. When the rankings name another upload of the fight, the review says so
    in view and the replay merges it without being asked (0.2.356)."""
    page = app_page
    since = len(community.requests)
    go(page, app_url, f"#/combat-log/shared/{LOG_ID}?segment=2")
    box = page.locator("[data-replay]")
    page.wait_for_function("document.querySelector('[data-replay]')?.textContent.includes('Merged with 1 of 1 other recordings')")
    assert community.reached(page, f"/api/v1/logs/{LOG_ID}/movement", since)
    shared = page.locator("p.note", has_text="Also recorded by")
    assert shared.is_visible() and "Testcleric" in shared.inner_text()
    assert "The movement replay below merges its movement with this recording's." in shared.inner_text()
    text = box.inner_text()
    assert "Testcleric's recording (clock -3.00 s from 40 shared hits, 45 positions)" in text
    assert "comes from 45 positions in the other recordings" in text and box.locator("[data-merge]").count() == 0
    page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", 31)
    assert box.locator("[data-tokens] circle", has=page.locator("title", has_text="from Testcleric's recording")).count() == 1


def test_a_recording_without_movement_takes_it_from_the_others(app_page, app_url, community):
    """A recording made before 0.2.350 holds no movement, but the log server merges a newer recording of the same
    fight into it. The rankings name no other upload of this fight, so the replay asks before it looks."""
    page = app_page
    go(page, app_url, f"#/combat-log/shared/{LOG_ID}?segment=1")
    box = page.locator("[data-replay]")
    box.locator("[data-merge]").wait_for()
    assert "holds no movement" in box.inner_text() and box.locator("svg").count() == 0
    box.locator("[data-merge]").click()
    page.wait_for_function("document.querySelector('[data-replay] [data-tokens] circle')")
    text = box.inner_text()
    assert "Testcleric's recording (clock -3.00 s from 40 shared hits, 40 positions)" in text
    assert box.locator("[data-tokens] circle").count() == 2 and box.locator("[data-merge]").count() == 0


def casting_recording():
    """The boss fight with the recording player's casts (0.2.306), and the analysis the meter saves with them."""
    from aion2calc.combat.insights import summarize
    doc = recording()
    me = doc["players"][0]["id"]
    doc["segments"][1]["casts"] = [{"t": 3.0 * i, "source": me, "target": "boss", "skill_id": 15210000, "skill": "Flame Arrow",
                                    "cooldown_ms": 3000} for i in range(10)]
    doc["encounter_insights"] = summarize(doc)
    return doc


def _saved(app_home, name, doc):
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_the_profile_lookup_picks_the_characters_server_by_name(app_page, app_url, app_home):
    """A character's build offers the official lookup's server by name (0.2.375): the region's servers, Elyos then
    Asmodian, the recorded one chosen and kept when another region is shown; the lookup sends the chosen server."""
    page = app_page
    doc = recording()
    doc["meta"]["region"] = "nae"
    path = _saved(app_home, "session-20261103-120000-abcdef.a2log.json", doc)
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=1")
        page.locator('[data-character="p:1101:1"]').first.click()
        server, region = page.locator("select[data-profile-server]"), page.locator("select[data-profile-region]")
        server.wait_for()
        assert server.input_value() == "1101" and region.input_value() == "nae"
        names = server.locator("option").all_inner_texts()
        assert names[0] == "Choose a server" and {"Siel", "Zikel"} <= set(names) and "Gauss" not in names
        assert server.locator("optgroup").evaluate_all("groups => groups.map(g => g.label)") == ["Elyos", "Asmodian"]
        region.select_option("eu")                        # another region's servers, the recorded one still offered
        assert "Gauss" in server.locator("option").all_inner_texts() and server.input_value() == "1101"
        server.select_option("")
        page.click("[data-profile-current]")
        page.wait_for_function("document.querySelector('[data-profile-message]').textContent.includes('home server')")
        server.select_option("1321")
        page.route("**/api/character/profile", lambda route: route.fulfill(json={"status": "unavailable", "reason": "Stand-in"}))
        with page.expect_request("**/api/character/profile") as sent:
            page.click("[data-profile-current]")
        body = json.loads(sent.value.post_data)
        assert body["player"]["server"] == "1321" and body["region"] == "eu"
    finally:
        page.goto("about:blank")
        path.unlink()


def test_the_details_open_on_the_ability_contribution_and_switch_between_tabs(app_page, app_url, app_home):
    """Ability contribution, Abilities, Skills and the cast timeline are tabs of one section that opens on the ability
    contribution, drawn at the page's own text size (0.2.357). The Rotation tab keeps the totals."""
    page = app_page
    path = _saved(app_home, "session-20261031-200000-abcdef.a2log.json", casting_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=1")
        details = page.locator(".cr-details")
        details.locator(".cr-bar").first.wait_for()
        tabs = details.locator("[data-detail]")
        assert tabs.all_inner_texts() == ["Ability contribution", "Abilities", "Skills", "Cast timeline", "Hide"]
        assert "primary" in tabs.nth(0).get_attribute("class")
        assert details.locator(".cr-bar").count() == 1 and "Testsorc" in details.locator(".cr-bar-name").inner_text()
        size = "s => getComputedStyle(document.querySelector(s)).fontSize"
        assert page.evaluate(size, ".cr-details .cr-bar-name") == page.evaluate(size, ".cr-review .t td")
        tabs.nth(1).click()
        assert "per second" in details.locator("table").inner_text().lower() and details.locator(".cr-bar").count() == 0
        tabs.nth(2).click()
        skills = details.locator("table").inner_text()
        assert "cooldown usage" in skills.lower() and "Flame Arrow" in skills
        tabs.nth(3).click()
        assert details.locator(".cr-timeline svg.cr-track:not(.cr-time-axis)").count() == 1
        tabs.nth(4).click()
        assert details.locator("table, .cr-bars, .cr-timeline").count() == 0
        rotation = page.locator(".cr-actions", has_text="Casts, buffs and break gauge")
        assert "skill casts" in rotation.inner_text().lower() and "cooldown usage" not in rotation.inner_text().lower()
        assert "Cast timeline" not in rotation.locator("h4").all_inner_texts()
    finally:
        path.unlink()


def enemies_recording():
    """A boss fight whose boss the game registered twice, with three adds of one name, and four unnamed summons that
    struck the recording player and that nobody struck."""
    doc = recording()
    me, fight = doc["players"][0]["id"], doc["segments"][1]
    enemy = lambda ref, name, code, boss=False: {"id": ref, "name": name, "kind": "enemy", "mob_code": code, "is_boss": boss}
    fight["entities"] = [enemy("boss", "Gatekeeper Testlord", 2390001, True), enemy("boss2", "Gatekeeper Testlord", 2390099, True),
                         *(enemy(f"add{i}", "Testling Add", 2920001) for i in range(3)),
                         *(enemy(f"sum{i}", "Unnamed summon", 2920521) for i in range(4))]
    hit = lambda t, target, amount: {"t": float(t), "kind": "damage", "source": me, "target": target, "skill_id": 15210000, "amount": amount}
    fight["events"] = sorted([hit(t, "boss" if t < 15 else "boss2", 2000.0) for t in range(30)]
                             + [hit(t + 0.5, f"add{t % 3}", 500.0) for t in range(6)]
                             + [{"t": 10.0 + i, "kind": "damage", "source": f"sum{i}", "target": me, "skill_id": 29205210, "amount": 800.0}
                                for i in range(4)], key=lambda e: e["t"])
    return doc


def test_enemies_are_listed_by_name_with_unnamed_summons_nobody_struck_folded(app_page, app_url, app_home):
    """One row per enemy name, the boss first: a boss registered twice and an add's spawns are one row each, counted
    and filtered together. Unnamed summons the party never struck are folded away with what they did (0.2.357)."""
    page = app_page
    path = _saved(app_home, "session-20261031-210000-abcdef.a2log.json", enemies_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=1")
        heading = page.locator("h3", has_text="Enemy encounters")
        heading.wait_for()
        listed = page.locator("h3:text-is('Enemy encounters') + .cr-scroll tbody tr")
        rows = [" ".join(r.split()) for r in listed.all_inner_texts()]
        assert len(rows) == 2, rows
        assert rows[0].startswith("Gatekeeper Testlord ×2 Filter (boss)") and "2390001, 2390099" in rows[0] and "60,000" in rows[0]
        assert rows[1].startswith("Testling Add ×3 Filter") and "3,000" in rows[1]
        folded = page.locator("details.cr-folded")
        assert folded.locator("summary").inner_text() == "4 unnamed summons the party never struck"
        assert not folded.locator("table").is_visible()
        folded.locator("summary").click()
        assert "struck the party 4 times" in folded.inner_text() and "Unnamed summon ×4" in folded.locator("tbody").inner_text()
        party = page.locator(".cr-review tr", has_text="Testsorc").first
        assert "63,000" in party.inner_text()
        listed.nth(0).locator("[data-enemy-filter]").click()
        assert page.locator('[data-enemy-filter="boss,boss2"]').get_attribute("class").split()[-1] == "primary"
        assert "60,000" in page.locator(".cr-review tr", has_text="Testsorc").first.inner_text()
    finally:
        path.unlink()


def test_a_log_to_compare_can_be_pasted_as_its_link(app_page, app_url, community):
    """The compare box takes another log's link as well as its ID, and opens the encounter the link names; anything
    else is refused before the log server is asked (0.2.357)."""
    page = app_page
    go(page, app_url, f"#/combat-log/shared/{LOG_ID}?segment=2")
    box = page.locator("[data-compare]")
    box.wait_for()
    since = len(community.requests)
    box.fill("not a log link")
    page.click("[data-compare-go]")
    assert "Paste another log's link, or its ID" in page.locator("[data-compare-result]").inner_text()
    assert not any("/raw" in path for _, path in community.requests[since:])
    box.fill(f"https://sam-t-anderson.github.io/Aion-2-tools/log.html?id={LOG_ID}&segment=1")
    page.click("[data-compare-go]")
    page.locator("[data-compare-segment]").wait_for()
    assert page.locator("[data-compare-segment]").input_value() == "1"
    assert community.reached(page, f"/api/v1/logs/{LOG_ID}/raw", since)


def test_a_shared_fight_combines_the_other_recordings_of_it(app_page, app_url, community):
    """Log server 0.2.149 combines a fight's combat records from every public recording of it. The review offers it
    beside "Also recorded by", shows where its records came from, goes back on request and on another encounter."""
    page = app_page
    go(page, app_url, f"#/combat-log/shared/{LOG_ID}?segment=2")
    button = page.locator("[data-view-combined]")
    button.wait_for()
    assert button.inner_text() == "Combine all 2 recordings of this fight"
    players = "p:has-text('DPS uses shared active damage time') + .cr-scroll tr"
    healer = lambda: " ".join(page.locator(players, has_text="Testcleric").inner_text().split())
    assert "9,000" not in healer()
    since = len(community.requests)
    button.click()
    banner = page.locator("[data-combined-fight]")
    banner.wait_for()
    assert community.reached(page, f"/api/v1/logs/{LOG_ID}/combined?segment=2", since)
    text = " ".join(banner.inner_text().split())
    assert "Combined fight · 2 recordings" in text and "This recording" in text
    assert "Testcleric -3.00 s · 40 shared hits 2 events, 3 MP readings" in text
    assert "9,000" in healer() and page.locator("[data-view-combined]").count() == 0      # Testcleric's own heals
    page.click("[data-own-recording]")
    assert banner.count() == 0 and "9,000" not in healer()
    page.click("[data-view-combined]")
    banner.wait_for()
    page.select_option('[data-control="segment"]', "1")
    page.wait_for_function("!document.querySelector('[data-combined-fight]')")
    page.select_option('[data-control="segment"]', "2")
    page.locator("[data-view-combined]").wait_for()
    assert banner.count() == 0 and "9,000" not in healer()


def arena_recording():
    """A lost arena match from the game's own records (0.2.361): the recording player won the first round and the
    opponent the next three, and each round's loser has a death marker that names the winner."""
    doc = recording()
    me, fight, foe = doc["players"][0]["id"], doc["segments"][1], "2:7001"
    death = lambda t, target, source: {"t": t, "kind": "death", "target": target, "source": source}
    fight.update(label="Combat 2", boss=None, killed=False, encounter_type="pvp_arena", zone="Impetusium Arena",
                 entities=[{"id": foe, "name": "Testfoe", "kind": "enemy", "is_player": True, "class": "gladiator", "server": "1107"}],
                 hits=[{**h, "target": foe} for h in fight["hits"]],
                 events=[death(6.5, foe, me), death(14.0, me, foe), death(21.5, me, foe), death(29.5, me, foe)],
                 arena={"match": 16945404, "result": "loss", "rounds_won": 1, "rounds_lost": 3, "rating": 1505,
                        "fighters": [{"name": "Testme", "class": "sorcerer", "server": "1101", "faction": "asmodian", "level": 45,
                                      "rating": 1530, "ref": me, "self": True},
                                     {"name": "Testfoe", "class": "gladiator", "server": "1107", "faction": "elyos", "level": 45,
                                      "rating": 1548, "ref": foe}],
                        "rounds": [{"round": 1, "t": 6.5, "winner": 0, "loser": 1}, {"round": 2, "t": 14.0, "winner": 1, "loser": 0},
                                   {"round": 3, "t": 21.5, "winner": 1, "loser": 0}, {"round": 4, "t": 29.5, "winner": 1, "loser": 0}]})
    return doc


def test_an_arena_match_shows_its_result_rating_fighters_and_rounds(app_page, app_url, app_home):
    """The arena's own records name the match's result, score and rating change, its fighters and every round's winner
    (0.2.361); a PvP fight without them keeps the note that nothing of the kind is inferred."""
    page = app_page
    path = _saved(app_home, "session-20261031-220000-abcdef.a2log.json", arena_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=1")
        card = page.locator("[data-arena-match]")
        card.wait_for()
        assert " ".join(card.locator("h3").inner_text().split()) == "Arena match · Loss 1–3 · Rating 1530 → 1505 (−25)"
        fighters, rounds = card.locator("table").nth(0).locator("tbody tr"), card.locator("table").nth(1).locator("tbody tr")
        me, foe = (" ".join(fighters.nth(i).inner_text().split()) for i in (0, 1))
        assert "Testsorc" in me and "(recording player)" in me and "Asmodian" in me and me.endswith("1530 1")   # the log's own name
        assert "Testfoe" in foe and "gladiator" in foe and "Elyos" in foe and foe.endswith("1548 3")
        assert rounds.count() == 4
        assert [" ".join(rounds.nth(i).inner_text().split()).split()[1] for i in range(4)] == ["0:06.50", "0:14.00", "0:21.50", "0:29.50"]
        assert "Testfoe" in rounds.nth(3).locator("td").nth(2).inner_text() and "Testsorc" in rounds.nth(3).locator("td").nth(3).inner_text()
        assert "kill credit are not inferred" not in page.locator(".cr-review").inner_text()
    finally:
        path.unlink()
    doc = arena_recording()
    del doc["segments"][1]["arena"]
    path = _saved(app_home, "session-20261031-230000-abcdef.a2log.json", doc)
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=1")
        page.locator(".cr-review").wait_for()
        page.wait_for_function("document.querySelector('.cr-review').innerText.includes('kill credit are not inferred')")
        assert page.locator("[data-arena-match]").count() == 0
    finally:
        path.unlink()


def pvp_recording(opponent_casts=True):
    """A one-against-one arena match, a Templar recording against a Ranger: each one's hits on the other, the Templar's
    shields recorded with the Ranger as their source (as a meter before 0.2.399 recorded an absorb), the Ranger's own heal,
    casts and buff, crowd control both ways, and each round's loser dying, the arena's death marker naming the winner.
    Validated as the meter saves it, with the analysis that comes with that: the Ranger's casts have no cast time,
    which the game sends for the recording player only (0.2.398). Without ``opponent_casts`` the Ranger's casts and
    heal are not in it, as in a log the meter made before 0.2.398 (it recorded the party's casts only)."""
    from aion2calc.combat import a2log
    me, foe = "p:1101:1", "2:7001"
    effect = lambda t, end, target, source, skill, name, **extra: {"t": t, "end": end, "target": target, "source": source,  # noqa: E731
                                                                    "skill_id": skill, "skill": name, **extra}
    event = lambda t, source, target, skill, name, amount, kind="damage": {"t": float(t), "kind": kind, "source": source, "target": target,  # noqa: E731
                                                                           "skill_id": skill, "skill": name, "amount": amount}
    cast = lambda t, skill, name, **extra: {"t": t, "source": foe, "skill_id": skill, "skill": name, **extra}  # noqa: E731
    theirs = [event(t, foe, me, 14340000, "Tempest Shot", 1000.0) for t in range(1, 11)] + [event(t, foe, me, 14030000, "Rapid Fire", 600.0) for t in range(11, 16)]
    mine = [event(t, me, foe, 12010000, "Vicious Strike", 1500.0) for t in range(20, 28)]
    shields = [event(t, foe, me, 12320000, "Nezekan's Shield", 2000.0, "heal") for t in (2, 5, 8)]
    events = [*theirs, *mine, *shields, *([event(30, foe, foe, 14790000, "Revitalization Contract", 1500.0, "heal")] if opponent_casts else []),
              {"t": 16.0, "kind": "death", "target": me, "source": foe}, {"t": 18.0, "kind": "revive", "target": me},
              {"t": 28.0, "kind": "death", "target": foe, "source": me}]
    foe_casts = [*(cast(t, 14340000, "Tempest Shot", target=me, cooldown_ms=3000) for t in (0.9, 3.9, 6.9)),
                 cast(10.9, 14030000, "Rapid Fire", target=me, cooldown_ms=8000), cast(12.5, 14000100, "Dodge", cooldown_ms=500)]
    fight = {"label": "Combat 1", "duration": 40.0, "encounter_type": "pvp_arena", "zone": "Impetusium Arena", "ping_recorder": me,
             "party_members": [me],
             "entities": [{"id": foe, "name": "Testranger", "kind": "enemy", "is_player": True, "class": "Ranger", "server": "1107"}],
             "hits": [{"t": e["t"], "player": me, "target": foe, "skill_id": 12010000, "skill": "Vicious Strike", "damage": 1500.0} for e in mine],
             "events": sorted(events, key=lambda e: e["t"]),
             "casts": [*(foe_casts if opponent_casts else []),
                       {"t": 19.9, "source": me, "skill_id": 12010000, "skill": "Vicious Strike", "target": foe, "cooldown_ms": 6000}],
             "effects": [effect(12.0, 14.0, me, foe, 14070000, "Suppressing Arrow", ended="expired"),
                         effect(14.5, 16.0, me, foe, 14130000, "Snare Shot", ended="removed"),
                         effect(21.0, 23.0, foe, me, 12100000, "Shield Smite", ended="expired"),
                         effect(29.0, 35.0, foe, foe, 14790000, "Revitalization Contract", ended="expired")],
             "health": [{"t": 0.0, "entity": me, "current": 20000.0, "max": 20000.0}, {"t": 15.5, "entity": me, "current": 1500.0, "max": 20000.0},
                        {"t": 19.0, "entity": foe, "current": 20000.0, "max": 20000.0}, {"t": 24.0, "entity": foe, "current": 12000.0, "max": 20000.0},
                        {"t": 27.5, "entity": foe, "current": 2000.0, "max": 20000.0}],
             "arena": {"match": 16945405,
                       "fighters": [{"name": "Testtemplar", "class": "templar", "server": "1101", "faction": "asmodian", "rating": 1530, "ref": me, "self": True},
                                    {"name": "Testranger", "class": "ranger", "server": "1107", "faction": "elyos", "rating": 1548, "ref": foe}],
                       "rounds": [{"round": 1, "t": 16.0, "winner": 1, "loser": 0}, {"round": 2, "t": 28.0, "winner": 0, "loser": 1}]}}
    return a2log.validate({"format": "a2log", "version": 1, "meta": {"title": "Arena session", "capture_scope": "party",
                                                                  "uploader": {"name": "Testtemplar", "verified": True}},
                           "players": [{"id": me, "name": "Testtemplar", "class": "templar", "server": "1101"}], "segments": [fight]})


ME, FOE = "p:1101:1", "2:7001"
squash = lambda text: " ".join(text.split())                                                        # noqa: E731
#: the note on the heals between the two sides, which a meter before 0.2.399 recorded for a shield's absorbs
NOBODYS = ("Left out of everyone's healing: 3 heal records between the two sides, 6,000 as recorded (Nezekan's Shield ×3). "
           "They are shields' absorbs, which a meter before 0.2.399 recorded as heals by the attacker, of what was left of "
           "the shield. The log does not name the shields' casters, so they count for no one.")
SUMMARY = ".cr-review .cr-scroll table:has(th:text-is('HPS')) tbody tr"                     # the players' table


def older_heal_over_time_recording():
    """A boss fight a meter before 0.2.399 saved (0.2.385): a Cleric's Light of Regeneration recorded as its pool of
    5,946 when cast and then what was left of it at each of its 15 ticks, 47,616 in all, beside the Cleric's hits."""
    from aion2calc.combat import a2log
    me, boss = "p:1101:5", "2:9001"
    lor = lambda t, amount: {"t": float(t), "kind": "heal", "source": me, "target": me, "skill_id": 17090120,  # noqa: E731
                             "skill": "Light of Regeneration", "amount": float(amount)}
    hits = [{"t": float(t), "player": me, "target": boss, "skill_id": 17010000, "skill": "Earth's Wrath", "damage": 2000.0}
            for t in range(0, 60, 5)]
    events = [lor(10, 5946), *(lor(10 + 2 * k, 5946 - 396 * k) for k in range(1, 16)),
              *({"t": h["t"], "kind": "damage", "source": me, "target": boss, "skill_id": 17010000, "skill": "Earth's Wrath",
                 "amount": 2000.0} for h in hits)]
    fight = {"label": "Testboss", "boss": "Testboss", "duration": 60.0, "encounter_type": "expedition", "party_members": [me],
             "entities": [{"id": boss, "name": "Testboss", "kind": "enemy", "is_boss": True}],
             "hits": hits, "events": sorted(events, key=lambda e: e["t"])}
    return a2log.validate({"format": "a2log", "version": 1,
                           "meta": {"title": "Dungeon run", "capture_scope": "party",
                                    "capture_quality": {"decoder": "a2tools-python-v1", "app_version": "0.2.385"}},
                           "players": [{"id": me, "name": "Testcleric", "class": "cleric", "server": "1101"}],
                           "segments": [fight]})


def test_an_older_logs_heals_over_time_read_what_their_ticks_took(app_page, app_url, app_home):
    """A log a meter before 0.2.399 saved is rebuilt when the review reads it (0.2.404): the Light of Regeneration
    of 5,946 heals 15 ticks of 396, 5,940, not the 47,616 its records add up to, and the review says what it rebuilt."""
    page = app_page
    path = _saved(app_home, "session-20261106-010000-abcdef.a2log.json", older_heal_over_time_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=0")
        note = page.locator("[data-heals-over-time]")
        note.wait_for()
        assert squash(note.inner_text()) == (
            "Heals over time rebuilt: 16 heal records (Light of Regeneration ×16), 47,616 as recorded, now 5,940. A meter "
            "before 0.2.399 recorded a heal over time whole when it was cast and then, at each tick, what was left of it; "
            "each record now heals what the ticks since the one before took.")
        [row] = [squash(r) for r in page.locator(SUMMARY).all_inner_texts()]
        assert row.startswith("Testcleric") and " 5,940 99 " in f" {row} "                    # healing and HPS over 60 s
        assert "47,616" not in row
    finally:
        path.unlink()


def test_a_pvp_opponent_is_chosen_under_player_and_shows_their_side_of_the_fight(app_page, app_url, app_home):
    """In a PvP fight the Player menu offers the opponents beside the party, and one chosen reads the fight from their
    side as a party player's view does: their row in the table, whom they struck and who struck them, their abilities,
    skills, rotation and cast timeline, the buffs and debuffs on and from them, crowd control both ways, and the death
    recaps of their deaths and of the party's they struck in. The heal records between the two sides (the party's
    shields, recorded with them as the source) are left out of everyone's healing, with a note in both views."""
    page = app_page
    path = _saved(app_home, "session-20261109-200000-abcdef.a2log.json", pvp_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=0")
        menu = page.locator('[data-control="actor"]')
        menu.wait_for()
        assert menu.locator("optgroup").evaluate_all("groups => groups.map(g => g.label)") == ["Opponents"]
        assert [o.split(" · ")[0] for o in menu.locator("optgroup option").all_inner_texts()] == ["Testranger"]
        review = squash(page.locator(".cr-review").inner_text())
        assert "Choose an opponent under Player to see the fight from their side." in review
        assert NOBODYS in review                                                    # the party's view says so too
        party = [squash(r) for r in page.locator(SUMMARY).all_inner_texts()]
        assert len(party) == 1 and party[0].startswith("Testtemplar") and page.locator("[data-opponent]").count() == 0
        menu.select_option(FOE)
        card = page.locator("[data-opponent]")
        card.wait_for()
        text = squash(card.inner_text())
        assert text.startswith("Opponent · Testranger") and card.locator("h3").inner_text().endswith("· Ranger")
        assert ("Recorded: 15 hits of theirs, 8 hits on them, 1 heal, 5 casts, 4 buff and debuff records, 3 HP readings, 1 death marker. "
                "Not recorded: their positions.") in text
        dealt, taken = (squash(card.locator("table").nth(i).locator("tbody").inner_text()) for i in (0, 1))
        assert dealt.startswith("Testtemplar") and dealt.endswith("13,000 100.0% 15 1,000 867")      # DPS on their 15 active seconds
        assert taken.startswith("Testtemplar") and taken.endswith("12,000 100.0% 8 1,500 300")       # per second over the 40 s
        assert NOBODYS in text
        [row] = [squash(r) for r in page.locator(SUMMARY).all_inner_texts()]
        assert row.startswith("Testranger") and row.endswith("Ranger 13,000 867 12,000 1,500 38 1")
        # in the Ranger's colour: an entity's class is capitalised ("Ranger"), the colour table's keys are not
        assert page.locator(SUMMARY).first.locator("td").first.evaluate("td => getComputedStyle(td).color") == "rgb(170, 211, 114)"
        assert "red: their HP" in page.locator(".cr-graph").inner_text()
        details = page.locator(".cr-details")
        details.locator('[data-detail="abilities"]').click()
        abilities = [squash(r) for r in details.locator("tbody tr").all_inner_texts()]
        assert len(abilities) == 2 and abilities[0].startswith("Testranger") and "Tempest Shot 10 10,000 76.9% 667" in abilities[0]
        assert "Rapid Fire 5 3,000 23.1%" in abilities[1]
        details.locator('[data-detail="skills"]').click()
        skills = [squash(r) for r in details.locator("tbody tr").all_inner_texts()]
        assert "Tempest Shot 3 3.0s 3.0s 3 of 13 · 23.1% — 0:00.90 → 0:06.90" in skills[0]         # no cast time
        assert "Rapid Fire 1 — 8.0s 1 of 4 · 25.0%" in skills[1] and "Dodge 1" in skills[2]
        details.locator('[data-detail="casts"]').click()
        lane = details.locator(".cr-timeline svg.cr-track:not(.cr-time-axis)")
        assert lane.count() == 1 and lane.locator("g.cr-marker").count() == 5
        assert details.locator(".cr-timeline .cr-lane-name").inner_text().startswith("Testranger")
        actions = page.locator(".cr-actions:not(.cr-details)")
        assert squash(actions.locator("tbody tr").inner_text()).endswith("5 7.5 0 1")              # casts, per minute, procs, dodges
        actions.locator('[data-actions="effects"]').click()
        assert actions.locator("h4").all_inner_texts() == ["Buffs on them", "Your party's effects on them", "Their effects on others"]
        mine, ours, theirs = (squash(actions.locator("table").nth(i).locator("tbody").inner_text()) for i in range(3))
        assert "Revitalization Contract 15.0% 6.0s 1 Testranger" in mine and "Shield Smite 5.0% 2.0s 1 Testtemplar" in ours
        assert "Suppressing Arrow 5.0% 2.0s 1 Testranger" in theirs and "Snare Shot 3.8% 1.5s 1 Testranger" in theirs
        actions.locator('[data-actions="cc"]').click()
        assert actions.locator("h4").all_inner_texts() == ["Their crowd control on your party", "Your party's crowd control on them"]
        landed_on_us = [squash(r) for r in actions.locator("table").nth(0).locator("tbody tr").all_inner_texts()]
        assert len(landed_on_us) == 2 and landed_on_us[0].startswith("0:12.00 Testtemplar") and landed_on_us[0].endswith("Suppressing Arrow Stun 2.00s Ran its duration")
        assert landed_on_us[1].endswith("Snare Shot Slow soft 1.50s Removed early")
        assert squash(actions.locator("table").nth(1).locator("tbody").inner_text()).endswith("Shield Smite Stun 2.00s Ran its duration")
        page.click('[data-metric="deaths"]')
        recaps = page.locator("h3:text-is('Player death recaps') + p + .cr-scroll tbody tr")
        rows = [squash(r) for r in recaps.all_inner_texts()]
        assert len(rows) == 2 and rows[0].startswith("Testtemplar") and "16.000s 10.0s 8,000 2,000" in rows[0]   # struck by them
        assert rows[1].startswith("Testranger") and "28.000s 10.0s 12,000 0 2,000 / 20,000 at 27.500s" in rows[1]
        assert rows[1].endswith("Vicious Strike · 1,500 at 27.000s")
        recaps.nth(1).locator("[data-recap]").click()
        assert "death marker at 28.000s" in page.locator("h4", has_text="death marker at").inner_text()
        window = page.locator("h4:has-text('death marker at') + p + .cr-scroll tbody tr")
        assert window.count() == 8 and all("Vicious Strike" in r for r in window.all_inner_texts())
        page.click('[data-metric="summary"]')
        page.click('[data-view="timeline"]')
        lanes = page.locator("h3:text-is('Recorded effect timeline') ~ .cr-timeline .cr-lane-name")
        assert lanes.count() == 2 and lanes.nth(1).inner_text().startswith("Testranger")
        menu.select_option("")                                    # the party again, as before
        page.wait_for_function("!document.querySelector('[data-opponent]')")
        page.click('[data-view="table"]')
        assert [squash(r).split(" · ")[0] for r in page.locator(SUMMARY).all_inner_texts()] == ["Testtemplar"]
    finally:
        path.unlink()


def test_your_view_lists_the_crowd_control_you_took_and_what_the_log_lacks_reads_not_recorded(app_page, app_url, app_home):
    """The player's own view lists the crowd control an opponent landed on them, per state and per application; an
    analysis made before it was listed says so. An opponent whose casts and heals the log does not hold (a log the
    meter made before 0.2.398, which recorded the party's casts only) reads not recorded in their table row, Skills,
    Cast timeline and Rotation."""
    page = app_page
    actions = page.locator(".cr-actions:not(.cr-details)")
    path = _saved(app_home, "session-20261109-210000-abcdef.a2log.json", pvp_recording())
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=0")
        page.select_option('[data-control="actor"]', ME)
        actions.locator('[data-actions="cc"]').click()
        assert actions.locator("h4").all_inner_texts() == ["Each application", "Crowd control on your party", "Each application on your party"]
        taken = [squash(r) for r in actions.locator("h4:text-is('Crowd control on your party') + p + .cr-scroll tbody tr").all_inner_texts()]
        assert len(taken) == 2 and taken[0].startswith("Testtemplar") and taken[0].endswith("Stun 1 2.0s 1 0") and taken[1].endswith("Slow 1 1.5s 0 1")
        each = [squash(r) for r in actions.locator("h4:text-is('Each application on your party') + .cr-scroll tbody tr").all_inner_texts()]
        assert len(each) == 2 and "Testranger" in each[0] and each[0].endswith("Suppressing Arrow Stun 2.00s Ran its duration")
    finally:
        path.unlink()
    doc = pvp_recording(opponent_casts=False)
    for key in ("crowd_control_received", "crowd_control_received_by_target"):          # as an older analyzer left it
        del doc["encounter_insights"]["segments"][0]["actions"][key]
    path = _saved(app_home, "session-20261109-220000-abcdef.a2log.json", doc)
    older = "Not in this log's analysis, which an older app or sharing server made."
    try:
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=0")
        page.select_option('[data-control="actor"]', ME)
        actions.locator('[data-actions="cc"]').click()
        assert older in squash(actions.inner_text()) and "Shield Smite" in actions.inner_text()
        page.select_option('[data-control="actor"]', FOE)
        card = squash(page.locator("[data-opponent]").inner_text())
        assert "Not recorded: their healing, their casts (recorded by the live meter since 0.2.398), their positions." in card
        [row] = [squash(r) for r in page.locator(SUMMARY).all_inner_texts()]
        assert row.endswith("Ranger 13,000 867 12,000 Not recorded — 1")
        details = page.locator(".cr-details")
        for tab in ("skills", "casts"):
            details.locator(f'[data-detail="{tab}"]').click()
            assert ("Their casts are not recorded in this log: the live meter records an opponent's casts since 0.2.398, "
                    "once the game has named them.") in squash(details.inner_text())
        actions.locator('[data-actions="rotation"]').click()
        assert "Their casts are not recorded" in actions.inner_text()
        actions.locator('[data-actions="cc"]').click()
        assert older in squash(actions.inner_text()) and "Shield Smite Stun" in squash(actions.inner_text())
    finally:
        path.unlink()


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_opponent_view_passes_axe(browser, app_url, app_home, axe_js, scheme):
    path = _saved(app_home, f"session-20261109-23000{scheme == 'light':d}-abcdef.a2log.json", pvp_recording())
    context = open_context(browser, app_url, scheme)
    try:
        page, watch = watched_page(context, app_url)
        go(page, app_url, f"#/combat-log/local/{path.name}?segment=0")
        page.select_option('[data-control="actor"]', FOE)
        page.locator("[data-opponent]").wait_for()
        problems = [f"opponent: {p}" for p in axe_findings(page, axe_js)]
        for tab in ("effects", "cc"):
            page.click(f'[data-actions="{tab}"]')
            problems += [f"{tab}: {p}" for p in axe_findings(page, axe_js)]
        page.click('[data-metric="deaths"]')
        problems += [f"deaths: {p}" for p in axe_findings(page, axe_js)]
        problems += watch.unexpected()
        assert not problems, "\n".join(problems)
    finally:
        close_context(context)
        path.unlink()


def test_open_in_raid_planner_shows_the_replay_and_asks_about_work_in_progress(app_page, app_url, app_home):
    """Open in Raid Planner (0.2.363) opens the planner on the replay: an untouched starter plan gives way to it,
    and work in progress is asked about first (keep it in the Plan list, discard it, or cancel)."""
    page = app_page
    name = "session-20261027-230000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moving_recording()), encoding="utf-8")
    plans = lambda: page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans') || '{}')).map(p => p.meta.name)")  # noqa: E731

    def open_replay():
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        page.locator("[data-replay] [data-tokens] circle").first.wait_for()
        page.locator("[data-replay] [data-plan]").click()
    try:
        # the planner was never opened: the replay is the plan shown, nothing asked
        open_replay()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        assert plans() == ["Gatekeeper Testlord"] and page.locator(".rp-ask").count() == 0
        # an untouched New plan gives way to the next replay
        page.click("#rnew")
        page.wait_for_function("document.querySelector('#rname')?.value === 'New plan'")
        open_replay()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        assert sorted(plans()) == ["Gatekeeper Testlord", "Gatekeeper Testlord"] and page.locator(".rp-ask").count() == 0
        # work in progress (a renamed plan) is asked about: Cancel keeps the log page and stores nothing
        page.fill("#rname", "Tahabata pulls")
        page.locator("#rname").dispatch_event("change")
        open_replay()
        ask = page.locator(".rp-ask")
        ask.wait_for()
        assert "Tahabata pulls" in ask.inner_text() and ask.locator('[data-choice="keep"]').evaluate("b => document.activeElement === b")
        ask.locator('[data-choice="cancel"]').click()
        page.wait_for_timeout(300)
        assert page.evaluate("location.hash").startswith("#/combat-log/") and sorted(plans()) == ["Gatekeeper Testlord", "Tahabata pulls"]
        # Keep: the plan stays in the Plan list, the replay opens as a new plan
        page.locator("[data-replay] [data-plan]").click()
        ask.wait_for()
        ask.locator('[data-choice="keep"]').click()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        assert sorted(plans()) == ["Gatekeeper Testlord", "Gatekeeper Testlord", "Tahabata pulls"]
        assert "Tahabata pulls" in page.locator("#rplan").inner_text()
        # Discard: the plan shown is dropped
        page.locator("#rplan").select_option(label="Tahabata pulls")
        page.wait_for_function("document.querySelector('#rname')?.value === 'Tahabata pulls'")
        open_replay()
        ask.wait_for()
        ask.locator('[data-choice="discard"]').click()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        assert plans() == ["Gatekeeper Testlord"] * 3 and "Tahabata pulls" not in page.locator("#rplan").inner_text()
    finally:
        page.goto("about:blank")
        path.unlink()


# an element's place on the page, whatever the page's scroll
PAGE_BOX = "e => {const r = e.getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height];}"


def test_the_raid_planner_takes_the_replays_areas_and_drops_what_faded(app_page, app_url, app_home):
    """Open in Raid Planner brings the boss's measured areas as area tokens of their shape, for as long as the replay
    draws them; a token is on the map only from its first position until it faded, 8 s after its last (0.2.372: a
    summon stood at its last place to the end of the plan). In the planner a click on empty space lets go of the
    selected token, and a token's keyframes sit in a box of their own that follows the replay."""
    page = app_page
    name = "session-20261027-234800-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    doc = moving_recording(casts=True)
    doc["segments"][1]["duration"] = 60.0
    path.write_text(json.dumps(doc), encoding="utf-8")
    shapes = {"123": {"shape": "circle_aim", "radius": 300.0, "delay": 1.0, "confidence": "high", "casts": 9, "accuracy": 0.9},
              "124": {"shape": "cone", "radius": 800.0, "angle": 45.0, "delay": 0.5, "confidence": "high", "casts": 9, "accuracy": 0.9}}
    page.route("**/static/aoe-shapes.json", lambda route: route.fulfill(json={"shapes": shapes}))
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        page.locator("[data-replay] [data-marks]").wait_for(state="attached")
        page.wait_for_function("document.querySelector('[data-replay] [data-events]')?.innerText.includes('circle of 3.0 m around the aim')")
        page.locator("[data-replay] [data-plan]").click()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        plan, = [p for p in page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans')))")
                 if p.get("meta", {}).get("name") == "Gatekeeper Testlord"]
        tokens = {t["id"]: t for t in plan["tokens"]}
        trample, meteor = tokens["aoe:0"], tokens["aoe:1"]
        assert (trample["kind"], trample["shape"], trample["from"], trample["until"]) == ("aoe", "circle", 4.0, 6.0)
        assert (meteor["shape"], meteor["angle"], meteor["facing"], meteor["from"], meteor["until"]) == ("cone", 45.0, 45.0, 14.0, 15.5)
        assert 0 < trample["radius"] < meteor["radius"] < 1
        assert tokens["add1"]["from"] == 12.0 and tokens["add1"]["until"] == 36.0      # appeared at 12 s, last seen at 28 s
        assert "from" not in tokens["boss"] and tokens["boss"]["until"] == 37.0
        shown = lambda tid: page.evaluate("id => getComputedStyle(document.querySelector(`[data-tid=\"${id}\"]`)).display !== 'none'", tid)  # noqa: E731

        def at(t):
            page.evaluate("t => {const s = document.querySelector('#rscrub'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
        at(5)
        assert shown("aoe:0") and not shown("aoe:1") and not shown("add1")
        assert page.locator('[data-tid="aoe:1"] svg path').count() == 1                  # the cone, as a wedge
        at(14.5)
        assert shown("aoe:1") and not shown("aoe:0") and shown("add1")
        at(40)
        assert not shown("add1") and not shown("boss")                                    # both faded
        # a click on the map's empty space lets go of the selected token
        at(10)
        page.locator('[data-tid="boss"]').click()
        assert page.locator("#slabel").count() == 1
        empty = page.evaluate("""() => {const a = document.querySelector('#arena'), r = a.getBoundingClientRect();
            for (let i = 1; i < 10; i++) for (let j = 1; j < 10; j++) {
              const x = r.left + r.width * i / 10, y = r.top + r.height * j / 10, hit = document.elementFromPoint(x, y);
              if (hit && a.contains(hit) && !hit.closest('.rtoken')) return [x, y];
            } return null;}""")
        page.mouse.click(*empty)
        assert page.locator("#slabel").count() == 0 and "Select a token on the map" in page.locator(".rpanel").first.inner_text()
        # the boss's 30 keyframes: a box of its own height that follows the replay
        page.locator('[data-tid="boss"]').click()
        kf = page.locator("[data-kflist]")
        assert kf.evaluate("k => k.scrollHeight > k.clientHeight && getComputedStyle(k).overflowY === 'auto'")
        at(25.5)
        assert kf.locator(".kfrow.on").inner_text().startswith("25.0s")
        assert kf.evaluate("""k => {const row = k.querySelector('.kfrow.on').getBoundingClientRect(), box = k.getBoundingClientRect();
            return row.top >= box.top && row.bottom <= box.bottom && k.scrollTop > 0;}""")
    finally:
        page.goto("about:blank")
        path.unlink()


def test_the_replay_shows_the_bosses_casts_and_what_appears(app_page, app_url, app_home):
    """Why everyone moved (0.2.363): a boss cast is ringed on the caster with a marker where it was aimed (the target,
    the caster itself or the ground) and a wedge for its facing, an add is ringed where it appeared, both are
    listed beside the arena with their times, the ones in progress marked (0.2.372), and the slider carries a tick
    at each; the key can hide them."""
    page = app_page
    name = "session-20261027-233000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moving_recording(casts=True)), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        key = box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        assert "Boss cast: ringed on the caster, a marker where it was aimed, a wedge for its facing" in key
        assert "Appeared: an enemy first seen here during the fight (an add, or a summon of the other side)" in key
        assert sorted(box.locator("#cr-ticks option").evaluate_all("os => os.map(o => o.value)")) == ["12.0", "14.0", "4.0"]
        assert box.locator("[data-scrub]").get_attribute("list") == "cr-ticks"
        # every cast and appearance beside the arena, from the top, with its time; none in progress yet
        rows = box.locator("[data-events] li")
        assert [" ".join(t.split()) for t in rows.all_inner_texts()] == [
            "4.0s Gatekeeper Testlord: Trample at Testally", "12.0s Summoned Spike appeared",
            "14.0s Gatekeeper Testlord: Meteor on the ground near Testally"]
        now = lambda: [" ".join(t.split()) for t in box.locator("[data-events] li.is-now .cr-ev-text").all_inner_texts()]  # noqa: E731
        arena = lambda: box.locator(".cr-arena").evaluate(PAGE_BOX)              # noqa: E731
        still = arena()
        assert now() == [] and box.locator("[data-marks] *").count() == 0 and rows.evaluate_all("rs => rs.every(r => r.classList.contains('is-next'))")
        scrub(4.5)                                                  # Trample, aimed at the party member's place
        assert box.locator("[data-marks] .cr-castring").count() == 1 and box.locator("[data-marks] .cr-face").count() == 1
        assert box.locator("[data-marks] .cr-aim").count() == 1 and box.locator("[data-marks] .cr-aimline").count() == 1
        assert now() == ["Gatekeeper Testlord: Trample at Testally"]
        assert "Trample at Testally · 4.0s" in box.locator("[data-marks] .cr-aim title").text_content()
        scrub(8.0)                                                  # over: nothing shown
        assert now() == [] and box.locator("[data-marks] *").count() == 0
        scrub(12.5)                                                 # the add appears
        assert box.locator("[data-marks] .cr-spawn").count() == 1 and now() == ["Summoned Spike appeared"]
        scrub(14.5)                                                 # Meteor, on the ground away from everyone (the add still ringed)
        assert now() == ["Summoned Spike appeared", "Gatekeeper Testlord: Meteor on the ground near Testally"]
        assert box.locator("[data-marks] .cr-spawn").count() == 1 and box.locator("[data-marks] .cr-aim").count() == 1
        assert arena() == still                                     # the arena never moved
        # a row takes the replay to its time
        rows.nth(0).locator("button").click()
        assert box.locator("[data-clock]").inner_text() == "4.0s" and now() == ["Gatekeeper Testlord: Trample at Testally"]
        scrub(14.5)
        # the key hides them
        box.locator('.cr-key [data-key-toggle="casts"]').uncheck()
        assert box.locator("[data-marks] .cr-aim").count() == 0 and now() == ["Summoned Spike appeared"] and rows.count() == 1
        box.locator('.cr-key [data-key-toggle="spawns"]').uncheck()
        assert box.locator("[data-marks] *").count() == 0 and now() == []
        assert rows.all_inner_texts() == ["The key hides every cast and event."]
        box.locator('.cr-key [data-key-toggle="casts"]').check()
        assert box.locator("[data-marks] .cr-castring").count() == 1 and rows.count() == 2
        assert arena() == still
    finally:
        page.goto("about:blank")
        path.unlink()


def summoner_recording():
    """A boss fight (0.2.393) with a party Spiritmaster whose Wind Spirit is linked to them and whose Fire Spirit is not,
    the spirit striking its owner as the recordings hold a summon's own strikes, a boss clone the game sends no position
    of striking the party member, who dies and is revived, and an add that dies early and is long unseen after."""
    doc = moving_recording(casts=True)
    me, ally, sm = "p:1101:1", "p:1101:2", "p:1101:3"
    doc["players"].append({"id": sm, "name": "Testspirit", "class": "spiritmaster", "server": "1101"})
    fight = doc["segments"][1]
    fight["duration"] = 70.0
    fight["entities"] += [{"id": "sp1", "name": "Wind Spirit", "kind": "pet", "owner": sm},
                          {"id": "sp2", "name": "Fire Spirit", "kind": "pet"},
                          {"id": "cl1", "name": "Unnamed summon", "kind": "enemy", "mob_code": 2920604}]
    fight["movement"] += ([{"t": float(t), "entity": sm, "x": 1200.0, "y": 1000.0 + 5 * t, "z": 50.0, "src": "party"} for t in range(0, 70, 4)]
                          + [{"t": float(t), "entity": "sp1", "x": 1210.0, "y": 1010.0, "z": 50.0, "src": "move"} for t in range(5, 29, 2)]
                          + [{"t": float(t), "entity": "sp2", "x": 1190.0, "y": 1010.0, "z": 50.0, "src": "move"} for t in range(6, 29, 2)])
    fight["movement"].sort(key=lambda m: m["t"])
    fight["events"] = ([{"kind": "damage", "t": float(t), "source": me, "target": "boss", "skill_id": 15210000, "skill": "Burst", "amount": 2000} for t in range(30)]
                       + [{"kind": "damage", "t": float(t), "source": sm, "target": "boss", "skill_id": 16010000, "skill": "Spirit Strike", "amount": 1500} for t in range(0, 30, 3)]
                       + [{"kind": "damage", "t": t, "source": "sp1", "target": sm, "skill_id": 16990003, "skill": "Wind Spirit: Basic Attack", "amount": 400} for t in (7.0, 9.0, 11.0)]
                       + [{"kind": "damage", "t": t, "source": "sp2", "target": "boss", "skill_id": 16990002, "skill": "Fire Spirit: Basic Attack", "amount": 300} for t in (8.0, 10.0)]
                       + [{"kind": "damage", "t": 6.0, "source": "cl1", "target": ally, "skill_id": 1800000, "skill": "Attack", "amount": 900},
                          {"kind": "damage", "t": 9.5, "source": "boss", "target": ally, "skill_id": 123, "skill": "Trample", "amount": 5000},
                          {"kind": "death", "t": 10.0, "target": ally}, {"kind": "revive", "t": 16.0, "target": ally}])
    fight["events"].sort(key=lambda e: e["t"])
    return doc


def test_the_replay_plays_in_real_seconds_at_the_chosen_speed(app_page, app_url, app_home):
    """Play runs the fight in real seconds at 1× (0.2.393) and faster or slower at the chosen speed, which is kept."""
    page = app_page
    name = "session-20261108-200000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    doc = moving_recording()
    doc["segments"][1]["duration"] = 120.0
    path.write_text(json.dumps(doc), encoding="utf-8")
    clock = lambda: float(page.locator("[data-replay] [data-clock]").inner_text().rstrip("s"))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        speed = box.locator("[data-speed]")
        assert speed.locator("option").all_inner_texts() == ["0.25×", "0.5×", "1×", "2×", "4×", "8×"] and speed.input_value() == "1"
        page.click("[data-play]")
        page.wait_for_timeout(1500)
        page.click("[data-play]")
        assert 1.0 <= clock() <= 2.6                                   # real seconds, give or take a frame or two
        speed.select_option("8")
        page.click("[data-rewind]")
        page.click("[data-play]")
        page.wait_for_timeout(1000)
        page.click("[data-play]")
        assert 6.0 <= clock() <= 12.0
        assert page.evaluate("localStorage.getItem('a2-replay-speed')") == "8"
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        assert page.locator("[data-replay] [data-speed]").input_value() == "8"
    finally:
        page.evaluate("localStorage.removeItem('a2-replay-speed')")
        page.goto("about:blank")
        path.unlink()


def test_the_replay_marks_deaths_revives_and_where_a_clone_struck(app_page, app_url, app_home):
    """A player's death is a ✕ where they fell and a greyed token until revived, a revive a ring, and a boss clone the
    game sends no position of is ringed where it struck the player (0.2.393); all listed and ticked on the slider."""
    page = app_page
    name = "session-20261108-201000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(summoner_recording()), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        rows = [" ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts()]
        assert "6.0s Clone hit Testally · Cleric" in rows
        assert "10.0s Testally · Cleric died" in rows and "16.0s Testally · Cleric revived" in rows
        ticks = box.locator("#cr-ticks option").evaluate_all("os => os.map(o => o.value)")
        assert {"6.0", "10.0", "16.0"} <= set(ticks)
        key = box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        assert "Death: a ✕ where a player fell, their token greyed until revived; a ring when revived" in key
        assert "Struck by an add or a boss's clone: where it hit a player (recordings before 0.2.394 hold no position of most adds)" in key
        ally = box.locator("[data-tokens] circle", has=page.locator("title", has_text="Testally"))
        scrub(6.5)                                                   # the clone's hit, ringed at the party member
        hit = box.locator("[data-marks] .cr-hit")
        assert hit.count() == 1 and "Clone hit Testally · Cleric · 6.0s" in hit.locator("title").text_content()
        assert hit.locator("circle").first.get_attribute("cx") == ally.get_attribute("cx")
        scrub(12)                                                    # dead: a ✕ where they fell, the token greyed
        assert box.locator("[data-marks] .cr-death").count() == 1 and ally.get_attribute("fill-opacity") == "0.2"
        assert "dead since 10.0s" in ally.locator("title").text_content()
        scrub(17)                                                    # revived: ringed, the ✕ gone
        assert box.locator("[data-marks] .cr-revive").count() == 1 and box.locator("[data-marks] .cr-death").count() == 0
        assert ally.get_attribute("fill-opacity") == "1"
        box.locator('.cr-key [data-key-toggle="lives"]').uncheck()
        assert box.locator("[data-marks] .cr-revive").count() == 0
        assert not any("revived" in " ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts())
        box.locator('.cr-key [data-key-toggle="hits"]').uncheck()
        scrub(6.5)
        assert box.locator("[data-marks] .cr-hit").count() == 0
    finally:
        page.goto("about:blank")
        path.unlink()


def test_a_token_long_unseen_leaves_the_replay(app_page, app_url, app_home):
    """A token fades 8 s after its last position and leaves the replay after 20 s unseen, a player or a boss after a
    minute (0.2.393); until then a summon that expired stayed faded at its last place for the rest of the fight."""
    page = app_page
    name = "session-20261108-202000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(summoner_recording()), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    token = lambda text: page.locator("[data-replay] [data-tokens] circle", has=page.locator("title", has_text=text))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        page.locator("[data-replay] [data-tokens] circle").first.wait_for()
        scrub(40)                                       # the spirits and the add last seen at 28 s: faded
        assert token("Wind Spirit").get_attribute("fill-opacity") == "0.35"
        assert token("Summoned Spike").get_attribute("fill-opacity") == "0.35"
        scrub(49)                                       # 21 s unseen: gone; the party member (last seen at 28 s) stays
        assert token("Wind Spirit").count() == 0 and token("Summoned Spike").count() == 0
        assert token("Testally").count() == 1 and token("Testally").get_attribute("fill-opacity") == "0.35"
        scrub(20)                                       # seen again: back
        assert token("Wind Spirit").count() == 1
    finally:
        page.goto("about:blank")
        path.unlink()


def test_a_partys_summons_are_on_the_partys_side(app_page, app_url, app_home):
    """A summon follows its owner (0.2.393): a party Spiritmaster's spirits, linked or not, are drawn as pets in the
    owner's colour and are never listed as enemies that appeared, while a boss's add stays an enemy. A spirit striking
    its own owner, as the recordings hold a summon's own strikes, is no damage taken. Until 0.2.392 the cast list
    named every summon of the party as an enemy that appeared."""
    page = app_page
    name = "session-20261108-203000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(summoner_recording()), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    token = lambda text: page.locator("[data-replay] [data-tokens] circle", has=page.locator("title", has_text=text))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        rows = [" ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts()]
        assert "12.0s Summoned Spike appeared" in rows                       # the boss's add: an enemy
        assert not any("Spirit" in r for r in rows), rows                   # the party's spirits: never enemies
        key = box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        assert "Pet or summon, in its owner's class colour" in key
        scrub(10)
        assert token("Wind Spirit").get_attribute("fill") == "#8788ee"      # the owner's class colour
        assert token("Fire Spirit").get_attribute("fill") == "#8788ee"      # no owner linked: placed by its skills
        assert token("Summoned Spike").count() == 0 or token("Summoned Spike").get_attribute("fill") == "#9a9a9a"
        # the spirit's strikes recorded on its own Spiritmaster are no damage taken
        taken = page.evaluate("""() => {
            const table = [...document.querySelectorAll('.cr-review table')].find(t => [...t.querySelectorAll('th')].some(h => h.textContent.trim() === 'Damage taken'));
            const column = [...table.querySelectorAll('th')].findIndex(h => h.textContent.trim() === 'Damage taken');
            return [...table.querySelectorAll('tr')].find(r => r.textContent.includes('Testspirit')).children[column].textContent.trim(); }""")
        assert taken == "0"
    finally:
        page.goto("about:blank")
        path.unlink()


def test_an_enemy_players_summons_stay_enemies(app_page, app_url, app_home):
    """In PvP an enemy Spiritmaster's spirit is the other side's (0.2.393): drawn grey with the enemies and listed when
    it appears, while the recording side keeps its own summons."""
    page = app_page
    name = "session-20261108-204000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    me = "p:1101:1"
    doc = recording()
    fight = doc["segments"][1]
    fight.update(label="Combat 1", boss="Combat 1", encounter_type="pvp_open_world", duration=30.0, killed=False)
    fight["entities"] = [{"id": "foe", "name": "Testfoe", "kind": "enemy", "is_player": True, "class": "spiritmaster"},
                         {"id": "fsp", "name": "Water Spirit", "kind": "pet", "owner": "foe"},
                         {"id": "usp", "name": "Earth Spirit", "kind": "pet"}]
    fight["movement"] = sorted([{"t": float(t), "entity": "foe", "x": 1000.0 + 10 * t, "y": 1000.0, "z": 50.0, "src": "move"} for t in range(30)]
                               + [{"t": float(t), "entity": "fsp", "x": 1020.0, "y": 1010.0, "z": 50.0, "src": "move"} for t in range(5, 30, 2)]
                               + [{"t": float(t), "entity": "usp", "x": 980.0, "y": 990.0, "z": 50.0, "src": "move"} for t in range(6, 30, 2)]
                               + [{"t": float(t), "entity": me, "x": 900.0, "y": 950.0, "z": 50.0, "src": "applied"} for t in range(0, 30, 3)],
                               key=lambda m: m["t"])
    fight["events"] = sorted([{"kind": "damage", "t": float(t), "source": me, "target": "foe", "skill_id": 15210000, "skill": "Burst", "amount": 2000} for t in range(0, 30, 2)]
                             + [{"kind": "damage", "t": float(t), "source": "foe", "target": me, "skill_id": 16010000, "skill": "Spirit Strike", "amount": 1500} for t in range(1, 30, 3)]
                             + [{"kind": "damage", "t": float(t), "source": "fsp", "target": me, "skill_id": 16990002, "skill": "Water Spirit: Basic Attack", "amount": 300} for t in (7, 9)]
                             + [{"kind": "damage", "t": float(t), "source": "usp", "target": me, "skill_id": 16990003, "skill": "Earth Spirit: Basic Attack", "amount": 300} for t in (8, 10)],
                             key=lambda e: e["t"])
    path.write_text(json.dumps(doc), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    token = lambda text: page.locator("[data-replay] [data-tokens] circle", has=page.locator("title", has_text=text))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        rows = [" ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts()]
        assert "5.0s Water Spirit appeared" in rows                          # the enemy player's linked spirit
        assert "6.0s Earth Spirit appeared" in rows                          # unlinked, with the other side's skills
        assert "Other enemy" in box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        scrub(10)
        assert token("Water Spirit").get_attribute("fill") == "#9a9a9a" and token("Earth Spirit").get_attribute("fill") == "#9a9a9a"
    finally:
        page.goto("about:blank")
        path.unlink()


def test_the_replay_draws_the_measured_dashes_trails_and_wedges(app_page, app_url, app_home):
    """The log server's 0.2.172 catalog (0.2.393): a dash is drawn along the boss's recorded track from the cast to the
    end of its span with round ends, a trail where the boss passed within its duration, and wedges round the caster's
    facing with the safe gaps between them undrawn, each instead of the skill's older shape, in the list, the key and
    the Raid Planner. A catalog without them draws as before."""
    page = app_page
    name = "session-20261108-205000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    doc = moving_recording(casts=True)
    doc["segments"][1]["npc_casts"].append({"t": 20.0, "source": "boss", "skill_id": 125, "skill": "Scorch", "facing": 90.0})
    path.write_text(json.dumps(doc), encoding="utf-8")
    wedges = {"shape": "arcs", "radius": 800.0, "inner": 0, "segments": [[-60, -30], [30, 60]], "anchor": "cast",
              "accuracy": 1.0, "confidence": "measured", "casts": 10}
    shapes = {"123": {"shape": "circle_aim", "radius": 300.0, "delay": 1.0, "confidence": "high", "casts": 9, "accuracy": 0.9,
                      "path": {"shape": "dash", "half_width": 200.0, "span": 3.0, "accuracy": 1.0, "confidence": "measured", "casts": 10}},
              "124": {**wedges, "arcs": dict(wedges)},
              "125": {"shape": "trail", "half_width": 150.0, "span": 4.0, "duration": 3.0, "accuracy": 0.95, "confidence": "measured", "casts": 12}}
    catalog = {"meta": {"extra_version": 1, "extra_shapes": {"dash": 1, "trail": 1, "arcs": 1}}, "shapes": shapes}
    page.route("**/static/aoe-shapes.json", lambda route: route.fulfill(json=catalog))

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    xy = lambda points: [tuple(map(float, p.split(","))) for p in points.split()]       # noqa: E731
    rows = lambda: [" ".join(t.split()) for t in page.locator("[data-replay] [data-events] li").all_inner_texts()]  # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        page.wait_for_function("document.querySelector('[data-replay] [data-events]')?.innerText.includes('wedges')")
        assert "Measured area: a dash or trail along the boss's path; wedges with safe gaps between them" in box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        assert "4.0s Gatekeeper Testlord: Trample at Testally · dash 4.0 m wide along its path for 3.0 s" in rows()
        assert "14.0s Gatekeeper Testlord: Meteor on the ground near Testally · 2 wedges of 8.0 m around the caster, safe between them" in rows()
        assert "20.0s Gatekeeper Testlord: Scorch · trail 3.0 m wide along its path for 4.0 s, each part staying 3.0 s" in rows()
        marks = box.locator("[data-marks]")
        boss = box.locator("[data-tokens] circle", has=page.locator("title", has_text="Gatekeeper Testlord"))
        scrub(5)            # the dash: the boss's way from the cast to 3 s after it, ahead of the boss, not the circle at the aim
        assert marks.locator(".cr-aoe-dash").count() == 1 and marks.locator(".cr-aoe-circle_aim").count() == 0
        band = marks.locator(".cr-aoe-dash .cr-aoe-band")
        way = xy(band.get_attribute("points"))
        assert len(way) == 4 and all(b[0] > a[0] for a, b in zip(way, way[1:])) and len({y for _, y in way}) == 1
        assert way[0][0] < float(boss.get_attribute("cx")) < way[-1][0]
        assert band.evaluate("e => getComputedStyle(e).strokeLinecap") == "round" and band.evaluate("e => parseFloat(getComputedStyle(e).strokeWidth)") > 1
        assert "dash 4.0 m wide along its path for 3.0 s (measured, 10 casts, 100% of the positions explained)" in marks.locator(".cr-aoe-dash title").text_content()
        scrub(8)
        assert marks.locator(".cr-aoe-path").count() == 0
        scrub(14.5)         # two wedges either side of the facing (45°, counter-clockwise), the gap between them undrawn
        assert marks.locator(".cr-aoe-arcs path").count() == 2 and marks.locator(".cr-aoe-cone").count() == 0
        angles = marks.locator(".cr-aoe-arcs path").evaluate_all("""ps => ps.map(p => {
            const [bx, by, x1, y1, , , , , , x2, y2] = p.getAttribute('d').match(/-?[0-9.]+/g).map(Number);
            const deg = (x, y) => Math.round(Math.atan2(by - y, x - bx) * 180 / Math.PI); return [deg(x1, y1), deg(x2, y2)]; })""")
        assert angles == [[-15, 15], [75, 105]]
        scrub(20)
        start = float(boss.get_attribute("cx"))
        scrub(21)           # the trail: where the boss passed since the cast
        trail = xy(marks.locator(".cr-aoe-trail .cr-aoe-band").get_attribute("points"))
        assert abs(trail[0][0] - start) < .01 and abs(trail[-1][0] - float(boss.get_attribute("cx"))) < .01
        scrub(26)           # 2 s after the span ended: only the part passed in the last 3 s, behind the boss
        trail = xy(marks.locator(".cr-aoe-trail .cr-aoe-band").get_attribute("points"))
        assert trail[0][0] > start + 1 and trail[-1][0] < float(boss.get_attribute("cx"))
        scrub(27.5)
        assert marks.locator(".cr-aoe-path").count() == 0
        # the Raid Planner takes them: the dash and the trail as lines along the boss's way, a wedge for each segment
        box.locator("[data-plan]").click()
        page.wait_for_function("location.hash === '#/raid' && document.querySelector('#rname')?.value === 'Gatekeeper Testlord'")
        plan, = [p for p in page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans')))") if p.get("meta", {}).get("name") == "Gatekeeper Testlord"]
        areas = [(t["shape"], t["from"], t["until"], t["facing"], t.get("angle")) for t in plan["tokens"] if t["kind"] == "aoe"]
        assert areas == [("line", 4.0, 7.6, 0.0, None), ("cone", 14.0, 15.5, 0.0, 15.0), ("cone", 14.0, 15.5, 90.0, 15.0), ("line", 20.0, 27.0, 0.0, None)]
        # an older catalog: the old shapes, and no word of the new ones
        page.unroute("**/static/aoe-shapes.json")
        older = {"123": {k: v for k, v in shapes["123"].items() if k != "path"},
                 "124": {"shape": "cone", "radius": 800.0, "angle": 45.0, "delay": 0.5, "confidence": "high", "casts": 9, "accuracy": 0.9}}
        page.route("**/static/aoe-shapes.json", lambda route: route.fulfill(json={"shapes": older}))
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box.locator("[data-tokens] circle").first.wait_for()
        page.wait_for_function("document.querySelector('[data-replay] [data-events]')?.innerText.includes('cone')")
        assert "4.0s Gatekeeper Testlord: Trample at Testally · circle of 3.0 m around the aim" in rows()
        assert "14.0s Gatekeeper Testlord: Meteor on the ground near Testally · 90° cone 8.0 m long" in rows()
        assert "20.0s Gatekeeper Testlord: Scorch" in rows()
        assert not any("Measured area: a dash" in k for k in box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts())
        scrub(4.5)
        assert marks.locator(".cr-aoe-circle_aim").count() == 1 and marks.locator(".cr-aoe-path").count() == 0
        scrub(14.5)
        assert marks.locator(".cr-aoe-cone").count() == 1 and marks.locator(".cr-aoe-arcs").count() == 0
    finally:
        page.goto("about:blank")
        path.unlink()


def test_a_boss_add_or_clone_is_drawn_in_the_bosss_colour(app_page, app_url, app_home):
    """An NPC of the boss's side, no one's summon, that struck the party in a boss fight is the boss's add or clone
    (0.2.393): drawn in the boss's colour, named by the community catalog when the game data gives it no name (else
    Clone), ringed where it appeared and where it struck; an add that struck nobody stays a grey enemy."""
    page = app_page
    name = "session-20261108-206000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    me, ally = "p:1101:1", "p:1101:2"
    doc = moving_recording(casts=True)
    fight = doc["segments"][1]
    fight["entities"].append({"id": "cl2", "name": "Unnamed summon", "kind": "enemy", "mob_code": 2920601})
    fight["movement"] = sorted(fight["movement"] + [{"t": float(t), "entity": "cl2", "x": 950.0, "y": 1000.0, "z": 50.0, "src": "move"} for t in range(13, 19)],
                               key=lambda m: m["t"])
    fight["events"] = ([{"kind": "damage", "t": float(t), "source": me, "target": "boss", "skill_id": 15210000, "skill": "Burst", "amount": 2000} for t in range(30)]
                       + [{"kind": "damage", "t": 15.0, "source": "cl2", "target": ally, "skill_id": 1800000, "skill": "Attack", "amount": 900}])
    fight["events"].sort(key=lambda e: e["t"])
    path.write_text(json.dumps(doc), encoding="utf-8")
    page.add_init_script("window.A2CommunityNames = {'2920601': 'Test Echo'};")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    token = lambda text: page.locator("[data-replay] [data-tokens] circle", has=page.locator("title", has_text=text))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        key = box.locator('.cr-key ul[aria-label="Key"] li').all_inner_texts()
        assert "Boss add or clone: an enemy that struck the party, or cast, during the boss fight" in key and "Other enemy" in key
        rows = [" ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts()]
        assert "13.0s Test Echo appeared" in rows and "15.0s Test Echo hit Testally · Cleric" in rows
        assert "12.0s Summoned Spike appeared" in rows
        scrub(15.5)
        assert token("Test Echo").get_attribute("fill") == "#ef6262" and token("Test Echo").get_attribute("r") == "1.8"
        assert token("Summoned Spike").get_attribute("fill") == "#9a9a9a"
        assert "Test Echo hit Testally · Cleric · 15.0s" in box.locator("[data-marks] .cr-hit title").text_content()
        box.locator('.cr-key [data-key-toggle="add"]').uncheck()
        assert token("Test Echo").count() == 0 and token("Summoned Spike").count() == 1
    finally:
        page.goto("about:blank")
        path.unlink()


def test_an_add_with_casts_of_its_own_is_drawn_and_listed_as_the_bosss(app_page, app_url, app_home):
    """From 0.2.394 the meter records the casts and positions of a boss's adds and clones: an add that cast in the
    boss fight, though it struck nobody, is drawn in the boss's colour where it was recorded, and its casts are
    listed with the boss's."""
    page = app_page
    name = "session-20261109-010000-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    doc = moving_recording(casts=True)
    fight = doc["segments"][1]
    fight["entities"].append({"id": "cl3", "name": "Unnamed summon", "kind": "enemy", "mob_code": 2920604})
    fight["movement"] = sorted(fight["movement"] + [{"t": float(t), "entity": "cl3", "x": 1200.0 + 10 * t, "y": 900.0, "z": 50.0,
                                                     "src": "spawn" if t == 16 else "targeted"} for t in range(16, 21)],
                               key=lambda m: m["t"])
    fight["npc_casts"] = sorted(fight["npc_casts"] + [{"t": 17.0, "source": "cl3", "skill_id": 1802012, "skill": "Leap",
                                                       "pos": [1370.0, 900.0, 50.0], "facing": 0.0}], key=lambda c: c["t"])
    from aion2calc.combat.insights import summarize
    doc["encounter_insights"] = summarize(doc)                 # the analysis the meter saves with the log
    path.write_text(json.dumps(doc), encoding="utf-8")
    page.add_init_script("window.A2CommunityNames = {'2920604': 'Test Leaper'};")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    token = lambda text: page.locator("[data-replay] [data-tokens] circle", has=page.locator("title", has_text=text))   # noqa: E731
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-tokens] circle").first.wait_for()
        rows = [" ".join(t.split()) for t in box.locator("[data-events] li").all_inner_texts()]
        assert any(row.startswith("17.0s Test Leaper: Leap") for row in rows), rows
        scrub(18.5)
        assert token("Test Leaper").get_attribute("fill") == "#ef6262"          # the boss's colour, though it struck no one
        before = token("Test Leaper").get_attribute("cx")
        scrub(20.0)
        assert token("Test Leaper").get_attribute("cx") != before               # its recorded positions move it
        # the Boss casts panel lists the add's skill after the boss's, and its casts in order stay the boss's
        page.locator('[data-actions="boss"]').click()
        panel = page.locator(".cr-actions", has=page.locator('[data-actions="boss"]'))
        panel.locator("table").first.wait_for()
        skills = [" ".join(t.split()) for t in panel.locator("table").first.locator("tbody tr").all_inner_texts()]
        assert skills[-1].startswith("Test Leaper boss's add Leap"), skills
        order = [" ".join(t.split()) for t in panel.locator("table").nth(1).locator("tbody tr").all_inner_texts()]
        assert order and not any("Test Leaper" in row for row in order), order
        assert "Not listed here: 1 cast by the bosses' adds and clones" in panel.inner_text()
    finally:
        page.goto("about:blank")
        path.unlink()


def test_the_replays_cast_list_keeps_its_size_and_follows_the_replay(app_page, app_url, app_home):
    """A fight with many casts (0.2.372): the list beside the arena keeps its size and scrolls on its own as the replay
    plays, the same skill cast at once by a boss's clones is one row with a count, and on a phone the list sits under
    the arena. Until 0.2.371 the casts in progress were listed above the arena and pushed it down with each one."""
    page = app_page
    name = "session-20261027-234500-abcdef.a2log.json"
    path = app_home / "logs" / name
    path.parent.mkdir(exist_ok=True)
    doc = moving_recording(casts=True)
    fight = doc["segments"][1]
    fight["npc_casts"] += [{"t": float(t), "source": "boss", "skill_id": 200 + t, "skill": f"Strike {t}"} for t in range(1, 29)]
    fight["npc_casts"] += [{"t": 20.2, "source": "boss", "skill_id": 300, "skill": "Mirror Burst"}] * 4
    path.write_text(json.dumps(doc), encoding="utf-8")

    def scrub(t):
        page.evaluate("t => {const s = document.querySelector('[data-scrub]'); s.value = t; s.dispatchEvent(new Event('input'));}", t)
    try:
        go(page, app_url, f"#/combat-log/local/{name}?segment=1")
        box = page.locator("[data-replay]")
        box.locator("[data-events] li").first.wait_for()
        pane, rows, scroller = box.locator(".cr-events"), box.locator("[data-events] li"), box.locator("[data-events]")
        assert rows.count() == 28 + 3 + 1                                   # the four clones' casts are one row
        burst = rows.filter(has_text="Mirror Burst")
        assert burst.count() == 1 and " ".join(burst.inner_text().split()) == "20.2s Gatekeeper Testlord: Mirror Burst ×4"
        size, arena = pane.evaluate(PAGE_BOX), box.locator(".cr-arena").evaluate(PAGE_BOX)
        assert abs(size[3] - arena[3]) < 2 and size[0] > arena[0] + arena[2] - 1          # beside the arena, as tall
        assert scroller.evaluate("p => p.scrollHeight > p.clientHeight && p.scrollTop === 0")             # from the top
        visible = """(p, text) => {const row = [...p.querySelectorAll('li')].find(r => r.textContent.includes(text)).getBoundingClientRect(),
            box = p.getBoundingClientRect(); return row.top >= box.top && row.bottom <= box.bottom;}"""
        scrub(25.5)
        assert scroller.evaluate(visible, "Strike 25") and scroller.evaluate("p => p.scrollTop > 0")
        assert pane.evaluate(PAGE_BOX) == size and box.locator(".cr-arena").evaluate(PAGE_BOX) == arena
        page.click("[data-rewind]")
        assert scroller.evaluate("p => p.scrollTop") == 0
        # playing: the list follows the replay
        page.click("[data-play]")
        page.wait_for_function("parseFloat(document.querySelector('[data-clock]').textContent) >= 12.5", timeout=20000)
        page.click("[data-play]")
        clock = float(box.locator("[data-clock]").inner_text().rstrip("s"))
        assert scroller.evaluate(visible, f"Strike {int(clock)}")
        # a phone: the list under the arena, still its own size
        page.set_viewport_size({"width": 390, "height": 800})
        page.wait_for_timeout(100)
        small, arena = pane.evaluate(PAGE_BOX), box.locator(".cr-arena").evaluate(PAGE_BOX)
        assert small[1] >= arena[1] + arena[3] - 1 and small[2] <= 390 and small[3] < size[3]
        scrub(3.5)
        assert pane.evaluate(PAGE_BOX) == small and box.locator(".cr-arena").evaluate(PAGE_BOX) == arena
    finally:
        page.goto("about:blank")
        path.unlink()


def test_a_part_of_a_longer_recording_keeps_its_fight_and_offers_the_whole(app_page, app_url, community):
    """A link to one fight of a multi-part recording shows that fight; the other parts are an offer, and the stitched
    recording opens on the same fight (0.2.367). Until 0.2.366 the page swapped itself for the stitched recording's
    first encounter a few seconds after it opened."""
    page = app_page
    go(page, app_url, f"#/combat-log/shared/{PART_LOG_ID}?segment=1")
    offer = page.locator("[data-archive-offer]")
    offer.wait_for(timeout=15000)
    assert offer.inner_text().startswith("This is part 2 of a recording in 2 parts")
    fight = "24 recorded positions of 2 players and enemies"                      # part 2's boss fight, the one the link named
    assert fight in page.locator("[data-replay] p").first.inner_text()
    page.wait_for_timeout(1500)                                                    # nothing swaps the page on its own
    assert page.locator("[data-source-back]").count() == 0
    assert page.locator(".cr-review h2").first.text_content() == "Test run · Part 2"
    assert fight in page.locator("[data-replay] p").first.inner_text()
    offer.locator("[data-combine-all]").click()
    page.locator("[data-source-back]").wait_for(timeout=15000)
    assert page.locator(".cr-review h2").first.text_content() == "Test run · Parts 1–2"
    assert fight in page.locator("[data-replay] p").first.inner_text()           # the same fight, not part 1's first encounter
    assert page.locator("[data-archive-offer]").count() == 0
    page.click("[data-source-back]")
    page.wait_for_function("document.querySelector('.cr-review h2').textContent === 'Test run · Part 2'")
    assert fight in page.locator("[data-replay] p").first.inner_text()


def test_the_raid_planner_hands_its_saved_plans_to_the_app_for_the_overlay(app_page, app_url):
    """The overlay's window keeps a storage of its own, so its plan view never saw the planner's saved plans (0.2.371):
    the planner hands its whole set to the app when it opens and after each save, and the app keeps it."""
    page = app_page
    go(page, app_url, "#/raid")
    page.wait_for_selector("#rname")
    saved = lambda: page.evaluate("fetch('/api/plans/saved').then(r => r.json()).then(d => Object.values(d.plans).map(p => p.meta.name))")  # noqa: E731
    page.wait_for_function("fetch('/api/plans/saved').then(r => r.json()).then(d => Object.keys(d.plans).length > 0)", polling=300)
    names = saved()
    assert names == page.evaluate("Object.values(JSON.parse(localStorage.getItem('a2plans'))).map(p => p.meta.name)")
    page.fill("#rname", "Kept for the overlay")
    page.dispatch_event("#rname", "change")
    page.wait_for_function("fetch('/api/plans/saved').then(r => r.json()).then(d => Object.values(d.plans).some(p => p.meta.name === 'Kept for the overlay'))",
                           polling=300)


# An analyzed fight (Combat Logs → an AbyssLogs import), as GET /api/encounters/<id> answers it: no damage taken recorded.
ANALYSIS = {
    "id": "TestFight01",
    "meta": {"player": "Testsorc", "class": "sorcerer", "target": "Gatekeeper Testlord", "source": "AbyssLogs",
             "combat_power": 123456, "party": [], "notes": ["Test analysis"]},
    "summary": {"total": 1_560_000, "dps": 13_000, "duration": 120.0, "hits": 412, "crit": .42, "double": .1, "perfect": .06,
                "multi": .13, "back": .2, "front": .5, "cpm": 38, "idle_seconds": 4.5,
                "biggest_hit": {"skill": "Test Burst", "damage": 48211, "t": 33.2}},
    "skills": [{"skill": skill, "skill_id": 11000000 + 10000 * k, "share": share, "hits": 20 + 5 * k, "avg_hit": 5000.0,
                "max_hit": 15000.0}
               for k, (skill, share) in enumerate((("Test Strike", .4), ("Test Burst", .25), ("Test Bolt", .15),
                                                   ("Test Wave", .1), ("Test Flare", .06), ("Test Spark", .04)))],
    "timeline": {"per_second": [13_000.0] * 120, "rolling10": [13_000.0] * 120},
    "rotation": [[1.6 * i, ("Test Strike", "Test Burst", "Test Bolt")[i % 3]] for i in range(60)],
    "buffs": [], "gaps": [], "vs_optimal": {"error": "no optimized build"}, "vs_top": {},
}


def test_an_analyzed_fights_breakdown_shows_every_section_at_once_inside_its_window(app_page, app_url):
    """An analyzed fight draws the Live Meter's breakdown in its Encounter window: every section at once, the highest
    hit over the donut, the hits the analysis counted, a note where defense has nothing recorded, and the rotation
    strip scrolling inside the card, where the keyboard reaches it (the combat review's parse badge, also named parse
    until now, had let the card grow to the strip's whole width, past the window)."""
    page = app_page
    page.route("**/api/encounters/TestFight01", lambda r: r.fulfill(json=ANALYSIS))
    go(page, app_url, "#/combat-log/analysis/TestFight01")
    card = page.locator("#focused-log .parse")
    card.wait_for()
    card_box, window_box = card.bounding_box(), page.locator("#focused-log section.win").first.bounding_box()
    assert window_box["x"] < card_box["x"] and card_box["x"] + card_box["width"] < window_box["x"] + window_box["width"]
    assert page.locator("#focused-log .ptabs").is_hidden()
    assert page.locator("#focused-log h3.psh").all_text_contents() == ["Damage by skill", "DPS over the fight", "Skills",
                                                                       "Defense", "Accuracy"]
    assert page.locator("#focused-log .pdmg .phi").inner_text().split() == ["HIGHEST", "HIT", "48.21K"]
    assert page.locator("#focused-log .pacc .rc").first.inner_text().split() == ["HITS", "412"]
    assert page.locator("#focused-log .pdef .pnote").inner_text() == "This source does not provide incoming-damage events."
    assert page.locator("#focused-log .pdef h3").get_attribute("title") is None      # no note to give
    chart, defense = (page.locator(f"#focused-log .{name}").bounding_box() for name in ("pchart", "pdef"))
    assert abs(chart["y"] + chart["height"] - defense["y"] - defense["height"]) < 1   # the columns end together
    strip = page.locator("#focused-log .prot .strip")
    assert strip.evaluate("s => s.scrollWidth > s.clientWidth + 100") and strip.get_attribute("tabindex") == "0"
