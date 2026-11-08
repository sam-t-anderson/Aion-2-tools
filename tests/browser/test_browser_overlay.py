"""The overlay page itself, the window over the game (0.2.344): its header (the Meter and Plan tabs, Lock, New,
Copy, Hide and Start/Stop) stays inside the card at every width the overlay can be given; at 340 px, the default,
Stop ran past the card's right edge. Since 0.2.370 the meter's header is the compact layout's toolbar, an icon
each, which wraps inside its chip when the card is too narrow for one line; the party window keeps the older
header, a card too narrow for one line wrapping it onto a second, Start/Stop still at its right end. In
performance mode (0.2.355) it asks for the meter once a second, and nothing on it moves between polls."""
import time

import pytest

PARTY = [("Seraphel", "sorcerer", 23400), ("Nyxara", "ranger", 15600), ("Velmira", "cleric", 6700)]
FIGHT = {"running": True, "combine_pets": True, "snapshot": {
    "boss": "Atiel", "duration": 75.0, "recorded_duration": 75.0, "paused": False, "battle_over": False, "boss_alive": True,
    "current_target": {"name": "Atiel", "mob_code": 2340601, "hp_pct": 0.47, "ttk": 66.0, "ttk_fraction": 0.53,
                       "damage": 3_420_000, "contributors": [{"name": name, "dps": dps} for name, _, dps in PARTY]},
    "players": [{"id": str(i), "key": str(i), "name": name, "class": cls, "dps": dps, "damage": dps * 75, "hps": 0,
                 "healing": 0, "dtps": 0, "incoming": {"damage": 0}} for i, (name, cls, dps) in enumerate(PARTY)]}}


def open_overlay(page, app_url: str, width: int, meter: dict, view: str = "", **look) -> None:
    """The app's overlay at this width (its Settings → Overlay width) and these other overlay settings, over the
    meter's answer in ``meter``; ``view`` "party" opens the party window instead of the meter's."""
    def ui(route):
        if route.request.method != "GET":
            return route.continue_()
        route.fulfill(json={**route.fetch().json(), "overlay_width": width, **look})
    page.route("**/api/ui", ui)
    page.route("**/api/meter?view=latest", lambda route: route.fulfill(json=meter))
    page.goto(app_url + "overlay" + (f"?view={view}" if view else ""), wait_until="load")
    if view == "party":
        page.wait_for_function("document.querySelector('#ovcontent .ovpstat')")
    else:
        page.wait_for_function("!document.querySelector('#ovtarget').hidden")
    # The meter's answer is mocked and comes at once; the width comes with the settings, from the app
    page.wait_for_function("w => Math.abs(document.querySelector('.ovcard').getBoundingClientRect().width - w) < 1",
                           arg=width)


STATES = (({"running": True}, "Stop"), ({"running": True, "finalizing": True}, "Stopping…"), ({"running": False}, "Start"))


def _states(page, meter):
    """Each Start/Stop state in turn, once the button reads it."""
    for state, label in STATES:
        meter.pop("finalizing", None)
        meter.update(state)
        page.wait_for_function("label => document.querySelector('#ovcapture').textContent === label", arg=label)
        yield label


@pytest.mark.parametrize("width,scale", [(260, 100), (340, 100), (260, 160)])
def test_the_toolbar_stays_inside_the_card_whatever_start_stop_reads(app_page, app_url, width, scale):
    page = app_page
    meter = {**FIGHT}
    open_overlay(page, app_url, width, meter, overlay_font_scale=scale)
    card = page.locator(".ovcard").bounding_box()
    assert abs(card["width"] - width) < 1
    header = page.locator(".ovhd")
    for label in _states(page, meter):
        box = header.bounding_box()
        right = box["x"] + box["width"]
        assert box["x"] >= card["x"] - 0.5 and right <= card["x"] + card["width"] + 0.5, label
        assert header.evaluate("h => h.scrollWidth <= h.clientWidth"), label
        buttons = [b.bounding_box() for b in header.locator("button:visible").all()]
        assert len(buttons) >= 7, label                  # the view, Lock, New, Copy, Options, Start/Stop and Hide
        for edge in buttons:                             # every one of them inside the toolbar, on whichever line
            assert box["x"] - 0.5 <= edge["x"] and edge["x"] + edge["width"] <= right + 0.5, label
            assert box["y"] - 0.5 <= edge["y"] and edge["y"] + edge["height"] <= box["y"] + box["height"] + 0.5, label
        hide, capture = page.locator("#ovhide").bounding_box(), page.locator("#ovcapture").bounding_box()
        assert hide["x"] + hide["width"] >= max(b["x"] + b["width"] for b in buttons) - 0.5   # Hide at the end
        assert hide["y"] >= max(b["y"] for b in buttons) - 0.5
        if abs(capture["y"] - hide["y"]) < 1:            # Start/Stop just before it, on the same line
            assert abs(capture["x"] + capture["width"] - hide["x"]) < 1, label
        # an icon now: the words stay for its tooltip and a screen reader, the icon says which
        assert page.locator("#ovcapture").get_attribute("title").startswith("Start" if label == "Start" else "Stop")
        assert ("on" in page.locator("#ovcapture").get_attribute("class").split()) == (label != "Start")
    if width == 260 and scale == 160:                    # too narrow for one line: it wrapped, inside the card
        tops = {round(b["y"]) for b in buttons}
        assert len(tops) > 1


