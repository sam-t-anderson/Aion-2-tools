"""Every choice, field and slider of the native windows has words a screen reader can say (0.2.508): the words of the
label beside it, as the web pages' ``<label>`` gives its ``<select>``, where News' and Timers' choices, the overlay's
options and opacity sliders and four read-only logs had none. Drawn off screen.
"""
import os
import pathlib
import re
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QLineEdit,  # noqa: E402
                               QPlainTextEdit, QSlider, QTextEdit, QWidget)

from aion2calc.gui import interface, theme  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_settings import FakeApp  # noqa: E402

GUI = pathlib.Path(__file__).resolve().parent.parent / "aion2calc" / "gui"
CONTROLS = (QAbstractButton, QComboBox, QLineEdit, QAbstractSpinBox, QSlider, QPlainTextEdit, QTextEdit)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()
    theme.apply_look("dark")


def _words(control) -> str:
    """What a screen reader can say of a control: its name, else its own words, else its tip."""
    if control.accessibleName().strip():
        return control.accessibleName().strip()
    if isinstance(control, QAbstractButton) and control.text().strip():
        return control.text().strip()
    if isinstance(control, QLineEdit) and control.placeholderText().strip():
        return control.placeholderText().strip()
    return control.toolTip().strip()


def _nameless(root, within) -> list:
    return [(type(c).__name__, c.objectName()) for c in root.findChildren(QWidget)
            if isinstance(c, CONTROLS) and c.isVisibleTo(within) and not _words(c)
            and not isinstance(c.parent(), QAbstractSpinBox)]          # a spin box's own field: the box's name is it


def test_every_page_of_the_window_names_its_controls(qapp, monkeypatch):
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    window = native_window.MainWindow(FakeApp())
    window.show()
    QCoreApplication.processEvents()
    missing = {}
    for key in window.page_index:
        window.show_page(key)
        for _ in range(3):
            QCoreApplication.processEvents()
        found = _nameless(window.page(key), window)
        if found:
            missing[key] = found
    found = _nameless(window.header, window)
    if found:
        missing["header"] = found
    assert missing == {}


def test_news_and_timers_choices_say_their_labels(qapp):
    from aion2calc.gui.news import NewsPage
    from aion2calc.gui.timers_page import TimersPage
    news = NewsPage(None)
    assert (news.region_box.accessibleName(), news.filter_box.accessibleName()) == ("News region", "Show")
    timers = TimersPage(None)
    assert [box.accessibleName() for box in (timers.region_box, timers.group_box, timers.server_box,
                                             timers.faction_box)] == [
        "Game region", "Korean matching group", "Game server", "Faction"]


def test_the_overlay_windows_options_and_opacity_say_their_labels(qapp):
    from aion2calc.gui.companions import PartyWindow
    from aion2calc.gui.overlay import MeterOverlay
    overlay = MeterOverlay()
    overlay.apply_ui({"overlay_width": 340})
    assert overlay.slider.accessibleName() == "Opacity"
    picks = [box for box in overlay.findChildren(QComboBox) if box.objectName() == "ovsel"]
    assert picks and all(box.accessibleName() for box in picks)
    party = PartyWindow()
    assert party.foot.slider.accessibleName() == "Opacity"                  # each companion window's foot


def test_no_choice_field_or_slider_is_made_without_a_name():
    """Each one the native windows make is named (or given its placeholder) where it is made, as a page shown in
    the first test may not show them all: a log only while a calculation runs, a saved advice's text."""
    made = re.compile(r"\s*(self\.\w+|\w+)\s*=\s*(QComboBox|QLineEdit|QSpinBox|QDoubleSpinBox|QDateEdit|QTextEdit|"
                      r"QPlainTextEdit|QSlider)\(")
    unnamed = []
    for path in sorted(GUI.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines):
            match = made.match(line)
            if match is None:
                continue
            name, near = match.group(1), "\n".join(lines[number:number + 14])
            if not (f"{name}.setAccessibleName" in near or f"{name}.setPlaceholderText" in near
                    or "setAccessibleName" in line or "placeholder" in line.lower()):
                unnamed.append(f"{path.name}:{number + 1}")
    assert unnamed == []
