"""The native Live Meter page's words and its fight's figures (meter.js ``pageMeter`` and ``renderMeter``), drawn by
``meter_page``. Since 0.2.471:

- **the capture's state**: Recording or Stopped and the packets and combat events so far (``#mmsg``), the run
  (``#mrun``), the character the capture found (``#midentity``), where the session is saved (``#msaved``);
- **the view's choices**: the players' scope, the combats retained to view one of, and whether the view follows the
  latest combat (``#mviewstate``);
- **the fight**: why there is nothing yet, the enemies (one chosen shows each player's damage against it), the
  players with their bars, the ping and the game's counters, and the chosen player's parse card (``parseFromMeter``);
- **the capture's setup**: Npcap's state (``refreshNpcap``), the capture interfaces, what Start sends, and what each
  action says it did;
- **the rest of Advanced capture** (since 0.2.472): the game installations (``renderInstallations``), the installed
  game version and capture context (``#mautometa``), and the capture diagnostics: the driver's counters and the
  capture's stage (``#mdriverstats``), the raw TCP recording, a diagnostic ZIP saved (``renderDiagnosticExport``),
  what went wrong (``#mdiagerror``), and the marks and candidates (``renderMarks``, ``renderCandidates``).

Every figure is the app's ``/api/meter`` reading, as the web page shows it.
"""
from __future__ import annotations

import math

from . import theme
from .combat import js_text
from .news import when as moment
from .results import _dict, _list, _truthy, cap, n0, pct
from .timers import world_for

HEAD = "Live damage meter"
SUB = "built-in A2Tools packet capture, live analysis and a2log sharing"
SOURCES = (("a2tools", "Live Capture"), ("replay", "Demo replay"), ("live", "Custom decoder"))
SCOPES = (("auto", "Automatic · allow partial metrics"), ("party", "Self + Party"), ("self", "Self only"),
          ("all", "All observed players"))
SCOPE_KEY = "meter-scope"                # the players' scope, kept as the web page keeps it (``meter-scope``)
CHARACTER_KEY = "meter-character"        # the name override (Advanced capture)
FINAL_BOSS_KEY = "meter-final-boss-ids"  # the final bosses' NPC type IDs (Advanced capture)
GAP_LEAST, GAP_MOST, GAP = 120, 3600, 120   # ``Split after no outgoing damage for`` its seconds
PORT = 50349                             # ``Fixed port``
PLAYERS = "Players"
ENEMIES = "Enemies"
ENEMIES_SUB = "select an enemy to show each player's damage against it"
NO_DATA = "No data yet — choose a source and press Start."
CLEAR_ASK = "Clear retained combat history? Export or save it first if you want to keep a copy."
DECODER_HINT = "Choose a trusted Python decoder. Its code runs when capture starts."
DECODER_TOO_LARGE = "Decoder files must be smaller than 1 MiB"
DECODER_FIRST = "Choose a decoder .py file first."
ENCODER = "Built-in A2Tools decoder"
ADVANCED = "Advanced capture"
ADVANCED_SUB = "network interface and game port, name override, game installation, final boss, diagnostics"
FINAL_NOTE = ("Final-boss order and PvP match-end packets are not yet verified. Configure the final boss before Start, or "
              "use Finish run. Map/instance changes create separate runs without claiming completion. Capture keeps "
              "running.")
ENGINE_NOTE = ("Live Capture uses the included A2Tools protocol engine. It needs Npcap in WinPcap-compatible mode, Scapy, "
               "and capture permission. {}Export writes an open a2log file; Upload uses the log server configured in "
               "Settings.")
NPCAP_OFF = "Npcap setup is only needed on Windows."
NPCAP_ON = ("Npcap is installed. Live Capture may need administrator permissions if Npcap was installed with "
            "administrator-only access.")
NPCAP_ASK = ("Download the current Npcap installer from npcap.com and open it now? Npcap is installed separately and may "
             "ask for administrator approval.")
