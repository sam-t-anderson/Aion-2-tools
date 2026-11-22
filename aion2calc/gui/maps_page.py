"""The native Maps page (0.2.433): Game → Maps as the web page shows it (static/maps.js, ``A2Maps``), its three
windows one under the other.

- **Interactive maps:** the provider's maps (InteractiveMap.app) for Verteron, Altgard, Poeta and Ishalgen. The
  native window cannot embed the provider's page, so **Open provider** shows the chosen map in the browser, as the web
  page's own button does; the provider's notes and the other regional references are as on the web page.
- **Abyss PvP heat map:** where players fight players in the Abyss, from the log server's ``/api/v1/pvp-heat``
  through the app: the server matchups by region (the busiest first), the square size, the status line, the map
  itself (the ground recordings have covered, the squares in their ramp step, kills, the recorded bosses, and what
  the pointer is over), its legend and its 25 busiest squares. It is read again every ``refresh_seconds`` (at least
  five minutes) while the page is shown.
- **Farming routes:** the bundled route catalog (``static/farming-routes.json``): each zone's attributed waypoint
  loops with their legs, waypoints, sources and licences, **Copy as text**, and its guide links. The zone follows
  the map chosen above.

The words and the geometry are ``maps.py``'s, checked against the web page's own functions. The choices last while
the app runs.
"""
from __future__ import annotations

import html
import time
import urllib.parse
import webbrowser

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import maps as m
from . import theme
from .api import AppApi, Requests
from .chrome import FlowLayout
from .database_page import Window
from .gathering_page import GatheringPage, table
from .timers_page import Fold

ROUTES_LOADING = "Loading the route catalog…"
HEAT_LOADING = "Loading the heat map…"
GUIDES = "Guides (links only — no reuse terms, so nothing from them is copied)"
NATIVE_NOTE = ("The native window does not embed the provider's page: Open provider shows the map in your browser. "
               "The provider's page downloads about 10–14 MB, including its advertising and tracking scripts.")


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _link(href: str, words: str) -> str:
    return (f"<a href='{html.escape(str(href), quote=True)}' style='color: {theme.COLORS['accent']};'>"
            f"{html.escape(str(words))}</a>")


def _plain() -> QWidget:
    box = QWidget()
    box.setObjectName("plain")
    return box


def _field(words: str, widget: QWidget) -> QWidget:
    box = _plain()
    line = QHBoxLayout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    line.addWidget(_label(words, wrap=False))
    line.addWidget(widget)
    return box


def _flow() -> tuple[QWidget, FlowLayout]:
    box = _plain()
    return box, FlowLayout(box, align=Qt.AlignLeft, gap=(12, 8))


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget, inner = child.widget(), child.layout()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif inner is not None:
            _clear(inner)


