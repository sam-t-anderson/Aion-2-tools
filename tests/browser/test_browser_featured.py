"""Featured encounters (log server 0.2.145): the encounters the server's operator features sit at the top of the
Combat Logs page, above its tabs, each with its landing cards; each has a race summary, progress, all reports,
rankings and statistics page, reached from its cards and its own navigation."""
import pytest

from apphelpers import axe_findings, close_context, go, open_context, watched_page
from community import FEATURED_ID, LOG_ID

CARDS = ["Progress", "Speed", "Execution", "All Stars (DPS)", "All Stars (Tank)", "All Stars (Support)", "DPS", "Tank Damage",
         "Support Damage"]
VIEWS = {"race": "Race Summary", "progress": "Progress", "reports": "All Reports", "rankings": "Rankings", "statistics": "Statistics"}


def open_featured(page, app_url, view, query=""):
    go(page, app_url, f"#/featured/{FEATURED_ID}/{view}{query}")
    page.wait_for_function("document.querySelector('[data-fe-body] table, [data-fe-body] .fe-race')")


def test_the_featured_encounters_sit_above_the_logs_tabs(app_page, app_url):
    page = app_page
    go(page, app_url, "#/combat")
    page.wait_for_function("document.querySelector('#featured .fe-zone')")
    above = page.evaluate("() => !!(document.querySelector('#featured').compareDocumentPosition(document.querySelector('#logs-tabs'))"
                          " & Node.DOCUMENT_POSITION_FOLLOWING)")
    assert above, "the featured encounters are not above the Browse logs tabs"
    zone = page.locator("#featured .fe-zone")
    assert zone.count() == 1 and zone.locator("h3").inner_text() == "Testlord race"
    assert zone.locator(".fe-card h4").all_inner_texts() == CARDS
    head, first = zone.locator(".fe-zone-head").bounding_box(), zone.locator(".fe-card").first.bounding_box()
    assert head["height"] > 40 and head["y"] + head["height"] <= first["y"], "the encounter's header overlaps its cards"
    tops = {round(zone.locator(".fe-card").nth(i).bounding_box()["y"]) for i in range(3)}
    assert len(tops) == 1, "the first three cards are not one row"                  # three a row, as fflogs' cards
    card = lambda title: zone.locator(".fe-card", has=page.locator("h4", has_text=title)).first
    # the legion that cleared it first, then the party still on the mini boss at 35.5%
    assert card("Progress").locator(".fe-who .fe-team").all_inner_texts() == ["Testers", "Testsorc's party"]
    assert card("Progress").locator(".fe-val").all_inner_texts() == ["Complete", "0/2 · 35.5%"]
    assert card("Speed").locator(".fe-val").all_inner_texts() == ["12:34"]
    assert card("Execution").locator(".fe-val").all_inner_texts() == ["1 death · 1:35"]
    assert card("All Stars (DPS)").locator(".fe-val").all_inner_texts() == ["187.5"]
    assert "No records yet." in card("All Stars (Tank)").inner_text()
    assert card("Support Damage").locator(".fe-val").all_inner_texts() == ["5,000"]
    # each card leads to the page with more, the speed card to the teams' speed ranking
    assert card("Speed").locator("a.fe-more").get_attribute("href") == f"#/featured/{FEATURED_ID}/rankings?metric=speed"
    assert card("Progress").locator("a.fe-more").get_attribute("href") == f"#/featured/{FEATURED_ID}/progress"
    links = zone.locator(".fe-nav a")
    assert links.all_inner_texts() == list(VIEWS.values())
    assert [links.nth(i).get_attribute("href") for i in range(5)] == [f"#/featured/{FEATURED_ID}/{v}" for v in VIEWS]
    links.first.click()
    page.wait_for_function("document.querySelector('.fe-race')")
    assert page.locator("#page-title").inner_text() == "Featured encounter"
    assert page.locator(".nav.sections a[data-section][aria-current]").get_attribute("data-section") == "combat"


def test_the_race_summary_shows_each_phase_then_the_teams(app_page, app_url, community):
    page = app_page
    open_featured(page, app_url, "race")
    assert page.locator(".fe-page h2").inner_text() == "Testlord race"
    assert page.locator('.fe-nav a[aria-current="page"]').inner_text() == "Race Summary"
    heads = page.locator(".fe-race .fe-race-head").all_inner_texts()               # the two bosses, then Complete!
    assert len(heads) == 3 and "Watcher Testling" in heads[0] and "Gatekeeper Testlord" in heads[1] and heads[2] == "Complete!"
    # one bar under them, filled as far as the leading team got (it finished)
    assert page.locator(".fe-race-track").get_attribute("aria-label") == "2 phases: a team has completed it"
    assert page.eval_on_selector_all(".fe-race-seg > span", "s => s.map(x => x.style.width)") == ["100%", "100%", "100%"]
    stats = page.locator(".fe-race > p").all_inner_texts()
    assert "2 reached · 1 killed" in stats[0] and "First: Testers" in stats[0] and stats[2] == "1 complete"
    # the party still on the mini boss stands under it, the legion that finished under Complete!
    lists = page.locator(".fe-race > ol.fe-standing")
    assert lists.nth(0).locator("li").all_inner_texts() == ["2. Testsorc's party 35.5%"]
    assert lists.nth(1).locator("li").count() == 0 and "1. Testers" in lists.nth(2).inner_text()
    closer = page.locator(".fe-closer")
    assert closer.count() == 2
    assert closer.nth(1).locator(".fe-members").inner_text() == "Testsorc, Testcleric"
    assert "working on" in closer.nth(1).inner_text().lower() and "complete!" in closer.nth(0).inner_text().lower()
    assert closer.first.locator("a.fe-more").get_attribute("href") == f"#/combat-log/shared/{LOG_ID}"
    # fflogs' "All regions": the regions the encounter was fought in
    assert page.locator("[data-region] option").all_inner_texts() == ["All regions", "KR", "NA"]
    since = len(community.requests)
    page.select_option("[data-region]", "nae")
    assert community.reached(page, f"/api/v1/featured/{FEATURED_ID}/race?region=nae", since)


