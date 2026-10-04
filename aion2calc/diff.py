"""Compare two optimized result folders (``build.json``) and write a Markdown diff.

    python -m aion2calc diff results/sorcerer_l45 results/sorcerer_l45_geared

Works for two loadouts of one class, two Daevanion budgets, or two classes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _load(d: str) -> dict:
    return json.loads((Path(d) / "build.json").read_text(encoding="utf-8"))


def _label(s: dict, d: str) -> str:
    return f"{s['class'].capitalize()} · {s.get('loadout', Path(d).name)}"


def write_diff(a_dir: str, b_dir: str, out: str | None = None) -> str:
    a, b = _load(a_dir), _load(b_dir)
    la, lb = _label(a, a_dir), _label(b, b_dir)
    out = out or str(Path(b_dir) / "DIFF.md")
    rel = lambda d: os.path.relpath(Path(d) / "images", Path(out).parent)  # noqa: E731
    L: list[str] = []
    w = L.append
    w(f"# {la}  vs  {lb}\n")
    w("| | A | B | B vs A |")
    w("|---|---:|---:|---:|")
    for k in a["dps"]:
        if k in b["dps"]:
            w(f"| {k} DPS | {a['dps'][k]:,.0f} | {b['dps'][k]:,.0f} | {100 * (b['dps'][k] / a['dps'][k] - 1):+.1f}% |")
    for key, label, pct in [("crit_chance_vs_target", "Crit chance", True), ("cdr", "Cooldown reduction", True),
                            ("combat_speed", "Combat Speed", True), ("attack_avg", "Attack (avg)", False),
                            ("boost_bucket", "Damage Boost bucket", True)]:
        x, y = a["stats"].get(key), b["stats"].get(key)
        if x is None or y is None:
            continue
        f = (lambda v: f"{100 * v:.1f}%") if pct else (lambda v: f"{v:,.0f}")
        w(f"| {label} | {f(x)} | {f(y)} | |")
    w("")

    if a["class"] == b["class"]:
        ba, bb = a["build"], b["build"]
        w("## Build changes\n")
        rows = []
        for n in sorted(set(ba["sp"]) | set(bb["sp"])):
            if ba["sp"].get(n, 1) != bb["sp"].get(n, 1):
                rows.append(f"| {n} | SP level | {ba['sp'].get(n, 1)} | {bb['sp'].get(n, 1)} |")
        for n in sorted(set(ba["effective_levels"]) | set(bb["effective_levels"])):
            x, y = ba["effective_levels"].get(n, 1), bb["effective_levels"].get(n, 1)
            if x != y:
                rows.append(f"| {n} | effective level | {x} | {y} |")
        for n in sorted(set(ba["specs"]) | set(bb["specs"])):
            x, y = ba["specs"].get(n, []), bb["specs"].get(n, [])
            if x != y:
                rows.append(f"| {n} | specializations | {'; '.join(x) or '—'} | {'; '.join(y) or '—'} |")
        for n in sorted(set(ba["stigmas"]) | set(bb["stigmas"])):
            x, y = ba["stigmas"].get(n), bb["stigmas"].get(n)
            if x != y:
                rows.append(f"| {n} | stigma level | {x or '—'} | {y or '—'} |")
        if rows:
            w("| Skill | What | A | B |")
            w("|---|---|---|---|")
            L.extend(rows)
        else:
            w("Same skill points, specializations and stigmas.")
        na, nb = set(ba["daevanion_nodes"]), set(bb["daevanion_nodes"])
        w(f"\nDaevanion: {len(na & nb)} nodes shared, {len(na - nb)} only in A, {len(nb - na)} only in B.\n")

    w("## Daevanion boards\n")
    w(f"A:\n\n![A]({rel(a_dir)}/daevanion_optimized.png)\n")
    w(f"B:\n\n![B]({rel(b_dir)}/daevanion_optimized.png)\n")

    w("## Rotation\n")
    w("| # | A | B |")
    w("|---:|---|---|")
    for i in range(max(len(a["policy"]), len(b["policy"]))):
        x = a["policy"][i] if i < len(a["policy"]) else ""
        y = b["policy"][i] if i < len(b["policy"]) else ""
        w(f"| {i + 1} | `{x}` | `{y}` |" if x and y else f"| {i + 1} | {f'`{x}`' if x else ''} | {f'`{y}`' if y else ''} |")
    w("")

    w("## Stat weights (DPS gain per step)\n")
    wa = {x["label"]: x["pct"] for x in a["weights"]}
    wb = {x["label"]: x["pct"] for x in b["weights"]}
    w("| Upgrade | A | B |")
    w("|---|---:|---:|")
    for k in sorted(set(wa) | set(wb), key=lambda k: -max(wa.get(k, 0), wb.get(k, 0))):
        w(f"| {k} | {wa.get(k, 0):+.2f}% | {wb.get(k, 0):+.2f}% |")
    w("")

    w("## Damage shares\n")
    w("| Source | A | B |")
    w("|---|---:|---:|")
    sa, sb = a.get("shares", {}), b.get("shares", {})
    for k in sorted(set(sa) | set(sb), key=lambda k: -max(sa.get(k, 0), sb.get(k, 0)))[:16]:
        w(f"| {k} | {100 * sa.get(k, 0):.1f}% | {100 * sb.get(k, 0):.1f}% |")
    Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")
    return out
