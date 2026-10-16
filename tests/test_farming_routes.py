"""Farming routes on the Maps page: an attributed catalog of waypoint loops from a source whose
terms allow reuse, computed loop order labelled as computed, guide links where no such source
exists, and nothing invented for zones without one."""
import json
from pathlib import Path

import pytest

from aion2calc.scrape import routes

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
CATALOG = json.loads((STATIC / "farming-routes.json").read_text(encoding="utf-8"))


def test_the_bundled_catalog_is_attributed_and_consistent():
    assert CATALOG["format"] == "a2routes" and CATALOG["version"] == 1
    for key, src in CATALOG["sources"].items():
        assert src["license"] and src["license_url"].startswith("https://") and src["url"].startswith("https://")
        assert src["attribution"] and len(src["revision"]) == 40
    ids = [z["id"] for z in CATALOG["zones"]]
    assert ids == ["verteron", "altgard", "reshanta", "poeta", "ishalgen"]
    for zone in CATALOG["zones"]:
        assert zone["name"] and zone["faction"] in ("elyos", "asmodian", "both") and zone["notes"]
        for route in zone["routes"]:
            assert route["source"] in CATALOG["sources"] and "computed" in route["method"]
            assert [w["n"] for w in route["waypoints"]] == list(range(1, route["count"] + 1))
            assert sum(l["count"] for l in route["legs"]) == route["count"]
            assert route["legs"][0]["from"] == 1 and route["legs"][-1]["to"] == route["count"]
            assert all(isinstance(w["x"], int) and isinstance(w["y"], int) for w in route["waypoints"])
        for guide in zone["guides"]:
            assert guide["url"].startswith("https://") and guide["title"] and guide["topic"]
    by_id = {z["id"]: z for z in CATALOG["zones"]}
    assert {r["id"] for r in by_id["verteron"]["routes"]} == {"hiddenCube", "monolithMaterial"}
    assert {r["id"] for r in by_id["altgard"]["routes"]} == {"hiddenCube", "monolithMaterial"}
    assert [r["id"] for r in by_id["reshanta"]["routes"]] == ["monolithMaterial"] and by_id["reshanta"]["guides"]
    # Zones with no permitted source carry no route and say so; nothing is invented for them.
    for zone_id in ("poeta", "ishalgen"):
        assert by_id[zone_id]["routes"] == [] and any("No source with reuse terms" in n for n in by_id[zone_id]["notes"])
    assert all(any("no source with reuse terms" in n.lower() for n in z["notes"]) for z in CATALOG["zones"])


def test_the_builder_orders_a_loop_from_source_markers_and_names_areas(tmp_path):
    yaml = pytest.importorskip("yaml")
    data = tmp_path / "data"
    (data / "markers").mkdir(parents=True)
    (data / "regions").mkdir()
    square = [[[0, 0], [100, 0], [100, 100], [0, 100]]]
    (data / "regions" / "World_L_A.yaml").write_text(yaml.safe_dump({"regions": [
        {"id": "r1", "name": "WesternCantasValley", "type": "", "borders": square},
        {"id": "r2", "name": "GardenoftheIllusionGod", "type": "", "borders": [[[200, 0], [300, 0], [300, 100], [200, 100]]]}]}), encoding="utf-8")
    markers = [{"category": "location", "subtype": "teleport", "name": "t", "x": 5, "y": 5, "id": "t1"}]
    for i, (x, y) in enumerate([(90, 90), (10, 10), (50, 50), (250, 50), (210, 10)]):
        markers.append({"category": "collection", "subtype": "hiddenCube", "name": "", "x": x, "y": y, "id": f"c{i}"})
    (data / "markers" / "World_L_A.yaml").write_text(yaml.safe_dump({"markers": markers}), encoding="utf-8")
    for other in ("World_D_A", "Abyss_Reshanta_A"):
        (data / "markers" / f"{other}.yaml").write_text("markers: []\n", encoding="utf-8")
    catalog = routes.build(data, "a" * 40, checked_at="2026-10-16T00:00:00+00:00")
    verteron = catalog["zones"][0]
    route = verteron["routes"][0]
    assert route["id"] == "hiddenCube" and route["count"] == 5 and route["start"] == {"area": "Western Cantas Valley", "near_teleport": True}
    assert [(w["x"], w["y"]) for w in route["waypoints"]][0] == (10, 10)            # nearest the teleport
    assert [w["area"] for w in route["waypoints"]] == ["Western Cantas Valley"] * 3 + ["Garden of the Illusion God"] * 2
    assert route["legs"] == [{"area": "Western Cantas Valley", "from": 1, "to": 3, "count": 3},
                             {"area": "Garden of the Illusion God", "from": 4, "to": 5, "count": 2}]
    assert catalog["sources"]["aion2-interactive-map"]["revision"] == "a" * 40
    # Maps without markers get no route and say so; the starter zones say no permitted source exists.
    assert catalog["zones"][1]["routes"] == [] and any("no markers" in n for n in catalog["zones"][1]["notes"])
    assert catalog["zones"][3]["id"] == "poeta" and catalog["zones"][3]["routes"] == []
    with pytest.raises(ValueError):
        routes.build(data, "short")


def test_names_and_loops():
    assert routes.pretty("WesternCantasValley") == "Western Cantas Valley"
    assert routes.pretty("GardenoftheIllusionGod") == "Garden of the Illusion God"
    assert routes.pretty("ForestofExiles") == "Forest of Exiles" and routes.pretty("PilgrimsRidge") == "Pilgrim's Ridge"
    assert routes.pretty("IdunsLake") == "Idun's Lake" and routes.pretty("") == ""
    points = [(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)]
    order = routes.loop(points, 0)
    assert sorted(order) == [0, 1, 2, 3, 4] and order[0] == 0
    assert routes.loop([(0, 0)]) == [0] and routes.loop([]) == []
    assert routes.region_of([{"name": "A", "borders": [[[0, 0], [10, 0], [10, 10], [0, 10]]]},
                             {"name": "B", "borders": [[[100, 100], [110, 100], [110, 110], [100, 110]]]}], 5, 5) == "A"
    assert routes.region_of([{"name": "A", "borders": [[[0, 0], [10, 0], [10, 10], [0, 10]]]},
                             {"name": "B", "borders": [[[100, 100], [110, 100], [110, 110], [100, 110]]]}], 90, 90) == "B"


def test_the_maps_page_renders_the_catalog_on_app_and_site():
    js = (STATIC / "maps.js").read_text(encoding="utf-8")
    assert "farming-routes.json" in js and "function mountRoutes" in js and "Copy as text" in js
    assert "links only" in js and "data-copy-route" in js
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert pages.count("aion2calc/app/static/farming-routes.json") == 2
    assert "routes-build" in (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
