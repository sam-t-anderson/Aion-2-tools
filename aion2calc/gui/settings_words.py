"""The native Settings page's words and figures (0.2.475), as pages/settings.js writes them: its tabs, and the rows of
App & data with their notes, the game database's line, the storage maintenance's table, the version and its update,
and the patch notes; since 0.2.476 the Meter tab's Combat records and the Server tab's log server and community stats;
since 0.2.477 the Pet Tracker tab; since 0.2.478 the Overlay tab's first half, described as the rows' controls in their
order (``LIVE_OVERLAY``, ``RTSS``, ``LAYOUT``); since 0.2.479 the Hidden Cube radar's words and the hotkeys' actions.
The page (settings_page.py) draws them.
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


# ------------------------------------------------------------------ Meter: Combat records (0.2.476)
#: The row's checkboxes in its order: the setting, its words, the muted part, whether it is on unless false (else on
#: only when true), and what is said once it is saved.
RECORD_CHECKS = (
    ("meter_reset_after_battle", "Clear the live meter after a battle ends (off by default — the last fight's numbers "
     "stay on the overlay until the next fight, a wipe or a manual clear)", "", False, None),
    ("meter_reset_on_boss_start", "Reset the live meter when a boss fight starts (on by default — a boss, mini-boss, "
     "field boss or world boss pull clears the overlay so each fight shows fresh)", "", True, None),
    ("meter_save_records", "Save combat records automatically (write each session to the logs folder)", "", True,
     "Saved · applies to the next capture"),
    ("meter_upload_before_prune", "Upload a recording to the server before auto-delete reclaims it (on by default)", "",
     True, None),
    ("meter_autostart", "Start the meter automatically when the app launches (on by default — it runs in the background "
     "and the overlay shows data without pressing Start)", "", True, SAVED_NEXT_LAUNCH),
    ("meter_show_server_name", "Show each player's server (world) name next to their name on the live meter",
     "(off by default; needs the region/world list — use Retry region detection if it hasn't resolved)", False, None),
    ("meter_auto_upload", "Upload every recording of this session that is not on the configured server yet when the "
     "meter stops (from the app, the overlay or its hotkey) or the app quits (on by default)", "", True, None),
    ("meter_catch_up_uploads", "Catch up at the next launch: upload recordings from the last 7 days that are still not "
     "on the server (needs the option above; on by default)", "", True, None),
    ("meter_upload_per_fight", "Upload the recording each time a boss fight ends, so its kill, standings and timers "
     "reach the community during play (needs automatic uploads; on by default)", "", True, None),
    ("meter_report_boss_kills", "Report open-world boss kills to the community world-boss feed",
     "(anonymous per-install; shown only once two installs agree; on by default)", True, None),
    ("meter_report_enemy_hp", "Share enemy HP data to improve everyone's HP bars (on by default)", "", True, None),
    ("share_gathering", "Share gathering and drop data for the community drop rates (on by default)", "", True, None),
    ("meter_report_diagnostics", "Share anonymous diagnostics to improve the catalog and catch meter bugs (on by "
     "default)", "", True, None),
    ("meter_show_dummy_parse", "Show a training-dummy parse readout when hitting a dummy", "", True, None),
)
#: The numbers checked before they are saved (``saveRecNum``): the setting, its words before and after the field,
#: its least and most, and the value shown when the app has none.
RECORD_NUMBERS = {
    "meter_reset_delay": ("Reset delay", "s", 1, 120, 5),
    "meter_max_records": ("Keep up to", "past combats", 1, 500, 20),
    "meter_dummy_record_seconds": ("Training-dummy parse window", "s", 5, 3600, 60),
}
LOG_CACHE = ("Keep the logs folder under", "MB", 0, 1048576, 1024)
LOG_CACHE_NOTE = ("A long session writes many rollover parts; when the logs folder passes this size the oldest "
                  "recordings are deleted automatically to make room (the one being captured is never deleted). "
                  "Default 1024 MB (1 GB); set 0 to never auto-delete.")
PRUNE_NOTE = ("When the logs folder is over its size cap (above) and a recording is about to be deleted to make room, "
              "upload it first so its data — boss kills included — isn't lost. Only matters while auto-delete is on and "
              "a share server is set; it uploads at your upload visibility (Log server, public unless you change it), "
              "like the stop/quit auto-upload.")
PER_FIGHT_NOTE = ("Sends the current recording once a boss, mini-boss, field or world boss has died and the fight has "
                  "paused, at most every 30 seconds; the share server updates the same log in place, so the upload at "
                  "Stop and these are one log, never duplicates.")
BOSS_KILLS_NOTE = ("Anonymous and opt-in: sends only the boss, server and kill time (no account, character, log or IP). "
                   "Two different installs must report the same kill before it shows, so the public world-boss "
                   "availability feed stays corroborated.")
ENEMY_HP_NOTE = ("Anonymous and opt-out: when an enemy dies, sends only how much damage it took to die, its NPC id and "
                 "the game build (no account, character, log or IP). The server pools these across players — including "
                 "party kills — to learn each enemy's real HP so the meter can show an accurate HP %. The more players "
                 "share, the better the bars for all.")
GATHERING_NOTE = ("Opt-out: sends what each gather gave (the item, how many, whether it came up a better grade or "
                  "failed, the kind of node, the map and dungeon, and the node's place in the world) and what each "
                  "dungeon reward cube held, with an anonymous per-install key, so the Gathering page can show "
                  "everyone's drop rates and, in time, where each kind of node grows. Your character's name goes with it "
                  "only while the app is signed in to your account, so your own Gathering page on the website can list "
                  "it; nobody else sees it. The app keeps its own gathering log either way.")
DIAGNOSTICS_NOTE = ("Anonymous and opt-out: after a fight, sends only the NPC/skill ids the app couldn't name yet (so new "
                    "content gets added to the catalog) and a few capture-health counters like rollover and "
                    "dropped-packet totals (so meter bugs such as a mid-fight reset show up across players). No account, "
                    "character, combat log or IP — just ids, small numbers, the game build and region.")
RECORDS_NOTE = ("Applies to the live meter and overlay. A cleared battle's details stay available in the segment list "
                "until replaced.")


def _js_number_or_nan(value) -> float:
    """``Number(value)``: JavaScript's number for a value, NaN where it has none."""
    x = _js_number(value)
    return math.nan if x is None else x


