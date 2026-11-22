"""The native News page (0.2.427): the official AION 2 headlines as the web page shows them (pages/news.js and
``A2News`` in static/news.js), off screen.

Only an article on the region's official site and a picture on the official download server are shown; the page
reads its region from the app, then the region's feed through the app's proxy to the log server, and draws a card
for each headline in columns of at least 280 px.
"""
from datetime import datetime, timezone
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.app import server  # noqa: E402
from aion2calc.app.settings_backup import _clean  # noqa: E402
from aion2calc.gui import news  # noqa: E402
from aion2calc.gui.news import NewsPage, date, meta, official, shown, status, thumbnail, when  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

PICTURE = "https://fizz-download.playnccdn.com/lg/file/aion2_global/news/headline-1"


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
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def article(n: int, board: str = "notice", region: str = "global") -> str:
    return f"{news.REGIONS[region][1]}/board/{board}/view?articleId={n:024x}"


def entry(n: int, category: str = "Notices", region: str | None = None, **extra) -> dict:
    row = {"title": f"Headline {n}", "category": category,
           "url": article(n, "notice" if category == "Notices" else "update", region or "global"),
           "published_at": "2026-11-20T10:00:00Z", "preview": f"What headline {n} says.",
           "publisher": "AION 2 team", "retrieved_at": 1763632800}
    if region:
        row["region"] = region
    row.update(extra)
    return row


FEED = {"status": "ready", "entries": [entry(1, image=PICTURE), entry(2, "Updates"), entry(3)],
        "note": "Headlines are kept for 30 days."}


class FakeApp:
    """The app as the page asks it: its settings, and the log server's feed for each region."""

    def __init__(self, feeds: dict, ui: dict | None = None, fail: str = "", fail_ui: bool = False):
        self.feeds, self.ui, self.fail, self.fail_ui = feeds, dict(ui or {"news_region": "global"}), fail, fail_ui
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path))
        if path == "/api/ui":
            if self.fail_ui:
                raise OSError("the app did not answer")
            return dict(self.ui)
        assert path.startswith("/api/community?path=")
        inner = urllib.parse.unquote(path.split("=", 1)[1])
        assert inner.startswith("/api/v1/news?region=")
        if self.fail:
            raise OSError(self.fail)
        return self.feeds[inner.split("=", 1)[1]]

    def post(self, path, payload):
        self.calls.append(("POST", path, payload))
        self.ui.update(payload)
        return {"ok": True}


def png(width: int, height: int, colour: str) -> bytes:
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def _store(**values):
    """The interface data of a page of its own, as the app gives it (each value a text)."""
    from aion2calc.gui import interface
    store = interface.InterfaceStore(shared=interface._Shared())
    for key, value in values.items():
        store.setValue(key, value)
    return store


def _page(app: FakeApp, width: int = 1000, **kwargs) -> NewsPage:
    opened = []
    kwargs.setdefault("store", _store())
    page = NewsPage(app, open_link=opened.append, **kwargs)
    page.opened = opened
    page.resize(width, 800)
    page.show()
    settle(lambda: not page.busy and page.serial > 0)
    QCoreApplication.processEvents()
    return page


# ------------------------------------------------------------------ the arithmetic
def test_only_an_article_on_the_regions_site_and_a_picture_on_the_official_server_are_shown():
    good = article(0xABC)
    assert official(good, "global") == good
    assert official(article(5, "update"), "global")
    assert official(article(5, region="kr"), "kr") and official(article(5, region="tw"), "tw")
    assert official(good.replace("https://", "https://aion2.plaync.com:443@", 1), "global") == ""     # a sign-in
    for wrong in (article(5, region="kr"),                                        # another region's site
                  good.replace("/notice/view", "/notice/list"),                   # not an article
                  good.replace("https://", "http://"),                            # not the site's own origin
                  good.replace("aion2.plaync.com", "aion2.plaync.com.example"),
                  good.replace("articleId=", "articleId=X"),                      # an id of 24 hex digits only
                  good[:-1], good.upper().replace("HTTPS://AION2.PLAYNC.COM/EN-US", news.REGIONS["global"][1]),
                  "https://user:pw@aion2.plaync.com/en-us/board/notice/view?articleId=" + "a" * 24,
                  "not an address", "", None, 12):
        assert official(wrong, "global") == "", wrong
    assert official(good, "mars") == ""
    assert official("https://aion2.plaync.com:443/en-us/board/notice/view?articleId=" + "b" * 24, "global")
    assert thumbnail(PICTURE) == PICTURE
    assert thumbnail("https://fizz-download.playnccdn.com/download/v2/buckets/news/a_b-1")
    for wrong in (PICTURE + "?size=big", PICTURE + "#top", PICTURE.replace("https://", "http://"),
                  PICTURE.replace("https://", "https://me@"), PICTURE.replace("aion2_global", "lineage"),
                  PICTURE + "/../../secret", "https://example.com/lg/file/aion2/news/a", "", None):
        assert thumbnail(wrong) == "", wrong


