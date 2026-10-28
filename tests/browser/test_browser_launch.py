"""What the app does as it opens: it applies the text size and opens the chosen page when its address has
none (an address with a page opens that page), it shows a newer release's quiet download at the bottom left and
offers Update now without a popup, and it tells an install whose uploads became public so, once. Each test puts its settings back,
since the tests share one running app."""
import json

from apphelpers import close_context, go, on_page, open_context, open_settings, posted, until, watched_page


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


def with_download(page, download):
    """The app's status says release 99.1.0 is out and its background download is ``download()`` (0.2.353)."""
    def status(route):
        body = route.fetch().json()
        route.fulfill(json={**body, "update": {"version": "99.1.0", "url": "https://github.com/x/releases/tag/v99.1.0"},
                            "update_download": download(), "update_on_close": True})
    page.route("**/api/status*", status)


def test_an_update_downloads_quietly_at_the_bottom_left_then_offers_update_now(browser, app_url):
    """No popup: the download's progress in the small bar at the bottom left, then Update now and "Update when the
    app closes", ticked unless the player unticks it; the newest release is what downloads."""
    context = open_context(browser, app_url)
    try:
        page, watch = watched_page(context, app_url)
        download = {"state": "downloading", "version": "99.1.0", "kind": "installer", "received": 25, "total": 100}
        with_download(page, lambda: dict(download))
        prompts = []
        page.on("dialog", lambda d: (prompts.append(d.message), d.dismiss()))
        go(page, app_url, "#/meter")
        bar = page.locator("#updbar")
        bar.locator("progress").wait_for()
        assert "Downloading version 99.1.0" in bar.inner_text() and bar.locator("progress").evaluate("p => p.value") == 25
        assert page.locator("#update").is_hidden()                 # the bar says it; the header chip does not
        download.update(state="ready", received=100)                 # looked at again every second while downloading
        bar.get_by_text("Update ready: version 99.1.0").wait_for(timeout=5000)
        close = bar.locator("[data-upd-close]")
        assert close.is_checked()
        assert posted(page, lambda: close.uncheck()) == {"update_on_close": False}
        posted(page, lambda: close.check())                          # put back: the tests share the app
        page.route("**/api/update", lambda r: r.fulfill(json={"status": "launching"}))
        bar.locator("[data-upd-now]").click()
        page.get_by_text("Aion 2 Calc is closing. The installer will open in a moment.").wait_for()
        assert prompts == []
        assert not watch.unexpected(), watch.unexpected()
    finally:
        close_context(context)


def test_a_newer_release_with_nothing_downloading_only_shows_the_chip(browser, app_url):
    """A copy run from source, or with background updates off, downloads nothing: the header names the release and
    nothing pops up."""
    context = open_context(browser, app_url)
    try:
        page, watch = watched_page(context, app_url)
        with_download(page, lambda: {"state": "idle"})
        prompts = []
        page.on("dialog", lambda d: (prompts.append(d.message), d.dismiss()))
        go(page, app_url, "#/meter")
        page.wait_for_function("document.querySelector('#update') && !document.querySelector('#update').hidden")
        assert page.locator("#update").inner_text() == "Version 99.1.0 available"
        page.wait_for_timeout(800)
        assert page.locator("#updbar").is_hidden() and prompts == []
        assert not watch.unexpected(), watch.unexpected()
    finally:
        close_context(context)


def test_a_check_still_running_is_looked_at_again_soon(app_page, app_url):
    asked = []

    def status(route):
        asked.append(route.request.url)
        body = route.fetch().json()
        route.fulfill(json={**body, "update": None, "update_state": {"checking": True}})
    app_page.route("**/api/status*", status)
    go(app_page, app_url, "#/maps")
    until(app_page, lambda: len(asked) >= 2, timeout_ms=8000)
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


def test_the_patch_notes_show_once_after_an_update_and_settings_shows_them_again(browser, app_url):
    """What's new (0.2.353): after an update the new version's notes open over the page once; closing them tells the
    app, and Settings' What's new opens this version's notes again from the changelog the app carries."""
    context = open_context(browser, app_url)
    try:
        page, watch = watched_page(context, app_url)
        notes = {"version": "99.1.0", "all": "https://github.com/sam-t-anderson/Aion-2-tools/releases", "show": True,
                 "notes": [{"version": "99.1.0", "title": "Newest", "html": "<p>New <strong>things</strong>.</p>"},
                           {"version": "99.0.0", "title": "Older", "html": "<ul><li>older</li></ul>"}]}
        seen = []

        def patch_notes(route):
            if route.request.method == "POST":
                seen.append(json.loads(route.request.post_data))
                notes["show"] = False                                 # as the app records it: once
                return route.fulfill(json={"seen": "99.1.0"})
            if "force=1" in route.request.url:
                return route.continue_()                              # Settings: the real changelog's section
            route.fulfill(json=notes)
        page.route("**/api/patch-notes*", patch_notes)
        go(page, app_url, "#/meter")
        dialog = page.locator("dialog#patch-notes")
        dialog.wait_for()
        assert dialog.locator("h2").inner_text() == "What's new in Aion 2 Calc 99.1.0"
        assert dialog.locator("h3").all_inner_texts() == ["Newest 99.1.0", "Older 99.0.0"]
        assert dialog.locator("a").get_attribute("href").endswith("/releases")
        dialog.locator("[data-close]").click()
        until(page, lambda: seen)
        assert seen == [{"action": "seen"}] and page.locator("dialog#patch-notes").count() == 0
        open_settings(page, app_url, "system")
        page.click("#whatsnew")
        page.locator("dialog#patch-notes").wait_for()
        version = page.evaluate("api('/api/status').then(s => s.version)")
        assert page.locator("dialog#patch-notes h2").inner_text() == f"What's new in Aion 2 Calc {version}"
        page.keyboard.press("Escape")                                  # closes it; Settings' copy records nothing
        page.wait_for_function("!document.querySelector('dialog#patch-notes')")
        assert seen == [{"action": "seen"}]
        assert not watch.unexpected(), watch.unexpected()
    finally:
        close_context(context)
