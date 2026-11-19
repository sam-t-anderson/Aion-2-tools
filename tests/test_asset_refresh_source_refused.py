"""The asset refresh keeps going when metabot.gg refuses it.

Since 12 November 2026 metabot.gg has answered the scheduled `Refresh game asset references` run with HTTP 403,
and the run stopped before the crafting, NPC-portrait and catalog-audit steps. A source that cannot be read at
all now leaves the snapshot's skill icons as they are and the rest of the refresh runs. A page that answers with
a changed layout or a disagreeing icon still fails the run, and an icon the snapshot never had still counts as
missing.
"""
import hashlib
import importlib.util
import json
import runpy
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest

from aion2calc.scrape.http import NotFound

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("refresh_assets", ROOT / "tools" / "refresh_assets.py")
refresh_assets = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(refresh_assets)

SKILL = "https://metabot.gg/web/aion2/skills/{}.webp"


def _classes(tmp_path, *names):
    files = []
    for name in names:
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
        files.append(tmp_path / f"{name}.json")
    return files


def test_a_refused_class_page_is_reported_as_the_source_being_unavailable(tmp_path, monkeypatch):
    def refused(cls, fresh):
        raise NotFound(f"403 for https://metabot.gg/en/aion-2/classes/{cls}/build")
    monkeypatch.setattr(refresh_assets.metabot, "class_data", refused)
    with pytest.raises(refresh_assets.SourceUnavailable, match="403"):
        refresh_assets.class_skill_refs(_classes(tmp_path, "assassin"))


def test_a_page_that_answers_with_a_changed_layout_still_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh_assets.metabot, "class_data", lambda cls, fresh: {"skills": []})
    with pytest.raises(ValueError, match="layout changed"):
        refresh_assets.class_skill_refs(_classes(tmp_path, "assassin"))
    skills = [{"id": n, "icon": SKILL.format(n + 1)} for n in range(1, 20)]
    monkeypatch.setattr(refresh_assets.metabot, "class_data", lambda cls, fresh: {"skills": skills})
    with pytest.raises(ValueError, match="disagrees"):
        refresh_assets.class_skill_refs(_classes(tmp_path, "assassin"))


def test_the_snapshot_skill_references_are_kept_and_nothing_else(tmp_path):
    manifest = tmp_path / "game-assets.json"
    manifest.write_text(json.dumps({"references": {
        "metabot:skill:11": {"namespace": "metabot", "kind": "skill", "id": "11", "url": SKILL.format(11)},
        "metabot:skill:12": {"namespace": "metabot", "kind": "skill", "id": "12", "url": SKILL.format(99)},
        "metabot:item-slug:x": {"namespace": "metabot", "kind": "item-slug", "id": "x",
                                "url": "https://metabot.gg/web/aion2/items/x.webp"},
    }}), encoding="utf-8")
    assert refresh_assets.previous_skill_refs(manifest) == {11: {"id": 11, "url": SKILL.format(11)}}
    with pytest.raises(ValueError, match="No previous asset snapshot"):
        refresh_assets.previous_skill_refs(tmp_path / "absent.json")


def test_the_current_snapshot_yields_its_skill_references():
    refs = refresh_assets.previous_skill_refs(ROOT / "aion2calc/app/static/game-assets.json")
    assert len(refs) > 100 and all(row["url"] == SKILL.format(key) for key, row in refs.items())


def _exporter_tree(tmp_path, held, new):
    """A copy of tools/export_game_assets.py beside catalogs naming one icon it holds and one it doesn't."""
    (tmp_path / "tools").mkdir()
    shutil.copy(ROOT / "tools/export_game_assets.py", tmp_path / "tools/export_game_assets.py")
    static = tmp_path / "aion2calc/app/static"
    (static / "game-assets").mkdir(parents=True)
    skills = [{"id": 1, "icon": held}, {"id": 2, "icon": new}]
    (static / "build-catalog.json").write_text(json.dumps({"classes": {"assassin": {"skills": skills}}}),
                                               encoding="utf-8")
    (static / "crafting-catalog.json").write_text(json.dumps({"items": {}}), encoding="utf-8")
    name = hashlib.sha256(held.encode()).hexdigest()[:24] + ".webp"
    (static / "game-assets" / name).write_bytes(b"RIFF\0\0\0\0WEBPheld")
    return tmp_path / "tools/export_game_assets.py", static, name


