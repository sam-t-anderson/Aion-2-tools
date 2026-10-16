"""Catalog leftovers: an instance the catalog does not name but whose final boss is curated is
labelled "<Final boss> (instance N)", marked derived, and the catalog-gaps report lists what
is still missing upstream without inventing anything."""
import json
import subprocess
import sys

from aion2calc.combat.catalog import gaps
from aion2calc.meter.context import DERIVED_ZONE, classify, derived_zone_label


def test_the_gap_report_lists_the_three_gaps_from_the_bundled_tables():
    report = gaps()
    counts = report["counts"]
    assert report["format"] == "a2catalog-gaps" and report["catalog_revision"] and report["catalog_source"].get("revision")
    # Named tiers without a boss: only the Citadel tiers remain (no curated sibling to derive from).
    assert {row["instance_id"] for row in report["named_tiers_without_final_boss"]} >= {600151, 600152, 600153}
    assert counts["named_tiers_without_final_boss"] == len(report["named_tiers_without_final_boss"]) <= 5
    # The unnamed instances carry their curated boss names and the label reports will use.
    unnamed = report["unnamed_instances_with_final_boss"]
    assert counts["unnamed_instances_with_final_boss"] == len(unnamed) >= 50
    for row in unnamed:
        assert row["final_bosses"] and row["codes"]
        assert row["label"].endswith(f" (instance {row['instance_id']})") and row["final_bosses"][0] in row["label"]
    assert {r["instance_id"] for r in unnamed} >= {610020, 910011}
    # Every curated code is backed by a named boss NPC record.
    assert report["final_boss_codes_without_npc"] == [] and counts["final_boss_codes_without_npc"] == 0
    assert counts["curated_instances"] >= 100 and counts["derived_tiers"] >= 17


def test_an_unnamed_instance_is_labelled_by_its_final_boss_and_marked_derived():
    instance = gaps()["unnamed_instances_with_final_boss"][0]["instance_id"]
    label = derived_zone_label(instance)
    assert label and label.endswith(f"(instance {instance})")
    result = classify(0, instance, False, [])
    assert result["zone"] == label and result["zone_source"].endswith(DERIVED_ZONE)
    assert result["classification"]["derived_zone"] is True
    assert result["classification"]["status"] == "catalog_match"
    # A named dungeon keeps its exact catalog name and is not marked derived.
    named = classify(0, 600022, False, [])
    assert named["zone"] and "(instance" not in named["zone"] and named["zone_source"].endswith(" + exact dungeon name")
    assert "derived_zone" not in named["classification"]
    # No curated boss, no name: nothing is invented.
    assert derived_zone_label(600151) is None and derived_zone_label(0) is None
    assert "zone" not in classify(0, 999_999_001, False, [])        # unknown instance: no name, no curated boss


def test_the_cli_writes_the_report(tmp_path):
    out = tmp_path / "gaps.json"
    run = subprocess.run([sys.executable, "-m", "aion2calc", "catalog-gaps", "--out", str(out)],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["unnamed_instances_with_final_boss"] == len(report["unnamed_instances_with_final_boss"])
    assert "Instances with a curated final boss but no dungeon name:" in run.stdout
    assert "Named dungeon tiers without a curated or derived final boss:" in run.stdout
