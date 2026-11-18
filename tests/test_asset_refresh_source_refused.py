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
import urllib.request
from pathlib import Path

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
