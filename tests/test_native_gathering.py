"""The native Gathering page (0.2.430): what you gathered and took from dungeon reward cubes, and everyone's drop rates,
as the web page shows them (pages/gathering.js and ``A2Gathering`` in static/gathering.js), off screen, over records in
the summary's own shape (``combat/gathering.summary``).
"""
import os
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton, QTableWidget  # noqa: E402

from aion2calc.gui import gathering_page as g  # noqa: E402
from aion2calc.gui.gathering_page import GatheringPage  # noqa: E402
from aion2calc.gui.news import when  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

T = 1763700000
ODYLE = {"name": "Odyle", "gathers": 25, "results": {"normal": 20, "better": 3, "failed": 2}, "kinds": ["dungeon"],
         "places": [{"name": f"Place {n}", "gathers": 10 - n} for n in range(7)],
         "items": [{"item": 1, "name": "Odyle", "grade": "Rare", "gathers": 20, "count": 26, "share": 0.8},
                   {"item": 2, "name": "Fine Odyle", "grade": "Epic", "gathers": 3, "count": 3, "share": 0.12}]}
FLAX = {"name": "Flax", "gathers": 4, "results": {"normal": 4}, "kinds": ["open_world", "dungeon"], "places": [],
        "items": [{"item": 3, "name": "Flax", "grade": "", "gathers": 4, "count": 9, "share": 1.0}]}
DUNGEON = {"name": "Dungeon A (hard)", "cubes": 3,
           "items": [{"item": 10, "name": "Stone", "grade": "Rare", "material": True, "share": 1.0, "average": 2.5},
                     {"item": 11, "name": "Sword", "grade": "Unique", "material": False, "share": 0.3333, "average": 1}]}
MINE = {"sharing": True, "gathers": 29, "gathered": 38, "cubes": 3, "results": {"normal": 24, "better": 3, "failed": 2},
        "nodes": [ODYLE, FLAX], "dungeons": [DUNGEON],
        "recent": [{"kind": "gather", "t": T, "place": "Place 0", "character": "Tester", "result": "better", "count": 1,
                    "item": 2, "name": "Fine Odyle", "grade": "Epic"},
                   {"kind": "gather", "t": T - 60, "place": None, "character": None, "result": "failed", "item": 1,
                    "name": "Odyle", "grade": "Rare"},
                   {"kind": "reward", "t": T - 120, "place": "Dungeon A (hard)", "character": "Tester",
                    "items": [{"item": 10, "name": "Stone", "grade": "Rare", "count": 2, "material": True},
                              {"item": 11, "name": "Sword", "grade": "Unique", "count": 1, "material": False}]}]}
EVERYONE = {"gathers": 900, "nodes": [{**ODYLE, "gathers": 900, "reporters": 12}],
            "dungeons": [{**DUNGEON, "cubes": 150, "reporters": 7}]}


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
    """The app as the page asks it: this computer's records, and everyone's through its proxy to the log server."""

    def __init__(self, mine=MINE, everyone=EVERYONE, fail=()):
        self.mine, self.everyone, self.fail, self.calls = mine, everyone, set(fail), []

    def get(self, path):
        self.calls.append(path)
        if path == "/api/gathering":
            if "mine" in self.fail:
                raise OSError("the gathering log could not be read")
            return self.mine
        assert urllib.parse.unquote(path) == "/api/community?path=/api/v1/gathering/stats"
        if "everyone" in self.fail:
            raise OSError("the log server did not answer")
        return self.everyone


def _page(app, **kwargs) -> GatheringPage:
    opened = []
    page = GatheringPage(app, show_page=opened.append, **kwargs)
    page.opened = opened
    page.resize(1040, 900)
    page.show()
    settle(lambda: not page.loading)
    QCoreApplication.processEvents()
    return page


def _texts(widget) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def _tables(page) -> list[QTableWidget]:
    QCoreApplication.processEvents()                  # a widget a layout takes in is shown at the next turn
    return [w for w in page.window_.findChildren(QTableWidget) if w.isVisibleTo(page)]


