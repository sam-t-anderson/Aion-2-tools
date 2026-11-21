"""The native News page (0.2.427): the official AION 2 headlines, as the web page shows them (pages/news.js and
``A2News`` in static/news.js).

The headlines come from the log server through the app (``/api/community`` asking ``/api/v1/news`` for a region),
each with its category, date, title, preview and its article on the official site. As on the web page, only an
article on the region's official site and a picture on the official download server are shown (``official``,
``thumbnail``): an entry whose link is anything else is left out, and a picture from anywhere else is not read.
The links open in the system's browser. The pictures are read from the official server, as the web page's are,
off the interface's thread.

The arithmetic (``official``, ``thumbnail``, ``when``, ``shown``, ``status``) is kept apart from the page that
draws it, and tested alone.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import math
import re
import urllib.parse
import urllib.request
import webbrowser

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import pictures, theme
from .api import AppApi, Requests

#: Each news region: its name and its official site (news.js ``regions``).
REGIONS = {"global": ("Global (English)", "https://aion2.plaync.com/en-us"),
           "kr": ("Korea (Korean)", "https://aion2.plaync.com/ko-kr"),
           "tw": ("Taiwan (Traditional Chinese)", "https://tw.ncsoft.com/aion2")}
FILTERS = ("All", "Notices", "Updates")
MOST = 20                                         # the headlines the page shows, newest first
PREVIEW = 320                                     # a preview's characters
NOTE = ("Official regional headlines in their original language. This preference does not change your game region "
        "or identify the build used in a combat log.")
NONE_SHOWN = "No retained headlines match this filter. Use the official source links above."
NEEDS_UPDATE = "This community server needs an update to serve regional news. Use the official source links."
UNAVAILABLE = "The news feed is unavailable. Use the official source links."
PICTURE_HOST = "https://fizz-download.playnccdn.com"
PICTURE_PATH = re.compile(r"/(?:lg/file/aion2(?:_tw|_global)?/[A-Za-z0-9_/-]+|download/v2/buckets/[A-Za-z0-9_/-]+)")
PICTURE_MOST = 4 * 1024 * 1024                    # a picture larger than this is not read
ARTICLE_ID = re.compile(r"[a-f0-9]{24}")
CARD_WIDTH, CARD_GAP = 280, 14                    # app.css .news-cards: minmax(280px, 1fr), 14 px apart
PICTURE_HEIGHT = 180                              # .news-preview-image: max-height
_PORTS = {"http": 80, "https": 443}


def _origin(parts: urllib.parse.SplitResult) -> str | None:
    """An address's origin as a browser writes it (``URL.origin``): its scheme, host and a port that is not the
    scheme's own."""
    try:
        port = parts.port
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname}" + (f":{port}" if port and port != _PORTS.get(parts.scheme) else "")


def official(value, region: str) -> str:
    """``value`` when it is an article on the region's official site (news.js ``official``): on its notice or
    update board, with an article id of 24 hex digits and no sign-in in the address; else ""."""
    if region not in REGIONS or not isinstance(value, str):
        return ""
    try:
        url, base = urllib.parse.urlsplit(value), urllib.parse.urlsplit(REGIONS[region][1])
        origin = _origin(url)
        if origin is None or origin != _origin(base) or url.username or url.password:
            return ""
    except ValueError:
        return ""
    if not re.fullmatch(re.escape(base.path) + r"/board/(notice|update)/view", url.path):
        return ""
    ids = urllib.parse.parse_qs(url.query).get("articleId") or [""]
    return value if ARTICLE_ID.fullmatch(ids[0]) else ""


def thumbnail(value) -> str:
    """``value`` when it is a picture on the official download server (news.js ``thumbnail``), else ""."""
    if not isinstance(value, str):
        return ""
    try:
        url = urllib.parse.urlsplit(value)
        fits = (_origin(url) == PICTURE_HOST and not url.username and not url.password and not url.query
                and not url.fragment and PICTURE_PATH.fullmatch(url.path))
    except ValueError:
        return ""
    return value if fits else ""


def when(value) -> str:
    """A moment with its time of day in the computer's clock (news.js ``whenAt``), ``2026-10-23 15:04:05``: from
    milliseconds since 1970 or an ISO date; "—" for none or one that does not read."""
    if value is None or value == "" or isinstance(value, bool):
        return "—"
    try:
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                return "—"
            moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        else:
            text = str(value).strip()
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if moment.tzinfo is None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                moment = moment.replace(tzinfo=timezone.utc)   # a date alone is midnight UTC, as a browser reads it
        return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return "—"


