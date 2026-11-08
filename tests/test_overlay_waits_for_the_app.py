"""The overlay never shows the browser's error page (0.2.390).

Reported: opening the overlay sometimes showed Microsoft Edge's "Hmmm... can't reach this page. 127.0.0.1 refused
to connect" in a near-full-screen window with a title bar. Paths there, each closed here:

* The overlay process opened its address in the default browser whenever pywebview could not be imported or its
  window failed, and ``webview.start`` failing as the window closed (the app going away) counted too: a
  full-size browser window at an address where nothing listened any more. It never opens a browser now; a window
  that cannot open ends with ``UNAVAILABLE_EXIT_CODE``, which the app does not relaunch, and Open overlay then
  lets the page's own small window stand in.
* The window went to the app's address the moment it was made, before the app answered, and the watchdog's
  reload and navigate steps and the page's own startup guard reloaded it whether or not the app answered. The
  window now opens on its own waiting card at its own size, frameless, loads the page once the app answers, turns
  WebView2's built-in error page off, and puts the card back (and waits again) when a load fails anyway.
* The Live Meter page opened its popup fallback when its request to the app failed outright: a popup to an
  address that does not answer.
"""
import http.server
import pathlib
import socket
import sys
import threading
import time
import types

import pytest

from aion2calc import overlay
from aion2calc.app import overlay_launch
from aion2calc.overlay_health import (RESTART_EXIT_CODE, UNAVAILABLE_EXIT_CODE, WAITING_HTML, OverlayLog,
                                      RelaunchLimiter, app_answers)

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
URL = "http://127.0.0.1:8765/overlay"
BASE = "http://127.0.0.1:8765"


@pytest.fixture
def answering():
    """A local server that answers every GET (a 500 for one path: any answer counts)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(500 if self.path.startswith("/broken") else 200)
            self.end_headers()
            self.wfile.write(b'{"reload_seq": 0}')

        def log_message(self, *args):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def _refused_base():
    with socket.socket() as s:                      # a port nothing listens on once this closes
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def test_the_app_answers_when_anything_answers_and_not_when_refused(answering):
    assert app_answers(answering) and app_answers(answering + "/")
    assert app_answers(None)                         # an address with no app to ask: nothing to wait for
    assert not app_answers(_refused_base(), timeout=0.5)

    def erroring(url, timeout):
        import urllib.error
        raise urllib.error.HTTPError(url, 503, "busy", {}, None)
    assert app_answers(BASE, opener=erroring)        # an error status is still an answer


class _Window:
    """pywebview's window, as far as the waiting logic uses it."""

    def __init__(self):
        self.calls = []
        self.native = types.SimpleNamespace()

    def load_url(self, url):
        self.calls.append(("url", url))

    def load_html(self, html):
        self.calls.append(("html", html))


def _api(tmp_path, base=BASE):
    api = overlay._OverlayAPI()
    api._window = window = _Window()
    api.url, api.app_base = URL, base
    api.log = OverlayLog(tmp_path / "overlay.log")
    api._closed = threading.Event()
    return api, window


def _wait_for(condition, seconds=3.0):
    deadline = time.time() + seconds
    while not condition() and time.time() < deadline:
        time.sleep(0.01)
    return condition()


def test_the_window_loads_the_page_at_once_when_the_app_answers(tmp_path):
    api, window = _api(tmp_path)
    assert api.open_app(answers=lambda base: True) is True
    assert window.calls == [("url", URL)] and not api._waiting


def test_the_window_keeps_its_waiting_card_until_the_app_answers(tmp_path, monkeypatch):
    api, window = _api(tmp_path)
    up = {"now": False}
    monkeypatch.setattr(overlay, "app_answers", lambda base, timeout=1.0: up["now"])
    clock = {"t": 0.0}
    loaded = api.open_app(first_wait=1.0, answers=lambda base: up["now"], clock=lambda: clock["t"],
                          sleep=lambda s: clock.__setitem__("t", clock["t"] + s))
    assert loaded is False and api._waiting and window.calls == []     # the card the window opened on stays
    assert "waiting for the app: the app did not answer in 1 s" in api.log.tail()
    up["now"] = True                                                    # the app comes up: the waiter loads the page
    assert _wait_for(lambda: window.calls == [("url", URL)], 4.0)
    assert not api._waiting and "loading the page: the app answers" in api.log.tail()
    api._closed.set()


