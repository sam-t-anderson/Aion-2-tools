"""A fight the recording player fought alone has a party of one. The game sends no party list to a player
outside a party, so every solo fight was exported with an incomplete roster, and the logs listed its party
size as "1?". The party list can also go unsent for minutes while in a party, so the fight must hold nobody
else: another player on its enemy, or any actor the game did not name as an NPC, keeps the party unknown."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.session import CombatSession

ME, PET, STRANGER, BOSS = 5001, 6001, 5002, 9001


def _engine(map_id=111035, dungeon_id=0):
    e = MeterEngine()
    e.names = {ME: "Me", STRANGER: "Stranger"}
    e.known_players = {ME, STRANGER}
    e.roster, e.roster_complete = {}, False
    e.local_player_id, e.local_identity_from_game = ME, True
    e.map_id, e.dungeon_id = map_id, dungeon_id
    e.last_zone_reset_ms = None
    e.spawn_info = {BOSS: {"mobCode": 2300171}}
    e.summons, e.summon_owners = {PET}, {PET: ME}
    return e


def _fight(s, e, actors=(ME,), t0=1_000_000):
    for i in range(5):
        t = t0 + i * 1000
        s.observe(e, [DamageEvent(a, BOSS, 15010000, 1000, t + k) for k, a in enumerate(actors)], timestamp_ms=t + 10)


def _segment(s):
    return s.to_a2log("party")["segments"][-1]


def _session():
    s = CombatSession()
    s.pvp, s.retain_scope = False, "party"
    return s


def test_a_fight_the_player_fought_alone_has_a_party_of_one():
    s, e = _session(), _engine()
    _fight(s, e, actors=(ME, PET))                                      # a pet is the player's own
    segment = _segment(s)
    assert segment["party_roster_complete"] is True and len(segment["party_members"]) == 1


def test_a_stranger_on_the_same_enemy_keeps_the_party_unknown():
    s, e = _session(), _engine()
    _fight(s, e, actors=(ME, STRANGER))
    assert s.out_of_scope == 0                                           # with no party list every effect is kept
    assert _segment(s)["party_roster_complete"] is False


def test_an_unknown_actor_on_the_same_enemy_or_a_heal_from_another_player_keeps_it_unknown():
    s, e = _session(), _engine()
    _fight(s, e)
    s.observe(e, [DamageEvent(7777, BOSS, 1, 50, 1_002_500)], timestamp_ms=1_002_510)   # no spawn or name record
    assert _segment(s)["party_roster_complete"] is False
    s2, e2 = _session(), _engine()
    _fight(s2, e2)
    s2.observe(e2, [HealEvent(STRANGER, 17010000, 500, 1_002_500, target_id=ME)], timestamp_ms=1_002_510)
    assert _segment(s2)["party_roster_complete"] is False


def test_a_party_list_in_the_zone_keeps_its_own_rule():
    s, e = _session(), _engine()
    e.roster = {"Ally": {"serverId": 2107, "dbid": 12, "job": "Cleric"}}    # a party whose ally is elsewhere
    _fight(s, e)
    assert _segment(s)["party_roster_complete"] is False


def test_a_pvp_fight_is_never_counted_alone():
    s, e = _session(), _engine()
    for i in range(5):
        t = 1_000_000 + i * 1000
        s.observe(e, [DamageEvent(ME, STRANGER, 15010000, 1000, t)], timestamp_ms=t + 10)
    segment = s.to_a2log("party")["segments"][-1]
    assert segment["party_roster_complete"] is False


def test_an_enemy_whose_spawn_was_missed_is_still_an_enemy():
    # a meter started inside a zone has no spawn record for the monsters already there
    s, e = _session(), _engine()
    e.spawn_info = {}
    _fight(s, e)
    s.observe(e, [DamageEvent(BOSS, ME, 1, 50, 1_002_500)], timestamp_ms=1_002_510)
    assert _segment(s)["party_roster_complete"] is True
