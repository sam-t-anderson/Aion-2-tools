"""The native overlay's ninth part (0.2.422): the chrome round the rows as the web overlay's compact layout draws it
(overlay.css ``#ov.ov-nm``), off screen.

The card's parts in the compact layout's order and with its margins in each background; the fight's clock, your
contribution, the identity line and the events strip as chips under the rows; the ping, the frame rate and the
toolbar of icons with the metric chip on a line of their own; the options folded away under the toolbar; the lock's
dashed edge; and what the overlay says when the app does not answer. No check hangs on the width of a font.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QHelpEvent, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolTip  # noqa: E402

from aion2calc.gui import chrome  # noqa: E402
from aion2calc.gui.chrome import ICONS, FlowLayout, IconButton, icon  # noqa: E402
from aion2calc.gui.look import CHIP_SHADOW, TextLook, draw_text  # noqa: E402
from aion2calc.gui.overlay import MeterOverlay  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, laid_out_apart, settle  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def _shown(window):
    window.show()
    QCoreApplication.processEvents()
    return window


def _place(window, widget):
    """``widget``'s place in the window's own pixels."""
    corner = widget.mapTo(window, QPoint(0, 0))
    return corner.x(), corner.y(), widget.width(), widget.height()


def _near(image: QImage, colour: str, box: QRectF | None = None, reach: int = 40) -> int:
    want, count = QColor(colour), 0
    box = box or QRectF(0, 0, image.width(), image.height())
    for y in range(max(0, int(box.top())), min(image.height(), int(box.bottom()))):
        for x in range(max(0, int(box.left())), min(image.width(), int(box.right()))):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > 150:
                count += 1
    return count


# ------------------------------------------------------------------ the card
def test_the_cards_parts_come_in_the_compact_layouts_order(qapp):
    window = _overlay()
    box = window.box
    order = [window.connection, window.lines_part, window.target_card, window.dummy, window.content,
             window.panel_scroll, window.graph, window.cooldowns, window.chips, window.foot, window.options]
    assert [box.indexOf(part) for part in order] == sorted(box.indexOf(part) for part in order)
    assert box.spacing() == 0                                       # each part keeps its own margins, none shared
    chips = window.chips.layout()
    assert [chips.itemAt(i).widget() for i in range(chips.count())] == [window.clock, window.contribution,
                                                                        window.identity, window.events]
    foot = window.foot.layout()
    assert [foot.itemAt(i).widget() for i in range(foot.count())] == [window.ping, window.fps, window.toolbar]
    tools = window.toolbar.layout()
    assert tools.itemAt(0).widget() is window.metric_chip            # the chip at the toolbar's head
    assert [tools.itemAt(i).widget().icon_name for i in range(1, tools.count())] == [
        "camera", "new", "copy", "options", "stop", "close"]          # the fight runs: the stop square
    laid_out_apart(_shown(window))


@pytest.mark.parametrize("mode, margins, rows", [("card", (9, 5, 9, 9), 322), ("top", (1, 1, 1, 1), 338),
                                                 ("none", (1, 1, 1, 1), 338)])
def test_each_background_takes_the_web_cards_padding(qapp, mode, margins, rows):
    window = _shown(_overlay(overlay_bg_mode=mode))
    got = window.box.contentsMargins()
    assert (got.left(), got.top(), got.right(), got.bottom()) == margins
    assert all(row.width() == rows for row in _rows(window))         # on the whole card 8 px in, else a pixel
    # The counters' box keeps its padding with no counter shown, as the web overlay's does: on the whole card the
    # target card starts 5 px under the card's own 5, with nothing behind it 12 px under its 1 (the box a chip).
    lines = window.lines_part.layout().contentsMargins()
    assert window.lines.isHidden() and window.lines_part.height() == lines.top() + lines.bottom()
    assert window.target_card.geometry().top() == {"card": 10, "top": 8, "none": 13}[mode]
    pad = window.target_row.contentsMargins()
    assert (pad.left(), pad.top()) == ((2, 6) if mode == "card" else (10, 7))
    laid_out_apart(window)


def test_the_card_takes_the_compact_layouts_colour_and_the_top_portion_ends_at_the_rows(qapp):
    window = _shown(_overlay())
    image = window.card.grab().toImage()
    pixel = image.pixelColor(window.width() // 2, 3)                # above the target card, nothing drawn on it
    assert all(abs(got - want) <= 1 for got, want in zip(pixel.getRgb(), (12, 14, 17, round(255 * 0.72))))
    window.apply_ui({"overlay_width": 340, "overlay_bg_mode": "top"})
    window.apply_meter(fight())
    QCoreApplication.processEvents()
    image = window.card.grab().toImage()
    end = window.content.geometry().top()                          # the rows' part begins
    assert image.pixelColor(170, end - 3).alpha() > 150             # the panel behind the top portion
    assert image.pixelColor(170, end + 2).alpha() == 0              # and nothing between it and the first row
    assert image.pixelColor(window.width() - 3, window.chips.geometry().center().y()).alpha() == 0


def test_lock_draws_the_cards_edge_dashed_green(qapp):
    window = _shown(_overlay())
    plain = window.card.grab().toImage()
    window.toggle_lock()
    locked = window.card.grab().toImage()
    edge = [(x, 0) for x in range(20, 320)]
    greener = sum(1 for x, y in edge if locked.pixelColor(x, y).green() > plain.pixelColor(x, y).green() + 40)
    assert 80 < greener < 220                                      # along the edge, dashed
    window.toggle_lock()
    assert window.card.grab().toImage() == plain


# ------------------------------------------------------------------ the chips under the rows
def test_the_clock_its_notes_and_its_tooltip(qapp):
    meter = fight()
    meter["snapshot"].update(duration=3725.4, decode_backlog={"catching_up": True, "queue_depth": 64})
    meter["targets"] = ["boss", "player"]
    meter["error"] = "the capture driver stopped"
    window = _overlay(meter)
    assert window.clock.text() == ("62:05 Bosses + PvP catching up (64) Capture stopped Party DPS 45.70K")
    assert window.clock.toolTip() == window.status_text == "Capture stopped: the capture driver stopped"
    tips = [part.tip for part in window.clock.parts]
    assert tips == ["", "", "Boss and player damage only", "", "the capture driver stopped", ""]
    (time_, made, colour), = window.clock.parts[1].runs
    assert made.families()[0] in chrome.MONOSPACE and int(made.weight()) == 700 and colour == "#e9edf1"
    assert made.letterSpacing() == 0.5 and made.pixelSize() == 13
    party = window.clock.parts[-1].runs
    assert [(text, colour, int(made.weight())) for text, made, colour in party] == [
        ("Party DPS ", "#9aa3b5", 600), ("45.70K", "#63d3e6", 800)]
    window.set_metric("dtps")                     # the recorded time outside DPS, and the notes of DPS alone
    assert window.clock.text() == "01:15 catching up (64) Capture stopped Party DTPS 0"
    window.set_metric("hps")
    assert window.clock.isHidden()                # no healing, no rows: no clock, as on the web overlay
    for player in meter["snapshot"]["players"]:
        player["hps"], player["healing"] = 900, 900 * 75
    window.apply_meter(meter)
    assert not window.clock.isHidden() and window.clock.parts[-1].runs[0][0] == "Party HPS "


def test_a_notes_own_tooltip_shows_over_it(qapp, monkeypatch):
    meter = fight()
    meter["targets"] = ["boss"]
    window = _shown(_overlay(meter))
    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda point, text, widget=None: shown.append(text))
    places = dict((part.tip or "", rect) for part, rect in window.clock._places())
    for tip in ("Boss damage only", ""):
        centre = places[tip].center().toPoint()
        window.clock.event(QHelpEvent(QEvent.ToolTip, centre, window.clock.mapToGlobal(centre)))
    assert shown == ["Boss damage only", window.status_text]       # the note's own, else the fight's status


def test_the_clocks_parts_go_on_to_another_line_in_a_narrow_overlay(qapp):
    meter = fight()
    meter["snapshot"].update(paused=True, decode_backlog={"catching_up": True, "queue_depth": 1200})
    wide = _shown(_overlay(fight()))
    narrow = _shown(_overlay(meter, overlay_width=260, overlay_font_scale=160))
    assert wide.clock.height() < 30 < narrow.clock.height()         # one line, then more than one
    places = [rect for _part, rect in narrow.clock._places()]
    assert len({round(rect.top()) for rect in places}) > 1
    assert all(rect.right() <= narrow.clock.width() for rect in places)
    laid_out_apart(narrow)


def test_the_chips_share_a_line_where_they_fit(qapp):
    meter = fight()
    meter["snapshot"]["contribution"] = {"damage": 1_380_000, "share": 0.34, "dps": 18_400}
    window = _shown(_overlay(meter))
    assert window.contribution.text() == "Your contribution: 34% · 1.38M (18.40K/s)"
    assert window.contribution.geometry().top() > window.clock.geometry().bottom()   # no room beside the clock
    assert window.contribution.geometry().left() == window.clock.geometry().left() == 0
    (text, made, colour), = window.contribution.parts[0].runs
    assert colour == "#88d1d2" and made.pointSizeF() == pytest.approx(10.5 * 0.75)   # 10.5 px, its own size
    wide = _shown(_overlay(meter, overlay_width=800))
    clock, contribution = wide.clock.geometry(), wide.contribution.geometry()
    assert contribution.top() == clock.top() and contribution.left() == clock.right() + 1 + 6   # 6 px apart


def test_the_identity_line_and_the_rows_notes_float_as_chips(qapp):
    meter = fight()
    meter["snapshot"]["identity_status"].update(unnamed_actors=2, linked_pets=1)
    meter["snapshot"]["warning"] = "Your name comes with the next zone load"
    window = _shown(_overlay(meter))
    assert not window.identity.isHidden() and window.identity.parentWidget() is window.chips
    margins = window.identity.contentsMargins()
    assert (margins.left(), margins.top()) == (9, 3)
    assert window.identity.graphicsEffect().shadow == CHIP_SHADOW
    assert window.warning.graphicsEffect().shadow == CHIP_SHADOW and window.warning.parentWidget() is window.content
    assert window.warning.width() < window.content.width()          # as wide as its words (``inline-block``)


def test_a_chips_text_lies_over_its_shadow():
    image = QImage(120, 30, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    font = chrome.font(["DejaVu Sans"], 14, 700)
    draw_text(painter, QRectF(10, 0, 100, 30), "Atiel", font, QColor("#ffffff"), Qt.AlignLeft, TextLook({}),
              shadow=CHIP_SHADOW)
    painter.end()
    dark = sum(1 for y in range(30) for x in range(120)
               if image.pixelColor(x, y).alpha() > 40 and image.pixelColor(x, y).lightness() < 60)
    white = sum(1 for y in range(30) for x in range(120) if image.pixelColor(x, y).lightness() > 200
                and image.pixelColor(x, y).alpha() > 200)
    assert dark > 40 and white > 20                                # the words, and the dark round them
    assert TextLook({}).painted is False                            # a chip's shadow is no effect of the look's


# ------------------------------------------------------------------ the line of the ping and the toolbar
def test_the_ping_left_and_the_toolbar_right_on_a_line_of_their_own(qapp):
    window = _shown(_overlay())
    ping, toolbar = window.ping.geometry(), window.toolbar.geometry()
    assert ping.left() == 0 and toolbar.right() == window.foot.width() - 1 and ping.top() == toolbar.top()
    assert window.foot.geometry().top() > window.chips.geometry().bottom()
    narrow = _shown(_overlay(overlay_width=260, overlay_font_scale=160))
    ping, toolbar = narrow.ping.geometry(), narrow.toolbar.geometry()
    assert toolbar.top() > ping.bottom()                           # no room beside the ping: a line below
    assert toolbar.right() == narrow.foot.width() - 1               # and to the right still
    laid_out_apart(narrow)


def test_the_icons_are_the_web_overlays_drawn_in_their_colour(qapp):
    assert set(ICONS) == {"camera", "new", "copy", "options", "play", "stop", "close", "signal"}
    for name in ICONS:
        picture = icon(name, 16, 16, "#ff0000").toImage()
        assert _near(picture, "#ff0000", reach=10) > 15, name     # drawn, in red
        assert _near(picture, "#ffffff", reach=10) == 0
    signal = icon("signal", 23, 20, "#4ea8ef").toImage()           # 20 × 16, as large as fits and centred
    rows = [y for y in range(20) if any(signal.pixelColor(x, y).alpha() > 128 for x in range(23))]
    assert rows[0] >= 1 and rows[-1] <= 18


def test_a_buttons_colour_says_what_it_is_and_how_its_press_went(qapp):
    button = IconButton("copy", "Copy", "Copy the meter")
    assert button.accessibleName() == "Copy" and button.toolTip() == "Copy the meter"
    assert button.sizeHint().toTuple() == (26, 24) and button.shown_colour().name() == "#c9d1db"
    button.state = "ok"
    assert button.shown_colour().name() == "#6fe3a3"
    button.state = "err"
    assert button.shown_colour().name() == "#ff8585"
    button.tone = "#63d3e6"                                         # its own colour wins over the press's
    assert button.shown_colour().name() == "#63d3e6"
    button.state, button.tone, button.scale = "", None, 1.5
    assert button.sizeHint().toTuple() == (39, 36)
    image = button.grab().toImage()
    assert _near(image, "#c9d1db", reach=12) > 10


def test_the_toolbar_draws_the_icons_and_the_metric_chip(qapp):
    window = _shown(_overlay())
    image = window.grab().toImage()
    x, y, width, height = _place(window, window.metric_chip)
    assert _near(image, "#63d3e6", QRectF(x, y, width, height), reach=30) > 10    # DPS in teal
    x, y, width, height = _place(window, window.tools["capture"])
    assert _near(image, "#ff8585", QRectF(x, y, width, height), reach=30) > 30    # the red stop square


def test_the_frame_rate_counts_the_overlays_own_frames(qapp):
    window = _overlay()
    assert window.fps.isHidden() and not window.fps.running()       # off by default
    window.apply_ui({"overlay_width": 340, "overlay_show_fps": True})
    assert window.fps.running() and window.fps.text() == ""          # nothing until a second is counted,
    assert not window.fps.isHidden() and window.fps.sizeHint().toTuple() == (1, 1)   # a pixel to draw into
    _shown(window)
    drawn = window.fps.frames
    window.fps.repaint()
    assert window.fps.frames == drawn + 1                            # each frame drawn is counted
    now = [100.0]
    window.fps.clock = lambda: now[0]
    window.fps.frames, window.fps.since = 0, 100.0
    window.fps.frames = 30
    now[0] = 100.5
    window.fps.count()
    assert window.fps.rate is None                                  # half a second: not yet
    window.fps.frames, now[0] = 60, 101.0
    window.fps.count()
    assert window.fps.rate == 60 and window.fps.text() == "60 FPS" and not window.fps.isHidden()
    window.apply_ui({"overlay_width": 340, "overlay_show_fps": True, "performance_mode": True})
    assert not window.fps.running() and window.fps.isHidden()       # never in performance mode


# ------------------------------------------------------------------ when the app does not answer
def test_the_connection_says_why_and_retry_asks_again(qapp):
    api = FakeApp(fight())
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340})
    window._meter_answered(fight())
    assert window.connection.isHidden() and window.last_success is not None
    window._meter_failed("timed out")
    assert not window.connection.isHidden() and window.status_text == "Refresh failed · retrying"
    assert window.reason.text().startswith("timed out · ")
    assert window.reason.text().endswith("s since last refresh. Last readings retained; capture status unknown.")
    assert len(_rows(window)) == 3 and window.clock.toolTip() == "Refresh failed · retrying"   # the last reading
    window.retry.click()
    settle(lambda: ("GET", "/api/meter?view=latest", None) in api.calls)
    window._meter_answered(fight())
    assert window.connection.isHidden() and window.status_text.startswith("Latest combat · Atiel")
    fresh = MeterOverlay(None)
    fresh._meter_failed("Connection refused")
    assert fresh.reason.text() == "Connection refused · Last readings retained; capture status unknown."


def test_between_the_chips_lies_the_game(qapp):
    window = _shown(_overlay(overlay_bg_mode="none"))
    host = window.host
    ratio = window.devicePixelRatioF()
    on = window.ping.mapTo(window, window.ping.rect().center())
    assert host.over_overlay((on.x() * ratio, on.y() * ratio))
    toolbar = window.toolbar.mapTo(window, QPoint(0, 0))
    gap = QPoint((window.ping.mapTo(window, QPoint(window.ping.width(), 0)).x() + toolbar.x()) // 2, on.y())
    assert window.childAt(gap) is window.foot
    assert not host.over_overlay((gap.x() * ratio, gap.y() * ratio))   # the game, between the ping and the toolbar


def test_the_options_hold_their_choices_side_by_side_and_the_opacity_under_them(qapp):
    window = _shown(_overlay(overlay_width=500))
    window.toggle_options()
    QCoreApplication.processEvents()
    assert window.combine.geometry().top() == window.boss_only.geometry().top()   # side by side
    assert window.boss_only.geometry().left() > window.combine.geometry().right()
    assert window.slider.mapTo(window, QPoint(0, 0)).y() > window.combine.mapTo(window, QPoint(0, 0)).y()
    assert all(label.graphicsEffect().shadow == CHIP_SHADOW for label in window.option_labels)
    assert window.options.geometry().top() > window.foot.geometry().bottom()
    laid_out_apart(window)


def test_the_names_do_not_turn_while_the_sheen_runs(qapp):
    look = {"overlay_text_colors": {"name": "#0000ff"}, "overlay_text_retro": True, "overlay_color_cycle": True}
    window = _shown(_overlay(**look))
    row = _rows(window)[0]
    row.seconds = 3.5                       # the sheen's band beyond the names, the cycle a quarter turn on
    row.update()
    image = row.grab().toImage()
    assert _near(image, "#0000ff", QRectF(0, 0, 170, row.height()), reach=30) > 3   # their own blue, not turned


def test_a_flow_without_a_shown_widget_takes_no_room(qapp):
    window = _overlay()
    layout = FlowLayout(None, Qt.AlignLeft, (6, 4), lead=4)
    assert layout.heightForWidth(300) == 0 and layout.sizeHint().toTuple() == (0, 0)
    for chip in (window.clock, window.contribution, window.identity, window.events):
        chip.hide()
    assert window.chips.layout().heightForWidth(322) == 0
