"""The bundled class comparison (results/compare): a build for every class and an index that lists
them in DPS order with the numbers their build.json files hold."""
import json
import re
from pathlib import Path

from aion2calc.__main__ import compare_markdown

ROOT = Path(__file__).resolve().parents[1] / "results" / "compare"
CLASSES = {"gladiator", "templar", "assassin", "chanter", "sorcerer", "ranger", "spiritmaster", "cleric"}


def test_every_class_has_a_bundled_build_and_the_index_lists_them_in_order():
    summaries = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in ROOT.glob("*/build.json")}
    assert set(summaries) == CLASSES
    listed = re.findall(r"^\| (\w+) \| ([\d,]+) \|", (ROOT / "README.md").read_text(encoding="utf-8"), re.M)
    assert [c for c, _ in listed] == sorted(CLASSES, key=lambda c: -summaries[c]["dps"]["boss"])
    for cls, dps in listed:
        assert dps == f"{summaries[cls]['dps']['boss']:,.0f}"


def test_the_index_explains_the_healers_heals_only_when_they_are_listed():
    rows = [("sorcerer", 20000.0, 18000.0, 0.8), ("cleric", 16000.0, 12000.0, None), ("chanter", 13000.0, 11000.0, 0.4)]
    md = compare_markdown(rows, "boss", 2)
    assert "2 optimizer iterations" in md and "| cleric | 16,000 | 12,000 | +33.3% | — |" in md
    for note in ("The Cleric's boss number includes its heals", "The Chanter's boss number includes its heals"):
        assert note in md and note not in compare_markdown(rows[:1], "boss", 1)
