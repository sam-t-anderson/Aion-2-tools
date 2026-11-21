"""What the native Settings page shows and saves (0.2.414): the web Settings page's rows, in its order and words.

Each control saves one setting through the app's ``/api/ui``, as the web page's control does: ``Bool`` a checkbox,
``Choice`` a list, ``Number`` a whole number within the web page's limits. A row the native page does not draw in
full yet (``web``: the log server, profiles and backups, hotkeys, colours and fonts, the background image) shows
what it can and opens the web Settings page for the rest. Generated from ``pages/settings.js``'s controls and the
keys their handlers save, then kept by hand; ``tests/test_native_settings.py`` checks every key is a setting.
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


#: The web page's groups, in its order (its filter buttons).
GROUPS = [('appearance', 'Appearance'), ('system', 'App'), ('server', 'Log server'), ('overlay', 'Overlay'), ('pettracker', 'Pet Tracker'), ('meter', 'Combat records'), ('backup', 'Backup')]

ROWS = (
    Row('appearance', 'Theme', (), web=True),
    Row('appearance', 'Accent colour', (), web=True),
    Row('system', 'Native interface', (Bool('interface_native', 'open the app and the meter overlay in the native interface, drawn in Python instead of a browser'),), web=False),
    Row('system', 'Open as its own window', (Bool('app_window', 'start in a separate app window (Edge or Chrome) instead of a browser tab; closing it stops the app'),), web=False),
    Row('system', 'Text size', (Choice('app_text_scale', "Size of the app's text", ((70, '70%'), (80, '80%'), (90, '90%'), (100, '100%'), (110, '110%'), (120, '120%'), (130, '130%'), (140, '140%'), (150, '150%')), int),), web=False),
    Row('system', 'Performance mode', (Bool('performance_mode', 'Lighter on a low-spec PC (off by default)'),), web=False),
    Row('system', 'Language', (), web=True),
    Row('system', 'Page at launch', (Choice('app_default_page', 'Open the app on', (('meter', 'Live Meter'), ('combat', 'Combat Logs'), ('raid', 'Raid Planner'), ('planner', 'Build Planner'), ('builds', 'Builds'), ('character', 'My Character'), ('gear', 'Gear & Advice'), ('history', 'Saved Results'), ('timers', 'Timers'), ('maps', 'Maps'), ('database', 'Database'), ('crafting', 'Crafting'), ('gathering', 'Gathering'), ('pets', 'Pet Tracker'), ('news', 'News'), ('settings', 'Settings')), str),), web=False),
    Row('system', 'My Character at launch', (Bool('character_auto_open', 'Show the character you opened last when My Character opens (off by default)'),
         Bool('character_auto_refresh', 'Refresh that character from the official site when the app opens, instead of showing the last snapshot (off by default; needs the setting above)')), web=False),
    Row('system', 'Collapse to tray', (Bool('tray_on_close', 'keep running in the system tray when the window is closed (Windows, macOS, Linux); Quit from the tray icon. Takes effect on next launch.'),), web=False),
    Row('system', 'Your data', (), web=True),
    Row('server', 'Log server', (), web=True),
    Row('server', 'Community stats', (Bool('community_heartbeat', 'Contribute to the anonymous daily-active-meters count (on by default)'),
         Bool('community_contribute_character', "Share your build's point totals when you collect a character (on by default)")), web=False),
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
    Row('pettracker', 'Pet Tracker', (), web=True),
    Row('pettracker', 'Use Pet Tracker', (Bool('pettracker_enabled', "Run Pet Tracker's capture with Aion 2 Calc (Windows; off by default)"),), web=False),
    Row('pettracker', 'Pet Tracker overlay', (Bool('pettracker_overlay', 'Show the Pet Tracker overlay while the game runs'),
         Choice('pettracker_overlay_style', 'Style', (('app', "in Aion 2 Calc's own window"), ('pettracker', "as Pet Tracker's own window")), str)), web=False),
    Row('pettracker', 'Pet Tracker folder', (), web=True),
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
    Row('meter', 'Combat records', (Bool('meter_reset_after_battle', "Clear the live meter after a battle ends (off by default — the last fight's numbers stay on the overlay until the next fight, a wipe or a manual clear)"),
         Bool('meter_reset_on_boss_start', 'Reset the live meter when a boss fight starts (on by default — a boss, mini-boss, field boss or world boss pull clears the overlay so each fight shows fresh)'),
         Bool('meter_save_records', 'Save combat records automatically (write each session to the logs folder)'),
         Bool('meter_upload_before_prune', 'Upload a recording to the server before auto-delete reclaims it (on by default)'),
         Bool('meter_autostart', 'Start the meter automatically when the app launches (on by default — it runs in the background and the overlay shows data without pressing Start)'),
         Bool('meter_show_server_name', "Show each player's server (world) name next to their name on the live meter (off by default; needs the region/world list — use Retry region detection if it hasn't resolved)"),
         Bool('meter_auto_upload', 'Upload every recording of this session that is not on the configured server yet when the meter stops (from the app, the overlay or its hotkey) or the app quits (on by default)'),
         Bool('meter_catch_up_uploads', 'Catch up at the next launch: upload recordings from the last 7 days that are still not on the server (needs the option above; on by default)'),
         Bool('meter_upload_per_fight', 'Upload the recording each time a boss fight ends, so its kill, standings and timers reach the community during play (needs automatic uploads; on by default)'),
         Bool('meter_report_boss_kills', 'Report open-world boss kills to the community world-boss feed (anonymous per-install; shown only once two installs agree; on by default)'),
         Bool('meter_report_enemy_hp', "Share enemy HP data to improve everyone's HP bars (on by default)"),
         Bool('share_gathering', 'Share gathering and drop data for the community drop rates (on by default)'),
         Bool('meter_report_diagnostics', 'Share anonymous diagnostics to improve the catalog and catch meter bugs (on by default)'),
         Bool('meter_show_dummy_parse', 'Show a training-dummy parse readout when hitting a dummy'),
         Number('meter_reset_delay', 'Reset delay', 1, 120, 's'),
         Number('meter_max_records', 'Keep up to', 1, 500, 'past combats'),
         Number('meter_log_cache_mb', 'Keep the logs folder under', 0, 1048576, 'MB'),
         Number('meter_dummy_record_seconds', 'Training-dummy parse window', 5, 3600, 's')), web=False),
    Row('backup', 'Customization profiles', (), web=True),
    Row('backup', 'Settings backup', (), web=True),
    Row('overlay', 'Overlay colors & fonts', (Bool('overlay_glow', 'Text glow'),
         Number('overlay_font_scale', 'Text size', 80, 160, '%')), web=True),
    Row('overlay', 'Overlay text effects & per-element fonts', (), web=True),
    Row('overlay', 'Overlay background', (), web=True),
    Row('overlay', 'Overlay look presets', (), web=True),
    Row('overlay', 'Hotkeys (Windows)', (), web=True),
    Row('appearance', 'Combat class colors', (), web=True),
    Row('system', 'Storage maintenance', (), web=True),
    Row('system', 'Updates', (Bool('auto_update', 'download new versions in the background'),
         Bool('update_on_close', 'install a downloaded update when the app closes')), web=False),
    Row('system', 'Version', (), web=True),
    Row('system', 'Patch notes', (), web=True),
    Row('system', 'Community', (), web=True),
    Row('system', 'Stop the app', (), web=True),
)
