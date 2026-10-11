"""The collapse-to-tray wrapper: menu actions call the right callbacks, Quit also
stops the icon, and a missing/broken backend degrades to a no-op so the app keeps
its default lifetime instead of crashing on launch."""
import sys
import types

from aion2calc.app import tray as tray_mod


class _FakeMenuItem:
    def __init__(self, text, action, default=False):
        self.text, self.action, self.default = text, action, default


class _FakeIcon:
    instances = []

    def __init__(self, name, image, title, menu):
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.ran = False
        self.stopped = False
        _FakeIcon.instances.append(self)

    def run(self):
        self.ran = True          # a real icon blocks here; the fake returns at once

    def run_detached(self):
        self.ran = "detached"

    def stop(self):
        self.stopped = True


def _install_fake_pystray(monkeypatch):
    module = types.ModuleType("pystray")
    module.Icon = _FakeIcon
    module.Menu = lambda *items: list(items)
    module.MenuItem = _FakeMenuItem
    monkeypatch.setitem(sys.modules, "pystray", module)
    _FakeIcon.instances = []
    return module


def test_menu_actions_invoke_callbacks_and_quit_stops_icon(monkeypatch):
    _install_fake_pystray(monkeypatch)
    opened, quit_called = [], []
    tray = tray_mod.Tray(on_open=lambda: opened.append(1), on_quit=lambda: quit_called.append(1))
    assert tray.run() is True
    icon = _FakeIcon.instances[-1]
    by_text = {item.text: item for item in icon.menu}

    by_text["Open Aion 2 Calc"].action(icon, by_text["Open Aion 2 Calc"])
    assert opened == [1]
    assert by_text["Open Aion 2 Calc"].default is True       # left-click opens the window

    by_text["Quit"].action(icon, by_text["Quit"])
    assert quit_called == [1]
    assert icon.stopped is True                              # Quit tears the icon down


def test_quit_still_stops_icon_if_callback_raises(monkeypatch):
    _install_fake_pystray(monkeypatch)
    def boom():
        raise RuntimeError("shutdown hiccup")
    tray = tray_mod.Tray(on_open=lambda: None, on_quit=boom)
    tray.run()
    icon = _FakeIcon.instances[-1]
    quit_item = next(i for i in icon.menu if i.text == "Quit")
    quit_item.action(icon, quit_item)                        # must not propagate
    assert icon.stopped is True


def test_run_returns_false_when_backend_cannot_build(monkeypatch):
    # pystray importable but constructing the icon fails (e.g. no display): no crash.
    module = types.ModuleType("pystray")

    class _Broken:
        def __init__(self, *a, **k):
            raise RuntimeError("no display")
    module.Icon = _Broken
    module.Menu = lambda *items: list(items)
    module.MenuItem = _FakeMenuItem
    monkeypatch.setitem(sys.modules, "pystray", module)
    tray = tray_mod.Tray(on_open=lambda: None, on_quit=lambda: None)
    assert tray.run() is False                               # caller falls back to normal lifetime


def test_available_false_without_pystray(monkeypatch):
    monkeypatch.setitem(sys.modules, "pystray", None)
    # find_spec("pystray") raises ValueError for a None entry; available() swallows it.
    assert tray_mod.available() is False
