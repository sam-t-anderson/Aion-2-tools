"""The native Live Meter page (0.2.471): the capture and its actions, Advanced capture's part that Start reads, the
view's choices, the capture's state and the fight, as pages/meter.js draws them. The page reads the app through its
local API, so it is tested on a made-up app (``FakeApp``) answering each request as the app would, off screen; the
fight is made up too. ``live_meter`` holds the words and figures, tested first without Qt."""
import io
import json
import os
import sys
import threading
import time
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget  # noqa: E402

from aion2calc.gui import live_meter as lm  # noqa: E402
from aion2calc.gui.api import AppApi, Poller, Requests  # noqa: E402
from aion2calc.gui.combat_analysis_page import ParseCard  # noqa: E402
from aion2calc.gui.meter_page import Details, MeterPage, PlayerRow  # noqa: E402
from aion2calc.gui.pictures import Pictures  # noqa: E402
from aion2calc.gui.result_windows import GridTable  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402


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


# ------------------------------------------------------------------ a made-up fight
def _player(i, name, cls, dps, share, server=None, **extra):
    row = {"id": str(10 + i), "key": str(10 + i), "name": name, "class": cls, "dps": dps, "damage": dps * 75, "share": share,
           "hits": 100 + i, "crit": 0.3, "back": 0.2, "front": 0.5, "parry": 0.01, "double": 0.1, "perfect": 0.05,
           "multi": 0.02, "healing": 0, "incoming": {"damage": 4000, "hits": 9, "parries": 4, "shield_blocks": 3, "endurance": 2},
           "skills": [{"skill": "Test Strike", "skill_id": 11000000, "hits": 60, "damage": dps * 45, "share": 0.6, "min": 900},
                      {"skill": "Test Burst", "skill_id": 11010000, "hits": 40, "damage": dps * 30, "share": 0.4}], **extra}
    if server:
        row["server_name"] = server
    return row


def _fight(**snap):
    players = [_player(0, "Testsorc", "sorcerer", 23405, 0.51, "Zikel"), _player(1, "Testranger", "ranger", 15600.5, 0.34),
               _player(2, "Testcleric", "cleric", 6700, 0.15, "Ariel")]
    snapshot = {"players": players, "duration": 75.4, "dps": 45705.5, "boss": "Testlord", "scope": "party",
                "selection_mode": "latest", "selected_segment": "",
                "segments": [{"id": "s1", "label": "Combat 1", "start": 1763763200000, "duration": 61.25},
                             {"id": "s2", "label": "Testlord", "start": "2026-11-21T22:15:00Z", "duration": 75.4}],
                "ping": {"current": 42, "avg": 45.5, "min": 30, "max": 88, "samples": 120},
                "odyle": {"regular": 1200, "bonus": 300}, "shugo_keys": {"regular": 3, "bonus": 0},
                "nightmare_tickets": {"regular": 9, "bonus": 2},
                "weekly_runs": {"regular": 3, "bonus": 1, "zone": "Test Isle", "difficulty": "hard"},
                "enemies": [{"key": "boss:1", "name": "Testlord", "damage": 3200000, "dps": 42666.6},
                            {"key": "add:2", "name": "Test Shade", "damage": 230000, "dps": 3066}],
                "selected_enemy": "boss:1", **snap}
    return {"running": True, "source": "a2tools", "snapshot": snapshot,
            "diagnostics": {"packets": 1200, "decoded_events": 34, "port": 50349},
            "identity": {"id": 31, "name": "Testsorc", "verified": True, "serverId": 2102},
            "run": {"id": 4, "closed": False}}


IDLE = {"running": False, "snapshot": {"players": []}}


# ------------------------------------------------------------------ the words and figures
def test_the_capture_state_words():
    d = {"packets": 1200, "decoded_events": 34, "port": 50349}
    assert lm.status_text({"running": True, "diagnostics": d}) == "Recording · 1200 TCP packets · 34 combat events · port 50349"
    assert lm.status_text({"running": True, "diagnostics": {"auto_port": True}, "snapshot": {"paused": True}}) == \
        "Paused DPS · capture continues · 0 TCP packets · 0 combat events · detecting game port"
    assert lm.status_text({"running": True, "diagnostics": {"packets": 5, "tcp_stream_resets": 2, "pcap_if_dropped": 1}}) == (
        "Recording · 5 TCP packets · 0 combat events · 2 lossy TCP recovery boundaries (capture incomplete) · Capture "
        "drops detected; data may be incomplete (see diagnostics)")
    assert lm.status_text({"running": True, "diagnostics": {"state": "stopping"}}) == \
        "Stopping capture · decoding queued payloads before saving…"
    assert lm.status_text({"finalizing": True, "running": True}) == "Saving stopped capture and diagnostics…"
    assert lm.status_text({"running": False}) == "Stopped" and lm.status_text({"error": "no permission"}) == "no permission"
    assert lm.run_text({}) is None                                          # the line stays as it was
    assert lm.run_text({"run": {"id": 4, "closed": False}}) == "Run 4 · recording"
    assert lm.run_text({"run": {"id": 5.0, "closed": True, "end_reason": "map change"}}) == \
        "Run 5 · finished/boundary recorded; waiting for next fight · map change"
    who = {"identity": {"id": 31, "name": "Testsorc", "verified": True, "serverId": 2102}}
    assert lm.identity_text(who) == "Detected automatically: Testsorc · Zikel · combat entity #31 (changes between instances)"
    who["automatic_metadata"] = {"server_name": "Testworld"}                  # the region's own name for it first
    assert lm.identity_text(who).startswith("Detected automatically: Testsorc · Testworld · ")
    assert lm.identity_text({"identity": {"id": 7, "serverId": 9999}}).startswith(
        "Matched name override: Player #7 · server 9999 · combat entity #7")
    status = {"snapshot": {"identity_status": {"self_identified": False, "unnamed_actors": 2, "linked_pets": 0}}}
    assert lm.identity_text(status) == (
        "Auto-detecting your character. Start before entering an instance, or set a name override under Advanced capture. "
        "Selected combat: Self identity not received · 2 unnamed actors · 0 linked pets. Unknown actors remain separate "
        "until identity/owner links arrive.")
    assert lm.saved_text({}) == "Current part checkpoints every 15 seconds and saves on Stop."
    assert lm.saved_text({"saved_log": "C:/logs/a.a2log", "diagnostics": {"archive_parts_saved": 2}}) == (
        "2 earlier archive part(s) saved in Combat Logs. Upload combines every part into one recording; live view and "
        "export show the current part. Latest saved part: C:/logs/a.a2log")
    assert lm.saved_text({"saved_log": "x", "diagnostics": {"log_save_error": "disk full"}}) == "disk full"
    assert lm.stop_words({"saved_log": "C:/s.a2log"}) == "Capture stopped. Session saved to C:/s.a2log"
    assert lm.stop_words({"diagnostics": {"log_save_error": "disk full"}}) == "Capture stopped, but log saving failed: disk full"
    assert lm.stop_words({}) == "Capture stopped. No session file was saved; check Combat Logs and capture diagnostics."


