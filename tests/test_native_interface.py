"""The native interface (0.2.413; the default since 0.2.426): the app's windows drawn by Qt (PySide6) in Python.

The windows read the app through its local API, as the web pages do, so they are tested here on the same meter
answers the browser tests use (``tests/browser/test_browser_overlay_look.py``), off screen. The setting that
turns them on, and the launcher and overlay hooks that open them, are tested without Qt.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc import gui, launcher  # noqa: E402
from aion2calc.app import overlay_launch, server  # noqa: E402
from aion2calc.app.settings_backup import _clean  # noqa: E402
from aion2calc.gui import overlay as native_overlay  # noqa: E402
from aion2calc.gui.api import AppApi, Poller  # noqa: E402
from aion2calc.gui.overlay import MeterOverlay, counter_lines  # noqa: E402
from aion2calc.gui.window import SECTIONS, MainWindow, MeterPage, WebPage  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
from test_browser_overlay_look import counted  # noqa: E402

WEEKLY = {"instance": 600073, "counter": 60000009, "regular": 3, "bonus": 1, "timestamp_ms": 1,
          "zone": "Vakron Sky Island", "difficulty": "hard"}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted when it ends, while Qt's application still exists: a window
    left for Python to collect at exit was destroyed after the application, and the process crashed on its way
    out (a segmentation fault after every test had passed)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def _meter():
    meter = counted()
    meter["snapshot"]["weekly_runs"] = dict(WEEKLY)
    return meter


# ------------------------------------------------------------------ the overlay
def test_the_overlay_draws_the_meters_reading(qapp):
    window = MeterOverlay()
    window.apply_ui({"overlay_width": 340, "overlay_show_ttk": True, "overlay_show_enemy_hp": True})
    window.apply_meter(_meter())
    rows = [row for row in window.rows if not row.isHidden()]
    assert [row.name for row in rows] == ["Seraphel", "Nyxara", "Velmira"]          # by DPS, highest first
    # The compact layout's numbers: the rate in whole digits, the share of the total to a tenth.
    assert [(row.rate, row.share) for row in rows] == [("23,400/s", "51.2%"), ("15,600/s", "34.1%"), ("6,700/s", "14.7%")]
    assert rows[0].fill == 1.0 and 0 < rows[2].fill < rows[1].fill < 1
    assert [row.mine for row in rows] == [False, True, False]                         # you, by the local name
    # The fight's clock under the rows, the status (the web overlay's words) its tooltip.
    assert window.clock.text() == "01:15 Party DPS 45.70K" and not window.clock.isHidden()
    assert window.status_text == "Latest combat · Atiel · 75s · 45.70K DPS" == window.clock.toolTip()
    assert window.target_text == "Atiel  ·  47.0%  ·  TTK 1m06s" and window.hp.fraction == pytest.approx(0.47)
    assert window.width() == 340
    window.grab()                                                                     # paints without error


def test_the_counter_lines_full_or_short(qapp):
    snap = _meter()["snapshot"]
    assert [text for _key, text, _short in counter_lines(snap)] == [
        "Odyle Energy 1,500 (1,200 + 300 bonus)", "Shugo Keys 16 (12 + 4 bonus)", "Nightmare Tickets 11 (9 + 2 bonus)",
        "Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)"]
    window = MeterOverlay()
    window.apply_ui({"overlay_width": 340})
    window.apply_meter(_meter())
    assert window.lines.text() == "1,200(+300) 12(+4) 9(+2) 3(+1)"            # no room for the words: the counts
    assert [part.tip.split("\n")[0] for part in window.lines.parts][3] == (
        "Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)")             # in full in its tooltip
    one = _meter()
    for key in ("shugo_keys", "nightmare_tickets", "weekly_runs"):
        one["snapshot"].pop(key)
    window.apply_ui({"overlay_width": 800})
    window.apply_meter(one)
    assert window.lines.text() == "Odyle Energy 1,500 (1,200 + 300 bonus)"            # room for the words


def test_the_metric_switches_the_rows_and_the_settings_shape_the_window(qapp):
    window = MeterOverlay()
    window.apply_ui({"overlay_width": 300, "overlay_max_players": 2, "overlay_row_height": 30,
                     "overlay_show_target": False})
    meter = _meter()
    for player, hps in zip(meter["snapshot"]["players"], (0, 0, 900)):
        player["hps"], player["healing"] = hps, hps * 75
    window.apply_meter(meter)
    assert [row.name for row in window.rows if not row.isHidden()] == ["Seraphel", "Nyxara"]     # two rows
    assert all(row.height() == 36 for row in window.rows) and window.width() == 300   # the row height and 6
    assert window.target_card.isHidden()
    assert window.metric_chip.text() == "DPS"
    window.metric_chip.click()                    # the chip moves on to the next metric
    assert window.rate_metric == "hps" and window.metric_chip.text() == "HPS"
    assert [row.name for row in window.rows if not row.isHidden()][0] == "Velmira"
    assert window.status_text.endswith(" HPS") and window.clock.text().endswith("Party HPS 900")
    window.metric_chip.click()
    assert window.rate_metric == "dtps" and window.metric_chip.text() == "D.Taken"
    assert window.metric_chip.toolTip() == "D.Taken — click for the next: DPS, HPS, damage taken"
    window.metric_chip.click()
    assert window.rate_metric == "dps"            # and round again


def test_click_through_and_the_remembered_position(qapp):
    window = MeterOverlay()
    window.apply_ui({"overlay_pos_x": 120, "overlay_pos_y": 80, "overlay_click_through": True})
    assert window.pos().x() == 120 and window.pos().y() == 80
    assert window.click_through and window.windowFlags() & Qt.WindowTransparentForInput
    window.apply_ui({"overlay_click_through": False})
    assert not window.windowFlags() & Qt.WindowTransparentForInput


def test_an_idle_meter_says_so(qapp):
    window = MeterOverlay()
    window.apply_meter({"running": False, "snapshot": {}})
    assert window.empty.text() == "No fight yet. Start the meter in the app." and window.clock.isHidden()
    assert all(row.isHidden() for row in window.rows)
    assert window.status_text == "Latest combat · idle · 0s · 0 DPS"
    window.apply_meter({"running": True, "snapshot": {"players": []}})
    assert window.empty.text() == "Waiting for combat data…"
    assert window.status_text == "Latest combat · recording · 0s · 0 DPS"


# ------------------------------------------------------------------ the app window
def test_the_window_lists_the_web_navigation_and_draws_the_live_meter(qapp, monkeypatch):
    window = MainWindow(None, "http://127.0.0.1:8765/")
    titles = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert titles[:4] == ["COMBAT", "Live Meter", "Combat Logs", "Raid Planner"]
    assert titles[-2:] == ["Settings", "Account"] and len(titles) == 3 + sum(len(pages) for _s, pages in SECTIONS)
    assert isinstance(window.page("meter"), MeterPage) and isinstance(window.page("raid"), WebPage)
    assert window.pages.currentWidget() is window.page("meter")
    window.show_page("raid")
    assert window.pages.currentWidget() is window.page("raid")
    opened = []
    monkeypatch.setattr(launcher, "open_window", lambda url, prefer_app=True, native=None: opened.append((url, native)))
    window.page("raid").button.click()
    assert opened == [("http://127.0.0.1:8765/#/raid", False)]                       # the web interface's page


def test_the_live_meter_page_shows_the_fight_and_its_buttons(qapp, tmp_path):
    """The page as the web page draws it since 0.2.471 (tests/test_native_meter.py has the rest)."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QLabel
    from aion2calc.gui.meter_page import PlayerRow
    from aion2calc.gui.pictures import Pictures
    from test_native_overlay_toolbar import settle
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    page = MeterPage(None, store=store)
    meter = _meter()
    meter["snapshot"]["dps"] = 45700
    page.apply({**meter, "running": True})
    players = page.slots["players"].itemAt(0).widget()
    rows = players.findChildren(PlayerRow)
    assert [row.accessibleName().split(" · ")[0] for row in rows] == ["Seraphel", "Nyxara", "Velmira"]
    assert rows[0].bar.words == "23.40K/s · 51%" and rows[0].chosen
    assert page.start_button.text() == "Stop" and page.start_button.isEnabled() and not page.clear_button.isEnabled()
    assert players.subtitle.text() == "Atiel · 75s · 45.70K raid DPS"
    assert "Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)" in [l.text() for l in players.findChildren(QLabel)]
    page.apply({"running": False, "snapshot": {}})
    assert page.slots["players"].parentWidget().isHidden() and page.start_button.text() == "Start"
    empty = page.slots["empty"].itemAt(0).widget()
    assert empty.findChildren(QLabel)[-1].text() == "No data yet — choose a source and press Start."

    class Recorder:
        def __init__(self):
            self.calls = []

        def url(self, path):
            return "http://127.0.0.1:9/" + path.lstrip("/")

        def get(self, path, timeout=None):
            self.calls.append((path, None))
            return {"supported": False}

        def get_bytes(self, path, timeout=None):
            raise OSError("no pictures here")

        def post(self, path, payload, timeout=None, origin=False):
            self.calls.append((path, payload))
            return {"running": False, "snapshot": {"players": []}}

    app = Recorder()
    page = MeterPage(app, store=store, pictures=Pictures(None))
    page.start_button.click()                         # Self + Party, as the web page starts (0.2.416), packet capture checked
    settle(lambda: len(app.calls) == 2)
    assert app.calls[0] == ("/api/capture/setup", None)
    path, body = app.calls[1]
    assert path == "/api/meter" and (body["action"], body["source"], body["auto_port"], body["scope"]) == (
        "start", "a2tools", True, "party")
    page.stop()