def record_number(ui, key: str) -> int:
    """A checked number's value shown (``Number(ui[key]) || fallback``)."""
    x = _js_number_or_nan(_dict(ui).get(key)) if key in _dict(ui) else math.nan
    if math.isnan(x) or x == 0:
        return RECORD_NUMBERS[key][4]
    return int(x) if float(x).is_integer() else int(x)


def log_cache(ui) -> int:
    """The logs folder's cap shown (``Number.isFinite(+ui.meter_log_cache_mb) ? ... : 1024``)."""
    ui = _dict(ui)
    x = _js_number_or_nan(ui.get("meter_log_cache_mb")) if "meter_log_cache_mb" in ui else math.nan
    return int(x) if math.isfinite(x) else LOG_CACHE[4]


def number_check(text, low: int, high: int) -> tuple[int | None, str]:
    """A number as typed (``saveRecNum``): the whole number to save, or the words saying what it must be."""
    n = parse_int(text)
    if n is None or n < low or n > high:
        return None, f"Enter a whole number from {low} to {high}."
    return n, ""


def log_cache_value(value) -> int:
    """The logs folder's cap as saved: rounded and kept between 0 and 1048576 MB."""
    x = _js_number_or_nan(value)
    x = 0 if math.isnan(x) else x
    return max(0, min(1048576, int(math.floor(x + 0.5))))


def log_cache_saved(value: int) -> str:
    return f"Saved · logs kept under {value} MB" if value else "Saved · auto-delete off"


# ------------------------------------------------------------------ Server: Log server and Community stats (0.2.476)
SERVER_PLACEHOLDER = "https://logs.example.com"
KEY_SAVED = "key saved"
KEY_OPTIONAL = "upload key (optional)"
VISIBILITIES = (("public", "public"), ("unlisted", "unlisted"), ("legion", "legion only"), ("private", "private"))
VISIBILITY_LABEL = "Who can see your uploads"
VISIBILITY_TIP = ("Public uploads are listed in the community logs and count in the rankings; unlisted ones open only "
                  "with their link; legion only ones open for the members of your legions (signed in, Account); private "
                  "ones need the secret link")
SAVE = "Save"
CHECK_SERVER = "Check saved server"
DEFAULT_SERVER = "Using the community default server. Enter your own above to override it."
SAVED_CHECKING = "saved · checking…"
CHECKING_SERVER = "Checking saved server runtime…"
HEARTBEAT = "Contribute to the anonymous daily-active-meters count (on by default)"
HEARTBEAT_NOTE = ("Once a day the app tells the configured log server that a meter ran, so the community can see how "
                  "many are active. It sends only an anonymous token that rotates every day (it can't be traced to you or "
                  "linked across days), the date, and the app version — never your name, character, server, IP or any "
                  "combat data. Uncheck to opt out.")
CONTRIBUTE = "Share your build's point totals when you collect a character (on by default)"
CONTRIBUTE_NOTE = ("When you collect a character in My Character, send its spent skill, stigma and Daevanion point totals "
                   "to the community \"highest observed build points\" so the shared budgets stay current. Anonymous: "
                   "only the class, region, game version and the three point totals — never your name, character, "
                   "server, IP or gear. Running Optimize already shares these; this adds the same from a plain collect. "
                   "Uncheck to opt out.")


def server_form(server) -> dict:
    """The Log server's fields as the page opens (``srv``): the address and its hint, the key's hint, the visibility,
    and whether the community default is in use."""
    s = _dict(server)
    default = _truthy(s.get("is_default")) and _truthy(s.get("url"))
    return {"url": "" if _truthy(s.get("is_default")) else js_text(s.get("url")) if _truthy(s.get("url")) else "",
            "placeholder": f"{js_text(s['url'])} (default)" if default else SERVER_PLACEHOLDER,
            "key": KEY_SAVED if _truthy(s.get("has_key")) else KEY_OPTIONAL,
            "visibility": js_text(s.get("visibility")) if _truthy(s.get("visibility")) else "public",
            "default": default}


def server_versions(r) -> str:
    """The server's own versions after a check (``serverVersionText``)."""
    software = _dict(_dict(r).get("software"))
    if _truthy(software.get("server")) or _truthy(software.get("analyzer")):
        server = js_text(software["server"]) if _truthy(software.get("server")) else "not reported"
        analyzer = js_text(software["analyzer"]) if _truthy(software.get("analyzer")) else "not reported"
        return f" · server {server} · analyzer {analyzer}"
    return " · runtime versions not reported by this server"


def saved_check(r) -> str:
    """What Save says once the app has probed the server it saved (``#ssave``)."""
    r = _dict(r)
    if _truthy(r.get("ok")):
        name = f" — {js_text(r['name'])}" if _truthy(r.get("name")) else ""
        return "saved · server reachable" + name + server_versions(r)
    detail = f" ({js_text(r['detail'])})" if _truthy(r.get("detail")) else ""
    return "saved · can't reach the server" + detail


def saved_unchecked(why: str) -> str:
    return f"saved · could not check: {why}"


def server_check(r) -> str:
    """What Check saved server says (``#scheck``)."""
    r = _dict(r)
    if _truthy(r.get("ok")):
        return "Server reachable" + server_versions(r)
    return "Check failed: " + (js_text(r["detail"]) if _truthy(r.get("detail")) else "unavailable")


