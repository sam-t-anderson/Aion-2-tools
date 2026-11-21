"""The native Pet Tracker page (0.2.431): Pet Tracker's head, its pets of the moment, the farming session and the
collection, as the web page shows them (pages/pets.js and ``A2Pets`` in static/pet-tracker.js), off screen. Pet
Tracker's state is the app's own (``pettracker.render`` of a worker's view), and the controls change that view as Pet
Tracker would.
"""
import io
import json
import os
import struct
import sys
import urllib.error
import zlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QPushButton, QTableWidget  # noqa: E402

from aion2calc.app import pettracker as pt  # noqa: E402
from aion2calc.gui import pets_page as p  # noqa: E402
from aion2calc.gui.pets_page import PetsPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402
from test_pettracker import ACCOUNT, KEY, NOW, _view  # noqa: E402

INSTALLED = {"kind": "installer", "folder": "C:\\Program Files\\PetTracker", "version": "0.1.58"}
#: What the app says of Pet Tracker beside its worker's view (``Service.state``): installed, on, connected.
BASE = {"supported": True, "enabled": True, "source": pt.SOURCE_URL, "installed": INSTALLED,
        "setup": {"supported": True, "status": "idle", "version": None, "error": None},
        "running": {"app": False, "worker": True}, "connected": True, "problem": "", "start": "",
        "update": {"available": False, "latest": "0.1.58", "installed": "0.1.58", "kind": "installer", "checked": 1,
                   "error": ""}}
NEWER = {"available": True, "latest": "0.1.60", "installed": "0.1.58", "kind": "installer", "checked": 1, "error": ""}
UPDATING = "Pet Tracker is open: its updater installs Pet Tracker 0.1.60."


def _png(rgb=(220, 40, 40), size=4) -> bytes:
    """A small PNG of one colour, a pet's portrait as the app serves it."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


PORTRAIT = _png()


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


def _refused(path, words):
    return urllib.error.HTTPError(path, 400, "Bad Request", None, io.BytesIO(json.dumps({"error": words}).encode()))


class FakeApp:
    """The app as the page asks it: Pet Tracker's state and collection worked out by the app's own rules from a
    worker's view, its controls applied to that view as Pet Tracker applies them, and the app's settings."""

    def __init__(self, view=None, base=None, ui=None, fail=(), refuse=None, missing=(1005,)):
        self.view = view if view is not None else _view()
        self.base = {**BASE, **(base or {})}
        self.ui = {"pettracker_enabled": True, "pettracker_overlay": True, "pettracker_overlay_style": "app", **(ui or {})}
        self.fail, self.refuse, self.missing = set(fail), refuse, set(missing)
        self.calls, self.posts = [], []

    def state(self, collection=False):
        out = dict(self.base)
        if out["connected"]:
            out.update(pt.render(self.view, NOW, collection))
        return out

    def get(self, path):
        self.calls.append(path)
        if path in self.fail:
            raise OSError("the app did not answer")
        if path == "/api/ui":
            return dict(self.ui)
        if path == "/api/pettracker":
            return self.state()
        assert path == "/api/pettracker?collection=1"
        return self.state(collection=True)

    def get_bytes(self, path):
        self.calls.append(path)
        assert path.startswith("/api/pettracker/portrait/") and path.endswith(".png")
        if int(path.rsplit("/", 1)[1][:-4]) in self.missing:
            raise _refused(path, "no portrait")
        return PORTRAIT

    def post(self, path, body):
        self.posts.append((path, body))
        if path == "/api/ui":
            if "ui" in self.fail:
                raise OSError("the settings could not be saved")
            self.ui.update(body)
            return dict(self.ui)
        assert path == "/api/pettracker"
        if self.refuse:
            raise _refused(path, self.refuse)
        settings, action = self.view["Settings"], body["action"]
        if action == "mode":
            settings["TrackerMode"] = body["value"]
        elif action == "hide_maxed":
            settings["HideMaxed"] = body["value"]
        elif action == "pin":
            pins = settings["PinnedPetIds"]
            pins.append(body["pet"]) if body["value"] else pins.remove(body["pet"])
        elif action == "goal":
            self.view["Profile"]["Pets"][str(body["pet"])]["TargetRank"] = body["rank"]
        elif action == "reset_session":
            self.view["Farming"]["Pets"] = []
        elif action == "open":
            self.base["running"] = {"app": True, "worker": True}
        elif action == "install":
            self.base["setup"] = {"supported": True, "status": "downloading", "version": "0.1.58", "error": None}
        elif action == "link":
            self.view.update(Ready=True, Status="Live")
        out = self.state()
        if action == "update":
            out["message"] = UPDATING
        return out


def _page(api=None, width=1100, **kwargs):
    page = PetsPage(api if api is not None else FakeApp(), **kwargs)
    page.resize(width, 1600)
    page.show()
    settle(lambda: page.state is not None and page.collection is not None)
    QCoreApplication.processEvents()
    return page


def _shown(widget, kind):
    """The widgets of a kind shown in ``widget``: a part drawn anew is shown on Qt's next turn, so that turn first."""
    QCoreApplication.processEvents()
    return [child for child in widget.findChildren(kind) if child.isVisibleTo(widget)]


