"""The Combat Logs page's words (0.2.450), as pages/combat.js writes them: its views and lists, and the Saved Logs list
(a fight analyzed from a link or a file, the folder the analyzed logs are kept in, the log server shared to, and the
encounters analyzed); since 0.2.451 the recorded encounters by type (saved-logs.js) and the queue that uploads the
recordings (archive-upload.js), with its rules: which files a batch takes, what a recovery checkpoint may hold, which
refusals stop a batch, and what its results manifest says.
"""
from __future__ import annotations

import gzip
import json
import math
import re
import secrets
import unicodedata
import urllib.parse
from datetime import datetime

from .news import when as moment
from .results import _dict, _list, _truthy, cap, js_text, n0
from . import theme

SUBTITLE = "per-skill breakdown, timeline, rates, idle time — compared with your optimal rotation"
VIEWS = (("community", "Browse logs"), ("speed", "Completed-run speed"), ("progression", "Boss progression"),
         ("points", "Highest observed build points"), ("extras", "Personal records"))
LISTS = (("community", "Community Combat Logs"), ("owned", "My Uploads"), ("saved", "Saved Logs"),
         ("identities", "My Character Identities"))
REF_HINT = "AbyssLogs link (abysslogs.com/e/…) or A2DIL link"
PLAYER_HINT = "player (party logs)"
ABYSSLOGS = "https://abysslogs.com"
IMPORT_NOTE = ("Record a fight with the free <a href='https://abysslogs.com' style='color: " + theme.COLORS["accent"] + ";'>"
               "AbyssLogs meter</a>, press Share, and paste the "
               "link here. A party log shows the recorder's damage unless you name a player. Files: AbyssLogs segment (.json / "
               ".json.gz), aion2calc JSON (see docs), or CSV with columns t, skill, damage, crit, double, perfect, multi, dot.")
FILE_KINDS = "Combat logs (*.json *.gz *.csv)"
VISIBILITY = (("public", "public"), ("unlisted", "unlisted"), ("legion", "legion only"), ("private", "private"))
SERVER_HINT = "https://logs.example.com"
NO_ENCOUNTERS = "No encounters yet."
ENCOUNTER_COLUMNS = ["#", "Player", "Class", "Target", "Source", "Duration", "DPS", ""]
ON_THE_WEB_VIEW = "This view opens in the web interface for now."
ON_THE_WEB_LIST = "This list opens in the web interface for now."


def list_page(key: str) -> str:
    """A list of the web page (``#/combat/<list tab>`` opens it)."""
    return f"combat/{key}"


def analysis_page(identifier) -> str:
    """An analyzed encounter's page in the web interface (``#/combat-log/analysis/<id>``)."""
    return "combat-log/analysis/" + urllib.parse.quote(js_text(identifier), safe="")


def folder_line(answer) -> tuple[str, str]:
    """Where every analyzed log is saved, and how many files are there."""
    answer = _dict(answer)
    return js_text(answer.get("folder")), f"({js_text(answer.get('files'))} files)"


def server_row(answer) -> dict:
    """The log server shared to: its address, whether its upload key is saved (only that is said), and who sees the
    uploads."""
    answer = _dict(answer)
    visibility = answer.get("visibility") or "public"
    return {"url": js_text(answer.get("url") or ""), "key_hint": "key saved" if answer.get("has_key") else "upload key",
            "visibility": visibility if visibility in dict(VISIBILITY) else "public"}


def server_body(url: str, key: str, visibility: str) -> dict:
    """What Save sends: the key only when one is typed (``null`` keeps the one saved)."""
    return {"url": url, "key": key or None, "visibility": visibility}


def encounter_rows(answer) -> list[dict]:
    """The encounters analyzed (``hist``): id, player, class, target, source, length and DPS."""
    rows = []
    for e in _list(answer):
        if not isinstance(e, dict):
            continue
        duration = e.get("duration") or 0
        rows.append({"id": e.get("id"), "player": js_text(e.get("player") or ""), "class": cap(e.get("class_name")),
                     "boss": js_text(e.get("boss") or ""), "source": js_text(e.get("source")),
                     "duration": f"{theme.fixed(float(duration) if isinstance(duration, (int, float)) else 0.0, 0)}s",
                     "dps": n0(e.get("dps"))})
    return rows


def import_body(ref: str, player: str) -> dict:
    return {"ref": ref, "player": player}


