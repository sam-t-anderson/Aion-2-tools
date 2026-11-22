"""The overlay's look on the native Settings page (0.2.480), as pages/settings.js draws and saves it: the text's colours
and the fonts (**Overlay colors & fonts**), the text effects and each element's own font, the background image with its
sliders and auto-contrast, and the look presets with their share codes. The page (settings_page.py) draws them.

The starter presets, their descriptions and the settings a preset carries are read from the web page's own script
(``BUNDLED_PRESETS``, ``BUNDLED_PRESET_DESC`` and ``OVERLAY_VISUAL_KEYS``), so both pages offer the same ones. A share code
is the web page's too (``A2P1:``, then the preset as JSON in base64), so a code copied on one page opens on the other.
"""
from __future__ import annotations

import base64
import functools
import json
import math
import os
import re

from .results import _dict, _list, _truthy, js_text

#: The web page's script, shipped with the app: the presets are read from it.
SETTINGS_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "pages",
                           "settings.js")
SAVING = "Saving…"

# ------------------------------------------------------------------ Overlay colors & fonts
#: Each picker's colour until one is chosen: the overlay stylesheet's own (``OVERLAY_TEXT_DEFAULTS``).
TEXT_DEFAULTS = {"rate": "#ffffff", "total": "#9bb1c1", "name": "#e9f7ff", "header": "#e8cf8e", "target": "#f0d6da",
                 "hp": "#e9a4b6", "ttk": "#e3ad7f", "label": "#b39aa2", "also": "#c9a86a", "ping": "#76c59d",
                 "identity": "#e8cf8e"}
#: The text's colours in the row's order (``#ov-rate-color`` …): the element each one colours, and its words.
TEXT_COLOURS = (("rate", "Rate text"), ("total", "Total / share text"), ("name", "Player name"), ("header", "Header"),
                ("target", "Target text"), ("hp", "Enemy-HP text"), ("ttk", "TTK text"), ("label", "Labels"),
                ("also", "Also-targets +N"), ("ping", "Ping line"), ("identity", "Identity line"))
COLOURS_RESET = "Reset number colors"
RESET_COLOURS = ("rate", "total")                   # what Reset number colors puts back
#: The overlay's fonts as the app takes them (``""`` is the overlay's own).
FONTS = ("", "Segoe UI", "Arial", "Verdana", "Georgia", "Trebuchet MS", "Consolas", "Tahoma")
WEIGHTS = (400, 500, 600, 700, 800)
FONT = "Font"
DEFAULT_FONT = "Default"
SIZE = "Size"
WEIGHT = "Weight"
SIZE_RANGE = "Size must be 80–160%."
OUTLINE_TIP = "A crisp outline around the text for legibility over busy backgrounds (separate from the soft glow)"
CYCLE_TIP = "Slowly cycle the header and player names through the colour spectrum (respects your reduced-motion setting)"
#: The font line after its font, size and weight: a checkbox (its setting, words and tip; on only when true) or a
#: colour (its setting, words, and the colour until one is chosen).
FONT_LINE = (("check", "overlay_glow", "Text glow", ""), ("colour", "overlay_glow_color", "Glow color", "#e8cf8e"),
             ("colour", "overlay_hp_color", "Enemy HP bar color", "#e4808f"),
             ("colour", "overlay_ttk_color", "TTK bar color", "#86a9c6"),
             ("check", "overlay_text_outline", "Text outline", OUTLINE_TIP),
             ("colour", "overlay_outline_color", "Outline color", "#000000"),
             ("check", "overlay_color_cycle", "Colour-cycle", CYCLE_TIP))
COLOURS_NOTE = "Number colors apply to DPS, HPS and D.Taken. Changes reach an open overlay within 10 seconds."

# ------------------------------------------------------------------ Overlay text effects & per-element fonts
HALO_TIP = "A soft luminous ring around the overlay text, layered on top of any glow"
RETRO_TIP = ("A subtle sheen sweeping across the headline text, like reflective material catching light (respects your "
             "reduced-motion setting)")
#: The effects' line, described as the font line is; they are said where the fonts are (``saveFont``).
EFFECTS = (("check", "overlay_text_halo", "Halo", HALO_TIP), ("colour", "overlay_halo_color", "Halo color", "#e8cf8e"),
           ("check", "overlay_text_retro", "Retroreflection", RETRO_TIP))