def test_an_icon_the_snapshot_holds_is_kept_when_checking_it_again_is_refused(tmp_path, monkeypatch, capsys):
    held, new = SKILL.format(1), SKILL.format(2)
    script, static, name = _exporter_tree(tmp_path, held, new)

    def refused(request, timeout=0):
        raise urllib.request.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refused)
    monkeypatch.setattr("sys.argv", [str(script), "--refresh-existing"])
    runpy.run_path(str(script), run_name="__main__")
    manifest = json.loads((static / "game-assets.json").read_text(encoding="utf-8"))
    assert manifest["assets"] == {held: "game-assets/" + name}   # kept, file untouched
    # Never held (this skill, and the class and Odyle Energy icons the exporter always adds): still missing,
    # so the refresh still fails rather than publish a snapshot without them.
    assert new in manifest["missing"] and held not in manifest["missing"]
    assert (static / "game-assets" / name).read_bytes() == b"RIFF\0\0\0\0WEBPheld"
    assert "could not be checked again" in capsys.readouterr().out


# DBAion2 (dbaion2.ru) as the second source for skill icons.

def _dbaion2_table(*rows):
    return json.dumps([{"id": 13000000 + n, "name": f"Skill {n}", "icon": f"ICON_AS_SKILL_{n:03d}"}
                       for n in range(1, 12)] + list(rows)).encode()


def test_dbaion2s_table_gives_each_skill_id_its_game_icon():
    icons = refresh_assets.dbaion2_skill_icons(_dbaion2_table({"id": 13999999, "name": "No icon"}))
    assert icons[13000001] == "https://dbaion2.ru/icons/ICON_AS_SKILL_001.webp"
    assert 13999999 not in icons and len(icons) == 11


@pytest.mark.parametrize("bad", [{"id": "13010000", "icon": "X"}, {"id": 13010000, "icon": "../x"},
                                 {"id": 13010000, "icon": "a" * 81}, "not a row"])
def test_a_dbaion2_table_of_another_shape_is_refused(bad):
    with pytest.raises(ValueError):
        refresh_assets.dbaion2_skill_icons(_dbaion2_table(bad))
    with pytest.raises(ValueError, match="layout changed"):
        refresh_assets.dbaion2_skill_icons(b'{"skills": []}')


def test_an_icon_metabot_will_not_serve_comes_from_dbaion2_under_the_url_the_app_looks_up(tmp_path, monkeypatch,
                                                                                          capsys):
    held, new = SKILL.format(1), SKILL.format(2)
    script, static, name = _exporter_tree(tmp_path, held, new)
    mirror = "https://dbaion2.ru/icons/ICON_AS_SKILL_002.webp"
    mirrors = tmp_path / "mirrors.json"
    mirrors.write_text(json.dumps({held: "https://dbaion2.ru/icons/ICON_AS_SKILL_001.webp", new: mirror}),
                       encoding="utf-8")
    asked = []

    class Response:
        def __init__(self, data):
            self.data = data

        def read(self, _n):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def metabot_refuses(request, timeout=0):
        asked.append(request.full_url)
        if urlparse(request.full_url).hostname == "dbaion2.ru":
            return Response(b"RIFF\0\0\0\0WEBPdbaion2")
        raise urllib.request.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", metabot_refuses)
    monkeypatch.setattr("sys.argv", [str(script), "--refresh-existing", "--mirrors", str(mirrors)])
    runpy.run_path(str(script), run_name="__main__")
    manifest = json.loads((static / "game-assets.json").read_text(encoding="utf-8"))
    new_name = hashlib.sha256(new.encode()).hexdigest()[:24] + ".webp"
    assert manifest["assets"][new] == "game-assets/" + new_name          # filed under metabot's URL
    assert (static / "game-assets" / new_name).read_bytes() == b"RIFF\0\0\0\0WEBPdbaion2"
    assert manifest["fetched_from"] == {new: mirror}
    assert manifest["sources"] == ["https://metabot.gg/", "https://gamers4.life/aion-2/database/en/crafting-calculator/",
                                   "https://dbaion2.ru/"]
    # The icon it already held is kept as it was, not replaced by DBAion2's.
    assert (static / "game-assets" / name).read_bytes() == b"RIFF\0\0\0\0WEBPheld"
    assert "https://dbaion2.ru/icons/ICON_AS_SKILL_001.webp" not in asked
    assert new not in manifest["missing"]
    assert "fetched from DBAion2" in capsys.readouterr().out


