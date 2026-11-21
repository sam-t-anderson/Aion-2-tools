"""The native Gathering page (0.2.430): what you gathered and took from dungeon reward cubes, and everyone's drop rates,
as the web page shows them (pages/gathering.js and ``A2Gathering`` in static/gathering.js).

Your records are this computer's gathering log (``/api/gathering``); everyone's are the log server's drop rates
(``/api/v1/gathering/stats``, through the app). Both have one shape (``combat/gathering.summary``). The page has:

- your totals: gathers, items gathered, better-grade and failed results with their shares, and reward cubes;
- **Gathering:** each kind of node, everyone's or yours, with where it grows, how often it gives each result, and
  what it gave, how often and how many;
- **Dungeon materials:** each dungeon's reward cubes and the crafting materials they held (every drop on asking);
- **Your log:** your latest gathers and reward cubes.

The arithmetic is kept apart from the page and tested alone.
"""
from __future__ import annotations

import html
import math
import urllib.parse

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme
from .api import AppApi, Requests
from .database_page import DatabasePage, Kpi, Window
from .news import when

SUBTITLE = "what you gather and take from dungeon reward cubes, and everyone's drop rates"
RESULTS = {"normal": "Normal", "better": "Better grade", "failed": "Failed"}
KINDS = {"dungeon": "dungeon node", "open_world": "open-world node"}
PLACES_SHOWN = 5
TABS = (("nodes", "Gathering"), ("dungeons", "Dungeon materials"), ("log", "Your log"))
#: The grade dots' colours (app.css ``.gt-dot``); any other grade is muted.
DOTS = {"Rare": "#3fb37a", "Epic": "#49a0e0", "Unique": "#e0a030", "Heroic": "#a07ce0", "Special": "#e06aa0"}
NODES_NOTE = ("How often each kind of node gives each grade, and how many a gather gives. A better-grade result gives "
              "the Fine or Pure material; a failed one gives nothing.")
DUNGEONS_NOTE = ("A dungeon's reward cube pays out the run's loot when claimed. \"In cubes\" is the share of claimed cubes "
                 "holding the material; \"How many\" is the average count when it is there.")
NO_COMMUNITY = ("Everyone's drop rates are not available: the log server does not have them yet, or cannot be "
                "reached.")
NO_MATERIAL = "No reward cube held a crafting material yet. Show every drop to see what they held."
NO_LOG = "Nothing recorded yet: run the Live Meter while you gather or open a dungeon's reward cube."


# ------------------------------------------------------------------ the arithmetic
def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def num(value) -> str:
    """A whole number grouped in thousands, "—" for none (gathering.js ``num``)."""
    return f"{theme.js_round(value):,}" if _finite(value) else "—"


def pct(value) -> str:
    """A share to a tenth of a percent, "—" for none (gathering.js ``pct``)."""
    return theme.fixed(value * 100, 1) + "%" if _finite(value) else "—"


def item_name(row: dict) -> str:
    return str(row.get("name") or f"Item {row.get('item')}")


def dot(grade) -> str:
    return DOTS.get(str(grade or ""), theme.COLORS["muted"])


def share_of(part, whole) -> str:
    """A part's share of a whole, "—" without a whole."""
    return pct(part / whole) if _finite(part) and _finite(whole) and whole else "—"


def kind_label(node: dict) -> str:
    """Where a kind of node grows, by its records: a dungeon, the open world or both; "" when they do not say."""
    kinds = [kind for kind in node.get("kinds") or [] if kind in KINDS]
    if not kinds:
        return ""
    return "dungeon and open-world node" if len(kinds) > 1 else KINDS[kinds[0]]


def node_title(node: dict) -> str:
    """A node card's title: its material, where it grows, its gathers and how many players reported it."""
    kind = kind_label(node)
    who = f" · {num(node['reporters'])} players" if _finite(node.get("reporters")) else ""
    return f"{node.get('name')}{' — ' + kind if kind else ''} · {num(node.get('gathers'))} gathers{who}"


def where_line(node: dict) -> str:
    """The places a kind of node was gathered, the most gathers first, five of them and how many more."""
    places = [place for place in node.get("places") or [] if isinstance(place, dict) and place.get("name")]
    if not places:
        return ""
    shown = ", ".join(str(place["name"]) for place in places[:PLACES_SHOWN])
    more = f" and {num(len(places) - PLACES_SHOWN)} more" if len(places) > PLACES_SHOWN else ""
    return f"Found in {shown}{more}"


def results_line(node: dict) -> list[tuple[str, str]]:
    """Each result with its share of the node's gathers."""
    results = node.get("results") or {}
    return [(label, share_of(results.get(key) or 0, node.get("gathers"))) for key, label in RESULTS.items()]


