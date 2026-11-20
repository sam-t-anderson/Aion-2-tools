"""The native overlay's third part (0.2.416): the web overlay's toolbar and its player panel.

Lock, New, Copy, Options, Start or Stop and Hide send the app what the web overlay's buttons send it (a stand-in for
the app's local API notes each request and answers it), and a click on a player opens their panel with what the
web overlay's panel shows (``tests/browser/test_browser_overlay_look.py``), off screen.
"""
import io
import json
import os
import sys
import time
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.overlay import MeterOverlay, fmt_secs, leaderboard_text  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
from test_browser_overlay_look import BUFFS, fight  # noqa: E402


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


class FakeApp:
    """The app's local API as the overlay calls it: each request is noted, and answered with ``meter`` for the
    meter's reading, the player in depth for the panel, or ``{"ok": True}``; a path in ``refuse`` is refused with
    that message, as the app refuses a request it cannot do."""

    def __init__(self, meter=None, buffs=None):
        self.meter, self.calls, self.refuse, self.buffs = meter or {}, [], {}, BUFFS if buffs is None else buffs

    def get(self, path):
        return self._answer("GET", path, None)

    def post(self, path, payload):
        return self._answer("POST", path, payload)

    def _answer(self, method, path, payload):
        self.calls.append((method, path, payload))
        if path in self.refuse:
            body = io.BytesIO(json.dumps({"error": self.refuse[path]}).encode())
            raise urllib.error.HTTPError("http://127.0.0.1" + path, 400, "Bad Request", {}, body)
        if path.startswith("/api/meter?view=latest"):
            return self.meter
        if path.startswith("/api/meter/player"):
            key = parse_qs(urlparse(path).query).get("key", [""])[0]
            return {"player": {"key": key, "buffs": self.buffs.get(key, []), "active_seconds": 61, "duration": 75.0}}
        return {"ok": True}


def settle(done, timeout=3.0):
    """Let the overlay's requests come back (their answers are signals to the interface's thread) until ``done``."""
    deadline = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < deadline, "the overlay's request was not answered"
        QCoreApplication.processEvents()
        time.sleep(0.005)


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def test_copy_puts_the_views_leaderboard_on_the_clipboard(qapp):
    window = _overlay()
    expected = ("DPS · Atiel · 75s\n1. Seraphel  23.40K/s  (51%)\n2. Nyxara  15.60K/s  (34%)\n"
                "3. Velmira  6.70K/s  (15%)\n— Aion 2 Calc")
    assert window.copy_text == expected
    window.copy()
    assert QGuiApplication.clipboard().text() == expected
    assert window.tools["copy"].text() == "Copied"
    meter = fight()
    meter["targets"] = ["boss"]
    window.apply_meter(meter)
    assert window.copy_text.startswith("DPS · Boss damage only · Atiel · 75s\n")
    window.set_metric("hps")                                                   # no healing: the head alone
    assert window.copy_text == "HPS · Atiel · 75s\n— Aion 2 Calc"


def test_the_leaderboard_and_spans_round_as_the_web_overlay_rounds():
    players = [{"name": "A", "dps": 2.5, "damage": 1}, {"name": "B", "dps": 1, "damage": 1}]
    text = leaderboard_text({"boss": "", "duration": 74.5}, players, "dps", "", lambda p: p["name"])
    assert text.splitlines()[:3] == ["DPS · combat · 75s", "1. A  3/s  (50%)", "2. B  1/s  (50%)"]
    assert (fmt_secs(45.4), fmt_secs(59.5), fmt_secs(75), fmt_secs(None)) == ("45s", "1m 00s", "1m 15s", "0s")


