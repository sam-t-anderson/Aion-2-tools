"""The verified deity-name mapping and the in-game Genus/Pantheon observation
snapshot stay consistent with each other and with the modelled genus data."""
import json
from pathlib import Path

from aion2calc.sources.character import DEITY_NAMES, DEITY_TYPES

ROOT = Path(__file__).resolve().parent.parent / "aion2calc" / "data" / "global"


def test_deity_names_are_a_verified_subset_of_the_deity_types():
    assert set(DEITY_NAMES) <= DEITY_TYPES                    # every named deity is a known effect category
    assert len(DEITY_NAMES) == 9                              # nine were on the observed board
    assert DEITY_NAMES["Justice"] == "Nezekan" and DEITY_NAMES["Time"] == "Siel"
    assert DEITY_NAMES["Illusion"] == "Kaisinel"
    assert "Destruction" not in DEITY_NAMES                   # present in the API set but unobserved -> not guessed


def test_observed_snapshot_is_valid_and_reconciles_with_the_model():
    snap = json.loads((ROOT / "genus_pantheon_observed.json").read_text(encoding="utf-8"))
    model = json.loads((ROOT / "genus_insight.json").read_text(encoding="utf-8"))

    genera = snap["genus_insight"]["genera"]
    names = [g["name"] for g in genera]
    assert names == ["Cogni", "Fera", "Natura", "Varian", "Special"]
    assert set(names) == set(model["genera"])                 # same five genera the model defines
    special = next(g for g in genera if g["name"] == "Special")
    assert special["level"] == 10 and special["max"] is True  # observed at MAX
    assert all(line["value"] >= 0 for g in genera for line in g["analysis_effect"])

    pantheon = snap["pantheon"]
    assert pantheon["collection_owned"] == 15 and pantheon["collection_total"] == 94
    assert len(pantheon["deities"]) == 9
    for d in pantheon["deities"]:                             # the snapshot's names match the code mapping exactly
        assert DEITY_NAMES[d["category"]] == d["deity"]
