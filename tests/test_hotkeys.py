"""Global hotkeys: combo parsing, config validation, settings wiring.

The Windows RegisterHotKey message loop can't run headless, so these cover the
platform-independent parts (parsing, validation, defaults, backup) and assert the
UI/launcher wiring is present.
"""
import pathlib
import sys

import pytest

from aion2calc.app import hotkeys, server, settings_backup

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
LAUNCHER = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "launcher.py").read_text(encoding="utf-8")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("combo,mods,vk", [
    ("Ctrl+Shift+M", 0x0002 | 0x0004, ord("M")),
    ("Alt+F4", 0x0001, 0x73),              # F4 = 0x70 + 3
    ("Win+5", 0x0008, ord("5")),
    ("ctrl+space", 0x0002, 0x20),
    ("F13", 0, 0x7C),
])
def test_parse_combo_valid(combo, mods, vk):
    assert hotkeys.parse_combo(combo) == (mods, vk)


@pytest.mark.parametrize("combo", ["", "Ctrl", "Ctrl+Shift", "Ctrl+A+B", "Ctrl+F25", "Ctrl+nope", None, 5])
def test_parse_combo_invalid(combo):
    assert hotkeys.parse_combo(combo) is None


def test_clean_hotkeys_filters_and_validates():
    cleaned = hotkeys.clean_hotkeys({
        "toggle_overlay": "Ctrl+Shift+O",
        "toggle_events": "Ctrl+Shift+E",   # newly bindable action
        "quit": "Ctrl+Shift+Q",            # newly bindable action
        "clear_meter": "",             # explicit unbind -> dropped
        "unknown_action": "Ctrl+X",    # unknown -> dropped
    })
    assert cleaned == {"toggle_overlay": "Ctrl+Shift+O", "toggle_events": "Ctrl+Shift+E", "quit": "Ctrl+Shift+Q"}
    assert "toggle_events" in hotkeys.ACTIONS and "quit" in hotkeys.ACTIONS
    with pytest.raises(ValueError):
        hotkeys.clean_hotkeys({"toggle_meter": "Ctrl"})       # modifier only
    with pytest.raises(ValueError):
        hotkeys.clean_hotkeys("not a dict")


def test_hotkeys_default_empty_and_back_up(home):
    assert server.ui_settings()["hotkeys"] == {}
    out = settings_backup.import_settings({"hotkeys": {"toggle_meter": "Ctrl+Alt+S", "bogus": "x"}})
    assert out["settings"]["hotkeys"] == {"toggle_meter": "Ctrl+Alt+S"}
    with pytest.raises(ValueError):
        settings_backup.import_settings({"hotkeys": {"toggle_meter": "Shift"}})


def test_manager_is_inert_off_windows():
    # start() must be a no-op (no thread) on non-Windows, and never raise.
    mgr = hotkeys.HotkeyManager(lambda: {}, {})
    mgr.start()
    if sys.platform != "win32":
        assert mgr._thread is None
    mgr.stop()


def test_every_action_has_a_label_and_is_wired():
    # The UI action list and the launcher dispatch must cover exactly ACTIONS.
    for action in hotkeys.ACTIONS:
        assert action in APP_JS                 # Settings capture row
        assert f'"{action}"' in LAUNCHER        # launcher dispatch entry
    # Settings UI scaffolding + save.
    assert 'id="hotkey-rows"' in APP_JS
    assert 'id="hotkeys-save"' in APP_JS
    assert "hotkeys:map" in APP_JS


def test_newly_wired_actions_present():
    # The two actions added for the overlay hotkey wiring.
    assert "open_settings" in hotkeys.ACTIONS and "screenshot_lock" in hotkeys.ACTIONS
    # open_settings lands on the Settings route; screenshot_lock drives the overlay lock pulse.
    assert "#/settings" in LAUNCHER
    assert "pulse_overlay_lock" in LAUNCHER


def test_overlay_lock_pulse_channel():
    # A hotkey in the app process can't call the separate overlay window, so it bumps a
    # counter the overlay watches on its own poll (which keeps running even while locked).
    before = server.OVERLAY_COMMANDS.get("lock_seq", 0)
    server.pulse_overlay_lock()
    assert server.OVERLAY_COMMANDS["lock_seq"] == before + 1
    overlay_js = (STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "/api/overlay/commands" in overlay_js and "lock_seq" in overlay_js and "toggleLock" in overlay_js
