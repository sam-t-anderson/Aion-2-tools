"""The Account page before signing in (pages/account.js, account-view.js): where the log server has accounts,
the page offers to create one and the header offers to sign in; where it has none, the page says the server's
reason and offers no sign-up that could only fail."""
from urllib.parse import parse_qs, urlparse

import community as stand_in
from apphelpers import close_context, go, open_context, until, watched_page

PROFILE = {"id": "acc_1", "name": "Seren", "logs": 1, "characters": [], "passkeys": 0, "apps": 1, "discord": None}
LOG = {"id": "log_1", "created_at": 1793000000, "visibility": "public", "title": "First kill", "boss": "Berk", "region": "nae",
       "source": "test", "duration": 300, "segments": 1, "top_dps": 20000, "uploader": "Seren", "players": 6, "via": "upload",
       "url": "http://logs.test/l/log_1", "held": False}


def _signed_in(page, asked, lists):
    """The app answers as a signed-in account whose log lists come from `lists(path)`; every account request is noted."""
    def account(route):
        if route.request.method == "GET":
            return route.fulfill(json={"signed_in": True, "here": True, "server": "http://logs.test", "account": PROFILE,
                                       "session": {"id": 1, "kind": "app"}})
        body = route.request.post_data_json or {}
        path = body.get("path") or ""
        asked.append(path)
        answer = lists(path) if body.get("action") == "request" else None
        return route.fulfill(json={} if answer is None else answer)
    page.route("**/api/account", account)


def _query(path):
    return {k: v[0] for k, v in parse_qs(urlparse(path).query).items()}