# ------------------------------------------------------------------ Pet Tracker (0.2.477)
PET_INTRO = ("Pet Tracker, by 0Fox2Give, shows your pet ranks and how many souls you still need while you farm. Aion 2 "
             "Calc can install it, run its capture, and show its pets in an overlay window of its own and on the ")
PET_PAGE = "Pet Tracker page"
CHECKING_PETS = "Checking Pet Tracker…"
PETS_UNSUPPORTED = "Pet Tracker runs on Windows only."
NOT_INSTALLED = "Not installed on this computer."
INSTALL_PETS = "Install Pet Tracker"
PET_INSTALL_NOTE = ("It downloads Pet Tracker's official installer and starts it only once it matches the release its "
                    "publisher signed.")
USE_PETS = "Run Pet Tracker's capture with Aion 2 Calc"
WINDOWS_OFF = "(Windows; off by default)"
USE_PETS_NOTE = ("It starts with the app, before you log into your character, so your collection syncs at login. When the "
                 "app quits it stops too, unless Pet Tracker's own window is open and still using it.")
PET_OVERLAY = "Show the Pet Tracker overlay while the game runs"
PET_WINDOW_LABEL = "Which window"
PET_WINDOWS = (("app", "in Aion 2 Calc's own window"), ("pettracker", "as Pet Tracker's own window"))
PET_OVERLAY_NOTE = ("Aion 2 Calc's window is a separate overlay with its own Lock, Hide and opacity, and it remembers where "
                    "you put it. While it is open, a running Pet Tracker's own overlay is hidden, so one shows, not two; it "
                    "comes back when the window closes. Pet Tracker's own window adds Find a pet, farming maps and the "
                    "Black Cloud Merchant list; if Pet Tracker started minimized, show it once from its tray icon. A hotkey "
                    "can show and hide either (Overlay → Hotkeys).")
PET_FOLDER_LABEL = "Pet Tracker folder"
PET_FOLDER_HINT = "Found automatically"
PET_FOLDER_NOTE = ("Only for a copy of Pet Tracker unpacked in a folder of your own (its portable ZIP). Leave it empty to "
                   "use the installed one.")
PET_BUSY = ("finding", "downloading", "installing", "started")     # an install under way: read again every 2 s
PET_ENABLED_READ_MS = 800                                          # after Use Pet Tracker is saved, read it again


def pet_status(state) -> dict:
    """Pet Tracker's line in Settings (``ptStatus``): whether it runs here, its install and how it is doing, or its
    install button with what the install is doing; a newer Pet Tracker's notice; whether to read it again soon."""
    from .pets_page import setup_text, status_line, update_notice
    s = _dict(state)
    setup = _dict(s.get("setup"))
    busy = setup.get("status") in PET_BUSY
    if not _truthy(s.get("supported")):
        return {"text": PETS_UNSUPPORTED, "install": None, "setup": "", "notice": None, "busy": busy}
    if _truthy(s.get("installed")):
        installed = _dict(s["installed"])
        version = f": version {js_text(installed['version'])}" if _truthy(installed.get("version")) else ""
        return {"text": f"Installed{version}, in {js_text(installed.get('folder'))}. {status_line(s)[0]}",
                "install": None, "setup": "", "notice": update_notice(s), "busy": busy}
    return {"text": NOT_INSTALLED, "install": not busy or setup.get("status") == "started",
            "setup": setup_text(s.get("setup")), "notice": None, "busy": busy}


# ------------------------------------------------------------------ Overlay, first part (0.2.478)
#: How a row's controls read the app's value, as the web page's template writes them: ``on`` ``!== false``, ``true``
#: ``=== true``; a number ``finite`` (``Number.isFinite(+v) ? +v : d``) or ``or`` (``Number(v) || d``).
SAVED_RELAUNCH_OVERLAY = "Saved · reopen the overlay to apply"
SAVED_OPEN_OVERLAY = "Saved · applies to the open overlay within 10s"
COULD_NOT_SAVE_OVERLAY = "Could not save overlay preference: {}"
#: The overlay's animated row effects (``OVERLAY_COSMETICS``).
COSMETICS = (("none", "None"), ("gold", "Gold: a turning gold frame and a diamond"),
             ("rainbow", "Rainbow: a glowing rainbow name"), ("ember", "Ember: a pulsing fire glow"),
             ("frost", "Frost: an icy sheen"), ("aether", "Aether: a violet and teal aurora"),
             ("starlight", "Starlight: twinkling stars"))


def check(key, words, muted="", rule="on", saved=SAVED, tip="", indent=0):
    return ("check", key, words, muted, rule, saved, tip, indent)


def note(text, indent=0, rich=False):
    return ("note", text, indent, rich)


def number(key, before, after, low, high, fallback, shown="finite", save="clamp", step=1, muted="", name=""):
    """A number field: ``save`` ``clamp`` (kept within its limits, ``parseInt(...) || fallback``, then "Saved") or
    ``checked`` (``saveLayoutNum``: checked and said beside its row). ``name`` names a field without words before it."""
    return ("number", key, before, after, low, high, fallback, shown, save, step, muted, name or before or after)


def select(key, before, options, fallback):
    return ("select", key, before, tuple(options), fallback)


def row(*controls, indent=0, message=""):
    return ("row", controls, indent, message)


