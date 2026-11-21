"""The native Crafting page (0.2.432): the Crafting workshop as the web page shows it (static/crafting.js,
``A2Crafting``), off screen, over the app's own bundled recipe snapshot, success rates and pictures. The arithmetic
(``gui/crafting.py``) was checked against crafting.js's own functions over random filters, plans and scenarios; these
tests pin what it gives.
"""
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QTableWidget  # noqa: E402

from aion2calc.gui import crafting as c  # noqa: E402
from aion2calc.gui import theme  # noqa: E402
from aion2calc.gui import crafting_page as cp  # noqa: E402
from aion2calc.gui.crafting_page import CraftingPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
CATALOG = json.loads((STATIC / "crafting-catalog.json").read_text(encoding="utf-8"))
SUCCESS = json.loads((STATIC / "crafting-success.json").read_text(encoding="utf-8"))
SWORD, TRUE_SWORD, WARNS = "111012001", "111013001", "111013011"   # Noble / True / Splendent True Dragon Lord Longsword
SWORD_ITEM = "110220001"
COMMUNITY = f"<span style='color: {theme.COLORS['muted']};'>community-measured (metabot.gg), not official</span>"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


class FakeApp:
    """The app as the page asks it: its bundled files, read from the package (``fail`` names paths it cannot give,
    ``answers`` stands in for one)."""

    def __init__(self, fail=(), answers=None):
        self.fail, self.answers, self.calls = set(fail), dict(answers or {}), []

    def get(self, path):
        self.calls.append(path)
        if path in self.fail:
            raise OSError("the app did not answer")
        if path in self.answers:
            return self.answers[path]
        assert path in ("/static/crafting-catalog.json", "/static/crafting-success.json", "/static/game-assets.json")
        return json.loads((STATIC / path.rsplit("/", 1)[1]).read_text(encoding="utf-8"))

    def get_bytes(self, path):
        self.calls.append(path)
        assert path.startswith("/static/game-assets/") and ".." not in path
        return (STATIC / path[len("/static/"):]).read_bytes()


def _page(api=None, **kwargs):
    page = CraftingPage(api if api is not None else FakeApp(), **kwargs)
    page.resize(1100, 1600)
    page.show()
    settle(lambda: page.state in ("read", "failed"))
    QCoreApplication.processEvents()
    return page


def _shown(widget, kind):
    QCoreApplication.processEvents()
    return [child for child in widget.findChildren(kind) if child.isVisibleTo(widget)]


def _texts(widget):
    return [label.text() for label in _shown(widget, QLabel)]


def _button(page, words):
    return next((button for button in _shown(page, QPushButton) if button.text() == words), None)


def _entry(page, name):
    return next((entry for entry in _shown(page.detail_box, QLineEdit) if entry.accessibleName() == name), None)


def _finish(entry, text):
    """A field typed into and left (Qt marks it changed, as typing does)."""
    entry.setText(text)
    entry.setModified(True)
    entry.editingFinished.emit()
    QCoreApplication.processEvents()


def _listed(page):
    return [button.recipe_id for button in page.buttons if button.isVisibleTo(page)]


