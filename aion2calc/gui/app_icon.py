"""The app's icon on its native windows (0.2.501): the logo (``app/static/logo.png``, the picture the installed app's
executable carries as ``aion2calc.ico``, whose sizes are this picture's), on the title bar, the taskbar and the window
switcher, where Qt drew its placeholder. Qt does not take the executable's icon for its windows, as the web
interface's window took it, so each native process sets it on its application (``apply``): the app's window, the
meter overlay and its companion windows, and every dialog they open.
"""
from __future__ import annotations

import pathlib

from PySide6.QtGui import QIcon

LOGO = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "logo.png"


def app_icon() -> QIcon:
    """The app's icon (an empty icon when its picture is missing, so a window keeps Qt's own rather than failing)."""
    return QIcon(str(LOGO)) if LOGO.is_file() else QIcon()


def apply(app) -> QIcon:
    """The app's icon set on ``app`` (a QApplication), for every window it opens; the icon, empty when it is missing
    (Qt's placeholder is then left as it is)."""
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    return icon
