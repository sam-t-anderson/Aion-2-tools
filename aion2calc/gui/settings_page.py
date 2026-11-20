"""The native Settings page (0.2.414): the web Settings page's rows, drawn from ``settings_schema``.

Each control saves its one setting through the app's ``/api/ui`` the moment it changes, as the web page's does,
and the page fills them from the app's answer when it opens. A filter shows one group of rows (the web page's
App, Log server, Overlay ... buttons). A row the native page does not draw in full yet opens the web Settings
page for the rest.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from .api import AppApi
from .settings_schema import GROUPS, ROWS, Bool, Choice


class WrapCheck(QWidget):
    """A checkbox with a label that wraps; a click on the label toggles it too."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.box = QCheckBox()
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.mousePressEvent = lambda _event: self.box.toggle()
        row.addWidget(self.box, 0, Qt.AlignTop)
        row.addWidget(self.label, 1)


class SettingsPage(QWidget):
    """The Settings page. ``api`` is the app's local API (None in tests); ``open_web(page)`` opens a web page."""

    def __init__(self, api: AppApi | None, open_web, parent=None):
        super().__init__(parent)
        self.api, self.open_web = api, open_web
        self.controls: dict[str, QWidget] = {}
        self.row_frames: list[tuple[str, QFrame]] = []
        self.saved: list[tuple[str, object]] = []            # what this page saved, latest last (for its status)
        self._pending: dict[str, QTimer] = {}
        self._latest: dict[str, object] = {}
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 12)
        head = QHBoxLayout()
        heading = QLabel("Settings")
        heading.setObjectName("heading")
        head.addWidget(heading)
        head.addStretch(1)
        self.filter = QComboBox()
        self.filter.addItem("All settings", "")
        for key, title in GROUPS:
            self.filter.addItem(title, key)
        self.filter.currentIndexChanged.connect(self._filter)
        head.addWidget(self.filter)
        outer.addLayout(head)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        outer.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.rows_box = QVBoxLayout(body)
        self.rows_box.setSpacing(10)
        for row in ROWS:
            self._add_row(row)
        self.rows_box.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # ------------------------------------------------------------------ building
    def _add_row(self, row) -> None:
        frame = QFrame()
        frame.setObjectName("setrow")
        frame.setStyleSheet("QFrame#setrow { border-bottom: 1px solid #263048; }")
        line = QHBoxLayout(frame)
        line.setContentsMargins(0, 6, 0, 10)
        title = QLabel(row.title)
        title.setFixedWidth(210)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 700; color: #e8cf8e;")
        line.addWidget(title, 0, Qt.AlignTop)
        cell = QVBoxLayout()
        cell.setSpacing(6)
        for control in row.controls:
            cell.addWidget(self._control(control))
        if row.web:
            note = QLabel("More of this setting is on the web Settings page for now." if row.controls
                          else "This setting is on the web Settings page for now.")
            note.setObjectName("muted")
            button = QPushButton("Open the web Settings page")
            button.clicked.connect(lambda: self.open_web("settings"))
            web = QHBoxLayout()
            web.addWidget(note)
            web.addWidget(button)
            web.addStretch(1)
            cell.addLayout(web)
        line.addLayout(cell, 1)
        self.rows_box.addWidget(frame)
        self.row_frames.append((row.group, frame))

    def _control(self, control) -> QWidget:
        if isinstance(control, Bool):
            widget = WrapCheck(control.label)
            widget.box.toggled.connect(lambda on, key=control.key: self.save(key, bool(on)))
            self.controls[control.key] = widget
            return widget
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        if control.label:
            row.addWidget(QLabel(control.label))
        if isinstance(control, Choice):
            box = QComboBox()
            for value, text in control.options:
                box.addItem(text, value)
            box.currentIndexChanged.connect(lambda _i, key=control.key, b=box, cast=control.cast:
                                            self.save(key, cast(b.currentData())))
        else:
            box = QSpinBox()
            box.setRange(control.minimum, control.maximum)
            if control.unit:
                box.setSuffix(" " + control.unit)
            box.valueChanged.connect(lambda value, key=control.key: self._save_later(key, int(value)))
        row.addWidget(box)
        row.addStretch(1)
        self.controls[control.key] = box
        return holder

    def _filter(self) -> None:
        group = self.filter.currentData()
        for row_group, frame in self.row_frames:
            frame.setVisible(not group or row_group == group)

    # ------------------------------------------------------------------ values
    def start(self) -> None:
        if self.api is None:
            return
        try:
            self.apply(self.api.get("/api/ui"))
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not read the settings: {exc}")

    def apply(self, ui: dict) -> None:
        """Show the app's settings (its answer to ``/api/ui``) without saving them back."""
        self._loading = True
        try:
            for row in ROWS:
                for control in row.controls:
                    widget, value = self.controls[control.key], ui.get(control.key)
                    if isinstance(control, Bool):
                        widget.box.setChecked(value is True)
                    elif isinstance(control, Choice):
                        index = widget.findData(value)
                        if index < 0 and value is not None:
                            index = widget.findData(control.cast(value)) if _castable(control.cast, value) else -1
                        if index >= 0:
                            widget.setCurrentIndex(index)
                    elif isinstance(value, (int, float)) and not isinstance(value, bool):
                        widget.setValue(int(value))
        finally:
            self._loading = False

    def _save_later(self, key: str, value) -> None:
        """A number saves once its field has been still for a moment, not at every keystroke."""
        if self._loading:
            return
        self._latest[key] = value
        timer = self._pending.get(key)
        if timer is None:
            timer = self._pending[key] = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(400)
            timer.timeout.connect(lambda key=key: self.save(key, self._latest[key]))
        timer.start()

    def save(self, key: str, value) -> None:
        """Save one setting through the app's ``/api/ui``, as the web page does."""
        if self._loading:
            return
        self.saved.append((key, value))
        if self.api is None:
            self.status.setText("Saved")
            return
        try:
            self.api.post("/api/ui", {key: value})
            self.status.setText("Saved")
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not save it: {exc}")


def _castable(cast, value) -> bool:
    try:
        cast(value)
        return True
    except (TypeError, ValueError):
        return False
