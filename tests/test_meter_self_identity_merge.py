"""A player must be one row on the live meter, even after their combat actor id changes.

A death/revive or an instance mechanic reassigns a player's combat actor id mid-fight.
The live view keys a row by actor id, so without care one player (e.g. Spirited) shows
as two rows — damage before the swap on one, after it on another — and the overlay has
to warn that matching names have separate actor ids.

Two layers fix this. For YOU it is authoritative: the engine records the local-player id
on every record (re-acquired after tele/port/revive), so every id it confirmed as yours
folds into one row. For a PARTY MEMBER it is a conservative behavioural match: same name,
a compatible inferred class, and activity that never overlaps (a hand-off, not two people
fighting at once) — flagged as inferred. A different player who merely shares a name and
is active at the same time is never merged."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=9001, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _party_engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None          # same instance throughout: no zone load, one run
    return engine


def test_local_player_reregistration_is_one_row_not_two():
    s = CombatSession()
    s.pvp = False
    engine = _party_engine()

    # You are #4503 "Spirited"; a party mate deals damage too.
    engine.local_player_id = 4503
    engine.names = {4503: "Spirited", 4063: "MateA"}
    engine.known_players = {4503, 4063}
    engine.roster = {"Spirited": {}, "MateA": {}}
    s.observe(engine, [_hit(4503, 10_000, 500), _hit(4063, 10_100, 300)], timestamp_ms=10_100)

    # Same fight, no zone load: you die/revive and re-register as #10210, still "Spirited".
    engine.local_player_id = 10210
    engine.names = {4503: "Spirited", 10210: "Spirited", 4063: "MateA"}
    engine.known_players = {10210, 4063}
    s.observe(engine, [_hit(10210, 12_000, 700), _hit(4063, 12_100, 300)], timestamp_ms=12_100)

    snap = s.snapshot(scope="party", segment_id=None)
    names = [p["name"] for p in snap["players"]]
    assert names.count("Spirited") == 1, names            # merged, not duplicated
    you = next(p for p in snap["players"] if p["name"] == "Spirited")
    assert you["damage"] == 1200                           # 500 (as #4503) + 700 (as #10210)
    assert not you.get("inferred_identity")                # your own merge is authoritative, not inferred
    mate = next(p for p in snap["players"] if p["name"] == "MateA")
    assert mate["damage"] == 600                           # the party mate stays its own row
    assert {p["name"] for p in snap["players"]} == {"Spirited", "MateA"}


def test_party_member_reregistration_is_correlated_and_flagged():
    """A party member who dies and re-registers (a hand-off: no overlap, same name) is
    correlated into one row by behaviour, and the row is flagged inferred."""
    s = CombatSession()
    s.pvp = False
    engine = _party_engine()
    engine.local_player_id = 9000
    engine.names = {9000: "Me", 4063: "MateA"}
    engine.known_players = {9000, 4063}
    engine.roster = {"Me": {}, "MateA": {}}
    s.observe(engine, [_hit(9000, 10_000, 100), _hit(4063, 10_050, 400), _hit(4063, 11_000, 400)],
              timestamp_ms=11_000)
    # MateA dies and re-registers as #5555 later in the same fight (no activity overlap).
    engine.names = {9000: "Me", 4063: "MateA", 5555: "MateA"}
    engine.known_players = {9000, 5555}
    s.observe(engine, [_hit(9000, 20_000, 100), _hit(5555, 20_050, 500), _hit(5555, 21_000, 500)],
              timestamp_ms=21_000)

    snap = s.snapshot(scope="party", segment_id=None)
    names = [p["name"] for p in snap["players"]]
    assert names.count("MateA") == 1, names                # the two actor ids are one row
    mate = next(p for p in snap["players"] if p["name"] == "MateA")
    assert mate["damage"] == 1800                          # 400+400 (as #4063) + 500+500 (as #5555)
    assert mate.get("inferred_identity") is True           # behavioural correlation is marked inferred


def test_two_concurrent_players_sharing_a_name_stay_separate():
    """Correlation needs a hand-off. Two different players who share a name but trade
    blows at the same time (overlapping activity) are never merged — the overlap is the
    tell that they are two people, not one re-registered character."""
    s = CombatSession()
    s.pvp = False
    engine = _party_engine()
    engine.local_player_id = 4503
    engine.names = {4503: "Spirited", 7777: "Spirited", 4063: "MateA"}
    engine.known_players = {4503, 7777, 4063}
    engine.roster = {"Spirited": {}, "MateA": {}}
    # #4503 (you) and #7777 (a different Spirited) interleave hits across the same window.
    s.observe(engine, [_hit(4503, 10_000, 500), _hit(7777, 11_000, 900),
                       _hit(4503, 12_000, 500), _hit(7777, 13_000, 900),
                       _hit(4503, 14_000, 500)], timestamp_ms=14_000)

    snap = s.snapshot(scope="all", segment_id=None)
    you = [p for p in snap["players"] if p["id"] == "4503"]
    other = [p for p in snap["players"] if p["id"] == "7777"]
    assert len(you) == 1 and you[0]["damage"] == 1500      # your own row (3 × 500)
    assert len(other) == 1 and other[0]["damage"] == 1800  # the concurrent stranger is NOT folded in
    assert not other[0].get("inferred_identity")
