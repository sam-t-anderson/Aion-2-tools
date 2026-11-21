"""The native Pet Tracker page (0.2.431): Pet Tracker (0Fox2Give's program) inside Aion 2 Calc, as the web page shows
it (pages/pets.js, its pets drawn as ``A2Pets`` in static/pet-tracker.js draws them).

The app runs Pet Tracker's capture and builds its rows with Pet Tracker's own rules (``app/pettracker.py``). This page
draws what ``GET /api/pettracker`` returns and sends its controls back (``POST /api/pettracker``):

- **Pet Tracker:**
  - whether it is installed, and its install;
  - its version and folder, and a newer release;
  - whether Aion 2 Calc uses it and shows its overlay, and in which window;
  - how it is doing, and **Open Pet Tracker**.
- **Now:** the pets of the moment, Recent or Nearby, with maxed ones shown or hidden. Each pet has its portrait, rank,
  souls toward the next rank, family, Pet Tracker's notice, its bar and its pin. Or the character Pet Tracker waits
  to link to its account.
- **This session:** the souls and rank-ups of the farming session, and its reset.
- **Collection:** every pet, searched and filtered by family and rank, by name or closest to its next rank, each with
  its farming goal.

It reads Pet Tracker's state every 1.5 s while Pet Tracker is connected (every 3 s otherwise) and the collection every
10 s, only while the page is shown. A part is drawn again only when what it shows changed, and the collection's pets
are kept and updated in place. The words are worked out apart from the page and tested alone.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import json
import webbrowser

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import pictures, theme
from .api import AppApi, Requests
from .chrome import FlowLayout
from .database_page import Window
from .gathering_page import GatheringPage, table

SUBTITLE = "by 0Fox2Give · your pet ranks and the souls you still need, inside Aion 2 Calc"
ACCENTS = {"Gold": "#d9b24c", "Blue": "#60b1ec", "Teal": "#53c9b5"}     # Pet Tracker's accent choices
ACCENT_NAMES = {colour: name for name, colour in ACCENTS.items()}
#: The families' colours: Pet Tracker's crystals' (pet-tracker.css ``--pt-*``).
FAMILIES = {"Cogni": "#6fb4f0", "Fera": "#f08a7a", "Natura": "#7fd38a", "Varian": "#c39af0", "Special": "#e8cf8e"}
TONES = {"ok": "#76c59d", "off": "#e9a4b6", "wait": theme.COLORS["muted"]}
PAUSED = "#747d8a"                       # a bar while the totals wait to sync
TRACK = "#1d2539"                        # a bar's track: app.css ``--line-soft``
SETUP = {"finding": "Checking Pet Tracker's signed release…", "downloading": "Downloading Pet Tracker…",
         "installing": "Pet Tracker's installer is running…",
         "started": "Pet Tracker's installer is running; this page notices when it finishes.",
         "installed": "Pet Tracker is installed."}
RANKS = (("all", "All ranks"), ("0", "Uncollected"), ("1", "Rank 1"), ("2", "Rank 2"), ("3", "Maxed"),
         ("unknown", "Rank unknown"), ("hide", "Hide maxed"))
GOALS = (("", "No goal"), ("1", "Rank 1"), ("2", "Rank 2"), ("3", "Rank 3"))
INSTALL_NOTE = ("Downloads Pet Tracker's official installer from its GitHub release, and starts it only once it matches "
                "the release its publisher signed. Pet Tracker needs Npcap, as the Live Meter does.")
SYNC_NOTE = "Totals paused. Return to character selection, then log back in; pet rewards still appear meanwhile."
SOURCE = "https://github.com/0Fox2Give/PetTracker"
ATTRIBUTION = ("Pet Tracker is a separate program by 0Fox2Give, open source under GPL-3.0 "
               f"(<a href='{SOURCE}' style='color: {theme.COLORS['accent']};'>its source and releases</a>), used here "
               "with its author's permission. Aion 2 Calc runs its capture and shows its data. Like any third-party tool, "
               "it is unofficial, and using it can put your game account at risk.")
RUNNING_TIP = "Pet Tracker is running: its paw icon in the Windows tray opens Find a pet, its settings and more"
OPEN_TIP = "Starts Pet Tracker: its overlay, and its paw icon in the Windows tray with Find a pet, its settings and more"
MANAGE = "Open Pet Tracker's Settings → Account → Manage accounts to link it."
CONNECTED_MS, WAITING_MS, COLLECTION_MS = 1500, 3000, 10000
TOAST_MS = 4000                          # app.js ``toast``'s time
PICTURE = 48                             # a portrait's size on the page (``.ptpage .ptpic``)
GRID_MIN, GRID_GAP = 320, 6              # the collection's columns: ``repeat(auto-fill, minmax(320px, 1fr))``
#: What draws Pet Tracker's head anew: its install, its update and its switches. Its status line and its Open button
#: are drawn anew in place, so a menu of the head left open stays open as Pet Tracker's status moves on.
HEAD_KEYS = ("supported", "installed", "setup", "enabled", "update", "source")


# ------------------------------------------------------------------ the words (pet-tracker.js, pets.js)
def status_line(state) -> tuple[str, str, str]:
    """How Pet Tracker is doing in one line, how it reads ("ok", "wait" or "off"), and its detail
    (``A2Pets.status``)."""
    if not state:
        return "Loading Pet Tracker…", "wait", ""
    if not state.get("supported"):
        return "Pet Tracker runs on Windows only.", "off", ""
    if not state.get("installed"):
        return "Pet Tracker is not installed. Install it under Settings → Pet Tracker.", "off", ""
    if not state.get("enabled"):
        return "Pet Tracker is off. Turn it on under Settings → Pet Tracker.", "off", ""
    if not state.get("connected"):
        tone = "off" if state.get("start") in ("failed", "stopped") else "wait"
        return state.get("problem") or "Starting Pet Tracker's capture…", tone, ""
    link = state.get("link")
    if link:
        return f"{link.get('character')} is not linked to {link.get('account')}", "wait", state.get("detail") or ""
    who = f"{state['character']} · " if state.get("character") else ""
    return (who + (state.get("status") or "Connected"), "ok" if state.get("status") == "Live" else "wait",
            state.get("detail") or "")


def setup_text(setup) -> str:
    """What Pet Tracker's install is doing (pets.js ``petSetupText``)."""
    if not setup:
        return ""
    if setup.get("status") == "error":
        return setup.get("error") or "Pet Tracker could not be installed."
    if setup.get("status") == "downloading" and setup.get("version"):
        return f"Downloading Pet Tracker {setup['version']}…"
    return SETUP.get(setup.get("status"), "")


