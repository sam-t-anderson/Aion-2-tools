"""Command line entry point: ``python -m aion2calc <command>``.

Commands
  refresh    re-scrape the sources and rebuild aion2calc/data
  optimize   full build + rotation optimization for a class, writes a report folder
  simulate   simulate the typical top global build or a saved build.json
  compare    optimize several classes with the same settings and rank them
  diff       compare two result folders (e.g. median vs geared loadout)
  render     rewrite a result folder's README.md from its build.json
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aion2calc", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refresh", help="re-scrape sources and rebuild aion2calc/data")
    r.add_argument("--only", help="a single class key, e.g. sorcerer")
    r.add_argument("--skip-kr", action="store_true", help="skip gamers4.life / A2DIL")
    r.add_argument("--items-only", action="store_true", help="only items and titles")

    o = sub.add_parser("optimize", help="optimize build + rotation and write a report")
    o.add_argument("cls", help="class key: gladiator templar assassin ranger sorcerer spiritmaster cleric chanter")
    o.add_argument("--out", help="output folder (default results/<cls>_l45)")
    o.add_argument("--scenario", default="boss", choices=["boss", "dummy"])
    o.add_argument("--daevanion", type=int, default=360, help="Daevanion Crystal points (global launch: 360)")
    o.add_argument("--iterations", type=int, default=3)
    o.add_argument("--loadout", help="loadout file name in data/global/loadouts")
    o.add_argument("--crit-midpoint", type=float,
                   help="Crit value with ~52%% crit chance (default 1024.5, the measured fit); lower it if "
                        "launch testing shows more crit at your Crit value")

    s = sub.add_parser("simulate", help="simulate a build")
    s.add_argument("cls")
    s.add_argument("--build", help="build.json written by optimize (default: community build)")
    s.add_argument("--scenario", default="boss", choices=["boss", "dummy"])
    s.add_argument("--loadout")
    s.add_argument("--crit-midpoint", type=float)

    c = sub.add_parser("compare", help="optimize several classes and rank DPS")
    c.add_argument("classes", nargs="+")
    c.add_argument("--scenario", default="boss", choices=["boss", "dummy"])
    c.add_argument("--iterations", type=int, default=2)
    c.add_argument("--out", default="results/compare")
    c.add_argument("--crit-midpoint", type=float)

    df = sub.add_parser("diff", help="compare two optimize result folders")
    df.add_argument("a", help="result folder A (contains build.json)")
    df.add_argument("b", help="result folder B")
    df.add_argument("--out", help="output Markdown file (default <b>/DIFF.md)")

    rr = sub.add_parser("render", help="rewrite README.md of a result folder from build.json")
    rr.add_argument("dir")

    args = p.parse_args(argv)
    if getattr(args, "crit_midpoint", None):
        from .model.stats import set_crit_midpoint
        set_crit_midpoint(args.crit_midpoint)
    if args.cmd == "refresh":
        from .scrape.refresh import refresh
        refresh(only=args.only, skip_kr=args.skip_kr, items_only=args.items_only)
    elif args.cmd == "optimize":
        from .report import run_report
        run_report(args.cls, args.out or f"results/{args.cls}_l45", scenario_name=args.scenario,
                   daev_budget=args.daevanion, iterations=args.iterations, loadout=args.loadout)
    elif args.cmd == "simulate":
        from .run import simulate
        from .scenarios import SCENARIOS, typical_build
        scen = SCENARIOS[args.scenario](args.loadout or f"{args.cls}_l45_global_median")
        if args.build:
            from .opt.rotation import materialize
            from .report import build_from_summary
            b, policy = build_from_summary(json.load(open(args.build)))
            res = simulate(b, scen, policy=materialize(policy))
        else:
            res = simulate(typical_build(args.cls), scen)
        print(f"DPS {res.dps:,.0f}")
        for k, v in res.shares().items():
            print(f"  {k:32s} {100 * v:5.1f}%")
    elif args.cmd == "render":
        from .report import rerender
        print(rerender(args.dir))
    elif args.cmd == "diff":
        from .diff import write_diff
        print(write_diff(args.a, args.b, args.out))
    elif args.cmd == "compare":
        from .report import run_report
        rows = []
        for cls in args.classes:
            summ = run_report(cls, f"{args.out}/{cls}", scenario_name=args.scenario,
                              iterations=args.iterations)
            rows.append((cls, summ["dps"][args.scenario], summ["baseline"]["community_optimized_rotation"],
                         (summ.get("kr_fidelity") or {}).get("overlap")))
        rows.sort(key=lambda r: -r[1])
        print(f"{'class':14s} {'optimized':>12s} {'community':>12s} {'gain':>7s}")
        md = [f"# Class comparison ({args.scenario}, same settings, {args.iterations} optimizer "
              f"iteration{'s' if args.iterations != 1 else ''} per class)\n",
              "Each class is optimized with the same budgets (203 SP, 30 stigma points, 360 Daevanion) on its own "
              "median global loadout. **Gain** (optimized vs the typical top global build of that class, same "
              "rotation optimizer) is the reliable number. Absolute DPS across classes is only as good as each class "
              "kit: Sorcerer has a hand-written kit; the others use the generic tooltip-driven kit, whose fidelity "
              "is shown as the share overlap with Korean A2DIL dummy logs.\n",
              "| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |",
              "|---|---:|---:|---:|---:|---|"]
        for cls, dps, comm, fid in rows:
            print(f"{cls:14s} {dps:12,.0f} {comm:12,.0f} {100 * (dps / comm - 1):6.1f}%")
            md.append(f"| {cls} | {dps:,.0f} | {comm:,.0f} | {100 * (dps / comm - 1):+.1f}% | "
                      f"{'—' if fid is None else f'{100 * fid:.0f}%'} | [{cls}]({cls}/README.md) |")
        from pathlib import Path
        Path(args.out, "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
