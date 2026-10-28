"""What's new after an update (0.2.353): the release notes the player has not seen, once, drawn from the changelog
the app carries as plain HTML with nothing of the text taken for markup; Settings shows this version's again."""
import json

import pytest

from aion2calc.app import patch_notes

CHANGELOG = """# Release notes

## Third thing (0.2.12)

A paragraph with `code`, **bold**, *italics* and a [link](https://example.test/a_(b)).

- one
  - nested
- two

## Second thing (0.2.11)

Text.

## First thing (0.2.10)

Older.
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setattr(patch_notes, "__version__", "0.2.12")
    monkeypatch.setattr(patch_notes, "_LAUNCH", {"earlier": None})
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(patch_notes, "notes_path", lambda: notes)
    return tmp_path / "home"


def test_the_changelog_splits_into_versions_newest_first():
    found = patch_notes.sections(CHANGELOG)
    assert [(s["version"], s["title"]) for s in found] == [("0.2.12", "Third thing"), ("0.2.11", "Second thing"),
                                                          ("0.2.10", "First thing")]


def test_markdown_is_drawn_and_every_character_of_the_text_escaped():
    html = patch_notes.render(patch_notes.sections(CHANGELOG)[0]["body"])
    assert "<code>code</code>" in html and "<strong>bold</strong>" in html and "<em>italics</em>" in html
    assert '<a href="https://example.test/a_(b)" target="_blank" rel="noopener">link</a>' in html
    assert "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>" in html
    hostile = patch_notes.render('<script>alert(1)</script> [x](javascript:alert(1)) `<b>` "q"')
    assert "<script>" not in hostile and "&lt;script&gt;" in hostile
    assert "javascript:" not in hostile.split("href")[0] and 'href="javascript' not in hostile
    assert "<code>&lt;b&gt;</code>" in hostile


def test_after_an_update_the_unseen_versions_show_once(home):
    (home / "app_url.txt").write_text("http://127.0.0.1:8765/", encoding="utf-8")    # an earlier launch was here
    (home / patch_notes.STATE).write_text(json.dumps({"seen": "0.2.10"}), encoding="utf-8")
    patch_notes.started()
    out = patch_notes.pending()
    assert out["show"] and [n["version"] for n in out["notes"]] == ["0.2.12", "0.2.11"]
    assert out["all"] == patch_notes.RELEASES_URL
    patch_notes.mark_seen()
    assert patch_notes.pending()["show"] is False
    forced = patch_notes.pending(force=True)                        # Settings' What's new: this version's, again
    assert forced["show"] is False and [n["version"] for n in forced["notes"]] == ["0.2.12"]


def test_a_new_install_shows_nothing_and_an_install_from_before_the_record_shows_this_version(home):
    patch_notes.started()                                           # nothing here before: a new install
    assert patch_notes.pending()["show"] is False
    assert json.loads((home / patch_notes.STATE).read_text(encoding="utf-8")) == {"seen": "0.2.12"}
    (home / patch_notes.STATE).unlink()
    (home / "app_url.txt").write_text("x", encoding="utf-8")        # an install from before 0.2.353 kept no record
    patch_notes.started()
    out = patch_notes.pending()
    assert out["show"] and [n["version"] for n in out["notes"]] == ["0.2.12"]


def test_a_changelog_the_build_does_not_carry_shows_nothing(home, monkeypatch):
    monkeypatch.setattr(patch_notes, "notes_path", lambda: home / "missing.md")
    (home / "app_url.txt").write_text("x", encoding="utf-8")
    patch_notes.started()
    assert patch_notes.pending() == {"version": "0.2.12", "all": patch_notes.RELEASES_URL, "show": False, "notes": []}


def test_the_shipped_changelog_holds_this_versions_notes():
    from aion2calc import __version__
    notes = patch_notes.notes_since(None, __version__)
    assert notes and notes[0]["version"] == __version__ and "<" in notes[0]["html"]