NPCAP_STARTING = "Starting Npcap setup…"
NPCAP_AGAIN_MS = 1200                    # how soon a download or installer under way is checked again
REGION_RETRY = "Retry region detection"
REGION_CHECKING = "Re-checking official region and world list…"
REGION_RETRYING = "Retrying — the region and world update here when it resolves."
STOPPING = "Stopping capture and saving logs…"
STARTED = "Capture started. Waiting for combat data."
NOT_STARTED = "Capture did not start. Check capture diagnostics."
UPLOADING_STOPPED = "Capture stopped. Uploading the log to the server…"
COMPLETED = "Action completed."
REFRESHED = "Capture interfaces refreshed."
SPLIT = "Next combat event starts a new split."
FINISHED = "Run finished. Capture continues; the next fight starts a new run."
HIDDEN = "Overlay hidden. Open overlay to show it again."
CLEARED = "Combat history cleared."
OVERLAY_SILENT = "Aion 2 Calc did not answer, so the overlay was not opened. Try again in a moment."
OVERLAY_WINDOW = "Overlay opened in a window."
OVERLAY_BLOCKED = "Overlay popup was blocked. Click Open overlay to retry."
OVERLAY_TIP = "Open the compact overlay in a separate window"
SHOT_TOO_LARGE = "This page is too large for a readable PNG. Collapse long sections or filter the log, then retry."
SHOT_RENDERING = "Rendering the full application page…"
SHOT_SAVING = "Saving application PNG…"
INSTALL_AUTO = "Auto (one installed copy)"
INSTALL_GONE = "Selected installation unavailable"
INSTALL_CHOOSE = "Multiple copies found: choose the copy you play."
INSTALL_NEXT = "Selection applies to the next capture. Save and clear retained combat before changing it."
INSTALL_NONE = "No registered installation found. Capture can still run; Product version remains unavailable."
INSTALL_PATH_FIRST = "Enter the game’s install folder."
INSTALL_CHECKING = "Checking…"
INSTALL_ADDED = "Added and selected."
INSTALL_PLACEHOLDER = "C:\\Program Files (x86)\\NC\\AION 2"
META_HEAD = "Installed game version and capture context"
DIAGNOSTICS = "Capture diagnostics"
DIAGNOSTICS_SUB = "capture counters, TCP recording for diagnostics, diagnostics export"
RECORD = "Record TCP payloads for diagnostics (optional; remembered, and every capture records while it is ticked)"
DIAGNOSTICS_NOTE = (
    "Diagnostic ZIPs include capture counters, status errors and a readable summary even with TCP recording off. Open "
    "diagnostics folder to find saved ZIPs. Ticked, TCP recording additionally writes raw payloads without a record or "
    "size limit, even when no combat events are decoded: for every capture however it starts (here, the overlay's Start, "
    "the Start/Stop hotkey or the start at launch), and from the moment you tick it during a capture. Available disk "
    "space limits recording. Saves a diagnostic ZIP automatically when capture stops; long recordings take longer to "
    "compress. Raw traffic may contain character names, IP addresses and other traffic; review before sharing.")
MARKS_NOTE = (
    "A mark stamps the capture's clock with what you saw, so the recording can be read against it: a shield soaking a "
    "hit, an interrupted cast, a miss, reduced damage, a heal over time, a PvP team or round, a boss mechanic. Marks ride "
    "in the diagnostic ZIP (marks.jsonl) and in the saved log. The <em>Mark this moment</em> hotkey (Settings → Overlay → "
    "Hotkeys) adds one from inside the game; label it here afterwards.")
RELABEL_TIP = "Give the latest mark this label and note (a hotkey press is labelled afterwards)"
MARK_NOTE_HINT = "What you saw (optional)"
#: What a mark says was seen (``MARK_LABELS``), each with its words.
MARK_LABELS = (("shield", "A shield absorbed a hit"), ("interrupt", "A cast was interrupted"),
               ("miss", "An attack missed or was evaded"), ("mitigation", "Damage was reduced (block, resist)"),
               ("hot", "A heal over time ticked"), ("pvp", "PvP team or round changed"),
               ("mechanic", "Boss mechanic (describe it)"), ("other", "Other"))
MARKED = "Moment marked."
RELABELLED = "Latest mark labelled."
CONFIRMED = "Candidate confirmed as a mark."
DISMISSED = "Candidate dismissed."
RECORDING_ON = "TCP recording on: every capture records raw TCP from now on"
RECORDING_OFF = "TCP recording off"
DOWNLOAD_ZIP = "Download diagnostic ZIP"
#: The actions whose button says what it is doing until it is done (``actionLabels``), each with its button's words.
ACTIONS = {
    "save": ("Save to Combat Logs", "Saving combat log…"),
    "export": ("Export a2log", "Exporting combat log…"),
    "upload": ("Upload", "Uploading combat log…"),
    "screenshot": ("Screenshot", "Saving screenshot…"),
    "split": ("Split now", "Splitting encounter…"),
    "finish": ("Finish run", "Finishing run…"),
    "hide": ("Hide overlay", "Hiding overlay…"),
    "overlay": ("Open overlay", "Opening overlay…"),
    "interfaces": ("Refresh interfaces", "Refreshing interfaces…"),
    "diagnostics": ("Export capture diagnostics", "Exporting diagnostic ZIP…"),
    "folder": ("Open diagnostics folder", "Opening diagnostics folder…"),
}
STAGES = {
    "capture_error": "Capture reported an error",
    "waiting_for_tcp": "No TCP packets observed",
    "waiting_for_payloads": "TCP packets observed; waiting for payload data",
    "waiting_for_game_flow": "Payloads observed; automatic game-flow detection is waiting",
    "waiting_for_reassembly": "Payloads observed; waiting for reassembled game data",
    "waiting_for_combat_effects": "Game data forwarded; no combat effects decoded yet",
    "no_players_in_selected_view": "Combat effects decoded; no players in the selected scope / encounter / enemy view",
    "combat_visible": "Decoded combat is visible in the selected view",
}


