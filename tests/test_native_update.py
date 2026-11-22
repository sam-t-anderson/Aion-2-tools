"""The quiet update in the native window (0.2.493): app.js's status poll, update bar and Update now."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QProgressBar, QPushButton  # noqa: E402

from aion2calc.gui import update_bar as ub  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_settings import FakeApp, _refused  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _downloading(received=512, total=1024, version="0.2.500"):
    return {"db": {"items": 48213}, "update": {"version": version, "url": "https://example.org/r"},
            "update_download": {"state": "downloading", "version": version, "received": received, "total": total,
                                "kind": "installer"}}


def _ready(kind="installer", on_close=True):
    return {"db": {"items": 48213}, "update_download": {"state": "ready", "version": "0.2.500", "kind": kind},
            "update": {"version": "0.2.500", "url": "https://example.org/r"}, "update_on_close": on_close}


def test_the_status_words_and_when_it_is_asked_again():
    assert ub.poll_ms({"sync": {"running": True}, **_downloading()}) == ub.SYNCING_MS
    assert ub.poll_ms(_downloading()) == ub.DOWNLOADING_MS
    assert ub.poll_ms({"db": {}, "update_state": {"checking": True}}) == ub.CHECKING_MS
    assert ub.poll_ms({"db": {}, "update_state": {"checking": True}, "update": {"version": "1"}}) == ub.IDLE_MS
    assert ub.poll_ms({}) == ub.poll_ms(None) == ub.IDLE_MS
    # a status without the database's count, which the web page's line cannot read: asked for again in 20 s
    assert ub.poll_ms({"update_download": {"state": "downloading"}, "db": None}) == ub.IDLE_MS
    # the download's progress, a whole percent; none known yet
    assert ub.bar_state(_downloading(received=2047, total=4096)) == {
        "kind": "downloading", "words": "Downloading version 0.2.500…", "pct": 49, "key": "downloading"}
    assert ub.bar_state(_downloading(received=10, total=0))["pct"] == 0
    assert ub.bar_state(_downloading(received=9000, total=4096))["pct"] == 100
    # ready: the installer with Update now and its check box, any other download shown
    ready = ub.bar_state(_ready())
    assert ready["words"] == "Update ready: version 0.2.500" and ready["button"] == ub.UPDATE_NOW
    assert ready["installer"] and ready["on_close"] and ready["key"] == "ready:0.2.500"
    assert ub.bar_state(_ready(kind="zip"))["button"] == ub.SHOW_DOWNLOAD
    assert not ub.bar_state(_ready(on_close=False))["on_close"]
    assert ub.bar_state({"update_download": {"state": "failed"}}) is None and ub.bar_state({}) is None
    # the newer release named only where nothing downloads it
    assert ub.available(_ready(), quiet=True) is None and ub.available({}, quiet=False) is None
    assert ub.available(_ready(), quiet=False) == {"words": "Version 0.2.500 available", "url": "https://example.org/r"}
    assert ub.said("up-to-date") == "Already up to date." and ub.said("applying") == "applying"
    assert ub.said(None) == "undefined"


def test_the_window_shows_the_download_then_the_update_ready(qapp):
    from aion2calc.gui.window import MainWindow
    window = MainWindow(None)
    window.resize(1200, 800)
    window.show()
    bar = window.update_bar
    window._status(_downloading(received=256, total=1024))
    assert bar.isVisible() and not window.update_chip.isVisible()
    assert bar.text.text() == "Downloading version 0.2.500…" and bar.findChild(QProgressBar).value() == 25
    assert any(label.text() == "25%" for label in bar.findChildren(QLabel))
    assert bar.x() == 12 and bar.geometry().bottom() == window.centralWidget().height() - 13     # bottom left
    window._status(_downloading(received=768, total=1024))                  # the same bar, further on
    assert bar.findChild(QProgressBar).value() == 75
    # ready: Update now, and the check box as the app keeps it
    window._status(_ready())
    button = bar.findChild(QPushButton)
    box = bar.findChild(QCheckBox)
    assert bar.text.text() == "Update ready: version 0.2.500" and button.text() == ub.UPDATE_NOW
    assert box.text() == ub.ON_CLOSE and box.isChecked() and bar.findChild(QProgressBar) is None
    window._status(_ready(on_close=False))
    assert not box.isChecked()
    # nothing downloading: the bar gone, the newer release named as a link to its page
    window._status({"db": {"items": 1}, "update": {"version": "0.2.500", "url": "https://example.org/r"}})
    assert not bar.isVisible() and window.update_chip.isVisible()
    assert "Version 0.2.500 available" in window.update_chip.text() and 'href="https://example.org/r"' in window.update_chip.text()
    window._status({})                                     # without the database's count: nothing changes (syncPill)
    assert window.update_chip.isVisible()
    window._status({"db": {"items": 1}})
    assert not window.update_chip.isVisible()
    # the app closing for its installer: the window says so in place of its pages
    window._closing()
    assert window.centralWidget().text() == ub.CLOSING
    window.close()


def test_the_status_asked_for_and_update_now_said(qapp):
    app = FakeApp({("GET", "/api/status?fresh=1", None): _downloading(),
                   ("GET", "/api/status", None): [_ready(), _refused("/api/status", 500, "busy"), {}],
                   ("POST", "/api/update", None): [{"status": "up-to-date"}, _refused("/api/update", 500, "no network"),
                                                   {"status": "launching"}],
                   ("POST", "/api/ui", None): {"ok": True}})
    watch = ub.UpdateWatch(app)
    seen, said, closing = [], [], []
    watch.changed.connect(seen.append)
    watch.said.connect(said.append)
    watch.closing.connect(lambda: closing.append(True))
    watch.start()                                                   # a fresh release check first
    settle(lambda: seen)
    assert app.calls[0] == ("GET", "/api/status?fresh=1", None) and seen[0] == _downloading()
    assert watch.timer.isActive() and watch.timer.interval() == ub.DOWNLOADING_MS
    watch.timer.stop()
    watch.ask()                                                     # then plain
    settle(lambda: len(seen) == 2)
    assert app.calls[-1] == ("GET", "/api/status", None) and watch.timer.interval() == ub.IDLE_MS
    watch.timer.stop()
    watch.ask()                                                     # refused: asked again in 20 s
    settle(lambda: watch.timer.isActive())
    assert len(seen) == 2 and watch.timer.interval() == ub.IDLE_MS
    watch.timer.stop()
    # Update now: what the app says, why it failed, then closing for the installer
    watch.update_now()
    settle(lambda: said)
    assert said == ["Already up to date."] and app.sent("POST", "/api/update") == [("POST", "/api/update", {})]
    watch.update_now()
    settle(lambda: len(said) == 2)
    assert said[1] == "Update failed: no network"
    watch.update_now()
    settle(lambda: closing)
    assert not watch.timer.isActive()
    # the check box kept by the app, and said
    watch = ub.UpdateWatch(app)
    watch.said.connect(said.append)
    watch.on_close(False)
    settle(lambda: len(said) == 3)
    assert app.sent("POST", "/api/ui")[-1] == ("POST", "/api/ui", {"update_on_close": False}) and said[2] == ub.WAITS
    watch.on_close(True)
    settle(lambda: len(said) == 4)
    assert said[3] == ub.INSTALLS_ON_CLOSE
    QCoreApplication.processEvents()


def test_the_bar_s_button_and_check_box_ask_the_app(qapp):
    from aion2calc.gui.window import MainWindow
    window = MainWindow(None)
    asked = []
    window.update_bar.update_now = lambda: asked.append("update")
    window.update_bar.on_close = lambda checked: asked.append(("close", checked))
    window.show()
    window._status(_ready())
    window.update_bar.findChild(QPushButton).click()
    window.update_bar.findChild(QCheckBox).click()
    assert asked == ["update", ("close", False)]
    window.close()
