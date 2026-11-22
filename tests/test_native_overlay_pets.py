"""The Pet Tracker window, natively (0.2.498): Pet Tracker's pets on the overlay's card in a Qt window of its own
(``aion2calc/gui/pets_window.py``), where until now it was a page in pywebview (pet-overlay.html,
``overlay?view=pets``).

Pet Tracker's state is the app's own (``pettracker.render`` of a worker's view, ``tests/test_native_pets.py``'s
stand-in for the app), and its controls change that view as Pet Tracker would; the window is drawn off screen.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.app import overlay_launch  # noqa: E402
from aion2calc import gui  # noqa: E402
from aion2calc.gui import companions as cp  # noqa: E402
from aion2calc.gui import pets_window as pw  # noqa: E402
from aion2calc.gui.interface import OVERLAY, InterfaceStore, _Shared  # noqa: E402
from aion2calc.overlay import _GameWindow  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_overlay_window import Desktop  # noqa: E402
from test_native_pets import FakeApp, _waiting_to_link  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


class Overlay(FakeApp):
    """The app with the overlay's own requests too: its settings, its commands and Hide."""

    def get(self, path):
        if path == "/api/overlay/commands":
            self.calls.append(path)
            return {"lock_seq": 0, "reload_seq": 0}
        return super().get(path)

    def post(self, path, body):
        if path == "/api/overlay":
            self.posts.append((path, body))
            return {"hidden": True}
        return super().post(path, body)


def _window(api=None, **ui):
    window = pw.PetsWindow(api if api is not None else Overlay())
    window.apply_ui(ui)
    window.show()
    window.start()
    settle(lambda: window.state is not None)
    QCoreApplication.processEvents()
    return window


def _names(window):
    return [row.name.text() for row in window.pet_rows]


def _words(window):
    QCoreApplication.processEvents()
    return [label.text() for label in window.rows.findChildren(QLabel) if label.isVisibleTo(window.rows)
            and label.objectName() == "ptempty"]


def test_the_window_draws_pet_trackers_pets(qapp):
    window = _window()
    assert window.windowTitle() == "Aion 2 Calc Pet Tracker" and window.width() == 320
    assert window.title.text == "Pet Tracker" and [b.text() for b in window.buttons.values()] == ["Lock", "Hide"]
    assert window.status.text() == "Ranger · Live" and "#76c59d" in window.status.styleSheet()
    assert window.modes["Recent"].property("on") and not window.modes["Nearby"].property("on")
    assert window.modes["Recent"].isEnabled() and not window.hide_maxed.isChecked()
    assert _names(window) == ["Forest Specter", "Klaw", "Krall Laborer"]
    first = window.pet_rows[0]
    assert first.progress.text() == "3 / 5" and first.family.text() == "Natura" and first.picture.width() == 40
    assert first.bar.track == pw.TRACK and not first.bar.isHidden()
    assert window.pet_rows[2].progress.text() == "✓ MAX" and window.pet_rows[2].bar.isHidden()
    assert window.foot.brand.text() == "Pet Tracker · 0Fox2Give" and window.foot.brand.toolTip() == pw.BRAND_TIP
    settle(lambda: window.pet_rows[0].picture.pixmap is not None)          # the portraits, each read once
    assert window.pet_rows[1].picture.none                                  # one the app has not
    assert sum(call.startswith("/api/pettracker/portrait/") for call in window.api.calls) == 3
    window.show_state({**window.state, "options": {**window.state["options"], "compact": True, "accent": "Teal"}})
    assert window.pet_rows[0].picture.width() == 30 and window.pet_rows[0].bar.colour == pw.ACCENTS["Teal"]
    assert pw.ACCENTS["Teal"] in window.styleSheet()
    window.show_state({**window.state, "sync_notice": True})
    assert window.sync.isVisibleTo(window) and "Totals paused." in window.sync.text()


def test_the_controls_go_back_to_pet_tracker(qapp):
    app = Overlay()
    window = _window(app)

    def sent(body):
        settle(lambda: app.posts and app.posts[-1] == ("/api/pettracker", body))
    window.modes["Nearby"].click()
    assert window.modes["Recent"].property("on")                          # until Pet Tracker answers
    sent({"action": "mode", "value": "Nearby"})
    settle(lambda: window.modes["Nearby"].property("on"))
    assert not window.modes["Recent"].property("on")
    window.modes["Recent"].click()
    sent({"action": "mode", "value": "Recent"})
    window.hide_maxed.click()
    sent({"action": "hide_maxed", "value": True})
    settle(lambda: _names(window) == ["Forest Specter", "Klaw"])
    window.hide_maxed.click()
    sent({"action": "hide_maxed", "value": False})
    settle(lambda: len(window.pet_rows) == 3)
    window.pet_rows[0].pin.click()
    sent({"action": "pin", "pet": 1003, "value": True})
    settle(lambda: window.pet_rows[0].pin.text() == "★")
    app.refuse = "Pin limit reached. Unpin a pet first."
    window.pet_rows[1].pin.click()
    settle(lambda: window.status.text() == "Pin limit reached. Unpin a pet first.")
    assert "#e9a4b6" in window.status.styleSheet()                          # said in the "off" colour


