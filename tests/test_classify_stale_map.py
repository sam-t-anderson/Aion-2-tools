"""Automatic context: a recorded instance id wins over a stale open-world map id. The
instance-entry record precedes the map record (or the map record is lost), so the first fights
inside an instance carried the open-world map id and were typed open-world trash -- and a boss
among them an open-world field-boss kill. Seen in the live server's recent uploads."""
from aion2calc.meter.context import classify


def test_recorded_instance_beats_a_stale_open_world_map():
    r = classify(1110, 600092, False, [])                 # Altgard's map id, Ferocious Horn Den's instance id
    assert r["encounter_type"] == "expedition" and r["zone"] == "Ferocious Horn Den"
    assert "open-world map id not yet updated at entry" in r["zone_source"]
    ev = r["classification"]
    assert ev["status"] == "catalog_match" and ev["basis"] == "recorded_instance" and ev["stale_map"] is True


def test_open_world_without_an_instance_stays_open_world():
    r = classify(1110, 0, False, [])
    assert r["encounter_type"] == "pve_open_world" and r["classification"]["status"] == "map_match"
    assert "stale_map" not in r["classification"]


def test_an_unknown_instance_id_with_an_open_world_map_is_still_a_conflict():
    r = classify(1110, 999_999_123, False, [])            # no such instance in the catalog: nothing to trust
    assert r["encounter_type"] == "pve_open_world" and r["classification"]["status"] == "conflict"


def test_a_matching_map_and_instance_carry_no_stale_mark():
    r = classify(600092, 600092, False, [])
    assert r["encounter_type"] == "expedition" and r["zone"] == "Ferocious Horn Den"
    assert "stale_map" not in r["classification"] and "not yet updated" not in r["zone_source"]
