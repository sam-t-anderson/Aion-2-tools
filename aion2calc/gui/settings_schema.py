"""What the native Settings page shows and saves (0.2.414): the web Settings page's rows, in its order and words.

Each control saves one setting through the app's ``/api/ui``, as the web page's control does: ``Bool`` a checkbox,
``Choice`` a list, ``Number`` a whole number within the web page's limits. A row the native page does not draw in
full yet (``web``: the log server, profiles and backups, hotkeys, colours and fonts, the background image) shows
what it can and opens the web Settings page for the rest. Generated from ``pages/settings.js``'s controls and the
keys their handlers save, then kept by hand; ``tests/test_native_settings.py`` checks every key is a setting.

Since 0.2.475 the page draws App & data as the web page does (settings_page.py, settings_words.py), since 0.2.476
the Meter and Server tabs, since 0.2.477 Pet Tracker and since 0.2.478 the first half of Overlay, so their rows are no
longer here; the others follow.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bool:
    key: str
    label: str


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    options: tuple
    cast: type = str


@dataclass(frozen=True)
class Number:
    key: str
    label: str
    minimum: int
    maximum: int
    unit: str = ""


@dataclass(frozen=True)
class Row:
    group: str
    title: str
    controls: tuple
    web: bool = False                         # part of the row is only on the web Settings page so far


#: The web page's groups, in its order (its tabs, ``data-settab``).
GROUPS = [('appearance', 'Appearance'), ('overlay', 'Overlay'), ('pettracker', 'Pet Tracker'), ('meter', 'Meter'), ('server', 'Server'), ('backup', 'Profiles & backup'), ('system', 'App & data')]

ROWS = (
    Row('appearance', 'Theme', (), web=True),
    Row('appearance', 'Accent colour', (), web=True),
    Row('overlay', 'Hidden Cube radar', (Bool('radar_enabled', 'Show where a Hidden Cube is around you and how near, from the jingle it plays (Windows; off by default)'),
         Number('radar_sensitivity', 'Sensitivity', 1, 10, '')), web=False),
    Row('backup', 'Customization profiles', (), web=True),
    Row('backup', 'Settings backup', (), web=True),
    Row('overlay', 'Overlay colors & fonts', (Bool('overlay_glow', 'Text glow'),
         Number('overlay_font_scale', 'Text size', 80, 160, '%')), web=True),
    Row('overlay', 'Overlay text effects & per-element fonts', (), web=True),
    Row('overlay', 'Overlay background', (), web=True),
    Row('overlay', 'Overlay look presets', (), web=True),
    Row('overlay', 'Hotkeys (Windows)', (), web=True),
    Row('appearance', 'Combat class colors', (), web=True),
)
