"""Community-measured crafting success rates (metabot.gg) feed the workshop: the exporter
parses the product table, the published snapshot is well-formed and matches our catalog's
product names, and crafting.js surfaces a success line (actual / estimated / not available)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
sys.path.insert(0, str(ROOT / "tools"))
import export_crafting_success as ex  # noqa: E402

SUCCESS = json.loads((STATIC / "crafting-success.json").read_text(encoding="utf-8"))
CATALOG = json.loads((STATIC / "crafting-catalog.json").read_text(encoding="utf-8"))
JS = (STATIC / "crafting.js").read_text(encoding="utf-8")

# A minimal product-table fragment in the shape the page renders (tab-separated after tag strip).
_FIXTURE = (
    b"<td>Fine Durable Balaur Horn</td><td>80</td><td>&mdash;</td><td>95.2%</td><td>x</td>"
    b"<td>True Dragon Lord Guard</td><td>Elyos</td><td>60</td><td>25%</td><td>67.5%</td><td>x</td>"
)


def test_exporter_parses_the_product_table():
    recipes = ex.parse(_FIXTURE.replace(b"&mdash;", b"\xe2\x80\x94"))
    assert recipes["fine durable balaur horn"] == {"name": "Fine Durable Balaur Horn", "mastery": 80, "combo_chance": 0.0, "base_success": 95.2}
    g = recipes["true dragon lord guard"]
    assert g["mastery"] == 60 and g["combo_chance"] == 0.25 and g["base_success"] == 67.5


def test_published_snapshot_is_well_formed_and_attributed():
    assert SUCCESS["version"] == 1 and "metabot.gg" in SUCCESS["source"]
    assert "community" in SUCCESS["note"].lower() and "not developer-confirmed" in SUCCESS["note"].lower()
    assert len(SUCCESS["recipes"]) >= 80
    sample = next(iter(SUCCESS["recipes"].values()))
    assert {"name", "mastery", "combo_chance", "base_success"} <= set(sample)
    assert all(0 < r["base_success"] <= 100 for r in SUCCESS["recipes"].values())


def test_snapshot_names_match_catalog_products():
    items = CATALOG["items"]
    outputs = {items.get(str(r["output"]), {}).get("name", "").lower() for r in CATALOG["recipes"].values()}
    matched = set(SUCCESS["recipes"]) & outputs
    # The scraped product names are a subset of our catalog's recipe outputs — so they actually attach.
    assert len(matched) >= len(SUCCESS["recipes"]) * 0.9, (len(matched), len(SUCCESS["recipes"]))


def test_crafting_ui_surfaces_a_success_line():
    assert "crafting-success.json" in JS and "function successLine" in JS
    # It distinguishes measured, projected and missing data.
    assert "not available" in JS and "estimated" in JS and "community-measured" in JS
