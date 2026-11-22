"""The native Live Meter page (pages/meter.js ``pageMeter`` and ``renderMeter``); its words and figures are in
``live_meter``. Since 0.2.471:

- **the capture**: the source (a custom decoder chosen as a file), Start or Stop, Show overlay when starting (kept by
  the app), Clear session, Save to Combat Logs, Export a2log, Upload, Screenshot (the page's whole content as a PNG the
  app saves), Split now, Finish run, Hide overlay and Open overlay. An action's button says what it is doing until it
  is done; the line under the controls, and the note at the page's foot for a while, say what it did. Start checks
  the packet-capture support first, offering to install it, and opens the overlay when asked; Stop saves the session
  and uploads it unless Settings says not to;
- **Advanced capture**, the part Start reads: the network interface, the game host, the game port found or fixed, the
  name override, and the final bosses whose death finishes a run. The game installation, the game version and capture
  context and the capture diagnostics are still in the web interface's Live Meter, and say so;
- **the view**: the players' scope (kept), Combine pets with owner, Automatic splits and the time without outgoing
  damage that splits a fight, the combat retained to view, All enemies and Follow latest combat;
- **the state**: Recording or Stopped with the packets and combat events so far, Npcap's setup while it is missing,
  the region's retry when the official lookup failed, the run, the character found, where the session is saved, and
  what the last action did;
- **the fight**: why there is nothing yet; the enemies, one chosen showing each player's damage against it; the
  players with their bars, one chosen to show its parse card under them; the ping and the game's counters. A part is
  drawn again only when what it shows changed.

The page reads ``/api/meter`` while it is shown: every 0.7 s while capturing (1.5 s in performance mode), every 1.2 s
otherwise (2 s), every 0.3 s for its first six seconds to catch a start at launch, and every 3 s while its window is
minimized. The session's live review is still in the web interface's Live Meter, and says so.
"""
from __future__ import annotations

import base64
import html
import json
import os
import time

from PySide6.QtCore import (QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, QPoint, QSize, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QRegion
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import live_meter as lm
from . import theme
from .api import AppApi, Job, Poller, Requests, why
from .chrome import FlowLayout, icon
from .combat import safe_link
from .combat_analysis_page import STYLE as ANALYSIS_STYLE, Bar, ParseCard
from .combat_community import _note
from .combat_saved import _button, _clear, _label
from .database_page import Window
from .gathering_page import GatheringPage
from .overlay import COUNTER_ICONS, COUNTER_TIPS, counter_lines
from .pets_page import Toast
from .pictures import ODYLE_ICON, Pictures
from .planner_page import interface_store
from .result_windows import STYLE as RESULT_STYLE, GridTable
from .results import _dict, _list, _truthy, js_text

C = theme.COLORS
TOAST_MS = 6000                          # ``toast(…, 6000)``: an action's words at the page's foot
DECODER_MOST = 1048576                   # a custom decoder's file is smaller than 1 MiB
WAIT_S = 120                             # how long an action may take (Stop saves the session and its diagnostics)
READ_S = 8                               # how long a reading may take (``meterStatus``)
WARMING_S = 6                            # the first seconds read briskly, to catch a start at launch
ADVANCED_KEY = "meter-advanced-open"     # whether Advanced capture was left open
#: The requests to ``/api/meter``, whose answer is the meter's state: an ``error`` in it is part of what it reports
#: (why a capture did not start), not a refusal.
METER_ASKS = {"view", "clear", "start", "stop", "region", "act:save", "act:export", "act:split", "act:finish"}
COUNTER_GOLD = "#e8cf8e"                 # a counter's icon (``.keyicon``, ``.ticketicon``, ``.runicon``)
STYLE = f"""
    QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
        border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
    QPushButton#danger {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #a32c36, stop:1 #682029);
        border: 1px solid #d75c66; color: #fff; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
    QPushButton#primary:disabled, QPushButton#danger:disabled {{ color: rgba(255, 243, 207, 0.5); }}
    QLabel#small, QFrame#note QLabel#small, QCheckBox#small {{ color: {C['muted']}; font-size: 12px; }}
    QLabel#faintSmall {{ color: {C['faint']}; font-size: 12px; }}
    QLabel#status {{ font-size: 12px; }}
    QFrame#win QLabel#empty {{ color: {C['faint']}; padding: 18px; }}
    QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
        padding: 9px 12px; }}
    QFrame#note QLabel, QFrame#note QCheckBox, QFrame#note QWidget#plain {{ background: transparent; }}
    QFrame#note QLabel {{ color: #f1d4a3; }}
    QToolButton#fold {{ color: #f1d4a3; font-weight: 700; border: none; background: transparent; padding: 2px 0px; }}
    QFrame#pm {{ background: transparent; border: none; }}
    QFrame#pm QLabel {{ background: transparent; }}
    QWidget#counter, QWidget#counter QLabel {{ background: transparent; }}
"""


# ------------------------------------------------------------------ the parts
class InlineLabel(QLabel):
    """Words among a row's controls (a ``span`` in a ``.row``): as wide as they are on one line, so the row puts
    them beside the controls where they fit and under them where they do not, wrapping only when even a line of
    their own is too narrow (a wrapping label would ask for a narrow column)."""

    def __init__(self, text: str = "", name: str = "small", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName(name)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)

    def sizeHint(self) -> QSize:
        if not self.text():
            return QSize(0, 0)
        margins = self.contentsMargins()
        width = (self.fontMetrics().horizontalAdvance(self.text()) + margins.left() + margins.right()
                 + 2 * self.margin() + 1)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0) if not self.text() else QSize(0, super().minimumSizeHint().height())