LIVE_OVERLAY = (
    check("overlay_open_on_app_start", "Open the overlay when the app starts (on by default)", saved=SAVED_NEXT_LAUNCH),
    note("The overlay opens with the app and waits for the game; it still follows the AION 2 window when that appears."),
    check("overlay_on_start", "Show overlay when starting the live meter", saved="revert"),
    note("Also available beside Start on the Live Meter page."),
    check("overlay_close_on_stop", "Close the overlay when I stop the meter (off by default — the overlay stays up "
          "showing the last fight, and its own Stop button never closes it)", rule="true"),
    check("overlay_show_contribution", "Show your contribution (your share of the encounter's damage)"),
    check("overlay_show_target", "Show the current target and each player's DPS to it"),
    check("overlay_show_deaths", "Mark party members who are dead (row shows DEAD until they recover)"),
    check("overlay_show_enemy_hp", "Show the current target's remaining HP as a percentage and bar (only when the game "
          "reports it). The game's internal HP value is on a much larger scale than damage numbers, so it is shown as a "
          "percentage, not a raw number that won't match your damage.", rule="true"),
    check("overlay_show_ttk", "Show estimated time-to-kill for the current target, as a number and a progress bar (from "
          "the target's observed HP-decline rate)", rule="true"),
    check("overlay_show_break_gauge", "Show the current target's break (stagger) gauge, as a readout and a bar",
          "(bosses and elites carry one; off by default)", rule="true"),
    check("overlay_show_cooldowns", "Show a strip of your skills on cooldown, each counting down", OFF_BY_DEFAULT,
          rule="true"),
    row(number("overlay_cooldowns_min_s", "Shortest cooldown shown", "s", 1, 120, 3),
        number("overlay_cooldowns_max", "Icons", "", 1, 16, 8),
        select("overlay_cooldowns_position", "Position", (("bottom", "Below the meter"), ("top", "Above the player rows")),
               "bottom"), indent=22),
    note("Uses the cooldown the game sends with each of your casts, so your cooldown reduction is already included and "
         "there is nothing to set up. It only knows skills you have used since Start. A skill lights up as it comes off "
         "cooldown, and an open chain-skill window shows first. If a proc resets a cooldown, the strip catches up on your "
         "next cast.", indent=22),
    check("overlay_show_combat_power", "Show your combat power beside your name (when the game reports it)"),
    check("overlay_show_odyle", "Show your Odyle Energy on the overlay and the Live Meter page", "(on by default)",
          tip="The game's own count, sent when you enter the world, at every zone load and whenever it changes"),
    check("overlay_show_shugo_keys", "Show your Shugo Festival keys on the overlay and the Live Meter page",
          "(on by default)", tip="The game's own count of your Shugo Festival Reward Keys, sent with the same counters "
          "as Odyle Energy"),
    check("overlay_show_nightmare_tickets", "Show your Nightmare tickets on the overlay and the Live Meter page",
          "(on by default)", tip="The game's own count of your Nightmare tickets, sent with the same counters as Odyle "
          "Energy"),
    check("overlay_show_weekly_runs", "Show the dungeon's weekly runs left on the overlay and the Live Meter page",
          "(on by default)", tip="The game's own count of the runs you have left this week for the dungeon you are in. "
          "The meter learns which of the game's counters is a dungeon's the first time a run there is rewarded, then "
          "shows it whenever you are inside"),
    check("overlay_show_community_rank", "Show your community rank for your last uploaded fight",
          "(needs auto-upload; off by default)", rule="true",
          tip="After a fight auto-uploads, show your community standing (e.g. “World Top 8%”) for that encounter "
          "beside your name"),
    check("overlay_live_community_rank", "Update the rank live after each fight", "(needs the rank badge on + a share "
          "server; uploads each ranked fight at your upload visibility; off by default)", rule="true",
          tip="While capturing, refresh your community-rank badge after each ranked fight by uploading it, instead of "
          "only when you press Upload"),
    check("overlay_show_events", "Show regional event notifications on the overlay",
          "(uses the region you pick on the Timers page; community forecast, on by default)",
          tip="Shows the next rift / Shugo / battlefield / field-boss windows for your region when one is active or "
          "within 15 minutes"),
    check("overlay_show_field_bosses", "Include observed field-boss timers in the event strip",
          "(kills recorded on your server and faction; on by default)",
          tip="Field and world bosses the live meter saw die on your server count down to their return in the event "
          "strip"),
    check("overlay_events_sound", "Play a sound when an event notification appears", OFF_BY_DEFAULT, rule="true",
          tip="Play a short chime when an event notification appears on the overlay"),
    ("sound",),
    check("overlay_plan_autoplay", "Auto-play a saved raid plan on the overlay's Plan tab when you fight the boss it is "
          "bound to, synced to the pull (on by default)"),
    note("Bind a plan to a boss in the Raid planner (set its Boss / NPC id). When the meter is in that fight, the Plan tab "
         "plays that plan at the encounter's elapsed time; otherwise it loops the latest plan as a preview."),
)
SOUND_UPLOAD = "Upload sound"
SOUND_TEST = "Test"
SOUND_DEFAULT = "Use default chime"
SOUND_SET = "Custom sound set (≤2s recommended)."
SOUND_BUILT_IN = "Built-in chime."
SOUND_TOO_BIG = "Sound must be 1 MB or smaller — keep it short (~2s)."
SOUND_UPLOADING = "Uploading…"
SOUND_SAVED = "Custom sound set. Use Test to hear it."
SOUND_CLEARED = "Using the built-in chime."
SOUND_READ_FAILED = "Could not read the file"
#: the native window has no audio player: Test plays the system's alert, as the native overlay does for an event
SOUND_NATIVE = "This window has no audio of its own: Test plays your system's alert, as the native overlay does."
SOUND_TYPES = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".webm": "audio/webm"}