def test_the_view_words():
    assert lm.view_state({}) == ("Following latest combat. Overlay always follows the latest encounter.", False)
    assert lm.view_state({"selection_mode": "whole"}) == ("Viewing the whole retained session.", True)
    assert lm.view_state({"selection_mode": "encounter"}) == (
        "This encounter is pinned; select Follow latest combat to follow the next pull.", True)
    assert lm.view_state({"selection_mode": "encounter", "viewing_historical": True})[0] == \
        "Viewing an earlier encounter; capture continues into newer combat."
    snap = _fight()["snapshot"]
    assert lm.segment_options(snap) == [("", "Latest combat"), ("all", "Whole session"),
                                        ("s1", "Combat 1 · 22:13:20 · 61.3s"), ("s2", "Testlord · 22:15:00 · 75.4s")]
    assert lm.segment_options({"segments": [{"id": 3}]})[-1] == ("3", " · — · NaNs")      # as the page writes one it cannot read
    assert lm.segment_chosen(snap, "") == "" and lm.segment_chosen({"selected_segment": "all"}, "") == "all"
    assert lm.segment_chosen({"selected_segment": "all"}, "s2") == "s2"                    # the one pinned
    assert lm.final_boss_ids(" 2001, x, 3002 ,,40.5, ٣") == [2001, 3002]                  # whole numbers alone


def test_the_fight_words():
    s = _fight()
    snap = s["snapshot"]
    assert lm.enemy_rows(snap) == [{"key": "boss:1", "name": "Testlord", "damage": "3.20M", "dps": "42.67K", "chosen": True},
                                   {"key": "add:2", "name": "Test Shade", "damage": "230.00K", "dps": "3.07K", "chosen": False}]
    assert lm.players_sub(snap) == "Testlord · 75s · 45.71K raid DPS"
    assert lm.players_sub({"boss": None, "duration": None}) == "0s · 0 raid DPS"
    rows = lm.player_rows(snap)
    assert [(r["name"], r["server"], r["class"], r["words"]) for r in rows] == [
        ("Testsorc", "Zikel", "Sorcerer", "23.41K/s · 51%"), ("Testranger", "", "Ranger", "15.60K/s · 34%"),
        ("Testcleric", "Ariel", "Cleric", "6.70K/s · 15%")]
    assert [round(r["share"], 5) for r in rows] == [1.0, 0.66655, 0.28626]             # against the fastest
    assert lm.chosen_player(snap, "11") == 1 and lm.chosen_player(snap, "gone") == 0
    assert lm.ping_text(snap) == ("Ping 42 ms now · 46 ms capture avg · 30–88 ms range (120 samples across this recording "
                                  "connection, logged over time)")
    assert lm.ping_text({}) == ""
    d = lm.parse_from_meter(snap, 0)
    assert (d["name"], d["cls"], d["dmg"], d["dps"], d["hits"], d["contrib"], d["boss"], d["live"]) == (
        "Testsorc", "sorcerer", 23405 * 75, 23405, 100, 0.51, "Testlord", True)
    assert d["rates"] == {"crit": 0.3, "double": 0.1, "perfect": 0.05, "multi": 0.02, "back": 0.2, "front": 0.5, "parry": 0.01}
    first = d["skills"][0]
    assert first["dps"] == pytest.approx(23405 * 45 / 75.4) and first["avg"] == pytest.approx(23405 * 45 / 60)
    assert (first["min"], first["max"], d["skills"][1]["min"]) == (900, None, None)
    assert d["timeline"] is None and lm.parse_from_meter({"players": [{"timeline": []}]}, 0)["timeline"] == []
    assert lm.parse_from_meter(snap, 7) is None
    assert lm.empty_text({}) == ["No data yet — choose a source and press Start."]
    assert lm.empty_text({"running": True}) == [
        "No packets yet. Check capture support, adapter permissions and your interface selection, then enter combat."]
    assert lm.empty_text({"running": True, "diagnostics": {"packets": 5}})[0].startswith("Packets are arriving.")
    assert lm.empty_text({"running": True, "diagnostics": {"packets": 5, "forwarded": 2, "warnings": ["a", "b"]},
                          "snapshot": {"warning": "Test warning"}}) == [
        "The game stream is reaching the decoder but no combat events have been recognized. Enable TCP recording before "
        "Start and export capture diagnostics after fighting briefly.", "Test warning", "a; b"]
    assert lm.empty_text({"diagnostics": {"decoded_events": 3}})[0] == \
        "Combat effects were decoded; waiting for a matching player identity or party roster in this view."


def test_the_capture_setup_words():
    assert lm.npcap_state({"supported": False}) == {"shown": False, "info": "Npcap setup is only needed on Windows."}
    assert lm.npcap_state({"supported": True, "installed": True})["info"].startswith("Npcap is installed.")
    assert lm.npcap_state({"supported": True, "detection_error": "Registry unreadable."}) == {
        "shown": True, "text": "Registry unreadable. Installation status is unknown; check with your administrator before "
                               "reinstalling."}
    assert lm.npcap_state({"supported": True, "status": "downloading", "version": "1.79"}) == {
        "shown": True, "text": "Downloading Npcap 1.79…", "again": True}
    assert lm.npcap_state({"supported": True, "status": "installer-opened", "version": "1.79"}) == {
        "shown": True, "text": "Npcap 1.79 installer is open. Finish its setup, then", "button": "Check again", "after": "."}
    assert lm.npcap_state({"supported": True, "status": "idle", "error": "Download failed."}) == {
        "shown": True, "text": "Npcap is required for Live Capture.", "button": "Install Npcap", "after": " Download failed."}
    assert lm.region_retry_shown({"automatic_metadata": {"region_status": "unavailable"}})
    assert not lm.region_retry_shown({"automatic_metadata": {"region_status": "ready"}}) and not lm.region_retry_shown({})
    assert lm.interface_options({"devices": [{"name": "eth0", "label": "Ethernet", "address": "10.0.0.2"},
                                             {"name": "wlan0", "label": "Wi-Fi"}]}) == [
        ("auto", "Auto"), ("eth0", "Ethernet · 10.0.0.2"), ("wlan0", "Wi-Fi")]
    assert lm.interface_options({"interfaces": ["eth0"]}) == [("auto", "Auto"), ("eth0", "eth0")]
    assert lm.interface_options({"devices": [], "interfaces": ["eth0"]}) == [("auto", "Auto")]        # an empty list given
    choices = dict(scope="party", gap=120, decoder="/d/x.py", auto_port=True, automatic_splits=True, auto_finish=True,
                   final_bosses="2001", iface="auto", host="any", port=50349, character="")
    assert lm.start_body("a2tools", **choices) == {
        "action": "start", "source": "a2tools", "scope": "party", "segment_gap": 120, "decoder": None, "auto_port": True,
        "automatic_splits": True, "auto_finish": True, "final_boss_ids": [2001], "iface": None, "host": None,
        "port": 50349, "target_mode": "allTargets", "character_name": None}
    custom = lm.start_body("live", **{**choices, "iface": "eth0", "host": "10.0.0.9", "port": 0, "character": "Testsorc"})
    assert (custom["decoder"], custom["auto_port"], custom["iface"], custom["host"], custom["port"], custom["character_name"]) == (
        "/d/x.py", False, "eth0", "10.0.0.9", 50349, None)
    replay = lm.start_body("replay", **{**choices, "iface": "eth0", "host": "10.0.0.9", "character": "Testsorc"})
    assert (replay["iface"], replay["host"], replay["port"], replay["character_name"]) == (None, None, None, None)
    assert lm.start_body("a2tools", **{**choices, "character": " Testsorc"})["character_name"] == " Testsorc"
    assert lm.overlay_words({"native": True}) == "Overlay opened."
    assert lm.overlay_words({"native": True, "already_open": True}) == "Overlay is already open."
    assert lm.overlay_words({"native": False, "reason": "x"}) is None
    assert lm.setup_words({"kind": "Npcap"}, True) == "Npcap setup is starting. Finish it, then press Start again."
    assert lm.setup_words({"kind": "Npcap"}, False) == "Npcap is required before Live Capture can start."
    assert lm.saved_words({"id": 7.0}) == "saved as encounter #7" and lm.exported_words({"file": "x.a2log"}) == "exported x.a2log"
    assert lm.shot_scale(1300, 2000) == 1 and lm.shot_scale(1000, 60000) == 0.5
    assert lm.shot_scale(8000, 10000) == pytest.approx(0.70711, abs=1e-5)                 # 40 million pixels at most
    assert lm.shot_words({"file": "a.png"}, True) == "Application screenshot saved: a.png (scaled to fit PNG limits)"


