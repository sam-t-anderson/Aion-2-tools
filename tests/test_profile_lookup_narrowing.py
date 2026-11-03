"""The upload-time profile lookup tells same-named characters apart (0.2.375). A name is unique on a server,
not in a region: a recording that kept no server for a character left the official search with every character
of that name in the region (ten of one name in North America), and the lookup gave up ("did not identify
exactly one matching character"). The search's own results carry each character's class (``pcId``) and the
game's database id (the portrait address's ``charKey``), which a recording keeps. Synthetic names only."""
from aion2calc.sources import official, profile_snapshot
from aion2calc.sources.official import search_char_key, search_class
from aion2calc.sources.profile_snapshot import lookup, narrowed, recorded_character_id


def _row(server, pc_id, key, name="Qavren"):
    return {"characterId": f"id{server}", "name": f"<strong>{name}</strong>", "race": int(str(server)[0]), "pcId": pc_id,
            "level": 45, "serverId": server, "serverName": "x",
            "profileImageUrl": f"/game_profile_images/aion2global/images?gameServerKey={server}&charKey={key}", "region": "nae"}


ROWS = [_row(1101, 22, 900000000000000011), _row(2102, 7, 900000000000000022), _row(2104, 32, 900000000000000033),
        _row(2105, 6, 900000000000000044)]


def test_a_search_result_names_its_class_and_database_id():
    assert [search_class(x) for x in (5, 8, 9, 14, 17, 22, 28, 32, 36)] == [
        "gladiator", "gladiator", "templar", "ranger", "assassin", "spiritmaster", "sorcerer", "cleric", "chanter"]
    assert search_class(0) is None and search_class(None) is None and search_class(True) is None
    assert search_char_key(ROWS[1]["profileImageUrl"]) == "900000000000000022"
    assert search_char_key("/images?charKey=abc") is None and search_char_key(None) is None


def _search(monkeypatch, rows=ROWS):
    monkeypatch.setattr(official, "fetch_json", lambda url, params, referer=None: {"list": rows})
    return {m["character_id"]: m for m in official.search("Qavren", region="nae")}


def test_the_recorded_database_id_then_the_class_tell_same_named_characters_apart(monkeypatch):
    found = _search(monkeypatch)
    assert [m["class"] for m in found.values()] == ["spiritmaster", "gladiator", "cleric", "gladiator"]
    by_id = narrowed(found, {"name": "Qavren", "id": "p:2105:900000000000000044", "class": "gladiator"})
    assert [m["server_id"] for m in by_id.values()] == [2105]                 # the id outranks the class
    assert [m["server_id"] for m in narrowed(found, {"name": "Qavren", "class": "cleric"}).values()] == [2104]
    assert [m["server_id"] for m in narrowed(found, {"name": "Qavren", "class": "Elementalist"}).values()] == [1101]
    assert len(narrowed(found, {"name": "Qavren", "class": "gladiator"})) == 2      # two gladiators: no guess
    assert narrowed(found, {"name": "Qavren"}) == found                         # nothing recorded to tell them apart
    assert narrowed(found, {"name": "Qavren", "class": "templar"}) == found     # none of the class: still ambiguous
    assert recorded_character_id({"character_id": "77"}) == "77" and recorded_character_id({"id": "p:2102:88"}) == "88"
    assert recorded_character_id({"id": "25:42617"}) is None and recorded_character_id({"id": "p:2102:qavren"}) is None


def test_the_lookup_at_upload_fetches_the_one_character_the_recording_names(monkeypatch):
    _search(monkeypatch)
    fetched = []

    def fetch(character_id, server_id, region, details=True, use_cache=0, progress=None):
        fetched.append((character_id, server_id, region))
        return {"profile": {"characterName": "Qavren", "serverId": server_id, "className": "Cleric"}, "items": {}}

    monkeypatch.setattr(profile_snapshot.official, "fetch_character", fetch)
    ready = lookup({"name": "Qavren", "class": "cleric"}, region="nae")
    assert ready["status"] == "ready" and fetched == [("id2104", 2104, "nae")]
    assert ready["identity"] == {"name": "Qavren", "server": "2104", "region": "nae", "character_id": "id2104"}
    unsure = lookup({"name": "Qavren", "class": "gladiator"}, region="nae")
    assert unsure["status"] == "unavailable" and "4 characters with this name" in unsure["reason"]
    assert "choose the character's server" in unsure["reason"] and len(fetched) == 1
