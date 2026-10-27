"""Reading the game's Genus Insight panel and Title window from the screen (aion2calc/screenread).

Windows' text recognition is not on the test machines, so the engine's output is built here: lines of
words with their boxes, laid out as the game's windows lay them out (a 1080p screen, text 20 px tall).
The titles are taken from the title catalog itself, and nothing here is a player's name.
"""
import base64
import io
import json
import threading
import urllib.error
import urllib.request

import pytest
from PIL import Image, ImageDraw

from aion2calc.paths import read_json
from aion2calc.screenread import ocr, parse, service
from aion2calc.screenread.ocr import Line, Word

H = 20          # text height in px


def words(text: str, x: float, y: float, h: float = H) -> list[Word]:
    out = []
    for part in text.split():
        w = len(part) * h * 0.55
        out.append(Word(part, x, y, w, h))
        x += w + 0.4 * h
    return out


def line(text: str, x: float, y: float, h: float = H) -> Line:
    return Line(tuple(words(text, x, y, h)))


#: the Fera Insight panel at level 8, as read: each line's name at the left of the panel and its value at the right
FERA = [("Fera Defense", "49"), ("Boss Defense", "108"), ("Power Shard Damage Bonus", "7"), ("MP", "18"),
        ("MP", "9"), ("MP", "6"), ("PvE Defense", "89"), ("PvE Defense", "79")]


def genus_panel(rows=FERA, heading="Fera Insight", level="Lv. 8", left=980, value_x=1380, extra=()):
    lines = [
        # another window to the left of the panel (the game's screenshot settings, in Spanish): not the panel's
        line("Captura de pantalla", 120, 180), line("Calidad de imagen 100", 120, 300),
        line("Formato 1920 1080", 120, 340), line("Guardar 25", 120, 420),
        line(heading, left, 180),
    ]
    if level:
        lines.append(line(level, left + 260, 180))
    lines.append(line("Analysis Effect", left, 240))
    y = 290
    for name, value in rows:
        lines += [line(name, left, y)] + ([line(value, value_x, y)] if value else [])
        y += 40
    lines.append(line("Unlock Insight Lv. 9", left, y + 10))
    lines += list(extra)
    return lines


def test_the_fera_panel_is_read_line_by_line_into_its_slots():
    found = parse.parse_genus(genus_panel())
    assert found["genus"] == "Fera" and found["level"] == 8 and found["notes"] == []
    assert [(line["slot"], line["stat"], line["value"]) for line in found["lines"]] == [
        (i + 1, name, value) for i, (name, value) in enumerate(FERA)]
    assert not any(line["check"] for line in found["lines"])
    assert parse.parse(genus_panel())["kind"] == "genus"


def test_misread_names_and_values_are_matched_or_marked_for_the_player_to_check():
    rows = [("Fera Defence", "49"),            # a letter misread: still Fera Defense
            ("Boss Defense", "250"),           # more than slot 2 ever rolls: kept, and marked
            ("Xyzzy Plugh", "7"),              # no line the slot rolls: kept as read, and marked
            ("o MP", "18")]                    # the slot's lock icon read as a letter before the name
    found = parse.parse_genus(genus_panel(rows=rows, level="Lv. 4"))
    lines = {line["slot"]: line for line in found["lines"]}
    assert lines[1]["stat"] == "Fera Defense" and lines[1]["check"] == ""
    assert lines[2]["stat"] == "Boss Defense" and "250 is outside what slot 2 rolls" in lines[2]["check"]
    assert lines[3]["stat"] == "Xyzzy Plugh" and lines[3]["check"] == "the stat name was not recognised"
    assert lines[4]["stat"] == "MP" and lines[4]["value"] == "18" and lines[4]["check"] == ""


def test_a_value_misread_with_letters_is_guessed_and_one_not_read_keeps_its_slot():
    rows = [("Fera Defense", "49"), ("Boss Defense", "1O8"), ("Power Shard Damage Bonus", ""), ("MP", "18")]
    lines = {line["slot"]: line for line in parse.parse_genus(genus_panel(rows=rows, level="Lv. 4"))["lines"]}
    assert lines[2]["stat"] == "Boss Defense" and lines[2]["value"] == "108"
    assert lines[2]["check"] == "check the value (read as 1O8)"
    assert lines[3]["stat"] == "Power Shard Damage Bonus" and lines[3]["value"] == ""
    assert lines[3]["check"] == "the value was not read"
    assert lines[4]["stat"] == "MP" and lines[4]["value"] == "18"                         # not moved up a slot


