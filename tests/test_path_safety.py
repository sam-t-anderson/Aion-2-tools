"""Containment helpers that stop request-controlled names from escaping a base
directory (the barrier behind the path-injection hardening)."""
import os

import pytest

from aion2calc.paths import safe_component, within


def test_safe_component_accepts_a_plain_name():
    assert safe_component("sorcerer.json") == "sorcerer.json"


@pytest.mark.parametrize("bad", [
    "../secret", "a/b", "a\\b", "..", ".", "", "x\x00y", "/etc/passwd",
])
def test_safe_component_rejects_traversal(bad):
    with pytest.raises(ValueError):
        safe_component(bad)


def test_within_resolves_inside_the_base(tmp_path):
    (tmp_path / "data").mkdir()
    target = within(tmp_path, "data", "file.json")
    assert str(target).startswith(str(tmp_path))
    assert target.name == "file.json"


@pytest.mark.parametrize("escape", ["../outside.json", "a/../../outside.json", "/etc/passwd"])
def test_within_blocks_escape(tmp_path, escape):
    with pytest.raises(ValueError):
        within(tmp_path, escape)


def test_within_blocks_symlink_escape(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    link = base / "link"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ValueError):
        within(base, "link")


def test_within_allows_the_base_itself(tmp_path):
    assert within(tmp_path) == tmp_path.resolve()
