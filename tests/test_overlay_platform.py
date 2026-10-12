"""The overlay's native-backend platform abstraction (overlay.native_overlay and the
per-OS backends). Windows is implemented; macOS/Linux are scaffolds (supported=False),
so on those platforms the factory returns None and the overlay keeps its fallback."""
import sys

import pytest

from aion2calc import overlay


def test_backend_flags():
    assert overlay._Windows.platform == "win32" and overlay._Windows.supported is True
    assert overlay._MacOS.platform == "darwin" and overlay._MacOS.supported is False
    assert overlay._Linux.platform == "linux" and overlay._Linux.supported is False


def test_scaffolds_are_safe_no_ops_or_explicit_stubs():
    mac = overlay._MacOS()
    # Cheap, always-safe defaults from the base interface.
    assert mac.monitors() == []
    assert mac.cursor_in_client(object()) is None
    # The genuinely native operations are explicit stubs, not silent wrong answers.
    for call in (lambda: mac.game_window(), lambda: mac.rect(0),
                 lambda: mac.move(0, 0, 0), lambda: mac.set_click_through(0, True)):
        with pytest.raises(NotImplementedError):
            call()


def test_factory_returns_none_on_unimplemented_platforms(monkeypatch):
    # macOS/Linux backends are unsupported -> factory yields None (fallback path).
    monkeypatch.setattr(sys, "platform", "darwin")
    assert overlay.native_overlay() is None
    monkeypatch.setattr(sys, "platform", "linux")
    assert overlay.native_overlay() is None
    # An OS with no backend at all -> None, no crash.
    monkeypatch.setattr(sys, "platform", "freebsd13")
    assert overlay.native_overlay() is None


def test_factory_is_resilient_when_the_windows_backend_cannot_load(monkeypatch):
    # On a non-Windows host, constructing _Windows() fails (no user32); the factory must
    # swallow that and return None rather than propagate.
    monkeypatch.setattr(sys, "platform", "win32")
    assert overlay.native_overlay() is None
