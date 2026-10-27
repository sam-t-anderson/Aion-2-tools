"""One screen read from start to finish, the recent reads the app's pages pick up, and the pages of the
Title window read so far.

A read takes a picture of the game window (or a screenshot the player pasted), has Windows read it
twice (enlarged, then in grey with light text turned dark on light, as the engine reads small light
interface text on a dark background best one way or the other) and keeps the better result. A hotkey
read lands in the recent reads, where the Genus editor and the titles panel find it when the player
comes back to the app; nothing reaches a character until the player saves it there.

The titles a character owns come from the Title window's pages: a page read with "Show unacquired
titles only" ticked lists titles the character does not have, so every title of the character's
faction that no such page listed is owned (``title_summary``).
"""
from __future__ import annotations

import base64
import binascii
import io
import itertools
import threading
import time
from collections import Counter, deque
from concurrent.futures import TimeoutError as _Timeout

from ..paths import read_json
from . import ocr, parse

#: the reads the pages pick up (a hotkey read waits here while the app is in the background)
KEEP_READS = 20
#: the Title window pages kept for the owned-titles list
KEEP_PAGES = 400
#: the largest screenshot a page may send (a 4K screenshot as PNG is about 10 MB)
MAX_IMAGE_BYTES = 24 * 1024 * 1024
MAX_PIXELS = 40_000_000
#: the longest wait before a read started in the app (time to switch to the game)
MAX_DELAY_S = 10.0
#: what is kept of the text read when no window was recognised, to show the player what was seen
SEEN_LINES = 40

_LOCK = threading.Lock()
_BUSY = threading.Lock()                # one read at a time
_IDS = itertools.count(1)
_READS: deque = deque(maxlen=KEEP_READS)
_PAGES: list[dict] = []
_AVAILABLE: tuple[bool, str] | None = None


def available(refresh: bool = False) -> tuple[bool, str]:
    """Whether Windows can read text on this computer, and why not; asked once. While a read is running
    (a hotkey's, before any page asked), it is answered at once rather than after the read, which holds
    the engine's one thread."""
    global _AVAILABLE
    if _AVAILABLE is None or refresh:
        if _BUSY.locked():
            return True, "reading the screen"
        _AVAILABLE = ocr.available()
    return _AVAILABLE


def status(since: int = 0) -> dict:
    """What ``GET /api/screen-read`` answers: whether reads work here and the reads newer than ``since``."""
    ok, message = available()
    with _LOCK:
        reads = [dict(read) for read in _READS if read["id"] > since]
        latest = _READS[-1]["id"] if _READS else 0
    return {"available": ok, "message": message, "latest": latest, "reads": reads}


