"""The native Maps page (0.2.433): the Abyss PvP heat map and the farming routes as the web page shows them
(static/maps.js, ``A2Maps``), off screen; not the web page's interactive maps (0.2.512). The heat map is the sample the browser tests serve
(tests/browser/community.py) and the routes are the app's bundled catalog. ``gui/maps.py``'s words and steps were
checked against maps.js's own functions; these tests pin what they give.
"""
import json
import os
import pathlib
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget, QToolButton  # noqa: E402

from aion2calc.gui import maps as m  # noqa: E402
from aion2calc.gui.maps_page import MapsPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
from test_native_overlay_toolbar import settle  # noqa: E402
from community import HEAT, NOW, _heat  # noqa: E402

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
ROUTES = json.loads((STATIC / "farming-routes.json").read_text(encoding="utf-8"))
NAE1, NAE2 = (_heat({"matchup": [name]}) for name in ("nae-1", "nae-2"))


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
    """The app as the page asks it: its route catalog, and the log server's heat map through its proxy (``heat``
    stands in for the answer, an exception for a refusal)."""

    def __init__(self, heat=None, routes_fail=False):
        self.heat, self.routes_fail, self.calls, self.asked = heat, routes_fail, [], []

    def get(self, path):
        self.calls.append(path)
        if path == "/static/farming-routes.json":
            if self.routes_fail:
                raise OSError("HTTP 404")
            return ROUTES
        assert path.startswith("/api/community?path=")
        asked = urllib.parse.unquote(path[len("/api/community?path="):])
        self.asked.append(asked)
        if isinstance(self.heat, Exception):
            raise self.heat
        return self.heat if self.heat is not None else _heat(urllib.parse.parse_qs(urllib.parse.urlparse(asked).query))


def _store(**values):
    """The interface data of a page of its own, as the app gives it (each value a text)."""
    from aion2calc.gui import interface
    store = interface.InterfaceStore(shared=interface._Shared())
    for key, value in values.items():
        store.setValue(key, value)
    return store


def _page(api=None, **kwargs):
    kwargs.setdefault("store", _store())
    page = MapsPage(api if api is not None else FakeApp(), now=lambda: NOW, **kwargs)
    page.resize(1100, 1400)
    page.show()
    settle(lambda: (page.routes is not None or page.route_body.count() and "Route catalog unavailable" in
                    page.route_body.itemAt(0).widget().text()) and (page.heat is not None or page.refresh.isEnabled()))
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    QCoreApplication.processEvents()
    return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)


