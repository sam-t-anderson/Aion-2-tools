"""The Combat Logs page: the website's tabs (browse, speed, boss progression, build points) and the app's own
Personal records tab, each showing its panel alone; the log server's fights, newest first with mini-bosses
hidden until asked for, each opening at its own fight; the recordings saved on this computer, by type; and
the panels for the player's uploads (with the appeal against a moderator's hold) and characters."""
import json

from apphelpers import go
from community import FIGHTS, LOG_ID

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


def moving_recording():
    """A boss fight with recorded movement (0.2.350): the boss walks east, the party member moves and once shows
    up far away (back at a respawn point), and the recording player is placed only by the effects they apply. The
    trash fight before it has the recording player's movement and no boss."""
    doc = recording()
    me, ally = "p:1101:1", "p:1101:2"
    doc["players"].append({"id": ally, "name": "Testally", "class": "Cleric", "server": "1101"})
    fight = doc["segments"][1]
    fight["movement"] = (
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