def test_tiers_levels_and_numbers():
    assert [c.tier_level(x) for x in (1, 50, 51, 55, 150, 151, 200, 250, 0, -3, 99.5, None)] == [
        "Novice level 1", "Novice level 50", "Professional level 1", "Professional level 5", "Expert level 50",
        "Master level 1", "Master level 50", "Master level 100", "Novice level 1", "Novice level 1",
        "Professional level 50", "Novice level 1"]
    assert c.my_proficiency("", "") is None and c.my_proficiency("", "17") == 17
    assert c.my_proficiency("Professional", "40") == 90 and c.my_proficiency("Master", "1") == 151
    # numbers as the browser writes them (toLocaleString, at most three places)
    assert [theme.number(x) for x in (10000, 0.25, 1234.5678, 1.0005, 99.99999, -0.0001)] == [
        "10,000", "0.25", "1,234.568", "1.001", "100", "-0"]
    assert c.js_text(99.0) == "99" and c.js_text(67.5) == "67.5" and c.chance_text(0.12345) == "12.345"
    # the fields, read as the web page reads them
    assert c.level_entry("", 50, "7") == "" and c.level_entry("12", 50, "7") == "12"
    assert c.level_entry("0", 50, "7") == c.level_entry("51", 50, "7") == c.level_entry("x", 50, "7") == "7"
    assert c.crafts_entry("10000", 1) == 10000 and c.crafts_entry("2.0", 1) == 2
    assert c.crafts_entry("0", 3) == c.crafts_entry("10001", 3) == c.crafts_entry("1.5", 3) == c.crafts_entry("", 3) == 3
    assert c.seed_entry("", 5) == 0 and c.seed_entry("4294967295", 5) == 4294967295
    assert c.seed_entry("-1", 5) == c.seed_entry("4294967296", 5) == c.seed_entry("seed", 5) == 5
    assert c.owned_entry("12", 0) == 12 and c.owned_entry("", 4) == c.owned_entry("-1", 4) == 4
    assert c.owned_entry(str(10 ** 12 + 1), 4) == 4
    assert c.chance_entry("25") == 0.25 and c.chance_entry("0") == 0.0
    assert c.chance_entry("") is c.chance_entry("101") is c.chance_entry("-1") is c.chance_entry("x") is None


def test_the_recipes_filters_and_standing():
    recipe = CATALOG["recipes"][SWORD]
    assert c.item_name(CATALOG, recipe["output"]) == "Noble Dragon Lord Longsword"
    assert c.heading(CATALOG, SWORD, recipe) == ("Heroic · Weapon · blacksmithing · Elyos · Professional level 45 · "
                                                 "recipe 111012001")
    assert c.recipe_line(CATALOG, recipe, "", None) == "Heroic · blacksmithing · Elyos · Professional level 45"
    assert c.recipe_line(CATALOG, recipe, "40", 90).endswith(" · locked for you")
    assert c.recipe_line(CATALOG, recipe, "45", 95).endswith(" · ✓ you can craft")
    # the list: by name or recipe id, profession, faction, rarity, kind, what you can craft
    everything = c.matching(CATALOG)
    assert len(everything) == 2442 and everything[0][0] == SWORD
    assert [rid for rid, _r in c.matching(CATALOG, "noble DRAGON lord longsword")] == [SWORD, "131012001"]
    assert SWORD in [rid for rid, _r in c.matching(CATALOG, "1110120")]
    assert all(r["profession"] == "cooking" for _rid, r in c.matching(CATALOG, profession="cooking"))
    assert all(r["faction"] == "dark" for _rid, r in c.matching(CATALOG, faction="dark"))
    assert all(c.grade_name(CATALOG, r["output"]) == "Epic" for _rid, r in c.matching(CATALOG, rarity="Epic"))
    assert all(c.type_of(CATALOG, r["output"]) == "Armor" for _rid, r in c.matching(CATALOG, kind="Armor"))
    mine = c.my_proficiency("Professional", "10")
    craftable = c.matching(CATALOG, craftable_only=True, mine=mine)
    assert craftable and all(r["mastery_level"] <= 60 for _rid, r in craftable) and len(craftable) < 2442
    assert c.count_line(2442) == "2442 matching recipes; showing up to 80. Filter or search to narrow the list."
    # the filters offer only what the profession makes, and the level stays within the tier's cap
    cooking = c.profession_meta(CATALOG, "cooking")
    assert cooking["grades"] == ["Common", "Rare", "Epic"] and cooking["types"] == ["ETC"]
    assert cooking["tiers"] == ["Novice", "Professional"]
    assert c.fit_filters(cooking, "Heroic", "Weapon", "Expert", "15") == ("", "", "", "15")
    smithing = c.profession_meta(CATALOG, "blacksmithing")
    assert c.level_cap(smithing, "Expert") == 15 and c.level_cap(smithing, "Novice") == 50 and c.level_cap(smithing, "") == 50
    assert c.fit_filters(smithing, "Heroic", "Weapon", "Expert", "40") == ("Heroic", "Weapon", "Expert", "15")
    # where you stand
    assert c.standing(recipe, "", "", None)[0] == "muted"
    assert c.standing(recipe, "Professional", "40", 90) == (
        "note", "You're 5 levels short: this needs <b>Professional level 45</b> and you entered Professional level 40.")
    assert c.standing(recipe, "Professional", "44", 94)[1].startswith("You're 1 level short")
    assert c.standing(recipe, "Professional", "45", 95)[1].startswith(
        "You can craft this: your Professional level 45 is exactly at the required <b>Professional level 45</b>.")
    assert "is +6 above the required" in c.standing(recipe, "Expert", "1", 101)[1]


