"""The native Builds page (0.2.486): Character → Builds as the web page draws it (pages/builds.js, build-workspace.js's
``A2BuildWorkspace.mount``). Its rules are ``builds.py``'s.

- **The draft:** the class, **New empty draft**, **Import profile / optimizer / draft JSON**, **Load current community
  preset** (``/api/v2/presets/<class>/<mode>`` through the app's community proxy); its name, mode and character level;
  **Save local draft** and **Export build JSON**; what was done, said under them.
- **Saved local drafts:** each kept draft to load or remove (``a2-build-drafts-v1``, the app's interface data since
  0.2.482, which the web page shares).
- **Active skills, Passives and Stigmas:** the class's skills with their trained or equipped levels, manual bonus
  levels and supporting effects, searched by name; **Daevanion:** each board's nodes to take from its centre, and the
  separate budget of a board that is not a crystal board. Each with its budget, what it uses, the class's highest
  server-reported budgets (``/api/v1/progression``) and the catalog's checks; then the draft's notes.
- Equipment, Arcana cards, Pantheon, Genus Insight, Evaluation / advanced inputs and Source character are still
  drawn on the web Builds page: a saved draft opens there.

The page starts afresh each time it is opened, as the web page does (its unsaved edits are not kept on leaving);
the catalog is read once.
"""
from __future__ import annotations

import html
import math
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QRectF, QRegularExpression, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import builds as b
from . import image_health, theme
from .api import AppApi, Requests
from .character import field_value, js_number, js_string
from .chrome import FlowLayout
from .combat_page import stylesheet as combat_stylesheet
from .combat_review_page import LOGO, AutoGrid
from .combat_saved import _clear
from .database_page import Window
from .news import when as when_at
from .pictures import Pictures
from .planner import budgets as read_budgets, progression_path
from .planner_page import interface_store
from .settings_looks import js_parse, js_slice, js_units
from .timers_page import Fold

# ------------------------------------------------------------------ the words (build-workspace.js)
TITLE = "Build workspace"
LOADING = "Loading build catalog…"
UNAVAILABLE = "Build catalog unavailable"
UNSUPPORTED = "Unsupported catalog"
INTRO = ("Plan a local allocation draft. Source character stats, equipment and optimizer scores remain read-only "
         "references. Explicit evaluation uses entered equipment/stat contributions and Genus lines with the existing "
         "damage model. It does not recalculate combat power, gear score or survivability.")
NEW = "New empty draft"
IMPORT = "Import profile / optimizer / draft JSON"
CHOOSE = "Choose file…"
PRESET = "Load current community preset"
SAVE = "Save local draft"
EXPORT = "Export build JSON"
SAVED_TITLE = "Saved local drafts"
SAVED_NOTE = ("Up to ten drafts / 2 MiB, kept by the app on your machine for its window and the web pages alike. Saved "
              "references can contain character information. Nothing is uploaded automatically. Unsaved edits are not "
              "retained after leaving this page.")
NO_DRAFTS = "No drafts saved."
TABS = (("active", "Active skills"), ("passive", "Passives"), ("stigma", "Stigmas"), ("daevanion", "Daevanion"),
        ("equipment", "Equipment"), ("arcana", "Arcana cards"), ("pantheon", "Pantheon"), ("genus", "Genus Insight"),
        ("inputs", "Evaluation / advanced inputs"), ("reference", "Source character"))
SKILL_TABS = {"active": "Active skills", "passive": "Passives", "stigma": "Stigmas"}
NO_BUDGETS = "No server totals loaded."
READING_BUDGETS = "Loading highest server-reported totals…"
NO_COMMUNITY = "Community server unavailable; enter budgets explicitly."
SERVER_BUDGETS = "Use highest server-reported budgets"
ERRORS_TITLE = "Catalog validation errors"
PASSES = ("Allocation passes the listed catalog and entered-budget checks. Game legality, ownership and current-build "
          "applicability remain unverified.")
SEARCH = "Search skills"
NO_MATCH = "No skills match this search."
BOARDS = "Daevanion boards"
NOTES = "Draft notes"
SOURCE_IMAGE = "Source image unavailable"
ON_THE_WEB = ("This part of the draft is drawn on the web Builds page for now. Save the draft here, then load it there "
              "from Saved local drafts.")
OPEN_WEB = "Open the web Builds page"
# what was done
PENDING = "Apply pending component/Genus edits first."
MODE_CHANGED = "Draft mode changed. No score was recalculated."
BAD_LEVEL = "Choose an integer level from 1 to 45."
BAD_BUDGET = "Budget must be an integer from 0 to 10000."
BAD_BONUS = "Bonus level must be an integer from 0 to 30."
BAD_BOARD_BUDGET = "Board budget must be an integer from 0 to 10000."
APPLY_FIRST_TAB = "Apply component edits or save Genus lines before changing build sections."
APPLY_FIRST_SAVE = "Apply edited equipment/Genus inputs before saving."
APPLY_FIRST_EXPORT = "Apply edited equipment/Genus inputs before exporting."
EXPORT_BLOCKED = "Export blocked: fix the catalog validation errors first."
TOO_LARGE = "Build is too large to export (2 MiB limit)."
SAVED_WITH_ERRORS = "Draft saved locally with validation errors; export stays blocked."
SAVED_OK = "Draft saved by the app."
LOADED = "Saved draft loaded."
REMOVED = "Local saved draft removed. The open draft is retained."
IMPORTED = "Import loaded. Check the reference and catalog validation before exporting."
FILE_TOO_LARGE = "Choose JSON no larger than 2 MiB."
LOADING_PRESET = "Loading server-evaluated community preset…"
PRESET_LOADED = ("Community preset copied into a local draft. Its original score is reference only; edits are not "
                 "scored.")
NO_PRESET_SERVER = "Community server unavailable"
# the questions
ASK_CLASS = "Replace unsaved allocations with an empty draft for this class?"
ASK_NEW = "Replace the unsaved draft with an empty draft?"
ASK_LOAD = "Replace the unsaved draft with this saved draft?"
ASK_IMPORT = "Replace the unsaved draft with this import?"
ASK_PRESET = "Replace the unsaved allocation with the current community preset?"
#: A picture the page shows (``icon``): one on these hosts, else the catalog's ◇.
ICON = re.compile(r"https://(?:metabot\.gg/web/aion2/|assets\.playnccdn\.com/|profileimg\.plaync\.com/"
                  r"|gamers4\.life/aion-2/database/icons/)")
#: A board node's edge by its grade (``colors``).
NODE_EDGES = {"Unique": "g_unique", "Legend": "g_legend", "Epic": "g_epic", "Rare": "g_rare"}
NODE = 48                                         # a node's square (``.bw-node``), 6 px apart (``.bw-board``)
NODE_GAP = 6


