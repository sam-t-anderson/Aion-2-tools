"""The native My Character page (0.2.440): Character → My Character as the web page shows it (pages/character.js).

- **Search** a character by name in a region on the official site, and **Import** one of those found (its job); or one
  of the characters imported before (newest first), fetched again; or, with Settings → My Character at launch, the
  one opened last, from its last snapshot or refreshed (once each time the app runs).
- **The character:** its counts (DPS in each scenario, the points spent of each budget), where its budgets come from,
  its warnings, and the totals to optimize with: what the profile shows spent, or what you type above it (kept for
  that character); the class's highest reported totals for reference; the game version; the damage objective; the
  survival options and trained-skill reserves (0.2.441, ``character_options.py``); and Pet Genus Insight: whether its
  saved lines count, the PvE enemy mix, and the lines themselves in the Genus editor, with the row that reads them from
  the game (0.2.442, ``genus_editor.py`` and ``screen_read.py``).
- **Optimize** a PvE, PvP damage or World PvP build: the job's progress, then its score and gain, the model's note, the
  community preset's word and what changes, and the optimized build in the result windows. A run goes on while you look
  at another character, and is shown on its own character's page.

What the web page keeps in its browser this page keeps in the native interface's settings. Its requests wait as long as
a browser would (a search asks the official site).
"""
from __future__ import annotations

import json
import urllib.parse

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import character as c
from . import result_windows
from . import results as r
from . import theme
from .api import AppApi, Job, Requests
from .character_options import AutoGrid, SkillReserves, SurvivalOptions, style as options_style
from .chrome import FlowLayout
from .database_page import Kpi, Window
from .gathering_page import GatheringPage
from .genus_editor import GenusEditor, style as editor_style
from .pets_page import Toast
from .planner import budgets, progression_path
from .planner_page import interface_store
from .result_windows import GridTable, ResultWindows
from .screen_read import ScreenRead
from .timers_page import Fold

LONG_AGO = 10 * 365 * 86400                          # a snapshot of any age: the last character's, at launch
WAIT_S = 120                                         # how long a request may take (the official site, a large recording)


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _plain() -> QWidget:
    box = QWidget()
    box.setObjectName("plain")
    return box


