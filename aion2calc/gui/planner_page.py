"""The native Build Planner page (0.2.439): Character → Build Planner as the web page shows it (pages/planner.js).

- **Welcome:** the three steps to a best build, each opening its page, and the Discord link; **Hide** keeps it hidden
  (in the native interface's own settings, as the web page keeps it in its browser).
- **Build planner:** the optimized builds, the community's presets and the examples (``/api/planner/presets``), with
  **Refresh presets**; or **Optimize** a class in a mode with its skill, stigma, Daevanion and Ariel crystal budgets,
  which the log server's highest reported totals fill in for the class; **Saved results** opens that page.
- **The chosen build** in its result windows (``result_windows.py``), its stat priority filled in when its job ends.

The builds and classes are read each time the page is shown, and the chosen build with them, as the web page does.
"""
from __future__ import annotations

import pathlib
import urllib.parse

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from . import planner as p
from . import result_windows, theme
from .api import AppApi, Job, Requests
from .chrome import FlowLayout
from .database_page import Window
from .gathering_page import GatheringPage
from .result_windows import Columns, ResultWindows

LOGO = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "logo.png"


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def interface_store() -> QSettings:
    """The native interface's own settings (what the web pages keep in their browser): the user's settings file."""
    return QSettings(QSettings.IniFormat, QSettings.UserScope, "Aion 2 Calc", "native-interface")


