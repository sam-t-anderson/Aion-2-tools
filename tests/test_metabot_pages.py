"""metabot.gg's pages as the database sync reads them, and what the sync does when they read wrong (0.2.371).

In late October 2026 the site moved to Next.js 16 and its titles table gained a Role column. The text walk then
read nothing past each page's root, and the titles listing read one column off: installs stored the role as each
title's equip bonus and the equip bonus as its owned bonus, and every item the sync fetched since was stored with
no stats. Every page here is synthetic; no test touches the network.
"""
import gzip
import json

import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.db import store
    monkeypatch.setattr(store, "SEED", tmp_path / "no-seed.json.gz")
    store._local.__dict__.clear()
    yield tmp_path / "home"
    store._local.__dict__.clear()


def flight_rows(rows: dict) -> str:
    return "\n".join(f"{key}:{json.dumps(value)}" for key, value in rows.items())


def test_the_text_walk_follows_a_next16_page_through_its_router_maps():
    """The router tree reaches the page through "$Q" maps and keeps each segment's node under "d"; an SVG path's "d"
    is still not text, and a map's keys are not text either."""
    from aion2calc.scrape.rsc import text_lines
    data = flight_rows({
        "0": {"P": None, "c": ["", "en", "titles"], "t": {"t": {"s": "", "d": {"r": "$L1", "p": False}, "c": "$Q2"}}},
        "1": ["$", "header", None, {"children": "Site menu"}],
        "2": [["children", {"s": "titles", "d": {"r": "$L3", "p": False}, "c": "$Q4"}]],
        "3": ["$", "div", None, {"children": "Titles layout"}],
        "4": [["children", {"s": "__PAGE__", "d": {"r": "$L5", "p": False}}]],
        "5": ["$", "table", None, {"children": [
            ["$", "path", None, {"d": "M0 0L1 1"}],
            ["$", "tr", "0", {"children": [["$", "th", "0", {"children": "A Title"}],
                                           ["$", "td", "1", {"children": "Unique"}], "$@6"]}]]}],
        "6": ["$", "td", "2", {"children": "Both factions"}],
    })
    lines = text_lines(data)
    seen = [line for line in lines if line in ("Site menu", "Titles layout", "A Title", "Unique", "Both factions")]
    assert seen == ["Site menu", "Titles layout", "A Title", "Unique", "Both factions"]
    assert "children" not in lines and "M0 0L1 1" not in lines


def _title_lines(rows, role=True):
    out = []
    for name, grade, faction, role_word, equip, owned in rows:
        out += [name, grade, faction] + ([role_word] if role else []) + [equip, owned, "How to get"]
    return out


ROWS = [("Strong", "Unique", "Both factions", "Offensive", "PvE Damage Boost +4.5%, Critical Hit +68",
         "PvE Damage Boost +1%"),
        ("Tough", "Epic", "Elyos", "Defensive", "Defense Bonus +300", "MP +20"),
        ("Fast", "Rare", "Asmodian", "Utility", "Combat Speed +3.5%", "HP +120"),
        ("Season", "Unique", "Both factions", "—", "—", "—")]


def test_the_titles_listing_reads_with_and_without_its_role_column():
    from aion2calc.scrape import metabot
    new = metabot.parse_titles(["Titles", "Name"] + _title_lines(ROWS))
    assert [(t["name"], t["equip"], t["owned"], t.get("role"), t.get("slot")) for t in new] == [
        ("Strong", "PvE Damage Boost +4.5%, Critical Hit +68", "PvE Damage Boost +1%", "Offensive", "Attack"),
        ("Tough", "Defense Bonus +300", "MP +20", "Defensive", "Defense"),
        ("Fast", "Combat Speed +3.5%", "HP +120", "Utility", "Etc"),
        ("Season", "—", "—", None, None)]
    old = metabot.parse_titles(_title_lines(ROWS, role=False))
    assert [(t["name"], t["equip"], t["owned"]) for t in old] == [(r[0], r[4], r[5]) for r in ROWS]
    assert all("role" not in t for t in old)


def test_a_titles_listing_that_read_wrong_never_replaces_the_stored_one():
    from aion2calc.scrape import metabot
    many = [dict(name=f"T{i}", grade="Rare", faction="Elyos", equip=f"Critical Hit +{i}", owned=f"HP +{i}")
            for i in range(60)]
    assert metabot.titles_problem(many) is None
    assert "read as 3 titles" in metabot.titles_problem(many[:3])
    moved = [dict(t, equip="Offensive", owned=t["equip"]) for t in many]
    assert "read a role where a bonus belongs" in metabot.titles_problem(moved)
    assert "without a value" in metabot.titles_problem([dict(t, equip="Critical Hit") for t in many])


