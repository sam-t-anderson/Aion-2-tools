"""The tray's icon is the app's logo (0.2.502), as the app's windows (0.2.501) and its program file show it, where it
was a mark of its own; the mark stays for when the logo cannot be read."""
import hashlib
import pathlib
import sys
import types

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from aion2calc.app import tray  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pixels(image):
    return image.convert("RGBA").tobytes()


def test_the_tray_icon_is_the_apps_logo():
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
    # the picture the build makes the program file's icon from, and the windows' icon (gui/app_icon.py)
    assert tray.LOGO.is_file() and digest(tray.LOGO) == digest(ROOT / "packaging" / "aion2calc.png")
    assert tray.LOGO == ROOT / "aion2calc" / "app" / "static" / "logo.png"
    image = tray._icon_image()
    assert image.mode == "RGBA" and image.size == (tray.ICON_SIZE, tray.ICON_SIZE) == (256, 256)
    with Image.open(tray.LOGO) as logo:
        expected = logo.convert("RGBA").resize((256, 256), Image.LANCZOS)
    assert _pixels(image) == _pixels(expected)
    assert image.getpixel((0, 0))[3] == 0 and image.getpixel((128, 128))[3] == 255     # the round badge, see-through


def test_without_the_logo_the_tray_keeps_its_own_mark(monkeypatch, tmp_path):
    monkeypatch.setattr(tray, "LOGO", tmp_path / "gone.png")
    image = tray._icon_image()
    assert image.size == (64, 64) and _pixels(image) == _pixels(tray._drawn_mark())
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a picture")
    monkeypatch.setattr(tray, "LOGO", broken)
    assert tray._icon_image().size == (64, 64)


def test_the_tray_shows_it(monkeypatch):
    made = {}

    class Icon:
        def __init__(self, name, image, title, menu):
            made.update(name=name, image=image, title=title, menu=menu)

    fake = types.SimpleNamespace(Icon=Icon, Menu=lambda *items: list(items),
                                 MenuItem=lambda words, action, default=False: (words, default))
    monkeypatch.setitem(sys.modules, "pystray", fake)
    tray.Tray(on_open=lambda: None, on_quit=lambda: None)._build()
    assert made["name"] == "aion2calc" and made["title"] == "Aion 2 Calc"
    assert made["menu"] == [("Open Aion 2 Calc", True), ("Quit", False)]
    assert made["image"].size == (256, 256) and _pixels(made["image"]) == _pixels(tray._icon_image())
