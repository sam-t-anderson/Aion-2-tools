"""The shared local-document loader used by the npc-evidence and defeats CLIs."""
import json

from aion2calc.__main__ import _load_local_docs


def test_load_local_docs_reads_files_and_folders(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"n": 1}), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps({"n": 2}), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")        # non-json is not globbed
    one = tmp_path / "solo.json"
    one.write_text(json.dumps({"n": 3}), encoding="utf-8")

    from_dir = _load_local_docs([str(tmp_path)], on_skip=lambda *_: None)
    assert sorted(d["n"] for d in from_dir) == [1, 2, 3]                     # every .json in the folder

    from_file = _load_local_docs([str(one)], on_skip=lambda *_: None)
    assert [d["n"] for d in from_file] == [3]                               # a single file by path


def test_load_local_docs_skips_bad_files_without_failing(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    skipped = []
    docs = _load_local_docs([str(tmp_path), str(tmp_path / "missing.json")], on_skip=skipped.append)
    assert docs == [{"ok": True}]                                           # the good one still loads
    assert len(skipped) == 2 and any("broken.json" in s for s in skipped)   # bad + missing both noted