def test_a_percent_line_carries_its_percent_sign_however_it_was_read():
    rows = [("Fera Defense", "49"), ("Boss Defense", "108"), ("Power Shard Damage Bonus", "7"),
            ("Fera Damage Boost", "3,2")]       # a comma for the decimal point, and the % sign lost
    found = parse.parse_genus(genus_panel(rows=rows, level="Lv. 4"))
    assert found["lines"][3]["stat"] == "Fera Damage Boost" and found["lines"][3]["value"] == "3.2%"


def test_the_heading_is_found_when_the_engine_reads_insight_with_a_small_l_and_the_level_under_it():
    lines = genus_panel(heading="Fera lnsight", level=None) + [line("Lv.8", 980, 210)]
    found = parse.parse_genus(lines)
    assert found["genus"] == "Fera" and found["level"] == 8 and len(found["lines"]) == 8


def test_without_the_level_every_slot_is_read_and_the_player_is_asked_for_it():
    found = parse.parse_genus(genus_panel(level=None))
    assert found["level"] is None and len(found["lines"]) == 8
    assert any("level was not read" in note for note in found["notes"])


def test_a_second_column_on_the_same_row_does_not_supply_the_value():
    totals = [line("MP +33", 1500, 290 + 40 * i) for i in range(8)]       # e.g. a column of totals to the right
    found = parse.parse_genus(genus_panel(extra=totals))
    assert [line["value"] for line in found["lines"]] == [value for _, value in FERA]


def test_a_missing_line_is_said_and_another_window_is_not_a_genus_panel():
    found = parse.parse_genus(genus_panel(rows=FERA[:6]))
    assert len(found["lines"]) == 6 and any("6 of the 8 open slots" in note for note in found["notes"])
    assert parse.parse_genus([line("Inventory", 100, 100), line("Gold 1200", 100, 140)]) is None
    nothing = parse.parse([line("Inventory", 100, 100)])
    assert nothing["kind"] is None and nothing["notes"]


# ------------------------------------------------------------------------------------------- the Title window
CATALOG = read_json("global", "titles.json")
ELYOS = [t["name"] for t in CATALOG if t["faction"] == "Elyos"]
BOTH = [t["name"] for t in CATALOG if t["faction"] == "Both factions"]
ASMODIAN = [t["name"] for t in CATALOG if t["faction"] == "Asmodian"]


