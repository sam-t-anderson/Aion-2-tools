"""The native overlay's eighth part (0.2.421): its player rows and target card as the web overlay's compact layout
draws them (overlay.css ``#ov.ov-nm``), off screen.

The rows: the class's emblem from the app's bundled art (your row's with a green dot), the rank in gold, silver and
bronze, the rate in whole digits and the share to a tenth, the combat-power chip and the share giving way in a
narrow overlay, the row effects for your row and the top row, and long names scrolling under the pointer. The target
card: the boss's portrait or the target mark, the name with the others struck, the HP in damage units and to a tenth,
the bars inside the card, and the time to kill, the enrage timer and the break under them. No check hangs on the
width of a font.
"""
import io
import json
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QHoverEvent, QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import theme  # noqa: E402
from aion2calc.gui.overlay import MeterOverlay, fmt_ttk, hp_tip, rate_text  # noqa: E402
from aion2calc.gui.pictures import CLASS_ART, Pictures, decoded  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, laid_out_apart, settle  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "aion2calc" / "app" / "static"
ASSETS = json.loads((STATIC / "game-assets.json").read_text(encoding="utf-8"))


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


class AssetApp(FakeApp):
    """The app's local API with its bundled art: the asset map and each picture, read from the package."""

    def __init__(self, meter=None):
        super().__init__(meter or fight())

    def get(self, path):
        if path == "/static/game-assets.json":
            self.calls.append(("GET", path, None))
            return ASSETS
        return super().get(path)

    def get_bytes(self, path):
        self.calls.append(("GET", path, None))
        file = STATIC / path.removeprefix("/static/")
        if not file.is_file():
            raise urllib.error.HTTPError("http://127.0.0.1" + path, 404, "Not Found", {}, io.BytesIO(b""))
        return file.read_bytes()


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _with_art(window):
    """The classes' bundled emblems handed over as the app gives them (no app: the tests' windows have none)."""
    window.pictures.read_map(ASSETS)
    for file in window.pictures.classes.values():
        window.pictures.keep(file, QPixmap(str(STATIC / file)))
    return window


def _hover(row, enter: bool) -> None:
    point = QPointF(10, 10)
    row.event(QHoverEvent(QEvent.HoverEnter if enter else QEvent.HoverLeave, point, point, point))


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def _near(image: QImage, colour: str, box: QRectF, reach: int = 40) -> int:
    want, count = QColor(colour), 0
    for y in range(max(0, int(box.top())), min(image.height(), int(box.bottom()))):
        for x in range(max(0, int(box.left())), min(image.width(), int(box.right()))):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > 150:
                count += 1
    return count


def _shot(window, widget) -> QImage:
    """``widget`` as the window draws it, over the card (a child drawn alone has nothing behind it)."""
    window.show()
    QCoreApplication.processEvents()
    image = window.grab().toImage()
    corner = widget.mapTo(window, widget.rect().topLeft())
    return image.copy(corner.x(), corner.y(), widget.width(), widget.height())


# ------------------------------------------------------------------ the numbers
def test_the_rate_in_whole_digits_and_the_share_to_a_tenth():
    assert rate_text(23_234.4) == "23,234" and rate_text(2.5) == "3"            # Math.round: a half goes up
    assert rate_text(9_999_999.4) == "9,999,999" and rate_text(12_500_000) == "12.50M"   # from ten million, kfmt
    assert theme.fixed(51.2, 1) == "51.2" and theme.fixed(14.66, 1) == "14.7"
    assert (fmt_ttk(45.4), fmt_ttk(66), fmt_ttk(3725), fmt_ttk(None)) == ("45s", "1m06s", "1h2m", "0s")


def test_the_digits_follow_the_systems_language(monkeypatch):
    from PySide6.QtCore import QLocale
    theme._digit_locale.cache_clear()
    try:
        monkeypatch.setattr(QLocale, "uiLanguages", lambda self: ["de-DE", "de"])
        assert theme.digits(1_234_567) == "1.234.567"
        theme._digit_locale.cache_clear()
        monkeypatch.setattr(QLocale, "uiLanguages", lambda self: ["C"])
        assert theme.digits(1_234_567) == "1,234,567"                           # none named: as in English
    finally:
        theme._digit_locale.cache_clear()


