"""The app in another language (i18n.js): the choice in the header is kept, the navigation and the account
page read in that language, names stay as they are, and choosing English again brings the English back."""
from apphelpers import close_context, go, open_context, watched_page


def test_the_app_reads_in_the_chosen_language_and_back(browser, app_url):
    context = open_context(browser, app_url)
    context.add_init_script("try { if (!sessionStorage.getItem('chosen')) { localStorage.setItem('a2-lang', 'de');"
                            " sessionStorage.setItem('chosen', '1'); } } catch (e) {}")
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/meter")
        page.wait_for_function("document.documentElement.lang === 'de'")
        sections = page.evaluate("[...document.querySelectorAll('.nav.sections a')].map(a => a.textContent)")
        assert sections == ["Kampf", "Charakter", "Spiel", "Einstellungen"]
        assert page.locator(".subnav a[data-page=meter]").inner_text() == "Live-Meter"
        assert page.locator("#lang-slot select").input_value() == "de"
        go(page, app_url, "#/account/")
        page.wait_for_selector("[data-register]")
        assert page.locator("[data-register]").inner_text() == "Mein Konto erstellen"
        assert page.locator(".brand").text_content().startswith("Aion 2 Calc")    # a name, not translated
        page.select_option("#lang-slot select", "en")                            # reloads in English
        page.wait_for_function("document.documentElement.lang === 'en'")
        page.wait_for_selector("[data-register]")
        assert page.locator("[data-register]").inner_text() == "Create my account"
        assert page.evaluate("[...document.querySelectorAll('.nav.sections a')].map(a => a.textContent)")[0] == "Combat"
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