def test_a_load_that_fails_puts_the_waiting_card_back_and_retries(tmp_path, monkeypatch):
    api, window = _api(tmp_path)
    up = {"now": False}
    monkeypatch.setattr(overlay, "app_answers", lambda base, timeout=1.0: up["now"])
    core = types.SimpleNamespace(Source=URL)
    failed = types.SimpleNamespace(IsSuccess=False, WebErrorStatus="ConnectionAborted")
    api._on_navigation_completed(core, failed)
    assert api._waiting and window.calls == [("html", WAITING_HTML)]
    assert "waiting for the app: the page did not load (ConnectionAborted)" in api.log.tail()
    api._on_navigation_completed(core, failed)                         # one waiter at a time
    assert window.calls == [("html", WAITING_HTML)]
    up["now"] = True
    assert _wait_for(lambda: window.calls[-1] == ("url", URL), 4.0) and not api._waiting
    # a load that worked, and the waiting card's own load, start nothing
    api._on_navigation_completed(core, types.SimpleNamespace(IsSuccess=True))
    api._on_navigation_completed(types.SimpleNamespace(Source="about:blank"), failed)
    assert window.calls[-1] == ("url", URL) and not api._waiting
    api._closed.set()


def test_a_load_another_load_replaced_is_no_failure_and_repeated_failures_back_off(tmp_path):
    api, window = _api(tmp_path)
    core = types.SimpleNamespace(Source=URL)
    api._on_navigation_completed(core, types.SimpleNamespace(IsSuccess=False, WebErrorStatus="OperationCanceled"))
    assert not api._waiting and window.calls == []           # the waiting card's own load, as the page loads over it
    api._load_failures = 3
    api._on_navigation_completed(core, types.SimpleNamespace(IsSuccess=True))
    assert api._load_failures == 0                           # the page loaded: the next failure starts afresh
    # the third failure in a row with the app answering waits 4 s before it loads the page again
    api._load_failures, api._waiting = 3, True
    waits = []
    api._closed = types.SimpleNamespace(is_set=lambda: False, wait=lambda s: waits.append(s))
    api._await_app(interval=1.0, answers=lambda base: True)
    assert waits == [4.0] and window.calls == [("url", URL)] and not api._waiting


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def test_the_browsers_own_error_page_is_turned_off_and_loads_are_followed(tmp_path):
    api, window = _api(tmp_path)
    api._on_ui = lambda callback: callback()
    window.native.webview = types.SimpleNamespace(CoreWebView2=None)
    assert api.prepare_navigation() is False                          # the core is not up yet: asked again later
    core = types.SimpleNamespace(Settings=types.SimpleNamespace(IsBuiltInErrorPageEnabled=True),
                                 NavigationCompleted=_Event())
    window.native.webview.CoreWebView2 = core
    assert api.prepare_navigation() is True and api.prepare_navigation() is True
    assert core.Settings.IsBuiltInErrorPageEnabled is False
    assert core.NavigationCompleted.handlers == [api._on_navigation_completed]