def test_the_party_windows_header_keeps_start_stop_at_its_right_end(app_page, app_url):
    page = app_page
    meter = {**FIGHT}
    open_overlay(page, app_url, 260, meter, view="party")
    assert not page.evaluate("document.querySelector('#ov').classList.contains('ov-nm')")   # the older look
    card = page.locator(".ovcard").bounding_box()
    header = page.locator(".ovhd")
    for label in _states(page, meter):
        box = header.bounding_box()
        right = box["x"] + box["width"]
        assert right <= card["x"] + card["width"] and header.evaluate("h => h.scrollWidth <= h.clientWidth"), label
        for button in header.locator("button:visible").all():
            edge = button.bounding_box()
            assert edge["x"] + edge["width"] <= right + 0.5, (label, button.inner_text())
        capture = page.locator("#ovcapture").bounding_box()
        assert abs(capture["x"] + capture["width"] - right) < 1, label    # at the right end, on whichever line it lands


def test_the_radars_title_shortens_rather_than_wrap_lock_and_hide(app_page, app_url):
    # The Hidden Cube radar's window (232 px) has a title, Lock and Hide in its header: at the largest text size
    # the title gives way, with an ellipsis, and the buttons stay on its line
    page = app_page
    page.route("**/api/ui", lambda route: route.continue_() if route.request.method != "GET" else
               route.fulfill(json={**route.fetch().json(), "overlay_font_scale": 160}))
    page.goto(app_url + "overlay?view=radar", wait_until="load")
    page.wait_for_function("window.A2OverlayUp === 'ready' && document.querySelector('#ovviewtitle').offsetWidth > 0")
    middles = page.evaluate("""() => ['#ovviewtitle', '#ovlock', '#ovhide'].map(s => {
        const r = document.querySelector(s).getBoundingClientRect(); return (r.top + r.bottom) / 2; })""")
    assert max(middles) - min(middles) < 2, middles
    assert page.evaluate("() => { const t = document.querySelector('#ovviewtitle'); return t.scrollWidth > t.clientWidth; }")


def test_performance_mode_polls_once_a_second_and_holds_still_between_polls(app_page, app_url):
    page = app_page
    asked = []
    page.route("**/api/ui", lambda route: route.continue_() if route.request.method != "GET" else route.fulfill(json={
        **route.fetch().json(), "performance_mode": True, "overlay_dps_interpolate": True, "overlay_show_fps": True,
        "overlay_color_cycle": True, "overlay_text_retro": True}))
    page.route("**/api/meter?view=latest", lambda route: asked.append(time.monotonic() * 1000) or route.fulfill(json=FIGHT))
    page.goto(app_url + "overlay", wait_until="load")
    page.wait_for_function("document.querySelector('#ov').classList.contains('ov-perf')")
    asked.clear()
    page.wait_for_timeout(3200)
    gaps = [b - a for a, b in zip(asked, asked[1:])]
    assert len(asked) >= 2 and min(gaps) >= 900, gaps                       # a running capture: every second, not 500 ms
    assert page.locator("#ovfps").is_hidden()                               # no frame counter, nor its per-frame loop
    assert page.evaluate("""() => [...document.querySelectorAll('#ov .ovhd, #ov .ovname, #ov .ovbar i')].every(e => {
        const s = getComputedStyle(e); return s.animationName === 'none' && parseFloat(s.transitionDuration) === 0; })""")
    assert not page.evaluate("document.querySelector('#ov').classList.contains('ov-ticking')")   # no live tick


def test_the_damage_filters_follow_the_app_save_and_name_themselves(app_page, app_url):
    """Boss damage only and Player (PvP) damage only (0.2.390) sit in the Options under the toolbar, beside Combine
    pets: the boxes follow the filters the app's reading says it applied, a click saves the setting, the clock names
    the filter in short, and rows the filter left empty say what it left out."""
    import json
    from apphelpers import until
    page = app_page
    meter = json.loads(json.dumps(FIGHT))
    meter["targets"] = ["boss"]
    saved = []

    def ui(route):
        if route.request.method != "POST":
            return route.fallback()
        body = json.loads(route.request.post_data or "{}")
        saved.append(body)
        route.fulfill(json=body)
    open_overlay(page, app_url, 340, meter, overlay_boss_only=True)
    page.route("**/api/ui", ui)                       # the saves stop here; the settings still come from the app
    page.click("#ovsettings")
    assert page.locator("#ovbossonly").is_checked() and not page.locator("#ovpvponly").is_checked()
    assert page.locator("#ovbossonly").is_visible() and page.locator("#ovpvponly").is_visible()
    page.wait_for_function("document.querySelector('#ovclock .ovclkfilter')?.textContent === 'Boss only'")
    page.click("#ovpvponly")
    assert until(page, lambda: saved) == [{"overlay_pvp_only": True}]
    meter["targets"] = ["boss", "player"]
    page.wait_for_function("document.querySelector('#ovclock .ovclkfilter')?.textContent === 'Bosses + PvP'")
    assert page.locator("#ovbossonly").is_checked() and page.locator("#ovpvponly").is_checked()
    # a fight with no damage the filters keep: the rows say what they left out
    meter["snapshot"]["players"] = [{**p, "damage": 0, "dps": 0, "healing": 500, "hps": 10} for p in meter["snapshot"]["players"]]
    page.wait_for_function("document.querySelector('#ovcontent').textContent.includes("
                           "'No damage to bosses or players in this combat (Boss and player damage only).')")
    # the app no longer applies a filter: both boxes clear, and the clock drops its note
    meter["targets"] = []
    meter["snapshot"]["players"] = FIGHT["snapshot"]["players"]
    page.wait_for_function("!document.querySelector('#ovbossonly').checked && !document.querySelector('#ovpvponly').checked")
    page.wait_for_function("!document.querySelector('#ovclock .ovclkfilter')")
