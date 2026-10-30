"""Stamina and MP a skill restores are not healing (0.2.355).

The game sends them in the layout of an HP restore, each with its own effect number (the skill times 100
plus the effect's index) and nothing that names the resource: Defiance's "Restores 1,000 Stamina"
arrives as a heal of 100,000 (Stamina in hundredths) beside its 20% HP restore, Shield Rush's and
Infiltrate's 300 Stamina as 30,000, and Shield of Protection's "Restores {1} MP and Stamina" as 200 and
20,000. The meter counted them all as healing (in the diagnostic captures and on the log server, a
Templar's Defiance outhealed everything else it did). A heal record whose amount is exactly the Stamina
(x100) or MP its skill's own text names is now left out by the decoder, and by the repair every stored
recording passes through when it is loaded. Synthetic records only."""
from aion2calc.combat.unnamed import relabel
from aion2calc.meter.a2parser.lookup import restored_resource
from aion2calc.meter.a2parser.models import HealEvent
from aion2calc.meter.a2parser.parser import decode_stream, parse_damage_packet

DEFIANCE, PROTECTION, SHIELD_RUSH, INFILTRATE = 12260000, 12110000, 12430000, 13360000
POACH_SHIELD, SMASHING_BLOW, ABSORB_ESSENCE, HEALING_TOUCH = 12130040, 11010047, 15760000, 18170000
ME = 4321


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _self_restore(skill, effect, amount):
    """One self-targeted \\x04\\x38 record as the captures carry them: target and actor the same entity,
    layout 4, the effect number (skill x 100 + index) in the modifier block, then two values, the
    second the amount."""
    body = (_varint(ME) + b"\x04\x00" + _varint(ME) + skill.to_bytes(4, "little") + b"\x01\x02"
            + (skill * 100 + effect).to_bytes(4, "little") + b"\x01\x00\x00\x00" + _varint(1000) + _varint(amount) + b"\x01\x00")
    inner = b"\x04\x38" + body
    return _varint(len(inner) + 4) + inner


def test_the_stamina_and_mp_a_skill_names_are_told_from_its_hp_restores():
    assert restored_resource(DEFIANCE, 100_000) == "Stamina"                # "Restores 1,000 Stamina"
    assert restored_resource(DEFIANCE, 9286) is None                        # its 20% HP restore
    assert restored_resource(PROTECTION, 200) == "MP"                       # "Restores {1} MP and Stamina"
    assert restored_resource(PROTECTION, 20_000) == "Stamina"
    assert restored_resource(PROTECTION, 7600) is None                      # "Restores 10% HP once on Block"
    assert restored_resource(SHIELD_RUSH, 30_000) == restored_resource(INFILTRATE, 30_000) == "Stamina"
    assert restored_resource(SMASHING_BLOW, 50) == "MP"                     # Rending Blow's "Restores 50 MP on ... Critical Hit"
    assert restored_resource(ABSORB_ESSENCE, 60) == "MP"                    # "restores {1} MP", at its level
    assert restored_resource(HEALING_TOUCH, 100_000) == "Stamina" and restored_resource(HEALING_TOUCH, 1892) is None
    assert restored_resource(POACH_SHIELD, 3544) is None                    # a shield is no restore
    assert restored_resource(None, 100_000) is None and restored_resource(DEFIANCE, "x") is None


def test_the_decoder_leaves_out_a_restore_and_keeps_the_hp():
    stamina, hp = _self_restore(DEFIANCE, 13, 100_000), _self_restore(DEFIANCE, 14, 9286)
    [read] = parse_damage_packet(stamina, 5, known_players={ME})              # the record itself still reads
    assert isinstance(read, HealEvent) and read.amount == 100_000
    assert list(decode_stream(stamina, 5, set(), known_players={ME})) == []
    [heal] = decode_stream(hp, 5, set(), known_players={ME})
    assert (heal.actor_id, heal.skill_code, heal.amount) == (ME, DEFIANCE, 9286)


def test_a_stored_recording_loses_its_restores_whenever_it_is_loaded():
    def heal(skill, amount, target=None):
        return {"kind": "heal", "t": 1.0, "source": "p:1:1", "target": target, "skill_id": skill, "skill": "x", "amount": amount}
    events = [heal(DEFIANCE, 100_000), heal(DEFIANCE, 9286), heal(PROTECTION, 200), heal(PROTECTION, 20_000),
              heal(PROTECTION, 7600), heal(POACH_SHIELD, 3544, "p:1:1"),
              {"kind": "damage", "t": 2.0, "source": "p:1:1", "target": "12:9", "skill_id": SHIELD_RUSH, "skill": "x", "amount": 30_000}]
    doc = relabel({"segments": [{"entities": [], "hits": [], "events": events}]})
    kept = doc["segments"][0]["events"]
    assert [(e["kind"], e["amount"]) for e in kept] == [("heal", 9286), ("heal", 7600), ("heal", 3544), ("damage", 30_000)]
    assert relabel(doc)["segments"][0]["events"] == kept                      # nothing left to take out