class _Summary(QLabel):
    """A ``<summary>``'s words beside its arrow: choosing them opens or closes the part too."""

    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Details(QFrame):
    """A ``<details class="note">``: its summary (a bold title and muted words) opens and closes its body.
    ``toggled`` tells of each change."""

    toggled = Signal(bool)

    def __init__(self, title: str, sub: str, opened: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("note")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        head = QWidget()
        head.setObjectName("plain")
        line = QHBoxLayout(head)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.button = QToolButton()
        self.button.setObjectName("fold")
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.button.setAccessibleName(title)
        line.addWidget(self.button)
        self.sub = _Summary(sub)
        self.sub.setObjectName("small")
        self.sub.setWordWrap(True)
        self.sub.setCursor(Qt.PointingHandCursor)
        self.sub.clicked.connect(self.button.toggle)
        line.addWidget(self.sub, 1)
        column.addWidget(head)
        self.inside = QWidget()
        self.inside.setObjectName("plain")
        self.body = QVBoxLayout(self.inside)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        column.addWidget(self.inside)
        self.button.setChecked(opened)
        self._shown(opened)
        self.button.toggled.connect(self._toggled)

    def _shown(self, opened: bool) -> None:
        self.button.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.inside.setVisible(opened)

    def _toggled(self, opened: bool) -> None:
        self._shown(opened)
        self.toggled.emit(opened)

    def is_open(self) -> bool:
        return self.button.isChecked()

    def set_open(self, opened: bool) -> None:
        self.button.setChecked(opened)


class PlayerRow(QFrame):
    """A player of the fight (``.pm``): their name, server and class in a 150 px column, then their DPS against the
    fastest's as a bar; the chosen player's name gold. Choosing a row shows its parse card."""

    def __init__(self, row: dict, chosen: bool, choose, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pm")
        self.chosen, self.choose = chosen, choose
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"{row['name']} · {row['words']}")
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 3, 0, 3)
        line.setSpacing(10)
        muted = C["muted"]
        who = f"<b style='color: {C['gold'] if chosen else C['text']};'>{html.escape(row['name'])}</b>"
        if row["server"]:
            who += f" <span style='color: {muted}; font-size: 12px;'>· {html.escape(row['server'])}</span>"
        who += f" <span style='color: {muted}; font-size: 12px;'>{html.escape(row['class'])}</span>"
        self.who = _label(who, rich=True)
        self.who.setFixedWidth(150)
        line.addWidget(self.who, 0, Qt.AlignVCenter)
        self.bar = Bar(row["share"], row["words"])
        line.addWidget(self.bar, 1, Qt.AlignVCenter)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.choose()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.choose()
            return
        super().keyPressEvent(event)