def test_progress_reports_rankings_and_statistics(app_page, app_url, community):
    page = app_page
    open_featured(page, app_url, "progress")
    captions = page.locator(".fe-table caption").all_inner_texts()
    assert captions == ["Teams by progress", "Final-boss kills, first first"]
    rows = page.locator(".fe-table").first.locator("tbody tr")
    assert rows.count() == 2 and "Testers" in rows.first.inner_text() and "2/2" in rows.first.inner_text()
    kill = page.locator(".fe-table").nth(1).locator("tbody tr").first
    assert kill.locator(".fe-comp img").count() == 2 and "1:35" in kill.inner_text()

    open_featured(page, app_url, "reports")
    link = page.locator(".fe-table tbody tr a").first
    assert link.inner_text() == "Test run" and link.get_attribute("href") == f"#/combat-log/shared/{LOG_ID}"

    open_featured(page, app_url, "rankings")
    names = lambda: page.locator(".fe-table tbody .fe-classed").all_inner_texts()
    assert names() == ["Testsorc", "Testcleric"]
    # a ranked player's log opens at the ranked fight
    assert page.locator(".fe-table tbody a").first.get_attribute("href") == f"#/combat-log/shared/{LOG_ID}?segment=2"
    since = len(community.requests)
    page.select_option("[data-class]", "cleric")
    page.wait_for_function("document.querySelectorAll('.fe-table tbody tr').length === 1")
    assert names() == ["Testcleric"]
    assert community.reached(page, f"/api/v1/featured/{FEATURED_ID}/rankings?metric=dps&boss=npc%3A2390001&class=cleric", since)
    page.select_option("[data-boss]", "npc:2390002")                              # the mini boss
    page.wait_for_function("document.querySelector('.fe-table caption').textContent.includes('Watcher Testling')")
    page.select_option("[data-metric]", "speed")
    page.wait_for_function("document.querySelector('.fe-table caption').textContent.includes('fastest')")
    assert page.locator("[data-boss]").count() == 0 and "12:34" in page.locator(".fe-table tbody").inner_text()

    open_featured(page, app_url, "rankings", "?metric=speed")                    # the Speed card's link
    assert page.locator("[data-metric]").input_value() == "speed"

    open_featured(page, app_url, "statistics")
    classes = page.locator(".fe-table tbody tr td:first-child").all_inner_texts()
    assert [c.strip() for c in classes] == ["Sorcerer", "Cleric"]
    assert page.locator(".fe-bar-iqr").count() == 2


def test_an_unknown_featured_address_says_so(app_page, app_url):
    page = app_page
    go(page, app_url, "#/featured/not-an-id/race")
    assert "no featured encounter" in page.locator("#featured-page").inner_text()
    assert page.locator("a", has_text="Back to combat logs").count() == 1


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_featured_cards_and_pages_pass_axe(browser, app_url, axe_js, scheme):
    context = open_context(browser, app_url, scheme)
    try:
        page, watch = watched_page(context, app_url)
        problems = []
        go(page, app_url, "#/combat")
        page.wait_for_function("document.querySelector('#featured .fe-zone')")
        problems += [f"combat: {p}" for p in axe_findings(page, axe_js)]
        for view in VIEWS:
            open_featured(page, app_url, view)
            problems += [f"{view}: {p}" for p in axe_findings(page, axe_js)]
        problems += watch.unexpected()
        assert not problems, "\n".join(problems)
    finally:
        close_context(context)


def test_the_featured_cards_read_in_the_chosen_language_and_names_stay(browser, app_url):
    context = open_context(browser, app_url)
    context.add_init_script("try { localStorage.setItem('a2-lang', 'de'); } catch (e) {}")
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/combat")
        page.wait_for_function("document.querySelector('#featured .fe-zone') && document.documentElement.lang === 'de'")
        page.wait_for_function("document.querySelector('#featured h2').textContent === 'Hervorgehobene Begegnungen'")
        zone = page.locator("#featured .fe-zone")
        assert zone.locator(".fe-card h4").first.inner_text() == "Fortschritt"
        assert zone.locator(".fe-nav a").first.inner_text() == "Rennübersicht"
        # names from the game and from players are left as they are
        assert zone.locator("h3").inner_text() == "Testlord race"
        assert zone.locator(".fe-card .fe-team").first.inner_text() == "Testers"
        open_featured(page, app_url, "race")
        page.wait_for_function("document.querySelector('.fe-race-done').textContent === 'Abgeschlossen!'")
        assert "Watcher Testling" in page.locator(".fe-race-head").first.inner_text()
        assert "Phase 1" in page.locator(".fe-race-head").first.inner_text()
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
