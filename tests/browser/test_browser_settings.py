"""The Settings page: every setting saves what it shows and shows what was saved. Changing a control posts
its one setting to /api/ui (a number held to its range), and Settings opened afresh shows the saved value.
Uploads offer public first and save with the log server; a customization profile keeps the overlay's
background on this computer, out of its share code. Each test puts its settings back, since the tests share
one running app."""
import base64
import json
import re
import struct
import zlib

import pytest

from apphelpers import open_settings, posted, put_back

# section -> (checkbox, setting)
SWITCHES = {
    "overlay": [("ov-open-on-app", "overlay_open_on_app_start"), ("ov-close-on-stop", "overlay_close_on_stop"),
                ("ov-odyle", "overlay_show_odyle"), ("ov-shugo", "overlay_show_shugo_keys"),
                ("ov-nightmare", "overlay_show_nightmare_tickets"), ("ov-field-bosses", "overlay_show_field_bosses"),
                ("ov-plan-autoplay", "overlay_plan_autoplay"), ("ov-dps-graph", "overlay_dps_graph"),
                ("ov-clickthrough", "overlay_click_through"), ("ov-cooldowns", "overlay_show_cooldowns"),
                ("ov-break-gauge", "overlay_show_break_gauge"), ("radar-enabled", "radar_enabled"),
                ("rtss-enabled", "rtss_enabled")],
    "pettracker": [("pt-set-enabled", "pettracker_enabled")],
    "meter": [("rec-autostart", "meter_autostart"), ("rec-catchup", "meter_catch_up_uploads")],
    "system": [("char-auto-open", "character_auto_open"), ("char-auto-refresh", "character_auto_refresh")],
}
# (section, control, value entered, setting, value saved)
VALUES = [
    ("overlay", "ov-cd-min", "7", "overlay_cooldowns_min_s", 7),
    ("overlay", "ov-cd-max", "99", "overlay_cooldowns_max", 16),             # held to the 16 icons there is room for
    ("overlay", "ov-cd-pos", "top", "overlay_cooldowns_position", "top"),
    ("overlay", "ov-bg-autocontrast", "luminance", "overlay_text_autocontrast", "luminance"),
    ("overlay", "radar-sens", "8", "radar_sensitivity", 8),
    ("overlay", "rtss-rows", "30", "rtss_rows", 24),
    ("overlay", "rtss-metric", "hps", "rtss_metric", "hps"),
    ("overlay", "rtss-style", "colored", "rtss_style", "colored"),
    ("overlay", "rtss-interval", "50", "rtss_interval_ms", 100),
    ("system", "defaultpage", "timers", "app_default_page", "timers"),
]


def enter(page, control: str, value: str) -> None:
    """Set a control as a player does: choose an option, or type a number and leave the field."""
    field = page.locator(f"#{control}")
    if field.evaluate("e => e.tagName") == "SELECT":
        field.select_option(value)
    else:
        field.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); "
                       "e.dispatchEvent(new Event('change', {bubbles: true})); }", value)


@pytest.mark.parametrize("section", sorted(SWITCHES))
def test_each_switch_saves_its_setting_and_shows_it_when_settings_open_again(app_page, app_url, section):
    open_settings(app_page, app_url, section)
    was = {}
    for control, setting in SWITCHES[section]:
        box = app_page.locator(f"#{control}")
        was[control] = box.is_checked()
        assert posted(app_page, box.click) == {setting: not was[control]}, control
    open_settings(app_page, app_url, section)
    for control, setting in SWITCHES[section]:
        box = app_page.locator(f"#{control}")
        assert box.is_checked() is not was[control], f"{control} did not keep {setting}"
        assert posted(app_page, box.click) == {setting: was[control]}, control        # as it was


@pytest.mark.parametrize("section, control, value, setting, saved", VALUES, ids=[v[1] for v in VALUES])
def test_each_value_saves_its_setting_within_its_range(app_page, app_url, section, control, value, setting, saved):
    open_settings(app_page, app_url, section)
    before = app_page.locator(f"#{control}").input_value()
    assert posted(app_page, lambda: enter(app_page, control, value)) == {setting: saved}
    open_settings(app_page, app_url, section)
    assert app_page.locator(f"#{control}").input_value() == str(saved)
    posted(app_page, lambda: enter(app_page, control, before))