RTSS = (
    check("rtss_enabled", "Draw the meter inside the game through RivaTuner Statistics Server",
          "(Windows; off by default; needs RTSS running with its on-screen display enabled)", rule="true"),
    row(number("rtss_rows", "Rows", "", 1, 24, 5),
        select("rtss_metric", "Metric", (("dps", "DPS"), ("hps", "HPS"), ("dtps", "Damage taken")), "dps"),
        select("rtss_style", "Style", (("plain", "Plain text"), ("colored", "Class colours (RTSS colour tags)")), "plain"),
        number("rtss_interval_ms", "Refresh", "ms", 100, 5000, 500, step=50), indent=22),
    ("rtss-status",),
    note("The app writes the meter text into RTSS's own shared memory (an OSD slot named Aion2Calc); RTSS draws it inside "
         "the game the way it draws its frame counter. Nothing is injected into or loaded by the game by this app; RTSS "
         "does its own hooking under its own terms. Position, font and size come from RTSS's settings. A first draft: "
         "please report what you see.", indent=22),
)
RTSS_UNKNOWN = "RTSS status unknown."
RTSS_READ_MS = 800                                  # after In-game (RTSS) is saved, its state read again


def rtss_status(state) -> str:
    """What RTSS is doing (``rtssStatus``)."""
    s = _dict(state)
    if not _truthy(s.get("supported")):
        return "RTSS output is available on Windows only."
    if not _truthy(s.get("enabled")):
        return "Off."
    if _truthy(s.get("connected")):
        return (f"Drawing in RTSS OSD slot {js_text(s.get('slot'))} (shared memory v{js_text(s.get('version'))}, "
                f"{js_text(s.get('updates'))} updates).")
    return js_text(s["error"]) if _truthy(s.get("error")) else "Waiting for RTSS…"


RTSS_UNAVAILABLE = "RTSS status unavailable."
STREAM_LABEL = "Overlay browser-source URL"
STREAM_COPY = "Copy URL"
STREAM_COPIED = "Copied — paste into an OBS Browser Source."
STREAM_NOTES = (
    "Add this as an <b>OBS / Streamlabs Browser Source</b> (it renders transparent) and composite it over your "
    "game-capture scene, then stream that scene to Discord — the overlay shows on your stream. To go through Discord "
    "<b>Go&nbsp;Live</b> directly instead, share your <b>whole screen</b> (not just the game window) so the always-on-top "
    "overlay is included.",
    "A game-<i>window</i>-only share will <b>not</b> show the overlay: it's a separate window layered on top, not part of "
    "the game's own frame, so a per-window capture never includes it (the same reason most meter overlays don't appear "
    "in window captures). Use a Browser Source or full-screen share.")

LAYOUT = (
    row(number("overlay_max_players", "Players shown", "", 1, 24, 8, shown="or", save="checked"),
        number("overlay_width", "Width", "px", 260, 800, 340, shown="or", save="checked"),
        number("overlay_height", "Height", "px", 0, 800, 0, shown="or", save="checked", muted="(0 = fit to contents)"),
        number("overlay_row_height", "Row height", "px", 14, 48, 22, shown="or", save="checked"), message="layout"),
    check("overlay_auto_expand", "Auto-expand to show every captured player (beyond the limit above)", rule="true"),
    check("overlay_only_in_combat", "Show the meter only during combat (collapse between pulls)", rule="true"),
    check("overlay_boss_only", "Boss damage only: count the damage dealt to bosses, mini-bosses, field and world bosses",
          "(leaves out trash and, in the Abyss, other players)", rule="true"),
    check("overlay_pvp_only", "Player (PvP) damage only: count the damage dealt to other players",
          "(with Boss damage only on too, bosses count as well)", rule="true"),
    row(select("overlay_name_mode", "Name display", (("name", "Character names"), ("class_number", "Class + party number"),
                                                     ("number", "Party number only")), "name")),
    check("overlay_long_names_scroll", "Scroll long names on hover", rule="true"),
    row(select("overlay_bar_style", "Bar style", (("flat", "Flat class colour"), ("gradient", "Gradient")), "flat")),
    row(select("overlay_bg_mode", "Background", (("card", "Whole card"),
                                                 ("top", "Top portion only (header, boss panel, Odyle lines)"),
                                                 ("none", "None: rows, bars and text alone over the game")), "card")),
    row(select("overlay_me_cosmetic", "My row's effect", COSMETICS, "none")),
    row(select("overlay_top_cosmetic", "Top row's effect", COSMETICS, "none")),
    note("The effects are free for everyone and hold still in performance mode. Click a player's name on the overlay for "
         "their details: totals, crit, front and back shares, their top skills and the buffs on them.", indent=14),
    check("overlay_bar_rounded", "Rounded bar corners", rule="true"),
    check("overlay_class_color_names", "Colour player names by class", rule="true"),
    check("overlay_row_stripes", "Zebra-stripe the player rows", rule="true"),
    check("overlay_class_swatch", "Show a class-colour swatch before each name", rule="true"),
    check("overlay_compact_rows", "Compact rows (hide the total & percent, keep the per-second rate)", rule="true"),
    check("overlay_rank_numbers", "Show rank numbers (1., 2., 3. …) before each name", rule="true"),
    check("overlay_highlight_me", "Highlight my own row (accent bar, so you can find yourself at a glance)", rule="true"),
    ("check-number", check("overlay_dps_interpolate", "Live-ticking DPS numbers (recompute between polls for a real-time "
                           "feel; on by default)", rule="true"),
     number("overlay_interpolate_ms", "", "ms", 50, 1000, 200, shown="or", save="checked", name="Live-ticking interval")),
    check("overlay_dps_graph", "Show a live DPS/HPS graph (a sparkline of the party total over the fight, from real "
          "per-poll readings)", rule="true"),
    check("overlay_show_fps", "Show the overlay's own render FPS (the game's FPS can't be read from capture)", rule="true"),
    check("overlay_click_through", "Click through the overlay — let the mouse pass through to the game, so the overlay "
          "never eats a click", "(Windows; the overlay's own buttons/sliders still work when you hover them)",
          rule="true", saved=SAVED_OPEN_OVERLAY),
    check("overlay_hover_interact", "With click-through on, rest the pointer on the overlay for 5 seconds to click "
          "anywhere on it", "(a ring fills in while it counts; clicks pass through again once the pointer leaves)",
          rule="true", saved=SAVED_OPEN_OVERLAY, indent=22),
    check("overlay_party_enabled", "Open a separate Party-DPS overlay (raid totals) alongside the meter", rule="true"),
    note("These need the overlay reopened to apply:"),
    check("overlay_always_visible", "Keep the overlay visible even when the game is not in focus (on by default; so "
          "clicking another overlay, the app window or a game popup never hides it)", saved=SAVED_RELAUNCH_OVERLAY),
    check("overlay_remember_position", "Remember where I drag the overlay and reopen it there, instead of following the "
          "game window (on by default, Windows; each overlay remembers its own spot — uncheck to follow the game window "
          "instead)", saved=SAVED_RELAUNCH_OVERLAY),
    check("overlay_resizable", "Resize the overlay by dragging its edges/corners", rule="true",
          saved=SAVED_RELAUNCH_OVERLAY),
    check("overlay_snap_edge", "Snap to the game window's edges", rule="true", saved=SAVED_RELAUNCH_OVERLAY),
    check("overlay_expand_up", "Expand upward (anchor the overlay near the bottom of the game window)", rule="true",
          saved=SAVED_RELAUNCH_OVERLAY),
    note("Applies to the live overlay; changes reach an open overlay within 10 seconds."),
)