def test_an_item_page_reads_its_facts_far_above_the_stats_and_one_enchant_table():
    """The Next.js 16 item page keeps the facts block a few hundred lines above the stats, puts no-break spaces
    around each enhancement step's arrow, adds a PvP enhancement table that starts again at +0, and ends the last
    class's skill pool at the app banner."""
    from aion2calc.scrape import metabot
    lines = (["Grade", "Unique", "Category", "Legs", "Item Level", "70", "Required Level", "45",
              "Max enhance", "+15 (+18)", "Trading", "Soul-bound on pickup"] + ["filler"] * 200
             + ["Fixed stats come with every copy of Greaves; random stats are rolled from the pool below.",
                "Defense", "+131", "HP", "+90", "Random stats", "Roll chance", "Accuracy", "+10 – +20", "50%",
                "Enhancement rates", "Step", "Stats at new level",
                "+0\xa0→\xa0+1", "1", "5,000", "Kina", "Enhance Stone", "Defense +11, HP +9",
                "+1\xa0→\xa0+2", "1", "7,300", "Kina", "Enhance Stone", "Defense +22, HP +18",
                "+0\xa0→\xa0+1", "1", "9,000", "Kina", "Enhance Stone", "PvP Damage Tolerance +0.5%",
                "Random skill options", "Templar", "2 skills, up to Lv. 1", "up to Lv. 1", "Shield Bash", "50%",
                "Punishment", "50%", "MetaBot Desktop", "Download for Windows"])
    item = metabot._parse_item(lines, "greaves")
    assert item["meta"] == {"Category": "Legs", "Item Level": "70", "Required Level": "45", "Max enhance": "+15 (+18)"}
    assert item["fixed"] == {"Defense": "+131", "HP": "+90"}
    assert item["random"] == [{"stat": "Accuracy", "range": "+10 – +20", "chance": "50%"}]
    assert item["enchant"] == [{"step": "+0 → +1", "stats": "Defense +11, HP +9"},
                               {"step": "+1 → +2", "stats": "Defense +22, HP +18"}]
    assert metabot._skill_pools(lines)["templar"]["skills"] == ["Shield Bash", "Punishment"]


SHIFTED = {"name": "Unbound by Genus", "grade": "Unique", "faction": "Both factions", "equip": "Offensive",
           "owned": "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68", "slot": "Attack"}


def test_the_planners_read_a_shifted_title_list_put_back(home):
    """A title list the sync stored one column off is read put back: the equip bonus in place, the owned bonus
    from the shipped copy, else from the title page's sentence, else unknown."""
    from aion2calc.paths import write_user_json
    from aion2calc.plan import titles
    unknown = {"name": "Not Shipped", "grade": "Rare", "faction": "Elyos", "equip": "Defensive",
               "owned": "Block +44", "earn": "Equipped, it gives Block +44. Owning it adds MP +5 to your title "
                                             "collection bonus."}
    bare = {"name": "Also Not Shipped", "grade": "Rare", "faction": "Elyos", "equip": "Utility", "owned": "HP +9"}
    write_user_json([SHIFTED, unknown, bare], "global", "titles.json")
    rows = {t["name"]: t for t in titles.titles_data()}
    assert rows["Unbound by Genus"]["equip"] == "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68"
    assert rows["Unbound by Genus"]["owned"] == "PvE Damage Boost +1%" and rows["Unbound by Genus"]["role"] == "Offensive"
    assert (rows["Not Shipped"]["equip"], rows["Not Shipped"]["owned"], rows["Not Shipped"]["slot"]) == \
        ("Block +44", "MP +5", "Defense")
    assert (rows["Also Not Shipped"]["equip"], rows["Also Not Shipped"]["owned"], rows["Also Not Shipped"]["slot"]) == \
        ("HP +9", "—", "Etc")
    cat = {t["name"]: t for t in titles.catalog()}
    assert cat["Unbound by Genus"]["equip_stats"] and cat["Unbound by Genus"]["owned_stats"]
    assert cat["Unbound by Genus"]["equip_stats"] != cat["Unbound by Genus"]["owned_stats"]


def _seed(path, items):
    path.write_bytes(gzip.compress(json.dumps([{"data": it, "lastmod": "2026-10-01"} for it in items]).encode()))