class CharacterPage(QWidget):
    """Character → My Character. ``open_web`` opens a page of the web interface; ``store`` keeps what the web page keeps
    in its browser (the totals typed for each character, the game version, the objective, the Genus choice)."""

    def __init__(self, api: AppApi | None, open_web=None, store: QSettings | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_web = api, open_web
        self.store = store if store is not None else interface_store()
        self.known: list[dict] = []
        self.hits: list[dict] = []
        self.hit: dict | None = None
        self.view: dict | None = None
        self.meta: dict = {}
        self.opt: dict | None = None
        self.auto_opened, self.points_turn = False, 0
        self.survival: SurvivalOptions | None = None
        self.reserves: SkillReserves | None = None
        self.panels = 0                                  # the survival panels drawn, each answered under its own number
        self.requests = Requests(api, self, timeout=WAIT_S) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.importing = Job(api, self) if api is not None else None
        self.optimizing = Job(api, self, patient=True) if api is not None else None
        if self.importing is not None:
            self.importing.logged.connect(lambda log: self.message.setText(c.js_text(log[-1]) if log else ""))
            self.importing.done.connect(self._imported)
            self.importing.failed.connect(lambda why: self._show_note(why, "bad"))
            self.optimizing.logged.connect(self._opt_logged)
            self.optimizing.done.connect(self._opt_done)
            self.optimizing.failed.connect(self._opt_failed)
        self.setStyleSheet(GatheringPage._stylesheet() + result_windows.STYLE + f"""
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#primary:disabled, QPushButton#small:disabled {{ color: {theme.COLORS['faint']}; }}
            QPlainTextEdit#diff {{ background: rgba(6, 9, 15, 0.65); border: none; border-radius: 6px; padding: 10px; }}
            QLabel#good {{ color: {theme.COLORS['good']}; }}
            QFrame#win QLabel#kpiGood {{ color: {theme.COLORS['good']}; font-size: 19px; font-weight: 700; }}
            QFrame#screenRead {{ border: 1px dashed {theme.COLORS['line2']}; border-radius: 6px; background: transparent; }}
            QFrame#screenRead QLabel {{ background: transparent; }}
            """ + options_style() + editor_style() + Toast.STYLE)
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
        self.layout_.setSpacing(14)
        self.layout_.addWidget(self._search())
        holder = _plain()
        self.cview = QVBoxLayout(holder)
        self.cview.setContentsMargins(0, 0, 0, 0)
        self.cview.setSpacing(14)
        self.layout_.addWidget(holder)
        self.windows = ResultWindows(api, open_web, "character")
        self.windows.hide()
        self.layout_.addWidget(self.windows)
        self.layout_.addStretch(1)
        self.character: Window | None = None
        self.opt_box: QVBoxLayout | None = None
        self.drawn = None                             # what the optimization's place shows, to update a run in place
        self.buttons: list[QPushButton] = []
        self.toast = Toast(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.place()

    # ------------------------------------------------------------------ the search
    def _search(self) -> Window:
        window = Window("My character", c.TITLE_SUB)
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Character name")
        self.name.setAccessibleName("Character name")
        self.name.setFixedWidth(252)
        self.name.returnPressed.connect(self.search)
        flow.addWidget(self.name)
        self.region = QComboBox()
        self.region.setAccessibleName("Region")
        for key, words in c.REGIONS:
            self.region.addItem(words, key)
        flow.addWidget(self.region)
        find = QPushButton("Search")
        find.setObjectName("primary")
        find.clicked.connect(self.search)
        flow.addWidget(find)
        self.message = _label("", "muted")
        self.message.setMaximumWidth(520)
        flow.addWidget(self.message)
        window.body.addWidget(row)
        hits = _plain()
        self.hits_box = QVBoxLayout(hits)
        self.hits_box.setContentsMargins(0, 0, 0, 0)
        window.body.addWidget(hits)
        known = _plain()
        self.known_box = QVBoxLayout(known)
        self.known_box.setContentsMargins(0, 0, 0, 0)
        window.body.addWidget(known)
        return window

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.requests is not None:
            self.requests.get("characters", "/api/characters")
            if not self.auto_opened:
                self.requests.get("ui", "/api/ui")

    def search(self) -> None:
        self.message.setText("…")
        if self.requests is not None:
            self.requests.get("search", c.search_path(self.name.text(), self.region.currentData()))

    def import_character(self, hit: dict, cache: int | None = None) -> None:
        """A character read through its job: from the official site, or its last snapshot of at most ``cache`` s."""
        self._show_note(c.importing(hit, cache), "empty")
        if self.importing is not None:
            self.pending = hit
            self.importing.start("/api/character/import", {**hit, "cache": cache} if cache else hit)

    def _replied(self, name: str, answer) -> None:
        kind, _, rest = name.partition(":")
        if kind == "characters":
            self.known = [x for x in answer if isinstance(x, dict)] if isinstance(answer, list) else []
            self._draw_known()
        elif kind == "ui":
            ui = answer if isinstance(answer, dict) else {}
            if ui.get("character_auto_open") and self.known and not self.auto_opened and self.view is None:
                self.auto_opened = True               # once each time the app runs
                self.import_character(c.known_hit(self.known[0]), 0 if ui.get("character_auto_refresh") else LONG_AGO)
            self.auto_opened = True
        elif kind == "search":
            self.hits = [x for x in answer if isinstance(x, dict)] if isinstance(answer, list) else []
            self.message.setText(f"{len(self.hits)} found")
            self._draw_hits()
        elif kind == "survival":
            panel, _, what = rest.partition(":")
            if self.survival is not None and panel == str(self.panels):
                self.survival.replied(what, answer)
        elif kind == "inventory" and rest == str(self.panels) and self.character is not None:
            self._inventory(answer)
        elif kind == "genus" and rest == str(self.panels) and self.genus_editor is not None:
            genus = answer.get("genus") if isinstance(answer, dict) else None
            self.genus_editor.saved(genus if c._truthy(genus) else {})
        elif kind == "points" and rest == str(self.points_turn) and self.character is not None and self.view is not None:
            try:
                found = budgets(answer, str(self.view.get("class") or ""), {"region": (self.hit or {}).get("region") or ""})
            except ValueError:
                return
            note = c.community_note(found["points"], c.budget_keys(self.view))
            if note:
                self.community.setText(note)
                self.community.show()

    def _failed(self, name: str, why: str) -> None:
        kind, _, rest = name.partition(":")
        if name == "search":
            self.message.setText(why)
        elif kind == "survival":
            panel, _, what = rest.partition(":")
            if self.survival is not None and panel == str(self.panels):
                self.survival.failed(what, why)
        elif kind == "inventory" and rest == str(self.panels) and self.character is not None:
            self._clear(self.genus_host)
            self.genus_host.addWidget(_label("Could not load Genus: " + why))
        elif kind == "genus" and rest == str(self.panels) and self.genus_editor is not None:
            self.genus_editor.not_saved(why)

    def _draw_known(self) -> None:
        self._clear(self.known_box)
        if not self.known:
            return
        self.known_box.addWidget(_label("Imported before · newest first (click to fetch current profile):", "muted"))
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(8, 6))
        for found in self.known[:8]:
            button = QPushButton(c.known_line(found).replace("&", "&&"))
            button.setObjectName("small")
            button.clicked.connect(lambda _checked=False, found=found: self.import_character(c.known_hit(found)))
            flow.addWidget(button)
        self.known_box.addWidget(row)

    def _draw_hits(self) -> None:
        self._clear(self.hits_box)
        if not self.hits:
            return
        rows = []
        for hit in self.hits[:30]:
            button = QPushButton("Import")
            button.setObjectName("small")
            button.setAccessibleName(f"Import {c.js_text(hit.get('name'))}")
            button.clicked.connect(lambda _checked=False, hit=hit: self.import_character(hit))
            rows.append(c.hit_row(hit) + [button])
        self.hits_box.addWidget(GridTable(["Name", "Level", "Server", ""], rows, {0: 3, 2: 2}))

    # ------------------------------------------------------------------ the character
    def _show_note(self, text: str, kind: str) -> None:
        self._clear(self.cview)
        self.character, self.opt_box, self.drawn, self.survival, self.reserves = None, None, None, None, None
        self.windows.hide()
        note = _label(text, kind)
        note.setAlignment(Qt.AlignCenter)
        self.cview.addWidget(note)

    def _imported(self, view) -> None:
        if not isinstance(view, dict):
            self._show_note("The character could not be read.", "bad")
            return
        self.view, self.hit = view, getattr(self, "pending", None) or {}
        if self.opt is not None and self.opt.get("status") != "running":
            self.opt = None                           # a finished run belongs to the import it ran on
        self._show_character()

    def _saved_budgets(self) -> dict:
        return c.read_store(self.store.value(c.BUDGETS_KEY)).get(str(self.view.get("key")), {}) or {}

    def _show_character(self) -> None:
        v = self.view
        self._clear(self.cview)
        window = Window(c.js_text(v.get("name")), c.subtitle(v))
        self.buttons = []
        for index, (mode, words, _name) in enumerate(c.MODES):
            button = QPushButton(words)
            button.setObjectName("primary" if index == 0 else "small")
            if mode == "world":
                button.setToolTip(c.WORLD_TIP)
            button.clicked.connect(lambda _checked=False, mode=mode: self.optimize(mode))
            window.tool(button)
            self.buttons.append(button)
        tiles = []
        for name, value in c.kpis(v):
            tile = Kpi(name)
            tile.findChild(QLabel, "kpiName").setWordWrap(True)
            tile.value.setText(value)
            tile.layout().addStretch(1)                       # at the tile's top, as tall as its row
            tiles.append(tile)
        window.body.addWidget(AutoGrid(tiles, least=150, gap=10, fill=True, top=False))   # .kpis, 0.2.441
        if v.get("progression"):
            fold = Fold("Point budget provenance")
            fold.add(_label(r.progression(v["progression"]), rich=True))
            window.body.addWidget(fold)
        for line in c.warnings(v):
            window.body.addWidget(_label(line, "muted"))
        window.body.addWidget(_label(c.POINTS_NOTE, "muted"))
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.fields: dict[str, QLineEdit] = {}
        shown = c.available(v, self._saved_budgets())
        for key in c.budget_keys(v):
            field = QLineEdit(c.js_text(shown.get(key)))
            field.setFixedWidth(103)
            field.setAccessibleName(f"{c.budget_label(key)} total")
            field.editingFinished.connect(self._remember)
            self.fields[key] = field
            pair = _plain()
            line = QHBoxLayout(pair)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            label = _label(f"{c.budget_label(key)} total", wrap=False)
            if key == "ariel":
                label.setToolTip(c.ARIEL_TIP)
            line.addWidget(label)
            line.addWidget(field)
            flow.addWidget(pair)
        patch = _plain()
        line = QHBoxLayout(patch)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(_label("Game version (optional)", wrap=False))
        self.patch = QLineEdit(str(self.store.value(c.PATCH_KEY) or ""))
        self.patch.setPlaceholderText("Unknown")
        self.patch.setMaxLength(100)
        self.patch.setAccessibleName("Game version (optional)")
        self.patch.editingFinished.connect(lambda: self.store.setValue(c.PATCH_KEY, self.patch.text().strip()))
        line.addWidget(self.patch)
        flow.addWidget(patch)
        window.body.addWidget(row)
        self.community = _label("", "muted")
        self.community.hide()
        window.body.addWidget(self.community)
        window.body.addWidget(_label(c.PVP_NOTE, "muted"))
        objective = _plain()
        line = QHBoxLayout(objective)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(_label("Damage objective", wrap=False))
        self.objective = QComboBox()
        self.objective.setAccessibleName("Damage objective")
        for key, words in c.OBJECTIVES:
            self.objective.addItem(words, key)
        self.objective.setCurrentIndex(1 if self.store.value(c.OBJECTIVE_KEY) == "balanced" else 0)
        self.objective.activated.connect(lambda _i: self.store.setValue(c.OBJECTIVE_KEY, self.objective.currentData()))
        line.addWidget(self.objective)
        line.addStretch(1)
        window.body.addWidget(objective)
        window.body.addWidget(_label(c.BALANCED_NOTE, "muted"))
        self.panels += 1
        self.survival = SurvivalOptions(self.store, c.options_key(c.SURVIVAL_PREFIX, self.hit, v), v, self._send,
                                        self.toast.say)
        window.body.addWidget(self.survival)
        self.reserves = SkillReserves(self.store, c.options_key(c.RESERVES_PREFIX, self.hit, v), v, self.toast.say)
        window.body.addWidget(self.reserves)
        window.body.addWidget(self._genus())
        holder = _plain()
        self.opt_box = QVBoxLayout(holder)
        self.opt_box.setContentsMargins(0, 0, 0, 0)
        self.opt_box.setSpacing(6)
        self.drawn = None
        window.body.addWidget(holder)
        self.character = window
        self.cview.addWidget(window)
        self.meta = c.meta(v)
        self.windows.set_view(v)
        self.windows.show()
        self._draw_opt()
        if c.at_level_cap(v) and self.requests is not None:
            self.points_turn += 1
            path = progression_path(str(v.get("class") or ""), {"region": (self.hit or {}).get("region") or ""})
            self.requests.get(f"points:{self.points_turn}", "/api/community?path=" + urllib.parse.quote(path, safe=""))

    def _genus(self) -> Fold:
        """Pet Genus Insight (``mountCharacterGenus``, closed): whether the saved lines count, and the PvE mix."""
        saved = c.read_store(self.store.value(self._genus_key()))
        fold = self.genus_fold = Fold("Pet Genus Insight · PvE and PvP")
        fold.add(_label(c.GENUS_NOTE, "muted"))
        self.use_genus = QCheckBox("Include saved Genus lines")
        self.use_genus.setChecked(saved.get("enabled") is not False)
        fold.add(self.use_genus)
        fold.add(_label(c.MIX_NOTE, "muted"))
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        self.mix: dict[str, QLineEdit] = {}
        mix = saved.get("mix") if isinstance(saved.get("mix"), dict) else {}
        for genus in c.GENERA:
            field = QLineEdit(c.js_text(mix.get(genus, 0 if genus == "Special" else 25)))
            field.setFixedWidth(86)
            field.setAccessibleName(f"{genus} weight")
            self.mix[genus] = field
            pair = _plain()
            line = QHBoxLayout(pair)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            line.addWidget(_label(genus, wrap=False))
            line.addWidget(field)
            flow.addWidget(pair)
        fold.add(row)
        reads = _plain()
        self.genus_reads = QVBoxLayout(reads)                  # the read row, once the lines are loaded
        self.genus_reads.setContentsMargins(0, 0, 0, 0)
        fold.add(reads)
        host = _plain()
        self.genus_host = QVBoxLayout(host)
        self.genus_host.setContentsMargins(0, 0, 0, 0)
        self.genus_host.addWidget(_label("Loading saved lines…"))
        fold.add(host)
        self.genus_editor: GenusEditor | None = None
        if self.requests is not None:
            self.requests.get(f"inventory:{self.panels}", "/api/inventory?character=" +
                              urllib.parse.quote(str(self.view.get("key")), safe=""))
        return fold

    def _inventory(self, answer) -> None:
        """The character's saved Genus lines in the editor (``A2GenusEditor.mount``), with the row that reads them from
        the game."""
        self._clear(self.genus_host)
        genus = answer.get("genus") if isinstance(answer, dict) else None
        self.genus_editor = GenusEditor(genus if c._truthy(genus) else {}, self._save_genus)
        self.genus_host.addWidget(self.genus_editor)
        self.genus_reads.addWidget(ScreenRead(self.api, "genus", self.genus_editor.apply_read))

    def _save_genus(self, draft: dict) -> None:
        if self.requests is not None:
            self.requests.post(f"genus:{self.panels}", "/api/inventory/genus",
                               {"character": self.view.get("key"), "genus": c.to_json(draft)})

    def _send(self, name: str, path: str, body: dict) -> None:
        """The survival panel's import requests, answered to the panel shown (one drawn since is not answered)."""
        if self.requests is not None:
            self.requests.post(f"survival:{self.panels}:{name}", path, body)

    def _genus_key(self) -> str:
        return "character-genus-options:" + str((self.view or {}).get("key"))

    def _remember(self) -> dict:
        """The totals in the fields, those above what the profile shows spent kept for this character."""
        values = c.field_values({k: f.text() for k, f in self.fields.items()})
        kept = c.read_store(self.store.value(c.BUDGETS_KEY))
        kept[str(self.view.get("key"))] = c.remembered(self.view, values)
        self.store.setValue(c.BUDGETS_KEY, json.dumps(kept))
        return values

    # ------------------------------------------------------------------ optimizing
    def optimize(self, mode: str) -> None:
        """An optimization: its request read as the web page reads it (the totals, the survival options, the reserves,
        then the Genus choice, each kept as it is read), or why it cannot start."""
        if (self.opt is not None and self.opt.get("status") == "running" or self.view is None or self.optimizing is None
                or self.survival is None or self.reserves is None):
            return
        try:
            totals = self._remember()
            survival = self.survival.save()
            reserves = self.reserves.read()
            if self.use_genus.isChecked() and (self.genus_editor is None or self.genus_editor.is_dirty()):
                raise ValueError(c.WAIT_GENUS if self.genus_editor is None else c.SAVE_GENUS)
            genus = c.genus_choice(self.use_genus.isChecked(), {g: f.text() for g, f in self.mix.items()}, mode)
        except ValueError as problem:
            self.opt = {"status": "error", "error": str(problem)}
            self._draw_opt()
            return
        self.store.setValue(self._genus_key(), json.dumps({"enabled": self.use_genus.isChecked(),
                                                           "mix": {g: c._float(f.text()) for g, f in self.mix.items()}}))
        self.opt = {"status": "running", "mode": mode, "log": [], "key": self.view.get("key"), "name": self.view.get("name")}
        self._draw_opt()
        self.optimizing.start("/api/character/optimize", c.optimize_body(
            self.hit or {}, mode, self.objective.currentData(), totals, survival, reserves, genus, self.patch.text()))

    def _opt_logged(self, log: list) -> None:
        if self.opt is not None and self.opt.get("status") == "running":
            self.opt["log"] = log or self.opt.get("log") or []
            self._draw_opt()

    def _opt_done(self, result) -> None:
        if self.opt is None:
            return
        self.opt.update(status="done", result=result if isinstance(result, dict) else {})
        self._draw_opt()

    def _opt_failed(self, why: str) -> None:
        if self.opt is None:
            return
        self.opt.update(status="error", error=why or "optimization failed")
        self._draw_opt()

    def _draw_opt(self) -> None:
        """The optimization's place on the character's page (``renderOptState``): another character's run, this one's
        progress, its error, or its result and the optimized build. A run already shown is updated in place as its job
        is read, rather than drawn again (its log keeps where it is scrolled to)."""
        if self.opt_box is None:
            return
        o = self.opt
        for button in self.buttons:
            button.setEnabled(not (o and o.get("status") == "running"))
        elsewhere = bool(o) and o.get("key") is not None and self.view is not None and o.get("key") != self.view.get("key")
        if o and o.get("status") == "running":
            drawn = ("elsewhere", c.elsewhere(o.get("name"))) if elsewhere else ("running", o.get("mode"))
            if drawn == self.drawn:
                if not elsewhere:
                    line, tail = c.running(o.get("mode"), o.get("log") or [])
                    self.run_line.setText(line)
                    if self.run_log.toPlainText() != tail:
                        self.run_log.setPlainText(tail)
                return
            self.drawn = drawn
        else:
            self.drawn = None
        self._clear(self.opt_box)
        if not o or elsewhere:
            if elsewhere and o.get("status") == "running":
                self.opt_box.addWidget(_label(c.elsewhere(o.get("name")), "muted"))
            return
        if o.get("status") == "running":
            line, tail = c.running(o.get("mode"), o.get("log") or [])
            self.run_line = _label(line, "strong")
            self.opt_box.addWidget(self.run_line)
            self.run_log = QPlainTextEdit(tail)
            self.run_log.setObjectName("diff")
            self.run_log.setReadOnly(True)
            self.run_log.setFont(QFont("monospace"))
            self.run_log.setMaximumHeight(150)
            self.opt_box.addWidget(self.run_log)
            self.opt_box.addWidget(_label(c.RUNNING_NOTE, "faint"))
        elif o.get("status") == "error":
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(c.js_text(o.get("error") or "optimization failed")))
            note.layout().setContentsMargins(0, 0, 0, 0)
            self.opt_box.addWidget(note)
        elif o.get("status") == "done":
            self._draw_result(o.get("result") or {})

    def _draw_result(self, result: dict) -> None:
        shown = c.result(result)
        counts = _plain()
        row = QHBoxLayout(counts)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(10)
        score = Kpi(shown["label"])
        score.value.setText(shown["score"])
        row.addWidget(score)
        gain = Kpi("Gain")
        gain.value.setText(shown["gain"])
        if shown["good"]:
            gain.value.setObjectName("kpiGood")
        row.addWidget(gain)
        row.addStretch(1)
        self.opt_box.addWidget(counts)
        if shown["model_note"]:
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(shown["model_note"]))
            note.layout().setContentsMargins(0, 0, 0, 0)
            self.opt_box.addWidget(note)
        if shown["preset"]:
            self.opt_box.addWidget(_label(shown["preset"], "good" if shown["accepted"] else "muted"))
        self.opt_box.addWidget(_label("The windows below now show the optimized build. What changes:", "muted"))
        diff = QPlainTextEdit(shown["diff"])
        diff.setObjectName("diff")
        diff.setReadOnly(True)
        diff.setFont(QFont("monospace"))
        diff.setMaximumHeight(320)
        self.opt_box.addWidget(diff)
        self.windows.set_view(c.optimized_view(result, self.meta))

    def closeEvent(self, event) -> None:
        self.windows.stop()
        for worker in (self.requests, self.importing, self.optimizing):
            if worker is not None:
                worker.stop()
        super().closeEvent(event)