def test_the_community_success_rate():
    sword = CATALOG["recipes"][SWORD]
    assert c.success_line(CATALOG, sword, SUCCESS, None) == (
        "muted", "Success rate: not available for this recipe in the community dataset.")
    assert c.success_line(CATALOG, sword, None, None)[0] == "muted"
    true_sword = CATALOG["recipes"][TRUE_SWORD]                 # measured: 67.5% at Professional level 5
    assert c.success_line(CATALOG, true_sword, SUCCESS, None) == ("", (
        "Success rate: <b>67.5%</b> at the required proficiency (Professional level 5), rising toward ~93.1% as you "
        f"out-level it. {COMMUNITY}."))
    assert c.success_line(CATALOG, true_sword, SUCCESS, 55)[1] == f"Success rate: <b>67.5%</b> at your proficiency. {COMMUNITY}."
    assert c.success_line(CATALOG, true_sword, SUCCESS, 76)[1] == (
        "Success rate: <b>67.5%</b> at the requirement (Professional level 5); <b>~80.3%</b> estimated at your +21 "
        f"proficiency (projected toward the ~93.1% cap). Base {COMMUNITY}; the projection is an estimate.")
    assert "<b>~93.1%</b> estimated at your +45" in c.success_line(CATALOG, true_sword, SUCCESS, 100)[1]


def test_the_material_plan_and_its_bounds():
    planned = c.plan(CATALOG, SWORD, 1)
    assert [(m["id"], m["quantity"]) for m in planned["materials"]] == [
        ("110230013", 5), ("610530010", 50), ("610710012", 122), ("610511013", 18), ("610511014", 27), ("610511015", 42),
        ("610511019", 19), ("610620016", 121), ("610610016", 70)]
    assert (planned["fee"], planned["steps"], planned["warnings"]) == (10000, [{"recipe": SWORD, "crafts": 1}], [])
    assert c.fees_line(planned) == "Listed fees: 10,000 Kinah · 1 recipe branches."
    # expanded: the horn is made by its own recipe, 244 crafts for two swords' 244 horns
    expanded = c.plan(CATALOG, SWORD, 2, True, {"610511018": 100, "110230013": 3})
    assert expanded["steps"] == [{"recipe": SWORD, "crafts": 2}, {"recipe": "115023001", "crafts": 244}]
    assert expanded["fee"] == 752000 and "610710012" not in [m["id"] for m in expanded["materials"]]
    rows = {m["id"]: m for m in expanded["materials"]}
    assert rows["610511018"] == {"id": "610511018", "quantity": 488, "owned": 100, "remaining": 388}
    assert rows["110230013"]["remaining"] == 7 and c.material_line(rows["610511018"]) == "Required 488 · remaining 388"
    assert c.plan(CATALOG, WARNS, 1, True)["warnings"] == [c.COMBO_WARNING]
    assert c.plan_heading(True) == "Material plan (expanded where supported)" and c.plan_heading(False) == "Material plan (direct)"
    # bounds: a cycle, too deep, too large, and a recipe that makes nothing
    looped = {"items": {}, "recipes": {
        "a": {"faction": "light", "fee": 1, "output": "x", "quantity": 1, "combo_chance": 0, "inputs": [{"item": "y", "quantity": 1, "recipe": "b"}]},
        "b": {"faction": "light", "fee": 1, "output": "y", "quantity": 1, "combo_chance": 0, "inputs": [{"item": "x", "quantity": 1, "recipe": "a"}]}}}
    with pytest.raises(c.PlanError, match="Recipe cycle detected"):
        c.plan(looped, "a", 1, True)
    assert c.plan(looped, "a", 1)["materials"][0]["id"] == "y"                         # direct: no expansion, no cycle
    deep = {"items": {}, "recipes": {str(i): {"faction": "light", "fee": 0, "output": f"i{i}", "quantity": 1, "combo_chance": 0,
                                               "inputs": [{"item": f"i{i + 1}", "quantity": 1, "recipe": str(i + 1)}]}
                                     for i in range(30)}}
    with pytest.raises(c.PlanError, match="bounded depth/work limit"):
        c.plan(deep, "0", 1, True)
    huge = {"items": {}, "recipes": {"a": {"faction": "light", "fee": 2 ** 52, "output": "x", "quantity": 1, "combo_chance": 0, "inputs": []}}}
    with pytest.raises(c.PlanError, match="safe numeric limits"):
        c.plan(huge, "a", 4)
    empty = {"items": {}, "recipes": {
        "a": {"faction": "light", "fee": 1, "output": "x", "quantity": 1, "combo_chance": 0, "inputs": [{"item": "y", "quantity": 3, "recipe": "b"}]},
        "b": {"faction": "light", "fee": 1, "output": "y", "quantity": 0, "combo_chance": 0, "inputs": []}}}
    with pytest.raises(c.PlanError, match="safe numeric limits"):
        c.plan(empty, "a", 1, True)


