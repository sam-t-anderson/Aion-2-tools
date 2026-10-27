"""What a picture of the game shows: a genus's Insight lines, or a page of the Title window.

The engine returns lines of words with their boxes (``ocr.Line``). The Genus Insight panel is found by
its heading ("Fera Insight", then "Lv. 8") and read row by row under "Analysis Effect": each row's
name is matched against the lines its slot can roll (``genus_properties.json``) and its value checked
against their ranges, so a misread name or digit is flagged for the player to check rather than saved
as read. A page of the Title window is found by its "Total Collection Status" line or its tabs; the
title names on it are matched against the title catalog, outside the Equip Status panel beside it.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache

from ..paths import read_json
from .ocr import Line, Word

GENERA = ("Cogni", "Fera", "Natura", "Varian", "Special")
#: "Fera Insight" (the engine reads a capital I as l, 1 or | now and then)
_INSIGHT = re.compile(r"\b(cogni|fera|natura|varian|special)\s*[il1|]nsight\b", re.I)
_LEVEL = re.compile(r"\bl[vy]\s*[.,:]?\s*(\d{1,2})\b", re.I)
_VALUE = re.compile(r"^\+?(\d{1,4}(?:[.,]\d{1,2})?)(%?)$")
_COLLECTION = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})")
#: rows of the Insight panel that are not analysis lines
_PANEL_LABELS = ("analysis effect", "insight info", "all applied effects", "auto analysis", "analyze")
#: the Title window's tabs, which name the window when the collection line is not on screen
_TITLE_TABS = ("quest", "progress", "challenge", "exploration", "dungeon", "resource")
#: a genus line's stat name, matched to a line its slot can roll
NAME_MATCH = 0.75
#: a title on the page, matched to the catalog: close enough that a stat line never passes
TITLE_MATCH = 0.86


def norm(text: str) -> str:
    """Lower case letters, digits and apostrophes, single spaces: what a name is compared by."""
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'").lower()
    return " ".join(re.sub(r"[^0-9a-z' ]+", " ", text).split())


def rows(lines: list[Line]) -> list[list[Word]]:
    """The words on each visual row, left to right, rows top to bottom. The engine can return a name
    and its value at the far end of the row as two lines; they share a row here."""
    merged: list[dict] = []
    for found in sorted(lines, key=lambda line: line.cy):
        last = merged[-1] if merged else None
        if last is not None and abs(last["cy"] - found.cy) <= 0.6 * max(last["h"], found.h):
            last["words"].extend(found.words)
        else:
            merged.append({"cy": found.cy, "h": found.h, "words": list(found.words)})
    return [sorted(row["words"], key=lambda word: word.x) for row in merged]


def _row_text(words: list[Word]) -> str:
    return " ".join(word.text for word in words)


def segments(words: list[Word]) -> list[list[Word]]:
    """A row split where the gap between two words is wider than the text is tall: the names of
    neighbouring cards, or a name and the icon at the card's edge."""
    pieces: list[list[Word]] = []
    for word in sorted(words, key=lambda w: w.x):
        if pieces:
            last = pieces[-1][-1]
            if word.x - (last.x + last.w) <= 1.5 * max(last.h, word.h, 1):
                pieces[-1].append(word)
                continue
        pieces.append([word])
    return pieces


@lru_cache(maxsize=1)
def _properties() -> dict:
    return read_json("global", "genus_properties.json")["genera"]


def _slot_lines(genus: str, slot: int) -> dict:
    return _properties().get(genus, {}).get("slots", {}).get(str(slot), {})


def _value(text: str) -> tuple[float, bool] | None:
    found = _VALUE.match(text.replace(" ", ""))
    if not found:
        return None
    return float(found.group(1).replace(",", ".")), bool(found.group(2))


#: letters the engine reads in place of digits ("1O8" for 108)
_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5",
                                   "B": "8", "Z": "2"})


def _value_guess(text: str) -> tuple[float, bool] | None:
    """A number read with a letter or two in place of digits, when the rest of it is digits."""
    return _value(text.translate(_DIGIT_LOOKALIKES)) if re.search(r"\d", text) else None


def _match_stat(name: str, value: float | None, choices: dict) -> tuple[str | None, float]:
    """The slot's line the name reads as, and how close: of names about as close, the one whose range
    holds the value."""
    target = norm(name)
    scored = sorted(((difflib.SequenceMatcher(None, target, norm(stat)).ratio(), stat) for stat in choices),
                    reverse=True)
    if not scored:
        return None, 0.0
    best_score = scored[0][0]
    near = [stat for score, stat in scored if best_score - score <= 0.05]
    if value is not None and len(near) > 1:
        fits = [stat for stat in near if _in_range(choices[stat], value)]
        if len(fits) == 1:
            return fits[0], dict((stat, score) for score, stat in scored)[fits[0]]
    return scored[0][1], best_score