def test_my_logs_narrow_to_a_boss_and_to_days(browser, app_url):
    """My logs (0.2.368) filters by boss and by upload day. The From/To days are the viewer's own, as the table shows its
    times, so the server gets the instants they span; Clear brings everything back."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []

    def lists(path):
        if path.startswith("/api/v1/account/logs?"):
            rows = [] if "since" in _query(path) else [LOG]
            return {"logs": rows, "total": len(rows), "page": 1, "limit": 50}
        return None
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/logs")
        page.wait_for_selector("table.acct-logs")
        assert asked[-1] == "/api/v1/account/logs?page=1&limit=50" and not page.locator("[data-clear]").count()
        page.fill("[data-boss]", "Berk")
        page.fill("[data-since]", "2026-10-31")
        page.fill("[data-until]", "2026-10-31")
        page.click("[data-filter]")
        page.wait_for_selector("[data-clear]")
        assert _query(asked[-1]) == {"page": "1", "limit": "50", "boss": "Berk",
                                     "since": page.evaluate("new Date(2026, 9, 31).toISOString()"),
                                     "until": page.evaluate("new Date(2026, 10, 1).toISOString()")}
        assert page.locator("#account-root p.empty").inner_text() == "No logs match."
        # the filters are kept while the list is redrawn, and Clear drops them all
        assert page.input_value("[data-since]") == "2026-10-31" and page.input_value("[data-boss]") == "Berk"
        page.click("[data-clear]")
        page.wait_for_selector("table.acct-logs")
        assert asked[-1] == "/api/v1/account/logs?page=1&limit=50"
        assert page.input_value("[data-since]") == "" and page.input_value("[data-until]") == "" and page.input_value("[data-boss]") == ""
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_legions_logs_take_the_same_filters_and_pages(browser, app_url):
    """The legion's page lists its logs with the boss and From/To filters My logs has, and pages them (0.2.368,
    log server 0.2.160); the filters redraw only the list, not the legion's page."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    legion = {"id": "lg_0123456789ab", "name": "Testers", "server": "2102", "faction": "", "members": 1, "leader": "Seren",
              "description": "", "role": "member", "requests": [], "invites": [], "show_progress": False,
              "roster": [{"member": 1, "character": "Seren", "server": "2102", "role": "member", "joined_at": 1793000000,
                          "you": True, "claim": "active"}]}
    asked = []

    def lists(path):
        if path == f"/api/v1/legions/{legion['id']}":
            return legion
        if path.startswith(f"/api/v1/legions/{legion['id']}/logs?"):
            q = _query(path)
            rows = [dict(LOG, id=f"log_{i}", title=f"Kill {i}", member="Seren") for i in range(50)] if "since" not in q else []
            return {"logs": rows, "total": 120 if rows else 0, "page": int(q["page"]), "limit": 50}
        return None
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/legions/" + legion["id"])
        logs = page.locator("[data-legion-logs]")
        logs.locator("table").wait_for()
        assert asked[-1] == f"/api/v1/legions/{legion['id']}/logs?page=1&limit=50"
        assert logs.locator("[data-page]").inner_text() == "Next" and "Page 1 of 3" in logs.inner_text()
        pages_drawn = asked.count(f"/api/v1/legions/{legion['id']}")
        logs.locator("[data-page]").click()
        assert until(page, lambda: asked[-1] == f"/api/v1/legions/{legion['id']}/logs?page=2&limit=50")
        page.wait_for_function("document.querySelector('[data-legion-logs]').innerText.includes('Page 2 of 3')")
        logs.locator("[data-since]").fill("2026-10-31")
        logs.locator("[data-filter]").click()
        logs.locator("[data-clear]").wait_for()
        assert _query(asked[-1]) == {"page": "1", "limit": "50", "since": page.evaluate("new Date(2026, 9, 31).toISOString()")}
        assert logs.locator("p.empty").inner_text() == "No logs match."
        assert asked.count(f"/api/v1/legions/{legion['id']}") == pages_drawn      # the legion's page itself stayed
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_signing_up_is_offered_where_the_server_has_accounts(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/account/")
        page.wait_for_selector("[data-register]")
        assert page.locator("[data-register]").is_enabled()
        assert page.locator("#account-menu .acct-signin").inner_text() == "Sign in"
        assert not page.locator("#account-root div.note").count()      # no notice above the sign-up
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_server_without_accounts_says_so(browser, app_url):
    config = stand_in.ANSWERS.pop("/api/v1/account/config")
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/account/")
        page.wait_for_selector("[data-register]")
        assert page.locator("#account-root div.note").inner_text() == "not served by the test server"
        assert page.locator("[data-register]").is_disabled()
        assert page.locator("#account-menu .acct-signin").inner_text() == "Sign in"
    finally:
        stand_in.ANSWERS["/api/v1/account/config"] = config
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_the_legions_tab_points_at_my_character_identities(browser, app_url):
    """Signed in without a claimed character, Legions says where characters are claimed and links there."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    profile = {"id": "acc_1", "name": "Seren", "logs": 0, "characters": [], "passkeys": 0, "apps": 1, "discord": None}

    def account(route):
        if route.request.method == "GET":
            return route.fulfill(json={"signed_in": True, "here": True, "server": "http://logs.test", "account": profile,
                                       "session": {"id": 1, "kind": "app"}})
        body = route.request.post_data_json or {}
        if body.get("action") == "request" and body.get("path") == "/api/v1/legions/mine":
            return route.fulfill(json={"legions": []})
        return route.fulfill(json={})
    page.route("**/api/account", account)
    try:
        go(page, app_url, "#/account/legions")
        link = page.locator("#account-root a", has_text="Open My Character Identities")
        link.wait_for()
        assert "Combat Logs → My Character Identities" in page.locator("#account-root div.note").first.inner_text()
        link.click()
        page.wait_for_selector("#log-panel-identities:not([hidden])")
        assert page.evaluate("location.hash") == "#/combat/identities"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_the_leader_shows_the_legion_on_the_featured_encounter_pages(browser, app_url):
    """The featured encounters' race and progress pages (log server 0.2.145) show a legion only when its leader
    turns it on in the legion's page: off until then."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    profile = {"id": "acc_1", "name": "Seren", "logs": 0, "characters": [], "passkeys": 0, "apps": 1, "discord": None}
    legion = {"id": "lg_0123456789ab", "name": "Testers", "server": "2102", "faction": "", "members": 1, "leader": "Seren",
              "description": "", "role": "leader", "requests": [], "invites": [], "show_progress": False,
              "roster": [{"member": 1, "character": "Seren", "server": "2102", "role": "leader", "joined_at": 1793000000,
                          "you": True, "claim": "active"}]}
    posted, asked = [], []

    def account(route):
        if route.request.method == "GET":
            return route.fulfill(json={"signed_in": True, "here": True, "server": "http://logs.test", "account": profile,
                                       "session": {"id": 1, "kind": "app"}})
        body = route.request.post_data_json or {}
        path = body.get("path") or ""
        asked.append(path)
        if body.get("action") == "request" and path == f"/api/v1/legions/{legion['id']}/progress":
            posted.append(body.get("body"))
            legion["show_progress"] = (body.get("body") or {}).get("show") is True
            return route.fulfill(json=legion)
        if body.get("action") == "request" and path == f"/api/v1/legions/{legion['id']}":
            return route.fulfill(json=legion)
        if body.get("action") == "request" and path.startswith(f"/api/v1/legions/{legion['id']}/logs"):
            return route.fulfill(json={"logs": []})
        return route.fulfill(json={})
    page.route("**/api/account", account)
    try:
        go(page, app_url, "#/account/legions/" + legion["id"])
        box = page.locator("[data-show-progress]")
        box.wait_for()
        assert not box.is_checked()
        assert "its members are never listed" in page.locator("#account-root").inner_text()
        box.check()
        # the page draws the legion again with the server's answer; its logs are the last thing it asks for
        assert until(page, lambda: asked.count(f"/api/v1/legions/{legion['id']}/logs?page=1&limit=50") >= 2)
        page.wait_for_function("document.querySelector('[data-show-progress]')?.checked === true")
        assert posted == [{"show": True}]
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


TOP = {"parses": [
    {"character": "Seren", "server": "2102", "class": "sorcerer", "boss": "Gatekeeper Testlord", "boss_key": "npc:2390001",
     "encounter_type": "expedition", "game_patch": "version:product:2.0.10.0", "difficulty": "normal", "dps": 12345.6,
     "parse": 96.4, "parse_rank": 2, "parse_runs": 40, "provisional": False, "attempts": 3, "log": "log_1", "segment": 2,
     "duration": 120.0, "uploaded_at": 1793000000, "visibility": "public", "url": "http://logs.test/l/log_1"},
    {"character": "Seren", "server": "2102", "class": "sorcerer", "boss": "Watcher Testling", "boss_key": "npc:2390002",
     "encounter_type": "expedition", "game_patch": "version:product:2.0.10.0", "difficulty": "hard", "dps": 9000.0,
     "parse": None, "parse_rank": None, "parse_runs": 1, "provisional": False, "attempts": 1, "log": "log_2", "segment": 0,
     "duration": 60.0, "uploaded_at": 1793000500, "visibility": "private", "url": "http://logs.test/l/log_2?t=view"}],
    "total": 2, "truncated": False, "characters": 1, "note": ""}


def test_my_logs_show_the_accounts_top_parses(browser, app_url):
    """Top parses (0.2.391): the account's best run on each boss and difficulty with the rankings' parse, linked to its
    encounter. They are asked for before the list and once per visit: filtering the list does not ask again."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []

    def lists(path):
        if path.startswith("/api/v1/account/logs?"):
            return {"logs": [LOG], "total": 1, "page": 1, "limit": 50}
        return TOP if path == "/api/v1/account/top-parses" else None
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/logs")
        page.wait_for_selector("table.acct-parses")
        assert asked.index("/api/v1/account/top-parses") < asked.index("/api/v1/account/logs?page=1&limit=50")
        assert page.locator("[data-top-parses] h3").inner_text() == "Top parses"
        rows = page.locator("table.acct-parses tbody tr")
        assert rows.count() == 2
        cells = [c.strip() for c in rows.first.locator("td").all_inner_texts()]
        assert cells[:6] == ["Gatekeeper Testlord", "Normal", "Seren Zikel", "Sorcerer", "12,346", "96"]
        parse = rows.first.locator(".parse")
        assert "q-orange" in parse.get_attribute("class") and "rank 2 of 40" in parse.get_attribute("title")
        assert rows.first.locator("td.r").first.get_attribute("title") == "Best of 3 ranked runs"
        assert rows.first.locator("a").get_attribute("href") == "#/combat-log/shared/log_1?segment=2"
        lone = rows.nth(1).locator(".parse")
        assert lone.inner_text() == "·" and "q-none" in lone.get_attribute("class")
        # filtering the list redraws it without asking for the parses again
        page.fill("[data-boss]", "Berk")
        page.click("[data-filter]")
        page.wait_for_selector("[data-clear]")
        page.wait_for_selector("table.acct-parses")
        assert asked.count("/api/v1/account/top-parses") == 1
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_top_parses_wait_for_a_server_that_lists_them(browser, app_url):
    """A log server before 0.2.170 has no top parses: the section says so and the list is unaffected."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []

    def lists(path):
        if path.startswith("/api/v1/account/logs?"):
            return {"logs": [LOG], "total": 1, "page": 1, "limit": 50}
        return {"error": "not found"} if path == "/api/v1/account/top-parses" else None
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/logs")
        page.wait_for_selector("table.acct-logs")
        page.locator("[data-top-parses]").filter(has_text="doesn't list top parses yet").wait_for()
        assert page.locator("[data-top-parses]").inner_text().endswith("The community server doesn't list top parses yet.")
        assert not page.locator("table.acct-parses").count()
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
