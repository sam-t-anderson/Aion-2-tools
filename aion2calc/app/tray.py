"""Optional system-tray presence (Windows, macOS, Linux).

When the user enables "collapse to tray", closing the app window no longer quits
the app: the server, live meter and overlay keep running and a tray icon offers
*Open* (re-show the window) and *Quit* (really stop). pystray is bundled best-
effort; when it or a platform backend is unavailable this degrades to a no-op and
the caller keeps the current "closing the window stops the app" behaviour.

pystray's macOS backend must own the main thread, so :func:`run` is written to be
called from the main thread (the launcher runs the HTTP server on a worker when
the tray is active). ``run_detached`` is tried first for backends that support it.
"""
from __future__ import annotations

import importlib.util
import threading


def available() -> bool:
    """Is pystray importable (so a tray icon is possible on this machine)?"""
    try:
        return importlib.util.find_spec("pystray") is not None and importlib.util.find_spec("PIL") is not None
    except Exception:
        return False


def _icon_image():
    """A small self-drawn icon, so no packaged image file has to be located at runtime."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(16, 22, 34, 255), outline=(232, 207, 142, 255), width=3)
    # A bright chevron evoking the app mark; readable at tray size on light and dark bars.
    draw.polygon([(size * 0.32, size * 0.68), (size * 0.5, size * 0.3),
                  (size * 0.68, size * 0.68), (size * 0.5, size * 0.56)], fill=(232, 207, 142, 255))
    return image


class Tray:
    """A lightweight wrapper over pystray with a two-item menu."""

    def __init__(self, *, on_open, on_quit, title: str = "Aion 2 Calc"):
        self._on_open = on_open
        self._on_quit = on_quit
        self._title = title
        self._icon = None
        self._started = threading.Event()

    def _build(self):
        import pystray

        def open_action(icon, item):      # noqa: ARG001 - pystray passes icon/item
            try:
                self._on_open()
            except Exception:
                pass

        def quit_action(icon, item):      # noqa: ARG001
            try:
                self._on_quit()
            except Exception:
                pass
            finally:
                self.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Open Aion 2 Calc", open_action, default=True),
            pystray.MenuItem("Quit", quit_action),
        )
        return pystray.Icon("aion2calc", _icon_image(), self._title, menu)

    def run(self) -> bool:
        """Create and run the tray icon. Blocks until :meth:`stop` (call on the main
        thread). Returns ``False`` without blocking if the tray cannot be created."""
        try:
            self._icon = self._build()
        except Exception:
            self._icon = None
            return False
        self._started.set()
        try:
            self._icon.run()
        except Exception:
            return False
        return True

    def run_detached(self) -> bool:
        """Start the tray without blocking, where the backend supports it. Returns
        whether a detached icon was started."""
        try:
            self._icon = self._build()
            self._icon.run_detached()
            self._started.set()
            return True
        except Exception:
            self._icon = None
            return False

    def notify(self, message: str, title: str | None = None) -> None:
        icon = self._icon
        if icon is not None:
            try:
                icon.notify(message, title or self._title)
            except Exception:
                pass

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