def shown_number(ui, key: str, fallback: int, rule: str) -> int:
    """A number field's value from the app's (``finite``: ``Number.isFinite(+v) ? +v : d``; ``or``:
    ``Number(v) || d``; ``nullish``: ``v ?? d``, since 0.2.480)."""
    ui = _dict(ui)
    x = _js_number_or_nan(ui.get(key)) if key in ui else math.nan
    if rule == "finite":
        return int(x) if math.isfinite(x) else fallback
    if rule == "nullish":
        return fallback if ui.get(key) is None or not math.isfinite(x) else int(x)
    return int(x) if math.isfinite(x) and x else fallback


def clamped(value, low: int, high: int, fallback: int) -> int:
    """``Math.max(low, Math.min(high, parseInt(value, 10) || fallback))``."""
    return max(low, min(high, parse_int(value) or fallback))


def stream_url(base: str) -> str:
    """The overlay's address for a browser source: the app's own, then ``/overlay`` (``location.origin``)."""
    import urllib.parse
    parts = urllib.parse.urlsplit(base)
    return f"{parts.scheme}://{parts.netloc}/overlay"


# ------------------------------------------------------------------ Overlay: the Hidden Cube radar (0.2.479)
RADAR_ON = "Show where a Hidden Cube is around you and how near, from the jingle it plays"
RADAR_NOTE = ("The radar is its own small overlay window, opened beside the meter overlay while it is on, with its own "
              "opacity slider, Lock and Hide; it remembers where you drag it. After Hide, <b>Open overlay</b> or the "
              "radar's on/off hotkey brings it back.")
#: The learn steps' buttons and what each asks the app (``/api/radar``).
RADAR_LEARN = (("1. Learn the background", {"action": "learn", "kind": "background"}),
               ("2. Learn the cube, facing it", {"action": "learn", "kind": "cube"}),
               ("3. Learn the cube behind you", {"action": "learn", "kind": "cube", "facing": "behind"}),
               ("Learn a sound that is not a cube", {"action": "learn", "kind": "other"}))
RADAR_CANCEL = "Cancel"
RADAR_CLEAR = "Forget every sample"
RADAR_ASK_CLEAR = "Forget every learned sample: the backgrounds, the cube's sound and the sounds that are not a cube?"
RADAR_SENSITIVITY = "Sensitivity"
RADAR_UNKNOWN = "Radar status unknown."
RADAR_UNAVAILABLE = "Radar status unavailable."
RADAR_FORGET = "Forget"
RADAR_SAMPLES = "Learned sound samples"
RADAR_POLL_MS = 500                                  # read again while the Overlay tab shows it
RADAR_ENABLED_READ_MS = 400                          # after the radar is turned on or off
#: The radar's learn steps and their keys (hotkeys.py ``RADAR_DEFAULTS``) unless Settings → Hotkeys changed them.
RADAR_STEPS = {"radar_learn_background": "Ctrl+1", "radar_learn_cube": "Ctrl+2", "radar_learn_cube_behind": "Ctrl+3",
               "radar_learn_other": "Ctrl+4"}
RADAR_NEAR = ((0.8, "right here"), (0.5, "close"), (0.25, "nearby"), (0, "far"))
LAYOUTS = {4: "quad", 6: "5.1", 8: "7.1"}
FRONT_BACK = {
    "learned": "It tells ahead from behind.",
    "alike": "Ahead and behind sound alike to it: turn on the game's 3D audio, then learn both again a few steps from "
             "the cube.",
    "need_ahead": "Learn it facing the cube too (step 2) to tell ahead from behind.",
    "need_more": "Too little of the jingle was heard to tell ahead from behind: learn both again a little closer.",
}


def radar_sensitivity(ui) -> int:
    """The slider's value (``Number.isInteger(+v) && 1 <= v <= 10 ? +v : 5``)."""
    x = _js_number_or_nan(_dict(ui).get("radar_sensitivity")) if "radar_sensitivity" in _dict(ui) else math.nan
    return int(x) if math.isfinite(x) and float(x).is_integer() and 1 <= x <= 10 else 5


def radar_key(ui, action: str) -> str:
    """A learn step's key (``radarKey``): the one Settings → Hotkeys saved ("" when cleared), else its default."""
    saved = _dict(_dict(ui).get("hotkeys"))
    return js_text(saved[action]) if action in saved and _truthy(saved[action]) else "" if action in saved else RADAR_STEPS[action]


