"""The Combat Logs page's words (0.2.450), as pages/combat.js writes them: its views and lists, and the Saved Logs list
(a fight analyzed from a link or a file, the folder the analyzed logs are kept in, the log server shared to, and the
encounters analyzed).
"""
from __future__ import annotations

import gzip
import urllib.parse

from .results import _dict, _list, cap, js_text, n0
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
ON_THE_WEB_PART = "These open in the web interface for now."


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
