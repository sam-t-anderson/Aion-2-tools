"""The window's header (0.2.494): what the web pages' top bar (index.html's ``.topbar``, app.js) has beside the pages.

- **The brand**, then **the game database** (``#syncpill``): its items, or its update as it runs, with a dot (green
  when done, red when the last update had errors, pulsing in the accent colour while it runs). It reads the status the
  window asks for the quiet update (``syncPill``); a window 1,180 pixels wide or less shows the dot alone.
- **A newer version** where nothing downloads it (``#update``, under the language choice in 0.2.493).
- **The account** (``A2Account.menu``): **Sign in**, or the account's name with My logs, Top parses, Legions,
  Sign-in & security, Approve a website sign-in, Open the website signed in and **Sign out** under it.
- **The Discord**, **Application screenshot** (``A2Screenshot.capture``: the window with the page shown whole, saved
  by the app as a PNG in its data folder's ``screenshots``), **the language**, **the theme** (◐ follow the computer,
  ☀ light, ☾ dark, in turn) and **Quit** (the app stopped, as the web page's Quit stops it).
"""
from __future__ import annotations

import contextlib
import math
import webbrowser
from decimal import Decimal

from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPainter, QPixmap, QRadialGradient, QRegion
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem, QLineEdit, QMenu, QPushButton,
                               QScrollArea, QWidget)

from . import i18n, theme
from .app_icon import LOGO                       # the app's logo, its icon too (0.2.501)
from .character import js_number, js_string
from .live_meter import shot_scale
from .pictures import sized
from .results import _dict, _truthy

# ------------------------------------------------------------------ index.html's, app.js's and account-view.js's words
BRAND, TAGLINE = "Aion 2 Calc", "AION 2 build planner & combat analyzer"
DISCORD_URL = "https://discord.gg/9y6zkUyvBv"
DISCORD_TIP = "Join the aion2calc Discord"
SCREENSHOT = "Application screenshot"
SHOT_FAILED = "Screenshot failed: "
QUIT, QUIT_TIP = "Quit", "Stop the app"
ASK_QUIT = "Stop aion2calc? Start it again from the Start menu or desktop shortcut."
STOPPED = "aion2calc has stopped. You can close this window."
SIGN_IN, SIGN_OUT = "Sign in", "Sign out"
#: What the account menu offers besides the Account page's tabs (``accountIO.menuItems``).
MENU_ITEMS = (("approve", "Approve a website sign-in"), ("website", "Open the website signed in"))
THEMES = ("system", "light", "dark")
THEME_ICONS = {"system": "◐", "light": "☀", "dark": "☾"}
NARROW = 1180                       # app.css: a window this wide or less shows the database's dot alone


# ------------------------------------------------------------------ the rules
def n0(x) -> str:
    """``n0``: a whole number grouped by commas, "—" for none or what reads as no number."""
    if x is None:
        return "—"
    value = js_number(x)
    if math.isnan(value):
        return "—"
    if math.isinf(value):
        return "∞" if value > 0 else "-∞"
    whole = theme.js_round(value)
    if abs(whole) >= 2 ** 53:                        # past whole numbers a double holds exactly: its shortest digits
        return f"{Decimal(repr(float(whole))):,.0f}"
    return ("-" if whole == 0 and math.copysign(1.0, value) < 0 else "") + f"{whole:,}"


def _length(value) -> bool:
    """``value.length`` as a condition: a list's or a text's length, an object's own ``length``."""
    if isinstance(value, (list, str)):
        return len(value) > 0
    return isinstance(value, dict) and _truthy(value.get("length"))


def database_state(s) -> tuple[str, str] | None:
    """``#syncpill``: the dot (``run``, ``err`` or ``ok``) and its words; None where the web page's line stays as it
    was (a status without the database's, which it cannot read)."""
    s = _dict(s)
    sync = s.get("sync")
    running = isinstance(sync, dict) and _truthy(sync.get("running"))
    if running:
        total = sync.get("total")
        done = f"{js_string(sync['done']) if 'done' in sync else 'undefined'}/{js_string(total)}" if _truthy(total) else ""
        phase = sync.get("phase")
        return "run", f"updating database · {'' if phase is None else js_string(phase)} {done}"
    dot = "err" if isinstance(sync, dict) and _length(sync.get("errors")) else "ok"
    db = s.get("db")
    if db is None:
        return None
    return dot, f"database {n0(db.get('items') if isinstance(db, dict) else None)} items"