def test_dates_read_as_the_web_page_reads_them():
    local = lambda *parts: datetime(*parts, tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    assert when("2026-10-23T15:04:05Z") == local(2026, 10, 23, 15, 4, 5)
    assert when(1763632800 * 1000) == local(2025, 11, 20, 10, 0, 0)               # milliseconds since 1970
    assert when("2026-10-23") == local(2026, 10, 23)                               # a date alone is midnight UTC
    assert when(None) == when("") == when("soon") == when(True) == when(float("nan")) == "—"
    assert date(None) == "Date unavailable" and date("2026-10-23T15:04:05Z") == local(2026, 10, 23, 15, 4, 5)
    row = entry(1)
    assert meta(row, "global") == "Global (English) · AION 2 team · retrieved " + local(2025, 11, 20, 10, 0, 0)
    assert meta({}, "kr") == "Korea (Korean) · Official AION 2 site"
    assert meta({"retrieved_at": "yesterday"}, "tw") == "Taiwan (Traditional Chinese) · Official AION 2 site"


def test_the_headlines_shown_are_the_first_twenty_of_the_region_in_the_category_chosen():
    entries = [entry(n, "Updates" if n % 2 else "Notices") for n in range(1, 25)]
    data = {"entries": entries}
    assert [row["title"] for row in shown(data, "global")] == [f"Headline {n}" for n in range(1, 21)]
    assert all(row["category"] == "Updates" for row in shown(data, "global", "Updates"))
    assert len(shown(data, "global", "Notices")) == 10
    mixed = {"entries": [entry(1), entry(2, region="kr"), entry(3, region="global"), entry(4, url="https://x.example/")]}
    assert [row["title"] for row in shown(mixed, "global")] == ["Headline 1", "Headline 3"]   # no region: global
    assert [row["title"] for row in shown(mixed, "kr")] == ["Headline 2"]
    assert shown(None, "global") == shown({"entries": "none"}, "global") == []
    assert status(True, "", None, "kr") == "Loading Korea (Korean) headlines…"
    assert status(False, "No log server", FEED, "global") == "No log server"
    assert status(False, "", None, "global") == ""
    assert status(False, "", FEED, "global") == "Official sources loaded."
    assert status(False, "", {"status": "partial"}, "global") == (
        "Some official sources are unavailable; retained headlines may be stale.")


# ------------------------------------------------------------------ the page
def test_the_page_reads_its_region_then_the_feed_and_draws_a_card_for_each_headline(qapp):
    app = FakeApp({"global": {**FEED, "unavailable_sources": ["updates board"]}})
    page = NewsPage(app, open_link=lambda url: None)
    assert app.calls == []                                                       # nothing asked before it is shown
    page = _page(app)
    assert app.calls[:2] == [("GET", "/api/ui"), ("GET", "/api/community?path=" + urllib.parse.quote(
        "/api/v1/news?region=global", safe=""))]
    assert page.status.text() == "Official sources loaded."
    assert page.unavailable.text() == "Unavailable sources: updates board" and not page.unavailable.isHidden()
    assert page.note.text() == "Headlines are kept for 30 days." and page.empty.isHidden()
    assert [card.url for card in page.cards] == [article(1), article(2, "update"), article(3)]
    card = page.cards[1]
    assert card.category.text() == "Updates" and card.preview.text() == "What headline 2 says."
    assert card.date.text() == when("2026-11-20T10:00:00Z") and card.meta.text() == meta(entry(2), "global")
    assert "Headline 2" in card.title.text() and card.title.toolTip() == article(2, "update")
    card.title.linkActivated.emit(article(2, "update"))
    card.read.click()
    assert page.opened == [article(2, "update")] * 2                             # in the system's browser
    assert "board/notice/list" in page.links.text() and "board/update/list" in page.links.text()
    page.links.linkActivated.emit(news.REGIONS["global"][1] + "/board/notice/list")
    assert page.opened[-1] == "https://aion2.plaync.com/en-us/board/notice/list"
    page.filter_box.setCurrentText("Updates")                                    # the category shown
    assert [card.url for card in page.cards] == [article(2, "update")]
    page.filter_box.setCurrentText("All")
    page.refresh.click()
    settle(lambda: not page.busy)
    assert len([call for call in app.calls if call[1].startswith("/api/community")]) == 2


def test_choosing_a_region_keeps_it_and_reads_its_feed(qapp):
    kr = {"status": "ready", "region": "kr", "entries": [entry(7, region="kr"), entry(8)]}
    app = FakeApp({"global": FEED, "kr": kr, "tw": {"status": "ready", "entries": [entry(9, region="tw")]}},
                  ui={"news_region": "kr"})
    page = _page(app)
    assert page.region_box.currentData() == "kr" and page.region == "kr"         # the region kept in the app
    assert [card.url for card in page.cards] == [article(7, region="kr")]
    assert "Korea (Korean)" in page.cards[0].meta.text()
    assert "ko-kr/board/notice/list" in page.links.text()
    page.region_box.setCurrentIndex(list(news.REGIONS).index("global"))
    settle(lambda: not page.busy)
    assert ("POST", "/api/ui", {"news_region": "global"}) in app.calls
    assert page.store.value(news.REGION_KEY) == "global"                         # with the web page's choice
    assert [card.url for card in page.cards] == [article(1), article(2, "update"), article(3)]
    page.region_box.setCurrentIndex(list(news.REGIONS).index("tw"))              # a feed that answers another region
    settle(lambda: not page.busy)
    assert page.status.text() == news.NEEDS_UPDATE and page.cards == []
    assert page.empty.text() == news.NONE_SHOWN and not page.empty.isHidden()


def test_the_region_the_web_page_keeps_comes_first(qapp):
    kr = {"status": "ready", "region": "kr", "entries": [entry(7, region="kr")]}
    tw = {"status": "ready", "region": "tw", "entries": [entry(9, region="tw")]}
    app = FakeApp({"global": FEED, "kr": kr, "tw": tw}, ui={"news_region": "kr"})
    page = _page(app, store=_store(**{news.REGION_KEY: "tw"}))                    # news.js's own: over the app's
    assert page.region == "tw" and page.region_box.currentData() == "tw"
    assert [card.url for card in page.cards] == [article(9, region="tw")]
    page = _page(app, store=_store(**{news.REGION_KEY: "mars"}))                  # not a region: the app's
    assert page.region == "kr"
    page = _page(FakeApp({"global": FEED, "tw": tw}, fail_ui=True), store=_store(**{news.REGION_KEY: "tw"}))
    assert page.region == "tw"                                                    # the app's settings not read


def test_a_headlines_words_are_text_not_markup(qapp):
    row = entry(1, category="<b>Notices</b>", preview="<img src='x'> <a href='https://x.example/'>here</a>",
                publisher="<i>Team</i>", title="<u>Big</u> news")
    page = _page(FakeApp({"global": {"status": "<b>ready</b>", "note": "<b>note</b>",
                                      "unavailable_sources": ["<i>board</i>"], "entries": [row]}}))
    (card,) = page.cards
    assert card.category.text() == "<b>Notices</b>" and card.category.textFormat() == Qt.PlainText
    assert card.preview.textFormat() == Qt.PlainText and card.meta.textFormat() == Qt.PlainText
    assert "&lt;u&gt;Big&lt;/u&gt; news" in card.title.text()                     # the title escaped in its link
    assert page.note.textFormat() == Qt.PlainText and page.unavailable.textFormat() == Qt.PlainText


def test_a_feed_that_cannot_be_read_says_why(qapp):
    page = _page(FakeApp({}, fail="the log server did not answer"))
    assert page.status.text() == "the log server did not answer" and not page.empty.isHidden()
    page = _page(FakeApp({"global": {"error": "No log server is set"}}))           # the app's own refusal
    assert page.status.text() == "No log server is set"
    page = _page(FakeApp({"global": {"status": "stale", "entries": []}}))
    assert page.status.text() == "Some official sources are unavailable; retained headlines may be stale."
    assert page.empty.text() == news.NONE_SHOWN and not page.empty.isHidden()


def test_the_cards_lay_out_in_columns_of_at_least_280_px(qapp):
    many = {"status": "ready", "entries": [entry(n) for n in range(1, 6)]}
    page = _page(FakeApp({"global": many}), width=1000)
    assert page.columns == 3                                                     # (952 + 14) // (280 + 14)
    positions = {(page.grid.getItemPosition(page.grid.indexOf(card))[:2]) for card in page.cards}
    assert positions == {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)}
    page.resize(560, 800)
    QCoreApplication.processEvents()
    assert page.columns == 1
    page.resize(1000, 800)
    QCoreApplication.processEvents()
    assert page.columns == 3
    lefts = sorted({card.geometry().left() for card in page.cards})
    widths = {card.width() for card in page.cards}
    assert len(lefts) == 3 and max(widths) - min(widths) <= 1                    # equal columns
    two = _page(FakeApp({"global": {"status": "ready", "entries": [entry(1), entry(2)]}}), width=1000)
    assert two.columns == 2                                                      # fewer cards share the width


