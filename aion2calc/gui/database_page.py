"""The native Database page (0.2.429): the game database's state and its item catalog, as the web page shows them
(pages/database.js).

- **Game database:** how many items, characters and encounters it holds and when it last updated, the update under
  way (its phase, its message, how far it is, what changed, its first errors) and the data folder, read every two
  seconds while an update runs and every fifteen otherwise, while the page is shown. **Check for updates** and
  **Full re-sync** start one, as the web page's buttons do.
- **Item catalog:** a search by name and category, each item with its icon (through the app's icon cache), its name
  in its grade's colour, its category and level; an item opens with its fixed stats, its enchantment steps, its
  random roll pool and its skill roll pools.

The arithmetic is kept apart from the page and tested alone.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import json
import math
import urllib.parse

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from . import pictures, theme
from .api import AppApi, Requests
from .news import when

SUBTITLE = "updates itself on every launch from the live sources — no code changes needed for new items, skills or classes"
#: app.css's grade colours in the dark theme (``--g-*``).
GRADE_COLORS = {"Common": "rgba(255, 255, 255, 0.88)", "Rare": "#52b35c", "Legend": "#3d94d8", "Unique": "#e9a43a",
                "Epic": "#ee6c2a", "Mythic": "#d33939", "Special": "#34b798"}
RUNNING_MS, RESTING_MS = 2000, 15000              # how often the database's state is read, an update under way or not
ICON_SIZE = 22


# ------------------------------------------------------------------ the arithmetic
def n0(value) -> str:
    """A whole number grouped in thousands as the web page writes it (``n0``), "—" for none."""
    if value is None or isinstance(value, bool):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(number):
        return "—"
    return f"{theme.js_round(number):,}"


def progress(sync: dict) -> float:
    """How far an update is, in percent: its steps done of its total, 5 while it runs without a total, else 100."""
    total = sync.get("total") or 0
    if total:
        return 100 * float(sync.get("done") or 0) / float(total)
    return 5.0 if sync.get("running") else 100.0


def changed_text(sync: dict) -> str:
    """What the update changed, as the web page writes it (its JSON)."""
    changed = sync.get("changed") or {}
    return "changed: " + json.dumps(changed, separators=(",", ":"), ensure_ascii=False) if changed else ""


def icon_path(url) -> str:
    """The app's cached copy of an item's icon (app.js ``icon``): a path on metabot.gg is that site's."""
    if not url:
        return ""
    url = str(url)
    return "/api/icon?u=" + urllib.parse.quote("https://metabot.gg" + url if url.startswith("/") else url, safe="")


def grade_color(grade) -> str:
    return GRADE_COLORS.get(str(grade or ""), theme.COLORS["text"])


def fixed_pairs(item: dict) -> list[tuple[str, str]]:
    return [(str(key), str(value)) for key, value in (item.get("fixed") or {}).items()]


def enchant_pairs(item: dict) -> list[tuple[str, str]]:
    return [(str(step.get("step")), str(step.get("stats"))) for step in item.get("enchant") or [] if isinstance(step, dict)]


def random_pairs(item: dict) -> list[tuple[str, str, str]]:
    """The random roll pool: each stat, its range and its chance."""
    return [(str(roll.get("stat")), str(roll.get("range")), str(roll.get("chance") or ""))
            for roll in item.get("random") or [] if isinstance(roll, dict)]


def skill_pool_lines(item: dict) -> list[tuple[str, str]]:
    """The skill roll pools: each class with how far its skills go, and the skills."""
    pools = item.get("skill_pools") or {}
    lines = []
    for cls, pool in pools.items():
        if not isinstance(pool, dict):
            continue
        name = str(cls)[:1].upper() + str(cls)[1:]
        lines.append((f"{name} (up to +{pool.get('max_level')})", ", ".join(str(skill) for skill in pool.get("skills") or [])))
    return lines


def last_sync(db: dict) -> str:
    last = db.get("last_sync")
    return when(last["at"] * 1000) if isinstance(last, dict) and last.get("at") is not None else "never"


# ------------------------------------------------------------------ the parts
class Icons(QObject):
    """The items' icons through the app's icon cache, read off the interface's thread four at a time, each once."""

    loaded = Signal(str, bytes)

    def __init__(self, api: AppApi | None, parent: QObject | None = None):
        super().__init__(parent)
        self.api = api
        self._asked: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gui-icons")

    def ask(self, path: str) -> None:
        if self.api is None or not path or path in self._asked:
            return
        self._asked.add(path)
        try:
            self._pool.submit(self._get, path)
        except RuntimeError:                     # stopped: its window has closed
            pass

    def _get(self, path: str) -> None:
        try:
            data = self.api.get_bytes(path)
        except Exception:                        # noqa: BLE001 - an icon that cannot be read is left out
            return
        if data:
            self.loaded.emit(path, data)

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def _label(text: str = "", name: str = "", wrap: bool = True, rich: bool = False) -> QLabel:
    """A label of plain text, so what the database holds is never read as markup; rich only where the page builds
    the markup itself."""
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


