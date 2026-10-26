"""The app's navigation (0.2.342): three sections, Combat, Character and Game, and Settings, with the pages of
the current section in a row underneath; every page opens without an error, under one main heading named
after it, and without a serious accessibility problem in either theme."""
import pytest

from apphelpers import axe_findings, go, on_page, open_context, watched_page

# Each page with its section and the name it shows; the order is the navigation's.
PAGES = [("meter", "combat", "Live Meter"), ("combat", "combat", "Combat Logs"), ("raid", "combat", "Raid Planner"),
         ("planner", "character", "Build Planner"), ("builds", "character", "Builds"),
         ("character", "character", "My Character"), ("gear", "character", "Gear & Advice"),
         ("history", "character", "Saved Results"), ("timers", "game", "Timers"), ("maps", "game", "Maps"),
         ("database", "game", "Database"), ("crafting", "game", "Crafting"), ("pets", "game", "Pet Tracker"),
         ("news", "game", "News"), ("settings", None, "Settings")]


def shown(page) -> list:
    """[the section link marked current, the pages listed underneath, the page marked current there]."""
    return page.evaluate("""() => [
        (document.querySelector('.nav.sections a[data-section][aria-current]') || {}).textContent || null,
        [...document.querySelectorAll('.subnav [data-pages]:not([hidden]) a')].map(a => a.textContent),
        (document.querySelector('.subnav a[aria-current="page"]') || {}).textContent || null]""")


def test_a_section_lists_its_pages_and_returns_to_the_page_last_used_in_it(app_page, app_url):
    page = app_page
    sections = page.locator(".nav.sections")
    go(page, app_url, "#/meter")
    assert shown(page) == ["Combat", ["Live Meter", "Combat Logs", "Raid Planner"], "Live Meter"]
    sections.get_by_role("link", name="Character").click()
    on_page(page, "Build Planner")
    assert shown(page) == ["Character", ["Build Planner", "Builds", "My Character", "Gear & Advice", "Saved Results"],
                           "Build Planner"]
    page.locator(".subnav").get_by_role("link", name="Gear & Advice").click()
    on_page(page, "Gear & Advice")
    sections.get_by_role("link", name="Combat").click()                      # back where Combat was left
    on_page(page, "Live Meter")
    sections.get_by_role("link", name="Character").click()                   # and Character, on Gear & Advice
    on_page(page, "Gear & Advice")
    sections.get_by_role("link", name="Settings").click()                    # in no section: the row stays as it was
    on_page(page, "Settings")
    current, listed, on = shown(page)
    assert current is None and listed[0] == "Build Planner" and on is None
    assert sections.get_by_role("link", name="Settings").get_attribute("aria-current") == "page"
    assert page.locator(".subnav").get_attribute("aria-label") == "Character pages"
    go(page, app_url, "#/meter")                                             # remembered after a restart too
    assert sections.get_by_role("link", name="Character").get_attribute("href") == "#/gear"


def test_leaving_a_page_before_it_has_loaded_raises_no_script_error(app_page, app_url):
    """A page's requests can still be on their way when the player moves on: what they then find gone is no
    error (the Live Meter's capture interfaces and the Build Planner's build raised one)."""
    page = app_page
    go(page, app_url, "#/meter")
    for wait in (100, 400):
        for page_id, _, _ in PAGES + PAGES[:1]:
            page.evaluate("id => { location.hash = '/' + id; }", page_id)
            page.wait_for_timeout(wait)
    page.wait_for_timeout(2500)                                              # what was still on its way arrives


# The app's settings, status, characters and builds answer 0.4 s late, so a page that waits for them is left
# while it waits.
SLOW_START = """(() => { const fetch_ = window.fetch;
  window.fetch = (input, init) => { const answer = fetch_(input, init);
    return /\\/api\\/(ui|status|logserver|characters|planner\\/presets)(\\?|$)/.test(String(input)) && !(init && init.method)
      ? answer.then((r) => new Promise((done) => setTimeout(() => done(r), 400))) : answer; }; })();"""


def test_a_page_left_while_it_loads_does_not_draw_over_the_next(app_page, app_url):
    """The pages that wait for the app before they draw (the Live Meter, Settings, Gear & Advice, the Raid
    Planner, Pet Tracker) used to draw over the page the player had moved on to meanwhile, and one that fails
    on its own page once it is gone (the Build Planner) showed its error there ("Cannot set properties of
    null" on My Character)."""
    page = app_page
    page.add_init_script(SLOW_START)
    go(page, app_url, "#/news")
    for left, own in (("meter", "#mstart"), ("settings", "[data-settab]"), ("gear", "#gadvice-progress"),
                      ("raid", "#rbrowse"), ("pets", "#pt-head"), ("planner", "#res")):
        page.evaluate("id => { location.hash = '/' + id; }", left)
        page.wait_for_timeout(50)
        page.evaluate("() => { location.hash = '/character'; }")
        page.wait_for_timeout(1200)                                          # the page left gets its answers
        drawn = page.evaluate("own => [!!document.querySelector('#nm'), !!document.querySelector(own)]", own)
        assert drawn == [True, False], f"{left} drew over My Character"


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_every_page_opens_cleanly_under_one_heading(browser, app_url, axe_js, community, scheme):
    context = open_context(browser, app_url, scheme)
    unknown = len(community.unknown)                                         # what earlier tests asked for is theirs
    try:
        page, watch = watched_page(context, app_url)
        problems = []
        for page_id, section, name in PAGES:
            go(page, app_url, "#/" + page_id)
            headings = page.locator("h1").all_inner_texts()
            if headings != [name]:
                problems.append(f"{page_id}: main headings {headings}, expected [{name!r}]")
            current = page.locator(".nav.sections a[data-section][aria-current]")
            if (current.get_attribute("data-section") if current.count() else None) != section:
                problems.append(f"{page_id}: the {section} section is not marked current")
            problems += [f"{page_id}: {p}" for p in axe_findings(page, axe_js)]
        problems += watch.unexpected()                                      # the portraits' 404 used to be here
        problems += [f"the test log server does not serve {path}" for path in community.unknown[unknown:]]
        assert not problems, "\n".join(problems)
    finally:
        context.close()
