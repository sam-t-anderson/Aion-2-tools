"""The staged field-boss respawn reference (aion2calc/app/static/field-bosses.json)
is community-sourced, so it must stay well-formed and keep its provenance intact:
version 1, a community_unverified status, dated sources, and every boss carrying a
name/zone/level plus either a kill-based respawn interval or a scheduled note. This
guards against a hand edit dropping the "not official" framing or shipping a boss
with no staged value at all."""
import json
import pathlib

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
DATA = json.loads((STATIC / "field-bosses.json").read_text(encoding="utf-8"))

FACTIONS = {"elyos", "asmodian", "abyss"}


def test_envelope_and_provenance():
    assert DATA["version"] == 1
    assert DATA["status"] == "community_unverified"
    assert DATA["disputed"] is True
    # Dated so the Timers page can flag it stale and prompt a re-check.
    for key in ("checked_at", "review_after"):
        assert isinstance(DATA[key], str) and len(DATA[key]) == 10
    assert DATA["note"] and "confirm" in DATA["note"].lower()
    assert isinstance(DATA["sources"], list) and DATA["sources"]
    for src in DATA["sources"]:
        assert src["name"]
        assert src["url"].startswith("https://")


def test_every_boss_is_well_formed_and_staged():
    bosses = DATA["bosses"]
    assert len(bosses) >= 40
    for b in bosses:
        assert b["name"] and isinstance(b["name"], str)
        assert b["faction"] in FACTIONS
        assert b["zone"] and isinstance(b["zone"], str)
        assert isinstance(b["level"], int) and 1 <= b["level"] <= 99
        assert isinstance(b["checked_in_game"], bool)
        # Each boss must carry a staged value: a kill-based respawn, or a schedule note.
        rm = b["respawn_minutes"]
        if rm is None:
            assert b.get("schedule"), f"{b['name']} has neither respawn nor schedule"
        else:
            assert isinstance(rm, int) and 1 <= rm <= 1440


def test_abyss_bosses_use_schedules_not_kill_timers():
    # Abyss bosses appear on a fixed clock, not a kill-based respawn cycle.
    for b in DATA["bosses"]:
        if b["faction"] == "abyss":
            assert b["respawn_minutes"] is None and b.get("schedule")


def test_the_4_november_2026_patch_notes():
    """The official Global patch notes of 3 Nov (PST) / 4 Nov (CET) 2026: Gartua and High Commander Lagta respawn 11 hours
    after a kill for both factions (12 before), the three Artifact Bosses come on Thursdays and Saturdays at 21:30 with
    the Artifact Siege at 21:00 (Monday is dropped), and Argo, the Spirit King spawns at 10:30 and 22:30 every day."""
    by = {(b["name"], b["faction"]): b for b in DATA["bosses"]}
    for key in (("Eternal Gartua", "elyos"), ("High Commander Lagta", "elyos"),
                ("Immortal Gartua", "asmodian"), ("High Commander Lagta", "asmodian")):
        assert by[key]["respawn_minutes"] == 660, key
    for name in ("Executor Tamasa", "Executor Argo", "Executor Kaira"):
        assert by[(name, "abyss")]["schedule"].startswith("Global: Thu and Sat 21:30 server time")
    assert "daily at 10:30 and 22:30 server time" in by[("Argo, the Spirit King", "abyss")]["schedule"]
    schedules = json.loads((STATIC / "event-schedules.json").read_text(encoding="utf-8"))
    events = {e["id"]: e for e in schedules["events"]}
    assert events["siege"]["days"] == events["siege-bosses"]["days"] == [4, 6]          # Thursday and Saturday
    assert schedules["overrides"]["kr"]["siege"]["days"] == [3, 6]                       # Korea keeps its own days
