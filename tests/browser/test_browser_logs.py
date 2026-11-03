"""The Combat Logs page: the website's tabs (browse, speed, boss progression, build points) and the app's own
Personal records tab, each showing its panel alone; the log server's fights, newest first with mini-bosses
hidden until asked for, each opening at its own fight; the recordings saved on this computer, by type; and
the panels for the player's uploads (with the appeal against a moderator's hold) and characters; and a fight's
review: its details tabs, its enemies by name, a comparison from a pasted link, the fight combined from every
recording of it, and an arena match's result and rounds."""
import json

from apphelpers import go
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
            "Faded: last seen over 8 seconds ago, or outside the fight area", "Arena"]
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
            "Movement in the last 6 seconds", "Faded: last seen over 8 seconds ago, or outside the fight area"]
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
        assert "Appeared: an enemy or pet first seen here during the fight" in key
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
        assert rows.all_inner_texts() == ["The key hides every cast and appearance."]
        box.locator('.cr-key [data-key-toggle="casts"]').check()
        assert box.locator("[data-marks] .cr-castring").count() == 1 and rows.count() == 2
        assert arena() == still
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