def read_log_file(path: str) -> str:
    """A log file's text: an AbyssLogs segment (gzip) unpacked, anything else read as text."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8")


def file_body(text: str, name: str, player: str) -> dict:
    return {"text": text, "name": name, "player": player}


def last_line(log) -> str:
    """A job's progress (``progress``): its log's last line."""
    lines = _list(log)
    return js_text(lines[-1]) if lines else ""


def encode_component(value) -> str:
    """``encodeURIComponent``."""
    return urllib.parse.quote(js_text(value), safe="!~*'()")


def js_string(value) -> str:
    """``String(value)`` in a list joined: none is empty, true and false as JavaScript writes them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return js_text(value)


def locale_key(text) -> tuple:
    """A key that sorts names as ``localeCompare`` does for the bosses' names: letters before their accents and case,
    and a lower-case letter before its capital."""
    text = js_text(text)
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return bare.casefold(), text.casefold(), text.swapcase()


def sessions_path(offset: int, limit: int, archive: str = "") -> str:
    """A page of the recordings saved on this computer (``/api/sessions?paged=1``), all or one recording's parts."""
    return f"/api/sessions?paged=1&offset={offset}&limit={limit}&archive={encode_component(archive or '')}"


def local_page(file, segment=None) -> str:
    """A saved recording's page in the web interface (``#/combat-log/local/<file>``), at one of its encounters."""
    page = "combat-log/local/" + encode_component(file)
    return page + (f"?segment={segment}" if isinstance(segment, int) and not isinstance(segment, bool) else "")


# ------------------------------------------------------------------ recorded encounters by type (saved-logs.js, 0.2.451)
SECTIONS = (("pvp", "PvP encounters"), ("world_boss", "World bosses"), ("field_boss", "Field bosses"), ("raid", "Raids"),
            ("nightmare", "Nightmare dungeons"), ("ascension", "Ascension trials"), ("expedition", "Expeditions"),
            ("transcendence", "Transcendence dungeons"), ("daily", "Daily dungeons"), ("open_world", "Open world"),
            ("other", "Other / unverified"))
ROLE = {"final": "Final boss", "mini": "Mini-boss", "field": "Field boss", "world": "World boss"}
#: The encounter types (community.js ``types``).
TYPES = {"unknown": "Unknown", "pve_open_world": "PvE · Open world", "pve_unverified": "PvE · Unverified source",
         "transcendence": "Transcendence dungeon", "daily": "Daily dungeon", "expedition": "Expedition",
         "ascension": "Ascension trials", "nightmare": "Nightmare", "sanctuary": "Sanctuary raids",
         "pvp_battleground": "PvP · Battlefield", "pvp_arena": "PvP · Arena", "pvp_abyss": "PvP · Abyss",
         "pvp_rift": "PvP · Rift", "pvp_open_world": "PvP · Open world", "pvp_other": "PvP · Unverified / other"}
PER_SECTION = 200                     # rows drawn in a section; "+N more" says the rest
RECORDED_PAGE = 50
MINI_KEY = "a2.logs.showMiniBosses"   # the choice the community combat logs keep too
MINI_TIP = "Earlier bosses of a dungeon whose final boss the catalog knows; hidden unless shown"
RECORDED_NOTE = "Your recorded encounters, grouped by type. Each row opens that encounter."
RECORDED_LOADED = " The filters apply to the recordings loaded so far."
NO_RECORDED = "No recorded encounters yet. Record a fight with the live meter and it will appear here, grouped by type."
RECORDED_FAILED = "Could not load saved recordings."
LOADING = "Loading…"
RECORDED_COLUMNS = ["Boss / encounter", "Role", "Difficulty", "Time", "Date", ""]
NO_FILTERS = {"boss": "", "category": "", "role": "", "difficulty": "", "from": "", "to": ""}


def secs(x) -> str:
    """A length as m:ss (``secs``); "—" for none."""
    if x is None or isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x):
        return "—"
    x = theme.js_round(x)
    return f"{math.floor(x / 60)}:{int(math.fmod(x, 60)):02d}"


def saved_at(ts) -> str:
    """When a recording was saved, in the computer's clock (``day``)."""
    if ts is None or isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return "—"
    return moment(ts * 1000)


