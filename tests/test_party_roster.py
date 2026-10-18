"""The party roster decides whose effects a Party capture keeps. A roster that decoded short dropped the rest of
the party for good: in a Krao Cave run the 0.2.314 meter listed one other member of five, and the log kept under a
third of each boss's damage, the overlay showing two players. The decoder now steps past a member record it cannot
fully read, and inside a group instance every player present counts as the party.

The packets here follow the layout of the 106 roster frames in the diagnostic captures (names made up)."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import scan_party_roster
from aion2calc.meter.session import CombatSession

TAIL = b"\x00\x21" + bytes(7) + b"\x01\x01"          # what follows the combat power in every recorded member


def member(slot, name, server=2102, power=60_000, tail=TAIL, before_server=b""):
    dbid = (server << 48) | (4000 + slot)
    record = bytes([0x1E, slot]) + dbid.to_bytes(8, "little") + bytes([len(name)]) + name.encode()
    record += (7).to_bytes(4, "little") + (45).to_bytes(4, "little") + (1300).to_bytes(4, "little")
    return record + before_server + server.to_bytes(2, "little") + b"\x0d\x10\x04" + power.to_bytes(8, "little") + tail


def empty_slot(slot):
    return bytes([0x1E, slot]) + bytes(8) + b"\x00" + bytes(12)


def roster(records, count=None, dungeon=600001):
    head = b"\x02\x97" + b"\x01\x02\x03\x04" + b"\x05Party" + b"\x05" + dungeon.to_bytes(4, "little")
    head += b"\x00\x03" + ((2102 << 48) | 4001).to_bytes(8, "little") + b"\xff\x02\x02"
    return head + bytes([len(records) if count is None else count]) + b"".join(records) + b"\x00\x09"


def names(packet):
    members, complete, dungeon = scan_party_roster(packet)
    return sorted(members), complete, dungeon


PARTY = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]


def test_a_recorded_layout_decodes_every_member():
    members, complete, dungeon = scan_party_roster(roster([member(i + 1, n) for i, n in enumerate(PARTY)]))
    assert sorted(members) == sorted(PARTY) and complete and dungeon == 600001
    assert members["Charlie"] == {"slot": 3, "dbid": (2102 << 48) | 4003, "serverId": 2102, "job": members["Charlie"]["job"],
                                  "level": 45, "gearScore": 1300, "combatPower": 60_000}


def test_a_longer_member_tail_does_not_cut_the_party_short():
    # The decoder looked 32 bytes past the combat power for the next member; a tail longer than that ended the
    # roster after the first member, with the rest of the party gone.
    records = [member(1, "Alpha", tail=TAIL + bytes(range(1, 41)))] + [member(i + 2, n) for i, n in enumerate(PARTY[1:])]
    assert names(roster(records)) == (sorted(PARTY), True, 600001)


def test_a_gap_in_the_slots_is_stepped_over():
    records = [member(1, "Alpha"), member(2, "Bravo"), member(4, "Delta"), member(5, "Echo")]
    assert names(roster(records)) == (["Alpha", "Bravo", "Delta", "Echo"], True, 600001)


def test_a_member_record_with_an_unexpected_layout_is_still_listed():
    # No server id where the decoder expects it: the member is listed by name, class and level without a combat
    # power, and the members after it are decoded too.
    records = [member(1, "Alpha"), member(2, "Bravo", before_server=bytes(12)), member(3, "Charlie")]
    members, complete, _ = scan_party_roster(roster(records))
    assert sorted(members) == ["Alpha", "Bravo", "Charlie"] and complete
    assert "combatPower" not in members["Bravo"] and members["Bravo"]["level"] == 45
    assert members["Charlie"]["combatPower"] == 60_000


def test_an_empty_slot_does_not_hide_the_members_after_it():
    # The members after it are read. The count then is not met, so the roster is merged rather than replacing
    # the one known (and a wipe is never inferred from it), as it already was for an empty last slot.
    middle = [member(1, "Alpha"), empty_slot(2), member(3, "Charlie"), member(4, "Delta")]
    assert names(roster(middle)) == (["Alpha", "Charlie", "Delta"], False, 600001)
    assert names(roster([empty_slot(1), member(2, "Bravo"), member(3, "Charlie")])) == (["Bravo", "Charlie"], True, 600001)
    assert names(roster([member(1, "Alpha"), member(2, "Bravo"), empty_slot(3)])) == (["Alpha", "Bravo"], False, 600001)


def _engine(map_id, dungeon_id):
    e = MeterEngine()
    e.names = {5001: "Me", 5002: "Ally", 5003: "Third", 5004: "Fourth"}
    e.known_players = {5001, 5002, 5003, 5004}
    e.roster = {"Ally": {"serverId": 2107, "dbid": 12, "job": "Cleric"}}   # decoded short: not even "Me"
    e.roster_complete = False
    e.local_player_id = 5001
    e.local_identity_from_game = True
    e.map_id, e.dungeon_id = map_id, dungeon_id
    e.last_zone_reset_ms = None
    e.spawn_info = {9001: {"mobCode": 2300171}}
    return e


def _fight(s, e, t0=1_000_000):
    for i in range(5):
        t = t0 + i * 1000
        s.observe(e, [DamageEvent(a, 9001, 11010000, 1000 * (a - 5000), t + a - 5000) for a in (5001, 5002, 5003, 5004)],
                  timestamp_ms=t + 10)


def test_in_a_dungeon_every_player_present_is_the_party():
    s, e = CombatSession(), _engine(600001, 600001)            # Krao Cave
    s.pvp, s.retain_scope = False, "party"
    _fight(s, e)
    assert s.out_of_scope == 0 and len(s.records) == 20         # nobody's hits dropped
    rows = {r["name"]: r["damage"] for r in s.snapshot("party")["players"]}
    assert rows == {"Me": 5000, "Ally": 10000, "Third": 15000, "Fourth": 20000}
    segment = s.to_a2log("party")["segments"][-1]
    assert len(segment["party_members"]) == 4 and segment["party_roster_complete"] is True
    assert sum(h["damage"] for h in segment["hits"]) == 50_000


def test_a_player_counted_through_the_instance_is_a_member_of_the_fights_they_were_in():
    # A party that changes inside one instance: each line-up is listed for its own fights only, not both for
    # every fight in the zone context (replaying a recorded two-line-up Krao Cave capture listed 12 members).
    s, e = CombatSession(), _engine(600001, 600001)
    s.pvp, s.retain_scope = False, "party"
    for start, third in ((1_000_000, 5003), (1_200_000, 5004)):   # past the 120 s gap: two fights
        for i in range(5):
            t = start + i * 1000
            s.observe(e, [DamageEvent(a, 9001, 11010000, 100, t + a - 5000) for a in (5001, 5002, third)], timestamp_ms=t + 10)
    first, second = (sorted(m.rsplit(":", 1)[-1] for m in seg["party_members"]) for seg in s.to_a2log("party")["segments"])
    assert first == ["12", "5001", "5003"] and second == ["12", "5001", "5004"]     # Ally by roster id, Me, then each third


def test_in_the_open_world_the_roster_still_decides():
    s, e = CombatSession(), _engine(111035, 0)                  # an open-world map: other players are strangers
    s.pvp, s.retain_scope = False, "party"
    _fight(s, e)
    assert s.out_of_scope == 10 and {r.event.actor_id for r in s.records} == {5001, 5002}
    assert {r["name"] for r in s.snapshot("party")["players"]} == {"Me", "Ally"}