def test_the_sync_puts_back_what_the_misread_pages_stored(home, tmp_path, monkeypatch):
    """Before anything is fetched, and with the site unreachable: the shifted titles are put back on disk, an item
    stored empty takes the seed's copy or goes so it is fetched again, and the gear reference's empty entries take
    the shipped ones. A titles listing that reads wrong is reported and stored nowhere."""
    from aion2calc.db import store, sync
    from aion2calc.paths import PKG_DATA, read_json, write_user_json
    from aion2calc.scrape import metabot
    good = {"slug": "kept-sword", "name": "Kept Sword", "fixed": {"Attack": "+10"}, "meta": {"Category": "Sword"}}
    stone = {"slug": "theostone-x", "name": "Theostone: X", "category": "Theostone"}     # no stats, and right so
    seed = tmp_path / "seed.json.gz"
    _seed(seed, [good, stone])
    monkeypatch.setattr(store, "SEED", seed)
    monkeypatch.setattr(store.import_seed, "__defaults__", (seed,))       # its default was bound at import
    shipped = json.loads((PKG_DATA / "global" / "items.json").read_text(encoding="utf-8"))
    slug = next(s for s, e in shipped.items() if e.get("fixed"))
    write_user_json({slug: {"slug": slug, "fixed": {}, "random": [], "enchant": [], "meta": {}}}, "global", "items.json")
    write_user_json([SHIFTED], "global", "titles.json")
    db = tmp_path / "s.db"
    conn = store.connect(db)
    blank = {"fixed": {}, "random": [], "enchant": [], "meta": {}, "skill_pools": {}, "category": None}
    with conn:
        store.upsert_item(conn, {"slug": "kept-sword", **blank}, "2026-11-01")
        store.upsert_item(conn, {"slug": "gone-ring", **blank}, "2026-11-01")
    monkeypatch.setattr(metabot, "sitemap", lambda name: {})
    monkeypatch.setattr(metabot, "category_slugs", lambda cat: [])
    monkeypatch.setattr(metabot, "titles", lambda fresh=False: [dict(SHIFTED, name=f"T{i}") for i in range(60)])
    monkeypatch.setattr(sync.Sync, "_classes", lambda self, conn, pages: [])
    state = sync.Sync(db_path=db).run()
    assert read_json("global", "titles.json")[0]["equip"].startswith("PvE Damage Boost +4.5%")
    assert store.item(conn, "kept-sword")["fixed"] == {"Attack": "+10"} and store.item(conn, "gone-ring") is None
    assert read_json("global", "items.json")[slug] == shipped[slug]
    assert store.item(conn, "theostone-x")["name"] == "Theostone: X"           # a named item without stats stays
    assert state.changed["titles_repaired"] == 1 and state.changed["items_repaired"] == 2
    assert any("read a role where a bonus belongs" in e and "keeping the stored titles" in e for e in state.errors)


def test_the_sync_never_stores_an_item_page_that_read_as_nothing(home, tmp_path, monkeypatch):
    from aion2calc.db import store, sync
    from aion2calc.scrape import metabot
    slugs = [f"item-{i}" for i in range(8)]
    monkeypatch.setattr(metabot, "sitemap", lambda name: {})
    monkeypatch.setattr(metabot, "category_slugs", lambda cat: slugs if cat == "weapons" else [])
    read = []
    monkeypatch.setattr(metabot, "item_full", lambda slug, cache=False: read.append(slug) or
                        {"slug": slug, "fixed": {}, "random": [], "enchant": [], "meta": {}})
    monkeypatch.setattr(metabot, "titles", lambda fresh=False: [])
    monkeypatch.setattr(sync.Sync, "_classes", lambda self, conn, pages: [])
    db = tmp_path / "s.db"
    state = sync.Sync(db_path=db).run()
    assert store.connect(db).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    assert len(read) == sync.UNREAD_ITEMS_STOP                          # the layout changed: the rest waits
    assert any("read without stats" in e for e in state.errors)


def test_saved_advice_with_shifted_titles_is_calculated_again():
    from aion2calc.plan.advisor import shifted_titles
    plate = {"name": "Unbound by Genus", "equip": "Offensive",
             "owned_bonus": "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68"}
    assert shifted_titles({"titles": {"slots": {"Attack": {"equipped": plate, "best": []}}, "collect": []}})
    collect = {"name": "Unbound by Genus", "owned_bonus": "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68"}
    assert shifted_titles({"titles": {"slots": {}, "collect": [collect]}})
    right = {"name": "Unbound by Genus", "equip": "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68",
             "owned_bonus": "PvE Damage Boost +1%"}
    assert not shifted_titles({"titles": {"slots": {"Attack": {"equipped": right}},
                                          "collect": [{"name": "Unbound by Genus", "owned_bonus": "PvE Damage Boost +1%"}]}})
    assert not shifted_titles({"character": {}})
