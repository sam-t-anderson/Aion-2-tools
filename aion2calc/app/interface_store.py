"""The interfaces' own data in one place (0.2.482): what the web pages keep in their browser's storage (the theme, the
accent colour, the language, the customization profiles, the raid plans, the builds and the screenshots, each page's
choices) and what the native window and overlay keep (their settings files until now), kept by the app in its data
folder (``interface.json``) and given to both interfaces.

Each value is a text, as a browser's storage keeps it, under the same key. The web pages get the app's values with
the page itself (``page_with_store``), before any of their scripts reads its storage, and send what they change
(``static/store.js``); the native interface reads and writes them through ``/api/interface`` (``gui/interface.py``).
Messages between a browser's windows (``aion2calc-closing``) are not data and stay in the browser.
"""
from __future__ import annotations

import json
import threading

from ..paths import user_data, write_user_json

FILE = "interface.json"
#: Keys a browser keeps for itself: a message between its windows, its own mark that it gave its data over once, and
#: its list of the changes the app has not yet said it kept (``static/store.js``).
LOCAL_ONLY = frozenset({"aion2calc-closing", "a2-store-browser", "a2-store-pending"})
KEY_LIMIT = 300                                    # a key's length
LIMIT = 64 * 1024 * 1024                           # everything kept, in characters (a browser keeps 5 MB a site)
_lock = threading.Lock()


def _path():
    return user_data() / FILE


def values() -> dict[str, str]:
    """Everything kept, by key; nothing when the file is missing or unreadable."""
    try:
        kept = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    kept = kept.get("values") if isinstance(kept, dict) else None
    return {k: v for k, v in kept.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(kept, dict) else {}


def update(changes) -> dict:
    """Keep each key's new text, or forget the key where its value is null; keys a browser keeps for itself are left
    out. ValueError for what is not a set of keys and texts, or would make the store too large."""
    if not isinstance(changes, dict):
        raise ValueError("set must be an object of keys and texts")
    for key, value in changes.items():
        if not isinstance(key, str) or not key or len(key) > KEY_LIMIT:
            raise ValueError("each key must be a text of 1 to 300 characters")
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{key}: a value must be a text, or null to forget it")
    with _lock:
        kept = values()
        for key, value in changes.items():
            if key in LOCAL_ONLY:
                continue
            if value is None:
                kept.pop(key, None)
            else:
                kept[key] = value
        if sum(len(k) + len(v) for k, v in kept.items()) > LIMIT:
            raise ValueError("the interfaces' data would be larger than 64 MB")
        write_user_json({"values": kept}, FILE)
    return {"ok": True}


def page_with_store(html: str) -> str:
    """A page of the web interface with the app's data before its first script (``window.A2STORE``, then
    ``store.js``): the data written so no text in it ends the script or the page's markup."""
    data = json.dumps(values(), ensure_ascii=False, separators=(",", ":"))
    for ch in ("<", ">", "&", chr(0x2028), chr(0x2029)):
        data = data.replace(ch, chr(92) + "u" + format(ord(ch), "04x"))
    tags = f'<script>window.A2STORE={data};</script><script src="/static/store.js"></script>'
    for mark in ('<meta charset="utf-8">', "<head>"):             # after the page's charset, before its first script
        at = html.find(mark)
        if at >= 0:
            at += len(mark)
            return html[:at] + tags + html[at:]
    return tags + html