def quit_tip(s) -> str:
    """Quit's tip once the status has come: this copy's version (``s.version || ""``)."""
    version = _dict(s).get("version")
    return f"{QUIT_TIP} (version {js_string(version) if _truthy(version) else ''})"


def theme_after(current) -> str:
    """The theme the button turns to: the next of follow the computer, light and dark (one none of them: the first)."""
    return THEMES[(THEMES.index(current) + 1) % len(THEMES) if current in THEMES else 0]


def theme_tip(current) -> str:
    return f"Theme: {'follow the computer' if current == 'system' else js_string(current)} (click to change)"


def account_name(s) -> str | None:
    """The name the header shows for the account signed in (``menu``'s ``refresh``), from the app's account status as
    the Account page reads it; None for Sign in (signed out, or signed in on another log server than Settings uses)."""
    if not isinstance(s, dict):
        return None
    if _truthy(s.get("signed_in")) and s.get("here") is False:
        return None
    if not (_truthy(s.get("signed_in")) and _truthy(s.get("account"))):
        return None
    account = s["account"]
    name = account.get("name") if isinstance(account, dict) else None
    return js_string(name) if _truthy(name) else None


# ------------------------------------------------------------------ the header's line
class FlowLayout(QLayout):
    """The header's parts side by side, each centred on its line, carried onto another line where the window is too
    narrow for them (``.topbar``'s ``flex-wrap: wrap``, ``align-items: center``); ``push`` and the parts after it moved
    to the right end of their line (the database's ``margin-left: auto``). ``gaps`` are between parts and lines."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.parts: list[QLayoutItem] = []
        self.push: QWidget | None = None
        self.gaps = (18, 10)

    def addItem(self, item: QLayoutItem) -> None:
        self.parts.append(item)

    def count(self) -> int:
        return len(self.parts)

    def itemAt(self, index: int):
        return self.parts[index] if 0 <= index < len(self.parts) else None

    def takeAt(self, index: int):
        return self.parts.pop(index) if 0 <= index < len(self.parts) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._lay(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._lay(rect, True)

    def sizeHint(self) -> QSize:
        """On one line."""
        shown = [part.sizeHint() for part in self.parts if not part.isEmpty()]
        m = self.contentsMargins()
        return QSize(sum(size.width() for size in shown) + self.gaps[0] * max(0, len(shown) - 1) + m.left() + m.right(),
                     max((size.height() for size in shown), default=0) + m.top() + m.bottom())

    def minimumSize(self) -> QSize:
        """As wide as its widest part: the others go onto lines of their own."""
        size = QSize(0, 0)
        for part in self.parts:
            if not part.isEmpty():
                size = size.expandedTo(part.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _lay(self, rect: QRect, place: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        across, down = self.gaps
        lines, line, used = [], [], 0
        for part in self.parts:
            if part.isEmpty():
                continue
            width = part.sizeHint().width()
            if line and used + across + width > area.width():
                lines.append((line, used))
                line, used = [], 0
            used += (across if line else 0) + width
            line.append(part)
        if line:
            lines.append((line, used))
        y = area.y()
        for line, used in lines:
            tallest = max(part.sizeHint().height() for part in line)
            x = area.x()
            for part in line:
                if self.push is not None and part.widget() is self.push:
                    x += max(0, area.width() - used)
                size = part.sizeHint()
                if place:
                    part.setGeometry(QRect(QPoint(x, y + (tallest - size.height()) // 2), size))
                x += size.width() + across
            y += tallest + down
        return (y - down if lines else y) - rect.y() + m.bottom()


# ------------------------------------------------------------------ the dot
class Dot(QWidget):
    """``.dot``: 8 pixels, green when done, red after errors, glowing in the accent colour and pulsing while the
    database updates."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = "ok"
        self.opacity = 1.0
        self.still = False                                   # performance mode: no pulse (``body.perf``)
        self.setFixedSize(QSize(16, 16))
        self.pulse = QVariantAnimation(self)                 # ``@keyframes pulse { 50% { opacity: .35; } }``, 1.2 s
        self.pulse.setDuration(1200)
        self.pulse.setStartValue(1.0)
        self.pulse.setKeyValueAt(0.5, 0.35)
        self.pulse.setEndValue(1.0)
        self.pulse.setLoopCount(-1)
        self.pulse.valueChanged.connect(self._faded)

    def set_state(self, state: str) -> None:
        self.state = state
        if state == "run" and not self.still:
            if self.pulse.state() != QAbstractAnimation.State.Running:
                self.pulse.start()
        else:
            self.pulse.stop()
            self.opacity = 1.0
        self.update()

    def hold(self, still: bool) -> None:
        """Performance mode (app.css's ``body.perf``: no animation): the dot holds still while the database updates."""
        self.still = still
        self.set_state(self.state)

    def _faded(self, value) -> None:
        self.opacity = float(value)
        self.update()

    def paintEvent(self, _event) -> None:
        c = theme.COLORS
        colour = QColor({"run": c["accent"], "err": c["bad"], "ok": c["good"]}.get(self.state, c["faint"]))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self.opacity)
        painter.setPen(Qt.NoPen)
        if self.state == "run":                               # ``box-shadow: 0 0 8px var(--accent)``
            glow = QRadialGradient(8, 8, 8)
            halo = QColor(colour)
            halo.setAlpha(150)
            glow.setColorAt(0.4, halo)
            halo.setAlpha(0)
            glow.setColorAt(1.0, halo)
            painter.setBrush(glow)
            painter.drawEllipse(0, 0, 16, 16)
        painter.setBrush(colour)
        painter.drawEllipse(4, 4, 8, 8)


