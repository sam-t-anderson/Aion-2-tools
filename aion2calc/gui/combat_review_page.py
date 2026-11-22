"""The log review in the native Combat Logs page, part 1 (0.2.457), as combat-review.js draws a log's own page: a
session recorded on this computer (``#/combat-log/local/<file>``) or a log shared on the log server
(``#/combat-log/shared/<id>``). It is shown in place of Combat Logs' views, with **← Back to combat logs**.

Drawn here so far:
- the encounter chosen, by combat mode, run and encounter, and a player or a PvP opponent;
- the PvP and arena match notes, an opponent's records, the heals left out or rebuilt, and the sources;
- the capture's quality, with how a cut fight was joined, and the run timing and boss progression;
- the summary of every player's damage done and taken, healing and deaths, by the metric chosen, with each player's
  parse from the log server's rankings.
- Since 0.2.458 the rate chart, in either style, with the rates and the bosses' HP at any moment of it; the recorder's
  ping; the bosses' remaining HP; and the enemy encounters, any of which narrows the review to it.
- Since 0.2.459 the Table, Timeline and Events views: the events' list with a spreadsheet's column filters, a time and
  an amount range and its sort, a hundred at a time; and the recorded effect timeline, its window chosen, moved or
  scrubbed, its lanes shown, hidden or collapsed, and each effect inspected.
- Since 0.2.460 the abilities and skills: each player's abilities as bars and as a table, their skills' casts with
  cooldown usage, and the cast timeline.
- Since 0.2.461 the casts, buffs and break gauge: the rotation, the buffs and debuffs, the crowd control, the break
  gauge, the boss casts and the buff contribution estimate.
- Since 0.2.462 the player death recaps, each opened with its effects and HP samples.
- Since 0.2.463 the encounter insights, shown with **Encounter insights**; and the automatic encounter context and the
  mapping coverage, folded, the coverage's report exported to a file.
- Since 0.2.464 the matched public comparisons (each player's standings and the run's speed), the encounter's metadata
  (corrected and saved for a recording on this computer), a shared log's report to its server's operator, and a
  recording's upload.
- Since 0.2.465 the comparisons with other logs: a shared log by its link or ID, or an a2log file on this computer, each
  player's DPS against a same-class player chosen in it.
- Since 0.2.466 the character builds: each character's button, their build in place of the review as the official
  profile saved with the log (or a current one looked up), and the class colours' panel (**Class colors**).
- Since 0.2.467 a recording's other parts, listed, opened and combined into an unranked review; the combined review with
  its parts, runs and totals; the other uploads of the same fight, and the log server's combination of them.
- Since 0.2.468 the movement replay (``combat_replay``, ``combat_replay_view``): the fight's positions on the ground
  they covered, played back, paused, rewound or scrubbed at the speed chosen, in the arena's shape chosen.
- Since 0.2.469 the replay's boss casts with their measured areas (``aoe-shapes.json``, read once for the page), the
  appearances, deaths, revives and add hits: drawn under the tokens and listed beside the arena, a row chosen going to
  its time.
- Since 0.2.470 the replay's key, each entry unticked hiding what it names while the log is open; and for a shared log
  the movement of the fight's other recordings, merged by the log server when asked for or when the parses name
  another upload of the fight.
- Since 0.2.473 the live session's review under the Live Meter (``live``, ``A2CombatReview.mount`` with ``live``): given
  each document of the session as the meter reads it (``show_live``, then ``update_live``), it follows the latest
  encounter until another is chosen (**Follow latest encounter**), and has no other parts to list, metadata to save or
  recording to upload.
- Since 0.2.474 an upload's log, as its server gave it to the upload's credential from My Uploads' **Review**
  (``#/combat-log/opened``, ``show_opened``): reviewed with the review's own choices alone, so without other parts,
  metadata to save, an upload, a report or the fight's other recordings.

The replay's Raid Planner file opens in the web interface for now, from a button on the page (for an upload's log, the
web interface's My Uploads, which reviews it there too).
"""
from __future__ import annotations

import html
import math
import os

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QRegularExpression, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import combat_replay as rp
from . import combat_review as cw
from . import combat_records as cr
from . import combat_views as cv
from . import image_health, theme
from .account import TIER_COLOURS
from .account_page import _parse_pill
from .api import AppApi, Requests
from .class_colours import ClassColours
from .combat import safe_link
from .combat_community import _note
from .chrome import FlowLayout
from .combat_review_charts import HP, PingChart, RateChart
from .combat_replay_view import ReplayPanel, merge_row
from .combat_review_views import ContributionBars, FilterPopup, GaugeChart, Placer, Timeline
from .combat_saved import TIMEOUT, Section, _button, _clear, _head, _label
from .database_page import Window
from .pictures import Pictures
from .planner_page import interface_store
from .result_windows import GridTable
from .results import _dict, _list, _truthy, js_text

C = theme.COLORS
NUMBER = r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?"        # what a number field takes (``type="number"``)


def _plain(layout=QVBoxLayout, spacing: int = 0):
    box = QWidget()
    box.setObjectName("plain")
    line = layout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _muted(words: str) -> QLabel:
    return _label(words, "small")


def _tipped(words: str, tip: str) -> QLabel:
    """A cell's words with their tip (``title``)."""
    label = _label(words)
    label.setToolTip(tip)
    return label


def _field_row(words: str, widget: QWidget) -> QWidget:
    """A field with its name before it (``<label>words <input></label>``)."""
    box, line = _plain(QHBoxLayout, 6)
    line.addWidget(_label(words, wrap=False))
    line.addWidget(widget)
    line.addStretch(1)
    return box


def _noted(widget: QWidget) -> QFrame:
    """A part in a note's frame (``.note``), as a ``details`` of the web page's is."""
    frame = QFrame()
    frame.setObjectName("note")
    line = QVBoxLayout(frame)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(widget)
    return frame


class OfficialPictures(QObject):
    """A character's pictures on the official and community hosts (``profileImage``), read off the interface's thread
    and handed over as ``loaded(url, bytes)``; each asked for once, one that cannot be read said so as ``failed(url)``
    (the web page's ``onerror``)."""

    loaded = Signal(str, bytes)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None, read=None):
        super().__init__(parent)
        from .news import _read
        self.read = read or _read
        self._asked: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gui-profile-pictures")

    def ask(self, url: str) -> None:
        if not cw.profile_image(url) or url in self._asked:
            return
        self._asked.add(url)
        try:
            self._pool.submit(self._get, url)
        except RuntimeError:                     # stopped: its window has closed
            pass

    def _get(self, url: str) -> None:
        try:
            data = self.read(url)
        except Exception:                        # noqa: BLE001 - a picture that cannot be read is said so
            data = b""
        if data:
            self.loaded.emit(url, data)
        else:
            self.failed.emit(url)

    def forget(self, url: str) -> None:
        """A picture to be asked for again (Retry images)."""
        self._asked.discard(url)

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def cw_fight() -> dict:
    """This recording's own fight (``ownFight``): no combined fight in view, asked for, or refused."""
    return {"segment": -1, "own": None, "loading": False, "error": ""}


#: A card's edge by its grade (``.cr-profile-card[data-grade=…]``).
GRADE_EDGES = {"Unique": "#f0bf4a", "Legend": "#a46cf0", "Epic": "#a46cf0", "Rare": "#4aa3e6"}


