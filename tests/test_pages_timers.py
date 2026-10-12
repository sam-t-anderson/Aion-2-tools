"""The public Timers page (GitHub Pages) must load the shared schedule engine.

``static/timers.js`` destructures ``window.A2EventSchedule`` at load time (the
DST-aware occurrence/countdown engine shared with the overlay, defined in
``event-schedule.js``). The desktop app loads ``event-schedule.js`` before
``timers.js``; the Pages site must do the same, and the Pages build must copy the
file. A 0.2.233 refactor split the engine out but left the Pages site without it,
so the whole Timers page threw and rendered blank. This guards that wiring."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TIMERS_JS = (ROOT / "aion2calc" / "app" / "static" / "timers.js").read_text(encoding="utf-8")
ENGINE_JS = (ROOT / "aion2calc" / "app" / "static" / "event-schedule.js").read_text(encoding="utf-8")
TIMERS_HTML = (ROOT / "site" / "timers.html").read_text(encoding="utf-8")
PAGES_YML = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")


def test_timers_depends_on_the_shared_engine():
    # The real dependency: timers.js reads A2EventSchedule, event-schedule.js defines it.
    assert "window.A2EventSchedule" in TIMERS_JS
    assert "window.A2EventSchedule" in ENGINE_JS


def test_pages_timers_loads_the_engine_before_timers():
    assert "static/event-schedule.js" in TIMERS_HTML, "Pages timers.html must load event-schedule.js"
    # It must come before static/timers.js, which destructures A2EventSchedule at load.
    assert TIMERS_HTML.index("static/event-schedule.js") < TIMERS_HTML.index("static/timers.js")


def test_pages_build_copies_the_engine():
    # The deploy copies it into _site/static and rebuilds when it changes.
    assert "aion2calc/app/static/event-schedule.js" in PAGES_YML
    # Named in the cp list next to the other static modules, not only the paths trigger.
    assert PAGES_YML.count("aion2calc/app/static/event-schedule.js") >= 2
