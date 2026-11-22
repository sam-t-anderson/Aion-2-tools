"""The Pet Genus Insight editor (0.2.442), as genus-editor.js's ``A2GenusEditor.mount`` draws it: the five genera's
tabs with their recorded levels, the chosen genus's Insight level, its ring, its nine analysis slots (a stat and a
value each, cleared one at a time), the lines a read of the game is unsure of marked to check, the Advanced JSON draft,
and Save genus lines. The draft is kept across the tabs until it is saved. My Character's Genus panel holds it (and
Gear & Advice's will).

The words and the draft's rules are functions here, the widget ``GenusEditor`` draws them.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import character as c
from . import theme
from .result_windows import GenusRing
from .results import _whole_number
from .timers_page import Fold

GENERA = ("Cogni", "Fera", "Natura", "Varian", "Special")
INTRO = ("Enter your in-game Pet Genus Insight levels and analysis lines. The official profile does not provide these "
         "allocations. Changes apply to advice and PvE/PvP character optimization after saving and recalculating.")
LEVEL_HINT = "Nine analysis slots · level 10 changes grade chances"
UNUSUAL = ("Some saved entries need review. They are retained in Advanced JSON; correct their genus/slot before "
           "saving.")
RING_KEY = ("Gold: saved line · gray: not recorded · dim: locked. Colors indicate recording status, not in-game "
            "rarity.")
COPY_NOTE = ("Copy numeric values exactly, including % when shown. Defensive lines are retained, but the current advice "
             "model scores damage effects only. Clear occupied slots before lowering the Insight level. Leave a level "
             "blank when unrecorded; 0 means you explicitly recorded level 0.")
JSON_TITLE = "Advanced JSON / repair older entries"
JSON_NOTE = "Apply JSON before changing genus tabs. Nothing is saved until Save genus lines succeeds."
REPAIR = "Older genus data needs repair in Advanced JSON."
KEEP_LINES = "Clear saved lines before removing the recorded level."
BAD_LEVEL = "Use a whole level from 0 to 10."
APPLIED = "Draft applied. Review and save."
NOT_OBJECT = "Use an object keyed by genus."
APPLY_FIRST = "Apply the edited JSON before saving."
SAVING = "Saving genus lines…"
SAVED = "Genus lines saved. Optimize or run advice again to recalculate."
SAVE_FIRST = "Save, or apply the Advanced JSON, before reading from the game."
NARROW = 360                                         # the slots in one column (app.css: a 680 px window)
WIDE = 780                                           # the ring beside the slots (app.css: wider than 1100 px)


def _object(value) -> bool:
    return isinstance(value, dict)


def _lines(group) -> list:
    """``Array.isArray(group.lines) ? group.lines : []``."""
    return group["lines"] if _object(group) and isinstance(group.get("lines"), list) else []


def json_text(value) -> str:
    """``JSON.stringify(value, null, 2)``."""
    return json.dumps(c.to_json(value), indent=2, ensure_ascii=False)


def valid_group(group) -> bool:
    """A genus whose lines can be edited: none yet, or an object whose lines (when it has them) are a list."""
    return group is None or (_object(group) and ("lines" not in group or isinstance(group["lines"], list)))


def unusual(state: dict) -> bool:
    """Whether saved entries need review: a key that is no genus, or a genus, its lines or a line's slot malformed."""
    if any(key not in GENERA for key in state):
        return True
    for genus in GENERA:
        x = state.get(genus)
        if not c._truthy(x):
            continue
        if not _object(x) or ("lines" in x and not isinstance(x["lines"], list)):
            return True
        if isinstance(x.get("lines"), list) and any(not c._truthy(line) or not _object(line)
                                                    or _whole_number(line.get("slot")) is None
                                                    or not 1 <= line["slot"] <= 9 for line in x["lines"]):
            return True
    return False


def tab_text(state: dict, genus: str) -> str:
    level = _whole_number(state.get(genus, {}).get("level")) if _object(state.get(genus)) else None
    return f"{genus} · " + ("Not recorded" if level is None else f"Lv {c.esc_text(state[genus]['level'])}")


def slot_row(group, slot: int) -> dict:
    """The line in a slot (``rows.find(x => x && x.slot === slot) || {}``)."""
    for line in _lines(group if _object(group) else {}):
        if c._truthy(line) and _object(line) and c._number_is(float(slot), line.get("slot")):
            return line
    return {}


