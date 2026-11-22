"""The native Settings page's words and figures (0.2.475), as pages/settings.js writes them: its tabs, and the rows of
App & data with their notes, the game database's line, the storage maintenance's table, the version and its update,
and the patch notes. The page (settings_page.py) draws them.
"""
from __future__ import annotations

import math
import re

from . import theme
from .combat import js_text
from .news import when
from .results import _dict, _list, _truthy, n0

#: The web page's tabs (``data-settab``), in its order: one group of rows shows at a time.
TABS = (("appearance", "Appearance"), ("overlay", "Overlay"), ("pettracker", "Pet Tracker"), ("meter", "Meter"),
        ("server", "Server"), ("backup", "Profiles & backup"), ("system", "App & data"))
TAB_KEY = "a2-settab"                       # the tab chosen last, kept as the web page keeps it in its browser


def chosen_tab(stored) -> str:
    """The tab to show: the one chosen last, else Appearance (``a2-settab``)."""
    return stored if isinstance(stored, str) and stored in dict(TABS) else "appearance"


#: Every row in the web page's order (its ``.setrow``s): each tab shows its own in this order.
ROW_ORDER = (
    ("appearance", "Theme"), ("appearance", "Accent colour"), ("system", "Native interface"),
    ("system", "Open as its own window"), ("system", "Text size"), ("system", "Performance mode"), ("system", "Language"),
    ("system", "Page at launch"), ("system", "My Character at launch"), ("system", "Collapse to tray"),
    ("system", "Your data"), ("server", "Log server"), ("server", "Community stats"), ("overlay", "Live meter overlay"),
    ("overlay", "Hidden Cube radar"), ("pettracker", "Pet Tracker"), ("pettracker", "Use Pet Tracker"),
    ("pettracker", "Pet Tracker overlay"), ("pettracker", "Pet Tracker folder"), ("overlay", "In-game (RTSS)"),
    ("overlay", "Streaming (OBS / Discord)"), ("overlay", "Overlay layout"), ("meter", "Combat records"),
    ("backup", "Customization profiles"), ("backup", "Settings backup"), ("overlay", "Overlay colors & fonts"),
    ("overlay", "Overlay text effects & per-element fonts"), ("overlay", "Overlay background"),
    ("overlay", "Overlay look presets"), ("overlay", "Hotkeys (Windows)"), ("appearance", "Combat class colors"),
    ("system", "Game database"), ("system", "Storage maintenance"), ("system", "Updates"), ("system", "Version"),
    ("system", "Patch notes"), ("system", "Community"), ("system", "Stop the app"), ("system", "Author"))

SAVED = "Saved"
SAVED_NEXT_LAUNCH = "Saved · applies on next launch"

# ------------------------------------------------------------------ App & data
NATIVE = "open the app and the meter overlay in the native interface, drawn in Python instead of a browser"
NATIVE_NOTE = ("On by default since 0.2.426. Every page but Raid Planner and Builds is native so far: the meter overlay, "
               "the Live Meter page, Combat Logs with a log's own page and its movement replay, Build Planner, My "
               "Character, Gear & Advice, Saved Results, Timers, Maps, Database, Crafting, Gathering, Pet Tracker, News, "
               "Settings (in part) and Account. Raid Planner, Builds, the movement replay's Raid Planner file and the "
               "rest of Settings open in the web interface from the app's window. It takes effect the next time the app "
               "or the overlay opens. The app comes with what it needs, and installs it with its other requirements when "
               "run from source.")
APP_WINDOW = "start in a separate app window (Edge or Chrome) instead of a browser tab; closing it stops the app"
APP_WINDOW_NOTE = ("The window opens at 1920×1080, or as large as the screen allows when it is smaller, centred; it is "
                   "not maximized, so you can place and size it.")
TEXT_LABEL = "Size of the app's text"
TEXT_SCALES = (70, 80, 90, 100, 110, 120, 130, 140, 150)
TEXT_NOTE = ("Scales every word in the app, and the layout with it, like the browser's zoom; 100% is the size the app "
             "ships with. The overlay's text has its own size under Live meter overlay.")