# ------------------------------------------------------------------ the API and the poll
class _App(BaseHTTPRequestHandler):
    answers = {"/api/meter?view=latest": {"running": True, "snapshot": {"players": []}}}
    posted = []

    def do_GET(self):
        body = json.dumps(self.answers.get(self.path, {})).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.posted.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
        self.do_GET()

    def log_message(self, *args):
        pass


def test_the_poll_hands_each_answer_to_the_window(qapp):
    app = ThreadingHTTPServer(("127.0.0.1", 0), _App)
    threading.Thread(target=app.serve_forever, daemon=True).start()
    try:
        api = AppApi(f"http://127.0.0.1:{app.server_address[1]}/overlay#ignored".split("/overlay")[0])
        got = []
        poller = Poller(api, "/api/meter?view=latest", 50)
        poller.answered.connect(got.append)
        poller.start()
        clock = QElapsedTimer()
        clock.start()
        while len(got) < 2 and clock.elapsed() < 5000:
            QCoreApplication.processEvents()
        poller.stop()
        assert got[0] == {"running": True, "snapshot": {"players": []}} and len(got) >= 2
        assert api.post("/api/ui", {"overlay_pos_x": 5}) == {} and _App.posted[-1] == ("/api/ui", {"overlay_pos_x": 5})
    finally:
        app.shutdown()