def node_count(row: dict) -> str:
    """How many a gather of an item gives: its average, else its count over its gathers, to two places."""
    if _finite(row.get("average")):
        return theme.fixed(row["average"], 2)
    if row.get("gathers"):
        return theme.fixed((row.get("count") or 0) / row["gathers"], 2)
    return "—"


def cube_count(row: dict) -> str:
    """How many of a drop a reward cube holds when it holds it, to at most two places (``toLocaleString``)."""
    if not _finite(row.get("average")):
        return "—"
    shown = f"{round(row['average'], 2):,.2f}".rstrip("0").rstrip(".")
    return shown


def dungeon_rows(data, show_all: bool) -> list[tuple[dict, list[dict]]]:
    """Each dungeon with its drops: the crafting materials, or every drop on asking; a dungeon with none is out."""
    rows = []
    for place in (data or {}).get("dungeons") or []:
        items = [row for row in place.get("items") or [] if show_all or row.get("material")]
        if items:
            rows.append((place, items))
    return rows


def dungeon_title(place: dict) -> str:
    who = f" · {num(place['reporters'])} players" if _finite(place.get("reporters")) else ""
    return f"{place.get('name') or 'Unknown place'} · {num(place.get('cubes'))} reward cubes{who}"


def what(row: dict) -> str:
    """A log entry, as rich text: a gather's item and how many (a failed one gave nothing), or a reward cube's
    materials."""
    if row.get("kind") == "gather":
        name = _dotted(row)
        if row.get("result") == "failed":
            return f"{name} <span style='color: {theme.COLORS['muted']};'>Failed: nothing gathered</span>"
        return (f"{name} ×{num(row.get('count'))} "
                f"<span style='color: {theme.COLORS['muted']};'>{html.escape(RESULTS.get(row.get('result'), ''))}</span>")
    items = row.get("items") or []
    materials = [f"{_dotted(it)} ×{num(it.get('count'))}" for it in items if isinstance(it, dict) and it.get("material")]
    return (f"Reward cube: {', '.join(materials) or 'no crafting materials'} "
            f"<span style='color: {theme.COLORS['muted']};'>({num(len(items))} drops)</span>")


def _dotted(row: dict) -> str:
    return f"<span style='color: {dot(row.get('grade'))};'>●</span> {html.escape(item_name(row))}"


def empty(what_: str, source: str, mine, community_error: str, mine_error: str) -> str:
    """What a tab says with nothing to show."""
    if source == "everyone":
        if community_error:
            return community_error
        return (f"Nobody has shared any {what_} yet. The desktop app shares them while \"Share gathering and drop data\" "
                "is on in Settings.")
    if not mine:
        return mine_error or "Nothing recorded yet."
    return f"No {what_} recorded yet: run the Live Meter while you play and they appear here."


def sharing_line(sharing: bool) -> str:
    """The page's note on sharing, as rich text with a link to Settings."""
    settings = f"<a href='page:settings' style='color: {theme.COLORS['accent']};'>Settings</a>"
    if sharing:
        return ("The Live Meter records what you gather and what dungeon reward cubes give, and shares it for everyone's "
                f"drop rates (\"Share gathering and drop data\" in {settings}).")
    return ("The Live Meter records what you gather and what dungeon reward cubes give. Sharing is off, so your records "
            f"stay on this computer ({settings}).")


# ------------------------------------------------------------------ the page
def _label(text: str = "", name: str = "", rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


def _dot_icon(grade) -> QIcon:
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(dot(grade)))
    painter.drawEllipse(0, 0, 10, 10)
    painter.end()
    return QIcon(pixmap)


class FullTable(QTableWidget):
    """A table as tall as its rows (``table.t``), so the page scrolls rather than the table: its height is worked out
    as the layout asks for it, once Qt's styles have given the rows and the head their sizes."""

    def __init__(self, rows: int, columns: int, parent: QWidget | None = None):
        super().__init__(rows, columns, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        rows = sum(self.rowHeight(row) for row in range(self.rowCount()))
        height = self.horizontalHeader().sizeHint().height() + rows + 2 * self.frameWidth()
        return QSize(super().sizeHint().width(), height)

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), self.sizeHint().height())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.resizeRowsToContents()                   # the rows at the styled font's height
        self.updateGeometry()


