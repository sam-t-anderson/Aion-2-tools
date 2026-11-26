"""The native overlay's events strip (0.2.419): the next windows of the region picked on the Timers page and the
field bosses the meter's uploaders saw killed, as the web overlay's strip shows them.

The schedule is ``event-schedule.js``'s, ported (``aion2calc/gui/events.py``): it is checked here by hand across a
daylight-saving change and against the web pages' own engine, run in Node where Node is installed. The strip is
checked on the overlay, off screen.
"""
import calendar
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import chime  # noqa: E402
from aion2calc.gui import events  # noqa: E402
from aion2calc.gui.overlay import MeterOverlay  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, settle  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
CATALOG = json.loads((STATIC / "event-schedules.json").read_text(encoding="utf-8"))
RIFT = {"id": "rift", "name": "Spacetime Rift", "hours": [20], "minute": 0, "duration_minutes": 60, "entry_minutes": 10}


def utc(*parts) -> int:
    return calendar.timegm(parts + (0,) * (6 - len(parts))) * 1000


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


def test_an_event_keeps_its_wall_clock_time_across_a_daylight_saving_change():
    # 20:00 in New York is 00:00 UTC under daylight saving, and 01:00 UTC once it ends (1 November 2026)
    times = events.occurrences(RIFT, "America/New_York", utc(2026, 10, 31, 12))
    assert utc(2026, 11, 1, 0) in times and utc(2026, 11, 2, 1) in times
    # 02:30 does not exist the night clocks go forward (8 March 2026), and comes twice the night they go back
    night = {"id": "n", "name": "N", "hours": [2], "minute": 30, "duration_minutes": 10}
    spring = events.occurrences(night, "America/New_York", utc(2026, 3, 8, 12))
    assert [t for t in spring if utc(2026, 3, 8) <= t < utc(2026, 3, 9)] == []
    autumn = events.occurrences({**night, "hours": [1]}, "America/New_York", utc(2026, 11, 1, 12))
    assert [t for t in autumn if utc(2026, 11, 1) <= t < utc(2026, 11, 2)] == [utc(2026, 11, 1, 5, 30),
                                                                                utc(2026, 11, 1, 6, 30)]
    assert events.occurrences(RIFT, "Nowhere/Atlantis", utc(2026, 11, 1)) == []


def test_upcoming_states_the_running_and_the_next_and_their_entry_window():
    catalog = {"regions": [{"id": "na-east", "timezone": "America/New_York"}], "events": [RIFT]}
    at_start = utc(2026, 11, 20, 1, 5)                                         # 20:05 New York: five minutes in
    (state,) = events.upcoming(catalog, "na-east", "", at_start)
    assert state["active"] and state["entry_open"] and state["ends_at"] == utc(2026, 11, 20, 1, 10)   # entry
    (state,) = events.upcoming(catalog, "na-east", "", at_start + 10 * 60_000)
    assert state["active"] and not state["entry_open"] and state["ends_at"] == utc(2026, 11, 20, 2)
    (state,) = events.upcoming(catalog, "na-east", "", utc(2026, 11, 20, 0, 50))
    assert not state["active"] and state["starts_in_ms"] == 10 * 60_000
    assert events.upcoming(catalog, "nowhere", "", at_start) == []
    assert [events.short_countdown(ms) for ms in (0, 45_000, 59_001, 300_000, 3_900_000)] == ["0s", "45s", "1m",
                                                                                            "5m", "1h 05m"]


def test_a_matching_groups_time_and_a_regions_overrides():
    kr = events.resolve_events(CATALOG, "kr", "")
    grouped = [raw["id"] for raw in CATALOG["events"] if raw.get("group_times")
               or (CATALOG["overrides"].get("kr", {}).get(raw["id"], {}).get("group_times"))]
    assert not any(event["id"] in grouped for event, _zone in kr)             # no group picked: left out
    for event, _zone in events.resolve_events(CATALOG, "kr", "2"):
        if event["id"] in grouped:
            assert event["hours"] == [int(event["group_times"][1].split(":")[0])]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node runs the web pages' own engine")