def test_the_watchdog_leaves_a_waiting_window_alone_and_heals_only_into_an_answering_app(tmp_path, monkeypatch):
    from test_overlay_health import _frame, _watchdog
    frame = {"bytes": _frame(40_800)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    api.app_base = BASE
    window.load_html = lambda html: window.loaded.append("waiting card")
    api._waiting = True
    api._reload_requested = 1
    for _ in range(8):
        clock["now"] += 5
        assert watchdog.tick() is None                                 # nothing to heal while the card is up
    assert native.calls == [] and window.loaded == []
    # Not waiting, the app asks for a reload, but the app does not answer the overlay: the card, not the page.
    api._waiting = False
    api._closed = threading.Event()
    monkeypatch.setattr(overlay, "app_answers", lambda base, timeout=1.0: False)
    assert watchdog.tick() == "reload"
    assert native.calls == [] and window.loaded == ["waiting card"] and api._waiting
    assert "waiting for the app: reload put off: the app does not answer" in api.log.tail()
    api._closed.set()


@pytest.fixture
def no_browser(monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: opened.append(a) or True)
    monkeypatch.setattr(overlay, "_log_path", lambda: overlay_log_path["path"])
    return opened


overlay_log_path = {}


def _fake_webview(monkeypatch, start):
    made = []
    module = types.ModuleType("webview")
    module.create_window = lambda title, url=None, **kw: made.append((title, url, kw)) or types.SimpleNamespace()
    module.start = start
    monkeypatch.setitem(sys.modules, "webview", module)
    return made


def test_the_overlay_process_never_opens_a_browser(monkeypatch, tmp_path, no_browser):
    overlay_log_path["path"] = tmp_path / "overlay.log"
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.delenv("AION2CALC_PARENT_PID", raising=False)
    # No pywebview at all
    monkeypatch.setitem(sys.modules, "webview", None)
    assert overlay.main(["--url", URL]) == UNAVAILABLE_EXIT_CODE
    assert "cannot open: pywebview is not available" in OverlayLog(tmp_path / "overlay.log").tail()
    # The window opens on its waiting card, frameless at the overlay's size, not at the app's address
    made = _fake_webview(monkeypatch, lambda func, args, gui=None: None)
    assert overlay.main(["--url", URL]) == 0
    title, url, kw = made[-1]
    assert url is None and kw["html"] == WAITING_HTML and kw["frameless"] is True and kw["hidden"] is True
    assert (kw["width"], kw["height"]) == (340, 120)
    # WebView2 refuses to start before the window ever showed: unavailable, no browser
    def refused(func, args, gui=None):
        raise RuntimeError("WebView2 runtime missing")
    _fake_webview(monkeypatch, refused)
    assert overlay.main(["--url", URL]) == UNAVAILABLE_EXIT_CODE
    # It ran, then failed as it closed (the app going away): a normal end, no browser
    def failed_closing(func, args, gui=None):
        args[1]._ever_shown = True
        raise RuntimeError("the form was disposed")
    _fake_webview(monkeypatch, failed_closing)
    assert overlay.main(["--url", URL]) == 0
    # ... and a restart the watchdog asked for still ends with the restart code
    def failed_restarting(func, args, gui=None):
        args[1]._ever_shown = args[1]._restart = True
        raise RuntimeError("the form was disposed")
    _fake_webview(monkeypatch, failed_restarting)
    assert overlay.main(["--url", URL]) == RESTART_EXIT_CODE
    assert no_browser == []
    assert "the window failed: RuntimeError: WebView2 runtime missing" in OverlayLog(tmp_path / "overlay.log").tail()
    source = (ROOT / "aion2calc" / "overlay.py").read_text(encoding="utf-8")
    assert "webbrowser" not in source


class _Popen:
    def __init__(self):
        self._done, self.returncode = threading.Event(), None

    def wait(self):
        self._done.wait()
        return self.returncode

    def poll(self):
        return self.returncode if self._done.is_set() else None

    def terminate(self):
        self.end(1)

    def end(self, code):
        self.returncode = code
        self._done.set()


def test_a_window_that_cannot_open_is_not_started_again_and_the_page_stands_in(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    spawned = []
    monkeypatch.setattr(overlay_launch, "_spawn", lambda url: spawned.append(_Popen()) or spawned[-1])
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    monkeypatch.setattr(overlay_launch, "_party_enabled", lambda: False)
    monkeypatch.setattr(overlay_launch, "_radar_enabled", lambda: False)
    for name in ("_PROCESS", "_PARTY_PROCESS", "_RADAR_PROCESS", "_PETS_PROCESS"):
        monkeypatch.setattr(overlay_launch, name, None)
    monkeypatch.setattr(overlay_launch, "_RELAUNCHES", RelaunchLimiter())
    monkeypatch.setattr(overlay_launch, "_UNAVAILABLE", {})
    assert overlay_launch.launch(URL)["native"] is True and len(spawned) == 1
    spawned[0].end(UNAVAILABLE_EXIT_CODE)
    assert _wait_for(lambda: overlay_launch._PROCESS is None)
    time.sleep(0.1)
    assert len(spawned) == 1                                            # not started again
    result = overlay_launch.launch(URL)
    assert result["native"] is False and "could not open its window" in result["reason"] and len(spawned) == 1
    assert overlay_launch.sync_pets(URL + "?view=pets", True) is False and len(spawned) == 1
    log = (tmp_path / "logs" / "overlay.log").read_text(encoding="utf-8")
    assert "could not open its window; not started again" in log
    # ten minutes on, the native window is tried again
    monkeypatch.setitem(overlay_launch._UNAVAILABLE, "at", time.time() - overlay_launch.UNAVAILABLE_FOR - 1)
    assert overlay_launch.launch(URL)["native"] is True and len(spawned) == 2
    overlay_launch.close()


def test_the_pages_reload_only_into_an_answering_app():
    for name in ("overlay.html", "pet-overlay.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        guard = html[html.index("function check()"):]
        assert "setTimeout(reload, 300)" in guard and "window.location.reload" not in guard
        reload = html[html.index("function reload()"):html.index("function check()")]
        assert "answers(function (up)" in reload and "window.location.reload()" in reload and "waiting()" in reload
        assert 'fetch("/api/overlay/commands"' in html and "Waiting for Aion 2 Calc" in html


def test_the_live_meter_page_opens_no_popup_when_the_app_does_not_answer():
    js = (STATIC / "pages" / "meter.js").read_text(encoding="utf-8")
    body = js[js.index("async function openMeterOverlay()"):js.index('st.overlayPopup = window.open("/overlay"')]
    assert "e instanceof TypeError" in body and "did not answer" in body