def _in_range(grades: dict, value: float) -> bool:
    return any(low - 1e-9 <= value <= high + 1e-9 for low, high, *_ in grades.values())


def _percent(grades: dict) -> bool:
    return any(len(spec) > 2 and spec[2] for spec in grades.values())


def _format(value: float) -> str:
    return f"{value:g}"


def parse_genus(lines: list[Line]) -> dict | None:
    """The Genus Insight panel on the screen: ``{"kind": "genus", "genus", "level", "lines": [...]}``, each
    line ``{"slot", "stat", "value", "read", "check"}`` (``check`` says what to look at, or is empty), or
    None when no Insight heading is on the screen."""
    heading = next((line for line in lines if _INSIGHT.search(line.text)), None)
    if heading is None:
        return None
    genus = next(g for g in GENERA if g.lower() == _INSIGHT.search(heading.text).group(1).lower())
    # The panel: the heading's column and everything under it. Text further left (another window, the
    # pet list) is not part of it.
    left = heading.x - 2 * heading.h
    panel = [line for line in lines if line.right > left and line.x >= left and line.bottom > heading.y]
    all_rows = rows(panel)
    head_row = next((i for i, row in enumerate(all_rows) if any(word in heading.words for word in row)), 0)
    # the level beside the heading, or on a short row of its own under it ("Lv. 8")
    level_match = _LEVEL.search(_row_text(all_rows[head_row]))
    for i in range(head_row + 1, min(head_row + 3, len(all_rows))):
        if level_match or len(all_rows[i]) > 3:
            break
        level_match = _LEVEL.search(_row_text(all_rows[i]))
        head_row = i if level_match else head_row
    level = int(level_match.group(1)) if level_match and 0 < int(level_match.group(1)) <= 10 else None
    notes = [] if level is not None else ["The Insight level was not read: enter it."]
    slots = min(level, 9) if level is not None else 9
    read_lines, slot = [], 0
    for row in all_rows[head_row + 1:]:
        text = norm(_row_text(row))
        if not text or any(label == text or text.startswith(label) for label in _PANEL_LABELS):
            continue
        if text.startswith("unlock"):           # "Unlock Insight Lv. 9": the locked slots start here
            break
        # the line's value: the first number after its name (a number before the name is not it, and what
        # stands further along the row, another column, is not either)
        named = re.compile(r"[a-z]", re.I)
        reader = _value
        index = next((i for i, word in enumerate(row) if _value(word.text) is not None
                      and any(named.search(w.text) for w in row[:i])), None)
        if index is None:                       # "1O8": a digit read as a letter
            reader = _value_guess
            index = next((i for i, word in enumerate(row) if re.search(r"\d", word.text)
                          and _value_guess(word.text) is not None
                          and any(named.search(w.text) and not re.search(r"\d", w.text) for w in row[:i])), None)
        if index is None:
            # a line whose value was not read keeps its slot when its name is one the slot rolls, so the
            # lines under it are not moved up a slot
            name = " ".join(word.text for word in row if named.search(word.text) and not re.search(r"\d", word.text))
            stat, score = _match_stat(name, None, _slot_lines(genus, slot + 1))
            if stat is None or score < NAME_MATCH or slot + 1 > slots:
                continue
            slot += 1
            read_lines.append({"slot": slot, "stat": stat, "value": "", "read": _row_text(row),
                               "check": "the value was not read"})
            continue
        value, percent_read = reader(row[index].text)
        name_words = [word for word in row[:index] if named.search(word.text)]
        slot += 1
        if slot > slots:
            break
        name = " ".join(word.text for word in name_words)
        choices = _slot_lines(genus, slot)
        stat, score = _match_stat(name, value, choices)
        # a leading speck the engine read in place of the lock icon ("a Fera Defense") reads better without
        if len(name_words) > 1 and len(name_words[0].text) <= 2:
            stat2, score2 = _match_stat(" ".join(word.text for word in name_words[1:]), value, choices)
            if score2 > score:
                stat, score = stat2, score2
        checks = [f"check the value (read as {row[index].text})"] if reader is _value_guess else []
        if stat is None or score < NAME_MATCH:
            checks.append("the stat name was not recognised")
            stat = name
        elif not _in_range(choices[stat], value):
            checks.append(f"{_format(value)} is outside what slot {slot} rolls for {stat}")
        elif score < 0.9:
            checks.append("check the stat name")
        percent = _percent(choices[stat]) if stat in choices else percent_read
        read_lines.append({"slot": slot, "stat": stat, "value": _format(value) + ("%" if percent else ""),
                           "read": _row_text(row), "check": "; ".join(checks)})
    if level is not None and len(read_lines) < slots:
        notes.append(f"{len(read_lines)} of the {slots} open slots were read: enter the rest.")
    return {"kind": "genus", "genus": genus, "level": level, "lines": read_lines, "notes": notes}