def day_start(day: str) -> float | None:
    """A day's midnight in the computer's clock, in seconds (``dayStart``)."""
    try:
        return datetime.strptime(day, "%Y-%m-%d").timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def recorded(answer) -> list[dict]:
    """A page of recordings as their encounters (``fetchPage``): each fight with a boss, or of a known kind."""
    found = []
    for r in _list(_dict(answer).get("rows")):
        if not isinstance(r, dict):
            continue
        for c in _list(r.get("contexts")):
            if not isinstance(c, dict) or (c.get("boss") is None and c.get("category") == "other"):
                continue                      # an empty fight with no boss
            found.append({"boss": c.get("boss"), "boss_code": c.get("boss_code"),
                          "category": c.get("category") if _truthy(c.get("category")) else "other",
                          "role": c.get("role"), "difficulty": c.get("difficulty"), "duration": c.get("duration"),
                          "killed": c.get("killed"), "date": r.get("updated"), "file": r.get("file"),
                          "segment": c.get("segment"), "enc_type": c.get("encounter_type")})
    return found


def role_of(e: dict) -> str:
    """The role a filter reads: PvP, or a boss's role in its dungeon."""
    role = e.get("role")
    return "pvp" if e.get("category") == "pvp" else (role if isinstance(role, str) else "")


def role_label(e: dict) -> str:
    """A row's role (``roleLabel``): a PvP encounter's kind, or a boss's role."""
    if e.get("category") == "pvp":
        kind = TYPES.get(e.get("enc_type")) if isinstance(e.get("enc_type"), str) else None
        return re.sub(r"^PvP · ", "", kind) if kind else "PvP"
    return ROLE.get(e.get("role"), "") if isinstance(e.get("role"), str) else ""


def role_name(role: str) -> str:
    return "PvP" if role == "pvp" else ROLE.get(role, role)


def section_title(key: str) -> str:
    return next((title for k, title in SECTIONS if k == key), key)


def shown(e: dict, f: dict, mini: bool) -> bool:
    """Whether a filter lets an encounter through (``matches``): a mini-boss only when they are shown, or chosen."""
    if f["boss"] and e.get("boss") != f["boss"]:
        return False
    if f["category"] and e.get("category") != f["category"]:
        return False
    if f["role"] and role_of(e) != f["role"]:
        return False
    if f["difficulty"] and (e.get("difficulty") or "") != f["difficulty"]:
        return False
    start = day_start(f["from"]) if f["from"] else None
    end = day_start(f["to"]) if f["to"] else None
    date = e.get("date") if isinstance(e.get("date"), (int, float)) and not isinstance(e.get("date"), bool) else None
    if start and not (date is not None and date >= start):
        return False
    if end and not (date is not None and date < end + 86400):
        return False
    return mini or e.get("role") != "mini" or f["boss"] == e.get("boss") or f["role"] == "mini"


def recorded_choices(encounters: list[dict], mini: bool) -> dict:
    """What the filters offer (``filtersHTML``): the bosses (a mini-boss when they are shown), the kinds, roles and
    difficulties recorded."""
    bosses = sorted({e["boss"] for e in encounters if isinstance(e.get("boss"), str) and e["boss"]
                     and (mini or e.get("role") != "mini")}, key=locale_key)
    kinds = [key for key, _title in SECTIONS if any(e.get("category") == key for e in encounters)]
    roles = list(dict.fromkeys(role for role in (role_of(e) for e in encounters) if role))
    levels = sorted({e["difficulty"] for e in encounters
                     if isinstance(e.get("difficulty"), str) and e["difficulty"] and e["difficulty"] != "unknown"})
    return {"boss": [(b, b) for b in bosses], "category": [(k, section_title(k)) for k in kinds],
            "role": [(r, role_name(r)) for r in roles], "difficulty": [(d, cap(d)) for d in levels]}


def recorded_sections(encounters: list[dict], f: dict, mini: bool) -> list[dict]:
    """The encounters a filter lets through, by kind in the sections' order, each newest first."""
    groups: dict[str, list] = {}
    for e in encounters:
        if shown(e, f, mini):
            groups.setdefault(e.get("category"), []).append(e)
    sections = []
    for key, title in SECTIONS:
        rows = sorted(groups.get(key, []), key=lambda e: -(e["date"] if isinstance(e.get("date"), (int, float)) else 0))
        if rows:
            sections.append({"key": key, "title": title, "count": len(rows), "rows": [recorded_row(e) for e in rows[:PER_SECTION]],
                             "more": max(0, len(rows) - PER_SECTION)})
    return sections