def _n(value) -> str:
    """``${x || 0}``: a count as JavaScript writes it."""
    return js_text(value) if _truthy(value) else "0"


def clock_at(x) -> str:
    """``clockAt``: a moment's time of day alone, ``15:04:05``."""
    text = moment(x)
    return text[11:] if len(text) > 11 else text


def status_text(s: dict) -> str:
    """The capture's state beside Start (``#mmsg``)."""
    s = _dict(s)
    if _truthy(s.get("error")):
        return js_text(s["error"])
    d = _dict(s.get("diagnostics"))
    if _truthy(s.get("finalizing")):
        return "Saving stopped capture and diagnostics…"
    if _truthy(s.get("running")) and d.get("state") == "stopping":
        return "Stopping capture · decoding queued payloads before saving…"
    if not _truthy(s.get("running")):
        return "Stopped"
    paused = _truthy(_dict(s.get("snapshot")).get("paused"))
    text = (f"{'Paused DPS · capture continues' if paused else 'Recording'} · {_n(d.get('packets'))} TCP packets · "
            f"{_n(d.get('decoded_events'))} combat events")
    if _truthy(d.get("tcp_stream_resets")):
        text += f" · {js_text(d['tcp_stream_resets'])} lossy TCP recovery boundaries (capture incomplete)"
    if _truthy(d.get("port")):
        text += f" · port {js_text(d['port'])}"
    elif _truthy(d.get("auto_port")):
        text += " · detecting game port"
    if _truthy(d.get("pcap_dropped")) or _truthy(d.get("pcap_if_dropped")):
        text += " · Capture drops detected; data may be incomplete (see diagnostics)"
    return text


def run_text(s: dict) -> str | None:
    """The run being recorded (``#mrun``); None to leave the line as it was."""
    run = _dict(s).get("run")
    if not _truthy(run):
        return None
    run = _dict(run)
    text = (f"Run {js_text(run.get('id'))} · "
            + ("finished/boundary recorded; waiting for next fight" if _truthy(run.get("closed")) else "recording"))
    return text + (f" · {js_text(run['end_reason'])}" if _truthy(run.get("end_reason")) else "")


def identity_text(s: dict) -> str:
    """The character the capture found (``#midentity``), and the chosen combat's identities."""
    s = _dict(s)
    who = _dict(s.get("identity"))
    if _truthy(who.get("id")):
        world = _dict(s.get("automatic_metadata")).get("server_name")
        server = ""
        if _truthy(who.get("serverId")):
            server = " · " + (js_text(world) if _truthy(world)
                              else world_for(who["serverId"], f"server {js_text(who['serverId'])}"))
        name = js_text(who["name"]) if _truthy(who.get("name")) else f"Player #{js_text(who['id'])}"
        text = (f"{'Detected automatically' if _truthy(who.get('verified')) else 'Matched name override'}: {name}{server} · "
                f"combat entity #{js_text(who['id'])} (changes between instances)")
    else:
        text = ("Auto-detecting your character. Start before entering an instance, or set a name override under "
                "Advanced capture.")
    i = _dict(s.get("snapshot")).get("identity_status")
    if _truthy(i):
        i = _dict(i)
        text += (f" Selected combat: {'Self identified' if _truthy(i.get('self_identified')) else 'Self identity not received'}"
                 f" · {js_text(i.get('unnamed_actors'))} unnamed actors · {js_text(i.get('linked_pets'))} linked pets. "
                 "Unknown actors remain separate until identity/owner links arrive.")
    return text


def saved_text(s: dict) -> str:
    """Where the session is saved (``#msaved``)."""
    s = _dict(s)
    d = _dict(s.get("diagnostics"))
    if _truthy(d.get("log_save_error")):
        return js_text(d["log_save_error"])
    text = ""
    if _truthy(d.get("archive_parts_saved")):
        text = (f"{js_text(d['archive_parts_saved'])} earlier archive part(s) saved in Combat Logs. Upload combines every "
                "part into one recording; live view and export show the current part. ")
    return text + (f"Latest saved part: {js_text(s['saved_log'])}" if _truthy(s.get("saved_log"))
                   else "Current part checkpoints every 15 seconds and saves on Stop.")