# ------------------------------------------------------------------ the setting and the hooks
def test_the_setting_is_on_by_default_and_a_choice_is_kept(home, monkeypatch):
    from aion2calc.paths import write_user_json
    assert server.ui_settings()["interface_native"] is True                     # the default since 0.2.426
    # Every save writes the whole of the settings: a file from before holds the old default as if it were chosen.
    write_user_json({"interface_native": False, "app_window": False}, "ui.json")
    ui = server.ui_settings()
    assert ui["interface_native"] is True and ui["app_window"] is False         # the new default, for everyone once
    write_user_json({"interface_native": False, "interface_native_chosen": True}, "ui.json")
    assert server.ui_settings()["interface_native"] is False                    # chosen: kept
    assert _clean({"interface_native": True, "interface_native_chosen": True}) == {
        "interface_native": True, "interface_native_chosen": True}               # and in the backup
    with pytest.raises(ValueError):
        _clean({"interface_native": "yes"})
    monkeypatch.setattr(gui, "available", lambda: True)
    assert gui.enabled({"interface_native": True}) and not gui.enabled({"interface_native": False})
    monkeypatch.setattr(gui, "available", lambda: False)
    assert not gui.enabled({"interface_native": True})                                # without PySide6: the web


def test_turning_the_native_interface_off_in_settings_is_a_choice_kept(home):
    from http.server import ThreadingHTTPServer
    import urllib.request
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(body):
        request = urllib.request.Request(base + "/api/ui", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(request, timeout=30).read())
    try:
        post({"app_window": False})                                            # another setting: the default stays
        assert server.ui_settings()["interface_native"] is True
        post({"interface_native": False})                                      # turned off in Settings
        post({"app_window": True})
        assert server.ui_settings()["interface_native"] is False
        post({"interface_native": True})
        assert server.ui_settings()["interface_native"] is True
    finally:
        srv.shutdown()