def recorded_row(e: dict) -> dict:
    level = e.get("difficulty") if isinstance(e.get("difficulty"), str) and e["difficulty"] != "unknown" else ""
    return {"boss": js_text(e.get("boss")) if _truthy(e.get("boss")) else "—", "code": e.get("boss_code"),
            "role": role_label(e), "difficulty": cap(level) or "—", "time": secs(e.get("duration")),
            "date": saved_at(e.get("date")), "file": e.get("file"),
            "segment": e.get("segment") if isinstance(e.get("segment"), int) and not isinstance(e.get("segment"), bool) else None}


def no_match(more: bool) -> str:
    return f"No recorded encounters match these filters{' among the recordings loaded so far' if more else ''}."


# ------------------------------------------------------------------ upload recordings (archive-upload.js, 0.2.451)
CHECKPOINT = "a2log-upload-checkpoint"
QUEUE_LIMIT = 100
UPLOAD_PAGE = 25
QUEUE_VISIBILITY = ("public", "unlisted", "private")
STATUSES = ("pending", "uploading", "unknown", "failed", "uploaded")
QUEUE_HEAD = "Saved parts · review and batch upload"
QUEUE_NOTE = ("Each selected file becomes a separate report. Active/unfinished checkpoints are excluded from the queue. "
              "Up to 100 files per queue. Recovery metadata is saved locally without upload keys, private links or "
              "ownership credentials. Navigating away stops before the next upload; the in-flight request can finish.")
QUEUE_FOOT = ("Public uploads are listed; unlisted uploads can be viewed with their link; private uploads require a secret "
              "link. The results manifest can contain unlisted links, but excludes private links and ownership/upload keys. "
              "A failed network response can be ambiguous: interrupted requests are marked uncertain and require explicit "
              "retry. Updated servers reuse matching request IDs instead of creating duplicate reports. Older servers and "
              "legacy uncertain requests without a prior ID can still duplicate. Request IDs are not ownership credentials; "
              "retries do not reissue private links or management tokens.")
QUEUE_COLUMNS = ["Select", "Session / archive part", "Encounters", "State", ""]
FILTER_HINT = "Archive ID, name or encounter type"
NO_FILES = "No matching files on this page."
RETRY_UNKNOWN = "I checked My uploads and want to retry uncertain requests (may duplicate an accepted upload)."
RESTORED = ("Queue restored. Files are verified before skipping known successes. Interrupted requests remain uncertain; "
            "check My uploads before retrying them.")
CLEARED = "Queue cleared; local files and server uploads remain."
CANCELLING = "Cancellation requested; the in-flight upload can finish."
RECOVERY_FILE, MANIFEST_FILE = "combat-upload-recovery.json", "combat-upload-manifest.json"
RECOVERY_LIMIT = 256 * 1024
_KNOWN = re.compile(r"\b(400|401|403|409|410|413|429)\b|file changed|unfinished checkpoints", re.I)
_HALTING = re.compile(r"\b(401|403|409|410|429)\b|server changed|failed to fetch|timed out|aborted", re.I)


def queue_label(row: dict) -> str:
    return js_text(row.get("title")) if _truthy(row.get("title")) else js_text(row.get("file"))


def href(link: str) -> str | None:
    """An http(s) address as a browser writes it (``new URL(x).href``), or None."""
    try:
        parts = urllib.parse.urlsplit(link.strip())
        host, port = parts.hostname, parts.port
    except (ValueError, AttributeError):
        return None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not host:
        return None
    user = parts.netloc.rpartition("@")[0]
    place = (user + "@" if "@" in parts.netloc else "") + (f"[{host}]" if ":" in host else host)
    if port is not None and port != {"http": 80, "https": 443}[scheme]:
        place += f":{port}"
    return (f"{scheme}://{place}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
            + (f"#{parts.fragment}" if parts.fragment else ""))


def safe_link(value) -> str:
    """``safeLink``: an http(s) address, else nothing."""
    return href(js_text(value)) or ""


def exported_link(value) -> str | None:
    """``exportedLink``: an uploaded report's address for the manifest, only when it holds no secret (no query, no
    fragment)."""
    link = safe_link(value)
    if not link:
        return None
    parts = urllib.parse.urlsplit(link)
    return None if parts.query or parts.fragment else link


def archive_meta(archive) -> dict | None:
    """``archiveMeta``: a part's recording and number, when it has them."""
    if not isinstance(archive, dict) or not isinstance(archive.get("id"), str):
        return None
    part = archive.get("part")
    if isinstance(part, bool) or not isinstance(part, (int, float)) or not float(part).is_integer() \
            or not 0 < part <= 2 ** 53 - 1:
        return None
    return {"id": archive["id"][:100], "part": int(part), "closed": archive.get("closed") is True}


