"""The native Database page (0.2.429): the game database's state and its item catalog as the web page shows them
(pages/database.js), off screen, over the app's own local API and its bundled item database.

The sync and the item icons are stood in for, so the tests ask nothing of the network.
"""
import os
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from aion2calc.app import server  # noqa: E402
from aion2calc.gui import database_page as db  # noqa: E402
from aion2calc.gui.api import AppApi  # noqa: E402
from aion2calc.gui.database_page import DatabasePage  # noqa: E402
from aion2calc.gui.news import when  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ITEM = {"slug": "boots", "name": "Test Boots", "grade": "Unique", "category": "Shoes",
        "fixed": {"Defense": "+225", "HP": "+92"},
        "enchant": [{"step": "+0 → +1", "stats": "Defense +13, HP +10"}, {"step": "+1 → +2", "stats": "Defense +26"}],
        "random": [{"stat": "Block", "range": "+15 – +24", "chance": "6%"}, {"stat": "MP", "range": "+58 – +74"}],
        "skill_pools": {"cleric": {"max_level": 1, "skills": ["Immortal Veil", "Heal Block"]}}}


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


@pytest.fixture
def app_api(tmp_path, monkeypatch):
    """The app's own local API over its bundled database, its sync and icons stood in for."""
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    real = AppApi(f"http://127.0.0.1:{srv.server_address[1]}/", timeout=30)

    class App:
        posts, icons = [], []

        def get(self, path):
            return real.get(path)

        def post(self, path, payload):
            assert path == "/api/sync"
            self.posts.append(payload)
            return {"ok": True}

        def get_bytes(self, path):
            assert path.startswith("/api/icon?u=")
            self.icons.append(path)
            return png(40, 40, "#3d94d8")
    yield App()
    srv.shutdown()


def png(width: int, height: int, colour: str) -> bytes:
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


# ------------------------------------------------------------------ the arithmetic
def test_the_numbers_and_the_items_parts_read_as_the_web_page_writes_them():
    assert [db.n0(x) for x in (2081, 1234567.5, 0, None, "x", float("nan"), True)] == [
        "2,081", "1,234,568", "0", "—", "—", "—", "—"]
    assert db.progress({"done": 3, "total": 12}) == 25.0
    assert db.progress({"running": True}) == 5.0 and db.progress({}) == 100.0
    assert db.changed_text({"changed": {"items": 3}}) == 'changed: {"items":3}' and db.changed_text({}) == ""
    assert db.icon_path("/web/aion2/items/a.webp") == "/api/icon?u=https%3A%2F%2Fmetabot.gg%2Fweb%2Faion2%2Fitems%2Fa.webp"
    assert db.icon_path("https://assets.playnccdn.com/x.png") == "/api/icon?u=https%3A%2F%2Fassets.playnccdn.com%2Fx.png"
    assert db.icon_path("") == db.icon_path(None) == ""
    assert db.grade_color("Unique") == "#e9a43a" and db.grade_color("Rare") == "#52b35c"
    assert db.grade_color("Nothing") == db.grade_color(None) == "#e9e6df"
    assert db.fixed_pairs(ITEM) == [("Defense", "+225"), ("HP", "+92")]
    assert db.enchant_pairs(ITEM) == [("+0 → +1", "Defense +13, HP +10"), ("+1 → +2", "Defense +26")]
    assert db.random_pairs(ITEM) == [("Block", "+15 – +24", "6%"), ("MP", "+58 – +74", "")]
    assert db.skill_pool_lines(ITEM) == [("Cleric (up to +1)", "Immortal Veil, Heal Block")]
    assert db.fixed_pairs({}) == db.enchant_pairs({}) == db.random_pairs({}) == db.skill_pool_lines({}) == []
    assert db.last_sync({"last_sync": {"at": 1763632800}}) == when(1763632800 * 1000)
    assert db.last_sync({"last_sync": None}) == db.last_sync({}) == "never"


