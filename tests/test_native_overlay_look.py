"""The native overlay's seventh part (0.2.420): its look, from the settings the web overlay's ``syncColors`` reads.

The fonts (``overlay_font_family``, ``_scale`` and ``_weight``, and each element's own in ``overlay_text_fonts``),
the text colours (``overlay_text_colors``), the outline, glow and halo, the colour cycle and the sheen, the
time-to-kill bar, the background image with its opacity, zoom and darkening, auto-contrast, and the resize grips
with ``overlay_height``, off screen. The colour cycle's colours are Chromium's own for ``filter: hue-rotate``, read
from a page it drew; no check here hangs on the width of a font, so the tests pass in any.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
import sys
import threading
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, QPoint, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from aion2calc.gui import events, overlay, theme  # noqa: E402
from aion2calc.gui.api import AppApi  # noqa: E402
from aion2calc.gui.look import (CHIP_SHADOW, TextEffect, TextLook, background_rect, contrast_colour, cycled,  # noqa: E402
                                family_name, sheen_brush)
from aion2calc.gui.overlay import MeterOverlay  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_events import CATALOG, utc  # noqa: E402
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


class PictureApp(FakeApp):
    """The app's local API with a background image to give (``/overlay-background``), or none to give (404)."""

    def __init__(self, picture=None, meter=None):
        super().__init__(meter or fight())
        self.picture = picture

    def get_bytes(self, path):
        self.calls.append(("GET", path, None))
        if self.picture is None:
            raise urllib.error.HTTPError("http://127.0.0.1" + path, 404, "Not Found", {}, io.BytesIO(b""))
        return self.picture

    def asked(self):
        return sum(1 for _method, path, _body in self.calls if path.startswith("/overlay-background?v="))


def picture(colour: str, width: int = 40, height: int = 20) -> bytes:
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def _text_colour(widget) -> str:
    return widget.palette().color(widget.foregroundRole()).name()


def _near(image: QImage, colour: str, left: int, right: int, reach: int = 48) -> int:
    """How many pixels of ``image`` from ``left`` to ``right`` are within ``reach`` of ``colour`` in each channel."""
    want, count = QColor(colour), 0
    for y in range(image.height()):
        for x in range(max(0, left), min(image.width(), right)):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > 200:
                count += 1
    return count


def _redder(image: QImage, plain: QImage, by: int = 20) -> int:
    """How many pixels of ``image`` are redder than the same of ``plain`` (red over the mean of green and blue)."""
    def red(pixel):
        return pixel.red() - (pixel.green() + pixel.blue()) / 2
    return sum(1 for y in range(min(image.height(), plain.height())) for x in range(min(image.width(), plain.width()))
               if red(image.pixelColor(x, y)) - red(plain.pixelColor(x, y)) >= by)


# ------------------------------------------------------------------ the settings
def test_the_settings_are_read_as_the_web_overlay_reads_them():
    look = TextLook({"overlay_text_colors": {"rate": "#FFD36B", "name": "red", "hp": "#12345", "ping": "#60ffff"},
                     "overlay_text_fonts": {"rate": {"scale": 140, "weight": 800}, "name": {"family": 'Fira "Code"; }'},
                                            "hp": {"scale": 170, "weight": 300}, "ttk": "bold"},
                     "overlay_font_family": "  Fira Sans ", "overlay_font_scale": "120", "overlay_font_weight": 900,
                     "overlay_text_outline": True, "overlay_glow": "yes", "overlay_text_halo": True,
                     "overlay_halo_color": "#40c0ff", "overlay_ttk_color": "nope",
                     "overlay_text_autocontrast": "dynamic"})
    assert look.colours == {"rate": "#FFD36B", "ping": "#60ffff"}                # ``#rrggbb`` alone
    assert look.fonts == {"rate": (None, 1.4, 800), "name": ("Fira Code", None, None)}   # in their ranges alone
    assert (look.family, look.scale, look.weight) == ("Fira Sans", 1.2, 600)    # 900 is past 800: the default
    assert look.outline and not look.glow and look.halo and look.effects and look.painted
    assert (look.halo_colour, look.glow_colour, look.ttk_colour) == ("#40c0ff", "#e8cf8e", "#8fb3d0")
    assert look.autocontrast == "off"
    assert look.families("name")[0] == "Fira Code" and look.families("rate")[0] == "Fira Sans"
    assert look.size("rate", 12) == 17 and look.weight_of("rate", 400) == 800 and look.weight_of("total", 400) == 400
    assert look.colour("rate", "#ffffff") == "#FFD36B" and look.colour("total", "#ffffff") == "#ffffff"
    assert look.style("hp", 12) == "" and look.inline("hp", "47%", 12) == "47%"   # nothing of its own: the line's
    look.contrast = "#0a0e16"                                                     # auto-contrast over every colour
    assert look.colour("rate", "#ffffff") == "#0a0e16" and look.inline("hp", "47%", 12).startswith(
        '<span style="color:#0a0e16">')
    plain = TextLook({})
    assert (plain.scale, plain.weight, plain.family, plain.effects, plain.painted) == (1.0, 600, "", False, False)