# ------------------------------------------------------------------ a made-up app
def _refused(path, status, message):
    return urllib.error.HTTPError("http://127.0.0.1:9" + path, status, "refused", {},
                                  io.BytesIO(json.dumps({"error": message}).encode()))


class FakeApp:
    """The app's local API as the page asks it: ``answers`` maps ``(method, path, action)`` to what the app says (a
    dict; an exception it raises; or a list of either, given in turn). Unknown requests are not found."""

    base = "http://127.0.0.1:9/"

    def __init__(self, answers=None):
        self.answers = {key: list(value) if isinstance(value, list) else value for key, value in (answers or {}).items()}
        self.calls = []
        self.hold = None                                    # an Event: requests wait for it

    def url(self, path):
        return self.base + path.lstrip("/")

    def _answer(self, method, path, body, origin=False):
        if self.hold is not None:
            self.hold.wait(5)
        key = (method, path, (body or {}).get("action") if method == "POST" else None)
        self.calls.append((method, path, body, origin))
        if key not in self.answers:
            raise _refused(path, 404, "not found")
        found = self.answers[key]
        if isinstance(found, list):
            found = found.pop(0) if len(found) > 1 else found[0]
        if isinstance(found, BaseException):
            raise found
        return json.loads(json.dumps(found))

    def get(self, path, timeout=None):
        return self._answer("GET", path, None)

    def get_bytes(self, path, timeout=None):
        raise _refused(path, 404, "not found")

    def post(self, path, payload, timeout=None, origin=False):
        return self._answer("POST", path, payload, origin)

    def sent(self, method=None, path=None):
        return [(m, p, b) for m, p, b, _o in self.calls if (method is None or m == method) and (path is None or p == path)]


def _store(tmp_path):
    return QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)


def _page(tmp_path, app=None, reading=None, answer=True, **kwargs):
    asked = []

    def ask(question):
        asked.append(question)
        return answer
    kwargs.setdefault("store", _store(tmp_path))
    kwargs.setdefault("pictures", Pictures(None))           # the art handed over, none here: no requests for it
    page = MeterPage(app, ask=ask, **kwargs)
    page.asked = asked
    for job in (page.upload_job, page.stop_job):
        if job is not None:
            job.interval_ms = 10
    page.resize(1300, 1500)
    page.show()
    page.mounted = True                                     # shown and reading, without the poll running
    page.apply(json.loads(json.dumps(reading if reading is not None else IDLE)))
    _shown()
    return page


def _shown():
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents()
    QCoreApplication.processEvents()


def _visible_texts(widget):
    _shown()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget) and label.text()]


def _part(page, key):
    box = page.slots[key]
    return box.itemAt(0).widget() if box.count() and not box.parentWidget().isHidden() else None


def _cells(table: GridTable):
    rows = []
    for r in range(table.grid.rowCount()):
        row = []
        for c in range(table.grid.columnCount()):
            widget = table.grid.itemAtPosition(r, c).widget()
            row.append(widget.text() if isinstance(widget, QLabel) else widget.findChild(QPushButton).text())
        rows.append(row)
    return rows


# ------------------------------------------------------------------ the page drawn
def test_a_reading_is_drawn_as_the_web_page_draws_it(qapp, tmp_path):
    page = _page(tmp_path, reading=_fight())
    assert page.message.text() == "Recording · 1200 TCP packets · 34 combat events · port 50349"
    assert (page.start_button.text(), page.start_button.objectName(), page.start_button.isEnabled()) == ("Stop", "danger", True)
    assert not page.clear_button.isEnabled()                                      # not while capturing
    assert page.lines["run"].text() == "Run 4 · recording"
    assert page.lines["identity"].text().startswith("Detected automatically: Testsorc · Zikel · combat entity #31")
    assert page.lines["saved"].text() == "Current part checkpoints every 15 seconds and saves on Stop."
    assert page.lines["notice"].isHidden()
    assert page.view_words.text() == "Following latest combat. Overlay always follows the latest encounter."
    assert page.follow.isHidden() and page.region_button.isHidden() and page.region.isHidden()
    assert [page.segments.itemText(i) for i in range(page.segments.count())] == [
        "Latest combat", "Whole session", "Combat 1 · 22:13:20 · 61.3s", "Testlord · 22:15:00 · 75.4s"]
    assert page.segments.currentData() == "" and page.scope.currentData() == "party" and page.combine_pets.isChecked()
    assert page.source.currentData() == "a2tools"                                   # the first reading's source
    # the fight: no warning, the enemies, the players with the ping and the counters, the chosen player's parse card
    assert _part(page, "empty") is None and _part(page, "warning") is None
    enemies = _part(page, "enemies")
    assert (enemies.title.text(), enemies.subtitle.text()) == (
        "ENEMIES", "select an enemy to show each player's damage against it")
    assert _cells(enemies.findChild(GridTable)) == [["ENEMY", "PARTY DAMAGE DEALT", "PARTY DPS"],
                                                    ["Testlord", "3.20M", "42.67K"], ["Test Shade", "230.00K", "3.07K"]]
    players = _part(page, "players")
    assert (players.title.text(), players.subtitle.text()) == ("PLAYERS", "Testlord · 75s · 45.71K raid DPS")
    rows = players.findChildren(PlayerRow)
    assert [(row.bar.words, round(row.bar.fraction, 3), row.chosen, row.who.width()) for row in rows] == [
        ("23.41K/s · 51%", 1.0, True, 150), ("15.60K/s · 34%", 0.667, False, 150), ("6.70K/s · 15%", 0.286, False, 150)]
    assert "Testsorc</b>" in rows[0].who.text() and "· Zikel" in rows[0].who.text() and "Sorcerer" in rows[0].who.text()
    assert "color: #e8cf8e" in rows[0].who.text() and "color: #e8cf8e" not in rows[1].who.text()   # the chosen name gold
    texts = _visible_texts(players)
    assert "Ping 42 ms now · 46 ms capture avg · 30–88 ms range (120 samples across this recording connection, logged " \
           "over time)" in texts
    counters = [w for w in players.findChildren(QWidget) if w.objectName() == "counter"]
    assert [(w.findChildren(QLabel)[-1].text(), w.toolTip()[:25]) for w in counters] == [
        ("Odyle Energy 1,500 (1,200 + 300 bonus)", "Your Odyle Energy, as the"), ("Shugo Keys 3", "Your Shugo Festival Rewar"),
        ("Nightmare Tickets 11 (9 + 2 bonus)", "Your Nightmare tickets, a"),
        ("Test Isle · hard: 4 runs left this week (3 + 1 bonus)", "This dungeon's weekly ent")]
    marks = [w.findChildren(QLabel)[0] for w in counters]
    assert marks[0].pixmap().isNull() and not marks[1].pixmap().isNull()   # the Odyle item's art comes from the app
    card = _part(page, "parse")
    assert isinstance(card, ParseCard) and card.d["name"] == "Testsorc" and card.d["live"] is True
    # an idle meter: why there is nothing yet, under Meter
    page.apply(json.loads(json.dumps({**IDLE, "diagnostics": {"warnings": ["first", "second"]},
                                      "snapshot": {"players": [], "warning": "Test warning"}})))
    _shown()
    assert all(_part(page, key) is None for key in ("warning", "enemies", "players", "parse"))
    empty = _part(page, "empty")
    assert empty.title.text() == "METER" and empty.subtitle.isHidden()
    words = empty.findChildren(QLabel)[-1]
    assert words.objectName() == "empty" and words.text() == (
        "No data yet — choose a source and press Start.<p>Test warning</p><p>first; second</p>")
    assert (page.start_button.text(), page.start_button.objectName()) == ("Start", "primary") and page.clear_button.isEnabled()
    assert page.lines["run"].text() == "Run 4 · recording"                           # kept: this reading has no run
    assert page.message.text() == "Stopped"


