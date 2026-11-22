"""The interfaces' own data in the app (0.2.482, ``static/store.js``): a page of the app finds in its browser's storage
what the app keeps, before its first script reads it, and what the page changes there goes to the app, where the
native window and the player's other browsers find it. A browser that kept data of its own before gives it to the app
once; a change the app had not yet kept when the next page opened is put back and sent again."""
import json
import urllib.request

from apphelpers import close_context, go, open_context, until, watched_page


def kept(base: str) -> dict:
    with urllib.request.urlopen(base + "api/interface", timeout=10) as answer:
        return json.load(answer)["values"]


def keep(base: str, changes: dict) -> None:
    """A change made elsewhere: in the native window, or another browser."""
    body = json.dumps({"set": changes}).encode()
    request = urllib.request.Request(base + "api/interface", body, {"Content-Type": "application/json"})
    urllib.request.urlopen(request, timeout=10).close()


LOOK = "[document.documentElement.dataset.theme || '', document.documentElement.dataset.accent || '', document.documentElement.lang]"


def test_a_page_reads_the_apps_choices_before_its_first_script(browser, app_url):
    context = open_context(browser, app_url)
    keep(app_url, {"theme": "light", "accent": "azure", "a2-lang": "de"})
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/meter")
        assert page.evaluate(LOOK) == ["light", "azure", "de"]           # the theme's script and i18n.js read them
        assert page.locator(".subnav a[data-page=meter]").inner_text() == "Live-Meter"
        assert page.evaluate("localStorage.getItem('a2-store-browser')") == "1"
        # the app's data is the whole of it: what the app forgot (in the native window, say) goes from the browser
        keep(app_url, {"accent": None, "a2-lang": None})
        go(page, app_url, "#/meter")
        assert page.evaluate(LOOK) == ["light", "", "en"]
        assert page.evaluate("localStorage.getItem('a2-lang')") is None
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_what_a_page_changes_goes_to_the_app(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/meter")
        page.evaluate("""() => {
            localStorage.setItem('a2-settab', 'overlay');
            localStorage.setItem('theme', 'light');
            localStorage.removeItem('theme');
            localStorage.setItem('aion2calc-closing', '1700000000000');   // a message between the browser's windows
            sessionStorage.setItem('a2-overlay-reloads', '2');            // the tab's own storage
        }""")
        assert until(page, lambda: kept(app_url).get("a2-settab") == "overlay")
        values = kept(app_url)
        assert not {"theme", "aion2calc-closing", "a2-overlay-reloads", "a2-store-browser", "a2-store-pending"} & set(values)
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-pending')") is None)   # the app kept it
        # clearing the storage forgets the page's data in the app too; the browser stays one that gave its data over
        page.evaluate("localStorage.clear()")
        assert until(page, lambda: "a2-settab" not in kept(app_url))
        assert page.evaluate("localStorage.getItem('a2-store-browser')") == "1"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_browsers_own_data_goes_to_the_app_once(browser, app_url):
    context = open_context(browser, app_url)
    keep(app_url, {"accent": "rose"})
    page, watch = watched_page(context, app_url)
    try:
        # what a browser kept until 0.2.482, written where the store's script is not (an answer of the app)
        page.goto(app_url + "api/status")
        page.evaluate("""() => {
            localStorage.setItem('theme', 'light');
            localStorage.setItem('accent', 'emerald');
            localStorage.setItem('a2plans', '{"p1":{"meta":{"name":"Kept plan"}}}');
            localStorage.setItem('aion2calc-closing', '1700000000000');
        }""")
        go(page, app_url, "#/meter")
        assert until(page, lambda: kept(app_url).get("a2plans") == '{"p1":{"meta":{"name":"Kept plan"}}}')
        values = kept(app_url)
        assert values["theme"] == "light" and values["accent"] == "rose" and "aion2calc-closing" not in values
        assert page.evaluate(LOOK)[:2] == ["light", "rose"]                 # where both had one, the app's
        assert page.evaluate("localStorage.getItem('aion2calc-closing')") == "1700000000000"
        # the browser is marked once the app said it kept its data, not before
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-browser')") == "1")
        # once only: what the browser holds after that without the app, the next page takes away
        page.goto(app_url + "api/status")
        page.evaluate("localStorage.setItem('written-behind', '1')")
        keep(app_url, {"a2plans": None})
        go(page, app_url, "#/meter")
        assert page.evaluate("[localStorage.getItem('a2plans'), localStorage.getItem('written-behind')]") == [None, None]
        assert "written-behind" not in kept(app_url)
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_changes_made_while_one_is_sent_go_together(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    held, posts = [], []

    def hold(route):
        if route.request.method != "POST":
            return route.continue_()
        posts.append(json.loads(route.request.post_data)["set"])
        if held:
            return route.continue_()
        held.append(route)                                               # the app takes its time over the first

    try:
        go(page, app_url, "#/meter")
        page.route("**/api/interface", hold)
        page.evaluate("localStorage.setItem('a2-test-drag', '0.9')")
        assert until(page, lambda: held)
        page.evaluate("""async () => {                                    // a slider dragged, a step a task
            for (const step of ['0.8', '0.7', '0.6', '0.5']) {
                localStorage.setItem('a2-test-drag', step);
                await new Promise((done) => setTimeout(done, 20));
            }
            localStorage.removeItem('a2-test-gone');
        }""")
        assert len(posts) == 1 and posts[0]["a2-test-drag"] == "0.9"       # nothing more while the first is on its way
        held[0].continue_()
        assert until(page, lambda: len(posts) == 2)
        assert posts[1]["a2-test-drag"] == "0.5" and posts[1]["a2-test-gone"] is None
        assert until(page, lambda: kept(app_url).get("a2-test-drag") == "0.5")
        page.wait_for_timeout(300)
        assert len(posts) == 2
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_browser_is_marked_only_once_the_app_kept_its_data(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        page.goto(app_url + "api/status")
        page.evaluate("localStorage.setItem('a2-settab', 'server')")      # what the browser kept until 0.2.482
        page.route("**/api/interface", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
        go(page, app_url, "#/meter")                                     # given to an app that does not answer
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-pending')"))
        assert page.evaluate("localStorage.getItem('a2-store-browser')") is None and "a2-settab" not in kept(app_url)
        page.unroute("**/api/interface")
        go(page, app_url, "#/meter")                                     # nothing lost: given again
        assert page.evaluate("localStorage.getItem('a2-settab')") == "server"
        assert until(page, lambda: kept(app_url).get("a2-settab") == "server")
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-pending')") is None)
        assert page.evaluate("localStorage.getItem('a2-store-browser')") == "1"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_change_the_app_had_not_kept_is_put_back_on_the_next_page(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/meter")
        page.route("**/api/interface", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
        page.evaluate("localStorage.setItem('a2-lang', 'fr')")           # the app does not answer
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-pending')"))
        assert json.loads(page.evaluate("localStorage.getItem('a2-store-pending')")) == {"a2-lang": "fr"}
        assert "a2-lang" not in kept(app_url)
        page.unroute("**/api/interface")
        go(page, app_url, "#/meter")                                     # the app's data, without the change
        assert page.evaluate("document.documentElement.lang") == "fr"
        assert until(page, lambda: kept(app_url).get("a2-lang") == "fr")
        assert until(page, lambda: page.evaluate("localStorage.getItem('a2-store-pending')") is None)
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_language_chosen_in_one_browser_opens_the_next_in_it(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    other = None
    try:
        go(page, app_url, "#/meter")
        page.select_option("#lang-slot select", "de")                    # the page reloads in German at once
        page.wait_for_function("document.documentElement.lang === 'de'")
        assert until(page, lambda: kept(app_url).get("a2-lang") == "de")
        other = open_context(browser, app_url, forget=False)              # the player's other browser, or the app window
        second, second_watch = watched_page(other, app_url)
        go(second, app_url, "#/meter")
        assert second.evaluate("document.documentElement.lang") == "de"
        assert second.locator("#lang-slot select").input_value() == "de"
        assert not second_watch.unexpected(), second_watch.unexpected()
    finally:
        if other is not None:
            close_context(other)
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
