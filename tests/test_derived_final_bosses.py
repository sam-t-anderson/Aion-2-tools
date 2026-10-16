"""Dungeon tiers the catalog names but attributes no NPC to take their sibling tiers' final boss
under every catalog code of that boss, so a clear of such a tier completes (and can rank) too;
curated entries always win and tiers without a curated sibling stay unmapped."""
import json
from importlib.resources import files

from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info

DATA = files("aion2calc.meter.a2parser").joinpath("data")


def test_derived_tiers_resolve_and_curated_tiers_are_untouched():
    assert dungeon_final_bosses(600022) == frozenset({2300371})                    # Fire Temple, curated
    assert {2300371, 2310371, 2320371, 2330371} <= dungeon_final_bosses(600024)      # a Fire Temple tier with no curated boss
    assert 2330171 in dungeon_final_bosses(600003)                                   # Krao Cave's unassigned tier code
    assert dungeon_final_bosses(600151) == frozenset()                               # Citadel of the Fallen Daeva: no curated sibling
    assert dungeon_final_bosses(0) == frozenset() and dungeon_final_bosses("600024") == frozenset()


def test_every_derived_entry_is_backed_by_the_catalog():
    doc = json.loads(DATA.joinpath("dungeon_final_bosses.json").read_text(encoding="utf-8"))
    dungeons = json.loads(DATA.joinpath("i18n", "dungeons", "en.json").read_text(encoding="utf-8"))
    curated = doc["final_bosses"]
    assert doc["derived_final_bosses"] and not set(doc["derived_final_bosses"]) & set(curated)
    for instance, entry in doc["derived_final_bosses"].items():
        name = dungeons[instance]["name"]
        siblings = [i for i in curated if dungeons.get(i, {}).get("name") == name]
        assert siblings, instance
        sibling_codes = {c for i in siblings for c in curated[i]}
        assert sibling_codes <= set(entry["codes"]), instance
        suffixes = {c % 1000 for c in sibling_codes}
        for code in entry["codes"]:
            info = npc_info(code)
            assert info.get("isBoss") and info.get("name") in entry["boss"] and code % 1000 in suffixes, (instance, code)
