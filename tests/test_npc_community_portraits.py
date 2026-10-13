"""The community portrait overlay in npc_info: a fallback behind the curated
bundled table. The server's scraped npc-portraits-community.json fills art for
catalog NPCs that have no bundled portrait, and never overrides a curated one."""
import json

from aion2calc.meter.a2parser import lookup
from aion2calc.meter.a2parser.lookup import npc_info, set_community_portraits


def _fake_tables(monkeypatch, npcs, bundled):
    def table(category, locale):
        return {"npcs": npcs, "npc-portraits": bundled}.get(category, {})
    monkeypatch.setattr(lookup, "_table", table)
    monkeypatch.setattr(lookup, "_npc_overrides", lambda: {})


def test_community_portrait_fills_an_npc_without_bundled_art(tmp_path, monkeypatch):
    _fake_tables(monkeypatch, {"500": {"name": "Fediv Wraith"}}, {})
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"portraits": {"500": {"name": "Fediv Wraith",
                       "icon": "https://gamers4.life/x/Texture/Portrait/fediv.webp", "source": "gamers4.life"}}}))
    try:
        set_community_portraits(overlay)
        info = npc_info(500)
        assert info["name"] == "Fediv Wraith"
        assert info["icon"] == "https://gamers4.life/x/Texture/Portrait/fediv.webp"
    finally:
        set_community_portraits(None)


def test_bundled_portrait_wins_over_community(tmp_path, monkeypatch):
    _fake_tables(monkeypatch, {"500": {"name": "Kapu"}},
                 {"500": {"name": "Kapu", "icon": "https://dbaion2.ru/icons/curated.webp"}})
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"portraits": {"500": {"icon": "https://gamers4.life/community.webp"}}}))
    try:
        set_community_portraits(overlay)
        assert npc_info(500)["icon"] == "https://dbaion2.ru/icons/curated.webp"  # curated stays primary
    finally:
        set_community_portraits(None)


def test_overlay_accepts_a_flat_map_and_only_augments_catalog_npcs(tmp_path, monkeypatch):
    _fake_tables(monkeypatch, {"500": {"name": "Known"}}, {})
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"500": "https://gamers4.life/a.webp", "999": "https://gamers4.life/b.webp"}))
    try:
        set_community_portraits(overlay)
        assert npc_info(500)["icon"] == "https://gamers4.life/a.webp"
        assert npc_info(999) == {}          # no catalog entry -> community art is not invented onto it
    finally:
        set_community_portraits(None)


def test_missing_or_cleared_overlay_yields_no_icon(tmp_path, monkeypatch):
    _fake_tables(monkeypatch, {"500": {"name": "Known"}}, {})
    set_community_portraits(tmp_path / "does-not-exist.json")
    assert "icon" not in npc_info(500)
    set_community_portraits(None)
    assert "icon" not in npc_info(500)


def test_community_name_fills_an_id_the_catalog_does_not_map(tmp_path, monkeypatch):
    # New content (e.g. the 295xxxx range) the bundled catalog hasn't mapped: the scraped
    # name resolves it instead of showing "#<code>". Marked community-sourced.
    from aion2calc.meter.a2parser.lookup import npc_name
    _fake_tables(monkeypatch, {}, {})                       # empty catalog: id 2951001 is unknown
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"portraits": {"2951001": {"name": "Nemon", "icon": None,
                                                              "source": "gamers4.life"}}}))
    try:
        set_community_portraits(overlay)
        info = npc_info(2951001)
        assert info == {"name": "Nemon", "community": True}  # name only, no art
        assert npc_name(2951001) == "Nemon"                  # was "#2951001"
    finally:
        set_community_portraits(None)


def test_community_name_and_art_for_an_unmapped_id(tmp_path, monkeypatch):
    _fake_tables(monkeypatch, {}, {})
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"portraits": {"2951100": {"name": "Guard",
                       "icon": "https://gamers4.life/icons/reference/npcs/2951100.webp"}}}))
    try:
        set_community_portraits(overlay)
        info = npc_info(2951100)
        assert info["name"] == "Guard" and info["community"] is True
        assert info["icon"].endswith("/2951100.webp")
    finally:
        set_community_portraits(None)


def test_unmapped_id_without_a_scraped_name_stays_unknown(tmp_path, monkeypatch):
    # An overlay row with art but no name must not invent a nameless NPC onto an id the
    # catalog doesn't map — only a real scraped name resolves an unknown id.
    _fake_tables(monkeypatch, {}, {})
    overlay = tmp_path / "npc-portraits-community.json"
    overlay.write_text(json.dumps({"portraits": {"2952000": {"name": None,
                       "icon": "https://gamers4.life/icons/reference/npcs/2952000.webp"}}}))
    try:
        set_community_portraits(overlay)
        assert npc_info(2952000) == {}
    finally:
        set_community_portraits(None)