# ------------------------------------------------------------------ the header
class Header(QFrame):
    """The window's header, ``language`` the language choice it holds. ``account_tab(key)`` opens a tab of the Account
    page (``None``: its sign-in); ``account_item(id)`` is one of ``MENU_ITEMS`` chosen; ``sign_out(name)`` the account's
    Sign out; ``change_theme(theme)`` the theme to show; ``quit_app()`` Quit; ``capture()`` Application screenshot."""

    account_tab = Signal(object)
    account_item = Signal(str)
    sign_out = Signal(str)
    change_theme = Signal(str)
    quit_app = Signal()
    capture = Signal()

    def __init__(self, language: QWidget | None = None, parent: QWidget | None = None, open_link=webbrowser.open):
        super().__init__(parent)
        self.setObjectName("header")
        self.open_link = open_link
        line = self.line = FlowLayout(self)
        line.setContentsMargins(22, 10, 22, 10)
        # the brand: the logo, the name and what the app is
        brand = QWidget()
        brand.setObjectName("headerPart")
        row = QHBoxLayout(brand)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        logo = QLabel()
        picture = QPixmap(str(LOGO))
        if not picture.isNull():
            logo.setPixmap(sized(picture, 30, 30, logo.devicePixelRatioF()))
        row.addWidget(logo)
        name = QLabel(BRAND)
        name.setObjectName("brandName")
        font = name.font()
        font.setCapitalization(QFont.AllUppercase)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        name.setFont(font)
        row.addWidget(name)
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("tagline")
        row.addWidget(tagline)
        line.addWidget(brand)
        # the game database, and what follows it, at the right end of its line
        pill = QWidget()
        pill.setObjectName("headerPart")
        row = QHBoxLayout(pill)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.dot = Dot()
        self.database = QLabel()
        self.database.setObjectName("syncpill")
        self.database.setTextFormat(Qt.PlainText)
        row.addWidget(self.dot)
        row.addWidget(self.database)
        line.addWidget(pill)
        line.push = pill
        # a newer version, where nothing downloads it
        self.update_chip = QLabel()
        self.update_chip.setObjectName("updchip")
        self.update_chip.setTextFormat(Qt.RichText)
        self.update_chip.setOpenExternalLinks(True)
        self.update_chip.hide()
        line.addWidget(self.update_chip)
        # the account
        self.account = QPushButton()
        self.account.setObjectName("small")
        self.account_menu = QMenu(self.account)
        self.account_menu.setObjectName("acctDrop")
        self.account.clicked.connect(self._account_clicked)
        line.addWidget(self.account)
        self.name: str | None = None
        self.show_account(None)
        # the Discord
        discord = QPushButton("\U0001F4AC")
        discord.setObjectName("iconbtn")
        discord.setToolTip(DISCORD_TIP)
        discord.setAccessibleName(DISCORD_TIP)
        discord.clicked.connect(lambda _checked=False: self.open_link(DISCORD_URL))
        line.addWidget(discord)
        # Application screenshot, and what it is doing
        shot = self.shot_box = QWidget()                 # left out of the picture it takes (``data-html2canvas-ignore``)
        shot.setObjectName("headerPart")
        row = QHBoxLayout(shot)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.shot = QPushButton(SCREENSHOT)
        self.shot.setObjectName("small")
        self.shot.clicked.connect(lambda _checked=False: self.capture.emit())
        self.shot_status = QLabel()
        self.shot_status.setObjectName("shotStatus")
        self.shot_status.setTextFormat(Qt.PlainText)
        row.addWidget(self.shot)
        row.addWidget(self.shot_status)
        line.addWidget(shot)
        # the language, the theme and Quit
        self.language = language
        if language is not None:
            line.addWidget(language)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("iconbtn")
        self.theme_button.clicked.connect(lambda _checked=False: self.change_theme.emit(theme_after(self.theme)))
        line.addWidget(self.theme_button)
        self.theme = "system"
        self.show_theme("system")
        self.quit_button = QPushButton(QUIT)
        self.quit_button.setObjectName("small")
        self.quit_button.setToolTip(QUIT_TIP)
        self.quit_button.clicked.connect(lambda _checked=False: self.quit_app.emit())
        line.addWidget(self.quit_button)
        self.dot.set_state("ok")
        self.database.setText("database")

    # ---------------------------------------------------------------- what it shows
    def show_status(self, s) -> None:
        """The app's status: the game database's line, and Quit's tip with this copy's version; nothing of it where the
        line cannot be read (``syncPill`` stops there)."""
        line = database_state(s)
        if line is None:
            return
        self.dot.set_state(line[0])
        self.database.setText(line[1])
        self.quit_button.setToolTip(quit_tip(s))

    def show_newer(self, newer: dict | None) -> None:
        """A newer version where nothing downloads it, a link to its page; nothing else."""
        import html
        if newer is None:
            self.update_chip.hide()
            return
        self.update_chip.setText(f'<a href="{html.escape(newer["url"])}" style="color: {theme.COLORS["gold"]}; '
                                 f'text-decoration: none;">{html.escape(newer["words"])}</a>')
        self.update_chip.show()

    def show_account(self, name: str | None) -> None:
        """``menu``'s ``refresh``: Sign in, or the name with what an account offers under it."""
        from .account import TABS
        self.name = name
        self.account_menu.clear()
        if name is None:
            self.account.setMenu(None)
            self.account.setText(SIGN_IN)
            return
        self.account.setText(f"{name} ▾")
        for key, words in TABS:
            action = QAction(i18n.t(words), self.account_menu)
            action.triggered.connect(lambda _checked=False, key=key: self.account_tab.emit(key))
            self.account_menu.addAction(action)
        for key, words in MENU_ITEMS:
            action = QAction(i18n.t(words), self.account_menu)
            action.triggered.connect(lambda _checked=False, key=key: self.account_item.emit(key))
            self.account_menu.addAction(action)
        out = QAction(i18n.t(SIGN_OUT), self.account_menu)
        out.triggered.connect(lambda _checked=False, name=name: self.sign_out.emit(name))
        self.account_menu.addAction(out)
        self.account.setMenu(self.account_menu)

    def _account_clicked(self, _checked=False) -> None:
        if self.name is None:                           # Sign in: the Account page, where an account is made or linked
            self.account_tab.emit(None)

    def show_theme(self, current) -> None:
        """The theme chosen (``setTheme``): its sign, none for one that is not a theme, and what a click does."""
        self.theme = current
        self.theme_button.setText(THEME_ICONS.get(current, "") if isinstance(current, str) else "")
        self.theme_button.setToolTip(theme_tip(current))
        self.theme_button.setAccessibleName(theme_tip(current))

    def say(self, words: str) -> None:
        """What Application screenshot is doing, or did."""
        self.shot_status.setText(words)

    def calm(self, on: bool) -> None:
        """Performance mode on or off (Settings → App & data): what moves in the header holds still."""
        self.dot.hold(on)

    def fit(self, width: int) -> None:
        """A window 1,180 pixels wide or less (app.css's ``max-width: 1180px``): the database's dot without its words,
        the parts closer together and nearer the edges."""
        narrow = width <= NARROW
        self.database.setVisible(not narrow)
        self.line.gaps = (10, 10) if narrow else (18, 10)
        self.line.setContentsMargins(*((14, 10, 14, 10) if narrow else (22, 10, 22, 10)))
        self.line.invalidate()