#: the native window cannot be zoomed while it is open: it takes the size as it opens (``QT_SCALE_FACTOR``)
TEXT_NATIVE = "This window takes a new size the next time it opens."
PERFORMANCE = "Lighter on a low-spec PC"
OFF_BY_DEFAULT = "(off by default)"
PERFORMANCE_NOTE = ("The live meter works out its numbers every second instead of twice a second and records where "
                    "everyone stands once a second; the overlay refreshes every second and holds still in between (no "
                    "live-ticking numbers, frame counter, animations or colour effects that move), and the app's pages "
                    "stop animating. Every reading stays as accurate; it only updates less often. Takes effect within a "
                    "few seconds, and from the next fight for the movement replay.")
LANGUAGE_NOTE = ("The app's buttons, headings and short texts; the game's names, long explanations, the overlay and the "
                 "reports stay in English. The same choice as at the top of the page.")
#: the language is the web interface's own (its words, kept in its browser): the native window is in English for now
LANGUAGE_WEB = "The native window is in English for now; the language is chosen on the web Settings page."
OPEN_WEB_SETTINGS = "Open the web Settings page"
LAUNCH_LABEL = "Open the app on"
#: The pages the app can open on at launch (app.js ``LAUNCH_PAGES``): the navigation's, but Account.
LAUNCH_PAGES = (("meter", "Live Meter"), ("combat", "Combat Logs"), ("raid", "Raid Planner"), ("planner", "Build Planner"),
                ("builds", "Builds"), ("character", "My Character"), ("gear", "Gear & Advice"),
                ("history", "Saved Results"), ("timers", "Timers"), ("maps", "Maps"), ("database", "Database"),
                ("crafting", "Crafting"), ("gathering", "Gathering"), ("pets", "Pet Tracker"), ("news", "News"),
                ("settings", "Settings"))
LAUNCH_NOTE = ("The page the app shows when it starts, and when the tray icon or the Open-app hotkey brings it back. "
               "Links to the other pages work as before.")
CHARACTER_OPEN = "Show the character you opened last when My Character opens"
CHARACTER_NOTE = ("With My Character as the page at launch, the app opens straight on your character: the newest of the "
                  "characters imported before, from the snapshot saved at its last import, so it shows at once and "
                  "without the official site.")
CHARACTER_REFRESH = ("Refresh that character from the official site when the app opens, instead of showing the last "
                     "snapshot")
CHARACTER_REFRESH_DEFAULT = "(off by default; needs the setting above)"
TRAY = ("keep running in the system tray when the window is closed (Windows, macOS, Linux); Quit from the tray icon. "
        "Takes effect on next launch.")
#: Your data's buttons (``data-open``): the app opens each folder.
FOLDERS = (("data", "Open folder"), ("logs", "Combat logs"), ("results", "Advice & results"))

# the game database
CHECK_NOW = "Check now"
REINDEX = "Re-index cached icons"
EXPORT_IMAGES = "Export image coverage"
RETRY_IMAGES = "Retry images"
SYNCING = "Checking for game updates"
REINDEXING = "Re-indexing cached official references…"
REINDEX_RUNNING = "Re-indexing…"
REINDEXED_TOAST = "Cached icon re-index complete"
COLLECTING = "Collecting image references…"
IMAGES_FILE = "aion2-asset-coverage.json"
RETRIED = "Image retries enabled. Reopen the affected view to reload its images."


def _times_1000(at):
    """``at * 1000`` as JavaScript reckons it: nothing (``undefined``) gives NaN, ``null`` gives 0."""
    if at is None:
        return 0
    if isinstance(at, bool):
        return int(at) * 1000
    if isinstance(at, (int, float)):
        return at * 1000
    try:
        return float(str(at).strip() or 0) * 1000
    except ValueError:
        return math.nan


def database_line(status) -> str:
    """The game database's line: its items and when it last updated (``s.db``)."""
    db = _dict(_dict(status).get("db"))
    last = db.get("last_sync")
    if _truthy(last):
        moment = _times_1000(last.get("at")) if isinstance(last, dict) and "at" in last else math.nan
        shown = when(moment) if isinstance(moment, (int, float)) and math.isfinite(moment) else "—"
    else:
        shown = "never"
    return f"{n0(db.get('items'))} items · last update {shown}"