def clean_checkpoint(value) -> dict:
    """``cleanCheckpoint``: a recovery checkpoint as it may be kept, or ValueError saying what is wrong with it."""
    if (not isinstance(value, dict) or value.get("format") != CHECKPOINT or isinstance(value.get("version"), bool)
            or value.get("version") != 1 or not isinstance(value.get("parts"), list) or len(value["parts"]) > QUEUE_LIMIT
            or len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)) > RECOVERY_LIMIT):
        raise ValueError("Choose an upload recovery checkpoint with at most 100 files.")
    server = re.sub(r"/+$", "", js_string(value.get("server"))) if _truthy(value.get("server")) else ""
    if server and (href(server) is None or _with_secret(server)):
        raise ValueError("Invalid checkpoint server.")
    visibility = value.get("visibility") if _truthy(value.get("visibility")) else "unlisted"
    if not isinstance(visibility, str) or visibility not in QUEUE_VISIBILITY:
        raise ValueError("Invalid checkpoint visibility.")
    seen, parts = set(), []
    for r in value["parts"]:
        file = r.get("file") if isinstance(r, dict) else None
        if not isinstance(file, str) or not file or len(file) > 1024 or file in seen:
            raise ValueError("Invalid or duplicate checkpoint filename.")
        seen.add(file)
        fingerprint, request_id, log_id = r.get("fingerprint"), r.get("request_id"), r.get("id")
        if fingerprint is not None and not re.fullmatch(r"[a-f0-9]{64}", js_string(fingerprint)):
            raise ValueError("Invalid file fingerprint.")
        if request_id is not None and not re.fullmatch(r"[a-f0-9]{32}", js_string(request_id)):
            raise ValueError("Invalid upload request ID.")
        status = r.get("status") if _truthy(r.get("status")) else "pending"
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Invalid checkpoint status.")
        if log_id is not None and not re.fullmatch(r"[a-z0-9]{6,16}", js_string(log_id), re.I):
            raise ValueError("Invalid uploaded report ID.")
        if status == "uploaded" and (not server or not _truthy(log_id) or not _truthy(fingerprint)):
            raise ValueError("Successful records require a server, ID and fingerprint.")
        parts.append({"file": file, "name": js_string(r.get("name") if _truthy(r.get("name")) else file)[:1024],
                      "title": js_string(r.get("title") if _truthy(r.get("title")) else file)[:200],
                      "fingerprint": fingerprint if _truthy(fingerprint) else None,
                      "request_id": request_id if _truthy(request_id) else None, "status": status,
                      "id": log_id if _truthy(log_id) else None})
    return {"format": CHECKPOINT, "version": 1, "server": server, "visibility": visibility, "parts": parts}


def _with_secret(server: str) -> bool:
    """An address with a user, a password, a query or a fragment: not a checkpoint's server."""
    parts = urllib.parse.urlsplit(server)
    return bool(parts.username or parts.password or parts.query or parts.fragment)


def checkpoint(selected: dict, results: dict, batch: dict | None, chosen: str) -> dict:
    """The queue as its recovery checkpoint keeps it (``checkpoint``): never a key, a private link or a credential."""
    batch = batch or {}
    return clean_checkpoint({
        "format": CHECKPOINT, "version": 1, "server": batch.get("url") or "", "visibility": batch.get("visibility") or chosen,
        "parts": [{"file": r.get("file"), "name": r.get("name") or r.get("file"), "title": queue_label(r),
                   "fingerprint": r.get("fingerprint"), "request_id": r.get("request_id"),
                   "status": (results.get(r.get("file")) or {}).get("status") or "pending",
                   "id": (results.get(r.get("file")) or {}).get("id")} for r in selected.values()]})


def restored(value) -> tuple[dict | None, str, dict, dict]:
    """``restore``: the batch a checkpoint was for, its visibility, its files and their results. An interrupted upload
    is uncertain."""
    parts = value.get("parts") if isinstance(value, dict) else None
    if not isinstance(parts, (list, str)) or not parts:
        raise ValueError("No saved upload queue is available.")
    saved = clean_checkpoint(value)
    batch = {"url": saved["server"], "visibility": saved["visibility"]} if saved["server"] else None
    selected, results = {}, {}
    for item in saved["parts"]:
        row = {"file": item["file"], "name": item["name"], "title": item["title"], "fingerprint": item["fingerprint"],
               "request_id": item["request_id"]}
        selected[row["file"]] = row
        results[row["file"]] = {"status": "unknown" if item["status"] == "uploading" else item["status"], "id": item["id"],
                                "fingerprint": item["fingerprint"]}
    return batch, saved["visibility"], selected, results