def test_the_pages_offered_at_launch_are_the_navigations_pages(app_page, app_url):
    from aion2calc.app.settings_backup import APP_PAGES
    open_settings(app_page, app_url, "system")
    offered = app_page.eval_on_selector_all("#defaultpage option", "os => os.map(o => o.value)")
    sections = app_page.eval_on_selector_all(".subnav a[data-page]", "as => as.map(a => a.dataset.page)")
    assert app_page.locator(".nav a[data-page='settings']").count() == 1
    assert tuple(offered) == APP_PAGES and offered == sections + ["settings"]       # the sections' pages, then Settings


def test_the_window_note_and_the_update_line_read_as_they_should(app_page, app_url):
    open_settings(app_page, app_url, "system")
    note = app_page.locator(".setrow[data-g=system]", has=app_page.locator("#appwin")).inner_text()
    assert "1920×1080" in note and "not maximized" in note
    app_page.route("**/api/update/check", lambda r: r.fulfill(json={"update": None, "update_state": {"checked_at": 1700000000}}))
    assert posted(app_page, lambda: app_page.click("#chkupd"), "/api/update/check") == {}
    app_page.wait_for_function("(document.querySelector('#updstate') || {}).textContent.startsWith('· up to date (checked ')")
    app_page.route("**/api/update/check", lambda r: r.fulfill(json={"update": None, "update_state": {"error": "timed out"}}))
    app_page.click("#chkupd")
    app_page.wait_for_function("(document.querySelector('#updstate') || {}).textContent === "
                               "'· could not check for updates (timed out); trying again shortly'")


def test_uploads_offer_public_first_and_the_choice_is_saved_with_the_server(app_page, app_url, community):
    page = app_page
    sent = []

    def logserver(route):
        if route.request.method != "POST":
            return route.continue_()
        sent.append(json.loads(route.request.post_data))                         # kept from the app: the tests share it
        route.fulfill(json={"url": community.url, "visibility": "unlisted", "has_key": True})
    page.route("**/api/logserver", logserver)
    open_settings(page, app_url, "server")
    assert page.eval_on_selector_all("#svis option", "os => os.map(o => o.value)") == ["public", "unlisted", "private"]
    assert page.locator("#svis").input_value() == "public" and page.locator("#surl").input_value() == community.url
    page.select_option("#svis", "unlisted")
    page.click("#ssave")
    page.wait_for_function("document.querySelector('#smsg').textContent.startsWith('saved · server reachable')")
    assert sent == [{"url": community.url, "key": None, "visibility": "unlisted"}]   # the key it has stays