#: The overlay's texts that take a font of their own (``#ov-fe-el``).
ELEMENTS = (("rate", "Rate (DPS/HPS)"), ("total", "Total · percent"), ("name", "Player name"), ("header", "Header"),
            ("target", "Target line"), ("hp", "Target HP"), ("ttk", "Target TTK"), ("label", "Target label"),
            ("also", "Also-targets +N"), ("ping", "Ping line"), ("identity", "Identity line"))
ELEMENT = "Element"
INHERIT = "Inherit"
AUTO = "Auto"
AUTO_SIZE = "auto"
ELEMENT_RESET = "Reset element"
ELEMENTS_NOTE = ("Each element's font falls back to the overlay font above when left on Inherit/Auto. Changes reach an "
                 "open overlay within 10 seconds.")

# ------------------------------------------------------------------ Overlay background
BG_CHOOSE = "Choose image"
BG_REMOVE = "Remove"
BG_SET = "An image is set."
BG_NONE = "No image set."
#: The background's numbers: the setting, its words, its limits, the number shown until one is saved, and how the
#: app's is read (``nullish``: ``v ?? d``; ``or``: ``Number(v) || d``).
BG_NUMBERS = (("overlay_bg_opacity", "Visibility", 0, 100, 100, "nullish"),
              ("overlay_bg_zoom", "Zoom", 50, 200, 100, "or"),
              ("overlay_bg_darken", "Darken", 0, 100, 20, "nullish"))
AUTOCONTRAST = "Auto-contrast text to image"
AUTOCONTRASTS = (("off", "Off"), ("blend", "Dynamic (per-pixel blend)"), ("luminance", "By brightness (computed)"))
BG_NOTE = ("A PNG or JPEG (8 MB max) shown behind the overlay card. Set Visibility above 0 to show it. The image is "
           "stored locally, not in the settings backup. <strong>Auto-contrast</strong> keeps the text legible against "
           "that image: <em>Dynamic</em> paints each glyph as the inverse of whatever is behind it (a "
           "<code>mix-blend-mode</code>); <em>By brightness</em> picks one light or dark colour from the image's relative "
           "luminance. It only reads the overlay's own image — not the game behind a transparent window — so set a "
           "background image to use it.")
BG_LIMIT = 8 * 1024 * 1024
BG_TOO_BIG = "Image must be 8 MB or smaller."
BG_UPLOADING = "Uploading…"
BG_UPLOADED = "Image set. Set Visibility above 0 to show it."
BG_REMOVED = "Removed."
BG_READ_FAILED = "Could not read the file"
#: A file's kind as the browser names it for its data address (``FileReader``), by its name's end.
BG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
BG_FILES = "Images (*.png *.jpg *.jpeg)"


def bg_range(low: int, high: int) -> str:
    """A background number outside its limits (``saveBgNum``)."""
    return f"Enter {low}–{high}."


# ------------------------------------------------------------------ Overlay look presets
PRESET = "Overlay look preset"
STARTER = "Starter presets"
SAVED_PRESETS = "Saved presets"
APPLY = "Apply"
SAVE_AS = "Save current look as…"
DELETE = "Delete"
COPY = "Copy share code"
PASTE = "Paste a shared code…"
PRESETS_NOTE = ("A preset bundles the overlay's colors, fonts, glow, enemy-HP color, background sliders, name display and "
                "per-class bar colors (not the background image). Saved presets ride the settings backup file. "
                "<strong>Copy share code</strong> turns the selected preset into a short code to send a friend; "
                "<strong>Paste a shared code</strong> saves one they sent you.")
YOURS = "Your saved preset."
NOT_FOUND = "Preset not found."
APPLYING = "Applying…"
APPLIED = "Preset applied"
NAME_IT = "Name this preset:"
NAME_LIMIT = 40
NAME_TOO_LONG = "Name must be 40 characters or fewer."
SAVED_IT = "Preset saved"
PICK_SAVED = "Pick a saved preset to delete."
DELETING = "Deleting…"
DELETED = "Preset deleted"
MY_LOOK = "My overlay look"
COPIED = "Share code copied — send it to a friend."
PASTE_IT = "Paste a preset share code:"
NOT_A_CODE = "That is not a valid preset share code."
SAVE_SHARED_AS = "Save the shared preset as:"
SHARED = "Shared preset"
SHARED_SAVED = "Shared preset saved"
CODE_PREFIX = "A2P1:"


def could_not_save(why: str) -> str:
    """A shared preset the app did not save."""
    return "Could not save: " + why