def test_item_stats_combo_checks_and_the_export():
    stats = c.item_stats(CATALOG, SWORD_ITEM)
    assert (stats["title"], stats["variant"], stats["levels"][:3], len(stats["levels"])) == ("Item stats · item level 108", "t3", [1, 2, 3], 20)
    assert stats["rows"][:3] == [("Min Attack", "436", "0", "436"), ("Max Attack", "545", "0", "545"), ("Accuracy", "150", "0", "150")]
    assert ("Parry Damage Reduction Rate", "31%", "0%", "31%") in stats["rows"]                  # a percent stat in hundredths
    assert len(stats["rolls"]) == 16 and stats["source"] == "https://gamers4.life/aion-2/database/db/item/en/110220001.json"
    assert c.item_stats(CATALOG, SWORD_ITEM, 5)["rows"][:2] == [("Min Attack", "436", "50", "486"), ("Max Attack", "545", "50", "595")]
    assert c.item_stats(CATALOG, "missing-item") is None
    # combo checks, and the scenario the web page's own generator gives for each seed
    assert c.combo_line(1, 0.25) == ("Conditional on 1 independent completed-craft checks with a fixed 25% combo rate: "
                                     "expected checks triggering combo 0.25; probability of at least one 25%.")
    assert c.combo_line(10, 0.25).endswith("expected checks triggering combo 2.5; probability of at least one 94.369%.")
    assert c.at_least_one(5, 1) == 1 and c.at_least_one(5, 0) == 0
    assert [c.simulate(seed, count, chance) for seed, count, chance in
            ((1, 1000, 0.25), (42, 10000, 0.25), (4294967295, 7, 0.5), (0, 100, 0.999), (123456789, 10000, 0.1))] == [
        255, 2516, 1, 100, 989]
    assert c.simulation_line(1, 255, 1000) == ("Illustrative scenario, seed 1: 255 of 1,000 combo checks triggered. This "
                                               "does not predict game outcomes or output quantities.")
    assert c.rate_line(CATALOG["recipes"][SWORD], None) == (
        "Published combo trigger rate: 25%",
        "Craft success rate is shown above (community-measured where available) · Using the published combo rate.")
    assert c.rate_line(CATALOG["recipes"][SWORD], 0.5)[1].endswith("Using your assumed effective combo rate; no modifier formula is verified.")
    planned = c.plan(CATALOG, SWORD, 3)
    document = c.plan_document(CATALOG, SWORD, {SWORD_ITEM: 5}, 3, 0.25, 7, False, planned)
    assert list(document) == ["format", "version", "source", "source_sha256", "source_retrieved_at", "game_build", "recipe",
                              "products", "item_details_retrieved_at", "completed_crafts", "assumed_effective_combo_chance",
                              "seed", "expand_intermediates", "materials", "fee", "steps", "warnings", "note"]
    assert (document["format"], document["version"], document["game_build"], document["recipe"]) == ("a2craft-plan", 1, None, SWORD)
    assert [(p["id"], p["enhancement_preview"]) for p in document["products"]] == [(SWORD_ITEM, 5), ("110220006", 0)]
    assert document["products"][0]["reference"] == CATALOG["item_details"][SWORD_ITEM] and document["fee"] == 30000