@lru_cache(maxsize=1)
def _title_names() -> dict[str, str]:
    return {norm(title["name"]): title["name"] for title in read_json("global", "titles.json")}


def _is_title_window(lines: list[Line]) -> bool:
    text = norm(" ".join(line.text for line in lines))
    return "collection status" in text or sum(tab in text.split() for tab in _TITLE_TABS) >= 4


def box_ticked(image, label: Line) -> bool | None:
    """Whether the square box just left of ``label`` (the game's "Show unacquired titles only") is
    ticked: its inside is dark when empty. None without the picture."""
    if image is None:
        return None
    size = 1.07 * label.h
    right = label.x - 0.65 * label.h
    left, top = right - size, label.cy - size / 2
    inset = 0.3 * size
    box = (int(left + inset), int(top + inset), int(right - inset), int(top + size - inset))
    if box[2] <= box[0] or box[3] <= box[1] or box[0] < 0 or box[1] < 0:
        return None
    from PIL import ImageStat
    return ImageStat.Stat(image.convert("L").crop(box)).mean[0] > 110


def parse_titles(lines: list[Line], image=None) -> dict | None:
    """A page of the Title window: ``{"kind": "titles", "titles": [...], "unacquired_only", "collection"}``,
    the titles on the page by their catalog names, whether "Show unacquired titles only" is ticked (None
    when it cannot be seen) and the window's ``{"owned", "total"}``; or None for another window."""
    if not _is_title_window(lines):
        return None
    equip = next((line for line in lines if norm(line.text).startswith("equip status")), None)
    toggle = next((line for line in lines if "unacquired titles only" in norm(line.text)), None)
    page = rows(lines)
    # the tab bar: the row naming most of the tabs (a single word of one, as in a title's name, is not it)
    tab_bar = next((row for row in page if sum(tab in norm(_row_text(row)).split() for tab in _TITLE_TABS) >= 3), None)
    right = equip.x - equip.h if equip else float("inf")
    top = max((word.y + word.h for word in tab_bar), default=float("-inf")) if tab_bar else float("-inf")
    bottom = toggle.y if toggle else float("inf")
    names = _title_names()
    found, collection, pieces = [], None, []
    for row in page:
        text = norm(_row_text(row))
        if "collection status" in text:
            count = _COLLECTION.search(_row_text(row))
            if count and int(count.group(1)) <= int(count.group(2)):
                collection = {"owned": int(count.group(1)), "total": int(count.group(2))}
        pieces += [piece for piece in segments(row) if piece[0].x < right and top < piece[0].y < bottom]

    def title(words: list[Word]) -> str | None:
        target = norm(_row_text(words))
        match = difflib.get_close_matches(target, list(names), n=1, cutoff=TITLE_MATCH) if len(target) >= 4 else []
        return names[match[0]] if match else None

    used = set()
    for i, piece in enumerate(pieces):
        if i in used:
            continue
        name = title(piece)
        if name is None:
            # a long name wrapped onto a second line on its card: the piece just under this one, where it starts
            h = max(word.h for word in piece)
            below = next((j for j, other in enumerate(pieces) if j > i and j not in used
                          and 0 < other[0].y - piece[0].y <= 1.8 * h and abs(other[0].x - piece[0].x) <= h), None)
            if below is not None:
                name = title(piece + pieces[below])
                if name is not None:
                    used.add(below)
        if name is not None and name not in found:
            found.append(name)
    return {"kind": "titles", "titles": found, "unacquired_only": box_ticked(image, toggle) if toggle else None,
            "collection": collection}


def parse(lines: list[Line], image=None) -> dict:
    """What the screen shows: a Genus Insight panel, a Title window page, or ``{"kind": None}`` with a
    note on what to open."""
    return (parse_genus(lines) or parse_titles(lines, image)
            or {"kind": None, "notes": ["No Genus Insight panel or Title window was found on the screen. Open "
                                        "Pets → Genus Insight or the Title window in the game and read again."]})
