"""What the app does as it opens: it applies the text size and opens the chosen page when its address has
none (an address with a page opens that page), it offers a waiting update once a window, naming the newest
release, and it tells an install whose uploads became public so, once. Each test puts its settings back,
since the tests share one running app."""
import json

from apphelpers import go, on_page, open_context, open_settings, posted, watched_page


def test_the_text_size_applies_at_once_and_at_each_launch(app_page, app_url):
    open_settings(app_page, app_url, "system")
    assert posted(app_page, lambda: app_page.select_option("#textscale", "120")) == {"app_text_scale": 120}
    assert app_page.evaluate("document.body.style.zoom") == "1.2"
    go(app_page, app_url, "#/meter")                                     # a fresh launch
    assert app_page.evaluate("document.body.style.zoom") == "1.2"
    open_settings(app_page, app_url, "system")
    posted(app_page, lambda: app_page.select_option("#textscale", "100"))
    assert app_page.evaluate("document.body.style.zoom") == ""


def test_the_app_opens_on_the_chosen_page_unless_its_address_names_one(app_page, app_url):
    open_settings(app_page, app_url, "system")
    posted(app_page, lambda: app_page.select_option("#defaultpage", "timers"))
    go(app_page, app_url, "")                                            # the app's window, the tray icon
    on_page(app_page, "Timers")
    assert app_page.evaluate("location.hash") == "#/timers"
    go(app_page, app_url, "#/maps")
    on_page(app_page, "Maps")
    open_settings(app_page, app_url, "system")
    posted(app_page, lambda: app_page.select_option("#defaultpage", "meter"))
    go(app_page, app_url, "")
    on_page(app_page, "Live Meter")
    assert app_page.evaluate("location.hash") == ""                      # the Live Meter needs no address


def with_update(page, newest="99.1.0"):
    """The app's status says release 99.0.0 is out, and a fresh check finds ``newest``."""
    asked = []

    def status(route):
        asked.append(route.request.url)
        body = route.fetch().json()
        route.fulfill(json={**body, "update": {"version": "99.0.0", "url": "https://github.com/x/releases/tag/v99.0.0"}})
    page.route("**/api/status*", status)
    page.route("**/api/update/check", lambda r: r.fulfill(json={"update": {"version": newest, "url": "https://github.com/x"}}))
    return asked


def test_a_waiting_update_is_offered_once_a_window_naming_the_newest_release(browser, app_url):
    context = open_context(browser, app_url)
    try:
        page, watch = watched_page(context, app_url)
        asked = with_update(page)
        prompts = []
        page.on("dialog", lambda d: (prompts.append(d.message), d.dismiss()))
        go(page, app_url, "#/meter")
        page.wait_for_function("document.querySelector('#update') && !document.querySelector('#update').hidden")
        assert page.locator("#update").inner_text() == "Version 99.0.0 available"
        page.wait_for_timeout(800)
        assert len(prompts) == 1 and prompts[0].startswith("Aion 2 Calc 99.1.0 is ready (you have ")
        assert "This installs the newest version directly, not the versions in between." in prompts[0]
        assert asked[0].endswith("/api/status?fresh=1")               # the window's first look asks for a fresh check
        page.reload()
        page.wait_for_timeout(1500)
        assert len(prompts) == 1                                      # the same window does not ask again
        other = context.new_page()                                    # another window does
        with_update(other)
        other.on("dialog", lambda d: (prompts.append(d.message), d.dismiss()))
        go(other, app_url, "#/meter")
        page.wait_for_timeout(800)
        assert len(prompts) == 2
        assert not watch.unexpected(), watch.unexpected()
    finally:
        context.close()


def test_an_update_is_not_offered_when_a_fresh_check_finds_none_and_an_accepted_one_says_how_it_went(browser, app_url):
    context = open_context(browser, app_url)
    try:
        page, watch = watched_page(context, app_url)
        with_update(page)
        page.unroute("**/api/update/check")                           # the release was withdrawn meanwhile
        page.route("**/api/update/check", lambda r: r.fulfill(json={"update": None, "update_state": {"checked_at": 1700000000}}))
        prompts = []
        page.on("dialog", lambda d: (prompts.append(d.message), d.accept()))
        go(page, app_url, "#/meter")
        page.wait_for_timeout(800)
        assert prompts == []
        other = context.new_page()                                   # a new window, and GitHub is out of reach
        with_update(other)
        other.on("dialog", lambda d: (prompts.append(d.message), d.accept()))
        other.route("**/api/update", lambda r: r.fulfill(json={"status": "check-failed"}))
        go(other, app_url, "#/meter")
        other.get_by_text("Could not reach GitHub for the update. Try again in a minute.").wait_for()
        assert len(prompts) == 1
        assert not watch.unexpected(), watch.unexpected()
    finally:
        context.close()


def test_a_check_still_running_is_looked_at_again_soon(app_page, app_url):
    asked = []

    def status(route):
        asked.append(route.request.url)
        body = route.fetch().json()
        route.fulfill(json={**body, "update": None, "update_state": {"checking": True}})
    app_page.route("**/api/status*", status)
    go(app_page, app_url, "#/maps")
    app_page.wait_for_timeout(2600)
    assert len(asked) >= 2                                            # every 2 s while checking, not every 20 s
    assert asked[1].endswith("/api/status")


def test_an_install_whose_uploads_became_public_is_told_once(app_page, app_url):
    page = app_page
    sent = []

    def logserver(route):
        if route.request.method == "POST":
            sent.append(json.loads(route.request.post_data))
            return route.fulfill(json={})
        answer = route.fetch()                                                  # unlisted by the old default
        route.fulfill(response=answer, json={**answer.json(), "visibility_notice": True})
    page.route("**/api/logserver", logserver)
    go(page, app_url, "#/meter")
    page.get_by_text("Your uploads are now public: they appear in the community logs and count in the rankings.").wait_for()
    assert sent == [{"action": "notice-seen"}]                                  # so it is not told again
