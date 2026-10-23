"""Write ``aion2calc/app/static/server-names.js``: the world (server) names by game server ID.

The app, the overlay, the GitHub Pages site and the log server's pages show a server by its world
name (2102 -> "Zikel") wherever a recording or a report carries only the ID. The names come from
the bundled official server list (``aion2calc/meter/a2parser/data/servers.json``, English column);
this tool renders them as one small script, ``window.A2Servers``, so every page can resolve an ID
without a request. Run it after updating the bundled list; ``tests/test_server_names.py`` fails
when the script is out of date.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "aion2calc" / "meter" / "a2parser" / "data" / "servers.json"
TARGET = ROOT / "aion2calc" / "app" / "static" / "server-names.js"

HEADER = """\
/* World (server) names by game server ID, for every page that shows a recording's server:
   A2Servers.name(2102) -> "Zikel"; A2Servers.label(2102) -> "Zikel", A2Servers.label(99, "server 99") -> "server 99".
   Generated from aion2calc/meter/a2parser/data/servers.json (the bundled official server list, English
   names) by tools/export_server_names.py: do not edit by hand. Shared by the desktop app, the overlay,
   the GitHub Pages site and the log server's pages. */
(function () {
  "use strict";
  const NAMES = {
"""

FOOTER = """\
  };
  // The world name for a server ID (a number or its string), or null when the list has no such ID.
  const name = (id) => { const key = String(id ?? "").trim(); return Object.prototype.hasOwnProperty.call(NAMES, key) ? NAMES[key] : null; };
  // The world name, else `fallback` when given, else "server <id>" (empty for an empty ID).
  const label = (id, fallback) => name(id) || (fallback !== undefined ? fallback : (String(id ?? "").trim() ? "server " + String(id).trim() : ""));
  window.A2Servers = { name, label, names: NAMES };
})();
"""


def names(source: Path = SOURCE) -> dict[str, str]:
    """``{server id: English world name}`` from the bundled list, in numeric ID order."""
    table = json.loads(source.read_text(encoding="utf-8")).get("servers") or {}
    out = {}
    for sid, row in table.items():
        if not isinstance(row, dict):
            continue
        value = row.get("en") or next((v for v in row.values() if isinstance(v, str) and v.strip()), None)
        if isinstance(value, str) and value.strip() and str(sid).strip().isdigit():
            out[str(sid).strip()] = value.strip()
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def render(source: Path = SOURCE) -> str:
    """The script's text: the header, the table wrapped at about 100 columns, the helpers."""
    entries = [f"{json.dumps(sid)}: {json.dumps(value, ensure_ascii=False)}" for sid, value in names(source).items()]
    lines, line = [], "   "
    for entry in entries:
        piece = " " + entry + ","
        if len(line) + len(piece) > 100 and line.strip():
            lines.append(line)
            line = "   "
        line += piece
    if line.strip():
        lines.append(line)
    return HEADER + "\n".join(lines) + "\n" + FOOTER


def main() -> None:
    text = render()
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"{TARGET.relative_to(ROOT)}: {len(names())} servers, {len(text.encode('utf-8'))} bytes")


if __name__ == "__main__":
    main()