def reindexed(r) -> str:
    """What re-indexing the cached icons did (``/api/assets/reindex``)."""
    r = _dict(r)
    return (f"Re-indexed {n0(r.get('profiles'))} profiles · {n0(r.get('references'))} references examined · "
            f"{n0(r.get('skipped'))} skipped. Reopen the affected view to reload icons.")


def reindex_failed(why: str) -> str:
    return f"Could not re-index icons: {why}"


def images_saved(path: str) -> str:
    """The image coverage saved: where (the web page leaves it in the Downloads folder)."""
    return f"Image coverage saved: {path}"


def images_failed(why: str) -> str:
    return f"Could not export image coverage: {why}"


# storage maintenance
INSPECT = "Inspect cache / updates"
CLEAN_CACHE = "Clean old disposable cache"
CLEAN_UPDATES = "Clean old update files"
MAINTENANCE_NOTE = ("Web/comparison cache: 7 days; images: 30 days. Updates retain two packages, helpers for 7 days, and "
                    "at least five logs / 30 days. Active or uninspectable helpers are preserved. Cache images may need "
                    "downloading again.")
INSPECTING = "Inspecting managed cache and update files…"
CLEANING = "Cleaning eligible files…"
EXTERNAL_CACHE = "An external web cache is configured; this tool leaves it untouched."
SCAN_LIMIT = "Scan limit reached; counts are lower bounds."
MAINTENANCE_COLUMNS = ["Category", "Files", "MiB", "Oldest (days)", "Cache cleanup eligible"]


def _mib(value) -> str:
    x = _js_number(value)
    return "NaN" if x is None else theme.fixed(x / 1048576, 2)


def _js_number(value):
    """A value as JavaScript's arithmetic reads it, or None where it gives NaN."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    if value is None:
        return 0.0
    try:
        return float(str(value).strip() or 0)
    except ValueError:
        return None


def maintenance(r) -> dict:
    """The managed cache and update files (``showMaintenance``): the note, the warnings, and a row per category."""
    r = _dict(r)
    rows = [[js_text(g.get("category")), js_text(g.get("files")), _mib(g.get("bytes")), js_text(g.get("oldest_days")),
             f"{js_text(g.get('eligible_files'))} files / {_mib(g.get('eligible_bytes'))} MiB"]
            for g in (_dict(group) for group in _list(r.get("groups")))]
    return {"note": js_text(r.get("note")), "external": _truthy(r.get("external_web_cache")),
            "truncated": _truthy(r.get("truncated")), "rows": rows}


def cleaned(r) -> str:
    """What a clean removed (``/api/maintenance`` with an action)."""
    r = _dict(r)
    kept = r.get("skipped") if _truthy(r.get("skipped")) else 0
    return f"Removed {js_text(r.get('deleted'))} files; {js_text(kept)} changed, active, locked or uninspectable files preserved."


# updates and the version
AUTO_UPDATE = "download new versions in the background"
UPDATE_ON_CLOSE = "install a downloaded update when the app closes"
UPDATES_NOTE = "A new version downloads quietly; a small bar at the bottom left shows its progress, then offers Update now."
UPDATE_NOW = "Update now"
RELEASE_NOTES = "release notes"
CHECKING = "· checking for updates…"
OPENING_INSTALLER = "Opening the installer…"
DOWNLOADING = "Downloading and checking the installer…"
CLOSING = "Aion 2 Calc is closing. The installer will open in a moment."
#: What the app says it did with Update now (``/api/update``'s status).
INSTALL_WORDS = {
    "launch-failed": "The installer helper did not start. Your app is still running; open the updates folder to run the "
                     "setup file.",
    "applying": "installing — the app will restart",
    "launching": "closing the app, then opening the installer — follow its prompts",
    "downloaded": "downloaded — open your data folder’s “updates” to run it",
    "download-failed": "download failed",
    "check-failed": "could not reach GitHub for the update; try again in a minute",
    "up-to-date": "already up to date",
}


def install_words(status) -> str:
    """Update now's outcome in words, or the status itself when it is none of them."""
    return INSTALL_WORDS.get(status, js_text(status)) if isinstance(status, str) else js_text(status)