class AutoGrid(QWidget):
    """Widgets in equal columns at least ``least`` wide, as many as fit, fewer when there are fewer widgets
    (``grid-template-columns: repeat(auto-fit, minmax(least, 1fr))``); laid out again as the width changes."""

    def __init__(self, widgets: list[QWidget], least: int, gap: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.widgets, self.least, self.gap, self.columns = widgets, least, gap, 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(gap)
        self.grid.setVerticalSpacing(gap)
        self._place(1)

    def _place(self, columns: int) -> None:
        if columns == self.columns:
            return
        for widget in self.widgets:
            self.grid.removeWidget(widget)
        for column in range(max(self.columns, columns)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, widget in enumerate(self.widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.columns = columns

    def resizeEvent(self, event) -> None:
        fit = max(1, (event.size().width() + self.gap) // (self.least + self.gap))
        self._place(max(1, min(len(self.widgets), fit)))
        super().resizeEvent(event)


LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "logo.png")


def details_view(details: dict, picture) -> QWidget:
    """A recorded character (character-view.js ``details``): the portrait and its lines, then each part's cards.
    ``picture(url, alt, size, height)`` draws a picture (the official one, or the app's copy)."""
    box, column = _plain(spacing=8)
    if "empty" in details:
        column.addWidget(_label(details["empty"]))
        return box
    hero = details["hero"]
    top, line = _plain(QHBoxLayout, 20)
    portrait = picture(hero["image"], hero["alt"], 140, 180)                       # ``.cr-profile-hero > img``
    portrait.setStyleSheet(f"QLabel {{ background: {C['panel']}; border-radius: 8px; color: {C['muted']}; font-size: 24px; }}")
    line.addWidget(portrait)
    words, lines = _plain(spacing=2)
    lines.addStretch(1)                                          # beside the portrait's middle (``align-items: center``)
    lines.addWidget(_label(hero["name"], "combatHead"))
    lines.addWidget(_label("\n".join(hero["lines"])))
    lines.addStretch(1)
    line.addWidget(words, 1)
    column.addWidget(top)
    column.addWidget(_head("Character stats"))
    column.addWidget(stat_grid(details["stats"]))
    for title, key, none in (("Equipment and inventory slots", "gear", "Equipment was not included in this snapshot."),
                             ("Skills, passives and stigmas", "skills", "Skills were not included in this snapshot."),
                             ("Pet and wings", "petwing", "Pet and wings were not included in this snapshot."),
                             ("Daevanion boards", "boards", "Boards were not included in this snapshot.")):
        column.addWidget(_head(title))
        column.addWidget(profile_cards(details[key], none, picture))
        if key == "petwing":
            column.addWidget(_muted(details["genus"]))
    return box


def stat_grid(stats: list) -> QWidget:
    """The stats (``.cr-profile-stats``): each in its box, at least 160 px wide."""
    if not stats:
        return _label("Stats were not included in this snapshot.")
    boxes = []
    for name, value, more in stats:
        cell = QFrame()
        cell.setObjectName("profileStat")
        cell.setStyleSheet(f"QFrame#profileStat {{ border: 1px solid {C['line']}; border-radius: 6px; }}")
        column = QVBoxLayout(cell)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(1)
        column.addWidget(_label(f"<b>{html.escape(name, quote=False)}</b>", rich=True))
        column.addWidget(_label(value))
        for words in more:
            column.addWidget(_label(words, "small"))
        column.addStretch(1)
        boxes.append(cell)
    return AutoGrid(boxes, 160, 8)


def profile_cards(cards: list, none: str, picture) -> QWidget:
    """A part's cards (``.cr-profile-card``): each its picture, slot, name and line."""
    if not cards:
        return _label(none)
    frames = []
    for card in cards:
        frame = QFrame()
        frame.setObjectName("profileCard")
        edge = GRADE_EDGES.get(card.get("grade") or "", C["line"])
        frame.setStyleSheet(f"QFrame#profileCard {{ background: {C['panel']}; border: 1px solid {edge}; border-radius: 6px; }}")
        line = QHBoxLayout(frame)
        line.setContentsMargins(12, 12, 12, 12)
        line.setSpacing(12)
        image = picture(card["image"], card["alt"], 48)
        image.setStyleSheet(f"QLabel {{ color: {C['muted']}; font-size: 24px; }}")
        line.addWidget(image)
        words, column = _plain(spacing=1)
        if card["small"]:
            column.addWidget(_label(card["small"], "muted"))
        column.addWidget(_label(f"<b>{html.escape(card['title'], quote=False)}</b>", rich=True))
        column.addWidget(_label(card["line"], "muted"))
        line.addWidget(words, 1)
        frames.append(frame)
    return AutoGrid(frames, 240, 10)


class ReviewPage(QWidget):
    """A log's own page (``pageCombatLog``, ``A2CombatReview.mount``). ``open_web`` opens a page of the app (another log
    opens here again); ``open_in_web`` opens a page in the web interface itself (the full review). ``uploaded`` says this
    recording was uploaded (``a2log-uploaded``). ``store`` keeps what the web page keeps in its browser (the movement
    replay's speed and arena shape)."""

    uploaded = Signal()

    def __init__(self, api: AppApi | None, open_web=None, open_in_web=None, parent: QWidget | None = None,
                 pictures: Pictures | None = None, read_picture=None, store=None, live: bool = False, open_builds=None):
        super().__init__(parent)
        self.live = live                                 # the live session's review (``options.live``, 0.2.473)
        # ``options.openBuildWorkspace`` (0.2.489): a character's saved profile opened in Builds, given the context and
        # how to come back to this log
        self.open_builds = open_builds
        self.store = store if store is not None else interface_store()
        self.replay: ReplayPanel | None = None           # the movement replay drawn last, while it may be playing
        self.aoe_shapes: dict | None = None              # the bosses' skills' measured areas (``aoeShapes``), read once
        self.replay_hidden: set = set()                  # the replay's key entries unticked (``replayHidden``), per log
        # per document and encounter: the movement the log server merged from the fight's other recordings
        # (``mergedMoves``); the log server's combined fight shares its recording's, a combined review has its own
        self.moves_by_doc: dict = {}
        self.moving: dict = {}                           # the merges asked for, by request: the moves they answer into
        self.ranks_segment = -1                          # the encounter the parses were asked for
        self.setObjectName("plain")
        self.official = OfficialPictures(self, read_picture)          # a character's pictures off the official hosts
        self.official.loaded.connect(self._official_picture)
        self.official.failed.connect(self._official_failed)
        self.official_kept: dict[str, QPixmap | None] = {}
        image_health.watch(self)                         # Settings' Retry images reads them again (0.2.475)
        self.open_web = open_web or (lambda page: None)
        self.open_in_web = open_in_web or self.open_web
        self.pictures = pictures
        self.names: dict | None = None                  # the community's NPC names, read once
        self.soon = QTimer(self)                         # pictures that come together, drawn once
        self.soon.setSingleShot(True)
        self.soon.setInterval(120)
        self.soon.timeout.connect(lambda: self.draw() if self.awaiting else None)
        self.awaiting = False                            # a portrait of this review's still being read
        if self.pictures is not None:
            self.pictures.changed.connect(self.soon.start)
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.asked: dict[str, int] = {}
        self.colours: dict = {}
        self.doc: dict | None = None
        self.where: dict = {}
        self.state = cw.fresh_state()
        self.ranks = None
        self.summary = None
        self.popup: FilterPopup | None = None          # a column's filter of the events, while it is open
        self.filter_buttons: dict = {}
        self._forget_timeline()
        self._forget_forms()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)

    def stop(self) -> None:
        self.soon.stop()
        self._stop_replay()
        self.official.stop()
        if self.popup is not None:
            self.popup.hide()
        if self.requests is not None:
            self.requests.stop()

    def _forget_forms(self) -> None:
        """The report, the metadata's save and the upload as a log opens: nothing written, sent or said (``reportReason``…)."""
        self.report = {"reason": "privacy", "details": "", "status": "", "busy": False}
        self.meta_result, self.meta_open, self.meta_busy = "", False, False
        self.publish = {"visibility": "public", "result": "", "busy": False}
        self.previews: dict = {}                                     # current profiles looked up, by character
        self.profile_for, self.profile_message, self.colours_open = "", "", False
        self.compared: list[dict] = []                               # the logs compared (``comparisons``)
        self.compare_result, self.compare_segment = "", 0
        self.compare_status = None
        self.mapping_status = self.meta_parts = self.publish_parts = self.standings_box = None
        self.source_view: dict | None = None                         # the part a combined review was made from
        self.archive = {"page": None, "offset": 0, "busy": False, "error": "", "open": False, "offer": 0, "first": 1, "last": 1}
        self.fight = {"segment": -1, "own": None, "loading": False, "error": ""}   # the log server's combined fight
        self.combined_status, self.archive_asked_offset = "", 0

    def _forget_timeline(self) -> None:
        """The timeline's lanes all shown and open again, its window at the start, nothing inspected: as another encounter
        opens (``timelineHidden.clear()``…)."""
        self.lanes_hidden: set = set()
        self.lanes_folded: set = set()
        self.effect = ""
        self.lanes_open = False                       # the lanes' visibility opened (kept while the encounter is)
        self.timeline_scroll: tuple | None = None
        self.timeline_place: tuple | None = None
        self.state["timeline_start"] = 0.0

    # ---------------------------------------------------------------- questions and answers
    def _ask(self, kind: str, path: str, proxied: bool = False, body: dict | None = None) -> None:
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is None:
            return
        name = f"{kind}:{self.asked[kind]}"
        if body is not None:
            self.requests.post(name, "/api/community", {"path": path, "body": body})
        else:
            self.requests.get(name, cv.community_path(path) if proxied else path)

    def _current(self, name: str) -> str | None:
        kind, _, number = name.partition(":")
        return kind if number == str(self.asked.get(kind)) else None

    def show_log(self, kind: str, value: str, mode=None, segment=None) -> None:
        """A log's page opened (``pageCombatLog``): its log read, then drawn at the mode and encounter asked for."""
        self.where = {"kind": kind, "value": value}
        self.doc, self.ranks = None, None
        self.state = cw.fresh_state(mode, segment)
        self._forget_timeline()
        self._forget_forms()
        self._stop_replay()                                          # its panel goes with the page cleared below
        self.replay_hidden = set()                                   # the key as it starts for each log
        self.moves_by_doc, self.moving = {}, {}
        for kind_of in [k for k in self.asked if k.startswith("movement.")]:
            self.asked[kind_of] += 1                                 # merges asked for the log shown before let go
        for kind_of in ("log", "ranks"):
            self.asked[kind_of] = self.asked.get(kind_of, 0) + 1     # answers about the log shown before are let go
        _clear(self.box)
        self.box.addWidget(_label(cw.LOADING, "muted"))
        self._ask("ui", "/api/ui")
        if self.names is None:
            self._ask("names", "/api/v1/npc-portraits", proxied=True)
        if self.aoe_shapes is None and not self.asked.get("aoe"):   # the newer of the app's copy and the log server's
            self._ask("aoe", "/static/aoe-shapes.json")
        path, proxied = cw.log_path(kind, value)
        self._ask("log", path, proxied)

    def _given(self, kind: str) -> None:
        """A log given whole rather than read (``kind`` ``live`` or ``opened``): the page as a log's opens, at its first
        encounter, everything asked for the log shown before let go."""
        self.where = {"kind": kind, "value": ""}
        self.doc, self.ranks = None, None
        self.state = cw.fresh_state()
        self._forget_timeline()
        self._forget_forms()
        self._stop_replay()
        self.replay_hidden = set()
        self.moves_by_doc, self.moving = {}, {}
        for kind_of in [k for k in self.asked if k.startswith("movement.")]:
            self.asked[kind_of] += 1
        for kind_of in ("log", "ranks"):
            self.asked[kind_of] = self.asked.get(kind_of, 0) + 1
        self._ask("ui", "/api/ui")
        if self.names is None:
            self._ask("names", "/api/v1/npc-portraits", proxied=True)
        if self.aoe_shapes is None and not self.asked.get("aoe"):
            self._ask("aoe", "/static/aoe-shapes.json")

    def show_live(self, doc: dict) -> None:
        """The live session's review (``mount`` with ``live``): its document as the meter reads it, at its latest
        encounter, followed until another is chosen."""
        self.live = True
        self._given("live")
        self.state["follow_latest"] = True
        self.doc = _dict(doc)
        self._select_latest()
        self.draw()
        self.ask_ranks()

    def show_opened(self, doc) -> None:
        """An upload's log as its server gave it to the upload's credential, from My Uploads' Review
        (``#/combat-log/opened``, 0.2.474): reviewed as the web page reviews it, with the review's own choices alone
        (``localReviewOptions()``). It has no parts to list or join, no metadata to save, no upload, report, combined
        fight or other recordings' movement; its parses are asked for with the log sent whole."""
        self.live = False
        self._given("opened")
        self.doc = _dict(doc)
        self.draw()
        self.ask_ranks()

    def update_live(self, doc: dict) -> None:
        """The session's next document (``update``): the choices kept, the latest encounter followed, and its parses
        asked for when the review moves to it."""
        self.fight = cw_fight()
        self.doc = _dict(doc)
        self.state["segment"] = min(self.state["segment"], len(cw.segments(self.doc)) - 1)
        moved = self._select_latest()
        self.draw()
        if moved:
            self.ask_ranks()

    def _select_latest(self) -> bool:
        """``selectLatest``: following the latest encounter, the newest of the mode chosen; whether the review moved."""
        if not self.live or not self.state.get("follow_latest"):
            return False
        segments = cw.segments(self.doc)
        index = len(segments) - 1
        while index >= 0 and not cw.matches_mode(self.doc, segments[index], self.state["mode"]):
            index -= 1
        if index < 0:
            return False
        self.state["run"] = ""
        if index == self.state["segment"]:
            return False
        self._forget_timeline()
        self.state.update(segment=index, actor="", enemy="", page=0)
        self.ranks = None
        return True

    def reload(self) -> None:
        """The log read again, the choices kept. An upload's log is kept as it was given, as the web page keeps it
        (``S.combat.openedLog``): reading it again needs its credential."""
        if self.where.get("kind") in ("local", "shared"):
            path, proxied = cw.log_path(self.where["kind"], self.where["value"])
            self._ask("ui", "/api/ui")
            self._ask("log", path, proxied)

    def _replied(self, name: str, answer) -> None:
        kind = self._current(name)
        if kind == "ui":
            self.colours = _dict(_dict(answer).get("combat_colors"))
        elif kind == "names":
            self.names = cw.community_names(answer)
            self.draw()
        elif kind == "aoe":                                          # a catalog without shapes draws no areas
            shapes = _dict(answer).get("shapes")
            if isinstance(shapes, dict) and shapes:
                self.aoe_shapes = shapes
                if self.replay is not None:
                    self.replay.set_shapes(shapes)
        elif kind == "log":
            if isinstance(answer, dict) and _truthy(answer.get("error")):
                self._refused(js_text(answer["error"]))
                return
            first = self.doc is None
            self.doc = _dict(answer)
            segments = cw.segments(self.doc)
            asked = self.state["segment"]
            if first and not (0 <= asked < len(segments)):          # an encounter the log hasn't: its first
                self.state["segment"] = 0
            if first:
                part = _dict(_dict(self.doc.get("meta")).get("archive")).get("part")
                self.archive["last"] = part if isinstance(part, int) and not isinstance(part, bool) and part else 1
            self.draw()
            if first:
                self.ask_ranks()
                self._auto_combine()
        elif kind == "ranks":
            self.ranks = answer if isinstance(answer, dict) else {}
            self.draw()
            # another party member's public upload of this fight (``shared_uploads``): its movement joins unasked
            if _list(self.ranks.get("shared_uploads")) and self.ranks_segment == self.state["segment"]:
                self._merge_others(self.ranks_segment, unasked=True)
        elif kind is not None and kind.startswith("movement."):    # the fight's movement merged by the log server
            moves = self.moving.pop(kind, None)
            if moves is not None:
                moves[int(kind.split(".", 1)[1])] = (answer if isinstance(_dict(answer).get("movement"), list)
                                                     else {"error": rp.NO_MERGE_MOVEMENT})
                self.draw()
        elif kind == "save":                                         # the metadata saved: the log as the app keeps it
            self.doc, self.meta_busy, self.meta_result = _dict(answer), False, cw.METADATA_SAVED
            self.ranks = None
            self.draw()
            self.ask_ranks()
        elif kind == "report":
            receipt = _dict(answer)
            self.report.update(busy=False, details="",
                               status=f"{cw.js_string(receipt.get('message'))} Receipt: {cw.js_string(receipt.get('id'))}")
            self.draw()
        elif kind in ("parts", "autoparts"):                         # a page of the recording's parts
            if kind == "autoparts":                                  # asked unasked (``autoCombine``): only an offer
                span = cw.parts_span(answer)
                if span is not None and self.source_view is None:
                    self.archive.update(page=answer, offset=0, offer=span[0], first=span[1], last=span[2])
                    self.draw()
                return
            if isinstance(answer, dict) and isinstance(answer.get("rows"), list):
                self.archive.update(page=answer, offset=self.archive_asked_offset, error="")
            else:
                self.archive["error"] = cw.NO_PART_LIST
            self.archive["busy"] = False
            self.draw()
        elif kind == "reconstruct":                                  # the parts combined into one review
            self.archive["busy"] = False
            if cw.is_reconstruction(answer):
                self._apply_combined(_dict(answer))
            else:
                self.archive["error"] = cw.NO_RECONSTRUCTION
            self.draw()
        elif kind == "combined":                                     # the log server's combined fight
            index = self.fight["segment"]
            combined = _dict(answer)
            if self.state["segment"] != index:
                self.fight = cw_fight()
            elif isinstance(combined.get("meta"), dict) and _truthy(combined["meta"].get("combined")) and \
                    0 <= index < len(cw.segments(combined)) and isinstance(combined.get("segments"), list):
                self.fight = {**cw_fight(), "segment": index, "own": self.doc}
                self.moves_by_doc[id(combined)] = (combined, self._moves())   # it shares this recording's merged movement
                self.doc = combined
            else:
                self.fight = {**cw_fight(), "segment": index, "error": cw.NO_COMBINED_FIGHT}
            self.draw()
        elif kind == "profile":                                      # a current profile looked up: shown as a preview
            self.previews[self.profile_for] = answer
            self.profile_message = ""
            self.draw()
        elif kind == "colours":                                      # the class colours as the app keeps them
            kept = _dict(answer).get("combat_colors")
            if isinstance(kept, dict) and kept != self.colours:
                self.colours = kept
                self.draw()
        elif kind == "compare":                                      # another log read to compare
            try:
                self.compared.append(cw.comparison_of(answer, self.compare_segment))
            except ValueError as problem:
                self._compare_said(str(problem))
                return
            self.compare_result = ""
            self.draw()
        elif kind == "publish":
            shared = _dict(answer)
            link = safe_link(shared.get("url"))
            words = f"<a href='{html.escape(link)}'>Open shared log</a>" if link else ""
            if _truthy(shared.get("ownership_warning")):
                words += f"<p>{html.escape(cw.js_string(shared['ownership_warning']))}</p>"
            self._published(words)
            self.uploaded.emit()

    def _failed(self, name: str, why: str) -> None:
        kind = self._current(name)
        if kind is not None and kind.startswith("movement."):
            moves = self.moving.pop(kind, None)
            if moves is not None:
                moves[int(kind.split(".", 1)[1])] = {"error": why}
                self.draw()
        elif kind == "log":
            self._refused(why)
        elif kind == "ranks":
            self.ranks = {"error": why}
            self.draw()
        elif kind == "save":                                         # the form left as it is, to be sent again
            self.meta_busy, self.meta_result = False, why
            if self.meta_parts is not None:
                self.meta_parts["result"].setText(why)
                self.meta_parts["save"].setEnabled(True)
        elif kind == "report":
            self.report.update(busy=False, status=why)
            self.draw()
        elif kind == "publish":
            self._published(html.escape(why))
        elif kind == "compare":
            self._compare_said(why)
        elif kind == "profile":
            self.profile_message = why
            self.draw()
        elif kind in ("parts", "reconstruct"):
            self.archive.update(busy=False, error=why)
            self.draw()
        elif kind == "combined":
            if self.state["segment"] == self.fight["segment"]:
                self.fight = {**cw_fight(), "segment": self.fight["segment"], "error": why}
            else:
                self.fight = cw_fight()
            self.draw()

    def _refused(self, why: str) -> None:
        self._stop_replay()
        _clear(self.box)
        self.box.addWidget(_note(why or "Could not read the combat log."))

    def rankings(self) -> bool:
        """Whether the log server ranks this log (``options.rankings``): never a combined review of several parts."""
        return self.doc is not None and not cw.reconstructed(self.doc)

    def ask_ranks(self) -> None:
        """The encounter's parses asked for (``requestRanks``); until they come every parse reads "·"."""
        if not self.rankings() or self.state["segment"] < 0:
            return
        self.ranks, self.ranks_segment = None, self.state["segment"]
        path, body = cw.rankings_question(self.where["kind"], self.where["value"], self.state["segment"], self.doc)
        self._ask("ranks", path, proxied=body is None, body=body)

    # ---------------------------------------------------------------- choices
    def _changed(self, key: str, value) -> None:
        """A choice made (``data-control``): the mode and the run pick their first encounter; another encounter forgets
        the player and the parses."""
        state = self.state
        state[key] = value
        state["page"] = 0
        if key in ("run", "segment"):                                # an encounter chosen: no longer the latest's
            state["follow_latest"] = False
        if key == "mode":
            state["run"] = ""
            state["segment"] = max(0, next((i for i, s in enumerate(cw.segments(self.doc)) if cw.matches_mode(self.doc, s, value)), 0))
        if key == "run":
            state["segment"] = cw.first_of_run(self.doc, state)
        encounter = key in ("mode", "run", "segment", "follow_latest")
        if encounter:
            state["enemy"] = state["actor"] = ""
            self.ranks = None
            self._forget_timeline()
        self._select_latest()
        self.draw()
        if encounter:
            self.ask_ranks()

    def choose_metric(self, key: str) -> None:
        """A metric chosen (``data-metric``). Not ``metric``: ``QWidget.metric()`` is Qt's own, asked for the page's paint
        metrics."""
        self.state["metric"] = key
        self.state["page"] = 0
        self.draw()

    def view(self, key: str) -> None:
        """A view chosen (``data-view``): the Table's summary, the Timeline (turned on when it is chosen), or the Events."""
        self.state["view"] = key
        if key == "timeline":
            self.state["timeline"] = True
        self.draw()

    def open_segment(self, index: int) -> None:
        """Another encounter of the log (``data-attempt-segment``)."""
        self.state.update(segment=index, enemy="", actor="")
        self.ranks = None
        self._forget_timeline()
        self.draw()
        self.ask_ranks()

    def _open_other(self, log) -> None:
        """Another log the server links this fight to (``data-open-shared``)."""
        if _truthy(log):
            self.open_web(cv.shared_page(log, self.state["mode"]))

    def full_review(self) -> None:
        """The whole review, in the web interface (its graph, timeline, events and the rest)."""
        if not self.where:
            return
        if self.where["kind"] == "live":                             # the live session's: the web interface's Live Meter
            self.open_in_web("meter")
            return
        if self.where["kind"] == "opened":                           # an upload's: My Uploads there, to review it again
            self.open_in_web("combat/owned")
            return
        self.open_in_web(self._address())

    def _address(self) -> str:
        """This log's page at the mode and encounter shown (``#/combat-log/local/<file>``, ``#/combat-log/shared/<id>``)."""
        page = cw.local_page if self.where["kind"] == "local" else cv.shared_page
        return page(self.where["value"], self.state["mode"], self.state["segment"])

    # ---------------------------------------------------------------- drawing
    def draw(self) -> None:
        doc = self.doc
        if doc is None:
            return
        self.awaiting = False
        self._stop_replay()
        _clear(self.box)
        state = self.state
        if self.fight["segment"] != state["segment"] and not self.fight["loading"]:   # another encounter: this recording's
            if self.fight["own"] is not None:
                self.doc = doc = self.fight["own"]
            self.fight = cw_fight()
        cw.settle_segment(doc, state)
        if state["segment"] < 0:                                     # nothing in this mode (``No encounters recorded``)
            frame = Window(cw.title(doc))
            for part in (self._combined(), self._archive()):
                if part is not None:
                    frame.body.addWidget(part)
            frame.body.addWidget(_note(cw.NO_MODE_ENCOUNTERS))
            frame.body.addWidget(_button(cw.SHOW_ALL, lambda: self._changed("mode", ""), "small"))
            self.box.addWidget(frame)
            return
        d = cw.data(doc, state)
        self.build_window = self._build(d)
        if self.build_window is not None:                             # a character's build in place of the review
            self.box.addWidget(self.build_window)
            return
        foes = cw.opponents_of(doc, d)
        foe = state["actor"] if any(e.get("id") == state["actor"] for e in foes) else ""
        v = cw.data(doc, state, foe) if foe else d
        frame = Window(cw.title(doc), f"{theme.fixed(cw.duration(d), 1)}s")
        body = frame.body
        body.addWidget(self._controls(d, foes))
        if cw.is_pvp(doc, d):
            arena = cw.arena(d)
            body.addWidget(self._arena(arena) if arena is not None else _note(cw.PVP_NOTE))
        if foe:
            body.addWidget(self._opponent(cw.opponent(v)))
        else:
            if foes:
                body.addWidget(_muted(cw.CHOOSE_OPPONENT))
            line = cw.unattributed_line(v["unattributed"])
            if line:
                body.addWidget(_muted(line))
        rebuilt = cw.rebuilt_line(d["segment"].get("heals_over_time"))
        if rebuilt:
            body.addWidget(_muted(rebuilt))
        source = cw.source_line(doc, d)
        if source:
            body.addWidget(_muted(source))
        for part in (self._combined(), self._archive(), self._shared(), self._fight()):
            if part is not None:
                body.addWidget(part)
        body.addWidget(self._quality(d))
        cut = cw.pieces(doc, state)
        if cut:
            words = _muted("The meter cut this boss fight in two; this encounter is the whole fight, joined from its pieces, "
                           "which are still listed on their own (unranked).")
            body.addWidget(words)
            row, line = _plain(QHBoxLayout, 6)
            for index in cut:
                line.addWidget(_button("Open a piece", lambda index=index: self.open_segment(index)))
            line.addStretch(1)
            body.addWidget(row)
        self.mapping_status = None
        for part in (self._context(d), self._mapping()):
            if part is not None:
                body.addWidget(part)
        if state["mode"]:
            body.addWidget(_muted(f"Showing only encounters recorded as {state['mode'].upper()}. Whole-run timing is hidden in "
                                  "this filtered view."))
        else:
            body.addWidget(self._runs(d))
        body.addWidget(self._tabs())
        body.addWidget(self._options())
        body.addWidget(self._builds(d))
        self.colours_panel = None
        if self.colours_open:
            self.colours_panel = ClassColours(self.colours)
            self.colours_panel.saved.connect(self._colours_saved)
            body.addWidget(self.colours_panel)                        # ``<div data-colors>``: no frame of its own
        events = cw.visible_events(v, state)
        if state["graph"] and state["metric"] != "deaths":
            body.addWidget(self._graph(v, events))
        body.addWidget(self._ping(d))
        bosses = cw.boss_hp(d, state)
        if bosses:
            body.addWidget(_head("Remaining boss HP · latest recorded sample"))
            body.addWidget(self._table(["Boss", "Remaining HP", "Observed maximum", "Remaining %", "Sample time"], bosses))
            body.addWidget(_muted(cw.HP_NOTE))
        body.addWidget(self._enemies(d))
        self.recaps_box = None
        if state["metric"] == "deaths":
            body.addWidget(self._recaps(v))
        self.insights_fold = None
        if state.get("insights"):
            body.addWidget(self._insights(d))
        self.summary = self.timeline = None
        self.filter_buttons = {}
        if state["view"] == "table":                                 # the view chosen (``data-view``)
            parse_column = self.rankings() and not foe
            body.addWidget(_muted(cw.summary_note(d, v, foe, parse_column)))
            body.addWidget(self._summary(d, v, parse_column))
        elif state["view"] == "events":
            body.addWidget(self._events(d, events))
        if state["timeline"] and state["view"] == "timeline":
            body.addWidget(self._timeline(v, events))
        body.addWidget(self._details(d, v, events))
        body.addWidget(self._actions(v))
        notes = cw.notes_line(d)
        if notes:
            body.addWidget(_muted(notes))
        local, combined = self.where.get("kind") == "local", cw.reconstructed(doc)
        if self.where.get("kind") == "shared" and not combined:      # ``options.report``: a shared log's
            body.addWidget(self._report_form())
        body.addWidget(self._metadata(d))
        self.standings_box = None
        if self.rankings():
            body.addWidget(self._standings())
            row, line = _plain(QHBoxLayout)
            line.addWidget(_button(cw.REFRESH, self.ask_ranks))
            line.addStretch(1)
            body.addWidget(row)
        if local and not combined:                                   # ``options.publish``: a recording on this computer's
            body.addWidget(self._publish_form())
        replay = self._replay(d)
        if replay is not None:
            body.addWidget(replay)
        body.addWidget(self._compare_row())
        body.addWidget(self._comparisons(d))
        elsewhere = QFrame()
        elsewhere.setObjectName("note")
        line = QVBoxLayout(elsewhere)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        opened = self.where.get("kind") == "opened"
        line.addWidget(_label(cw.ELSEWHERE_OPENED if opened else cw.ELSEWHERE))
        row, row_line = _plain(QHBoxLayout)
        row_line.addWidget(_button(cw.OPEN_WEB_OPENED if opened else cw.OPEN_WEB, self.full_review))
        row_line.addStretch(1)
        line.addWidget(row)
        body.addWidget(elsewhere)
        self.box.addWidget(frame)

    def _pick(self, words: str, values, chosen, changed, groups=None) -> QWidget:
        """A choice with its name (``label`` around a ``select``); ``groups`` add an ``optgroup`` of their own."""
        box, line = _plain(QHBoxLayout, 6)
        line.addWidget(_label(words, wrap=False))
        pick = QComboBox()
        pick.setAccessibleName(words)
        for value, name in values:
            pick.addItem(name, value)
        for group, items in (groups or []):
            pick.addItem(group, None)
            pick.model().item(pick.count() - 1).setEnabled(False)       # the group's name
            for value, name in items:
                pick.addItem(f"  {name}", value)
        pick.setCurrentIndex(max(0, pick.findData(chosen)))
        pick.activated.connect(lambda _i: changed(pick.currentData()))
        line.addWidget(pick)
        return box

    def _controls(self, d: dict, foes: list[dict]) -> QWidget:
        """The mode, run, encounter and player (``data-control``), on as many lines as the window needs (``.row``'s
        ``flex-wrap``, since 0.2.473)."""
        doc, state = self.doc, self.state
        box = QWidget()
        box.setObjectName("plain")
        line = FlowLayout(box, align=Qt.AlignLeft, gap=(14, 8))
        line.addWidget(self._pick("Combat mode", cw.MODES, state["mode"], lambda value: self._changed("mode", value)))
        runs = cw.runs(doc, state)
        if any(run != "legacy" for run in runs):
            line.addWidget(self._pick("Run", [("", "All runs")] + [(run, f"Run {run}") for run in runs], state["run"],
                                      lambda value: self._changed("run", value)))
            run = _label(cw.run_line(d), "small", wrap=False)
            line.addWidget(run)
        if self.live:                                                # ``data-control="followLatest"``
            follow = QCheckBox(cw.FOLLOW_LATEST)
            follow.setChecked(bool(state.get("follow_latest")))
            follow.toggled.connect(lambda checked: self._changed("follow_latest", checked))
            line.addWidget(follow)
        line.addWidget(self._pick("Encounter", cw.segment_choices(doc, state), state["segment"],
                                  lambda value: self._changed("segment", int(value))))
        players = [(js_text(p.get("id")), cw.actor_label(p)) for p in d["rows"]]
        groups = [("Opponents", [(js_text(e.get("id")), cw.actor_label(e)) for e in foes])] if foes else None
        line.addWidget(self._pick("Player", [("", "All players")] + players, state["actor"],
                                  lambda value: self._changed("actor", value or ""), groups))
        line.addWidget(_button(cw.CLASS_COLOURS_BUTTON, self._toggle_colours))   # ``data-color-settings``
        insights = QCheckBox(cw.INSIGHTS)                            # the insights shown (``data-control="insights"``)
        insights.setChecked(bool(state.get("insights")))
        insights.toggled.connect(lambda checked: self._changed("insights", checked))
        line.addWidget(insights)
        return box

    def _tabs(self) -> QWidget:
        """The metric shown (``data-metric``), which the summary sorts by; and at the right the view (``data-view``)."""
        box, line = _plain(QHBoxLayout, 6)
        for key, words in cw.METRICS:
            tab = _button(words, lambda key=key: self.choose_metric(key), "primary" if self.state["metric"] == key else "small")
            line.addWidget(tab)
        line.addStretch(1)
        for key, words in cw.VIEWS:
            tab = _button(words, lambda key=key: self.view(key), "primary" if self.state["view"] == key else "small")
            tab.setAccessibleName(f"{words} view")
            line.addWidget(tab)
        return box

    # ---------------------------------------------------------------- the options, graph, ping and enemies (0.2.458)
    def _options(self) -> QWidget:
        """What the review shows (``cr-options``): the graph, pets, and pets counted with their owner."""
        box, line = _plain(QHBoxLayout, 14)
        for key, words in cw.OPTIONS:
            tick = QCheckBox(words)
            tick.setChecked(bool(self.state.get(key, True)))
            tick.toggled.connect(lambda checked, key=key: self._option(key, checked))
            line.addWidget(tick)
        line.addStretch(1)
        return box

    def _option(self, key: str, checked: bool) -> None:
        """An option ticked (``data-control``): pets combined with their owner turn a pet chosen into its owner."""
        if key == "combine" and checked and self.state["actor"]:
            r = cw.refs(self.doc, self.state)
            self.state["actor"] = _dict(r.get(self.state["actor"])).get("owner") or self.state["actor"]
        self.state[key] = checked
        self.state["page"] = 0
        self.draw()

    def _graph(self, v: dict, events: list[dict]) -> QWidget:
        """The rate chart (``graph``) with its style, key, the rates at the moment inspected, and its series."""
        model = cw.graph(v, events, self.state, self.state["hidden"])
        box, column = _plain(spacing=6)
        head, line = _plain(QHBoxLayout, 10)
        line.addWidget(self._pick("Graph style", cw.GRAPH_MODES, model["mode"], self._graph_mode))
        line.addWidget(_label(model["words"], "small", wrap=False))
        line.addStretch(1)
        column.addWidget(head)
        key, line = _plain(QHBoxLayout, 14)
        if model["mode"] == "players":
            line.addWidget(_label("Class-colored lines: player rates · solid: damage done · dashed: damage taken · dotted: "
                                  "healing", "small"))
        else:
            line.addWidget(self._key(f"Bars: total {model['primary'].lower()} per second", theme.css("chart_bar"), bar=True))
            line.addWidget(self._key("Gold line: trailing 10-second average", C["chart_line"]))     # --chart-line
        if model["health"]:
            line.addWidget(self._key(f"Red line: {model['hp_of']} (right axis)", HP.name()))
        line.addStretch(1)
        column.addWidget(key)
        chart = RateChart(model, v["r"], self.colours)
        self.chart = chart
        chart.clicked.connect(lambda t: self._graph_clicked(model, t))
        column.addWidget(chart)
        detail = QFrame()
        detail.setObjectName("note")
        self.detail = QVBoxLayout(detail)
        self.detail.setContentsMargins(0, 0, 0, 0)
        self.detail.setSpacing(6)
        self.detail.addWidget(_label(cw.GRAPH_HINT, "small"))
        column.addWidget(detail)
        chart.inspected.connect(lambda t: self._inspected(model, v, t))
        buttons, line = _plain(QHBoxLayout, 6)
        for s in model["lines"]:
            colour = cr.class_colour(_dict(v["r"].get(s["actor"])).get("class"), self.colours)
            button = _button(f"{cw.actor_label(v['r'].get(s['actor']))} · {s['kind']}", lambda key=s["key"]: self._hide(key))
            button.setStyleSheet(f"color: {colour};")
            button.setAccessibleName(f"Hide {cw.actor_label(v['r'].get(s['actor']))} · {s['kind']}")
            line.addWidget(button)
        line.addWidget(_button("Show all series", self._show_all))
        line.addStretch(1)
        column.addWidget(buttons)
        return box

    @staticmethod
    def _key(words: str, colour: str, bar: bool = False) -> QWidget:
        """A key of the chart: its swatch and its words."""
        box, line = _plain(QHBoxLayout, 6)
        swatch = QFrame()
        swatch.setFixedSize(18 if bar else 24, 12 if bar else 2)
        swatch.setStyleSheet(f"background: {colour}; border: none;")
        line.addWidget(swatch, 0, Qt.AlignVCenter)
        line.addWidget(_label(words, "small", wrap=False))
        return box

    def _graph_clicked(self, model: dict, t: float) -> None:
        """In Timeline view, a click on the graph moves the timeline's window to that moment (``hit.onclick``)."""
        if self.state["view"] == "timeline":
            cw.centred_window(self.state, t, model["duration"])
            self.draw()

    def _graph_mode(self, mode) -> None:
        self.state["graph_mode"] = mode or "total"
        self.draw()

    def _hide(self, key: str) -> None:
        self.state["hidden"].add(key)
        self.draw()

    def _show_all(self) -> None:
        self.state["hidden"].clear()
        self.draw()

    def _inspected(self, model: dict, v: dict, t: float) -> None:
        """The rates and the bosses' HP at the moment inspected (``inspect``)."""
        detail = cw.graph_detail(model, t, v["r"], v["foe"])
        _clear(self.detail)
        head, words = detail["head"].split(" · ", 1)
        self.detail.addWidget(_label(f"<b>{html.escape(head)}</b> · {html.escape(words)}", rich=True))
        rows = [[self._name(v["r"].get(row["actor"]))] + row["cells"] for row in detail["rows"]]
        self.detail.addWidget(self._table(["Player", "Damage done", "Healing", "Damage taken"], rows))
        if detail["hp"]:
            self.detail.addWidget(self._table(detail["hp_head"], detail["hp"]))

    def _ping(self, d: dict) -> QWidget:
        """The recorder's ping (``latencyHTML``)."""
        ping = cw.latency(d)
        if ping is None:
            return _muted(cw.NO_PING)
        box, column = _plain(spacing=6)
        column.addWidget(_head(ping["title"]))
        column.addWidget(_label(ping["figures"]))
        column.addWidget(_muted(ping["source"]))
        column.addWidget(PingChart(ping))
        return box

    def _enemies(self, d: dict) -> QWidget:
        """The enemy encounters (``encounters``), each filtering the review to it, the unnamed summons folded."""
        found = cw.enemy_encounters(d, self.state, self.names)
        box, column = _plain(spacing=6)
        column.addWidget(_head("Enemy encounters"))
        column.addWidget(self._enemy_table(found["rows"]))
        if found["named_note"]:
            column.addWidget(_muted(cw.UNNAMED_NOTE))
        if found["folded"]:
            fold = Section(found["folded"]["title"], None, False)
            fold.body_layout.addWidget(_muted(found["folded"]["note"]))
            fold.body_layout.addWidget(self._enemy_table(found["folded"]["rows"]))
            column.addWidget(fold)
        row, line = _plain(QHBoxLayout)
        line.addWidget(_button(cw.ALL_ENEMIES, lambda: self._filter("")))
        line.addStretch(1)
        column.addWidget(row)
        return box

    def _enemy_table(self, rows: list[dict]) -> QWidget:
        cells = []
        for row in rows:
            cell, line = _plain(QHBoxLayout, 6)
            if not row["player"] and self.pictures is not None:
                portrait = self.pictures.portrait(row["code"])
                if portrait is None and self.pictures.has_portrait(row["code"]):
                    self.awaiting = True                  # drawn again once it comes, and only then
                if portrait is not None and not portrait.isNull():
                    face = QLabel()
                    face.setFixedSize(22, 22)
                    face.setScaledContents(True)
                    face.setPixmap(portrait)
                    line.addWidget(face)
            name = self._name(row["entity"]) if row["player"] else _label(html.escape(row["name"]), rich=True)
            if row["count"] > 1:
                name.setText(name.text() + f" <span style='color: {C['muted']};'>×{row['count']}</span>")
            name.setWordWrap(False)
            line.addWidget(name)
            chosen = self.state["enemy"] == row["ids"]
            filter_button = _button(row["filter"], lambda ids=row["ids"]: self._filter(ids), "primary" if chosen else "small")
            filter_button.setAccessibleName(f"Filter to {row['name']}")
            line.addWidget(filter_button)
            line.addStretch(1)
            cell.setProperty("fill", True)
            cells.append([cell, row["types"], row["damage"], row["lifespan"]])
        table = self._table(cw.ENEMY_COLUMNS, cells)
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _filter(self, ids: str) -> None:
        """The review narrowed to some enemies, or to all again (``data-enemy-filter``, ``data-clear-enemy``)."""
        self.state["enemy"] = ids
        self.draw()

    def _name(self, actor) -> QLabel:
        """An actor in its class's colour (``actorHTML``)."""
        actor = _dict(actor)
        colour = cr.class_colour(actor.get("class"), self.colours)
        return _label(f"<span style='color: {colour};'>{html.escape(cw.actor_label(actor) if actor else cw.UNKNOWN)}</span>",
                      rich=True)

    # ---------------------------------------------------------------- the events' list (0.2.459)
    def _actor(self, actor) -> QLabel:
        """An actor in the events' list (``actorHTML``): a player in their class's colour, anyone else plainly."""
        if cw.is_character(actor, self.doc):
            return self._name(actor)
        return _label(cw.actor_label(actor))

    @staticmethod
    def _grid(columns, cells, stretch) -> QWidget:
        """A table (``table``), "No recorded events." under its head when it has no rows."""
        table = GridTable(columns, cells, stretch, left=True)
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _events(self, d: dict, events: list[dict]) -> QWidget:
        """The events' list (``eventTable``): its filters, the kept events' summary, a page of them and the pager."""
        model = cw.event_list(d, events, self.state)
        self.event_model = model
        ef = model["ef"]
        box, column = _plain(spacing=6)
        bar = QWidget()
        bar.setObjectName("plain")
        flow = FlowLayout(bar, align=Qt.AlignLeft, gap=(12, 8))
        flow.addWidget(_label("Filter:", "small", wrap=False))
        placer = self._placer()
        for c in model["columns"]:
            button = _button(c["caption"] + " ▾", lambda c=c: self._open_filter(c),
                             "primary" if c["chosen"] is not None else "small")
            button.setAccessibleName(c["caption"])
            button.installEventFilter(placer)
            self.filter_buttons[c["key"]] = button
            flow.addWidget(button)
        flow.addWidget(self._range("Time", ("t0", "from", "Time from (seconds)"), ("t1", "to", "Time to (seconds)"), "s"))
        flow.addWidget(self._range("Amount", ("a0", "min", "Smallest amount"), ("a1", "max", "Largest amount"), ""))
        flow.addWidget(self._pick("Sort", cw.SORTS, ef.get("sort", "time"), self._sort))
        if model["clear"]:
            flow.addWidget(_button("Clear filters", self._clear_filters))
        column.addWidget(bar)
        summary = _label(model["summary"], "small", rich=True) if model["count"] else _label(cw.NO_MATCH, "small")
        summary.setAccessibleName("Events kept")
        self.events_summary = summary
        column.addWidget(summary)
        r = d["r"]
        cells = [[row["time"], row["kind"], self._actor(r.get(row["source"])), self._actor(r.get(row["target"])), row["skill"],
                  row["amount"]] for row in model["rows"]]
        table = self._grid(cw.EVENT_COLUMNS, cells, {0: 2, 1: 2, 2: 5, 3: 5, 4: 3, 5: 2})     # as the web table's share
        table.setAccessibleName("Events")
        self.events_table = table
        column.addWidget(table)
        pager, line = _plain(QHBoxLayout, 8)
        line.addWidget(_button("Previous", lambda: self._page(-1)))
        line.addWidget(_label(model["pager"], wrap=False))
        line.addWidget(_button("Next", lambda: self._page(1)))
        line.addStretch(1)
        column.addWidget(pager)
        return box

    def _range(self, words: str, low: tuple, high: tuple, unit: str) -> QWidget:
        """A time or an amount range (``data-ef-range``), each bound read once its field is left or Enter pressed."""
        ef = cw.filters_of(self.state)
        box, line = _plain(QHBoxLayout, 6)
        line.addWidget(_label(words, "small", wrap=False))
        for index, (key, hint, name) in enumerate((low, high)):
            if index:
                line.addWidget(_label("to", "small", wrap=False))
            field = QLineEdit(js_text(ef.get(key) or ""))
            field.setPlaceholderText(hint)
            field.setAccessibleName(name)
            field.setValidator(QRegularExpressionValidator(QRegularExpression(NUMBER), field))
            field.setFixedWidth(84)
            field.editingFinished.connect(lambda key=key, field=field: self._bound(key, field.text()))
            line.addWidget(field)
        if unit:
            line.addWidget(_label(unit, "small", wrap=False))
        return box

    def _placer(self) -> Placer:
        if self.popup is None:
            self.popup = FilterPopup(self)
            self.popup.kept.connect(self._keep)
            self.popup.searched.connect(lambda key, words: self.state["ef_search"].__setitem__(key, words))
            self.popup.closed.connect(lambda: self.state.__setitem__("ef_open", ""))
            self.placer = Placer(self.popup, self)
        return self.placer

    def _open_filter(self, column: dict) -> None:
        """A column's filter opened under its button (``data-ef-col``), or closed when it was open."""
        self._placer()
        popup = self.popup
        if popup.isVisible() and popup.key == column["key"]:
            popup.hide()
            return
        self.state["ef_open"] = column["key"]
        popup.open(column, self.state["ef_search"].get(column["key"], ""),
                   lambda key=column["key"]: self.filter_buttons.get(key))

    def _keep(self, key: str, chosen) -> None:
        """The values a column keeps (``keep``); all of them is no filter. Its filter stays open."""
        ef = cw.filters_of(self.state)
        if chosen is None:
            ef["sel"].pop(key, None)
        else:
            ef["sel"][key] = list(chosen)
        self.state["page"] = 0
        self.draw()

    def _bound(self, key: str, words: str) -> None:
        ef = cw.filters_of(self.state)
        if js_text(ef.get(key) or "") == words:                     # left unchanged (``change`` fires on a change)
            return
        ef[key] = words
        self.state["page"] = 0
        self.draw()

    def _sort(self, value) -> None:
        cw.filters_of(self.state)["sort"] = value or "time"
        self.state["page"] = 0
        self.draw()

    def _clear_filters(self) -> None:
        """Every filter and search let go (``data-ef-clear``)."""
        self.state.update(ef=None, ef_search={}, ef_open="", page=0)
        if self.popup is not None:
            self.popup.hide()
        self.draw()

    def _page(self, step: int) -> None:
        """The page before or after (``data-prev``, ``data-next``); the list keeps the page within its pages."""
        self.state["page"] = max(0, int(self.state.get("page") or 0) + step)
        self.draw()

    # ---------------------------------------------------------------- the abilities and skills (0.2.460)
    def _details(self, d: dict, v: dict, events: list[dict]) -> QWidget:
        """The abilities and skills (``detailsHTML``): the tab chosen's, or nothing (**Hide**)."""
        state = self.state
        box, column = _plain(spacing=8)
        self.details = box
        column.addWidget(_head("Abilities and skills"))
        tabs, line = _plain(QHBoxLayout, 6)
        for key, words in cw.DETAILS:
            tab = _button(words, lambda key=key: self._detail(key), "primary" if state["detail"] == key else "small")
            tab.setAccessibleName(f"{words} tab")
            line.addWidget(tab)
        line.addStretch(1)
        column.addWidget(tabs)
        self.ability_table = self.skills_table = self.casts = None
        detail = state["detail"]
        if detail in ("contribution", "abilities"):
            if state["metric"] == "deaths":
                column.addWidget(_muted(cw.DEATHS_ABILITIES))
                return box
            found = cw.abilities(d, v, events, state)
            if detail == "contribution":
                bars = cw.contribution(found, d["r"], state)
                column.addWidget(_label(bars["note"], "small", rich=True) if bars["bars"] else _muted(bars["note"]))
                if bars["bars"]:
                    r, colours = d["r"], self.colours
                    column.addWidget(ContributionBars(bars["bars"], lambda actor: cr.class_colour(_dict(r.get(actor)).get("class"),
                                                                                                 colours)))
            else:
                rows = cw.ability_table(found, v, state, cw.duration(d))
                table = self._grid(cw.ABILITY_COLUMNS, [[self._name(d["r"].get(row["actor"]))] + row["cells"] for row in rows],
                                   {0: 3, 1: 3, 2: 1, 3: 2, 4: 1, 5: 2, 6: 2, 7: 2, 8: 2})
                table.setAccessibleName("Abilities")
                self.ability_table = table
                column.addWidget(table)
        elif detail == "skills":
            column.addWidget(self._skills(v))
        elif detail == "casts":
            column.addWidget(self._casts(v))
        return box

    def _detail(self, key: str) -> None:
        """A tab of the abilities and skills chosen (``data-detail``)."""
        self.state["detail"] = key
        self.draw()

    def _hide_procs(self) -> QCheckBox:
        tick = QCheckBox(cw.HIDE_PROCS)
        tick.setChecked(bool(self.state.get("hide_procs", True)))
        tick.toggled.connect(lambda checked: self._option("hide_procs", checked))
        return tick

    def _skills(self, v: dict) -> QWidget:
        """The skills' casts (``skillsHTML``): each skill's casts, gaps, cooldown and its usage, cast time and span."""
        missing = cw.casts_missing(self.doc, v, self.state)
        if missing:
            return _label(missing, "small", rich=True)
        box, column = _plain(spacing=6)
        column.addWidget(_muted(cw.SKILLS_NOTE))
        column.addWidget(self._hide_procs())
        cells = [[self._actor(v["r"].get(row["source"])), self._skill_cell(row["skill_id"], row["skill"], row["proc"])]
                 + row["cells"] for row in cw.skill_rows(self.doc, v, self.state)]
        table = self._grid(cw.SKILL_COLUMNS, cells, {0: 3, 1: 4, 2: 1, 3: 2, 4: 2, 5: 3, 6: 2, 7: 3})
        table.setAccessibleName("Skills")
        self.skills_table = table
        column.addWidget(table)
        return box

    def _skill_cell(self, skill_id, name: str, proc: bool) -> QWidget:
        """A skill with its icon when the app bundles it (``skillCell``), a proc marked as one."""
        cell, line = _plain(QHBoxLayout, 6)
        address = cw.skill_icon(skill_id)
        picture = self.pictures.by_address(address) if self.pictures is not None and address else None
        if picture is None and self.pictures is not None and self.pictures.has_address(address):
            self.awaiting = True                                   # drawn again once it comes
        if picture is not None and not picture.isNull():
            icon = QLabel()
            icon.setFixedSize(18, 18)
            icon.setScaledContents(True)
            icon.setPixmap(picture)
            line.addWidget(icon)
        words = _label(html.escape(name) + (f" <span style='color: {C['muted']};'>proc</span>" if proc else ""), rich=True)
        words.setWordWrap(False)
        line.addWidget(words)
        line.addStretch(1)
        cell.setProperty("fill", True)
        return cell

    def _casts(self, v: dict) -> QWidget:
        """Every press over the fight (``castsHTML``)."""
        missing = cw.casts_missing(self.doc, v, self.state)
        if missing:
            return _label(missing, "small", rich=True)
        model = cw.cast_timeline(self.doc, v, self.state, self.colours)
        if model is None:
            return _muted(cw.NO_PLAYER_CASTS)
        box, column = _plain(spacing=6)
        column.addWidget(_label("<b>Cast timeline</b>", rich=True))
        column.addWidget(_muted(cw.CASTS_NOTE))
        column.addWidget(self._hide_procs())
        casts = Timeline(model, self._cast_lane_name, lambda lane: QWidget(), self._skill_picture)
        casts.setAccessibleName("Cast timeline")
        if self.pictures is not None:
            self.pictures.changed.connect(casts.tracks.update)
        self.casts, self.casts_model = casts, model
        column.addWidget(casts)
        return box

    def _cast_lane_name(self, lane: dict) -> QWidget:
        """A cast lane's name in its class's colour, with how many presses had no room (``.cr-lane-name``)."""
        cell = QFrame()
        cell.setObjectName("crLaneName")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        layout.addStretch(1)
        layout.addWidget(self._name(lane["actor"]))
        if lane.get("omitted"):
            layout.addWidget(_muted(f"{lane['omitted']} not drawn (overlap)"))
        layout.addStretch(1)
        return cell

    # ---------------------------------------------------------------- the casts, buffs and break gauge (0.2.461)
    def _actions(self, v: dict) -> QWidget:
        """The casts, buffs and break gauge (``actionsHTML``): the tab chosen's, or nothing (**Hide**); or why the log
        holds none."""
        doc, state = self.doc, self.state
        missing = cw.actions_missing(doc, v, state)
        self.actions_box = None
        if missing:
            return _muted(missing)
        box, column = _plain(spacing=8)
        self.actions_box = box
        column.addWidget(_head("Casts, buffs and break gauge"))
        tabs, line = _plain(QHBoxLayout, 6)
        for key, words in cw.ACTIONS:
            tab = _button(words.replace("&", "&&"), lambda key=key: self._actions_tab(key),   # "&" alone marks a mnemonic
                          "primary" if state["actions"] == key else "small")
            tab.setAccessibleName(f"{words} actions")
            line.addWidget(tab)
        line.addStretch(1)
        column.addWidget(tabs)
        tab = state["actions"]
        if tab == "rotation":
            t = cw.rotation_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_label(t["missing"], "small", rich=True))
            else:
                column.addWidget(_muted(cw.ROTATION_NOTE))
                column.addWidget(self._rows(cw.ROTATION_COLUMNS, t["totals"], v))
                if t["mp"]:
                    column.addWidget(_label("<b>MP</b>", rich=True))
                    column.addWidget(_muted(cw.MP_NOTE))
                    column.addWidget(self._rows(cw.MP_COLUMNS, t["mp"], v))
                column.addWidget(_label(cw.SKILLS_ABOVE, "small", rich=True))
                if t["has_chains"]:
                    column.addWidget(_label("<b>Chain skills</b>", rich=True))
                    column.addWidget(_muted(cw.CHAINS_NOTE))
                    column.addWidget(self._rows(cw.CHAIN_COLUMNS, t["chains"], v))
        elif tab in ("effects", "cc"):
            t = cw.effects_tab(doc, v, state) if tab == "effects" else cw.cc_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_muted(t["missing"]))
            else:
                column.addWidget(_muted(t["note"]))
                for table in t["tables"]:
                    if table["title"]:
                        column.addWidget(_label(f"<b>{html.escape(table['title'], quote=False)}</b>", rich=True))
                    if table.get("older"):
                        column.addWidget(_muted(cw.OLDER_ANALYSIS))
                        continue
                    if table.get("note"):
                        column.addWidget(_muted(table["note"]))
                    column.addWidget(self._rows(table["columns"], table["rows"], v))
        elif tab == "stagger":
            t = cw.stagger_tab(doc, v, state)
            column.addWidget(_muted(t["note"]))
            if not t["bosses"]:
                column.addWidget(_label(cw.NO_STAGGER))
            for b in t["bosses"]:
                column.addWidget(_label(f"<b>{html.escape(b['title'], quote=False)}</b>" + (cw._muted_html("elite") if b["elite"] else ""),
                                        rich=True))
                column.addWidget(_label(b["line"], "small"))
                if b["gauge"] is not None:
                    column.addWidget(GaugeChart(b["gauge"]))
                column.addWidget(self._rows(cw.STAGGER_COLUMNS, b["rows"], v))
        elif tab == "boss":
            t = cw.boss_tab(doc, v, state, self.names)
            column.addWidget(_label(t["note"], "small", rich=True))
            if t.get("missing"):
                column.addWidget(_label(t["missing"]))
            else:
                column.addWidget(self._rows(cw.BOSS_COLUMNS, t["skills"], v))
                column.addWidget(_label("<b>Casts in order</b>", rich=True))
                column.addWidget(_muted(cw.BOSS_ORDER_NOTE))
                column.addWidget(self._rows(cw.BOSS_ORDER_COLUMNS, t["order"], v))
                for words in t["notes"]:
                    column.addWidget(_muted(words))
        elif tab == "contribution":
            t = cw.contribution_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_muted(t["missing"]))
            else:
                column.addWidget(_label(t["note"], "small", rich=True))
                column.addWidget(self._rows(cw.CONTRIBUTION_COLUMNS, t["players"], v))
                if t["unlisted"]:
                    column.addWidget(_muted(t["unlisted"]))
                column.addWidget(_label("<b>Who added what</b>", rich=True))
                column.addWidget(self._rows(cw.GIVEN_COLUMNS, t["given"], v))
                column.addWidget(_label("<b>Credited buffs</b>", rich=True))
                column.addWidget(self._rows(cw.CREDITED_COLUMNS, t["buffs"], v))
                if t["checks"]:
                    column.addWidget(_label("<b>Check against this fight's hits</b>", rich=True))
                    column.addWidget(_label(cw.CHECKS_NOTE, "small", rich=True))
                    column.addWidget(self._rows(cw.CHECK_COLUMNS, t["checks"], v))
        omitted = cw.omitted_actions(doc, state)
        if tab and omitted:
            column.addWidget(_muted(omitted))
        return box

    # ---------------------------------------------------------------- comparisons, metadata, report and upload (0.2.464)
    def _post_app(self, kind: str, path: str, body: dict) -> None:
        """A request to the app itself (``api(path, body)``): the metadata saved, the recording uploaded."""
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is not None:
            self.requests.post(f"{kind}:{self.asked[kind]}", path, body)

    def _standings(self) -> QWidget:
        """The matched public comparisons (``ranksHTML``): each player's standings now and at upload, and the run's speed;
        or that they are loading, or why they could not be read."""
        model = cw.standings(self.ranks)
        if "loading" in model:
            return _muted(model["loading"])
        box, column = _plain(spacing=8)
        self.standings_box = box
        column.addWidget(_head(cw.STANDINGS_HEAD))
        column.addWidget(_muted(model["note"]))
        for words in (model["unranked"], html.escape(model["none"], quote=False)):
            if words:
                column.addWidget(_noted(_label(words, rich=True)))
        column.addWidget(self._grid(cw.STANDINGS_COLUMNS, [[row[0], self._scopes(row[1]), self._scopes(row[2])]
                                                          for row in model["rows"]], {0: 1, 1: 1, 2: 1}))
        column.addWidget(_label(f"<b>{html.escape(cw.RUN_HEAD, quote=False)}</b>", rich=True))
        column.addWidget(self._grid(cw.RUN_COLUMNS, [[self._scopes(cell) for cell in model["run"]]], {0: 1, 1: 1}))
        return box

    @staticmethod
    def _scopes(cell: dict) -> QWidget:
        """A cell of standings: Server, Region and World, each its own line, its reasons its tip (``title``)."""
        box, column = _plain(spacing=4)
        box.setProperty("fill", True)                                # across its column, as the web page's cell is
        for name, standing in cell["standings"]:
            line = _label(f"{name}: {standing['html']}", rich=True)
            if standing["tip"]:
                line.setToolTip(standing["tip"])
            column.addWidget(line)
        return box

    def _metadata(self, d: dict) -> QWidget:
        """The encounter's metadata (``metadataHTML``): its line; for a completed recording on this computer, its fields
        to correct and save, folded."""
        model = cw.metadata(self.doc, d, self.where.get("kind", ""))
        self.meta_parts = None
        if "line" in model:
            return _muted(model["line"])
        fold = Section(cw.METADATA_HEAD, None, self.meta_open or bool(self.meta_result) or self.meta_busy)
        fold.button.setAccessibleName(cw.METADATA_HEAD)
        fold.button.toggled.connect(lambda opened: setattr(self, "meta_open", opened))
        fold.body_layout.addWidget(_muted(cw.METADATA_NOTE))
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        scope = QComboBox()
        scope.setAccessibleName("Apply changed fields to")
        scope.addItem("This encounter", "encounter")
        if model["run"]:
            scope.addItem("All encounters in this run", "run")
        kind = QComboBox()
        kind.setAccessibleName("Encounter type")
        for value, words in model["types"]:
            kind.addItem(words, value)
        kind.setCurrentIndex(max(0, kind.findData(model["type"])))
        fields: dict = {"encounter_type": kind}
        flow.addWidget(_field_row("Apply changed fields to", scope))
        flow.addWidget(_field_row("Encounter type", kind))
        for key, words, value in model["fields"]:
            edit = QLineEdit(value)
            edit.setMaxLength(200)
            edit.setAccessibleName(words)
            fields[key] = edit
            flow.addWidget(_field_row(words, edit))
        save = _button("Save metadata", lambda: self._save_metadata(fields, scope))
        save.setEnabled(not self.meta_busy)
        flow.addWidget(save)
        result = _label(self.meta_result, "small")
        flow.addWidget(result)
        self.meta_parts = {"save": save, "result": result}
        fold.body_layout.addWidget(row)
        return fold

    def _save_metadata(self, fields: dict, scope: QComboBox) -> None:
        """The metadata saved to the recording (``data-meta-save``): the fields changed, on this encounter or its run."""
        values = {key: (widget.currentData() if isinstance(widget, QComboBox) else widget.text()) for key, widget in fields.items()}
        try:
            log = cw.corrected(self.doc, self.state["segment"], values, scope.currentData() == "run")
        except ValueError as problem:
            self.meta_parts["result"].setText(str(problem))
            return
        self.meta_busy, self.meta_open = True, True
        self.meta_parts["save"].setEnabled(False)
        self._post_app("save", "/api/sessions", {"file": self.where.get("value"), "log": log})

    def _report_form(self) -> QWidget:
        """A shared log's report to its server's operator (``reportHTML``), folded; open while anything is written, sent
        or said."""
        report = self.report
        fold = Section(cw.REPORT_HEAD, None, bool(report["details"] or report["status"] or report["busy"]))
        fold.button.setAccessibleName(cw.REPORT_HEAD)
        layout = fold.body_layout
        layout.addWidget(_muted(cw.REPORT_NOTE))
        reason = QComboBox()
        reason.setAccessibleName("Reason")
        for value, words in cw.REPORT_REASONS:
            reason.addItem(words, value)
        reason.setCurrentIndex(max(0, reason.findData(report["reason"])))
        reason.activated.connect(lambda _i: report.update(reason=reason.currentData()))
        details = QPlainTextEdit(report["details"])
        details.setAccessibleName("Details")
        details.setFixedSize(260, 72)                                # ``rows="3"``

        def written() -> None:
            text = details.toPlainText()
            if len(text) > 1000:                                     # ``maxlength="1000"``
                details.setPlainText(text[:1000])
                return
            report["details"] = text
        details.textChanged.connect(written)
        send = _button("Send report", self._send_report)
        send.setEnabled(not report["busy"])
        row = QWidget()                                              # the reason, the details and Send on one line
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        flow.addWidget(_field_row("Reason", reason))
        flow.addWidget(_field_row("Details (10–1,000 characters)", details))
        flow.addWidget(send)
        layout.addWidget(row)
        layout.addWidget(_label(report["status"]))
        return fold

    def _send_report(self) -> None:
        """The report sent (``data-report-send``), once at a time."""
        if self.report["busy"]:
            return
        self.report["busy"] = True
        path = f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/reports"
        self._ask("report", path, body={"reason": self.report["reason"], "details": self.report["details"]})
        self.draw()

    def _publish_form(self) -> QWidget:
        """A recording's upload to the log server (``Publish this log``), folded; open once it is sent."""
        publish = self.publish
        fold = Section(cw.PUBLISH_HEAD, None, bool(publish["result"]) or publish["busy"])
        fold.button.setAccessibleName(cw.PUBLISH_HEAD)
        row, line = _plain(QHBoxLayout, 8)
        visibility = QComboBox()
        visibility.setAccessibleName("Upload visibility")
        for value in cw.VISIBILITIES:
            visibility.addItem(value, value)
        visibility.setCurrentIndex(max(0, visibility.findData(publish["visibility"])))
        visibility.activated.connect(lambda _i: publish.update(visibility=visibility.currentData()))
        line.addWidget(visibility)
        upload = _button("Upload saved session", self._upload)
        upload.setEnabled(not publish["busy"])
        line.addWidget(upload)
        result = _label(publish["result"], rich=True)
        result.setOpenExternalLinks(True)
        line.addWidget(result, 1)
        self.publish_parts = {"upload": upload, "result": result}
        fold.body_layout.addWidget(row)
        return fold

    def _upload(self) -> None:
        """The recording uploaded (``data-upload``) at the visibility chosen."""
        self.publish["busy"] = True
        self.publish_parts["upload"].setEnabled(False)
        self._post_app("publish", "/api/sessions/share", {"file": self.where.get("value"), "visibility": self.publish["visibility"]})

    def _published(self, words: str) -> None:
        """The upload's answer: its link and warning, or why it failed, the fold left as it is."""
        self.publish.update(busy=False, result=words)
        parts = self.publish_parts
        if parts is not None:
            try:
                parts["result"].setText(words)
                parts["upload"].setEnabled(True)
            except RuntimeError:                                     # drawn again meanwhile: the new fold shows it
                pass

    # ---------------------------------------------------------------- other parts, combined reviews and uploads (0.2.467)
    def _local(self) -> bool:
        return self.where.get("kind") == "local"

    def _parts(self) -> bool:
        """Whether the recording's other parts can be listed and joined (``options.archiveParts``): a recording on this
        computer or a shared log, not the live session or an upload's log opened with its credential."""
        return not self.live and self.where.get("kind") in ("local", "shared")

    def _open_part(self, row: dict) -> None:
        """Another part of the recording (``openArchivePart``): a recording on this computer by its file, a shared one by
        its ID."""
        row = _dict(row)
        if self._local() and _truthy(row.get("file")):
            self.open_web(cw.local_page(row["file"], self.state["mode"]))
        elif not self._local() and _truthy(row.get("id")):
            self.open_web(cv.shared_page(row["id"], self.state["mode"]))

    def _ask_parts(self, kind: str, offset: int, limit: int) -> None:
        """A page of the recording's parts (``options.archiveParts``): the app's for a recording here, the log server's
        for a shared one."""
        source = self.source_view["doc"] if self.source_view is not None else self.doc   # a combined review's source part
        archive = _dict(_dict(source).get("meta")).get("archive")
        if self._local():
            self._ask(kind, f"/api/sessions?paged=1&offset={offset}&limit={limit}&archive="
                            f"{cw.encode_component(cw.js_string(_dict(archive).get('id')))}")
        else:
            self._ask(kind, f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/parts?offset={offset}&limit={limit}",
                      proxied=True)

    def _auto_combine(self) -> None:
        """The recording's other parts looked for as it opens (``autoCombine``), for the offer to review them together;
        a recording still being written with no earlier part, a combined review, or a log of one part asks nothing."""
        archive = _dict(_dict(self.doc).get("meta")).get("archive")
        if not self._parts() or self.source_view is not None or cw.reconstructed(self.doc) or not isinstance(archive, dict):
            return
        part = archive.get("part")
        if not ((isinstance(part, (int, float)) and not isinstance(part, bool) and part > 1) or _truthy(archive.get("closed"))):
            return
        self._ask_parts("autoparts", 0, 100)

    def _load_parts(self, offset: int) -> None:
        """A page of the recording's parts (``data-archive-load``, Previous, Next)."""
        self.archive.update(busy=True, error="", open=True)
        self.archive_asked_offset = offset
        self._ask_parts("parts", offset, 25)
        self.draw()

    def _combine_parts(self, first, last) -> None:
        """The parts from ``first`` to ``last`` combined into one review (``combineParts``)."""
        self.archive.update(first=first, last=last)
        why = cw.combine_check(first, last)
        if why:
            self.archive["error"] = why
            self.draw()
            return
        self.archive.update(busy=True, error="")
        if self._local():
            self._ask("reconstruct", f"/api/sessions/reconstruction?file={cw.encode_component(self.where.get('value', ''))}"
                                     f"&first={first}&last={last}")
        else:
            self._ask("reconstruct", f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/reconstruction?first={first}"
                                     f"&last={last}", proxied=True)
        self.draw()

    def _apply_combined(self, combined: dict) -> None:
        """The combined review shown, this part kept to return to (``applyCombined``): the fight in view stays in view,
        and the choices that named this part's actors are let go."""
        same = cw.kept_encounter(self.doc, combined, self.state["segment"])
        self.source_view = {"doc": self.doc, "state": self.state}
        self.doc = combined
        self.ranks, self.compared = None, []
        self.previews.clear()
        for kind in ("ranks", "profile"):
            self.asked[kind] = self.asked.get(kind, 0) + 1
        self.state = {**self.state, "segment": same, "run": "", "actor": "", "enemy": "", "character": "", "page": 0,
                      "hidden": set()}
        self._forget_timeline()

    def _source_back(self) -> None:
        """The source part again (``data-source-back``)."""
        if self.source_view is None:
            return
        self.doc, self.state = self.source_view["doc"], self.source_view["state"]
        self.source_view, self.ranks = None, None
        self.previews.clear()
        self.combined_status = ""
        self.draw()
        self.ask_ranks()

    def _export_combined(self) -> None:
        """The combined review saved as an a2log (``data-combined-export``)."""
        import json
        path = self._ask_where(cw.COMBINED_FILE)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(json.dumps(self.doc, ensure_ascii=False))
        except OSError as problem:
            self.combined_status = f"The combined review could not be saved: {problem}"
        else:
            self.combined_status = f"Combined review saved: {path}. Upload the original parts to share them."
        self.draw()

    def _combined(self) -> QWidget | None:
        """A combined recording review (``combinedHTML``): its note, the way back, its export, its parts, runs and totals."""
        model = cw.combined_view(self.doc, self.state)
        if model is None:
            return None
        box = QFrame()
        box.setObjectName("note")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_head(cw.COMBINED_HEAD))
        column.addWidget(_label(model["note"]))
        row, line = _plain(QHBoxLayout, 8)
        if self.source_view is not None:
            line.addWidget(_button(cw.BACK_TO_SOURCE, self._source_back))
        line.addWidget(_button(cw.EXPORT_COMBINED, self._export_combined))
        line.addWidget(_label(self.combined_status), 1)
        column.addWidget(row)
        parts = QWidget()
        parts.setObjectName("plain")
        flow = FlowLayout(parts, align=Qt.AlignLeft, gap=(6, 6))
        sources = _list(_dict(_dict(self.doc.get("meta")).get("reconstruction")).get("sources"))
        for index, words in model["sources"]:
            part = _button(words, lambda row=sources[index]: self._open_part(row))
            part.setEnabled(bool(self.where))                       # ``options.openArchivePart``
            flow.addWidget(part)
        flow.addWidget(_label(model["count"], wrap=False))
        column.addWidget(parts)
        if model["runs"] is not None:
            column.addWidget(_head(cw.RUNS_HEAD))
            column.addWidget(self._grid(cw.RUNS_COLUMNS, model["runs"]["rows"], {n: 1 for n in range(len(cw.RUNS_COLUMNS))}))
            column.addWidget(_muted(model["runs"]["note"]))
        if model["summary"] is not None:
            column.addWidget(_label(model["summary"]["line"]))
            column.addWidget(self._grid(cw.TOTALS_COLUMNS, model["summary"]["rows"], {n: 1 for n in range(len(cw.TOTALS_COLUMNS))}))
        return box

    def _archive(self) -> QWidget | None:
        """A recording's other parts (``archiveHTML``): the offer to review them all together, then the list folded, with
        the parts to combine."""
        note = cw.archive_note(self.doc)
        if not note:
            return None
        if not self._parts():                                        # no parts to list or join (``options.live``, an upload's)
            return _note(note)
        a = self.archive
        box, column = _plain(spacing=8)
        if a["offer"]:
            part = _dict(_dict(self.doc.get("meta")).get("archive")).get("part")
            offer = QFrame()
            offer.setObjectName("note")
            line = QHBoxLayout(offer)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            line.addWidget(_label(f"This is part {cw.js_string(part)} of a recording in {a['offer']} parts.", wrap=False))
            together = _button("Combining the parts…" if a["busy"] else f"Review all {a['offer']} parts together",
                               lambda: self._combine_parts(self.archive["first"], self.archive["last"]))
            together.setEnabled(not a["busy"])
            line.addWidget(together)
            if a["error"]:
                line.addWidget(_label(a["error"], "small"))
            line.addStretch(1)
            column.addWidget(offer)
        fold = Section(cw.PARTS_HEAD, None, a["open"])
        fold.button.setAccessibleName(cw.PARTS_HEAD)
        fold.button.toggled.connect(lambda opened: self.archive.update(open=opened))
        body = fold.body_layout
        body.addWidget(_muted(note))
        body.addWidget(_muted(cw.PARTS_NOTE))
        page = a["page"]
        if page is not None:
            current = self.where.get("value", "")
            cells = []
            for row in cw.part_rows(page, current):
                tip = row["tip"]
                cell = row["cells"][:4] + [_tipped(row["cells"][4], tip)] + row["cells"][5:]
                if row["current"]:
                    cell.append("Current part")
                else:
                    cell.append(_button("Open part", lambda r=row["row"]: self._open_part(r)))
                cells.append(cell)
            body.addWidget(self._grid(cw.PARTS_COLUMNS, cells, {n: 1 for n in range(len(cw.PARTS_COLUMNS))}))
            body.addWidget(_muted(cw.js_string(_dict(page).get("note") or cw.PARTS_SAVED)))
        inputs = QWidget()
        inputs.setObjectName("plain")
        flow = FlowLayout(inputs, align=Qt.AlignLeft, gap=(12, 6))
        first, last = QSpinBox(), QSpinBox()
        for spin, value, least, words in ((first, a["first"], 1, "First part"), (last, a["last"], 2, "Last part")):
            spin.setRange(least, 999999)
            spin.setValue(value if isinstance(value, int) else least)
            spin.setAccessibleName(words)
            flow.addWidget(_field_row(words, spin))
        combine = _button(cw.COMBINE_PARTS, lambda: self._combine_parts(first.value(), last.value()))
        combine.setEnabled(not a["busy"])
        flow.addWidget(combine)
        body.addWidget(inputs)
        body.addWidget(_muted(cw.COMBINE_NOTE))
        rows = _list(_dict(page).get("rows")) if page is not None else []
        status = (cw.PARTS_LOADING if a["busy"] else a["error"] or
                  (f"{len(rows)} results on this page · {cw.js_string(_dict(page).get('file_count'))} available parts" if page is not None else ""))
        body.addWidget(_label(status))
        buttons, line = _plain(QHBoxLayout, 8)
        load = _button("Refresh parts" if page is not None else "Find recording parts", lambda: self._load_parts(self.archive["offset"]))
        load.setEnabled(not a["busy"])
        line.addWidget(load)
        if page is not None:
            previous = _button("Previous", lambda: self._load_parts(max(0, self.archive["offset"] - 25)))
            previous.setEnabled(not a["busy"] and a["offset"] != 0)
            following = _button("Next", lambda: self._load_parts(self.archive["offset"] + 25))
            following.setEnabled(not a["busy"] and _truthy(_dict(page).get("has_more")))
            line.addWidget(previous)
            line.addWidget(following)
        line.addStretch(1)
        body.addWidget(buttons)
        column.addWidget(_noted(fold))
        return box

    def _shared(self) -> QWidget | None:
        """The other uploads of this fight (``sharedHTML``): each to open, and the button combining them all."""
        shared_log = self.where.get("kind") == "shared" and not cw.reconstructed(self.doc)
        can_combine = shared_log and self.fight["own"] is None             # ``options.combined``, not in a combined fight
        model = cw.shared_uploads(self.ranks, can_combine, self.fight["loading"] and self.fight["segment"] == self.state["segment"],
                                  shared_log)
        if model is None:
            return None
        if "duplicate" in model:
            return _muted(model["duplicate"])
        box = QFrame()
        box.setObjectName("note")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        uploads = QWidget()
        uploads.setObjectName("plain")
        flow = FlowLayout(uploads, align=Qt.AlignLeft, gap=(6, 6))
        flow.addWidget(_label("Also recorded by:", wrap=False))
        for log, words in model["uploads"]:                                # ``openOther``: a button when it can open
            flow.addWidget(_button(words.replace("&", "&&"), lambda log=log: self._open_other(log)) if _truthy(log)
                           else _label(words, wrap=False))
        column.addWidget(uploads)
        column.addWidget(_label(model["words"].strip()))                    # the paragraph's words, the box's width
        if model["combine"]:
            row, line = _plain(QHBoxLayout)
            combine = _button(model["combine"], self._view_combined)
            combine.setEnabled(not model["busy"])
            line.addWidget(combine)
            line.addStretch(1)
            column.addWidget(row)
        return box

    def _view_combined(self) -> None:
        """The log server's combination of this fight with its other recordings (``viewCombined``)."""
        if self.fight["loading"] or self.where.get("kind") != "shared":
            return
        index = self.state["segment"]
        self.fight = {**cw_fight(), "segment": index, "loading": True}
        self._ask("combined", f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/combined?segment={index}",
                  proxied=True)
        self.draw()

    def _own_recording(self) -> None:
        """This recording alone again (``data-own-recording``)."""
        if self.fight["own"] is not None:
            self.doc = self.fight["own"]
        self.fight = cw_fight()
        self.draw()

    def _fight(self) -> QWidget | None:
        """The combined fight in view (``fightHTML``): where each recording's records came from; or why it couldn't be
        combined."""
        if self.fight["error"] and self.fight["segment"] == self.state["segment"]:
            return _note(f"The recordings could not be combined: {self.fight['error']}")
        if self.fight["own"] is None:
            return None
        model = cw.combined_fight(self.doc)
        if model is None:
            return None
        box = QFrame()
        box.setObjectName("note")
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_head(model["title"]))
        column.addWidget(_label(model["note"]))
        cells = [[_button(row["name"].replace("&", "&&"), lambda log=row["log"]: self._open_other(log)) if _truthy(row["log"])
                  else row["name"]] + row["cells"]
                 for row in model["rows"]]
        column.addWidget(self._grid(["Recording", "Uploaded by", "Clock", "Added"], cells, {0: 1, 1: 1, 2: 1, 3: 1}))
        row, line = _plain(QHBoxLayout)
        line.addWidget(_button(cw.BACK_TO_OWN, self._own_recording))
        line.addStretch(1)
        column.addWidget(row)
        return box

    # ---------------------------------------------------------------- the movement replay (0.2.468)
    def _movement(self) -> bool:
        """Whether the log server can merge the fight's other recordings (``options.movement``): a shared log's own."""
        return self.where.get("kind") == "shared" and not cw.reconstructed(self.doc)

    def _moves(self) -> dict:
        """The merged movement of the document shown, by encounter (``mergedFor``)."""
        found = self.moves_by_doc.get(id(self.doc))
        if found is None or found[0] is not self.doc:
            found = self.moves_by_doc[id(self.doc)] = (self.doc, {})
        return found[1]

    def _merge_others(self, index: int, unasked: bool = False) -> None:
        """One fight's movement merged by the log server from its other public recordings (``mergeOthers``): asked for
        with the replay's button (again after a failure), or once on its own when the parses name another upload."""
        if not self._movement():
            return
        moves = self._moves()
        prior = moves.get(index)
        if prior is not None and (unasked or _truthy(prior.get("loading")) or isinstance(prior.get("movement"), list)):
            return
        moves[index] = {"loading": True}
        kind = f"movement.{index}"
        self.moving[kind] = moves
        self._ask(kind, f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/movement?segment={index}",
                  proxied=True)
        self.draw()

    def _replay(self, d: dict) -> QWidget | None:
        """The fight's movement replay (``replay``), with the other recordings' movement once merged; for a shared log
        that holds no movement, why not; else nothing."""
        index = self.state["segment"]
        merging = self._moves().get(index)
        model = rp.Replay(self.doc, d, self.colours, self.names, self.replay_hidden, merging)
        model.shapes = self.aoe_shapes
        offer = self._movement() and model.merged is None
        merge = (lambda: self._merge_others(index)) if offer else None
        if not model.world and not model.flat:
            if self._movement():
                box, column = _plain(spacing=8)
                column.addWidget(_head(rp.HEAD))
                column.addWidget(_muted(rp.NO_MOVEMENT + ("" if model.merged is not None else rp.MAY_HOLD)))
                if model.sources_note():
                    column.addWidget(_muted(model.sources_note()))
                if merge is not None:
                    column.addWidget(merge_row(merge, merging))
                return box
            return None
        self.replay = ReplayPanel(model, self.store, merge=merge, merging=merging)
        return self.replay

    def _stop_replay(self) -> None:
        """The replay drawn last stopped (``cancelAnimationFrame``), as the page is drawn again or left."""
        if self.replay is not None:
            self.replay.stop()
            self.replay = None

    # ---------------------------------------------------------------- character builds and class colours (0.2.466)
    def _builds(self, d: dict) -> QWidget:
        """The encounter's characters, each a button opening their build (``Character builds:``)."""
        box = QWidget()
        box.setObjectName("plain")
        flow = FlowLayout(box, align=Qt.AlignLeft, gap=(6, 6))
        flow.addWidget(_label(cw.CHARACTER_BUILDS, wrap=False))
        for actor in cw.characters(d["r"], self.doc):
            button = _button(cw.actor_label(actor).replace("&", "&&"), lambda key=actor.get("id"): self._open_character(key))
            button.setAccessibleName(f"Character build of {cw.actor_label(actor)}")
            button.setStyleSheet(f"QPushButton {{ color: {cr.class_colour(actor.get('class'), self.colours)}; }}")
            flow.addWidget(button)
        return box

    def _open_character(self, key) -> None:
        """A character's build opened (``data-character``), in place of the review (``render``'s first lines)."""
        self.state["character"] = key
        self.profile_message = ""
        self.draw()
        if self.build_window is not None:
            QTimer.singleShot(0, lambda: self._scroll_to(self.build_window))

    def _scroll_to(self, widget: QWidget) -> None:
        """A part of the page brought into view (``scrollIntoView({block: 'nearest'})``)."""
        parent = self.parentWidget()
        while parent is not None and not hasattr(parent, "ensureWidgetVisible"):
            parent = parent.parentWidget()
        if parent is not None:
            try:
                parent.ensureWidgetVisible(widget, 0, 0)
            except RuntimeError:                                     # drawn again meanwhile
                pass

    def _to_builds(self, actor: dict) -> None:
        """Open saved character in Builds (``data-build-workspace``): its saved profile as the draft's reference, its
        class and level, and the way back to this log (``backURL``): its page, or the log given whole again."""
        kind = self.where.get("kind")
        if self.live:
            back = None
        elif kind in ("local", "shared"):
            back = ("page", self._address())
        else:
            back = ("doc", self.doc)
        self.open_builds(cw.builds_context(actor), back)

    def _close_character(self) -> None:
        """Back to the log (``data-profile-close``): a lookup still on its way is let go."""
        self.state["character"] = ""
        self.asked["profile"] = self.asked.get("profile", 0) + 1
        self.draw()

    def _build(self, d: dict) -> QWidget | None:
        """A character's build (``profileHTML``), or nothing when none is open or the encounter hasn't them."""
        character = self.state.get("character") or ""
        model = cw.character_build(self.doc, d["r"], character, self.previews.get(character))
        if model is None:
            return None
        frame = Window(model["title"])
        frame.tool(_button(cw.BACK_TO_LOG, self._close_character))
        frame.head.addStretch(1)                                     # the button after the title, as the web page has it
        body = frame.body
        body.addWidget(_noted(_label(model["note"])))
        body.addWidget(_label(f"{model['status']}\n{model['stamps']}"))
        if "source" in model:
            body.addWidget(_label(model["source"]))
            body.addWidget(self._details_view(model["details"]))
            body.addWidget(_head(cw.FULL_BUILD))
            body.addWidget(_muted(cw.FULL_BUILD_NOTE))
            for key, text in model["fields"]:
                fold = Section(key.replace("&", "&&"), None, False)
                fold.button.setAccessibleName(f"Recorded field {key}")
                field = _label(text, "profileJson", wrap=False)
                field.setTextInteractionFlags(Qt.TextSelectableByMouse)
                field.setStyleSheet("font-family: monospace;")
                fold.body_layout.addWidget(field)
                body.addWidget(fold)
            row, line = _plain(QHBoxLayout)
            line.addWidget(_button(cw.EXPORT_PROFILE, lambda snapshot=model["snapshot"]: self._export_profile(snapshot)))
            line.addStretch(1)
            body.addWidget(row)
        actor = d["r"].get(character) if isinstance(d.get("r"), dict) else None
        saved = _dict(_dict(actor).get("profile_snapshot"))
        if (self.open_builds is not None and _truthy(saved.get("data"))) or model["preview"]:
            row, line = _plain(QHBoxLayout)
            if self.open_builds is not None and _truthy(saved.get("data")):
                line.addWidget(_button(cw.OPEN_IN_BUILDS, lambda actor=actor: self._to_builds(actor)))
            if model["preview"]:
                line.addWidget(_button(cw.BACK_TO_SAVED, self._back_to_saved))
            line.addStretch(1)
            body.addWidget(row)
        if not cw.reconstructed(self.doc):                           # ``options.lookupProfile``: never a combined review's
            body.addWidget(self._lookup(model))
            body.addWidget(_muted(cw.LOOKUP_NOTE))
        if model["pending"]:
            body.addWidget(_muted(cw.PENDING_NOTE))
        body.addWidget(_label(self.profile_message))
        return frame

    def _lookup(self, model: dict) -> QWidget:
        """A current official profile looked up by region and server (``data-profile-current``)."""
        box = QWidget()
        box.setObjectName("plain")
        flow = FlowLayout(box, align=Qt.AlignLeft, gap=(12, 6))
        region = QComboBox()
        region.setAccessibleName("Region")
        region.addItem("All regions", "")
        for key, words in cw.PROFILE_REGIONS.items():
            region.addItem(words, key)
        region.setCurrentIndex(max(0, region.findData(model["region"])))
        server = QComboBox()
        server.setAccessibleName("Character server")

        def fill(chosen) -> None:
            server.clear()
            for value, words in cw.server_choices(region.currentData() or "", chosen):
                if isinstance(words, list):                          # a region's and faction's servers (``optgroup``)
                    server.addItem(value, None)
                    server.model().item(server.count() - 1).setEnabled(False)
                    for key, name in words:
                        server.addItem(f"  {name}", key)
                else:
                    server.addItem(words, value)
            server.setCurrentIndex(max(0, server.findData(js_text(chosen).strip())))
        fill(model["server"])
        region.activated.connect(lambda _i: fill(server.currentData() or ""))
        flow.addWidget(_field_row("Region", region))
        flow.addWidget(_field_row("Character server", server))
        fetch = _button(cw.FETCH_CURRENT, lambda: self._fetch_profile(region.currentData() or "", server.currentData() or "", fetch))
        flow.addWidget(fetch)
        return box

    def _fetch_profile(self, region: str, server: str, button) -> None:
        """The character's current official profile asked of the app (``options.lookupProfile``)."""
        key = self.state.get("character") or ""
        actor = cw.refs(self.doc, self.state).get(key)
        if not server:
            self.profile_message = cw.NO_SERVER
            self.draw()
            return
        region = region or cw.region_of(server)
        button.setEnabled(False)
        self.profile_for, self.profile_message = key, cw.FETCHING
        self._post_app("profile", "/api/character/profile", {"player": {**_dict(actor), "server": server, "region": region},
                                                             "region": region})
        self.draw()

    def _back_to_saved(self) -> None:
        """The saved profile again (``data-profile-saved``)."""
        self.previews.pop(self.state.get("character") or "", None)
        self.draw()

    def _export_profile(self, snapshot) -> None:
        """The profile shown saved as JSON (``data-profile-download``)."""
        import json
        path = self._ask_where(cw.PROFILE_FILE)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(json.dumps(snapshot, indent=2, ensure_ascii=False))
        except OSError as problem:
            self.profile_message = f"The profile could not be saved: {problem}"
            self.draw()

    def _picture(self, url: str, alt: str, size: int, height: int | None = None) -> QLabel:
        """A character's picture (``profileIcon``): the app's bundled copy, else the official one once read, else ◇."""
        label = QLabel()
        label.setObjectName("plain")
        label.setFixedSize(size, height or size)
        label.setAlignment(Qt.AlignCenter)
        label.setAccessibleName(alt)
        picture = self.pictures.by_address(url) if self.pictures is not None and url else None
        if picture is None and url:
            if url in self.official_kept and self.official_kept[url] is None:   # it could not be read: the app's logo
                picture = QPixmap(LOGO)
                label.setToolTip("Source image unavailable")
            else:
                picture = self.official_kept.get(url)
                if picture is None:
                    self.official.ask(url)
        if picture is None or picture.isNull():
            label.setText("◇")
            label.setAccessibleName("Image unavailable" if not url else alt)
        else:
            label.setPixmap(picture.scaled(size, height or size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return label

    def _official_picture(self, url: str, data: bytes) -> None:
        picture = QPixmap()
        self.official_kept[url] = picture if picture.loadFromData(data) else None
        if self.official_kept[url] is None:
            image_health.failed(url)
        self.awaiting = True
        self.soon.start()

    def _official_failed(self, url: str) -> None:
        self.official_kept[url] = None
        image_health.failed(url)                         # among the window's picture failures (``A2AssetHealth``)
        self.awaiting = True
        self.soon.start()

    def retry_pictures(self) -> None:
        """Retry images: the characters' pictures that could not be read are read again the next time they show."""
        for url in [u for u, picture in self.official_kept.items() if picture is None]:
            self.official_kept.pop(url)
            self.official.forget(url)

    def _details_view(self, details: dict) -> QWidget:
        """A recorded character (character-view.js ``details``)."""
        return details_view(details, self._picture)

    @staticmethod
    def _stat_grid(stats: list) -> QWidget:
        return stat_grid(stats)

    def _cards(self, cards: list, none: str) -> QWidget:
        return profile_cards(cards, none, self._picture)

    def _toggle_colours(self) -> None:
        """The class colours' panel shown or hidden (``data-color-settings``)."""
        self.colours_open = not self.colours_open
        self.draw()

    def _colours_saved(self, preference: dict) -> None:
        """The class colours chosen: drawn at once and kept by the app (``/api/ui``'s ``combat_colors``)."""
        self.colours = dict(preference)
        self._post_app("colours", "/api/ui", {"combat_colors": preference})
        self.draw()

    # ---------------------------------------------------------------- comparisons with other logs (0.2.465)
    def _compare_row(self) -> QWidget:
        """Another log to compare (``data-compare``): its link or ID, or an a2log file on this computer."""
        box = QWidget()
        box.setObjectName("plain")
        flow = FlowLayout(box, align=Qt.AlignLeft, gap=(8, 6))
        field = QLineEdit()
        field.setPlaceholderText(cw.COMPARE_PLACEHOLDER)
        field.setAccessibleName("Link or ID of the log to compare")
        field.setMinimumWidth(240)
        field.returnPressed.connect(lambda: self._compare(field.text()))
        flow.addWidget(field)
        flow.addWidget(_button(cw.COMPARE_GO, lambda: self._compare(field.text())))
        self.compare_status = _label(self.compare_result, "small", wrap=False)
        flow.addWidget(self.compare_status)
        flow.addWidget(_button(cw.COMPARE_FILE, self._compare_file))
        return box

    def _compare_said(self, words: str) -> None:
        self.compare_result = words
        if self.compare_status is not None:
            try:
                self.compare_status.setText(words)
            except RuntimeError:                                     # drawn again meanwhile
                pass

    def _compare(self, text: str) -> None:
        """A shared log compared (``data-compare-go``): read by its ID, at the encounter its link names."""
        log = cw.log_id_of(text)
        if not log:
            self._compare_said(cw.COMPARE_ID)
            return
        self._compare_said(cw.COMPARE_LOADING)
        self.compare_segment = cw.segment_of(text)
        self._ask("compare", f"/api/v1/logs/{cw.encode_component(log)}/raw", proxied=True)

    def _ask_a2log(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, cw.COMPARE_FILE, "", "a2log JSON (*.json)")
        return path

    def _compare_file(self) -> None:
        """An a2log file on this computer compared (``data-compare-file``)."""
        import json
        path = self._ask_a2log()
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as file:
                imported = json.load(file)
            if not isinstance(imported, dict) or imported.get("format") != "a2log" or not isinstance(imported.get("segments"), list):
                raise ValueError(cw.NOT_A2LOG_FILE)
            self.compared.append(cw.comparison_of(imported))
        except (OSError, ValueError) as problem:
            self._compare_said(str(problem))
            return
        self.compare_result = ""
        self.draw()

    def _comparisons(self, d: dict) -> QWidget:
        """The logs compared (``comparisonHTML``): each its encounter, Remove, its note and the players side by side."""
        box, column = _plain(spacing=8)
        for c in cw.comparisons(self.doc, d, self.compared):
            index = c["index"]
            column.addWidget(_head(c["title"]))
            row, line = _plain(QHBoxLayout, 8)
            encounter = QComboBox()
            encounter.setAccessibleName("Comparison encounter")
            for value, words in c["encounters"]:
                encounter.addItem(words, value)
            encounter.setCurrentIndex(max(0, encounter.findData(c["segment"])))
            encounter.activated.connect(lambda _i, index=index, pick=encounter: self._compare_encounter(index, pick.currentData()))
            line.addWidget(_field_row("Comparison encounter", encounter))
            line.addWidget(_button("Remove", lambda index=index: self._compare_remove(index)))
            line.addStretch(1)
            column.addWidget(row)
            column.addWidget(_muted(c["note"]))
            cells = []
            for r in c["rows"]:
                pick = QComboBox()
                pick.setAccessibleName("Same-class player to compare with")
                pick.addItem(cw.PICK_PLAYER, "")
                for value, words in r["choices"]:
                    pick.addItem(words, value)
                pick.setCurrentIndex(max(0, pick.findData(r["chosen"])))
                pick.activated.connect(lambda _i, index=index, player=r["player"].get("id"), pick=pick:
                                       self._compare_player(index, player, pick.currentData()))
                cells.append([self._actor(r["player"]), r["class"], r["own"], pick, r["theirs"], r["difference"]])
            column.addWidget(self._grid(cw.COMPARE_COLUMNS, cells, {n: 1 for n in range(len(cw.COMPARE_COLUMNS))}))
        return box

    def _compare_encounter(self, index: int, segment) -> None:
        """Another encounter of a compared log (``data-compare-segment``)."""
        self.compared[index]["segment"] = int(segment)
        self.draw()

    def _compare_player(self, index: int, player, other) -> None:
        """The player a player is compared with (``data-compare-player``)."""
        self.compared[index]["players"][player] = other
        self.draw()

    def _compare_remove(self, index: int) -> None:
        """A compared log let go (``data-compare-remove``)."""
        del self.compared[index]
        self.draw()

    # ---------------------------------------------------------------- the encounter's context, mapping and insights (0.2.463)
    def _context(self, d: dict) -> QWidget | None:
        """The automatic encounter context, folded (``classificationHTML``); nothing when the log holds none."""
        c = cw.encounter_context(d)
        if c is None:
            return None
        fold = Section(c["summary"].replace("&", "&&"), None, False)
        fold.button.setAccessibleName("Automatic encounter context")
        layout = fold.body_layout
        for words in [c["note"], c["line"]] + c["notes"]:
            layout.addWidget(_label(words))
        if c["npcs"]:
            layout.addWidget(self._table(cw.CONTEXT_COLUMNS, c["npcs"]))
        if c["omitted"]:
            layout.addWidget(_label(c["omitted"]))
        return _noted(fold)

    def _mapping(self) -> QWidget | None:
        """The mapping coverage, folded (``catalogHTML``), with **Export mapping report**; nothing for an older log."""
        m = cw.mapping_coverage(self.doc, self.state)
        if m is None:
            return None
        fold = Section(m["summary"], None, False)
        fold.button.setAccessibleName("Mapping coverage")
        layout = fold.body_layout
        layout.addWidget(_label(m["note"]))
        layout.addWidget(_label(m["line"]))
        if m["source"]:
            layout.addWidget(_muted(m["source"]))
        layout.addWidget(self._grid(cw.UNMAPPED_COLUMNS, m["rows"], {c: 1 for c in range(len(cw.UNMAPPED_COLUMNS))}))
        if m["unidentified"] is not None:
            layout.addWidget(_label(f"<b>{cw.UNIDENTIFIED_HEAD}</b>", rich=True))
            layout.addWidget(_muted(m["unidentified"]["note"]))
            layout.addWidget(self._grid(cw.UNIDENTIFIED_COLUMNS, m["unidentified"]["rows"], {0: 1, 1: 1}))
        row, line = _plain(QHBoxLayout, 8)
        line.addWidget(_button(cw.EXPORT_MAPPINGS, lambda report=m["report"]: self._export_mappings(report)))
        self.mapping_status = _label("", "small")
        line.addWidget(self.mapping_status, 1)
        layout.addWidget(row)
        return _noted(fold)

    def _ask_where(self, name: str) -> str:
        """Where a file is saved, the computer's Downloads folder offered (where a browser puts a download)."""
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, "Export", os.path.join(folder, name), "JSON (*.json)")
        return path

    def _export_mappings(self, report: dict) -> None:
        """The mapping report saved where the computer's user chooses (``data-export-mappings``)."""
        path = self._ask_where(cw.MAPPING_FILE)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(cw.mapping_report(report))
        except OSError as problem:
            words = f"The mapping report could not be saved: {problem}"
        else:
            words = f"Mapping report saved: {path}"
        if self.mapping_status is not None:
            self.mapping_status.setText(words)

    def _insights(self, d: dict) -> QWidget:
        """The encounter insights, open (``insightsHTML``); or why an older log holds none."""
        model = cw.insights(self.doc, d, self.state)
        if model.get("missing"):
            return _note(model["missing"])
        fold = Section(cw.INSIGHTS_HEAD, None, True)
        fold.button.setAccessibleName(cw.INSIGHTS)
        self.insights_fold = fold
        layout = fold.body_layout

        def part(words: str, note: str, columns=None, rows=None, rich: bool = False) -> None:
            layout.addWidget(_label(f"<b>{html.escape(words, quote=False)}</b>", rich=True))
            layout.addWidget(_label(note, "small", rich=rich))
            if columns is not None:
                layout.addWidget(self._rows(columns, rows, d))
        layout.addWidget(_label(model["intro"]))
        if model["limits"]:
            layout.addWidget(_label(model["limits"]))
        part("Evidence coverage", cw.COVERAGE_NOTE)
        if model["coverage"] is None:
            layout.addWidget(_label(cw.COVERAGE_OLDER))
        else:
            layout.addWidget(self._rows(cw.COVERAGE_COLUMNS, model["coverage"], d))
        pressure = model["pressure"]
        if pressure is not None:
            part("Peak recorded pressure windows", pressure["note"])
            layout.addWidget(_muted(pressure["line"]))
            layout.addWidget(self._rows(cw.PRESSURE_COLUMNS, pressure["windows"], d))
            part("Incoming abilities", cw.INCOMING_NOTE, cw.INCOMING_COLUMNS, pressure["incoming"])
        part("Boss HP milestones", cw.MILESTONES_NOTE, cw.MILESTONE_COLUMNS, model["milestones"])
        part("Healing relationships", model["healing_note"], cw.HEALING_COLUMNS, model["healing"])
        effective = model["effective"]
        if effective is not None:
            part("Effective healing and overheal", effective["note"], cw.HEALERS_COLUMNS, effective["healers"], rich=True)
            layout.addWidget(self._rows(cw.HEALING_PAIRS_COLUMNS, effective["pairs"], d))
            if effective["omitted"]:
                layout.addWidget(_muted(effective["omitted"]))
        part("Imported buff windows", model["buffs_note"], cw.BUFF_WINDOWS_COLUMNS, model["buffs"])
        part("Observed ability effects", cw.EFFECTS_NOTE, cw.EFFECTS_COLUMNS, model["effects"])
        part("Opening effect sequence", cw.OPENING_NOTE, cw.OPENING_COLUMNS, model["opening"])
        return _noted(fold)

    # ---------------------------------------------------------------- the death recaps (0.2.462)
    def _recaps(self, v: dict) -> QWidget:
        """The player death recaps (``recapsHTML``): the encounter's recaps, the one opened with its effects and HP
        samples; or why the log holds none."""
        model = cw.recaps(self.doc, v, self.state)
        if model.get("missing"):
            return _note(model["missing"])
        box, column = _plain(spacing=8)
        self.recaps_box = box
        column.addWidget(_head("Player death recaps"))
        column.addWidget(_muted(model["intro"]))
        # the columns shared out evenly: the web page's recap tables have no wide first column (its HP readings' two
        # columns sit near the middle)
        column.addWidget(self._rows(cw.RECAP_COLUMNS, model["rows"], v, first=1))
        chosen = model["selected"]
        if chosen is None:
            column.addWidget(_label(model["none"]))
            return box
        column.addWidget(_label(f"<b>{html.escape(chosen['title'], quote=False)}</b>", rich=True))
        column.addWidget(_muted(chosen["note"]))
        column.addWidget(self._rows(cw.RECAP_EFFECT_COLUMNS, chosen["events"], v, first=1))
        column.addWidget(self._rows(cw.RECAP_HP_COLUMNS, chosen["health"], v, first=1))
        return box

    def _recap(self, key: str) -> None:
        """A recap opened (``data-recap``)."""
        self.state["recap"] = key
        self.draw()

    def _actions_tab(self, key: str) -> None:
        """A tab of the casts, buffs and break gauge chosen (``data-actions``)."""
        self.state["actions"] = key
        self.draw()

    def _actor_html(self, actor) -> str:
        """An actor as rich text (``actorHTML``): a player in their class's colour, anyone else plainly."""
        words = html.escape(cw.actor_label(actor))
        if cw.is_character(actor, self.doc):
            return f"<span style='color: {cr.class_colour(_dict(actor).get('class'), self.colours)};'>{words}</span>"
        return words

    def _cell(self, cell, v: dict):
        """A cell of the model's rows: text, an actor (with **Open recap** under a recap's), a recap's last hit, a skill
        with its icon, rich text, or a list of actors with counts."""
        if not isinstance(cell, dict):
            return cell
        r = v["r"]
        if "recap" in cell:                                          # a recap's player, and **Open recap** under them
            box, column = _plain(spacing=4)
            column.addWidget(self._actor(r.get(cell["actor"])))
            row, line = _plain(QHBoxLayout)
            open_recap = _button(cw.OPEN_RECAP, lambda key=cell["recap"]: self._recap(key))
            open_recap.setAccessibleName(f"Open the recap of {cw.actor_label(r.get(cell['actor']))} at {cell['at']}")
            line.addWidget(open_recap)
            line.addStretch(1)
            column.addWidget(row)
            return box
        if "hit" in cell:                                            # a recap's last hit: its attacker, then its words
            return _label(self._actor_html(r.get(cell["hit"])) + html.escape(cell["words"], quote=False), rich=True)
        if "actor" in cell:
            if cell.get("boss"):
                return _label(self._actor_html(r.get(cell["actor"])) + cw._muted_html("boss"), rich=True)
            return self._actor(r.get(cell["actor"]))
        if "ref" in cell:
            return self._actor(cell["ref"])
        if "skill" in cell:
            return self._skill_cell(cell.get("skill_id"), cell["skill"], False)
        if "html" in cell:
            return _label(cell["html"], rich=True)
        if "sources" in cell:
            return _label(" ".join((f"{self._actor_html(r.get(source))} ×{cw.js_string(n)}" if source else
                                    f"Not recorded ×{cw.js_string(n)}") for source, n in cell["sources"]), rich=True)
        if "aimed" in cell:
            return _label(" ".join(f"{self._actor_html(r.get(target))} ×{cw.js_string(n)}" for target, n in cell["aimed"])
                          or "—", rich=True)
        return ""

    def _rows(self, columns: list[str], rows: list[list], v: dict, first: int = 2) -> QWidget:
        """One of the section's tables, its first column with a larger share (``first``), as the web page's tables share
        the width."""
        return self._grid(columns, [[self._cell(c, v) for c in row] for row in rows],
                          {c: first if c == 0 else 1 for c in range(len(columns))})

    # ---------------------------------------------------------------- the timeline (0.2.459)
    def _timeline(self, v: dict, events: list[dict]) -> QWidget:
        """The recorded effect timeline (``timeline``): whose lanes are shown, the window, the lanes, and the effect
        inspected."""
        state = self.state
        model = cw.timeline(v, events, state, self.lanes_hidden, self.lanes_folded, self.colours)
        self.timeline_model = model
        box, column = _plain(spacing=8)
        column.addWidget(_head("Recorded effect timeline"))
        fold = Section(model["visibility"], None, self.lanes_open)
        fold.button.setAccessibleName("Player timeline visibility")
        fold.button.toggled.connect(lambda opened: setattr(self, "lanes_open", opened))
        fold.body_layout.addWidget(_muted(cw.LANE_NOTE))
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        for player in model["players"]:
            tick = QCheckBox(player["label"])
            tick.setChecked(player["shown"])
            tick.toggled.connect(lambda shown, actor=player["id"]: self._lane_shown(actor, shown))
            flow.addWidget(tick)
        flow.addWidget(_button("Show all", self._lanes_all))
        flow.addWidget(_button("Expand all", self._lanes_open_all))
        fold.body_layout.addWidget(row)
        self.lanes_fold = fold
        column.addWidget(_noted(fold))
        controls, line = _plain(QHBoxLayout, 10)
        chosen = next((value for value, _words in model["windows"] if value == model["window"]), None)
        line.addWidget(self._pick("Window", model["windows"], chosen, self._window))
        line.addWidget(_button("Earlier", lambda: self._move_window(v, -1), enabled=model["earlier"]))
        line.addWidget(_button("Later", lambda: self._move_window(v, 1), enabled=model["later"]))
        line.addWidget(_label("Start", wrap=False))
        start = QDoubleSpinBox()
        start.setAccessibleName("Start")
        start.setDecimals(1)
        start.setSingleStep(0.5)
        start.setRange(0.0, model["latest"])
        start.setValue(model["start"])
        start.setKeyboardTracking(False)
        start.valueChanged.connect(self._start)
        line.addWidget(start)
        line.addWidget(_label(model["range"], wrap=False))
        line.addStretch(1)
        column.addWidget(controls)
        scrub = QSlider(Qt.Horizontal)
        scrub.setAccessibleName("Timeline window start")
        scrub.setRange(0, math.floor(model["latest"] * 2))           # half seconds (``step=".5"``)
        scrub.setValue(theme.js_round(model["start"] * 2))
        scrub.sliderReleased.connect(lambda: self._start(scrub.value() / 2))
        scrub.valueChanged.connect(lambda value: None if scrub.isSliderDown() else self._start(value / 2))
        self.scrub = scrub
        column.addWidget(scrub)
        column.addWidget(_muted(model["note"]))
        timeline = Timeline(model, self._lane_name, self._lane_folded, self._skill_picture)
        place = (model["start"], model["span"])
        if self.timeline_place == place and self.timeline_scroll is not None:
            timeline.keep(self.timeline_scroll)                    # scrolled as it was, the window the same
        self.timeline_place, self.timeline_scroll = place, None
        for bar in (timeline.horizontalScrollBar(), timeline.verticalScrollBar()):
            bar.valueChanged.connect(lambda _value, timeline=timeline: setattr(self, "timeline_scroll", timeline.scrolled()))
        if self.pictures is not None:
            self.pictures.changed.connect(timeline.tracks.update)    # a skill's icon read since
        self.timeline = timeline
        column.addWidget(timeline)
        panel = QFrame()
        panel.setObjectName("note")
        panel_line = QVBoxLayout(panel)
        panel_line.setContentsMargins(0, 0, 0, 0)
        words = _label(self.effect or cw.EFFECT_HINT)
        words.setAccessibleName("Effect inspected")
        panel_line.addWidget(words)
        self.effect_words = words
        timeline.inspected.connect(lambda detail: self._inspect_effect(detail))
        column.addWidget(panel)
        return box

    def _inspect_effect(self, detail: str) -> None:
        """An effect inspected (``data-effect-detail``): it stays in the panel while the encounter is shown."""
        self.effect = detail
        self.effect_words.setText(detail)

    def _skill_picture(self, address: str):
        return self.pictures.by_address(address) if self.pictures is not None else None

    def _lane_name(self, lane: dict) -> QWidget:
        """A lane's name in its class's colour (``.cr-lane-name``), with its Collapse and Hide buttons when it is open."""
        cell = QFrame()
        cell.setObjectName("crLaneName")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(self._name(lane["actor"]))
        if not lane["collapsed"]:
            controls, line = _plain(QHBoxLayout, 4)
            line.addWidget(self._lane_button("Collapse", lane, self._lane_fold))
            line.addWidget(self._lane_button("Hide", lane, self._lane_hide))
            line.addStretch(1)
            layout.addWidget(controls)
        layout.addStretch(1)
        return cell

    def _lane_folded(self, lane: dict) -> QWidget:
        """A collapsed lane's own controls, where its markers would be (``.cr-lane-collapsed``)."""
        cell, line = _plain(QHBoxLayout, 4)
        line.setContentsMargins(10, 5, 10, 5)
        line.addWidget(self._lane_button("Expand", lane, self._lane_fold))
        line.addWidget(self._lane_button("Hide", lane, self._lane_hide))
        line.addWidget(_label("Timeline collapsed", "small", wrap=False))
        line.addStretch(1)
        return cell

    @staticmethod
    def _lane_button(words: str, lane: dict, action) -> QWidget:
        button = _button(words, lambda: action(lane["id"]))
        button.setAccessibleName(f"{words} {lane['label']}")
        return button

    def _lane_fold(self, actor) -> None:
        """A lane collapsed, or expanded again (``data-timeline-collapse``)."""
        self.lanes_folded ^= {actor}
        self.draw()

    def _lane_hide(self, actor) -> None:
        self.lanes_hidden.add(actor)
        self.draw()

    def _lane_shown(self, actor, shown: bool) -> None:
        """A player's lane shown or hidden from the lanes' visibility (``data-timeline-visible``)."""
        if shown:
            self.lanes_hidden.discard(actor)
        else:
            self.lanes_hidden.add(actor)
        self.draw()

    def _lanes_all(self) -> None:
        self.lanes_hidden.clear()
        self.draw()

    def _lanes_open_all(self) -> None:
        self.lanes_folded.clear()
        self.draw()

    def _window(self, value) -> None:
        """The window's length chosen (``data-timeline-window``): a number of seconds, or the whole encounter."""
        self.state["timeline_window"] = value if value is not None else 0
        self.draw()

    def _move_window(self, v: dict, direction: int) -> None:
        cw.moved_window(self.state, v["segment"].get("duration"), direction)
        self.draw()

    def _start(self, value) -> None:
        """The window's start typed or scrubbed to (``data-time-start``, ``data-time-scrub``)."""
        self.state["timeline_start"] = float(value)
        self.draw()

    def _summary(self, d: dict, v: dict, parse_column: bool) -> QWidget:
        """Every player's totals (``summary``), with their parses."""
        cells = []
        for row in cw.summary_rows(d, v, self.state):
            line = [self._name(row["actor"])]
            if parse_column:
                badge = cw.parse_badge(self.ranks, row["id"], _dict(row["actor"]).get("class"))
                line.append(_parse_pill(badge["text"], TIER_COLOURS[badge["tier"]], badge["provisional"], badge["tip"]))
            deaths = (html.escape(js_text(row["deaths_count"])) + (f" <span style='color: {C['muted']};'>(revived "
                                                                    f"{row['revives']})</span>" if row["revives"] else "")
                      if row["deaths_count"] else "No markers")
            line += [row["class"], row["damage"], row["dps"], row["taken"], row["healing"], row["hps"], _label(deaths, rich=True)]
            cells.append(line)
        table = GridTable(cw.summary_columns(parse_column), cells, {0: 3}, left=True)
        table.setAccessibleName("Summary")
        self.summary = table
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _quality(self, d: dict) -> QFrame:
        """The capture's quality, folded (``qualityHTML``), with how a cut fight was joined (``stitchedHTML``)."""
        q = cw.quality(self.ranks, d)
        fold = Section(q["summary"], None, False)
        fold.button.setAccessibleName("Capture quality")
        self.quality_fold = fold
        layout = fold.body_layout
        for message in q["messages"]:
            layout.addWidget(_label("• " + message))
        for words in (q["note"], q["driver"], q["processing"]):
            if words:
                layout.addWidget(_label(words))
        for line in cw.stitched(self.ranks, d, self.doc):
            layout.addWidget(_label(line["words"]))
            if line.get("segment") is not None:
                layout.addWidget(_button(line["action"], lambda index=line["segment"]: self.open_segment(index)))
            elif _truthy(line.get("log")):
                layout.addWidget(_button(line["action"], lambda log=line["log"]: self._open_other(log)))
        return _noted(fold)

    def _table(self, columns, rows, stretch=None) -> GridTable:
        """A note's table, its columns sharing the width as the web page's tables do."""
        return GridTable(columns, rows, stretch or {c: 2 if c == 0 else 1 for c in range(len(columns))}, left=True)

    def _runs(self, d: dict) -> QWidget:
        """Run timing and boss progression, folded (``runsHTML``)."""
        runs = cw.run_tables(self.doc, d, self.state, self.ranks)
        if runs["kind"] == "none":
            return _muted(runs["note"])
        fold = Section(runs["title"], None, False)
        fold.button.setAccessibleName(runs["title"])
        self.runs_fold = fold
        layout = fold.body_layout
        if runs["note"]:
            layout.addWidget(_muted(runs["note"]))
        layout.addWidget(self._table(runs["columns"], runs["rows"]))
        progression = runs.get("progression")
        if progression:
            layout.addWidget(_head(progression["title"]))
            layout.addWidget(self._table(progression["columns"], progression["rows"]))
            layout.addWidget(self._table(progression["attempts_columns"], progression["attempts"]))
        return _noted(fold)

    def _arena(self, a: dict) -> QFrame:
        """An arena match from the game's own records (``arenaHTML``)."""
        frame = QFrame()
        frame.setObjectName("note")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(_head(a["title"]))

        def who(x):
            if x["actor"]:
                return self._name(x["actor"])
            colour = cr.class_colour(x["class"], self.colours)
            return _label(f"<span style='color: {colour};'>{html.escape(x['name'])}</span>", rich=True)
        fighters = []
        for f in a["fighters"]:
            name = who(f)
            if f["self"]:
                name.setText(name.text() + f" <span style='color: {C['muted']};'>(recording player)</span>")
            fighters.append([name, f["class"], f["server"], f["faction"], f["rating"], f["won"]])
        layout.addWidget(self._table(["Fighter", "Class", "Server", "Faction", "Rating before", "Rounds won here"], fighters))
        layout.addWidget(self._table(["Round", "Ended at", "Winner", "Loser"],
                                     [[x["round"], x["at"], who(x["winner"]), who(x["loser"])] for x in a["rounds"]]))
        layout.addWidget(_muted(cw.ARENA_NOTE))
        return frame

    def _opponent(self, o: dict) -> QFrame:
        """A PvP opponent chosen under Player (``opponentHTML``)."""
        frame = QFrame()
        frame.setObjectName("note")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        colour = cr.class_colour(o["actor"].get("class"), self.colours)
        heading = (f"Opponent · <span style='color: {colour};'>{html.escape(cw.actor_label(o['actor']))}</span>"
                   + (f" · {html.escape(o['class'][:1].upper() + o['class'][1:])}" if o["class"] else ""))
        layout.addWidget(_label(heading, "combatHead", rich=True))
        layout.addWidget(_muted(cw.OPPONENT_NOTE))
        layout.addWidget(_label(o["recorded"]))
        for title, rows, columns in (("Damage done by target", o["dealt"], ["Target", "Damage", "Share", "Hits", "Largest hit", "DPS"]),
                                     ("Damage taken by source", o["taken"],
                                      ["Source", "Damage", "Share", "Hits", "Largest hit", "Per second"])):
            layout.addWidget(_label(f"<b>{title}</b>", rich=True))
            cells = [[self._name(r["actor"]), r["amount"], r["share"], r["hits"], r["max"], r["rate"]] for r in rows]
            layout.addWidget(self._table(columns, cells))
        return frame