# ------------------------------------------------------------------ the values shown
def hex_colour(value, fallback: str) -> str:
    """A colour picker's colour: the app's when it is a six-digit hex colour (``/^#[0-9a-f]{6}$/i``), else ``fallback``;
    in lower case, as a picker gives it."""
    return value.lower() if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def text_colours(ui) -> dict:
    """The text's colours shown (``overlayText``): each element's, or the overlay stylesheet's own."""
    colours = _dict(_dict(ui).get("overlay_text_colors"))
    return {element: hex_colour(colours.get(element), TEXT_DEFAULTS[element]) for element, _words in TEXT_COLOURS}


def font_family(ui) -> str:
    """The overlay's font (``ui.overlay_font_family || ""``); the list shows its first, Default, for one it lacks."""
    family = _dict(ui).get("overlay_font_family")
    return family if _truthy(family) else ""


def font_weight(ui) -> int:
    """The overlay's weight (``Number(ui.overlay_font_weight) || 600``), or the list's first when it is none of its."""
    from .settings_words import _js_number
    x = _js_number(_dict(ui).get("overlay_font_weight"))
    x = x if x else 600                                     # NaN (None) and 0 read as none
    return next((weight for weight in WEIGHTS if weight == x), WEIGHTS[0])


def _number(value):
    """A value that is a number (``Number.isFinite``), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def element_fonts(ui) -> dict:
    """Each element's own font as the app has it (``{...ui.overlay_text_fonts}``), copied to be changed one at a time."""
    return dict(_dict(_dict(ui).get("overlay_text_fonts")))


def element_shown(fonts: dict, element: str) -> tuple:
    """An element's font, size and weight as its fields show them (``feLoad``): ``""`` for its font when it has none,
    and its size and weight only when they are numbers (None: the field left empty, *auto* or *Auto*)."""
    entry = fonts.get(element)
    entry = _dict(entry) if _truthy(entry) else {}
    family = entry.get("family")
    return (family if _truthy(family) else "", _number(entry.get("scale")), _number(entry.get("weight")))


def element_entry(family: str, scale, weight) -> dict:
    """An element's font to save (``feSave``): what of its font, size and weight is set."""
    entry = {}
    if family:
        entry["family"] = family
    if scale is not None:
        entry["scale"] = scale
    if weight is not None:
        entry["weight"] = weight
    return entry


def bg_message(ui) -> str:
    """Whether a background image is set, as the row says it when the page opens."""
    return BG_SET if _truthy(_dict(ui).get("overlay_bg_set")) else BG_NONE


def autocontrast(ui) -> str:
    """The auto-contrast chosen (``ui.overlay_text_autocontrast || "off"``); the list shows Off for one it lacks."""
    value = _dict(ui).get("overlay_text_autocontrast")
    return value if _truthy(value) else "off"


# ------------------------------------------------------------------ the web page's constants
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _skip(text: str, i: int) -> int:
    """Past the white space and the comments at ``text[i]``."""
    while i < len(text):
        if text[i].isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("a comment left open")
            i = end + 2
        else:
            break
    return i


def _string(text: str, i: int) -> tuple[str, int]:
    """The string literal at ``text[i]`` (in single or double quotes) and where it ends."""
    quote, out, i = text[i], [], i + 1
    while i < len(text):
        c = text[i]
        if c == quote:
            return "".join(out), i + 1
        if c == "\n":
            raise ValueError("a string across lines")
        if c != "\\":
            out.append(c)
            i += 1
            continue
        escape = text[i + 1]
        if escape == "u" and text[i + 2] == "{":
            end = text.index("}", i)
            out.append(chr(int(text[i + 3:end], 16)))
            i = end + 1
        elif escape == "u":
            out.append(chr(int(text[i + 2:i + 6], 16)))
            i += 6
        elif escape == "x":
            out.append(chr(int(text[i + 2:i + 4], 16)))
            i += 4
        elif escape == "\n":                                # a line continued
            i += 2
        else:
            out.append(_ESCAPES.get(escape, escape))
            i += 2
    raise ValueError("a string left open")