def test_a_picture_is_read_from_the_official_server_and_covers_its_box(qapp):
    asked = []

    def read(url):
        asked.append(url)
        if url == PICTURE:
            return png(400, 300, "#ff0000")
        raise urllib.error.URLError("no picture")

    feed = {"status": "ready", "entries": [entry(1, image=PICTURE), entry(2, image=PICTURE.replace("-1", "-2")),
                                           entry(3, image="https://example.com/tracker.png")]}
    page = _page(FakeApp({"global": feed}), read_picture=read)
    settle(lambda: page.cards[0].picture.isVisible())
    assert sorted(asked) == sorted([PICTURE, PICTURE.replace("-1", "-2")])        # never another server's
    first = page.cards[0].picture
    assert first.heightForWidth(248) == 180 and first.heightForWidth(200) == 150  # at most 180 px high
    QCoreApplication.processEvents()
    image = first.grab().toImage()
    middle = image.pixelColor(image.width() // 2, image.height() // 2)
    assert (middle.red(), middle.green(), middle.blue()) == (255, 0, 0)           # the picture covers its box
    corner = image.pixelColor(0, 0)
    assert corner.red() < 255 or corner.alpha() < 255                             # its corners rounded
    assert not page.cards[1].picture.isVisible() and not page.cards[2].picture.isVisible()
    page.filter_box.setCurrentText("Notices")                                     # drawn again, not read again
    settle(lambda: page.cards[0].picture.isVisible())
    assert asked.count(PICTURE) == 1
    opened = page.opened
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(page.cards[0].picture, QMouseEvent(kind, QPointF(10, 10), QPointF(10, 10),
                                                                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    assert opened[-1] == article(1)                                               # a click on it opens the article


def test_the_window_draws_the_news_page_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("news"), NewsPage) and not isinstance(window.page("news"), WebPage)
    assert not isinstance(window.page("raid"), WebPage)                               # every page native (0.2.490)


def test_the_news_region_is_one_of_the_apps_settings(home):
    from http.server import ThreadingHTTPServer
    assert server.ui_settings()["news_region"] == "global"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(body):
        request = urllib.request.Request(base + "/api/ui", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(request, timeout=30).read())
    try:
        post({"news_region": "tw"})
        assert server.ui_settings()["news_region"] == "tw"
        with pytest.raises(urllib.error.HTTPError):
            post({"news_region": "mars"})
        assert server.ui_settings()["news_region"] == "tw"
    finally:
        srv.shutdown()
    assert _clean({"news_region": "kr"}) == {"news_region": "kr"}                 # in a settings backup too
    with pytest.raises(ValueError):
        _clean({"news_region": "mars"})


def test_a_card_shows_no_window_of_its_own(qapp):
    """A card's category and preview are put in it before they are made visible: shown first, a parentless label
    would flash as a window of its own, and a window shown closes any popup open."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame
    popup = QFrame(None, Qt.Popup)
    popup.resize(60, 40)
    popup.show()
    QCoreApplication.processEvents()
    card = news.Card(entry(1), "global", lambda url: None)
    QCoreApplication.processEvents()
    assert popup.isVisible() and not card.category.isHidden() and not card.preview.isHidden()
    bare = news.Card(entry(2, category="", preview=""), "global", lambda url: None)
    assert bare.category.isHidden() and bare.preview.isHidden()
    popup.close()
