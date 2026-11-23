"""The native interface's pictures sharp on a scaled screen (0.2.507): a picture is drawn at as many pixels as the
screen gives the size it is shown at (Windows' display scaling, or the app's larger text), where one scaled to the
size alone was blown up blurred. Off screen; the scaled screen is a process of its own at twice the pixels.
"""
import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import pictures  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _halves(width: int, height: int) -> QPixmap:
    """A picture red on its left half and blue on its right."""
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor("blue"))
    painter = QPainter(image)
    painter.fillRect(0, 0, width // 2, height, QColor("red"))
    painter.end()
    return QPixmap.fromImage(image)


def test_a_picture_sized_for_its_screen(qapp):
    wide = _halves(100, 50)
    sharp = pictures.sized(wide, 30, 30, 2.0)
    assert (sharp.width(), sharp.height(), sharp.devicePixelRatio()) == (60, 30, 2.0)
    assert sharp.deviceIndependentSize().toTuple() == (30.0, 15.0)             # the size it is shown at
    plain = pictures.sized(wide, 30, 30)
    assert (plain.width(), plain.height(), plain.devicePixelRatio()) == (30, 15, 1.0)   # as before, at one to one
    cover = pictures.sized(wide, 30, 30, 2.0, Qt.KeepAspectRatioByExpanding)
    assert (cover.width(), cover.height()) == (120, 60)
    for ratio in (0, -1, None, "2"):                                           # no ratio Qt gives: one to one
        assert pictures.sized(wide, 30, 30, ratio).devicePixelRatio() == 1.0
    kept = pictures.sized(wide, 30, 30, 2.0)
    assert pictures.sized(kept, 30, 15, 2.0) is kept                           # drawn for it already: no copy


def test_a_cover_drawn_at_the_screens_own_pixels(qapp):
    canvas = QImage(100, 100, QImage.Format_ARGB32)                            # 50 x 50 at two pixels to each
    canvas.setDevicePixelRatio(2.0)
    canvas.fill(QColor("black"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    pictures.draw_cover(painter, QRectF(0, 0, 50, 50), _halves(200, 100))     # its middle square, both halves
    painter.end()
    assert canvas.pixelColor(20, 50).name() == "#ff0000" and canvas.pixelColor(80, 50).name() == "#0000ff"
    assert canvas.pixelColor(2, 2).name() == "#ff0000" and canvas.pixelColor(97, 97).name() == "#0000ff"   # filled
    empty = QImage(10, 10, QImage.Format_ARGB32)
    empty.fill(QColor("black"))
    painter = QPainter(empty)
    pictures.draw_cover(painter, QRectF(0, 0, 10, 10), QPixmap())             # none: nothing drawn
    painter.end()
    assert empty.pixelColor(5, 5).name() == "#000000"


SCALED = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, {root!r})
    from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication([])
    from aion2calc.gui import theme
    theme.apply_look("dark")
    art = QPixmap(64, 64)
    art.fill(QColor("red"))
    shown = {{}}

    def kept(label):
        pixmap = label.pixmap()
        return [pixmap.devicePixelRatio(), pixmap.width(), pixmap.height()]

    from aion2calc.gui.header import Header
    header = Header()
    shown["header logo"] = kept(next(l for l in header.findChildren(QLabel) if not l.pixmap().isNull()))
    from aion2calc.gui import crafting_page, builds_page, combat_featured_page
    item = crafting_page.Picture(36)
    item.show_pixmap(art)
    shown["crafting item"] = kept(item)
    built = builds_page.Picture("https://example.invalid/a.png", 48)
    built.show_picture(art)
    shown["builds picture"] = kept(built)
    shown["featured portrait"] = kept(combat_featured_page._Painted(art, 40))
    from aion2calc.gui.combat_analysis_page import ParseCard
    card = ParseCard({{"name": "TestSorc", "cls": "sorcerer", "dmg": 1000, "dps": 50, "rates": {{}},
                       "skills": [{{"skill": "Unknown", "skill_id": 0, "hits": 3, "dmg": 900, "share": 0.9, "dps": 45}}]}})
    shown["skill placeholder"] = kept(next(l for l in card.findChildren(QLabel) if l.objectName() == "pIcon"))
    # a pet's portrait, painted: one-pixel stripes, two to each of its points, come through as stripes
    from aion2calc.gui.pets_page import Portrait
    stripes = QImage(80, 80, QImage.Format_ARGB32)
    for x in range(80):
        for y in range(80):
            stripes.setPixelColor(x, y, QColor("white") if x % 2 else QColor("black"))
    portrait = Portrait(40)
    portrait.set_pixmap(QPixmap.fromImage(stripes))
    picture = portrait.grab().toImage()
    shown["pet portrait"] = [picture.devicePixelRatio(), picture.pixelColor(40, 40).name(),
                             picture.pixelColor(41, 40).name()]
    print(json.dumps(shown))
""")


def test_on_a_screen_of_twice_the_pixels_the_pictures_are_drawn_at_twice_the_pixels():
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": "2"}
    done = subprocess.run([sys.executable, "-c", SCALED.format(root=str(ROOT))], env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    shown = json.loads(done.stdout.strip().splitlines()[-1])
    assert shown["header logo"] == [2.0, 60, 60]                    # 30 px, at 60 of the screen's pixels
    assert shown["crafting item"] == [2.0, 72, 72]
    assert shown["builds picture"] == [2.0, 96, 96]
    assert shown["featured portrait"] == [2.0, 76, 76]
    assert shown["skill placeholder"] == [2.0, 36, 36]
    assert shown["pet portrait"] == [2.0, "#000000", "#ffffff"]       # stripes, not blurred into grey