def test_the_page_opens_the_catalog_once_shown(qapp):
    app, opened = FakeApp(), []
    page = CraftingPage(app, open_link=opened.append)
    assert app.calls == []
    page.resize(1100, 1600)
    page.show()
    settle(lambda: page.state == "read")
    QCoreApplication.processEvents()
    assert app.calls[:3] == ["/static/game-assets.json", "/static/crafting-catalog.json", "/static/crafting-success.json"]
    texts = _texts(page.window_)
    assert CATALOG["note"] in texts and CATALOG["item_details_note"] in texts
    source = next(label for label in _shown(page.window_, QLabel) if "Gamers4Life source" in label.text())
    assert "2442 recipes · 1466 source item references · retrieved " in source.text() and "source SHA256 194984fd2e1442f3" in source.text()
    source.linkActivated.emit(CATALOG["source_page"])
    assert opened == [CATALOG["source_page"]]
    # the list: the first 80 of 2442, the first chosen
    assert len(_listed(page)) == 80 and _listed(page)[0] == SWORD and page.selected == SWORD
    assert page.count_label.text() == c.count_line(2442)
    assert page.buttons[0].objectName() == "craftRecipeOn" and page.buttons[1].objectName() == "craftRecipe"
    assert page.buttons[0].name.text() == "Noble Dragon Lord Longsword"
    assert page.buttons[0].line.text() == "Heroic · blacksmithing · Elyos · Professional level 45"
    assert [page.rarity_box.itemText(i) for i in range(page.rarity_box.count())] == ["All rarities", *c.GRADE_ORDER]
    assert [page.kind_box.itemText(i) for i in range(page.kind_box.count())] == ["All types", "Accessory", "Armor",
                                                                                 "Material / other", "Weapon"]
    assert [page.tier_box.itemText(i) for i in range(page.tier_box.count())] == ["—", "Novice", "Professional", "Expert"]
    # the chosen recipe
    texts = _texts(page.detail_box)
    assert "Noble Dragon Lord Longsword" in texts and c.heading(CATALOG, SWORD, CATALOG["recipes"][SWORD]) in texts
    assert c.standing(CATALOG["recipes"][SWORD], "", "", None)[1] in texts
    assert "Success rate: not available for this recipe in the community dataset." in texts
    assert c.ASSUMPTIONS in texts and "Normal product reference" in texts and "Combo product reference" in texts
    assert "1 per listed normal output · 1 for the planned normal-output crafts" in texts
    assert cp.COMBO_CARD in texts and "Published combo trigger rate: 25%" in texts and c.combo_line(1, 0.25) in texts
    assert "Material plan (direct)" in texts and "Listed fees: 10,000 Kinah · 1 recipe branches." in texts
    assert texts.count("Owned base material") == 9 and "Required 122 · remaining 122" in texts
    tables = _shown(page.detail_box, QTableWidget)
    assert [tables[0].horizontalHeaderItem(i).text() for i in range(tables[0].columnCount())] == ["Stat", "Base"]
    assert [tables[0].item(0, i).text() for i in range(2)] == ["Min Attack", "436"]
    link = next(label for label in _shown(page.detail_box, QLabel) if "View source recipe" in label.text())
    link.linkActivated.emit(c.SOURCE_RECIPE.format(SWORD))
    assert opened[-1] == "https://gamers4.life/aion-2/database/en/recipe/111012001/"
    # the bundled pictures, each read once
    settle(lambda: page.buttons[0].picture.pixmap() is not None and not page.buttons[0].picture.pixmap().isNull())
    asked = [call for call in app.calls if call.startswith("/static/game-assets/")]
    assert asked and len(asked) == len(set(asked))


