"""The customization profiles (0.2.485), as pages/settings.js keeps and shares them: a named bundle of the whole look
(the theme, the accent colour, the class colours, the overlay's look and its background image) to switch to in a
click. They are kept under ``a2-custom-profiles``, a list in JSON, where the web page keeps them; since 0.2.482 that
is the app's interface data, so the web pages and the window share them. The settings page (settings_page.py) draws
the row.

A share code is ``A2PROF1:`` then the profile without its image, as JSON, in UTF-8, in base64 (``encodeProfile``);
one read (``decodeProfile``) keeps only a theme and an accent the pages know, the overlay look's settings and the class
colours.
"""
from __future__ import annotations

import base64

from . import settings_looks as looks
from . import theme

KEY = "a2-custom-profiles"
CODE_PREFIX = "A2PROF1:"
NAME_LIMIT = 40
IMAGE_SIDE, IMAGE_QUALITY = 1400, 82              # ``downscaleImageToDataUrl(blob, 1400, 0.82)``

LABEL = "Customization profile"
CHOOSE = "Choose a profile…"
NONE_YET = "No saved profiles yet"
APPLY = "Apply"
SAVE_AS = "Save current as…"
DELETE = "Delete"
COPY = "Copy share code"
PASTE = "Paste a shared code…"
NOTE = ("A profile bundles your whole look — <strong>theme</strong>, <strong>accent colour</strong>, <strong>class "
        "colours</strong>, the <strong>overlay look</strong> and your <strong>overlay background image</strong> — into "
        "one named set you can switch between in a click. Kept by the app on your machine, for its window and the web "
        "pages alike. Any profile that carries a background shows as a square above; click it to apply. The bundled "
        "image stays on your machine — it is never uploaded and is left out of the <strong>Copy share code</strong> "
        "(which carries only your colours and settings), and it is kept at a reduced size so it fits.")
NAME_IT = "Name this customization profile:"
NAME_TOO_LONG = "Name must be 40 characters or fewer."
SAVING = "Saving…"
SAVED = "Profile saved"
SAVED_WITH_IMAGE = "Profile saved with its background"
IMAGE_TOO_BIG = "Saved, but the background was too large to bundle in this browser."
PICK_TO_APPLY = "Pick a profile to apply."
PICK_TO_DELETE = "Pick a profile to delete."
PICK_TO_COPY = "Pick a profile to copy."
NOT_FOUND = "Profile not found."
APPLYING = "Applying…"
APPLIED = "Profile applied"
DELETED = "Profile deleted"
COPIED = "Share code copied — send it to a friend."
PASTE_IT = "Paste a profile share code:"
NOT_A_CODE = "That is not a valid profile share code."
SAVE_SHARED_AS = "Save the shared profile as:"
SHARED_SAVED = "Shared profile saved"
SHARED = "Shared profile"


_BOM = chr(0xFEFF)


def _text(value) -> str:
    """``String(value ?? "")``: a list's items joined with commas, an object as JavaScript names one."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    if isinstance(value, dict):
        return "[object Object]"
    if isinstance(value, list):
        return ",".join(_text(item) for item in value)
    return str(value)


def profiles(store) -> list:
    """``getCustomProfiles``: the kept list, or none where it is not a list of JSON."""
    try:
        raw = store.value(KEY) or "[]"
        # JSON.parse, which reads no byte-order mark (js_parse, a file's reading, takes one off)
        found = None if raw.startswith(_BOM) else looks.js_parse(raw.encode("utf-8"))
    except (ValueError, RecursionError, AttributeError):
        return []
    return found if isinstance(found, list) else []


def save(store, kept: list) -> None:
    """``saveCustomProfiles``: the list kept as JSON."""
    store.setValue(KEY, looks.js_json(kept))


def name_of(profile) -> str:
    return _text(profile.get("name")) if isinstance(profile, dict) else ""


def options(kept: list) -> list[tuple[str, str]]:
    """``customProfileOptions``: the list's first line (its value empty), then each profile by its name."""
    return [("", CHOOSE if kept else NONE_YET)] + [(name_of(p), name_of(p)) for p in kept]


def with_images(kept: list) -> list:
    """``customProfileGallery``: the profiles carrying a background, each shown as a square."""
    return [p for p in kept if isinstance(p, dict) and isinstance(p.get("bg"), str) and p["bg"]]


def find(kept: list, name: str):
    """The profile of that name, its case as it is (``p.name === sel``)."""
    return next((p for p in kept if isinstance(p, dict) and p.get("name") == name), None)


def without(kept: list, name: str) -> list:
    """The list without the profile of that name, whatever its case (``p.name.toLowerCase() !== …``)."""
    low = name.lower()
    return [p for p in kept if name_of(p).lower() != low]


def look_of(fresh: dict) -> dict:
    """The look a profile bundles from the app's settings: the overlay look's settings it has, then its class
    colours."""
    look = {key: fresh[key] for key in looks.visual_keys() if key in fresh}
    if "combat_colors" in fresh:
        look["combat_colors"] = fresh["combat_colors"]
    return look


def encode(profile: dict) -> str:
    """``encodeProfile``: the profile without its image, as JSON, in UTF-8, in base64, after ``A2PROF1:``."""
    rest = {key: value for key, value in profile.items() if key != "bg"}
    return CODE_PREFIX + base64.b64encode(looks.js_json(rest).encode("utf-8")).decode("ascii")


def decode(code: str) -> dict:
    """``decodeProfile``: a shared code read; ValueError where it is not one."""
    raw = looks.js_trim(code)
    data = raw[len(CODE_PREFIX):] if raw.startswith(CODE_PREFIX) else raw
    try:
        doc = looks.js_parse(looks._atob(data))
    except (ValueError, RecursionError) as problem:
        raise ValueError("not a profile") from problem
    if not isinstance(doc, (dict, list)):                # ``typeof obj !== "object"``: a list is one
        raise ValueError("not a profile")
    get = doc.get if isinstance(doc, dict) else (lambda _key, _default=None: None)
    chosen, accent = get("theme"), get("accent")
    src = get("ui")
    src = src if isinstance(src, dict) else {}
    ui = {key: src[key] for key in looks.visual_keys() if key in src}
    if "combat_colors" in src:
        ui["combat_colors"] = src["combat_colors"]
    name = get("name")
    return {"name": looks.js_slice(_text(name) if name else "", NAME_LIMIT) or SHARED,
            "theme": chosen if chosen in theme.THEMES else "system",
            "accent": accent if accent in theme.ACCENTS else "gold", "ui": ui}


def image_url(raw: bytes) -> str:
    """``downscaleImageToDataUrl``: a background's picture at most 1400 pixels a side (each side rounded), as a JPEG
    of quality 0.82 in a data address; nothing where it is not a picture."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    picture = QImage.fromData(raw)
    if picture.isNull():
        return ""
    w, h = picture.width(), picture.height()
    scale = min(1.0, IMAGE_SIDE / max(w, h or 1))
    w, h = max(1, round(w * scale)), max(1, round(h * scale))
    canvas = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(QColor(0, 0, 0, 0))                # a canvas: what a picture leaves clear is black in a JPEG
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawImage(canvas.rect(), picture.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not canvas.convertToFormat(QImage.Format_RGB32).save(buffer, "JPEG", IMAGE_QUALITY):
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(bytes(data)).decode("ascii")