def catalog_note(catalog: dict, draft: dict) -> str:
    """The catalog's note over the skills and boards (``p.small.muted``)."""
    revision = js_string(catalog.get("revision") or "")
    differs = draft.get("catalog_revision") != catalog.get("revision")
    return (f"{js_string(catalog.get('note'))} Revision {js_slice(revision, 12)}."
            + (" Imported catalog revision differs; this draft is being checked against the bundled catalog." if differs
               else "")
            + " Unentered bonus levels are assumed zero. PvE/PvP labels do not alter allocation rules or verify "
              "tactical performance.")


def budget_kind(tab: str) -> str:
    return "stigma" if tab == "stigma" else "daevanion" if tab == "daevanion" else "skill"


def used(tab: str, a: dict, draft: dict) -> str:
    """``Used: … / … points.``"""
    spent = a["stigma"] if tab == "stigma" else a["crystal"] if tab == "daevanion" else a["sp"]
    return f"Used: {js_string(spent)} / {js_string(draft['budgets'][budget_kind(tab)])} points."


def icon_url(entry) -> str:
    """The picture's address when it is one the page shows (``icon``), else nothing."""
    url = js_string(entry.get("icon") or "") if isinstance(entry, dict) else ""
    return url if ICON.match(url) else ""


def skill_line(s: dict, lv: dict, cards: dict, slots: int) -> str:
    """A skill card's line (``span``): its effective level, its arcana cards' levels, its supporting slots."""
    key = js_string(s.get("id"))
    level = lv.get(key)
    shown = js_string(level) if b.truthy(level) else "0"
    stigma = s.get("kind") == "stigma"
    return (f"Effective level {shown}" + (f" · {js_string(cards[key])} card levels" if b.truthy(cards.get(key)) else "")
            + (" · equipped only above zero" if stigma else f" · {slots} supporting slots"))


def effect_words(index: int, e: dict, level, stigma: bool) -> tuple[str, str]:
    """A supporting effect's words and its note (``(effect Lv …)``)."""
    locked = number_less(level, e.get("unlock"))
    return (f"{index + 1} · {js_string(e.get('text'))}",
            f"(effect Lv {js_string(e.get('unlock'))}{' · locked' if locked else ''}{' · automatic' if stigma else ''})")


def number_less(a, b_) -> bool:
    """``a < b`` for numbers, false where either is not one (NaN)."""
    x, y = js_number(a), js_number(b_)
    return not (math.isnan(x) or math.isnan(y)) and x < y


def node_title(n: dict, s: dict | None, locked: bool) -> str:
    """A board node's tip (``title``)."""
    stats = ", ".join(f"{js_string(x.get('stat'))} {js_string(x.get('value'))}" for x in n.get("stats") or []
                      if isinstance(x, dict))
    return (js_string(b._or(n.get("label"), n.get("type"))) + " · "
            + (f"{js_string(s.get('name'))} +{js_string(b._or(n.get('skillLevels'), 1))} · " if s is not None else "")
            + f"cost {js_string(b._or(n.get('cost'), 0))}" + (" · level locked" if locked else "") + " · " + stats)


def node_mark(n: dict, taken: bool) -> str:
    """The corner of a node (``small``): ★ the centre, ✓ taken, else its cost."""
    if n.get("type") == "Start":
        return "★"
    return "✓" if taken else js_string(b._or(n.get("cost"), 0))


