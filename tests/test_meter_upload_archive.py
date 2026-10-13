"""Upload must send the whole recording, not only the live storage part.

A long session rolls across storage boundaries into parts saved to disk; the Upload
button used to send only the current in-memory part, so earlier encounters were
missing from the uploaded log. (Seen in the wild as a public log titled "… Part 2"
holding a single 17-second fight, while the first ~31k records sat on disk as Part 1.)

``live_archive_sources`` gathers the earlier *closed* parts and hands them, with the
live current part, to ``reconstruction.combine`` so one Upload holds every encounter;
a single-part session is left exactly as it was, and a missing earlier part falls back
to uploading the current part alone."""
import uuid

import pytest

from aion2calc.combat import sessions
from aion2calc.combat.archive import retained_range
from aion2calc.combat.reconstruction import combine
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

ARCHIVE = uuid.uuid4().hex


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def _hit(actor, t, dmg=500):
    # A job-bearing skill code so observed players resolve without a roster.
    return DamageEvent(actor_id=actor, target_id=9001, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _entered_engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = 4062
    engine.names = {4062: "Me", 4063: "Mate4063"}
    engine.known_players = {4062, 4063}
    engine.roster = {name: {} for name in engine.names.values()}
    return engine


def _finalise(session, part, token, previous, closed):
    doc = session.to_a2log("party", f"Live combat session {ARCHIVE[:8]} · Part {part}")
    doc["meta"]["archive"] = {"id": ARCHIVE, "part": part, "closed": closed,
                              "continuity": retained_range(session, token, previous)}
    return doc, doc["meta"]["archive"]["continuity"]


def _two_part_session():
    """A continuing instance run that rolled over once: Part 1 closed (two pulls),
    Part 2 the live current part (one pull), chained by retained-record continuity."""
    engine = _entered_engine()
    part1 = CombatSession()
    part1.pvp = False
    part1.observe(engine, [], timestamp_ms=101_000)                                   # witnessed entry
    part1.observe(engine, [_hit(4062, 105_000), _hit(4063, 106_000)], timestamp_ms=106_000)
    part1.observe(engine, [_hit(4062, 400_000), _hit(4063, 401_000)], timestamp_ms=401_000)  # +294s → 2nd pull
    doc1, cont1 = _finalise(part1, 1, uuid.uuid4().hex, None, closed=True)

    engine.last_zone_reset_ms = None                                                   # same fight, no new load
    part2 = part1.continuation()
    part2.observe(engine, [_hit(4062, 700_000), _hit(4063, 701_000)], timestamp_ms=701_000)
    doc2, _cont2 = _finalise(part2, 2, uuid.uuid4().hex, cont1, closed=False)
    return doc1, doc2


def test_upload_stitches_earlier_parts_into_one_combined_recording(isolated_home):
    doc1, doc2 = _two_part_session()
    sessions.save(doc1, "session-20261013-000001-aaaaaa.a2log.json")   # Part 1 finalised on disk

    sources = sessions.live_archive_sources(doc2)                      # Part 2 is the live current part
    assert sources is not None
    # Earlier closed part first, then the in-memory current part.
    assert [src.get("file") or "live" for src, _doc in sources] == [
        "session-20261013-000001-aaaaaa.a2log.json", "live"]

    combined = combine(sources)
    assert combined["meta"]["capture_quality"]["reconstructed"] is True
    assert len(combined["meta"]["reconstruction"]["sources"]) == 2
    # One Upload now carries every encounter from both parts, none dropped.
    expected = len(doc1["segments"]) + len(doc2["segments"])
    assert expected >= 3
    assert len(combined["segments"]) == expected


def test_single_part_session_uploads_unchanged(isolated_home):
    engine = _entered_engine()
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [_hit(4062, 105_000), _hit(4063, 106_000)], timestamp_ms=106_000)
    doc, _ = _finalise(s, 1, uuid.uuid4().hex, None, closed=False)
    # Part 1 with nothing earlier → upload the current part as-is (no combine).
    assert sessions.live_archive_sources(doc) is None


def test_missing_earlier_part_falls_back_to_current_part_only(isolated_home):
    _doc1, doc2 = _two_part_session()
    # Part 1 was pruned off disk (never saved here): an unresolved chain must not drop
    # the upload — the caller uploads the current part alone rather than nothing.
    assert sessions.live_archive_sources(doc2) is None
