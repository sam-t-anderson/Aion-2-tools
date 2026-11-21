"""The native interface (0.2.413, a preview): the app's windows drawn by Qt (PySide6) in Python.

The windows read the app through its local API, as the web pages do, so they are tested here on the same meter
answers the browser tests use (``tests/browser/test_browser_overlay_look.py``), off screen. The setting that
turns them on, and the launcher and overlay hooks that open them, are tested without Qt.
"""
import json
import os
import sys
import threading
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


def test_the_live_meter_page_shows_the_fight_and_its_buttons(qapp):
    page = MeterPage(None)
    page.apply({**_meter(), "running": True})
    assert page.table.rowCount() == 3
    assert [page.table.item(row, 0).text() for row in range(3)] == ["Seraphel", "Nyxara", "Velmira"]
    assert page.table.item(0, 2).text() == "23.40K" and page.table.item(0, 4).text() == "51.0%"
    assert not page.start_button.isEnabled() and page.stop_button.isEnabled()
    assert page.fight.text() == "Atiel · 75s · 45.70K raid DPS"
    assert "Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)" in page.lines.text()
    page.apply({"running": False, "snapshot": {}})
    assert page.table.rowCount() == 0 and page.start_button.isEnabled() and page.fight.text() == "No fight yet"

    class Recorder:
        def __init__(self):
            self.calls = []

        def post(self, path, payload):
            self.calls.append((path, payload))
            return {}

    app = Recorder()
    MeterPage(app).start_capture()                    # Self + Party, as the web page starts (0.2.416)
    assert app.calls == [("/api/meter", {"action": "start", "source": "a2tools", "auto_port": True, "scope": "party"})]


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
def test_the_setting_is_off_by_default_and_kept_in_the_backup(home, monkeypatch):
    assert server.ui_settings()["interface_native"] is False
    assert _clean({"interface_native": True}) == {"interface_native": True}
    with pytest.raises(ValueError):
        _clean({"interface_native": "yes"})
    monkeypatch.setattr(gui, "available", lambda: True)
    assert gui.enabled({"interface_native": True}) and not gui.enabled({"interface_native": False})
    monkeypatch.setattr(gui, "available", lambda: False)
    assert not gui.enabled({"interface_native": True})                                # without PySide6: the web


def test_the_native_windows_open_in_their_own_processes(monkeypatch):
    started = []
    monkeypatch.setattr(gui.subprocess, "Popen", lambda args, env=None, close_fds=True: started.append((args, env)) or "proc")
    assert gui.spawn("window", "http://127.0.0.1:8765/#/meter") == "proc"
    args, env = started[-1]
    assert args[1:] == ["-m", "aion2calc.gui", "--url", "http://127.0.0.1:8765/#/meter"]
    assert env[gui.ENV_KIND] == "window" and env["AION2CALC_PARENT_PID"] == str(os.getpid())
    gui.spawn("overlay", "http://127.0.0.1:8765/overlay")
    assert started[-1][0][1:3] == ["-m", "aion2calc.gui.overlay"]
    monkeypatch.setattr(gui.sys, "frozen", True, raising=False)                       # the installed app
    gui.spawn("overlay", "http://127.0.0.1:8765/overlay")
    args, env = started[-1]
    assert args == [gui.sys.executable] and env[gui.ENV_KIND] == "overlay" and env[gui.ENV_URL].endswith("/overlay")
    with pytest.raises(ValueError):
        gui.spawn("radar", "x")


def test_the_launcher_and_the_overlay_open_the_native_windows_when_it_is_on(monkeypatch):
    spawned = []
    monkeypatch.setattr(gui, "spawn", lambda kind, url: spawned.append((kind, url)) or kind)
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