def test_the_native_windows_open_in_their_own_processes(monkeypatch):
    started = []
    monkeypatch.setattr(gui.subprocess, "Popen", lambda args, env=None, close_fds=True: started.append((args, env)) or "proc")
    assert gui.spawn("window", "http://127.0.0.1:8765/#/meter") == "proc"
    args, env = started[-1]
    assert args[1:] == ["-m", "aion2calc.gui", "--url", "http://127.0.0.1:8765/#/meter"]
    assert env[gui.ENV_KIND] == "window" and env["AION2CALC_PARENT_PID"] == str(os.getpid())
    gui.spawn("overlay", "http://127.0.0.1:8765/overlay")
    assert started[-1][0][1:3] == ["-m", "aion2calc.gui.overlay"]
    gui.spawn("window", "http://127.0.0.1:8765/", 4321)                               # the app runs in another process
    assert started[-1][1]["AION2CALC_PARENT_PID"] == "4321"
    gui.spawn("window", "http://127.0.0.1:8765/", 0)                                  # one not known: tied to none
    assert started[-1][1]["AION2CALC_PARENT_PID"] == ""
    monkeypatch.setattr(gui.sys, "frozen", True, raising=False)                       # the installed app
    gui.spawn("overlay", "http://127.0.0.1:8765/overlay")
    args, env = started[-1]
    assert args == [gui.sys.executable] and env[gui.ENV_KIND] == "overlay" and env[gui.ENV_URL].endswith("/overlay")
    with pytest.raises(ValueError):
        gui.spawn("radar", "x")


def test_the_launcher_and_the_overlay_open_the_native_windows_when_it_is_on(monkeypatch):
    spawned = []
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: spawned.append((kind, url)) or kind)
    monkeypatch.setattr(gui, "enabled", lambda ui=None: True)
    assert launcher.open_window("http://127.0.0.1:8765/") == "window"
    assert overlay_launch._spawn("http://127.0.0.1:8765/overlay") == "overlay"
    assert spawned == [("window", "http://127.0.0.1:8765/"), ("overlay", "http://127.0.0.1:8765/overlay")]
    monkeypatch.setattr(overlay_launch, "_webview", lambda: False)
    assert overlay_launch.available()                                                 # the native overlay can open
    with pytest.raises(OSError):                                                      # a companion needs pywebview
        overlay_launch._spawn("http://127.0.0.1:8765/overlay?view=radar")
    ran = []
    monkeypatch.setenv(gui.ENV_KIND, "overlay")
    monkeypatch.setenv(gui.ENV_URL, "http://127.0.0.1:8765/overlay")
    monkeypatch.setattr(native_overlay, "main", lambda argv: ran.append(argv) or 0)
    monkeypatch.setattr("aion2calc.tls.install", lambda: True)
    assert launcher.main([]) == 0 and ran == [["--url", "http://127.0.0.1:8765/overlay"]]


class _Process:
    """A native window's process for the launcher: it ends with ``code`` once let go (``end``), or runs on (None)."""

    def __init__(self, code=None):
        self.code, self.done = code, threading.Event()

    def end(self):
        self.done.set()

    def wait(self, timeout=None):
        if self.code is None or not self.done.wait(timeout):
            raise subprocess.TimeoutExpired("aion2calc", timeout)
        return self.code


def _until(condition, seconds=5.0):
    deadline = time.time() + seconds
    while not condition() and time.time() < deadline:
        time.sleep(0.01)
    return condition()


def _finished_starting():
    for thread in threading.enumerate():
        if thread.name == "native-window-start":
            thread.join(5)


@pytest.fixture
def web(monkeypatch):
    """The web interface's window as the launcher opens it (Edge in app mode), recorded; the native interface not
    given up on yet, and a native window's start watched for half a second."""
    opened = []
    monkeypatch.setattr(gui, "_FAILED", {})
    monkeypatch.setattr(gui, "FAILS_WITHIN", 0.5)
    monkeypatch.setattr(launcher, "app_browser", lambda: "C:/Edge/msedge.exe")
    monkeypatch.setattr(launcher, "work_area", lambda: (1920, 1080))
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: opened.append(args) or "web")
    monkeypatch.setitem(server.APP_WINDOW, "process", None)
    return opened


