"""Dungeon tiers the catalog names but attributes no NPC to take their sibling tiers' final boss
under every catalog code of that boss, so a clear of such a tier completes (and can rank) too;
curated entries always win, a tier without a curated sibling stays unmapped unless an outside source names its
final boss among the catalog's rows for the instance, and a hub takes every boss filed under it."""
import json
from importlib.resources import files

from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info

DATA = files("aion2calc.meter.a2parser").joinpath("data")


def test_derived_tiers_resolve_and_curated_tiers_are_untouched():
    assert dungeon_final_bosses(600022) == frozenset({2300371})                    # Fire Temple, curated
    assert {2300371, 2310371, 2320371, 2330371} <= dungeon_final_bosses(600024)      # a Fire Temple tier with no curated boss
    assert 2330171 in dungeon_final_bosses(600003)                                   # Krao Cave's unassigned tier code
    assert dungeon_final_bosses(600151) == frozenset({2301603})                    # Citadel of the Fallen Daeva: a sourced entry
    assert dungeon_final_bosses(0) == frozenset() and dungeon_final_bosses("600024") == frozenset()


def test_every_derived_entry_is_backed_by_the_catalog():
    doc = json.loads(DATA.joinpath("dungeon_final_bosses.json").read_text(encoding="utf-8"))
    dungeons = json.loads(DATA.joinpath("i18n", "dungeons", "en.json").read_text(encoding="utf-8"))
    curated = doc["final_bosses"]
    assert doc["derived_final_bosses"] and not set(doc["derived_final_bosses"]) & set(curated)
    curated_codes = {c for codes in curated.values() for c in codes}
    for instance, entry in doc["derived_final_bosses"].items():
        for code in entry["codes"]:
            info = npc_info(code)
            assert info.get("isBoss") and info.get("name") in entry["boss"], (instance, code)
        if entry.get("source"):
            # a tier the catalog does not name (the Citadel's DBAion2 tiers): its boss is one the catalog files as
            # a final boss under the catalog's own ids for the instance, and an outside page names it the final boss
            assert set(entry["codes"]) <= curated_codes and entry["source"].startswith("https://"), instance
            continue
        if instance not in dungeons:
            # a hub the meter matches by its map (Nightmare): every boss the catalog files under that instance
            assert len(entry["codes"]) > 1, instance
            assert all(npc_info(code).get("dungeonId") == int(instance) for code in entry["codes"]), instance
            continue
        name = dungeons[instance]["name"]
        siblings = [i for i in curated if dungeons.get(i, {}).get("name") == name]
        assert siblings, instance
        sibling_codes = {c for i in siblings for c in curated[i]}
        assert sibling_codes <= set(entry["codes"]), instance
        suffixes = {c % 1000 for c in sibling_codes}
        assert all(code % 1000 in suffixes for code in entry["codes"]), instance


def test_the_citadel_tiers_and_the_nightmare_hub_have_their_final_bosses():
    """The Citadel of the Fallen Daeva's named tiers (600151-600153, DBAion2) take Basilus the False from the
    catalog's Basilus rows under 600144-600146 (metabot.gg names him the Citadel's final boss at the same three
    difficulties); the Nightmare hub (200003) takes every one of its 300 stage bosses, one of which ends each run."""
    from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info
    assert dungeon_final_bosses(600151) == frozenset({2301603})
    assert dungeon_final_bosses(600152) == frozenset({2301703})
    assert dungeon_final_bosses(600153) == frozenset({2301723})
    for code in (2301603, 2301703, 2301723):
        assert npc_info(code)["name"] == "Basilus the False" and npc_info(code)["isBoss"]
    hub = dungeon_final_bosses(200003)
    assert len(hub) == 300 and 2980040 in hub                                   # Gatekeeper Pinopi, Level 1
    assert all(npc_info(code)["isBoss"] and npc_info(code)["dungeonId"] == 200003 for code in hub)
    assert {npc_info(code)["name"] for code in hub} >= {"Gatekeeper Pinopi", "Furious Feruk", "Mutated Gerod"}
