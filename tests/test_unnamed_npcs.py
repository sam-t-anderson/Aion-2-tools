"""What the game shows as "???" -- the invisible summons a boss's mechanics strike with, a Sorcerer's
ground effects, flags and timers -- is labelled in logs (0.2.355): an NPC by what its catalog row
is ("Unnamed summon"), a player's summon by the skill it strikes with. In 289 of 1,053 segments of
75 recent public logs an enemy or a pet was named "???". Synthetic data only."""
from aion2calc.combat.unnamed import relabel
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import npc_info
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession
from aion2calc.scrape import supplement

ORB, TALISRA = 2920563, 2356709         # an invisible summon of Talisra's fight; Talisra of the Void


def test_a_catalog_row_the_game_names_question_marks_is_labelled_by_its_type():
    orb = npc_info(ORB)
    assert orb["name"] == "Unnamed summon" and orb["unnamed"] is True and orb["npc_type"] == "Summon"
    assert orb["isBoss"] is False                                      # the catalog's fields stay
    assert npc_info(TALISRA)["name"] == "Talisra of the Void" and "unnamed" not in npc_info(TALISRA)


def test_the_supplement_keeps_the_type_of_a_placeholder_row_and_never_its_internal_name():
    community = {"10": {"name": "???", "isBoss": False}, "11": {"name": "Guard", "isBoss": False}}
    rows = supplement.build([{"id": 10, "name": "N_Invisible_Summon_X_01", "npcType": "Summon"},
                             {"id": 11, "name": "Guard Captain", "npcType": "Monster"},
                             {"id": 12, "name": "Merchant", "npcType": "Npc"}], [], community, {})
    assert rows["npcs"] == {"10": {"type": "Summon"}, "12": {"name": "Merchant", "type": "Npc"}}


def _doc():
    hits = [{"t": 1.0 + i, "player": "p:1", "target": "1:900", "skill_id": 15280000, "skill": "Bittercold Wind",
             "damage": 100.0, "pet": "1:50"} for i in range(3)]
    hits.append({"t": 5.0, "player": "p:1", "target": "1:900", "skill_id": 15390000, "skill": "Fire Wall",
                 "damage": 100.0, "pet": "1:50"})
    hits.append({"t": 6.0, "player": "p:1", "target": "1:900", "skill_id": 15200012, "skill": "Skill 15200012",
                 "damage": 100.0, "pet": "1:51"})
    entities = [{"id": "1:900", "name": "Talisra of the Void", "kind": "enemy", "mob_code": TALISRA, "is_boss": True},
                {"id": "1:901", "name": "???", "kind": "enemy", "mob_code": ORB},
                {"id": "1:902", "name": "???", "kind": "enemy"},
                {"id": "1:50", "name": "???", "kind": "pet", "owner": "p:1"},
                {"id": "1:51", "name": "???", "kind": "pet", "owner": "p:1"},
                {"id": "1:52", "name": "?", "kind": "pet", "owner": "p:1"}]
    return {"segments": [{"entities": entities, "hits": hits}]}


def test_old_recordings_are_relabelled_when_read():
    names = {e["id"]: e["name"] for e in relabel(_doc())["segments"][0]["entities"]}
    assert names == {"1:900": "Talisra of the Void", "1:901": "Unnamed summon", "1:902": "Unnamed NPC",
                     "1:50": "Bittercold Wind",          # the skill it struck with most
                     "1:51": "Cold Storm",               # an unlisted rank of a listed skill: its family's name
                     "1:52": "Unnamed summon"}           # struck with nothing: never guessed
    assert relabel({"segments": [None, {}]}) == {"segments": [None, {}]} and relabel(None) is None


def test_the_meter_exports_the_label():
    e = MeterEngine()
    e.map_id = e.dungeon_id = 610062
    e.names, e.known_players = {5001: "Me"}, {5001}
    e.local_player_id, e.local_identity_from_game = 5001, True
    e.spawn_info[9001] = {"mobCode": ORB, "maxHp": 10, "reportedMaxHp": 10, "currentHp": 10}
    e.known_entities.add(9001)
    s = CombatSession()
    s.pvp = False
    t0 = 1_000_000
    for i in range(3):
        events = [DamageEvent(actor_id=9001, target_id=5001, skill_code=1800000, damage=900, timestamp_ms=t0 + i * 1000),
                  DamageEvent(actor_id=5001, target_id=9001, skill_code=11010000, damage=5, timestamp_ms=t0 + i * 1000)]
        s.observe(e, events, timestamp_ms=t0 + i * 1000)
    names = [x["name"] for seg in s.to_a2log("party")["segments"] for x in seg["entities"] if x["id"].endswith(":9001")]
    assert names and set(names) == {"Unnamed summon"}
