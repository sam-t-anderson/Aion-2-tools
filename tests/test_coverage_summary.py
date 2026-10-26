"""The coverage summary CI writes after the tests (tools/coverage_summary.py): the total against main's last
successful run, the modules whose coverage fell or that are new, and one annotation line for the checks.
A fall is a warning naming the modules; an unchanged or higher total is a notice."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("coverage_summary", ROOT / "tools" / "coverage_summary.py")
summary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(summary)


def run(**percents):
    files = {f"aion2calc/{name}.py": {"statements": 200, "missed": int(200 - 2 * pct), "percent": pct}
             for name, pct in percents.items()}
    covered = sum(f["statements"] - f["missed"] for f in files.values())
    statements = sum(f["statements"] for f in files.values())
    return {"total": round(100 * covered / statements, 2), "statements": statements, "covered": covered, "files": files}


def test_a_fall_names_the_modules_that_fell():
    markdown, annotation = summary.summarize(run(meter=60, report=90, cards=50), run(meter=80, report=90))
    assert markdown.startswith("### Python test coverage: 66.7%\n\n400 of 600 statements run under the tests "
                               "(main: 85.0%, -18.3 points).")
    assert "| aion2calc/meter.py | 80.0% | 60.0% |" in markdown and "| aion2calc/report.py | 90.0% |" not in markdown
    assert "#### Modules new since main" in markdown and "| aion2calc/cards.py | 200 | 50.0% |" in markdown
    assert "<details><summary>Every module</summary>" in markdown and "| aion2calc/report.py | 200 | 20 | 90.0% |" in markdown
    assert annotation == ("::warning title=Python coverage fell::66.7% of statements (-18.3 points); "
                          "lower in aion2calc/meter.py (80.0% to 60.0%)")


def test_a_rise_or_no_baseline_is_a_notice():
    markdown, annotation = summary.summarize(run(meter=90), run(meter=80))
    assert "Modules whose coverage fell" not in markdown
    assert annotation == "::notice title=Python coverage::90.0% of statements (main: 80.0%, +10.0 points)"
    markdown, annotation = summary.summarize(run(meter=90.04), run(meter=90.1))     # rounding, not a fall
    assert "Modules whose coverage fell" not in markdown and annotation.startswith("::notice")
    markdown, annotation = summary.summarize(run(meter=90), None)
    assert "No coverage from main to compare with." in markdown and annotation == "::notice title=Python coverage::90.0% of statements"


def test_an_unreadable_baseline_is_no_baseline(tmp_path):
    assert summary.load_baseline(None) is None and summary.load_baseline(str(tmp_path / "missing.json")) is None
    (tmp_path / "bad.json").write_text("{\"total\": \"n/a\"}", encoding="utf-8")
    assert summary.load_baseline(str(tmp_path / "bad.json")) is None
    (tmp_path / "good.json").write_text(json.dumps(run(meter=80)), encoding="utf-8")
    assert summary.load_baseline(str(tmp_path / "good.json"))["total"] == 80
