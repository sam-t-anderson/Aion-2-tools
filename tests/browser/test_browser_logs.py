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
    for tab in ("owned", "saved", "community"):
        page.click(f"#log-tab-{tab}")
        assert shown() == [tab] and page.locator(f"#log-tab-{tab}").get_attribute("aria-selected") == "true"
    page.focus("#log-tab-community")
    page.keyboard.press("ArrowRight")                                                 # the arrow keys move along them
    assert shown() == ["owned"] and page.evaluate("document.activeElement.id") == "log-tab-owned"
    page.keyboard.press("End")
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
        page.click("#log-tab-owned")
    assert answer.value.ok
    page.wait_for_function("document.querySelector('#my-characters').children.length > 0")