def test_the_view_follows_the_reading(qapp, tmp_path):
    reading = _fight(selection_mode="encounter", viewing_historical=True, selected_segment="s1", scope="all",
                     warning="Partial view", enemies=[], ping=None, odyle=None)
    reading.update({"combine_pets": False, "finalizing": True, "automatic_metadata": {"region_status": "unavailable"}})
    page = _page(tmp_path, reading=reading)
    assert page.view_words.text() == "Viewing an earlier encounter; capture continues into newer combat."
    assert not page.follow.isHidden() and not page.region_button.isHidden() and not page.region.isHidden()
    assert page.scope.currentData() == "all" and not page.combine_pets.isChecked()
    assert (page.start_button.text(), page.start_button.isEnabled()) == ("Saving…", False)
    assert page.segments.currentData() == ""                       # what is pinned here, not what the reading follows
    assert _part(page, "warning").findChild(QLabel).text() == "Partial view" and _part(page, "enemies") is None
    players = _part(page, "players")
    assert not [t for t in _visible_texts(players) if t.startswith("Ping")]
    assert len([w for w in players.findChildren(QWidget) if w.objectName() == "counter"]) == 3
    page.pinned = "s2"                                             # pinned: chosen whatever the reading says
    page.apply(json.loads(json.dumps(_fight(selected_segment="all"))))
    assert page.segments.currentData() == "s2"
    page.pinned = ""
    page.apply(json.loads(json.dumps(_fight(selected_segment="all"))))
    assert page.segments.currentData() == "all"
    page.segments.setFocus()                                       # being chosen: left alone
    _shown()
    reading = _fight(segments=[{"id": "s9", "label": "Combat 9", "start": 1763763200000, "duration": 5}])
    page.apply(json.loads(json.dumps(reading)))
    if page.segments.hasFocus():
        assert page.segments.count() == 4
    page.scope.setFocus()
    _shown()
    assert not page.segments.hasFocus()
    page.apply(json.loads(json.dumps(reading)))
    assert page.segments.itemText(2) == "Combat 9 · 22:13:20 · 5.0s" and page.segments.count() == 3


def test_a_part_of_the_fight_is_drawn_again_only_when_it_changed(qapp, tmp_path):
    page = _page(tmp_path, reading=_fight())
    drawn = {key: _part(page, key) for key in ("enemies", "players", "parse")}
    page.apply(json.loads(json.dumps(_fight())))                   # the same reading: nothing drawn again
    assert {key: _part(page, key) for key in drawn} == drawn
    reading = _fight()
    reading["snapshot"]["players"][2]["dps"] = 7000                # the cleric's figures changed: the players again
    page.apply(reading)
    _shown()
    assert _part(page, "enemies") is drawn["enemies"] and _part(page, "parse") is drawn["parse"]
    assert _part(page, "players") is not drawn["players"]
    # choosing a player: their row marked and their parse card
    rows = _part(page, "players").findChildren(PlayerRow)
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(rows[2], Qt.LeftButton)
    _shown()
    assert [row.chosen for row in _part(page, "players").findChildren(PlayerRow)] == [False, False, True]
    assert _part(page, "parse").d["name"] == "Testcleric" and page.chosen_key == "12"
    page.apply(json.loads(json.dumps(_fight())))                    # kept as the readings come
    assert _part(page, "parse").d["name"] == "Testcleric"
    rows = _part(page, "players").findChildren(PlayerRow)
    rows[1].setFocus()
    QTest.keyClick(rows[1], Qt.Key_Space)
    _shown()
    assert _part(page, "parse").d["name"] == "Testranger"
    reading = _fight()
    reading["snapshot"]["players"].pop(1)                           # gone: the first again
    page.apply(reading)
    assert _part(page, "parse").d["name"] == "Testsorc"


# ------------------------------------------------------------------ the controls
def test_the_view_choices_are_sent_and_kept(qapp, tmp_path):
    app = FakeApp({("POST", "/api/meter", "view"): _fight(scope="self")})
    page = _page(tmp_path, app, reading=_fight())
    page.scope.setCurrentIndex(page.scope.findData("self"))
    page.scope.activated.emit(page.scope.currentIndex())
    page.combine_pets.click()
    page.auto_split.click()
    page.gap.setValue(300)
    page.segments.setCurrentIndex(page.segments.findData("s2"))
    page.segments.activated.emit(page.segments.currentIndex())
    next(b for b in page.findChildren(QPushButton) if b.text() == "All enemies").click()
    _part(page, "enemies").findChildren(QPushButton)[1].click()      # an enemy chosen
    settle(lambda: len(app.sent("POST")) == 7)
    assert [b for _m, _p, b in app.sent("POST")] == [
        {"action": "view", "scope": "self"}, {"action": "view", "combine_pets": False},
        {"action": "view", "automatic_splits": False}, {"action": "view", "segment_gap": 300},
        {"action": "view", "segment": "s2"}, {"action": "view", "enemy": None}, {"action": "view", "enemy": "add:2"}]
    assert page.pinned == "s2" and page.store.value(lm.SCOPE_KEY) == "self"
    settle(lambda: page.scope.currentData() == "self")               # each answer drawn
    page.follow.show()
    page.follow.click()
    settle(lambda: len(app.sent("POST")) == 8)
    assert app.sent("POST")[-1][2] == {"action": "view", "segment": None, "enemy": None} and page.pinned == ""
    # kept for the next visit, a stored scope that is none of them ignored
    assert MeterPage(None, store=page.store).scope.currentData() == "self"
    page.store.setValue(lm.SCOPE_KEY, "everyone")
    assert MeterPage(None, store=page.store).scope.currentData() == "party"
    # a choice refused says why
    app.answers[("POST", "/api/meter", "view")] = _refused("/api/meter", 500, "ValueError: no such enemy")
    page.view_choice({"enemy": "x"})
    settle(lambda: page.notice_text == "ValueError: no such enemy")


