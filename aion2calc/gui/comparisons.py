"""A result's community comparison in the native interface (0.2.500), as pages/results.js's
``renderCommonComparisons`` runs it under the Overview's **Contribute a community comparison**: a separate example of
the result's class and mode generated with common gear and the server's published point budgets, then its anonymous
allocations submitted. Until now it was generated on the web page only.

The comparisons asked for are the window's (``S.commonComparisons``): each class and mode's state, and its
calculation, which goes on while another window or page is shown, as the web page's goes on while another page is. The
words are ``results.py``'s.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import results as r
from .api import Job
from .results import _truthy


#: The room between the comparison's parts: the page's paragraph margin (1em of its 16 px) at the window's 13 px, less
#: the fold's own spacing above the button.
GAP, FOLD_SPACING = 13, 4


class CommonComparisons(QObject):
    """The comparisons asked for while the window runs, by ``class:mode``: each one's state (its status, what it says
    and its result) and the job calculating it, read every ``interval_ms``. ``changed(key)`` follows each change of a
    state."""

    changed = Signal(str)

    def __init__(self, parent: QObject | None = None, interval_ms: int = 1200):
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.states: dict[str, dict] = {}
        self.jobs: dict[str, Job] = {}

    def state(self, key: str) -> dict:
        return self.states.get(key, {})

    def start(self, api, cls: str, mode: str) -> None:
        """A comparison generated for ``cls`` and ``mode`` (the button's press): the calculation started, then read
        (every 1.2 s, as the web page reads it) until it is done or fails. Nothing while that comparison is calculated
        already."""
        key = f"{cls}:{mode}"
        if api is None or self.state(key).get("status") == "running":
            return
        before = self.jobs.pop(key, None)
        if before is not None:                         # its calculation is over: a new one asks afresh
            before.stop()
            before.deleteLater()
        job = self.jobs[key] = Job(api, self, self.interval_ms)
        job.logged.connect(lambda log, key=key: self._set(key, {"status": "running",
                                                                "message": r.comparison_reading(log)}))
        job.done.connect(lambda result, key=key: self._set(key, {**self.state(key), "status": "done",
                                                                 "result": result}))
        job.failed.connect(lambda why, key=key: self._set(key, {"status": "error", "message": why}))
        self._set(key, {"status": "running", "message": r.COMPARISON_STARTING})
        job.start(r.COMPARISON_PATH, {"class": cls, "mode": mode})

    def _set(self, key: str, state: dict) -> None:
        self.states[key] = state
        self.changed.emit(key)


_COMPARISONS: CommonComparisons | None = None


def comparisons() -> CommonComparisons:
    """The window's comparisons, made when first asked for."""
    global _COMPARISONS
    if _COMPARISONS is None:
        _COMPARISONS = CommonComparisons()
    return _COMPARISONS


class ComparisonPanel(QWidget):
    """A result's comparison (``data-common-comparison``): its button, what it says and, once one is saved, its
    figures, drawn again with each change of its state."""

    def __init__(self, api, view: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.api = api
        self.cls, self.mode = r.comparison_key(view if isinstance(view, dict) else {})
        self.key = f"{self.cls}:{self.mode}"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, GAP - FOLD_SPACING, 0, 0)       # a paragraph's room above it, as on the page
        layout.setSpacing(GAP)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton()
        self.button.setObjectName("small")
        self.button.clicked.connect(self.start)
        row.addWidget(self.button)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.figures = QLabel()
        self.figures.setObjectName("comparisonFigures")
        self.figures.setWordWrap(True)
        self.figures.setTextFormat(Qt.PlainText)
        layout.addWidget(self.figures)
        comparisons().changed.connect(self._changed)
        self.render()

    def start(self) -> None:
        comparisons().start(self.api, self.cls, self.mode)

    def _changed(self, key: str) -> None:
        if key == self.key:
            self.render()

    def render(self) -> None:
        state = comparisons().state(self.key)
        words, enabled = r.comparison_button(state)
        self.button.setText(words)
        self.button.setEnabled(enabled)
        message, taken = r.comparison_status(state)
        self.status.setText(message)
        self.status.setVisible(bool(message))                     # the page's empty line takes no room
        name = "comparisonGood" if taken else "comparisonStatus"
        if self.status.objectName() != name:
            self.status.setObjectName(name)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
        result = state.get("result")
        self.figures.setVisible(_truthy(result))
        self.figures.setText("\n".join(r.comparison_lines(result)) if _truthy(result) else "")