def view_state(snap: dict) -> tuple[str, bool]:
    """What the view shows (``#mviewstate``), and whether **Follow latest combat** is offered."""
    snap = _dict(snap)
    mode = snap.get("selection_mode") or "latest"
    if mode == "whole":
        text = "Viewing the whole retained session."
    elif mode == "encounter":
        text = ("Viewing an earlier encounter; capture continues into newer combat." if _truthy(snap.get("viewing_historical"))
                else "This encounter is pinned; select Follow latest combat to follow the next pull.")
    else:
        text = "Following latest combat. Overlay always follows the latest encounter."
    return text, mode != "latest"


def segment_options(snap: dict) -> list[tuple[str, str]]:
    """The combats retained (``#msegments``): the latest, the whole session, then each with its start and length."""
    out = [("", "Latest combat"), ("all", "Whole session")]
    for segment in _list(_dict(snap).get("segments")):
        segment = _dict(segment)
        duration = segment.get("duration")
        out.append((js_text(segment.get("id")), f"{js_text(segment.get('label'))} · {clock_at(segment.get('start'))} · "
                                                 f"{theme.fixed(duration, 1) if isinstance(duration, (int, float)) else 'NaN'}s"))
    return out


def segment_chosen(snap: dict, pinned: str) -> str:
    """The combat chosen: the one pinned, else the whole session or the latest as the reading says."""
    return pinned or ("all" if _dict(snap).get("selected_segment") == "all" else "")


def empty_text(s: dict) -> list[str]:
    """Why the meter has no player yet (``.empty``), then the reading's warnings."""
    s = _dict(s)
    d = _dict(s.get("diagnostics"))
    if _truthy(d.get("decoded_events")):
        first = "Combat effects were decoded; waiting for a matching player identity or party roster in this view."
    elif _truthy(s.get("running")):
        if _truthy(d.get("packets")):
            first = ("The game stream is reaching the decoder but no combat events have been recognized. Enable TCP "
                     "recording before Start and export capture diagnostics after fighting briefly."
                     if _truthy(d.get("forwarded")) else
                     "Packets are arriving. Waiting for a recognized game stream — enter combat. Enable TCP recording "
                     "before Start to investigate.")
        else:
            first = ("No packets yet. Check capture support, adapter permissions and your interface selection, then "
                     "enter combat.")
    else:
        first = NO_DATA
    out = [first]
    warning = _dict(s.get("snapshot")).get("warning")
    if _truthy(warning):
        out.append(js_text(warning))
    warnings = _list(d.get("warnings"))
    if warnings:
        out.append("; ".join(js_text(w) for w in warnings))
    return out


def enemy_rows(snap: dict) -> list[dict]:
    """The enemies of the view (``Enemies``): each with the party's damage and DPS against it, the one chosen marked."""
    snap = _dict(snap)
    return [{"key": e.get("key"), "name": js_text(e.get("name")), "damage": theme.kfmt(e.get("damage")),
             "dps": theme.kfmt(e.get("dps")), "chosen": e.get("key") == snap.get("selected_enemy")}
            for e in (_dict(x) for x in _list(snap.get("enemies")))]


def players_sub(snap: dict) -> str:
    """The players' window's subtitle: the boss, the fight's length and the raid's DPS."""
    snap = _dict(snap)
    boss = js_text(snap["boss"]) if _truthy(snap.get("boss")) else ""
    duration = snap.get("duration") if isinstance(snap.get("duration"), (int, float)) and _truthy(snap.get("duration")) else 0
    return f"{boss}{' · ' if boss else ''}{theme.fixed(duration, 0)}s · {theme.kfmt(snap.get('dps') or 0)} raid DPS"


def player_rows(snap: dict) -> list[dict]:
    """The players (``.pm``): their name, server and class, and their DPS against the fastest as a bar."""
    players = [_dict(p) for p in _list(_dict(snap).get("players"))]
    fastest = max([1.0] + [float(p["dps"]) for p in players if isinstance(p.get("dps"), (int, float))])
    return [{"key": p.get("key") or p.get("id"), "name": js_text(p.get("name")),
             "server": js_text(p["server_name"]) if _truthy(p.get("server_name")) else "", "class": cap(p.get("class") or ""),
             "share": (float(p["dps"]) if isinstance(p.get("dps"), (int, float)) else 0.0) / fastest,
             "words": f"{theme.kfmt(p.get('dps'))}/s · {pct(p.get('share'), 0)}"} for p in players]


def chosen_player(snap: dict, key) -> int:
    """The player whose parse card shows: the one chosen before, else the first."""
    for i, p in enumerate(_list(_dict(snap).get("players"))):
        if (_dict(p).get("key") or _dict(p).get("id")) == key:
            return i
    return 0