def has_line(group, slot: int) -> bool:
    return any(c._truthy(line) and _object(line) and c._number_is(float(slot), line.get("slot"))
               for line in _lines(group if _object(group) else {}))


def slot_state(group, slot: int) -> tuple[bool, str]:
    """Whether a slot is locked, and its hint: the level to enter first, the level it opens at, or what it holds."""
    item = group if c._truthy(group) and _object(group) else {"level": 0, "lines": []}
    unknown = _whole_number(group.get("level") if _object(group) else None) is None
    level = c.js_number(item.get("level"))
    level = 0.0 if level != level else level                       # Number(item.level) || 0
    locked = unknown or slot > level
    hint = ("Enter the Insight level first" if unknown else f"Opens at level {slot}" if locked else
            "Genus damage-line slot" if slot in (4, 7) else "Analysis line")
    return locked, hint


def level_change(state: dict, selected: str, text: str) -> str:
    """The Insight level typed (``data-genus-level``'s change): the draft changed, or why not. Empty removes the
    recorded level (only without lines); else a whole level from 0 to 10."""
    value = c.field_value(text)
    if value == "":
        group = state.get(selected)
        if not _object(group):
            state[selected] = group = {"level": 0, "lines": []}
        if _lines(group):
            return KEEP_LINES
        del state[selected]
        return ""
    number = c.js_number(value)
    if not number.is_integer() or not 0 <= number <= 10:
        return BAD_LEVEL
    group = state.get(selected)
    if not _object(group):
        state[selected] = group = {"level": 0, "lines": []}
    group["level"] = int(number)
    return ""


def apply_read(state: dict, flags: dict, selected: str, read) -> tuple[str, str] | None:
    """A screen read of the Genus Insight panel into the draft (``applyRead``): its genus chosen, the slots it read
    replacing those slots, the lines it is unsure of marked; the genus chosen and what to say, or None when it is
    not a read of a genus."""
    if not _object(read) or read.get("kind") != "genus" or read.get("genus") not in GENERA:
        return None
    selected = read["genus"]
    group = state.get(selected)
    if not _object(group):
        state[selected] = group = {"level": 0, "lines": []}
    lines = [line for line in (read.get("lines") if isinstance(read.get("lines"), list) else [])
             if c._truthy(line) and _object(line) and _whole_number(line.get("slot")) is not None and 1 <= line["slot"] <= 9]
    top = max([line["slot"] for line in lines], default=0)
    level_read = _whole_number(read.get("level")) is not None
    group["level"] = read["level"] if level_read else max(group["level"] if _whole_number(group.get("level")) is not None
                                                          else 0, top)
    kept = [line for line in _lines(group) if c._truthy(line) and _object(line)
            and not any(c._number_is(js(r["slot"]), line.get("slot")) for r in lines)
            and slot_number(line) <= min(c.js_number(group["level"]), 9)]
    group["lines"] = sorted(kept + [{"slot": line["slot"], "stat": c.js_string(line.get("stat")) if c._truthy(line.get("stat")) else "",
                                     "value": "" if line.get("value") is None else c.js_string(line.get("value"))}
                                    for line in lines], key=slot_number)
    flags[selected] = {line["slot"]: line["check"] for line in lines if c._truthy(line.get("check"))}
    checks = len(flags[selected])
    count = len(lines)
    notes = "".join(" " + c.js_string(note) for note in (read.get("notes") if isinstance(read.get("notes"), list) else [])
                    if "level was not read" not in c.js_string(note).lower())
    message = (f"Read from the game: {count} line{'' if count == 1 else 's'} of {selected} Insight"
               + (f", level {c.js_string(read['level'])}" if level_read else
                  f", level not read (set to {c.js_string(group['level'])}: correct it if needed)")
               + (f", {checks} to check (marked)" if checks else "")
               + f". Nothing is saved until you press Save genus lines.{notes}")
    return selected, message


def js(value) -> float:
    return c.js_number(value)


def slot_number(line: dict) -> float:
    """A line's slot as a number (``l.slot`` compared): none reads 0, a line without one NaN."""
    return c.js_number(line["slot"]) if "slot" in line else math.nan


