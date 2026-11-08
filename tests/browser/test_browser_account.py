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



def _parses(asked):
    """The top-parses requests the tab made, as their queries."""
    return [_query(p) for p in asked if p.startswith("/api/v1/account/top-parses")]


def _server_0_2_171(path):
    if path.startswith("/api/v1/account/logs?"):
        return {"logs": [LOG], "total": 1, "page": 1, "limit": 50}
    if path.startswith("/api/v1/account/top-parses"):
        return stand_in.top_parses(_query(path))
    return None


def test_top_parses_are_a_tab_of_their_own(browser, app_url):
    """Top parses (0.2.392): their own tab, reached from the account menu and by its link; My logs no longer holds
    them. A page of the best parses first, and Previous / Next through the pages (log server 0.2.171)."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []
    _signed_in(page, asked, _server_0_2_171)
    try:
        go(page, app_url, "#/account/logs")
        page.wait_for_selector("table.acct-logs")
        assert not page.locator("table.acct-parses").count() and not any(p.startswith("/api/v1/account/top-parses") for p in asked)
        page.locator("#account-menu button[aria-haspopup]").click()
        link = page.locator("#account-menu .acct-drop a", has_text="Top parses")
        assert link.get_attribute("href") == "#/account/parses"
        tab = page.locator('[data-acct-tab="parses"]')
        assert [t.strip() for t in page.locator("[data-acct-tab]").all_inner_texts()] == ["My logs", "Top parses", "Legions", "Sign-in & security"]
        tab.click()
        page.wait_for_selector("table.acct-parses")
        assert page.evaluate("location.hash") == "#/account/parses" and tab.get_attribute("aria-selected") == "true"
        assert _parses(asked)[-1] == {"page": "1", "limit": "25", "sort": "parse", "order": "desc"}
        rows = page.locator("table.acct-parses tbody tr")
        assert rows.count() == 25
        assert page.locator("[data-pp-status]").inner_text() == "Page 1 of 2 · 30 parses"
        best = [float(t) for t in page.locator("table.acct-parses tbody .parse:not(.q-none)").all_inner_texts()[:3]]
        assert best == sorted(best, reverse=True)                     # the best parses first
        assert page.locator("[data-pp=prev]").is_disabled()
        page.click("[data-pp=next]")
        page.locator("[data-pp-status]").filter(has_text="Page 2 of 2").wait_for()
        assert _parses(asked)[-1]["page"] == "2" and rows.count() == 5 and page.locator("[data-pp=next]").is_disabled()
        # its link opens the tab straight away
        go(page, app_url, "#/account/parses")
        page.wait_for_selector("table.acct-parses")
        assert page.locator('[data-acct-tab="parses"]').get_attribute("aria-selected") == "true"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_top_parses_sort_filter_and_page_size(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []
    _signed_in(page, asked, _server_0_2_171)
    try:
        go(page, app_url, "#/account/parses")
        page.wait_for_selector("table.acct-parses")
        parse_head = page.locator('th:has(button[data-sort="parse"])')
        assert parse_head.get_attribute("aria-sort") == "descending" and "▼" in parse_head.inner_text()
        # a header sorts by its column, its first click in the column's own direction, the next reversing it
        page.click('button[data-sort="dps"]')
        page.locator('th[aria-sort="descending"]:has(button[data-sort="dps"])').wait_for()
        assert _parses(asked)[-1] == {"page": "1", "limit": "25", "sort": "dps", "order": "desc"}
        assert page.locator('th:has(button[data-sort="parse"])').get_attribute("aria-sort") == "none"
        page.click('button[data-sort="dps"]')
        page.locator('th[aria-sort="ascending"]:has(button[data-sort="dps"])').wait_for()
        assert _parses(asked)[-1]["order"] == "asc" and "▲" in page.locator('button[data-sort="dps"]').inner_text()
        first = page.locator("table.acct-parses tbody tr").first.locator("td").nth(4).inner_text()
        assert first == "10,000"                                       # the lowest DPS first
        page.click('button[data-sort="boss"]')
        page.locator('th[aria-sort="ascending"]:has(button[data-sort="boss"])').wait_for()
        # the menus come from the facets; a filter asks again from the first page, Reset brings everything back
        boss_menu = page.locator('select[data-pf="boss"] option').all_inner_texts()
        assert boss_menu[0] == "All bosses" and "Gatekeeper Testlord (6)" in boss_menu
        page.select_option('select[data-pf="cls"]', "cleric")
        page.locator("[data-pp-status]").filter(has_text="15 parses").wait_for()
        assert _parses(asked)[-1] == {"page": "1", "limit": "25", "sort": "boss", "order": "asc", "class": "cleric"}
        page.select_option('select[data-pf="character"]', "Seren|2102")
        page.locator("table.acct-parses").wait_for(state="detached")
        assert _parses(asked)[-1]["character"] == "Seren" and _parses(asked)[-1]["server"] == "2102"
        assert page.locator(".acct-top-empty").inner_text() == "No parses match."
        page.click("[data-pf-reset]")
        page.locator("[data-pp-status]").filter(has_text="30 parses").wait_for()
        assert "class" not in _parses(asked)[-1] and page.locator("[data-pf-reset]").is_disabled()
        # the page size is kept in this browser for the next visit
        page.select_option("[data-pl]", "50")
        page.locator("[data-pp-status]").filter(has_text="Page 1 of 1").wait_for()
        assert page.locator("table.acct-parses tbody tr").count() == 30
        assert page.evaluate("localStorage.getItem('aion2.account.parsesPerPage')") == "50"
        go(page, app_url, "#/account/parses")
        page.wait_for_selector("table.acct-parses")
        assert _parses(asked)[-1]["limit"] == "50" and page.locator("[data-pl]").input_value() == "50"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_0_2_170_servers_whole_list_is_paged_here(browser, app_url):
    """Log server 0.2.170 sends every row whatever is asked: the tab pages, sorts and filters them itself, asking once."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []

    def lists(path):
        if path.startswith("/api/v1/account/top-parses"):
            return stand_in.top_parses({})                                # no page, no facets
        return _server_0_2_171(path)
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/parses")
        page.wait_for_selector("table.acct-parses")
        assert page.locator("[data-pp-status]").inner_text() == "Page 1 of 2 · 30 parses"
        assert page.locator("table.acct-parses tbody tr").count() == 25
        here = [float(t) for t in page.locator("table.acct-parses tbody .parse:not(.q-none)").all_inner_texts()]
        assert here == sorted(here, reverse=True)
        page.click('button[data-sort="dps"]')
        page.click('button[data-sort="dps"]')
        page.locator('th[aria-sort="ascending"]:has(button[data-sort="dps"])').wait_for()
        assert page.locator("table.acct-parses tbody tr").first.locator("td").nth(4).inner_text() == "10,000"
        page.select_option('select[data-pf="cls"]', "cleric")
        page.locator("[data-pp-status]").filter(has_text="Page 1 of 1 · 15 parses").wait_for()
        assert set(page.locator("table.acct-parses tbody td:nth-child(4)").all_inner_texts()) == {"Cleric"}
        page.click("[data-pf-reset]")
        page.click("[data-pp=next]")
        page.locator("[data-pp-status]").filter(has_text="Page 2 of 2").wait_for()
        assert len(_parses(asked)) == 1                                   # the list was asked for once
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_top_parses_wait_for_a_server_that_lists_them(browser, app_url):
    """A log server before 0.2.170 has no top parses: the tab says so."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    asked = []

    def lists(path):
        if path.startswith("/api/v1/account/top-parses"):
            return {"error": "not found"}
        return _server_0_2_171(path)
    _signed_in(page, asked, lists)
    try:
        go(page, app_url, "#/account/parses")
        page.locator("[data-acct-body]").filter(has_text="doesn't list top parses yet").wait_for()
        assert page.locator("[data-acct-body]").inner_text().strip() == "The community server doesn't list top parses yet."
        assert not page.locator("table.acct-parses").count()
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