def test_a_mirror_outside_dbaion2s_icons_is_refused(tmp_path, monkeypatch):
    script, static, _ = _exporter_tree(tmp_path, SKILL.format(1), SKILL.format(2))
    mirrors = tmp_path / "mirrors.json"
    mirrors.write_text(json.dumps({SKILL.format(2): "https://example.com/x.webp"}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [str(script), "--mirrors", str(mirrors)])
    with pytest.raises(ValueError, match="mirror"):
        runpy.run_path(str(script), run_name="__main__")


# DBAion2 dropping the connection (19 November 2026: SSL UNEXPECTED_EOF during the handshake).

class _Bytes:
    def __init__(self, data):
        self.data = data

    def read(self, _n):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_dropped_connection_is_asked_again_and_a_refusal_is_not(monkeypatch):
    calls = []

    def flaky(request, timeout=0):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise urllib.error.URLError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
        return _Bytes(b"[]")
    monkeypatch.setattr(refresh_assets, "urlopen", flaky)
    monkeypatch.setattr(refresh_assets.time, "sleep", lambda _s: None)
    assert refresh_assets.download("https://dbaion2.ru/data-en/npcs.json", 1024) == b"[]" and len(calls) == 3

    calls.clear()

    def refused(request, timeout=0):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(refresh_assets, "urlopen", refused)
    with pytest.raises(urllib.error.HTTPError):
        refresh_assets.download("https://metabot.gg/x", 1024)
    assert len(calls) == 1


def test_the_published_portraits_give_back_the_rows_they_were_matched_from(tmp_path):
    portraits = tmp_path / "en.json"
    portraits.write_text(json.dumps({
        "2100001": {"name": "A Boss", "icon": "https://dbaion2.ru/icons/UT_256_MOB_Boss_01.webp"},
        "2100002": {"name": "Elsewhere", "icon": "https://example.com/icons/x.webp"},
    }), encoding="utf-8")
    assert refresh_assets.previous_npc_rows(portraits) == [{"id": 2100001, "name": "A Boss",
                                                            "icon": "UT_256_MOB_Boss_01"}]
    with pytest.raises(ValueError, match="No previous NPC portraits"):
        refresh_assets.previous_npc_rows(tmp_path / "absent.json")


def test_the_published_portraits_rebuild_unchanged_while_dbaion2_cannot_be_reached():
    portraits = ROOT / "aion2calc/meter/a2parser/data/i18n/npc-portraits/en.json"
    rows = refresh_assets.previous_npc_rows(portraits)
    published = json.loads(portraits.read_text(encoding="utf-8"))
    assert len(rows) == len(published) > 100
    assert {str(r["id"]): f"https://dbaion2.ru/icons/{r['icon']}.webp" for r in rows} == \
        {k: v["icon"] for k, v in published.items()}