def _move(widget, x, y):
    event = QMouseEvent(QEvent.MouseMove, QPointF(x, y), QPointF(x, y), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(widget, event)


def test_the_heat_maps_words_and_geometry():
    assert [m.num(x) for x in (0, 999, 1000, 1234567, -4000, 2.5, 1.0005, None)] == [
        "0", "999", "1,000", "1,234,567", "-4,000", "2.5", "1.001", "0"]
    assert m.plural(1, "hit", "hits") == "1 hit" and m.plural(31, "hit", "hits") == "31 hits"
    assert m.heat_path(2000) == "/api/v1/pvp-heat?map=20&cell=2000"
    assert m.heat_path(4000, "nae-1") == "/api/v1/pvp-heat?map=20&cell=4000&matchup=nae-1"
    assert [m.heat_step(h, 31) for h in (1, 2, 3, 6, 10, 20, 31)] == [0, 1, 1, 2, 3, 4, 4]
    assert m.heat_step(1, 1) == 4 and m.heat_step(5, 0) == 4
    assert m.matchup_name(None) == "every server" and m.matchup_name(NAE1["matchup"]) == "Israphel vs Zikel (NA East)"
    assert m.matchup_groups(HEAT) == [("NA East", [("nae-1", "Israphel vs Zikel · last 24 h"),
                                                   ("nae-2", "Siel vs Nezekan · too few uploaders yet")]),
                                      ("", [("all", "Every server, pooled")])]
    assert m.busiest(HEAT) == "nae-1" and m.busiest({**HEAT, "matchups": []}) == "all"
    assert m.chosen("nae-2", HEAT) == "nae-2" and m.chosen("gone", HEAT) == m.chosen("", HEAT) == "all"
    shown_at = m.when(NOW * 1000)
    assert m.status_line(NAE1, NOW) == (
        "Israphel vs Zikel (NA East), the last 24 hours: 9 fights from 4 uploaders, 57 PvP hits and 3 kills in 3 squares "
        f"(1 square only one uploader recorded is left out). Updated {shown_at}.")
    assert m.status_line(_heat({}), NOW).startswith("Every server, the last 24 hours: 9 fights")
    assert m.status_line(NAE2, NOW) == (
        "Not enough recorded Abyss PvP for Siel vs Nezekan (NA East) yet: the map needs fights from at least 3 uploaders "
        "within 7 days, and has 1 uploader. Public Live Meter logs of Abyss fights add to it. Meanwhile the map shows "
        "the ground recordings have covered.")
    assert m.failure("not found") == m.failure("HTTP 404") == m.NOT_OFFERED
    assert m.failure("timed out") == "The PvP heat map could not be loaded: timed out"
    assert m.described(NAE1) == ("Abyss PvP heat map of Israphel vs Zikel (NA East): 3 squares with PvP over the last 24 "
                                 "hours, the busiest with 31 hits. The table below lists them.")
    rows, more = m.busiest_squares(NAE1)
    assert rows[0] == ["4,000 to 6,000", "-4,000 to -2,000", "31", "2"] and len(rows) == 3 and more == ""
    many = {**NAE1, "cells": [[x, 0, x + 1, 0] for x in range(30)]}
    assert len(m.busiest_squares(many)[0]) == 25 and m.busiest_squares(many)[1] == "The 25 busiest of 30 squares."
    assert m.refresh_ms(NAE1) == 900000 and m.refresh_ms({"refresh_seconds": 60}) == 300000 and m.refresh_ms(None) == 900000
    # where things are drawn: 12,000 units each way in a frame 1,000 px wide and a window 900 tall
    view = m.view(NAE1, 1000, 900)
    assert view["h"] == 648 and view["w"] == 648 and view["ox"] == 176 and view["s"] == pytest.approx(624 / 12000)
    x, y, z = m.box(view, 2, -2)
    assert (x, y, z) == (pytest.approx(176 + 12 + 4000 * view["s"]), pytest.approx(12 + 6000 * view["s"]), pytest.approx(104))
    assert m.under(view, NAE1, x + z / 2, y + z / 2) == ("cell", [2, -2, 31, 2])
    boss = m.at(view, 9000, -1000)
    assert m.under(view, NAE1, boss[0] + 5, boss[1]) == ("boss", HEAT["landmarks"][0]) and m.under(view, NAE1, 200, 30) is None
    assert m.tip(NAE1, ("cell", [2, -2, 31, 2])) == ("31 PvP hits", "2 kills", "x 4,000 to 6,000 · y -4,000 to -2,000")
    assert m.tip(NAE1, ("cell", [2, -1, 6, 0]))[1] == "no kills"
    assert m.tip(NAE1, ("boss", HEAT["landmarks"][0])) == ("Testboss Gamma", "a recorded boss", "x 9,000 · y -1,000")
    assert m.view({**NAE1, "bounds": None}, 1000, 900) is None


def test_the_routes_words():
    verteron = ROUTES["zones"][0]
    cubes = verteron["routes"][0]
    source = ROUTES["sources"][cubes["source"]]
    assert [m.zone_label(z) for z in ROUTES["zones"]] == ["Verteron (elyos)", "Altgard (asmodian)",
                                                         "Chaotic Lower Reshanta (Abyss)", "Poeta (elyos)", "Ishalgen (asmodian)"]
    assert m.route_summary(cubes) == ("Hidden Cube loop · 118 Hidden Cubes · 41 legs · starts in Aullaeu Funeral Island "
                                      "(near a teleport)")
    assert m.leg_line(cubes, cubes["legs"][0]).startswith("Aullaeu Funeral Island — 2 Hidden Cubes <span")
    assert "(waypoints 1–2)" in m.leg_line(cubes, cubes["legs"][0])
    single = next(leg for leg in cubes["legs"] if leg["count"] == 1)
    assert "— 1 Hidden Cube <span" in m.leg_line(cubes, single) and f"(waypoint {single['from']})" in m.leg_line(cubes, single)
    text = m.route_text(verteron, cubes, source).split("\n")
    assert text[0] == "Verteron · Hidden Cube loop · 118 Hidden Cubes" and text[3] == "" and len(text) == 4 + 118
    assert text[1] == f"Source: {source['name']} ({source['license']}, {source['url']}, commit {source['revision'][:12]})"
    assert text[4] == "1. Aullaeu Funeral Island (2785, 3408)"
    assert m.route_text(verteron, {**cubes, "source": "elsewhere"}, None).split("\n")[1] == "Source: elsewhere"
    assert f"href='{source['url']}'" in m.source_line(cubes, source) and f"commit {source['revision'][:12]}" in m.source_line(cubes, source)
    assert m.catalog_line(ROUTES) == f"{ROUTES['note']} Catalog built {m.when(ROUTES['generated_at'])}."


def test_the_page_reads_the_routes_and_the_busiest_matchups_heat_map(qapp):
    app = FakeApp()
    page = MapsPage(app, now=lambda: NOW, store=_store())
    assert app.calls == []
    page.resize(1100, 1400)
    page.show()
    settle(lambda: page.heat is not None and page.routes is not None)
    QCoreApplication.processEvents()
    # no matchup chosen yet: every server's answer names the busiest, which is asked for
    assert app.asked == ["/api/v1/pvp-heat?map=20&cell=2000", "/api/v1/pvp-heat?map=20&cell=2000&matchup=nae-1"]
    assert page.heat_status.text() == m.status_line(NAE1, NOW) and page.heat_note.text() == "Test heat map."
    box = page.matchup_box
    assert [box.itemText(i) for i in range(box.count())] == ["NA East", "Israphel vs Zikel · last 24 h",
                                                             "Siel vs Nezekan · too few uploaders yet", "Every server, pooled"]
    assert not box.model().item(0).isEnabled() and box.currentData() == "nae-1"
    # the map: the busiest square in the ramp's brightest step, the others below, a boss and the ground
    assert page.frame.isVisibleTo(page) and page.legend.isVisibleTo(page) and page.squares.isVisibleTo(page)
    heat = page.map
    view = heat.view
    assert view and heat.height() == view["h"] and heat.accessibleName() == m.described(NAE1)
    picture = heat.grab().toImage()
    x, y, z = m.box(view, 2, -2)
    assert picture.pixelColor(int(x + 4), int(y + 4)).name() == m.RAMP[4]
    x2, y2, _z = m.box(view, 2, -1)
    assert picture.pixelColor(int(x2 + 4), int(y2 + 4)).name() == m.RAMP[2]
    ground = m.box(view, 0, 1)
    assert picture.pixelColor(int(ground[0] + 4), int(ground[1] + 4)).name() == m.GROUND
    centre = picture.pixelColor(int(x + z / 2), int(y + z / 2))
    assert centre.name() != m.RAMP[4]                                                     # its kill's dot
    legend = " ".join(_texts(page.legend))
    assert "PvP hits per square:  1" in legend and "31" in legend and "a square with a kill" in legend
    assert "ground recordings have covered" in legend and "a recorded boss" in legend
    # under the pointer
    _move(heat, x + z / 2 + 10, y + z / 2 + 10)
    assert heat.tip.isVisibleTo(page) and heat.hover == ("cell", [2, -2, 31, 2])
    assert heat.tip.text() == (f"<b>31 PvP hits</b><br>2 kills<br><span style='color: {m.theme.COLORS['muted']};'>"
                               "x 4,000 to 6,000 · y -4,000 to -2,000</span>")
    boss = m.at(view, 9000, -1000)
    _move(heat, boss[0] + 3, boss[1])
    assert "Testboss Gamma" in heat.tip.text() and "a recorded boss" in heat.tip.text()
    _move(heat, 2, 2)
    assert not heat.tip.isVisibleTo(page) and heat.hover is None
    # the busiest squares as a table
    table = page.squares.findChild(QTableWidget)
    assert [table.horizontalHeaderItem(i).text() for i in range(4)] == ["Square: x", "Square: y", "PvP hits", "Kills"]
    assert [table.item(0, i).text() for i in range(4)] == ["4,000 to 6,000", "-4,000 to -2,000", "31", "2"]
    # read again every refresh_seconds while shown
    assert page.timer.isActive() and page.timer.interval() == 900000
    page.hide()
    assert not page.timer.isActive()


def test_the_matchup_square_size_and_refresh(qapp):
    app = FakeApp()
    page = _page(app)
    settle(lambda: page.heat is not None and page.heat.get("matchup"))
    page.cell_box.setCurrentIndex(page.cell_box.findData(4000))
    page.cell_box.activated.emit(page.cell_box.currentIndex())
    settle(lambda: page.heat["cell_size"] == 4000)
    assert app.asked[-1] == "/api/v1/pvp-heat?map=20&cell=4000&matchup=nae-1"
    assert page.store.value(m.CELL_KEY) == "4000" and page.store.value(m.MATCHUP_KEY) is None   # the busiest: no choice
    page.matchup_box.setCurrentIndex(page.matchup_box.findData("nae-2"))
    page.matchup_box.activated.emit(page.matchup_box.currentIndex())
    settle(lambda: not page.heat.get("available"))
    assert app.asked[-1] == "/api/v1/pvp-heat?map=20&cell=4000&matchup=nae-2"
    assert page.store.value(m.MATCHUP_KEY) == "nae-2"                            # with the web page's choices
    assert page.heat_status.text().startswith("Not enough recorded Abyss PvP for Siel vs Nezekan (NA East) yet")
    assert not page.squares.isVisibleTo(page) and page.frame.isVisibleTo(page)            # the ground, without squares
    assert m.described(page.heat) == page.map.accessibleName()
    count = len(app.asked)
    _button(page, "Refresh").click()
    settle(lambda: len(app.asked) > count and page.refresh.isEnabled())
    assert app.asked[-1] == "/api/v1/pvp-heat?map=20&cell=4000&matchup=nae-2"
    page.matchup_box.setCurrentIndex(page.matchup_box.findData("all"))
    page.matchup_box.activated.emit(page.matchup_box.currentIndex())
    settle(lambda: app.asked[-1].endswith("matchup=all") and page.heat.get("matchup") is None)
    assert page.heat_status.text().startswith("Every server, the last 24 hours")


def test_the_heat_maps_size_and_matchup_kept_here_or_on_the_web_page(qapp):
    app = FakeApp()
    page = _page(app, store=_store(**{m.CELL_KEY: "1000", m.MATCHUP_KEY: "nae-2"}))
    settle(lambda: page.heat is not None)
    assert app.asked == ["/api/v1/pvp-heat?map=20&cell=1000&matchup=nae-2"]        # asked for at once, not the busiest
    assert page.cell_box.currentData() == 1000 and page.matchup_box.currentData() == "nae-2"
    assert [m.kept_cell(x) for x in (None, "", "4000", " 1000 ", "1e3", "3000", "x")] == [2000, 2000, 4000, 1000, 1000,
                                                                                           2000, 2000]
    assert m.kept_matchup(None) == "" and m.kept_matchup("all") == "all"


def test_a_heat_map_the_log_server_does_not_give(qapp):
    missing = _page(FakeApp(heat=OSError("HTTP 404")))
    assert missing.heat_status.text() == m.NOT_OFFERED and not missing.frame.isVisibleTo(missing)
    broken = _page(FakeApp(heat=OSError("timed out")))
    assert broken.heat_status.text() == "The PvP heat map could not be loaded: timed out"
    older = _page(FakeApp(heat={"error": "unknown path"}))
    assert older.heat_status.text() == m.NOT_OFFERED and older.refresh.isEnabled()
    groundless = _page(FakeApp(heat={**NAE1, "bounds": None}))
    assert groundless.heat_status.text() == m.status_line(NAE1, NOW) and not groundless.frame.isVisibleTo(groundless)


def test_the_farming_routes(qapp):
    copied, opened = [], []
    page = _page(clipboard=copied.append, open_link=opened.append)
    zone = page.route_zone
    assert [zone.itemText(i) for i in range(zone.count())] == [m.zone_label(z) for z in ROUTES["zones"]]
    assert zone.currentData() == "verteron"                                       # the catalog's first zone
    texts = _texts(page)
    verteron = ROUTES["zones"][0]
    assert verteron["notes"][0] in texts and m.catalog_line(ROUTES) in texts
    assert "Guides (links only — no reuse terms, so nothing from them is copied)" in texts
    first = verteron["routes"][0]
    copy = [b for b in page.findChildren(QPushButton) if b.text() == "Copy as text"]
    assert len(copy) == 2 and copy[0].isVisibleTo(page) and not copy[1].isVisibleTo(page)       # the first route open
    copy[0].click()
    assert copied == [m.route_text(verteron, first, ROUTES["sources"][first["source"]])]
    assert "Copied." in _texts(page)
    source = next(label for label in page.findChildren(QLabel) if label.isVisibleTo(page) and "Source: " in label.text())
    source.linkActivated.emit(ROUTES["sources"][first["source"]]["url"])
    assert opened == [ROUTES["sources"][first["source"]]["url"]]
    # another zone's routes
    page.route_zone.setCurrentIndex(page.route_zone.findData("altgard"))
    page.route_zone.activated.emit(page.route_zone.currentIndex())
    assert m.route_summary(ROUTES["zones"][1]["routes"][0]) in [b.text() for b in page.findChildren(QToolButton)]
    # a zone without routes or guides
    page.route_zone.setCurrentIndex(page.route_zone.findData("poeta"))
    page.route_zone.activated.emit(page.route_zone.currentIndex())
    texts = _texts(page)
    assert "No route is listed for this zone." in texts and "No guide links were found for this zone." in texts


def test_the_page_has_no_interactive_map(qapp):
    """The window cannot show the provider's interactive maps (InteractiveMap.app), so all it had of them was a choice
    of map and Open provider, which showed the map in the browser: they are left out (0.2.512). The heat map and the
    routes are the page."""
    import re
    from aion2calc.gui.database_page import Window
    page = _page()
    assert [w.title.text() for w in page.findChildren(Window)] == ["ABYSS PVP HEAT MAP", "FARMING ROUTES"]
    words = [label.text() for label in page.findChildren(QLabel)]
    hosts = {urllib.parse.urlsplit(href).hostname for w in words for href in re.findall(r"href='([^']*)'", w)}
    assert not any(host == "interactivemap.app" for host in hosts)    # nothing links to the provider's maps
    assert not any("Open provider" in w for w in words)
    assert "Open provider ↗" not in [b.text() for b in page.findChildren(QPushButton)]
    assert not hasattr(page, "zone_box") and not hasattr(m, "provider_url")
    # the routes still credit their waypoints' source, the open AION 2 Interactive Map project (not the provider)
    assert any(host == "aion2-interactive-map.github.io" for host in hosts)


def test_copy_refused_and_a_route_catalog_missing(qapp):
    def refuse(_text):
        raise RuntimeError("the clipboard is held")
    page = _page(clipboard=refuse)
    _button(page, "Copy as text").click()
    assert "Clipboard blocked; select the list and copy it." in _texts(page)
    missing = _page(FakeApp(routes_fail=True))
    assert "Route catalog unavailable (HTTP 404)" in _texts(missing)


def test_the_window_draws_maps_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("maps"), MapsPage) and not isinstance(window.page("maps"), WebPage)
    assert not isinstance(window.page("raid"), WebPage)                                        # every page native (0.2.490)