def ping_text(snap: dict) -> str:
    """The recording connection's ping (``Ping … ms now``), or nothing."""
    ping = _dict(snap).get("ping")
    if not _truthy(ping):
        return ""
    ping = _dict(ping)
    return (f"Ping {theme.kfmt(ping.get('current'))} ms now · {theme.kfmt(ping.get('avg'))} ms capture avg · "
            f"{theme.kfmt(ping.get('min'))}–{theme.kfmt(ping.get('max'))} ms range ({js_text(ping.get('samples'))} samples "
            "across this recording connection, logged over time)")


def parse_from_meter(snap: dict, index: int) -> dict | None:
    """A player of the reading as the parse card reads a fight (``parseFromMeter``)."""
    snap = _dict(snap)
    players = _list(snap.get("players"))
    if not 0 <= index < len(players):
        return None
    p = _dict(players[index])
    duration = snap.get("duration")
    per = duration if isinstance(duration, (int, float)) and duration else 1
    skills = []
    for s in (_dict(x) for x in _list(p.get("skills"))):
        damage = s.get("damage") if isinstance(s.get("damage"), (int, float)) else 0
        hits = s.get("hits") if isinstance(s.get("hits"), (int, float)) and s.get("hits") else 1
        skills.append({"skill": s.get("skill"), "skill_id": s.get("skill_id"), "hits": s.get("hits"), "dps": damage / per,
                       "avg": damage / hits, "min": s.get("min"), "max": s.get("max"), "damage": s.get("damage"),
                       "share": s.get("share")})
    return {"name": p.get("name"), "cls": p.get("class"), "gs": None, "cp": None, "dmg": p.get("damage"), "dps": p.get("dps"),
            "hits": p.get("hits"), "contrib": p.get("share"), "duration": duration, "boss": snap.get("boss"), "highest": None,
            "rates": {k: p.get(k) for k in ("crit", "double", "perfect", "multi", "back", "front", "parry")},
            "skills": skills, "rotation": [], "timeline": p.get("timeline") if _truthy(p.get("timeline")) else None, "incoming": p.get("incoming"),
            "healing": p.get("healing"), "live": True}


def stop_words(result: dict) -> str:
    """What a Stop did (``Capture stopped…``)."""
    result = _dict(result)
    error = _dict(result.get("diagnostics")).get("log_save_error")
    if _truthy(error):
        return f"Capture stopped, but log saving failed: {js_text(error)}"
    if _truthy(result.get("saved_log")):
        return f"Capture stopped. Session saved to {js_text(result['saved_log'])}"
    return "Capture stopped. No session file was saved; check Combat Logs and capture diagnostics."


def final_boss_ids(text: str) -> list[int]:
    """The final bosses' NPC type IDs from what was typed: the whole numbers among the commas."""
    return [int(x.strip()) for x in str(text or "").split(",") if x.strip().isdigit() and x.strip().isascii()]


def engine_note(info: str) -> str:
    """The note on the protocol engine, Npcap's line in it (``#npcapinfo``); one space between the sentences, as the
    page's words run."""
    return ENGINE_NOTE.format(f"{info} " if info else "")


def npcap_state(r: dict) -> dict:
    """Npcap's state (``refreshNpcap``): ``shown`` when there is something to do, above the meter (its ``text``, a
    ``button`` and the ``after`` words that follow it, and whether to look ``again`` soon); otherwise the ``info``
    line under Advanced capture."""
    r = _dict(r)
    if not _truthy(r.get("supported")):
        return {"shown": False, "info": NPCAP_OFF}
    if _truthy(r.get("installed")):
        return {"shown": False, "info": NPCAP_ON}
    if _truthy(r.get("detection_error")):
        return {"shown": True, "text": js_text(r["detection_error"]) + " Installation status is unknown; check with your "
                "administrator before reinstalling."}
    version = js_text(r["version"]) if _truthy(r.get("version")) else ""
    status = r.get("status")
    busy = {"finding": "Finding the current official Npcap installer…", "downloading": f"Downloading Npcap {version}…",
            "opening": "Opening the Npcap installer…"}
    if status in busy:
        return {"shown": True, "text": busy[status], "again": True}
    if status == "installer-opened":
        return {"shown": True, "text": f"Npcap {version} installer is open. Finish its setup, then", "button": "Check again",
                "after": "."}
    return {"shown": True, "text": "Npcap is required for Live Capture.", "button": "Install Npcap",
            "after": f" {js_text(r['error'])}" if _truthy(r.get("error")) else ""}


def region_retry_shown(s: dict) -> bool:
    """Whether Retry region detection is offered: only when the official lookup failed (``region_status``)."""
    return _dict(_dict(s).get("automatic_metadata")).get("region_status") == "unavailable"


def interface_options(r: dict) -> list[tuple[str, str]]:
    """The capture interfaces (``#miface``): Auto, then each adapter with its address."""
    r = _dict(r)
    devices = r.get("devices") if _truthy(r.get("devices")) else [{"name": n, "label": n} for n in _list(r.get("interfaces"))]
    out = [("auto", "Auto")]
    for d in (_dict(x) for x in _list(devices)):
        address = f" · {js_text(d['address'])}" if _truthy(d.get("address")) else ""
        out.append((js_text(d.get("name")), js_text(d.get("label")) + address))
    return out