def test_the_sources_rows_and_advanced_capture(qapp, tmp_path):
    store = _store(tmp_path)
    store.setValue(lm.CHARACTER_KEY, "Testsorc")
    store.setValue(lm.FINAL_BOSS_KEY, "2001, 3002")
    app = FakeApp({("POST", "/api/meter", "view"): IDLE})
    page = _page(tmp_path, app, store=store)
    advanced = page.findChild(Details)
    assert not advanced.is_open() and advanced.inside.isHidden()                       # closed at first
    assert advanced.button.text() == "Advanced capture" and advanced.sub.text() == lm.ADVANCED_SUB
    advanced.sub.clicked.emit()                                                         # the summary's words open it too
    assert advanced.is_open() and store.value("meter-advanced-open") == "1"
    assert MeterPage(None, store=store).findChild(Details).is_open()                    # remembered
    advanced.button.click()
    assert store.value("meter-advanced-open") == "0"
    advanced.set_open(True)
    _shown()
    assert page.live.isVisibleTo(page) and page.custom.isHidden()
    assert (page.character.text(), page.final_bosses.text(), page.host.text(), page.port.value()) == (
        "Testsorc", "2001, 3002", "any", 50349)
    assert page.iface.currentData() == "auto" and page.auto_port.isChecked() and page.auto_finish.isChecked()
    assert page.engine.text().startswith("Live Capture uses the included A2Tools protocol engine.")
    for source, live, custom in (("replay", False, False), ("live", True, True), ("a2tools", True, False)):
        page.source.setCurrentIndex(page.source.findData(source))
        page.source.activated.emit(page.source.currentIndex())
        assert (page.live.isHidden(), page.custom.isHidden()) == (not live, not custom), source
    # the name override: kept and told to the view when changed, trimmed
    page.character.setText("  Testranger ")
    page.character.editingFinished.emit()
    page.character.editingFinished.emit()                                               # unchanged: not again
    settle(lambda: app.sent("POST"))
    assert app.sent("POST") == [("POST", "/api/meter", {"action": "view", "character_name": "Testranger"})]
    assert store.value(lm.CHARACTER_KEY) == "Testranger"
    page.final_bosses.setText("4004")
    page.final_bosses.editingFinished.emit()
    assert store.value(lm.FINAL_BOSS_KEY) == "4004"
    # what is not drawn here yet opens in the web interface
    opened = []
    page = _page(tmp_path, store=store, open_in_web=opened.append)
    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "Open in the web interface"]
    assert len(buttons) == 2 and all(b.isEnabled() for b in buttons)
    buttons[0].click()
    buttons[1].click()
    assert opened == ["meter", "meter"]
    assert lm.ELSEWHERE_REVIEW in _visible_texts(page)


def test_the_overlay_choice_is_kept_by_the_app(qapp, tmp_path):
    app = FakeApp({("POST", "/api/ui", None): {"overlay_on_start": False}})
    page = _page(tmp_path, app)
    page.overlay_on_start.click()
    settle(lambda: app.sent("POST"))
    assert app.sent("POST") == [("POST", "/api/ui", {"overlay_on_start": False})]
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 500, "OSError: read-only")
    page.overlay_on_start.click()                                                       # refused: put back
    settle(lambda: page.notice_text == "Could not save overlay preference: OSError: read-only")
    assert not page.overlay_on_start.isChecked()


def test_a_custom_decoder_is_read_and_kept_by_the_app(qapp, tmp_path):
    big, small = tmp_path / "big.py", tmp_path / "decoder.py"
    big.write_bytes(b"#" * (1048576 + 1))
    small.write_text("def decode(data):\n    return []\n", encoding="utf-8")
    chosen = [str(big)]
    app = FakeApp({("POST", "/api/meter/decoder", None): [{"path": "/app/decoders/decoder.py", "name": "decoder.py"}],
                   ("GET", "/api/capture/setup", None): {"supported": False},
                   ("POST", "/api/meter", "start"): {**IDLE, "error": "the test stops here"}})
    page = _page(tmp_path, app, choose_file=lambda: chosen[0])
    page.source.setCurrentIndex(page.source.findData("live"))
    page._source_shown()
    page.start_button.click()
    assert page.notice_text == "Choose a decoder .py file first." and not app.calls
    page.decoder_button.click()
    assert page.decoder_name.text() == "Decoder files must be smaller than 1 MiB" and not app.calls
    chosen[0] = str(small)
    page.decoder_button.click()
    settle(lambda: page.decoder_name.text() == "decoder.py")
    assert app.sent("POST", "/api/meter/decoder") == [
        ("POST", "/api/meter/decoder", {"name": "decoder.py", "source": "def decode(data):\n    return []\n"})]
    page.start_button.click()                                           # packet capture checked first, as for Live Capture
    settle(lambda: page.notice_text == "the test stops here")
    assert app.sent("GET", "/api/capture/setup")
    start = app.sent("POST", "/api/meter")[0][2]
    assert (start["source"], start["decoder"], start["port"]) == ("live", "/app/decoders/decoder.py", 50349)
    app.answers[("POST", "/api/meter/decoder", None)] = _refused("/api/meter/decoder", 400, "ValueError: not Python")
    page.decoder_button.click()
    settle(lambda: page.decoder_name.text() == "ValueError: not Python")
    assert page.decoder is None
    chosen[0] = ""                                                                      # none chosen: none kept
    page.decoder_button.click()
    assert page.decoder is None


# ------------------------------------------------------------------ Start and Stop
def test_start_checks_packet_capture_first_and_sends_what_the_web_page_sends(qapp, tmp_path):
    started = _fight()
    app = FakeApp({("GET", "/api/capture/setup", None): {"supported": False},
                   ("POST", "/api/meter", "start"): started,
                   ("POST", "/api/overlay", None): {"native": True, "already_open": False}})
    page = _page(tmp_path, app)
    page.pinned = "s1"
    page.start_button.click()
    page.start_button.click()                                      # pressed again while checking: once
    settle(lambda: page.notice_text == "Capture started. Overlay opened.")
    assert [(m, p) for m, p, _b in app.sent()] == [("GET", "/api/capture/setup"), ("POST", "/api/meter"), ("POST", "/api/overlay")]
    assert app.sent("POST", "/api/meter")[0][2] == {
        "action": "start", "source": "a2tools", "scope": "party", "segment_gap": 120, "decoder": None, "auto_port": True,
        "automatic_splits": True, "auto_finish": True, "final_boss_ids": [], "iface": None, "host": None, "port": 50349,
        "target_mode": "allTargets", "character_name": None}
    assert page.toast.text() == "Capture started" and page.pinned == ""
    assert (page.start_button.text(), page.start_button.isEnabled()) == ("Stop", True)
    # Advanced capture's choices, and no overlay when not wanted
    page = _page(tmp_path, app)
    page.overlay_on_start.setChecked(False)
    page.iface.addItem("Ethernet · 10.0.0.2", "eth0")
    page.iface.setCurrentIndex(1)
    page.host.setText("10.0.0.9")
    page.auto_port.setChecked(False)
    page.port.setValue(7777)
    page.character.setText("Testsorc")
    page.final_bosses.setText("2001, 3002")
    page.auto_finish.setChecked(False)
    page.auto_split.setChecked(False)
    page.gap.setValue(600)
    app.calls.clear()
    page.start_button.click()
    settle(lambda: page.notice_text == "Capture started. Waiting for combat data.")
    body = app.sent("POST", "/api/meter")[0][2]
    assert {k: body[k] for k in ("iface", "host", "auto_port", "port", "character_name", "final_boss_ids", "auto_finish",
                                 "automatic_splits", "segment_gap")} == {
        "iface": "eth0", "host": "10.0.0.9", "auto_port": False, "port": 7777, "character_name": "Testsorc",
        "final_boss_ids": [2001, 3002], "auto_finish": False, "automatic_splits": False, "segment_gap": 600}
    assert not app.sent("POST", "/api/overlay") and page.start_button.isEnabled()