def _js_drawn_bounds(cases: list) -> list:
    """maps.js's ``drawnBounds`` on each case, as the web page works them out."""
    import re
    import subprocess
    source = (STATIC / "maps.js").read_text(encoding="utf-8")
    found = re.search(r"\n const GROUND_PART=[^\n]*\n function drawnBounds\(d\)\{.*?\n \}\n", source, re.S)
    assert found, "maps.js has no drawnBounds"
    probe = found.group(0) + f"\nconsole.log(JSON.stringify({json.dumps(cases)}.map(drawnBounds)));"
    return json.loads(subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True).stdout)


def test_the_heat_map_shows_the_ground_without_the_squares_lying_apart(qapp):
    """The part of the Abyss the map shows (0.2.509): the log server's bounds take in every square recordings have
    covered, a few far off on the map's middle line among them, which made the map many times wider than tall, a thin
    strip; without them it is as tall as the ground (the sample's: 12,000 units each way), and a square lying apart is
    not drawn outside it."""
    assert HEAT["bounds"] == {"x": [-80000, 54000], "y": [-8000, 4000]}                # the sample's three apart
    assert m.drawn_bounds(HEAT) == {"x": [0, 12000], "y": [-8000, 4000]}
    assert m.view(HEAT, 1000, 900, HEAT["bounds"])["h"] < 120 < m.view(HEAT, 1000, 900)["h"] == 648   # a strip, before
    # a patch lying apart stays where a PvP square or a boss is in it
    boss = {**HEAT, "landmarks": HEAT["landmarks"] + [{"name": "Far boss", "x": -79500, "y": 100}]}
    assert m.drawn_bounds(boss) == {"x": [-80000, 12000], "y": [-8000, 4000]}
    fight = {**HEAT, "cells": HEAT["cells"] + [[26, 0, 1, 0]]}
    assert m.drawn_bounds(fight) == {"x": [0, 54000], "y": [-8000, 4000]}
    # a patch of a twentieth of the ground or more stays; a speck of three squares or fewer never does
    patch = {**HEAT, "footprint": HEAT["footprint"] + [[x, 0] for x in range(30, 35)]}
    assert m.drawn_bounds(patch) == {"x": [0, 70000], "y": [-8000, 4000]}
    # nothing lying apart, no ground or no bounds: the log server's as they are
    whole = {**HEAT, "footprint": HEAT["footprint"][:36], "bounds": {"x": [0, 12000], "y": [-8000, 4000]}}
    assert m.drawn_bounds(whole) is whole["bounds"]
    assert m.drawn_bounds({**HEAT, "footprint": []}) is HEAT["bounds"] and m.drawn_bounds({**HEAT, "bounds": None}) is None
    odd = {**HEAT, "footprint": HEAT["footprint"] + [None, [], [3], ["4", 5], [True, 1]], "cells": [[None, 1], ["2", 2]],
           "landmarks": [{"x": "?"}, None, {"x": True, "y": 1}]}
    assert m.drawn_bounds(odd) == {"x": [0, 12000], "y": [-8000, 4000]}               # what is not a place, left out
    # the web page works the part shown out alike (maps.js ``drawnBounds``)
    cases = [HEAT, boss, fight, patch, whole, {**HEAT, "footprint": []}, {**HEAT, "bounds": None}, odd]
    assert _js_drawn_bounds(cases) == [json.loads(json.dumps(m.drawn_bounds(case))) for case in cases]
    # the page's map: as tall as the ground, and a square lying apart beside it not drawn there
    near = {**NAE1, "footprint": NAE1["footprint"] + [[7, 0]], "bounds": {"x": [-80000, 54000], "y": [-8000, 4000]}}
    page = _page(FakeApp(heat=near))
    heat = page.map
    assert heat.view["h"] == heat.height() and heat.view["x0"] == 0 and heat.height() > 500
    picture = heat.grab().toImage()
    x, y, z = m.box(heat.view, 7, 0)                           # one square apart: beside the map, inside the widget
    assert heat.view["ox"] + heat.view["w"] < x + 8 < heat.width()
    assert picture.pixelColor(int(x + 8), int(y + z / 2)).name() != m.GROUND
    ground = m.box(heat.view, 0, 1)
    assert picture.pixelColor(int(ground[0] + 4), int(ground[1] + 4)).name() == m.GROUND