class PlannerPage(QWidget):
    """Character → Build Planner. ``show_page`` opens another page of the window, ``open_web`` a page of the web
    interface, ``open_link`` an address in the browser; ``store`` keeps whether the welcome card is hidden."""

    def __init__(self, api: AppApi | None, show_page=None, open_web=None, open_link=None, store: QSettings | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.show_page, self.open_web = api, show_page, open_web
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.store = store if store is not None else interface_store()
        self.state: dict = {"path": None, "choice": None}
        self.results: list[dict] = []
        self.classes: list[str] = []
        self.view: dict | None = None
        self.weight_job, self.budget_turn, self.build_turn = "", 0, 0
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.optimizing = Job(api, self) if api is not None else None
        self.refreshing = Job(api, self) if api is not None else None
        if self.optimizing is not None:
            self.optimizing.logged.connect(lambda log: self.message.setText(p.last(log, "working…")))
            self.optimizing.done.connect(self._optimized)
            self.optimizing.failed.connect(self._optimize_failed)
            self.refreshing.logged.connect(lambda log: self.message.setText(p.last(log, "Checking presets…")))
            self.refreshing.done.connect(self._refreshed)
            self.refreshing.failed.connect(self._refresh_failed)
        self.weights = QTimer(self)
        self.weights.setSingleShot(True)
        self.weights.setInterval(1200)
        self.weights.timeout.connect(self._read_weights)
        self.setStyleSheet(GatheringPage._stylesheet() + result_windows.STYLE + f"""
            QFrame#wstep {{ border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.COLORS['card_a']}, stop:1 {theme.COLORS['card_b']}); }}
            QFrame#wstep QLabel {{ background: transparent; }}
            QLabel#stepNumber {{ color: {theme.COLORS['gold']}; font-family: serif; font-size: 19px; font-weight: 700; }}
            QLabel#stepTitle {{ font-family: serif; font-weight: 700; letter-spacing: 0.8px; }}
            QLabel#heroTitle {{ color: {theme.COLORS['gold']}; font-family: serif; font-size: 22px; letter-spacing: 2px; }}
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#primary:disabled {{ color: {theme.COLORS['faint']}; }}
            """)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.welcome = None if self.store.value("welcome-hidden") == "1" else self._welcome()
        if self.welcome is not None:
            layout.addWidget(self.welcome)
        layout.addWidget(self._planner())
        holder = QWidget()
        holder.setObjectName("plain")
        self.wins = QVBoxLayout(holder)
        self.wins.setContentsMargins(0, 0, 0, 0)
        self.windows = ResultWindows(api, open_web, "planner")
        self.windows.hide()
        self.wins.addWidget(self.windows)
        self.note = _label("", "empty")
        self.note.setAlignment(Qt.AlignCenter)
        self.wins.addWidget(self.note)
        layout.addWidget(holder)
        layout.addStretch(1)

    # ------------------------------------------------------------------ the welcome card
    def _welcome(self) -> Window:
        window = Window("Welcome", p.WELCOME_SUB)
        hide = QPushButton("Hide")
        hide.setObjectName("small")
        hide.clicked.connect(self.hide_welcome)
        window.tool(hide)
        hero = QHBoxLayout()
        hero.setSpacing(18)
        logo = QLabel()
        logo.setFixedSize(92, 92)
        picture = QPixmap(str(LOGO))
        if not picture.isNull():
            logo.setPixmap(picture.scaled(92, 92, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        hero.addWidget(logo, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(4)
        words.addWidget(_label(p.HERO_TITLE, "heroTitle"))
        words.addWidget(_label(p.HERO_TEXT, "muted"))
        join = _label(f"Questions or builds to share? <a href='{p.DISCORD}' style='color: {theme.COLORS['accent']};'>"
                      "Join the Discord</a>.", rich=True)
        join.setTextInteractionFlags(Qt.TextBrowserInteraction)
        join.linkActivated.connect(self.open_link)
        words.addWidget(join)
        hero.addLayout(words, 1)
        window.body.addLayout(hero)
        steps = []
        for numeral, title, text, button_words, page in p.STEPS:
            step = QFrame()
            step.setObjectName("wstep")
            column = QVBoxLayout(step)
            column.setContentsMargins(15, 15, 15, 15)
            column.setSpacing(4)
            column.addWidget(_label(numeral, "stepNumber"))
            column.addWidget(_label(title, "stepTitle"))
            column.addWidget(_label(text, "muted"))
            column.addSpacing(4)
            button = QPushButton(button_words.replace("&", "&&"))
            button.setObjectName("primary")
            button.clicked.connect(lambda _checked=False, page=page: self.show_page(page) if self.show_page else None)
            column.addWidget(button, 0, Qt.AlignLeft)
            column.addStretch(1)
            steps.append(step)
        window.body.addWidget(Columns(steps, 3, 1, 12))
        return window

    def hide_welcome(self) -> None:
        self.store.setValue("welcome-hidden", "1")
        if self.welcome is not None:
            self.welcome.hide()
            self.welcome.deleteLater()
            self.welcome = None

    # ------------------------------------------------------------------ the planner's controls
    def _planner(self) -> Window:
        window = Window("Build planner", p.PLANNER_SUB)
        saved = QPushButton("Saved results")
        saved.setObjectName("small")
        saved.clicked.connect(lambda: self.show_page("history") if self.show_page else None)
        window.head.insertWidget(1, saved)
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        flow.addWidget(_label("Build", "muted", wrap=False))
        self.presets = QComboBox()
        self.presets.setAccessibleName("Build")
        self.presets.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.presets.activated.connect(lambda _index: self.load())
        flow.addWidget(self.presets)
        self.refresh_button = QPushButton("Refresh presets")
        self.refresh_button.setObjectName("small")
        self.refresh_button.clicked.connect(self.refresh_presets)
        flow.addWidget(self.refresh_button)
        flow.addWidget(_label("or optimize:", "muted", wrap=False))
        self.cls = QComboBox()
        self.cls.setAccessibleName("Class to optimize")
        self.cls.activated.connect(lambda _index: self.read_budgets())
        flow.addWidget(self.cls)
        self.mode = QComboBox()
        self.mode.setAccessibleName("Optimization mode")
        for key, words in p.MODES:
            self.mode.addItem(words, key)
        flow.addWidget(self.mode)
        self.fields: dict[str, QLineEdit] = {}
        for key, placeholder, tip in p.FIELDS:
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            field.setAccessibleName(placeholder)
            field.setToolTip(tip)
            field.setFixedWidth(150 if key in ("skill", "stigma") else 180)
            self.fields[key] = field
            flow.addWidget(field)
        self.budget_note = _label("", "muted")
        self.budget_note.setMaximumWidth(520)
        flow.addWidget(self.budget_note)
        self.go = QPushButton("Optimize")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.optimize)
        flow.addWidget(self.go)
        self.message = _label("", "muted")
        self.message.setMaximumWidth(520)
        flow.addWidget(self.message)
        window.body.addWidget(row)
        return window

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event) -> None:
        self.weights.stop()                       # as the web page stops reading the stat priority when left
        super().hideEvent(event)

    def refresh(self) -> None:
        """The builds and classes, then the chosen build and the class's budgets."""
        if self.requests is not None:
            self.requests.get("presets", "/api/planner/presets")
            self.requests.get("classes", "/api/classes")

    def load(self) -> None:
        """The chosen build (``load``): its view, the class and mode it was optimized for, and its windows."""
        self.state["path"] = self.presets.currentData() or ""
        chosen = next((r for r in self.results if r.get("path") == self.state["path"]), None)
        if chosen is not None:
            self.state["choice"] = {"class": chosen.get("class"), "mode": chosen.get("mode")}
        self.weights.stop()
        if not self.state["path"]:
            self._show_note(p.NO_BUILDS)
            return
        self._show_note(p.LOADING)
        self.build_turn += 1
        if self.requests is not None:
            self.requests.get(f"build:{self.build_turn}", "/api/build?path=" + urllib.parse.quote(self.state["path"], safe=""))

    def read_budgets(self) -> None:
        """The class's highest server-reported budgets into its empty fields (``loadPointBudgets``)."""
        self.budget_turn += 1
        for field in self.fields.values():
            field.clear()
        self.budget_note.setText(p.LOADING_BUDGETS)
        if self.requests is not None:
            path = "/api/community?path=" + urllib.parse.quote(p.progression_path(self.cls.currentText()), safe="")
            self.requests.get(f"budgets:{self.budget_turn}:{self.cls.currentText()}", path)

    def _replied(self, name: str, answer) -> None:
        kind, _, rest = name.partition(":")
        if kind == "presets":
            self.results = [r for r in answer if isinstance(r, dict)] if isinstance(answer, list) else []
            self.presets.clear()
            for r in self.results:
                self.presets.addItem(p.preset_line(r), r.get("path"))
            index = self.presets.findData(p.chosen_path(self.results, self.state))
            if index >= 0:
                self.presets.setCurrentIndex(index)
            self.load()
        elif kind == "classes":
            self.classes = [str(c) for c in answer] if isinstance(answer, list) else []
            current = self.cls.currentText()
            self.cls.clear()
            self.cls.addItems(self.classes)
            if current in self.classes:
                self.cls.setCurrentText(current)
            self.read_budgets()
        elif kind == "build":
            if rest != str(self.build_turn) or not isinstance(answer, dict):
                return                            # an older build's answer, overtaken by a newer choice
            self._show_view(answer)
        elif kind == "budgets":
            turn, _, cls = rest.partition(":")
            if turn != str(self.budget_turn):
                return
            try:
                found = p.budgets(answer, cls)
            except ValueError:
                self.budget_note.setText(p.NO_BUDGETS)
                return
            for key, field in self.fields.items():
                if field.text() == "" and found["points"].get(key) is not None:
                    field.setText(str(found["points"][key]))
            self.budget_note.setText(found["note"])
        elif kind == "weights":
            self._weights_answered(rest, answer)

    def _failed(self, name: str, why: str) -> None:
        kind, _, rest = name.partition(":")
        if kind == "build" and rest == str(self.build_turn):
            self._show_note(why, error=True)
        elif kind == "budgets" and rest.partition(":")[0] == str(self.budget_turn):
            self.budget_note.setText(p.NO_BUDGETS)
        elif kind == "weights" and rest == self.weight_job and self.isVisible():
            status = self._weight_label()
            if status is not None:
                status.setText(f"Stat priority refresh delayed: {why}")
            self.weights.start()
        elif kind in ("presets", "classes"):
            self.message.setText(why)

    # ------------------------------------------------------------------ the chosen build
    def _show_note(self, text: str, error: bool = False) -> None:
        self.windows.hide()
        self.note.setText(text)
        self.note.setObjectName("bad" if error else "empty")
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)
        self.note.show()

    def _show_view(self, view: dict) -> None:
        self.view = view
        if view.get("class") in self.classes and view.get("class") != self.cls.currentText():
            self.cls.setCurrentText(str(view.get("class")))
        index = self.mode.findData(p.mode_of(view))
        if index >= 0:
            self.mode.setCurrentIndex(index)
        self.note.hide()
        self.windows.set_view(view)
        self.windows.show()
        self.weight_job = str(view.get("weight_job") or "")
        if self.weight_job:
            self.weights.start()
        self.read_budgets()

    def _weight_label(self) -> QLabel | None:
        return self.windows.findChild(QLabel, "weightStatus")

    def _read_weights(self) -> None:
        if self.weight_job and self.requests is not None and self.isVisible():
            self.requests.get(f"weights:{self.weight_job}", "/api/jobs/" + urllib.parse.quote(self.weight_job, safe=""))

    def _weights_answered(self, job_id: str, job) -> None:
        if job_id != self.weight_job or self.view is None or not isinstance(job, dict):
            return                                # another build was chosen since
        if job.get("status") == "done":
            self.view["weights"] = list(job.get("result") or [])[:12]
            self.view.pop("weight_job", None)
            self.weight_job = ""
            self.windows.set_view(self.view)
            return
        status = self._weight_label()
        if status is not None:
            status.setText(p.weight_status(job))
        if job.get("status") != "error":
            self.weights.start()

    # ------------------------------------------------------------------ the jobs
    def refresh_presets(self) -> None:
        if self.refreshing is None:
            return
        self.refresh_button.setEnabled(False)
        self.refreshing.start("/api/planner/presets/refresh", {})

    def _refreshed(self, result) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh()
        self.message.setText(p.CHECKED if isinstance(result, dict) and result.get("checked") else p.UNCHECKED)

    def _refresh_failed(self, why: str) -> None:
        self.refresh_button.setEnabled(True)
        self.message.setText(why)

    def optimize(self) -> None:
        fields = {key: field.text() for key, field in self.fields.items()}
        problem = p.optimize_problem(fields)
        if problem:
            self.message.setText(problem)
            return
        if self.optimizing is None:
            return
        self.go.setEnabled(False)
        self.optimizing.start("/api/optimize", p.optimize_body(self.cls.currentText(), self.mode.currentData(), fields))

    def _optimized(self, view) -> None:
        self.go.setEnabled(True)
        if isinstance(view, dict):
            self.build_turn += 1                  # a build still loading no longer replaces this one
            self.weights.stop()
            self.view = view
            self.note.hide()
            self.windows.set_view(view)
            self.windows.show()
            self.weight_job = str(view.get("weight_job") or "")
            if self.weight_job:
                self.weights.start()
        self.message.setText(p.done_message(view))

    def _optimize_failed(self, why: str) -> None:
        self.go.setEnabled(True)
        self.message.setText(why)

    def closeEvent(self, event) -> None:
        self.weights.stop()
        self.windows.stop()
        for worker in (self.requests, self.optimizing, self.refreshing):
            if worker is not None:
                worker.stop()
        super().closeEvent(event)

