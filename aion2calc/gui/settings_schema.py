"""What the native Settings page shows and saves (0.2.414): the web Settings page's rows, in its order and words.

Each control saves one setting through the app's ``/api/ui``, as the web page's control does: ``Bool`` a checkbox,
``Choice`` a list, ``Number`` a whole number within the web page's limits. A row the native page does not draw in
full yet (``web``: the log server, profiles and backups, hotkeys, colours and fonts, the background image) shows
what it can and opens the web Settings page for the rest. Generated from ``pages/settings.js``'s controls and the
keys their handlers save, then kept by hand; ``tests/test_native_settings.py`` checks every key is a setting.

Since 0.2.475 the page draws App & data as the web page does (settings_page.py, settings_words.py), since 0.2.476
the Meter and Server tabs and since 0.2.477 Pet Tracker, so their rows are no longer here; the others follow, a tab at
a time.
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
    Row('overlay', 'Live meter overlay', (Bool('overlay_open_on_app_start', 'Open the overlay when the app starts (on by default)'),
         Bool('overlay_on_start', 'Show overlay when starting the live meter'),
         Bool('overlay_close_on_stop', 'Close the overlay when I stop the meter (off by default — the overlay stays up showing the last fight, and its own Stop button never closes it)'),
         Bool('overlay_show_contribution', "Show your contribution (your share of the encounter's damage)"),
         Bool('overlay_show_target', "Show the current target and each player's DPS to it"),
         Bool('overlay_show_deaths', 'Mark party members who are dead (row shows DEAD until they recover)'),
         Bool('overlay_show_enemy_hp', "Show the current target's remaining HP as a percentage and bar (only when the game reports it). The game's internal HP value is on a much larger scale than damage numbers, so it is shown as a percentage, not a raw number that won't match your damage."),
         Bool('overlay_show_ttk', "Show estimated time-to-kill for the current target, as a number and a progress bar (from the target's observed HP-decline rate)"),
         Bool('overlay_show_break_gauge', "Show the current target's break (stagger) gauge, as a readout and a bar (bosses and elites carry one; off by default)"),
         Bool('overlay_show_cooldowns', 'Show a strip of your skills on cooldown, each counting down (off by default)'),
         Bool('overlay_show_combat_power', 'Show your combat power beside your name (when the game reports it)'),
         Bool('overlay_show_odyle', 'Show your Odyle Energy on the overlay and the Live Meter page (on by default)'),
         Bool('overlay_show_shugo_keys', 'Show your Shugo Festival keys on the overlay and the Live Meter page (on by default)'),
         Bool('overlay_show_nightmare_tickets', 'Show your Nightmare tickets on the overlay and the Live Meter page (on by default)'),
         Bool('overlay_show_weekly_runs', "Show the dungeon's weekly runs left on the overlay and the Live Meter page (on by default)"),
         Bool('overlay_show_community_rank', 'Show your community rank for your last uploaded fight (needs auto-upload; off by default)'),
         Bool('overlay_live_community_rank', 'Update the rank live after each fight (needs the rank badge on + a share server; uploads each ranked fight at your upload visibility; off by default)'),
         Bool('overlay_show_events', 'Show regional event notifications on the overlay (uses the region you pick on the Timers page; community forecast, on by default)'),
         Bool('overlay_show_field_bosses', 'Include observed field-boss timers in the event strip (kills recorded on your server and faction; on by default)'),
         Bool('overlay_events_sound', 'Play a sound when an event notification appears (off by default)'),
         Bool('overlay_plan_autoplay', "Auto-play a saved raid plan on the overlay's Plan tab when you fight the boss it is bound to, synced to the pull (on by default)"),
         Choice('overlay_cooldowns_position', 'Cooldown strip', (('bottom', 'Below the meter'), ('top', 'Above the player rows')), str),
         Number('overlay_cooldowns_min_s', 'Shortest cooldown shown', 1, 120, 's'),
         Number('overlay_cooldowns_max', 'Icons', 1, 16, '')), web=False),
    Row('overlay', 'Hidden Cube radar', (Bool('radar_enabled', 'Show where a Hidden Cube is around you and how near, from the jingle it plays (Windows; off by default)'),
         Number('radar_sensitivity', 'Sensitivity', 1, 10, '')), web=False),
    Row('overlay', 'In-game (RTSS)', (Bool('rtss_enabled', 'Draw the meter inside the game through RivaTuner Statistics Server (Windows; off by default; needs RTSS running with its on-screen display enabled)'),
         Choice('rtss_metric', 'Metric', (('dps', 'DPS'), ('hps', 'HPS'), ('dtps', 'Damage taken')), str),
         Choice('rtss_style', 'Style', (('plain', 'Plain text'), ('colored', 'Class colours (RTSS colour tags)')), str),
         Number('rtss_rows', 'Rows', 1, 24, ''),
         Number('rtss_interval_ms', 'Refresh', 100, 5000, 'ms')), web=False),
    Row('overlay', 'Streaming (OBS / Discord)', (), web=True),
    Row('overlay', 'Overlay layout', (Bool('overlay_auto_expand', 'Auto-expand to show every captured player (beyond the limit above)'),
         Bool('overlay_only_in_combat', 'Show the meter only during combat (collapse between pulls)'),
         Bool('overlay_boss_only', 'Boss damage only: count the damage dealt to bosses, mini-bosses, field and world bosses (leaves out trash and, in the Abyss, other players)'),
         Bool('overlay_pvp_only', 'Player (PvP) damage only: count the damage dealt to other players (with Boss damage only on too, bosses count as well)'),
         Bool('overlay_long_names_scroll', 'Scroll long names on hover'),
         Bool('overlay_bar_rounded', 'Rounded bar corners'),
         Bool('overlay_class_color_names', 'Colour player names by class'),
         Bool('overlay_row_stripes', 'Zebra-stripe the player rows'),
         Bool('overlay_class_swatch', 'Show a class-colour swatch before each name'),
         Bool('overlay_compact_rows', 'Compact rows (hide the total & percent, keep the per-second rate)'),
         Bool('overlay_rank_numbers', 'Show rank numbers (1., 2., 3. …) before each name'),
         Bool('overlay_highlight_me', 'Highlight my own row (accent bar, so you can find yourself at a glance)'),
         Bool('overlay_dps_interpolate', 'Live-ticking DPS numbers (recompute between polls for a real-time feel; on by default) ms'),
         Bool('overlay_dps_graph', 'Show a live DPS/HPS graph (a sparkline of the party total over the fight, from real per-poll readings)'),
         Bool('overlay_show_fps', "Show the overlay's own render FPS (the game's FPS can't be read from capture)"),
         Bool('overlay_click_through', "Click through the overlay — let the mouse pass through to the game, so the overlay never eats a click (Windows; the overlay's own buttons/sliders still work when you hover them)"),
         Bool('overlay_hover_interact', 'With click-through on, rest the pointer on the overlay for 5 seconds to click anywhere on it (a ring fills in while it counts; clicks pass through again once the pointer leaves)'),
         Bool('overlay_party_enabled', 'Open a separate Party-DPS overlay (raid totals) alongside the meter'),
         Bool('overlay_always_visible', 'Keep the overlay visible even when the game is not in focus (on by default; so clicking another overlay, the app window or a game popup never hides it)'),
         Bool('overlay_remember_position', 'Remember where I drag the overlay and reopen it there, instead of following the game window (on by default, Windows; each overlay remembers its own spot — uncheck to follow the game window instead)'),
         Bool('overlay_resizable', 'Resize the overlay by dragging its edges/corners'),
         Bool('overlay_snap_edge', "Snap to the game window's edges"),
         Bool('overlay_expand_up', 'Expand upward (anchor the overlay near the bottom of the game window)'),
         Choice('overlay_name_mode', 'Name display', (('name', 'Character names'), ('class_number', 'Class + party number'), ('number', 'Party number only')), str),
         Choice('overlay_bar_style', 'Bar style', (('flat', 'Flat class colour'), ('gradient', 'Gradient')), str),
         Choice('overlay_bg_mode', 'Background', (('card', 'Whole card'), ('top', 'Top portion only (header, boss panel, Odyle lines)'), ('none', 'None: rows, bars and text alone over the game')), str),
         Choice('overlay_me_cosmetic', "My row's effect", (('none', 'None'), ('gold', 'Gold: a turning gold frame and a diamond'), ('rainbow', 'Rainbow: a glowing rainbow name'), ('ember', 'Ember: a pulsing fire glow'), ('frost', 'Frost: an icy sheen'), ('aether', 'Aether: a violet and teal aurora'), ('starlight', 'Starlight: twinkling stars')), str),
         Choice('overlay_top_cosmetic', "Top row's effect", (('none', 'None'), ('gold', 'Gold: a turning gold frame and a diamond'), ('rainbow', 'Rainbow: a glowing rainbow name'), ('ember', 'Ember: a pulsing fire glow'), ('frost', 'Frost: an icy sheen'), ('aether', 'Aether: a violet and teal aurora'), ('starlight', 'Starlight: twinkling stars')), str),
         Number('overlay_max_players', 'Players shown', 1, 24, ''),
         Number('overlay_width', 'Width', 260, 800, 'px'),
         Number('overlay_height', 'Height', 0, 800, 'px'),
         Number('overlay_row_height', 'Row height', 14, 48, 'px'),
         Number('overlay_interpolate_ms', 'Tick every', 50, 1000, 'ms')), web=False),
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