def test_start_says_when_capture_support_is_missing_or_capture_did_not_start(qapp, tmp_path):
    missing = {"supported": True, "installed": False, "kind": "Npcap", "prompt": "Install Npcap now?"}
    app = FakeApp({("GET", "/api/capture/setup", None): missing, ("POST", "/api/capture/setup", "install"): {"started": True}})
    page = _page(tmp_path, app, answer=False)
    page.start_button.click()
    settle(lambda: page.notice_text == "Npcap is required before Live Capture can start.")
    assert page.asked == ["Install Npcap now?"] and not app.sent("POST")
    page = _page(tmp_path, app, answer=True)
    page.start_button.click()
    settle(lambda: page.notice_text == "Npcap setup is starting. Finish it, then press Start again.")
    assert app.sent("POST") == [("POST", "/api/capture/setup", {"action": "install"})]
    assert page.start_button.isEnabled() and not page.checking
    app.answers[("GET", "/api/capture/setup", None)] = {"detection_error": "Registry unreadable"}
    page.start_button.click()
    settle(lambda: page.notice_text == "Could not check Npcap: Registry unreadable")
    app.answers[("GET", "/api/capture/setup", None)] = _refused("/api/capture/setup", 500, "OSError: no")
    page.start_button.click()
    settle(lambda: page.notice_text == "Could not check Npcap: OSError: no")
    # the demo replay starts without the check; a capture that did not start says why
    app = FakeApp({("POST", "/api/meter", "start"): [{**IDLE, "error": "the test stops here"}, IDLE]})
    page = _page(tmp_path, app)
    page.source.setCurrentIndex(page.source.findData("replay"))
    page.start_button.click()
    settle(lambda: page.notice_text == "the test stops here")
    assert app.sent()[0][2]["source"] == "replay" and app.sent()[0][2]["port"] is None
    page.start_button.click()
    settle(lambda: page.notice_text == "Capture did not start. Check capture diagnostics.")
    app.answers[("POST", "/api/meter", "start")] = _refused("/api/meter", 500, "RuntimeError: busy")
    page.start_button.click()
    settle(lambda: page.notice_text == "RuntimeError: busy")
    assert page.start_button.isEnabled()


def test_stop_saves_and_uploads_unless_settings_say_not_to(qapp, tmp_path):
    stopped = {**IDLE, "saved_log": "C:/logs/s.a2log"}
    app = FakeApp({("POST", "/api/meter", "stop"): stopped, ("GET", "/api/ui", None): {"meter_auto_upload": True},
                   ("POST", "/api/meter", "upload"): {"job": "j1"},
                   ("GET", "/api/jobs/j1", None): [{"status": "running", "log": ["Uploading part 1 of 1"]},
                                                   {"status": "done", "log": [], "result": {"url": "https://logs.example/r/9"}}]})
    opened = []
    page = _page(tmp_path, app, reading=_fight(), open_link=opened.append)
    page.start_button.click()
    assert page.notice_text == "Stopping capture and saving logs…" and not page.start_button.isEnabled()
    settle(lambda: page.notice_text.startswith("Capture stopped and uploaded"), timeout=5)
    assert page.notice_text == "Capture stopped and uploaded — open shared log"
    assert "href='https://logs.example/r/9'" in page.lines["notice"].text()
    assert page.toast.text() == "Capture stopped. Session saved to C:/logs/s.a2log"
    assert page.start_button.isEnabled() and page.start_button.text() == "Start"
    page.lines["notice"].linkActivated.emit("https://logs.example/r/9")
    assert opened == ["https://logs.example/r/9"]
    # Settings says not to upload; no file saved; the upload refused; the stop refused
    for answers, words in (
            ({("GET", "/api/ui", None): {"meter_auto_upload": False}}, "Capture stopped. Session saved to C:/logs/s.a2log"),
            ({("POST", "/api/meter", "stop"): IDLE},
             "Capture stopped. No session file was saved; check Combat Logs and capture diagnostics."),
            ({("GET", "/api/jobs/j1", None): {"status": "error", "error": "No log server key"}},
             "Capture stopped and saved. Auto-upload failed: No log server key (you can still Upload manually)."),
            ({("GET", "/api/ui", None): _refused("/api/ui", 500, "x"), ("GET", "/api/jobs/j1", None): {"status": "done"}},
             "Capture stopped and uploaded."),
            ({("POST", "/api/meter", "stop"): _refused("/api/meter", 500, "RuntimeError: stop failed")},
             "RuntimeError: stop failed")):
        app.answers.update(answers)
        page = _page(tmp_path, app, reading=_fight())
        page.start_button.click()
        settle(lambda: page.notice_text == words and page.start_button.isEnabled(), timeout=5)
        app.answers.update({("POST", "/api/meter", "stop"): stopped, ("GET", "/api/ui", None): {"meter_auto_upload": True},
                            ("GET", "/api/jobs/j1", None): {"status": "done", "result": {"url": "https://logs.example/r/9"}}})


def test_clear_asks_first(qapp, tmp_path):
    app = FakeApp({("POST", "/api/meter", "clear"): IDLE})
    page = _page(tmp_path, app, answer=False)
    page.pinned = "s1"
    page.clear_button.click()
    assert page.asked == [lm.CLEAR_ASK] and not app.calls and page.pinned == "s1"
    page = _page(tmp_path, app, answer=True)
    page.pinned = "s1"
    page.clear_button.click()
    settle(lambda: page.notice_text == "Combat history cleared.")
    assert app.sent() == [("POST", "/api/meter", {"action": "clear"})] and page.pinned == ""


# ------------------------------------------------------------------ the actions
@pytest.mark.parametrize("key, answer, words", [
    ("save", {"id": 7}, "saved as encounter #7 — open in Combat Logs"),
    ("export", {"file": "C:/logs/x.a2log"}, "exported C:/logs/x.a2log"),
    ("split", _fight(), "Next combat event starts a new split."),
    ("finish", _fight(), "Run finished. Capture continues; the next fight starts a new run."),
    ("hide", {"hidden": True}, "Overlay hidden. Open overlay to show it again."),
    ("overlay", {"native": True, "already_open": True}, "Overlay is already open."),
    ("interfaces", {"devices": [{"name": "eth0", "label": "Ethernet", "address": "10.0.0.2"}]}, "Capture interfaces refreshed."),
])
def test_an_action_says_what_it_is_doing_then_what_it_did(qapp, tmp_path, key, answer, words):
    method, path, action = {"save": ("POST", "/api/meter", "save"), "export": ("POST", "/api/meter", "export"),
                            "split": ("POST", "/api/meter", "split"), "finish": ("POST", "/api/meter", "finish-run"),
                            "hide": ("POST", "/api/overlay", "hide"), "overlay": ("POST", "/api/overlay", None),
                            "interfaces": ("GET", "/api/meter/interfaces", None)}[key]
    app = FakeApp({(method, path, action): answer})
    app.hold = threading.Event()
    page = _page(tmp_path, app, reading=_fight())
    page.pinned = "s1"
    button = page.actions[key]
    button.click()
    pending = lm.ACTIONS[key][1]
    assert (button.text(), button.isEnabled()) == (pending, False)                # until it is done
    assert page.notice_text in (pending, "saving…", "exporting…", "opening overlay…")
    button.click()                                                                # pressed again meanwhile: once
    app.hold.set()
    settle(lambda: not page.acting)
    assert page.notice_text == words and page.toast.text() == words
    assert (button.text(), button.isEnabled()) == (lm.ACTIONS[key][0], True)
    assert len(app.calls) == 1
    if key == "split":
        assert page.pinned == ""
    if key == "interfaces":
        assert [page.iface.itemText(i) for i in range(page.iface.count())] == ["Auto", "Ethernet · 10.0.0.2"]


