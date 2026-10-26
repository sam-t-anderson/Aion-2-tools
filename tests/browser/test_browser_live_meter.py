"""The Live Meter page (0.2.342): Start, the overlay, the session buttons, the view controls and the run's
status stay in view; the capture settings (network interface, game port, name override, game installation,
final boss) and the diagnostics sit under a closed "Advanced capture", which remembers being opened and
opens by itself when the player has a choice to make there. Npcap shows above it only when it needs doing."""
import json

from apphelpers import go


def visible(page, selector: str) -> bool:
    return page.locator(selector).first.is_visible()


def test_advanced_capture_starts_closed_and_holds_the_capture_settings(app_page, app_url):
    page = app_page
    go(page, app_url, "#/meter")
    advanced = page.locator("#madvanced")
    assert advanced.evaluate("d => d.open") is False
    for everyday in ("#msrc", "#mstart", "#mautooverlay", "#movl", "#mscope", "#msegments", "#mrun"):
        assert page.locator(everyday).evaluate("(n, d) => !d.contains(n)", advanced.element_handle()), everyday
    page.select_option("#msrc", "a2tools")
    for setting in ("#miface", "#mport", "#mchar", "#minstall", "#mfinalboss", "#mrecord", "#mautometa"):
        assert page.locator(setting).evaluate("(n, d) => d.contains(n)", advanced.element_handle()), setting
        assert not visible(page, setting), setting
    page.locator("#madvanced > summary").click()
    assert visible(page, "#miface") and visible(page, "#mfinalboss")
    page.wait_for_function("localStorage.getItem('meter-advanced-open') === '1'")   # the toggle event saves it
    go(page, app_url, "#/meter")                                             # remembered
    assert page.locator("#madvanced").evaluate("d => d.open") is True
    page.locator("#madvanced > summary").click()
    page.wait_for_function("localStorage.getItem('meter-advanced-open') === '0'")
    go(page, app_url, "#/meter")
    assert page.locator("#madvanced").evaluate("d => d.open") is False


def test_it_opens_by_itself_when_a_game_copy_must_be_chosen(app_page, app_url):
    page = app_page
    choice = {"installations": [{"id": "a", "label": "C:/Games/AION2"}, {"id": "b", "label": "D:/AION2"}],
              "selected": "", "selection_required": True}
    page.route("**/api/meter/installations", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                body=json.dumps(choice)))
    go(page, app_url, "#/meter")
    assert page.locator("#madvanced").evaluate("d => d.open") is True
    assert "choose the copy you play" in page.locator("#minstallstatus").inner_text()


def npcap(page, app_url, state: dict) -> None:
    page.route("**/api/npcap", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(state)))
    go(page, app_url, "#/meter")


def test_npcap_shows_above_the_meter_only_when_it_needs_doing(app_page, app_url):
    page = app_page
    npcap(page, app_url, {"supported": True, "installed": False, "detection_error": None, "status": "idle"})
    assert visible(page, "#npcap") and "Npcap is required for Live Capture" in page.locator("#npcap").inner_text()
    assert page.get_by_role("button", name="Install Npcap").is_visible()


def test_an_installed_npcap_is_a_line_under_advanced_capture(app_page, app_url):
    page = app_page
    npcap(page, app_url, {"supported": True, "installed": True, "detection_error": None, "status": "idle"})
    assert not visible(page, "#npcap")
    assert "Npcap is installed" in page.locator("#npcapinfo").text_content()


def test_the_maps_page_loads_the_provider_only_when_asked(app_page, app_url):
    page = app_page
    asked = []
    page.route("https://interactivemap.app/**", lambda r: (asked.append(r.request.url), r.abort()))
    go(page, app_url, "#/maps")
    assert not asked and page.locator("[data-map-frame]").is_hidden()
    page.get_by_role("button", name="Load the interactive map").click()
    page.wait_for_timeout(500)
    assert asked and page.locator("[data-map-frame]").is_visible()
