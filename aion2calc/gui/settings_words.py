"""The native Settings page's words and figures (0.2.475), as pages/settings.js writes them: its tabs, and the rows of
App & data with their notes, the game database's line, the storage maintenance's table, the version and its update,
and the patch notes; since 0.2.476 the Meter tab's Combat records and the Server tab's log server and community stats.
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