def test_a_typed_family_cannot_break_the_style_sheet():
    assert family_name('Fira "Code"; }') == "Fira Code"
    assert family_name("<b>Noto</b>\\") == "bNoto/b"
    assert family_name(None) == "" and family_name("   ") == ""


# ------------------------------------------------------------------ fonts and colours
def test_the_fonts_and_colours_reach_each_element(qapp):
    window = _overlay(overlay_font_family="Fira Sans", overlay_font_scale=150, overlay_font_weight=700,
                      overlay_text_colors={"header": "#9be7a0", "target": "#c0c8ff", "ping": "#60ffff",
                                           "identity": "#ffff60", "name": "#ff9db0", "total": "#7fe0ff",
                                           "rate": "#ffd36b"},
                      overlay_text_fonts={"ping": {"scale": 120, "weight": 400}, "header": {"family": "Fira Mono"}})
    px = 18                                                                       # 12 px at 150%
    target = window.target.font()
    assert target.families()[0] == "Fira Sans" and target.pixelSize() == px and int(target.weight()) == 400
    assert _text_colour(window.target) == "#c0c8ff"
    # The ping chip: its own size (120%) and colour, its weights the compact layout's (800 for the time, 600 after).
    (time_, time_font, time_colour), (unit, unit_font, _colour) = window.ping.parts[1].runs
    assert (unit, time_colour) == ("ms", "#60ffff") and time_font.families()[0] == "Fira Sans"
    assert time_font.pixelSize() == round(12 * 1.5 * 1.2) and int(time_font.weight()) == 800
    assert int(unit_font.weight()) == 600
    # The toolbar: the header's colour, at the text's size; the metric chip in the header's family, in teal.
    lock = window.tools["lock"]
    assert lock.colour == "#9be7a0" and lock.scale == 1.5 and lock.sizeHint().toTuple() == (39, 36)
    chip = window.metric_chip.label_font()
    assert chip.families()[0] == "Fira Mono" and chip.pixelSize() == px and int(chip.weight()) == 800
    # The footer's own sizes, which the text size leaves (overlay.css ``.ovidentity``, ``.ovdummy``).
    assert _text_colour(window.identity) == "#ffff60" and window.identity.font().pixelSize() == 10
    assert window.dummy.font().families()[0] == "Fira Sans" and window.dummy.font().pixelSize() == 11
    assert window.panel.value_colour == "#ffd36b"                                # the panel's tiles: the rate's
    rows = _rows(window)
    assert rows and all(row.text_look is window.text_look for row in rows)
    window.apply_ui({"overlay_width": 340})                                       # cleared: the overlay's own again
    assert window.metric_chip.label_font().families()[0] == theme.FONT_FAMILIES[0]
    assert window.metric_chip.label_font().pixelSize() == 12
    assert window.tools["lock"].colour == "#c9d1db" and window.tools["lock"].sizeHint().toTuple() == (26, 24)
    assert window.ping.parts[1].runs[0][2] == "#eef1f4" and _text_colour(window.identity) == "#e8cf8e"
    assert window.panel.value_colour == "#ffffff"


