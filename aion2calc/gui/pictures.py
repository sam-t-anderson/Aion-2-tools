"""The game's pictures on the native overlay (0.2.421): each class's emblem on the player rows and each boss's
portrait on the target card, from the art the app bundles (``static/game-assets.json``, the web pages'
``A2BundledAssets``), read through the app's local API as the web overlay reads it.

The asset map is read once, each picture when it is first wanted, and both are kept. A class or a boss the app has no
art for has none: the rows do without an emblem and the target card shows its target mark, as on the web overlay.
The web overlay can also show a portrait the log server's community map links to; the native overlay keeps to the
bundled ones, which need nothing but the app.
"""
from __future__ import annotations

import io
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from . import theme
from .api import AppApi, Requests

#: Where the web pages find a class's emblem (overlay.js ``classArt``); the asset map gives its bundled file.
CLASS_ART = "https://metabot.gg/web/aion2/classes/{}.webp"
RETRY_S = 30.0                            # a map or a picture the app could not give is asked for again after this


def decoded(data: bytes) -> QImage:
    """A picture's bytes as an image: Qt's own reading, else Pillow's (a Qt without its WebP plugin)."""
    image = QImage.fromData(data)
    if image.isNull() and data:
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as picture:
                buffer = io.BytesIO()
                picture.convert("RGBA").save(buffer, "PNG")
            image = QImage.fromData(buffer.getvalue())
        except Exception:                 # noqa: BLE001 - bytes neither can read are no picture
            image = QImage()
    return image


def _bundled(file) -> bool:
    return isinstance(file, str) and file.startswith("game-assets/") and ".." not in file and "\\" not in file


class Pictures(QObject):
    """The class emblems and boss portraits, from the app (``api``; None in tests that hand them over).
    ``changed`` is emitted when a picture arrives, for the overlay to draw it."""

    changed = Signal()

    def __init__(self, api: AppApi | None, parent: QObject | None = None):
        super().__init__(parent)
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.classes: dict[str, str] = {}         # a class's name: its emblem's bundled file
        self.npcs: dict[str, str] = {}            # a boss's code: its portrait's bundled file
        self._map_state = "unread"                # "asking", "read", or the monotonic time it failed at
        self._kept: dict[str, QPixmap | None] = {}
        self._failed_at: dict[str, float] = {}

    def stop(self) -> None:
        if self.requests is not None:
            self.requests.stop()

    def read_map(self, assets: dict) -> None:
        """Take the asset map (``game-assets.json``): the classes' emblems and the bosses' portraits it bundles."""
        files = assets.get("assets") if isinstance(assets.get("assets"), dict) else {}
        portraits = assets.get("npc_portraits") if isinstance(assets.get("npc_portraits"), dict) else {}
        self.classes = {cls: file for cls in theme.CLASS_COLORS
                        if _bundled(file := files.get(CLASS_ART.format(cls)))}
        self.npcs = {str(code): file for code, url in portraits.items()
                     if isinstance(url, str) and _bundled(file := files.get(url))}
        self._map_state = "read"
        self.changed.emit()

    def keep(self, file: str, picture: QPixmap | None) -> None:
        """A picture as read (or None: none to be had)."""
        self._kept[file] = picture if picture is not None and not picture.isNull() else None
        self.changed.emit()

    def emblem(self, cls) -> QPixmap | None:
        """A class's emblem, or None: none bundled for it, or not read yet (``changed`` says when it is)."""
        self._ask_map()
        return self._picture(self.classes.get(str(cls or "").lower()))

    def portrait(self, code) -> QPixmap | None:
        """A boss's portrait by its code (``mob_code``), or None."""
        if code is None or isinstance(code, bool):
            return None
        self._ask_map()
        return self._picture(self.npcs.get(str(code)))

    def _ask_map(self) -> None:
        state = self._map_state
        if self.requests is None or state in ("asking", "read"):
            return
        if isinstance(state, float) and time.monotonic() - state < RETRY_S:
            return
        self._map_state = "asking"
        self.requests.get("map", "/static/game-assets.json")

    def _picture(self, file: str | None) -> QPixmap | None:
        if not file:
            return None
        if file in self._kept:
            return self._kept[file]
        failed = self._failed_at.get(file)
        if self.requests is not None and (failed is None or time.monotonic() - failed >= RETRY_S):
            self._kept[file] = None               # asked for: one request, whatever asks again meanwhile
            self._failed_at.pop(file, None)
            self.requests.get_bytes("file:" + file, "/static/" + file)
        return None

    def _replied(self, name: str, answer) -> None:
        if name == "map":
            if isinstance(answer, dict):
                self.read_map(answer)
            else:
                self._map_state = time.monotonic()
            return
        if name.startswith("file:"):
            file = name[len("file:"):]
            image = decoded(bytes(answer)) if isinstance(answer, (bytes, bytearray)) else QImage()
            if image.isNull():
                self._forget(file)
            else:
                self.keep(file, QPixmap.fromImage(image))

    def _failed(self, name: str, why: str) -> None:
        if name == "map":
            self._map_state = time.monotonic()
        elif name.startswith("file:"):
            self._forget(name[len("file:"):])

    def _forget(self, file: str) -> None:
        """A picture the app could not give: none for now, asked for again a while later."""
        self._kept.pop(file, None)
        self._failed_at[file] = time.monotonic()