def counter_line(key: str, words: str, pictures: Pictures | None, ratio: float = 1.0) -> QWidget:
    """A counter of the game's (``p.odyle``): its icon, 20 px, then its words; its tip says what it counts. The Odyle
    Energy's icon is the game's recharge item, where the app has its art; the others are drawn in the counters' gold."""
    row = QWidget()
    row.setObjectName("counter")
    row.setToolTip(COUNTER_TIPS[key])
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    mark = QLabel()
    mark.setFixedSize(20, 20)
    if key == "odyle":
        picture = pictures.item(ODYLE_ICON) if pictures is not None else None
        if picture is not None and not picture.isNull():
            sized = picture.scaled(round(20 * ratio), round(20 * ratio), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            sized.setDevicePixelRatio(ratio)
            mark.setPixmap(sized)
    else:
        mark.setPixmap(icon(COUNTER_ICONS[key], 20, 20, COUNTER_GOLD, ratio))
    line.addWidget(mark, 0, Qt.AlignVCenter)
    line.addWidget(_label(words, "small"), 1, Qt.AlignVCenter)
    return row


# ------------------------------------------------------------------ the page
class MeterPage(QWidget):
    """The Live Meter page. ``open_page`` shows another page of the window (Combat Logs, for a log saved),
    ``open_link`` an address in the browser (a shared log), ``open_in_web`` a page in the web interface (what is not
    drawn here yet), ``open_window`` the overlay's own page in a window when the app cannot open its overlay window;
    ``pictures`` gives the parse card's and the counters' pictures, ``store`` keeps the players' scope and Advanced
    capture's choices; ``ask`` and ``choose_file`` stand in for the questions and the file dialog in tests."""

    def __init__(self, api: AppApi | None, parent: QWidget | None = None, open_page=None, open_link=None,
                 open_in_web=None, open_window=None, pictures: Pictures | None = None, store=None, ask=None,
                 choose_file=None):
        super().__init__(parent)
        self.api = api
        self.open_page, self.open_in_web = open_page, open_in_web
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.open_window = open_window or _browser_window
        self.store = store if store is not None else interface_store()
        self.ask = ask or (lambda question: QMessageBox.question(self, "Live Meter", question) == QMessageBox.Yes)
        self.choose_file = choose_file or (lambda: QFileDialog.getOpenFileName(self, "Decoder file", "",
                                                                                "Python decoder (*.py)")[0])
        self.pictures = pictures if pictures is not None else (Pictures(api, self) if api is not None else None)
        self.answer: dict = {}                   # the last reading (``renderMeter``'s ``s``)
        self.first = True                        # a visit's first reading sets the source (``initial.source``)
        self.started = False                     # the window has started its pages
        self.mounted = False                     # reading the meter while shown
        self.started_at = time.monotonic()
        self.light = False                       # performance mode (Settings → App & data)
        self.pinned = ""                         # the combat pinned (``st.pinnedSegment``)
        self.chosen_key = None                   # the player whose parse card shows (``st.selectedPlayerKey``)
        self.parts: dict[str, str | None] = {}   # what each part of the fight was drawn from
        self.busy = False                        # a Start or Stop on its way (``st.captureBusy``)
        self.checking = False                    # Start checking the packet-capture support
        self.setup: dict = {}                    # what that check found
        self.show_overlay = True                 # Show overlay when starting, as Start was pressed
        self.decoder: str | None = None          # the custom decoder the app keeps (``decoderPath``)
        self.no_overlay_window = False           # the app could not open its overlay window (``nativeOverlayUnavailable``)
        self.acting: dict[str, str] = {}         # the actions under way, each with what its button says meanwhile
        self.shot_scaled = False
        self.setObjectName("plain")
        self.setStyleSheet(GatheringPage._stylesheet() + RESULT_STYLE + STYLE + ANALYSIS_STYLE + Toast.STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)
        self.content = QWidget()
        self.scroll.setWidget(self.content)
        self.column = QVBoxLayout(self.content)
        self.column.setContentsMargins(24, 20, 24, 20)
        self.column.setSpacing(14)
        self.capture = Window(lm.HEAD, lm.SUB)
        self.column.addWidget(self.capture)
        self._controls(self.capture.body)
        self.slots: dict[str, QVBoxLayout] = {}
        for key in ("empty", "warning", "enemies", "players", "parse"):       # ``#mview``, a part at a time
            slot = QWidget()
            slot.setObjectName("plain")
            box = QVBoxLayout(slot)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(0)
            slot.hide()
            self.slots[key] = box
            self.column.addWidget(slot)
        self.column.addWidget(self._elsewhere(lm.ELSEWHERE_REVIEW))           # ``#mlog-review``
        self.column.addStretch(1)
        self.toast = Toast(self)

        self.requests = Requests(api, self, timeout=WAIT_S) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.upload_job = self._job(self._uploaded, self._upload_failed)
        self.stop_job = self._job(self._stop_uploaded, self._stop_upload_failed)
        self.poller = Poller(api, "/api/meter", 300, self, timeout=READ_S, explain=why) if api is not None else None
        if self.poller is not None:
            self.poller.answered.connect(self.apply)
            self.poller.failed.connect(self._poll_failed)
        self.redraw = QTimer(self)                # the counters drawn again once their pictures have come
        self.redraw.setSingleShot(True)
        self.redraw.setInterval(120)
        self.redraw.timeout.connect(self._pictures_came)
        if self.pictures is not None:
            self.pictures.changed.connect(self.redraw.start)
        self.render({"snapshot": {"players": []}})

    def _job(self, done, failed) -> Job | None:
        if self.api is None:
            return None
        job = Job(self.api, self)
        job.logged.connect(lambda lines: self._say(js_text(lines[-1])) if lines else None)
        job.done.connect(done)
        job.failed.connect(failed)
        return job

    # ---------------------------------------------------------------- the controls
    def _row(self, body) -> FlowLayout:
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        body.addWidget(row)
        return flow

    def _controls(self, body) -> None:
        flow = self._row(body)
        flow.addWidget(_label("Source", "small", wrap=False))
        self.source = QComboBox()
        self.source.setAccessibleName("Source")
        for value, words in lm.SOURCES:
            self.source.addItem(words, value)
        self.source.activated.connect(lambda _i: self._source_shown())
        flow.addWidget(self.source)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primary")
        self.start_button.setAccessibleName("Start")
        self.start_button.clicked.connect(self.start_stop)
        flow.addWidget(self.start_button)
        self.overlay_on_start = QCheckBox("Show overlay when starting")
        self.overlay_on_start.setObjectName("small")
        self.overlay_on_start.setChecked(True)
        self.overlay_on_start.clicked.connect(self._overlay_choice)
        flow.addWidget(self.overlay_on_start)
        self.clear_button = _button("Clear session", self.clear)
        flow.addWidget(self.clear_button)
        self.actions: dict[str, QPushButton] = {}
        for key in ("save", "export", "upload", "screenshot", "split", "finish", "hide", "overlay"):
            self.actions[key] = button = _button(lm.ACTIONS[key][0], lambda key=key: self.act(key))
            if key == "overlay":
                button.setToolTip(lm.OVERLAY_TIP)
            flow.addWidget(button)
        self.message = InlineLabel()                                         # ``#mmsg``
        flow.addWidget(self.message)

        self.custom = QWidget()                                              # ``#mcustom``
        self.custom.setObjectName("plain")
        line = FlowLayout(self.custom, align=Qt.AlignLeft, gap=(12, 8))
        line.addWidget(_label("Decoder file", "small", wrap=False))
        self.decoder_button = _button("Choose file…", self.choose_decoder)
        self.decoder_button.setAccessibleName("Decoder file")
        line.addWidget(self.decoder_button)
        self.decoder_name = InlineLabel(lm.DECODER_HINT)                     # ``#mdecodername``
        line.addWidget(self.decoder_name)
        self.custom.hide()
        body.addWidget(self.custom)

        self.npcap = QWidget()                                               # ``#npcap``: Npcap missing
        self.npcap.setObjectName("plain")
        line = FlowLayout(self.npcap, align=Qt.AlignLeft, gap=(6, 6))
        self.npcap_words = InlineLabel("", "status")
        line.addWidget(self.npcap_words)
        self.npcap_button = _button("", self._npcap_action)
        line.addWidget(self.npcap_button)
        self.npcap_after = InlineLabel("", "status")
        line.addWidget(self.npcap_after)
        self.npcap.hide()
        body.addWidget(self.npcap)
        self.npcap_again = QTimer(self)
        self.npcap_again.setSingleShot(True)
        self.npcap_again.setInterval(lm.NPCAP_AGAIN_MS)
        self.npcap_again.timeout.connect(self.read_npcap)

        flow = self._row(body)
        flow.addWidget(_label("Players", "small", wrap=False))
        self.scope = QComboBox()
        self.scope.setAccessibleName("Players")
        for value, words in lm.SCOPES:
            self.scope.addItem(words, value)
        kept = self.store.value(lm.SCOPE_KEY)
        self.scope.setCurrentIndex(self.scope.findData(kept if kept in dict(lm.SCOPES) else "party"))
        self.scope.activated.connect(lambda _i: self._scope_chosen())
        flow.addWidget(self.scope)
        self.combine_pets = QCheckBox("Combine pets with owner")
        self.combine_pets.setObjectName("small")
        self.combine_pets.setChecked(True)
        self.combine_pets.clicked.connect(lambda on: self.view_choice({"combine_pets": on}))
        flow.addWidget(self.combine_pets)
        self.auto_split = QCheckBox("Automatic splits")
        self.auto_split.setObjectName("small")
        self.auto_split.setChecked(True)
        self.auto_split.clicked.connect(lambda on: self.view_choice({"automatic_splits": on}))
        flow.addWidget(self.auto_split)
        flow.addWidget(_label("Split after no outgoing damage for", "small", wrap=False))
        self.gap = QSpinBox()
        self.gap.setAccessibleName("Split after no outgoing damage for (seconds)")
        self.gap.setRange(lm.GAP_LEAST, lm.GAP_MOST)
        self.gap.setValue(lm.GAP)
        self.gap.setKeyboardTracking(False)          # changed as the web page's ``change``: typed and left, or stepped
        self.gap.valueChanged.connect(lambda value: self.view_choice({"segment_gap": value or lm.GAP}))
        flow.addWidget(self.gap)
        flow.addWidget(_label("seconds", "small", wrap=False))
        flow.addWidget(_label("Combat", "small", wrap=False))
        self.segments = QComboBox()
        self.segments.setAccessibleName("Combat")
        for value, words in lm.segment_options({}):
            self.segments.addItem(words, value)
        self.segments.activated.connect(lambda _i: self._segment_chosen())
        flow.addWidget(self.segments)
        flow.addWidget(_button("All enemies", lambda: self.view_choice({"enemy": None})))
        self.follow = _button("Follow latest combat", self.follow_latest)
        self.follow.hide()
        flow.addWidget(self.follow)
        self.view_words = InlineLabel()                                      # ``#mviewstate``
        flow.addWidget(self.view_words)

        self.region = QWidget()                                              # ``#mregionretry``, ``#mregionmsg``
        self.region.setObjectName("plain")
        line = FlowLayout(self.region, align=Qt.AlignLeft, gap=(12, 8))
        self.region_button = _button(lm.REGION_RETRY, self.retry_region)
        self.region_button.hide()
        line.addWidget(self.region_button)
        self.region_words = InlineLabel()
        line.addWidget(self.region_words)
        self.region.hide()                                                   # nothing in it: no room taken
        body.addWidget(self.region)

        self.lines: dict[str, QLabel] = {}
        for key in ("run", "identity", "saved", "notice"):     # ``#mrun``, ``#midentity``, ``#msaved``, ``#mnotice``
            label = _label("", "status", rich=key == "notice")
            label.linkActivated.connect(self._link)
            label.hide()
            self.lines[key] = label
            body.addWidget(label)
        self.notice_text = ""                                                # ``#mnotice``'s words alone

        opened = self.store.value(ADVANCED_KEY) in ("1", 1, True, "true")
        self.advanced = Details(lm.ADVANCED, lm.ADVANCED_SUB, opened)       # ``#madvanced``
        self.advanced.toggled.connect(lambda on: self.store.setValue(ADVANCED_KEY, "1" if on else "0"))
        body.addWidget(self.advanced)
        self._advanced(self.advanced.body)
        self._source_shown()

    def _advanced(self, body) -> None:
        """Advanced capture's part that Start reads (``#mlive`` and the final boss's row), then its words."""
        self.live = QWidget()                                                # ``#mlive``: not for the demo replay
        self.live.setObjectName("plain")
        line = FlowLayout(self.live, align=Qt.AlignLeft, gap=(12, 8))
        line.addWidget(_label("Encoder", "small", wrap=False))
        encoder = QLineEdit(lm.ENCODER)
        encoder.setReadOnly(True)
        encoder.setAccessibleName("Encoder module")
        encoder.setFixedWidth(206)
        line.addWidget(encoder)
        line.addWidget(_label("Interface", "small", wrap=False))
        self.iface = QComboBox()
        self.iface.setAccessibleName("Capture interface")
        self.iface.setToolTip("Npcap interface; Auto monitors all available adapters")
        self.iface.addItem("Auto", "auto")
        line.addWidget(self.iface)
        self.actions["interfaces"] = _button(lm.ACTIONS["interfaces"][0], lambda: self.act("interfaces"))
        line.addWidget(self.actions["interfaces"])
        line.addWidget(_label("Game host", "small", wrap=False))
        self.host = QLineEdit("any")
        self.host.setAccessibleName("Game host")
        self.host.setToolTip("Use an address to limit the capture; any accepts game traffic on the port")
        self.host.setFixedWidth(115)
        line.addWidget(self.host)
        self.auto_port = QCheckBox("Detect game port")
        self.auto_port.setObjectName("small")
        self.auto_port.setChecked(True)
        line.addWidget(self.auto_port)
        line.addWidget(_label("Fixed port", "small", wrap=False))
        self.port = QSpinBox()
        self.port.setAccessibleName("Game server port")
        self.port.setRange(0, 65535)
        self.port.setValue(lm.PORT)
        self.port.setFixedWidth(92)
        line.addWidget(self.port)
        line.addWidget(_label("Name override (optional)", "small", wrap=False))
        self.character = QLineEdit(str(self.store.value(lm.CHARACTER_KEY) or ""))
        self.character.setAccessibleName("Name override (optional)")
        self.character.setPlaceholderText("Auto-detect")
        self.character.setFixedWidth(138)
        self.character_kept = self.character.text()
        self.character.editingFinished.connect(self._character_chosen)
        line.addWidget(self.character)
        body.addWidget(self.live)

        row = QWidget()
        row.setObjectName("plain")
        line = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 8))
        self.auto_finish = QCheckBox("Finish on configured final-boss death")
        self.auto_finish.setChecked(True)
        line.addWidget(self.auto_finish)
        line.addWidget(_label("Final-boss NPC type IDs", wrap=False))
        self.final_bosses = QLineEdit(str(self.store.value(lm.FINAL_BOSS_KEY) or ""))
        self.final_bosses.setAccessibleName("Final-boss NPC type IDs")
        self.final_bosses.setPlaceholderText("Comma-separated verified NPC IDs")
        self.final_bosses.setMinimumWidth(240)
        self.final_bosses.editingFinished.connect(
            lambda: self.store.setValue(lm.FINAL_BOSS_KEY, self.final_bosses.text()))
        line.addWidget(self.final_bosses)
        body.addWidget(row)
        body.addWidget(_label(lm.FINAL_NOTE, "small"))
        self.engine = _label(lm.ENGINE_NOTE.format(""), "faintSmall")        # with ``#npcapinfo``
        body.addWidget(self.engine)
        body.addWidget(self._elsewhere(lm.ELSEWHERE_ADVANCED))

    def _elsewhere(self, words: str) -> QWidget:
        """What is not drawn here yet, with a way to it in the web interface."""
        box = QWidget()
        box.setObjectName("plain")
        line = QHBoxLayout(box)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        line.addWidget(_label(words, "small"), 1)
        button = _button(lm.ELSEWHERE_OPEN, lambda: self.open_in_web("meter") if self.open_in_web else None)
        button.setEnabled(self.open_in_web is not None)
        line.addWidget(button, 0, Qt.AlignVCenter)
        return box

    def _source_shown(self) -> None:
        """The source's own rows (``live``): Advanced capture's for a capture, a decoder's file for a custom decoder."""
        source = self.source.currentData()
        self.live.setVisible(source != "replay")
        self.custom.setVisible(source == "live")

    def _overlay_choice(self, on: bool) -> None:
        """Show overlay when starting, kept by the app (``overlay_on_start``)."""
        if self.requests is not None:
            self.requests.post(f"overlay-choice:{int(on)}", "/api/ui", {"overlay_on_start": on})

    def _scope_chosen(self) -> None:
        self.store.setValue(lm.SCOPE_KEY, self.scope.currentData())
        self.view_choice({"scope": self.scope.currentData()})

    def _segment_chosen(self) -> None:
        self.pinned = self.segments.currentData() or ""
        self.view_choice({"segment": self.pinned})

    def _character_chosen(self) -> None:
        """A name override typed (``#mchar``'s ``change``): kept, and the view told of it."""
        if self.character.text() == self.character_kept:
            return
        self.character_kept = self.character.text()
        name = self.character.text().strip()
        self.store.setValue(lm.CHARACTER_KEY, name)
        self.view_choice({"character_name": name})

    def follow_latest(self) -> None:
        self.pinned = ""
        self.view_choice({"segment": None, "enemy": None})

    def view_choice(self, body: dict) -> None:
        """A choice of what the meter shows (``updateView``): the reading it answers is shown."""
        if self.requests is not None:
            self.requests.post("view", "/api/meter", {"action": "view", **body})

    def choose_decoder(self) -> None:
        """A custom decoder's file (``#mcustomdec``): read here, then kept by the app until capture starts."""
        path = self.choose_file()
        self.decoder = None
        if not path:
            return
        try:
            if os.path.getsize(path) > DECODER_MOST:
                raise ValueError(lm.DECODER_TOO_LARGE)
            with open(path, encoding="utf-8") as f:
                source = f.read()
        except (OSError, ValueError) as exc:          # a file that does not read as text is refused here
            self.decoder_name.setText(str(exc))
            return
        if self.requests is not None:
            self.requests.post("decoder", "/api/meter/decoder", {"name": os.path.basename(path), "source": source})

    # ---------------------------------------------------------------- reading the meter
    def start(self) -> None:
        """Begin reading the app: now if the page is shown, else when it is."""
        self.started = True
        if self.isVisible():
            self._mount()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.started and not event.spontaneous():
            self._mount()

    def hideEvent(self, event) -> None:
        if not event.spontaneous():                   # another page chosen: a minimized window keeps reading, slower
            self.mounted = False
            if self.poller is not None:
                self.poller.pause()
        super().hideEvent(event)

    def _mount(self) -> None:
        """The page opened (``pageMeter``): the app's settings, Npcap's state and the capture interfaces read, then
        the meter, briskly at first."""
        if self.mounted or self.api is None:
            return
        self.mounted = True
        self.first = True                             # the source the app captures from, as each visit shows it
        self.started_at = time.monotonic()
        self.parts.clear()                            # drawn afresh (``st.lastMeterRender = null``)
        self.requests.get("ui", "/api/ui")
        self.read_npcap()
        self.requests.get("interfaces", "/api/meter/interfaces")
        self.poller.set_interval(self._pace())
        self.poller.start()

    def stop(self) -> None:
        """The window closing: no more readings or requests."""
        for worker in (self.poller, self.requests):
            if worker is not None:
                worker.stop()

    def _pace(self) -> int:
        """How soon the meter is read again (``poll``'s pace)."""
        window = self.window()
        if window is not None and window.isMinimized():
            return 3000
        if _truthy(self.answer.get("running")):
            return 1500 if self.light else 700
        if time.monotonic() - self.started_at < WARMING_S:
            return 300
        return 2000 if self.light else 1200

    def _poll_failed(self, why: str) -> None:
        self.message.setText(f"Could not refresh the meter: {why}. Last readings retained; capture status is unknown. "
                             "Export capture diagnostics, or wait for automatic retry.")
        if self.poller is not None:
            self.poller.set_interval(self._pace())

    def apply(self, answer) -> None:
        """A reading of ``/api/meter``, while the page is shown."""
        if not self.mounted and self.api is not None:
            return
        answer = _dict(answer)
        if self.first:
            self.first = False
            index = self.source.findData(answer.get("source")) if _truthy(answer.get("source")) else -1
            if index >= 0:
                self.source.setCurrentIndex(index)
                self._source_shown()
        self.render(answer)
        if self.poller is not None:
            self.poller.set_interval(self._pace())

    def render(self, s: dict) -> None:
        """A reading shown (``renderMeter``)."""
        self.answer = s = _dict(s)
        running, finalizing = _truthy(s.get("running")), _truthy(s.get("finalizing"))
        self.combine_pets.setChecked(s.get("combine_pets") is not False)
        self.region_button.setVisible(lm.region_retry_shown(s))
        self._region_shown()
        run = lm.run_text(s)
        if run is not None:                           # the run stays as it was when the reading has none
            self._line("run", run)
        self._line("identity", lm.identity_text(s))
        self._line("saved", lm.saved_text(s))
        self.start_button.setEnabled(not self.busy and not finalizing)
        self.start_button.setText("Saving…" if finalizing else "Stop" if running else "Start")
        self.start_button.setAccessibleName(self.start_button.text())
        if self.start_button.objectName() != ("danger" if running else "primary"):
            self.start_button.setObjectName("danger" if running else "primary")
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
        self.clear_button.setEnabled(not running and not finalizing)
        snap = _dict(s.get("snapshot"))
        scope = snap.get("scope")
        if _truthy(scope):
            self.scope.setCurrentIndex(self.scope.findData(scope))
        words, follow = lm.view_state(snap)
        self.view_words.setText(words)
        self.follow.setVisible(follow)
        if _truthy(snap.get("segments")) and not self.segments.hasFocus() and not self.segments.view().isVisible():
            options = lm.segment_options(snap)
            if [(self.segments.itemData(i), self.segments.itemText(i)) for i in range(self.segments.count())] != options:
                self.segments.clear()
                for value, text in options:
                    self.segments.addItem(text, value)
            self.segments.setCurrentIndex(self.segments.findData(lm.segment_chosen(snap, self.pinned)))
        self.message.setText(lm.status_text(s))
        self._fight(s, snap)

    def _line(self, key: str, words: str) -> None:
        label = self.lines[key]
        label.setText(words)
        label.setVisible(bool(words))

    def _say(self, words: str, link: tuple[str, str] | None = None) -> None:
        """What the last action did (``#mnotice``), a link after it."""
        self.notice_text = words + (f" — {link[0]}" if link is not None else "")
        markup = html.escape(words)
        if link is not None:
            markup += (f" — <a href='{html.escape(link[1], quote=True)}' style='color: {C['accent']};'>"
                       f"{html.escape(link[0])}</a>")
        self._line("notice", markup)

    def _toast(self, words: str, ms: int | None = None) -> None:
        self.toast.say(words)
        if ms is not None:
            self.toast.timer.start(ms)

    def _link(self, href: str) -> None:
        if href == "#/combat":
            if self.open_page is not None:
                self.open_page("combat")
            return
        link = safe_link(href)
        if link:
            self.open_link(link)

    # ---------------------------------------------------------------- the fight
    def _fight(self, s: dict, snap: dict) -> None:
        """The fight (``#mview``): each part drawn again only when what it shows changed."""
        players = _list(snap.get("players"))
        if not players:
            self._part("empty", lm.empty_text(s), self._empty)
            for key in ("warning", "enemies", "players", "parse"):
                self._part(key, None, None)
            return
        self._part("empty", None, None)
        index = lm.chosen_player(snap, self.chosen_key)
        player = _dict(players[index])
        self.chosen_key = player.get("key") or player.get("id")
        warning = js_text(snap["warning"]) if _truthy(snap.get("warning")) else None
        self._part("warning", warning, _note)
        enemies = lm.enemy_rows(snap)
        self._part("enemies", enemies or None, self._enemies)
        players_part = {"sub": lm.players_sub(snap), "rows": lm.player_rows(snap), "chosen": index,
                        "ping": lm.ping_text(snap), "counters": counter_lines(snap)}
        self._part("players", players_part, self._players)
        self._part("parse", lm.parse_from_meter(snap, index), lambda d: ParseCard(d, self.pictures))

    def _part(self, key: str, what, draw) -> None:
        """One part of the fight: drawn from ``what`` when it changed, gone when there is none."""
        signature = None if what is None else json.dumps(what, sort_keys=True, default=str)
        if key in self.parts and self.parts[key] == signature:
            return
        self.parts[key] = signature
        box = self.slots[key]
        _clear(box)
        if what is not None:
            box.addWidget(draw(what))
        box.parentWidget().setVisible(what is not None)

    def _empty(self, lines: list[str]) -> Window:
        window = Window("Meter")
        words = html.escape(lines[0]) + "".join(f"<p>{html.escape(line)}</p>" for line in lines[1:])
        label = _label(words, "empty", rich=True)
        label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        window.body.addWidget(label)
        return window

    def _enemies(self, enemies: list[dict]) -> Window:
        """The enemies of the view: choosing one shows each player's damage against it."""
        window = Window(lm.ENEMIES, lm.ENEMIES_SUB)
        rows = []
        for e in enemies:
            button = _button(e["name"], lambda key=e["key"]: self.view_choice({"enemy": key}))
            button.setAccessibleName(e["name"])
            rows.append([button, e["damage"], e["dps"]])
        window.body.addWidget(GridTable(["Enemy", "Party damage dealt", "Party DPS"], rows, {0: 1, 1: 1, 2: 1}, left=True))
        return window

    def _players(self, part: dict) -> Window:
        """The players with their bars, the ping and the game's counters."""
        window = Window(lm.PLAYERS, part["sub"])
        rows = QWidget()
        rows.setObjectName("plain")
        column = QVBoxLayout(rows)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for i, row in enumerate(part["rows"]):
            column.addWidget(PlayerRow(row, i == part["chosen"], lambda i=i: self.choose_player(i)))
        window.body.addWidget(rows)
        if part["ping"]:
            window.body.addWidget(_label(part["ping"], "small"))
        ratio = self.devicePixelRatioF()
        for key, words, _short in part["counters"]:
            window.body.addWidget(counter_line(key, words, self.pictures, ratio))
        return window

    def _pictures_came(self) -> None:
        """A picture arrived: the counters drawn again with it (the parse card draws its own again)."""
        self.parts.pop("players", None)
        self._fight(self.answer, _dict(self.answer.get("snapshot")))

    def choose_player(self, index: int) -> None:
        """A player chosen (``data-sel``): their row marked and their parse card shown."""
        players = _list(_dict(self.answer.get("snapshot")).get("players"))
        if 0 <= index < len(players):
            self.chosen_key = _dict(players[index]).get("key") or _dict(players[index]).get("id")
            self._fight(self.answer, _dict(self.answer.get("snapshot")))

    # ---------------------------------------------------------------- Npcap and the region
    def read_npcap(self) -> None:
        if self.requests is not None:
            self.requests.get("npcap", "/api/npcap")

    def _npcap(self, state: dict) -> None:
        """Npcap's state (``refreshNpcap``): what to do above the meter, or a line under Advanced capture."""
        if not state["shown"]:
            self.npcap.hide()
            self.engine.setText(lm.ENGINE_NOTE.format(state["info"]))
            return
        self.npcap.show()
        self.npcap_words.setText(state["text"])
        self.npcap_button.setText(state.get("button") or "")
        self.npcap_button.setVisible(bool(state.get("button")))
        self.npcap_after.setText(state.get("after") or "")
        self.npcap_after.setVisible(bool(state.get("after")))
        if state.get("again"):
            self.npcap_again.start()

    def _npcap_says(self, words: str) -> None:
        self.npcap.show()
        self.npcap_words.setText(words)
        self.npcap_button.hide()
        self.npcap_after.hide()

    def _npcap_action(self) -> None:
        """Check again, or Install Npcap once asked."""
        if self.requests is None:
            return
        if self.npcap_button.text() != "Install Npcap":
            self.read_npcap()
            return
        if not self.ask(lm.NPCAP_ASK):
            return
        self._npcap_says(lm.NPCAP_STARTING)
        self.requests.post("npcap-install", "/api/npcap", {"action": "install"})

    def _region_shown(self) -> None:
        self.region.setVisible(not self.region_button.isHidden() or bool(self.region_words.text()))

    def _region_says(self, words: str) -> None:
        self.region_words.setText(words)
        self.region_words.updateGeometry()
        self._region_shown()

    def retry_region(self) -> None:
        """Retry region detection (``#mregionretry``)."""
        if self.requests is None:
            return
        self.region_button.setEnabled(False)
        self._region_says(lm.REGION_CHECKING)
        self.requests.post("region", "/api/meter", {"action": "retry-region"})

    # ---------------------------------------------------------------- Start and Stop
    def start_stop(self) -> None:
        """Start or Stop (``#mstart``)."""
        if self.busy or self.checking or _truthy(self.answer.get("finalizing")) or self.requests is None:
            return
        if _truthy(self.answer.get("running")):
            self.busy = True
            self.start_button.setEnabled(False)
            self._say(lm.STOPPING)
            self.requests.post("stop", "/api/meter", {"action": "stop"})
            return
        source = self.source.currentData()
        if source == "live" and not self.decoder:
            self._say(lm.DECODER_FIRST)
            return
        if source == "replay":
            self._start()
            return
        self.checking = True                          # the packet-capture support first
        self.requests.get("setup", "/api/capture/setup")

    def _start(self) -> None:
        source = self.source.currentData()
        body = lm.start_body(source, scope=self.scope.currentData() or "", gap=self.gap.value(), decoder=self.decoder,
                             auto_port=self.auto_port.isChecked(), automatic_splits=self.auto_split.isChecked(),
                             auto_finish=self.auto_finish.isChecked(), final_bosses=self.final_bosses.text(),
                             iface=self.iface.currentData() or "auto", host=self.host.text(), port=self.port.value(),
                             character=self.character.text())
        self.show_overlay = self.overlay_on_start.isChecked()
        self.busy = True
        self.start_button.setEnabled(False)
        self.pinned = ""
        self.requests.post("start", "/api/meter", body)

    def _done(self) -> None:
        """Start or Stop done (``finally``)."""
        self.busy = False
        self.start_button.setEnabled(not _truthy(self.answer.get("finalizing")))

    def clear(self) -> None:
        """Clear session (``#mclear``), asked first."""
        if self.requests is None or not self.ask(lm.CLEAR_ASK):
            return
        self.pinned = ""
        self.requests.post("clear", "/api/meter", {"action": "clear"})

    # ---------------------------------------------------------------- the actions
    def act(self, key: str) -> None:
        """An action (``actionLabels``): its button says what it is doing until it is done."""
        button = self.actions[key]
        if key in self.acting or not button.isEnabled() or self.requests is None:
            return
        pending = lm.ACTIONS[key][1]
        button.setEnabled(False)
        button.setText(pending)
        self.acting[key] = pending
        self._say(pending)
        if key == "save":
            self._say("saving…")
            self.requests.post("act:save", "/api/meter", {"action": "save"})
        elif key == "export":
            self._say("exporting…")
            self.requests.post("act:export", "/api/meter", {"action": "export"})
        elif key == "upload":
            self._say("uploading…")
            self.upload_job.start("/api/meter", {"action": "upload"})
        elif key == "screenshot":
            self._say("capturing screenshot…")
            self.screenshot()
        elif key == "split":
            self.pinned = ""
            self.requests.post("act:split", "/api/meter", {"action": "split"})
        elif key == "finish":
            self.requests.post("act:finish", "/api/meter", {"action": "finish-run"})
        elif key == "hide":
            self.requests.post("act:hide", "/api/overlay", {"action": "hide"})
        elif key == "overlay":
            self._say("opening overlay…")
            self._open_overlay("act:overlay")
        elif key == "interfaces":
            self.requests.get("act:interfaces", "/api/meter/interfaces")

    def _acted(self, key: str, failed: str | None = None) -> None:
        """An action done (``finally``): its button back, and what it did said, for a while at the page's foot too. An
        action whose own words let a failure through says ``Action failed``."""
        pending = self.acting.pop(key, None)
        if pending is None:
            return
        if failed is not None:
            self._say(f"Action failed: {failed}")
        elif self.notice_text == pending:
            self._say(lm.REFRESHED if key == "interfaces" else lm.COMPLETED)
        self._toast(self.notice_text, TOAST_MS)
        button = self.actions[key]
        button.setEnabled(True)
        button.setText(lm.ACTIONS[key][0])

    def _open_overlay(self, name: str) -> None:
        """``openMeterOverlay``: the app's overlay window, else the overlay's page in a window."""
        if self.no_overlay_window:
            self._overlay_answered(name, None)
            return
        self.requests.post(name, "/api/overlay", {})

    def _overlay_answered(self, name: str, answer) -> None:
        words = lm.overlay_words(answer) if answer is not None else None
        if words is None:
            if answer is not None:                    # the app said it cannot: its overlay's page from now on
                self.no_overlay_window = True
            opened = self.open_window(self.api.url("overlay")) if self.api is not None else False
            words = lm.OVERLAY_WINDOW if opened is not False else lm.OVERLAY_BLOCKED
        self._overlay_said(name, words)

    def _overlay_said(self, name: str, words: str) -> None:
        if name == "start-overlay":
            self._say(f"Capture started. {words}")
            self._done()
        else:
            self._say(words)
            self._acted("overlay")

    def screenshot(self) -> None:
        """Screenshot (``A2Screenshot.capture``): the page's whole content, below the fold too, as a PNG, shrunk to fit
        a PNG's limits, which the app saves among its screenshots."""
        self._say(lm.SHOT_RENDERING)
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)   # laid out as it is now, these words included
        content = self.scroll.widget()
        width, height = content.width(), content.height()
        scale = lm.shot_scale(width, height)
        if scale < 0.2:
            self._say(lm.SHOT_TOO_LARGE)
            self._acted("screenshot")
            return
        image = QImage(max(1, round(width * scale)), max(1, round(height * scale)), QImage.Format_ARGB32)
        image.fill(QColor(C["bg1"]))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.scale(scale, scale)
        content.render(painter, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawWindowBackground |
                       QWidget.RenderFlag.DrawChildren)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        self._say(lm.SHOT_SAVING)
        self.shot_scaled = scale < 1
        self.requests.post("act:screenshot", "/api/screenshot",
                           {"png": "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")}, origin=True)

    # ---------------------------------------------------------------- the app's answers
    def _replied(self, name: str, answer) -> None:
        kind, _, rest = name.partition(":")
        a = _dict(answer)
        if _truthy(a.get("error")) and not (name in METER_ASKS and isinstance(a.get("running"), bool)
                                            and _truthy(a.get("snapshot"))):
            self._failed(name, js_text(a["error"]))   # refused in its answer (``api``), unless the meter's state says why
            return
        if kind == "ui":
            self.overlay_on_start.setChecked(a.get("overlay_on_start") is not False)
            self.light = a.get("performance_mode") is True
        elif kind == "npcap":
            self._npcap(lm.npcap_state(a))
        elif kind == "npcap-install":
            self.read_npcap()
        elif kind == "interfaces":
            self._interfaces(a)
        elif kind in ("view", "clear"):
            self.render(a)
            if kind == "clear":
                self._say(lm.CLEARED)
        elif kind == "decoder":
            self.decoder = js_text(a.get("path")) if _truthy(a.get("path")) else None
            self.decoder_name.setText(js_text(a.get("name")))
        elif kind == "region":
            self._region_says(lm.REGION_RETRYING)
            self.region_button.setEnabled(True)
        elif kind == "setup":
            self._setup(a)
        elif kind == "setup-install":
            self.checking = False
            self._say(lm.setup_words(self.setup, True))
        elif kind == "start":
            self._started(a)
        elif kind == "start-overlay":
            self._overlay_answered(name, a)
        elif kind == "stop":
            self._stopped(a)
        elif kind == "stop-ui":
            self._stop_upload(a.get("meter_auto_upload") is not False)
        elif kind == "act":
            self._answered(rest, a)

    def _interfaces(self, r: dict) -> None:
        chosen = self.iface.currentData()
        self.iface.clear()
        for value, words in lm.interface_options(r):
            self.iface.addItem(words, value)
        index = self.iface.findData(chosen)
        self.iface.setCurrentIndex(index if index >= 0 else 0)

    def _setup(self, setup: dict) -> None:
        """The packet-capture support, checked before a capture starts."""
        self.setup = setup
        if _truthy(setup.get("detection_error")):
            self.checking = False
            self._say(f"Could not check Npcap: {js_text(setup['detection_error'])}")
            return
        if _truthy(setup.get("supported")) and not _truthy(setup.get("installed")):
            question = js_text(setup["prompt"]) if _truthy(setup.get("prompt")) else "Install packet-capture support now?"
            if self.ask(question):
                self.requests.post("setup-install", "/api/capture/setup", {"action": "install"})
                return
            self.checking = False
            self._say(lm.setup_words(setup, False))
            return
        self.checking = False
        self._start()

    def _started(self, a: dict) -> None:
        self.render(a)
        if not _truthy(a.get("running")):
            self._say(js_text(a["error"]) if _truthy(a.get("error")) else lm.NOT_STARTED)
            self._done()
            return
        self._say(lm.STARTED)
        self._toast("Capture started")
        if self.show_overlay:
            self._open_overlay("start-overlay")
        else:
            self._done()

    def _stopped(self, a: dict) -> None:
        self.render(a)
        words = lm.stop_words(a)
        self._say(words)
        self._toast(words, TOAST_MS)
        if _truthy(a.get("saved_log")):               # uploaded unless Settings says not to
            self.requests.get("stop-ui", "/api/ui")
        else:
            self._done()

    def _stop_upload(self, upload: bool) -> None:
        if not upload or self.stop_job is None:
            self._done()
            return
        self._say(lm.UPLOADING_STOPPED)
        self.stop_job.start("/api/meter", {"action": "upload"})

    def _answered(self, key: str, a: dict) -> None:
        if key == "save":
            self._say(lm.saved_words(a), ("open in Combat Logs", "#/combat"))
        elif key == "export":
            self._say(lm.exported_words(a))
        elif key == "screenshot":
            self._say(lm.shot_words(a, self.shot_scaled))
        elif key == "split":
            self.render(a)
            self._say(lm.SPLIT)
        elif key == "finish":
            self.render(a)
            self._say(lm.FINISHED)
        elif key == "hide":
            self._say(lm.HIDDEN)
        elif key == "overlay":
            self._overlay_answered("act:overlay", a)
            return
        elif key == "interfaces":
            self._interfaces(a)
        self._acted(key)

    def _failed(self, name: str, why: str) -> None:
        kind, _, rest = name.partition(":")
        if kind == "ui":
            return
        if kind == "overlay-choice":
            self.overlay_on_start.setChecked(not bool(int(rest or 0)))
            self._say(f"Could not save overlay preference: {why}")
        elif kind == "npcap":
            self._npcap_says(f"Could not check Npcap: {why}")
        elif kind == "npcap-install":
            self._npcap_says(why)
        elif kind == "interfaces":
            self._say(f"Could not list capture interfaces: {why}")
        elif kind in ("view", "clear", "start", "stop"):
            self._say(why)
            if kind in ("start", "stop"):
                self._done()
        elif kind == "decoder":
            self.decoder_name.setText(why)
        elif kind == "region":
            self._region_says(why)
            self.region_button.setEnabled(True)
        elif kind in ("setup", "setup-install"):
            self.checking = False
            self._say(f"Could not check Npcap: {why}")
        elif kind == "start-overlay":
            self._overlay_refused(name, why)
        elif kind == "stop-ui":
            self._stop_upload(True)
        elif kind == "act":
            if rest == "overlay":
                self._overlay_refused(name, why)
            elif rest == "interfaces":
                self._say(f"Could not list capture interfaces: {why}")
                self._acted(rest)
            elif rest in ("split", "hide"):            # their handlers let the failure through
                self._acted(rest, why)
            else:
                self._say(why)
                self._acted(rest)

    def _overlay_refused(self, name: str, why: str) -> None:
        """Opening the overlay failed: no answer at all is said; an answer refusing it opens the overlay's page."""
        if name in self.requests.unanswered:
            self._overlay_said(name, lm.OVERLAY_SILENT)
            return
        self._overlay_answered(name, None)

    def _uploaded(self, result) -> None:
        url = safe_link(_dict(result).get("url"))
        self._say("uploaded", ("open shared log", url) if url else None)
        self._acted("upload")

    def _upload_failed(self, why: str) -> None:
        self._say(why)
        self._acted("upload")

    def _stop_uploaded(self, result) -> None:
        url = safe_link(_dict(result).get("url"))
        if url:
            self._say("Capture stopped and uploaded", ("open shared log", url))
        else:
            self._say("Capture stopped and uploaded.")
        self._done()

    def _stop_upload_failed(self, why: str) -> None:
        self._say(f"Capture stopped and saved. Auto-upload failed: {why} (you can still Upload manually).")
        self._done()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.place()


def _browser_window(url: str) -> bool:
    """The overlay's page in a window of its own, when the app cannot open its overlay window (``window.open``)."""
    try:
        from ..launcher import open_window
        open_window(url, True, native=False)
    except Exception:                     # noqa: BLE001 - no window could open: said as a blocked popup
        return False
    return True