def start_body(source: str, *, scope, gap, decoder, auto_port: bool, automatic_splits: bool, auto_finish: bool,
               final_bosses: str, iface: str, host: str, port, character: str) -> dict:
    """What Start sends (``#mstart``): the source and the view's choices, and Advanced capture's for a capture."""
    replay = source == "replay"
    return {"action": "start", "source": source, "scope": scope, "segment_gap": gap or GAP,
            "decoder": decoder if source == "live" else None, "auto_port": source == "a2tools" and auto_port,
            "automatic_splits": automatic_splits, "auto_finish": auto_finish, "final_boss_ids": final_boss_ids(final_bosses),
            "iface": iface if not replay and iface != "auto" else None,
            "host": host if not replay and host != "any" else None, "port": None if replay else (port or PORT),
            "target_mode": "allTargets", "character_name": (character or None) if source == "a2tools" else None}


def overlay_words(result: dict) -> str | None:
    """What Open overlay did (``openMeterOverlay``); None when the app could not open its own window."""
    r = _dict(result)
    if not _truthy(r.get("native")):
        return None
    return "Overlay is already open." if _truthy(r.get("already_open")) else "Overlay opened."


def setup_words(setup: dict, installing: bool) -> str:
    """What Start says when packet-capture support is missing: setting it up, or that it is needed."""
    kind = js_text(_dict(setup).get("kind"))
    return f"{kind} setup is starting. Finish it, then press Start again." if installing else \
        f"{kind} is required before Live Capture can start."


def saved_words(result: dict) -> str:
    return f"saved as encounter #{js_text(_dict(result).get('id'))}"


def exported_words(result: dict) -> str:
    return f"exported {js_text(_dict(result).get('file'))}"


def shot_scale(width: float, height: float) -> float:
    """How far a page's picture is shrunk to fit a PNG's limits (``A2Screenshot.capture``): 30,000 pixels a side and
    40 million in all."""
    width, height = max(1.0, float(width)), max(1.0, float(height))
    return min(1.0, 30000 / max(width, height), math.sqrt(40000000 / (width * height)))


def shot_words(result: dict, scaled: bool) -> str:
    return (f"Application screenshot saved: {js_text(_dict(result).get('file'))}"
            + (" (scaled to fit PNG limits)" if scaled else ""))


# ------------------------------------------------------------------ the rest of Advanced capture (0.2.472)
def _js(value) -> str:
    """``${x}`` as JavaScript writes it, ``true`` and ``false`` too."""
    return "true" if value is True else "false" if value is False else js_text(value)


def _seconds_ago(value) -> str:
    return "not observed" if value is None else f"{theme.fixed(value, 1)}s ago" if isinstance(value, (int, float)) \
        else "NaNs ago"


def driver_text(s: dict) -> str:
    """The capture's counters (``#mdriverstats``): the driver's, the capture's stage, how long since game data and a
    combat effect, and the session's processing."""
    d = _dict(_dict(s).get("diagnostics"))
    if _truthy(d.get("pcap_stats_sampled")):
        text = (f"Driver counters{' (partial coverage)' if _truthy(d.get('pcap_stats_partial')) else ''}: "
                f"{_n(d.get('pcap_received'))} received, {_n(d.get('pcap_dropped'))} capture-buffer drops, "
                f"{_n(d.get('pcap_if_dropped'))} interface/driver drops. Zero does not prove loss-free capture; counts can "
                "include other traffic.")
    else:
        text = "Driver counters: unavailable or not sampled. TCP reassembly monitoring is separate."
    pipeline = d.get("pipeline")
    if _truthy(pipeline):
        pipeline = _dict(pipeline)
        stage = pipeline.get("stage")
        words = STAGES.get(stage) if isinstance(stage, str) else None
        text += (f" Capture stage: {words or _js(stage)}. Payload packets {_n(d.get('payload_packets'))}; forwarded chunks "
                 f"{_n(d.get('forwarded'))}; decoded effects {_n(d.get('decoded_events'))}; visible players "
                 f"{_n(pipeline.get('visible_players'))}. This summarizes retained counters, not proof of current activity. "
                 "Raw payload recording is optional.")
    text += (f" Last forwarded game data: {_seconds_ago(d.get('last_packet_age_seconds'))}. Last decoded effect: "
             f"{_seconds_ago(d.get('last_combat_age_seconds'))}. Idle time alone does not establish a capture failure.")
    processing = d.get("capture_processing")
    if _truthy(processing):
        p = _dict(processing)
        n = lambda key: "not recorded" if p.get(key) is None else n0(p[key])     # noqa: E731
        text += (f" Session processing: {n('decoder_errors')} decoder failures; {n('shutdown_discarded_payloads')} "
                 f"shutdown payload discards; {n('shutdown_drained_payloads')} payloads retained during shutdown. Legacy "
                 f"error/discard count {n('capture_errors')} overlaps these counters.")
    return text