def image_from_data_url(text) -> "object":
    """The screenshot a page sent as a ``data:image/...;base64,`` URL (pasted or chosen): PNG, JPEG, BMP
    or WebP, at most ``MAX_IMAGE_BYTES`` and ``MAX_PIXELS``."""
    if not isinstance(text, str) or not text.startswith("data:image/"):
        raise ValueError("Send the screenshot as a data:image URL.")
    head, _, data = text.partition(",")
    if not head.endswith(";base64"):
        raise ValueError("Send the screenshot base64-encoded.")
    if len(data) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        raise ValueError(f"The screenshot is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("The screenshot could not be decoded.") from None
    from PIL import Image
    try:
        picture = Image.open(io.BytesIO(raw), formats=["PNG", "JPEG", "BMP", "WEBP"])
    except Exception:  # noqa: BLE001 - any picture Pillow cannot open is "not a screenshot"
        raise ValueError("The file is not a PNG, JPEG, BMP or WebP picture.") from None
    if picture.width * picture.height > MAX_PIXELS:
        raise ValueError("The screenshot is larger than 40 megapixels.")
    try:
        picture.load()
    except Exception as err:  # noqa: BLE001
        raise ValueError(f"The screenshot could not be read ({type(err).__name__}).") from None
    return picture


def _copies(picture):
    """The copies of ``picture`` the engine reads, with the factor each is enlarged by: the screen at
    twice its size (interface text a dozen pixels tall reads better larger), then the same in grey with
    the light text turned dark on light."""
    from PIL import Image, ImageOps
    rgb = picture.convert("RGB")
    w, h = rgb.size
    factor = 2 if h <= 1600 and max(w, h) * 2 <= 7680 else 1
    large = rgb.resize((w * factor, h * factor), Image.LANCZOS) if factor > 1 else rgb
    yield large, factor
    yield ImageOps.autocontrast(ImageOps.invert(large.convert("L")), cutoff=1).convert("RGB"), factor


def _quality(found: dict) -> float:
    if found.get("kind") == "genus":
        return 100 + sum(1 if line["check"] else 3 for line in found["lines"]) + (2 if found["level"] else 0)
    if found.get("kind") == "titles":
        return (50 + len(found["titles"]) + (1 if found["collection"] else 0)
                + (1 if found["unacquired_only"] is not None else 0))
    return 0


def _complete(found: dict) -> bool:
    """A genus read with its level and every open slot read and in range: the second copy cannot do better."""
    return (found.get("kind") == "genus" and found["level"] is not None
            and len(found["lines"]) >= min(found["level"], 9) and not any(line["check"] for line in found["lines"]))


def _merged_titles(best: dict, found: dict) -> dict:
    """Two reads of one Title window page: the titles either found (the catalog match keeps a misread
    out), and the box and the count from whichever saw them."""
    merged = dict(best)
    merged["titles"] = list(dict.fromkeys(best["titles"] + found["titles"]))
    merged["collection"] = best["collection"] or found["collection"]
    if merged["unacquired_only"] is None:
        merged["unacquired_only"] = found["unacquired_only"]
    return merged


def read_picture(picture) -> dict:
    """What ``picture`` shows (``parse.parse``), the better of the engine's two reads."""
    best, seen = None, []
    for copy, factor in _copies(picture):
        lines = ocr.scaled(ocr.recognize(copy), 1 / factor)
        found = parse.parse(lines, picture)
        if not seen:
            seen = [" ".join(word.text for word in row) for row in parse.rows(lines)][:SEEN_LINES]
        if best is not None and best.get("kind") == "titles" and found.get("kind") == "titles":
            best = _merged_titles(best, found)
        elif best is None or _quality(found) > _quality(best):
            best = found
        if _complete(best):
            break
    if best.get("kind") is None:
        best = dict(best, seen=seen)
    return best


def read(picture=None, *, source: str = "screen", delay: float = 0) -> dict:
    """One read, kept with the recent reads: the game screen (after ``delay`` seconds, to switch to the
    game) or ``picture``. The record says ``kind`` ("genus", "titles" or None), what was read, and
    ``error`` when the read could not run."""
    record = {"source": source, "at": time.time()}
    if not _BUSY.acquire(timeout=ocr.TIMEOUT_S * 2):
        raise RuntimeError("Another screen read is still running.")
    try:
        if delay:
            time.sleep(min(max(float(delay), 0.0), MAX_DELAY_S))
        try:
            if picture is None:
                from .capture import game_screen
                picture, record["where"] = game_screen()
            record["size"] = list(picture.size)
            record.update(read_picture(picture))
        except ocr.Unavailable as err:
            record.update(kind=None, error=str(err))
        except _Timeout:
            record.update(kind=None, error="Windows took too long to read the screen. Try again.")
        except Exception as err:  # noqa: BLE001 - the player sees why, and can read again or type the lines in
            record.update(kind=None, error=f"The screen could not be read ({type(err).__name__}: {err}).")
    finally:
        _BUSY.release()
    with _LOCK:
        record["id"] = next(_IDS)
        _READS.append(record)
        if record.get("kind") == "titles":
            _PAGES.append({"id": record["id"], "at": record["at"], "titles": list(record["titles"]),
                           "unacquired_only": record["unacquired_only"], "collection": record["collection"]})
            del _PAGES[:-KEEP_PAGES]
    return record


def set_page_mode(page_id: int, unacquired_only) -> None:
    """Correct whether "Show unacquired titles only" was ticked on a page (None: not known)."""
    if unacquired_only not in (True, False, None):
        raise ValueError("unacquired_only must be true, false or null")
    with _LOCK:
        page = next((page for page in _PAGES if page["id"] == page_id), None)
        if page is None:
            raise ValueError("That page is no longer kept: read it again.")
        page["unacquired_only"] = unacquired_only


def forget_page(page_id: int) -> None:
    with _LOCK:
        _PAGES[:] = [page for page in _PAGES if page["id"] != page_id]


def clear_pages() -> None:
    with _LOCK:
        _PAGES.clear()


def _faction(title: dict) -> str:
    side = str(title.get("faction") or "").casefold()
    return "asmodian" if side.startswith("asmo") else "elyos" if side.startswith("ely") else "both"


def _faction_of(names, catalog: list[dict]) -> str | None:
    """The faction whose own titles the pages showed (the window lists one faction's), when they agree."""
    sides = Counter(_faction(title) for title in catalog if title["name"] in names)
    sides.pop("both", None)
    if not sides:
        return None
    side, count = sides.most_common(1)[0]
    return side if count >= 0.8 * sum(sides.values()) else None


def title_summary(pages: list[dict] | None = None, faction: str | None = None) -> dict:
    """What the Title window pages read so far say: ``{"pages", "unacquired", "seen", "owned", "basis",
    "faction", "faction_titles", "collection", "notes"}``.

    ``owned`` is every catalog title of the character's faction (``faction``, else the faction the pages
    show) that no page read with "Show unacquired titles only" ticked listed (``basis`` "catalog"); with
    no faction, the titles seen on unticked pages that no ticked page listed ("seen"). The game's own
    count (``collection``) checks the list."""
    if pages is None:
        with _LOCK:
            pages = [dict(page) for page in _PAGES]
    catalog = read_json("global", "titles.json")
    unacquired = list(dict.fromkeys(t for page in pages if page["unacquired_only"] is True for t in page["titles"]))
    seen = list(dict.fromkeys(t for page in pages if page["unacquired_only"] is False for t in page["titles"]))
    faction = faction if faction in ("elyos", "asmodian") else _faction_of(set(unacquired) | set(seen), catalog)
    mine = [title["name"] for title in catalog if faction and _faction(title) in ("both", faction)]
    collection = next((page["collection"] for page in reversed(pages) if page.get("collection")), None)
    gone = set(unacquired)
    if unacquired and faction:
        owned, basis = [name for name in mine if name not in gone], "catalog"
    elif unacquired and seen:
        owned, basis = [name for name in seen if name not in gone], "seen"
    else:
        owned, basis = [], None
    notes = []
    unknown = sum(1 for page in pages if page["unacquired_only"] is None)
    if not pages:
        notes.append("Open the Title window in the game, tick “Show unacquired titles only”, and read each page.")
    elif not unacquired:
        notes.append("No page was read with “Show unacquired titles only” ticked. Tick it and read those pages: "
                     "the titles they list are the ones you do not have yet.")
    if unknown:
        notes.append(f"{unknown} page{'s' if unknown > 1 else ''} did not show whether “Show unacquired titles only” "
                     "was ticked: choose it for each in the list of pages.")
    if unacquired and not faction and not seen:
        notes.append("The character's faction is not known, so the titles you own cannot be worked out from the "
                     "catalog: also read the pages with the box unticked.")
    if basis == "catalog" and collection:
        if len(owned) == collection["owned"]:
            notes.append(f"This matches the game's count: {collection['owned']} of {collection['total']} titles.")
        else:
            notes.append(f"The game counts {collection['owned']} of {collection['total']} titles collected; this list has "
                         f"{len(owned)}. Read any unacquired pages you missed, and check the list before you save it.")
    return {"pages": pages, "unacquired": unacquired, "seen": seen, "owned": owned, "basis": basis,
            "faction": faction, "faction_titles": len(mine), "collection": collection, "notes": notes}


def control(body: dict, faction: str | None = None) -> dict:
    """``POST /api/screen-read``: ``{"action": "read", "delay": seconds}`` (the game screen),
    ``{"action": "image", "image": "data:image/png;base64,..."}`` (a screenshot), ``{"action": "page",
    "page": id, "unacquired_only": true | false | null}``, ``{"action": "forget-page", "page": id}`` or
    ``{"action": "clear-titles"}``. A read returns its record; the others the title summary."""
    action = body.get("action")
    if action == "read":
        delay = body.get("delay") or 0
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= MAX_DELAY_S:
            raise ValueError(f"delay must be 0 to {MAX_DELAY_S:g} seconds")
        return read(source="screen", delay=delay)
    if action == "image":
        return read(image_from_data_url(body.get("image")), source="screenshot")
    if action in ("page", "forget-page"):
        page = body.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            raise ValueError("page must be a page id")
        if action == "page":
            set_page_mode(page, body.get("unacquired_only"))
        else:
            forget_page(page)
        return title_summary(faction=faction)
    if action == "clear-titles":
        clear_pages()
        return title_summary(faction=faction)
    raise ValueError("action must be read, image, page, forget-page or clear-titles")