def installing(state) -> bool:
    return ((state or {}).get("setup") or {}).get("status") in ("finding", "downloading", "installing")


def update_notice(state) -> tuple[str, str, str] | None:
    """A newer Pet Tracker (pets.js ``petUpdateNotice``): its words, then its button's words, or for a copy in a
    folder of the player's own the address of Pet Tracker's releases. None while there is none."""
    update = (state or {}).get("update")
    if not update or not update.get("available"):
        return None
    words = f"Pet Tracker {update.get('latest')} is available (you have {update.get('installed')})."
    if update.get("kind") == "custom":
        return words, "", f"{state.get('source') or ''}/releases"
    label = f"Install Pet Tracker {update.get('latest')}" if update.get("kind") == "offline" else "Update Pet Tracker"
    return words, label, ""


def accent(state) -> str:
    """Pet Tracker's accent colour, its settings' choice (``A2Pets.accent``)."""
    return ACCENTS.get(((state or {}).get("options") or {}).get("accent") or "Gold", ACCENTS["Gold"])


def row_tip(row: dict) -> str:
    """A pet's tooltip: where it came from, the souls to its next rank, whether its totals are estimated, its goal."""
    remaining = row.get("remaining")
    parts = [row.get("creature") and f"From {row['creature']}",
             remaining is not None and f"{remaining} soul{'' if remaining == 1 else 's'} to the next rank",
             row.get("estimated") and "Estimated while totals sync", row.get("goal_text")]
    return " · ".join(str(part) for part in parts if part)


def progress_text(row: dict) -> str:
    """The souls toward the next rank, "✓ MAX" once maxed, marked "≈" while estimated."""
    if row.get("max"):
        return "✓ MAX"
    return ("≈" if row.get("estimated") else "") + str(row.get("progress") if row.get("progress") is not None else "")


def bar_ratio(row: dict) -> float:
    """How far a bar is filled: the ratio to the whole percent, as the web page writes its width."""
    try:
        ratio = float(row.get("ratio") or 0)
    except (TypeError, ValueError):
        ratio = 0.0
    return max(0.0, min(1.0, theme.js_round(ratio * 100) / 100))


def link_words(link: dict) -> str:
    """Why Pet Tracker waits for the character logged in to be linked to its account (``A2Pets`` ``linkBox``)."""
    others = f" ({', '.join(link['characters'])})" if link.get("characters") else ""
    return (f"{link.get('character')} is not one of the characters of your Pet Tracker account {link.get('account')}"
            f"{others}. Pet collections are shared across an account, so Pet Tracker waits until this character is "
            "linked to it.")


def rank_matches(row: dict, chosen: str) -> bool:
    """Whether a pet's rank is the rank filter's choice (pets.js ``rankMatch``)."""
    if chosen == "all":
        return True
    if chosen == "unknown":
        return row.get("rank") is None
    if chosen == "hide":
        return row.get("rank") != 3
    try:
        return row.get("rank") == int(chosen)
    except (TypeError, ValueError):
        return False


def collection_rows(collection, query: str = "", family: str = "", rank: str = "all", sort: str = "name") -> list[dict]:
    """The collection's pets matching the search, family and rank: by name as Pet Tracker lists them, or closest to
    their next rank first."""
    term = query.strip().lower()
    rows = [row for row in (collection or {}).get("collection") or [] if isinstance(row, dict)
            and (not term or term in str(row.get("name") or "").lower())
            and (not family or row.get("family") == family) and rank_matches(row, rank)]
    if sort == "closest":
        rows.sort(key=lambda row: (row["remaining"] if isinstance(row.get("remaining"), (int, float)) else 1e9,
                                   str(row.get("name") or "").casefold()))
    return rows


def summary_parts(summary) -> list[tuple[str, str]]:
    """The collection's counts (``.ptsummary``): its pets, the collected, the maxed and the ranks unknown."""
    if not summary:
        return []
    names = (("Pets", "total"), ("Collected", "collected"), ("Maxed", "maxed"), ("Rank unknown", "unknown"))
    return [(words, str(summary.get(key))) for words, key in names]


def session_line(session: dict) -> str:
    """The farming session's souls and rank-ups, as rich text."""
    souls, ranked = session.get("souls") or 0, session.get("ranked") or 0
    line = (f"<b>{html.escape(str(souls))}</b> soul{'' if souls == 1 else 's'} · <b>{html.escape(str(ranked))}</b> "
            f"pet{'' if ranked == 1 else 's'} ranked up")
    if session.get("incomplete"):
        line += (f" <span style='color: {theme.COLORS['muted']};'>· some rewards may be missing: capture was "
                 "interrupted</span>")
    return line


def _key(*data) -> str:
    return json.dumps(data, sort_keys=True, default=str)