def test_the_rows_draw_each_part_in_its_elements_colour(qapp):
    window = _overlay(overlay_text_colors={"rate": "#ff0000", "total": "#00ff00", "name": "#0000ff"})
    row = _rows(window)[0]
    image = row.grab().toImage()
    half = image.width() // 2
    assert _near(image, "#0000ff", 0, half) > 3 and _near(image, "#0000ff", half, image.width()) == 0
    assert _near(image, "#ff0000", half, image.width()) > 3 and _near(image, "#ff0000", 0, half) == 0
    assert _near(image, "#00ff00", half, image.width()) > 3
    window.apply_ui({"overlay_width": 340, "overlay_compact_rows": True,
                     "overlay_text_colors": {"rate": "#ff0000", "total": "#00ff00", "name": "#0000ff"}})
    assert _near(_rows(window)[0].grab().toImage(), "#00ff00", 0, 340) == 0   # compact rows: no share


def test_the_target_lines_parts_in_their_own_look_and_its_time_to_kill_bar(qapp):
    meter = fight()
    target = meter["snapshot"]["current_target"]
    target.update(also_targets=["Lesser Atiel", "Spawn"], ttk_fraction=0.4, break_gauge={"pct": 62.4},
                  enrage={"enraged": False, "enrage_in": 95, "enrage_s": 300})
    shown = {"overlay_show_enemy_hp": True, "overlay_show_ttk": True, "overlay_show_break_gauge": True}
    window = _overlay(meter, **shown)
    assert window.target_text == "Atiel +2 (Lesser Atiel, Spawn)  ·  47.0%  ·  TTK 1m06s  ·  Enrage 1m35s  ·  Break 62%"
    # The card's own look (overlay.css ``#ov.ov-nm .ovtarget``): the others struck at .92em in their gold, the
    # time to kill at .86em in its tan, the enrage timer the same at 85%, the break in amber.
    assert '<span style="color:#c9a86a; font-size:11px; font-weight:600">+2</span>' in window.target.text()
    assert '<span style="color:#e3ad7f; font-size:10px; font-weight:600">TTK&nbsp;1m06s</span>' in window.target_line.text()
    assert 'color:rgba(227,173,127,0.85); font-weight:400">Enrage&nbsp;1m35s' in window.target_line.text()
    assert _text_colour(window.target_hp) == "#e7ecea" and window.target_hp.font().pixelSize() == 15   # 1.22em
    assert not window.ttk_bar.isHidden() and window.ttk_bar.fraction == pytest.approx(0.4)
    assert window.ttk_bar.color.name() == "#8fb3d0" and window.ttk_bar.height() == 3
    window.apply_ui({"overlay_width": 340, **shown, "overlay_ttk_color": "#ff40c0",
                     "overlay_text_colors": {"hp": "#ff6060", "ttk": "#ffa040", "also": "#ff60ff"},
                     "overlay_text_fonts": {"hp": {"scale": 150}}})
    assert _text_colour(window.target_hp) == "#ff6060" and window.target_hp.font().pixelSize() == 22   # at 150%
    assert '<span style="color:#ffa040; font-size:10px; font-weight:600">TTK&nbsp;1m06s</span>' in window.target_line.text()
    assert 'color:rgba(255,160,64,0.85); font-weight:400">Enrage&nbsp;1m35s' in window.target_line.text()
    assert '<span style="color:#ff60ff; font-size:11px; font-weight:600">+2</span>' in window.target.text()
    assert "Break&nbsp;62%" in window.target_line.text()
    assert window.ttk_bar.color.name() == "#ff40c0"
    for fraction in (None, float("nan"), True):                                  # no estimate: no bar
        target["ttk_fraction"] = fraction
        window.apply_meter(meter)
        assert window.ttk_bar.isHidden()
    target["ttk_fraction"] = 0.4
    window.apply_ui({"overlay_width": 340, "overlay_show_enemy_hp": True})       # the time to kill off: none
    assert window.ttk_bar.isHidden() and not window.hp.isHidden()