def test_lock_holds_the_reading_and_the_place_and_the_screenshot_hotkey_toggles_it(qapp):
    api = FakeApp(fight())
    window = _overlay(api=api)
    window.show()
    window.toggle_lock()
    assert window.locked and window.tools["lock"].text() == "Unlock" and window.card.toolTip().startswith("Locked")
    later = fight()
    later["snapshot"]["boss"] = "Ereshkigal"
    window._meter_answered(later)
    assert "Atiel" in window.status.text()                                    # the reading it holds
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
    assert window._drag is None                                                # and it does not move
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
    window.toggle_lock()
    assert not window.locked and window.tools["lock"].text() == "Lock"
    settle(lambda: ("GET", "/api/meter?view=latest", None) in api.calls)       # it reads the meter again at once
    window._commands({"lock_seq": 3, "reload_seq": 0})                         # the first reading: the baseline
    assert not window.locked
    window._commands({"lock_seq": 4, "reload_seq": 0})                         # the hotkey was pressed
    assert window.locked
    window._commands({"lock_seq": 4, "reload_seq": 0})
    assert window.locked


def test_new_shows_the_meter_empty_until_the_next_fight_begins(qapp):
    meter = fight()
    meter["snapshot"]["selected_segment"] = 5
    api = FakeApp(meter)
    window = _overlay(meter, api)
    window.new_fight()
    settle(lambda: window.cleared_fight is not None)
    assert ("POST", "/api/meter", {"action": "split"}) in api.calls
    assert window.cleared_fight == "5" and window.tools["split"].text() == "New ✓"
    assert window.status.text() == "New fight · waiting for combat"
    assert _rows(window) == [] and window.empty.text() == "New fight — waiting for the first hit."
    assert window.target.isHidden() and window.copy_text == "DPS · Atiel · 75s\n— Aion 2 Calc"
    following = fight()
    following["snapshot"]["selected_segment"] = 6                               # its first hit gave it an id
    window.apply_meter(following)
    assert window.cleared_fight is None and len(_rows(window)) == 3 and window.empty.isHidden()


def test_start_and_stop_capture_and_say_why_a_start_was_refused(qapp):
    stopped = fight()
    stopped["running"] = False
    api = FakeApp(stopped)
    window = _overlay(stopped, api)
    button = window.tools["capture"]
    assert button.text() == "Start" and button.property("state") == "start"
    window.toggle_capture()
    assert button.text() == "Starting…" and not button.isEnabled()
    settle(lambda: not window._capture_busy)
    assert ("POST", "/api/meter", {"action": "start", "source": "a2tools", "auto_port": True,
                                   "scope": "party"}) in api.calls
    window.apply_meter(fight())
    assert button.text() == "Stop" and button.property("state") == "stop"
    window.toggle_capture()
    settle(lambda: not window._capture_busy)
    assert ("POST", "/api/meter", {"action": "stop", "from_overlay": True}) in api.calls
    api.refuse["/api/meter"] = "Npcap is not installed"
    window.toggle_capture()
    settle(lambda: button.text() == "Error")
    assert button.toolTip() == "Npcap is not installed" and button.property("state") == "err"
    finishing = fight()
    finishing["finalizing"] = True
    window._capture_busy = False
    window.apply_meter(finishing)
    assert button.text() == "Stopping…" and not button.isEnabled()


def test_hide_asks_the_app_to_close_every_overlay_window(qapp):
    api = FakeApp(fight())
    window = _overlay(api=api)
    window.show()
    window.hide_overlay()
    settle(lambda: not window.isVisible())
    assert ("POST", "/api/overlay", {"action": "hide", "view": "meter"}) in api.calls
    gone = FakeApp(fight())
    gone.refuse["/api/overlay"] = "no"
    lonely = _overlay(api=gone)
    lonely.show()
    lonely.hide_overlay()
    settle(lambda: not lonely.isVisible())                                     # it closes all the same


