"""What's new after an update (0.2.353).

On the first launch of a new version the app shows the release notes of the versions the player has not seen
yet, once: closing them records this version, so they never come back. A new install records its version and
shows nothing; an install from before 0.2.353 (which kept no record) shows this version's notes. The notes are
``packaging/RELEASE_NOTES.md``, which the builds carry, drawn as plain HTML; Settings links to every version's
on GitHub.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .. import __version__
from ..paths import home, resource_root

RELEASES_URL = "https://github.com/sam-t-anderson/Aion-2-tools/releases"
STATE = "patch_notes.json"      # {"seen": the version whose notes were closed, or a new install's version}
MOST = 5                        # the versions shown at once, newest first
_LAUNCH = {"earlier": None}     # whether a copy of the app had run here before this launch (see started())


def _vt(v) -> tuple:
    return tuple(int(x) for x in str(v).split(".")[:3] if x.isdigit())


def notes_path() -> Path:
    """The changelog beside the frozen app's files (the builds bundle it), or in the source checkout."""
    return resource_root() / "packaging" / "RELEASE_NOTES.md"


def sections(text: str) -> list[dict]:
    """Each ``## Title (x.y.z)`` section of the changelog, newest first as the file keeps them."""
    out = []
    for part in re.split(r"(?m)^(?=## )", text):
        head, _, body = part.partition("\n")
        m = re.match(r"## (.*?)\s*\((\d+\.\d+\.\d+)\)\s*$", head)
        if m:
            out.append({"version": m.group(2), "title": m.group(1), "body": body.strip()})
    return out


# ------------------------------------------------------------------ Markdown, as far as the changelog uses it
def _inline(text: str) -> str:
    """Escape the text, then draw code spans, http(s) links, bold and italics."""
    codes: list[str] = []

    def keep(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"
    text = re.sub(r"`([^`]+)`", keep, text)
    out = html.escape(text, quote=True)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        if not re.match(r"https?://[^\s\"'<>]+$", url):
            return label
        return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{label}</a>'
    out = re.sub(r"\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)", link, out)    # a URL may hold one level of brackets
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], out)


def _table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    body = [r for r in cells[1:] if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
    head = "".join(f"<th>{_inline(c)}</th>" for c in cells[0])
    rows_html = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table>"


def render(markdown: str) -> str:
    """The changelog's Markdown as HTML: paragraphs, lists (one level of nesting), headings, tables and code
    blocks. Every character of the text is escaped; the only markup is the one drawn here."""
    out: list[str] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        heading = re.match(r"(#{3,6})\s+(.*)", line)
        if heading:
            level = min(6, len(heading.group(1)) + 1)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j]))
            i = j
            continue
        item = re.match(r"(\s*)([-*]|\d+\.)\s+(.*)", line)
        if item:
            tag = "ol" if item.group(2)[0].isdigit() else "ul"
            items: list[list] = []          # [text, [nested items]]
            while i < len(lines):
                m = re.match(r"(\s*)([-*]|\d+\.)\s+(.*)", lines[i])
                if not m:
                    break
                if len(m.group(1)) >= 2 and items:
                    items[-1][1].append(m.group(3))
                else:
                    items.append([m.group(3), []])
                i += 1
            parts = []
            for text, nested in items:
                inner = "<ul>" + "".join(f"<li>{_inline(n)}</li>" for n in nested) + "</ul>" if nested else ""
                parts.append(f"<li>{_inline(text)}{inner}</li>")
            out.append(f"<{tag}>{''.join(parts)}</{tag}>")
            continue
        j = i + 1                           # a paragraph runs on until a blank line or another block
        while (j < len(lines) and lines[j].strip() and not lines[j].startswith("```") and not re.match(r"#{3,6}\s", lines[j])
               and not lines[j].lstrip().startswith("|") and not re.match(r"\s*([-*]|\d+\.)\s+", lines[j])):
            j += 1
        out.append("<p>" + _inline(" ".join(s.strip() for s in lines[i:j])) + "</p>")
        i = j
    return "".join(out)


# ------------------------------------------------------------------ what this launch shows
def _state_path() -> Path:
    return home() / STATE


def _seen() -> str | None:
    try:
        seen = json.loads(_state_path().read_text(encoding="utf-8")).get("seen")
        return seen if isinstance(seen, str) and _vt(seen) else None
    except (OSError, ValueError, AttributeError):
        return None


def mark_seen(version: str | None = None) -> None:
    """Record the version whose notes the player has seen (this one unless named; a new install's too), so they do
    not show again."""
    try:
        path = _state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": version or __version__}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def started() -> None:
    """At the start of a launch, before the app writes anything this launch: an earlier launch here leaves
    app_url.txt (every version since 0.2.10 writes it). A new install records its version and shows nothing."""
    earlier = (home() / "app_url.txt").exists()
    _LAUNCH["earlier"] = earlier
    if not earlier and _seen() is None:
        mark_seen()


def notes_since(seen: str | None, version: str | None = None, text: str | None = None) -> list[dict]:
    """The sections after ``seen`` up to ``version`` (this one unless named), newest first (at most MOST); with
    nothing seen yet, this version's alone."""
    version = version or __version__
    if text is None:
        try:
            text = notes_path().read_text(encoding="utf-8")
        except OSError:
            return []
    now = _vt(version)
    chosen = [s for s in sections(text) if _vt(s["version"]) <= now and (seen is None and _vt(s["version"]) == now
                                                                         or seen is not None and _vt(s["version"]) > _vt(seen))]
    chosen.sort(key=lambda s: _vt(s["version"]), reverse=True)
    return [{"version": s["version"], "title": s["title"], "html": render(s["body"])} for s in chosen[:MOST]]


def pending(force: bool = False) -> dict:
    """What the app shows at launch: ``show`` and the notes once after an update, until they are closed;
    ``force`` (Settings' What's new) gives this version's notes whatever was seen."""
    seen = _seen()
    out = {"version": __version__, "all": RELEASES_URL, "show": False, "notes": []}
    if force:
        out["notes"] = notes_since(None)
        return out
    if seen is not None and _vt(seen) >= _vt(__version__):
        return out
    if seen is None and _LAUNCH["earlier"] is False:       # a new install that could not record itself
        return out
    out["notes"] = notes_since(seen)
    out["show"] = bool(out["notes"])
    return out