# ------------------------------------------------------------------ the parts
def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _restyle(widget: QWidget, name: str) -> None:
    """A widget under another name of the style sheet's, drawn again in its rules."""
    if widget.objectName() != name:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _clear(layout) -> None:
    """A part's widgets taken away at once (a widget left for Qt to delete would still be shown until then)."""
    while layout.count():
        child = layout.takeAt(0)
        widget, inner = child.widget(), child.layout()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif inner is not None:
            _clear(inner)


def _flow(gap=(14, 10)) -> tuple[QWidget, FlowLayout]:
    """A line of widgets that goes on to the next where there is no room (``.row``, ``flex-wrap: wrap``)."""
    box = QWidget()
    box.setObjectName("plain")
    flow = FlowLayout(box, align=Qt.AlignLeft, gap=gap)
    return box, flow


class Elided(QLabel):
    """One line of text cut short with an ellipsis where its room ends (``text-overflow: ellipsis``); it can be
    narrower than its text (``min-width: 0``)."""

    def __init__(self, text: str = "", name: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        if name:
            self.setObjectName(name)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def shown_text(self) -> str:
        return self.fontMetrics().elidedText(self.text(), Qt.ElideRight, max(0, self.contentsRect().width()))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(self.contentsRect(), int(Qt.AlignLeft | Qt.AlignVCenter), self.shown_text())
        painter.end()


class Portraits(QObject):
    """The pets' portraits from the app (``/api/pettracker/portrait/<id>.png``), read off the interface's thread two at
    a time, each once. ``loaded`` gives a portrait, ``missing`` one the app has not."""

    loaded = Signal(str, bytes)
    missing = Signal(str)

    def __init__(self, api: AppApi | None, parent: QObject | None = None):
        super().__init__(parent)
        self.api = api
        self.pixmaps: dict[str, QPixmap] = {}
        self.failed: set[str] = set()
        self._asked: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gui-portraits")

    def ask(self, path: str) -> None:
        if self.api is None or not path.startswith("/api/pettracker/portrait/") or path in self._asked:
            return
        self._asked.add(path)
        try:
            self._pool.submit(self._get, path)
        except RuntimeError:                     # stopped: the page has closed
            pass

    def _get(self, path: str) -> None:
        try:
            data = self.api.get_bytes(path)
        except Exception:                        # noqa: BLE001 - a portrait that cannot be read is left out
            data = b""
        if data:
            self.loaded.emit(path, data)
        else:
            self.missing.emit(path)

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class Portrait(QWidget):
    """A pet's portrait (``.ptpic``): its picture covering a rounded square, the square alone until it is read, and
    nothing where the app has none (``.ptpic.none``)."""

    def __init__(self, size: int = PICTURE, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.pixmap: QPixmap | None = None
        self.none = False

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self.pixmap, self.none = pixmap, False
        self.update()

    def set_missing(self) -> None:
        self.pixmap, self.none = None, True
        self.update()

    def paintEvent(self, _event) -> None:
        if self.none:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, self.width(), self.height(), 7, 7)
        painter.fillPath(clip, QColor(27, 40, 56, 230))
        if self.pixmap is not None and not self.pixmap.isNull():
            painter.setClipPath(clip)
            scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        painter.end()


class Bar(QWidget):
    """A pet's souls toward its next rank (``.ptbar``): 4 px, in the accent colour, grey while its totals wait."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.ratio, self.colour = 0.0, ACCENTS["Gold"]
        self.setFixedHeight(4)

    def set(self, ratio: float, colour: str) -> None:
        if (ratio, colour) != (self.ratio, self.colour):
            self.ratio, self.colour = ratio, colour
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(TRACK))
        painter.drawRoundedRect(self.rect(), 2, 2)
        if self.ratio > 0:
            painter.setBrush(QColor(self.colour))
            painter.drawRoundedRect(0, 0, round(self.width() * self.ratio), self.height(), 2, 2)
        painter.end()


def _dim(colour: str | None) -> str:
    """A family's colour at nine tenths (``.ptfam``'s ``opacity: .9``)."""
    tint = QColor(colour or theme.COLORS["muted"])
    return f"rgba({tint.red()}, {tint.green()}, {tint.blue()}, 0.9)"


class PetRow(QFrame):
    """One pet (``.ptrow``): its portrait, its name and rank, then the souls toward its next rank, its family and Pet
    Tracker's notice, its bar, and its pin. ``set_row`` draws a pet's row anew in place."""

    def __init__(self, pin, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ptrow")
        self.row: dict = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(8)
        self.picture = Portrait()
        layout.addWidget(self.picture, 0, Qt.AlignVCenter)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        line = QHBoxLayout()
        line.setSpacing(6)
        self.name = Elided(name="ptname")
        line.addWidget(self.name)
        line.addStretch(1)
        self.rank = _label("", "ptrank", wrap=False)
        line.addWidget(self.rank)
        body.addLayout(line)
        sub = QHBoxLayout()
        sub.setSpacing(6)
        self.progress = _label("", "ptprog", wrap=False)
        sub.addWidget(self.progress)
        self.family = _label("", "ptfam", wrap=False)
        sub.addWidget(self.family)
        sub.addStretch(1)
        self.notice = Elided(name="ptnotice")
        sub.addWidget(self.notice)
        body.addLayout(sub)
        self.bar = Bar()
        body.addWidget(self.bar)
        layout.addLayout(body, 1)
        self.pin = QPushButton()
        self.pin.setObjectName("ptpin")
        self.pin.setCursor(Qt.PointingHandCursor)
        self.pin.clicked.connect(lambda: pin(self.row.get("id"), not self.row.get("pinned")))
        layout.addWidget(self.pin, 0, Qt.AlignVCenter)

    def set_row(self, row: dict, colour: str, portraits: bool = True, bars: bool = True) -> None:
        self.row = row
        maxed = bool(row.get("max"))
        self.setToolTip(row_tip(row))
        self.picture.setVisible(portraits)
        self.name.setText(str(row.get("name") or ""))
        _restyle(self.name, "ptnameMax" if maxed else "ptname")
        self.rank.setText(str(row.get("rank_text") or ""))
        self.progress.setText(progress_text(row))
        _restyle(self.progress, "ptprogMax" if maxed else "ptprog")
        family = str(row.get("family") or "")
        self.family.setText(family)
        self.family.setVisible(bool(family))
        _restyle(self.family, "fam" + (family if family in FAMILIES else "Other"))   # in its colour (the page's rules)
        self.notice.setText(str(row.get("notice") or ""))
        self.notice.setVisible(bool(row.get("notice")))
        self.bar.setVisible(not maxed and bars)
        self.bar.set(bar_ratio(row), PAUSED if row.get("paused") else colour)
        pinned = bool(row.get("pinned"))
        self.pin.setText("★" if pinned else "☆")
        self.pin.setToolTip("Unpin this pet" if pinned else "Pin this pet to the top")
        self.pin.setAccessibleName(f"{'Unpin' if pinned else 'Pin'} {row.get('name') or 'this pet'}")
        _restyle(self.pin, "ptpin" + (ACCENT_NAMES.get(colour, "Gold") if pinned else ""))    # a pin in the accent colour

    def set_picture(self, pixmap: QPixmap | None, missing: bool = False) -> None:
        if missing:
            self.picture.set_missing()
        else:
            self.picture.set_pixmap(pixmap)


class CollectionItem(QWidget):
    """A pet of the collection (``.ptitem``): its row, then its farming goal (``.ptgoal``) with its words."""

    def __init__(self, pin, goal, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.pet = PetRow(pin)
        layout.addWidget(self.pet)
        line = QHBoxLayout()
        line.setContentsMargins(6, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(_label("Farming goal", "muted", wrap=False))
        self.choice = QComboBox()
        self.choice.setAccessibleName("Farming goal")
        for value, words in GOALS:
            self.choice.addItem(words, value)
        self.choice.activated.connect(lambda index: goal(self.pet.row.get("id"), self.choice.itemData(index)))
        line.addWidget(self.choice)
        self.goal = _label("", "muted")
        line.addWidget(self.goal, 1)
        layout.addLayout(line)

    def set_row(self, row: dict, colour: str) -> None:
        self.pet.set_row(row, colour)                  # the collection's pets always show their portrait and bar
        chosen = "" if row.get("goal_rank") is None else str(row["goal_rank"])
        self.choice.setCurrentIndex(max(0, self.choice.findData(chosen)))
        self.goal.setText(str(row.get("goal_text") or ""))


class PetGrid(QWidget):
    """The collection's pets in as many columns of at least 320 px as fit, 6 px apart; a column left empty keeps its
    room (``repeat(auto-fill, minmax(320px, 1fr))``)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GRID_GAP)
        self.items: list[QWidget] = []
        self.columns = 0

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width())

    def set_items(self, items: list[QWidget]) -> None:
        for item in self.items:
            self.grid.removeWidget(item)
        self.items = list(items)
        self.columns = 0
        self.place(self.width())

    def place(self, width: int) -> None:
        columns = max(1, (width + GRID_GAP) // (GRID_MIN + GRID_GAP))
        if columns == self.columns:
            return
        self.columns = columns
        for item in self.items:
            self.grid.removeWidget(item)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for index, item in enumerate(self.items):
            self.grid.addWidget(item, index // columns, index % columns)
            item.show()
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class Seg(QFrame):
    """Buttons side by side in one frame, the chosen one in gold (``.seg``, ``button.on``). The choice moves only when
    ``set`` says so (Pet Tracker's answer), as on the web page, not as a button is pressed."""

    def __init__(self, choices: tuple[str, ...], choose, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("segBox")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.chosen: str | None = None
        self.buttons: dict[str, QPushButton] = {}
        for index, choice in enumerate(choices):
            button = QPushButton(choice)
            button.setObjectName(self._name(index, len(choices), False))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, choice=choice: choose(choice))
            layout.addWidget(button)
            self.buttons[choice] = button

    @staticmethod
    def _name(index: int, count: int, on: bool) -> str:
        return ("segFirst" if index == 0 else "segLast" if index == count - 1 else "segButton") + ("On" if on else "")

    def set(self, chosen: str | None, enabled: bool) -> None:
        self.chosen = chosen
        for index, (choice, button) in enumerate(self.buttons.items()):
            _restyle(button, self._name(index, len(self.buttons), choice == chosen))
            button.setAccessibleDescription("chosen" if choice == chosen else "")
            button.setEnabled(enabled)


class Capped(QWidget):
    """A part as wide as its row up to ``width`` and no wider (``max-width``), set at the left of its row."""

    def __init__(self, width: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.setMaximumWidth(width)

    def sizeHint(self) -> QSize:
        return QSize(self.maximumWidth(), super().sizeHint().height())


class SetRow(QFrame):
    """A row of the page (``.setrow``): its name on the left in 200 px, its parts beside it, a line under it but the
    last."""

    def __init__(self, title: str, last: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("setrowLast" if last else "setrow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(14)
        name = _label(title, "lbl")
        name.setFixedWidth(200)
        layout.addWidget(name, 0, Qt.AlignTop | Qt.AlignLeft)
        self.cell = QVBoxLayout()
        self.cell.setContentsMargins(0, 0, 0, 0)
        self.cell.setSpacing(6)
        layout.addLayout(self.cell, 1)


class Toast(QLabel):
    """The app's short message at the foot of the page for four seconds (app.js ``toast``). A page that shows one
    adds ``STYLE`` to its stylesheet."""

    STYLE = (f"QLabel#toast {{ background: #1c2438; border: 1px solid rgba(233, 203, 128, 0.6); border-radius: 6px; "
             f"padding: 8px 16px; color: {theme.COLORS['gold']}; }}")

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setTextFormat(Qt.PlainText)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def say(self, words: str) -> None:
        self.setText(words)
        self.adjustSize()
        self.place()
        self.raise_()
        self.show()
        self.timer.start(TOAST_MS)

    def place(self) -> None:
        page = self.parentWidget()
        self.move(max(0, (page.width() - self.width()) // 2), max(0, page.height() - self.height() - 20))


# ------------------------------------------------------------------ the page
class PetsPage(QWidget):
    """Game → Pet Tracker. It reads Pet Tracker's state and collection while it is shown."""

    def __init__(self, api: AppApi | None, open_link=webbrowser.open, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_link = api, open_link
        self.state: dict | None = None
        self.collection: dict | None = None
        self.ui: dict = {}
        self.keys: dict[str, str] = {}
        self.live_rows: list[PetRow] = []
        self.items: dict = {}                            # the collection's pets by id, kept between draws
        self.status: QLabel | None = None                # Pet Tracker's status line, while it is installed
        self.opener: QPushButton | None = None           # and its Open button
        self._tone = ""
        self._ui_saves: list[dict] = []
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.portraits = Portraits(api, self)
        self.portraits.loaded.connect(self._portrait)
        self.portraits.missing.connect(self._no_portrait)
        self.poll = QTimer(self)
        self.poll.setSingleShot(True)
        self.poll.timeout.connect(self.read_state)
        self.poll_collection = QTimer(self)
        self.poll_collection.setSingleShot(True)
        self.poll_collection.timeout.connect(self.read_collection)
        self.quiet = QTimer(self)
        self.quiet.setSingleShot(True)
        self.quiet.timeout.connect(lambda: self.message.setText(""))
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
        self.window_ = Window("Pet Tracker", SUBTITLE)
        layout.addWidget(self.window_)
        layout.addStretch(1)
        body = self.window_.body
        body.setSpacing(0)

        row = SetRow("Pet Tracker")
        head = QWidget()
        head.setObjectName("plain")
        self.head = QVBoxLayout(head)
        self.head.setContentsMargins(0, 0, 0, 0)
        self.head.setSpacing(8)
        self.head.addWidget(_label("Loading Pet Tracker…"))
        row.cell.addWidget(head)
        self.note = _label("")                           # what the update notice's button did (``#pt-note``)
        self.note.hide()
        row.cell.addWidget(self.note)
        body.addWidget(row)

        row = SetRow("Now")
        tools, flow = _flow()
        self.modes = Seg(("Recent", "Nearby"), lambda mode: self.control({"action": "mode", "value": mode}))
        flow.addWidget(self.modes)
        self.hide_maxed = QCheckBox("Hide maxed")
        self.hide_maxed.clicked.connect(lambda checked: self.control({"action": "hide_maxed", "value": bool(checked)}))
        flow.addWidget(self.hide_maxed)
        self.message = _label("", "muted", wrap=False)
        flow.addWidget(self.message)
        row.cell.addWidget(tools)
        self.sync = _label(SYNC_NOTE, "note")
        self.sync.hide()
        row.cell.addWidget(self.sync)
        live = Capped(640)                               # ``.ptpage .ptrows { max-width: 640px }``
        self.live = QVBoxLayout(live)
        self.live.setContentsMargins(0, 0, 0, 0)
        self.live.setSpacing(4)
        row.cell.addWidget(live, 0, Qt.AlignLeft)
        body.addWidget(row)

        row = SetRow("This session")
        session = QWidget()
        session.setObjectName("plain")
        self.session = QVBoxLayout(session)
        self.session.setContentsMargins(0, 0, 0, 0)
        self.session.setSpacing(8)
        row.cell.addWidget(session)
        body.addWidget(row)

        row = SetRow("Collection", last=True)
        summary, self.summary = _flow((14, 4))
        row.cell.addWidget(summary)
        filters, flow = _flow((8, 8))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search pets")
        self.search.setAccessibleName("Search pets")
        self.search.setMinimumWidth(220)
        self.family = QComboBox()
        self.family.setAccessibleName("Family")
        self.family.addItem("All families", "")
        for name in FAMILIES:
            self.family.addItem(name, name)
        self.rank = QComboBox()
        self.rank.setAccessibleName("Rank")
        for value, words in RANKS:
            self.rank.addItem(words, value)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sort")
        self.sort.addItem("By name", "name")
        self.sort.addItem("Closest to next rank", "closest")
        for widget in (self.search, self.family, self.rank, self.sort):
            flow.addWidget(widget)
        self.search.textChanged.connect(lambda _text: self.draw())
        for box in (self.family, self.rank, self.sort):
            box.currentIndexChanged.connect(lambda _index: self.draw())
        row.cell.addWidget(filters)
        self.grid = PetGrid()
        row.cell.addWidget(self.grid)
        self.empty = _label("", "muted")                  # the collection's line while it shows no pet
        self.empty.hide()
        row.cell.addWidget(self.empty)
        body.addWidget(row)

        attribution = _label(ATTRIBUTION, "muted", rich=True)
        attribution.setContentsMargins(0, 10, 0, 0)
        attribution.linkActivated.connect(self.open_link)
        body.addWidget(attribution)
        self.toast = Toast(self)

    @staticmethod
    def _stylesheet() -> str:
        c = theme.COLORS
        return GatheringPage._stylesheet() + f"""
        QWidget#plain {{ background: transparent; }}
        QFrame#setrow {{ background: transparent; border: none; border-bottom: 1px solid {TRACK}; }}
        QFrame#setrowLast {{ background: transparent; border: none; }}
        QLabel#lbl {{ color: {c['muted']}; font-weight: 600; }}
        QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
                       color: #f1d4a3; padding: 9px 12px; }}
        QFrame#note QLabel {{ background: transparent; border: none; padding: 0; color: #f1d4a3; }}
        QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                              border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; }}
        QPushButton#primary:disabled {{ color: rgba(255, 243, 207, 0.5); border-color: rgba(233, 203, 128, 0.3); }}
        QFrame#segBox {{ background: rgba(6, 9, 15, 0.65); border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 5px; }}
        QPushButton#segFirst, QPushButton#segLast, QPushButton#segButton, QPushButton#segFirstOn, QPushButton#segLastOn,
        QPushButton#segButtonOn {{ border: none; border-radius: 0; background: transparent; color: {c['muted']};
            padding: 6px 14px; font-weight: 600; }}
        QPushButton#segFirst, QPushButton#segFirstOn {{ border-top-left-radius: 4px; border-bottom-left-radius: 4px; }}
        QPushButton#segLast, QPushButton#segLastOn {{ border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
        QPushButton#segFirstOn, QPushButton#segLastOn, QPushButton#segButtonOn {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ecd79f, stop:1 #b9984f); color: #10131a; }}
        QFrame#ptrow {{ background: {c['panel2']}; border: 1px solid {c['line']}; border-radius: 8px; }}
        QFrame#ptrow QLabel {{ background: transparent; }}
        QLabel#ptname {{ color: {c['text']}; font-weight: 700; }}
        QLabel#ptnameMax {{ color: {c['faint']}; font-weight: 700; }}
        QLabel#ptrank {{ color: {c['muted']}; }}
        QLabel#ptprog {{ color: {c['text']}; }}
        QLabel#ptprogMax {{ color: {c['faint']}; }}
        {", ".join(f"QLabel#fam{name}" for name in (*FAMILIES, "Other"))} {{ font-weight: 700; border-radius: 4px;
            padding: 0 4px; }}
        {"".join(f"QLabel#fam{name} {{ color: {_dim(tint)}; border: 1px solid {_dim(tint)}; }}" for name, tint in
                 (*FAMILIES.items(), ("Other", c['muted'])))}
        QLabel#ptnotice {{ color: {c['gold']}; }}
        QLabel#ptempty {{ color: {c['muted']}; padding: 6px 2px; }}
        {", ".join(f"QPushButton#ptpin{name}" for name in ("", *ACCENTS))} {{ background: transparent; border: none;
            color: {c['muted']}; padding: 2px 3px; }}
        {"".join(f"QPushButton#ptpin{name} {{ color: {tint}; }}" for name, tint in ACCENTS.items())}
        {", ".join(f"QPushButton#ptpin{name}:hover" for name in ("", *ACCENTS))} {{ color: {c['text']}; }}
        QPushButton#ptlink {{ background: transparent; border-radius: 6px; padding: 3px 9px; }}
        {Toast.STYLE}
        """

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.requests is not None:
            self.requests.get("ui", "/api/ui")
        self.read_state()
        self.read_collection()

    def hideEvent(self, event) -> None:
        self.poll.stop()
        self.poll_collection.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.place()

    def read_state(self) -> None:
        self.poll.stop()
        if self.requests is not None:
            self.requests.get("state", "/api/pettracker")

    def read_collection(self) -> None:
        self.poll_collection.stop()
        if self.requests is not None:
            self.requests.get("collection", "/api/pettracker?collection=1")

    def control(self, body: dict) -> None:
        """A control sent to Pet Tracker (pets.js ``act``); it answers with Pet Tracker's state."""
        if self.requests is not None:
            self.requests.post("control:" + str(body.get("action")), "/api/pettracker", body)

    def set_ui(self, changes: dict) -> None:
        """One of the app's Pet Tracker settings, saved as the web page saves it (pets.js ``setUi``)."""
        if self.requests is not None:
            self._ui_saves.append(changes)
            self.requests.post("ui-save", "/api/ui", changes)

    def say(self, words: str) -> None:
        """A word beside the tools, for four seconds (pets.js ``say``)."""
        self.message.setText(words)
        self.quiet.start(4000)

    def _replied(self, name: str, answer) -> None:
        if name == "ui":
            self.ui = answer if isinstance(answer, dict) else {}
            self.draw()
        elif name == "state":
            if isinstance(answer, dict):
                self.state = answer
                self.draw()
            self._poll_again()
        elif name == "collection":
            if isinstance(answer, dict):
                self.collection = answer
                self.draw()
            if self.isVisible():
                self.poll_collection.start(COLLECTION_MS)
        elif name.startswith("control:"):
            if not isinstance(answer, dict) or answer.get("error"):
                why = answer.get("error") if isinstance(answer, dict) else None
                return self._failed(name, str(why or "Pet Tracker did not answer"))
            self.state = answer
            self.draw()
            if name == "control:update":
                self._note(str(answer.get("message") or ""))
            else:
                self.read_collection()
        elif name == "ui-save":
            if self._ui_saves:
                self.ui.update(self._ui_saves.pop(0))
            self.draw()
            self.toast.say("Saved")
            QTimer.singleShot(600, self.read_state)

    def _failed(self, name: str, why: str) -> None:
        if name == "state":
            self._poll_again()                             # the next poll tries again
        elif name == "collection":
            if self.isVisible():
                self.poll_collection.start(COLLECTION_MS)
        elif name == "control:update":
            self._note(why)
        elif name.startswith("control:"):
            self.say(why)
        elif name == "ui-save":
            if self._ui_saves:
                self._ui_saves.pop(0)
            self.say(why)

    def _poll_again(self) -> None:
        if self.isVisible():
            self.poll.start(CONNECTED_MS if (self.state or {}).get("connected") else WAITING_MS)

    def _note(self, words: str) -> None:
        self.note.setText(words)
        self.note.setVisible(bool(words))

    # ------------------------------------------------------------------ drawing
    def _changed(self, part: str, *data) -> bool:
        """Whether a part's data changed since it was drawn (the web page redraws a part only then)."""
        key = _key(*data)
        if self.keys.get(part) == key:
            return False
        self.keys[part] = key
        return True

    def filters(self) -> tuple[str, str, str, str]:
        return (self.search.text(), self.family.currentData() or "", self.rank.currentData() or "all",
                self.sort.currentData() or "name")

    def draw(self) -> None:
        """The page from Pet Tracker's state; nothing until it is first read (pets.js ``draw``)."""
        state = self.state
        if state is None:
            return
        options = state.get("options") or {}
        colour = accent(state)
        if self._changed("head", {key: state.get(key) for key in HEAD_KEYS}, self.ui.get("pettracker_overlay"),
                         self.ui.get("pettracker_overlay_style")):
            self._draw_head()
        self._draw_status()
        connected = bool(state.get("connected"))
        self.modes.set(options.get("mode") or "Recent", connected)
        self.hide_maxed.setChecked(bool(options.get("hide_maxed")))
        self.hide_maxed.setEnabled(connected)
        self.sync.setVisible(bool(state.get("sync_notice")))
        if self._changed("live", status_line(state)[0] if not connected else "", connected, state.get("link"),
                         state.get("rows"), state.get("empty"), options.get("portraits"), options.get("progress_bars"),
                         colour):
            self._draw_live()
        if self._changed("session", connected, state.get("session")):
            self._draw_session()
        summary = (self.collection or state).get("summary")
        if self._changed("summary", connected, summary):
            _clear(self.summary)
            for words, value in summary_parts(summary) if connected else []:
                self.summary.addWidget(_label(f"{html.escape(words)} <b style='color: {theme.COLORS['text']};'>"
                                              f"{html.escape(value)}</b>", "muted", rich=True, wrap=False))
        if self._changed("collection", self.collection, self.filters(), colour):
            self._draw_collection()

    def _draw_head(self) -> None:
        self.status = self.opener = None
        self._tone = ""
        _clear(self.head)
        state = self.state or {}
        if not state.get("supported"):
            self.head.addWidget(_label("Pet Tracker runs on Windows only.", "note"))
            return
        if not state.get("installed"):
            self.head.addWidget(_label("Pet Tracker is not installed on this computer."))
            line, flow = _flow()
            install = QPushButton("Install Pet Tracker")
            install.setObjectName("primary")
            install.setEnabled(not installing(state))
            install.clicked.connect(lambda: self.control({"action": "install"}))
            flow.addWidget(install)
            flow.addWidget(_label(setup_text(state.get("setup")), "muted"))
            self.head.addWidget(line)
            self.head.addWidget(_label(INSTALL_NOTE, "muted"))
            return
        installed = state["installed"]
        line, flow = _flow()
        version = f" {installed['version']}" if installed.get("version") else ""
        flow.addWidget(_label(f"<b>Pet Tracker{html.escape(str(version))}</b>", rich=True, wrap=False))
        flow.addWidget(_label(str(installed.get("folder") or ""), "muted", wrap=False))
        self.head.addWidget(line)
        notice = update_notice(state)
        if notice is not None:
            words, button_words, link = notice
            box = QFrame()
            box.setObjectName("note")
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)                 # the note's own padding (``.note``)
            row.setSpacing(6)
            row.addWidget(_label(words, wrap=False))
            if button_words:
                update = QPushButton(button_words)
                update.clicked.connect(lambda: self.control({"action": "update"}))
                row.addWidget(update)
            else:
                releases = _label(f"<a href='{html.escape(link, quote=True)}' style='color: {theme.COLORS['accent']};'>"
                                  "Download it from Pet Tracker's releases</a>", rich=True, wrap=False)
                releases.linkActivated.connect(self.open_link)
                row.addWidget(releases)
            row.addStretch(1)
            self.head.addWidget(box)
        enabled = bool(state.get("enabled"))
        line, flow = _flow()
        use = QCheckBox("Use Pet Tracker with Aion 2 Calc")
        use.setChecked(enabled)
        use.clicked.connect(lambda checked: self.set_ui({"pettracker_enabled": bool(checked)}))
        flow.addWidget(use)
        overlay = QCheckBox("Show the Pet Tracker overlay")
        overlay.setChecked(self.ui.get("pettracker_overlay") is True)
        overlay.setEnabled(enabled)
        overlay.clicked.connect(lambda checked: self.set_ui({"pettracker_overlay": bool(checked)}))
        flow.addWidget(overlay)
        style = QComboBox()
        style.setAccessibleName("Which window")
        style.addItem("in Aion 2 Calc's own window", "app")
        style.addItem("as Pet Tracker's own window", "pettracker")
        style.setCurrentIndex(1 if self.ui.get("pettracker_overlay_style") == "pettracker" else 0)
        style.setEnabled(enabled)
        style.activated.connect(lambda index: self.set_ui({"pettracker_overlay_style": style.itemData(index)}))
        flow.addWidget(style)
        self.head.addWidget(line)
        line, flow = _flow()
        self.status = _label("", "ptstatus")
        flow.addWidget(self.status)
        self.opener = QPushButton()
        self.opener.clicked.connect(lambda: self.control({"action": "open"}))
        flow.addWidget(self.opener)
        self.head.addWidget(line)

    def _draw_status(self) -> None:
        """Pet Tracker's status line in its tone, with its detail as its tooltip, and its Open button (or that it
        runs), drawn anew in place."""
        if self.status is None or self.opener is None:
            return
        state = self.state or {}
        text, tone, title = status_line(state)
        self.status.setText(text)
        self.status.setToolTip(title)
        if tone != self._tone:
            self._tone = tone
            self.status.setStyleSheet(f"color: {TONES[tone]};")
        running = bool((state.get("running") or {}).get("app"))
        self.opener.setText("Pet Tracker is running (tray icon)" if running else "Open Pet Tracker")
        self.opener.setEnabled(not running)
        self.opener.setToolTip(RUNNING_TIP if running else OPEN_TIP)

    def _picture(self, row: dict, widget: PetRow) -> None:
        """A pet's portrait on its row: read already, missing, or asked for."""
        path = str(row.get("portrait") or "")
        if path in self.portraits.pixmaps:
            widget.set_picture(self.portraits.pixmaps[path])
        elif path in self.portraits.failed or not path:
            widget.set_picture(None, missing=True)
        else:
            widget.set_picture(None)
            self.portraits.ask(path)

    def _pin(self, pet, value: bool) -> None:
        self.control({"action": "pin", "pet": pet, "value": bool(value)})

    def _goal(self, pet, value) -> None:
        self.control({"action": "goal", "pet": pet, "rank": int(value) if value else None})

    def _draw_live(self) -> None:
        """The pets of the moment (``A2Pets.rows``), or why there are none."""
        _clear(self.live)
        self.live_rows = []
        state = self.state or {}
        if not state.get("connected"):
            self.live.addWidget(_label(status_line(state)[0], "ptempty"))
            return
        link = state.get("link")
        if link:
            self.live.addWidget(_label(link_words(link), "ptempty"))
            if link.get("key"):
                button = QPushButton(f"Link {link.get('character')} to {link.get('account')}")
                button.setObjectName("ptlink")
                button.setStyleSheet(f"QPushButton#ptlink {{ border: 1px solid {accent(state)}; color: {accent(state)}; }}")

                def link_it(_checked=False, button=button, character=link.get("character")):
                    button.setEnabled(False)
                    self.control({"action": "link", "character": character})
                button.clicked.connect(link_it)
                self.live.addWidget(button, 0, Qt.AlignLeft)
            else:
                self.live.addWidget(_label(MANAGE))
            return
        rows = [row for row in state.get("rows") or [] if isinstance(row, dict)]
        if not rows:
            if state.get("empty"):
                self.live.addWidget(_label(str(state["empty"]), "ptempty"))
            return
        options = state.get("options") or {}
        for row in rows:
            widget = PetRow(self._pin)
            widget.set_row(row, accent(state), options.get("portraits") is not False,
                           options.get("progress_bars") is not False)
            self._picture(row, widget)
            self.live.addWidget(widget)
            self.live_rows.append(widget)

    def _draw_session(self) -> None:
        """The farming session (pets.js ``session``)."""
        _clear(self.session)
        state = self.state or {}
        session = state.get("session")
        if not state.get("connected") or not session:
            self.session.addWidget(_label("Pet Tracker's farming session shows here once it is connected.", "muted"))
            return
        pets = [pet for pet in session.get("pets") or [] if isinstance(pet, dict)]
        if not pets:
            self.session.addWidget(_label("No soul rewards yet this session.", "muted"))
        else:
            self.session.addWidget(_label(session_line(session), rich=True))
            self.session.addWidget(table(["Pet", "Souls", "Rank ups"],
                                         [[pet.get("name") or "", _count(pet.get("souls")), _count(pet.get("rank_ups"))]
                                          for pet in pets]))
        reset = QPushButton("Reset session")
        reset.clicked.connect(lambda: self.control({"action": "reset_session"}))
        self.session.addWidget(reset, 0, Qt.AlignLeft)

    def _draw_collection(self) -> None:
        """The collection's pets that match the filters (pets.js ``collection``): each pet's widget is kept, and drawn
        anew in place."""
        collection = self.collection
        if not collection or not collection.get("connected"):
            return self._collection_line("Your collection shows here once Pet Tracker is connected.")
        rows = collection_rows(collection, *self.filters())
        if not rows:
            return self._collection_line("No pet matches.")
        colour = accent(self.state)
        self.grid.hide()                     # its pets placed, shown and hidden at once: the page laid out once, not each
        shown = []
        for row in rows:
            item = self.items.get(row.get("id"))
            if item is None:
                item = self.items[row.get("id")] = CollectionItem(self._pin, self._goal)
            item.set_row(row, colour)
            self._picture(row, item.pet)
            shown.append(item)
        here = {id(item) for item in shown}
        for item in self.items.values():
            if id(item) not in here:
                item.hide()
        self.grid.set_items(shown)
        self.empty.hide()
        self.grid.show()

    def _collection_line(self, words: str) -> None:
        self.grid.set_items([])
        for item in self.items.values():
            item.hide()
        self.grid.hide()
        self.empty.setText(words)
        self.empty.show()

    def _portrait(self, path: str, data: bytes) -> None:
        image = pictures.decoded(data)
        if image.isNull():
            return self._no_portrait(path)
        pixmap = QPixmap.fromImage(image)
        self.portraits.pixmaps[path] = pixmap
        for widget in self._pets():
            if str(widget.row.get("portrait") or "") == path:
                widget.set_picture(pixmap)

    def _no_portrait(self, path: str) -> None:
        self.portraits.failed.add(path)
        for widget in self._pets():
            if str(widget.row.get("portrait") or "") == path:
                widget.set_picture(None, missing=True)

    def _pets(self) -> list[PetRow]:
        return [*self.live_rows, *(item.pet for item in self.items.values())]

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.poll_collection.stop()
        self.portraits.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)


def _count(value) -> str:
    return "" if value is None else str(value)
