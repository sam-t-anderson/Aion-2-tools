"""The native Timers page (0.2.428): the regional event timers, the field bosses' respawn reference, their kills by
server and the recorded boss defeats as the web page shows them (pages/timers.js and ``A2Timers`` in
static/timers.js), off screen, over the bundled catalogs and a stand-in for the log server.
"""
from datetime import datetime, timezone
import json
import os
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import timers  # noqa: E402
from aion2calc.gui.news import when  # noqa: E402
from aion2calc.gui.timers_page import TimersPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aion2calc", "app", "static")
CATALOG = json.load(open(os.path.join(STATIC, "event-schedules.json"), encoding="utf-8"))
FIELD = json.load(open(os.path.join(STATIC, "field-bosses.json"), encoding="utf-8"))
NOW = datetime(2026, 11, 21, 10, 5, tzinfo=timezone.utc).timestamp() * 1000     # a Saturday, 10:05 UTC
SECONDS = NOW / 1000
#: One event a day at 10:00 UTC for an hour, entry for its first ten minutes.
ONE = {"version": 1, "note": "A test schedule.", "source_name": "Test source", "source_updated_at": "2026-11-01",
       "checked_at": "2026-11-02", "review_after": "2026-12-01",
       "regions": [{"id": "test", "name": "Test region", "timezone": "UTC"}],
       "events": [{"id": "door", "name": "Door", "hours": [10], "minute": 0, "duration_minutes": 60, "entry_minutes": 10}]}
IDENTITY = {"server": 2102, "server_name": "Zikel", "faction": "asmodian", "character": "Tester"}
KILLS = {"window_seconds": 172800, "generated_at": SECONDS, "kills": [
    {"boss": "Eternal Gartua", "server": 2102, "server_name": "Zikel", "killed_at": SECONDS - 3600, "map_id": 110001,
     "reports": 2, "logs": ["abcDEF1234"], "previous_killed_at": SECONDS - 13 * 3600},
    {"boss": "Kernon of the West", "server": 2102, "server_name": "Zikel", "killed_at": SECONDS - 600, "map_id": 100001,
     "reports": 1},
    {"boss": "Argo, the Spirit King", "server": 2102, "server_name": "Zikel", "killed_at": SECONDS - 7200, "map_id": 600001,
     "reports": 3, "respawn_at": SECONDS + 3600, "respawn_seconds": 43200, "respawn_samples": 3, "logs": ["xyzXYZ987"]},
    {"boss": "Kernon of the West", "server": 1101, "killed_at": SECONDS - 900, "map_id": 100001, "reports": 1},
    {"boss": "No time", "server": 2102}]}
DEFEATS = {"generated_at": SECONDS, "truncated": True, "note": "Observations come from uploaded public logs.", "groups": [
    {"boss": "Atiel", "npc_id": 2340601, "region": "eu", "last_defeat_at": SECONDS - 7200, "observed_defeats": 4,
     "game_patch": "version:product:1.2.3.4.5", "map_id": 600001, "instance_id": 12, "last_log_id": "abcDEF1234",
     "last_segment": 1, "omitted_history": 3,
     "recent_defeats": [{"defeated_at": SECONDS - 7200, "engaged_roster_members": 8, "evidence": "boss HP reached zero",
                         "timing_basis": "recorded_clock", "log_id": "abcDEF1234", "segment": 1},
                        {"defeated_at": None, "evidence": None, "timing_basis": "upload_time", "log_id": "bad id"}]},
    {"boss": "Orissan", "npc_id": 2340700, "region": None, "last_defeat_at": None}]}


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


