"""The overlay page itself, the window over the game (0.2.344): its header (the Meter and Plan tabs, Lock, New,
Copy, Hide and Start/Stop) stays inside the card at every width the overlay can be given. A card too narrow for
one line wraps the header onto a second, Start/Stop still at its right end; at 340 px, the default, Stop ran
past the card's right edge. In performance mode (0.2.355) it asks for the meter once a second, and nothing on it
moves between polls."""
import time

import pytest

PARTY = [("Seraphel", "sorcerer", 23400), ("Nyxara", "ranger", 15600), ("Velmira", "cleric", 6700)]
FIGHT = {"running": True, "combine_pets": True, "snapshot": {
    "boss": "Atiel", "duration": 75.0, "recorded_duration": 75.0, "paused": False, "battle_over": False, "boss_alive": True,
    "current_target": {"name": "Atiel", "mob_code": 2340601, "hp_pct": 0.47, "ttk": 66.0, "ttk_fraction": 0.53,
                       "damage": 3_420_000, "contributors": [{"name": name, "dps": dps} for name, _, dps in PARTY]},
    "players": [{"id": str(i), "key": str(i), "name": name, "class": cls, "dps": dps, "damage": dps * 75, "hps": 0,
                 "healing": 0, "dtps": 0, "incoming": {"damage": 0}} for i, (name, cls, dps) in enumerate(PARTY)]}}


def open_overlay(page, app_url: str, width: int, meter: dict) -> None:
    """The app's overlay at this width (its Settings → Overlay width), over the meter's answer in ``meter``."""
    def ui(route):
        if route.request.method != "GET":
            return route.continue_()
        route.fulfill(json={**route.fetch().json(), "overlay_width": width})
    page.route("**/api/ui", ui)
    page.route("**/api/meter?view=latest", lambda route: route.fulfill(json=meter))
    page.goto(app_url + "overlay", wait_until="load")
    page.wait_for_function("!document.querySelector('#ovtarget').hidden")
    # The meter's answer is mocked and comes at once; the width comes with the settings, from the app
    page.wait_for_function("w => Math.abs(document.querySelector('.ovcard').getBoundingClientRect().width - w) < 1",
                           arg=width)


@pytest.mark.parametrize("width", [260, 340])
def test_the_header_stays_inside_the_card_whatever_start_stop_reads(app_page, app_url, width):
    page = app_page
    meter = {**FIGHT}
    open_overlay(page, app_url, width, meter)
    card = page.locator(".ovcard").bounding_box()
    assert abs(card["width"] - width) < 1
    header = page.locator(".ovhd")
    for state, label in (({"running": True}, "Stop"), ({"running": True, "finalizing": True}, "Stopping…"),
                         ({"running": False}, "Start")):
        meter.pop("finalizing", None)
        meter.update(state)
        page.wait_for_function("label => document.querySelector('#ovcapture').textContent === label", arg=label)
        box = header.bounding_box()
        right = box["x"] + box["width"]
        assert right <= card["x"] + card["width"] and header.evaluate("h => h.scrollWidth <= h.clientWidth"), label
        for button in header.locator("button").all():
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