def manifest(selected: dict, results: dict, batch: dict | None) -> dict:
    """The upload results (``download``): each file's state, report and error; a link only for a report that is not
    private and whose address holds no secret."""
    doc: dict = {"format": "a2log-upload-manifest", "version": 1}
    if batch:
        doc["server"], doc["visibility"] = batch.get("url"), batch.get("visibility")
    parts = []
    for r in selected.values():
        s = results.get(r.get("file")) or {}
        part = {"file": r.get("file")}
        meta = archive_meta(r.get("archive"))
        if meta is not None:
            part["archive"] = meta
        part["status"] = s.get("status") or "pending"
        part.update({key: s[key] for key in ("id", "error") if key in s})
        if s.get("status") == "uploaded" and s.get("visibility") != "private":
            link = exported_link(s.get("url"))
            if link is not None:
                part["url"] = link
        parts.append(part)
    doc["parts"] = parts
    return doc


def visible_rows(rows: list, words: str, kind: str) -> list[dict]:
    """The files on the page a filter and an encounter type let through."""
    shown_rows = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        contexts = [c for c in _list(r.get("contexts")) if isinstance(c, dict)]
        if kind and not any(c.get("encounter_type") == kind for c in contexts):
            continue
        if words:
            archive = r.get("archive") if isinstance(r.get("archive"), dict) else {}
            text = " ".join(js_string(x) for x in [queue_label(r), archive.get("id"), archive.get("part"),
                                                   *(c.get("encounter_type") for c in contexts)])
            if words.lower() not in text.lower():
                continue
        shown_rows.append(r)
    return shown_rows


def pick(selected: dict, results: dict, row: dict) -> None:
    """A file put in the queue (``pick``), with the fingerprint it was seen with."""
    file = row.get("file")
    if len(selected) >= QUEUE_LIMIT and file not in selected:
        raise ValueError("Queue limit is 100 files. Upload/clear this queue before adding more.")
    if not _truthy(row.get("fingerprint")):
        row["fingerprint"] = (selected.get(file) or {}).get("fingerprint") or (results.get(file) or {}).get("fingerprint")
    selected[file] = row


def request_id() -> str:
    """A new upload's request ID: the server answers a request it already took instead of storing it again."""
    return secrets.token_hex(16)


def upload_body(row: dict, batch: dict) -> dict:
    return {"file": row["file"], "visibility": batch["visibility"], "server": batch["url"], "completed_only": True,
            "fingerprint": row["fingerprint"], "request_id": row["request_id"]}


def uploaded(answer: dict, batch: dict, fingerprint: str) -> dict:
    """A report uploaded: its ID, link and visibility, and a warning when its ownership was not kept."""
    result = {"status": "uploaded", **{key: answer[key] for key in ("id", "url") if key in answer},
              "visibility": answer.get("visibility") or batch.get("visibility")}
    if "ownership_warning" in answer:
        result["warning"] = answer["ownership_warning"]
    result["fingerprint"] = fingerprint
    return result


def refused(message: str) -> tuple[str, bool]:
    """An upload refused: failed when the refusal is one the server gives knowingly, else uncertain (it may have been
    taken); and whether the batch stops there (a connection, sign-in or rate-limit refusal)."""
    known = bool(_KNOWN.search(message))
    return ("failed" if known else "unknown"), (not known or bool(_HALTING.search(message)))


def batch_message(done: int, total: int, cancelled: bool, halted: bool) -> str:
    return (f"{done} / {total} uploaded. " + ("Cancelled between uploads. " if cancelled else "")
            + ("Stopped after a connection, authentication or rate-limit error; remaining files are pending. " if halted else "")
            + "Known successful files are skipped only when their fingerprints match.")


def status_line(row: dict, result: dict | None) -> str:
    """A queued file's line: its state, its error and warning."""
    s = result or {}
    line = f"{queue_label(row)}: {js_text(s.get('status')) if _truthy(s.get('status')) else 'pending'}"
    if _truthy(s.get("error")):
        line += " — " + js_text(s["error"])
    if _truthy(s.get("warning")):
        line += " — " + js_text(s["warning"])
    return line