def date(value) -> str:
    """A headline's date, or "Date unavailable" (news.js ``date``)."""
    shown_at = when(value)
    return "Date unavailable" if shown_at == "—" else shown_at


def shown(data, region: str, category: str = "All") -> list[dict]:
    """The headlines to show: the first ``MOST`` of the feed, those of the region (one without a region is the
    global site's) and the category chosen, each with an official article to link to."""
    entries = data.get("entries") if isinstance(data, dict) else None
    rows = entries[:MOST] if isinstance(entries, list) else []
    return [row for row in rows if isinstance(row, dict)
            and (row.get("region") == region if row.get("region") else region == "global")
            and (category == "All" or row.get("category") == category)
            and official(row.get("url"), region)]


def status(busy: bool, error: str, data, region: str) -> str:
    """The page's status line (news.js ``render``)."""
    if busy:
        return f"Loading {REGIONS[region][0]} headlines…"
    if error:
        return error
    if not data:
        return ""
    if data.get("status") == "ready":
        return "Official sources loaded."
    return "Some official sources are unavailable; retained headlines may be stale."


def meta(row: dict, region: str) -> str:
    """A headline's foot: its region, its publisher and when the log server read it."""
    words = f"{REGIONS[region][0]} · {row.get('publisher') or 'Official AION 2 site'}"
    retrieved = row.get("retrieved_at")
    if isinstance(retrieved, (int, float)) and not isinstance(retrieved, bool) and math.isfinite(retrieved):
        words += " · retrieved " + date(retrieved * 1000)
    return words


def _read(url: str) -> bytes:
    """A picture's bytes from the official server; nothing for one larger than ``PICTURE_MOST``."""
    request = urllib.request.Request(url, headers={"User-Agent": "aion2calc"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read(PICTURE_MOST + 1)
    return b"" if len(data) > PICTURE_MOST else data


class Pictures(QObject):
    """The headlines' pictures, read off the interface's thread and handed over as ``loaded(url, bytes)``. Each is
    asked for once; one that cannot be read is not drawn (the web page hides it)."""

    loaded = Signal(str, bytes)

    def __init__(self, parent: QObject | None = None, read=_read):
        super().__init__(parent)
        self.read = read
        self._asked: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gui-news-pictures")

    def ask(self, url: str) -> None:
        if not thumbnail(url) or url in self._asked:
            return
        self._asked.add(url)
        try:
            self._pool.submit(self._get, url)
        except RuntimeError:                     # stopped: its window has closed
            pass

    def _get(self, url: str) -> None:
        try:
            data = self.read(url)
        except Exception:                        # noqa: BLE001 - a picture that cannot be read is left out
            return
        if data:
            self.loaded.emit(url, data)

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class Picture(QWidget):
    """A headline's picture (.news-preview-image): the card's width, at most 180 px high, the picture covering it
    and cropped to fit, its corners rounded. It takes no room until it is read, and a click opens the article."""

    def __init__(self, open_article, parent: QWidget | None = None):
        super().__init__(parent)
        self.open_article = open_article
        self.pixmap = QPixmap()
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)   # the height its width gives it
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setCursor(Qt.PointingHandCursor)
        self.hide()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.pixmap = pixmap
        self.setVisible(not pixmap.isNull())
        self.updateGeometry()
        self.update()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if self.pixmap.isNull() or self.pixmap.width() <= 0:
            return 0
        return min(PICTURE_HEIGHT, round(width * self.pixmap.height() / self.pixmap.width()))

    def sizeHint(self) -> QSize:
        width = self.width() if self.width() > 0 else CARD_WIDTH - 32
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, _event) -> None:
        if self.pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        box = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(box, 5, 5)
        painter.setClipPath(clip)
        scale = max(box.width() / self.pixmap.width(), box.height() / self.pixmap.height())   # object-fit: cover
        width, height = self.pixmap.width() * scale, self.pixmap.height() * scale
        painter.drawPixmap(QRectF(box.center().x() - width / 2, box.center().y() - height / 2, width, height),
                           self.pixmap, QRectF(self.pixmap.rect()))
        painter.end()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.open_article()