def _texts(widget):
    return [label.text() for label in _shown(widget, QLabel)]


def _button(page, words):
    return next((button for button in _shown(page, QPushButton) if button.text() == words), None)


def _check(page, words):
    return next((box for box in _shown(page, QCheckBox) if box.text() == words), None)


def _combo(page, name):
    return next((box for box in _shown(page, QComboBox) if box.accessibleName() == name), None)


def _names(page):
    return [item.pet.name.text() for item in page.grid.items]


def _waiting_to_link(**overrides):
    return _view(**{"Ready": False, "Status": "Alt — link to account", "Detail": "Selected account: Main account.",
                    "DetectedCharacter": "Alt", "Profiles": [ACCOUNT], "Selected": KEY, **overrides})


def test_the_words_are_the_web_pages():
    live = FakeApp().state()
    assert p.status_line(None) == ("Loading Pet Tracker…", "wait", "")
    assert p.status_line({"supported": False}) == ("Pet Tracker runs on Windows only.", "off", "")
    assert p.status_line({"supported": True})[:2] == ("Pet Tracker is not installed. Install it under Settings → Pet Tracker.",
                                                      "off")
    assert p.status_line({**BASE, "enabled": False})[:2] == ("Pet Tracker is off. Turn it on under Settings → Pet Tracker.",
                                                             "off")
    assert p.status_line({**BASE, "connected": False}) == ("Starting Pet Tracker's capture…", "wait", "")
    assert p.status_line({**BASE, "connected": False, "problem": "Pet Tracker's capture stopped.", "start": "stopped"}) == \
        ("Pet Tracker's capture stopped.", "off", "")
    assert p.status_line(live) == ("Ranger · Live", "ok", "Receiving soul updates.")
    assert p.status_line({**live, "status": "Collection sync needed", "character": ""})[:2] == ("Collection sync needed", "wait")
    linking = FakeApp(_waiting_to_link()).state()
    assert p.status_line(linking) == ("Alt is not linked to Main account", "wait", "Selected account: Main account.")
    # the install
    assert p.setup_text(None) == p.setup_text({"status": "idle"}) == ""
    assert p.setup_text({"status": "downloading", "version": "0.1.58"}) == "Downloading Pet Tracker 0.1.58…"
    assert p.setup_text({"status": "downloading"}) == "Downloading Pet Tracker…"
    assert p.setup_text({"status": "started"}) == "Pet Tracker's installer is running; this page notices when it finishes."
    assert p.setup_text({"status": "error", "error": "The download did not match its release."}) == \
        "The download did not match its release."
    assert p.setup_text({"status": "error"}) == "Pet Tracker could not be installed."
    assert p.installing({"setup": {"status": "installing"}}) and not p.installing({"setup": {"status": "started"}})
    # a newer Pet Tracker
    assert p.update_notice({}) is None and p.update_notice(live) is None
    assert p.update_notice({"update": NEWER}) == ("Pet Tracker 0.1.60 is available (you have 0.1.58).", "Update Pet Tracker", "")
    assert p.update_notice({"update": {**NEWER, "kind": "offline"}})[1] == "Install Pet Tracker 0.1.60"
    assert p.update_notice({"update": {**NEWER, "kind": "custom"}, "source": pt.SOURCE_URL})[1:] == \
        ("", "https://github.com/0Fox2Give/PetTracker/releases")
    # a pet
    assert p.accent(None) == p.accent({"options": {"accent": "Purple"}}) == "#d9b24c"
    assert p.accent({"options": {"accent": "Teal"}}) == "#53c9b5"
    rows = {row["id"]: row for row in live["rows"]}
    kept = {row["id"]: row for row in FakeApp().state(collection=True)["collection"]}
    assert p.row_tip(rows[1003]) == "From Wisp · 2 souls to the next rank"
    assert p.row_tip(kept[1004]) == "15 souls to the next rank · 90 souls to Rank 3"
    assert p.row_tip({"remaining": 1, "estimated": True}) == "1 soul to the next rank · Estimated while totals sync"
    assert p.progress_text(rows[1003]) == "3 / 5" and p.progress_text(rows[1002]) == "✓ MAX"
    assert p.progress_text({"progress": "74 / 75", "estimated": True}) == "≈74 / 75"
    assert (p.bar_ratio(rows[1003]), p.bar_ratio({"ratio": 0.125}), p.bar_ratio({"ratio": 0.124})) == (0.6, 0.13, 0.12)
    assert p.bar_ratio({}) == 0 and p.bar_ratio({"ratio": 1.5}) == 1 and p.bar_ratio({"ratio": "?"}) == 0
    assert p.link_words(linking["link"]) == (
        "Alt is not one of the characters of your Pet Tracker account Main account (Ranger, Healer). Pet collections are "
        "shared across an account, so Pet Tracker waits until this character is linked to it.")
    # the collection
    collection = FakeApp().state(collection=True)

    def names(*filters):
        return [row["name"] for row in p.collection_rows(collection, *filters)]
    assert names() == ["Black Dragon", "Forest Specter", "Fossa", "Klaw", "Krall Laborer"]       # as Pet Tracker lists them
    assert names(" FO ") == ["Forest Specter", "Fossa"] and names("", "Fera") == ["Fossa"]
    assert names("", "", "0") == ["Forest Specter"] and names("", "", "1") == ["Fossa", "Klaw"]
    assert names("", "", "3") == ["Krall Laborer"] and names("", "", "unknown") == []
    assert names("", "", "hide") == ["Black Dragon", "Forest Specter", "Fossa", "Klaw"]
    assert names("", "", "all", "closest") == ["Forest Specter", "Black Dragon", "Klaw", "Fossa", "Krall Laborer"]
    assert p.collection_rows(None) == [] and p.rank_matches({"rank": None}, "unknown")
    assert p.summary_parts(collection["summary"]) == [("Pets", "5"), ("Collected", "4"), ("Maxed", "1"), ("Rank unknown", "0")]
    assert p.summary_parts(None) == []
    assert p.session_line(collection["session"]) == "<b>8</b> souls · <b>1</b> pet ranked up"
    interrupted = p.session_line({"souls": 1, "ranked": 2, "incomplete": True})
    assert interrupted.startswith("<b>1</b> soul · <b>2</b> pets ranked up <span")
    assert interrupted.endswith("· some rewards may be missing: capture was interrupted</span>")


