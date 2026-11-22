"""The Pet Tracker window, natively (0.2.498): Pet Tracker's pets on the overlay's card in a small Qt window of its own
over the game, where until now it was a page in a pywebview window (pet-overlay.html, ``overlay?view=pets``).

It shows what that page shows (pet-overlay.js, its rows as ``A2Pets`` in pet-tracker.js draws them):

- **its header:** the green dot, *Pet Tracker*, Lock and Hide (Hide also turns its setting off, as the app does for
  that page's Hide);
- **how Pet Tracker is doing**, in one line coloured by how it reads, its detail in the tooltip;
- **Recent and Nearby**, and **Hide maxed**, sent back to Pet Tracker's capture (``POST /api/pettracker``), so its own
  window and the app's Pet Tracker page show the same;
- **Totals paused** while Pet Tracker waits for the character to log in again;
- **the pets of the moment**, each with its portrait, name and rank, souls toward the next rank, family, Pet
  Tracker's notice, bar and pin, as the app's Pet Tracker page draws them, in Pet Tracker's accent colour and
  smaller where Pet Tracker's compact rows are on; or why there are none, or the character Pet Tracker waits to
  link, with its Link button;
- **the foot:** the opacity slider (its own, 90% until moved) and *Pet Tracker · 0Fox2Give*.

It reads Pet Tracker every second while it is connected (every 2 s otherwise), not while locked. It keeps its own
place (``overlay_pets_pos_*``), opening first below the meter overlay's corner; it shows and hides with the game and
passes clicks through to it as the meter overlay does, but keeps its own look: the overlay's fonts, colours and
background are not its, nor is hover to interact or the screenshot hotkey, as on that page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .companions import GOLD, CompanionWindow
from .pets_page import ACCENTS, FAMILIES, PetRow, Portraits, _clear, _dim, _key, accent, link_words, status_line

WIDTH = 320                               # ``#ov.ov-pets .ovcard { width: var(--ov-width, 320px) }``
CONNECTED_MS, WAITING_MS = 1000, 2000     # its poll (pet-overlay.js ``poll``)
OPACITY = 0.9                             # its own opacity until moved (``ovopacity-pets``)
#: Pet Tracker's colours on the window (pet-tracker.css ``:root``): always dark, whatever the app's theme.
INK, DIM, MAX_INK, ROW, ROW_LINE = "#e9edf4", "#9aa3b5", "#919baa", "rgba(255, 255, 255, 9)", "rgba(255, 255, 255, 15)"
TRACK = QColor(255, 255, 255, 23)         # a bar's track (``--pt-track: rgba(255, 255, 255, .09)``)
TONES = {"ok": "#76c59d", "off": "#e9a4b6", "wait": DIM}
MODES = (("Recent", "Your recent pet rewards and tracked kills"),
         ("Nearby", "Pet mobs the game reported around you (distance is not measured)"))
SYNC = "<b>Totals paused.</b> Return to character selection, then log back in."
BRAND = "Pet Tracker · 0Fox2Give"
BRAND_TIP = "Pet Tracker is 0Fox2Give's program; Aion 2 Calc shows its data here"
MANAGE = "Open Pet Tracker's Settings → Account → Manage accounts to link it."


def poll_ms(state) -> int:
    """How soon it reads Pet Tracker again: each second while connected, every 2 s otherwise."""
    return CONNECTED_MS if isinstance(state, dict) and state.get("connected") else WAITING_MS


def mode_of(state) -> str:
    """The view Pet Tracker shows: Recent unless it says Nearby."""
    options = (state or {}).get("options") if isinstance(state, dict) else None
    return (options or {}).get("mode") or "Recent"


class PetsWindow(CompanionWindow):
    """The Pet Tracker window (pet-overlay.html and pet-overlay.js)."""

    VIEW = "pets"
    WIDTH = WIDTH
    PADDING = (11, 9, 11, 8)                      # ``#ov.ov-pets .ovcard { padding: 8px 10px 7px }``
    HEADER_GAP = 2
    OPACITY = OPACITY
    FOLLOWS_LOOK = False
    SETTINGS_MS = 10000                           # its click-through, read every 10 s (``syncSettings``)
    LOCK_HOTKEY = False

    def build(self) -> None:
        self.state: dict | None = None
        self.busy = False
        self._drawn = None                        # what the pets were last drawn from
        self.host.below = True
        self.title.set_words("Pet Tracker", self.title.font_, GOLD, self.text_look)
        self.title.show()
        self.add_button("lock", "Lock", "Freeze the window in place for a screenshot", self.toggle_lock)
        self.add_button("hide", "Hide", "Hide the Pet Tracker window (Settings → Pet Tracker shows it again)",
                        self.hide_window)
        self.status = QLabel("Loading Pet Tracker…", self.card)   # ``#ptstatus``
        self.status.setObjectName("ptstatus")
        self.status.setAccessibleName("Pet Tracker status")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.status.setContentsMargins(0, 0, 0, 5)
        self.box.addWidget(self.status)
        self.tools = QWidget(self.card)          # ``.pttools``: Recent, Nearby, then Hide maxed at the right
        self.tools.setAttribute(Qt.WA_TranslucentBackground)
        line = QHBoxLayout(self.tools)
        line.setContentsMargins(0, 0, 0, 6)
        line.setSpacing(2)
        self.modes: dict[str, QPushButton] = {}
        for mode, tip in MODES:
            button = QPushButton(mode, self.tools)
            button.setObjectName("ptmode")
            button.setToolTip(tip)
            button.setProperty("on", False)       # Pet Tracker's view, shown once it says so (``.on``)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _checked=False, m=mode: self.control({"action": "mode", "value": m}))
            line.addWidget(button)
            self.modes[mode] = button
        line.addStretch(1)
        self.hide_maxed = QCheckBox("Hide maxed", self.tools)
        self.hide_maxed.setObjectName("pthidemax")
        self.hide_maxed.setToolTip("Hide pets at Rank 3 / MAX")
        self.hide_maxed.setFocusPolicy(Qt.NoFocus)
        self.hide_maxed.clicked.connect(lambda on: self.control({"action": "hide_maxed", "value": bool(on)}))
        line.addWidget(self.hide_maxed)
        self.box.addWidget(self.tools)
        self.sync = QLabel(SYNC, self.card)       # ``#ptsync``
        self.sync.setObjectName("ptsync")
        self.sync.setTextFormat(Qt.RichText)
        self.sync.setWordWrap(True)
        self.sync.hide()
        self.box.addWidget(self.sync)
        self.box.addSpacing(0)
        self.rows = QWidget(self.card)            # ``#ptrows``: the pets, or why there are none
        self.rows.setAttribute(Qt.WA_TranslucentBackground)
        self.rows_box = QVBoxLayout(self.rows)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(4)
        self.box.addWidget(self.rows)
        self.pet_rows: list[PetRow] = []
        self.link_button: QPushButton | None = None
        self.foot.brand.setText(BRAND)
        self.foot.brand.setToolTip(BRAND_TIP)
        self.portraits = Portraits(self.api, self)
        self.portraits.loaded.connect(self._portrait_read)
        self.portraits.missing.connect(self._portrait_missing)
        self._poll = QTimer(self)
        self._poll.setSingleShot(True)
        self._poll.timeout.connect(self.poll)
        self.show_state(None)

    def start(self) -> None:
        super().start()
        self.poll()

    def closeEvent(self, event):
        self._poll.stop()
        self.portraits.stop()
        super().closeEvent(event)

    def apply_settings(self, ui: dict) -> None:
        """Its click-through alone of the overlay's settings, and no hover to interact (pet-overlay.js)."""
        self.ui = {key: value for key, value in ui.items() if key != "overlay_hover_interact"}

    def extra_sheet(self) -> str:
        """Pet Tracker's rows on the window (pet-tracker.css), in its accent colour."""
        colour = accent(self.state)
        names = (*FAMILIES, "Other")
        return (
            f"QLabel#ptstatus {{ font-size: 12px; font-weight: 400; }}"
            f"QPushButton#ptmode {{ background: transparent; border: none; color: #7f8aa3; font-size: 14px;"
            f" font-weight: 700; padding: 0 4px 0 0; }}"
            f"QPushButton#ptmode[on=\"true\"] {{ color: {GOLD}; }}"
            f"QPushButton#ptmode:disabled {{ color: rgba(127, 138, 163, 128); }}"
            f"QPushButton#ptmode[on=\"true\"]:disabled {{ color: rgba(232, 207, 142, 128); }}"
            f"QCheckBox#pthidemax {{ color: {DIM}; font-size: 12px; spacing: 4px; }}"
            f"QCheckBox#pthidemax:disabled {{ color: rgba(154, 163, 181, 128); }}"
            f"QLabel#ptsync {{ background: rgba(230, 199, 124, 26); border: 1px solid rgba(230, 199, 124, 89);"
            f" color: #e6c77c; border-radius: 6px; padding: 4px 7px; margin: 0 0 6px 0; font-size: 12px; }}"
            f"QFrame#ptrow {{ background: {ROW}; border: 1px solid {ROW_LINE}; border-radius: 8px; }}"
            f"QFrame#ptrow QLabel {{ background: transparent; font-size: 12px; }}"
            f"QLabel#ptname {{ color: {INK}; font-weight: 700; }}"
            f"QLabel#ptnameMax {{ color: {MAX_INK}; font-weight: 700; }}"
            f"QLabel#ptrank {{ color: {DIM}; font-weight: 400; }}"
            f"QLabel#ptprog {{ color: {INK}; font-weight: 400; }}"
            f"QLabel#ptprogMax {{ color: {MAX_INK}; font-weight: 400; }}"
            f"{', '.join(f'QLabel#fam{name}' for name in names)} {{ font-weight: 700; border-radius: 4px; padding: 0 4px; }}"
            + "".join(f"QLabel#fam{name} {{ color: {_dim(tint)}; border: 1px solid {_dim(tint)}; }}" for name, tint in
                      (*FAMILIES.items(), ("Other", DIM)))
            + f"QLabel#ptnotice {{ color: #e6c77c; font-weight: 400; }}"
            f"QLabel#ptempty {{ color: {DIM}; padding: 6px 2px; font-size: 12px; font-weight: 400; }}"
            f"{', '.join(f'QPushButton#ptpin{name}' for name in ('', *ACCENTS))} {{ background: transparent;"
            f" border: none; color: {DIM}; padding: 2px 3px; font-size: 12px; }}"
            + "".join(f"QPushButton#ptpin{name} {{ color: {tint}; }}" for name, tint in ACCENTS.items())
            + f"{', '.join(f'QPushButton#ptpin{name}:hover' for name in ('', *ACCENTS))} {{ color: {INK}; }}"
            f"QPushButton#ptlink {{ background: transparent; border: 1px solid {colour}; color: {colour};"
            f" border-radius: 6px; padding: 3px 9px; margin: 0 2px 4px 2px; font-size: 12px; }}"
            f"QPushButton#ptlink:hover {{ color: {INK}; border-color: {INK}; }}"
            f"QPushButton#ptlink:disabled {{ color: rgba(233, 237, 244, 128); }}")

    def text_labels(self):
        return []                                 # its own look: no overlay effects on its words

    # ------------------------------------------------------------------ reading Pet Tracker
    def poll(self) -> None:
        """Read Pet Tracker (``GET /api/pettracker``), unless a reading is on its way or the window is locked; then
        again in a second while it is connected, in two otherwise."""
        self._poll.stop()
        if not self.busy and not self.locked and self.requests is not None:
            self.busy = True
            self.requests.get("state", "/api/pettracker")
        else:
            self._poll.start(poll_ms(self.state))

    def unlocked(self) -> None:
        self.poll()

    def control(self, body: dict) -> None:
        """A control sent back to Pet Tracker's capture (``A2Pets.control``); its answer is the new state."""
        if self.requests is not None:
            self.requests.post("control", "/api/pettracker", body)

    def _replied(self, name: str, answer) -> None:
        if name == "state":
            self.busy = False
            self.show_state(answer if isinstance(answer, dict) else None)
            self._poll.start(poll_ms(self.state))
        elif name == "control":
            if isinstance(answer, dict) and answer.get("error"):
                self.say_error(str(answer["error"]))
            else:
                self.show_state(answer if isinstance(answer, dict) else None)
        else:
            super()._replied(name, answer)

    def _failed(self, name: str, why_: str) -> None:
        if name == "state":                       # the app did not answer: as a reading of nothing (``render(null)``)
            self.busy = False
            self.show_state(None)
            self._poll.start(poll_ms(self.state))
        elif name == "control":
            self.say_error(why_)
        else:
            super()._failed(name, why_)

    def say_error(self, message: str) -> None:
        """A control Pet Tracker refused: why, in the status line, in its "off" colour (``showError``)."""
        self.status.setProperty("full", message)
        self.status.setText(self.status.fontMetrics().elidedText(message, Qt.ElideRight, max(40, self.status.width())))
        self.status.setStyleSheet(f"color: {TONES['off']};")

    # ------------------------------------------------------------------ drawing
    def show_state(self, state: dict | None) -> None:
        """Draw Pet Tracker's state (pet-overlay.js ``render``): the status line, the tools, the notice and the pets."""
        self.state = state
        words, tone, detail = status_line(state)
        self.status.setProperty("full", words)
        self.status.setText(self.status.fontMetrics().elidedText(words, Qt.ElideRight, max(40, self.status.width())))
        self.status.setStyleSheet(f"color: {TONES.get(tone, DIM)};")
        self.status.setToolTip(detail or "")
        options = (state or {}).get("options") or {}
        live = bool(state and state.get("connected"))
        for mode, button in self.modes.items():
            on = mode == mode_of(state)
            if button.property("on") != on:
                button.setProperty("on", on)
                button.setAccessibleName(f"{mode} (shown)" if on else mode)
                button.style().unpolish(button)
                button.style().polish(button)
            button.setEnabled(live)
        self.hide_maxed.setChecked(bool(options.get("hide_maxed")))
        self.hide_maxed.setEnabled(live)
        self.sync.setVisible(bool(state and state.get("sync_notice")))
        self.restyle_sheet()                      # in Pet Tracker's accent colour
        drawn = _key(None if not state else [state.get(k) for k in ("connected", "link", "rows", "options", "empty")],
                     words if not (state and state.get("connected")) else "")
        if drawn != self._drawn:                  # what the pets show changed (the page's ``setHtml``)
            self._drawn = drawn
            self._draw_rows(state)
        self._relayout()

    def _draw_rows(self, state: dict | None) -> None:
        """The pets (``A2Pets.rows``): each row drawn anew in place where it still is, or why there are none, or the
        character to link."""
        options = (state or {}).get("options") or {}
        rows = [row for row in (state or {}).get("rows") or [] if isinstance(row, dict)] if state else []
        if not state or not state.get("connected") or state.get("link") or not rows:
            self._clear_rows()
            if not state or not state.get("connected"):
                self._words(status_line(state)[0])
            elif state.get("link"):
                self._link(state["link"])
            elif state.get("empty"):
                self._words(str(state["empty"]))
            return
        if self.link_button is not None or len(self.pet_rows) != len(rows) or self.rows_box.count() != len(rows):
            self._clear_rows()
            for _row in rows:
                widget = PetRow(self._pin)
                self._fit_row(widget, options)
                self.rows_box.addWidget(widget)
                self.pet_rows.append(widget)
        colour = accent(state)
        for widget, row in zip(self.pet_rows, rows):
            self._fit_row(widget, options)
            widget.set_row(row, colour, options.get("portraits") is not False, options.get("progress_bars") is not False)
            widget.bar.track = TRACK
            self._picture(row, widget)

    def _fit_row(self, widget: PetRow, options: dict) -> None:
        """A row at Pet Tracker's size: its portrait 40 px, 30 px with compact rows on, its room to match."""
        compact = bool(options.get("compact"))
        side = 30 if compact else 40
        if widget.picture.width() != side:
            widget.picture.setFixedSize(side, side)
        widget.layout().setContentsMargins(*((5, 3, 5, 3) if compact else (6, 5, 6, 5)))

    def _clear_rows(self) -> None:
        _clear(self.rows_box)
        self.pet_rows, self.link_button = [], None

    def _words(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("ptempty")
        label.setWordWrap(True)
        self.rows_box.addWidget(label)

    def _link(self, link: dict) -> None:
        """The character Pet Tracker waits to link to its account (``linkBox``), with its Link button when there is
        one account to link it to."""
        self._words(link_words(link))
        if link.get("key"):
            button = QPushButton(f"Link {link.get('character')} to {link.get('account')}")
            button.setObjectName("ptlink")
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)

            def link_it(_checked=False, character=link.get("character")):
                button.setEnabled(False)          # until the pets show something else, as on the page
                self.control({"action": "link", "character": character})
            button.clicked.connect(link_it)
            self.rows_box.addWidget(button, 0, Qt.AlignLeft)
            self.link_button = button
        else:
            label = QLabel(MANAGE)
            label.setObjectName("ptempty")
            label.setWordWrap(True)
            self.rows_box.addWidget(label)

    def _pin(self, pet, value: bool) -> None:
        self.control({"action": "pin", "pet": pet, "value": bool(value)})

    def _picture(self, row: dict, widget: PetRow) -> None:
        path = str(row.get("portrait") or "")
        if path in self.portraits.pixmaps:
            widget.set_picture(self.portraits.pixmaps[path])
        elif path in self.portraits.failed or not path:
            widget.set_picture(None, missing=True)
        else:
            widget.set_picture(None)
            self.portraits.ask(path)

    def _portrait_read(self, path: str, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._portrait_missing(path)
            return
        self.portraits.pixmaps[path] = pixmap
        for widget in self.pet_rows:
            if str(widget.row.get("portrait") or "") == path:
                widget.set_picture(pixmap)

    def _portrait_missing(self, path: str) -> None:
        self.portraits.failed.add(path)
        for widget in self.pet_rows:
            if str(widget.row.get("portrait") or "") == path:
                widget.set_picture(None, missing=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        full = self.status.property("full")
        if isinstance(full, str) and full:        # the status line cut to the window's width again
            self.status.setText(self.status.fontMetrics().elidedText(full, Qt.ElideRight, max(40, self.status.width())))

