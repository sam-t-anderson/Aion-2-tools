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
- **Equipment and Arcana cards** (0.2.487): the doll's twenty slots or the five cards, each with its draft item; the
  slot chosen's catalog items, searched by name; its item's enhancement, entered random rolls from the item's source
  pool and a card's skill levels from the class's pool, held until applied or discarded; the draft's other imported
  contributions to remove; the source profile's recorded equipment, read only.
- Pantheon, Genus Insight, Evaluation / advanced inputs and Source character are still drawn on the web Builds page:
  a saved draft opens there.

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
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
                           QRegularExpressionValidator)
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import builds as b
from . import advice_view, image_health, theme
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
# Equipment and Arcana cards (0.2.487)
EQUIPMENT_HEAD = "Equipment"
ARCANA_HEAD = "Arcana cards"
ARCANA_NOTE = ("Select a card to enter its skill levels from the bundled class/slot pool. Manual bonus levels are additional "
               "contributions; remove overlapping imported bonuses before entering card options.")
DOLL_NOTE = "Select a slot, then choose a catalog item below."
EMPTY_SLOT = "Empty draft slot"
NO_DRAFT_ITEM = "No draft item selected."
ENHANCEMENT = "Enhancement"
CLEAR_SLOT = "Clear draft slot"
SEARCH_CATALOG = "Search catalog"
ITEM_NAME = "Item name"
NO_ITEMS = "No compatible items in the bundled catalog."
ROLLS_HEAD = "Entered random rolls"
NO_ROLL = "No roll entered"
APPLY_OPTIONS = "Apply item options"
DISCARD_OPTIONS = "Discard item edits"
CARD_HEAD = "Card skill levels"
EXTRA_HEAD = "Additional imported contributions"
EXTRA_NOTE = ("These aggregate or custom components are preserved. Remove overlapping contributions before adding "
              "individual items.")
REMOVE_CONTRIBUTION = "Remove contribution"
SOURCE_HEAD = "Recorded source equipment (read-only)"
RECORDED_SLOT = "Recorded slot"
PENDING_ROLLS = "Apply or discard pending roll edits first."
PENDING_SEARCH = "Apply or discard pending roll edits before searching."
ITEM_APPLIED = "Draft item applied. Save or evaluate to update results."
EDITS_DISCARDED = "Unapplied item edits discarded."
NEED_VALUE = "Enter a value for every selected roll."
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


def matching(count: int) -> str:
    """How many items match the search (``p.small.muted``)."""
    return f"{count} matching items" + (" · showing first 80; narrow the search" if count > b.SHOWN_ITEMS else "")


def rolls_note(count) -> str:
    return (f"Up to {js_string(count)} distinct lines from the bundled source pool. Blank lines add nothing. These ranges do "
            "not verify current-build legality or ownership. Effects without a damage coefficient are retained but not "
            "scored.")


def roll_option(o: dict) -> str:
    """A roll's line in its list: its stat and range, and whether the model scores it."""
    unit = o.get("unit")
    return f"{js_string(o.get('stat'))} ({js_string(o.get('range'))})" + ("" if b.truthy(unit) and len(unit) else " · unmodeled")


def cards_note(total, most) -> str:
    return (f"{js_string(total)} total options at this grade/enhancement, up to {js_string(most)} per skill according to the "
            "bundled source. Ownership and current-build applicability remain unverified. Card levels add to separately "
            "entered manual bonuses.")


def source_line(c: dict) -> str:
    """A recorded item's line (``+enchant · grade``)."""
    enchant = c.get("enchantLevel")
    return f"+{'0' if enchant is None else js_string(enchant)} · {js_string(b._or(c.get('grade'), ''))}"


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


