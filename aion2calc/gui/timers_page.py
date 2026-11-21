"""The native Timers page (0.2.428): what ``timers.py`` works out, drawn as the web page draws it (pages/timers.js and
``A2Timers`` in static/timers.js), in four sections:

- **Regional event timers:** the region and Korean matching group the app keeps (``event_region``, ``event_group``,
  which the overlay's events strip reads too), the schedule's source, the computer's clock, and a card for each
  event counting down to its window or its end, every second while the page is shown.
- **Field boss respawn reference:** the bundled reference by zone, searchable.
- **Field boss kills by server:** the kills the log server has for your server, which the live meter tells, with
  when each boss is expected back.
- **Recorded boss defeats:** the observations the log server has, by region and boss.

A source log opens in the web interface; the schedule's sources open in the browser.
"""
from __future__ import annotations

import html
import time
import urllib.parse
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from . import theme, timers
from .api import AppApi, Requests

CARD_WIDTH, CARD_GAP = 280, 14                    # app.css .news-cards, which the event cards are too


def _now() -> float:
    return time.time() * 1000


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    if rich:
        label.setTextFormat(Qt.RichText)
    return label


class Fold(QWidget):
    """A part that opens and closes under its title, as a ``<details>`` element does."""

    def __init__(self, title: str, opened: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        self.button = QToolButton()
        self.button.setObjectName("fold")
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.button.toggled.connect(self.set_open)
        layout.addWidget(self.button, 0, Qt.AlignLeft)
        self.body = QWidget()
        self.body.setObjectName("foldBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(20, 0, 0, 4)
        self.body_layout.setSpacing(4)
        layout.addWidget(self.body)
        self.button.setChecked(opened)
        self.set_open(opened)

    def set_open(self, opened: bool) -> None:
        self.button.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.body.setVisible(opened)

    def add(self, widget: QWidget) -> QWidget:
        self.body_layout.addWidget(widget)
        return widget


class CardGrid(QWidget):
    """Cards in as many columns of at least 280 px as fit, 14 px apart and as wide as each other; fewer cards than
    columns share the width (app.css ``.news-cards``)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setSpacing(CARD_GAP)
        self.cards: list[QWidget] = []
        self.columns = 0

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width())

    def set_cards(self, cards: list[QWidget]) -> None:
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards = list(cards)
        self.columns = 0
        self.place(self.width())

    def place(self, width: int) -> None:
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


class EventCard(QFrame):
    """One event's card: its name, its schedule, what it is, and its countdown, which ``tick`` moves on."""

    def __init__(self, item: dict, group, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("newsCard")
        self.item = item
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        self.name = _label(str(item["event"].get("name") or ""), "cardTitle")
        self.schedule = _label(timers.schedule_line(item, group), "muted")
        self.note = _label(timers.forecast_note(item["event"]))
        self.status = _label()
        self.countdown = _label("", "countdown")
        self.next = _label()
        self.upcoming = _label("", "muted")
        for widget in (self.name, self.schedule, self.note, self.status, self.countdown, self.next, self.upcoming):
            layout.addWidget(widget)
        self.unavailable = _label(timers.NO_GROUP)
        self.unavailable.setVisible(item["unavailable"])
        layout.addWidget(self.unavailable)
        layout.addStretch(1)
        for widget in (self.status, self.countdown, self.next, self.upcoming):
            widget.setVisible(not item["unavailable"])

    def tick(self, now: float) -> None:
        if self.item["unavailable"]:
            return
        state = timers.card_state(self.item, now)
        self.status.setText(state["status"])
        self.countdown.setText(state["countdown"])
        self.next.setText(state["next"])
        self.next.setVisible(bool(state["next"]))
        self.upcoming.setText(state["upcoming"])


class TimersPage(QWidget):
    """Game → Timers. It reads the app's region, the schedules and the respawn reference the first time it is
    shown, and your server and faction from the live meter each time; its clocks move while it is shown."""

    def __init__(self, api: AppApi | None, open_web=None, open_link=webbrowser.open, now=_now,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_web, self.open_link, self.now = api, open_web, open_link, now
        self.catalog: dict | None = None
        self.field_catalog: dict | None = None
        self.region, self.group = "", ""
        self.prepared: list[dict] | None = None
        self.prepared_day = ""
        self.identified: dict | None = None
        self.kill_data: dict | None = None
        self.kill_server, self.kill_faction = "", "mine"
        self.boss_data: dict | None = None
        self.serials = {"kills": 0, "bosses": 0}
        self.started = False
        self.cards: list[EventCard] = []
        self.backs: list[tuple[QLabel, float, str]] = []
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.tick)
        self.setStyleSheet(self._stylesheet())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(12)
        self.loading = _label("Loading event schedules…")
        self.layout_.addWidget(self.loading)
        self.sections = [self._events_section(), self._reference_section(), self._kills_section(),
                         self._defeats_section()]
        for section in self.sections:
            section.hide()
            self.layout_.addWidget(section)
        self.layout_.addStretch(1)

    @staticmethod
    def _stylesheet() -> str:
        c = theme.COLORS
        return f"""
        QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 6px; }}
        QFrame#note QLabel, QFrame#note QToolButton {{ background: transparent; }}
        QFrame#newsCard {{ background: {c['panel2']}; border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 8px; }}
        QLabel#h2 {{ color: {c['gold']}; font-size: 17px; font-weight: 700; }}
        QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
        QLabel#countdown {{ font-size: 15px; font-weight: 700; }}
        QToolButton#fold {{ border: none; padding: 2px 0; color: {c['text']}; }}
        QWidget#foldBody {{ background: transparent; }}
        """

    # ------------------------------------------------------------------ the sections
    def _section(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("note")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(_label(title, "h2"))
        return frame, layout

    def _link(self, href: str) -> None:
        if href.startswith("web:"):
            if self.open_web is not None:
                self.open_web(href[4:])
        else:
            self.open_link(href)

    def _rich(self, text: str = "", name: str = "") -> QLabel:
        label = _label(text, name, rich=True)
        label.linkActivated.connect(self._link)
        return label

    def _events_section(self) -> QFrame:
        frame, layout = self._section("Regional event timers")
        self.events_note = _label()
        layout.addWidget(self.events_note)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Game region"))
        self.region_box = QComboBox()
        self.region_box.currentIndexChanged.connect(self._region_chosen)
        row.addWidget(self.region_box)
        self.group_label = QLabel("Korean matching group")
        row.addWidget(self.group_label)
        self.group_box = QComboBox()
        self.group_box.addItem("Unknown — hide group-specific forecasts", "")
        for number in ("1", "2", "3"):
            self.group_box.addItem(f"Group {number}", number)
        self.group_box.currentIndexChanged.connect(self._group_chosen)
        row.addWidget(self.group_box)
        row.addStretch(1)
        layout.addLayout(row)
        self.source = self._rich("", "muted")
        layout.addWidget(self.source)
        self.clock_line = _label("", "muted")
        layout.addWidget(self.clock_line)
        self.no_region = _label(timers.NO_REGION)
        layout.addWidget(self.no_region)
        self.event_grid = CardGrid()
        layout.addWidget(self.event_grid)
        return frame

    def _reference_section(self) -> QFrame:
        frame, layout = self._section("Field boss respawn reference")
        self.reference_loading = _label("Loading community respawn reference…", "muted")
        layout.addWidget(self.reference_loading)
        self.reference_note = _label("", "muted")
        layout.addWidget(self.reference_note)
        row = QHBoxLayout()
        self.reference_search_label = QLabel("Search bosses")
        row.addWidget(self.reference_search_label)
        self.reference_search = QLineEdit()
        self.reference_search.setPlaceholderText("Boss name or zone")
        self.reference_search.textChanged.connect(lambda _text: self._show_reference())
        row.addWidget(self.reference_search, 1)
        row.addStretch(1)
        layout.addLayout(row)
        self.reference_box = QVBoxLayout()
        self.reference_box.setSpacing(2)
        layout.addLayout(self.reference_box)
        self.reference_empty = _label("No field boss matches your search.", "muted")
        layout.addWidget(self.reference_empty)
        for widget in (self.reference_note, self.reference_search_label, self.reference_search, self.reference_empty):
            widget.hide()
        self.reference_folds: list[Fold] = []
        return frame

    def _kills_section(self) -> QFrame:
        frame, layout = self._section("Field boss kills by server")
        layout.addWidget(_label(timers.KILLS_NOTE, "muted"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Game server"))
        self.server_box = QComboBox()
        self.server_box.addItem("Load kills to choose a server", "")
        self.server_box.currentIndexChanged.connect(self._server_chosen)
        row.addWidget(self.server_box)
        row.addWidget(QLabel("Faction"))
        self.faction_box = QComboBox()
        for key, words in timers.KILL_FACTIONS:
            self.faction_box.addItem(words, key)
        self.faction_box.currentIndexChanged.connect(self._faction_chosen)
        row.addWidget(self.faction_box)
        self.kills_button = QPushButton("Load / refresh kills")
        self.kills_button.clicked.connect(self.load_kills)
        row.addWidget(self.kills_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.identity = _label("", "muted")
        layout.addWidget(self.identity)
        self.kills_status = _label("Load to retrieve recent kills from the community server.")
        layout.addWidget(self.kills_status)
        self.kills_box = QVBoxLayout()
        self.kills_box.setSpacing(2)
        layout.addLayout(self.kills_box)
        self.no_kills = _label("", "muted")
        self.no_kills.hide()
        layout.addWidget(self.no_kills)
        self.kill_folds: list[Fold] = []
        self._show_identity()
        return frame

    def _defeats_section(self) -> QFrame:
        frame, layout = self._section("Recorded boss defeats")
        layout.addWidget(_label(timers.DEFEATS_NOTE, "muted"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Recorded region"))
        self.defeats_region = QLineEdit()
        self.defeats_region.setPlaceholderText("All regions")
        self.defeats_region.setMaxLength(32)
        row.addWidget(self.defeats_region)
        row.addWidget(QLabel("Search displayed bosses"))
        self.defeats_search = QLineEdit()
        self.defeats_search.setPlaceholderText("Boss name or NPC ID")
        self.defeats_search.textChanged.connect(lambda _text: self._show_defeats())
        row.addWidget(self.defeats_search)
        self.defeats_button = QPushButton("Load / refresh observations")
        self.defeats_button.clicked.connect(self.load_defeats)
        row.addWidget(self.defeats_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.defeats_status = _label("Load to retrieve public observations from the community server.")
        layout.addWidget(self.defeats_status)
        self.defeats_box = QVBoxLayout()
        self.defeats_box.setSpacing(2)
        layout.addLayout(self.defeats_box)
        self.defeats_empty = _label("No recorded defeats match this view.")
        self.defeats_empty.hide()
        layout.addWidget(self.defeats_empty)
        self.defeats_note = _label("", "muted")
        self.defeats_note.hide()
        layout.addWidget(self.defeats_note)
        layout.addWidget(self._rich(f'<a href="web:combat" style="color: {theme.COLORS["accent"]};">Browse combat logs →</a>'))
        self.defeat_folds: list[Fold] = []
        return frame

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.started:
            self.start()
        elif self.requests is not None:
            self.requests.get("identity", "/api/meter?view=latest")      # who you are, as of this visit
        if self.catalog is not None:
            self.tick()
            self.clock.start()

    def hideEvent(self, event) -> None:
        self.clock.stop()
        super().hideEvent(event)

    def start(self) -> None:
        """The app's region, then the schedules (the first time the page is shown)."""
        self.started = True
        if self.requests is None:
            return
        self.requests.get("ui", "/api/ui")
        self.requests.get("catalog", "/static/event-schedules.json")

    def _community(self, name: str, path: str) -> None:
        self.requests.get(name, "/api/community?path=" + urllib.parse.quote(path, safe=""))

    def load_kills(self) -> None:
        if self.requests is None:
            return
        self.serials["kills"] += 1
        self.kills_button.setEnabled(False)
        self.kills_status.setText("Loading recent kills…")
        self._community(f"kills:{self.serials['kills']}", f"/api/v1/boss-kills?window={timers.KILL_WINDOW}")

    def load_defeats(self) -> None:
        if self.requests is None:
            return
        self.serials["bosses"] += 1
        region = self.defeats_region.text().strip()
        query = urllib.parse.urlencode({"region": region}) if region else ""
        self.defeats_button.setEnabled(False)
        self.defeats_status.setText("Loading recorded defeats…")
        self._community(f"bosses:{self.serials['bosses']}", "/api/v1/boss-status?" + query)

    def _replied(self, name: str, answer) -> None:
        if name == "ui":
            if isinstance(answer, dict):
                self.region = str(answer.get("event_region") or "")
                self.group = str(answer.get("event_group") or "")
        elif name == "catalog":
            if not isinstance(answer, dict) or answer.get("version") != 1:
                self.loading.setText("Could not load schedules: Unsupported schedule format")
                return
            self.catalog = answer
            self._show_catalog()
            if self.requests is not None:
                self.requests.get("field", "/static/field-bosses.json")
                self.requests.get("identity", "/api/meter?view=latest")
        elif name == "field":
            if isinstance(answer, dict) and answer.get("version") == 1 and isinstance(answer.get("bosses"), list):
                self.field_catalog = answer
                self._show_reference()
                if self.kill_data is not None:
                    self._show_kills()
        elif name == "identity":
            snapshot = answer.get("snapshot") if isinstance(answer, dict) else None
            doc = snapshot.get("field_bosses") if isinstance(snapshot, dict) else None
            if isinstance(doc, dict) and doc.get("server"):
                self.identified = doc
                if not self.kill_server:
                    self.kill_server = str(doc["server"])
                self._show_identity()
                if self.kill_data is None:
                    self.load_kills()
                else:
                    self._show_kills()
        elif name.startswith("kills:"):
            if int(name.split(":")[1]) != self.serials["kills"]:
                return
            self.kills_button.setEnabled(True)
            if isinstance(answer, dict) and answer.get("error"):
                return self._kills_failed(str(answer["error"]))
            if not isinstance(answer, dict) or not isinstance(answer.get("kills"), list):
                return self._kills_failed("The community server does not offer kills yet.")
            self.kill_data = answer
            self._show_kills()
        elif name.startswith("bosses:"):
            if int(name.split(":")[1]) != self.serials["bosses"]:
                return
            self.defeats_button.setEnabled(True)
            if not isinstance(answer, dict):
                return self._defeats_failed("the community server sent no observations")
            if answer.get("error"):
                return self._defeats_failed(str(answer["error"]))
            self.boss_data = answer
            self._show_defeats()

    def _failed(self, name: str, why: str) -> None:
        if name == "catalog":
            self.loading.setText(f"Could not load schedules: {why}")
        elif name.startswith("kills:") and int(name.split(":")[1]) == self.serials["kills"]:
            self.kills_button.setEnabled(True)
            self._kills_failed(why)
        elif name.startswith("bosses:") and int(name.split(":")[1]) == self.serials["bosses"]:
            self.defeats_button.setEnabled(True)
            self._defeats_failed(why)
        # the app's settings, the reference and the live meter are optional: the page goes on without them

    def _kills_failed(self, why: str) -> None:
        self.kill_data = None
        self._clear(self.kill_folds)
        self.backs = []
        self.no_kills.hide()
        self.kills_status.setText(f"Could not load kills: {why}")

    def _defeats_failed(self, why: str) -> None:
        self.boss_data = None
        self._clear(self.defeat_folds)
        self.defeats_empty.hide()
        self.defeats_note.hide()
        self.defeats_status.setText(f"Could not load observations: {why}")

    # ------------------------------------------------------------------ choices
    def _region_chosen(self, index: int) -> None:
        region = self.region_box.itemData(index) or ""
        if region == self.region:
            return
        self.region = region
        self._save()
        self._prepare()

    def _group_chosen(self, index: int) -> None:
        group = self.group_box.itemData(index) or ""
        if group == self.group:
            return
        self.group = group
        self._save()
        self._prepare()

    def _save(self) -> None:
        """The region and group, kept by the app for this page and the overlay's events strip."""
        if self.requests is not None:
            self.requests.post("save", "/api/ui", {"event_region": self.region, "event_group": self.group})

    def _server_chosen(self, index: int) -> None:
        server = self.server_box.itemData(index)
        if server is None or server == self.kill_server:
            return
        self.kill_server = server
        self._show_kills()

    def _faction_chosen(self, index: int) -> None:
        self.kill_faction = self.faction_box.itemData(index) or "mine"
        self._show_identity()
        self._show_kills()

    # ------------------------------------------------------------------ drawing
    def _show_catalog(self) -> None:
        catalog = self.catalog
        self.loading.hide()
        for section in self.sections:
            section.show()
        self.events_note.setText(str(catalog.get("note") or ""))
        self.region_box.blockSignals(True)
        self.region_box.clear()
        self.region_box.addItem("Choose a region", "")
        for region in catalog.get("regions") or []:
            self.region_box.addItem(str(region.get("name") or region.get("id")), region.get("id"))
        found = self.region_box.findData(self.region)
        self.region_box.setCurrentIndex(found if found >= 0 else 0)
        self.region_box.blockSignals(False)
        if found < 0:
            self.region = ""
        self.group_box.blockSignals(True)
        self.group_box.setCurrentIndex(max(0, self.group_box.findData(self.group)))
        self.group_box.blockSignals(False)
        accent = theme.COLORS["accent"]
        self.source.setText(html.escape(timers.source_line(catalog))
                            + f' <a href="{timers.SCHEDULE_SOURCE}" style="color: {accent};">Schedule source ↗</a> · '
                            f'<a href="{timers.RIFT_REPORT}" style="color: {accent};">Conflicting rift report ↗</a>')
        self._prepare()
        if self.isVisible():
            self.clock.start()

    def _prepare(self) -> None:
        """The region's events worked out afresh (a new region or group, or a new day)."""
        now = self.now()
        self.prepared_day = timers.utc_day(now)
        self.group_label.setVisible(self.region == "kr")
        self.group_box.setVisible(self.region == "kr")
        self.prepared = timers.prepare(self.catalog, self.region, self.group, now) if self.catalog else None
        self.no_region.setVisible(self.prepared is None)
        self.cards = [EventCard(item, self.group) for item in self.prepared or []]
        self.event_grid.set_cards(self.cards)
        self.event_grid.setVisible(bool(self.cards))
        self.tick()

    def tick(self) -> None:
        """The clocks moved on: the device time, each event's countdown and each kill's expected return."""
        if self.catalog is None:
            return
        now = self.now()
        if timers.utc_day(now) != self.prepared_day:
            return self._prepare()
        self.clock_line.setText(timers.clock_line(self.catalog, now))
        for card in self.cards:
            card.tick(now)
        for label, back, basis in self.backs:
            label.setText(f"{html.escape(timers.back_text(back, now))} · {html.escape(basis)}")

    def _clear(self, folds: list[Fold]) -> None:
        for fold in folds:
            fold.setParent(None)
            fold.deleteLater()
        folds.clear()

    def _show_reference(self) -> None:
        if self.field_catalog is None:
            return
        self.reference_loading.hide()
        for widget in (self.reference_note, self.reference_search_label, self.reference_search):
            widget.show()
        self.reference_note.setText(str(self.field_catalog.get("note") or ""))
        self._clear(self.reference_folds)
        groups = timers.boss_groups(self.field_catalog, self.reference_search.text())
        muted = theme.COLORS["muted"]
        for _faction, title, rows, opened in groups:
            fold = Fold(timers.group_title(title, rows), opened)
            for boss in rows:
                fold.add(self._rich(
                    f"<b>{html.escape(str(boss.get('name')))}</b> · <span style='color: {muted};'>"
                    f"{html.escape(str(boss.get('zone')))} · Lv {html.escape(str(boss.get('level')))}</span><br>"
                    f"{html.escape(timers.respawn_line(boss))}"))
            self.reference_folds.append(fold)
            self.reference_box.addWidget(fold)
        self.reference_empty.setVisible(not groups)

    def _show_identity(self) -> None:
        line = timers.identity_line(self.identified, self.kill_faction)
        self.identity.setText(line)
        self.identity.setVisible(bool(line))

    def _show_kills(self) -> None:
        if self.kill_data is None:
            return
        kills = timers.kills_of(self.kill_data)
        listed = timers.servers(kills, self.kill_server)
        self.server_box.blockSignals(True)
        self.server_box.clear()
        self.server_box.addItem("Choose a server", "")
        for server, words in listed:
            self.server_box.addItem(words, server)
        self.server_box.setCurrentIndex(max(0, self.server_box.findData(self.kill_server)))
        self.server_box.blockSignals(False)
        faction = timers.wanted_faction(self.kill_faction, self.identified)
        rows = timers.kill_rows(kills, self.kill_server, faction, self.field_catalog)
        self.kills_status.setText(timers.kills_status(self.kill_data, self.kill_server, rows, len(listed)))
        self._clear(self.kill_folds)
        self.backs = []
        muted = theme.COLORS["muted"]
        for kill in rows:
            entry = timers.boss_entry(kill, self.field_catalog)
            fold = Fold(timers.kill_summary(kill, entry))
            back = timers.kill_back(kill, entry)
            if back is None:
                fold.add(_label(timers.UNKNOWN_RESPAWN))
            else:
                label = fold.add(_label("", rich=True))
                self.backs.append((label, back, timers.kill_basis(kill, entry)))
            sources = timers.kill_sources(kill)
            if sources:
                fold.add(self._rich(f"<span style='color: {muted};'>{sources}</span>"))
            self.kill_folds.append(fold)
            self.kills_box.addWidget(fold)
        words = timers.no_kills(self.kill_server, rows, faction)
        self.no_kills.setText(words)
        self.no_kills.setVisible(bool(words))
        self.tick()

    def _show_defeats(self) -> None:
        if self.boss_data is None:
            return
        rows = timers.defeat_rows(self.boss_data, self.defeats_search.text())
        self.defeats_status.setText(timers.defeats_status(self.boss_data, rows))
        self._clear(self.defeat_folds)
        for group in rows:
            fold = Fold(timers.defeat_summary(group))
            fold.add(self._rich(timers.defeat_detail(group)))
            fold.add(_label("Availability / respawn: unknown. Physical server / channel: unknown. Different perspectives "
                            "may repeat one defeat.", "muted"))
            history = timers.defeat_history(group)
            if history is None:
                fold.add(_label("Update the community server for recent observation history."))
            else:
                fold.add(_label("Recent retained observations", "cardTitle"))
                for line in history:
                    fold.add(self._rich("• " + line))
                fold.add(_label(timers.omitted_line(group), "muted"))
            self.defeat_folds.append(fold)
            self.defeats_box.addWidget(fold)
        self.defeats_empty.setVisible(not rows)
        note = self.boss_data.get("note")
        self.defeats_note.setText(str(note or ""))
        self.defeats_note.setVisible(bool(note))

    def closeEvent(self, event) -> None:
        self.clock.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