def test_the_hp_tooltip_says_where_its_numbers_come_from():
    measured = {"effective_current_hp": 1_200_000, "effective_max_hp": 2_500_000, "effective_hp_samples": 1,
                "damage": 3_420_000}
    assert hp_tip(measured) == ("HP ≈ 1.20M / 2.50M in damage units — calibrated from 1 community kill on this "
                                "game build. Effective HP dealt so far ≈ 3.42M.")
    raw = {"damage": 3_420_000, "current_hp": 61_000_000, "max_hp": 130_000_000}
    assert hp_tip(raw) == ("Effective HP so far ≈ 3.42M (total recorded damage dealt to it). Game internal HP "
                           "61.00M / 130.00M is on a larger, different scale than damage, so it is shown here as a "
                           "percentage.")


# ------------------------------------------------------------------ the pictures
def test_the_pictures_are_read_once_from_the_apps_bundled_art(qapp):
    app = AssetApp()
    pictures = Pictures(app)
    seen = []
    pictures.changed.connect(lambda: seen.append(1))
    assert pictures.emblem("Sorcerer") is None                                  # asked for: the map first
    settle(lambda: pictures.classes)
    assert set(pictures.classes) == {"assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer",
                                     "spiritmaster", "templar"}                  # no art for the Brawler
    assert pictures.classes["sorcerer"] == ASSETS["assets"][CLASS_ART.format("sorcerer")]
    assert len(pictures.npcs) == len(ASSETS["npc_portraits"])
    assert pictures.emblem("sorcerer") is None
    settle(lambda: pictures.emblem("sorcerer") is not None)
    emblem = pictures.emblem("SORCERER")
    assert emblem.width() == 256 and seen
    assert pictures.emblem("brawler") is None and pictures.portrait(None) is None
    asked = [path for _method, path, _body in app.calls]
    assert asked.count("/static/game-assets.json") == 1 and asked.count("/static/" + pictures.classes["sorcerer"]) == 1
    assert pictures.portrait(2340601) is None                                   # Atiel's portrait, read too
    settle(lambda: pictures.portrait("2340601") is not None)
    pictures.stop()


def test_a_picture_neither_reader_takes_is_none():
    webp = (STATIC / ASSETS["assets"][CLASS_ART.format("cleric")]).read_bytes()
    assert decoded(webp).size().toTuple() == (256, 256)
    assert decoded(b"not a picture").isNull() and decoded(b"").isNull()


# ------------------------------------------------------------------ the rows
def test_the_rows_draw_the_compact_layouts_parts(qapp):
    window = _with_art(_overlay(overlay_rank_numbers=True))
    rows = _rows(window)
    assert [(row.rate, row.share) for row in rows] == [("23,400/s", "51.2%"), ("15,600/s", "34.1%"),
                                                       ("6,700/s", "14.7%")]
    assert all(row.height() == 28 for row in rows)                              # the row height and 6
    assert [row.label() for row in rows] == ["1. Seraphel", "2. Nyxara  123.5K", "3. Velmira"]
    assert all(row.emblem is not None and row.emblem.width() == 256 for row in rows)
    image = _shot(window, rows[1])                                              # yours: Nyxara
    assert _near(image, "#3ddc84", QRectF(0, 0, 80, 28)) > 6                    # the green dot by the emblem
    assert _near(_shot(window, rows[0]), "#3ddc84", QRectF(0, 0, 80, 28)) == 0
    for row, podium in zip(rows, ("#f2c84b", "#cfd4dc", "#d08a52")):            # gold, silver and bronze
        assert _near(_shot(window, row), podium, QRectF(0, 0, 26, 28), 30) > 3
    window.apply_ui({"overlay_width": 340, "overlay_highlight_me": True, "overlay_show_deaths": True})
    meter = fight()
    meter["snapshot"]["players"][2]["dead"] = True
    window.apply_meter(meter)
    rows = _rows(window)
    assert rows[1].label() == "Nyxara  123.5K  ME" and rows[2].label() == "Velmira  DEAD"
    laid_out_apart(window)