def test_the_dummy_parse_and_events_labels_take_the_labels_look(qapp):
    meter = fight()
    meter["snapshot"]["dummy_parse"] = {"duration": 45.4, "window_seconds": 60, "window_reached": True,
                                        "your_dps": 15_600, "target_dps": 45_700}
    window = _overlay(meter, overlay_text_colors={"label": "#60ff60"},
                      overlay_text_fonts={"label": {"weight": 800}})
    assert window.dummy_text == "Dummy parse 45s / 60s ✓ · You 15.60K/s · Total 45.70K/s"
    assert window.dummy.text().startswith('<span style="color:#60ff60; font-weight:800">Dummy parse</span> 45s')
    strip = MeterOverlay(None)
    strip._catalog = CATALOG
    strip.events_clock = lambda: utc(2026, 11, 20, 0, 50)
    strip.apply_ui({"overlay_width": 800, "event_region": "na-east", "overlay_text_colors": {"label": "#60ff60"}})
    assert strip.events.text().startswith('<span style="color:#60ff60; font-weight:600">Events</span> ')
    assert events.strip_html([], '<b>Events</b>') == "<b>Events</b> "


# ------------------------------------------------------------------ the effects
def test_settings_that_change_nothing_redraw_nothing(qapp, monkeypatch):
    ui = {"overlay_width": 340, "overlay_glow": True, "overlay_text_colors": {"rate": "#ff0000"}}
    window = _overlay(**{key: value for key, value in ui.items() if key != "overlay_width"})
    effects = [label.graphicsEffect() for label in window._text_labels()]
    told, looks = [], []
    monkeypatch.setattr(overlay.PlayerRow, "set_text_look", lambda row, look: told.append(look))
    monkeypatch.setattr(TextEffect, "set_look", lambda effect, look, shadow=None: looks.append(look))
    window.apply_ui(dict(ui))                                                     # the settings' poll, every 3 s
    assert told == [] and looks == []
    assert [label.graphicsEffect() for label in window._text_labels()] == effects   # each kept as it was
    window.apply_ui({**ui, "overlay_text_colors": {"rate": "#00ff00"}})
    assert len(told) == len(window.rows) and len(looks) == len(window._text_labels())


def test_the_effects_are_drawn_round_each_text(qapp):
    window = _overlay()
    chips = window._chip_labels()
    plain = [label for label in window._text_labels() if label not in chips]
    assert all(label.graphicsEffect() is None for label in plain)                 # none: plain text
    # The chips float over the game in every background, their text over the chips' shadow (``--nm-shadow``).
    assert all(label.graphicsEffect().shadow == CHIP_SHADOW for label in chips)
    assert chips[0].graphicsEffect().boundingRectFor(QRectF(0, 0, 10, 10)) == QRectF(-6, -6, 22, 22)
    window.apply_ui({"overlay_width": 340, "overlay_glow": True})
    effects = [label.graphicsEffect() for label in window._text_labels()]
    assert all(isinstance(effect, TextEffect) and effect.look is window.text_look for effect in effects)
    assert effects[0].boundingRectFor(QRectF(0, 0, 10, 10)) == QRectF(-10, -10, 30, 30)
    window.apply_ui({"overlay_width": 340, "overlay_glow": True, "overlay_text_halo": True})
    assert window.target.graphicsEffect() is effects[0]                         # kept, with the new look
    assert effects[0].boundingRectFor(QRectF(0, 0, 10, 10)) == QRectF(-16, -16, 42, 42)
    window.apply_ui({"overlay_width": 340})
    assert all(label.graphicsEffect() is None for label in plain)
    window.apply_ui({"overlay_width": 340, "overlay_bg_mode": "none"})           # nothing behind: the top parts too
    assert window.target.graphicsEffect().shadow == CHIP_SHADOW
    window.apply_ui({"overlay_width": 340})
    assert window.target.graphicsEffect() is None
    # Drawn: the outline in its colour round a label's text and a row's, a quarter of its strength as the web
    # overlay's 0.6 px stroke shows.
    card = QWidget()                                 # a label draws its text alone on a clear ground, as the overlay's
    card.setObjectName("card")
    card.setStyleSheet("QWidget#card { background: #1b202a; } QLabel { color: #ffffff; font-size: 16px; }")
    label = QLabel("Atiel", card)
    label.move(20, 10)
    plain = card.grab().toImage()
    effect = TextEffect(TextLook({"overlay_text_outline": True, "overlay_outline_color": "#ff0000"}), label)
    label.setGraphicsEffect(effect)
    assert _redder(card.grab().toImage(), plain) > 10
    effect.set_look(TextLook({}))
    assert _redder(card.grab().toImage(), plain) == 0
    plain = _rows(_overlay())[0].grab().toImage()
    outlined = _rows(_overlay(overlay_text_outline=True, overlay_outline_color="#ff0000"))[0].grab().toImage()
    assert _redder(outlined, plain) > 10