# ------------------------------------------------------------------ the pictures
class Remote(QObject):
    """Pictures on the hosts the page shows (``icon``) the app does not bundle, read off the interface's thread and
    handed over as ``loaded(url, bytes)``, or ``failed(url)`` (the web page's ``onerror``); each asked for once."""

    loaded = Signal(str, bytes)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None, read=None):
        super().__init__(parent)
        from .news import _read
        self.read = read or _read
        self._asked: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gui-build-pictures")

    def ask(self, url: str) -> None:
        if not ICON.match(url or "") or url in self._asked:
            return
        self._asked.add(url)
        try:
            self._pool.submit(self._get, url)
        except RuntimeError:                     # stopped: its window has closed
            pass

    def _get(self, url: str) -> None:
        try:
            data = self.read(url)
        except Exception:                        # noqa: BLE001 - a picture that cannot be read is said so
            data = b""
        if data:
            self.loaded.emit(url, data)
        else:
            self.failed.emit(url)

    def forget(self, url: str) -> None:
        self._asked.discard(url)

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class Picture(QLabel):
    """A picture of the page (``icon``): the app's bundled copy, else the source's once read, else the app's logo
    with its tip; ◇ where the catalog gives none on a host the page shows."""

    def __init__(self, url: str, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.url, self.side = url, size
        self.setObjectName("plain")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        if not url:
            self.setText("◇")                    # ``.cr-profile-empty``
            self.setObjectName("bwEmpty")

    def show_picture(self, picture: QPixmap | None, failed: bool = False) -> None:
        if failed:
            picture = QPixmap(LOGO)
            self.setToolTip(SOURCE_IMAGE)
        if picture is not None and not picture.isNull():
            self.setPixmap(picture.scaled(self.side, self.side, Qt.KeepAspectRatio, Qt.SmoothTransformation))


# ------------------------------------------------------------------ the parts
def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _button(words: str, action, name: str = "small") -> QPushButton:
    button = QPushButton(words.replace("&", "&&"))
    button.setObjectName(name)
    button.setAccessibleName(words)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _plain(kind=QVBoxLayout, spacing: int = 8) -> tuple[QWidget, QVBoxLayout | QHBoxLayout]:
    box = QWidget()
    box.setObjectName("plain")
    line = kind(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _row(*widgets: QWidget) -> QWidget:
    """``.row``: side by side 12 px apart, on to another line where there is no room."""
    box = QWidget()
    box.setObjectName("plain")
    flow = FlowLayout(box, align=Qt.AlignLeft, gap=(12, 8))
    for widget in widgets:
        flow.addWidget(widget)
    return box


def _field(words: str, widget: QWidget) -> QWidget:
    """``<label>words <input></label>``."""
    box, line = _plain(QHBoxLayout, 6)
    line.addWidget(_label(words, wrap=False))
    line.addWidget(widget)
    return box


def _note(*widgets: QWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("note")
    column = QVBoxLayout(frame)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)
    for widget in widgets:
        column.addWidget(widget)
    return frame


def _head(words: str) -> QLabel:
    label = _label(words, "combatHead")
    label.setIndent(0)
    return label


class NumberField(QLineEdit):
    """A number field (``input type=number``) as the web page reads it: what a browser lets be typed in one (digits,
    a point, a sign and an exponent), and its value (``field_value``: empty when that is not a number) when it is
    changed and left, or Enter is pressed (``change``)."""

    changed = Signal(str)

    def __init__(self, value, width: int = 75, parent: QWidget | None = None):
        super().__init__(field_value(js_string(value)) if value is not None else "", parent)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9.eE+\-]*"), self))
        self.kept = self.text()
        self.setFixedWidth(width)
        self.editingFinished.connect(self._finished)

    def value(self) -> str:
        return field_value(self.text())

    def reset(self, value) -> None:
        self.setText(field_value(js_string(value)))
        self.kept = self.text()

    def _finished(self) -> None:
        if self.text() != self.kept:
            self.kept = self.text()
            self.changed.emit(field_value(self.text()))


class Notes(QPlainTextEdit):
    """The draft's notes (``textarea maxlength=4000 rows=3``): ``changed`` when edited and left."""

    changed = Signal(str)

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlainText(text)
        self.kept = text
        self.setFixedHeight(self.fontMetrics().lineSpacing() * 3 + 14)
        self.textChanged.connect(self._limit)

    def _limit(self) -> None:
        text = self.toPlainText()
        if js_units(text) > 4000:
            self.blockSignals(True)
            self.setPlainText(js_slice(text, 4000))
            self.blockSignals(False)
            self.moveCursor(self.textCursor().MoveOperation.End)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if self.toPlainText() != self.kept:
            self.kept = self.toPlainText()
            self.changed.emit(self.kept)


class Effect(QWidget):
    """A supporting effect (``.bw-effects label``): its tick, then its words and its note in small muted letters, which
    wrap; a click on the words ticks it, as on a label."""

    def __init__(self, text: str, note: str, on: bool, enabled: bool, toggled, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.plain = f"{text} {note}"
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.tick = QCheckBox()
        self.tick.setChecked(on)
        self.tick.setEnabled(enabled)
        self.tick.setAccessibleName(f"{text} {note}")
        self.tick.toggled.connect(toggled)
        line.addWidget(self.tick, 0, Qt.AlignTop)
        self.words = QLabel(f"{html.escape(text, quote=False)} <span style='color: {theme.COLORS['muted']};'>"
                            f"{html.escape(note, quote=False)}</span>")
        self.words.setTextFormat(Qt.RichText)
        self.words.setWordWrap(True)
        self.words.setObjectName("bwEffect")
        line.addWidget(self.words, 1)

    def mouseReleaseEvent(self, event) -> None:
        if self.tick.isEnabled() and event.button() == Qt.LeftButton:
            self.tick.toggle()
        super().mouseReleaseEvent(event)


class Node(QPushButton):
    """A board node (``.bw-node``): 48 px, its edge its grade's colour, its skill's picture or its short words, and its
    mark in the corner; gold within when taken (or the centre)."""

    def __init__(self, n: dict, chosen: bool, mark: str, words: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.node_id, self.mark = n.get("id"), mark
        self.setObjectName("bwNodeOn" if chosen else "bwNode")
        self.setFixedSize(NODE, NODE)
        self.setCheckable(False)
        self.setCursor(Qt.PointingHandCursor)
        edge = theme.css(NODE_EDGES[n.get("grade")]) if n.get("grade") in NODE_EDGES else theme.COLORS["line"]
        self.setStyleSheet(f"QPushButton {{ border: 2px solid {edge}; }}")
        grid = QGridLayout(self)
        grid.setContentsMargins(3, 3, 2, 0)
        grid.setSpacing(0)
        self.picture: Picture | None = None
        self.face = _label(words or "", "bwNodeWords", wrap=False)
        self.face.setAlignment(Qt.AlignCenter)
        self.face.setAttribute(Qt.WA_TransparentForMouseEvents)
        grid.addWidget(self.face, 0, 0, Qt.AlignCenter)
        corner = _label(mark, "bwNodeMark", wrap=False)
        corner.setAttribute(Qt.WA_TransparentForMouseEvents)
        grid.addWidget(corner, 0, 0, Qt.AlignRight | Qt.AlignBottom)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.objectName() == "bwNodeOn":
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(theme.COLORS["gold"]), 2))
            painter.drawRoundedRect(QRectF(3, 3, self.width() - 6, self.height() - 6), 3, 3)
            painter.end()

    def hold(self, picture: "Picture") -> None:
        """The node's skill's picture in its middle (``img`` 32 px)."""
        self.picture = picture
        picture.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.layout().addWidget(picture, 0, 0, Qt.AlignCenter)
        self.face.hide()


def stylesheet() -> str:
    c = theme.COLORS
    return combat_stylesheet() + f"""
        QFrame#bwSkill {{ background: {theme.css('panel')}; border: 1px solid {c['line']}; border-radius: 6px; }}
        QFrame#bwSkill QLabel, QFrame#bwSkill QCheckBox {{ background: transparent; }}
        QFrame#bwCard {{ background: {theme.css('panel')}; border: 1px solid {c['line']}; border-radius: 6px; }}
        QLabel#bwEmpty {{ color: {c['muted']}; font-size: 24px; }}
        QLabel#bwKind, QLabel#bwLine, QLabel#bwEffectNote {{ color: {c['muted']}; }}
        QLabel#bwName {{ font-weight: 700; }}
        QPushButton#bwNode, QPushButton#bwNodeOn {{ border-radius: 5px; background: {c['bg1']}; color: {c['text']};
            padding: 0px; }}
        QPushButton#bwNodeOn {{ background: #554421; }}
        QPushButton#bwNode:disabled, QPushButton#bwNodeOn:disabled {{ color: {c['text']}; }}
        QLabel#bwNodeWords {{ background: transparent; }}
        QLabel#bwNodeMark {{ background: {c['bg1']}; padding: 0px 2px; font-size: 11px; }}
        QWidget#bwBoard, QScrollArea#bwBoardScroll {{ background: transparent; border: none; }}
        QPlainTextEdit#bwNotes {{ background: {c['bg2']}; border: 1px solid {c['line2']}; border-radius: 5px; }}
        """


# ------------------------------------------------------------------ the page
class BuildsPage(QWidget):
    """Character → Builds. ``open_web`` opens a page of the web interface; ``confirm``, ``choose_file`` and
    ``save_file`` stand in for the questions and the file dialogs; ``store`` keeps the drafts (the app's interface
    data); ``read_picture`` reads a source's picture (the web page's ``img``)."""

    def __init__(self, api: AppApi | None, open_web=None, parent: QWidget | None = None, store=None, confirm=None,
                 choose_file=None, save_file=None, pictures: Pictures | None = None, read_picture=None):
        super().__init__(parent)
        self.api = api
        self.open_web = open_web or (lambda page: None)
        self.store = store if store is not None else interface_store()
        self.confirm = confirm or self._ask
        self.choose_file = choose_file or self._ask_file
        self.save_file = save_file or self._ask_where
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.pictures = pictures if pictures is not None else (Pictures(api, self) if api is not None else None)
        if self.pictures is not None:
            self.pictures.changed.connect(self._bundled)
            self.pictures.unmapped.connect(self._bundled)
        self.remote = Remote(self, read_picture)
        self.remote.loaded.connect(self._remote_loaded)
        self.remote.failed.connect(self._remote_failed)
        self.kept_pictures: dict[str, QPixmap | None] = {}     # a source's picture once read (None: it could not be)
        self.shown_pictures: list[Picture] = []
        image_health.watch(self)
        self.catalog: dict | None = None
        self.catalog_error = ""
        self.context: dict = {}
        self.mount_turn = 0                       # each opening of the page: a later one lets the earlier's answers go
        self.mounted = False
        self.draft: dict = {}
        self.draft_turn = 0                       # each draft put in place (``draft !== owner``)
        self.serial = 0
        self.budget_request = 0
        self.reset_state()
        self.setObjectName("plain")
        self.setStyleSheet(stylesheet())
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        content = QWidget()
        content.setObjectName("plain")
        self.scroll.setWidget(content)
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(12)
        self.frame: Window | None = None
        self.message_label: QLabel | None = None
        self.preset_button: QPushButton | None = None
        self.body: QVBoxLayout | None = None
        self.skills_box: QVBoxLayout | None = None

    def reset_state(self) -> None:
        self.tab = "active"
        self.skill_filter = ""
        self.board_name = ""
        self.dirty = False
        self.budget_note = NO_BUDGETS
        self.reference = None
        self.source: dict = {}
        self.component_buffer = None
        self.genus_dirty = False
        self.input_buffer = None

    # ---------------------------------------------------------------- opening and leaving
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.mounted:
            self.mount()

    def leave(self) -> None:
        """Another page shown (the web page's ``dispose``): what is on its way is let go, and the page starts afresh
        when it is opened again."""
        self.mounted = False
        self.mount_turn += 1
        self.serial += 1

    def mount(self, context: dict | None = None) -> None:
        """The page opened (``mount``): the catalog read once, then an empty draft for the class (``io.className``,
        else the catalog's first), the mode and the level given, and the class's budgets asked for."""
        self.mounted = True
        self.mount_turn += 1
        self.context = dict(context or {})
        self.reset_state()
        self.reference = self.context.get("reference")
        self.source = self.context.get("source") or {}
        self.tab = "reference" if self.context.get("reference") else "active"
        if self.catalog is not None:
            self._start()
            return
        self._loading(LOADING)
        if self.requests is not None:
            self.requests.get(f"catalog:{self.mount_turn}", "/static/build-catalog.json")
        else:
            self._loading("Could not open build workspace: " + UNAVAILABLE)

    def _loading(self, words: str) -> None:
        _clear(self.layout_)
        self.frame = None
        self.layout_.addWidget(_label(words))
        self.layout_.addStretch(1)

    def _start(self) -> None:
        catalog = self.catalog or {}
        names = list(b.classes(catalog))
        wanted = self.context.get("className")
        initial = wanted if isinstance(wanted, str) and wanted in b.classes(catalog) else (names[0] if names else "")
        level = self.context.get("level")
        self._put(b.fresh(catalog, initial, "pvp" if self.context.get("mode") == "pvp" else "pve",
                          level if b.integer(level, 1, 45) else 45))
        self.render()
        self.server_budgets()

    def _put(self, draft: dict) -> None:
        """A draft put in place (``draft = …``)."""
        self.draft = draft
        self.draft_turn += 1

    # ---------------------------------------------------------------- the frame (``render``)
    def message(self, words: str) -> None:
        if self.message_label is not None:
            self.message_label.setText(words)

    def pending_inputs(self) -> bool:
        """Edits not applied yet (``pendingInputs``): a card's rolls or skills, the Genus lines, the advanced JSON."""
        return bool(self.component_buffer) or self.genus_dirty or bool(self.input_buffer)

    def render(self) -> None:
        catalog, draft = self.catalog or {}, self.draft
        _clear(self.layout_)
        frame = Window(TITLE)
        self.frame = frame
        body = frame.body
        body.addWidget(_note(_label(INTRO)))
        self.class_box = QComboBox()
        self.class_box.setAccessibleName("Class")
        for name in b.classes(catalog):
            self.class_box.addItem(name, name)
        at = self.class_box.findData(draft["class"]) if isinstance(draft["class"], str) else -1
        self.class_box.setCurrentIndex(max(0, at))
        self.class_index = self.class_box.currentIndex()
        self.class_box.activated.connect(self._class_changed)
        self.preset_button = _button(PRESET, self.canonical)
        body.addWidget(_row(_field("Class", self.class_box), _button(NEW, self.new_draft),
                            _field(IMPORT, _button(CHOOSE, self.import_file)), self.preset_button))
        self.name_edit = QLineEdit(js_string(draft["name"]))
        self.name_edit.setMaxLength(120)
        self.name_edit.setAccessibleName("Draft name")
        self.name_edit.setMinimumWidth(220)
        self.name_kept = self.name_edit.text()
        self.name_edit.editingFinished.connect(self._name_changed)
        self.mode_box = QComboBox()
        self.mode_box.setAccessibleName("Mode")
        self.mode_box.addItem("PvE", "pve")
        self.mode_box.addItem("PvP", "pvp")
        self.mode_box.setCurrentIndex(1 if draft["mode"] == "pvp" else 0)
        self.mode_index = self.mode_box.currentIndex()
        self.mode_box.activated.connect(self._mode_changed)
        self.level_edit = NumberField(draft["level"], 75)
        self.level_edit.setAccessibleName("Character level")
        self.level_edit.changed.connect(self._level_changed)
        body.addWidget(_row(_field("Draft name", self.name_edit), _field("Mode", self.mode_box),
                            _field("Character level", self.level_edit), _button(SAVE, self.save),
                            _button(EXPORT, self.download)))
        self.message_label = _label("", "combatMessage")
        self.message_label.setAccessibleName("Status")
        body.addWidget(self.message_label)
        self.saved_fold = Fold(SAVED_TITLE)
        self.saved_fold.add(_label(SAVED_NOTE, "small"))
        holder, self.saved_rows = _plain(spacing=8)
        self.saved_fold.add(holder)
        body.addWidget(self.saved_fold)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, words in TABS:
            tab = QPushButton(words)
            tab.setObjectName("tabOn" if key == self.tab else "tab")
            tab.setAccessibleName(words)
            tab.clicked.connect(lambda _checked=False, key=key: self.show_tab(key))
            self.tab_buttons[key] = tab
        body.addWidget(_tab_row(list(self.tab_buttons.values())))
        holder, self.body = _plain(spacing=10)
        body.addWidget(holder)
        self.layout_.addWidget(frame)
        self.layout_.addStretch(1)
        self.render_saved()
        self.draw_body()

    def _changed(self) -> None:
        """What every edit of the draft does: ``serial++``, the preset button free again, the draft not saved."""
        self.serial += 1
        if self.preset_button is not None:
            self.preset_button.setEnabled(True)
        self.dirty = True

    def _name_changed(self) -> None:
        if self.name_edit.text() == self.name_kept:
            return
        self.name_kept = self.name_edit.text()
        self.draft["name"] = self.name_kept
        self._changed()

    def _mode_changed(self, index: int) -> None:
        if index == self.mode_index:
            return
        if self.pending_inputs():
            self.mode_box.setCurrentIndex(self.mode_index)
            self.message(PENDING)
            return
        self.mode_index = index
        self.draft["mode"] = self.mode_box.itemData(index)
        self._changed()
        self.draw_body()
        self.message(MODE_CHANGED)

    def _level_changed(self, value: str) -> None:
        if self.pending_inputs():
            self.level_edit.reset(self.draft["level"])
            self.message(PENDING)
            return
        n = js_number(value)
        if not b.integer(n, 1, 45):
            self.message(BAD_LEVEL)
            self.level_edit.reset(self.draft["level"])
            return
        self.draft["level"] = int(n)
        self._changed()
        self.draw_body()

    def _class_changed(self, index: int) -> None:
        if index == self.class_index:
            return
        if (self.dirty or self.pending_inputs()) and not self.confirm(ASK_CLASS):
            self.class_box.setCurrentIndex(self.class_index)
            return
        self._fresh_start(self.class_box.itemData(index), self.draft["mode"], 45)
        self.board_name = ""
        self.render()
        self.server_budgets()

    def _fresh_start(self, cls, mode, level) -> None:
        self.component_buffer = self.input_buffer = None
        self.genus_dirty = False
        self.serial += 1
        self._put(b.fresh(self.catalog or {}, cls, mode, level))
        self.reference, self.source = None, {}
        self._changed()

    def new_draft(self) -> None:
        if (self.dirty or self.pending_inputs()) and not self.confirm(ASK_NEW):
            return
        self._fresh_start(self.draft["class"], self.draft["mode"], self.draft["level"])
        self.render()
        self.server_budgets()

    def show_tab(self, key: str) -> None:
        if self.pending_inputs():
            self.message(APPLY_FIRST_TAB)
            return
        self.tab = key
        self.genus_dirty = False
        self.render()

    # ---------------------------------------------------------------- the drafts kept
    def kept_text(self):
        return self.store.value(b.STORE)

    def render_saved(self) -> None:
        _clear(self.saved_rows)
        self.saved_buttons: list[tuple[str, QPushButton, QPushButton]] = []
        rows = b.saved(self.kept_text())
        if not rows:
            self.saved_rows.addWidget(_label(NO_DRAFTS))
            return
        for row in rows:
            key = b.row_key(row)
            load = _button(b.row_name(row), lambda key=key: self.load_saved(key))
            remove = _button("Remove", lambda key=key: self.remove_saved(key))
            self.saved_buttons.append((key, load, remove))
            when = _label(when_at(row.get("updated_at") if isinstance(row, dict) else None), "small", wrap=False)
            self.saved_rows.addWidget(_row(load, when, remove))

    def load_saved(self, key: str) -> None:
        try:
            if (self.dirty or self.pending_inputs()) and not self.confirm(ASK_LOAD):
                return
            entry = b.find_row(self.kept_text(), key)
            self.component_buffer = self.input_buffer = None
            self.genus_dirty = False
            self.serial += 1
            if entry is None:
                raise b.BuildError("Cannot read properties of undefined (reading 'draft')")
            draft = b.normalize(self.catalog or {}, entry.get("draft") if isinstance(entry, dict) else None)
            draft["local_id"] = entry["id"]
            self._put(draft)
            self.reference, self.source = draft["reference"], draft["source"]
            self.dirty = False
            self.render()
            self.message(LOADED)
        except b.BuildError as problem:
            self.message(str(problem))

    def remove_saved(self, key: str) -> None:
        try:
            self.store.setValue(b.STORE, b.stringify(b.without(self.kept_text(), key)))
            if b.same(self.draft.get("local_id", b._MISSING), key):
                del self.draft["local_id"]
            self.render_saved()
            self.message(REMOVED)
        except b.BuildError as problem:
            self.message(str(problem))

    def save(self) -> None:
        """Save local draft (``save``): the draft checked and kept first among the drafts."""
        if self.pending_inputs():
            self.message(APPLY_FIRST_SAVE)
            return
        try:
            rows, ident = b.saved_with(self.catalog or {}, self.draft, self.reference, self.source, self.kept_text())
            self.store.setValue(b.STORE, b.stringify(rows))
            self.draft["local_id"] = ident
            self.dirty = False
            self.render_saved()
            self.message(SAVED_WITH_ERRORS if b.assessment(self.catalog or {}, self.draft)["errors"] else SAVED_OK)
        except b.BuildError as problem:
            self.message("Could not save draft: " + str(problem))

    def download(self) -> None:
        """Export build JSON (``download``): the draft checked, then saved as a file of its own."""
        try:
            if self.pending_inputs():
                self.message(APPLY_FIRST_EXPORT)
                return
            if b.assessment(self.catalog or {}, self.draft)["errors"]:
                self.message(EXPORT_BLOCKED)
                return
            doc = b.copy(self.draft)
            doc["catalog_revision"] = (self.catalog or {}).get("revision")
            doc["reference"], doc["source"] = self.reference, self.source
            clean = b.normalize(self.catalog or {}, doc)
            if b.size(clean) > b.MAX:
                self.message(TOO_LARGE)
                return
            path = self.save_file(b.export_name(js_string(self.draft["name"])))
            if not path:
                return
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(b.stringify(clean, 2))
            self.message(f"Build exported: {path}. Source stats were not recalculated.")
        except b.BuildError as problem:
            self.message("Export failed: " + str(problem))
        except OSError as problem:
            self.message("Export failed: " + str(problem))

    def import_file(self) -> None:
        """Import profile / optimizer / draft JSON (``importFile``)."""
        path = self.choose_file()
        if not path:
            return
        self.serial += 1
        try:
            if os.path.getsize(path) > b.MAX:
                raise b.BuildError(FILE_TOO_LARGE)
            with open(path, "rb") as file:
                value = js_parse(file.read())
        except (OSError, ValueError, RecursionError) as problem:
            self.message("Import failed: " + str(problem))
            return
        try:
            if (self.dirty or self.pending_inputs()) and not self.confirm(ASK_IMPORT):
                return
            nxt, profile = b.imported(self.catalog or {}, self.draft, value)
            if profile:
                self.tab = "reference"
            self.component_buffer = self.input_buffer = None
            self.genus_dirty = False
            self.serial += 1
            self._put(nxt)
            self.reference, self.source = nxt["reference"], nxt["source"]
            self._changed()
            self.render()
            self.message(IMPORTED)
        except b.BuildError as problem:
            self.message("Import failed: " + str(problem))

    def canonical(self) -> None:
        """Load current community preset (``canonical``)."""
        if (self.dirty or self.pending_inputs()) and not self.confirm(ASK_PRESET):
            return
        self.serial += 1
        self.preset_button.setEnabled(False)
        self.message(LOADING_PRESET)
        if self.requests is None:
            self.message("Could not load preset: " + NO_PRESET_SERVER)
            self.preset_button.setEnabled(True)
            return
        path = "/api/v2/presets/" + js_string(self.draft["class"]) + "/" + js_string(self.draft["mode"])
        self.requests.get(f"preset:{self.serial}:{self.mount_turn}",
                          "/api/community?path=" + urllib.parse.quote(path, safe="-_.!~*'()"))

    def _preset(self, answer, request: int) -> None:
        if request != self.serial or not self.mounted:
            return
        try:
            if isinstance(answer, dict) and b.truthy(answer.get("error")):
                raise b.BuildError(js_string(answer["error"]))
            self.component_buffer = self.input_buffer = None
            self.genus_dirty = False
            draft = b.from_summary(self.catalog or {}, b.get(answer, "build"))
            self._put(draft)
            self.reference, self.source = draft["reference"], draft["source"]
            self.serial += 1
            self.dirty = True
            self.render()
            self.message(PRESET_LOADED)
        except b.BuildError as problem:
            self.message("Could not load preset: " + str(problem))
            if self.preset_button is not None:
                self.preset_button.setEnabled(True)

    # ---------------------------------------------------------------- the class's budgets (``serverBudgets``)
    def server_budgets(self) -> None:
        self.budget_request += 1
        self.budget_note = READING_BUDGETS
        self.message(self.budget_note)
        if self.requests is None:
            self._budgets_failed(self.budget_request, self.draft_turn, NO_COMMUNITY)
            return
        snapshot = b.get(self.reference, "snapshot")
        region = b._or(b.get(b.get(snapshot, "identity"), "region"), b._or(b.get(b.get(snapshot, "data"), "region"), ""))
        context = {"region": region} if b.truthy(region) else {}
        path = progression_path(js_string(self.draft["class"]), context)
        self.requests.get(f"budgets:{self.budget_request}:{self.draft_turn}:{self.mount_turn}",
                          "/api/community?path=" + urllib.parse.quote(path, safe="-_.!~*'()"))

    def _budgets(self, answer, request: int, owner: int) -> None:
        if request != self.budget_request or owner != self.draft_turn or not self.mounted:
            return
        try:
            if isinstance(answer, dict) and b.truthy(answer.get("error")):
                raise ValueError(js_string(answer["error"]))
            snapshot = b.get(self.reference, "snapshot")
            region = b._or(b.get(b.get(snapshot, "identity"), "region"),
                           b._or(b.get(b.get(snapshot, "data"), "region"), ""))
            result = read_budgets(answer, js_string(self.draft["class"]), {"region": region} if b.truthy(region) else {})
        except ValueError as problem:
            self._budgets_failed(request, owner, str(problem))
            return
        self.budget_note = result["note"]
        for key in b.KINDS:
            if result["points"].get(key) is not None:
                self.draft["budgets"][key] = result["points"][key]
        self.serial += 1
        self.dirty = True
        if not self.pending_inputs():
            self.draw_body()
        self.message(result["note"])

    def _budgets_failed(self, request: int, owner: int, why: str) -> None:
        if request != self.budget_request or owner != self.draft_turn or not self.mounted:
            return
        self.budget_note = why
        if not self.pending_inputs():
            self.draw_body()
        self.message(why)

    # ---------------------------------------------------------------- answers
    def _replied(self, name: str, answer) -> None:
        kind, *rest = name.split(":")
        if kind == "catalog":
            if int(rest[0]) != self.mount_turn:
                return
            if not isinstance(answer, dict) or not b.same(answer.get("version", b._MISSING), 1):
                self._loading("Could not open build workspace: " + UNSUPPORTED)
                return
            self.catalog = answer
            self._start()
        elif kind == "budgets":
            if int(rest[2]) == self.mount_turn:
                self._budgets(answer, int(rest[0]), int(rest[1]))
        elif kind == "preset":
            if int(rest[1]) == self.mount_turn:
                self._preset(answer, int(rest[0]))

    def _failed(self, name: str, why: str) -> None:
        kind, *rest = name.split(":")
        if kind == "catalog":
            if int(rest[0]) == self.mount_turn:
                self._loading("Could not open build workspace: " + UNAVAILABLE)
        elif kind == "budgets":
            if int(rest[2]) == self.mount_turn:
                self._budgets_failed(int(rest[0]), int(rest[1]), why)
        elif kind == "preset":
            if int(rest[1]) == self.mount_turn and int(rest[0]) == self.serial and self.mounted:
                self.message("Could not load preset: " + why)
                if self.preset_button is not None:
                    self.preset_button.setEnabled(True)

    # ---------------------------------------------------------------- the tab's body (``body``)
    def draw_body(self) -> None:
        if self.body is None:
            return
        _clear(self.body)
        self.shown_pictures = [p for p in self.shown_pictures if _alive(p)]
        if self.tab not in ("active", "passive", "stigma", "daevanion"):
            self.body.addWidget(_note(_label(ON_THE_WEB)))
            self.body.addWidget(_row(_button(OPEN_WEB, lambda: self.open_web("builds"))))
            return
        catalog, draft = self.catalog or {}, self.draft
        a = b.assessment(catalog, draft)
        cd = b.class_of(catalog, draft["class"]) or {}
        boards = cd.get("boards") or []
        if not any(bd.get("name") == self.board_name for bd in boards):
            self.board_name = js_string(boards[0].get("name")) if boards else ""
        self.body_words = {"note": catalog_note(catalog, draft), "used": used(self.tab, a, draft),
                           "budget_note": self.budget_note, "errors": list(a["errors"])}
        self.body.addWidget(_label(catalog_note(catalog, draft), "small"))
        kind = budget_kind(self.tab)
        field = self.budget_field = NumberField(draft["budgets"][kind], 90)
        words = "Daevanion" if kind == "daevanion" else kind
        field.setAccessibleName(f"{words} budget")
        field.changed.connect(lambda value, kind=kind, field=field: self._budget_changed(kind, value, field))
        self.body.addWidget(_row(_field(f"{words} budget", field)))
        self.body.addWidget(_label(used(self.tab, a, draft)))
        self.body.addWidget(_label(self.budget_note, "small"))
        self.body.addWidget(_row(_button(SERVER_BUDGETS, self.server_budgets)))
        if a["errors"]:
            title = _label(ERRORS_TITLE, "strong")
            lines = [_label("•  " + error) for error in a["errors"]]
            validation = _note(title, *lines)
        else:
            validation = _note(_label(PASSES))
        validation.setAccessibleName("Validation")
        self.body.addWidget(validation)
        if self.tab in SKILL_TABS:
            self.body.addWidget(_head(SKILL_TABS[self.tab]))
            search = self.search_edit = QLineEdit(self.skill_filter)
            search.setAccessibleName(SEARCH)
            search.setMinimumWidth(220)
            search.textChanged.connect(lambda text, lv=a["levels"]: self._search(text, lv))
            self.body.addWidget(_row(_field(SEARCH, search)))
            holder, self.skills_box = _plain(spacing=0)
            self.body.addWidget(holder)
            self.draw_skills(a["levels"])
        else:
            self.body.addWidget(_head(BOARDS))
            self.board_tabs: dict[str, QPushButton] = {}
            for bd in boards:
                name = js_string(bd.get("name"))
                words = f"{name} · cost {js_string(b._or(a['boardCosts'].get(bd.get('name')), 0))}"
                tab = QPushButton(words)
                tab.setObjectName("tabOn" if name == self.board_name else "tab")
                tab.setAccessibleName(words)
                tab.clicked.connect(lambda _checked=False, name=name: self._board_chosen(name))
                self.board_tabs[name] = tab
            self.body.addWidget(_tab_row(list(self.board_tabs.values())))
            self.draw_board(cd)
        notes = self.notes_edit = Notes(js_string(draft["notes"]))
        notes.setObjectName("bwNotes")
        notes.setAccessibleName(NOTES)
        notes.changed.connect(self._notes_changed)
        box, column = _plain(spacing=6)
        column.addWidget(_label(NOTES))
        column.addWidget(notes)
        self.body.addWidget(box)

    def _budget_changed(self, kind: str, value: str, field: NumberField) -> None:
        n = js_number(value)
        if value == "" or not b.integer(n, 0, 10000):
            self.message(BAD_BUDGET)
            field.reset(self.draft["budgets"][kind])
            return
        self.draft["budgets"][kind] = int(n)
        self._changed()
        self.draw_body()

    def _notes_changed(self, text: str) -> None:
        self.draft["notes"] = text
        self._changed()

    def _search(self, text: str, lv: dict) -> None:
        self.skill_filter = text
        self.draw_skills(lv)

    def _board_chosen(self, name: str) -> None:
        self.board_name = name
        self.draw_body()

    # ---------------------------------------------------------------- the skills (``skills``)
    def draw_skills(self, lv: dict) -> None:
        if self.skills_box is None:
            return
        _clear(self.skills_box)
        self.skill_widgets: dict[str, dict] = {}                 # each skill's fields, by its id
        catalog, draft = self.catalog or {}, self.draft
        cards = b.safe_card_bonuses(catalog, draft)
        cd = b.class_of(catalog, draft["class"]) or {}
        wanted = self.skill_filter.lower()
        shown = [s for s in cd.get("skills") or [] if s.get("kind") == self.tab and wanted in js_string(s.get("name")).lower()]
        if not shown:
            self.skills_box.addWidget(_label(NO_MATCH))
            return
        spec_levels = catalog.get("spec_slot_levels") or []
        self.skills_box.addWidget(AutoGrid([self._skill(s, lv, cards, spec_levels) for s in shown], 240, 10))

    def _skill(self, s: dict, lv: dict, cards: dict, spec_levels: list) -> QFrame:
        key, build = js_string(s.get("id")), self.draft["build"]
        stigma = s.get("kind") == "stigma"
        trained = b._or(build["stigmas"].get(key), 0) if stigma else b._or(build["sp"].get(key), 1)
        cap = 20 if stigma else min(10, b._or(s.get("buyMax"), 10))
        level = lv.get(key, math.nan)
        slots = sum(1 for n in spec_levels if not number_less(level, n) and not math.isnan(js_number(level)))
        frame = QFrame()
        frame.setObjectName("bwSkill")
        column = QVBoxLayout(frame)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(10)
        card = QFrame()
        card.setObjectName("bwCard")
        line = QHBoxLayout(card)
        line.setContentsMargins(12, 12, 12, 12)
        line.setSpacing(12)
        line.addWidget(self._picture(icon_url(s), 48))
        words, lines = _plain(spacing=1)
        labels = [_label(js_string(s.get("kind")), "bwKind"), _label(js_string(s.get("name")), "bwName"),
                  _label(skill_line(s, lv, cards, slots), "bwLine")]
        for label in labels:
            lines.addWidget(label)
        line.addWidget(words, 1)
        column.addWidget(card)
        box = QComboBox()
        box.setAccessibleName(f"{'Equipped level' if stigma else 'Trained level'} {js_string(s.get('name'))}")
        for n in range(0 if stigma else 1, int(cap) + 1):
            box.addItem(str(n), n)
        at = box.findData(trained) if b.integer(trained, -math.inf, math.inf) else -1
        box.setCurrentIndex(max(0, at))
        box.activated.connect(lambda index, box=box, key=key, stigma=stigma, start=box.currentIndex():
                              index != start and self._trained(key, stigma, box.itemData(index)))
        parts = [_field("Equipped level" if stigma else "Trained level", box)]
        handles = self.skill_widgets[key] = {"frame": frame, "trained": box, "bonus": None, "effects": {},
                                             "words": [label.text() for label in labels]}
        if not stigma:
            bonus = NumberField(b._or(build["bonus"].get(key), 0), 75)
            bonus.setAccessibleName(f"Manual bonus levels {js_string(s.get('name'))}")
            bonus.changed.connect(lambda value, key=key, bonus=bonus: self._bonus(key, value, bonus))
            parts.append(_field("Manual bonus levels", bonus))
            handles["bonus"] = bonus
        column.addWidget(_row(*parts))
        effects = s.get("specs") or []
        if effects:
            holder, rows = _plain(spacing=7)
            chosen = build["specs"].get(key) or []
            for index, e in enumerate(effects):
                text, note = effect_words(index, e, level, stigma)
                on = (not number_less(trained, e.get("unlock"))) if stigma else any(b.same(x, e.get("id")) for x in chosen)
                effect = Effect(text, note, on, not stigma,
                                lambda checked, key=key, ident=e.get("id"): self._effect(key, ident, checked))
                handles["effects"][e.get("id")] = effect
                rows.addWidget(effect)
            column.addWidget(holder)
        column.addStretch(1)
        return frame

    def _trained(self, key: str, stigma: bool, n: int) -> None:
        field = "stigmas" if stigma else "sp"
        if n == 0:
            self.draft["build"][field].pop(key, None)
        else:
            self.draft["build"][field][key] = n
        self._changed()
        self.draw_body()

    def _bonus(self, key: str, value: str, field: NumberField) -> None:
        n = js_number(value)
        if value == "" or not b.integer(n, 0, 30):
            self.message(BAD_BONUS)
            field.reset(b._or(self.draft["build"]["bonus"].get(key), 0))
            return
        self.draft["build"]["bonus"][key] = int(n)
        self._changed()
        self.draw_body()

    def _effect(self, key: str, ident, checked: bool) -> None:
        chosen = b._or(self.draft["build"]["specs"].get(key), [])
        self.draft["build"]["specs"][key] = [*chosen, ident] if checked else [n for n in chosen if not b.same(n, ident)]
        self._changed()
        self.draw_body()

    # ---------------------------------------------------------------- a board (``board``)
    def draw_board(self, cd: dict) -> None:
        self.board_budget_field = None
        self.node_buttons = {}
        board = next((bd for bd in cd.get("boards") or [] if js_string(bd.get("name")) == self.board_name), None)
        if board is None:
            return
        catalog, draft = self.catalog or {}, self.draft
        selected = set(draft["build"]["daevanion_nodes"])
        nodes = board.get("nodes") or []
        name = js_string(board.get("name"))
        self.board_text = (f"{name} · opens at character Lv {js_string(board.get('needLevel'))}. Select adjacent paths "
                           "from the centre. Node icons identify the skill ranked up; hover or focus for node details.")
        self.body.addWidget(_label(self.board_text))
        if board.get("name") not in (catalog.get("crystal_boards") or []):
            field = self.board_budget_field = NumberField(b._or(draft["budgets"]["boards"].get(board.get("name")), 0), 90)
            field.setAccessibleName(f"Separate {name} cost budget")
            field.changed.connect(lambda value, board=board: self._board_budget(board, value))
            self.body.addWidget(_row(_field(f"Separate {name} cost budget", field)))
        if not nodes:
            return
        rows = [n.get("row", 0) for n in nodes]
        cols = [n.get("col", 0) for n in nodes]
        least_row, least_col = min(rows), min(cols)
        grid_box = QWidget()
        grid_box.setObjectName("bwBoard")
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(5, 5, 5, 5)
        grid.setSpacing(NODE_GAP)
        skills = cd.get("skills") or []
        for n in nodes:
            s = next((s for s in skills if b.same(s.get("id"), n.get("skillId"))), None)
            start, taken = n.get("type") == "Start", n.get("id") in selected
            locked = number_less(draft["level"], b._or(n.get("needLevel"), board.get("needLevel")))
            words = None if s is not None else js_string(b._or(n.get("short"), js_slice(js_string(b._or(n.get("type"), "")), 2)))
            button = Node(n, taken or start, node_mark(n, taken), words or "")
            if s is not None:
                button.hold(self._picture(icon_url(s), 32))
            button.setToolTip(node_title(n, s, locked))
            button.setAccessibleName(node_title(n, s, locked))
            button.setEnabled(not start)
            button.clicked.connect(lambda _checked=False, ident=n.get("id"): self._node(ident))
            grid.addWidget(button, int(n.get("row", 0) - least_row), int(n.get("col", 0) - least_col))
            self.node_buttons[n.get("id")] = button
        scroll = QScrollArea()
        scroll.setObjectName("bwBoardScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(grid_box)
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        grid_box.adjustSize()
        scroll.setFixedHeight(grid_box.sizeHint().height() + scroll.horizontalScrollBar().sizeHint().height() + 2)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.body.addWidget(scroll)

    def _node(self, ident) -> None:
        nodes = self.draft["build"]["daevanion_nodes"]
        self.draft["build"]["daevanion_nodes"] = [n for n in nodes if n != ident] if ident in nodes else [*nodes, ident]
        self._changed()
        self.draw_body()
        button = getattr(self, "node_buttons", {}).get(ident)
        if button is not None:
            button.setFocus()

    def _board_budget(self, board: dict, value: str) -> None:
        n = js_number(value)
        if value == "" or not b.integer(n, 0, 10000):
            self.message(BAD_BOARD_BUDGET)
            return
        self.draft["budgets"]["boards"][board.get("name")] = int(n)
        self._changed()
        self.draw_body()

    # ---------------------------------------------------------------- pictures
    def _picture(self, url: str, size: int) -> Picture:
        label = Picture(url, size)
        if url:
            self.shown_pictures.append(label)
            self._fill(label)
        return label

    def _fill(self, label: Picture) -> None:
        url = label.url
        bundled = self.pictures.by_address(url) if self.pictures is not None else None
        if bundled is not None:
            label.show_picture(bundled)
            return
        if self.pictures is not None and self.pictures.bundles(url) is not False:
            return                                   # the app bundles it, or its map is being read: ``changed`` says
        if url in self.kept_pictures:
            kept = self.kept_pictures[url]
            label.show_picture(kept, failed=kept is None)
        else:
            self.remote.ask(url)

    def _bundled(self) -> None:
        self.shown_pictures = [p for p in self.shown_pictures if _alive(p)]
        for label in self.shown_pictures:
            if label.pixmap() is None or label.pixmap().isNull():
                self._fill(label)

    def _remote_loaded(self, url: str, data: bytes) -> None:
        picture = QPixmap()
        self.kept_pictures[url] = picture if picture.loadFromData(data) else None
        if self.kept_pictures[url] is None:
            image_health.failed(url)
        self._show_kept(url)

    def _remote_failed(self, url: str) -> None:
        self.kept_pictures[url] = None
        image_health.failed(url)
        self._show_kept(url)

    def _show_kept(self, url: str) -> None:
        self.shown_pictures = [p for p in self.shown_pictures if _alive(p)]
        kept = self.kept_pictures.get(url)
        for label in self.shown_pictures:
            if label.url == url:
                label.show_picture(kept, failed=kept is None)

    def retry_pictures(self) -> None:
        """Retry images: the sources' pictures that could not be read are read again the next time they show."""
        for url in [u for u, picture in self.kept_pictures.items() if picture is None]:
            self.kept_pictures.pop(url)
            self.remote.forget(url)

    # ---------------------------------------------------------------- the dialogs
    def _ask(self, words: str) -> bool:
        return QMessageBox.question(self, "Aion 2 Calc", words) == QMessageBox.Yes

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, IMPORT, "", "Build JSON (*.json *.a2build)")
        return path

    def _ask_where(self, name: str) -> str:
        """Where the build is saved, the computer's Downloads folder offered (where a browser puts a download)."""
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, EXPORT, os.path.join(folder, name), "JSON (*.json)")
        return path

    def closeEvent(self, event) -> None:
        self.remote.stop()
        super().closeEvent(event)


def _alive(widget) -> bool:
    try:
        import shiboken6
        return shiboken6.isValid(widget)
    except ImportError:                          # pragma: no cover - PySide6 brings it
        return True


def _tab_row(tabs: list[QWidget]) -> QWidget:
    """A row of tabs 4 px apart that goes on to another line where there is no room (``.tabs``)."""
    box = QWidget()
    box.setObjectName("plain")
    flow = FlowLayout(box, align=Qt.AlignLeft, gap=(4, 4))
    for tab in tabs:
        flow.addWidget(tab)
    return box