class Card(QFrame):
    """One headline (.news-card): its picture, category and date, its title linking to the article, its preview,
    where it comes from, and a button to read it on the official site."""

    def __init__(self, row: dict, region: str, open_link, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("newsCard")
        self.url = official(row.get("url"), region)
        self.picture_url = thumbnail(row.get("image"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.picture = Picture(lambda: open_link(self.url))
        layout.addWidget(self.picture)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.category = QLabel(str(row.get("category") or ""))
        self.category.setObjectName("chip")
        self.category.setVisible(bool(self.category.text()))
        self.date = QLabel(date(row.get("published_at")))
        self.date.setObjectName("muted")
        head.addWidget(self.category)
        head.addStretch(1)
        head.addWidget(self.date)
        layout.addLayout(head)
        self.title = QLabel(f'<a href="{html.escape(self.url)}" style="color: {theme.COLORS["accent"]};">'
                            f'{html.escape(str(row.get("title") or ""))}</a>')      # a link, as app.css draws one
        self.title.setObjectName("newsTitle")
        self.title.setTextFormat(Qt.RichText)
        self.title.setWordWrap(True)
        self.title.setToolTip(self.url)
        self.title.linkActivated.connect(lambda _link: open_link(self.url))
        layout.addWidget(self.title)
        preview = str(row.get("preview") or "")[:PREVIEW]
        self.preview = QLabel(preview)
        self.preview.setWordWrap(True)
        self.preview.setVisible(bool(preview))
        layout.addWidget(self.preview)
        self.meta = QLabel(meta(row, region))
        self.meta.setObjectName("muted")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        self.read = QPushButton("Read on official site ↗")
        self.read.setToolTip(self.url)
        self.read.clicked.connect(lambda: open_link(self.url))
        layout.addWidget(self.read, 0, Qt.AlignLeft)
        layout.addStretch(1)


class NewsPage(QWidget):
    """The News page (Game → News): the official headlines of the region chosen, their category to show, and a
    button to read the feed again. The region is the app's setting ``news_region``; the page reads the feed the
    first time it is shown."""

    def __init__(self, api: AppApi | None, open_link=webbrowser.open, read_picture=_read,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_link = api, open_link
        self.region, self.category = "global", "All"
        self.data, self.busy, self.error, self.serial = None, False, "", 0
        self.started = False
        self.pixmaps: dict[str, QPixmap] = {}
        self.cards: list[Card] = []
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.pictures = Pictures(self, read_picture)
        self.pictures.loaded.connect(self._picture)
        self.setStyleSheet(self._stylesheet())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        heading = QLabel("Official AION 2 news")
        heading.setObjectName("heading")
        head.addWidget(heading)
        head.addSpacing(8)
        head.addWidget(QLabel("News region"))
        self.region_box = QComboBox()
        for key, (label, _site) in REGIONS.items():
            self.region_box.addItem(label, key)
        self.region_box.currentIndexChanged.connect(self._region_chosen)
        head.addWidget(self.region_box)
        self.refresh = QPushButton("Refresh")
        self.refresh.clicked.connect(self.load)
        head.addWidget(self.refresh)
        head.addWidget(QLabel("Show"))
        self.filter_box = QComboBox()
        self.filter_box.addItems(FILTERS)
        self.filter_box.currentTextChanged.connect(self._filtered)
        head.addWidget(self.filter_box)
        head.addStretch(1)
        layout.addLayout(head)

        note = QLabel(NOTE)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.links = QLabel()
        self.links.setTextFormat(Qt.RichText)
        self.links.linkActivated.connect(self.open_link)
        layout.addWidget(self.links)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.unavailable = QLabel("")
        self.unavailable.setObjectName("muted")
        self.unavailable.setWordWrap(True)
        layout.addWidget(self.unavailable)
        self.grid_box = QWidget()
        self.grid = QGridLayout(self.grid_box)
        self.grid.setContentsMargins(0, 6, 0, 6)
        self.grid.setSpacing(CARD_GAP)
        layout.addWidget(self.grid_box)
        self.empty = QLabel(NONE_SHOWN)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.note = QLabel("")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)
        self.columns = 0
        self.render()

    @staticmethod
    def _stylesheet() -> str:
        c = theme.COLORS
        return f"""
        QFrame#newsCard {{ background: {c['panel2']}; border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 8px; }}
        QFrame#newsCard QLabel {{ background: transparent; }}
        QLabel#chip {{ background: rgba(57, 194, 224, 0.12); color: {c['accent']}; border: 1px solid rgba(57, 194, 224, 0.25);
                       border-radius: 3px; padding: 1px 6px; }}
        QLabel#newsTitle {{ font-size: 15px; font-weight: 700; }}
        """

    # ------------------------------------------------------------------ the feed
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.started:
            self.start()

    def start(self) -> None:
        """Read the region the app keeps for the page, then the feed (the first time the page is shown)."""
        self.started = True
        if self.requests is None:
            return
        self.busy = True
        self.render()
        self.requests.get("ui", "/api/ui")

    def load(self) -> None:
        """Ask the log server, through the app, for the region's headlines; an answer to an earlier ask is dropped."""
        if self.requests is None:
            return
        self.serial += 1
        self.busy, self.error = True, ""
        self.render()
        path = "/api/community?path=" + urllib.parse.quote(f"/api/v1/news?region={self.region}", safe="")
        self.requests.get(f"news:{self.serial}:{self.region}", path)

    def _replied(self, name: str, answer) -> None:
        if name == "ui":
            region = answer.get("news_region") if isinstance(answer, dict) else None
            if region in REGIONS and region != self.region:
                self.region = region
                self.region_box.blockSignals(True)
                self.region_box.setCurrentIndex(list(REGIONS).index(region))
                self.region_box.blockSignals(False)
            self.load()
            return
        if not name.startswith("news:"):
            return
        _news, serial, region = name.split(":", 2)
        if int(serial) != self.serial:
            return
        if isinstance(answer, dict) and answer.get("error"):
            self.error = str(answer["error"])
        elif not isinstance(answer, dict) or (region != "global" and answer.get("region") != region):
            self.error = NEEDS_UPDATE
        else:
            self.data = answer
        self.busy = False
        self.render()

    def _failed(self, name: str, why: str) -> None:
        if name == "ui":
            self.load()                          # the app's settings did not come: the global news, then
            return
        if not name.startswith("news:") or int(name.split(":", 2)[1]) != self.serial:
            return
        self.error = why or UNAVAILABLE
        self.busy = False
        self.render()

    def _region_chosen(self, index: int) -> None:
        region = self.region_box.itemData(index)
        if region not in REGIONS or region == self.region:
            return
        self.region, self.data = region, None
        if self.requests is not None:
            self.requests.post("save", "/api/ui", {"news_region": region})
        self.load()

    def _filtered(self, category: str) -> None:
        self.category = category if category in FILTERS else "All"
        self.render()

    # ------------------------------------------------------------------ drawing
    def render(self) -> None:
        site = REGIONS[self.region][1]
        self.links.setText(f'<a href="{site}/board/notice/list" style="color: {theme.COLORS["accent"]};">Official '
                           f'notices</a> · <a href="{site}/board/update/list" style="color: {theme.COLORS["accent"]};">'
                           f'Official updates</a>')
        self.refresh.setEnabled(not self.busy)
        self.status.setText(status(self.busy, self.error, self.data, self.region))
        self.status.setVisible(bool(self.status.text()))
        sources = self.data.get("unavailable_sources") if isinstance(self.data, dict) else None
        sources = [str(source) for source in sources] if isinstance(sources, list) else []
        self.unavailable.setText("Unavailable sources: " + ", ".join(sources) if sources else "")
        self.unavailable.setVisible(bool(sources))
        rows = shown(self.data, self.region, self.category)
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards = [Card(row, self.region, self.open_link) for row in rows]
        for card in self.cards:
            if card.picture_url in self.pixmaps:
                card.picture.set_pixmap(self.pixmaps[card.picture_url])
            elif card.picture_url:
                self.pictures.ask(card.picture_url)
        self.columns = 0
        self._place_cards()
        self.empty.setVisible(not self.cards and not self.busy)
        note = self.data.get("note") if isinstance(self.data, dict) else None
        self.note.setText(str(note or ""))
        self.note.setVisible(bool(note))

    def _place_cards(self) -> None:
        """Lay the cards out in as many columns of at least 280 px as fit, each as wide (repeat(auto-fit, ...)):
        fewer cards than columns share the width between them."""
        width = self.scroll.viewport().width() - 48     # the page's margins
        columns = max(1, min(len(self.cards) or 1, (width + CARD_GAP) // (CARD_WIDTH + CARD_GAP)))
        if columns == self.columns:
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_cards()

    def _picture(self, url: str, data: bytes) -> None:
        image = pictures.decoded(data)
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        self.pixmaps[url] = pixmap
        for card in self.cards:
            if card.picture_url == url:
                card.picture.set_pixmap(pixmap)

    def closeEvent(self, event) -> None:
        self.pictures.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