def test_the_filters_and_your_mastery(qapp):
    page = _page()
    page.search_box.setText("Noble Dragon Lord Longsword")
    assert _listed(page) == [SWORD, "131012001"] and page.count_label.text().startswith("2 matching recipes")
    page.search_box.setText("zzz")
    assert not _listed(page) and page.no_recipes.isVisibleTo(page) and page.no_recipes.text() == cp.NO_RECIPES
    page.search_box.setText("")
    page.profession_box.setCurrentIndex(page.profession_box.findData("cooking"))
    page.profession_box.activated.emit(page.profession_box.currentIndex())
    assert [page.rarity_box.itemText(i) for i in range(page.rarity_box.count())] == ["All rarities", "Common", "Rare", "Epic"]
    assert [page.tier_box.itemText(i) for i in range(page.tier_box.count())] == ["—", "Novice", "Professional"]
    assert all(CATALOG["recipes"][rid]["profession"] == "cooking" for rid in _listed(page))
    page.faction_box.setCurrentIndex(page.faction_box.findData("dark"))
    page.faction_box.activated.emit(page.faction_box.currentIndex())
    assert all(CATALOG["recipes"][rid]["faction"] == "dark" for rid in _listed(page))
    page.profession_box.setCurrentIndex(page.profession_box.findData("blacksmithing"))
    page.profession_box.activated.emit(page.profession_box.currentIndex())
    page.faction_box.setCurrentIndex(0)
    page.faction_box.activated.emit(0)
    page.tier_box.setCurrentIndex(page.tier_box.findData("Expert"))
    page.tier_box.activated.emit(page.tier_box.currentIndex())
    assert page.level_box.placeholderText() == "1–15"
    page.level_box.setText("40")
    page.level_box.textEdited.emit("40")
    assert page.level_box.text() == "" and page.my_level == ""                      # past Expert's 15: refused
    page.tier_box.setCurrentIndex(page.tier_box.findData("Professional"))
    page.tier_box.activated.emit(page.tier_box.currentIndex())
    page.level_box.setText("40")
    page.level_box.textEdited.emit("40")
    assert page.my_level == "40" and page.buttons[0].line.text().endswith(" · locked for you")
    assert "You're 5 levels short: this needs Professional level 45 and you entered Professional level 40." in [
        label.text().replace("<b>", "").replace("</b>", "") for label in _shown(page.detail_box, QLabel)]
    page.craftable_box.click()
    assert _listed(page) and all(CATALOG["recipes"][rid]["mastery_level"] <= 90 for rid in _listed(page))
    assert all(button.line.text().endswith(" · ✓ you can craft") for button in page.buttons if button.isVisibleTo(page))
    page.rarity_box.setCurrentIndex(page.rarity_box.findData("Epic"))
    page.rarity_box.activated.emit(page.rarity_box.currentIndex())
    assert all(c.grade_name(CATALOG, CATALOG["recipes"][rid]["output"]) == "Epic" for rid in _listed(page))
    page.kind_box.setCurrentIndex(page.kind_box.findData("Weapon"))
    page.kind_box.activated.emit(page.kind_box.currentIndex())
    assert all(c.type_of(CATALOG, CATALOG["recipes"][rid]["output"]) == "Weapon" for rid in _listed(page))
    page.profession_box.setCurrentIndex(page.profession_box.findData("cooking"))   # cooking makes no Epic weapon
    page.profession_box.activated.emit(page.profession_box.currentIndex())
    assert (page.rarity, page.kind, page.my_tier) == ("Epic", "", "Professional") and page.kind_box.currentData() == ""


