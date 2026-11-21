"""The native Gear & Advice page (0.2.443; its advice since 0.2.444, its arcana, titles and Pantheon since 0.2.445):
Character → Gear & Advice as pages/gear.js shows it.

- **The character** to advise, chosen among those imported on My Character, and **Run advice** (its job): its progress
  as it runs, and the advice kept from the last run (when it was calculated, what has changed since). Opening the page,
  or another character, shows the advice kept, or runs it when there is none.
- **The inventory:** the items the character wears and those added from the bag and warehouse, each with its rolls,
  skill options and source; **Edit** and **Remove** for those added; the catalog's search to add more, in the item
  panel (enchant level, random rolls, skill options and a note).
- **Genus Insight:** the Genus editor and the row that reads it from the game (as on My Character); saving the lines
  sets the advice aside until it runs again.
- **Titles you own:** the Title window's pages read from the game, the titles they say the character owns, and the
  list kept with **Save titles**.

The advice is drawn under them (``advice_view.AdviceView``): its top changes, skill specialties, paper doll, upgrade path,
arcana, titles, Pantheon, fights and calibration. Its genus recommendations open in the web interface for now.
"""
from __future__ import annotations

import html
import time
import urllib.parse

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import character as c
from . import gear as g
from . import result_windows
from . import results as r
from . import theme
from .api import AppApi, Job, Requests
from .advice_view import STYLE as ADVICE_STYLE, AdviceView
from .character_options import style as options_style
from .database_page import Window
from .gathering_page import GatheringPage
from .genus_editor import GenusEditor, style as editor_style
from .pets_page import Toast
from .result_windows import GridTable
from .screen_read import ScreenRead, TitleReads

WAIT_S = 120


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


def _button(words: str, action, name: str = "small") -> QPushButton:
    button = QPushButton(words)
    button.setObjectName(name)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _graded(name: str, grade: str, note: str = "") -> QLabel:
    """An item's name in its grade's colour (``.gname[data-grade]``), and its note muted."""
    colour = result_windows._css_colour(r.GRADES[grade]).name() if grade else theme.COLORS["text"]
    words = f"<span style='color: {colour}; font-weight: 600;'>{html.escape(name)}</span>"
    if note:
        words += r.muted(html.escape(f" · {note}"))
    return _label(words, rich=True)


def _row(*widgets, gap: int = 8) -> QWidget:
    row = _plain()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(gap)
    for widget in widgets:
        line.addWidget(widget)
    line.addStretch(1)
    return row


