"""The web Settings page's rows the native Settings page does not draw yet (0.2.414): each says the setting is on the
web Settings page, and opens it.

Until 0.2.475 every row was here, its controls each saving one setting through the app's ``/api/ui``. Since 0.2.475 the
page draws App & data as the web page does (settings_page.py, settings_words.py), since 0.2.476 the Meter and Server
tabs, since 0.2.477 Pet Tracker, since 0.2.478 the first half of Overlay, since 0.2.479 the radar and the hotkeys,
since 0.2.480 the rest of Overlay (settings_looks.py) and since 0.2.481 the class colours and the settings backup, so
their rows are no longer here, since 0.2.484 the theme and the accent colour, and since 0.2.485 the customization
profiles: every row is drawn natively, and none is left here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    group: str
    title: str


#: The web page's groups, in its order (its tabs, ``data-settab``).
GROUPS = [('appearance', 'Appearance'), ('overlay', 'Overlay'), ('pettracker', 'Pet Tracker'), ('meter', 'Meter'), ('server', 'Server'), ('backup', 'Profiles & backup'), ('system', 'App & data')]

ROWS: tuple[Row, ...] = ()