def meta_summary(s: dict) -> str:
    """The folded line of the installed game version and capture context (``#mautometa-sum``)."""
    s = _dict(s)
    m = _dict(s.get("automatic_metadata"))
    zone = _dict(s.get("automatic_context")).get("zone")
    return f"{_installed(m)} · {_js(zone) if _truthy(zone) else 'zone not identified'} · expand for the comparison " \
           "version, region and catalog coverage"


def _installed(m: dict) -> str:
    build = m.get("installed_build") if _truthy(m.get("installed_build")) else m.get("status")
    source = f" ({_js(m['installed_build_source'])})" if _truthy(m.get("installed_build_source")) else ""
    return f"Installed game version: {_js(build) if _truthy(build) else 'unavailable'}{source}"


def meta_text(s: dict) -> str:
    """The installed game version and capture context unfolded (``#mautometa``)."""
    s = _dict(s)
    m = _dict(s.get("automatic_metadata"))
    ctx = _dict(s.get("automatic_context"))
    coverage = _dict(s.get("catalog_coverage"))
    classification = _dict(ctx.get("classification"))
    ready = m.get("region_status") == "ready"
    patch = _js(m["game_patch"]) if _truthy(m.get("game_patch")) else ""
    if patch.startswith("version:product:"):
        patch = patch[len("version:product:"):]
    region = m.get("region") if _truthy(m.get("region")) else "waiting for recorded server ID" if ready \
        else m.get("region_status")
    world = m.get("server_name") if _truthy(m.get("server_name")) else "waiting for recorded server ID" if ready \
        else "unavailable"
    known = lambda value, missing: _js(value) if _truthy(value) else missing     # noqa: E731
    unmapped = coverage.get("unmapped")
    conflicts = _list(classification.get("conflicts"))
    return (f"{_installed(m)}. Comparison version: {patch or 'unavailable'}. Automatic region: "
            f"{known(region, 'unavailable')}. World: {_js(world)}. Zone: {known(ctx.get('zone'), 'not identified')}. "
            f"Content: {known(ctx.get('encounter_type'), 'not identified')}. Difficulty: "
            f"{known(ctx.get('difficulty'), 'not identified')}. Map / instance IDs: {known(coverage.get('map_id'), 'not recorded')} / "
            f"{known(coverage.get('instance_id'), 'not recorded')}. "
            f"{len(unmapped) if isinstance(unmapped, (list, str)) and unmapped else 0} unmapped catalog IDs and "
            f"{_n(coverage.get('npc_entities_without_type'))} enemy references without an NPC type in this view (included "
            f"in diagnostics). "
            + (f"Context conflict: {'; '.join(_js(c) for c in conflicts)}. " if conflicts else "")
            + ("NPC-only instance suggestion; entry remains unverified. " if classification.get("basis") == "npc_only" else "")
            + (f"{_js(m['reason'])} " if _truthy(m.get("reason")) else "")
            + "Product version identifies comparison groups across launchers; legacy capture metadata is retained.")


def record_text(s: dict) -> str:
    """The raw TCP recording's state (``#mrecordstatus``)."""
    r = _dict(_dict(s).get("recording"))
    size = r.get("disk_bytes") if isinstance(r.get("disk_bytes"), (int, float)) and r.get("disk_bytes") else 0
    recorded = f"{_n(r.get('records'))} TCP payload records · {theme.fixed(size / 1048576, 1)} MiB on disk"
    if _truthy(r.get("enabled")):
        return f"Recording raw TCP · {recorded} · no record limit"
    if _truthy(r.get("records")):
        return f"Raw TCP recording off · {recorded}, kept for this capture's diagnostic ZIP"
    return "Raw TCP recording is off · not required for live combat capture"