def test_a_native_window_that_fails_as_it_starts_gives_way_to_the_web_interface(home, web, monkeypatch):
    url = "http://127.0.0.1:8765/"
    monkeypatch.setattr(gui, "available", lambda: True)
    window, spawned = _Process(1), []
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: spawned.append((kind, parent_pid)) or window)
    assert gui.enabled() and launcher.open_window(url) is window and spawned == [("window", None)]
    server.APP_WINDOW["process"] = window                                       # the app keeps its window
    window.end()                                                                # Qt could not open it on this computer
    assert _until(lambda: web) and web[0][0] == "C:/Edge/msedge.exe" and f"--app={url}" in web[0]
    assert _until(lambda: server.APP_WINDOW["process"] == "web")                # the app closes this one when it quits
    assert gui.failed() == "the native window ended with code 1 as it started"
    assert not gui.enabled() and not gui.enabled({"interface_native": True})    # until the app starts again
    overlay_launch._spawn(url + "overlay")                                      # and the overlay is the web one
    assert web[-1][1:3] == ["-m", "aion2calc.overlay"]
    # A native window that runs on, or that was closed normally, stays the app's window.
    monkeypatch.setattr(gui, "_FAILED", {})
    for code in (None, 0):
        window = _Process(code)
        window.end()
        web.clear()
        assert launcher.open_window(url) is window
        _finished_starting()
        assert web == [] and not gui.failed()
    # One the app closed as it quit, soon after its start, is not a failure either.
    monkeypatch.setitem(server.HTTPD, "closing", True)
    window = _Process(1)
    window.end()
    assert launcher.open_window(url) is window
    _finished_starting()
    assert web == [] and not gui.failed()
    monkeypatch.setitem(server.HTTPD, "closing", False)

    def missing(kind, url, parent_pid=None):                                    # one that cannot be started at all
        raise OSError("no such file")
    monkeypatch.setattr(gui, "spawn", missing)
    assert launcher.open_window(url) == "web" and gui.failed() == "the native window could not start: no such file"


def test_a_second_start_ties_its_native_window_to_the_running_app(home, web, monkeypatch):
    from aion2calc import tls
    from aion2calc.app.server import make_server
    url = "http://127.0.0.1:8765/"
    running, spawned = _Process(None), []
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: spawned.append(parent_pid) or running)
    # The second start ends at once, so it sees the window open before it does: this one ran on.
    assert launcher.open_window(url, native=True, parent_pid=4321, wait=True) is running
    assert spawned == [4321] and web == []
    failing = _Process(3)
    failing.end()
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: failing)
    assert launcher.open_window(url, native=True, parent_pid=4321, wait=True) == "web"      # this one failed
    assert web[0][0] == "C:/Edge/msedge.exe"
    # The running app says which process it is, and the second start hands that to the window. A fresh app makes its
    # database on its first status, which on a slow machine outlasts the two seconds the launcher waits (a running app
    # has made it long since): it is made first.
    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/status", timeout=60).read()
        assert launcher._app_pid(srv.server_address[1]) == os.getpid()
    finally:
        srv.shutdown()
    assert launcher._app_pid(launcher.free_port(0)) == 0                       # no app there
    calls = []
    monkeypatch.setattr(launcher, "running_app", lambda port: True)
    monkeypatch.setattr(launcher, "_app_pid", lambda port: 4321)
    monkeypatch.setattr(launcher, "open_window", lambda *args, **kwargs: calls.append((args, kwargs)))
    try:
        assert launcher.main(["--port", "8765"]) == 0
    finally:
        tls.uninstall()
    assert calls == [(("http://127.0.0.1:8765/", True), {"parent_pid": 4321, "wait": True})]


def test_a_native_overlay_that_fails_as_it_starts_gives_way_to_the_web_overlay(home, monkeypatch):
    from aion2calc.overlay_health import RelaunchLimiter

    class Overlay(_Process):
        native = True

    spawned = []
    monkeypatch.setattr(gui, "_FAILED", {})
    monkeypatch.setattr(overlay_launch, "_RELAUNCHES", RelaunchLimiter())
    monkeypatch.setattr(overlay_launch, "_PROCESS", None)
    monkeypatch.setattr(overlay_launch, "_spawn", lambda url: spawned.append(Overlay(3)) or spawned[-1])
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    monkeypatch.setattr(overlay_launch, "_party_enabled", lambda: False)
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    spawned[0].end()                                                            # Qt could not open the overlay
    assert _until(lambda: len(spawned) == 2)                                    # started again
    assert gui.failed() == "the native overlay ended with code 3 as it started"
    log = (home / "home" / "logs" / "overlay.log").read_text(encoding="utf-8")
    assert "the overlay opens in pywebview until the app starts again" in log
    monkeypatch.setattr(overlay_launch, "_PROCESS", None)                       # the app lets the second one go
    spawned[1].end()
