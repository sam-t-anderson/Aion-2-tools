"""The native window in the web pages' theme and accent colour (0.2.484, ``gui/theme.py``): app.css's dark and light
themes and its six accents, read from app.css itself; the theme and accent the web pages keep, shown as the window
opens and drawn again when another is chosen (Settings → Appearance), or when the computer turns light or dark while
the theme follows it. What the pages draw reads the look shown when it is drawn."""
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import shiboken6  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import interface, theme  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
#: The dark theme the native window had until 0.2.484, written out by hand.
DARK_UNTIL_NOW = {
    "bg0": "#070a10", "bg1": "#0d1320", "bg2": "#121a2a", "panel": "#101623", "panel2": "#182032",
    "card_a": "#1c2236", "card_b": "#121726", "hover": "#1b2337", "line": "#263048", "line2": "#3a4562",
    "gold": "#e8cf8e", "gold_dim": "#b49a5c", "text": "#e9e6df", "muted": "#9aa3b5", "faint": "#848b9a",
    "accent": "#39c2e0", "good": "#6fcf7a", "bad": "#e66a5a", "warn": "#e9a43a",
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def look(qapp, monkeypatch):
    """A look for one test, the choices in a store of their own; the dark one again after."""
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    yield theme.apply_look
    theme.apply_look("dark")


def settle(done=lambda: True, rounds=200):
    for _ in range(rounds):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
        if done():
            return True
    return done()


def test_the_palettes_are_app_css(look):
    assert {k: theme.COLORS[k] for k in DARK_UNTIL_NOW} == DARK_UNTIL_NOW          # nothing changed in the dark
    css = (ROOT / "aion2calc" / "app" / "static" / "app.css").read_text(encoding="utf-8")
    light = re.search(r":root\[data-theme=light\] \{(.*?)\n\}", css, re.S).group(1)
    for name, value in re.findall(r"--([\w-]+):\s*([^;]+);", light):
        assert theme.palette("light")[name.replace("-", "_")] == value.strip(), name
    # each accent's own rule, over each theme; the theme's colours for the rest
    for accent in theme.ACCENTS[1:]:
        for shown, selector in (("dark", f":root[data-accent={accent}]"), ("light", f":root[data-accent={accent}][data-theme=light]")):
            rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css).group(1)
            own = {n.replace("-", "_"): v.strip() for n, v in re.findall(r"--([\w-]+):\s*([^;]+);", rule)}
            assert set(own) == {"gold", "gold_dim", "accent", "note_fg", "chart_line"}
            mixed = theme.palette(shown, accent)
            assert {k: mixed[k] for k in own} == own and mixed["bg1"] == theme.palette(shown)["bg1"], (accent, shown)
    assert theme.palette("light", "gold") == theme.palette("light")                # gold is the theme's own


def test_the_look_chosen_and_the_computers(look):
    assert look("light") == "light" and theme.COLORS["bg1"] == "#f7f2e7" and theme.LOOK["theme"] == "light"
    assert theme.COLORS["panel"] == "#fffcf5" and theme.css("panel") == "rgba(255, 252, 245, 0.96)"   # as Qt reads it
    assert look("dark", "rose") == "dark" and theme.COLORS["gold"] == "#f0a8c6" and theme.COLORS["bg1"] == "#0d1320"
    assert look("system", "azure", computer_light=True) == "light" and theme.COLORS["gold"] == "#1f5a8a"
    assert look("system", computer_light=False) == "dark" and theme.LOOK == {"theme": "system", "accent": "gold",
                                                                             "shown": "dark"}
    assert look("sepia", "plaid", computer_light=True) == "light" and theme.LOOK["accent"] == "gold"   # not theirs
    store = interface.store()
    assert theme.look_of(store) == ("system", "gold")
    store.setValue("theme", "light")
    store.setValue("accent", "emerald")
    assert theme.look_of(store) == ("light", "emerald")
    store.setValue("theme", "neon")
    store.setValue("accent", "neon")
    assert theme.look_of(store) == ("system", "gold")


def test_colours_read_as_the_look_is_when_written(look):
    gain, frame = theme.Shade("gain"), theme.Shade("frame", whole=True)
    sheet = theme.Sheet(lambda: f"color: {gain}; border: 1px solid {frame};")
    grades = theme.Shades({"Rare": theme.Shade("g_rare"), "Common": theme.Shade("g_common", whole=True)})
    assert str(sheet) == "color: #8fe08f; border: 1px solid rgba(206, 182, 122, 0.28);"
    assert "QLabel { " + sheet == "QLabel { " + str(sheet) and sheet == str(sheet)
    assert grades["Rare"] == "#52b35c" and grades.get("Common") == "rgba(255, 255, 255, 0.88)" and grades.get("x") is None
    inset = theme.qcolor("inset")
    assert (inset.red(), inset.green(), inset.blue(), inset.alpha()) == (6, 9, 15, 166)
    look("light")
    assert str(sheet) == "color: #23853a; border: 1px solid rgba(160, 120, 45, 0.32);"
    assert f"{gain}" == "#23853a" and gain == "#23853a" and "x" + gain == "x#23853a"
    assert grades.items() == [("Rare", "#2f8a3a"), ("Common", "#4a4f5c")] and "Rare" in grades
    assert theme.qcolor("inset").alpha() == round(0.7 * 255)