# ------------------------------------------------------------------ the page
def test_the_database_state_is_read_when_shown_and_again_while_shown(qapp, app_api):
    page = DatabasePage(app_api)
    assert page.status is None                                                   # nothing before it is shown
    page.resize(1040, 900)
    page.show()
    settle(lambda: page.status is not None, timeout=20)
    items = page.status["db"]["items"]
    assert items > 1000 and page.kpis["items"].value.text() == f"{items:,}"
    assert page.kpis["characters"].value.text() == "0" and page.kpis["encounters"].value.text() == "0"
    assert page.kpis["last"].value.text() == "never"
    assert page.folder.text() == f"Data folder: {page.status['home']}"
    assert page.phase.isHidden() and page.bar.isHidden()                         # no update under way
    assert page.poll.isActive() and page.poll.interval() == db.RESTING_MS        # read again in 15 s
    categories = [page.category.itemText(i) for i in range(page.category.count())]
    assert categories[0] == "all categories" and len(categories) > 5
    assert all(text.endswith(")") for text in categories[1:])                  # each with its count
    page.check.click()
    settle(lambda: app_api.posts == [{}])
    page.full.click()
    settle(lambda: len(app_api.posts) == 2)
    assert app_api.posts[1] == {"force": True, "budget": 3600}
    page.hide()
    assert not page.poll.isActive()


def test_an_update_under_way_shows_its_phase_progress_changes_and_errors(qapp):
    page = DatabasePage(None)
    page.status = {"home": "/data", "db": {"items": 10, "characters": 2, "encounters": 3, "categories": []},
                   "sync": {"running": True, "phase": "items", "message": "reading the catalog", "done": 3, "total": 12,
                            "changed": {"items": 3}, "errors": [f"error {n}" for n in range(7)]}}
    page._show_status()
    assert page.phase.text() == "items" and page.message.text() == "reading the catalog" and page.steps.text() == "3/12"
    assert page.bar.value() == 250                                               # a quarter of the way
    assert page.changed.text() == 'changed: {"items":3}' and not page.changed.isHidden()
    assert page.errors.text().splitlines() == [f"error {n}" for n in range(5)]  # the first five
    page.show()
    page._next(True)
    assert page.poll.interval() == db.RUNNING_MS                                 # every two seconds while it runs


def test_the_catalog_is_searched_and_an_item_opens(qapp, app_api):
    page = DatabasePage(app_api)
    page.resize(1040, 900)
    page.show()
    settle(lambda: page.status is not None, timeout=20)
    page.search.setText("Ancient")
    page.find_button.click()
    settle(lambda: page.items, timeout=20)
    assert page.table.rowCount() == len(page.items) > 3 and not page.table.isHidden()
    first = page.items[0]
    name = page.table.item(0, 1)
    assert name.text() == first["name"] and name.foreground().color().name() == db.grade_color(first["grade"])
    assert page.table.item(0, 2).text() == first["category"]
    assert page.table.item(0, 3).text() == str(first["item_level"])
    settle(lambda: len(page.icons_shown) >= 1, timeout=20)                       # through the app's icon cache
    assert all(path.startswith("/api/icon?u=") for path in app_api.icons)
    assert len(app_api.icons) == len({db.icon_path(item["icon"]) for item in page.items if item.get("icon")})
    settle(lambda: not page.table.item(0, 0).icon().isNull())
    rows = sum(page.table.rowHeight(row) for row in range(page.table.rowCount()))
    assert page.table.height() >= rows                                           # every row shown, the page scrolls
    page.category.setCurrentIndex(page.category.findData(first["category"]))
    page.find_button.click()
    settle(lambda: all(item["category"] == first["category"] for item in page.items) and page.items, timeout=20)
    page.open_item(0)
    settle(lambda: page.item is not None and not page.detail.isHidden(), timeout=20)
    item = page.item
    assert page.detail.title.text() == (item.get("name") or item["slug"]).upper()
    assert page.detail.subtitle.text() == f"{item.get('grade') or ''} {item.get('category') or ''}".strip()
    texts = [label.text() for label in page.detail.findChildren(QLabel)]
    assert "FIXED" in texts and "ENCHANT" in texts and "RANDOM ROLL POOL" in texts
    for key, value in db.fixed_pairs(item):
        assert key in texts


def test_an_items_values_are_text_not_markup(qapp):
    page = DatabasePage(None)
    page.item = {**ITEM, "fixed": {"<b>Defense</b>": "<i>+225</i>"}}
    page._show_item()
    texts = [label.text() for label in page.detail.findChildren(QLabel)]
    assert "<b>Defense</b>" in texts                                             # shown as written
    assert "&lt;i&gt;+225&lt;/i&gt;" in texts
    assert any(text.startswith("<b>Cleric (up to +1)</b>: Immortal Veil") for text in texts)
    assert any("+15 – +24" in text and "6%" in text for text in texts)


def test_the_window_draws_the_database_page_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("database"), DatabasePage) and not isinstance(window.page("database"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                               # not moved over yet