class IconBox(QFrame):
    """An item's square (``.icon``): its picture, or the gold ◇ of an empty slot (``.asset-placeholder``)."""

    def __init__(self, picture: QWidget | None, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("bwIcon")
        self.setFixedSize(size, size)
        line = QHBoxLayout(self)
        line.setContentsMargins(1, 1, 1, 1)
        if picture is None:
            picture = _label("◇", "bwPlaceholder", wrap=False)
            picture.setAlignment(Qt.AlignCenter)
        line.addWidget(picture)


class Elided(QLabel):
    """A line of words cut with "…" where it is too long for its room (``white-space: nowrap; text-overflow:
    ellipsis``)."""

    def __init__(self, text: str, name: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(10)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect()
        painter.drawText(rect, int(Qt.AlignLeft | Qt.AlignVCenter),
                         self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width()))
        painter.end()


class Tile(QPushButton):
    """A slot of the doll or an arcana card (``.dslot``): its item's square, the slot and the item's name; its left edge
    in the item's grade's colour; the slot chosen lit."""

    def __init__(self, slot: str, component, picture: QWidget | None, chosen: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.slot = slot
        self.setObjectName("dslot")
        self.setProperty("grade", js_string(b._or(b.get(component, "grade"), "")))
        self.setCheckable(True)
        self.setChecked(chosen)
        self.setMinimumHeight(46)
        self.name = js_string(b._or(b.get(component, "item"), EMPTY_SLOT))
        self.setAccessibleName(f"{slot}: {self.name}")
        line = QHBoxLayout(self)
        line.setContentsMargins(8, 5, 8, 5)
        line.setSpacing(8)
        line.addWidget(IconBox(picture, 34))
        words, column = _plain(spacing=0)
        column.addWidget(Elided(slot.upper(), "dsl"))
        column.addWidget(Elided(self.name, "bwGname"))
        line.addWidget(words, 1)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def sizeHint(self):
        return self.layout().sizeHint()


class Centre(QFrame):
    """The doll's middle (``.dcenter``): the class and the draft's name over the inset, a gold light above its middle."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("bwCentre")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        painter.fillPath(outline, theme.qcolor("inset"))
        light = QRadialGradient(self.width() * 0.5, self.height() * 0.35, max(self.width(), self.height()) * 0.6)
        light.setColorAt(0, QColor(232, 207, 142, 36))
        light.setColorAt(1, QColor(232, 207, 142, 0))
        painter.fillPath(outline, light)
        painter.setPen(QPen(QColor(theme.COLORS["line"]), 1))
        painter.drawPath(outline)
        painter.end()


class Capped(QScrollArea):
    """Its content as tall as it is up to ``most`` pixels, scrolled within beyond (``max-height; overflow: auto``)."""

    def __init__(self, content: QWidget, most: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.content, self.most = content, most
        self.setObjectName("bwPicker")
        holder, column = _plain(spacing=0)
        column.addWidget(content)
        column.addStretch(1)                              # what is left below the items, not stretched into them
        self.setWidget(holder)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = self.viewport().width()
        tall = self.content.heightForWidth(width) if self.content.hasHeightForWidth() else -1
        tall = tall if tall > 0 else self.content.sizeHint().height()
        self.setFixedHeight(min(self.most, tall) + 2 * self.frameWidth())


class ItemChoice(QPushButton):
    """An item to put in the slot (``.bw-item-choice``): its picture, its name, its grade and level."""

    def __init__(self, item: dict, picture: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.slug = item.get("slug")
        self.setObjectName("bwChoice")
        name = js_string(item.get("name"))
        line_words = f"{js_string(item.get('grade'))} · Lv {js_string(item.get('required_level'))}"
        self.setAccessibleName(f"{name} {line_words}")
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 10, 10, 10)
        line.setSpacing(10)
        line.addWidget(picture)
        words, column = _plain(spacing=4)
        column.addWidget(_label(name, "bwName"))
        column.addWidget(_label(line_words, "bwLine"))
        line.addWidget(words, 1)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)   # its column's width, its words wrapped in it

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


def stylesheet() -> str:
    c = theme.COLORS
    return combat_stylesheet() + str(advice_view.STYLE) + f"""
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
        QFrame#bwIcon {{ border: 1px solid {c['line2']}; border-radius: 5px; background: {c['icon_bg']}; }}
        QLabel#bwPlaceholder {{ color: {c['gold']}; font-size: 16px; background: transparent; }}
        QLabel#bwGname {{ color: {c['text']}; }}
        QFrame#bwCentre QLabel {{ background: transparent; }}
        QLabel#bwCls {{ color: {c['gold']}; font-size: 22px; font-weight: 700; letter-spacing: 1px; }}
        QPushButton#bwChoice {{ background: {theme.css('panel')}; color: {c['text']}; border: 1px solid {c['line']};
            border-radius: 5px; text-align: left; padding: 0px; }}
        QPushButton#bwChoice:hover {{ border-color: {c['gold']}; }}
        QPushButton#bwChoice QLabel {{ background: transparent; }}
        QFrame#bwRolls {{ border: 1px solid {c['line']}; border-radius: 5px; background: transparent; }}
        QFrame#bwRolls QLabel, QFrame#bwRolls QWidget#plain {{ background: transparent; }}
        QLabel#bwH4 {{ font-weight: 700; }}
        QFrame#bwDinfo {{ background: transparent; border: none; border-top: 1px dashed {c['line']}; }}
        QFrame#bwDinfo QWidget#plain {{ background: transparent; }}
        QScrollArea#bwPicker {{ background: transparent; border: none; }}
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
        self.evaluation = None
        self.gear_slot = ""                       # the slot chosen on Equipment or Arcana cards (``gearSlot``)
        self.gear_search = ""                     # its catalog search (``gearSearch``)

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
        if self.tab in ("equipment", "arcana"):
            self.draw_components(self.tab)
            return
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

    # ---------------------------------------------------------------- equipment and arcana cards (``components``)
    def _component_changed(self) -> None:
        """``changed``: the draft edited, its evaluation and advanced inputs let go."""
        self.input_buffer = None
        self.evaluation = None
        self._changed()

    def draw_components(self, kind: str) -> None:
        """Equipment's doll or the arcana cards, the slot chosen's items, the draft's other contributions and the
        source's recorded equipment."""
        if self.body is None:
            return
        _clear(self.body)
        catalog, draft = self.catalog or {}, self.draft
        components = draft["loadout"]["components"]
        selected = [c for c in components if b.component_kind(c) == kind]
        slots = b.slots_for(catalog, kind)
        if self.gear_slot not in slots:
            self.gear_slot = slots[0] if slots else ""
        data = b.get(b.get(self.reference, "snapshot"), "data")
        recorded = b.get(b.get(data, "equipment"), "equipmentList")
        source_items = [c for c in (recorded if isinstance(recorded, list) else []) if isinstance(c, dict)
                        and bool(re.match("arcana", js_string(b._or(c.get("slotPosName"), "")), re.I)) == (kind == "arcana")]
        self.body.addWidget(_head(ARCANA_HEAD if kind == "arcana" else EQUIPMENT_HEAD))
        item_note = js_string(b._or(catalog.get("item_note"), b.NO_ITEM_RULES))
        self.body.addWidget(_label(item_note, "small"))
        self.tiles: dict[str, Tile] = {}
        words = self.component_words = {"head": ARCANA_HEAD if kind == "arcana" else EQUIPMENT_HEAD, "item_note": item_note}

        def tile(slot: str) -> Tile:
            c = next((c for c in selected if b.same(b.get(c, "slot", b._MISSING), slot)), None)
            picture = self._picture(icon_url(c), 32) if c is not None else None
            button = Tile(slot, c, picture, slot == self.gear_slot)
            button.clicked.connect(lambda _checked=False, slot=slot: self._gear_slot_chosen(kind, slot))
            self.tiles[slot] = button
            return button
        if kind == "arcana":
            self.body.addWidget(AutoGrid([tile(slot) for slot in slots], 180, 10))
            self.body.addWidget(_label(ARCANA_NOTE, "small"))
        else:
            doll, grid = _plain(QGridLayout, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(5)
            left, right = slots[:10], slots[10:]
            for index, slot in enumerate(left):
                grid.addWidget(tile(slot), index, 0)
            for index, slot in enumerate(right):
                grid.addWidget(tile(slot), index, 2)
            middle = Centre()
            middle.setFixedWidth(240)
            column = QVBoxLayout(middle)
            column.setContentsMargins(14, 14, 14, 14)
            column.setSpacing(8)
            column.addStretch(1)
            centre = ((js_string(draft["class"]).upper(), "bwCls"), (js_string(draft["name"]), ""), (DOLL_NOTE, "small"))
            for text, name in centre:
                label = _label(text, name)
                label.setAlignment(Qt.AlignHCenter)
                column.addWidget(label)
            words["centre"] = [text for text, _name in centre]
            column.addStretch(1)
            grid.addWidget(middle, 0, 1, max(1, len(left), len(right)), 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(2, 1)
            self.body.addWidget(doll)
        picker = QFrame()
        picker.setObjectName("bwDinfo")                      # ``.dinfo``: under a dashed line
        holder = QVBoxLayout(picker)
        holder.setContentsMargins(0, 10, 0, 0)
        holder.setSpacing(10)
        self.picker_box = holder
        self.body.addWidget(picker)
        self.draw_picker(kind)
        extra = [c for c in selected if b.get(c, "slot", b._MISSING) not in slots]
        self.extra_buttons: list[QPushButton] = []
        if extra:
            fold = Fold(EXTRA_HEAD, opened=True)
            fold.add(_label(EXTRA_NOTE, "small"))
            cards = []
            for c in extra:
                index = next(i for i, x in enumerate(components) if x is c)
                remove = _button(REMOVE_CONTRIBUTION, lambda index=index: self._remove_component(kind, index))
                self.extra_buttons.append(remove)
                cards.append(self._card(c, js_string(b.get(c, "slot")), js_string(b.get(c, "item")), None, remove))
                words.setdefault("extra", []).append([js_string(b.get(c, "slot")), js_string(b.get(c, "item"))])
            fold.add(AutoGrid(cards, 240, 10))
            self.body.addWidget(fold)
        if source_items:
            fold = Fold(SOURCE_HEAD)
            rows = [[js_string(b._or(c.get("slotPosName"), RECORDED_SLOT)),
                     js_string(b._or(c.get("name"), b._or(c.get("itemName"), c.get("id")))), source_line(c)] for c in source_items]
            words["source"] = rows
            cards = [self._card(c, *row) for c, row in zip(source_items, rows)]
            fold.add(AutoGrid(cards, 240, 10))
            self.body.addWidget(fold)
        self.body.addStretch(1)

    def _card(self, c: dict, small: str, strong: str, line: str | None, button: QPushButton | None = None) -> QFrame:
        """A card (``.cr-profile-card``): its picture, then its slot, name, line or button; its edge its grade's."""
        from .combat_review_page import GRADE_EDGES
        frame = QFrame()
        frame.setObjectName("bwCard")
        edge = GRADE_EDGES.get(js_string(b._or(c.get("grade"), "")), theme.COLORS["line"])
        frame.setStyleSheet(f"QFrame#bwCard {{ border-color: {edge}; }}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        row.addWidget(self._picture(icon_url(c), 48))
        words, column = _plain(spacing=1)
        if small is not None:
            column.addWidget(_label(small, "bwKind"))
        column.addWidget(_label(strong, "bwName"))
        if line is not None:
            column.addWidget(_label(line, "bwLine"))
        if button is not None:
            column.addWidget(button, 0, Qt.AlignLeft)
        row.addWidget(words, 1)
        return frame

    def draw_picker(self, kind: str) -> None:
        """The slot chosen (``gearPicker``): its draft item with its enhancement, rolls and card levels, then the
        catalog's items for it."""
        _clear(self.picker_box)
        catalog, draft = self.catalog or {}, self.draft
        chosen = b.chosen_in(draft, self.gear_slot)
        item = b.catalog_item(catalog, draft, self.gear_slot, chosen)
        self.roll_lines: list[tuple[QComboBox, NumberField, list]] = []
        self.card_selects: dict[str, QComboBox] = {}
        self.enchant_box: QComboBox | None = None
        self.clear_button: QPushButton | None = None
        self.picker_box.addWidget(_label(self.gear_slot, "bwH4"))
        words = self.picker_words = {"slot": self.gear_slot}
        if chosen is not None:
            self.picker_box.addWidget(self._card(chosen, None, js_string(b.get(chosen, "item")), b.stats_line(chosen)))
            words["chosen"] = [js_string(b.get(chosen, "item")), b.stats_line(chosen), js_string(b._or(b.get(chosen, "grade"), ""))]
            parts = []
            if item is not None:
                box = self.enchant_box = QComboBox()
                box.setAccessibleName(ENHANCEMENT)
                for level in range(len(item.get("levels") or [])):
                    box.addItem(f"+{level}", level)
                at = box.findData(chosen.get("enchant")) if b.integer(chosen.get("enchant"), 0, 10 ** 6) else -1
                box.setCurrentIndex(max(0, at))
                box.shown = box.currentIndex()               # the value it shows, as a select's ``change`` compares
                box.activated.connect(lambda index, kind=kind, item=item: self._enchant(kind, item, index))
                parts.append(_field(ENHANCEMENT, box))
                if kind == "arcana":
                    words["enchant_note"] = b.card_note(catalog, item, chosen.get("enchant"))
                    parts.append(_label(words["enchant_note"], "small"))
            self.clear_button = _button(CLEAR_SLOT, lambda: self._clear_slot(kind))
            parts.append(self.clear_button)
            self.picker_box.addWidget(_row(*parts))
        else:
            self.picker_box.addWidget(_label(NO_DRAFT_ITEM))
            words["chosen"] = NO_DRAFT_ITEM
        if item is not None and b.truthy(item.get("roll_count")):
            self.picker_box.addWidget(self._rolls_panel(kind, item, chosen))
        pool = b.get(b.get(catalog.get("arcana_pools"), draft["class"]), self.gear_slot)
        base = b.get(catalog.get("arcana_base_rolls"), item.get("grade")) if item is not None else None
        if kind == "arcana" and item is not None and b.truthy(pool) and base is not None:
            self.picker_box.addWidget(self._cards_panel(kind, item, chosen, pool, base))
        search = self.gear_search_edit = QLineEdit(self.gear_search)
        search.setPlaceholderText(ITEM_NAME)
        search.setAccessibleName(SEARCH_CATALOG)
        search.setMinimumWidth(220)
        search.textEdited.connect(lambda text, kind=kind: self._gear_search_changed(kind, text))
        self.picker_box.addWidget(_row(_field(SEARCH_CATALOG, search)))
        holder, self.items_box = _plain(spacing=8)
        self.picker_box.addWidget(holder)
        self.draw_items(kind)

    def draw_items(self, kind: str) -> None:
        """The catalog's items for the slot, the first 80, with how many match."""
        _clear(self.items_box)
        shown = b.available(self.catalog or {}, self.draft, self.gear_slot, self.gear_search)
        self.items_label = _label(matching(len(shown)), "small")
        self.picker_words["count"] = matching(len(shown))
        self.picker_words["items"] = [[js_string(c.get("slug")), js_string(c.get("name")),
                                       f"{js_string(c.get('grade'))} · Lv {js_string(c.get('required_level'))}", js_string(c.get("grade"))]
                                      for c in shown[:b.SHOWN_ITEMS]]
        self.items_box.addWidget(self.items_label)
        self.item_buttons: dict[str, ItemChoice] = {}
        if not shown:
            self.items_box.addWidget(_label(NO_ITEMS))
            return
        choices = []
        for c in shown[:b.SHOWN_ITEMS]:
            choice = ItemChoice(c, self._picture(icon_url(c), 48))
            choice.clicked.connect(lambda _checked=False, slug=c.get("slug"), kind=kind: self._pick_item(kind, slug))
            self.item_buttons.setdefault(js_string(c.get("slug")), choice)
            choices.append(choice)
        self.items_box.addWidget(Capped(AutoGrid(choices, 210, 8), 480))

    def _rolls_panel(self, kind: str, item: dict, chosen: dict) -> QFrame:
        """Entered random rolls (``.bw-rolls``): a line for each roll the item has, from its source pool."""
        frame, column = self._panel(ROLLS_HEAD, rolls_note(item.get("roll_count")))
        options = item.get("roll_options") or []
        given = chosen.get("rolls") if isinstance(chosen.get("rolls"), list) else []
        for i in range(int(js_number(item.get("roll_count")))):
            line = given[i] if i < len(given) and isinstance(given[i], dict) else None
            box = QComboBox()
            box.setAccessibleName(f"Line {i + 1}")
            box.addItem(NO_ROLL, "")
            for o in options:
                box.addItem(roll_option(o), o.get("stat"))
            at = next((n + 1 for n, o in enumerate(options) if line is not None and b.same(o.get("stat", b._MISSING),
                                                                                             line.get("stat", b._MISSING))), 0)
            box.setCurrentIndex(at)
            option = options[at - 1] if at else None
            value = line.get("value") if line is not None else None
            field = NumberField(value, 100)
            field.setAccessibleName(f"Value {i + 1}")
            field.setEnabled(option is not None)
            box.activated.connect(lambda index, box=box, field=field, options=options: self._roll_chosen(box, field, options))
            field.textEdited.connect(lambda _text: self._buffer())
            self.roll_lines.append((box, field, options))
            column.addWidget(_row(_field(f"Line {i + 1}", box), _field("Value", field)))
        self.option_buttons = (_button(APPLY_OPTIONS, lambda: self._apply_edits(kind)),
                               _button(DISCARD_OPTIONS, lambda: self._discard_edits(kind)))
        column.addWidget(_row(*self.option_buttons))
        return frame

    def _cards_panel(self, kind: str, item: dict, chosen: dict, pool: dict, base) -> QFrame:
        """Card skill levels (``.bw-rolls``): each skill of the class's pool for the card, +0 to its most."""
        frame, column = self._panel(CARD_HEAD, cards_note(base + chosen.get("enchant", 0), pool.get("max_level")))
        cards = []
        levels = chosen.get("arcana_skills") if isinstance(chosen.get("arcana_skills"), dict) else {}
        for sk in pool.get("skills") or []:
            key = js_string(sk.get("id"))
            box = QComboBox()
            box.setAccessibleName(js_string(sk.get("name")))
            for n in range(int(pool.get("max_level") or 0) + 1):
                box.addItem(f"+{n}", n)
            at = levels.get(key)
            box.setCurrentIndex(box.findData(at) if b.integer(at, 0, 10 ** 6) and box.findData(at) >= 0 else 0)
            box.activated.connect(lambda _index: self._buffer())
            self.card_selects[key] = box
            self.picker_words.setdefault("card_names", {})[key] = js_string(sk.get("name"))
            card = QFrame()
            card.setObjectName("bwCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 12, 12, 12)
            row.setSpacing(12)
            row.addWidget(self._picture(icon_url(sk), 48))
            words, lines = _plain(spacing=4)
            lines.addWidget(_label(js_string(sk.get("name"))))
            lines.addWidget(box, 0, Qt.AlignLeft)
            row.addWidget(words, 1)
            cards.append(card)
        column.addWidget(AutoGrid(cards, 240, 10))
        self.option_buttons = (_button(APPLY_OPTIONS, lambda: self._apply_edits(kind)),
                               _button(DISCARD_OPTIONS, lambda: self._discard_edits(kind)))
        column.addWidget(_row(*self.option_buttons))
        return frame

    def _panel(self, title: str, note: str) -> tuple[QFrame, QVBoxLayout]:
        self.picker_words.setdefault("panels", []).append([title, note])
        frame = QFrame()
        frame.setObjectName("bwRolls")
        column = QVBoxLayout(frame)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(8)
        column.addWidget(_label(title, "bwH4"))
        column.addWidget(_label(note, "small"))
        return frame, column

    def _buffer(self) -> None:
        """An item option edited, not applied yet (``componentBuffer``)."""
        self.component_buffer = True
        self.dirty = True

    def _roll_chosen(self, box: QComboBox, field: "NumberField", options: list) -> None:
        self._buffer()
        stat = box.currentData()
        option = next((o for o in options if b.same(o.get("stat", b._MISSING), stat)), None) if stat else None
        field.setEnabled(option is not None)
        field.setText(js_string(option.get("min")) if option is not None else "")

    def _gear_slot_chosen(self, kind: str, slot: str) -> None:
        if self.component_buffer:
            self.message(PENDING_ROLLS)
            self.tiles[slot].setChecked(slot == self.gear_slot)
            return
        self.gear_slot, self.gear_search = slot, ""
        self.draw_components(kind)

    def _gear_search_changed(self, kind: str, text: str) -> None:
        if self.component_buffer:
            self.gear_search_edit.setText(self.gear_search)
            self.message(PENDING_SEARCH)
            return
        self.gear_search = text
        self.draw_items(kind)

    def _pick_item(self, kind: str, slug) -> None:
        if self.component_buffer:
            self.message(PENDING_ROLLS)
            return
        item = next((c for c in b.available(self.catalog or {}, self.draft, self.gear_slot, self.gear_search)
                     if b.same(c.get("slug", b._MISSING), slug)), None)
        if item is not None:
            self._apply(kind, item, 0)

    def _enchant(self, kind: str, item: dict, index: int) -> None:
        box = self.enchant_box
        if index == box.shown:
            return
        chosen = b.chosen_in(self.draft, self.gear_slot)
        if self.component_buffer:
            box.setCurrentIndex(box.shown)
            self.message(PENDING_ROLLS)
            return
        box.shown = index
        self._apply(kind, item, box.itemData(index), b._or(chosen.get("rolls"), []), b._or(chosen.get("arcana_skills"), {}))

    def _apply_edits(self, kind: str) -> None:
        """Apply item options (``applyEdits``): the rolls and card levels entered, at the item's enhancement."""
        chosen = b.chosen_in(self.draft, self.gear_slot)
        item = b.catalog_item(self.catalog or {}, self.draft, self.gear_slot, chosen)
        rolls, values = [], {}
        for box, field, _options in self.roll_lines:
            if not box.currentData():
                continue
            if field.value() == "":
                self.message(NEED_VALUE)
                return
            rolls.append({"stat": box.currentData(), "value": js_number(field.value())})
        for key, box in self.card_selects.items():
            if box.currentData():
                values[key] = box.currentData()
        self._apply(kind, item, chosen.get("enchant"), rolls if self.roll_lines else b._or(chosen.get("rolls"), []),
                    values if self.card_selects else b._or(chosen.get("arcana_skills"), {}))

    def _apply(self, kind: str, item: dict, level, rolls=None, skills=None) -> None:
        try:
            components = b.with_item(self.catalog or {}, self.draft, self.gear_slot, item, level, rolls, skills)
        except b.BuildError as problem:
            self.message(str(problem))
            return
        self.draft["loadout"]["components"] = components
        self.component_buffer = None
        self._component_changed()
        self.draw_components(kind)
        self.message(ITEM_APPLIED)

    def _discard_edits(self, kind: str) -> None:
        self.component_buffer = None
        self.draw_picker(kind)
        self.message(EDITS_DISCARDED)

    def _clear_slot(self, kind: str) -> None:
        self.component_buffer = None
        self.draft["loadout"]["components"] = b.without_slot(self.draft, self.gear_slot)
        self._component_changed()
        self.draw_components(kind)

    def _remove_component(self, kind: str, index: int) -> None:
        del self.draft["loadout"]["components"][index]
        self._component_changed()
        self.draw_components(kind)

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