def stylesheet() -> str:
    c = theme.COLORS
    return f"""
        QFrame#header {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['topbar_a']}, stop:1 {c['topbar_b']});
            border: none; border-bottom: 1px solid {theme.css('frame')}; }}
        QFrame#header QWidget#headerPart, QFrame#header QLabel {{ background: transparent; }}
        QFrame#header QLabel#brandName {{ color: {c['gold']}; font-size: 17px; font-weight: 700; }}
        QFrame#header QLabel#tagline {{ color: {c['muted']}; font-size: 13px; font-weight: 500; }}
        QFrame#header QLabel#syncpill, QFrame#header QLabel#shotStatus {{ color: {c['muted']}; }}
        QFrame#header QPushButton#small {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['btn_a']},
            stop:1 {c['btn_b']}); border: 1px solid {theme.css('frame')}; border-radius: 4px; padding: 3px 8px;
            font-weight: 600; color: {c['text']}; }}
        QFrame#header QPushButton#small:hover {{ border-color: {theme.css('frame_hi')}; color: {c['gold']}; }}
        QFrame#header QPushButton#small:disabled {{ color: {c['faint']}; }}
        QFrame#header QPushButton#small::menu-indicator {{ image: none; width: 0; }}
        QFrame#header QPushButton#iconbtn {{ background: transparent; border: 1px solid {theme.css('frame')};
            border-radius: 15px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; padding: 0;
            color: {c['gold']}; }}
        QFrame#header QPushButton#iconbtn:hover {{ border-color: {theme.css('frame_hi')}; background: {c['hover']}; }}
        QMenu#acctDrop {{ background: {c['panel']}; border: 1px solid {theme.css('frame_hi')}; border-radius: 8px;
            padding: 6px; color: {c['text']}; }}
        QMenu#acctDrop::item {{ padding: 8px 10px; border-radius: 5px; min-width: 220px; }}
        QMenu#acctDrop::item:selected {{ background: {c['row_hover']}; color: {c['gold']}; }}
        """