def local(*parts) -> str:
    return datetime(*parts, tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ the arithmetic
def test_the_words_and_numbers_read_as_the_web_page_writes_them():
    assert [timers.dur(m) for m in (30, 60, 90, 660, None)] == ["30m", "1h", "1h 30m", "11h", ""]
    assert timers.build_label("version:product:1.2.3.4.5") == "Product version 1.2.3.4"
    assert timers.build_label("build:steam:123:456") == "Legacy build 456 · Steam"
    assert timers.build_label("build:purple:A2_LIVE_PURPLE:789") == "Legacy build 789 · PURPLE"
    assert timers.build_label(None) == timers.build_label("") == "Unknown game version"
    assert timers.when_in(NOW, "Asia/Seoul") == "2026-11-21 19:05:00"            # the event's own zone
    assert timers.when_in(NOW, "Mars/Olympus") == when(NOW)                       # a zone that does not read
    assert timers.world_for(2102, "x") == "Zikel" and timers.world_for(" 2102 ", "x") == "Zikel"
    assert timers.world_for(9999, "Server 9999") == "Server 9999" and timers.world_for(None, "none") == "none"
    assert timers.name_key("Argo, the Spirit King") == "argo the spirit king"
    assert [timers.map_faction(m) for m in (1100, 110001, "111999", 1000, 100500, 600001, None, "x")] == [
        "asmodian", "asmodian", "asmodian", "elyos", "elyos", None, None, None]


def test_an_events_window_its_entry_and_its_next_start():
    (item,) = timers.prepare(ONE, "test", "", NOW)
    assert timers.schedule_line(item, "") == "Daily · 10:00 · UTC"
    assert timers.forecast_note(item["event"]) == "Community forecast — not live status."
    state = timers.card_state(item, NOW)                                          # 10:05, entry open till 10:10
    assert state["status"] == "Forecast: entry window" and state["countdown"] == "00:05:00"
    later = timers.card_state(item, NOW + 15 * 60_000)                           # 10:20: in, but the entry closed
    assert later["status"] == "Forecast: event window; entry closed" and later["countdown"] == "00:40:00"
    before = timers.card_state(item, NOW - 65 * 60_000)                          # 09:00
    assert before["status"] == "Next scheduled start" and before["countdown"] == "01:00:00"
    assert before["next"] == f"Next: {local(2026, 11, 21, 10)} local · 2026-11-21 10:00:00 (UTC)"
    assert before["upcoming"] == "Upcoming local starts: " + " · ".join(
        local(2026, 11, day, 10) for day in (21, 22, 23))
    plain = dict(item, event={**item["event"], "entry_minutes": 0})
    assert timers.card_state(plain, NOW)["status"] == "Forecast: scheduled window"
    assert timers.card_state({**item, "times": []}, NOW)["countdown"] == "No upcoming start in the calculated horizon"
    assert timers.prepare(ONE, "", "", NOW) is None and timers.prepare(ONE, "mars", "", NOW) is None


def test_the_catalogs_events_by_region_and_korean_matching_group():
    europe = timers.prepare(CATALOG, "eu", "", NOW)
    assert len(europe) == 9 and not any(item["unavailable"] for item in europe)
    rift = europe[0]
    assert timers.schedule_line(rift, "").startswith("Daily · 02:00, 05:00, 08:00") and rift["zone"] == "Europe/Berlin"
    assert timers.forecast_note(rift["event"]).startswith("Conflicting community reports")
    korea = timers.prepare(CATALOG, "kr", "", NOW)
    assert [item["event"]["id"] for item in korea if item["unavailable"]] == ["siege", "siege-bosses", "nahma"]
    siege = next(item for item in korea if item["event"]["id"] == "siege")
    assert siege["times"] == [] and timers.schedule_line(siege, "") == (
        "Wed, Sat · group time unavailable · Asia/Seoul · matching group unknown")
    grouped = next(item for item in timers.prepare(CATALOG, "kr", "2", NOW) if item["event"]["id"] == "siege")
    assert not grouped["unavailable"] and timers.schedule_line(grouped, "2") == (
        "Wed, Sat · 21:50 · Asia/Seoul · matching group 2")
    festival = next(item for item in europe if item["event"]["id"] == "festival")
    assert timers.schedule_line(festival, "") == "Daily · hourly at :00 · Europe/Berlin"
    assert timers.source_line(CATALOG) == (
        "Shugo.GG community schedule · source updated 2026-10-05 · checked 2026-11-04 · review after 2026-11-18.")
    assert timers.clock_line(CATALOG, NOW).endswith("Schedule review is overdue; forecasts may be stale.")
    assert timers.clock_line(ONE, NOW) == f"Device time: {when(NOW)} · local zone {timers.system_zone()}."
    assert timers.utc_day(NOW) == "2026-11-21"


def test_the_respawn_reference_by_zone():
    groups = timers.boss_groups(FIELD)
    assert [(key, len(rows), opened) for key, _title, rows, opened in groups] == [
        ("elyos", 24, False), ("asmodian", 24, False), ("abyss", 6, True)]       # the Abyss open
    assert timers.group_title("Abyss · Chaotic Lower Reshanta", groups[2][2]) == "Abyss · Chaotic Lower Reshanta · 6 bosses"
    assert timers.group_title("X", [1]) == "X · 1 boss"
    found = timers.boss_groups(FIELD, "  GARTUA ")
    assert [key for key, *_ in found] == ["elyos", "asmodian"] and all(opened for *_, opened in found)
    assert timers.boss_groups(FIELD, "no such boss") == [] and timers.boss_groups(None) == []
    kernon = FIELD["bosses"][0]
    assert timers.respawn_line(kernon) == "Respawn ~30m after kill"
    assert timers.respawn_line({"respawn_minutes": 660, "checked_in_game": True}) == "Respawn ~11h after kill · checked in game"
    assert timers.respawn_line({"schedule": "Daily at 22:30"}) == "Daily at 22:30"
    assert timers.respawn_line({}) == "Schedule unknown"


def test_a_kills_boss_zone_and_return():
    gartua = KILLS["kills"][0]
    entry = timers.boss_entry(gartua, FIELD)                                     # listed in both zones: the map says
    assert entry["faction"] == "asmodian" and entry["zone"]
    reference = {"bosses": [{"name": "Twin", "faction": "elyos", "zone": "Verteron · A", "respawn_minutes": 30},
                            {"name": "Twin", "faction": "asmodian", "zone": "Altgard · B", "respawn_minutes": 45}]}
    assert timers.boss_entry({"boss": "Twin", "map_id": 1100}, reference) == {
        "faction": "asmodian", "zone": "Altgard · B", "respawn_minutes": 45}
    assert timers.boss_entry({"boss": "Twin"}, reference) == {                   # no map: both rows, as the Abyss
        "faction": "abyss", "zone": "Verteron · A / Altgard · B", "respawn_minutes": None}
    lone = {"bosses": [{"name": "Lone", "faction": "abyss", "zone": "Reshanta", "respawn_minutes": None}]}
    assert timers.boss_entry({"boss": "Lone", "map_id": 1000}, lone) == {        # a namesake elsewhere: the map wins
        "faction": "elyos", "zone": "Verteron", "respawn_minutes": None}
    assert timers.boss_entry({"boss": "Nobody"}, None) == {"faction": None, "zone": "", "respawn_minutes": None}
    kernon = KILLS["kills"][1]
    entry = timers.boss_entry(kernon, FIELD)
    assert entry["respawn_minutes"] == 30 and timers.kill_back(kernon, entry) == kernon["killed_at"] + 1800
    assert timers.kill_basis(kernon, entry) == "community respawn reference 30m (unverified)"
    assert timers.kill_summary(kernon, entry) == (
        f"Kernon of the West · {entry['zone']} · killed {when(kernon['killed_at'] * 1000)} · 1 uploader")
    argo = KILLS["kills"][2]
    argo_entry = {"faction": "abyss", "zone": "Reshanta", "respawn_minutes": None}
    assert timers.kill_back(argo, argo_entry) == argo["respawn_at"]
    assert timers.kill_basis(argo, argo_entry) == "respawn about 12:00:00, measured from 3 gaps between kills"
    assert timers.kill_back({"killed_at": 1}, argo_entry) is None
    at = SECONDS + 300
    assert timers.back_text(at, NOW) == f"Expected back within 00:05:00 ({when(at * 1000)})"
    assert timers.back_text(at, at * 1000 + 1) == f"Expected back since {when(at * 1000)}"
    assert timers.kill_summary({"boss": "X", "killed_at": 0, "reports": 3}, {"zone": ""}).endswith(" · 3 uploaders")


def test_the_kills_by_server_and_faction():
    kills = timers.kills_of(KILLS)
    assert len(kills) == 4                                                        # one without a time left out
    one = timers.world_for(1101, "Server 1101")
    assert timers.servers(kills, "") == sorted([("2102", "Zikel"), ("1101", one)], key=lambda pair: pair[1].casefold())
    listed = dict(timers.servers(kills, "9999"))
    assert listed["9999"] == "Server 9999 · no recent kills" and listed["2102"] == "Zikel"
    assert timers.server_label({"server": 2102, "region": "eu"}) == "Zikel · EU"
    assert timers.server_label({"server": 9999}) == "Server 9999"
    every = timers.kill_rows(kills, "2102", "", FIELD)
    assert [k["boss"] for k in every] == ["Eternal Gartua", "Kernon of the West", "Argo, the Spirit King"]
    asmodian = timers.kill_rows(kills, "2102", "asmodian", FIELD)
    assert [k["boss"] for k in asmodian] == ["Eternal Gartua", "Argo, the Spirit King"]   # and the Abyss
    assert timers.wanted_faction("mine", IDENTITY) == "asmodian" and timers.wanted_faction("mine", None) == ""
    assert timers.wanted_faction("all", IDENTITY) == "" and timers.wanted_faction("elyos", IDENTITY) == "elyos"
    assert timers.kills_status(KILLS, "2102", asmodian, 2) == (
        f"2 bosses with a recorded kill in the last 48 hours. Snapshot {when(NOW)}.")
    assert timers.kills_status(KILLS, "", [], 2) == "2 servers have recorded kills. Choose yours."
    assert timers.no_kills("2102", [], "elyos") == (
        "No kills recorded for this server in elyos zones or the Abyss yet. They come from public Live Meter logs "
        "uploaded by players there.")
    assert timers.no_kills("2102", [1], "") == timers.no_kills("", [], "") == ""
    assert timers.identity_line(IDENTITY, "mine").startswith("Identified from your live meter: Tester on Zikel · Asmodian.")
    assert "faction not resolved yet" in timers.identity_line({"server": 2102}, "all")
    assert timers.identity_line(None, "mine").startswith("Start the live meter")
    assert timers.identity_line(None, "elyos") == ""


def test_a_source_log_links_to_the_web_interface():
    assert timers.log_page("abcDEF1234") == "combat-log/shared/abcDEF1234?mode=pve"
    assert timers.log_page("abcDEF1234", 2) == "combat-log/shared/abcDEF1234?mode=pve&segment=2"
    assert timers.log_page("bad id") == timers.log_page("abc") == timers.log_page(None) == ""
    assert 'href="web:combat-log/shared/abcDEF1234?mode=pve&amp;segment=1"' in timers.source_link("abcDEF1234", 1)
    assert "Source log · encounter 2" in timers.source_link("abcDEF1234", 1)
    assert timers.source_link("bad id") == "Source unavailable"
    sources = timers.kill_sources(KILLS["kills"][0])
    assert sources.startswith(f"Previous kill {when((SECONDS - 13 * 3600) * 1000)} · ") and "Source log" in sources
    assert timers.kill_sources({"logs": ["bad!", "abcDEF1234", "abcDEF1235", "abcDEF1236"]}).count(" · ") == 2


def test_the_recorded_defeats():
    rows = timers.defeat_rows(DEFEATS)
    assert [g["boss"] for g in rows] == ["Atiel", "Orissan"]
    assert [g["boss"] for g in timers.defeat_rows(DEFEATS, "2340700")] == ["Orissan"]   # by its NPC id
    assert len(timers.defeat_rows({"groups": [{"boss": str(n), "npc_id": n} for n in range(40)]})) == 25
    assert timers.defeats_status(DEFEATS, rows) == (
        f"2 displayed groups (up to 25). Snapshot {when(NOW)}. Server results capped. Search filters the returned snapshot.")
    assert timers.defeat_summary(DEFEATS["groups"][0]) == f"Atiel · eu · {when((SECONDS - 7200) * 1000)}"
    assert timers.defeat_summary(DEFEATS["groups"][1]) == "Orissan · Unknown region · Time unavailable"
    detail = timers.defeat_detail(DEFEATS["groups"][0])
    assert detail.startswith("4 observations · Product version 1.2.3.4 · NPC 2340601 · map 600001 / instance 12. ")
    assert timers.defeat_detail(DEFEATS["groups"][1]).startswith(
        "0 observations · Unknown game version · NPC 2340700 · map unknown / instance unknown. Source unavailable")
    first, second = timers.defeat_history(DEFEATS["groups"][0])
    assert first.startswith(f"{when((SECONDS - 7200) * 1000)} · 8 engaged · boss HP reached zero · ")   # its clock unsaid
    assert second.startswith("Time unavailable · 0 engaged · Evidence unavailable · upload_time · Source unavailable")
    assert timers.defeat_history(DEFEATS["groups"][1]) is None                    # an older log server
    assert timers.omitted_line(DEFEATS["groups"][0]) == "3 earlier observations omitted."


# ------------------------------------------------------------------ the page
class FakeApp:
    """The app as the page asks it: its settings, the bundled catalogs, the live meter and the log server."""

    def __init__(self, ui=None, identity=IDENTITY, kills=KILLS, defeats=DEFEATS, fail=()):
        self.ui = dict(ui or {"event_region": "eu", "event_group": ""})
        self.identity, self.kills, self.defeats, self.fail = identity, kills, defeats, set(fail)
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        if path == "/api/ui":
            return dict(self.ui)
        if path.startswith("/static/"):
            if "catalog" in self.fail and "event-schedules" in path:
                raise OSError("the schedule file is missing")
            with open(os.path.join(STATIC, path.split("/static/", 1)[1]), encoding="utf-8") as file:
                return json.load(file)
        if path == "/api/meter?view=latest":
            return {"running": False, "snapshot": {"field_bosses": self.identity} if self.identity else {}}
        assert path.startswith("/api/community?path=")
        inner = urllib.parse.unquote(path.split("=", 1)[1])
        if "boss-kills" in inner:
            if "kills" in self.fail:
                raise OSError("the log server did not answer")
            return self.kills
        assert inner.startswith("/api/v1/boss-status?")
        if "defeats" in self.fail:
            raise OSError("the log server did not answer")
        return self.defeats

    def post(self, path, payload):
        self.calls.append(("POST", path, payload))
        self.ui.update(payload)
        return {"ok": True}


def _page(app: FakeApp, clock=None, **kwargs) -> TimersPage:
    clock = clock if clock is not None else {"now": NOW}
    opened, links = [], []
    page = TimersPage(app, open_web=opened.append, open_link=links.append, now=lambda: clock["now"], **kwargs)
    page.opened, page.links, page.clock_ = opened, links, clock
    page.resize(1040, 900)
    page.show()
    settle(lambda: page.catalog is not None and page.field_catalog is not None, timeout=10)
    QCoreApplication.processEvents()
    return page


def test_the_page_reads_the_region_and_schedules_once_shown_and_counts_down(qapp):
    app = FakeApp()
    page = TimersPage(app, open_web=lambda page: None, open_link=lambda url: None)
    assert app.calls == [] and not page.loading.isHidden()                        # nothing before it is shown
    page = _page(app)
    assert app.calls[:4] == [("GET", "/api/ui"), ("GET", "/static/event-schedules.json"),
                             ("GET", "/static/field-bosses.json"), ("GET", "/api/meter?view=latest")]
    assert page.loading.isHidden() and all(not section.isHidden() for section in page.sections)
    assert page.region_box.currentData() == "eu" and page.group_box.isHidden()
    assert page.events_note.text() == CATALOG["note"] and timers.source_line(CATALOG) in page.source.text()
    assert len(page.cards) == 9 and page.event_grid.columns == 3 and page.no_region.isHidden()
    card = page.cards[0]
    assert card.name.text() == "Spacetime Rift" and card.status.text() == "Forecast: entry window"   # 11:05 in Berlin
    first = card.countdown.text()
    assert first == "00:05:00"
    assert page.clock.isActive()                                                  # it counts while shown
    page.clock_["now"] += 1000
    page.tick()
    assert card.countdown.text() != first and page.clock_line.text().startswith(f"Device time: {when(NOW + 1000)}")
    page.hide()
    assert not page.clock.isActive()                                              # and not while hidden
    page.source.linkActivated.emit(timers.SCHEDULE_SOURCE)
    assert page.links == [timers.SCHEDULE_SOURCE]                                 # the sources in the browser


def test_choosing_a_region_and_a_korean_group_keeps_them_and_works_the_schedule_out(qapp):
    app = FakeApp(ui={"event_region": "", "event_group": ""})
    page = _page(app)
    assert page.region_box.currentData() == "" and not page.no_region.isHidden()
    assert page.no_region.text() == timers.NO_REGION and page.cards == []
    page.region_box.setCurrentIndex(page.region_box.findData("kr"))
    assert ("POST", "/api/ui", {"event_region": "kr", "event_group": ""}) in app.calls   # the overlay reads it too
    assert not page.group_box.isHidden() and len(page.cards) == 9
    waiting = [card for card in page.cards if card.item["unavailable"]]
    assert len(waiting) == 3 and all(not card.unavailable.isHidden() and card.countdown.isHidden() for card in waiting)
    page.group_box.setCurrentIndex(page.group_box.findData("2"))
    assert ("POST", "/api/ui", {"event_region": "kr", "event_group": "2"}) in app.calls
    assert not any(card.item["unavailable"] for card in page.cards)
    siege = next(card for card in page.cards if card.item["event"]["id"] == "siege")
    assert siege.schedule.text() == "Wed, Sat · 21:50 · Asia/Seoul · matching group 2"
    page.clock_["now"] += 24 * 3600 * 1000                                        # a new day: worked out afresh
    page.tick()
    assert page.prepared_day == "2026-11-22"


def test_the_respawn_reference_opens_by_zone_and_is_searched(qapp):
    page = _page(FakeApp())
    assert page.reference_loading.isHidden() and page.reference_note.text() == FIELD["note"]
    titles = [fold.button.text() for fold in page.reference_folds]
    assert titles == ["Verteron · Elyos · 24 bosses", "Altgard · Asmodian · 24 bosses",
                      "Abyss · Chaotic Lower Reshanta · 6 bosses"]
    assert [fold.body.isHidden() for fold in page.reference_folds] == [True, True, False]
    page.reference_folds[0].button.click()
    assert not page.reference_folds[0].body.isHidden()
    page.reference_search.setText("gartua")
    assert [fold.body.isHidden() for fold in page.reference_folds] == [False, False]
    page.reference_search.setText("no such boss")
    assert page.reference_folds == [] and not page.reference_empty.isHidden()


def test_the_kills_of_your_server_load_as_the_live_meter_tells_it(qapp):
    app = FakeApp()
    page = _page(app)
    settle(lambda: page.kill_data is not None)                                    # asked for by itself
    assert page.identity.text().startswith("Identified from your live meter: Tester on Zikel · Asmodian.")
    assert page.server_box.currentData() == "2102" and page.server_box.itemText(0) == "Choose a server"
    titles = [fold.button.text() for fold in page.kill_folds]
    assert len(titles) == 2 and titles[0].startswith("Eternal Gartua") and titles[1].startswith("Argo, the Spirit King")
    assert page.kills_status.text().startswith("2 bosses with a recorded kill in the last 48 hours.")
    page.faction_box.setCurrentIndex(page.faction_box.findData("all"))
    assert len(page.kill_folds) == 3 and page.identity.text().startswith("Identified")
    kernon = page.kill_folds[1]
    (label, back, basis) = next(entry for entry in page.backs if entry[0].parent() is kernon.body)
    assert basis == "community respawn reference 30m (unverified)"
    assert label.text().startswith("Expected back within 00:20:00")             # killed 10 minutes ago
    page.clock_["now"] += 60_000
    page.tick()
    assert label.text().startswith("Expected back within 00:19:00")
    gartua = page.kill_folds[0]
    source = [child for child in gartua.body.findChildren(type(label)) if "Source log" in child.text()][0]
    source.linkActivated.emit("web:combat-log/shared/abcDEF1234?mode=pve")
    assert page.opened == ["combat-log/shared/abcDEF1234?mode=pve"]                # in the web interface
    page.server_box.setCurrentIndex(page.server_box.findData("1101"))
    assert len(page.kill_folds) == 1 and page.kill_server == "1101"
    page.faction_box.setCurrentIndex(page.faction_box.findData("asmodian"))
    assert page.kill_folds == [] and page.no_kills.text().startswith("No kills recorded for this server in asmodian")
    page.kills_button.click()
    settle(lambda: page.kills_button.isEnabled())
    assert len([call for call in app.calls if "boss-kills" in urllib.parse.unquote(call[1])]) == 2


def test_without_the_live_meter_the_kills_wait_for_the_button_and_say_what_failed(qapp):
    app = FakeApp(identity=None, fail={"kills"})
    page = _page(app)
    assert page.identity.text().startswith("Start the live meter") and page.kill_data is None
    assert page.kills_status.text() == "Load to retrieve recent kills from the community server."
    page.kills_button.click()
    settle(lambda: page.kills_button.isEnabled() and "Could not" in page.kills_status.text())
    assert page.kills_status.text() == "Could not load kills: the log server did not answer"
    page = _page(FakeApp(identity=None, kills={"error": "No log server is set"}))
    page.kills_button.click()
    settle(lambda: "Could not" in page.kills_status.text())
    assert page.kills_status.text() == "Could not load kills: No log server is set"
    page = _page(FakeApp(identity=None, kills={"nothing": True}))
    page.kills_button.click()
    settle(lambda: "Could not" in page.kills_status.text())
    assert page.kills_status.text() == "Could not load kills: The community server does not offer kills yet."
    page.kill_server = ""
    page.kill_data = KILLS
    page._show_kills()
    assert page.kills_status.text().startswith("2 servers have recorded kills. Choose yours.")


def test_the_recorded_defeats_load_by_region_and_are_searched(qapp):
    app = FakeApp()
    page = _page(app)
    assert page.defeats_status.text() == "Load to retrieve public observations from the community server."
    page.defeats_region.setText("eu")
    page.defeats_button.click()
    settle(lambda: page.boss_data is not None)
    asked = [urllib.parse.unquote(call[1]) for call in app.calls if "boss-status" in urllib.parse.unquote(call[1])]
    assert asked == ["/api/community?path=/api/v1/boss-status?region=eu"]
    assert [fold.button.text() for fold in page.defeat_folds] == [
        timers.defeat_summary(DEFEATS["groups"][0]), "Orissan · Unknown region · Time unavailable"]
    assert page.defeats_status.text().startswith("2 displayed groups (up to 25).")
    assert page.defeats_note.text() == DEFEATS["note"] and not page.defeats_note.isHidden()
    texts = [label.text() for label in page.defeat_folds[0].body.findChildren(type(page.defeats_note))]
    assert "Recent retained observations" in texts and "3 earlier observations omitted." in texts
    older = [label.text() for label in page.defeat_folds[1].body.findChildren(type(page.defeats_note))]
    assert "Update the community server for recent observation history." in older
    page.defeats_search.setText("orissan")
    assert len(page.defeat_folds) == 1
    page.defeats_search.setText("nobody")
    assert page.defeat_folds == [] and not page.defeats_empty.isHidden()
    browse = [label for label in page.sections[3].findChildren(type(page.defeats_note)) if "Browse combat logs" in label.text()]
    browse[0].linkActivated.emit("web:combat")
    assert page.opened[-1] == "combat"
    failing = _page(FakeApp(fail={"defeats"}))
    failing.defeats_button.click()
    settle(lambda: "Could not" in failing.defeats_status.text())
    assert failing.defeats_status.text() == "Could not load observations: the log server did not answer"


def test_a_schedule_that_cannot_be_read_says_why(qapp):
    page = TimersPage(FakeApp(fail={"catalog"}), open_web=lambda page: None)
    page.show()
    settle(lambda: "Could not" in page.loading.text())
    assert page.loading.text() == "Could not load schedules: the schedule file is missing"
    assert all(section.isHidden() for section in page.sections)


def test_the_window_draws_the_timers_page_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("timers"), TimersPage) and not isinstance(window.page("timers"), WebPage)
    assert isinstance(window.page("maps"), WebPage)                                # not moved over yet