def test_the_colour_cycle_is_chromiums_hue_rotate():
    for colour, degrees, chromium in (("#ff0000", 180, "#006d6d"), ("#e8cf8e", 90, "#8ee6b7"),
                                      ("#3a86c8", 250, "#489223"), ("#e9e6df", 120, "#dfe8e7")):
        assert cycled(colour, degrees / 360 * 12).name() == chromium              # 12 s a whole turn
    assert cycled("#3a86c8", 0).name() == "#3a86c8" and cycled("#3a86c8", 12).name() == "#3a86c8"
    assert {cycled("#808080", seconds).name() for seconds in (1, 4, 9)} == {"#808080"}   # a grey stays grey


def test_the_sheen_crosses_the_names_twice_a_turn():
    room = QRectF(10, 0, 100, 22)

    def band(seconds):
        gradient = sheen_brush(room, QColor("#e9e6df"), seconds)
        return (gradient.start().x() + gradient.finalStop().x()) / 2

    assert band(0) == pytest.approx(160)               # beyond the names: they show in their own colour
    assert band(3.5 / 4) == pytest.approx(10)          # the band comes in at the left
    assert band(3.5 / 3) == pytest.approx(60)          # across the middle
    assert band(3.5 * 3 / 4) == pytest.approx(10)      # and again, half a turn on
    stops = sheen_brush(room, QColor("#e9e6df"), 1).stops()
    assert [round(at, 2) for at, _colour in stops] == [0, 0.42, 0.5, 0.58, 1]
    assert stops[2][1].getRgb() == (255, 255, 255, 235) and stops[0][1].name() == "#e9e6df"


def test_the_cycle_and_the_sheen_move_unless_held_still(qapp, monkeypatch):
    window = _overlay(overlay_color_cycle=True)
    assert window._anim_timer.isActive() and window._anim_timer.interval() == 50
    window._paint_moment(3.0)
    assert all(row.seconds == 3.0 for row in _rows(window))
    capture = window.tools["capture"]                                             # the toolbar turns through the hues
    assert capture.seconds == 3.0 and window.metric_chip.seconds == 3.0
    assert capture.tone == "#ff8585"                                              # the fight runs: the red stop
    assert capture.shown_colour().name() == cycled("#ff8585", 3.0).name() != "#ff8585"
    window.apply_ui({"overlay_width": 340, "overlay_color_cycle": True, "performance_mode": True})
    assert not window._anim_timer.isActive() and all(row.seconds is None for row in _rows(window))
    assert capture.seconds is None and capture.shown_colour().name() == "#ff8585"   # held still
    window.apply_ui({"overlay_width": 340, "overlay_text_retro": True})
    window._paint_moment(3.0)
    assert window._anim_timer.isActive() and capture.seconds is None             # the sheen: the names alone
    window.apply_ui({"overlay_width": 340, "overlay_text_retro": True, "overlay_color_cycle": True})
    window._paint_moment(3.0)                     # both: the sheen's animation takes the cycle's place, as on the web
    assert capture.seconds is None and all(row.seconds == 3.0 for row in _rows(window))
    monkeypatch.setattr(overlay, "reduced_motion", lambda: True)                  # the system asks for less motion
    window.apply_ui({"overlay_width": 340, "overlay_text_retro": True})
    assert not window._anim_timer.isActive()
    window.apply_ui({"overlay_width": 340})
    assert not window._anim_timer.isActive()


