"""The native overlay's twelfth part (0.2.425): the counters across the top of the card as the web overlay's compact
layout draws them (overlay.js ``odyleLine``, ``shugoLine``, ``nightmareLine``, ``weeklyLine``, ``compactLines``),
off screen: each with its icon, in full words where they all fit on one line, else their counts, larger, the bonus in
teal.
"""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.look import CHIP_SHADOW  # noqa: E402
from aion2calc.gui.overlay import COUNTER_TIPS, MeterOverlay, counter_items  # noqa: E402
from aion2calc.gui.pictures import ODYLE_ICON  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import laid_out_apart  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "aion2calc" / "app" / "static"
ASSETS = json.loads((STATIC / "game-assets.json").read_text(encoding="utf-8"))
COUNTERS = {"odyle": {"regular": 1_200, "bonus": 300}, "shugo_keys": {"regular": 12, "bonus": 4},
            "nightmare_tickets": {"regular": 9, "bonus": 0},
            "weekly_runs": {"regular": 3, "bonus": 1, "zone": "Vakron Sky Island", "difficulty": "hard"}}


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


def _meter(**counters):
    meter = fight()
    meter["snapshot"].update(counters)
    return meter


def _overlay(meter, art=True, **ui):
    window = MeterOverlay()
    if art:                                       # the app's bundled art, as it hands it over
        window.pictures.read_map(ASSETS)
        file = window.pictures.items[ODYLE_ICON]
        window.pictures.keep(file, QPixmap(str(STATIC / file)))
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter)
    return window


def _near(image: QImage, colour: str, box: QRectF, reach: int = 40) -> int:
    want, count = QColor(colour), 0
    for y in range(max(0, int(box.top())), min(image.height(), int(box.bottom()))):
        for x in range(max(0, int(box.left())), min(image.width(), int(box.right()))):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > 150:
                count += 1
    return count


def test_the_counters_in_their_order_with_their_counts():
    assert counter_items(dict(COUNTERS)) == [
        ("odyle", "Odyle Energy 1,500 (1,200 + 300 bonus)", 1_200, 300),
        ("shugo_keys", "Shugo Keys 16 (12 + 4 bonus)", 12, 4),
        ("nightmare_tickets", "Nightmare Tickets 9", 9, 0),
        ("weekly_runs", "Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)", 3, 1)]
    assert counter_items({}) == []


def test_in_full_where_they_fit_else_their_counts_larger_the_bonus_in_teal(qapp):
    window = _overlay(_meter(odyle=COUNTERS["odyle"]), overlay_width=800)
    (part,) = window.lines.parts
    assert window.lines.text() == "Odyle Energy 1,500 (1,200 + 300 bonus)"     # room for the words
    (text, made, colour), = part.runs
    assert made.pixelSize() == 10 and int(made.weight()) == 600 and colour == "#e9edf1"
    assert part.mark.key[0] == "picture" and part.size.width() == pytest.approx(14)   # the item, 1.4em
    window = _overlay(_meter(**COUNTERS))
    assert window.lines.text() == "1,200(+300) 12(+4) 9 3(+1)"                   # no room: the counts
    first = window.lines.parts[0]
    assert [(text, int(made.weight()), colour) for text, made, colour in first.runs] == [
        ("1,200", 700, "#e9edf1"), ("(+300)", 600, "#63d3e6")]
    assert first.runs[0][1].pixelSize() == 12
    assert [part.mark.key for part in window.lines.parts[1:]] == [
        ("icon", "key", "#e8cf8e"), ("icon", "ticket", "#e8cf8e"), ("icon", "runs", "#e8cf8e")]
    assert window.lines.parts[3].tip == ("Vakron Sky Island · hard: 4 runs left this week (3 + 1 bonus)\n"
                                         + COUNTER_TIPS["weekly_runs"])


def test_the_fit_is_the_web_overlays(qapp):
    """``compactLines``: the full words' widths and 10 px for each counter, against the counters' room."""
    window = _overlay(_meter(odyle=COUNTERS["odyle"], shugo_keys=COUNTERS["shugo_keys"]), overlay_width=800)
    window.show()
    QCoreApplication.processEvents()
    full = [part.measure().width() for part in window.lines.parts]
    need = sum(full) + 10 * len(full)
    margins = window.lines_part.layout().contentsMargins()
    room = window._content_width() - margins.left() - margins.right()
    assert need <= room + 1 and window.lines.text().startswith("Odyle Energy")
    narrow = _overlay(_meter(odyle=COUNTERS["odyle"], shugo_keys=COUNTERS["shugo_keys"]),
                      overlay_width=int(need + 18 + 4 - 20))        # a little short of the room they need
    assert narrow.lines.text() == "1,200(+300) 12(+4)"


def test_the_counters_take_the_pings_look_and_draw_their_icons(qapp):
    window = _overlay(_meter(**COUNTERS), overlay_text_colors={"ping": "#60ffff"},
                      overlay_text_fonts={"ping": {"scale": 120}}, overlay_font_scale=150)
    first = window.lines.parts[0].runs[0]
    assert first[2] == "#60ffff" and first[1].pixelSize() == round(12 * 1.5 * 1.2)
    window.show()
    QCoreApplication.processEvents()
    image = window.lines.grab().toImage()
    assert _near(image, "#e8cf8e", QRectF(0, 0, image.width(), image.height()), 30) > 20   # the gold icons
    laid_out_apart(window)
    bare = _overlay(_meter(**COUNTERS), art=False)                  # no art: the Odyle count alone
    assert bare.lines.parts[0].mark is None and bare.lines.text().startswith("1,200(+300)")


def test_over_the_game_the_counters_lie_over_the_chips_shadow(qapp):
    window = _overlay(_meter(**COUNTERS))
    assert window.lines.shadow is None                                   # on the card: no shadow
    window.apply_ui({"overlay_width": 340, "overlay_bg_mode": "none"})
    assert window.lines.shadow == CHIP_SHADOW
    window.apply_ui({"overlay_width": 340, "overlay_only_in_combat": True})
    idle = _meter(**COUNTERS)
    idle["running"] = False
    window.apply_meter(idle)
    assert window.lines.isHidden()                                       # folded away between fights