class HeatMap(QWidget):
    """The heat map (``data-heat-canvas``): north up, the squares in their ramp step over the ground recordings have
    covered, a dot for a square with a kill, a diamond for each recorded boss, and the tip of what the pointer is
    over."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.data: dict | None = None
        self.view: dict | None = None
        self.hover = None
        self.setMouseTracking(True)
        self.setObjectName("heatMap")
        self.tip = QLabel(self)
        self.tip.setObjectName("heatTip")
        self.tip.setTextFormat(Qt.RichText)
        self.tip.hide()
        self.tip.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_data(self, data: dict | None) -> None:
        self.data, self.hover = data, None
        self.tip.hide()
        self.setAccessibleName(m.described(data) if data else "")
        self.lay_out()
        self.update()

    def lay_out(self) -> None:
        """The map's place and size for the frame's width (``layout``); the widget is as tall as the map."""
        window = self.window()
        tall = window.height() if window is not None and window is not self else 900
        self.view = m.view(self.data, self.width(), tall) if self.data else None
        height = self.view["h"] if self.view else 0
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)
            self.setMaximumHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.lay_out()

    def paintEvent(self, _event) -> None:
        if not self.data or not self.view:
            return
        v, data = self.view, self.data
        top = m.most_hits(data)
        text, muted, surface = QColor(theme.COLORS["text"]), QColor(theme.COLORS["muted"]), QColor(m.SURFACE)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(QRectF(v["ox"], 0, v["w"], v["h"]), surface)
        ground = QColor(m.GROUND)
        for cx, cy in data.get("footprint") or []:                 # the ground recordings have covered, without gaps
            x, y, z = m.box(v, cx, cy)
            painter.fillRect(QRectF(x, y, z + .5, z + .5), ground)
        painter.setPen(Qt.NoPen)
        for cell in data.get("cells") or []:                       # a 1 px surface gap round a square big enough
            x, y, z = m.box(v, cell[0], cell[1])
            g = 1 if z >= 6 else 0
            painter.setBrush(QColor(m.RAMP[m.heat_step(cell[2], top)]))
            if z >= 8:
                painter.drawRoundedRect(QRectF(x + g, y + g, z - 2 * g, z - 2 * g), min(3, z / 4), min(3, z / 4))
            else:
                painter.drawRect(QRectF(x + g, y + g, z - 2 * g, z - 2 * g))
        for cell in data.get("cells") or []:                       # a kill: a dot with a surface ring
            if not cell[3]:
                continue
            x, y, z = m.box(v, cell[0], cell[1])
            r = max(1.5, min(5, z * .15))
            painter.setPen(QPen(surface, 2 if z >= 20 else 1))
            painter.setBrush(text)
            painter.drawEllipse(QPointF(x + z / 2, y + z / 2), r, r)
        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        for boss in data.get("landmarks") or []:                   # a boss: a diamond, its name with a surface halo
            x, y = m.at(v, boss["x"], boss["y"])
            diamond = QPainterPath(QPointF(x, y - 6))
            for px, py in ((x + 6, y), (x, y + 6), (x - 6, y)):
                diamond.lineTo(px, py)
            diamond.closeSubpath()
            painter.setPen(QPen(text, 2))
            painter.setBrush(surface)
            painter.drawPath(diamond)
            name = str(boss.get("name") or "")
            wide = metrics.horizontalAdvance(name)
            left = x + 10 + wide > v["ox"] + v["w"]
            start = x - 10 - wide if left else x + 10
            path = QPainterPath()
            path.addText(QPointF(start, y + (metrics.ascent() - metrics.descent()) / 2), font, name)
            painter.setPen(QPen(surface, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(muted)
            painter.drawPath(path)
        if self.hover and self.hover[0] == "cell":
            x, y, z = m.box(v, self.hover[1][0], self.hover[1][1])
            painter.setPen(QPen(text, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(x + 1, y + 1, z - 2, z - 2))
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        if not self.data or not self.view:
            return
        point = event.position()
        found = m.under(self.view, self.data, point.x(), point.y())
        if (found and found[1]) is not (self.hover and self.hover[1]):
            self.hover = found
            self.update()
        if not found:
            self.tip.hide()
            return
        lead, line, where = m.tip(self.data, found)
        self.tip.setText(f"<b>{html.escape(lead)}</b><br>{html.escape(line)}<br>"
                         f"<span style='color: {theme.COLORS['muted']};'>{html.escape(where)}</span>")
        self.tip.adjustSize()
        left = min(max(4, point.x() + 14), self.width() - self.tip.width() - 4)
        top = point.y() - self.tip.height() - 10
        self.tip.move(int(left), int(top if top >= 4 else point.y() + 16))
        self.tip.show()
        self.tip.raise_()

    def leaveEvent(self, event) -> None:
        if self.hover:
            self.hover = None
            self.update()
        self.tip.hide()
        super().leaveEvent(event)


class Mark(QWidget):
    """A key's mark as the map draws it: a kill's dot with its surface ring, or a boss's diamond."""

    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(14, 14)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        text, surface = QColor(theme.COLORS["text"]), QColor(m.SURFACE)
        if self.kind == "kill":
            painter.setPen(QPen(surface, 2))
            painter.setBrush(text)
            painter.drawEllipse(QPointF(7, 7), 4, 4)
        else:
            diamond = QPainterPath(QPointF(7, 2))
            for x, y in ((12, 7), (7, 12), (2, 7)):
                diamond.lineTo(x, y)
            diamond.closeSubpath()
            painter.setPen(QPen(text, 2))
            painter.setBrush(surface)
            painter.drawPath(diamond)
        painter.end()