def test_the_sheen_paints_every_part_of_the_names_in_their_colour(qapp):
    look = {"overlay_class_color_names": True, "overlay_text_colors": {"name": "#0000ff"}}
    window = _overlay(**look)
    image = _rows(window)[0].grab().toImage()
    assert _near(image, "#0000ff", 0, 170) == 0                                   # the class's colour wins
    window.apply_ui({"overlay_width": 340, "overlay_text_retro": True, **look})
    image = _rows(window)[0].grab().toImage()
    assert _near(image, "#0000ff", 0, 170) > 3                                    # the names' own colour, as on the web


# ------------------------------------------------------------------ the background image
def test_the_background_image_lies_under_the_readings(qapp):
    app = PictureApp(picture("#ffffff"))
    window = _overlay(api=app, overlay_bg_set=True, overlay_bg_darken=0)
    settle(lambda: window.card.background is not None)
    assert app.asked() == 1

    def edge(y):                                                                  # the card's right margin
        image = window.card.grab().toImage()
        return image.pixelColor(image.width() - 4, y).getRgb()[:3]

    middle = window.card.height() // 2
    assert edge(middle) == (255, 255, 255)
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True, "overlay_bg_darken": 50})
    assert edge(middle) in {(127, 127, 127), (128, 128, 128)}                     # darkened by half
    assert app.asked() == 1                                                       # read once
    assert (window.card.bg_opacity, window.card.bg_zoom, window.card.bg_darken) == (1.0, 1.0, 0.5)
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True, "overlay_bg_zoom": 999, "overlay_bg_opacity": -1})
    assert (window.card.bg_opacity, window.card.bg_zoom, window.card.bg_darken) == (1.0, 1.0, 0.2)   # the defaults
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True, "overlay_bg_mode": "none"})
    assert window.card.background is None                                         # nothing behind: no image
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True, "overlay_bg_mode": "top", "overlay_bg_darken": 0})
    first = _rows(window)[0]
    assert edge(24) == (255, 255, 255) and edge(first.mapTo(window.card, first.rect().center()).y()) != (255, 255, 255)
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True, "overlay_bg_opacity": 0})
    assert window.card.background is None
    window.apply_ui({"overlay_width": 340, "overlay_bg_set": True})               # on again: read afresh
    settle(lambda: app.asked() == 2 and window.card.background is not None)
    window.refresh()                                                              # Open overlay: a new upload shows
    settle(lambda: app.asked() == 3)
    assert MeterOverlay(None).card.background is None                             # none set: none asked for


def test_the_image_is_read_from_the_app_as_it_comes(qapp):
    """Through the app's own local API: ``/overlay-background`` answers the image itself, not JSON."""
    served = picture("#ffffff")
    asked = []

    class App(BaseHTTPRequestHandler):
        def do_GET(self):
            asked.append(self.path)
            image = self.path.startswith("/overlay-background")
            body = served if image else b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "image/png" if image else "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    app = ThreadingHTTPServer(("127.0.0.1", 0), App)
    threading.Thread(target=app.serve_forever, daemon=True).start()
    try:
        api = AppApi(f"http://127.0.0.1:{app.server_address[1]}")
        assert api.get_bytes("/overlay-background") == served
        window = _overlay(api=api, overlay_bg_set=True)
        settle(lambda: window.card.background is not None)
        assert window.card.background.size().toTuple() == (40, 20)
        assert any(path.startswith("/overlay-background?v=") for path in asked)
    finally:
        app.shutdown()


