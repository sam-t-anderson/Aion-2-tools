"""Saved Logs' recorded encounters by type and its upload queue in the native Combat Logs page (0.2.451), as
saved-logs.js and archive-upload.js draw them.

- **Recorded encounters by type:** every fight of every recording this computer saved, fifty recordings at a time,
  in sections by kind (PvP, world and field bosses, raids, the dungeons, the open world), each newest first with its
  boss's portrait, role, difficulty, length and when it was saved, and **view** opening it at its fight (the log's
  review, on this page since 0.2.457). Filters by boss, kind, role, difficulty and the days saved; mini-bosses are
  hidden unless shown, a choice kept as the community combat logs keep it.
- **Upload recordings:** the saved parts, twenty-five to a page or one recording's parts, put in a queue of at most a
  hundred and uploaded one by one as separate reports to the log server, as the web page does it: each file's
  fingerprint is read first (a file changed since it was queued stops the batch), each upload carries a request ID
  the server answers again rather than storing twice, an upload whose outcome is unknown is retried only when asked,
  and a connection, sign-in or rate-limit refusal stops the batch. The queue's recovery checkpoint (never a key, a
  private link or a credential) is kept by the app, restored, imported or exported as a file, and the results
  exported as a manifest.
"""
from __future__ import annotations

import html
import json
import os

from PySide6.QtCore import QDate, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from . import combat as cb
from . import theme
from .api import AppApi, Requests
from .pictures import Pictures
from .planner_page import LOGO, interface_store
from .result_windows import GridTable
from .results import _dict, _list, _truthy, js_text

#: How long a request may take: an upload waits up to a minute for the log server, and the recordings' list reads
#: every file it has not read before.
TIMEOUT = 120
FACE = 22


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _button(words: str, action, name: str = "small", enabled: bool = True) -> QPushButton:
    button = QPushButton(words)
    button.setObjectName(name)
    button.setEnabled(enabled)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _head(words: str) -> QLabel:
    """A heading (``h3``); its margin would make it a frame, which indents a label's words."""
    label = _label(words, "combatHead")
    label.setIndent(0)
    return label


def _row(*widgets: QWidget, spacing: int = 8) -> QWidget:
    row = QWidget()
    row.setObjectName("plain")
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    for widget in widgets:
        line.addWidget(widget)
    line.addStretch(1)
    return row


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _field(words: str, widget: QWidget) -> QWidget:
    """A filter with its name over it (``label.small.muted``)."""
    box = QWidget()
    box.setObjectName("plain")
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(2)
    column.addWidget(_label(words, "small", wrap=False))
    column.addWidget(widget)
    return box


def _rounded(picture: QPixmap) -> QPixmap:
    """A portrait 22 px square with rounded corners (``.sl-ic``)."""
    ratio = 2.0
    side = round(FACE * ratio)
    scaled = picture.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(side, side)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, side, side), 4 * ratio, 4 * ratio)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    out.setDevicePixelRatio(ratio)
    return out


def _alive(widget) -> bool:
    try:
        return widget is not None and widget.parent() is not None
    except RuntimeError:                                  # drawn again since
        return False