def update_state_text(state) -> str:
    """The line for the last release check (``updateStateText``): a failed check is said, never "up to date"."""
    st = _dict(state)
    if _truthy(st.get("checking")):
        return CHECKING
    if _truthy(st.get("error")):
        return f"· could not check for updates ({js_text(st['error'])}); trying again shortly"
    if _truthy(st.get("checked_at")):
        at = _times_1000(st["checked_at"])
        clock = when(at) if isinstance(at, (int, float)) and math.isfinite(at) else "—"
        return f"· up to date (checked {clock[11:] if len(clock) > 11 else clock})"
    return "· up to date"


def check_failed(why: str) -> str:
    return f"· could not check: {why}"


def version(status) -> dict:
    """The Version row: this copy's version, and a newer one when there is (downloaded or available, with its notes)."""
    s = _dict(status)
    update = s.get("update")
    if _truthy(update):
        u = _dict(update)
        ready = _dict(s.get("update_download")).get("state") == "ready"
        return {"version": js_text(s.get("version")), "update": {
            "words": f"· version {js_text(u.get('version'))} {'downloaded' if ready else 'available'}",
            "url": js_text(u.get("url")), "ready": ready}, "state": ""}
    return {"version": js_text(s.get("version")), "update": None, "state": update_state_text(s.get("update_state"))}


# patch notes, the community, stopping the app, the author
WHATS_NEW = "What's new in this version"
ALL_NOTES = "All patch notes on GitHub"
PATCH_NOTES_URL = "https://github.com/sam-t-anderson/Aion-2-tools/releases"
PATCH_NOTE = "After an update the app shows the new version's notes once; this shows them again."
NO_NOTES = "This copy of the app does not hold this version's notes."
CLOSE = "Close"
DISCORD_URL = "https://discord.gg/9y6zkUyvBv"
DISCORD = "Join the aion2calc Discord"
DISCORD_REST = " — questions, builds and help"
QUIT = "Quit aion2calc"
ASK_QUIT = "Stop aion2calc? Start it again from the Start menu or desktop shortcut."
AUTHOR = "Spirited - Zikel : Asmodian  |  Legion: WhaleWatch"


def notes_title(version_) -> str:
    """The patch notes' heading (patch-notes.js)."""
    return f"What's new in Aion 2 Calc {js_text(version_)}"


def patch_notes(data) -> dict:
    """The notes to show (``/api/patch-notes``): the version, each version's notes (its title, version and HTML),
    newest first, and the link to all of them."""
    d = _dict(data)
    notes = [{"title": js_text(n.get("title")), "version": js_text(n.get("version")), "html": js_text(n.get("html"))}
             for n in (_dict(x) for x in _list(d.get("notes")))]
    return {"title": notes_title(d.get("version")), "notes": notes, "all": js_text(d.get("all")),
            "show": _truthy(d.get("show"))}


def parse_int(value) -> int | None:
    """``parseInt(value, 10)``: the whole number a value's text starts with, or None (NaN)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    text = js_text(value).strip()
    match = re.match(r"[+-]?\d+", text)
    return int(match.group(0)) if match else None


def text_scale(ui) -> int:
    """The text size shown: the app's (``parseInt(...) || 100``), the first size when it is none of the choices, as a
    list shows its first when none is chosen."""
    number = parse_int(_dict(ui).get("app_text_scale")) or 100
    return number if number in TEXT_SCALES else TEXT_SCALES[0]


def launch_page(ui) -> str:
    """The page at launch shown: the app's (``|| "meter"``), the first page when it is none of them."""
    value = _dict(ui).get("app_default_page")
    value = value if _truthy(value) else "meter"
    return value if value in dict(LAUNCH_PAGES) else LAUNCH_PAGES[0][0]