def diagnostic_errors(s: dict) -> str:
    """What went wrong with the recording, the decoder or the diagnostic ZIP (``#mdiagerror``)."""
    s = _dict(s)
    r, d = _dict(s.get("recording")), _dict(s.get("diagnostics"))
    backlog = _dict(_dict(s.get("snapshot")).get("decode_backlog"))
    parts = [
        f"TCP recording stopped writing: {_js(r['error'])}. {_n(r.get('discarded_records'))} records were not saved. Free "
        "disk space and export the retained data." if _truthy(r.get("error")) else "",
        f"{_js(d['decoder_warning'])}. Capture continues; affected data remains unranked." if _truthy(d.get("decoder_warning"))
        else "",
        _js(d["archive_deferred"]) if _truthy(d.get("archive_deferred")) else "",
        f"Could not save diagnostic ZIP: {_js(d['archive_error'])}. Use Export capture diagnostics to retry before starting "
        "another capture." if _truthy(d.get("archive_error")) else "",
        f"Raw diagnostic cleanup failed: {_js(d['recording_cleanup_error'])}. The raw file remains in the diagnostics "
        "folder." if _truthy(d.get("recording_cleanup_error")) else "",
        f"Live view is catching up ({_js(backlog.get('queue_depth'))} packets queued) during a heavy fight; final totals are "
        "unaffected." if _truthy(backlog.get("catching_up")) else "",
    ]
    return " ".join(part for part in parts if part)


def export_lines(r: dict) -> list[str]:
    """A diagnostic ZIP saved (``renderDiagnosticExport``): what it holds and where it is."""
    r = _dict(r)
    lines = [f"Saved ZIP: {n0(r.get('size_bytes'))} bytes · {n0(r.get('records'))} raw TCP records.",
             f"Capture packets: {n0(r.get('capture_packets'))} · decoded events: {n0(r.get('decoded_events'))} · retained "
             f"effects: {n0(r.get('retained_effects'))}.",
             f"Saved on this computer: {_js(r.get('file'))}",
             "Contains a readable capture-summary.txt and diagnostics.json."]
    if not _truthy(r.get("records")):
        lines.append("Raw TCP recording was off or empty, so tcp-payloads.jsonl is intentionally empty. The ZIP still "
                     "contains capture status, counters and errors. Use Open diagnostics folder to find it.")
    return lines


def exported_zip_words(r: dict) -> str:
    """What Export capture diagnostics did."""
    r = _dict(r)
    records = f"{_js(r['records'])} raw TCP records." if _truthy(r.get("records")) else \
        "Metadata-only ZIP; raw TCP recording is off or empty."
    return f"Diagnostic ZIP saved ({n0(r.get('size_bytes'))} bytes) to {_js(r.get('file'))}. {records}"


def installations(r: dict) -> dict:
    """The game's installations (``renderInstallations``): the choices, the one chosen, whether one must be chosen
    (Advanced capture then opens), and what that means."""
    r = _dict(r)
    rows = [_dict(x) for x in _list(r.get("installations"))]
    options = [("", INSTALL_AUTO)] + [(_js(x.get("id")), _js(x.get("label"))) for x in rows]
    selected = _js(r["selected"]) if _truthy(r.get("selected")) else ""
    if selected and not any(_js(x.get("id")) == selected for x in rows):
        options.append((selected, INSTALL_GONE))
    required = _truthy(r.get("selection_required"))
    status = INSTALL_CHOOSE if required else INSTALL_NEXT if rows else INSTALL_NONE
    return {"options": options, "selected": selected, "required": required, "status": status}


def _when(value) -> str:
    """A mark's moment as the page writes it: its ISO time, the ``T`` a space and the fraction of a second dropped."""
    import re
    return re.sub(r"\.\d+Z$", "Z", (_js(value) if value is not None and value != "" else "").replace("T", " ", 1))


def marks_line(marks) -> list[dict]:
    """The latest marks (``renderMarks``), the newest first: when, what, the note and how far into which fight."""
    rows = [_dict(m) for m in _list(marks) if (_dict(m).get("kind") or "mark") == "mark"][-8:][::-1]
    out = []
    for m in rows:
        fight = ""
        t = m.get("fight_t")
        if isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t):
            fight = f" · {theme.js_round(t)}s into {_js(m['boss']) if _truthy(m.get('boss')) else 'the fight'}"
        out.append({"when": _when(m.get("at")), "label": _js(m.get("label")),
                    "note": _js(m["note"]) if _truthy(m.get("note")) else "", "fight": fight})
    return out


def candidates(marks) -> tuple[list[dict], int]:
    """The candidates the app noticed and still waiting (``renderCandidates``), the newest six first, and how many were
    decided."""
    rows = [_dict(m) for m in _list(marks)]
    pending = [m for m in rows if m.get("kind") == "candidate" and m.get("status") == "pending"][-6:][::-1]
    decided = sum(1 for m in rows if m.get("kind") == "candidate" and m.get("status") != "pending")
    return ([{"id": m.get("id"), "when": _when(m.get("at")), "label": _js(m.get("label")),
              "why": _js(m.get("why")) if _truthy(m.get("why")) else ""} for m in pending], decided)


def candidates_head(pending: list, decided: int) -> str:
    if pending:
        return ("Candidates the app noticed (confirm what you saw, dismiss what you did not"
                + (f"; {decided} decided" if decided else "") + "):")
    return f"No candidate waiting ({decided} decided this capture)." if decided else ""