class Section(QWidget):
    """A part that opens and closes under its title (``details``): a kind's encounters with their count
    (``.sl-sec``), or a list's note."""

    def __init__(self, title: str, count: int | None, opened: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        self.button = QToolButton()
        self.button.setObjectName("fold")
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.button.toggled.connect(self.set_open)
        heads = [self.button] + ([_label(f"({count})", "small", wrap=False)] if count is not None else [])
        layout.addWidget(_row(*heads, spacing=4))
        self.body = QWidget()
        self.body.setObjectName("plain")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(4)
        layout.addWidget(self.body)
        self.button.setChecked(opened)
        self.set_open(opened)

    def set_open(self, opened: bool) -> None:
        self.button.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.body.setVisible(opened)


class RecordedEncounters(QWidget):
    """The recorded encounters by type (saved-logs.js). ``open_web`` opens a page of the app (a log's review);
    ``store`` keeps whether mini-bosses are shown; ``pictures`` gives the bosses' portraits."""

    def __init__(self, api: AppApi | None, open_web=None, store=None, pictures: Pictures | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.open_web = open_web
        self.store = store if store is not None else interface_store()
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.pictures = pictures if pictures is not None else (Pictures(api, self) if api is not None else None)
        if self.pictures is not None:
            self.pictures.changed.connect(self._portraits)
        self.encounters: list[dict] = []
        self.offset, self.more, self.loading, self.problem = 0, True, False, None
        self.f = dict(cb.NO_FILTERS)
        self.mini = self.store.value(cb.MINI_KEY) == "1"
        self.faces: list[tuple[QLabel, object]] = []
        self.logo = QPixmap(str(LOGO))
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.results: QVBoxLayout | None = None
        self.load(True)

    def stop(self) -> None:
        for worker in (self.requests, self.pictures):
            if worker is not None:
                worker.stop()

    # ---------------------------------------------------------------- reading
    def load(self, reset: bool) -> None:
        """The first fifty recordings again (``Refresh``), or the next fifty (``Load more recordings``)."""
        if self.loading:
            return
        if reset:
            self.encounters, self.offset, self.more = [], 0, True
        self.loading, self.problem = True, None
        self.render()
        if self.requests is not None:
            self.requests.get("page", cb.sessions_path(self.offset, cb.RECORDED_PAGE))

    def _replied(self, name: str, answer) -> None:
        if name != "page":
            return
        if isinstance(answer, dict) and _truthy(answer.get("error")):       # app.js's api() refuses it
            self._failed(name, js_text(answer["error"]))
            return
        self.offset += cb.RECORDED_PAGE
        self.more = _truthy(_dict(answer).get("has_more"))
        self.encounters.extend(cb.recorded(answer))
        self.loading = False
        self.render()

    def _failed(self, name: str, why: str) -> None:
        if name == "page":
            self.loading = False
            self.problem = why or cb.RECORDED_FAILED
            self.render()

    # ---------------------------------------------------------------- drawing
    def render(self) -> None:
        _clear(self.box)
        self.faces = []
        self.results = None
        if self.problem is not None:
            note = QFrame()
            note.setObjectName("note")
            line = QVBoxLayout(note)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(_label(self.problem))
            self.box.addWidget(note)
            self.box.addWidget(_row(_button("Retry", lambda: self.load(True))))
            return
        self.box.addWidget(_label(cb.RECORDED_NOTE + (cb.RECORDED_LOADED if self.more else ""), "small"))
        if self.encounters:
            self.box.addWidget(self._filters())
        holder = QWidget()
        holder.setObjectName("plain")
        self.results = QVBoxLayout(holder)
        self.results.setContentsMargins(0, 0, 0, 0)
        self.results.setSpacing(2)
        self.box.addWidget(holder)
        self._results()
        tools = [_button("Load more recordings", lambda: self.load(False))] if self.more else []
        tools.append(_button("Refresh", lambda: self.load(True)))
        self.box.addWidget(_row(*tools))

    def _filters(self) -> QWidget:
        """The filters (``filtersHTML``): boss, mini-bosses shown, kind, role, difficulty and the days saved."""
        choices = cb.recorded_choices(self.encounters, self.mini)
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 4, 0, 6)
        line.setSpacing(10)
        widgets = []
        for key, words in (("boss", "Boss"), ("category", "Type"), ("role", "Role"), ("difficulty", "Difficulty")):
            combo = QComboBox()
            combo.setAccessibleName(words)
            combo.addItem("any", "")
            for value, name in choices[key]:
                combo.addItem(name, value)
            combo.setCurrentIndex(max(0, combo.findData(self.f[key])))
            if key == "boss":
                combo.setMinimumWidth(195)
            combo.activated.connect(lambda _index, key=key, combo=combo: self._filter(key, combo.currentData() or ""))
            widgets.append(_field(words, combo))
            if key == "boss":
                mini = QCheckBox("show")
                mini.setAccessibleName("Show mini-bosses")
                mini.setToolTip(cb.MINI_TIP)
                mini.setChecked(self.mini)
                mini.toggled.connect(self.show_mini)
                widgets.append(_field("Mini-bosses", mini))
        for key, words in (("from", "Saved from"), ("to", "to")):
            day = self._date_field(self.f[key], words)
            day.editingFinished.connect(lambda key=key, day=day: self._filter(key, self._day(day)))
            day.calendarWidget().clicked.connect(
                lambda _date, key=key, day=day: QTimer.singleShot(0, lambda: self._filter(key, self._day(day))))
            widgets.append(_field(words, day))
        widgets.append(_button("Clear", self.clear_filters))
        for widget in widgets:
            line.addWidget(widget, 0, Qt.AlignBottom)
        line.addStretch(1)
        return row

    @staticmethod
    def _date_field(day: str, words: str) -> QDateEdit:
        """A day to filter by (``input type="date"``), empty until one is chosen."""
        field = QDateEdit()
        field.setCalendarPopup(True)
        field.setDisplayFormat("yyyy-MM-dd")
        field.setMinimumDate(QDate(2000, 1, 1))
        field.setSpecialValueText(" ")                   # the earliest day stands for none
        field.setAccessibleName(words)
        field.setDate(QDate.fromString(day, "yyyy-MM-dd") if day else field.minimumDate())
        return field

    @staticmethod
    def _day(field: QDateEdit) -> str:
        try:
            return "" if field.date() == field.minimumDate() else field.date().toString("yyyy-MM-dd")
        except RuntimeError:                              # drawn again since
            return ""

    def _filter(self, key: str, value: str) -> None:
        if self.f[key] != value:
            self.f[key] = value
            self._results()

    def show_mini(self, shown: bool) -> None:
        """Mini-bosses shown or hidden, a choice kept (``a2.logs.showMiniBosses``)."""
        self.mini = bool(shown)
        self.store.setValue(cb.MINI_KEY, "1" if self.mini else "0")
        self.render()

    def clear_filters(self) -> None:
        self.f = dict(cb.NO_FILTERS)
        self.render()

    def _results(self) -> None:
        """The sections a filter lets through, the first open; or why there are none."""
        if self.results is None:
            return
        _clear(self.results)
        self.faces = []
        sections = cb.recorded_sections(self.encounters, self.f, self.mini)
        if not self.encounters:
            self.results.addWidget(self._empty(cb.LOADING if self.loading else cb.NO_RECORDED))
        elif not sections:
            self.results.addWidget(self._empty(cb.no_match(self.more)))
        for index, section in enumerate(sections):
            fold = Section(section["title"], section["count"], index == 0)
            cells = [[self._boss(row), self._role(row), row["difficulty"], row["time"],
                      _label(f"<span style='color: {theme.COLORS['muted']};'>{html.escape(row['date'])}</span>", rich=True),
                      _button("view", lambda row=row: self._open(row))] for row in section["rows"]]
            fold.body_layout.addWidget(GridTable(cb.RECORDED_COLUMNS, cells, {0: 3, 1: 1, 2: 1, 4: 2}, left=True, right=(3,)))
            if section["more"]:
                fold.body_layout.addWidget(_label(f"+{section['more']} more in this category.", "small"))
            self.results.addWidget(fold)

    @staticmethod
    def _empty(words: str) -> QLabel:
        label = _label(words, "empty")
        label.setAlignment(Qt.AlignCenter)
        return label

    def _boss(self, row: dict) -> QWidget:
        """A boss with its portrait (the app's logo when it has none)."""
        face = QLabel()
        face.setFixedSize(FACE, FACE)
        face.setPixmap(self._face(row["code"]))
        self.faces.append((face, row["code"]))
        cell = QWidget()
        cell.setObjectName("plain")
        line = QHBoxLayout(cell)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(face)
        line.addWidget(_label(row["boss"], wrap=False))
        return cell

    def _face(self, code) -> QPixmap:
        picture = self.pictures.portrait(code) if self.pictures is not None and code is not None else None
        picture = picture if picture is not None and not picture.isNull() else self.logo
        return _rounded(picture) if not picture.isNull() else QPixmap()

    def _portraits(self) -> None:
        """The portraits that have come since the rows were drawn."""
        for face, code in list(self.faces):
            try:
                face.setPixmap(self._face(code))
            except RuntimeError:
                pass

    @staticmethod
    def _role(row: dict) -> QWidget | str:
        if not row["role"]:
            return ""
        cell = QWidget()
        cell.setObjectName("plain")
        line = QHBoxLayout(cell)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(_label(row["role"], "slBadge", wrap=False))
        return cell

    def _open(self, row: dict) -> None:
        if self.open_web is not None and row["file"]:
            self.open_web(cb.local_page(row["file"], row["segment"]))


class UploadQueue(QFrame):
    """The recordings' upload queue (archive-upload.js). ``open_web`` opens a page of the app (a log's review),
    ``open_link`` an uploaded report in the browser; ``choose_file`` and ``save_file`` stand in for the file dialogs.
    ``uploaded`` says a report was uploaded."""

    uploaded = Signal()

    def __init__(self, api: AppApi | None, open_web=None, open_link=None, choose_file=None, save_file=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("note")
        self.open_web = open_web
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.choose_file = choose_file or self._ask_file
        self.save_file = save_file or self._ask_save
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.rows: list[dict] = []
        self.offset, self.more, self.asked = 0, False, 0
        self.busy = self.cancel = self.retry_unknown = False
        self.message = self.filter = self.kind = self.recording = ""
        self.chosen, self.batch = "public", None
        self.selected: dict[str, dict] = {}
        self.results: dict[str, dict] = {}
        self.batch_run: dict | None = None               # the batch being uploaded: its files, where it is
        self.after_save = None                           # what follows the checkpoint being saved
        self.stopped = False
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.render()
        self.load(0)

    def stop(self) -> None:
        """The page has let go of the queue: no upload starts after the one under way."""
        self.stopped = True
        if self.requests is not None:
            self.requests.stop()

    def _ask(self, name: str, path: str, body: dict | None = None) -> None:
        if self.requests is None:
            return
        if body is None:
            self.requests.get(name, path)
        else:
            self.requests.post(name, path, body)

    # ---------------------------------------------------------------- the page of files
    def load(self, start: int) -> None:
        self.busy = True
        self.asked = start
        self.render()
        self._ask("page", cb.sessions_path(start, cb.UPLOAD_PAGE, self.recording))

    def _page(self, answer) -> None:
        page = _dict(answer)
        self.rows = [r for r in _list(page.get("rows")) if isinstance(r, dict)]
        self.offset, self.more = self.asked, _truthy(page.get("has_more"))
        self.busy = False
        self.render()

    def show_recording(self, archive: str) -> None:
        """One recording's parts, still separate reports (``Show recording``), or every recording again."""
        self.recording, self.filter, self.kind = archive, "", ""
        self.load(0)

    def _visible(self) -> list[dict]:
        return cb.visible_rows(self.rows, self.filter, self.kind)

    # ---------------------------------------------------------------- the queue
    def remember(self) -> None:
        """The queue's recovery checkpoint kept by the app (``remember``)."""
        try:
            value = cb.checkpoint(self.selected, self.results, self.batch, self.chosen)
        except ValueError as problem:
            self.message = "Could not save recovery state: " + str(problem)
            return
        self._ask("save", "/api/upload-queue", value)

    def toggle(self, row: dict, chosen: bool) -> None:
        try:
            if chosen:
                cb.pick(self.selected, self.results, row)
            else:
                self.selected.pop(row.get("file"), None)
        except ValueError as problem:
            self.message = str(problem)
        self.remember()
        self.render()

    def select_eligible(self) -> None:
        """Every finished file on the page put in the queue, up to its limit."""
        try:
            for row in self._visible():
                if not _truthy(row.get("unfinished")):
                    cb.pick(self.selected, self.results, row)
        except ValueError as problem:
            self.message = str(problem)
        self.remember()
        self.render()

    def remove(self, file: str) -> None:
        self.selected.pop(file, None)
        self.remember()
        self.render()

    def clear_queue(self) -> None:
        """The queue emptied; the files and the uploads stay."""
        for row in [*self.rows, *self.selected.values()]:
            row.pop("request_id", None)
            row.pop("fingerprint", None)
        self.selected.clear()
        self.results.clear()
        self.batch, self.retry_unknown = None, False
        self.remember()
        self.message = cb.CLEARED
        self.render()

    def choose_visibility(self, visibility: str) -> None:
        self.chosen = visibility
        self.remember()

    def restore_saved(self) -> None:
        """The queue the app kept (``Restore saved queue``)."""
        self.busy = True
        self.render()
        self._ask("restore", "/api/upload-queue")

    def _restore(self, value) -> None:
        if self.selected:
            raise ValueError("Clear the current queue before restoring another.")
        batch, chosen, selected, results = cb.restored(value)
        self.batch, self.chosen, self.retry_unknown = batch, chosen, False
        self.selected.update(selected)
        self.results.update(results)
        self.message = cb.RESTORED

    def import_recovery(self) -> None:
        """A recovery file restored, then kept (``Import recovery file``)."""
        path = self.choose_file()
        if not path:
            return
        self.busy = True
        self.render()
        try:
            if os.path.getsize(path) > cb.RECOVERY_LIMIT:
                raise ValueError("Recovery file exceeds 256 KiB.")
            with open(path, encoding="utf-8", errors="replace") as handle:
                self._restore(json.loads(handle.read()))
            value = cb.checkpoint(self.selected, self.results, self.batch, self.chosen)
        except (OSError, ValueError) as problem:
            self.message = str(problem)
            self.busy = False
            self.render()
            return
        self._ask("imported", "/api/upload-queue", value)

    def export_recovery(self) -> None:
        try:
            value = cb.checkpoint(self.selected, self.results, self.batch, self.chosen)
        except ValueError as problem:
            self.message = str(problem)
            self.render()
            return
        self._write(cb.RECOVERY_FILE, value)

    def export_results(self) -> None:
        self._write(cb.MANIFEST_FILE, cb.manifest(self.selected, self.results, self.batch))

    def _write(self, name: str, value: dict) -> None:
        path = self.save_file(name)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(value, indent=2, ensure_ascii=False))
        except OSError as problem:
            self.message = str(problem)
            self.render()

    # ---------------------------------------------------------------- the batch
    def run(self) -> None:
        """The queue uploaded (``Upload selected / retry remaining``)."""
        if self.busy or not self.selected:
            return
        visibility = self.visibility.currentData() if _alive(getattr(self, "visibility", None)) else self.chosen
        self.busy, self.cancel = True, False
        self.render()
        self.batch_run = {"files": list(self.selected), "index": 0, "halted": False, "visibility": visibility}
        self._ask("context", "/api/logserver")

    def cancel_batch(self) -> None:
        self.cancel = True
        self.message = cb.CANCELLING
        self.render()

    def _context(self, config) -> None:
        config, visibility = _dict(config), self.batch_run["visibility"]
        if not _truthy(config.get("url")):
            self._end("Set an upload server first.")
        elif self.batch and (self.batch.get("url") != config.get("url") or self.batch.get("visibility") != visibility):
            self._end("Server or visibility changed. Clear the queue before starting a different batch.")
        else:
            self.batch = {**config, "visibility": visibility}
            self._save_then(self._next)

    def _save_then(self, step) -> None:
        """The checkpoint kept before the batch goes on (``await persist()``)."""
        try:
            value = cb.checkpoint(self.selected, self.results, self.batch, self.chosen)
        except ValueError as problem:
            self._end(str(problem))
            return
        self.after_save = step
        self._ask("batch-save", "/api/upload-queue", value)

    def _current(self) -> tuple[str, dict]:
        file = self.batch_run["files"][self.batch_run["index"]]
        return file, self.selected[file]

    def _next(self) -> None:
        run = self.batch_run
        if self.cancel or not self._shown() or run["index"] >= len(run["files"]):
            self._finish()
            return
        file = run["files"][run["index"]]
        self._ask("fingerprint", "/api/sessions?fingerprint=" + cb.encode_component(file))

    def _fingerprint(self, answer) -> None:
        file, row = self._current()
        fingerprint = _dict(answer).get("fingerprint")
        if _truthy(row.get("fingerprint")) and row["fingerprint"] != fingerprint:
            self._end(f"File changed: {cb.queue_label(row)}. Clear the queue and review the new content before uploading.")
            return
        row["fingerprint"] = fingerprint
        status = (self.results.get(file) or {}).get("status")
        if status == "uploaded":                             # its report is on the server: skipped
            self.batch_run["index"] += 1
            self._next()
            return
        if status == "unknown" and not self.retry_unknown:
            self._end(f"Uncertain upload outcome for {cb.queue_label(row)}. Check My uploads, then explicitly allow retry "
                      "if it was not received.")
            return
        if self.cancel or not self._shown():
            self._finish()
            return
        if not _truthy(row.get("request_id")):
            row["request_id"] = cb.request_id()
        self.results[file] = {"status": "uploading", "fingerprint": fingerprint}
        self.message = f"Uploading {cb.queue_label(row)}…"
        self.render()
        self._save_then(self._send)

    def _send(self) -> None:
        file, row = self._current()
        if self.cancel or not self._shown():
            self.results[file] = {"status": "pending", "fingerprint": row.get("fingerprint")}
            self._save_then(self._finish)
            return
        self._ask("share", "/api/sessions/share", cb.upload_body(row, self.batch))

    def _shared(self, answer) -> None:
        file, row = self._current()
        self.results[file] = cb.uploaded(_dict(answer), self.batch, row.get("fingerprint"))
        self.uploaded.emit()
        self._save_then(self._uploaded)

    def _refused(self, why: str) -> None:
        file, row = self._current()
        status, halted = cb.refused(why)
        self.results[file] = {"status": status, "error": why, "fingerprint": row.get("fingerprint")}
        self.batch_run["halted"] = halted
        self._save_then(self._uploaded)

    def _uploaded(self) -> None:
        if self.batch_run["halted"]:
            self._finish()
            return
        self.render()
        self.batch_run["index"] += 1
        self._next()

    def _finish(self) -> None:
        done = sum(1 for file in self.selected if (self.results.get(file) or {}).get("status") == "uploaded")
        self._end(cb.batch_message(done, len(self.selected), self.cancel, bool(self.batch_run and self.batch_run["halted"])))

    def _end(self, message: str) -> None:
        self.message = message
        self.batch_run, self.after_save = None, None
        self.busy = False
        self.render()

    def _shown(self) -> bool:
        """Still on the page (``root.isConnected``): a queue the page has let go of stops before its next upload."""
        return not self.stopped

    # ---------------------------------------------------------------- answers
    def _replied(self, name: str, answer) -> None:
        if isinstance(answer, dict) and _truthy(answer.get("error")):       # app.js's api() refuses it
            self._failed(name, js_text(answer["error"]))
            return
        if name == "page":
            self._page(answer)
        elif name == "restore":
            try:
                self._restore(answer)
            except ValueError as problem:
                self.message = str(problem)
            self.busy = False
            self.render()
        elif name == "imported":
            self.busy = False
            self.render()
        elif name == "context" and self.batch_run is not None:
            self._context(answer)
        elif name == "batch-save" and self.after_save is not None:
            step, self.after_save = self.after_save, None
            step()
        elif name == "fingerprint" and self.batch_run is not None:
            self._fingerprint(answer)
        elif name == "share" and self.batch_run is not None:
            self._shared(answer)

    def _failed(self, name: str, why: str) -> None:
        if name == "page":
            self.rows, self.more, self.message, self.busy = [], False, why, False
            self.render()
        elif name == "save":
            self.message = "Could not save recovery state: " + why
            self.render()
        elif name in ("restore", "imported"):
            self.message, self.busy = why, False
            self.render()
        elif name == "share" and self.batch_run is not None:
            self._refused(why)
        elif name in ("context", "batch-save", "fingerprint") and self.batch_run is not None:
            self._end(why)

    # ---------------------------------------------------------------- drawing
    def render(self) -> None:
        _clear(self.box)
        busy, has = self.busy, bool(self.selected)
        self.box.addWidget(_label(cb.QUEUE_HEAD, "queueHead"))
        self.box.addWidget(_label(cb.QUEUE_NOTE, "small"))
        self.box.addWidget(_row(_button("Restore saved queue", self.restore_saved, enabled=not busy and not has),
                                _button("Import recovery file…", self.import_recovery, enabled=not busy and not has),
                                _button("Export recovery file", self.export_recovery, enabled=not busy and has)))
        if self.recording:
            self.box.addWidget(_row(_label(f"Recording {self.recording} · parts remain separate reports", wrap=False),
                                    _button("All recordings", lambda: self.show_recording(""), enabled=not busy)))
        words = QLineEdit(self.filter)
        words.setPlaceholderText(cb.FILTER_HINT)
        words.setAccessibleName("Filter this page")
        words.setMinimumWidth(230)
        words.setEnabled(not busy)
        words.editingFinished.connect(lambda: self._set_filter(words))
        kind = QComboBox()
        kind.setAccessibleName("Encounter type")
        kind.addItem("All", "")
        for value, name in cb.TYPES.items():
            kind.addItem(name, value)
        kind.setCurrentIndex(max(0, kind.findData(self.kind)))
        kind.setEnabled(not busy)
        kind.activated.connect(lambda _index: self._set_kind(kind.currentData() or ""))
        earlier, later = ("Previous parts", "Next parts") if self.recording else ("Newer", "Older")
        self.box.addWidget(_row(_label("Filter this page", wrap=False), words, _label("Encounter type", wrap=False), kind,
                                _button("Select eligible rows on this page", self.select_eligible, enabled=not busy),
                                _button(earlier, lambda: self.load(max(0, self.offset - cb.UPLOAD_PAGE)),
                                        enabled=not busy and self.offset > 0),
                                _label(f"File slots {self.offset + 1}–{self.offset + cb.UPLOAD_PAGE}", wrap=False),
                                _button(later, lambda: self.load(self.offset + cb.UPLOAD_PAGE), enabled=not busy and self.more)))
        self.box.addWidget(self._table(busy))
        self.visibility = QComboBox()
        self.visibility.setAccessibleName("Visibility")
        for value in cb.QUEUE_VISIBILITY:                       # each shown in the language chosen, sent as it is
            self.visibility.addItem(value, value)
        self.visibility.setCurrentIndex(max(0, self.visibility.findData(self.chosen)))
        self.visibility.setEnabled(not busy)
        self.visibility.activated.connect(lambda _index: self.choose_visibility(self.visibility.currentData()))
        self.box.addWidget(_row(_label(f"{len(self.selected)} selected", wrap=False), _label("Visibility", wrap=False),
                                self.visibility,
                                _button("Upload selected / retry remaining", self.run, "primary", enabled=not busy and has),
                                _button("Cancel after current upload", self.cancel_batch, enabled=busy),
                                _button("Clear queue", self.clear_queue, enabled=not busy),
                                _button("Export upload results", self.export_results, enabled=not busy and bool(self.results))))
        retry = QCheckBox(cb.RETRY_UNKNOWN)
        retry.setChecked(self.retry_unknown)
        retry.setEnabled(not busy)
        retry.toggled.connect(lambda checked: setattr(self, "retry_unknown", bool(checked)))
        self.box.addWidget(retry)
        self.box.addWidget(_label(cb.QUEUE_FOOT, "small"))
        status = _label(self.message)
        status.setAccessibleName("Upload status")
        self.box.addWidget(status)
        for file, row in self.selected.items():
            self.box.addWidget(self._queued(file, row, busy))

    def _table(self, busy: bool) -> QWidget:
        cells = []
        for row in self._visible():
            unfinished = _truthy(row.get("unfinished"))
            pick = QCheckBox()
            pick.setAccessibleName(f"Select {cb.queue_label(row)}")
            pick.setChecked(row.get("file") in self.selected)
            pick.setEnabled(not busy and not unfinished)
            pick.toggled.connect(lambda checked, row=row: self.toggle(row, checked))
            cells.append([pick, self._name(row, busy), js_text(row.get("segments")) if row.get("segments") is not None else "—",
                          "Unfinished checkpoint" if unfinished else "Saved file",
                          _button("Open", lambda row=row: self._open(row), enabled=not busy)])
        table = GridTable(cb.QUEUE_COLUMNS, cells, {1: 3, 2: 1, 3: 1}, left=True)
        if cells:
            return table
        box = QWidget()                                   # the words across the table (``colspan="5"``)
        box.setObjectName("plain")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(table)
        column.addWidget(_label(cb.NO_FILES, "tcell"))
        return box

    def _name(self, row: dict, busy: bool) -> QWidget | str:
        """A file's name, and the recording and part it is (``Show recording``)."""
        archive = row.get("archive") if isinstance(row.get("archive"), dict) else None
        if archive is None:
            return cb.queue_label(row)
        cell = QWidget()
        cell.setObjectName("plain")
        column = QVBoxLayout(cell)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addWidget(_label(cb.queue_label(row)))
        part = f"{js_text(archive.get('id'))} · Part {js_text(archive.get('part'))}"
        column.addWidget(_row(_label(part, "small", wrap=False),
                              _button("Show recording", lambda: self.show_recording(js_text(archive.get("id"))), enabled=not busy)))
        return cell

    def _queued(self, file: str, row: dict, busy: bool) -> QWidget:
        """A queued file's line: Remove, its state, error and warning, and its uploaded report."""
        result = self.results.get(file) or {}
        words = html.escape(cb.status_line(row, result))
        link = cb.safe_link(result.get("url")) if result.get("status") == "uploaded" else ""
        if link:
            words += (f" · <a href='{html.escape(link, quote=True)}' style='color: {theme.COLORS['accent']};'>"
                      "Open uploaded report</a>")
        line = _label(words, rich=True)
        line.linkActivated.connect(self.open_link)
        row = QWidget()                                   # the words take the row's room, wrapping in it
        row.setObjectName("plain")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_button("Remove", lambda: self.remove(file), enabled=not busy), 0, Qt.AlignTop)
        layout.addWidget(line, 1)
        return row

    def _set_filter(self, field: QLineEdit) -> None:
        try:
            text = field.text()
        except RuntimeError:
            return
        if text != self.filter:
            self.filter = text
            self.render()

    def _set_kind(self, kind: str) -> None:
        self.kind = kind
        self.render()

    def _open(self, row: dict) -> None:
        if self.open_web is not None:
            self.open_web(cb.local_page(row.get("file")))

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, "Import a recovery file", "", "Recovery files (*.json)")
        return path

    def _ask_save(self, name: str) -> str:
        path, _kind = QFileDialog.getSaveFileName(self, "Export", name, "JSON (*.json)")
        return path
