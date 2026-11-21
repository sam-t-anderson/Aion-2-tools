"""The native Combat Logs page, part 1 (0.2.450): Combat → Combat Logs as pages/combat.js shows it.

- **Its views:** Browse logs, Completed-run speed, Boss progression, Highest observed build points and Personal
  records; and under Browse logs its lists: Community Combat Logs, My Uploads, Saved Logs and My Character Identities.
- **Saved Logs** is drawn here: a fight **analyzed** from an AbyssLogs or A2DIL link (for a party log, as a player
  named) or from a file (an AbyssLogs segment, gzipped or not, aion2calc JSON or CSV), its progress as the job runs,
  then its analysis; the folder every analyzed log is saved in, with **Open folder**; the **log server** shared to,
  with its upload key (only whether one is saved is shown) and who sees the uploads; and the **encounters analyzed**,
  each opened.
- Since 0.2.451 its **recorded encounters by type** and its **upload queue** too (combat_saved.py). The Saved Logs
  list stays as it is while the page lives, its upload going on while another list or view is shown, and its
  recordings, folder, log server and encounters are read again when the page is shown again.
- Since 0.2.452 **My Uploads** and **My Character Identities** too (combat_owned.py), each drawn when first chosen and
  kept like Saved Logs, and read again after an upload, as the web page reads them.
- Since 0.2.453 the community's views too (combat_community.py): **Community Combat Logs**, **Completed-run speed**,
  **Boss progression** and **Highest observed build points**, each drawn when first chosen and kept.
- Since 0.2.454 **Personal records** too (combat_extras.py): the recorded boss defeats, each class's performance, and a
  character's records, attempts, consistency and trends.
- Since 0.2.455 the **featured encounters** too (combat_featured_page.py). Their landing cards are drawn above the views.
  Each encounter's pages (race summary, progress, all reports, rankings and statistics) are shown in place of the views,
  with **← Back to combat logs**.
- Since 0.2.456 an **analyzed encounter's page** too (combat_analysis_page.py), shown in place of the views likewise:
  opened from the encounters analyzed, after a fight is analyzed, and from any page that links to it.
- Since 0.2.457 a **log's own page** too (combat_review_page.py), a recorded or shared log's review, shown in place of
  the views likewise: its encounters, notes and summary with parses. Its other sections open in the web interface for
  now, from a button on it.
"""
from __future__ import annotations

import html
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from . import combat as cb
from . import combat_featured as cf
from . import theme
from .api import AppApi, Job, Requests
from .combat_community import BossProgression, BuildPoints, Community, CommunityLogs, RunSpeed
from .combat_analysis_page import STYLE as ANALYSIS_STYLE, AnalysisPage
from .combat_extras import PersonalRecords
from .combat_featured_page import STYLE as FEATURED_STYLE, FeaturedPage, FeaturedSection
from .combat_owned import Identities, OwnedUploads
from .combat_review_page import ReviewPage
from .combat_saved import RecordedEncounters, UploadQueue, _button, _clear, _head, _label, _row
from .database_page import Window
from .gathering_page import GatheringPage
from .pets_page import Toast
from .pictures import Pictures
from .planner_page import interface_store
from .result_windows import STYLE as RESULT_STYLE, GridTable