def radar_notes(ui) -> str:
    """How to teach the radar (``radarNotes``), naming each step's key or button."""
    import html as _html

    def key(action, button):
        bound = radar_key(ui, action)
        return f"<b>{_html.escape(bound)}</b>" if bound else button
    return ("<p>Put headphones on and, in the game's sound settings, turn 3D audio on and mute the music, ambient, monster "
            "and your own character's sounds, keeping the effect volume up (what the cube guides advise). Then teach the "
            "radar the game's sound in samples. In the game, while the radar is on, each step's key listens at once; its "
            "button here waits 5 seconds first, so you can switch back to the game.</p>"
            f"<ol><li>{key('radar_learn_background', 'Button 1')} where no cube or feather can be heard, for the "
            "background (it listens 4 seconds). Take one in each kind of place you search: the radar takes off what it "
            "learned of each before it listens for the jingle.</li>"
            f"<li>{key('radar_learn_cube', 'Button 2')} facing a Hidden Cube while it jingles (8 seconds): first beside "
            "it, then a few steps away, then as far off as you can still hear it. The farther samples teach it the jingle "
            "at a distance and set how far its rings reach.</li>"
            f"<li>{key('radar_learn_cube_behind', 'Button 3')} from where you took one, with your back to the cube: it "
            "learns how the game's 3D audio changes the jingle behind you, and then shows whether the cube is ahead of "
            "you or behind.</li></ol>"
            f"<p>{key('radar_learn_other', 'The “not a cube” button')} while a sound the radar takes for a cube plays (an "
            "Empyrean Trace feather, a voice in voice chat; 6 seconds): it no longer takes that sound for one, unless it "
            "sounds the same as the cube's.</p>"
            "<p>The overlay then shows the cube on a circle around you, ahead of you at the top: louder is closer. Without "
            "the game's 3D audio or a surround output, stereo cannot tell ahead from behind: the radar shows both places "
            "the cube can be, and turning towards it tells which (a cube ahead moves to the middle, one behind further "
            "out), as does walking forward (one ahead grows louder). Raise the sensitivity to hear a cube farther away, "
            "lower it if voice chat sets it off. Settings → Hotkeys changes the keys. The app reads what Windows plays, in "
            "memory, and keeps only the samples' levels in 40 frequency bands and the jingle's peak frequencies: nothing "
            "is recorded or uploaded.</p>")


def _plural(n, one: str, many: str = "") -> str:
    return f"{js_text(n)} {one if n == 1 else many or one + 's'}"


def _what(learning) -> str:
    learning = _dict(learning)
    if learning.get("kind") == "background":
        return "the background"
    if learning.get("kind") == "other":
        return "a sound that is not a cube"
    return "the cube's sound behind you" if learning.get("facing") == "behind" else "the cube's sound"


def _near(r) -> str:
    p = _js_number(_dict(r).get("proximity")) or 0
    return next((words for limit, words in RADAR_NEAR if p >= limit), RADAR_NEAR[3][1])


def radar_learned(r) -> str:
    """What the radar has learned (``learnedText``)."""
    r = _dict(r)
    m = _dict(r.get("model"))
    if not _truthy(r.get("ready")):
        if _truthy(m.get("backgrounds")):
            return f"{_plural(m['backgrounds'], 'background sample')} learned: now learn the cube's sound (step 2)."
        return "Nothing learned yet: step 1, then step 2."
    cubes = _plural(m.get("cubes"), "cube sample")
    if _truthy(m.get("behind")):
        cubes += f" ({js_text(m.get('ahead'))} facing it, {js_text(m['behind'])} behind you)"
    bits = [cubes, _plural(m["backgrounds"], "background sample") if _truthy(m.get("backgrounds"))
            else "no background (step 1 improves it)"]
    if _truthy(m.get("others")):
        bits.append(_plural(m["others"], "sound that is not a cube", "sounds that are not a cube"))
    facing = FRONT_BACK.get(m.get("front_back")) if isinstance(m.get("front_back"), str) else None
    if not facing:
        channels = _js_number(r.get("channels")) or 0
        facing = "" if channels >= 4 else "Learn it behind you too (step 3) to tell ahead from behind."
    return f"Learned {', '.join(bits)}{', with the jingle' + chr(39) + 's notes' if _truthy(m.get('notes')) else ''}. {facing}".strip()


def radar_status(r) -> str:
    """The radar's line (``radarStatus``): where it runs, a step under way, what it learned and what it hears."""
    r = _dict(r)
    learning, last = r.get("learning"), r.get("last_learn")
    if not _truthy(r.get("supported")):
        return "The radar listens to Windows' sound output; it runs on Windows only."
    if _truthy(learning):
        seconds = js_text(math.ceil(_js_number(_dict(learning).get("seconds")) or 0))
        if _dict(learning).get("phase") == "countdown":
            return f"Learning {_what(learning)} in {seconds} s: switch to the game."
        return f"Listening to {_what(learning)}… {seconds} s left."
    parts = []
    if _truthy(last):
        parts.append(js_text(_dict(last).get("message")))
    parts.append(radar_learned(r))
    if _truthy(r.get("error")):
        parts.append(f"Not listening: {js_text(r['error'])}.")
    elif _truthy(r.get("enabled")) and _truthy(r.get("listening")):
        if _truthy(r.get("heard")):
            match = theme.js_round((_js_number(r.get("match")) or 0) * 100)
            parts.append(f"Hearing a cube {js_text(r.get('direction'))}, {_near(r)} (match {match} %).")
        else:
            device = f" to {js_text(r['device'])}" if _truthy(r.get("device")) else ""
            channels = _js_number(r.get("channels")) or 0
            rear = (f" ({LAYOUTS.get(int(channels), js_text(r.get('channels')) + ' channels')}: it hears the rear channels)"
                    if channels >= 4 else "")
            parts.append(f"Listening{device}{rear}: no cube heard.")
    elif not _truthy(r.get("setting")):
        parts.append("Off.")
    return " ".join(parts)