# ------------------------------------------------------------------ the arithmetic
def test_the_numbers_and_words_read_as_the_web_page_writes_them():
    assert [g.num(x) for x in (1234.5, 0, None, float("nan"), True)] == ["1,235", "0", "—", "—", "—"]
    assert [g.pct(x) for x in (0.8, 0.12345, 1, None)] == ["80.0%", "12.3%", "100.0%", "—"]
    assert g.share_of(3, 25) == "12.0%" and g.share_of(3, 0) == "—"
    assert g.item_name({"item": 7}) == "Item 7" and g.item_name({"name": "Stone"}) == "Stone"
    assert g.dot("Epic") == "#49a0e0" and g.dot("Common") == g.dot(None) == "#9aa3b5"
    assert g.kind_label(ODYLE) == "dungeon node" and g.kind_label(FLAX) == "dungeon and open-world node"
    assert g.kind_label({"kinds": ["somewhere"]}) == ""
    assert g.node_title(ODYLE) == "Odyle — dungeon node · 25 gathers"
    assert g.node_title({**ODYLE, "reporters": 12, "kinds": []}) == "Odyle · 25 gathers · 12 players"
    assert g.where_line(ODYLE) == "Found in Place 0, Place 1, Place 2, Place 3, Place 4 and 2 more"
    assert g.where_line(FLAX) == ""
    assert g.results_line(ODYLE) == [("Normal", "80.0%"), ("Better grade", "12.0%"), ("Failed", "8.0%")]
    assert g.node_count({"average": 1.3}) == "1.30" and g.node_count({"gathers": 20, "count": 26}) == "1.30"
    assert g.node_count({}) == "—"
    assert [g.cube_count({"average": a}) for a in (2.5, 1, 1234.567, None)] == ["2.5", "1", "1,234.57", "—"]
    assert g.dungeon_title(DUNGEON) == "Dungeon A (hard) · 3 reward cubes"
    assert g.dungeon_title({"cubes": 150, "reporters": 7}) == "Unknown place · 150 reward cubes · 7 players"
    assert [[row["name"] for row in items] for _place, items in g.dungeon_rows(MINE, False)] == [["Stone"]]
    assert [[row["name"] for row in items] for _place, items in g.dungeon_rows(MINE, True)] == [["Stone", "Sword"]]
    assert g.dungeon_rows({"dungeons": [{**DUNGEON, "items": [DUNGEON["items"][1]]}]}, False) == []


def test_a_log_entrys_words():
    better, failed, cube = MINE["recent"]
    assert "Fine Odyle</" not in g.what(better) and "Fine Odyle ×1" in g.what(better) and "Better grade" in g.what(better)
    assert "Failed: nothing gathered" in g.what(failed)
    assert g.what(cube).startswith("Reward cube: ") and "Stone ×2" in g.what(cube) and "(2 drops)" in g.what(cube)
    assert "Sword" not in g.what(cube)                                           # not a crafting material
    assert "no crafting materials" in g.what({"kind": "reward", "items": [{"name": "Sword"}]})
    assert "&lt;b&gt;" in g.what({"kind": "gather", "result": "normal", "count": 1, "name": "<b>x</b>"})
    assert g.empty("gathering", "everyone", MINE, "", "").startswith("Nobody has shared any gathering yet.")
    assert g.empty("gathering", "everyone", MINE, g.NO_COMMUNITY, "") == g.NO_COMMUNITY
    assert g.empty("reward cubes", "yours", MINE, "", "").startswith("No reward cubes recorded yet")
    assert g.empty("gathering", "yours", None, "", "broken") == "broken"
    assert "shares it for everyone's" in g.sharing_line(True) and "Sharing is off" in g.sharing_line(False)


# ------------------------------------------------------------------ the page
def test_the_page_reads_both_records_once_shown_and_shows_your_totals(qapp):
    app = FakeApp()
    page = GatheringPage(app, show_page=lambda page: None)
    assert app.calls == [] and _texts(page.window_).count("Loading…") == 1       # nothing asked before it is shown
    page = _page(app)
    assert app.calls[:2] == ["/api/gathering", "/api/community?path=%2Fapi%2Fv1%2Fgathering%2Fstats"]
    kpis = {key: kpi.value.text() for key, kpi in page.kpis.items()}
    assert kpis["gathers"] == "29" and kpis["gathered"] == "38" and kpis["cubes"] == "3"
    assert kpis["better"].startswith("3 ") and "(10.3%)" in kpis["better"] and "(6.9%)" in kpis["failed"]
    assert "shares it for everyone's drop rates" in page.sharing.text()
    page.sharing.linkActivated.emit("page:settings")
    assert page.opened == ["settings"]                                           # the native Settings page
    assert page.tab == "nodes" and page.source == "everyone"
    texts = _texts(page.window_)
    assert "Odyle — dungeon node · 900 gathers · 12 players" in texts and g.NODES_NOTE in texts
    (rates,) = _tables(page)
    assert [rates.item(0, c).text() for c in range(4)] == ["Odyle", "Rare", "80.0%", "1.30"]
    assert not rates.item(0, 0).icon().isNull()                                  # the grade's dot
    page.hide()
    page.show()
    settle(lambda: not page.loading)
    assert len(app.calls) == 4                                                   # read again each time it is shown


