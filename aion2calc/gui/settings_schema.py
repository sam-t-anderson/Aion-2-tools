"""The web Settings page's rows the native Settings page does not draw yet (0.2.414): each says the setting is on the
web Settings page, and opens it.

Until 0.2.475 every row was here, its controls each saving one setting through the app's ``/api/ui``. Since 0.2.475 the
page draws App & data as the web page does (settings_page.py, settings_words.py), since 0.2.476 the Meter and Server
tabs, since 0.2.477 Pet Tracker, since 0.2.478 the first half of Overlay, since 0.2.479 the radar and the hotkeys and
since 0.2.480 the rest of Overlay (settings_looks.py), so their rows are no longer here; the others follow.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Row:
    group: str
    title: str


#: The web page's groups, in its order (its tabs, ``data-settab``).
GROUPS = [('appearance', 'Appearance'), ('overlay', 'Overlay'), ('pettracker', 'Pet Tracker'), ('meter', 'Meter'), ('server', 'Server'), ('backup', 'Profiles & backup'), ('system', 'App & data')]

ROWS = (
    Row('appearance', 'Theme'),
    Row('appearance', 'Accent colour'),
    Row('backup', 'Customization profiles'),
    Row('backup', 'Settings backup'),
    Row('appearance', 'Combat class colors'),
)