class CombatPage(QWidget):
    """Combat Logs. ``open_web`` opens a page of the web interface; ``choose_file``, ``choose_recovery``,
    ``choose_backup`` and ``save_file`` stand in for the file dialogs (a log to analyze, a recovery file or a private
    backup to import, where an export goes), ``confirm`` for the questions and ``open_link`` for the browser; ``store``
    keeps the choices the web page keeps in its browser; ``identity_call`` sends a request to the share server's
    identity routes; ``open_in_web`` opens a page in the web interface itself, even one drawn here (a log's full
    review)."""

    def __init__(self, api: AppApi | None, open_web=None, choose_file=None, open_link=None, parent: QWidget | None = None,
                 store=None, choose_recovery=None, save_file=None, choose_backup=None, confirm=None, identity_call=None,
                 open_in_web=None):
        super().__init__(parent)
        self.api, self.open_web, self.store = api, open_web, store
        self.open_in_web = open_in_web or open_web
        self.choose_file = choose_file or self._ask_file
        self.choose_recovery, self.save_file, self.choose_backup = choose_recovery, save_file, choose_backup
        self.confirm, self.identity_call = confirm, identity_call
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.view, self.list = "community", "community"              # ``st.logsTab``, ``st.listTab``
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.job = Job(api, self) if api is not None else None
        if self.job is not None:
            self.job.logged.connect(lambda log: self._say(cb.last_line(log)))
            self.job.done.connect(self._analyzed)
            self.job.failed.connect(self._say)
        self.setStyleSheet(GatheringPage._stylesheet() + RESULT_STYLE + f"""
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#primary:disabled {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(107, 85, 35, 0.5),
                stop:1 rgba(63, 50, 21, 0.5)); border-color: rgba(233, 203, 128, 0.33); color: rgba(255, 243, 207, 0.5); }}
            QPushButton#small[chosen="true"] {{ font-weight: 700; text-decoration: underline; }}
            QLabel#combatHead {{ color: {theme.COLORS['text']}; font-size: 15px; font-weight: 700; margin-top: 6px; }}
            QLabel#combatMessage {{ color: {theme.COLORS['muted']}; }}
            QLabel#faint {{ color: {theme.COLORS['faint']}; }}
            QLabel#small, QFrame#note QLabel#small {{ color: {theme.COLORS['muted']}; font-size: 12px; }}
            QLabel#empty {{ color: {theme.COLORS['faint']}; padding: 18px; }}
            QLabel#slBadge {{ color: rgba(233, 230, 223, 0.85); border: 1px solid rgba(233, 230, 223, 0.85);
                border-radius: 9px; padding: 0px 6px; }}
            QToolButton#fold {{ color: {theme.COLORS['text']}; font-weight: 600; border: none; background: transparent;
                padding: 2px 0px; }}
            QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35);
                border-radius: 5px; padding: 9px 12px; }}
            QFrame#note QLabel, QFrame#note QCheckBox {{ background: transparent; color: #f1d4a3; }}
            QFrame#note QWidget#plain {{ background: transparent; }}
            QFrame#note QLabel#queueHead {{ color: #f1d4a3; font-size: 15px; font-weight: 700; }}
            QLabel#bucketHead {{ font-weight: 700; margin-top: 4px; }}
            QFrame#rowNote {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35);
                border-radius: 5px; padding: 6px 9px; }}
            QFrame#note QToolButton#fold {{ color: #f1d4a3; }}
            """ + FEATURED_STYLE + ANALYSIS_STYLE + Toast.STYLE)
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
        self.featured_box = QWidget()                    # a featured encounter's or an analysis's page, in place of the views
        self.featured_box.setObjectName("plain")
        self.featured_line = QVBoxLayout(self.featured_box)
        self.featured_line.setContentsMargins(0, 0, 0, 0)
        self.featured_line.setSpacing(14)
        self.featured_line.addWidget(_row(_button(cf.BACK, self.close_featured)))
        self.featured_box.setVisible(False)
        layout.addWidget(self.featured_box)
        self.featured_page: FeaturedPage | None = None   # drawn when first opened and kept
        self.analysis_page: AnalysisPage | None = None   # likewise
        self.review_page: ReviewPage | None = None       # likewise
        self.frame = Window("Combat logs", cb.SUBTITLE)
        layout.addWidget(self.frame)
        layout.addStretch(1)
        self.views = QHBoxLayout()
        self.views.setSpacing(6)
        self.frame.body.addLayout(self.views)
        holder = QWidget()
        holder.setObjectName("plain")
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 6, 0, 0)
        self.body.setSpacing(10)
        self.frame.body.addWidget(holder)
        self.lists_box = QWidget()                       # the lists' tabs, under Browse logs
        self.lists_box.setObjectName("plain")
        self.lists = QHBoxLayout(self.lists_box)
        self.lists.setContentsMargins(0, 0, 0, 0)
        self.lists.setSpacing(6)
        self.body.addWidget(self.lists_box)
        self.saved_panel: QWidget | None = None          # Saved Logs, drawn once and kept
        self.recorded: RecordedEncounters | None = None
        self.queue: UploadQueue | None = None
        self.owned: OwnedUploads | None = None           # My Uploads, drawn when first chosen and kept
        self.identities: Identities | None = None        # My Character Identities, likewise
        self.community_logs: CommunityLogs | None = None  # the community's views, likewise
        self.speed: RunSpeed | None = None
        self.progression: BossProgression | None = None
        self.points: BuildPoints | None = None
        self.records: PersonalRecords | None = None
        self.shared = Community(self.store if self.store is not None else interface_store(), self)
        self.pictures = Pictures(api, self) if api is not None else None
        self.featured = FeaturedSection(api, self.open_featured, self.pictures)   # above the views; nothing when none
        self.frame.body.insertWidget(0, self.featured)
        self.message = None
        self.seen = False
        self.toast = Toast(self)
        self.draw()

    # ---------------------------------------------------------------- the views and lists
    def _tabs(self, layout: QHBoxLayout, tabs, chosen: str, pick, underlined: bool = False) -> None:
        """Tabs as ``.btn small``: the chosen list ``primary`` (log-tabs.js), the chosen view bold and underlined
        (logs-view.js)."""
        _clear(layout)
        for key, words in tabs:
            tab = QPushButton(words)
            tab.setObjectName("primary" if key == chosen and not underlined else "small")
            tab.setProperty("chosen", key == chosen)
            tab.setAccessibleName(words)
            tab.clicked.connect(lambda _checked=False, key=key: pick(key))
            layout.addWidget(tab)
        layout.addStretch(1)

    def draw(self) -> None:
        self._tabs(self.views, cb.VIEWS, self.view, self.show_view, underlined=True)
        community = self.view == "community"
        self.lists_box.setVisible(community)
        if community:
            self._tabs(self.lists, cb.LISTS, self.list, self.show_list)
        for view, key, name, draw in (("community", "community", "community_logs", self._community),
                                      ("community", "saved", "saved_panel", self._saved),
                                      ("community", "owned", "owned", self._owned),
                                      ("community", "identities", "identities", self._identities),
                                      ("speed", None, "speed", lambda: self._view(RunSpeed)),
                                      ("progression", None, "progression", lambda: self._view(BossProgression)),
                                      ("points", None, "points", lambda: self._view(BuildPoints)),
                                      ("extras", None, "records",
                                       lambda: PersonalRecords(self.api, self.shared, self.open_web))):
            shown = self.view == view and (key is None or self.list == key)
            panel = getattr(self, name)
            if shown and panel is None:
                panel = draw()
                setattr(self, name, panel)
                self.body.addWidget(panel)
            if panel is not None:
                panel.setVisible(shown)

    def _community(self) -> CommunityLogs:
        """Community Combat Logs."""
        return self._view(CommunityLogs)

    def _view(self, kind):
        """One of the community's views, sharing the server's facets and the mini-bosses' choice."""
        return kind(self.api, self.shared, self.open_web, self.pictures)

    def _owned(self) -> OwnedUploads:
        """My Uploads."""
        return OwnedUploads(self.api, self.open_web, open_link=self.open_link, confirm=self.confirm,
                            choose_file=self.choose_backup, save_file=self.save_file)

    def _identities(self) -> Identities:
        """My Character Identities."""
        return Identities(self.api, call=self.identity_call, confirm=self.confirm)

    def _uploaded(self) -> None:
        """A report uploaded: My Uploads and the characters it may let you claim read again (``a2log-uploaded``)."""
        for panel in (self.owned, self.identities):
            if panel is not None:
                panel.load()

    def show_view(self, key: str) -> None:
        self.view = key
        self.draw()

    def show_list(self, key: str) -> None:
        self.list = key
        self.draw()

    def _web(self, page: str) -> None:
        if self.open_web is not None:
            self.open_web(page)

    # ---------------------------------------------------------------- the featured encounters
    def open_featured(self, fid, view=None, metric=None) -> None:
        """A featured encounter's page in place of the views (``#/featured/<id>/<view>?metric=``), from its top."""
        if self.featured_page is None:
            self.featured_page = FeaturedPage(self.api, self.open_web, self.pictures, opened=self.open_featured)
            self.featured_line.addWidget(self.featured_page)
        self.featured_page.show_page(fid, view, metric)
        self._in_place(self.featured_page)

    def open_analysis(self, identifier) -> None:
        """An analyzed encounter's page in place of the views (``#/combat-log/analysis/<id>``), from its top."""
        if self.analysis_page is None:
            self.analysis_page = AnalysisPage(self.api, self.open_analysis, self.open_link, self.toast.say, self.pictures)
            self.featured_line.addWidget(self.analysis_page)
        self.analysis_page.show_encounter(identifier)
        self._in_place(self.analysis_page)

    def open_review(self, kind: str, value: str, mode=None, segment=None) -> None:
        """A log's own page in place of the views (``#/combat-log/local/<file>``, ``#/combat-log/shared/<id>``)."""
        if self.review_page is None:
            self.review_page = ReviewPage(self.api, self.open_web, self.open_in_web)
            self.featured_line.addWidget(self.review_page)
        self.review_page.show_log(kind, value, mode, segment)
        self._in_place(self.review_page)

    def _in_place(self, shown: QWidget) -> None:
        for page in (self.featured_page, self.analysis_page, self.review_page):
            if page is not None:
                page.setVisible(page is shown)
        self.frame.setVisible(False)
        self.featured_box.setVisible(True)
        self.scroll.verticalScrollBar().setValue(0)

    def close_featured(self) -> None:
        """Back to the views as they were left, the featured encounters and the encounters analyzed read again
        (``#/combat``)."""
        self.featured_box.setVisible(False)
        self.frame.setVisible(True)
        self.featured.load()
        if self.requests is not None and self.saved_panel is not None:
            self.requests.get("encounters", "/api/encounters")
        self.scroll.verticalScrollBar().setValue(0)

    # ---------------------------------------------------------------- saved logs
    def _saved(self) -> QWidget:
        """Saved Logs: a fight analyzed, where the logs are kept, the log server, the recorded encounters by type, the
        recordings to upload, and the encounters analyzed."""
        panel = QWidget()
        panel.setObjectName("plain")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.ref = QLineEdit()
        self.ref.setPlaceholderText(cb.REF_HINT)
        self.ref.setAccessibleName("AbyssLogs or A2DIL link")
        self.ref.setMinimumWidth(420)
        self.player = QLineEdit()
        self.player.setPlaceholderText(cb.PLAYER_HINT)
        self.player.setAccessibleName("Player")
        self.player.setMaximumWidth(180)
        self.analyze = _button("Analyze", self.import_link, "primary")
        self.message = _label("", "combatMessage", wrap=False)
        layout.addWidget(_row(self.ref, self.player, self.analyze, _label("or", "muted", wrap=False),
                              _button("Choose a file…", self.import_file), self.message))
        note = _label(cb.IMPORT_NOTE, "faint", rich=True)
        note.linkActivated.connect(self.open_link)
        layout.addWidget(note)
        self.folder = _row()
        layout.addWidget(self.folder)
        self.server = _row()
        layout.addWidget(self.server)
        layout.addWidget(_head("Recorded encounters by type"))
        self.recorded = RecordedEncounters(self.api, self.open_web, store=self.store)
        layout.addWidget(self.recorded)
        layout.addWidget(_head("Upload recordings"))
        self.queue = UploadQueue(self.api, self.open_web, open_link=self.open_link, choose_file=self.choose_recovery,
                                 save_file=self.save_file)
        self.queue.uploaded.connect(self._uploaded)
        layout.addWidget(self.queue)
        layout.addWidget(_head("Analyzed encounters"))
        self.encounters_box = QWidget()
        self.encounters_box.setObjectName("plain")
        self.encounters = QVBoxLayout(self.encounters_box)
        self.encounters.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.encounters_box)
        self._read_saved()
        return panel

    def _read_saved(self) -> None:
        if self.requests is not None:
            self.requests.get("logs", "/api/logs")
            self.requests.get("logserver", "/api/logserver")
            self.requests.get("encounters", "/api/encounters")

    def showEvent(self, event) -> None:
        """Saved Logs read again when the page is shown again, as the web page reads them when it opens; an upload
        under way goes on."""
        super().showEvent(event)
        if self.seen and self.saved_panel is not None:
            self._read_saved()
            if self.recorded is not None:
                self.recorded.load(True)
            if self.queue is not None and not self.queue.busy:
                self.queue.load(self.queue.offset)
        if self.seen:
            self._uploaded()
            for view in (self.community_logs, self.speed, self.progression, self.points, self.records):
                if view is not None and view.isVisibleTo(self):
                    view.refresh()                       # the one shown, read again as the web page reads it
            self.featured.load()
            if self.featured_page is not None and self.featured_page.isVisibleTo(self):
                self.featured_page.reload()
            if self.analysis_page is not None and self.analysis_page.isVisibleTo(self):
                self.analysis_page.show_encounter(self.analysis_page.identifier)
            if self.review_page is not None and self.review_page.isVisibleTo(self):
                self.review_page.reload()
        self.seen = True

    def _replied(self, name: str, answer) -> None:
        if name == "logs":
            self._folder(answer)
        elif name == "logserver":
            self._server(answer)
        elif name == "saved-server":
            self.toast.say("Saved")
            if self.requests is not None:
                self.requests.get("logserver", "/api/logserver")
        elif name == "encounters":
            self._encounters(answer)

    def _failed(self, name: str, why: str) -> None:
        if name in ("open-folder", "saved-server"):
            self._say(why)
        elif name == "encounters":
            self._encounters([])
        # the folder and the log server rows stay empty when the app does not say (``.catch(() => {})``)

    def _alive(self, widget) -> bool:
        try:
            return widget is not None and widget.parent() is not None
        except RuntimeError:                              # drawn again since
            return False

    def _folder(self, answer) -> None:
        if not self._alive(getattr(self, "folder", None)):
            return
        folder, files = cb.folder_line(answer)
        line = self.folder.layout()
        _clear(line)
        line.addWidget(_label("Every analyzed log is saved as a file in", "muted", wrap=False))
        line.addWidget(_label(f"<code>{html.escape(folder)}</code>", rich=True, wrap=False))
        line.addWidget(_label(files, "faint", wrap=False))
        line.addWidget(_button("Open folder", self.open_folder))
        line.addStretch(1)

    def _server(self, answer) -> None:
        if not self._alive(getattr(self, "server", None)):
            return
        row = cb.server_row(answer)
        line = self.server.layout()
        _clear(line)
        self.server_url = QLineEdit(row["url"])
        self.server_url.setPlaceholderText(cb.SERVER_HINT)
        self.server_url.setAccessibleName("Log server")
        self.server_url.setMinimumWidth(260)
        self.server_key = QLineEdit()
        self.server_key.setEchoMode(QLineEdit.Password)
        self.server_key.setPlaceholderText(row["key_hint"])
        self.server_key.setAccessibleName("Upload key")
        self.server_key.setMaximumWidth(190)
        self.server_seen = QComboBox()
        for key, words in cb.VISIBILITY:
            self.server_seen.addItem(words, key)
        self.server_seen.setCurrentIndex(self.server_seen.findData(row["visibility"]))
        self.server_seen.setAccessibleName("Who can see your uploads")
        for widget in (_label("Share to a log server:", "muted", wrap=False), self.server_url, self.server_key, self.server_seen,
                       _button("Save", self.save_server)):
            line.addWidget(widget)
        line.addStretch(1)

    def _encounters(self, answer) -> None:
        if not self._alive(getattr(self, "encounters_box", None)):
            return
        _clear(self.encounters)
        rows = cb.encounter_rows(answer)
        if not rows:
            self.encounters.addWidget(_label(cb.NO_ENCOUNTERS, "faint"))
            return
        cells = [[str(r["id"]), r["player"], r["class"], r["boss"], r["source"], r["duration"], r["dps"],
                  _button("Open", lambda identifier=r["id"]: self.open_analysis(identifier))] for r in rows]
        self.encounters.addWidget(GridTable(cb.ENCOUNTER_COLUMNS, cells, {column: 1 for column in range(1, 7)}, right=(5, 6)))

    def _say(self, words: str) -> None:
        if self.message is not None:
            try:
                self.message.setText(words)
            except RuntimeError:
                pass

    def import_link(self) -> None:
        """A fight analyzed from its link (``#imp``)."""
        if self.job is not None:
            self.job.start("/api/encounters/import", cb.import_body(self.ref.text(), self.player.text()))

    def import_file(self) -> None:
        """A fight analyzed from a file (``#file``): an AbyssLogs segment unpacked when it is gzipped."""
        path = self.choose_file()
        if not path:
            return
        try:
            text = cb.read_log_file(path)
        except (OSError, ValueError, EOFError) as problem:
            self._say(str(problem))
            return
        if self.job is not None:
            self.job.start("/api/encounters/import", cb.file_body(text, os.path.basename(path), self.player.text()))

    def _analyzed(self, result) -> None:
        """The fight analyzed: its analysis opened, and the list read again."""
        identifier = (result or {}).get("id") if isinstance(result, dict) else None
        if identifier is not None:
            self.open_analysis(identifier)
        if self.requests is not None and self.saved_panel is not None:
            self.requests.get("encounters", "/api/encounters")

    def open_folder(self) -> None:
        if self.requests is not None:
            self.requests.post("open-folder", "/api/logs/open", {})

    def save_server(self) -> None:
        if self.requests is not None:
            self.requests.post("saved-server", "/api/logserver",
                               cb.server_body(self.server_url.text(), self.server_key.text(), self.server_seen.currentData()))

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, "Analyze a combat log", "", cb.FILE_KINDS)
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.place()

    def closeEvent(self, event) -> None:
        for worker in (self.requests, self.job, self.recorded, self.queue, self.owned, self.identities,
                       self.community_logs, self.speed, self.progression, self.points, self.records, self.featured,
                       self.featured_page, self.analysis_page, self.review_page, self.pictures):
            if worker is not None:
                worker.stop()
        super().closeEvent(event)