def title_window(names, equipped=(), collection="Total Collection Status 123/509", toggle_y=900):
    lines = [line("Title", 120, 60),
             line("All Quest Progress Challenge Exploration Dungeon Resource", 120, 110)]
    for i, name in enumerate(names):                      # cards three to a row, each name over its bonus
        x, y = 140 + (i % 3) * 420, 180 + (i // 3) * 110
        lines += [line(name, x, y), line("Attack Bonus +1", x, y + 30, h=16)]
    lines.append(line("Equip Status", 1460, 110))
    lines += [line(name, 1480, 180 + 60 * i) for i, name in enumerate(equipped)]
    if collection:
        lines.append(line(collection, 140, 860))
    lines.append(line("Show unacquired titles only", 200, toggle_y))
    return lines


def test_a_title_window_page_lists_its_titles_by_catalog_name_but_not_the_equipped_ones():
    names = ELYOS[:5] + BOTH[:4]
    found = parse.parse_titles(title_window(names, equipped=BOTH[10:13]))
    assert found["titles"] == names
    assert found["collection"] == {"owned": 123, "total": 509} and found["unacquired_only"] is None
    assert parse.parse(title_window(names))["kind"] == "titles"


def test_a_misread_title_still_matches_and_a_long_one_wrapped_on_its_card_is_joined():
    name = next(n for n in BOTH if len(n.split()) >= 3)
    first, rest = name.split(" ", 1)
    misread = name[:-1] + ("x" if name[-1] != "x" else "y")
    lines = title_window([misread]) + [line(first, 980, 400), line(rest, 980, 425)]
    found = parse.parse_titles(lines)
    assert found["titles"][0] == name
    assert name in found["titles"]


def test_the_unacquired_only_box_is_read_from_the_picture():
    label = line("Show unacquired titles only", 200, 900)

    def screen(ticked: bool):
        picture = Image.new("RGB", (1920, 1080), (14, 18, 30))
        size, right = 1.07 * H, label.x - 0.65 * H
        box = (right - size, label.cy - size / 2, right, label.cy + size / 2)
        draw = ImageDraw.Draw(picture)
        draw.rectangle(box, outline=(150, 150, 150), fill=(230, 200, 120) if ticked else (20, 22, 30))
        return picture

    assert parse.box_ticked(screen(True), label) is True
    assert parse.box_ticked(screen(False), label) is False
    assert parse.box_ticked(None, label) is None
    page = parse.parse_titles(title_window(ELYOS[:3]), screen(True))
    assert page["unacquired_only"] is True


def test_the_titles_owned_are_the_factions_titles_no_unacquired_page_listed():
    unacquired = ELYOS[:4] + BOTH[:3]
    pages = [{"id": 1, "at": 0, "titles": unacquired[:4], "unacquired_only": True, "collection": None},
             {"id": 2, "at": 1, "titles": unacquired[4:], "unacquired_only": True,
              "collection": {"owned": len(ELYOS) + len(BOTH) - len(unacquired), "total": len(ELYOS) + len(BOTH)}}]
    summary = service.title_summary(pages, faction="elyos")
    assert summary["basis"] == "catalog" and summary["faction"] == "elyos"
    assert set(summary["owned"]) == set(ELYOS + BOTH) - set(unacquired)
    assert not set(summary["owned"]) & set(ASMODIAN)
    assert any("matches the game's count" in note for note in summary["notes"])
    # the faction from the titles the pages showed, when the character's is not known
    assert service.title_summary(pages)["faction"] == "elyos"
    # one unacquired page short of the game's count: said
    short = service.title_summary(pages[1:], faction="elyos")
    assert any("this list has" in note for note in short["notes"])


def test_without_a_faction_the_titles_owned_are_those_seen_unticked_and_never_ticked():
    pages = [{"id": 1, "at": 0, "titles": BOTH[:6], "unacquired_only": False, "collection": None},
             {"id": 2, "at": 1, "titles": BOTH[:2], "unacquired_only": True, "collection": None},
             {"id": 3, "at": 2, "titles": BOTH[8:9], "unacquired_only": None, "collection": None}]
    summary = service.title_summary(pages)
    assert summary["faction"] is None and summary["basis"] == "seen" and summary["owned"] == BOTH[2:6]
    assert any("did not show whether" in note for note in summary["notes"])
    assert service.title_summary([])["notes"] and service.title_summary([])["owned"] == []


# --------------------------------------------------------------------------------------------- a whole read
@pytest.fixture()
def engine(monkeypatch):
    """Windows' engine replaced: it 'reads' the lines set on it, and the reads start from nothing."""
    monkeypatch.setattr(service, "_READS", service.deque(maxlen=service.KEEP_READS))
    monkeypatch.setattr(service, "_PAGES", [])
    monkeypatch.setattr(service, "_AVAILABLE", (True, "en-US"))
    seen = {"lines": [], "calls": 0}

    def recognize(picture):
        seen["calls"] += 1
        factor = picture.width / 1920
        return ocr.scaled(seen["lines"], factor)
    monkeypatch.setattr(ocr, "recognize", recognize)
    return seen


def test_a_read_keeps_its_record_for_the_pages_and_a_title_page_for_the_titles(engine):
    picture = Image.new("RGB", (1920, 1080))
    engine["lines"] = genus_panel()
    record = service.read(picture, source="hotkey")
    assert record["kind"] == "genus" and record["level"] == 8 and record["size"] == [1920, 1080]
    assert engine["calls"] == 1                         # every slot read in range: the second copy is not needed
    engine["lines"] = title_window(ELYOS[:3])
    page = service.read(picture)
    assert page["kind"] == "titles" and page["titles"] == ELYOS[:3] and engine["calls"] == 3
    state = service.status(0)
    assert [r["id"] for r in state["reads"]] == [record["id"], page["id"]] and state["latest"] == page["id"]
    assert service.status(record["id"])["reads"][0]["id"] == page["id"]
    assert service.title_summary()["pages"][0]["titles"] == ELYOS[:3]


def test_a_read_that_cannot_run_or_finds_nothing_says_why(engine, monkeypatch):
    picture = Image.new("RGB", (800, 600))
    engine["lines"] = [line("Inventory", 100, 100)]
    nothing = service.read(picture)
    assert nothing["kind"] is None and nothing["notes"] and nothing["seen"] == ["Inventory"]

    def unavailable(_picture):
        raise ocr.Unavailable("no engine here")
    monkeypatch.setattr(ocr, "recognize", unavailable)
    failed = service.read(picture)
    assert failed["kind"] is None and failed["error"] == "no engine here"


def test_while_a_read_runs_the_pages_are_answered_at_once(monkeypatch):
    monkeypatch.setattr(service, "_AVAILABLE", None)
    monkeypatch.setattr(ocr, "available", lambda: pytest.fail("asked the engine's thread while it was busy"))
    with service._BUSY:
        assert service.status(0)["available"] is True
    assert service._AVAILABLE is None                   # asked properly once the read is over


def test_a_pasted_screenshot_is_checked_before_it_is_read():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), (1, 2, 3)).save(buffer, "PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    assert service.image_from_data_url(url).size == (64, 32)
    for bad in (None, "not a url", "data:image/png,raw", "data:image/png;base64,@@@",
                "data:image/png;base64," + base64.b64encode(b"GIF89a not a png").decode()):
        with pytest.raises(ValueError):
            service.image_from_data_url(bad)


def test_page_mode_corrections_and_control_actions(engine):
    picture = Image.new("RGB", (1920, 1080))
    engine["lines"] = title_window(ELYOS[:3])
    page = service.read(picture)
    summary = service.control({"action": "page", "page": page["id"], "unacquired_only": True}, faction="elyos")
    assert summary["unacquired"] == ELYOS[:3] and summary["basis"] == "catalog"
    with pytest.raises(ValueError):
        service.control({"action": "page", "page": 999, "unacquired_only": True})
    with pytest.raises(ValueError):
        service.control({"action": "read", "delay": 60})
    with pytest.raises(ValueError):
        service.control({"action": "nonsense"})
    assert service.control({"action": "forget-page", "page": page["id"]})["pages"] == []
    service.read(picture)
    assert service.control({"action": "clear-titles"})["pages"] == []


def test_the_screen_read_api(engine, tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer

    from aion2calc.app.server import Handler
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data, {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    try:
        assert call("/api/screen-read") == {"available": True, "message": "en-US", "latest": 0, "reads": []}
        buffer = io.BytesIO()
        Image.new("RGB", (1920, 1080)).save(buffer, "PNG")
        engine["lines"] = genus_panel()
        record = call("/api/screen-read", {"action": "image",
                                           "image": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()})
        assert record["kind"] == "genus" and record["source"] == "screenshot" and len(record["lines"]) == 8
        assert call("/api/screen-read?since=0")["reads"][0]["id"] == record["id"]
        assert call("/api/screen-read/titles?character=nobody")["pages"] == []
        with pytest.raises(urllib.error.HTTPError) as err:
            call("/api/screen-read", {"action": "page", "page": 12345, "unacquired_only": True})
        assert err.value.code == 500 and "no longer kept" in json.loads(err.value.read())["error"]
    finally:
        srv.shutdown()


def test_reading_runs_only_on_windows_and_says_so_elsewhere(monkeypatch):
    monkeypatch.setattr(ocr.sys, "platform", "linux")
    assert ocr.available()[0] is False and "Windows only" in ocr.available()[1]
    with pytest.raises(ocr.Unavailable):
        ocr.recognize(Image.new("RGB", (10, 10)))
    from aion2calc.screenread import capture
    monkeypatch.setattr(capture.sys, "platform", "linux")
    with pytest.raises(ocr.Unavailable):
        capture.game_screen()