def test_the_image_sits_centred_at_its_zoom():
    card = QRectF(0, 0, 340, 200)
    assert background_rect(card, 40, 20, 1.0) == QRectF(0, 15, 340, 170)
    assert background_rect(card, 40, 20, 0.5) == QRectF(85, 57.5, 170, 85)
    assert background_rect(card, 40, 20, 2.0) == QRectF(-170, -70, 680, 340)


def test_auto_contrast_picks_the_texts_colour_for_the_image(qapp):
    white = PictureApp(picture("#ffffff"))
    ui = {"overlay_width": 340, "overlay_bg_set": True, "overlay_text_autocontrast": "luminance",
          "overlay_text_colors": {"header": "#9be7a0"}}
    window = _overlay(api=white, **{key: value for key, value in ui.items() if key != "overlay_width"},
                      overlay_bg_darken=0)
    settle(lambda: window.text_look.contrast is not None)
    assert window.text_look.contrast == "#0a0e16"                                 # dark over a light image
    assert _text_colour(window.target) == "#0a0e16" and window.ping.parts[1].runs[0][2] == "#0a0e16"
    assert window.tools["lock"].colour == "#0a0e16"                               # the toolbar's colour too
    assert all(row.text_look.contrast == "#0a0e16" for row in _rows(window))     # read after the rows: theirs too
    window.apply_ui({**ui, "overlay_bg_darken": 90})                              # darkened, light text
    assert window.text_look.contrast == "#f4f1ea" and _text_colour(window.target) == "#f4f1ea"
    window.apply_ui({**ui, "overlay_bg_mode": "none", "overlay_bg_darken": 0})    # no image shown: still by it
    assert window.card.background is None and window.text_look.contrast == "#0a0e16"
    window.apply_ui({**ui, "overlay_text_autocontrast": "blend"})                 # white, blended with what is behind
    assert window.text_look.contrast == "#ffffff" and window.text_look.blend
    assert all(isinstance(label.graphicsEffect(), TextEffect) for label in window._text_labels())
    window.apply_ui({**ui, "overlay_bg_set": False})                              # no image: the user's colours
    assert window.text_look.contrast is None and window.tools["lock"].colour == "#9be7a0"
    assert window.target.graphicsEffect() is None
    assert contrast_colour(QImage(picture("#000000")), 0) == "#f4f1ea"
    assert contrast_colour(QImage.fromData(picture("#ffffff")), 0.5) == "#0a0e16"   # 1 × 0.5 is past 0.179
    missing = PictureApp(None)                                                    # none can be read
    window = _overlay(api=missing, **{key: value for key, value in ui.items() if key != "overlay_width"})
    settle(lambda: window.text_look.contrast is not None)
    assert window.text_look.contrast == "#f4f1ea" and window.card.background is None   # light, as the web overlay
    window.apply_ui(ui)                                                           # asked again with the settings
    settle(lambda: missing.asked() == 2)