def test_the_options_hold_the_pet_grouping_and_the_damage_filters(qapp):
    api = FakeApp(fight())
    window = _overlay(api=api)
    assert window.options.isHidden()
    window.toggle_options()
    assert not window.options.isHidden() and window.tools["options"].isChecked()
    assert window.combine.isChecked()                                          # the meter's answer combines pets
    window.combine.click()
    settle(lambda: window.combine.isEnabled())
    assert ("POST", "/api/meter", {"action": "view", "combine_pets": False}) in api.calls
    window.boss_only.click()
    settle(lambda: window.boss_only.isEnabled())
    assert ("POST", "/api/ui", {"overlay_boss_only": True}) in api.calls
    api.refuse["/api/ui"] = "read-only settings"
    window.pvp_only.click()
    settle(lambda: window.pvp_only.isEnabled())
    assert not window.pvp_only.isChecked() and window.message.text() == "Could not change the damage filter"
    meter = fight()
    meter["targets"] = ["player"]                                              # the filters the app applies
    window.apply_meter(meter)
    assert window.pvp_only.isChecked() and not window.boss_only.isChecked()
    assert window.status.text().endswith("· Player damage only")
    window.toggle_options()
    assert window.options.isHidden()


def test_the_opacity_and_the_metric_are_kept_for_the_next_time(qapp, tmp_path):
    store = QSettings(str(tmp_path / "native-overlay.ini"), QSettings.IniFormat)
    window = MeterOverlay(store=store)
    assert window.card.opacity == pytest.approx(0.72) and window.slider.value() == 72
    window.slider.setValue(45)
    assert window.card.opacity == pytest.approx(0.45)
    window.set_metric("hps")
    again = MeterOverlay(store=store)
    assert again.card.opacity == pytest.approx(0.45) and again.slider.value() == 45 and again.rate_metric == "hps"
    window.set_opacity(0.05)
    assert window.card.opacity == pytest.approx(0.2) and window.slider.value() == 20


def test_what_the_rows_place_says_without_rows(qapp):
    meter = fight()
    meter["snapshot"]["battle_over"] = True
    window = _overlay(meter)
    assert _rows(window) == [] and window.empty.text() == "Ready — waiting for the next fight."
    assert window.target.isHidden()
    window.apply_meter({"running": False, "snapshot": {}})
    assert window.empty.text() == "No fight yet. Start the meter in the app." and window.status.text() == "Idle"
    window.apply_meter({"running": True, "snapshot": {}})
    assert window.empty.text() == "Waiting for combat data…"
    window.set_metric("hps")
    window.apply_meter(fight())
    assert window.empty.text() == "No recorded healing in this combat."
    window.set_metric("dps")
    quiet = fight()
    for player in quiet["snapshot"]["players"]:
        player["damage"] = 0
    quiet["targets"] = ["boss"]
    window.apply_meter(quiet)
    assert window.empty.text() == "No damage to bosses in this combat (Boss damage only)."
    broken = fight()
    broken["error"] = "the capture driver stopped"
    broken["snapshot"]["warning"] = "Your name comes with the next zone load"
    window.apply_meter(broken)
    assert window.status.text() == "Capture stopped: the capture driver stopped"
    assert window.warning.text() == "Your name comes with the next zone load" and len(_rows(window)) == 3