def test_the_page_asks_nothing_until_shown_then_draws_pet_tracker(qapp):
    app, opened = FakeApp(), []
    page = PetsPage(app, open_link=opened.append)
    assert app.calls == []
    page.resize(1100, 1600)
    page.show()
    settle(lambda: page.collection is not None)
    QCoreApplication.processEvents()
    assert app.calls[:3] == ["/api/ui", "/api/pettracker", "/api/pettracker?collection=1"]
    texts = _texts(page.window_)
    # Pet Tracker
    assert "<b>Pet Tracker 0.1.58</b>" in texts and "C:\\Program Files\\PetTracker" in texts
    assert _check(page, "Use Pet Tracker with Aion 2 Calc").isChecked()
    overlay, style = _check(page, "Show the Pet Tracker overlay"), _combo(page, "Which window")
    assert overlay.isChecked() and overlay.isEnabled() and style.currentData() == "app" and style.isEnabled()
    status = page.findChild(QLabel, "ptstatus")
    assert (status.text(), status.toolTip()) == ("Ranger · Live", "Receiving soul updates.") and "#76c59d" in status.styleSheet()
    opener = _button(page, "Open Pet Tracker")
    assert opener.isEnabled() and opener.toolTip() == p.OPEN_TIP and not page.note.isVisible()
    # Now
    assert page.modes.chosen == "Recent" and page.modes.buttons["Recent"].objectName() == "segFirstOn"
    assert page.modes.buttons["Nearby"].objectName() == "segLast" and page.modes.buttons["Nearby"].isEnabled()
    assert page.hide_maxed.isEnabled() and not page.hide_maxed.isChecked()
    assert not page.sync.isVisible()
    assert [row.name.text() for row in page.live_rows] == ["Forest Specter", "Klaw", "Krall Laborer"]
    specter, klaw, krall = page.live_rows
    assert (specter.rank.text(), specter.progress.text(), specter.family.text()) == ("Unranked", "3 / 5", "Natura")
    assert specter.toolTip() == "From Wisp · 2 souls to the next rank" and specter.picture.isVisibleTo(specter)
    assert specter.bar.isVisibleTo(specter) and (specter.bar.ratio, specter.bar.colour) == (0.6, "#d9b24c")
    tint = specter.family.palette().color(specter.family.foregroundRole())
    assert specter.family.objectName() == "famNatura" and (tint.red(), tint.green(), tint.blue()) == (127, 211, 138)
    assert (specter.pin.text(), specter.pin.toolTip()) == ("☆", "Pin this pet to the top")
    assert (klaw.family.text(), klaw.bar.ratio, klaw.name.objectName()) == ("Varian", 0.8, "ptname")
    assert (krall.progress.text(), krall.name.objectName(), krall.progress.objectName()) == ("✓ MAX", "ptnameMax", "ptprogMax")
    assert not krall.bar.isVisibleTo(krall) and not krall.notice.isVisibleTo(krall)
    # This session
    assert "<b>8</b> souls · <b>1</b> pet ranked up" in texts
    session = next(widget for widget in page.findChildren(QTableWidget) if widget.isVisibleTo(page))
    assert [session.horizontalHeaderItem(c).text() for c in range(3)] == ["Pet", "Souls", "Rank ups"]
    assert [[session.item(r, c).text() for c in range(3)] for r in range(session.rowCount())] == \
        [["Forest Specter", "3", "0"], ["Fossa", "5", "1"]]
    assert _button(page, "Reset session")
    # Collection
    summary = [page.summary.itemAt(i).widget().text() for i in range(page.summary.count())]
    assert [text.split(" <b")[0] for text in summary] == ["Pets", "Collected", "Maxed", "Rank unknown"]
    assert [text.split(">")[1].split("<")[0] for text in summary] == ["5", "4", "1", "0"]
    assert _names(page) == ["Black Dragon", "Forest Specter", "Fossa", "Klaw", "Krall Laborer"]
    fossa = page.grid.items[2]
    assert (fossa.choice.currentData(), fossa.goal.text(), fossa.pet.progress.text()) == ("3", "90 souls to Rank 3", "10 / 25")
    assert page.grid.items[0].choice.currentText() == "No goal" and page.grid.columns == 2
    assert [page.grid.grid.getItemPosition(page.grid.grid.indexOf(item))[:2] for item in page.grid.items] == \
        [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
    # the attribution, its link opened in the browser
    attribution = next(label for label in page.findChildren(QLabel) if "separate program by 0Fox2Give" in label.text())
    assert f"href='{p.SOURCE}'" in attribution.text() and "can put your game account at risk." in attribution.text()
    attribution.linkActivated.emit(p.SOURCE)
    assert opened == ["https://github.com/0Fox2Give/PetTracker"]
    assert not app.posts                                                                   # drawing sends nothing


def test_the_portraits_are_read_once_each_and_one_the_app_has_not_is_left_out(qapp):
    app = FakeApp()
    page = _page(app)
    pets = page._pets()
    settle(lambda: all(row.picture.pixmap is not None or row.picture.none for row in pets if row.isVisibleTo(page)))
    asked = [call for call in app.calls if call.startswith("/api/pettracker/portrait/")]
    assert sorted(asked) == [f"/api/pettracker/portrait/{pet}.png" for pet in (1001, 1002, 1003, 1004, 1005)]
    specter, klaw = page.live_rows[:2]
    assert specter.picture.pixmap is not None and not specter.picture.none
    assert klaw.picture.none and klaw.picture.pixmap is None                               # the app has no portrait of 1005
    picture = specter.grab().toImage().pixelColor(specter.picture.geometry().center())
    assert picture.red() > 180 and picture.green() < 80                                    # drawn, covering its square
    page.read_state()
    count = len(app.calls)
    settle(lambda: len(app.calls) > count)
    QCoreApplication.processEvents()
    assert [call for call in app.calls if call.startswith("/api/pettracker/portrait/")] == asked    # each read once


def test_the_rows_follow_pet_trackers_own_settings(qapp):
    view = _view(PinnedPetIds=[1004])
    view["Settings"].update(Accent="Blue", Portraits=False, ProgressBars=False)
    page = _page(FakeApp(view))
    fossa = page.live_rows[0]                                                              # a pin leads
    assert (fossa.name.text(), fossa.notice.text(), fossa.pin.text()) == ("Fossa", "Pinned", "★")
    tint = fossa.pin.palette().color(fossa.pin.foregroundRole())
    assert fossa.pin.objectName() == "ptpinBlue" and tint.name() == "#60b1ec"
    assert fossa.pin.toolTip() == "Unpin this pet" and fossa.notice.isVisibleTo(fossa)
    assert not any(row.picture.isVisibleTo(row) or row.bar.isVisibleTo(row) for row in page.live_rows)
    kept = next(item for item in page.grid.items if item.pet.row["id"] == 1004)
    assert kept.pet.picture.isVisibleTo(kept) and kept.pet.bar.isVisibleTo(kept)            # the collection shows both
    assert kept.pet.bar.colour == "#60b1ec"
    paused = _page(FakeApp(_view(CollectionSynced=False, Status="Collection sync needed")))
    assert paused.sync.isVisibleTo(paused) and paused.sync.text() == p.SYNC_NOTE
    assert all(row.bar.colour == p.PAUSED for row in paused.live_rows if not row.row["max"])
    assert paused.findChild(QLabel, "ptstatus").text() == "Ranger · Collection sync needed"


def test_the_controls_are_sent_as_the_web_page_sends_them(qapp):
    app = FakeApp()
    page = _page(app)

    def sent(body):
        settle(lambda: app.posts and app.posts[-1] == ("/api/pettracker", body))
        count = len(app.calls)
        settle(lambda: "/api/pettracker?collection=1" in app.calls[count - 1:])         # the collection read again
    page.modes.buttons["Nearby"].click()
    assert page.modes.chosen == "Recent"                                                   # until Pet Tracker answers
    sent({"action": "mode", "value": "Nearby"})
    settle(lambda: page.modes.chosen == "Nearby")
    assert page.modes.buttons["Nearby"].objectName() == "segLastOn" and page.modes.buttons["Recent"].objectName() == "segFirst"
    page.modes.buttons["Recent"].click()
    sent({"action": "mode", "value": "Recent"})
    page.hide_maxed.click()
    sent({"action": "hide_maxed", "value": True})
    settle(lambda: [row.name.text() for row in page.live_rows] == ["Forest Specter", "Klaw"])
    page.hide_maxed.click()
    sent({"action": "hide_maxed", "value": False})
    settle(lambda: len(page.live_rows) == 3)
    page.live_rows[0].pin.click()
    sent({"action": "pin", "pet": 1003, "value": True})
    settle(lambda: page.live_rows[0].pin.text() == "★")
    assert page.live_rows[0].notice.text() == "Pinned"
    page.live_rows[0].pin.click()
    sent({"action": "pin", "pet": 1003, "value": False})
    klaw = next(item for item in page.grid.items if item.pet.row["id"] == 1005)
    klaw.choice.setCurrentIndex(2)
    klaw.choice.activated.emit(2)
    sent({"action": "goal", "pet": 1005, "rank": 2})
    settle(lambda: klaw.pet.row.get("goal_rank") == 2)
    assert klaw.choice.currentData() == "2" and klaw.goal.text() and klaw in page.grid.items     # the same pet, drawn anew
    klaw.choice.setCurrentIndex(0)
    klaw.choice.activated.emit(0)
    sent({"action": "goal", "pet": 1005, "rank": None})
    _button(page, "Reset session").click()
    sent({"action": "reset_session"})
    settle(lambda: "No soul rewards yet this session." in _texts(page.window_))
    _button(page, "Open Pet Tracker").click()
    sent({"action": "open"})
    settle(lambda: any(b.text() == "Pet Tracker is running (tray icon)" for b in page.findChildren(QPushButton)))
    running = _button(page, "Pet Tracker is running (tray icon)")
    assert not running.isEnabled() and running.toolTip() == p.RUNNING_TIP


def test_a_refused_control_says_why_beside_the_tools_for_four_seconds(qapp):
    app = FakeApp(refuse="Pin limit reached. Unpin a pet first.")
    page = _page(app)
    page.live_rows[0].pin.click()
    settle(lambda: page.message.text())
    assert page.message.text() == "Pin limit reached. Unpin a pet first."
    assert page.quiet.isActive() and page.quiet.interval() == 4000
    assert page.live_rows[0].pin.text() == "☆"                                             # nothing changed
    page.quiet.stop()
    page.quiet.timeout.emit()
    assert page.message.text() == ""


def test_the_apps_pet_tracker_settings_are_saved_as_the_web_page_saves_them(qapp):
    app = FakeApp()
    page = _page(app)
    _check(page, "Show the Pet Tracker overlay").click()
    settle(lambda: page.toast.isVisible())
    assert app.posts[-1] == ("/api/ui", {"pettracker_overlay": False}) and page.ui["pettracker_overlay"] is False
    assert page.toast.text() == "Saved" and page.toast.timer.interval() == 4000
    assert not _check(page, "Show the Pet Tracker overlay").isChecked()
    count = app.calls.count("/api/pettracker")
    settle(lambda: app.calls.count("/api/pettracker") > count)                            # read again 600 ms later
    style = _combo(page, "Which window")
    style.setCurrentIndex(1)
    style.activated.emit(1)
    settle(lambda: app.posts[-1] == ("/api/ui", {"pettracker_overlay_style": "pettracker"}))
    settle(lambda: getattr(_combo(page, "Which window"), "currentData", lambda: None)() == "pettracker")
    _check(page, "Use Pet Tracker with Aion 2 Calc").click()
    settle(lambda: app.posts[-1] == ("/api/ui", {"pettracker_enabled": False}))
    app.fail.add("ui")
    _check(page, "Show the Pet Tracker overlay").click()
    settle(lambda: page.message.text())
    assert page.message.text() == "the settings could not be saved" and page.ui["pettracker_overlay"] is False


def test_pet_tracker_not_installed_offers_its_install(qapp):
    app = FakeApp(base={"installed": None, "enabled": False, "connected": False})
    page = _page(app)
    texts = _texts(page.window_)
    assert "Pet Tracker is not installed on this computer." in texts and p.INSTALL_NOTE in texts
    install = _button(page, "Install Pet Tracker")
    assert install.isEnabled() and install.objectName() == "primary"
    assert "Pet Tracker is not installed. Install it under Settings → Pet Tracker." in texts      # Now
    assert "Pet Tracker's farming session shows here once it is connected." in texts
    assert "Your collection shows here once Pet Tracker is connected." in texts and not page.grid.isVisibleTo(page)
    assert not page.modes.buttons["Recent"].isEnabled() and not page.hide_maxed.isEnabled()
    assert page.findChild(QLabel, "ptstatus") is None                                    # no status line before it is installed
    assert not page.summary.count()
    install.click()
    settle(lambda: app.posts)
    assert app.posts[-1] == ("/api/pettracker", {"action": "install"})
    settle(lambda: "Downloading Pet Tracker 0.1.58…" in _texts(page.window_))
    assert not _button(page, "Install Pet Tracker").isEnabled()
    windows = _page(FakeApp(base={"supported": False, "installed": None, "enabled": False, "connected": False}))
    note = next(label for label in windows.findChildren(QLabel) if label.text() == "Pet Tracker runs on Windows only."
                and label.objectName() == "note")
    assert note.isVisibleTo(windows) and not any(b.text() == "Install Pet Tracker" for b in windows.findChildren(QPushButton))


def test_a_newer_pet_tracker_is_offered(qapp):
    app = FakeApp(base={"update": NEWER})
    page = _page(app)
    assert "Pet Tracker 0.1.60 is available (you have 0.1.58)." in _texts(page.window_)
    _button(page, "Update Pet Tracker").click()
    settle(lambda: page.note.isVisible())
    assert app.posts[-1] == ("/api/pettracker", {"action": "update"}) and page.note.text() == UPDATING
    assert _button(_page(FakeApp(base={"update": {**NEWER, "kind": "offline"}})), "Install Pet Tracker 0.1.60")
    opened = []
    custom = _page(FakeApp(base={"update": {**NEWER, "kind": "custom"}}), open_link=opened.append)
    releases = next(label for label in custom.findChildren(QLabel) if "Download it from Pet Tracker's releases" in label.text())
    assert "href='https://github.com/0Fox2Give/PetTracker/releases'" in releases.text()
    releases.linkActivated.emit("https://github.com/0Fox2Give/PetTracker/releases")
    assert opened == ["https://github.com/0Fox2Give/PetTracker/releases"]
    refused = _page(FakeApp(base={"update": NEWER}, refuse="Pet Tracker could not be opened."))
    _button(refused, "Update Pet Tracker").click()
    settle(lambda: refused.note.isVisible())
    assert refused.note.text() == "Pet Tracker could not be opened." and not refused.message.text()


def test_a_character_to_link_and_what_now_says_without_pets(qapp):
    app = FakeApp(_waiting_to_link())
    page = _page(app)
    assert p.link_words(app.state()["link"]) in _texts(page.window_)
    status = page.findChild(QLabel, "ptstatus")
    assert status.text() == "Alt is not linked to Main account"
    link = _button(page, "Link Alt to Main account")
    assert "#d9b24c" in link.styleSheet()
    link.click()
    assert not link.isEnabled()
    settle(lambda: app.posts)
    assert app.posts[-1] == ("/api/pettracker", {"action": "link", "character": "Alt"})
    settle(lambda: len(page.live_rows) == 3)                                              # linked: its pets
    assert page.findChild(QLabel, "ptstatus") is status and status.text() == "Ranger · Live"   # drawn anew in place
    second = dict(ACCOUNT, ProfileKey="f" * 24, AccountName="Second")
    several = _page(FakeApp(_waiting_to_link(Profiles=[ACCOUNT, second])))
    assert p.MANAGE in _texts(several.window_)
    assert not [button for button in several.findChildren(QPushButton) if button.text().startswith("Link ")]
    quiet = _page(FakeApp(_view(Recent=[])))
    assert "Recent pet rewards will appear here." in _texts(quiet.window_) and not quiet.live_rows
    starting = _page(FakeApp(base={"connected": False, "problem": "Pet Tracker's capture could not start.", "start": "failed"}))
    status = starting.findChild(QLabel, "ptstatus")
    assert status.text() == "Pet Tracker's capture could not start." and "#e9a4b6" in status.styleSheet()
    assert _texts(starting.window_).count("Pet Tracker's capture could not start.") == 2       # the head and Now


def test_the_collection_is_filtered_and_its_pets_kept_between_draws(qapp):
    app = FakeApp()
    page = _page(app)
    first = {item.pet.row["id"]: item for item in page.grid.items}
    page.search.setText("fo")
    assert _names(page) == ["Forest Specter", "Fossa"] and page.grid.items[0] is first[1003]
    assert not first[1001].isVisibleTo(page) and first[1003].isVisibleTo(page)
    page.search.setText("")
    page.family.setCurrentIndex(page.family.findData("Fera"))
    assert _names(page) == ["Fossa"]
    page.family.setCurrentIndex(0)
    page.rank.setCurrentIndex(page.rank.findData("hide"))
    assert _names(page) == ["Black Dragon", "Forest Specter", "Fossa", "Klaw"]
    page.rank.setCurrentIndex(page.rank.findData("unknown"))
    assert page.empty.isVisibleTo(page) and page.empty.text() == "No pet matches." and not page.grid.isVisibleTo(page)
    page.rank.setCurrentIndex(0)
    page.sort.setCurrentIndex(page.sort.findData("closest"))
    assert _names(page) == ["Forest Specter", "Black Dragon", "Klaw", "Fossa", "Krall Laborer"]
    assert page.grid.isVisibleTo(page) and not page.empty.isVisibleTo(page)
    assert [item.pet.row["id"] for item in page.grid.items] == [1003, 1001, 1005, 1004, 1002]
    app.view["Profile"]["Pets"]["1005"]["Souls"] = 24
    page.read_collection()
    settle(lambda: first[1005].pet.progress.text() == "24 / 25")
    assert first[1005] in page.grid.items and set(page.items.values()) == set(first.values())


def test_the_page_reads_pet_tracker_only_while_shown(qapp):
    page = _page()
    assert page.poll.isActive() and page.poll.interval() == 1500
    assert page.poll_collection.isActive() and page.poll_collection.interval() == 10000
    page.hide()
    assert not page.poll.isActive() and not page.poll_collection.isActive()
    assert _page(FakeApp(base={"connected": False})).poll.interval() == 3000
    failing = FakeApp(fail={"/api/pettracker"})
    page = PetsPage(failing)
    page.show()
    settle(lambda: page.poll.isActive() and page.collection is not None)
    assert page.state is None and page.poll.interval() == 3000                            # the next read tries again
    assert "Loading Pet Tracker…" in _texts(page.window_) and not page.grid.items         # nothing until Pet Tracker answers


def test_the_window_draws_pet_tracker_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("pets"), PetsPage) and not isinstance(window.page("pets"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                                        # not moved over yet