def test_a_recipe_planned(qapp, tmp_path):
    saved = tmp_path / "plan.json"
    page = _page(save_as=lambda name: (setattr(page, "asked_name", name), str(saved))[1])
    page.search_box.setText("True Dragon Lord Longsword")
    page.buttons[0].click()
    QCoreApplication.processEvents()
    assert page.selected == TRUE_SWORD and page.buttons[0].objectName() == "craftRecipeOn"
    assert any("<b>67.5%</b> at the required proficiency" in text for text in _texts(page.detail_box))
    _finish(_entry(page, "Planned completed crafts"), "0")
    assert page.count == 1 and _entry(page, "Planned completed crafts").text() == "1"     # refused, put back
    _finish(_entry(page, "Planned completed crafts"), "4")
    settle(lambda: f"{4 * CATALOG['recipes'][TRUE_SWORD]['quantity']} for the planned normal-output crafts" in " ".join(_texts(page.detail_box)))
    assert c.combo_line(4, 0.25) in _texts(page.detail_box)
    # what you own leaves the rest to find
    first = c.plan(CATALOG, TRUE_SWORD, 4)["materials"][0]
    _finish(_entry(page, f"Owned {c.item_name(CATALOG, first['id'])}"), "3")
    settle(lambda: page.stock.get(first["id"]) == 3 and c.material_line({**first, "remaining": first["quantity"] - 3}) in _texts(page.detail_box))
    # the expansion, and a warning for combo-capable intermediates
    expand = next(box for box in _shown(page.detail_box, QCheckBox) if box.text() == cp.EXPAND)
    expand.click()
    settle(lambda: "Material plan (expanded where supported)" in _texts(page.detail_box))
    # the enhancement preview
    choice = next(box for box in _shown(page.detail_box, QComboBox) if box.accessibleName() == "Enhancement preview")
    choice.setCurrentIndex(5)
    choice.activated.emit(5)
    settle(lambda: any(table.columnCount() == 4 for table in _shown(page.detail_box, QTableWidget)))
    table = next(table for table in _shown(page.detail_box, QTableWidget) if table.columnCount() == 4)
    assert [table.horizontalHeaderItem(i).text() for i in range(4)] == ["Stat", "Base", "Listed bonus", "Preview total"]
    # the combo rate, the seed and the scenario; a field only passed through changes nothing (``onchange``)
    _entry(page, "Assumed effective combo rate (%)").editingFinished.emit()
    QCoreApplication.processEvents()
    assert page.effective is None
    _finish(_entry(page, "Assumed effective combo rate (%)"), "150")
    assert page.effective is None and _entry(page, "Assumed effective combo rate (%)").text() == "25"
    _finish(_entry(page, "Assumed effective combo rate (%)"), "50")
    settle(lambda: "Using your assumed effective combo rate; no modifier formula is verified." in " ".join(_texts(page.detail_box)))
    assert page.effective == 0.5 and c.combo_line(4, 0.5) in _texts(page.detail_box)
    _finish(_entry(page, "Scenario seed"), "42")
    _button(page, "Simulate combo checks").click()
    assert page.simulation.text() == c.simulation_line(42, c.simulate(42, 4, 0.5), 4)
    _button(page, "Use source rate").click()
    settle(lambda: "Using the published combo rate." in " ".join(_texts(page.detail_box)))
    assert page.effective is None and page.result == ""
    # the export, as the web page writes it
    _button(page, "Export this material plan").click()
    written = json.loads(saved.read_text(encoding="utf-8"))
    assert page.asked_name == f"craft-plan-{TRUE_SWORD}.json" and page.simulation.text() == f"Material plan saved to {saved}."
    assert written == json.loads(json.dumps(c.plan_document(CATALOG, TRUE_SWORD, page.enhancements, 4, 0.25, 42, True,
                                                            c.plan(CATALOG, TRUE_SWORD, 4, True, page.stock))))
    assert written["seed"] == 42 and written["completed_crafts"] == 4 and written["expand_intermediates"] is True
    # what you entered lasts while the app runs: another recipe and back
    page.buttons[1].click()
    page.buttons[0].click()
    QCoreApplication.processEvents()
    assert (page.count, page.seed, page.stock.get(first["id"]), page.expand) == (4, 42, 3, True)


def test_a_catalog_the_page_cannot_open(qapp):
    missing = _page(FakeApp(fail={"/static/crafting-catalog.json"}))
    assert missing.state == "failed" and missing.status.text() == "Could not open crafting workshop: Crafting catalog unavailable"
    newer = _page(FakeApp(answers={"/static/crafting-catalog.json": {**CATALOG, "version": 2}}))
    assert newer.status.text() == "Could not open crafting workshop: Unsupported crafting catalog" and newer.workspace is None
    without = _page(FakeApp(fail={"/static/crafting-success.json", "/static/game-assets.json"}))
    assert without.state == "read" and without.success is None
    without.search_box.setText("True Dragon Lord Longsword")
    without.buttons[0].click()
    QCoreApplication.processEvents()
    assert "Success rate: not available for this recipe in the community dataset." in _texts(without.detail_box)
    assert without.buttons[0].picture.text() == "◇"                                 # no bundled pictures: the web page's ◇


def test_the_window_draws_crafting_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("crafting"), CraftingPage) and not isinstance(window.page("crafting"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                                        # not moved over yet