def test_a_click_on_a_player_opens_their_panel_with_tiles_skills_and_buffs(qapp):
    api = FakeApp(fight())
    window = _overlay(api=api)
    window.show()
    assert window.panel_scroll.isHidden()
    QTest.mouseClick(_rows(window)[0], Qt.LeftButton)
    assert window.detail_key == "0" and _rows(window)[0].open
    settle(lambda: window.detail_buffs is not None)
    assert ("GET", "/api/meter/player?view=latest&key=0", None) in api.calls
    panel = window.panel
    assert not window.panel_scroll.isHidden()
    assert (panel.name.text(), panel.sub.text()) == ("Seraphel", "Sorcerer")   # no combat power known for them
    assert panel.line.text() == "Target: Atiel · 1m 15s in combat"
    tiles = panel.reading["tiles"]
    assert [label for label, _value, _title in tiles] == ["Total damage", "DPS", "Contribution", "Combat time", "Hits",
                                                          "Parry", "Crit", "Front", "Back", "Perfect", "Double",
                                                          "Parried in", "Shield blocks", "Endurance"]
    values = panel.tile_values()
    assert (values["Combat time"], values["Hits"], values["Crit"], values["Parry"], values["Contribution"],
            values["Parried in"], values["Shield blocks"], values["Endurance"]) == ("1m 15s", "120", "33%", "5%",
                                                                                    "51%", "4", "3", "2")
    assert (values["DPS"], values["Total damage"]) == ("23.40K/s", "1.75M")
    titles = {label: title for label, _value, title in tiles}
    assert titles["Combat time"] == "Fight time; this player dealt damage in 1m 01s of it"
    assert titles["Endurance"] == "Hits on this player that their Endurance halved"
    skills = [line for line in panel.skill_lines if not line.isHidden()]
    assert [line.texts() for line in skills] == [["FB", "Flame Bolt", "1.05M · 60% · 60× · 40%"],
                                                 ["FS", "Frost Spear", "702.00K · 40% · 40× · 25%"]]
    assert [line.bar.fraction for line in skills] == [1.0, 0.67]              # bars against the top skill
    buffs = [line for line in panel.buff_lines if not line.isHidden()]
    assert [line.texts() for line in buffs] == [["Mo", "Mantra of Flame", "100% · 1m 15s"],
                                                ["P", "Protection", "80% · 1m 00s"]]
    assert buffs[0].toolTip().endswith("applied 1×, by this player") and window.panel_scroll.height() > 100
    window.grab()                                                              # the panel paints
    panel.close_button.click()
    assert window.panel_scroll.isHidden() and window.detail_key is None and not _rows(window)[0].open
    window.toggle_detail("1")                                                  # your own panel says so
    settle(lambda: window.detail_buffs is not None)
    assert (panel.name.text(), panel.sub.text()) == ("Nyxara", "Ranger · CP 123.46K")
    assert panel.line.text() == "Target: Atiel · 1m 15s in combat · you"
    assert panel.buffs_note.text() == "No buff records in this fight yet." and not panel.buffs_note.isHidden()
    window.toggle_detail("1")                                                  # a second click closes it
    assert window.panel_scroll.isHidden()


def test_the_panel_follows_the_fight_and_keeps_to_the_screen(qapp):
    many = {"0": [dict(BUFFS["0"][0], skill=f"Buff {n}") for n in range(14)]}
    api = FakeApp(fight(), buffs=many)
    window = _overlay(api=api)
    window.show()
    window.toggle_detail("2")
    settle(lambda: window.detail_buffs is not None)
    gone = fight()
    gone["snapshot"]["players"] = gone["snapshot"]["players"][:2]
    window.apply_meter(gone)
    assert (window.panel.name.text(), window.panel.line.text()) == ("Player",
                                                                    "This player is no longer in the live view.")
    assert all(tile.isHidden() for tile in window.panel.tiles) and window.panel.buffs_head.isHidden()
    busy = fight()
    seraphel = busy["snapshot"]["players"][0]
    seraphel["skills"] = [dict(seraphel["skills"][0], skill=f"Skill {n}", damage=1000 * (12 - n)) for n in range(12)]
    window.apply_meter(busy)
    window.toggle_detail("0")
    settle(lambda: window.detail_buffs is not None)
    shown = [line for line in window.panel.skill_lines if not line.isHidden()]
    assert len(shown) == 8 and len([line for line in window.panel.buff_lines if not line.isHidden()]) == 10
    room = min(800, window.screen().availableGeometry().height() - 16)
    content = window.panel.sizeHint().height()
    assert content > room - 200                                                # taller than the screen leaves it
    assert window.panel_scroll.height() < content and window.sizeHint().height() <= room   # it scrolls instead
    over = fight()
    over["snapshot"]["battle_over"] = True
    window.apply_meter(over)
    assert window.panel_scroll.isHidden()                                      # a finished fight puts it away


def test_a_press_that_moves_the_window_is_a_move_not_a_click(qapp):
    window = _overlay()
    window.show()
    row = _rows(window)[0]
    QTest.mousePress(row, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
    QTest.mouseRelease(row, Qt.LeftButton, Qt.NoModifier, QPoint(40, 10))
    assert window.detail_key is None
    QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
    assert window.detail_key == "0"