def png(width: int = 4, height: int = 4) -> bytes:
    """A small red PNG, as an overlay background."""
    rows = b"".join(b"\x00" + b"\xc8\x28\x28" * width for _ in range(height))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def test_a_profile_keeps_the_overlay_background_here_and_its_share_code_leaves_it_out(app_page, app_url):
    page = app_page
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    def settings(route):                                                         # an overlay background is set
        if route.request.method != "GET":
            return route.continue_()
        answer = route.fetch()
        route.fulfill(response=answer, json={**answer.json(), "overlay_bg_set": True})
    page.route("**/api/ui", settings)
    page.route(re.compile(r"/overlay-background\?\d+$"), lambda route: route.fulfill(body=png(), content_type="image/png"))
    backgrounds = []

    def background(route):
        backgrounds.append(json.loads(route.request.post_data))
        route.fulfill(json={"ok": True})
    page.route("**/api/overlay/background", background)
    page.on("dialog", lambda dialog: dialog.accept("Test look"))
    open_settings(page, app_url, "backup")
    assert page.locator("[data-cust-tile]").count() == 0
    page.click("#cust-save")
    tile = page.locator('[data-cust-tile="Test look"]')
    tile.wait_for()
    profile, = page.evaluate("JSON.parse(localStorage.getItem('a2-custom-profiles'))")
    assert profile["name"] == "Test look" and profile["bg"].startswith("data:image/jpeg;base64,")   # kept in this browser
    assert page.get_by_text("Profile saved with its background").count() == 1
    page.select_option("#cust-profile", "Test look")
    page.click("#cust-copy")
    page.wait_for_function("document.querySelector('#cust-msg').textContent === 'Share code copied — send it to a friend.'")
    code = page.evaluate("navigator.clipboard.readText()")
    assert code.startswith("A2PROF1:")
    shared = json.loads(base64.b64decode(code[len("A2PROF1:"):]))
    assert "bg" not in shared and {k: shared[k] for k in ("name", "theme", "accent", "ui")} == \
           {k: profile[k] for k in ("name", "theme", "accent", "ui")}                  # everything but the image
    look = posted(page, tile.click)                                                 # the square applies it…
    assert look == profile["ui"]
    for _ in range(30):                                                             # its answer on its way
        if backgrounds:
            break
        page.wait_for_timeout(100)
    assert backgrounds == [{"data": profile["bg"]}]                               # …with its background


def test_a_shared_profile_code_brings_its_look_but_never_an_image(app_page, app_url):
    page = app_page
    look = {"overlay_glow": True, "overlay_font_scale": 110}
    shared = {"name": "Friend's look", "theme": "dark", "accent": "azure", "ui": {**look, "overlay_width": 500},
              "bg": "data:image/png;base64,AAAA"}                                          # a code made by hand
    code = "A2PROF1:" + base64.b64encode(json.dumps(shared).encode()).decode()
    answers = {"Paste a profile share code:": code, "Save the shared profile as:": "From a friend"}
    page.on("dialog", lambda dialog: dialog.accept(answers[dialog.message]))
    open_settings(page, app_url, "backup")
    page.click("#cust-import")
    page.locator("#cust-profile option", has_text="From a friend").wait_for(state="attached")
    profile, = page.evaluate("JSON.parse(localStorage.getItem('a2-custom-profiles'))")
    assert profile == {"name": "From a friend", "theme": "dark", "accent": "azure", "ui": look}   # only look settings, no image


def test_a_saved_look_keeps_every_look_setting(app_page, app_url):
    # it lost the auto-contrast and colour-cycle settings when the app saved it
    page = app_page
    open_settings(page, app_url, "overlay")
    saved = page.evaluate("() => api('/api/ui')")
    page.on("dialog", lambda dialog: dialog.accept("Test look"))
    try:
        sent = posted(page, lambda: page.click("#ov-preset-save"))["overlay_presets"][-1]
        assert sent["name"] == "Test look" and {"overlay_text_autocontrast", "overlay_color_cycle"} <= set(sent["settings"])
        kept, = [p for p in page.evaluate("() => api('/api/ui')")["overlay_presets"] if p["name"] == "Test look"]
        assert kept == sent
    finally:
        put_back(page, {"overlay_presets": saved.get("overlay_presets", [])})


ACCENTS = ["gold", "crimson", "emerald", "azure", "amethyst", "rose"]


def test_each_accent_recolours_the_app_and_is_kept(app_page, app_url):
    page = app_page
    open_settings(page, app_url, "appearance")
    assert page.eval_on_selector_all("[data-accent-btn]", "bs => bs.map(b => b.dataset.accentBtn)") == ACCENTS
    gold = lambda: page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--gold').trim()")
    colours = {"gold": gold()}
    for accent in ACCENTS[1:]:
        page.click(f'[data-accent-btn="{accent}"]')
        assert page.evaluate("document.documentElement.dataset.accent") == accent
        colours[accent] = gold()
    assert len(set(colours.values())) == len(ACCENTS)                                # each its own colour
    page.goto(app_url + "#/meter")                                                   # applied as the next launch opens
    assert page.evaluate("document.documentElement.dataset.accent") == ACCENTS[-1]
