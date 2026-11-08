"""What an arcana card you have holds (0.2.389): Gear & Advice listed a card under YOURS by its name, level and
keep / replace only. Each card now shows its deity stat ("Time [Siel] +20"), any other stats, its skill options at
their levels and how many of its option levels they fill. An imported card's own main stats carry the deity stat
(the official API names it by its type, "Time"); a card added from the catalog, or imported before, takes its
variant's fixed stat at the card's grade from the catalog."""
import pytest

from aion2calc.plan import arcana, inventory


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fresh user folder: its database is seeded with the bundled catalog, arcana cards included."""
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def test_an_imported_card_keeps_its_main_stats_and_shows_its_deity_stat(home):
    from test_app import _profile
    from aion2calc.sources.character import from_profile
    imp = from_profile(_profile())
    row = imp.systems["arcana"][0]
    assert row["main_stats"] == [{"id": "Destiny", "value": "20"}]       # Destiny is in no damage stat: the
    assert row["deity"] == {}                                           # card's own stats were all that held it
    inv = inventory.from_character(imp, keep={"class": "sorcerer", "items": []})
    card = next(e for e in inv["items"] if e["category"] == "Parchment")
    assert card["main_stats"] == row["main_stats"]
    assert arcana.card_deity(card) == {"label": "Destiny [Marchutan]", "points": 20.0, "source": "card"}
    assert arcana.card_stats(card) == []
    # the character page's arcana cards show it too
    from aion2calc.app.views import character_view
    view = character_view(imp)
    assert view["arcana_items"][0]["deity"] == {"label": "Destiny [Marchutan]", "points": 20.0, "source": "card"}


@pytest.mark.parametrize("stat, label, points", [
    ({"id": "Time", "name": "Time", "value": "+15", "extra": "5"}, "Time [Siel]", 20.0),   # enchant extra added
    ({"id": "Destruction", "value": "20"}, "Destruction [Zikel]", 20.0),
    ({"id": "Ignored", "name": "Wisdom [Lumiel]", "value": "16"}, "Wisdom [Lumiel]", 16.0),  # by its label
    ({"id": "Space", "value": "12"}, "Space [Israphel]", 12.0),
])
def test_the_deity_stat_is_read_by_its_type_or_its_label(stat, label, points):
    assert arcana.card_deity({"main_stats": [stat]}) == {"label": label, "points": points, "source": "card"}


def test_a_card_without_main_stats_falls_back_to_its_deity_points_then_the_catalog(home):
    assert arcana.card_deity({"deity": {"time": 16}}) == {"label": "Time [Siel]", "points": 16.0, "source": "card"}
    # an equipped card found in the catalog by name, whose Unique variant is listed first: its own grade's stat
    # ("Legend" in the game's data, "Epic" in the catalog)
    for grade in ("Legend", "Epic"):
        card = {"source": "equipped", "name": "Chalice of Vigor", "grade": grade, "slug": "chalice-of-vigor"}
        assert arcana.card_deity(card) == {"label": "Time [Siel]", "points": 16.0, "source": "catalog"}
    # one added from the catalog is that exact variant
    assert arcana.card_deity({"source": "inventory", "slug": "bell-of-magic-rare", "name": "Bell of Magic",
                              "grade": "Rare"}) == {"label": "Destruction [Zikel]", "points": 12.0, "source": "catalog"}
    assert arcana.card_deity({"source": "equipped", "name": "No Such Card", "grade": "Unique"}) is None


def test_a_cards_other_stats_are_listed_as_the_page_shows_them():
    imported = {"source": "equipped", "rolls_text": [["Critical Hit", "+40"]],
                "main_stats": [{"id": "Time", "value": "20"}, {"id": "HPMax", "name": "HP", "value": "100", "extra": "20"}]}
    assert arcana.card_stats(imported) == [["HP", "100 (+20)"], ["Critical Hit", "+40"]]
    added = {"source": "inventory", "rolls": [["Critical Hit", 40]], "rolls_text": "Critical Hit +40"}
    assert arcana.card_stats(added) == [["Critical Hit", "+40"]]


def test_the_third_grade_holds_three_option_levels_by_either_name():
    assert arcana.BASE_ROLLS["Legend"] == arcana.BASE_ROLLS["Epic"] == 3
    assert inventory.options({"category": "Chalice", "grade": "Epic", "name": "Chalice of Vigor"},
                             "sorcerer")["skills"]["base"] == 3
