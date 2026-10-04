"""Helpers for reading Next.js App Router pages (React Server Component payloads).

Both metabot.gg and gamers4.life ship their data inside
``self.__next_f.push([1, "..."])`` script chunks.  The payload is a list of
``<hex id>:<json>`` rows that reference each other with ``$<id>`` / ``$L<id>``.
"""
from __future__ import annotations

import json
import re

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)


def flight(html: str) -> str:
    """Concatenate and unescape all flight chunks of a page."""
    return "".join(json.loads('"' + c + '"') for c in _PUSH.findall(html))


def rows(data: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in re.split(r"\n(?=[0-9a-f]+:)", data):
        k, _, v = r.partition(":")
        out[k] = v
    return out


def extract_object(s: str, start: int) -> str:
    """Return the balanced ``{...}`` JSON object that starts at ``start``."""
    depth = 0
    in_str = esc = False
    for k in range(start, len(s)):
        c = s[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:k + 1]
    raise ValueError("unbalanced object")


def find_object(data: str, marker: str) -> dict:
    """Find the first JSON object beginning with ``marker`` (e.g. '{"boards":[')."""
    i = data.find(marker)
    if i < 0:
        raise KeyError(marker)
    return json.loads(extract_object(data, i))


def _parse_row(v: str):
    if v.startswith("T"):
        m = re.match(r"T[0-9a-f]+,(.*)", v, re.S)
        return m.group(1) if m else v
    if v.startswith("I["):
        return None
    try:
        return json.loads(v)
    except Exception:
        return None


def text_lines(data: str) -> list[str]:
    """Resolve row references and return all visible text in document order."""
    rs = rows(data)
    cache: dict[str, object] = {}
    out: list[str] = []
    seen: set[str] = set()
    skip = {"className", "style", "href", "src", "d", "viewBox", "icon"}

    def walk(node, depth=0):
        if depth > 400:
            return
        if isinstance(node, str):
            m = re.fullmatch(r"\$L?([0-9a-f]+)", node)
            if m and m.group(1) in rs:
                k = m.group(1)
                if k in seen:
                    return
                seen.add(k)
                if k not in cache:
                    cache[k] = _parse_row(rs[k])
                walk(cache[k], depth + 1)
            elif not node.startswith("$"):
                out.append(node)
            return
        if isinstance(node, list):
            if len(node) == 4 and node[0] == "$" and isinstance(node[3], dict):
                props = node[3]
                if "children" in props:
                    walk(props["children"], depth + 1)
                for kk, vv in props.items():
                    if kk != "children" and kk not in skip and isinstance(vv, (list, dict)):
                        walk(vv, depth + 1)
                return
            for x in node:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            for kk, vv in node.items():
                if kk not in skip:
                    walk(vv, depth + 1)

    walk(_parse_row(rs.get("0", "null")))
    return out