def test_the_schedule_matches_the_web_pages_engine(tmp_path):
    instants = [utc(2026, 10, 28) + i * 389 * 60_000 for i in range(14)] + [
        utc(2026, 11, 1, 5, 30), utc(2026, 11, 1, 6, 1), utc(2026, 3, 8, 6, 45), utc(2026, 10, 25, 1, 0, 30)]
    harness = tmp_path / "upcoming.js"
    harness.write_text("""
        const fs = require("fs"); global.window = {}; global.localStorage = {getItem: () => null};
        eval(fs.readFileSync(process.argv[2], "utf8"));
        const catalog = JSON.parse(fs.readFileSync(process.argv[3], "utf8")), out = [];
        for (const now of JSON.parse(process.argv[4])) for (const r of catalog.regions) for (const g of ["", "1", "3"])
          out.push(window.A2EventSchedule.upcoming(catalog, r.id, g, now));
        console.log(JSON.stringify(out));""", encoding="utf-8")
    web = json.loads(subprocess.run(["node", str(harness), str(STATIC / "event-schedule.js"),
                                     str(STATIC / "event-schedules.json"), json.dumps(instants)],
                                    capture_output=True, text=True, check=True, timeout=60).stdout)
    ours = [events.upcoming(CATALOG, region["id"], group, now)
            for now in instants for region in CATALOG["regions"] for group in ("", "1", "3")]
    keys = (("id", "id"), ("active", "active"), ("entryOpen", "entry_open"), ("endsAt", "ends_at"), ("next", "next"),
            ("startsInMs", "starts_in_ms"), ("zone", "zone"))
    assert len(web) == len(ours)
    for theirs, mine in zip(web, ours):
        assert [[state[k] for k, _ in keys] for state in theirs] == [[state[k] for _, k in keys] for state in mine]


def _overlay(**ui):
    window = MeterOverlay(None)
    window._catalog = CATALOG
    window.events_clock = lambda: window.now
    window.now = utc(2026, 11, 20, 0, 50)                                      # 19:50 in New York
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(fight())
    return window


def test_the_strip_shows_the_next_three_windows_of_the_picked_region(qapp):
    window = _overlay(event_region="na-east", overlay_width=800)               # room for all three, in any font
    shown = events.strip(CATALOG, "na-east", "", None, window.now)
    assert not window.events.isHidden() and len(shown) <= 3
    assert window.events.text() == events.strip_html(shown)
    assert [event["text"] for event in shown][:1] == ["Spacetime Rift in 10m"]
    assert "community forecast (America/New_York), not live status" in window.events.toolTip()
    window.now = utc(2026, 11, 20, 1, 5)                                       # 20:05: the rift's entry is open
    window.render_events()
    assert "Spacetime Rift <b style='color:#8fd0a0'>entry 5m</b>" in window.events.text()
    window.apply_ui({"overlay_width": 340, "event_region": "na-east", "overlay_show_events": False})
    assert window.events.isHidden()
    window.apply_ui({"overlay_width": 340})                                    # no region picked on the Timers page
    assert window.events.isHidden()