# ------------------------------------------------------------------ the window as a PNG
_FLAGS = QWidget.RenderFlag.DrawWindowBackground | QWidget.RenderFlag.DrawChildren


def main_scroll(page: QWidget) -> QScrollArea | None:
    """Where the page's content scrolls: the largest scrolling area it shows, None where nothing scrolls."""
    areas = ([page] if isinstance(page, QScrollArea) else []) + page.findChildren(QScrollArea)
    shown = [a for a in areas if a.widget() is not None and (a is page or a.isVisibleTo(page))]
    return max(shown, key=lambda a: a.viewport().width() * a.viewport().height(), default=None)


def _below_fold(area: QScrollArea | None) -> int:
    """How much taller the page is drawn whole: its content past what its scrolling area shows."""
    return 0 if area is None else max(0, area.widget().height() - area.viewport().height())


def _rect_in(widget: QWidget, page: QWidget) -> QRect:
    return QRect(QPoint(0, 0) if widget is page else widget.mapTo(page, QPoint(0, 0)), widget.size())


def _draw_page(painter: QPainter, page: QWidget, at: QPoint, background: QColor) -> None:
    """The page drawn whole at ``at``: what is over and beside its scrolling area as it is, its content from the top,
    all of it, then what is under the area, moved down by what the content adds."""
    area = main_scroll(page)
    extra = _below_fold(area)
    if area is None or extra == 0:
        page.render(painter, at, QRegion(), _FLAGS)
        return
    box, view = _rect_in(area, page), _rect_in(area.viewport(), page)
    width, height = page.width(), page.height()
    parts = [QRect(0, 0, width, box.top()),                                         # over it
             QRect(0, box.top(), box.left(), box.height()),                        # beside it
             QRect(box.right() + 1, box.top(), width - box.right() - 1, box.height())]
    for part in parts:
        if part.width() > 0 and part.height() > 0:
            page.render(painter, at + part.topLeft(), QRegion(part), _FLAGS)
    painter.fillRect(QRect(at + box.topLeft(), QSize(box.width(), box.height() + extra)), background)
    content = area.widget()
    content.render(painter, at + view.topLeft(), QRegion(0, 0, min(content.width(), view.width()), content.height()),
                   _FLAGS)
    under = QRect(0, box.bottom() + 1, width, height - box.bottom() - 1)             # under it, moved down
    if under.height() > 0:
        page.render(painter, at + QPoint(0, under.top() + extra), QRegion(under), _FLAGS)