def test_the_chip_and_the_share_give_way_in_a_narrow_overlay(qapp):
    wide = _overlay(overlay_width=340)
    narrow = _overlay(overlay_width=260)
    teal = "#63d3e6"                                                            # the combat-power chip
    assert _near(_shot(wide, _rows(wide)[1]), teal, QRectF(0, 0, 220, 28), 30) > 4
    assert _near(_shot(narrow, _rows(narrow)[1]), teal, QRectF(0, 0, 200, 28), 30) == 0   # under 26.5em: none
    gold = "#f1d27c"                                                            # the share
    assert _near(_shot(narrow, _rows(narrow)[0]), gold, QRectF(150, 0, 90, 28), 30) > 4   # 240 px: still room
    tiny = _overlay(overlay_width=260, overlay_font_scale=160)                  # 19 px text: under 20em
    assert _near(_shot(tiny, _rows(tiny)[0]), gold, QRectF(0, 0, 240, 28), 30) == 0
    compact = _overlay(overlay_compact_rows=True)
    assert _near(_shot(compact, _rows(compact)[0]), gold, QRectF(0, 0, 320, 28), 30) == 0


@pytest.mark.parametrize("cosmetic", ["gold", "rainbow", "ember", "frost", "aether", "starlight"])
def test_each_row_effect_marks_your_row_and_moves(qapp, cosmetic):
    window = _overlay(overlay_me_cosmetic=cosmetic)
    rows = _rows(window)
    assert [row.cosmetic for row in rows] == [None, cosmetic, None]             # yours: Nyxara
    assert window._anim_timer.isActive()
    base = _overlay()
    plain = _shot(base, _rows(base)[1])
    window._anim_timer.stop()
    window._paint_moment(0.4)
    early = _shot(window, rows[1])
    window._paint_moment(1.3)
    later = _shot(window, rows[1])
    assert early != plain                                                       # drawn
    assert early != later                                                       # and moving
    window.apply_ui({"overlay_width": 340, "overlay_me_cosmetic": cosmetic, "performance_mode": True})
    assert not window._anim_timer.isActive() and not rows[1].moving             # held still


def test_the_top_rows_effect_and_yours_on_the_same_row(qapp):
    window = _overlay(fight(local_name="Seraphel"), overlay_top_cosmetic="frost", overlay_me_cosmetic="gold")
    assert [row.cosmetic for row in _rows(window)] == ["gold", None, None]      # yours wins on the top row
    window = _overlay(overlay_top_cosmetic="frost")
    assert [row.cosmetic for row in _rows(window)] == ["frost", None, None]
    window.apply_ui({"overlay_width": 340, "overlay_top_cosmetic": "sparkles"})  # no such effect
    assert [row.cosmetic for row in _rows(window)] == [None, None, None] and not window._anim_timer.isActive()


def test_a_long_name_scrolls_under_the_pointer(qapp):
    meter = fight()
    meter["snapshot"]["players"][0]["name"] = "Seraphelle of the Endless Burning Skies"
    window = _overlay(meter, overlay_long_names_scroll=True)
    row = _rows(window)[0]
    window.show()
    QCoreApplication.processEvents()
    assert row._cut                                                             # cut short with "…"
    _hover(row, True)
    assert row._scroll.isActive()
    row._scroll_from = time.monotonic() - 0.3                                   # 15% of 4 s: still
    assert row._scrolled(300) == 0
    row._scroll_from = time.monotonic() - 4.0                                   # the end: 60 px in
    assert row._scrolled(300) == pytest.approx(-240, abs=1)
    row._scroll_from = time.monotonic() - 8.0                                   # and back
    assert row._scrolled(300) == pytest.approx(0, abs=1)
    row._scroll_from = time.monotonic() - 2.3                                   # halfway along: (2.3/4 - .15)/.85
    assert row._scrolled(300) == pytest.approx(-240 * (0.575 - 0.15) / 0.85, abs=1)
    first = _shot(window, row)
    row._scroll_from = time.monotonic() - 4.0
    assert _shot(window, row) != first
    _hover(row, False)
    assert not row._scroll.isActive() and row._scroll_from is None
    short = _rows(window)[1]                                                    # Nyxara fits: nothing to scroll
    _hover(short, True)
    _shot(window, short)
    assert not short._cut and not short._scroll.isActive()
    window.apply_ui({"overlay_width": 340, "overlay_long_names_scroll": False})
    _hover(row, True)
    assert not row._scroll.isActive()                                           # the setting off


