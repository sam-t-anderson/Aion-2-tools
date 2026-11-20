"""The native Settings page (0.2.414): the web Settings page's rows, drawn from ``aion2calc/gui/settings_schema``.

Every control the schema names saves one setting through the app's ``/api/ui``, as the web page's control does,
so each key must be one of the app's settings and each default must fit its control; the page fills its controls
from the app's settings without saving them back, and a row it does not draw in full opens the web page.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.app import server  # noqa: E402
from aion2calc.gui.settings_page import SettingsPage  # noqa: E402
from aion2calc.gui.settings_schema import GROUPS, ROWS, Bool, Choice  # noqa: E402
from aion2calc.gui.window import MainWindow  # noqa: E402

CONTROLS = [control for row in ROWS for control in row.controls]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists, as in test_native_interface.py:
    a window left for Python to collect at exit crashed the process on its way out."""
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


def test_every_control_saves_one_of_the_apps_settings_and_its_default_fits(home):
    defaults = server.ui_settings()
    assert len(ROWS) == 37 and len(CONTROLS) == 99
    assert len({control.key for control in CONTROLS}) == len(CONTROLS)                 # one control per setting
    for control in CONTROLS:
        assert control.key in defaults, control.key
        value = defaults[control.key]
        if isinstance(control, Bool):
            assert isinstance(value, bool), control.key
        elif isinstance(control, Choice):
            assert control.cast(value) in [option for option, _text in control.options], control.key
        else:
            assert control.minimum <= value <= control.maximum, control.key
    assert {row.group for row in ROWS} <= {key for key, _title in GROUPS}


def test_the_page_shows_the_settings_without_saving_them_back(qapp, home):
    page = SettingsPage(None, lambda page: None)
    ui = {**server.ui_settings(), "overlay_show_weekly_runs": False, "overlay_width": 420, "overlay_bg_mode": "top",
          "app_text_scale": 120}
    page.apply(ui)
    assert page.saved == []
    assert page.controls["overlay_show_weekly_runs"].box.isChecked() is False
    assert page.controls["overlay_show_odyle"].box.isChecked() is True
    assert page.controls["overlay_width"].value() == 420
    assert page.controls["overlay_bg_mode"].currentData() == "top"
    assert page.controls["app_text_scale"].currentData() == 120


def test_each_control_saves_its_setting(qapp, home):
    page = SettingsPage(None, lambda page: None)
    page.apply(server.ui_settings())
    page.controls["overlay_show_weekly_runs"].box.setChecked(False)
    page.controls["overlay_show_weekly_runs"].label.mousePressEvent(None)            # the label toggles it too
    choice = page.controls["overlay_bg_mode"]
    choice.setCurrentIndex(choice.findData("none"))
    page.controls["app_text_scale"].setCurrentIndex(page.controls["app_text_scale"].findData(90))
    assert page.saved == [("overlay_show_weekly_runs", False), ("overlay_show_weekly_runs", True),
                          ("overlay_bg_mode", "none"), ("app_text_scale", 90)]
    page.controls["overlay_width"].setValue(500)
    page.controls["overlay_width"].setValue(520)                                       # typed on: saved once, when still
    clock = QElapsedTimer()
    clock.start()
    while len(page.saved) < 5 and clock.elapsed() < 3000:
        QCoreApplication.processEvents()
    assert page.saved[4:] == [("overlay_width", 520)] and page.status.text() == "Saved"


def test_the_group_filter_and_the_rows_on_the_web(qapp, home):
    opened = []
    page = SettingsPage(None, opened.append)
    page.filter.setCurrentIndex(page.filter.findData("overlay"))
    shown = {group for group, frame in page.row_frames if not frame.isHidden()}
    assert shown == {"overlay"}
    page.filter.setCurrentIndex(0)
    assert all(not frame.isHidden() for _group, frame in page.row_frames)
    web = [row for row in ROWS if row.web]
    assert {row.title for row in web} >= {"Log server", "Hotkeys (Windows)", "Settings backup", "Overlay colors & fonts"}
    from PySide6.QtWidgets import QPushButton
    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "Open the web Settings page"]
    assert len(buttons) == len(web)
    buttons[0].click()
    assert opened == ["settings"]


def test_the_window_draws_settings_natively(qapp, home):
    window = MainWindow(None, "http://127.0.0.1:8765/", page="settings")
    assert isinstance(window.page("settings"), SettingsPage)
    assert window.pages.currentWidget() is window.page("settings")