def test_observed_field_boss_kills_join_the_strip(qapp):
    window = _overlay()
    meter = fight()
    meter["snapshot"]["field_bosses"] = {"faction": "elyos", "server": 2001, "server_name": "Siel", "kills": [
        {"boss": "Kromede", "zone": "Verteron", "killed_at": window.now / 1000 - 3600, "expected_at": window.now / 1000 + 300,
         "reports": 2, "respawn_basis": "measured"},
        {"boss": "Bakarma", "zone": "", "killed_at": window.now / 1000 - 7200, "expected_at": window.now / 1000 - 60,
         "reports": 1, "respawn_basis": "reference", "respawn_minutes": 120},
        {"boss": "Later", "killed_at": 0, "expected_at": window.now / 1000 + 3600}]}
    window.apply_meter(meter)
    window.render_events()
    text = window.events.text()
    assert "Bakarma <b style='color:#f0c36a'>now</b>" in text and "Kromede <b style='color:#e3ad7f'>back in 5m</b>" in text
    assert "Later" not in text                                                 # due in an hour: not yet
    window.apply_ui({"overlay_width": 260, "event_region": "na-east"})         # narrow: the line keeps what fits
    assert window.events.text().endswith(" …") and "Kromede" in window.events.toolTip()
    assert ("Kromede — observed kill 1h 00m ago by 2 uploaders on Siel (live meter recordings, not Discord timers); "
            "respawn measured from repeated kills · Verteron") in window.events.toolTip()
    window.apply_ui({"overlay_width": 340, "overlay_show_field_bosses": False})
    assert window.events.isHidden()


def _chimes(monkeypatch, tmp_path):
    """The chimes played (whether with the uploaded sound) and the system's alerts sounded, the claims in ``tmp_path``."""
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    played, beeps = [], []
    monkeypatch.setattr(chime, "play", lambda custom_sound=False, home=None: played.append(custom_sound))
    monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    return played, beeps


def test_a_new_event_chimes_once_with_the_chime_on(qapp, monkeypatch, tmp_path):
    """The web page's chime (gui/chime.py), not the system's alert: until 0.2.513 Windows' "Default Beep" rang for every
    event entering the strip."""
    played, beeps = _chimes(monkeypatch, tmp_path)
    window = _overlay(event_region="na-east", overlay_events_sound=True)
    assert played == []                                                        # the first reading primes it
    window.now = utc(2026, 11, 20, 1, 0, 30)                                   # the rift opened, the festival began
    window.render_events()
    assert played == [False]                                                   # the built-in chime: no sound uploaded
    window.render_events()
    assert played == [False]
    window.apply_ui({"overlay_width": 340, "event_region": "na-east"})         # the chime off
    window.now = utc(2026, 11, 20, 1, 20)
    window.render_events()
    assert played == [False] and beeps == []


def test_the_meter_overlay_and_the_party_window_chime_once_between_them(qapp, monkeypatch, tmp_path):
    """Each overlay window is a process of its own and both show the strip: the first to see a new event claims it, and
    the other stays quiet (0.2.513; until then each rang the system's alert)."""
    from aion2calc.gui.companions import PartyWindow
    from test_native_overlay_companions import _store
    played, beeps = _chimes(monkeypatch, tmp_path)
    sound = {"event_region": "na-east", "overlay_events_sound": True, "overlay_events_sound_set": True}
    meter = _overlay(**sound)
    party = PartyWindow(None, store=_store())
    party._catalog = CATALOG
    party.events_clock = lambda: meter.now
    party.apply_ui({"overlay_width": 340, **sound})
    party.apply_meter(fight())
    assert not party.events.isHidden() and played == []                       # both show it; each primed silently
    meter.now = utc(2026, 11, 20, 1, 0, 30)
    meter.render_events()
    party.render_events()
    assert played == [True] and beeps == []                                    # your sound, once


class CatalogApp(FakeApp):
    """The app with its event schedule, as it serves the web pages' static files."""

    def _answer(self, method, path, payload):
        answer = super()._answer(method, path, payload)
        return CATALOG if path == "/static/event-schedules.json" else answer


def test_the_overlay_asks_the_app_for_the_schedule(qapp):
    api = CatalogApp(fight())
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, "event_region": "eu"})
    settle(lambda: window._catalog is not None)
    assert [call for call in api.calls if call[1] == "/static/event-schedules.json"] == [
        ("GET", "/static/event-schedules.json", None)]
    window.apply_ui({"overlay_width": 340, "event_region": "eu"})
    assert len([call for call in api.calls if call[1] == "/static/event-schedules.json"]) == 1   # once