def table(headers: list[str], rows: list[list], right: tuple[int, ...] = (), stretch: int = 0) -> QTableWidget:
    """A table of every row (``table.t``), column ``stretch`` taking the room the others leave. A cell is text,
    ``(grade, name)`` for an item with its grade's dot, or a label of rich text."""
    widget = FullTable(len(rows), len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionMode(QAbstractItemView.NoSelection)
    widget.setFocusPolicy(Qt.NoFocus)
    header = widget.horizontalHeader()
    for column in range(len(headers)):
        header.setSectionResizeMode(column, QHeaderView.Stretch if column == stretch else QHeaderView.ResizeToContents)
    for column in right:
        widget.horizontalHeaderItem(column).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            if isinstance(cell, tuple):
                grade, name = cell
                entry = QTableWidgetItem(_dot_icon(grade), name)
            elif isinstance(cell, QLabel):
                widget.setCellWidget(r, c, cell)
                continue
            else:
                entry = QTableWidgetItem(str(cell))
            if c in right:
                entry.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            widget.setItem(r, c, entry)
    widget.resizeRowsToContents()
    return widget


class GatheringPage(QWidget):
    """Game → Gathering. It reads your records and everyone's each time it is shown."""

    def __init__(self, api: AppApi | None, show_page=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.show_page = api, show_page
        self.tab, self.source, self.show_all = "nodes", "everyone", False
        self.mine: dict | None = None
        self.community: dict | None = None
        self.mine_error = self.community_error = ""
        self.loading = True
        self.pending: set[str] = set()
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
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
        self.window_ = Window("Gathering", SUBTITLE)
        layout.addWidget(self.window_)
        layout.addStretch(1)
        body = self.window_.body
        self.sharing = _label("", "muted", rich=True)
        self.sharing.linkActivated.connect(self._link)
        self.sharing.hide()
        body.addWidget(self.sharing)
        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self.kpis = {key: Kpi(name) for key, name in (("gathers", "Gathers"), ("gathered", "Items gathered"),
                                                      ("better", "Better grade"), ("failed", "Failed"),
                                                      ("cubes", "Reward cubes"))}
        for kpi in self.kpis.values():
            kpi.value.setTextFormat(Qt.RichText)
            kpis.addWidget(kpi)
        self.kpi_box = QWidget()
        self.kpi_box.setObjectName("kpiRow")
        self.kpi_box.setLayout(kpis)
        body.addWidget(self.kpi_box)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_buttons = {}
        for key, words in TABS:
            button = QPushButton(words)
            button.setObjectName("tab")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, key=key: self.set_tab(key))
            tabs.addWidget(button)
            self.tab_buttons[key] = button
        tabs.addStretch(1)
        body.addLayout(tabs)
        self.panel = QVBoxLayout()
        self.panel.setSpacing(10)
        body.addLayout(self.panel)
        self.render()

    @staticmethod
    def _stylesheet() -> str:
        c = theme.COLORS
        # The windows and the counts as the Database page draws them, then the tabs and the cards.
        return DatabasePage._stylesheet() + f"""
        QPushButton#tab, QPushButton#seg {{ border-radius: 6px; padding: 5px 12px; }}
        QPushButton#tab:checked, QPushButton#seg:checked {{ background: {c['hover']}; color: {c['gold']}; border-color: {c['gold_dim']}; }}
        QFrame#card {{ background: {c['panel2']}; border: 1px solid {c['line']}; border-radius: 8px; }}
        QFrame#card QLabel {{ background: transparent; }}
        QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
        QWidget#kpiRow {{ background: transparent; }}
        """

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load()

    def load(self) -> None:
        """Your records and everyone's, read afresh."""
        if self.requests is None or self.pending:
            return
        self.loading = True
        self.pending = {"mine", "community"}
        self.render()
        self.requests.get("mine", "/api/gathering")
        self.requests.get("community", "/api/community?path=" + urllib.parse.quote("/api/v1/gathering/stats", safe=""))

    def _replied(self, name: str, answer) -> None:
        if name == "mine":
            if isinstance(answer, dict) and not answer.get("error"):
                self.mine, self.mine_error = answer, ""
            else:
                self.mine = None
                self.mine_error = str((answer or {}).get("error") if isinstance(answer, dict) else "") or \
                    "Your records could not be read."
        elif name == "community":
            if isinstance(answer, dict) and not answer.get("error"):
                self.community, self.community_error = answer, ""
            else:
                self.community, self.community_error = None, NO_COMMUNITY
        self._settle(name)

    def _failed(self, name: str, why: str) -> None:
        if name == "mine":
            self.mine, self.mine_error = None, why or "Your records could not be read."
        elif name == "community":
            self.community, self.community_error = None, NO_COMMUNITY
        self._settle(name)

    def _settle(self, name: str) -> None:
        self.pending.discard(name)
        if self.pending:
            return
        if not self.community and self.mine:
            self.source = "yours"
        self.loading = False
        self.render()

    def _link(self, href: str) -> None:
        if href.startswith("page:") and self.show_page is not None:
            self.show_page(href[5:])

    # ------------------------------------------------------------------ choices
    def set_tab(self, tab: str) -> None:
        self.tab = tab if tab in dict(TABS) else "nodes"
        self.render()

    def set_source(self, source: str) -> None:
        self.source = source
        self.render()

    def set_show_all(self, show_all: bool) -> None:
        self.show_all = show_all
        self.render()

    # ------------------------------------------------------------------ drawing
    def view(self) -> dict | None:
        return self.mine if self.source == "yours" else self.community

    def render(self) -> None:
        mine = self.mine
        if mine is not None:
            self.sharing.setText(sharing_line(mine.get("sharing") is not False))
        self.sharing.setVisible(mine is not None)
        self.kpi_box.setVisible(bool(mine))
        if mine:
            results = mine.get("results") or {}
            gathers = mine.get("gathers")

            def share(n):
                return (f" <span style='color: {theme.COLORS['muted']}; font-size: 13px; font-weight: 400;'>"
                        f"({share_of(n, gathers)})</span>") if gathers else ""
            self.kpis["gathers"].value.setText(num(gathers))
            self.kpis["gathered"].value.setText(num(mine.get("gathered")))
            self.kpis["better"].value.setText(num(results.get("better")) + share(results.get("better") or 0))
            self.kpis["failed"].value.setText(num(results.get("failed")) + share(results.get("failed") or 0))
            self.kpis["cubes"].value.setText(num(mine.get("cubes")))
        for key, button in self.tab_buttons.items():
            button.setChecked(key == self.tab)
        _empty(self.panel)
        if self.loading and not self.mine and not self.community:
            self.panel.addWidget(_label("Loading…", "muted"))
            return
        if self.tab == "nodes":
            self._source_row(_label(NODES_NOTE, "muted"))
            self._nodes()
        elif self.tab == "dungeons":
            check = QCheckBox("Show every drop (equipment, currency)")
            check.setChecked(self.show_all)
            check.toggled.connect(self.set_show_all)
            self._source_row(check)
            self.panel.addWidget(_label(DUNGEONS_NOTE, "muted"))
            self._dungeons()
        else:
            self._log()

    def _source_row(self, beside: QWidget) -> None:
        row = QHBoxLayout()
        row.setSpacing(4)
        for key, words in (("everyone", "Everyone"), ("yours", "This computer")):
            button = QPushButton(words)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setChecked(self.source == key)
            button.clicked.connect(lambda _checked=False, key=key: self.set_source(key))
            row.addWidget(button)
        row.addSpacing(12)
        row.addWidget(beside, 1)
        self.panel.addLayout(row)

    def _say(self, words: str) -> None:
        self.panel.addWidget(_label(words, "muted"))

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(_label(title, "cardTitle"))
        self.panel.addWidget(card)
        return card, layout

    def _nodes(self) -> None:
        rows = (self.view() or {}).get("nodes") or []
        if not rows:
            return self._say(empty("gathering", self.source, self.mine, self.community_error, self.mine_error))
        for node in rows:
            _card, layout = self._card(node_title(node))
            where = where_line(node)
            if where:
                layout.addWidget(_label(where, "muted"))
            layout.addWidget(_label(" · ".join(f"{html.escape(label)} <b>{share}</b>" for label, share in results_line(node)),
                                    rich=True))
            layout.addWidget(table(["Gave", "Grade", "Chance", "How many"],
                                   [[(row.get("grade"), item_name(row)), row.get("grade") or "—", pct(row.get("share")),
                                     node_count(row)] for row in node.get("items") or [] if isinstance(row, dict)],
                                   right=(2, 3)))

    def _dungeons(self) -> None:
        data = self.view()
        if not (data or {}).get("dungeons"):
            return self._say(empty("reward cubes", self.source, self.mine, self.community_error, self.mine_error))
        rows = dungeon_rows(data, self.show_all)
        if not rows:
            return self._say(NO_MATERIAL)
        for place, items in rows:
            _card, layout = self._card(dungeon_title(place))
            layout.addWidget(table(["Drop" if self.show_all else "Material", "Grade", "In cubes", "How many"],
                                   [[(row.get("grade"), item_name(row)), row.get("grade") or "—", pct(row.get("share")),
                                     cube_count(row)] for row in items],
                                   right=(2, 3)))

    def _log(self) -> None:
        if not self.mine:
            return self._say(self.mine_error or "Nothing recorded yet.")
        rows = [row for row in self.mine.get("recent") or [] if isinstance(row, dict)]
        if not rows:
            return self._say(NO_LOG)
        self.panel.addWidget(table(["When", "Where", "What", "Character"],
                                   [[when((row.get("t") or 0) * 1000) if row.get("t") is not None else "—",
                                     row.get("place") or "—", _label(what(row), rich=True), row.get("character") or "—"]
                                    for row in rows], stretch=2))

    def closeEvent(self, event) -> None:
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)


def _empty(layout) -> None:
    """Take a layout's parts away at once: each widget off the page now and deleted later."""
    while layout.count():
        child = layout.takeAt(0)
        widget, inner = child.widget(), child.layout()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif inner is not None:
            _empty(inner)