class Window(QFrame):
    """A window of the web page (``.win``): its head with the title, a line under it and its tools, then its body."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("win")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QFrame()
        head.setObjectName("winHead")
        self.head = QHBoxLayout(head)
        self.head.setContentsMargins(14, 9, 14, 9)
        self.head.setSpacing(10)
        self.title = _label(title.upper(), "winTitle", wrap=False)
        self.head.addWidget(self.title)
        self.subtitle = _label(subtitle, "muted")
        self.head.addWidget(self.subtitle, 1)
        self.subtitle.setVisible(bool(subtitle))      # once in the head: shown alone, it would be a window of its own
        outer.addWidget(head)
        body = QWidget()
        body.setObjectName("winBody")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(14, 14, 14, 14)
        self.body.setSpacing(10)
        outer.addWidget(body)

    def tool(self, button: QPushButton) -> QPushButton:
        self.head.addWidget(button)
        return button


class Kpi(QFrame):
    """One count of the database (``.kpi``): its name over its value."""

    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("kpi")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(_label(name.upper(), "kpiName", wrap=False))
        self.value = _label("—", "kpiValue", wrap=False)
        layout.addWidget(self.value)


def pairs_grid(pairs: list[tuple[str, str]], columns: int = 2) -> QWidget:
    """Names and values (``.statgrid``), side by side in ``columns``: each name muted on the left, its value (rich
    text the page built) on the right, a dotted line under the pair."""
    box = QWidget()
    box.setObjectName("statgrid")
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(4)
    for index, (name, value) in enumerate(pairs):
        row = QFrame()
        row.setObjectName("statrow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 2, 0, 2)
        line.addWidget(_label(name, "muted", wrap=False))
        shown = _label(value, wrap=True, rich=True)       # the pair's free room, wrapping only when it must
        shown.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        line.addWidget(shown, 1)
        grid.addWidget(row, index // columns, index % columns)
    for column in range(columns):
        grid.setColumnStretch(column, 1)
    return box


class DatabasePage(QWidget):
    """Game → Database. It reads the database's state when it is shown, and again while it stays shown."""

    def __init__(self, api: AppApi | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api = api
        self.status: dict | None = None
        self.items: list[dict] = []
        self.item: dict | None = None
        self.icons_shown: dict[str, QPixmap] = {}
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.icons = Icons(api, self)
        self.icons.loaded.connect(self._icon)
        self.poll = QTimer(self)
        self.poll.setSingleShot(True)
        self.poll.timeout.connect(self.read_status)
        self.setStyleSheet(self._stylesheet())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        self.database = Window("Game database", SUBTITLE)
        self.check = self.database.tool(QPushButton("Check for updates"))
        self.check.clicked.connect(lambda: self._sync({}))
        self.full = self.database.tool(QPushButton("Full re-sync"))
        self.full.clicked.connect(lambda: self._sync({"force": True, "budget": 3600}))
        kpis = QGridLayout()
        kpis.setSpacing(10)
        self.kpis = {key: Kpi(name) for key, name in (("items", "Items"), ("characters", "Characters"),
                                                      ("encounters", "Encounters"), ("last", "Last sync"))}
        for index, kpi in enumerate(self.kpis.values()):
            kpis.addWidget(kpi, 0, index)
        self.database.body.addLayout(kpis)
        line = QHBoxLayout()
        line.setSpacing(8)
        self.phase = _label("", "phase", wrap=False)
        self.message = _label("", "muted")
        self.steps = _label("", "faint", wrap=False)
        line.addWidget(self.phase)
        line.addWidget(self.message, 1)
        line.addWidget(self.steps)
        self.database.body.addLayout(line)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setRange(0, 1000)
        self.database.body.addWidget(self.bar)
        self.changed = _label("", "muted")
        self.database.body.addWidget(self.changed)
        self.errors = _label("", "bad")
        self.database.body.addWidget(self.errors)
        self.folder = _label("", "faint")
        self.database.body.addWidget(self.folder)
        layout.addWidget(self.database)

        self.catalog = Window("Item catalog")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search items")
        self.search.returnPressed.connect(self.find)
        row.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.setAccessibleName("Category")
        self.category.addItem("all categories", "")
        row.addWidget(self.category)
        self.find_button = QPushButton("Search")
        self.find_button.clicked.connect(self.find)
        row.addWidget(self.find_button)
        self.catalog.body.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Item", "Category", "Item level"])
        self.table.horizontalHeaderItem(0).setToolTip("Icon")
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, ICON_SIZE + 12)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(lambda row, _column: self.open_item(row))
        self.table.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # every row shown; the page scrolls
        self.table.hide()
        self.catalog.body.addWidget(self.table)
        self.found = _label("", "muted")
        self.found.hide()
        self.catalog.body.addWidget(self.found)
        self.detail = Window("")
        self.detail.hide()
        self.catalog.body.addWidget(self.detail)
        layout.addWidget(self.catalog)
        layout.addStretch(1)

    @staticmethod
    def _stylesheet() -> str:
        c = theme.COLORS
        return f"""
        QFrame#win {{ background: rgba(16, 22, 35, 0.94); border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 8px; }}
        QFrame#winHead {{ background: rgba(232, 207, 142, 0.06); border: none; border-bottom: 1px solid rgba(206, 182, 122, 0.28);
                          border-top-left-radius: 8px; border-top-right-radius: 8px; }}
        QWidget#winBody, QWidget#statgrid {{ background: transparent; }}
        QFrame#win QLabel {{ background: transparent; }}
        QLabel#winTitle {{ color: {c['gold']}; font-size: 15px; font-weight: 700; letter-spacing: 1.4px; }}
        QFrame#kpi {{ background: rgba(6, 9, 15, 0.65); border: 1px solid {c['line']}; border-radius: 6px; }}
        QLabel#kpiName {{ color: {c['muted']}; letter-spacing: 0.6px; }}
        QLabel#kpiValue {{ font-size: 19px; font-weight: 700; }}
        QLabel#phase {{ color: {c['gold']}; font-weight: 700; }}
        QLabel#faint {{ color: {c['faint']}; }}
        QLabel#bad {{ color: {c['bad']}; }}
        QLabel#section {{ color: {c['gold']}; font-weight: 700; }}
        QFrame#statrow {{ background: transparent; border: none; border-bottom: 1px dotted {c['line']}; }}
        QProgressBar {{ background: rgba(6, 9, 15, 0.65); border: none; border-radius: 4px; }}
        QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a8fb0, stop:1 #39c2e0); }}
        """

    # ------------------------------------------------------------------ the database
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.read_status()

    def hideEvent(self, event) -> None:
        self.poll.stop()
        super().hideEvent(event)

    def read_status(self) -> None:
        if self.requests is not None:
            self.requests.get("status", "/api/status")

    def _sync(self, body: dict) -> None:
        if self.requests is not None:
            self.requests.post("sync", "/api/sync", body)

    def _next(self, running: bool) -> None:
        if self.isVisible():
            self.poll.start(RUNNING_MS if running else RESTING_MS)

    def _replied(self, name: str, answer) -> None:
        if name == "status":
            self.status = answer if isinstance(answer, dict) else None
            self._show_status()
            sync = (self.status or {}).get("sync")
            self._next(bool(isinstance(sync, dict) and sync.get("running")))
        elif name == "sync":
            self.poll.stop()
            self.read_status()
        elif name == "items":
            self.items = [item for item in answer if isinstance(item, dict)] if isinstance(answer, list) else []
            self._show_items()
        elif name.startswith("item:"):
            if isinstance(answer, dict):
                self.item = answer
                self._show_item()

    def _failed(self, name: str, why: str) -> None:
        if name == "status":
            self._next(False)
        elif name == "items":
            self.items = []
            self.table.hide()
            self.found.setText(f"Could not search the catalog: {why}")
            self.found.show()

    def _show_status(self) -> None:
        status = self.status or {}
        db = status.get("db") if isinstance(status.get("db"), dict) else {}
        self.kpis["items"].value.setText(n0(db.get("items")))
        self.kpis["characters"].value.setText(str(db.get("characters", "—")))
        self.kpis["encounters"].value.setText(str(db.get("encounters", "—")))
        self.kpis["last"].value.setText(last_sync(db))
        sync = status.get("sync") if isinstance(status.get("sync"), dict) else None
        for widget in (self.phase, self.message, self.steps, self.bar, self.changed, self.errors):
            widget.setVisible(sync is not None)
        if sync is not None:
            self.phase.setText(str(sync.get("phase") or ""))
            self.message.setText(str(sync.get("message") or ""))
            self.steps.setText(f"{sync.get('done')}/{sync.get('total')}")
            self.bar.setValue(round(10 * progress(sync)))
            self.changed.setText(changed_text(sync))
            self.changed.setVisible(bool(self.changed.text()))
            errors = [str(error) for error in (sync.get("errors") or [])[:5]]
            self.errors.setText("\n".join(errors))
            self.errors.setVisible(bool(errors))
        self.folder.setText(f"Data folder: {status.get('home') or ''}")
        chosen = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("all categories", "")
        for entry in db.get("categories") or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                self.category.addItem(f"{entry[0]} ({entry[1]})", entry[0])
        self.category.setCurrentIndex(max(0, self.category.findData(chosen)))
        self.category.blockSignals(False)

    # ------------------------------------------------------------------ the catalog
    def find(self) -> None:
        if self.requests is None:
            return
        query = urllib.parse.urlencode({"search": self.search.text(), "category": self.category.currentData() or ""})
        self.requests.get("items", "/api/items?" + query)

    def _show_items(self) -> None:
        self.found.hide()
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            picture = QTableWidgetItem()
            path = icon_path(item.get("icon"))
            if path in self.icons_shown:
                picture.setIcon(self.icons_shown[path])
            elif path:
                self.icons.ask(path)
            name = QTableWidgetItem(str(item.get("name") or ""))
            name.setForeground(QColor(grade_color(item.get("grade"))))
            font = name.font()
            font.setWeight(font.Weight.DemiBold)
            name.setFont(font)
            name.setToolTip(str(item.get("grade") or ""))
            level = QTableWidgetItem("" if item.get("item_level") is None else str(item["item_level"]))
            level.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for column, cell in enumerate((picture, name, QTableWidgetItem(str(item.get("category") or "")), level)):
                self.table.setItem(row, column, cell)
        self.table.resizeRowsToContents()
        rows = sum(self.table.rowHeight(row) for row in range(self.table.rowCount()))
        self.table.setFixedHeight(self.table.horizontalHeader().height() + rows + 2 * self.table.frameWidth())
        self.table.setVisible(True)

    def _icon(self, path: str, data: bytes) -> None:
        image = pictures.decoded(data)
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image).scaled(ICON_SIZE, ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icons_shown[path] = pixmap
        for row, item in enumerate(self.items):
            if icon_path(item.get("icon")) == path and self.table.item(row, 0) is not None:
                self.table.item(row, 0).setIcon(pixmap)

    def open_item(self, row: int) -> None:
        if self.requests is None or not 0 <= row < len(self.items):
            return
        slug = str(self.items[row].get("slug") or "")
        self.requests.get(f"item:{slug}", "/api/items/" + urllib.parse.quote(slug, safe=""))

    def _show_item(self) -> None:
        item = self.item or {}
        detail = self.detail
        detail.title.setText(str(item.get("name") or item.get("slug") or "").upper())
        detail.subtitle.setText(f"{item.get('grade') or ''} {item.get('category') or ''}".strip())
        detail.subtitle.setVisible(bool(detail.subtitle.text()))
        while detail.body.count():
            child = detail.body.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()
            elif child.layout() is not None:
                _empty(child.layout())
        columns = QHBoxLayout()
        columns.setSpacing(24)
        left, right = QVBoxLayout(), QVBoxLayout()
        faint = theme.COLORS["faint"]
        rolls = [(stat, f"{html.escape(span)} <span style='color: {faint};'>{html.escape(chance)}</span>")
                 for stat, span, chance in random_pairs(item)]
        for column, title, pairs in ((left, "FIXED", [(key, html.escape(value)) for key, value in fixed_pairs(item)]),
                                     (left, "ENCHANT", [(key, html.escape(value)) for key, value in enchant_pairs(item)]),
                                     (right, "RANDOM ROLL POOL", rolls)):
            column.addWidget(_label(title, "section"))
            column.addWidget(pairs_grid(pairs))
        pools = skill_pool_lines(item)
        if pools:
            right.addWidget(_label("SKILL ROLL POOLS", "section"))
            for heading, skills in pools:
                right.addWidget(_label(f"<b>{html.escape(heading)}</b>: {html.escape(skills)}", rich=True))
        left.addStretch(1)
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        detail.body.addLayout(columns)
        detail.show()

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.icons.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)


def _empty(layout) -> None:
    """Take a layout's items away, its widgets deleted."""
    while layout.count():
        child = layout.takeAt(0)
        if child.widget() is not None:
            child.widget().deleteLater()
        elif child.layout() is not None:
            _empty(child.layout())