# ------------------------------------------------------------------ the editor
class SlotGrid(QWidget):
    """The nine slots in three columns, or one on a narrow window (``.genus-editor-grid``)."""

    def __init__(self, slots: list[QWidget], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.slots = slots
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.columns = 0
        self.place(3)

    def place(self, columns: int) -> None:
        if columns == self.columns:
            return
        for slot in self.slots:
            self.grid.removeWidget(slot)
        for index, slot in enumerate(self.slots):
            self.grid.addWidget(slot, index // columns, index % columns)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.columns = columns
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(160, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(1 if event.size().width() <= NARROW else 3)


class EditorLayout(QWidget):
    """The ring beside the slots, or above them on a narrow window (``.genus-editor-layout``)."""

    def __init__(self, ring: QWidget, slots: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.ring, self.slots = ring, slots
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.wide = None
        self.place(True)

    def place(self, wide: bool) -> None:
        if wide == self.wide:
            return
        self.grid.removeWidget(self.ring)
        self.grid.removeWidget(self.slots)
        if wide:
            self.grid.addWidget(self.ring, 0, 0, Qt.AlignTop)
            self.grid.addWidget(self.slots, 0, 1, Qt.AlignTop)
            self.grid.setColumnStretch(0, 0)
            self.grid.setColumnStretch(1, 1)
        else:
            self.grid.addWidget(self.ring, 0, 0, Qt.AlignTop)
            self.grid.addWidget(self.slots, 1, 0)
            self.grid.setColumnStretch(1, 0)
        self.wide = wide
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(200, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width() > WIDE)


def style() -> str:
    colors = theme.COLORS
    return f"""
    QFrame#gslot {{ background: {theme.css('inset')}; border: 1px solid {colors['line']}; border-radius: 6px; }}
    QFrame#gslot[sp="true"] {{ border-color: {theme.css('frame_hi')}; background: rgba(233, 203, 128, 0.05); }}
    QFrame#gslot[gflag="true"] {{ border: 2px solid {colors['warn']}; }}
    QFrame#gslot QLabel {{ background: transparent; }}
    QFrame#gslot[locked="true"] QLabel {{ color: {colors['faint']}; }}
    QLabel#gflagText {{ color: {colors['warn']}; }}
    QPlainTextEdit#genusJson {{ background: {colors['bg2']}; border: 1px solid {colors['line2']}; border-radius: 5px; }}
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


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class GenusEditor(QWidget):
    """Manual Genus Insight lines (``A2GenusEditor.mount``). ``save(state)`` asks the app to keep the draft; its answer
    comes back as ``saved(genus)`` or ``not_saved(why)``. ``apply_read(read)`` takes a read of the game's panel into
    the draft; ``is_dirty()`` says whether there are edits not saved."""

    def __init__(self, initial, save: Callable[[dict], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.save_request = save
        self.dirty, self.busy, self.repair = False, False, False
        self.message, self.json_draft = "", None
        self.selected = GENERA[0]
        self.flags: dict[str, dict] = {}
        initial = initial if c._truthy(initial) else {}
        self.state = json.loads(json.dumps(c.to_json(initial)))
        if not _object(self.state):
            self.json_draft, self.state, self.repair, self.message = json_text(self.state), {}, True, REPAIR
        self.json_open = False
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.render()

    # ---------------------------------------------------------------- the draft
    def current(self) -> dict:
        group = self.state.get(self.selected)
        if not _object(group):
            self.state[self.selected] = group = {"level": 0, "lines": []}
        return group

    def update_line(self, slot: int, field: str, value: str) -> None:
        """A stat or value typed (``update``): the draft, the JSON and the ring follow; the slot is no longer marked."""
        self.dirty = True
        item = self.current()
        if not isinstance(item.get("lines"), list):
            item["lines"] = []
        row = next((x for x in item["lines"] if c._truthy(x) and _object(x) and c._number_is(float(slot), x.get("slot"))), None)
        if row is None:
            row = {"slot": slot, "stat": "", "value": ""}
            item["lines"].append(row)
        row[field] = value
        self.json_draft = None
        self.unflag(slot)
        self.json_box.blockSignals(True)
        self.json_box.setPlainText(json_text(self.state))
        self.json_box.blockSignals(False)
        self.ring.set_group(item)

    def unflag(self, slot: int) -> None:
        if self.selected in self.flags:
            self.flags[self.selected].pop(slot, None)
        frame, note = self.slot_frames[slot - 1], self.flag_notes[slot - 1]
        if note is not None:
            note.hide()
            note.deleteLater()
            self.flag_notes[slot - 1] = None
            frame.setProperty("gflag", False)
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def is_dirty(self) -> bool:
        return self.dirty or self.busy or self.repair or self.json_draft is not None

    # ---------------------------------------------------------------- drawing
    def render(self) -> None:
        if hasattr(self, "json_fold"):
            self.json_open = self.json_fold.button.isChecked()
        _clear(self.box)
        state, selected = self.state, self.selected
        group = state.get(selected)
        valid = valid_group(group)
        item = group if c._truthy(group) and _object(group) else {"level": 0, "lines": []}
        self.box.addWidget(_label(INTRO, "muted"))
        tabs = _plain()
        line = QHBoxLayout(tabs)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.tabs: list[QPushButton] = []
        for genus in GENERA:
            tab = QPushButton(tab_text(state, genus))
            tab.setObjectName("tab")
            tab.setCheckable(True)
            tab.setChecked(genus == selected)
            tab.setEnabled(not self.busy)
            tab.clicked.connect(lambda _checked=False, genus=genus: self.choose(genus))
            line.addWidget(tab)
            self.tabs.append(tab)
        line.addStretch(1)
        self.box.addWidget(tabs)
        head = _plain()
        line = QHBoxLayout(head)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)
        line.addWidget(_label(f"{selected} Insight", "section", wrap=False))
        line.addWidget(_label("Insight level", wrap=False))
        self.level = QLineEdit(c.field_text(group.get("level") if _object(group) else None))
        self.level.setPlaceholderText("Not recorded")
        self.level.setAccessibleName("Insight level")
        self.level.setFixedWidth(110)
        self.level.setEnabled(not (self.busy or self.repair or not valid))
        self.level.editingFinished.connect(self._level_done)
        line.addWidget(self.level)
        line.addWidget(_label(LEVEL_HINT, "muted", wrap=False))
        line.addStretch(1)
        self.box.addWidget(head)
        if unusual(state):
            note = QFrame()
            note.setObjectName("note")
            QVBoxLayout(note).addWidget(_label(UNUSUAL))
            self.box.addWidget(note)
        self.ring = GenusRing(selected, group)
        preview = _plain()
        column = QVBoxLayout(preview)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.ring)
        column.addWidget(_label(RING_KEY, "muted"))
        preview.setMaximumWidth(300)
        self.slot_frames, self.flag_notes, self.fields, self.clears = [], [], {}, []
        frames = [self._slot(slot, group, item, valid) for slot in range(1, 10)]
        self.box.addWidget(EditorLayout(preview, SlotGrid(frames)))
        self.box.addWidget(_label(COPY_NOTE, "muted"))
        self.json_fold = Fold(JSON_TITLE, self.json_open)
        self.json_fold.add(_label(JSON_NOTE, "muted"))
        self.json_box = QPlainTextEdit(self.json_draft if self.json_draft is not None else json_text(state))
        self.json_box.setObjectName("genusJson")
        self.json_box.setAccessibleName("Advanced JSON")
        self.json_box.setMinimumHeight(150)
        self.json_box.textChanged.connect(self._json_typed)
        self.json_fold.add(self.json_box)
        self.apply_button = QPushButton("Apply JSON to draft")
        self.apply_button.setObjectName("small")
        self.apply_button.setEnabled(not self.busy)
        self.apply_button.clicked.connect(lambda _checked=False: self.apply_json())
        self.json_fold.add(self.apply_button)
        self.box.addWidget(self.json_fold)
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(12)
        self.save_button = QPushButton("Saving…" if self.busy else "Save genus lines")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(not self.busy)
        self.save_button.clicked.connect(lambda _checked=False: self.save())
        line.addWidget(self.save_button)
        self.status = _label(self.message)
        self.status.setAccessibleName("Genus status")
        line.addWidget(self.status, 1)
        self.box.addWidget(row)

    def _slot(self, slot: int, group, item: dict, valid: bool) -> QFrame:
        row = slot_row(group, slot)
        locked, hint = slot_state(group, slot)
        flag = self.flags.get(self.selected, {}).get(slot)
        frame = QFrame()
        frame.setObjectName("gslot")
        frame.setProperty("sp", slot in (4, 7))
        frame.setProperty("locked", locked)
        frame.setProperty("gflag", bool(flag))
        lines = QVBoxLayout(frame)
        lines.setContentsMargins(12, 10, 12, 10)
        lines.setSpacing(6)
        lines.addWidget(_label(f"Slot {slot}", "strong"))
        note = None
        if flag:
            note = _label(f"Check: {c.esc_text(flag)}", "gflagText")
            lines.addWidget(note)
        lines.addWidget(_label(hint, "muted"))
        off = locked or self.busy or self.repair or not valid
        for field, words, limit, placeholder, text in (
                ("stat", "Stat", 100, f"{self.selected} Damage Boost", c.esc_text(row.get("stat") or "") if c._truthy(row.get("stat")) else ""),
                ("value", "Value", 40, "3.6%", c.esc_text(row.get("value")))):
            pair = _plain()
            line = QHBoxLayout(pair)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            label = _label(words, wrap=False)
            label.setFixedWidth(40)
            line.addWidget(label)
            edit = QLineEdit(text)
            edit.setCursorPosition(0)
            edit.setMaxLength(limit)
            edit.setPlaceholderText(placeholder)
            edit.setAccessibleName(f"Slot {slot} {words.lower()}")
            edit.setEnabled(not off)
            edit.textEdited.connect(lambda value, slot=slot, field=field: self.update_line(slot, field, value))
            line.addWidget(edit, 1)
            lines.addWidget(pair)
            self.fields[(slot, field)] = edit
        clear = QPushButton("Clear slot")
        clear.setObjectName("small")
        clear.setEnabled(not self.busy and has_line(group, slot))
        clear.clicked.connect(lambda _checked=False, slot=slot: self.clear_slot(slot))
        lines.addWidget(clear)                                # across the slot, as the web page's
        self.slot_frames.append(frame)
        self.flag_notes.append(note)
        self.clears.append(clear)
        return frame

    # ---------------------------------------------------------------- actions
    def choose(self, genus: str) -> None:
        self.selected, self.message = genus, ""
        self.render()

    def _level_done(self) -> None:
        if not self.level.isModified():
            return
        self.level.setModified(False)
        problem = level_change(self.state, self.selected, self.level.text())
        if problem:
            self.message = problem
        else:
            self.dirty, self.json_draft = True, None
        self.render()

    def clear_slot(self, slot: int) -> None:
        self.dirty = True
        group = self.current()
        group["lines"] = [x for x in _lines(group) if not c._truthy(x) or not _object(x)
                          or not c._number_is(float(slot), x.get("slot"))]
        self.flags.get(self.selected, {}).pop(slot, None)
        self.json_draft = None
        self.render()

    def _json_typed(self) -> None:
        self.dirty = True
        self.json_draft = self.json_box.toPlainText()

    def apply_json(self) -> None:
        text = self.json_draft if self.json_draft is not None else self.json_box.toPlainText()
        try:
            draft = json.loads(text)
            if not _object(draft):
                raise ValueError(NOT_OBJECT)
        except ValueError as problem:
            self.message = f"JSON could not be applied: {problem}"
            self.render()
            return
        self.dirty, self.state, self.repair, self.json_draft = True, draft, False, None
        self.message = APPLIED
        self.render()

    def save(self) -> None:
        if self.json_draft is not None:
            self.message = APPLY_FIRST
            self.render()
            return
        self.busy, self.message = True, SAVING
        self.render()
        self.save_request(copy.deepcopy(self.state))

    def saved(self, genus) -> None:
        """The app kept the draft: its lines as saved, nothing to check."""
        self.state = json.loads(json.dumps(c.to_json(genus)))
        self.dirty, self.busy = False, False
        self.flags.clear()
        self.message = SAVED
        self.render()

    def not_saved(self, why: str) -> None:
        self.busy, self.message = False, f"Not saved: {why}"
        self.render()

    def apply_read(self, read) -> bool:
        if not _object(read) or read.get("kind") != "genus" or read.get("genus") not in GENERA:
            return False
        if self.busy or self.repair or self.json_draft is not None:
            self.message = SAVE_FIRST
            self.render()
            return False
        self.selected, self.message = apply_read(self.state, self.flags, self.selected, read)
        self.dirty, self.json_draft = True, None
        self.render()
        return True