class Legend(QWidget):
    """The map's key (``.heat-legend``): the ramp from one hit to the busiest square's, a kill, the ground and a boss."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.flow = FlowLayout(self, align=Qt.AlignLeft, gap=(6, 4))

    def set_data(self, data: dict) -> bool:
        _clear(self.flow)
        cells = data.get("cells") or []
        if cells:
            self.flow.addWidget(_label("PvP hits per square:  1", wrap=False))
            for colour in m.RAMP:
                self.flow.addWidget(self._swatch(f"background: {colour}; border-radius: 2px;", 18, 12))
            self.flow.addWidget(_label(m.num(m.most_hits(data)), wrap=False))
            if any(cell[3] for cell in cells):
                self._key(Mark("kill"), "a square with a kill")
        if data.get("footprint"):
            self._key(self._swatch(f"background: {m.GROUND}; border: 1px solid {theme.COLORS['line']}; border-radius: 2px;",
                                   18, 12), "ground recordings have covered")
        if data.get("landmarks"):
            self._key(Mark("boss"), "a recorded boss")
        return self.flow.count() > 0

    def _swatch(self, style: str, width: int, height: int) -> QLabel:
        swatch = QLabel()
        swatch.setObjectName("swatch")
        swatch.setFixedSize(width, height)
        swatch.setStyleSheet(f"QLabel#swatch {{ {style} }}")
        return swatch

    def _key(self, mark: QWidget, words: str) -> None:
        key = _plain()
        line = QHBoxLayout(key)
        line.setContentsMargins(14, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(mark)
        line.addWidget(_label(words, wrap=False))
        self.flow.addWidget(key)


class MapsPage(QWidget):
    """Game → Maps. The route catalog and the heat map are read when the page is first shown; the heat map again
    every ``refresh_seconds`` while it is shown."""

    def __init__(self, api: AppApi | None, open_link=webbrowser.open, clipboard=None, now=time.time,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_link, self.now = api, open_link, now
        self.clipboard = clipboard or (lambda text: QGuiApplication.clipboard().setText(text))
        self.routes: dict | None = None
        self.heat: dict | None = None
        self.cell, self.matchup, self.listed = 2000, "", ""
        self.loaded_at = 0.0
        self.serial = 0
        self.started = False
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_heat)
        self.setStyleSheet(self._stylesheet())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(self._provider())
        layout.addWidget(self._heat())
        layout.addWidget(self._routes())
        layout.addStretch(1)

    @staticmethod
    def _stylesheet() -> str:
        cl = theme.COLORS
        return GatheringPage._stylesheet() + f"""
        QWidget#plain {{ background: transparent; }}
        QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
                       padding: 9px 12px; }}
        QFrame#note QLabel, QFrame#note QToolButton, QFrame#note QWidget#foldBody, QFrame#note QWidget#plain {{
            background: transparent; border: none; padding: 0; }}
        QFrame#note QLabel {{ color: {theme.COLORS['note_fg']}; }}
        QFrame#note QLabel#muted {{ color: {cl['muted']}; }}
        QFrame#note QToolButton#fold {{ color: {theme.COLORS['note_fg']}; font-weight: 600; }}
        QWidget#foldBody {{ background: transparent; }}
        QToolButton#fold {{ border: none; padding: 2px 0; color: {cl['text']}; }}
        QFrame#heatFrame {{ background: {m.SURFACE}; border: 1px solid {cl['line']}; border-radius: 6px; }}
        QWidget#heatMap {{ background: transparent; }}
        QLabel#heatTip {{ background: {cl['panel2']}; border: 1px solid {cl['line2']}; border-radius: 6px; padding: 6px 8px;
                          font-size: 12px; color: {cl['text']}; }}
        QLabel#h4 {{ font-weight: 700; }}
        """

    # ------------------------------------------------------------------ the windows
    def _provider(self) -> QWidget:
        window = Window("Interactive maps", "InteractiveMap.app")
        line, flow = _flow()
        self.zone_box = QComboBox()
        self.zone_box.setAccessibleName("Map")
        for zone, name in m.ZONES.items():
            self.zone_box.addItem(name, zone)
        self.zone_box.activated.connect(lambda _index: self._follow_map())
        flow.addWidget(_field("Map", self.zone_box))
        provider = QPushButton("Open provider ↗")
        provider.clicked.connect(lambda: self.open_link(m.provider_url(self.zone_box.currentData())))
        flow.addWidget(provider)
        window.body.addWidget(line)
        window.body.addWidget(_label(m.PROVIDER_NOTE, "muted"))
        window.body.addWidget(_label(NATIVE_NOTE))
        references = _label("More regional map references: " + " · ".join(_link(url, name) for name, url in m.REFERENCES)
                            + ".", "muted", rich=True)
        references.linkActivated.connect(self.open_link)
        window.body.addWidget(references)
        return window

    def _heat(self) -> QWidget:
        window = Window("Abyss PvP heat map", "Where players fight players, by server matchup")
        line, flow = _flow()
        self.matchup_box = QComboBox()
        self.matchup_box.setAccessibleName("Matchup")
        self.matchup_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.matchup_box.addItem("Loading the matchups…", "")
        self.matchup_box.activated.connect(lambda _index: self._choose_matchup())
        flow.addWidget(_field("Matchup", self.matchup_box))
        self.cell_box = QComboBox()
        self.cell_box.setAccessibleName("Squares")
        for size, words in m.HEAT_CELLS:
            self.cell_box.addItem(words, size)
        self.cell_box.activated.connect(lambda _index: self._choose_cell())
        flow.addWidget(_field("Squares", self.cell_box))
        self.refresh = QPushButton("Refresh")
        self.refresh.clicked.connect(self.load_heat)
        flow.addWidget(self.refresh)
        window.body.addWidget(line)
        self.heat_status = _label(HEAT_LOADING)
        window.body.addWidget(self.heat_status)
        self.frame = QFrame()
        self.frame.setObjectName("heatFrame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        self.map = HeatMap()
        frame_layout.addWidget(self.map)
        self.frame.hide()
        window.body.addWidget(self.frame)
        self.legend = Legend()
        self.legend.hide()
        window.body.addWidget(self.legend)
        self.squares = Fold("The squares as a table")
        self.squares.hide()
        window.body.addWidget(self.squares)
        self.heat_note = _label("", "muted")
        window.body.addWidget(self.heat_note)
        return window

    def _routes(self) -> QWidget:
        window = Window("Farming routes", "Attributed waypoint loops · guide links")
        line, flow = _flow()
        self.route_zone = QComboBox()
        self.route_zone.setAccessibleName("Zone")
        self.route_zone.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.route_zone.activated.connect(lambda _index: self.draw_routes())
        flow.addWidget(_field("Zone", self.route_zone))
        window.body.addWidget(line)
        body = _plain()
        self.route_body = QVBoxLayout(body)
        self.route_body.setContentsMargins(0, 0, 0, 0)
        self.route_body.setSpacing(8)
        self.route_body.addWidget(_label(ROUTES_LOADING, "muted"))
        window.body.addWidget(body)
        return window

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.started:
            self.started = True
            if self.requests is not None:
                self.requests.get("routes", "/static/farming-routes.json")
            self.load_heat()
        elif self.heat is not None and time.monotonic() - self.loaded_at > m.refresh_ms(self.heat) / 1000:
            self.load_heat()                                       # back after a while: the map read afresh
        if self.heat is not None and not self.timer.isActive():
            self.timer.start(m.refresh_ms(self.heat))

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_map)

    def _fit_map(self) -> None:
        if self.heat is not None and self.heat.get("bounds"):
            self.map.lay_out()
            self.map.update()

    def load_heat(self) -> None:
        """The heat map for the matchup and square size chosen (``load``)."""
        if self.requests is None:
            return
        self.serial += 1
        self.refresh.setEnabled(False)
        path = m.heat_path(self.cell, self.matchup)
        self.requests.get(f"heat:{self.serial}", "/api/community?path=" + urllib.parse.quote(path, safe=""))

    def _replied(self, name: str, answer) -> None:
        if name == "routes":
            if not isinstance(answer, dict) or not isinstance(answer.get("zones"), list):
                return self._routes_failed("Route catalog unavailable")
            self.routes = answer
            self.route_zone.clear()
            for zone in answer["zones"]:
                self.route_zone.addItem(m.zone_label(zone), zone.get("id"))
            current = m.zone_for_map(answer, self.zone_box.currentData())
            if current is not None:
                self.route_zone.setCurrentIndex(max(0, self.route_zone.findData(current.get("id"))))
            self.draw_routes()
        elif name.startswith("heat:"):
            if int(name[5:]) != self.serial:
                return                                             # an older answer, overtaken
            self.refresh.setEnabled(True)
            if not isinstance(answer, dict) or not isinstance(answer.get("cells"), list):
                return self._heat_failed(m.NOT_OFFERED)
            if not self.matchup and isinstance(answer.get("matchups"), list):
                pick = m.busiest(answer)
                if pick != "all":                                  # no choice yet: the busiest matchup, asked for
                    self.matchup = pick
                    self._list_matchups(answer)
                    return self.load_heat()
                self.matchup = "all"
            self._list_matchups(answer)
            self.heat, self.loaded_at = answer, time.monotonic()
            self.draw_heat()
            if self.isVisible():
                self.timer.start(m.refresh_ms(answer))

    def _failed(self, name: str, why: str) -> None:
        if name == "routes":
            self._routes_failed(f"Route catalog unavailable ({why})")
        elif name.startswith("heat:") and int(name[5:]) == self.serial:
            self.refresh.setEnabled(True)
            self._heat_failed(m.failure(why))

    def _heat_failed(self, words: str) -> None:
        self.heat_status.setText(words)
        if self.heat is None:
            self.frame.hide()
            self.legend.hide()
            self.squares.hide()

    def _routes_failed(self, words: str) -> None:
        _clear(self.route_body)
        self.route_body.addWidget(_label(words))

    # ------------------------------------------------------------------ the heat map
    def _list_matchups(self, data: dict) -> None:
        key = m.matchups_key(data)
        if key == self.listed:
            return
        self.listed = key
        box = self.matchup_box
        box.blockSignals(True)
        box.clear()
        for region, choices in m.matchup_groups(data):
            if region:
                box.addItem(region, None)                          # a region's heading, as an <optgroup> labels it
                heading = box.model().item(box.count() - 1)
                heading.setEnabled(False)
                font = heading.font()
                font.setBold(True)
                heading.setFont(font)
            for value, words in choices:
                box.addItem(words, value)
        box.setCurrentIndex(max(0, box.findData(m.chosen(self.matchup, data))))
        box.blockSignals(False)

    def _choose_matchup(self) -> None:
        self.matchup = self.matchup_box.currentData() or "all"
        self.load_heat()

    def _choose_cell(self) -> None:
        self.cell = int(self.cell_box.currentData())
        self.load_heat()

    def draw_heat(self) -> None:
        data = self.heat
        self.heat_status.setText(m.status_line(data, self.now()))
        self.heat_note.setText(str(data.get("note") or ""))
        if not data.get("bounds"):
            self.frame.hide()
            self.legend.hide()
            self.squares.hide()
            return
        self.frame.show()
        self.map.set_data(data)
        self.legend.setVisible(self.legend.set_data(data))
        rows, more = m.busiest_squares(data)
        _clear(self.squares.body_layout)
        if rows:
            self.squares.add(table(["Square: x", "Square: y", "PvP hits", "Kills"], rows))
            if more:
                self.squares.add(_label(more, "muted"))
        self.squares.setVisible(bool(rows))

    # ------------------------------------------------------------------ the routes
    def _follow_map(self) -> None:
        """The routes' zone follows the map chosen above it."""
        if self.routes is None:
            return
        zone = m.zone_for_map(self.routes, self.zone_box.currentData())
        if zone is not None:
            self.route_zone.setCurrentIndex(max(0, self.route_zone.findData(zone.get("id"))))
            self.draw_routes()

    def draw_routes(self) -> None:
        """The zone's routes and guides (``routesHTML``)."""
        data = self.routes
        if data is None:
            return
        _clear(self.route_body)
        zones = data.get("zones") or []
        zone = next((z for z in zones if z.get("id") == self.route_zone.currentData()), zones[0] if zones else None)
        if zone is None:
            self.route_body.addWidget(_label("The catalog has no zones.", "muted"))
            return
        for line in zone.get("notes") or []:
            self.route_body.addWidget(_label(str(line), "muted"))
        sources = data.get("sources") or {}
        routes = zone.get("routes") or []
        for index, route in enumerate(routes):
            self.route_body.addWidget(self._route(zone, route, sources.get(route.get("source")), index == 0))
        if not routes:
            self.route_body.addWidget(_label("No route is listed for this zone."))
        self.route_body.addWidget(_label(GUIDES, "h4"))
        guides = [g for g in zone.get("guides") or [] if isinstance(g, dict)]
        if guides:
            items = "".join(f"<li>{_link(g.get('url'), g.get('title'))}" + (
                f" <span style='color: {theme.COLORS['muted']};'>— {html.escape(str(g['topic']))}</span>" if g.get("topic")
                else "") + "</li>" for g in guides)
            listed = _label(f"<ul style='margin: 0;'>{items}</ul>", rich=True)
            listed.linkActivated.connect(self.open_link)
            self.route_body.addWidget(listed)
        else:
            self.route_body.addWidget(_label("No guide links were found for this zone.", "muted"))
        self.route_body.addWidget(_label(m.catalog_line(data), "muted"))

    def _route(self, zone: dict, route: dict, source, opened: bool) -> QFrame:
        """One route (a ``<details class="note">``): its note and method, its source, its legs, its waypoints and its
        Copy as text."""
        box = QFrame()
        box.setObjectName("note")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        fold = Fold(m.route_summary(route), opened=opened)
        fold.add(_label(f"{route.get('note')} {route.get('method')}", "muted"))
        credit = _label(m.source_line(route, source), rich=True)
        credit.linkActivated.connect(self.open_link)
        fold.add(credit)
        legs = "".join(f"<li>{m.leg_line(route, leg)}</li>" for leg in route.get("legs") or [])
        fold.add(_label(f"<ol style='margin: 0;'>{legs}</ol>", rich=True))
        points = Fold(f"All {route.get('count')} waypoints in order")
        points.add(_label("<ol style='margin: 0;'>" + "".join(f"<li>{m.waypoint_line(w)}</li>" for w in
                                                               route.get("waypoints") or []) + "</ol>", rich=True))
        fold.add(points)
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        copy = QPushButton("Copy as text")
        said = _label("", "muted", wrap=False)
        copy.clicked.connect(lambda: self._copy(m.route_text(zone, route, source), said))
        line.addWidget(copy)
        line.addWidget(said)
        line.addStretch(1)
        fold.add(row)
        layout.addWidget(fold)
        return box

    def _copy(self, text: str, said: QLabel) -> None:
        try:
            self.clipboard(text)
        except Exception:                                         # noqa: BLE001 - a clipboard another program holds
            said.setText("Clipboard blocked; select the list and copy it.")
            return
        said.setText("Copied.")

    def closeEvent(self, event) -> None:
        self.timer.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
