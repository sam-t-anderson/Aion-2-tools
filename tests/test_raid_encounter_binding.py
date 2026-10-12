"""A raid plan can be bound to an encounter (the boss/mini-boss it is for) so a plan
library can index it by boss and the overlay can auto-play it for the fight you are in.
The binding lives on the a2plan document, round-trips through share codes / imports, and
is sanitised so a shared plan can only ever carry a small, well-formed record."""
import pathlib

JS = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "raid.js").read_text(encoding="utf-8")


def test_new_plans_carry_an_encounter_field():
    assert "encounter: {}" in JS                       # a2plan schema includes the binding


def test_binding_is_sanitised_on_import_and_share_code():
    assert "function cleanEncounter" in JS
    # npc_id is the overlay's match key; coerced to a bounded positive integer.
    assert "parseInt(enc.npc_id" in JS
    assert "enc.boss.trim().slice(0, 80)" in JS         # bounded boss name
    # Applied where untrusted plans enter: the share-code decoder and file/plan import.
    assert JS.count("cleanEncounter(p.encounter)") >= 2


def test_planner_exposes_boss_and_npc_inputs():
    assert 'id="rbossname"' in JS and 'id="rbossnpc"' in JS
    # Editing either updates the plan's encounter and persists it.
    assert '"#rbossname"' in JS and '"#rbossnpc"' in JS
    assert "p.encounter = cleanEncounter(" in JS


def test_can_inherit_the_encounter_from_a_compared_fight():
    assert 'id="rbossfromfight"' in JS
    # The compared fight carries its boss name (and npc/map when the saved fight has them).
    assert "boss: a.boss" in JS
