"""The overlay page starts cleanly inside the native host.

pywebview's WebView2 backend injects ``window.pywebview`` once the navigation has completed, after the page's
own scripts have run, and then fires ``pywebviewready``: ``nativeInit()`` runs on that event, and during the
startup only in a host that has the bridge in place before the script. Everything that call reads must be
declared before the startup call (the first test pins the order; in 0.2.329 the radar's state was declared
further down), and the page must come up fitting its window under either sequence: the second test runs the
page in Chromium with a stand-in bridge that arrives after the load, as WebView2's does, and one in place
before the script, and checks that no page error occurs, the window keeps fitting as the content renders and
the page reports its startup as through."""
import os
import pathlib
import re
import threading

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")


def test_everything_native_init_reads_is_declared_before_the_startup_call():
    startup = JS.index("if (window.pywebview?.api?.fit) nativeInit();")
    for name in ("radarSetting", "radarOn", "radarTimer", "radarBusy", "clickThrough", "op", "nativeReady"):
        declaration = re.search(r"\b(?:let|const|var)\b[^;\n]*\b" + name + r"\s*=", JS)
        assert declaration and declaration.start() < startup, f"{name} must be declared before nativeInit() can run"
    # The observer that keeps the native window fitted to the card comes after the startup call: an
    # exception there would leave the window at its first size.
    assert JS.index("new ResizeObserver(fit).observe") > startup


BRIDGE = """
window.__fits = window.__fits || []; window.__errors = [];
window.pywebview = { platform: "edgechromium", api: {
  fit: async (w, h) => { window.__fits.push([w, h]); },
  set_opacity: async () => {}, set_click_through: async () => {}, set_interactive_rects: async () => {}, set_locked: async () => {},
}};
"""


@pytest.mark.parametrize("sequence", ["after-load", "before-script"])
@pytest.mark.parametrize("view", ["meter", "radar", "party"])
def test_the_page_starts_without_errors_in_the_native_host(tmp_path, monkeypatch, view, sequence):
    playwright = pytest.importorskip("playwright.sync_api")
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app.server import make_server
    srv = make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as p:
            chromium = "/opt/pw-browsers/chromium/chrome"
            try:
                browser = p.chromium.launch(executable_path=chromium if os.path.exists(chromium) else None)
            except Exception as err:                                              # noqa: BLE001 - no browser here
                pytest.skip(f"no Chromium for Playwright: {err}")
            page = browser.new_page(viewport={"width": 340, "height": 120})
            if sequence == "before-script":
                page.add_init_script(BRIDGE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/overlay" + ("" if view == "meter" else f"?view={view}"))
            if sequence == "after-load":                       # as pywebview does on NavigationCompleted
                page.wait_for_load_state("load")
                page.evaluate("() => {" + BRIDGE + "}")
                page.evaluate("() => window.dispatchEvent(new CustomEvent('pywebviewready'))")
            page.wait_for_timeout(2500)
            fits = page.evaluate("window.__fits")
            height = page.evaluate("document.getElementById('ov').getBoundingClientRect().height")
            up = page.evaluate("window.A2OverlayUp")
            browser.close()
    finally:
        srv.shutdown()
    assert errors == []
    assert up == "ready"
    assert fits and abs(fits[-1][1] - height) <= 2          # the last fit matches the card's height
    if view == "meter":
        assert height > 120                                 # header, metrics, options, status, ping and the footer