def js_literal(text: str, i: int = 0):
    """The JavaScript literal at ``text[i]`` and where it ends: an object, an array, a string, a number, ``true``,
    ``false`` or ``null``, as the web page's script writes its constants (keys bare or quoted, a comma after the last
    item allowed, comments skipped)."""
    i = _skip(text, i)
    if i >= len(text):
        raise ValueError("no literal")
    c = text[i]
    if c in "{[":
        close, out = ("}", {}) if c == "{" else ("]", [])
        i += 1
        while True:
            i = _skip(text, i)
            if i < len(text) and text[i] == close:
                return out, i + 1
            if c == "{":
                if i < len(text) and text[i] in "\"'":
                    key, i = _string(text, i)
                else:
                    match = _IDENTIFIER.match(text, i)
                    if match is None:
                        raise ValueError(f"no key at {i}")
                    key, i = match.group(0), match.end()
                i = _skip(text, i)
                if i >= len(text) or text[i] != ":":
                    raise ValueError(f"no colon at {i}")
                out[key], i = js_literal(text, i + 1)
            else:
                value, i = js_literal(text, i)
                out.append(value)
            i = _skip(text, i)
            if i < len(text) and text[i] == ",":
                i += 1
            elif i >= len(text) or text[i] != close:
                raise ValueError(f"no comma at {i}")
    if c in "\"'":
        return _string(text, i)
    match = _NUMBER.match(text, i)
    if match:
        literal = match.group(0)
        return (float(literal) if any(ch in literal for ch in ".eE") else int(literal)), match.end()
    for word, value in (("true", True), ("false", False), ("null", None)):
        if text.startswith(word, i):
            return value, i + len(word)
    raise ValueError(f"no literal at {i}")


@functools.lru_cache(maxsize=None)
def _page() -> dict:
    """The web page's constants the native page shares, read once: its presets, their descriptions and the settings a
    preset may carry. A constant that cannot be read is left out."""
    try:
        with open(SETTINGS_JS, encoding="utf-8") as file:
            text = file.read()
    except OSError:
        return {}
    out = {}
    for name in ("OVERLAY_VISUAL_KEYS", "BUNDLED_PRESETS", "BUNDLED_PRESET_DESC"):
        match = re.search(rf"\bconst {name}\s*=\s*", text)
        if match:
            try:
                out[name] = js_literal(text, match.end())[0]
            except (ValueError, IndexError):
                pass
    return out


def visual_keys() -> tuple:
    """The settings a preset carries (``OVERLAY_VISUAL_KEYS``, as settings_backup's ``_VISUAL_KEYS``)."""
    return tuple(key for key in _list(_page().get("OVERLAY_VISUAL_KEYS")) if isinstance(key, str))


def bundled() -> dict:
    """The starter presets (``BUNDLED_PRESETS``), by name in the web page's order."""
    return _dict(_page().get("BUNDLED_PRESETS"))


def described() -> dict:
    """What each starter preset looks like (``BUNDLED_PRESET_DESC``)."""
    return _dict(_page().get("BUNDLED_PRESET_DESC"))


# ------------------------------------------------------------------ the presets
def saved_presets(ui) -> list:
    """The presets saved (``Array.isArray(ui.overlay_presets) ? … : []``)."""
    return _list(_dict(ui).get("overlay_presets"))


def preset_groups(ui) -> list:
    """The list's groups (``overlayPresetOptions``): the starter presets, then the saved ones when there are any. Each
    choice's value says its kind (``b::``, ``s::``) and its name."""
    groups = [(STARTER, [("b::" + name, name) for name in bundled()])]
    mine = [("s::" + js_text(_dict(p).get("name")), js_text(_dict(p).get("name"))) for p in saved_presets(ui)]
    return groups + ([(SAVED_PRESETS, mine)] if mine else [])


def preset_said(choice: str) -> str:
    """What choosing a preset says (``#ov-preset``'s change): a starter preset's description, or that it is yours."""
    if choice[:1] == "b":
        return js_text(described().get(choice[3:]) or "")
    return YOURS


def preset_settings(choice: str, ui):
    """The settings the chosen preset applies: a starter preset's, or the saved one's (``find(…)?.settings``); None
    when there are none."""
    kind, name = choice[:1], choice[3:]
    if kind == "b":
        return bundled().get(name)
    for preset in saved_presets(ui):
        if isinstance(preset, dict) and preset.get("name") == name:
            return preset.get("settings")
    return None


def look_of(ui) -> dict:
    """The overlay's look as the app has it now (each of ``OVERLAY_VISUAL_KEYS`` it has)."""
    ui = _dict(ui)
    return {key: ui[key] for key in visual_keys() if key in ui}


