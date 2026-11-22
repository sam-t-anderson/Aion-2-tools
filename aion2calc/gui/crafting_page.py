"""The native Crafting page (0.2.432): the Crafting workshop as the web page shows it (static/crafting.js,
``A2Crafting``), over the app's dated, source-attributed recipe snapshot (``/static/crafting-catalog.json``) and its
optional community success rates (``/static/crafting-success.json``).

- **Recipe source and missing rules:** the catalog's note, its item stats' note, and its counts, date, fingerprint
  and source.
- **Recipes:** a search by item name or recipe id, the profession, faction, rarity and item type, and your crafting
  mastery (tier and level) with *Only what I can craft*; the first 80 matching recipes, each with its rarity,
  profession, faction and proficiency, and whether you can craft it.
- **A recipe:** where you stand against it, its community-measured success rate, the planned completed crafts and
  the expansion of intermediates; the normal and combo products with their item stats (an enhancement preview, the
  random rolls); the combo checks with an assumed rate and an illustrative scenario; the material plan with what you
  own, the fees and its warnings, and its export.

The arithmetic is ``crafting.py``'s, checked against the web page's own functions. The items' pictures are the ones
the app bundles (``static/game-assets.json``), so the page needs nothing but the app; the source's links open in the
browser. What you enter lasts while the app runs.
"""
from __future__ import annotations

import html
import json
import os
import webbrowser

from PySide6.QtCore import QStandardPaths, QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import crafting as c
from . import pictures, theme
from .api import AppApi, Requests
from .chrome import FlowLayout
from .database_page import Icons, Window
from .gathering_page import GatheringPage, table
from .timers_page import Fold

SUBTITLE = "Conditional recipe planning"
NOTE_TITLE = "Recipe source and missing rules"
LOADING = "Loading crafting catalog…"
UNAVAILABLE = "Crafting catalog unavailable"
UNSUPPORTED = "Unsupported crafting catalog"
NO_RECIPES = "No matching recipes. Widen the tier, type or profession filters."
MASTERY = "Your crafting mastery (optional — to see what you can make)"
EXPAND = "Expand source-linked intermediates without combo outcomes"
NO_COMBO = "No combo output in this recipe record."
COMBO_CARD = "Combo quantity and normal-output replacement rules unavailable"
ROLLS_NOTE = "Source ranges only; no roll is selected or included in the preview."
NO_STATS = "Item stats unavailable in this source record."
NO_BASE = "No base item stats listed in this record."
#: A card's border by its item's rarity (combat-review.css and workshop.css ``.cr-profile-card[data-grade]``).
GRADE_BORDERS = {"Rare": "#4aa3e6", "Epic": "#a46cf0", "Unique": "#f0bf4a", "Heroic": "#e85555"}
COLUMNS_AT = 1050                            # the detail's two columns from this width (``@container (min-width)``)
CARD_MIN, CARD_GAP = 240, 10                 # the material cards: ``repeat(auto-fit, minmax(240px, 1fr))``


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _link(href: str, words: str) -> str:
    return f"<a href='{html.escape(href, quote=True)}' style='color: {theme.COLORS['accent']};'>{html.escape(words)}</a>"


def _plain(name: str = "") -> QWidget:
    box = QWidget()
    box.setObjectName(name or "plain")
    return box


def _flow(gap=(12, 8)) -> tuple[QWidget, FlowLayout]:
    """A line of fields that goes on to the next where there is no room (``.row``)."""
    box = _plain()
    return box, FlowLayout(box, align=Qt.AlignLeft, gap=gap)


def _field(words: str, widget: QWidget) -> QWidget:
    """A field with its name before it (``<label>Words <input></label>``)."""
    box = _plain()
    line = QHBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    line.addWidget(_label(words, wrap=False))
    line.addWidget(widget)
    return box


def _entry(text: str, width: int = 120, placeholder: str = "") -> QLineEdit:
    entry = QLineEdit(text)
    entry.setFixedWidth(width)
    if placeholder:
        entry.setPlaceholderText(placeholder)
    return entry


