"""Report the test run's Python coverage, against main's last successful CI run, so a drop shows on the
pull request that caused it.

Run after `python -m coverage run -m pytest`. It
  - prints one annotation line that GitHub shows with the job's checks: a notice with the total, or a
    warning naming the modules whose coverage fell;
  - writes the total, the modules that fell or are new since main, and every module's figures as Markdown
    to $GITHUB_STEP_SUMMARY (to stdout outside CI);
  - saves this run's figures to --out, for later runs to compare with.

    python tools/coverage_summary.py [--baseline coverage-main/coverage-total.json] [--out coverage-total.json]

A missing or unreadable baseline is not an error: the summary then shows this run's figures alone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

FELL = 0.1          # points; smaller differences are rounding between runs


def measure() -> dict:
    """This run's figures: the total and each module's percentage, from the .coverage data file."""
    import coverage
    cov = coverage.Coverage()
    cov.load()
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "coverage.json"
        cov.json_report(outfile=str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
    files = {path: {"statements": f["summary"]["num_statements"], "missed": f["summary"]["missing_lines"],
                    "percent": round(f["summary"]["percent_covered"], 2)}
             for path, f in report["files"].items()}
    totals = report["totals"]
    return {"total": round(totals["percent_covered"], 2), "statements": totals["num_statements"],
            "covered": totals["covered_lines"], "files": files}


def load_baseline(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        baseline = json.loads(Path(path).read_text(encoding="utf-8"))
        float(baseline["total"])
        return baseline if isinstance(baseline.get("files"), dict) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def summarize(run: dict, baseline: dict | None) -> tuple[str, str]:
    """The Markdown summary and the annotation line for ``run``, compared with ``baseline`` when there is one."""
    total = f"{run['total']:.1f}%"
    lines = [f"### Python test coverage: {total}", "",
             f"{run['covered']:,} of {run['statements']:,} statements run under the tests"]
    fell, new = [], []
    if baseline:
        delta = run["total"] - float(baseline["total"])
        lines[-1] += f" (main: {float(baseline['total']):.1f}%, {delta:+.1f} points)."
        before = baseline["files"]
        for path, row in run["files"].items():
            if path not in before:
                new.append((path, row))
            elif row["percent"] < before[path]["percent"] - FELL:
                fell.append((before[path]["percent"] - row["percent"], path, row))
        fell.sort(key=lambda item: (-item[0], item[1]))
    else:
        delta = None
        lines[-1] += ". No coverage from main to compare with."
    if fell:
        lines += ["", "#### Modules whose coverage fell", "", "| Module | main | now |", "|---|---:|---:|"]
        lines += [f"| {path} | {baseline['files'][path]['percent']:.1f}% | {row['percent']:.1f}% |" for _, path, row in fell]
    if new:
        lines += ["", "#### Modules new since main", "", "| Module | Statements | Coverage |", "|---|---:|---:|"]
        lines += [f"| {path} | {row['statements']:,} | {row['percent']:.1f}% |" for path, row in sorted(new)]
    lines += ["", "<details><summary>Every module</summary>", "", "| Module | Statements | Missed | Coverage |",
              "|---|---:|---:|---:|"]
    lines += [f"| {path} | {row['statements']:,} | {row['missed']:,} | {row['percent']:.1f}% |"
              for path, row in sorted(run["files"].items())]
    lines += ["", "</details>", ""]
    if fell:
        names = ", ".join(f"{path} ({baseline['files'][path]['percent']:.1f}% to {row['percent']:.1f}%)"
                          for _, path, row in fell[:3]) + (f" and {len(fell) - 3} more" if len(fell) > 3 else "")
        annotation = f"::warning title=Python coverage fell::{total} of statements ({delta:+.1f} points); lower in {names}"
    else:
        annotation = f"::notice title=Python coverage::{total} of statements" + (
            "" if delta is None else f" (main: {float(baseline['total']):.1f}%, {delta:+.1f} points)")
    return "\n".join(lines), annotation


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", help="coverage-total.json saved by main's last successful run")
    parser.add_argument("--out", default="coverage-total.json", help="where to save this run's figures")
    args = parser.parse_args(argv)
    run = measure()
    markdown, annotation = summarize(run, load_baseline(args.baseline))
    Path(args.out).write_text(json.dumps({"total": run["total"], "statements": run["statements"],
                                          "files": run["files"]}, indent=1), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    else:
        print(markdown)
    print(annotation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