def with_preset(ui, name: str, settings) -> list:
    """The saved presets with ``name`` saved as ``settings``: one of the same name, whatever its case, replaced by it,
    the new one last."""
    kept = [p for p in saved_presets(ui) if js_text(_dict(p).get("name")).lower() != name.lower()]
    return kept + [{"name": name, "settings": settings}]


def without_preset(ui, name: str) -> list:
    """The saved presets without the one named ``name``."""
    return [p for p in saved_presets(ui) if _dict(p).get("name") != name]


# ------------------------------------------------------------------ the share codes
_SURROGATE = re.compile("[\ud800-\udfff]")
#: What JavaScript's ``trim`` takes off a text's ends.
_JS_SPACE = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029"
             "\u202f\u205f\u3000\ufeff")


def js_trim(text) -> str:
    """``(text || "").trim()``."""
    return (text or "").strip(_JS_SPACE) if isinstance(text, str) else ""


def js_units(text: str) -> int:
    """A text's length as JavaScript counts it (UTF-16 code units)."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def js_slice(text: str, size: int) -> str:
    """``text.slice(0, size)`` in UTF-16 code units; a character that would be cut in two is left out."""
    out, units = [], 0
    for ch in text:
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > size:
            break
        out.append(ch)
    return "".join(out)


def js_json(value) -> str:
    """``JSON.stringify(value)``: no spaces, each object's keys in their order, a whole number without its ``.0``, and a
    lone surrogate escaped."""
    def plain(v):
        if v is None or isinstance(v, (bool, int, str)):
            return v
        if isinstance(v, float):
            if not math.isfinite(v):
                return None
            return int(v) if v.is_integer() and abs(v) < 1e21 else v
        if isinstance(v, dict):
            return {str(k): plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        return None
    text = json.dumps(plain(value), ensure_ascii=False, separators=(",", ":"))
    return _SURROGATE.sub(lambda m: "\\u%04x" % ord(m.group(0)), text)


def encode_preset(name: str, settings) -> str:
    """A preset's share code (``encodePreset``): ``A2P1:``, then its name and settings as JSON, in UTF-8, in base64."""
    return CODE_PREFIX + base64.b64encode(js_json({"name": name, "settings": settings}).encode("utf-8")).decode("ascii")


def _atob(text: str) -> bytes:
    """``atob``: base64 read as a browser reads it (white space and the padding optional); ValueError where it cannot."""
    data = re.sub(r"[\t\n\f\r ]", "", text)
    if len(data) % 4 == 0 and data.endswith("="):
        data = data[:-2] if data.endswith("==") else data[:-1]
    if len(data) % 4 == 1 or not re.fullmatch(r"[A-Za-z0-9+/]*", data):
        raise ValueError("not base64")
    return base64.b64decode(data + "=" * (-len(data) % 4))


def _js_float(literal: str):
    """A JSON number with a fraction or an exponent, as JavaScript holds it: a whole one is a whole number."""
    x = float(literal)
    return int(x) if math.isfinite(x) and x.is_integer() and abs(x) < 2 ** 53 else x


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def js_parse(raw: bytes):
    """A file's or a code's bytes read as a browser reads them (``TextDecoder``, a byte-order mark taken off), then
    ``JSON.parse``d: no NaN or Infinity, and a number with a fraction or an exponent whole when it is (since 0.2.481,
    for a settings file too). ValueError when it is not JSON."""
    text = raw.decode("utf-8", "replace")
    text = text[1:] if text.startswith("\ufeff") else text
    return json.loads(text, parse_float=_js_float, parse_constant=_no_constant)


def decode_preset(code: str) -> dict:
    """A shared code read (``decodePreset``): its name (cut to 40, or "Shared preset") and the look settings it
    carries; ValueError when it is not a preset's code."""
    raw = js_trim(code)
    data = raw[len(CODE_PREFIX):] if raw.startswith(CODE_PREFIX) else raw
    try:
        doc = js_parse(_atob(data))
    except (ValueError, RecursionError) as problem:
        raise ValueError("not a preset") from problem
    if (not isinstance(doc, dict) or not isinstance(doc.get("name"), str)
            or not isinstance(doc.get("settings"), (dict, list))):
        raise ValueError("not a preset")
    given = _dict(doc["settings"])
    settings = {key: given[key] for key in visual_keys() if key in given}
    if not settings:
        raise ValueError("no recognised look settings")
    return {"name": js_slice(doc["name"], NAME_LIMIT) or SHARED, "settings": settings}
