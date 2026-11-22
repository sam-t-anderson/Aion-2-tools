"""The customization profiles in the native Settings page (0.2.485, ``gui/settings_profiles.py``), as pages/settings.js
keeps, applies and shares them: under ``a2-custom-profiles`` in the app's interface data, where the web pages keep them
too; saved with the app's overlay look, the class colours and the overlay background at a reduced size; applied (the
theme and accent, the look, the background); deleted; and shared as ``A2PROF1:`` codes without the image."""
import base64
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import interface, settings_looks as looks, settings_profiles as cp, theme  # noqa: E402
from aion2calc.gui.settings_page import ProfileTile  # noqa: E402
from test_native_settings import FakeApp, _answers, _page, _refused  # noqa: E402

LOOK = {"overlay_font_scale": 120, "overlay_text_colors": {"rate": "#ffffff"}, "overlay_glow": True}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    yield tmp_path
    theme.apply_look("dark")


class PictureApp(FakeApp):
    """The fake app, with the overlay background's picture."""

    def __init__(self, answers=None, picture=b""):
        super().__init__(answers)
        self.picture = picture

    def get_bytes(self, path, timeout=None):
        self.calls.append(("GET", path, None))
        if not path.startswith("/overlay-background?") or not self.picture:
            raise _refused(path, 404, "not found")
        return self.picture


def settle(done, rounds=400):
    """Let the page's requests be answered until ``done()``."""
    import time
    for _ in range(rounds):
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents()
        if done():
            return True
        time.sleep(0.005)
    return bool(done())


def _png(width, height, colour="#336699") -> bytes:
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(colour))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def _decoded(url: str) -> QImage:
    head, _, data = url.partition(",")
    assert head == "data:image/jpeg;base64"
    return QImage.fromData(base64.b64decode(data))


def test_the_profiles_kept_and_their_codes(home):
    store = interface.store()
    assert cp.profiles(store) == [] and cp.options([]) == [("", "No saved profiles yet")]
    for broken in ('{"a": 1}', "not json", chr(0xFEFF) + "[]", "[1, 2"):
        store.setValue(cp.KEY, broken)
        assert cp.profiles(store) == [], broken
    kept = [{"name": "Night", "theme": "dark", "accent": "rose", "ui": {"overlay_glow": True}, "bg": ""},
            {"name": "Day", "theme": "light", "accent": "gold", "ui": {}, "bg": "data:image/jpeg;base64,AAAA"}]
    cp.save(store, kept)
    assert store.value(cp.KEY) == looks.js_json(kept) and cp.profiles(store) == kept
    assert cp.options(kept) == [("", "Choose a profile…"), ("Night", "Night"), ("Day", "Day")]
    assert cp.with_images(kept) == [kept[1]] and cp.find(kept, "night") is None and cp.find(kept, "Night") is kept[0]
    assert cp.without(kept, "NIGHT") == [kept[1]]                                    # whatever its case
    fresh = {**LOOK, "combat_colors": {"enabled": True}, "tray_on_close": True}
    assert cp.look_of(fresh) == {**LOOK, "combat_colors": {"enabled": True}}
    # a share code: the profile without its picture, read back as the web page reads one
    code = cp.encode({**kept[1], "name": "Dé"})
    assert code.startswith("A2PROF1:") and "bg" not in looks.js_parse(base64.b64decode(code[8:]))
    assert cp.decode("  " + code + "\n") == {"name": "Dé", "theme": "light", "accent": "gold", "ui": {}}
    plain = base64.b64encode(looks.js_json({"name": "x" * 45, "theme": "neon", "accent": "plaid",
                                            "ui": {**LOOK, "tray_on_close": True, "combat_colors": None}}).encode())
    assert cp.decode(plain.decode()) == {"name": "x" * 40, "theme": "system", "accent": "gold",
                                         "ui": {**LOOK, "combat_colors": None}}
    for name, shown in ((0, "Shared profile"), ("", "Shared profile"), (7, "7"), ([1, None, "a"], "1,,a"),
                        ({"a": 1}, "[object Object]")):
        raw = base64.b64encode(looks.js_json({"name": name}).encode()).decode()
        assert cp.decode(raw)["name"] == shown, name
    assert cp.decode(base64.b64encode(b"[1, 2]").decode()) == {"name": "Shared profile", "theme": "system",
                                                                 "accent": "gold", "ui": {}}
    for bad in ("", "A2PROF1:!!!", base64.b64encode(b"null").decode(), base64.b64encode(b"5").decode()):
        with pytest.raises(ValueError):
            cp.decode(bad)


def test_a_background_kept_at_a_reduced_size(home):
    url = cp.image_url(_png(2800, 700))
    picture = _decoded(url)
    assert (picture.width(), picture.height()) == (1400, 350)
    middle = picture.pixelColor(700, 175)
    assert max(abs(middle.red() - 0x33), abs(middle.green() - 0x66), abs(middle.blue() - 0x99)) <= 3   # a JPEG's
    small = _decoded(cp.image_url(_png(300, 200)))
    assert (small.width(), small.height()) == (300, 200)                          # never made larger
    assert cp.image_url(b"not a picture") == ""


