"""The overlay windows opened at launch as the meter's header and nothing under it (0.2.329, 0.2.330): the page
without its script. The overlay log's watchdog numbers showed it: at one launch the meter window and the radar
window both captured an identical 0.7008 share of host-coloured pixels, the bare page at its first size in both,
and the radar's window carried the meter's header, which only a page whose script never applied its view can
show. The cause is the app server's listen backlog: socketserver's default of five, every request a connection
of its own (HTTP/1.0), two overlay pages loading six resources at once at the moment the app is busiest, and
Windows refusing a connection that finds the backlog full, after which a refused script is never fetched again.
Three guards (0.2.331): the backlog holds the burst, the page reloads itself when it comes up without its script
or stylesheet and says so in the overlay log, and the overlay's watchdog reloads a page whose script never
started, a bounded number of times (tests/test_overlay_health.py)."""
import os
import pathlib
import threading

import pytest

from aion2calc.app import server

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
HTML = (STATIC / "overlay.html").read_text(encoding="utf-8")
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")


def test_the_server_holds_the_launch_burst_of_connections():
    httpd = server.make_server("127.0.0.1", 0)
    try:
        assert httpd.request_queue_size >= 64          # listen() was given this backlog when the server bound
        assert httpd.daemon_threads
    finally:
        httpd.server_close()


def test_the_page_guards_its_own_startup():
    guard = HTML.index("a2-overlay-reloads")
    assert guard < HTML.index('<script src="/static/game-assets.js">')     # before the scripts it watches
    assert "failed to load" in HTML and "window.location.reload()" in HTML and "n >= 3" in HTML
    view = JS.index("const view = new URLSearchParams")
    assert JS.index('window.A2OverlayUp="starting"') < view                 # the script announces itself first
    assert 'window.A2OverlayUp="ready"' in JS[JS.index("applyOpacity(); renderMeter();"):]
    assert JS.index('window.addEventListener("error"') < view               # and reports errors from the start


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(server, "_OVERLAY_NOTES", [])
    srv = server.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    finally:
        srv.shutdown()
        srv.server_close()


def test_a_refused_script_is_reported_and_the_page_reloads_itself(app):
    playwright = pytest.importorskip("playwright.sync_api")
    base, home = app
    with playwright.sync_playwright() as p:
        chromium = "/opt/pw-browsers/chromium/chrome"
        try:
            browser = p.chromium.launch(executable_path=chromium if os.path.exists(chromium) else None)
        except Exception as err:                                                  # noqa: BLE001 - no browser here
            pytest.skip(f"no Chromium for Playwright: {err}")
        page = browser.new_page(viewport={"width": 340, "height": 120})
        refused = []

        def route(r):
            if refused:
                r.continue_()
            else:
                refused.append(r.request.url)
                r.abort("connectionrefused")

        page.route("**/static/overlay.js", route)
        page.goto(base + "/overlay?view=radar")
        page.wait_for_function("window.A2OverlayUp === 'ready'", timeout=20000)
        navigation = page.evaluate("performance.getEntriesByType('navigation')[0].type")
        radar = page.evaluate("document.getElementById('ov').classList.contains('ov-radar')")
        browser.close()
    assert refused and navigation == "reload" and radar
    log = (home / "logs" / "overlay.log").read_text(encoding="utf-8")
    assert "overlay page: load: failed to load" in log and "/static/overlay.js" in log
    assert "overlay page: startup: the page loaded without its script; reloading (1)" in log