@pytest.mark.parametrize("key, words", [
    ("save", "ValueError: nothing to save"), ("export", "ValueError: nothing to save"),
    ("split", "Action failed: ValueError: nothing to save"), ("finish", "ValueError: nothing to save"),
    ("hide", "Action failed: ValueError: nothing to save"), ("interfaces", "Could not list capture interfaces: ValueError: nothing to save"),
])
def test_an_action_refused_says_why(qapp, tmp_path, key, words):
    refusal = _refused("/x", 500, "ValueError: nothing to save")
    app = FakeApp({("POST", "/api/meter", "save"): refusal, ("POST", "/api/meter", "export"): refusal,
                   ("POST", "/api/meter", "split"): refusal, ("POST", "/api/meter", "finish-run"): refusal,
                   ("POST", "/api/overlay", "hide"): refusal, ("GET", "/api/meter/interfaces", None): refusal})
    page = _page(tmp_path, app, reading=_fight())
    page.actions[key].click()
    settle(lambda: not page.acting)
    assert page.notice_text == words and page.toast.text() == words and page.actions[key].isEnabled()


def test_an_answer_with_an_error_is_refused_unless_it_is_the_meters_state(qapp, tmp_path):
    app = FakeApp({("POST", "/api/meter", "save"): {"error": "nothing retained"},
                   ("POST", "/api/meter", "split"): {**_fight(), "error": "Capture warning"}})
    page = _page(tmp_path, app, reading=_fight())
    page.actions["save"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == "nothing retained"
    page.actions["split"].click()                                                 # the meter's state: drawn, its error shown
    settle(lambda: not page.acting)
    assert page.notice_text == "Next combat event starts a new split." and page.message.text() == "Capture warning"


def test_saved_opens_combat_logs_and_upload_runs_the_apps_job(qapp, tmp_path):
    shown = []
    app = FakeApp({("POST", "/api/meter", "save"): {"id": 7}, ("POST", "/api/meter", "upload"): {"job": "j1"},
                   ("GET", "/api/jobs/j1", None): [{"status": "running", "log": ["Uploading part 1 of 1"]},
                                                   {"status": "done", "log": [], "result": {"url": "javascript:alert(1)"}}]})
    opened = []
    page = _page(tmp_path, app, open_page=shown.append, open_link=opened.append)
    page.actions["save"].click()
    settle(lambda: not page.acting)
    assert "href='#/combat'" in page.lines["notice"].text()
    page.lines["notice"].linkActivated.emit("#/combat")
    assert shown == ["combat"]
    page.actions["upload"].click()
    assert page.notice_text == "uploading…"
    settle(lambda: page.notice_text == "Uploading part 1 of 1")                   # the job's log as it runs
    settle(lambda: not page.acting)
    assert page.notice_text == "uploaded" and "<a" not in page.lines["notice"].text()   # no web address: no link
    page.lines["notice"].linkActivated.emit("javascript:alert(1)")
    assert opened == []
    app.answers[("GET", "/api/jobs/j1", None)] = {"status": "error", "error": "No log server key"}
    page.actions["upload"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == "No log server key" and page.toast.text() == "No log server key"


def test_open_overlay_opens_the_overlays_page_when_the_app_cannot(qapp, tmp_path):
    windows = []
    app = FakeApp({("POST", "/api/overlay", None): {"native": False, "reason": "no window"}})
    page = _page(tmp_path, app, open_window=lambda url: windows.append(url))
    page.actions["overlay"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == "Overlay opened in a window." and windows == ["http://127.0.0.1:9/overlay"]
    page.actions["overlay"].click()                                               # not asked of the app again
    settle(lambda: not page.acting)
    assert len(app.calls) == 1 and len(windows) == 2
    page = _page(tmp_path, app, open_window=lambda url: False)
    page.actions["overlay"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == "Overlay popup was blocked. Click Open overlay to retry."
    # the app refusing opens the page; no answer at all is said
    app = FakeApp({("POST", "/api/overlay", None): _refused("/api/overlay", 500, "RuntimeError: x")})
    windows.clear()
    page = _page(tmp_path, app, open_window=lambda url: windows.append(url))
    page.actions["overlay"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == "Overlay opened in a window." and len(windows) == 1
    page.actions["overlay"].click()                                               # the app asked again next time
    settle(lambda: not page.acting)
    assert len(app.calls) == 2 and len(windows) == 2
    app = FakeApp({("POST", "/api/overlay", None): urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))})
    page = _page(tmp_path, app)
    page.actions["overlay"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == lm.OVERLAY_SILENT
    app.answers[("POST", "/api/meter", "start")] = _fight()                        # and after a Start
    page.source.setCurrentIndex(page.source.findData("replay"))
    page.start_button.click()
    settle(lambda: page.notice_text == "Capture started. " + lm.OVERLAY_SILENT)
    assert page.start_button.isEnabled()


def test_screenshot_saves_the_pages_whole_content_as_the_apps_own_page_would(qapp, tmp_path, monkeypatch):
    app = FakeApp({("POST", "/api/screenshot", None): {"file": "C:/shots/application-1.png", "bytes": 1}})
    page = _page(tmp_path, app, reading=_fight())
    page.resize(1300, 700)                                                       # the fight runs on below the fold
    _shown()
    page.actions["screenshot"].click()
    assert page.notice_text == "Saving application PNG…"                          # rendered, now saved by the app
    settle(lambda: not page.acting)
    assert page.notice_text == "Application screenshot saved: C:/shots/application-1.png"
    (_m, path, body, origin), = app.calls
    assert path == "/api/screenshot" and origin is True                            # as the app's own page asks
    assert body["png"].startswith("data:image/png;base64,")
    import base64
    image = QImage.fromData(base64.b64decode(body["png"].split(",", 1)[1]))
    content = page.scroll.widget()
    assert (image.width(), image.height()) == (content.width(), content.height()) and content.height() > page.height()
    monkeypatch.setattr(lm, "shot_scale", lambda width, height: 0.5)              # shrunk to fit: said
    page.actions["screenshot"].click()
    settle(lambda: not page.acting)
    assert page.notice_text.endswith(" (scaled to fit PNG limits)")
    image = QImage.fromData(base64.b64decode(app.calls[-1][2]["png"].split(",", 1)[1]))
    assert (image.width(), image.height()) == (round(content.width() / 2), round(content.height() / 2))
    monkeypatch.setattr(lm, "shot_scale", lambda width, height: 0.1)
    page.actions["screenshot"].click()
    settle(lambda: not page.acting)
    assert page.notice_text == lm.SHOT_TOO_LARGE and len(app.calls) == 2


# ------------------------------------------------------------------ Npcap and the region
def test_npcap_shows_above_the_meter_only_when_it_needs_doing(qapp, tmp_path):
    app = FakeApp({("GET", "/api/npcap", None): [{"supported": True, "installed": False, "status": "idle"},
                                                 {"supported": True, "installed": False, "status": "downloading",
                                                  "version": "1.79"},
                                                 {"supported": True, "installed": False, "status": "installer-opened",
                                                  "version": "1.79"},
                                                 {"supported": True, "installed": True}],
                   ("POST", "/api/npcap", "install"): {"status": "finding"}})
    page = _page(tmp_path, app, answer=False)
    page.npcap_again.setInterval(10)
    page.read_npcap()
    settle(lambda: not page.npcap.isHidden())
    assert (page.npcap_words.text(), page.npcap_button.text(), page.npcap_after.isHidden()) == (
        "Npcap is required for Live Capture.", "Install Npcap", True)
    page.npcap_button.click()                                                     # declined: nothing
    assert page.asked == [lm.NPCAP_ASK] and not app.sent("POST")
    page.ask = lambda question: True
    page.npcap_button.click()
    assert page.npcap_words.text() == "Starting Npcap setup…" and page.npcap_button.isHidden()
    settle(lambda: page.npcap_words.text() == "Npcap 1.79 installer is open. Finish its setup, then")   # read again after
    assert app.sent("POST") == [("POST", "/api/npcap", {"action": "install"})]
    assert [m for m, p, _b in app.sent() if p == "/api/npcap"].count("GET") == 3  # downloading: looked at again soon
    assert (page.npcap_button.text(), page.npcap_after.text()) == ("Check again", ".")
    page.npcap_button.click()                                                     # Check again: installed
    settle(lambda: page.npcap.isHidden())
    assert "Npcap is installed. Live Capture may need administrator permissions" in page.engine.text()
    app.answers[("GET", "/api/npcap", None)] = _refused("/api/npcap", 500, "OSError: x")
    page.read_npcap()
    settle(lambda: not page.npcap.isHidden())
    assert page.npcap_words.text() == "Could not check Npcap: OSError: x"


def test_retry_region_detection(qapp, tmp_path):
    reading = {**IDLE, "automatic_metadata": {"region_status": "unavailable"}}
    app = FakeApp({("POST", "/api/meter", "retry-region"): [{"ok": True}, _refused("/api/meter", 500, "OSError: offline")]})
    page = _page(tmp_path, app, reading=reading)
    assert not page.region.isHidden() and not page.region_button.isHidden()
    page.region_button.click()
    assert page.region_words.text() == lm.REGION_CHECKING and not page.region_button.isEnabled()
    settle(lambda: page.region_words.text() == lm.REGION_RETRYING)
    assert page.region_button.isEnabled() and app.sent()[0][2] == {"action": "retry-region"}
    page.region_button.click()
    settle(lambda: page.region_words.text() == "OSError: offline")
    page.apply({**IDLE, "automatic_metadata": {"region_status": "ready"}})
    assert page.region_button.isHidden() and not page.region.isHidden()           # its words stay


# ------------------------------------------------------------------ reading the meter
def test_the_meter_is_read_while_the_page_is_shown_at_the_web_pages_pace(qapp, tmp_path):
    app = FakeApp({("GET", "/api/ui", None): {"overlay_on_start": False, "performance_mode": True},
                   ("GET", "/api/npcap", None): {"supported": False},
                   ("GET", "/api/meter/interfaces", None): {"devices": [{"name": "eth0", "label": "Ethernet"}]},
                   ("GET", "/api/meter", None): _fight()})
    page = MeterPage(app, store=_store(tmp_path), pictures=Pictures(None))
    page.resize(1300, 1200)
    page.show()
    _shown()
    assert not app.calls                                                          # not before the window starts it
    page.start()
    settle(lambda: page.message.text().startswith("Recording"))
    assert {p for _m, p, _b in app.sent()} >= {"/api/ui", "/api/npcap", "/api/meter/interfaces", "/api/meter"}
    assert not page.overlay_on_start.isChecked() and page.light
    assert page.poller.timeout == 8 and page.poller._timer.isActive()
    settle(lambda: page.iface.count() == 2)
    assert page.poller._timer.interval() == 1500                                  # capturing, in performance mode
    page.light = False
    assert page._pace() == 700
    page.answer = IDLE
    assert page._pace() == 300                                                    # its first seconds
    page.started_at -= 7
    assert page._pace() == 1200
    page.light = True
    assert page._pace() == 2000
    page.window().showMinimized()
    if page.window().isMinimized():
        assert page._pace() == 3000
    page.window().showNormal()
    page.source.setCurrentIndex(page.source.findData("replay"))
    page.hide()                                                                   # another page: no more readings
    assert not page.poller._timer.isActive() and not page.mounted
    count = len(app.calls)
    page.apply(_fight())                                                          # a reading still on its way: dropped
    page.show()
    _shown()
    settle(lambda: len(app.calls) > count + 3)
    assert page.poller._timer.isActive()
    settle(lambda: page.source.currentData() == "a2tools")                       # the app's source, as each visit shows it
    app.answers[("GET", "/api/meter", None)] = _refused("/api/meter", 500, "OSError: gone")
    settle(lambda: page.message.text().startswith("Could not refresh the meter"))
    assert page.message.text() == ("Could not refresh the meter: OSError: gone. Last readings retained; capture status is "
                                   "unknown. Export capture diagnostics, or wait for automatic retry.")
    page.stop()


# ------------------------------------------------------------------ the API
def test_a_request_can_name_the_apps_own_origin_and_tell_silence_from_refusal(qapp, tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer
    from aion2calc.app import server
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        api = AppApi(f"http://127.0.0.1:{srv.server_address[1]}/")
        assert api.origin() == f"http://127.0.0.1:{srv.server_address[1]}"
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        image, data = QImage(4, 3, QImage.Format_ARGB32), QByteArray()
        image.fill(0xff336699)
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        import base64
        png = {"png": "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")}
        with pytest.raises(urllib.error.HTTPError) as refused:                     # a program naming no origin: refused
            api.post("/api/screenshot", png)
        assert refused.value.code == 403
        saved = api.post("/api/screenshot", png, origin=True)                     # the app's own page, as the window is
        assert saved["bytes"] == len(bytes(data)) and os.path.isfile(saved["file"])
        requests = Requests(api)
        got = []
        requests.replied.connect(lambda name, answer: got.append(name))
        requests.failed.connect(lambda name, why: got.append(name))
        requests.post("shot", "/api/screenshot", png, origin=True)
        requests.post("refused", "/api/screenshot", png)
        settle(lambda: len(got) == 2)
        assert got == ["shot", "refused"] and requests.unanswered == set()        # the app answered both
        quiet = Requests(AppApi("http://127.0.0.1:9/", timeout=1))
        quiet.failed.connect(lambda name, why: got.append(name))
        quiet.get("silent", "/api/ui")
        settle(lambda: "silent" in got, timeout=5)
        assert quiet.unanswered == {"silent"}
        requests.stop()
        quiet.stop()
        poller = Poller(api, "/api/ui", 30, timeout=5)                            # paused, then asking again
        answers = []
        poller.answered.connect(answers.append)
        poller.start()
        settle(lambda: len(answers) >= 2)
        poller.pause()
        _shown()
        count = len(answers)
        time.sleep(0.15)
        _shown()
        assert len(answers) <= count + 1 and not poller._timer.isActive()
        poller.start()
        settle(lambda: len(answers) >= count + 2)
        poller.stop()
    finally:
        srv.shutdown()
