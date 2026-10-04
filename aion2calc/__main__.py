"""Command line entry point: ``python -m aion2calc <command>``.

Commands
  refresh    re-scrape the sources and rebuild aion2calc/data
  optimize   full build + rotation optimization for a class, writes a report folder
  simulate   simulate the community (most common) build or a saved build.json
  compare    optimize several classes with the same settings and rank them
  diff       compare two result folders (e.g. median vs geared loadout)
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

    s = sub.add_parser("simulate", help="simulate a build")
    s.add_argument("cls")
    s.add_argument("--build", help="build.json written by optimize (default: community build)")
    s.add_argument("--scenario", default="boss", choices=["boss", "dummy"])
    s.add_argument("--loadout")

    c = sub.add_parser("compare", help="optimize several classes and rank DPS")
    c.add_argument("classes", nargs="+")
    c.add_argument("--scenario", default="boss", choices=["boss", "dummy"])
    c.add_argument("--iterations", type=int, default=2)
    c.add_argument("--out", default="results/compare")

    df = sub.add_parser("diff", help="compare two optimize result folders")
    df.add_argument("a", help="result folder A (contains build.json)")
    df.add_argument("b", help="result folder B")
    df.add_argument("--out", help="output Markdown file (default <b>/DIFF.md)")

    args = p.parse_args(argv)
    if args.cmd == "refresh":
        from .scrape.refresh import refresh
        refresh(only=args.only, skip_kr=args.skip_kr, items_only=args.items_only)
    elif args.cmd == "optimize":
        from .report import run_report
        run_report(args.cls, args.out or f"results/{args.cls}_l45", scenario_name=args.scenario,
                   daev_budget=args.daevanion, iterations=args.iterations, loadout=args.loadout)
    elif args.cmd == "simulate":
        from .kit.base import Build
        from .run import simulate
        from .scenarios import SCENARIOS, community_build
        scen = SCENARIOS[args.scenario](args.loadout or f"{args.cls}_l45_global_median")
        if args.build:
            data = json.load(open(args.build))
            from .kit.base import ClassData
            cd = ClassData(args.cls)
            b = Build(args.cls)
            byname = cd.by_name
            b.sp = {byname[k]["id"]: v for k, v in data["build"]["sp"].items()}
            b.stigmas = {byname[k]["id"]: v for k, v in data["build"]["stigmas"].items()}
            b.specs = {byname[k]["id"]: tuple(x["id"] for x in byname[k]["specs"] if x["text"] in v)
                       for k, v in data["build"]["specs"].items()}
            b.daevanion = set(data["build"]["daevanion_nodes"])
            policy = [e.split(" [")[0] if " [" not in e else (e.split(" [")[0], e.split(" [")[1][:-1])
                      for e in data["policy"]]
            from .opt.rotation import materialize
            res = simulate(b, scen, policy=materialize(policy))
        else:
            res = simulate(community_build(args.cls), scen)
        print(f"DPS {res.dps:,.0f}")
        for k, v in res.shares().items():
            print(f"  {k:32s} {100 * v:5.1f}%")
    elif args.cmd == "diff":
        from .diff import write_diff
        print(write_diff(args.a, args.b, args.out))
    elif args.cmd == "compare":
        from .report import run_report
        rows = []
        for cls in args.classes:
            summ = run_report(cls, f"{args.out}/{cls}", scenario_name=args.scenario,
                              iterations=args.iterations)
            rows.append((cls, summ["dps"][args.scenario], summ["baseline"]["community_optimized_rotation"]))
        rows.sort(key=lambda r: -r[1])
        print(f"{'class':14s} {'optimized':>12s} {'community':>12s} {'gain':>7s}")
        md = [f"# Class comparison ({args.scenario}, same settings)\n",
              "| Class | Optimized DPS | Most-common build DPS | Gain | Report |", "|---|---:|---:|---:|---|"]
        for cls, dps, comm in rows:
            print(f"{cls:14s} {dps:12,.0f} {comm:12,.0f} {100 * (dps / comm - 1):6.1f}%")
            md.append(f"| {cls} | {dps:,.0f} | {comm:,.0f} | {100 * (dps / comm - 1):+.1f}% | [{cls}]({cls}/README.md) |")
        from pathlib import Path
        Path(args.out, "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