def test_the_tabs_and_whose_records(qapp):
    page = _page(FakeApp())
    buttons = {b.text(): b for b in page.window_.findChildren(QPushButton)}
    buttons["This computer"].click()
    assert page.source == "yours"
    titles = [t for t in _texts(page.window_) if " gathers" in t]
    assert titles == ["Odyle — dungeon node · 25 gathers", "Flax — dungeon and open-world node · 4 gathers"]
    assert "Found in Place 0, Place 1, Place 2, Place 3, Place 4 and 2 more" in _texts(page.window_)
    page.tab_buttons["dungeons"].click()
    assert page.tab == "dungeons" and page.tab_buttons["dungeons"].isChecked()
    (cubes,) = _tables(page)
    assert cubes.horizontalHeaderItem(0).text() == "Material" and cubes.rowCount() == 1
    assert [cubes.item(0, c).text() for c in range(4)] == ["Stone", "Rare", "100.0%", "2.5"]
    page.window_.findChild(QCheckBox).setChecked(True)                           # every drop
    (cubes,) = _tables(page)
    assert cubes.horizontalHeaderItem(0).text() == "Drop" and cubes.rowCount() == 2
    assert [cubes.item(1, c).text() for c in range(3)] == ["Sword", "Unique", "33.3%"]
    page.tab_buttons["log"].click()
    (log,) = _tables(page)
    assert [log.horizontalHeaderItem(c).text() for c in range(4)] == ["When", "Where", "What", "Character"]
    assert log.item(0, 0).text() == when(T * 1000) and log.item(0, 1).text() == "Place 0"
    assert log.item(1, 1).text() == "—" and log.item(1, 3).text() == "—"
    assert "Failed: nothing gathered" in log.cellWidget(1, 2).text()
    assert log.cellWidget(2, 2).text().startswith("Reward cube: ")


def test_without_everyones_rates_your_own_are_shown_and_the_reason_given(qapp):
    page = _page(FakeApp(fail={"everyone"}))
    assert page.source == "yours" and page.community_error == g.NO_COMMUNITY     # your records, as on the web page
    page.set_source("everyone")
    assert g.NO_COMMUNITY in _texts(page.window_)
    nobody = _page(FakeApp(everyone={"nodes": [], "dungeons": []}))
    assert nobody.source == "everyone"
    assert any(t.startswith("Nobody has shared any gathering yet.") for t in _texts(nobody.window_))
    nobody.set_tab("dungeons")
    assert any(t.startswith("Nobody has shared any reward cubes yet.") for t in _texts(nobody.window_))


def test_without_your_records_the_page_says_so(qapp):
    page = _page(FakeApp(fail={"mine"}))
    assert page.mine is None and page.kpi_box.isHidden() and page.sharing.isHidden()
    page.set_tab("log")
    assert "the gathering log could not be read" in _texts(page.window_)
    empty = _page(FakeApp(mine={**MINE, "recent": [], "sharing": False}))
    assert "Sharing is off" in empty.sharing.text()
    empty.set_tab("log")
    assert g.NO_LOG in _texts(empty.window_)
    plain = _page(FakeApp(mine={**MINE, "dungeons": [{**DUNGEON, "items": [DUNGEON["items"][1]]}]}))
    plain.set_source("yours")
    plain.set_tab("dungeons")
    assert g.NO_MATERIAL in _texts(plain.window_)


def test_the_window_draws_the_gathering_page_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("gathering"), GatheringPage)
    assert isinstance(window.page("maps"), WebPage)                               # not moved over yet
    window.page("gathering").show_page("settings")
    assert window.pages.currentWidget() is window.page("settings")