class GearPage(QWidget):
    """Character → Gear & Advice. ``show_page`` opens another native page (Saved advice); ``open_web`` the web
    interface's (the advice's full view)."""

    def __init__(self, api: AppApi | None, show_page=None, open_web=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.show_page, self.open_web = api, show_page, open_web
        self.key = ""                                    # the character chosen (``st.key``)
        self.inv: dict = {}
        self.advice = None                               # the advice shown, and the kept run's facts (``st.adv``, ``st.kept``)
        self.kept = None
        self.advice_job: dict | None = None
        self.advice_run = 0
        self.genus_revision = 0
        self.query = ""                                  # the last search (kept across the inventory drawn again)
        self.visits = 0
        self.editor: dict | None = None
        self.genus_editor: GenusEditor | None = None
        self.requests = Requests(api, self, timeout=WAIT_S) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.advising = Job(api, self) if api is not None else None
        if self.advising is not None:
            self.advising.logged.connect(self._advice_logged)
            self.advising.done.connect(self._advice_done)
            self.advising.failed.connect(self._advice_failed)
        self.setStyleSheet(GatheringPage._stylesheet() + result_windows.STYLE + f"""
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#primary:disabled, QPushButton#small:disabled {{ color: {theme.COLORS['faint']}; }}
            QPlainTextEdit#diff {{ background: rgba(6, 9, 15, 0.65); border: none; border-radius: 6px; padding: 10px; }}
            QFrame#gedit {{ background: rgba(6, 9, 15, 0.65); border: 1px solid {theme.COLORS['line']}; border-radius: 6px; }}
            QFrame#gedit QLabel {{ background: transparent; }}
            QFrame#gelines {{ border: 1px dashed {theme.COLORS['line']}; border-radius: 6px; background: transparent; }}
            QLabel#gearHead {{ color: {theme.COLORS['gold']}; font-weight: 700; letter-spacing: 0.6px; }}
            QFrame#screenRead {{ border: 1px dashed {theme.COLORS['line2']}; border-radius: 6px; background: transparent; }}
            QFrame#screenRead QLabel {{ background: transparent; }}
            """ + options_style() + editor_style() + ADVICE_STYLE + Toast.STYLE)
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
        self.frame = Window("Gear & advice", g.SUBTITLE)
        self.frame.tool(_button("Saved advice", lambda: self.show_page("history") if self.show_page else None))
        self.layout_.addWidget(self.frame)
        out = _plain()
        self.out = QVBoxLayout(out)                       # the advice (``#gout``)
        self.out.setContentsMargins(0, 0, 0, 0)
        self.layout_.addWidget(out)
        self.layout_.addStretch(1)
        self.toast = Toast(self)
        self.combo: QComboBox | None = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.place()

    # ------------------------------------------------------------------ opening the page
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visits += 1
        if self.requests is not None:
            self.requests.get(f"characters:{self.visits}", "/api/characters")

    def _draw(self, characters: list[dict]) -> None:
        body = self.frame.body
        _clear(body)
        self.combo = None
        if not characters:
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(g.NO_CHARACTERS))
            body.addWidget(note)
            return
        self.combo = QComboBox()
        self.combo.setAccessibleName("Character")
        for row in characters:
            self.combo.addItem(g.character_line(row), c.esc_text(row.get("key")))
        index = self.combo.findData(self.key)
        self.combo.setCurrentIndex(index if index >= 0 else 0)
        self.combo.activated.connect(lambda _i: self._chosen())
        self.run = _button("Run advice", self.run_advice, "primary")
        self.message = _label("", "muted", wrap=False)
        body.addWidget(_row(self.combo, self.run, self.message))
        self.kept_line = _label("", rich=True)
        self.kept_line.hide()
        body.addWidget(self.kept_line)
        body.addWidget(_label(g.NOTE, "faint"))
        self.progress_box = QFrame()
        self.progress_box.setObjectName("note")
        self.progress = QVBoxLayout(self.progress_box)
        self.progress_box.hide()
        body.addWidget(self.progress_box)
        holder = _plain()
        self.inventory = QVBoxLayout(holder)
        self.inventory.setContentsMargins(0, 0, 0, 0)
        self.inventory.setSpacing(8)
        body.addWidget(holder)
        self.key = self.combo.currentData()
        self._render_progress()
        self.show_inventory(then_advice=True)

    def _chosen(self) -> None:
        """Another character (``#gchar``'s change): its inventory, then its kept advice."""
        if self.combo.currentData() == self.key:
            return
        self.advice = self.kept = None
        self._kept(None)
        _clear(self.out)
        self.key = self.combo.currentData()
        self._render_progress()
        self.show_inventory(then_advice="kept")

    # ------------------------------------------------------------------ the advice
    def _kept(self, kept) -> None:
        if not hasattr(self, "kept_line"):
            return
        self.kept_line.setVisible(bool(kept))
        self.kept_line.setText(g.kept_text(kept) if kept else "")

    def show_advice(self, advice, kept) -> None:
        """The advice on the page (``showAdvice``): its windows (``renderAdvice``), under the line about the advice
        kept."""
        _clear(self.out)
        self.out.addWidget(AdviceView(self.api, advice if isinstance(advice, dict) else {}, self.open_web))
        self.advice, self.kept = advice, kept
        self._kept(kept)

    def open_kept(self) -> None:
        """The advice kept from the last run, or a run when there is none (``openKept``)."""
        if self.combo is None or self._busy():
            return
        if self.requests is not None:
            self.requests.get(f"kept:{self.key}", "/api/advice/last?character=" + urllib.parse.quote(self.key, safe=""))

    def _busy(self) -> bool:
        return bool(self.advice_job) and self.advice_job.get("status") == "running"

    def run_advice(self) -> None:
        if self._busy() or self.combo is None:
            return
        if self.genus_editor is not None and self.genus_editor.is_dirty():
            self.message.setText(g.SAVE_GENUS_FIRST)
            self.toast.say(g.SAVE_GENUS_TOAST)
            return
        self.message.setText("")
        self.advice = self.kept = None
        self._kept(None)
        _clear(self.out)
        self.out.addWidget(_label(g.CALCULATING, "muted"))
        self.advice_run += 1
        self.advice_job = {"key": self.key, "status": "running", "started": time.time(), "log": [],
                           "run": self.advice_run, "revision": self.genus_revision}
        self._render_progress()
        if self.advising is not None:
            self.advising.start("/api/advice", {"character": self.key})

    def _advice_logged(self, lines: list) -> None:
        if self.advice_job is not None and self.advice_job.get("status") == "running":
            self.advice_job["log"] = lines
            self._render_progress()

    def _advice_done(self, advice) -> None:
        job = self.advice_job
        if job is None:
            return
        if self.key != job["key"] or self.advice_run != job["run"]:
            job["status"] = "done"                     # another character's: shown when it is chosen again (kept)
            self._render_progress()
            return
        if self.genus_revision != job["revision"]:
            self._advice_failed(g.GENUS_CHANGED)
            return
        job["status"] = "done"
        self.show_advice(advice, None)
        self.toast.say(g.DONE_TOAST)
        self._render_progress()

    def _advice_failed(self, why: str) -> None:
        job = self.advice_job
        if job is None:
            return
        job.update(status="error", error=why)
        if self.key == job["key"] and self.advice_run == job["run"]:
            _clear(self.out)
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(c.esc_text(why)))
            self.out.addWidget(note)
        self._render_progress()

    def _render_progress(self) -> None:
        """The advice job's place (``renderAdviceProgress``)."""
        if self.combo is None:
            return
        job = self.advice_job
        current = bool(job) and job["key"] == self.key
        busy = current and job["status"] == "running"
        self.run.setEnabled(not busy)
        self.run.setText(g.CALCULATING if busy else "Run advice")
        self.combo.setEnabled(not busy)
        self.progress_box.setVisible(current)
        _clear(self.progress)
        if not current:
            return
        state, line, tail = g.progress(job, time.time())
        if state == "running":
            self.progress.addWidget(_label(line, rich=True))
            bar = QProgressBar()
            bar.setRange(0, 0)                            # an indeterminate <progress>
            bar.setAccessibleName("Advice calculation in progress")
            bar.setMaximumHeight(8)
            bar.setTextVisible(False)
            self.progress.addWidget(bar)
            log = QPlainTextEdit(tail)
            log.setObjectName("diff")
            log.setReadOnly(True)
            log.setFont(QFont("monospace"))
            log.setMaximumHeight(130)
            self.progress.addWidget(log)
            self.progress.addWidget(_label(g.RUNNING_NOTE, "muted"))
        elif state == "done":
            self.progress.addWidget(_label(f"<b>{line}</b> {tail}", rich=True))
            self.progress.addWidget(_row(_button("View results ↓", self._view_results, "primary")))
        else:
            self.progress.addWidget(_label(line, "bad"))

    def _view_results(self) -> None:
        if self.out.count():
            self.scroll.ensureWidgetVisible(self.out.itemAt(0).widget(), 0, 0)

    # ------------------------------------------------------------------ the inventory
    def show_inventory(self, then_advice=False) -> None:
        self.then_advice = then_advice
        if self.requests is not None:
            self.requests.get(f"inventory:{self.key}", "/api/inventory?character=" + urllib.parse.quote(self.key, safe=""))

    def _draw_inventory(self, inv: dict) -> None:
        self.inv = inv
        _clear(self.inventory)
        self.editor = None
        self.inventory.addWidget(_label("INVENTORY", "gearHead"))
        rows = []
        for entry in r._list(inv.get("items")):
            if not isinstance(entry, dict):
                continue
            name = _graded(g.item_text(entry), r.slot_grade(entry),
                           c.esc_text(entry["note"]) if c._truthy(entry.get("note")) else "")
            actions = _plain()
            if entry.get("source") == "inventory":
                line = QHBoxLayout(actions)
                line.setContentsMargins(0, 0, 0, 0)
                line.setSpacing(6)
                edit = _button("Edit", lambda entry=entry: self.edit(entry))
                remove = _button("Remove", lambda entry=entry: self.remove(entry))
                line.addWidget(edit)
                line.addWidget(remove)
            rows.append([g.slot_text(entry), name, g.rolls_of(entry), g.skills_of(entry), c.esc_text(entry.get("source")),
                         actions])
        self.inventory.addWidget(GridTable(g.INVENTORY_HEADS, rows, {1: 3, 2: 2, 3: 2}))
        self.inventory.addWidget(_label(g.INVENTORY_NOTE, "faint", rich=True))
        holder = _plain()
        self.editor_box = QVBoxLayout(holder)
        self.editor_box.setContentsMargins(0, 0, 0, 0)
        self.inventory.addWidget(holder)
        self.search_field = QLineEdit(self.query)
        self.search_field.setPlaceholderText(g.SEARCH_HINT)
        self.search_field.setAccessibleName("Search the catalog")
        self.search_field.setFixedWidth(320)
        self.search_field.returnPressed.connect(self.search)
        self.inventory.addWidget(_row(self.search_field, _button("Search", self.search)))
        found = _plain()
        self.found = QVBoxLayout(found)
        self.found.setContentsMargins(0, 0, 0, 0)
        self.inventory.addWidget(found)
        # Genus Insight: the editor, read from the game; saving sets the advice aside
        self.inventory.addWidget(_label("GENUS INSIGHT", "gearHead"))
        genus = inv.get("genus")
        self.genus_editor = GenusEditor(genus if c._truthy(genus) else {}, self._save_genus)
        self.inventory.addWidget(ScreenRead(self.api, "genus", self.genus_editor.apply_read))
        self.inventory.addWidget(self.genus_editor)
        # Titles you own: the pages read, and the list kept
        self.inventory.addWidget(_label("TITLES YOU OWN", "gearHead"))
        self.inventory.addWidget(_label(g.TITLES_NOTE, "faint", rich=True))
        self.titles = QPlainTextEdit("\n".join(c.esc_text(x) for x in r._list(inv.get("titles_owned"))))
        self.titles.setAccessibleName("Titles you own")
        self.titles.setMaximumHeight(110)
        self.title_reads = TitleReads(self.api, self.key, self._fill_titles, self.toast.say)
        self.inventory.addWidget(ScreenRead(self.api, "titles", lambda _record: self.title_reads.refresh()))
        self.inventory.addWidget(self.title_reads)
        self.inventory.addWidget(_label(g.TITLES_LIST_NOTE, "faint"))
        self.inventory.addWidget(self.titles)
        self.inventory.addWidget(_row(_button("Save titles", self.save_titles)))
        if self.query:
            self.search()                                 # the last search stays after an add or an edit

    def _fill_titles(self, add: bool) -> None:
        self.titles.setPlainText(g.filled(self.title_reads.summary.get("owned", []), self.titles.toPlainText(), add))
        self.toast.say(g.LIST_FILLED)

    def save_titles(self) -> None:
        if self.requests is not None:
            self.requests.post(f"titles:{self.key}", "/api/inventory/titles",
                               {"character": self.key, "titles": self.titles.toPlainText().split("\n")})

    def _save_genus(self, draft: dict) -> None:
        if self.requests is not None:
            self.requests.post(f"genus:{self.key}", "/api/inventory/genus", {"character": self.key, "genus": c.to_json(draft)})

    def search(self) -> None:
        self.query = self.search_field.text()
        if self.requests is not None:
            self.requests.get(f"search:{self.key}", g.search_path(self.query))

    def _draw_found(self, items: list) -> None:
        _clear(self.found)
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _graded(c.esc_text(item.get("name")), r.slot_grade(item))
            add = _button("Add…", lambda item=item: self.open_editor(item.get("slug"), None))
            rows.append([name, c.esc_text(item.get("category")), c.esc_text(item.get("item_level")), add])
        self.found.addWidget(GridTable(["Item", "Category", "Item level", ""], rows, {0: 3, 1: 2}))

    def remove(self, entry: dict) -> None:
        if self.requests is not None:
            self.requests.post(f"removed:{self.key}", "/api/inventory/remove", {"character": self.key, "id": entry.get("id")})

    def edit(self, entry: dict) -> None:
        if c._truthy(entry.get("slug")):
            self.open_editor(entry["slug"], entry)
        else:
            self.toast.say(g.NOT_IN_CATALOG)

    # ------------------------------------------------------------------ the item panel
    def open_editor(self, slug, entry) -> None:
        self.pending_entry = entry
        if self.requests is not None:
            self.requests.get(f"options:{self.key}", g.options_path(slug, self.inv.get("class")))

    def _draw_editor(self, opt: dict) -> None:
        ed = self.editor
        _clear(self.editor_box)
        frame = QFrame()
        frame.setObjectName("gedit")
        lines = QVBoxLayout(frame)
        lines.setContentsMargins(12, 10, 12, 10)
        lines.setSpacing(8)
        name, facts, mode = g.heading(opt, ed)
        title = _graded(name, r.slot_grade(opt))
        title.setWordWrap(False)
        lines.addWidget(_row(title, _label(facts, "muted", wrap=False), _label(mode, "muted", wrap=False)))
        self.enchant = QComboBox()
        self.enchant.setAccessibleName("Enchant")
        for level in range(int(c.js_number(opt.get("max_enchant")) or 0) + 1):
            self.enchant.addItem(f"+{level}", level)
        self.enchant.setCurrentIndex(ed["enchant"])
        self.enchant.activated.connect(lambda _i: self._redraw_editor(opt))
        lines.addWidget(_row(_label("Enchant", wrap=False), self.enchant, _label(g.enchant_note(opt, ed), "muted", wrap=False)))
        self.rolls: list[tuple[QComboBox, QLineEdit, QLabel]] = []
        if c._truthy(opt.get("roll_count")):
            group = QFrame()
            group.setObjectName("gelines")
            rolls_lines = QVBoxLayout(group)
            rolls_lines.setContentsMargins(10, 8, 10, 8)
            rolls_lines.addWidget(_label(f"<b>Random rolls</b> {r.muted(html.escape(g.rolls_note(opt)))}", rich=True))
            for index, roll in enumerate(ed["rolls"]):
                stat = QComboBox()
                stat.setAccessibleName(f"roll {index + 1}")
                for value, words in g.roll_choices(opt):
                    stat.addItem(words, value)
                chosen = g.roll_option(opt, roll.get("stat") if roll else None)
                stat.setCurrentIndex(max(0, stat.findData(c.esc_text(roll.get("stat"))) if roll and chosen else 0))
                value = QLineEdit(c.field_text(roll.get("value")) if roll else "")
                value.setAccessibleName(f"roll {index + 1} value")
                value.setFixedWidth(110)
                value.setEnabled(chosen is not None)
                unit = _label("%" if chosen and c._truthy(chosen.get("percent")) else "", "muted", wrap=False)
                stat.activated.connect(lambda _i, stat=stat, value=value, unit=unit: self._roll_chosen(opt, stat, value, unit))
                rolls_lines.addWidget(_row(stat, value, unit))
                self.rolls.append((stat, value, unit))
            lines.addWidget(group)
        else:
            lines.addWidget(_label(f"{name} rolls no random stats.", "muted"))
        group = QFrame()
        group.setObjectName("gelines")
        skill_lines = QVBoxLayout(group)
        skill_lines.setContentsMargins(10, 8, 10, 8)
        skill_lines.addWidget(_label(f"<b>Skill options</b> {r.muted(html.escape(g.skills_note(opt, ed)))}", rich=True))
        self.skill_rows: list[tuple[QComboBox, QComboBox]] = []
        groups = g.skill_groups(opt)
        top = int(c.js_number(r._dict(opt.get("skills")).get("max_level")) or 0)
        for index, (skill_name, level) in enumerate(ed["skills"]):
            skill = QComboBox()
            skill.setAccessibleName(f"skill option {index + 1}")
            skill.addItem("— skill —", "")
            for heading, names in groups:
                skill.addItem(heading, None)
                skill.model().item(skill.count() - 1).setEnabled(False)
                for each in names:
                    skill.addItem("  " + each, each)
            found = skill.findData(skill_name) if skill_name else -1
            skill.setCurrentIndex(found if found >= 0 else 0)
            levels = QComboBox()
            levels.setAccessibleName(f"skill option {index + 1} level")
            for step in range(1, top + 1):
                levels.addItem(f"+{step}", step)
            levels.setCurrentIndex(max(0, levels.findData(int(c.js_number(level))) if c.js_number(level) == c.js_number(level) else 0))
            drop = _button("×", lambda index=index: self._drop_skill(opt, index))
            drop.setToolTip("remove this skill option")
            skill_lines.addWidget(_row(skill, levels, drop))
            self.skill_rows.append((skill, levels))
        add = _button("Add a skill option", lambda: self._add_skill(opt))
        add.setEnabled(g.used(ed) < g.slots(opt, ed["enchant"]))
        skill_lines.addWidget(_row(add))
        lines.addWidget(group)
        self.note = QLineEdit(ed["note"])
        self.note.setMaxLength(200)
        self.note.setPlaceholderText("e.g. warehouse, second tab")
        self.note.setFixedWidth(320)
        self.note.setAccessibleName("Note")
        lines.addWidget(_row(_label("Note", wrap=False), self.note))
        self.editor_message = _label("", wrap=False)
        lines.addWidget(_row(_button("Save changes" if ed.get("id") else "Add to inventory", lambda: self._save_entry(), "primary"),
                             _button("Cancel", self._close_editor), self.editor_message))
        self.editor_box.addWidget(frame)
        self.editor_opt = opt

    def _collect(self) -> None:
        ed = self.editor
        ed["enchant"] = self.enchant.currentData()
        ed["rolls"] = [({"stat": stat.currentData(), "value": c.field_value(value.text())} if stat.currentData() else None)
                       for stat, value, _unit in self.rolls]
        ed["skills"] = [[skill.currentData() or "", levels.currentData()] for skill, levels in self.skill_rows]
        ed["note"] = self.note.text()

    def _redraw_editor(self, opt: dict) -> None:
        self._collect()
        self._draw_editor(opt)

    def _roll_chosen(self, opt: dict, stat: QComboBox, value: QLineEdit, unit: QLabel) -> None:
        chosen = g.roll_option(opt, stat.currentData())
        value.setEnabled(chosen is not None)
        value.setText(c.field_text(chosen.get("min")) if chosen else "")
        unit.setText("%" if chosen and c._truthy(chosen.get("percent")) else "")

    def _add_skill(self, opt: dict) -> None:
        self._collect()
        self.editor["skills"].append(["", 1])
        self._draw_editor(opt)

    def _drop_skill(self, opt: dict, index: int) -> None:
        self._collect()
        del self.editor["skills"][index]
        self._draw_editor(opt)

    def _close_editor(self) -> None:
        self.editor = None
        _clear(self.editor_box)

    def _save_entry(self) -> None:
        self._collect()
        why = g.problem(self.editor)
        if why:
            self.editor_message.setText(why)
            return
        path, body = g.save_body(self.key, self.editor)
        if self.requests is not None:
            self.requests.post(f"entry:{self.key}", path, body)

    # ------------------------------------------------------------------ the app's answers
    def _replied(self, name: str, answer) -> None:
        kind, _, rest = name.partition(":")
        if kind == "characters" and rest == str(self.visits):
            self._draw([x for x in answer if isinstance(x, dict)] if isinstance(answer, list) else [])
        elif rest != self.key:
            return                                        # another character's answer
        elif kind == "inventory":
            self._draw_inventory(answer if isinstance(answer, dict) else {})
            then, self.then_advice = self.then_advice, False
            if then is True and self.advice is not None:
                self.show_advice(self.advice, self.kept)
            elif then:
                self.open_kept()
        elif kind == "kept":
            if self.advice is not None or self._busy():
                return
            kept = answer if isinstance(answer, dict) else None
            if kept and c._truthy(kept.get("advice")):
                self.show_advice(kept["advice"], kept)
            else:
                self.run_advice()
        elif kind == "search":
            self._draw_found(answer if isinstance(answer, list) else [])
        elif kind == "options" and isinstance(answer, dict):
            self.editor = g.new_entry(answer, answer.get("slug"), getattr(self, "pending_entry", None))
            self._draw_editor(answer)
            self.scroll.ensureWidgetVisible(self.editor_box.itemAt(0).widget())
        elif kind == "entry":
            self.toast.say("Saved" if self.editor and self.editor.get("id") else "Added")
            self.show_inventory()
        elif kind in ("removed", "titles"):
            if kind == "titles":
                self.toast.say("Saved")
            self.show_inventory()
        elif kind == "genus" and self.genus_editor is not None:
            saved = answer if isinstance(answer, dict) else {}
            self.message.setText("")
            self.genus_revision += 1
            self.inv = saved
            self.advice = self.kept = None
            self._kept(None)
            _clear(self.out)
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(g.GENUS_SAVED))
            self.out.addWidget(note)
            genus = saved.get("genus")
            self.genus_editor.saved(genus if c._truthy(genus) else {})

    def _failed(self, name: str, why: str) -> None:
        kind, _, rest = name.partition(":")
        if kind == "characters":
            self._draw([])
        elif rest != self.key:
            return
        elif kind == "kept":
            if self.advice is None and not self._busy():
                self.run_advice()
        elif kind == "options":
            self.toast.say(why)
        elif kind == "entry" and self.editor is not None:
            self.editor_message.setText(g.save_error(why))
        elif kind == "genus" and self.genus_editor is not None:
            self.genus_editor.not_saved(why)
        elif kind in ("titles", "removed", "search", "inventory"):
            self.toast.say(why)

    def closeEvent(self, event) -> None:
        for worker in (self.requests, self.advising):
            if worker is not None:
                worker.stop()
        super().closeEvent(event)