def radar_sample(s) -> str:
    """A learned sample's line (``sampleRow``)."""
    s = _dict(s)
    kind = s.get("kind")
    bits = ["Cube, behind you" if kind == "cube" and s.get("facing") == "behind" else "Cube, facing it" if kind == "cube"
            else "Not a cube" if kind == "other" else "Background"]
    if kind == "cube" and s.get("level_db") is not None:
        level = _js_number(s["level_db"])
        bits.append("the loudest" if level is not None and level >= -1 else f"{js_text(-level if level is not None else s['level_db'])} dB below the loudest")
    if kind != "background" and _truthy(s.get("notes")):
        bits.append("with its notes")
    if _truthy(s.get("alike")):
        bits.append("sounds the same as the cube, so it is not used")
    if _truthy(s.get("at")):
        bits.append(js_text(s["at"]).replace("T", " ", 1))
    return " · ".join(bits)


# ------------------------------------------------------------------ Overlay: Hotkeys (0.2.479)
#: The actions a global hotkey can do (hotkeys.py ``ACTIONS``), in the web page's order.
HOTKEY_ACTIONS = (
    ("toggle_overlay", "Show / hide the overlay"), ("toggle_meter", "Start / stop the meter"),
    ("clear_meter", "Clear the meter (battle reset)"),
    ("mark_moment", "Mark this moment for the diagnostics (label it on the Live Meter page)"),
    ("toggle_click_through", "Toggle click-through"), ("toggle_party_overlay", "Show / hide the Party-DPS overlay"),
    ("open_app", "Open the app window"), ("open_settings", "Open the Settings page"),
    ("toggle_events", "Show / hide overlay event notifications"),
    ("toggle_field_bosses", "Show / hide field-boss timers on the overlay"),
    ("toggle_combat_assist", "Show / hide combat assist (skill cooldowns, break gauge)"),
    ("toggle_cube_radar", "Turn the Hidden Cube radar on / off"),
    ("toggle_pet_tracker", "Show / hide the Pet Tracker overlay"),
    ("radar_learn_background", "Hidden Cube radar: learn the background (step 1)"),
    ("radar_learn_cube", "Hidden Cube radar: learn the cube's sound, facing it (step 2)"),
    ("radar_learn_cube_behind", "Hidden Cube radar: learn the cube's sound with it behind you (step 3)"),
    ("radar_learn_other", "Hidden Cube radar: learn a sound that is not a cube"),
    ("read_screen", "Read the game screen into the app (Genus Insight, Title window)"),
    ("screenshot_lock", "Screenshot lock (freeze the overlay)"), ("quit", "Exit Aion 2 Calc"))
HOTKEY_HINT = "Click, then press keys"
HOTKEY_CLEAR = "Clear"
HOTKEYS_SAVE = "Save hotkeys"
HOTKEYS_SAVING = "Saving…"
HOTKEYS_RADAR_NOTE = ("The Hidden Cube radar's learn steps work only while the radar is on, and are Ctrl+1 to Ctrl+4 "
                      "unless you change them. While they are bound, Windows gives those keys to this app instead of the "
                      "game: clear them or pick other keys if the game uses them.")
HOTKEYS_NOTE = ("Global shortcuts that work even while the game is focused (Windows only). Click a field and press the key "
                "combo (e.g. Ctrl+Shift+M), then <strong>Save hotkeys</strong>; <strong>Clear</strong> unbinds. Changes "
                "take effect within a couple of seconds. Leave all blank for no hotkeys (the default). Ride the settings "
                "backup.")


# ------------------------------------------------------------------ Appearance and Profiles & backup (0.2.481)
BACKUP_EXPORT = "Export settings"
BACKUP_IMPORT = "Import settings"
BACKUP_NOTE = ("Save the overlay and app settings to a file you can restore or share, then import it back. What belongs to "
               "this computer stays out of it: the Pet Tracker folder, the overlay's background image and event sound, raw "
               "traffic recording, and the Timers region and group.")
EXPORTING = "Exporting…"
IMPORTING = "Importing…"
BACKUP_FILES = "JSON (*.json);;All files (*)"


def exported(r) -> str:
    """Where the settings were saved (``#settings-export``)."""
    return "Saved to " + js_text(_dict(r).get("file"))


def imported(r) -> str:
    """What an import took (``#settings-import-file``)."""
    return ("Imported: " + ", ".join(js_text(key) for key in _list(_dict(r).get("imported")))
            + ". Reopen the overlay to apply.")


def could_not_import(why: str) -> str:
    return "Could not import: " + why


def hotkey_shown(ui, action: str) -> str:
    """An action's keys as the row shows them: a learn step's default until one is saved, else what was saved."""
    saved = _dict(_dict(ui).get("hotkeys"))
    if action in RADAR_STEPS and action not in saved:
        return RADAR_STEPS[action]
    return js_text(saved[action]) if _truthy(saved.get(action)) else ""


def hotkeys_to_save(values: dict) -> tuple[dict, str]:
    """The hotkeys to save from the fields (``#hotkeys-save``): those set, and the learn steps even when cleared (kept
    cleared), or the words saying a combo is bound twice."""
    saved = {action: value.strip() for action, value in values.items()
             if value.strip() or action in RADAR_STEPS}
    used: dict[str, int] = {}
    for _action, value in saved.items():
        if value:
            used[value.lower()] = used.get(value.lower(), 0) + 1
            if used[value.lower()] > 1:
                return saved, f"{value} is bound to two actions; give each action its own keys."
    return saved, ""
