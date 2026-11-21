"""My Character's survival options and trained-skill reserves (0.2.441), as pages/character.js's
``mountSurvivalOptions`` and ``mountSkillReserves`` draw them, each closed under its title until opened.

- **Survivability:** whether the crystal boards' HP is kept, its minimum and the current maximum HP; the incoming-damage
  scenarios (hit, incoming DPS, seconds, healing, HP reserve), each with its timed pressure reductions, which can link a
  skill and a supporting effect and assume a cooldown; the outgoing action-time windows; a recorded fight's incoming
  damage (an a2log) and optimized PvP opponents' benchmarks, imported as scenarios. At most eight of each.
- **Retain trained skills and equipped stigmas:** a minimum level for any skill or equipped stigma, and the supporting
  effects of active skills to keep.

Each keeps what is set for the character in the native interface's settings, under the web page's key, and an
optimization sends what they read, as the web page's do. The scenarios' table scrolls sideways in its panel where the
window is narrower than it (the web page's runs past the window's edge).
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Callable

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import character as c
from . import theme
from .chrome import FlowLayout
from .result_windows import GridTable
from .timers_page import Fold

FIELD_WIDTH = 109                                   # a scenario's number fields (``style="width:109px"``)
TIME_WIDTH = 98                                     # a reduction window's times
LEVEL_WIDTH = 92                                    # a reserve's minimum


def style() -> str:
    """The panels' fields, boxes and notes, beside the page's own look."""
    colors = theme.COLORS
    return f"""
    QGroupBox#fieldset {{ border: 1px solid {colors['line2']}; border-radius: 4px; margin-top: 10px;
                          padding: 10px 8px 8px 8px; background: transparent; }}
    QGroupBox#fieldset::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 0 3px;
                                 color: {colors['text']}; }}
    QFrame#reduction {{ border: 1px solid {colors['line2']}; border-radius: 4px; background: transparent; }}
    QFrame#reduction QLabel {{ background: transparent; }}
    QLineEdit:disabled, QComboBox:disabled {{ color: {colors['faint']}; }}
    QLineEdit[readOnly="true"] {{ color: {colors['muted']}; }}
    QLabel#trace {{ color: {colors['muted']}; font-size: 12px; }}
    """


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _plain() -> QWidget:
    box = QWidget()
    box.setObjectName("plain")
    return box


def _number(text: str, name: str, width: int | None = None, placeholder: str = "") -> QLineEdit:
    """A number field (``<input type=number>``): what it holds reads as a number, or as nothing."""
    field = QLineEdit(text)
    field.setCursorPosition(0)                       # its start in view, as a page shows a long value
    field.setAccessibleName(name)
    field.setPlaceholderText(placeholder)
    if width:
        field.setFixedWidth(width)
    return field


def _text(text: str, name: str, width: int | None = None) -> QLineEdit:
    field = QLineEdit(text)
    field.setMaxLength(100)
    field.setCursorPosition(0)
    field.setAccessibleName(name)
    if width:
        field.setFixedWidth(width)
    return field


def _choices(options: list[tuple[str, str]], selected: int, name: str) -> QComboBox:
    box = QComboBox()
    box.setAccessibleName(name)
    for value, words in options:
        box.addItem(words, value)
    box.setCurrentIndex(selected)
    return box


def _button(words: str, action: Callable, enabled: bool = True) -> QPushButton:
    button = QPushButton(words)
    button.setObjectName("small")
    button.setEnabled(enabled)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _pair(words: str, field: QWidget, above: bool = False) -> QWidget:
    """A field after its label (``<label>Name <input></label>``), or under it in a grid's narrow cell."""
    box = _plain()
    line = QVBoxLayout(box) if above else QHBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(3 if above else 6)
    line.addWidget(_label(words, wrap=above))
    line.addWidget(field)
    if not above:
        line.addStretch(1)
    return box


def _changed(field: QLineEdit, then: Callable) -> None:
    """``then`` once a field's edit is done and changed it (a ``change`` event: Enter or leaving the field)."""
    def done():
        if field.isModified():
            field.setModified(False)
            then()
    field.editingFinished.connect(done)