def test_the_pages_are_drawn_in_the_look_shown(look):
    from aion2calc.gui import advice_view, combat, database_page, result_windows, results
    look("light", "crimson")
    assert "#f7f2e7" in theme.app_stylesheet() and "#a12b2b" in theme.app_stylesheet()      # light, crimson's gold
    assert "rgba(160, 120, 45, 0.32)" in str(result_windows.STYLE)                            # --frame, light
    assert "rgba(236, 228, 211, 0.7)" in str(advice_view.STYLE)                               # --inset, light
    assert database_page.GRADE_COLORS["Rare"] == "#2f8a3a" and results.GRADES["Common"] == "#4a4f5c"
    assert "color: #b63629;" in combat.import_note()                                          # crimson's accent, light
    look("dark")
    assert "#0d1320" in theme.app_stylesheet() and "rgba(206, 182, 122, 0.28)" in str(result_windows.STYLE)
    assert "color: #39c2e0;" in combat.import_note()


def test_the_settings_rows_choose_the_look(look, qapp):
    from aion2calc.gui import settings_words as sw
    from aion2calc.gui.settings_page import SettingsPage
    assert SettingsPage(None, lambda _page: None, store=interface.store()).theme_seg.chosen == "Follow computer"  # none kept
    interface.store().setValue("theme", "dark")
    look("dark")
    page = SettingsPage(None, lambda _page: None, store=interface.store())
    assert [b.text() for b in page.theme_seg.buttons.values()] == ["Follow computer", "Light", "Dark"]
    assert [b.text() for b in page.accent_seg.buttons.values()] == ["Gold", "Crimson", "Emerald", "Azure", "Amethyst",
                                                                    "Rose"]
    assert page.theme_seg.chosen == "Dark" and page.accent_seg.chosen == "Gold"
    assert sw.ACCENT_NOTE in [label.text() for label in page.findChildren(__import__("PySide6.QtWidgets",
                                                                                     fromlist=["QLabel"]).QLabel)]
    page.theme_seg.buttons["Light"].click()                         # no window here to draw again: shown from now on
    assert interface.store().value("theme") == "light" and theme.LOOK["shown"] == "light"
    assert page.theme_seg.chosen == "Light"
    page.accent_seg.buttons["Amethyst"].click()
    assert interface.store().value("accent") == "amethyst" and theme.COLORS["gold"] == "#5a3a9e"
    assert page.accent_seg.chosen == "Amethyst" and interface.store().value("theme") == "light"
    # a theme the web pages do not know: no button chosen, as on the web page, and the computer's look shown
    interface.store().setValue("theme", "neon")
    look(*theme.look_of(interface.store()), computer_light=True)
    again = SettingsPage(None, lambda _page: None, store=interface.store())
    assert again.theme_seg.chosen is None and again.accent_seg.chosen == "Amethyst" and theme.LOOK["shown"] == "light"


def test_the_window_opens_in_the_look_and_draws_itself_again_in_another(look, monkeypatch):
    from aion2calc.gui import window as native_window
    from aion2calc.gui.window import MainWindow
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)       # no app to read
    store = interface.store()
    store.setValue("theme", "light")
    look(*theme.look_of(store))
    first = MainWindow(None)
    assert "#f7f2e7" in first.styleSheet() and first.shown_look == "light"
    first.show_page("settings")
    first.show()
    first.page("settings").accent_seg.buttons["Rose"].click()       # kept, and the window drawn again in it
    again = first.again
    assert store.value("accent") == "rose" and "#9e2a6a" in again.styleSheet() and again.current_page() == "settings"
    assert again.page("settings").accent_seg.chosen == "Rose" and settle(lambda: not shiboken6.isValid(first))
    # the computer turning dark: nothing while the theme is light; the window drawn again once it follows the computer
    again.computer_look_changed()
    assert not hasattr(again, "again")
    again.page("settings").theme_seg.buttons["Follow computer"].click()
    following = again.again
    monkeypatch.setattr(theme, "_computer_light", lambda: not (following.shown_look == "light"))
    following.computer_look_changed()
    assert following.again.shown_look != following.shown_look
    following.again.close()