# ------------------------------------------------------------------ the target card
def test_the_target_card_shows_the_bosss_portrait_or_the_mark(qapp):
    meter = fight()
    target = meter["snapshot"]["current_target"]
    target.update(effective_current_hp=1_200_000, effective_max_hp=2_500_000, effective_hp_samples=3)
    window = _overlay(meter, api=AssetApp(meter), overlay_show_enemy_hp=True)
    settle(lambda: window.portrait.picture is not None)                         # Atiel's, from the app
    assert not window.portrait.picture.isNull()
    marked = _overlay(fight(), overlay_show_enemy_hp=True)                       # no art: the target mark
    assert marked.portrait.picture is None
    assert _near(_shot(marked, marked.portrait), "#8b95a3", QRectF(0, 0, 34, 34), 30) > 20
    assert window.target_nums.text() == "1.2M / 2.5M" and not window.target_nums.isHidden()
    assert window.target_hp.text() == "47.0%" and window.target_nums.toolTip().startswith("HP ≈ 1.20M / 2.50M")
    narrow = _overlay(meter, overlay_width=260, overlay_show_enemy_hp=True)     # under 24em: the numbers step aside
    assert narrow.target_nums.isHidden() and not narrow.target_hp.isHidden()
    laid_out_apart(window)


def test_the_target_cards_name_keeps_the_count_and_gives_the_others_way(qapp):
    meter = fight()
    meter["snapshot"]["current_target"]["also_targets"] = ["Lesser Atiel of the Shattered Abyssal Gate"] * 3
    window = _overlay(meter, overlay_width=260)
    text = window.target.text()
    assert ">+3</span>" in text and "…" in text and ">Atiel</span>" in text      # the names cut, the count whole
    assert window.target_text.startswith("Atiel +3 (Lesser Atiel")


def test_the_target_cards_line_late_enrage_and_broken_gauge(qapp):
    meter = fight()
    target = meter["snapshot"]["current_target"]
    target.update(enrage={"enraged": False, "enrage_in": 40, "enrage_s": 300, "before_kill": True, "measured": True},
                  break_gauge={"pct": 3})
    window = _overlay(meter, overlay_show_ttk=True, overlay_show_break_gauge=True)
    line = window.target_line.text()
    assert 'color:rgba(255,107,107,1.00); font-weight:700">Enrage&nbsp;40s' in line   # late: red
    assert 'color:#f0c36a; font-weight:700; letter-spacing:0.4px">BROKEN' in line
    assert window.target_line.toolTip() == (
        "This boss enrages 5m00s after the pull (seen in recorded fights); at this pace the kill takes longer than "
        "that\nThe break gauge is empty: the enemy is broken (staggered) and takes more damage until it refills")
    assert window.gauge.broken and window.gauge.shown() == 1.0
    stripes = _shot(window, window.gauge)
    assert _near(stripes, "#f0c36a", QRectF(0, 0, 200, 4), 20) > 4 and _near(stripes, "#b5832e", QRectF(0, 0, 200, 4), 20) > 4
    target["enrage"] = {"enraged": True, "enrage_s": 300}
    window.apply_meter(meter)
    assert "ENRAGED" in window.target_line.text() and window.target_line.toolTip().startswith(
        "Past this boss's 5m00s enrage timer")
    window.apply_ui({"overlay_width": 340})                                     # neither on: no line, no bars
    assert window.target_line.isHidden() and window.target_bars.isHidden() and not window.target_card.isHidden()


def test_the_hp_bar_darkens_toward_its_start(qapp):
    window = _overlay(overlay_show_enemy_hp=True, overlay_hp_color="#ff0000")
    image = _shot(window, window.hp)
    start, end = image.pixelColor(3, 3), image.pixelColor(int(window.hp.width() * 0.47) - 3, 3)
    assert end.red() > start.red() + 60                                         # from 38% of the colour to it
