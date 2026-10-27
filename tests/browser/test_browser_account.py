"""The Account page before signing in (pages/account.js, account-view.js): where the log server has accounts,
the page offers to create one and the header offers to sign in; where it has none, the page says the server's
reason and offers no sign-up that could only fail."""
import community as stand_in
from apphelpers import close_context, go, open_context, until, watched_page


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
        assert until(page, lambda: asked.count(f"/api/v1/legions/{legion['id']}/logs?limit=50") >= 2)
        page.wait_for_function("document.querySelector('[data-show-progress]')?.checked === true")
        assert posted == [{"show": True}]
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