class Picture(QLabel):
    """An item's picture in its square, kept within it (``object-fit: contain``); ◇ where the source has none."""

    def __init__(self, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.side = size
        self.path = ""
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("picture")

    def show_none(self) -> None:
        self.path = ""
        self.setPixmap(QPixmap())
        self.setText("◇")

    def show_pixmap(self, pixmap: QPixmap) -> None:
        self.setText("")
        self.setPixmap(pixmap.scaled(QSize(self.side, self.side), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class RecipeButton(QPushButton):
    """A listed recipe (``.craft-recipe``): its product's picture and name, and its line; the chosen one in gold."""

    def __init__(self, choose, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("craftRecipe")
        self.setCursor(Qt.PointingHandCursor)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)   # a button's own would keep it wide
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.recipe_id = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.picture = Picture(36)
        layout.addWidget(self.picture, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(4)
        self.name = _label("", "recipeName")
        self.line = _label("", "muted")
        words.addWidget(self.name)
        words.addWidget(self.line)
        layout.addLayout(words, 1)
        self.clicked.connect(lambda: choose(self.recipe_id))

    def set_recipe(self, recipe_id: str, name: str, line: str, chosen: bool) -> None:
        self.recipe_id = recipe_id
        self.name.setText(name)
        self.line.setText(line)
        self.setAccessibleName(f"{name}, {line}")
        self.set_chosen(chosen)

    def set_chosen(self, chosen: bool) -> None:
        name = "craftRecipeOn" if chosen else "craftRecipe"
        if self.objectName() != name:
            self.setObjectName(name)
            self.style().unpolish(self)
            self.style().polish(self)

    def sizeHint(self) -> QSize:
        """As wide as its column lets it be, as tall as its words then are (``width: 100%``)."""
        width = min(self.layout().sizeHint().width(), 330)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return self.layout().totalMinimumSize()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.layout().totalHeightForWidth(width)


class Columns(QWidget):
    """Parts side by side from ``at`` px wide, one under the other below (``.craft-detail-columns``)."""

    def __init__(self, parts: list[QWidget], at: int = COLUMNS_AT, gap: int = 18, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.parts, self.at, self.side = parts, at, None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.place(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width())

    def place(self, width: int) -> None:
        side = width >= self.at
        if side == self.side:
            return
        self.side = side
        for part in self.parts:
            self.grid.removeWidget(part)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for index, part in enumerate(self.parts):
            self.grid.addWidget(part, 0 if side else index, index if side else 0, Qt.AlignTop)
        for column in range(len(self.parts) if side else 1):
            self.grid.setColumnStretch(column, 1)


class Cards(QWidget):
    """Cards in as many columns of at least 240 px as fit, sharing the width (``.cr-profile-grid``)."""

    def __init__(self, cards: list[QWidget], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.cards, self.columns = cards, 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setSpacing(CARD_GAP)
        self.place(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width())

    def place(self, width: int) -> None:
        columns = max(1, min(len(self.cards) or 1, (width + CARD_GAP) // (CARD_MIN + CARD_GAP)))
        if columns == self.columns:
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns, Qt.AlignTop)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class CraftingPage(QWidget):
    """Game → Crafting. It reads the recipe snapshot when it is first shown and keeps what you enter while the app
    runs."""

    def __init__(self, api: AppApi | None, open_link=webbrowser.open, save_as=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_link = api, open_link
        self.save_as = save_as or self._ask_where
        self.catalog: dict | None = None
        self.success = None
        self.assets: dict[str, str] = {}                 # a picture's address: its bundled file
        self.state = "unread"                             # "reading", "read" or "failed"
        self.selected = self.search = self.profession = self.faction = self.rarity = self.kind = ""
        self.my_tier = self.my_level = ""
        self.craftable_only = self.expand = False
        self.count, self.seed, self.effective, self.result = 1, 1, None, ""
        self.enhancements: dict = {}
        self.stock: dict = {}
        self.pictures: dict[str, QPixmap] = {}
        self.detail_pictures: list[tuple[Picture, str]] = []
        self.buttons: list[RecipeButton] = []
        self.planned: dict | None = None
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.icons = Icons(api, self)
        self.icons.loaded.connect(self._picture)
        self.later = QTimer(self)
        self.later.setSingleShot(True)
        self.later.timeout.connect(self.draw_detail)
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
        self.window_ = Window("Crafting workshop", SUBTITLE)
        layout.addWidget(self.window_)
        layout.addStretch(1)
        self.status = _label(LOADING)
        self.window_.body.addWidget(self.status)
        self.workspace: QWidget | None = None

    @staticmethod
    def _stylesheet() -> str:
        cl = theme.COLORS
        borders = "".join(f"QFrame#card{grade} {{ border-color: {colour}; }}" for grade, colour in GRADE_BORDERS.items())
        return GatheringPage._stylesheet() + f"""
        QWidget#plain, QWidget#detail {{ background: transparent; }}
        QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
                       color: {theme.COLORS['note_fg']}; padding: 9px 12px; }}
        QFrame#note QLabel, QFrame#note QToolButton, QFrame#note QWidget#foldBody, QFrame#note QWidget#plain {{
            background: transparent; border: none; padding: 0; color: {theme.COLORS['note_fg']}; }}
        QFrame#note QToolButton#fold {{ color: {theme.COLORS['note_fg']}; font-weight: 600; }}
        QWidget#foldBody {{ background: transparent; }}
        QToolButton#fold {{ border: none; padding: 2px 0; color: {cl['text']}; }}
        QPushButton#craftRecipe, QPushButton#craftRecipeOn {{ text-align: left; background: {cl['panel']};
            border: 1px solid {cl['line']}; border-radius: 5px; padding: 0; }}
        QPushButton#craftRecipeOn {{ border-color: {cl['gold']}; background: {cl['hover']}; }}
        QPushButton#craftRecipe QLabel, QPushButton#craftRecipeOn QLabel {{ background: transparent; }}
        QLabel#picture {{ color: {cl['muted']}; font-size: 20px; background: transparent; }}
        QLabel#h2 {{ font-size: 19px; font-weight: 700; }}
        QLabel#h3 {{ font-size: 15px; font-weight: 700; }}
        QLabel#h4 {{ font-weight: 700; }}
        QLabel#strong {{ font-weight: 700; }}
        QFrame#card, {", ".join(f"QFrame#card{grade}" for grade in GRADE_BORDERS)} {{ background: {cl['panel']};
            border: 1px solid {cl['line']}; border-radius: 6px; }}
        {borders}
        QFrame#card QLabel, {", ".join(f"QFrame#card{grade} QLabel" for grade in GRADE_BORDERS)} {{ background: transparent; }}
        QFrame#stats {{ background: transparent; border: 1px solid {cl['line']}; border-radius: 5px; }}
        QFrame#stats QLabel, QFrame#stats QWidget#plain, QFrame#stats QWidget#foldBody {{ background: transparent; }}
        QLabel#notice {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
                         color: {theme.COLORS['note_fg']}; padding: 9px 12px; }}
        """

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.state == "unread":
            self.load()

    def load(self) -> None:
        """The recipe snapshot, its success rates and the bundled pictures' map, read once."""
        if self.requests is None:
            return
        self.state = "reading"
        self.requests.get("assets", "/static/game-assets.json")     # first, so the recipes open with their pictures
        self.requests.get("catalog", "/static/crafting-catalog.json")
        self.requests.get("success", "/static/crafting-success.json")

    def _replied(self, name: str, answer) -> None:
        if name == "catalog":
            if not isinstance(answer, dict) or answer.get("version") != 1 or not isinstance(answer.get("recipes"), dict) \
                    or not answer["recipes"]:
                return self._fail(UNSUPPORTED)
            self.catalog = answer
        elif name == "success":
            if isinstance(answer, dict) and answer.get("version") == 1 and answer.get("recipes"):
                self.success = answer
            self._open()
        elif name == "assets":
            files = answer.get("assets") if isinstance(answer, dict) else None
            self.assets = {url: file for url, file in (files or {}).items() if isinstance(url, str) and _bundled(file)}
            self._refresh_pictures()

    def _failed(self, name: str, why: str) -> None:
        if name == "catalog":
            self._fail(UNAVAILABLE)
        elif name == "success":
            self._open()                                  # success rates are optional: "not available" without them

    def _fail(self, why: str) -> None:
        self.state = "failed"
        self.catalog = None
        self.status.setText(f"Could not open crafting workshop: {why}")

    def _open(self) -> None:
        if self.catalog is None or self.state != "reading":
            return
        self.state = "read"
        self.selected = next(iter(self.catalog["recipes"]))
        self.status.hide()
        self._build()
        self.fit_filters()
        self.draw_list()
        self.draw_detail()

    # ------------------------------------------------------------------ the workspace
    def _build(self) -> None:
        catalog = self.catalog
        note = QFrame()
        note.setObjectName("note")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(0, 0, 0, 0)
        fold = Fold(NOTE_TITLE, opened=True)
        fold.add(_label(str(catalog.get("note") or "")))
        fold.add(_label(str(catalog.get("item_details_note") or "Item stat references unavailable.")))
        source = _label(c.source_line(catalog), rich=True)
        source.linkActivated.connect(self.open_link)
        fold.add(source)
        note_layout.addWidget(fold)
        self.window_.body.addWidget(note)

        self.workspace = _plain()
        row = QHBoxLayout(self.workspace)
        row.setContentsMargins(0, 12, 0, 0)
        row.setSpacing(18)
        left = _plain()
        left.setMinimumWidth(230)
        left.setMaximumWidth(330)
        side = QVBoxLayout(left)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        line, flow = _flow()
        self.search_box = _entry("", 170, "Item name or recipe ID")
        self.search_box.setAccessibleName("Search")
        self.search_box.textChanged.connect(self._search)
        flow.addWidget(_field("Search", self.search_box))
        self.profession_box = QComboBox()
        self.profession_box.setAccessibleName("Profession")
        self.profession_box.addItem("All professions", "")
        for name in c.professions(catalog):
            self.profession_box.addItem(name, name)
        self.profession_box.activated.connect(lambda _index: self._choose_profession())
        flow.addWidget(_field("Profession", self.profession_box))
        self.faction_box = QComboBox()
        self.faction_box.setAccessibleName("Faction")
        for words, value in (("Both factions", ""), ("Elyos", "light"), ("Asmodian", "dark")):
            self.faction_box.addItem(words, value)
        self.faction_box.activated.connect(lambda _index: self._filter("faction", self.faction_box))
        flow.addWidget(_field("Faction", self.faction_box))
        side.addWidget(line)
        line, flow = _flow()
        self.rarity_box = QComboBox()
        self.rarity_box.setAccessibleName("Rarity")
        self.rarity_box.activated.connect(lambda _index: self._filter("rarity", self.rarity_box))
        flow.addWidget(_field("Rarity", self.rarity_box))
        self.kind_box = QComboBox()
        self.kind_box.setAccessibleName("Item type")
        self.kind_box.activated.connect(lambda _index: self._filter("kind", self.kind_box))
        flow.addWidget(_field("Item type", self.kind_box))
        side.addWidget(line)
        side.addWidget(_label(MASTERY, "muted"))
        line, flow = _flow()
        self.tier_box = QComboBox()
        self.tier_box.setAccessibleName("Tier")
        self.tier_box.activated.connect(lambda _index: self._choose_tier())
        flow.addWidget(_field("Tier", self.tier_box))
        self.level_box = _entry("", 92, "1–50")
        self.level_box.setAccessibleName("Level")
        self.level_box.textEdited.connect(self._level)
        flow.addWidget(_field("Level", self.level_box))
        self.craftable_box = QCheckBox("Only what I can craft")
        self.craftable_box.clicked.connect(self._craftable)
        flow.addWidget(self.craftable_box)
        side.addWidget(line)
        self.count_label = _label("", "muted")
        side.addWidget(self.count_label)
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFrameShape(QFrame.NoFrame)
        self.list_scroll.setMinimumHeight(340)
        self.list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        listed = _plain()
        self.list_layout = QVBoxLayout(listed)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(8)
        self.no_recipes = _label(NO_RECIPES)
        self.no_recipes.hide()
        self.list_layout.addWidget(self.no_recipes)
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(listed)
        side.addWidget(self.list_scroll, 1)
        row.addWidget(left, 0)
        self.detail_box = _plain("detail")
        self.detail_layout = QVBoxLayout(self.detail_box)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.detail_box, 1)
        self.window_.body.addWidget(self.workspace)

    def _mine(self):
        return c.my_proficiency(self.my_tier, self.my_level)

    def fit_filters(self) -> None:
        """The rarities, item types and tiers the profession makes, and the level's cap (``renderFilters``)."""
        meta = c.profession_meta(self.catalog, self.profession)
        self.rarity, self.kind, self.my_tier, self.my_level = c.fit_filters(meta, self.rarity, self.kind, self.my_tier,
                                                                             self.my_level)
        self._options(self.rarity_box, [("All rarities", "")] + [(g, g) for g in meta["grades"]], self.rarity)
        self._options(self.kind_box, [("All types", "")] + [(c.type_label(k), k) for k in meta["types"]], self.kind)
        self._options(self.tier_box, [("—", "")] + [(t, t) for t in meta["tiers"]], self.my_tier)
        cap = c.level_cap(meta, self.my_tier)
        self.level_box.setPlaceholderText(f"1–{cap}")
        self.level_box.setText(self.my_level)

    @staticmethod
    def _options(box: QComboBox, choices: list[tuple[str, str]], chosen: str) -> None:
        box.blockSignals(True)
        box.clear()
        for words, value in choices:
            box.addItem(words, value)
        box.setCurrentIndex(max(0, box.findData(chosen)))
        box.blockSignals(False)

    # ------------------------------------------------------------------ the filters
    def _search(self, text: str) -> None:
        self.search = text
        self.draw_list()

    def _choose_profession(self) -> None:
        self.profession = self.profession_box.currentData() or ""
        self.fit_filters()
        self.draw_list()
        self.draw_detail()

    def _filter(self, which: str, box: QComboBox) -> None:
        setattr(self, which, box.currentData() or "")
        self.draw_list()

    def _choose_tier(self) -> None:
        self.my_tier = self.tier_box.currentData() or ""
        self.fit_filters()
        self.draw_list()
        self.draw_detail()

    def _level(self, text: str) -> None:
        cap = c.level_cap(c.profession_meta(self.catalog, self.profession), self.my_tier)
        self.my_level = c.level_entry(text, cap, self.my_level)
        if self.level_box.text() != self.my_level:
            self.level_box.setText(self.my_level)
        self.draw_list()
        self.draw_detail()

    def _craftable(self, checked: bool) -> None:
        self.craftable_only = bool(checked)
        self.draw_list()

    # ------------------------------------------------------------------ the list
    def draw_list(self) -> None:
        """The first 80 matching recipes, in buttons kept between draws (``results``)."""
        catalog, mine = self.catalog, self._mine()
        rows = c.matching(catalog, self.search, self.profession, self.faction, self.rarity, self.kind,
                          self.craftable_only, mine)
        shown = rows[:c.SHOWN]
        while len(self.buttons) < len(shown):
            button = RecipeButton(self.choose)
            self.list_layout.insertWidget(len(self.buttons), button)
            self.buttons.append(button)
        for index, button in enumerate(self.buttons):
            if index < len(shown):
                recipe_id, recipe = shown[index]
                button.set_recipe(recipe_id, c.item_name(catalog, recipe.get("output")),
                                  c.recipe_line(catalog, recipe, self.my_level, mine), recipe_id == self.selected)
                self._show_picture(button.picture, c.icon(catalog, recipe.get("output")))
                button.show()
            else:
                button.hide()
        self.no_recipes.setVisible(not shown)
        self.count_label.setText(c.count_line(len(rows)))

    def choose(self, recipe_id: str) -> None:
        """A recipe opened: its combo rate and scenario start afresh."""
        self.selected, self.effective, self.result = recipe_id, None, ""
        for button in self.buttons:
            if button.isVisibleTo(self):
                button.set_chosen(button.recipe_id == recipe_id)
        self.draw_detail()

    # ------------------------------------------------------------------ pictures
    def _show_picture(self, picture: Picture, url: str) -> None:
        """An item's bundled picture: drawn once read, blank while it is asked for, and ◇ where the app bundles none
        (until the bundled pictures' map is read, which draws them again)."""
        file = self.assets.get(url) if url else None
        picture.show_none()
        if not file:
            return
        picture.path = "/static/" + file
        if picture.path in self.pictures:
            picture.show_pixmap(self.pictures[picture.path])
        else:
            picture.setText("")
            self.icons.ask(picture.path)

    def _picture(self, path: str, data: bytes) -> None:
        image = pictures.decoded(data)
        if image.isNull():
            return
        self.pictures[path] = QPixmap.fromImage(image)
        for picture in self._pictures():
            if picture.path == path:
                picture.show_pixmap(self.pictures[path])

    def _pictures(self) -> list[Picture]:
        return [*(button.picture for button in self.buttons), *(picture for picture, _url in self.detail_pictures)]

    def _refresh_pictures(self) -> None:
        """The bundled pictures' map read: the pictures already drawn without it, drawn again."""
        if self.catalog is None or self.state != "read":
            return
        self.draw_list()
        for picture, url in self.detail_pictures:
            self._show_picture(picture, url)

    # ------------------------------------------------------------------ the detail
    def later_detail(self) -> None:
        """The detail drawn anew once the field that changed it has finished with its signal."""
        self.later.start(0)

    def draw_detail(self) -> None:
        """The chosen recipe (``details``)."""
        for index in reversed(range(self.detail_layout.count())):
            child = self.detail_layout.takeAt(index)
            if child.widget() is not None:
                widget = child.widget()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.detail_pictures = []
        catalog = self.catalog
        recipe = (catalog.get("recipes") or {}).get(self.selected) if catalog else None
        if recipe is None:
            self.detail_layout.addWidget(_label("Select a recipe."))
            return
        self.detail_layout.addWidget(self._detail(catalog, recipe))

    def _detail(self, catalog: dict, recipe: dict) -> QWidget:
        box = _plain("detail")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        mine = self._mine()
        chance = self.effective if self.effective is not None else float(recipe.get("combo_chance") or 0)
        try:
            self.planned, error = c.plan(catalog, self.selected, self.count, self.expand, self.stock), ""
        except c.PlanError as problem:
            self.planned, error = None, str(problem)
        layout.addWidget(_label(c.item_name(catalog, recipe.get("output")), "h2"))
        layout.addWidget(_label(c.heading(catalog, self.selected, recipe)))
        tone, words = c.standing(recipe, self.my_tier, self.my_level, mine)
        layout.addWidget(_label(words, "notice" if tone == "note" else "muted" if tone == "muted" else "", rich=True))
        tone, words = c.success_line(catalog, recipe, self.success, mine)
        layout.addWidget(_label(words, "muted" if tone == "muted" else "", rich=True))
        line, flow = _flow()
        crafts = _entry(str(self.count))
        crafts.setAccessibleName("Planned completed crafts")
        crafts.editingFinished.connect(lambda: self._crafts(crafts))
        flow.addWidget(_field("Planned completed crafts", crafts))
        expand = QCheckBox(EXPAND)
        expand.setChecked(self.expand)
        expand.clicked.connect(self._expand)
        flow.addWidget(expand)
        layout.addWidget(line)
        layout.addWidget(_label(c.ASSUMPTIONS, "muted"))
        layout.addWidget(Columns([self._products(catalog, recipe, chance), self._materials(catalog, error)]))
        source = _label(_link(c.SOURCE_RECIPE.format(self.selected), "View source recipe ↗"), rich=True, wrap=False)
        source.linkActivated.connect(self.open_link)
        layout.addWidget(source)
        return box

    def _card(self, catalog: dict, item_id, detail: str) -> QFrame:
        """An item (``.cr-profile-card``): its picture, its name, its line and its source id, edged in its rarity."""
        card = QFrame()
        grade = c.grade_name(catalog, item_id)
        card.setObjectName("card" + grade if grade in GRADE_BORDERS else "card")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)
        picture = Picture(48)
        self._show_picture(picture, c.icon(catalog, item_id))
        self.detail_pictures.append((picture, c.icon(catalog, item_id)))
        row.addWidget(picture, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(_label(c.item_name(catalog, item_id), "strong"))
        words.addWidget(_label(detail, "muted"))
        words.addWidget(_label(f"Source item {item_id}", "muted"))
        row.addLayout(words, 1)
        return card

    def _stats(self, catalog: dict, item_id) -> QWidget:
        """The item's stats with the enhancement preview and its random rolls (``outputStats``)."""
        stats = c.item_stats(catalog, item_id, self.enhancements.get(item_id) or 0)
        if stats is None:
            return _label(NO_STATS, "muted")
        frame = QFrame()
        frame.setObjectName("stats")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(_label(stats["title"], "h4"))
        if stats["variant"]:
            layout.addWidget(_label(f"Source variant {stats['variant']}", "muted"))
        if stats["levels"]:
            choice = QComboBox()
            choice.setAccessibleName("Enhancement preview")
            choice.addItem("Base (+0)", 0)
            for level in stats["levels"]:
                choice.addItem(f"+{level}", level)
            choice.setCurrentIndex(max(0, choice.findData(stats["level"])))
            choice.activated.connect(lambda index, item_id=item_id, choice=choice: self._enhance(item_id, choice.itemData(index)))
            row = _plain()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(_field("Enhancement preview", choice))
            line.addStretch(1)
            layout.addWidget(row)
        if stats["rows"]:
            leveled = bool(stats["level"])
            headers = ["Stat", "Base"] + (["Listed bonus", "Preview total"] if leveled else [])
            rows = [[label, base] + ([bonus, total] if leveled else []) for label, base, bonus, total in stats["rows"]]
            layout.addWidget(table(headers, rows))
        else:
            layout.addWidget(_label(NO_BASE, "muted"))
        if stats["rolls"]:
            rolls = Fold(f"Possible random rolls ({len(stats['rolls'])})")
            rolls.add(_label(ROLLS_NOTE, "muted"))
            rolls.add(table(["Stat", "Range"], [list(row) for row in stats["rolls"]]))
            layout.addWidget(rolls)
        if stats["effect"]:
            layout.addWidget(_label(f"Use effect: {stats['effect']}. Effect coefficients are unavailable.", "muted"))
        note = html.escape(c.STATS_NOTE) + (" " + _link(stats["source"], "Source item record ↗") if stats["source"] else "")
        source = _label(note, "muted", rich=True)
        source.linkActivated.connect(self.open_link)
        layout.addWidget(source)
        return frame

    def _products(self, catalog: dict, recipe: dict, chance: float) -> QWidget:
        """The normal and combo products, then the combo checks (``.craft-products``)."""
        section = _plain()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        output = _plain()
        pair = QGridLayout(output)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setHorizontalSpacing(10)
        normal = QVBoxLayout()
        normal.addWidget(_label("Normal product reference", "h3"))
        normal.addWidget(self._card(catalog, recipe.get("output"), c.output_line(recipe, self.count)))
        normal.addWidget(self._stats(catalog, recipe.get("output")))
        normal.addStretch(1)
        pair.addLayout(normal, 0, 0)
        combo = QVBoxLayout()
        combo.addWidget(_label("Combo product reference", "h3"))
        if recipe.get("combo"):
            combo.addWidget(self._card(catalog, recipe.get("combo"), COMBO_CARD))
            combo.addWidget(self._stats(catalog, recipe.get("combo")))
        else:
            combo.addWidget(_label(NO_COMBO))
        combo.addStretch(1)
        pair.addLayout(combo, 0, 1)
        pair.setColumnStretch(0, 1)
        pair.setColumnStretch(1, 1)
        layout.addWidget(output)
        note = QFrame()
        note.setObjectName("note")
        lines = QVBoxLayout(note)
        lines.setContentsMargins(0, 0, 0, 0)
        lines.setSpacing(8)
        head, used = c.rate_line(recipe, self.effective)
        lines.addWidget(_label(head, "strong"))
        lines.addWidget(_label(used))
        row, flow = _flow()
        rate = _entry(c.chance_text(chance))
        rate.setAccessibleName("Assumed effective combo rate (%)")
        rate.editingFinished.connect(lambda: self._rate(rate, chance))
        flow.addWidget(_field("Assumed effective combo rate (%)", rate))
        reset = QPushButton("Use source rate")
        reset.clicked.connect(self._source_rate)
        flow.addWidget(reset)
        seed = _entry(str(self.seed))
        seed.setAccessibleName("Scenario seed")
        seed.editingFinished.connect(lambda: self._seed(seed))
        flow.addWidget(_field("Scenario seed", seed))
        simulate = QPushButton("Simulate combo checks")
        simulate.clicked.connect(lambda: self._simulate(chance))
        flow.addWidget(simulate)
        lines.addWidget(row)
        lines.addWidget(_label(c.combo_line(self.count, chance)))
        self.simulation = _label(self.result)
        self.simulation.setAccessibleName("Scenario result")
        lines.addWidget(self.simulation)
        layout.addWidget(note)
        return section

    def _materials(self, catalog: dict, error: str) -> QWidget:
        """The material plan (``.craft-materials``)."""
        section = _plain()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_label(c.plan_heading(self.expand), "h3"))
        planned = self.planned
        if planned is None:
            layout.addWidget(_label(error, "notice"))
            return section
        cards = []
        for material in planned["materials"]:
            cell = _plain()
            column = QVBoxLayout(cell)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(4)
            column.addWidget(self._card(catalog, material["id"], c.material_line(material)))
            owned = _entry(str(material["owned"]))
            owned.setAccessibleName(f"Owned {c.item_name(catalog, material['id'])}")
            owned.editingFinished.connect(lambda owned=owned, item_id=material["id"]: self._owned(owned, item_id))
            column.addWidget(_label("Owned base material", "muted"))
            column.addWidget(owned)
            cards.append(cell)
        layout.addWidget(Cards(cards))
        layout.addWidget(_label(c.fees_line(planned)))
        for warning in planned["warnings"]:
            layout.addWidget(_label(warning, "notice"))
        layout.addWidget(_label(c.OWNED_NOTE, "muted"))
        export = QPushButton("Export this material plan")
        export.clicked.connect(self.export)
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(export)
        line.addStretch(1)
        layout.addWidget(row)
        return section

    # ------------------------------------------------------------------ the detail's fields
    @staticmethod
    def _edited(entry: QLineEdit) -> bool:
        """Whether the field was changed since it was drawn (``onchange``): finishing a field left as it was, or
        finishing it twice, changes nothing."""
        edited = entry.isModified()
        entry.setModified(False)
        return edited

    def _crafts(self, entry: QLineEdit) -> None:
        if not self._edited(entry):
            return
        count = c.crafts_entry(entry.text(), self.count)
        if count == self.count:
            entry.setText(str(self.count))
            return
        self.count, self.result = count, ""
        self.later_detail()

    def _expand(self, checked: bool) -> None:
        self.expand = bool(checked)
        self.later_detail()

    def _enhance(self, item_id, level) -> None:
        if level == 0 or level in c.enhancement_levels(self.catalog, item_id):
            self.enhancements[item_id] = level
            self.later_detail()

    def _rate(self, entry: QLineEdit, chance: float) -> None:
        if not self._edited(entry):
            return
        rate = c.chance_entry(entry.text())
        if rate is None:
            entry.setText(c.js_text(chance * 100))           # the web page puts back chance × 100
            return
        self.effective, self.result = rate, ""
        self.later_detail()

    def _source_rate(self) -> None:
        self.effective, self.result = None, ""
        self.later_detail()

    def _seed(self, entry: QLineEdit) -> None:
        if not self._edited(entry):
            return
        seed = c.seed_entry(entry.text(), self.seed)
        entry.setText(str(seed))
        if seed != self.seed:
            self.seed, self.result = seed, ""
            self.simulation.setText("")

    def _simulate(self, chance: float) -> None:
        hits = c.simulate(self.seed, self.count, chance)
        self.result = c.simulation_line(self.seed, hits, self.count)
        self.simulation.setText(self.result)

    def _owned(self, entry: QLineEdit, item_id) -> None:
        if not self._edited(entry):
            return
        owned = c.owned_entry(entry.text(), self.stock.get(item_id) or 0)
        if owned == (self.stock.get(item_id) or 0):
            entry.setText(str(owned))
            return
        self.stock[item_id] = owned
        self.later_detail()

    # ------------------------------------------------------------------ the export
    def export(self) -> None:
        """The material plan saved as the web page exports it (``craft-plan-<recipe>.json``)."""
        if self.planned is None:
            return
        chance = self.effective if self.effective is not None else float(
            self.catalog["recipes"][self.selected].get("combo_chance") or 0)
        document = c.plan_document(self.catalog, self.selected, self.enhancements, self.count, chance, self.seed,
                                   self.expand, self.planned)
        path = self.save_as(f"craft-plan-{self.selected}.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(document, file, indent=2, ensure_ascii=False)
        except OSError as problem:
            self.simulation.setText(f"Could not save the material plan: {problem.strerror or problem}")
            return
        self.simulation.setText(f"Material plan saved to {path}.")

    def _ask_where(self, name: str) -> str:
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, "Export this material plan", os.path.join(folder, name),
                                                  "JSON (*.json)")
        return path

    def closeEvent(self, event) -> None:
        self.icons.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)


def _bundled(file) -> bool:
    return isinstance(file, str) and file.startswith("game-assets/") and ".." not in file and "\\" not in file