def test_a_profile_saved_applied_copied_and_deleted(home):
    store = interface.store()
    store.setValue("theme", "light")
    store.setValue("accent", "azure")
    fresh = {**LOOK, "combat_colors": {"enabled": True, "colors": {"ranger": "#112233"}}, "overlay_bg_set": True}
    app = PictureApp(_answers({("GET", "/api/ui", None): fresh, ("POST", "/api/overlay/background", None): {"ok": True}}),
                     picture=_png(64, 48))
    page = _page(home, app, store=store)
    page.show_tab("backup")
    asked = iter(["  My look  "])
    page.ask_text = lambda question, default: next(asked)
    page.save_profile()
    assert settle(lambda: cp.profiles(store))
    (saved,) = cp.profiles(store)
    assert saved["name"] == "My look" and saved["theme"] == "light" and saved["accent"] == "azure"
    assert saved["ui"] == {**LOOK, "combat_colors": fresh["combat_colors"]}
    assert _decoded(saved["bg"]).size().toTuple() == (64, 48)
    assert page.toast.text() == cp.SAVED_WITH_IMAGE
    assert [page.profile_box.itemText(i) for i in range(page.profile_box.count())] == ["Choose a profile…", "My look"]
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    tiles = page.profile_tiles.findChildren(ProfileTile)
    assert [t.name for t in tiles] == ["My look"] and tiles[0].toolTip() == "Apply My look" and page.profile_tiles.isVisibleTo(page)
    assert tiles[0].picture.size().toTuple() == (64, 48)
    # applied: from the list, with nothing chosen first
    page.apply_profile()
    assert page.profile_message.text() == cp.PICK_TO_APPLY
    store.setValue("theme", "dark")
    store.setValue("accent", "rose")
    page.profile_box.setCurrentIndex(1)
    before = len(app.calls)
    page.apply_profile()
    assert settle(lambda: page.toast.text() == cp.APPLIED)
    posted = [(p, b) for m, p, b in app.calls[before:] if m == "POST"]
    assert posted == [("/api/ui", saved["ui"]), ("/api/overlay/background", {"data": saved["bg"]})]
    assert (store.value("theme"), store.value("accent")) == ("light", "azure") and theme.LOOK["shown"] == "light"
    assert store.value("a2-combat-colors") == looks.js_json(fresh["combat_colors"])
    # applied from its square (the page drawn again since: its square as it is now)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    (tile,) = page.profile_tiles.findChildren(ProfileTile)
    before = len(app.calls)
    tile.click()
    assert settle(lambda: len([c for c in app.calls[before:] if c[0] == "POST"]) == 2)
    # copied: the code without the picture
    page.profile_box.setCurrentIndex(1)
    page.copy_profile()
    code = QApplication.clipboard().text()
    assert page.profile_message.text() == cp.COPIED and cp.decode(code)["ui"] == saved["ui"]
    assert "bg" not in looks.js_parse(base64.b64decode(code[8:]))
    # deleted
    page.profile_box.setCurrentIndex(0)
    page.delete_profile()
    assert page.profile_message.text() == cp.PICK_TO_DELETE
    page.profile_box.setCurrentIndex(1)
    page.delete_profile()
    assert cp.profiles(store) == [] and page.toast.text() == cp.DELETED and page.profile_box.count() == 1


def test_a_shared_code_pasted_and_the_names_and_refusals_said(home):
    store = interface.store()
    app = PictureApp(_answers({("GET", "/api/ui", None): LOOK}))
    page = _page(home, app, store=store)
    page.show_tab("backup")
    page.ask_text = lambda question, default: "x" * 41
    page.save_profile()
    assert page.profile_message.text() == cp.NAME_TOO_LONG
    page.ask_text = lambda question, default: "   "
    page.save_profile()                                             # nothing asked for, nothing said
    assert page.profile_message.text() == cp.NAME_TOO_LONG
    page.ask_text = lambda question, default: "not a code"
    page.paste_profile()
    assert page.profile_message.text() == cp.NOT_A_CODE
    code = cp.encode({"name": "Friend's", "theme": "dark", "accent": "emerald", "ui": LOOK, "extra": 1})
    asked = []
    answers = iter([code, ""])
    page.ask_text = lambda question, default: asked.append((question, default)) or next(answers)
    page.paste_profile()                                            # no name given: nothing kept
    assert cp.profiles(store) == [] and asked[-1] == (cp.SAVE_SHARED_AS, "Friend's")
    answers = iter([code, "friend's"])
    page.paste_profile()
    assert cp.profiles(store) == [{"name": "friend's", "theme": "dark", "accent": "emerald", "ui": LOOK}]
    assert page.toast.text() == cp.SHARED_SAVED
    # a saved profile without a picture to bundle (none set): saved without one, said so
    page.ask_text = lambda question, default: "FRIEND'S"
    page.save_profile()
    assert settle(lambda: cp.profiles(store) and cp.profiles(store)[0]["name"] == "FRIEND'S")
    assert page.toast.text() == cp.SAVED and cp.profiles(store)[0]["bg"] == ""       # the same name, replaced
    # applied, the app refusing the look: said where the page is drawn again, the theme and accent kept
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "font too large")
    page.profile_box.setCurrentIndex(1)
    page.apply_profile()
    assert settle(lambda: page.profile_message.text() == "font too large")
    assert store.value("theme") == "system" and not [p for m, p, b in app.calls if p == "/api/overlay/background"]
    page.profile_box.setCurrentIndex(1)
    QCoreApplication.processEvents()
    store.setValue(cp.KEY, "[]")
    page.apply_profile()
    assert page.profile_message.text() == cp.NOT_FOUND