def test_why_there_are_no_pets_and_the_character_to_link(qapp):
    window = _window()
    for state, words in ((None, "Loading Pet Tracker…"), ({"supported": False}, "Pet Tracker runs on Windows only."),
                         ({"supported": True, "installed": True, "enabled": False},
                          "Pet Tracker is off. Turn it on under Settings → Pet Tracker.")):
        window.show_state(state)
        assert _words(window) == [words] and window.pet_rows == []
        assert not window.modes["Recent"].isEnabled() and not window.hide_maxed.isEnabled()
        assert "#e9a4b6" in window.status.styleSheet() or state is None
    app = Overlay(view=_waiting_to_link())
    window = _window(app)
    assert window.status.text() == "Alt is not linked to Main account"
    assert _words(window)[0].startswith("Alt is not one of the characters of your Pet Tracker account Main account")
    button = window.link_button
    assert button is not None and button.text() == "Link Alt to Main account"
    button.click()
    assert not button.isEnabled()
    settle(lambda: ("/api/pettracker", {"action": "link", "character": "Alt"}) in app.posts)
    settle(lambda: window.link_button is None and len(window.pet_rows) == 3)   # linked: the pets come
    window.show_state({**window.state, "connected": True, "rows": [], "empty": "No pet rewards yet.", "link": None})
    assert _words(window) == ["No pet rewards yet."]


def test_it_reads_pet_tracker_each_second_while_connected_and_not_while_locked(qapp):
    app = Overlay()
    window = _window(app)
    assert window._poll.isActive() and window._poll.interval() == 1000
    assert pw.poll_ms(None) == pw.poll_ms({"connected": False}) == 2000 and pw.poll_ms({"connected": True}) == 1000
    window.toggle_lock()
    asked = app.calls.count("/api/pettracker")
    window.poll()
    assert app.calls.count("/api/pettracker") == asked and window._poll.isActive()   # held, and asked again later
    window.toggle_lock()
    settle(lambda: app.calls.count("/api/pettracker") > asked)
    assert pw.mode_of(None) == "Recent" and pw.mode_of({"options": {"mode": "Nearby"}}) == "Nearby"


def test_hide_turns_the_window_off(qapp):
    app = Overlay()
    window = _window(app)
    window.hide_window()
    settle(lambda: not window.isVisible())
    assert ("/api/overlay", {"action": "hide", "view": "pets"}) in app.posts


def test_it_keeps_its_own_place_and_look(qapp):
    desktop = Desktop(_GameWindow(hwnd=99, bounds=(100, 50, 1600, 900)))
    window = pw.PetsWindow(None, win32=desktop)
    window.apply_ui({"overlay_text_colors": {"header": "#ff0000"}, "overlay_bg_mode": "none", "overlay_glow": True,
                     "overlay_font_scale": 150, "overlay_hover_interact": True, "overlay_click_through": True})
    assert window.title.colour == cp.GOLD and window.card.mode == "card" and not window.text_look.glow
    assert window.ui.get("overlay_hover_interact") is None and window.click_through       # no hover; click-through
    window.host._follow_game()
    assert desktop.moves == [(116, 50 + 360)]                              # first below the meter overlay's corner
    window._commands({"lock_seq": 1, "reload_seq": 0})
    window._commands({"lock_seq": 2, "reload_seq": 0})
    assert not window.locked                                               # the screenshot hotkey is the overlay's
    placed = pw.PetsWindow(None, win32=Desktop())
    placed.apply_ui({"overlay_pets_pos_x": 300, "overlay_pets_pos_y": 200, "overlay_pets_pos_layout": [[0, 0, 1920, 1080]]})
    assert placed.host.place == "overlay_pets_pos" and placed.host.placed
    store = InterfaceStore(OVERLAY, shared=_Shared())
    kept = pw.PetsWindow(None, store=store)
    assert kept.card.opacity == 0.9                                         # 90% until moved
    kept.foot.slider.setValue(50)
    assert float(store.value("opacity-pets")) == 0.5 and store.value("opacity") is None


def test_the_app_opens_the_pet_tracker_window_natively(monkeypatch):
    spawned = []
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: spawned.append((kind, url)) or object())
    monkeypatch.setattr(gui, "enabled", lambda ui=None: True)
    monkeypatch.setattr(overlay_launch, "_webview", lambda: False)
    overlay_launch._spawn("http://127.0.0.1:8765/overlay?view=pets")
    assert spawned[-1] == ("overlay", "http://127.0.0.1:8765/overlay?view=pets")
    assert cp.view_of("http://x/overlay?view=pets") == "pets" and cp.window_class("pets") is pw.PetsWindow
    assert cp.window_class("meter") is None
    assert QPushButton is not None