@contextlib.contextmanager
def left_out(header: "Header"):
    """The header laid out without Application screenshot and what it says, as the picture shows it (the web page's
    ``data-html2canvas-ignore``); as it was again after."""
    box = header.shot_box
    hidden = box.isHidden()
    box.hide()
    header.layout().activate()
    try:
        yield
    finally:
        if not hidden:
            box.show()
        header.layout().activate()


def _header_height(header: QWidget) -> int:
    """The header's height in the picture: its parts' lines as they are laid out now, no taller than it is."""
    return min(header.height(), header.heightForWidth(header.width()))


def window_size(frame: QWidget, header: QWidget, page: QWidget) -> QSize:
    """The window drawn with its page whole: as wide as it is, as tall as the header and the page's content make it."""
    bottom = page.mapTo(frame, QPoint(0, 0)).y() + page.height() + _below_fold(main_scroll(page))
    return QSize(frame.width(), max(frame.height(), bottom) - (header.height() - _header_height(header)))


def window_picture(frame: QWidget, header: QWidget, side: QWidget, page: QWidget, scale: float) -> QImage:
    """The window (``frame``) as a picture at ``scale``: the header as it is laid out now, the navigation (``side``)
    with its own background down to the foot, and the page shown whole (``A2Screenshot.capture``'s ``html2canvas`` of
    the document). A password's dots are left out, as the web page empties those fields."""
    size = window_size(frame, header, page)
    head = _header_height(header)
    up = QPoint(0, header.height() - head)                # what is under the header moves up by what it lost
    image = QImage(max(1, round(size.width() * scale)), max(1, round(size.height() * scale)), QImage.Format_ARGB32)
    c = theme.COLORS
    image.fill(QColor(c["bg1"]))
    hidden = [field for field in frame.findChildren(QLineEdit) if field.echoMode() == QLineEdit.Password]
    for field in hidden:
        field.setEchoMode(QLineEdit.NoEcho)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.scale(scale, scale)
        at = header.mapTo(frame, QPoint(0, 0))
        header.render(painter, at, QRegion(0, 0, header.width(), head - 1), _FLAGS)
        header.render(painter, at + QPoint(0, head - 1), QRegion(0, header.height() - 1, header.width(), 1), _FLAGS)
        at = side.mapTo(frame, QPoint(0, 0)) - up
        painter.fillRect(QRect(at, QSize(side.width(), size.height() - at.y())), QColor(c["bg0"]))
        side.render(painter, at, QRegion(), _FLAGS)
        _draw_page(painter, page, page.mapTo(frame, QPoint(0, 0)) - up, QColor(c["bg1"]))
    finally:
        painter.end()
        for field in hidden:
            field.setEchoMode(QLineEdit.Password)
    return image


def picture_scale(frame: QWidget, header: QWidget, page: QWidget) -> float:
    size = window_size(frame, header, page)
    return shot_scale(size.width(), size.height())