def _value(kind: str, widget: QWidget):
    """A field's value as the web page reads it: a text field's text, a number field's number (or nothing), a list's
    chosen value, a box's state."""
    if kind == "text":
        return widget.text()
    if kind == "number":
        return c.field_value(widget.text())
    if kind == "list":
        return widget.currentData() if widget.currentIndex() >= 0 else ""
    return widget.isChecked()


def _values(fields: dict[str, tuple[str, QWidget]]) -> dict:
    return {key: _value(kind, widget) for key, (kind, widget) in fields.items()}


def _clear(layout: QLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class Fieldset(QGroupBox):
    """A ``<fieldset>`` with its legend on its line."""

    def __init__(self, legend: str = "", parent: QWidget | None = None):
        super().__init__(legend, parent)
        self.setObjectName("fieldset")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(4, 8, 4, 4)
        self.body.setSpacing(6)


class AutoGrid(QWidget):
    """Cells in as many columns of at least ``least`` px as fit, as wide as each other (``grid-template-columns:
    repeat(auto-fit, minmax(200px, 1fr))``; with ``fill``, ``auto-fill``: the columns there is room for, though fewer
    cells fill them). ``top`` keeps a cell at its own height at the top of its row; else a row's cells are as tall as
    each other."""

    def __init__(self, cells: list[QWidget], least: int = 200, gap: int = 6, fill: bool = False, top: bool = True,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.cells, self.least, self.gap, self.fill, self.top = cells, least, gap, fill, top
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.columns = 0
        self.place(1)

    def place(self, columns: int) -> None:
        columns = max(1, columns if self.fill else min(columns, len(self.cells) or 1))
        if columns == self.columns:
            return
        for cell in self.cells:
            self.grid.removeWidget(cell)
        for index, cell in enumerate(self.cells):
            if self.top:
                self.grid.addWidget(cell, index // columns, index % columns, Qt.AlignTop)
            else:
                self.grid.addWidget(cell, index // columns, index % columns)
        for column in range(max(self.columns, columns)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
            self.grid.setColumnMinimumWidth(column, 0)
        self.columns = columns
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(min(self.least, super().minimumSizeHint().width()), super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place((event.size().width() + self.gap) // (self.least + self.gap))


class SideScroll(QScrollArea):
    """A part wider than the window, scrolled sideways and as tall as what it holds."""

    def __init__(self, inner: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidget(inner)
        inner.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        inner.installEventFilter(self)
        self.fit()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.widget() and event.type() == QEvent.LayoutRequest:
            self.fit()
        return super().eventFilter(watched, event)

    def fit(self) -> None:
        inner = self.widget()
        least = inner.minimumSizeHint().width()
        bar = self.horizontalScrollBar().sizeHint().height() if least > self.viewport().width() else 0
        tall = inner.heightForWidth(max(least, self.viewport().width())) if inner.hasHeightForWidth() else -1
        self.setFixedHeight((tall if tall >= 0 else inner.sizeHint().height()) + bar)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit()


# ------------------------------------------------------------------ trained-skill reserves
class SkillReserves(Fold):
    """Retain trained skills and equipped stigmas (``mountSkillReserves``): ``read`` keeps and returns the minimums, or
    raises ``ValueError`` when a retained level is outside its range; a change keeps them, or says why not."""

    def __init__(self, store, key: str, view: dict, toast: Callable[[str], None], parent: QWidget | None = None):
        super().__init__(c.RESERVES_TITLE, parent=parent)
        self.store, self.key, self.toast = store, key, toast
        saved = c.read_store(store.value(key))
        self.rows = c.reserve_rows(view)
        self.add(_label(c.RESERVES_NOTE, "muted"))
        self.boxes: list[QCheckBox] = []
        self.levels: list[QLineEdit] = []
        self.effects: list[list[tuple[object, QCheckBox]]] = []
        cells = []
        for row in self.rows:
            name = c.esc_text(row.get("name"))
            box = QCheckBox()
            box.setAccessibleName(f"Retain {name}")
            box.setChecked(c.reserve_checked(saved, row))
            box.clicked.connect(lambda _checked=False: self.changed())
            level = _number(c.reserve_level(saved, row), f"Minimum {name} level", LEVEL_WIDTH)
            _changed(level, self.changed)
            chosen = []
            effects = c.reserve_effects(row)
            if effects:
                cell = Fold("Choose effects")
                for effect in effects:
                    check = QCheckBox(c.effect_line(effect))
                    check.setChecked(c.effect_checked(saved, row, effect))
                    check.clicked.connect(lambda _checked=False: self.changed())
                    cell.add(check)
                    chosen.append((effect.get("id"), check))
            else:
                cell = "—"
            self.boxes.append(box)
            self.levels.append(level)
            self.effects.append(chosen)
            cells.append([box, c.reserve_name(row), level, cell])
        self.table = GridTable(c.RESERVES_HEADS, cells, {1: 1, 3: 1}, left=True)
        self.add(self.table)
        try:
            self._read()                              # the minimum fields of the rows not retained turned off
        except ValueError:
            pass                                      # a kept level outside its range: said when it is used

    def _read(self) -> dict:
        plan, retained, through, problem = c.reserve_read(
            self.rows, [box.isChecked() for box in self.boxes], [field.text() for field in self.levels],
            [[effect for effect, check in pairs if check.isChecked()] for pairs in self.effects])
        for index in range(through):
            self.boxes[index].setChecked(retained[index])
            self.levels[index].setEnabled(retained[index])
        if problem:
            raise ValueError(problem)
        return plan

    def read(self) -> dict:
        """The minimums, kept for the character (``save``)."""
        plan = self._read()
        self.store.setValue(self.key, c.store_text(plan))
        return plan

    def changed(self) -> None:
        try:
            self.read()
        except ValueError as problem:
            self.toast(str(problem))


# ------------------------------------------------------------------ survival options
class SurvivalOptions(Fold):
    """Survivability (``mountSurvivalOptions``). ``send(name, path, body)`` posts an import's request through the page,
    whose answer comes back as ``replied(name, answer)`` or ``failed(name, why)``; ``read`` keeps and returns the
    options; ``choose_recording`` and ``choose_results`` ask for the files to import."""

    def __init__(self, store, key: str, view: dict, send: Callable[[str, str, dict], None], toast: Callable[[str], None],
                 parent: QWidget | None = None):
        super().__init__(c.SURVIVAL_TITLE, parent=parent)
        self.store, self.key, self.send, self.toast = store, key, send, toast
        self.choices = c.skill_choices(view)
        self.settings = c.survival_settings(c.read_saved(store.value(key)))
        self.recording = None                         # the a2log chosen, and its encounters with players hit
        self.encounters: list[dict] = []
        self.turn = 0                                 # the newest recording or benchmark batch read
        self.results: list[str] = []                  # the optimized results chosen to import
        self.batch: dict | None = None
        holder = _plain()
        self.content = QVBoxLayout(holder)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(8)
        self.add(holder)
        self.draw()

    # ---------------------------------------------------------------- reading and keeping
    def read(self) -> dict:
        """The options as the fields hold them (``read``)."""
        before = self.settings.get("opponents") if isinstance(self.settings.get("opponents"), list) else []
        actions = [c.read_action(_values(fields)) for fields in self.action_rows]
        opponents = [c.read_pressure(_values(row["fields"]), [_values(r) for r in row["reductions"]],
                                     before[index] if index < len(before) else None)
                     for index, row in enumerate(self.pressure_rows)]
        self.settings = c.read_survival(self.preserve.isChecked(), c.field_value(self.floor.text()),
                                        c.field_value(self.current.text()), actions, opponents)
        return self.settings

    def save(self) -> dict:
        """The options read and kept for the character; what an optimization sends."""
        self.read()
        self.keep()
        return self.settings

    def keep(self) -> None:
        """The options kept as they are (``saveState``)."""
        self.store.setValue(self.key, c.store_text(self.settings))

    # ---------------------------------------------------------------- drawing
    def draw(self, open_row: int | None = None) -> None:
        """The panel from the options (``render``); ``open_row``'s reduction windows open."""
        _clear(self.content)
        s = self.settings
        self.content.addWidget(_label(c.SURVIVAL_NOTE, "muted"))
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.preserve = QCheckBox("Preserve current crystal-board HP")
        self.preserve.setChecked(c._truthy(s.get("preserve_hp")))
        self.preserve.clicked.connect(lambda _checked=False: self.save())
        flow.addWidget(self.preserve)
        self.floor = _number(c.field_text(s.get("min_node_hp")), "Minimum crystal-board HP", 150)
        _changed(self.floor, self.save)
        flow.addWidget(_pair("Minimum crystal-board HP", self.floor))
        self.current = _number(c.field_text(s.get("current_hp")), "Current in-game maximum HP (for scenarios)", 150,
                               "Optional")
        _changed(self.current, self.save)
        flow.addWidget(_pair("Current in-game maximum HP (for scenarios)", self.current))
        self.content.addWidget(row)
        self.content.addWidget(_label(c.HITS_NOTE, "muted"))
        self.content.addWidget(self._scenarios(open_row))
        self.content.addWidget(_label(c.REDUCTIONS_NOTE, "muted"))
        self.content.addWidget(self._actions())
        self.content.addWidget(self._recorded())
        self.content.addWidget(self._benchmarks())
        self.add_scenario = _button("Add encounter / opponent scenario", self.add_pressure, len(s["opponents"]) < c.MOST)
        self.content.addWidget(self.add_scenario, 0, Qt.AlignLeft)
        self.content.addWidget(_label(c.SCENARIOS_NOTE, "muted"))

    def _scenarios(self, open_row: int | None) -> SideScroll:
        """The scenarios' table: a row's name (and its imported timed hits), its numbers, its reduction windows."""
        self.pressure_rows: list[dict] = []
        cells = []
        for index, raw in enumerate(self.settings["opponents"]):
            row = raw if isinstance(raw, dict) else {}
            fields: dict[str, tuple[str, QWidget]] = {}
            name = _text(c.name_text(row, "Incoming pressure"), "Encounter / opponent", 150)
            _changed(name, self.save)
            fields["name"] = ("text", name)
            first = _plain()
            column = QVBoxLayout(first)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(name)
            trace = None
            if c._truthy(row.get("damage_trace")):
                trace = _label(c.trace_line(row), "trace")
                trace.setFixedWidth(150)
                column.addWidget(trace)
            line = [first]
            for key, fallback in c.PRESSURE_FIELDS:
                field = _number(c.field_text(c.or_value(row, key, fallback)), key.replace("_", " "), FIELD_WIDTH,
                                "Rest of window" if key == "healing_duration_s" else "")
                if key == "window_s" and c._truthy(row.get("damage_trace")):
                    field.setReadOnly(True)
                    field.setToolTip(c.WINDOW_LOCKED)
                _changed(field, self.save)
                fields[key] = ("number", field)
                line.append(field)
            fold, reductions, add, removes = self._reductions(index, row, open_row == index)
            line.append(fold)
            remove = _button("Remove", lambda index=index: self.remove_pressure(index))
            line.append(remove)
            self.pressure_rows.append({"fields": fields, "reductions": reductions, "fold": fold, "trace": trace,
                                       "add": add, "removes": removes, "remove": remove})
            cells.append(line)
        return SideScroll(GridTable(c.PRESSURE_HEADS, cells, {8: 1}, left=True))

    def _reductions(self, index: int, row: dict, opened: bool) -> tuple[Fold, list[dict], QPushButton, list[QPushButton]]:
        """A scenario's timed pressure reductions, under "n assumed windows": their fields, Add window and each one's
        Remove window."""
        fold = Fold(f"{c.windows_count(row)} assumed windows", opened)
        rows, removes = [], []
        windows = c._list(row.get("reductions"))
        for number, raw in enumerate(windows):
            w = raw if isinstance(raw, dict) else {}
            box = QFrame()
            box.setObjectName("reduction")
            box.setMinimumWidth(220)
            lines = QVBoxLayout(box)
            lines.setContentsMargins(8, 6, 8, 6)
            lines.setSpacing(4)
            fields: dict[str, tuple[str, QWidget]] = {}
            name = _text(c.name_text(w, "Assumed reduction"), "Name", 170)
            _changed(name, self.save)
            fields["name"] = ("text", name)
            kind = _choices([(k, c.cap(k)) for k in c.REDUCTION_KINDS],
                            next((i for i, k in enumerate(c.REDUCTION_KINDS) if w.get("kind") == k), 0), "Type")
            kind.activated.connect(lambda _i: self.save())
            fields["kind"] = ("list", kind)
            link = self._link(w, fields, actions_only=False)
            for words, key in (("Name", "name"), ("Type", "kind")):
                lines.addWidget(_pair(words, fields[key][1]))
            for words, key in (("Retain skill", "skill_id"), ("Minimum trained level", "min_trained"),
                               ("Retain supporting effect", "effect_id"), ("Assumed effective cooldown (s)", "cooldown_s")):
                lines.addWidget(_pair(words, link[key]))
            for key, words, fallback in c.REDUCTION_TIMES:
                field = _number(c.field_text(c.or_value(w, key, fallback)), words, TIME_WIDTH)
                _changed(field, self.save)
                fields[key] = ("number", field)
                lines.addWidget(_pair(words, field))
            remove = _button("Remove window", lambda index=index, number=number: self.remove_reduction(index, number))
            lines.addWidget(remove)
            fold.add(box)
            rows.append(fields)
            removes.append(remove)
        add = _button("Add window", lambda index=index: self.add_reduction(index), c.windows_count(row) < c.MOST)
        fold.add(add)
        return fold, rows, add, removes

    def _link(self, w: dict, fields: dict, actions_only: bool) -> dict[str, QWidget]:
        """A window's link: its skill, minimum trained level, supporting effect and assumed cooldown (off while no skill is
        linked); choosing another skill starts its effect, cooldown and reserve afresh."""
        options, selected = c.skill_options(self.choices, w.get("skill_id"), actions_only)
        skill = _choices(options, selected, "Retain active skill / stigma" if actions_only else "Retain skill")
        unlinked = w.get("skill_id") is None
        level = _number(c.field_text(c.or_value(w, "min_trained", 1)), "Minimum trained level", 80)
        level.setEnabled(not unlinked)
        _changed(level, self.save)
        options, selected = c.effect_options(self.choices, w.get("skill_id"), w.get("effect_id"))
        effect = _choices(options, selected, "Retain supporting effect")
        effect.setEnabled(not unlinked)
        effect.activated.connect(lambda _i: self.save())
        cooldown = _number(c.field_text(c.or_value(w, "cooldown_s", "")), "Assumed effective cooldown (s)", 110, "Unknown")
        cooldown.setEnabled(not unlinked)
        _changed(cooldown, self.save)
        fields.update(skill_id=("list", skill), min_trained=("number", level), effect_id=("list", effect),
                      cooldown_s=("number", cooldown))
        skill.currentIndexChanged.connect(lambda _i: self._relinked(fields))
        return {"skill_id": skill, "min_trained": level, "effect_id": effect, "cooldown_s": cooldown}

    def _relinked(self, fields: dict) -> None:
        """Another skill linked (``root.onchange`` on a link's skill): its effects, no effect or cooldown yet, the reserve
        off, the minimum within the skill's range."""
        chosen = _value("list", fields["skill_id"][1])
        effect, level, cooldown = fields["effect_id"][1], fields["min_trained"][1], fields["cooldown_s"][1]
        options, selected = c.effect_options(self.choices, chosen, None)
        effect.blockSignals(True)
        effect.clear()
        for value, words in options:
            effect.addItem(words, value)
        effect.setCurrentIndex(selected)
        effect.blockSignals(False)
        effect.setEnabled(bool(chosen))
        level.setEnabled(bool(chosen))
        cooldown.setText("")
        cooldown.setEnabled(bool(chosen))
        if "reserve_cooldown" in fields:
            fields["reserve_cooldown"][1].setChecked(False)
        level.setText(c.clamp_level(c.level_max(self.choices, chosen), level.text()))
        self.save()

    def _actions(self) -> Fieldset:
        """Outgoing action-time assumptions: its note, each window, Add, and the links' note."""
        box = Fieldset(c.ACTION_LEGEND)
        box.body.addWidget(_label(c.ACTION_NOTE, "muted"))
        self.action_rows: list[dict] = []
        self.action_boxes: list[Fieldset] = []
        self.action_removes: list[QPushButton] = []
        for index, raw in enumerate(self.settings["action_windows"]):
            w = raw if isinstance(raw, dict) else {}
            window = Fieldset(f"Action-time window {index + 1}")
            fields: dict[str, tuple[str, QWidget]] = {}
            name = _text(c.name_text(w, "Tactical time"), "Name")
            _changed(name, self.save)
            fields["name"] = ("text", name)
            for key, words in (("start_s", "Start (s)"), ("duration_s", "Duration (s)")):
                field = _number(c.field_text(c.or_value(w, key, 0)), words)
                _changed(field, self.save)
                fields[key] = ("number", field)
            link = self._link(w, fields, actions_only=True)
            reserve = QCheckBox("Reserve cooldown in rotation")
            reserve.setChecked(c._truthy(w.get("reserve_cooldown")))
            reserve.clicked.connect(lambda _checked=False: self.save())
            fields["reserve_cooldown"] = ("box", reserve)
            remove = _button("Remove window", lambda index=index: self.remove_action(index))
            cells = [_pair("Name", name, True), _pair("Start (s)", fields["start_s"][1], True),
                     _pair("Duration (s)", fields["duration_s"][1], True),
                     _pair("Retain active skill / stigma", link["skill_id"], True),
                     _pair("Minimum trained level", link["min_trained"], True),
                     _pair("Retain supporting effect", link["effect_id"], True),
                     _pair("Assumed effective cooldown (s)", link["cooldown_s"], True), reserve, remove]
            window.body.addWidget(AutoGrid(cells))
            box.body.addWidget(window)
            self.action_rows.append(fields)
            self.action_boxes.append(window)
            self.action_removes.append(remove)
        self.add_window = _button("Add action-time window", self.add_action, len(self.settings["action_windows"]) < c.MOST)
        box.body.addWidget(self.add_window, 0, Qt.AlignLeft)
        box.body.addWidget(_label(c.ACTION_LINKS_NOTE, "muted"))
        return box

    def _recorded(self) -> Fieldset:
        """Import recorded incoming damage: the a2log chosen, then its encounters and recipients."""
        box = Fieldset(c.RECORDED_LEGEND)
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(_button("Choose file", self.choose_recording))
        self.recording_name = _label("No file chosen", wrap=False)
        line.addWidget(self.recording_name)
        line.addStretch(1)
        box.body.addWidget(row)
        importer = _plain()
        self.importer = QVBoxLayout(importer)
        self.importer.setContentsMargins(0, 0, 0, 0)
        box.body.addWidget(importer)
        box.body.addWidget(_label(c.RECORDED_NOTE, "muted"))
        if c._truthy(self.recording):
            self._show_import()
        return box

    def _benchmarks(self) -> Fieldset:
        """Import optimized PvP opponent benchmark: the results chosen, the pressure model, estimate, scale and window."""
        box = Fieldset(c.BENCHMARK_LEGEND)
        self.results = []
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        line.addWidget(_button("Choose files", self.choose_results))
        self.results_name = _label("No file chosen", wrap=False)
        line.addWidget(self.results_name)
        line.addStretch(1)
        box.body.addWidget(row)
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.model = _choices(list(c.METHODS), 0, "Pressure model")
        flow.addWidget(_pair("Pressure model", self.model))
        self.estimate = _choices(list(c.METRICS), 0, "Estimate")
        flow.addWidget(_pair("Estimate", self.estimate))
        self.scale = _number("", "Assumed incoming scale", 160, "Required · 1 = unchanged")
        flow.addWidget(_pair("Assumed incoming scale", self.scale))
        self.span = _number("5", "Pressure window (s)", 120)
        flow.addWidget(_pair("Pressure window (s)", self.span))
        self.use_results = _button("Import benchmark scenario", self.import_results)
        flow.addWidget(self.use_results)
        box.body.addWidget(row)
        self.status = _label(c.BENCHMARK_NOTE, "muted")
        box.body.addWidget(self.status)
        return box

    # ---------------------------------------------------------------- adding and removing
    def _redraw(self, open_row: int | None = None) -> None:
        self.keep()
        self.draw(open_row)
        self.button.setChecked(True)

    def add_action(self) -> None:
        self.save()
        if len(self.settings["action_windows"]) >= c.MOST:
            return
        self.settings["action_windows"].append(c.new_action(len(self.settings["action_windows"])))
        self._redraw()

    def remove_action(self, index: int) -> None:
        self.save()
        del self.settings["action_windows"][index]
        self._redraw()

    def add_pressure(self) -> None:
        self.save()
        self.settings["opponents"].append(c.new_pressure(len(self.settings["opponents"])))
        self._redraw()

    def remove_pressure(self, index: int) -> None:
        self.save()
        del self.settings["opponents"][index]
        self._redraw()

    def add_reduction(self, index: int) -> None:
        self.save()
        row = self.settings["opponents"][index]
        if row.get("reductions") is None:
            row["reductions"] = []
        if len(row["reductions"]) >= c.MOST:
            return
        row["reductions"].append(c.new_reduction())
        self._redraw(index)

    def remove_reduction(self, index: int, number: int) -> None:
        self.save()
        del self.settings["opponents"][index]["reductions"][number]
        self._redraw(index)

    # ---------------------------------------------------------------- a recorded fight's incoming damage
    def choose_recording(self) -> None:
        path, _kind = QFileDialog.getOpenFileName(self, "Choose an exported a2log JSON file", "",
                                                  "a2log or JSON (*.json *.a2log);;All files (*)")
        if path:
            self.use_recording(path)

    def use_recording(self, path: str) -> None:
        """An a2log read: its encounters where players were hit, asked of the app."""
        self.recording_name.setText(os.path.basename(path))
        self.turn += 1
        try:
            if os.path.getsize(path) > c.RECORDING_MIB * 1024 * 1024:
                raise ValueError(c.RECORDING_TOO_BIG)
            self._importer_text(c.READING_EVENTS)
            self.recording = json.loads(pathlib.Path(path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as problem:
            self.recording, self.encounters = None, []
            self._importer_text("Import failed: " + str(problem))
            return
        self.send(f"encounters:{self.turn}", "/api/character/pressure", {"log": c.to_json(self.recording)})

    def _importer_text(self, words: str) -> None:
        _clear(self.importer)
        self.importer.addWidget(_label(words))

    def _show_import(self) -> None:
        """The recording's encounters and their recipients, the window, and Import (``showImport``)."""
        _clear(self.importer)
        if not self.encounters:
            self.importer.addWidget(_label(c.NO_RECIPIENTS))
            return
        row = _plain()
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.encounter = QComboBox()
        self.encounter.setAccessibleName("Encounter")
        for e in self.encounters:
            self.encounter.addItem(c.encounter_line(e), c.js_string(e.get("index")))
        flow.addWidget(_pair("Encounter", self.encounter))
        self.recipient = QComboBox()
        self.recipient.setAccessibleName("Recipient")
        flow.addWidget(_pair("Recipient", self.recipient))
        self.seconds = _number("5", "Window seconds", 120)
        flow.addWidget(_pair("Window seconds", self.seconds))
        self.use_pressure = _button("Import pressure scenario", self.import_pressure)
        flow.addWidget(self.use_pressure)
        self.encounter.currentIndexChanged.connect(lambda _i: self._recipients())
        self._recipients()
        self.importer.addWidget(row)

    def _recipients(self) -> None:
        chosen = c.js_number(_value("list", self.encounter))
        found = next((e for e in self.encounters if c._number_is(chosen, e.get("index"))), {})
        self.recipient.clear()
        for p in c._list(found.get("targets")):
            if isinstance(p, dict):
                self.recipient.addItem(c.esc_text(p.get("name")), c.esc_text(p.get("id")))

    def import_pressure(self) -> None:
        self.use_pressure.setEnabled(False)
        self.save()
        if len(self.settings["opponents"]) >= c.MOST:
            self.toast(c.FULL)
            self.use_pressure.setEnabled(True)
            return
        self.send(f"pressure:{self.turn}", "/api/character/pressure", c.to_json({
            "log": self.recording, "segment": c.js_number(_value("list", self.encounter)),
            "target": _value("list", self.recipient), "window_s": c.js_number(c.field_value(self.seconds.text()))}))

    # ---------------------------------------------------------------- optimized PvP opponents' benchmarks
    def choose_results(self) -> None:
        paths, _kind = QFileDialog.getOpenFileNames(self, "Choose exported optimized PvP results", "",
                                                    "JSON (*.json);;All files (*)")
        if paths:
            self.use_results_files(paths)

    def use_results_files(self, paths: list[str]) -> None:
        self.results = list(paths)
        self.results_name.setText(os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files")

    def import_results(self) -> None:
        """Each result chosen read in turn (``/api/character/opponent-pressure``); all added, or none."""
        self.use_results.setEnabled(False)
        self.save()
        sizes = []
        for path in self.results:
            try:
                sizes.append(os.path.getsize(path))
            except OSError:
                sizes.append(0)                       # said when it is read
        problem = c.benchmark_problem(len(self.settings["opponents"]), sizes, c.field_value(self.scale.text()))
        if problem:
            self._results_failed(problem)
            return
        self.turn += 1
        self.batch = {"turn": self.turn, "paths": list(self.results), "index": 0, "scenarios": []}
        self._next_result()

    def _next_result(self) -> None:
        batch = self.batch
        if batch["index"] >= len(batch["paths"]):
            self.batch = None
            self.settings["opponents"].extend(batch["scenarios"])
            self._redraw()
            self.toast(c.benchmarks_imported(len(batch["scenarios"])))
            return
        path = batch["paths"][batch["index"]]
        name = os.path.basename(path)
        self.status.setText(c.reading_opponent(batch["index"], len(batch["paths"]), name))
        try:
            document = json.loads(pathlib.Path(path).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as problem:
            self._results_failed(c.benchmark_failed(name, str(problem)))
            return
        self.send(f"benchmark:{batch['turn']}:{batch['index']}", "/api/character/opponent-pressure", c.to_json({
            "result": document, "metric": self.estimate.currentData(),
            "scale": c.js_number(c.field_value(self.scale.text())),
            "window_s": c.js_number(c.field_value(self.span.text())), "method": self.model.currentData()}))

    def _results_failed(self, why: str) -> None:
        self.batch = None
        self.status.setText("Import failed: " + why)
        self.use_results.setEnabled(True)

    # ---------------------------------------------------------------- the app's answers
    def replied(self, name: str, answer) -> None:
        kind, _, rest = name.partition(":")
        turn, _, index = rest.partition(":")
        answer = answer if isinstance(answer, dict) else {}
        if kind == "encounters" and turn == str(self.turn) and self.recording is not None:
            self.encounters = [e for e in c._list(answer.get("encounters")) if isinstance(e, dict)]
            self._show_import()
        elif kind == "pressure":
            self.settings["opponents"].append(answer.get("scenario"))
            self._redraw()
            self.toast(c.PRESSURE_IMPORTED)
        elif kind == "benchmark" and self.batch is not None and turn == str(self.batch["turn"]):
            self.batch["scenarios"].append(answer.get("scenario"))
            self.batch["index"] += 1
            self._next_result()

    def failed(self, name: str, why: str) -> None:
        kind, _, rest = name.partition(":")
        turn, _, index = rest.partition(":")
        if kind == "encounters" and turn == str(self.turn):
            self.recording, self.encounters = None, []
            self._importer_text("Import failed: " + why)
        elif kind == "pressure":
            self.toast(why)
            if getattr(self, "use_pressure", None) is not None:
                self.use_pressure.setEnabled(True)
        elif kind == "benchmark" and self.batch is not None and turn == str(self.batch["turn"]):
            name = os.path.basename(self.batch["paths"][self.batch["index"]])
            self._results_failed(c.benchmark_failed(name, why))
