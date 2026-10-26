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


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_every_page_opens_cleanly_under_one_heading(browser, app_url, axe_js, scheme):
    context = open_context(browser, app_url, scheme)
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
        assert not problems, "\n".join(problems)
    finally:
        context.close()