# ------------------------------------------------------------------ resizing
def test_the_grips_drag_the_size_and_keep_it(qapp):
    app = FakeApp(fight())
    window = _overlay(api=app)
    assert all(grip.isHidden() for grip in window.grips.values())                # off unless the setting is on
    window.apply_ui({"overlay_width": 340, "overlay_resizable": True})
    window.show()
    QCoreApplication.processEvents()
    right, bottom, corner = (window.grips[edge] for edge in ("right", "bottom", "corner"))
    height = window.height()
    assert right.geometry().getRect() == (328, 4, 12, height - 20)
    assert bottom.geometry().getRect() == (4, height - 12, 320, 12)
    assert corner.geometry().getRect() == (324, height - 16, 16, 16)
    rects = window.host.control_rects()                                           # live through click-through
    for grip in (right, bottom, corner):
        place = grip.geometry()
        assert (place.x(), place.y(), place.x() + place.width(), place.y() + place.height()) in rects
    QTest.mousePress(right, Qt.LeftButton, Qt.NoModifier, QPoint(6, 20))
    QTest.mouseMove(right, QPoint(66, 20))
    QTest.mouseRelease(right, Qt.LeftButton, Qt.NoModifier, QPoint(6, 20))
    assert window.width() == 400 and right.geometry().x() == 388
    settle(lambda: ("POST", "/api/ui", {"overlay_width": 400}) in app.calls)
    window.apply_ui({"overlay_width": 340, "overlay_resizable": True})            # the drag's width stays
    assert window.width() == 400
    QTest.mousePress(right, Qt.LeftButton, Qt.NoModifier, QPoint(6, 20))
    QTest.mouseMove(right, QPoint(906, 20))
    QTest.mouseRelease(right, Qt.LeftButton, Qt.NoModifier, QPoint(6, 20))
    assert window.width() == 800                                                  # 800 at the most
    start = window.card.height()
    QTest.mousePress(bottom, Qt.LeftButton, Qt.NoModifier, QPoint(20, 6))
    QTest.mouseMove(bottom, QPoint(20, 156))
    QTest.mouseRelease(bottom, Qt.LeftButton, Qt.NoModifier, QPoint(20, 6))
    assert window.card.minimumHeight() == start + 150 and window.height() == start + 150
    settle(lambda: ("POST", "/api/ui", {"overlay_height": start + 150}) in app.calls)
    laid_out_apart(window)
    QTest.mousePress(corner, Qt.LeftButton, Qt.NoModifier, QPoint(8, 8))
    QTest.mouseMove(corner, QPoint(-892, -892))
    QTest.mouseRelease(corner, Qt.LeftButton, Qt.NoModifier, QPoint(8, 8))
    assert window.width() == 260 and window.card.minimumHeight() == 70            # the least: 260 by 70
    settle(lambda: ("POST", "/api/ui", {"overlay_width": 260, "overlay_height": 70}) in app.calls)


def test_overlay_height_sets_the_cards_least_height(qapp):
    window = _overlay(overlay_height=420)
    assert window.card.minimumHeight() == 420 and window.height() == 420
    laid_out_apart(window)                                                        # the room left under the readings
    window.apply_ui({"overlay_width": 340, "overlay_height": 0})                  # 0: as tall as the readings
    assert window.card.minimumHeight() == 0 and window.height() < 420
    window.apply_ui({"overlay_width": 340, "overlay_height": 900})                # out of range: the default
    assert window.card.minimumHeight() == 0


def test_a_large_font_wraps_the_toolbar_and_the_target_line(qapp):
    meter = fight()
    meter["snapshot"]["current_target"].update(break_gauge={"pct": 62.4},
                                               enrage={"enraged": False, "enrage_in": 95, "enrage_s": 300})
    window = _overlay(meter, overlay_width=260, overlay_font_scale=160, overlay_show_enemy_hp=True,
                      overlay_show_ttk=True, overlay_show_break_gauge=True)
    window.show()
    QCoreApplication.processEvents()
    buttons = [button for button in window.tools.values() if not button.isHidden()]
    places = [button.geometry() for button in buttons]
    assert all(window.toolbar.rect().contains(place) for place in places)         # each whole, in the toolbar
    assert not any(one.intersects(other) for index, one in enumerate(places) for other in places[index + 1:])
    assert len({place.top() for place in places}) > 1                             # on more than one line
    assert all(button.width() >= button.sizeHint().width() for button in buttons)
    assert max(place.right() for place in places) == window.toolbar.width() - 4  # each line to the right
    line = window.target_line                                                   # the time to kill wraps too
    assert line.height() > 1.5 * line.fontMetrics().height()
    laid_out_apart(window)
