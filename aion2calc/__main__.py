"""Command line entry point: ``python -m aion2calc <command>``.

Commands
  refresh    re-scrape the sources and rebuild aion2calc/data
  optimize   full build + rotation optimization for a class, writes a report folder
  simulate   simulate the typical top global build or a saved build.json
  compare    optimize several classes with the same settings and rank them
  diff       compare two result folders (e.g. median vs geared loadout)
  render     rewrite a result folder's README.md from its build.json
  sync       update the local game database (new items, skills, classes)
  character  import a character from the official site, score it, optimize it
  analyze    break down a combat log (A2DIL link, JSON or CSV) and compare it with the optimum
  app        start the local planner / analyzer app in the browser
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
    o.add_argument("--skill-points", type=int,
                   help="skill point budget (default: 203 from levels; ~383 with every Empyrean Trace)")
    o.add_argument("--stigma-points", type=int, help="stigma point budget (default 30)")
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

    sy = sub.add_parser("sync", help="update the local game database from the live sources")
    sy.add_argument("--force", action="store_true", help="re-read every page, not only changed ones")
    sy.add_argument("--budget", type=float, help="stop after this many seconds (resumes next run)")
    sy.add_argument("--export-seed", action="store_true", help="also write the bundled seed catalog")

    chp = sub.add_parser("character", help="import a character from the official AION 2 site")
    chp.add_argument("name")
    chp.add_argument("--region", default="nae", help="global region: nae, eu, as, la")
    chp.add_argument("--server", help="server name or id when several characters share the name")
    chp.add_argument("--optimize", action="store_true", help="also optimize it under the same resources")
    chp.add_argument("--iterations", type=int, default=2)
    chp.add_argument("--out", help="output folder (default results/characters/<name>_<server>)")

    an = sub.add_parser("analyze", help="analyze a combat log and keep it in the encounter history")
    an.add_argument("log", help="A2DIL record URL/id, or a .json/.csv log file")
    an.add_argument("--no-save", action="store_true", help="do not store it in the encounter history")

    rr = sub.add_parser("render", help="rewrite README.md of a result folder from build.json")
    rr.add_argument("dir")

    ap = sub.add_parser("app", help="start the local app (planner, character import, combat analyzer)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="skip the launch-time database update")

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
                   daev_budget=args.daevanion, iterations=args.iterations, loadout=args.loadout,
                   sp_budget=args.skill_points, stigma_points=args.stigma_points)
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
    elif args.cmd == "sync":
        from .db import store
        from .db.sync import Sync, status
        st = Sync(force=args.force, budget_s=args.budget, log=print).run()
        print(json.dumps({k: v for k, v in st.as_dict().items() if k in ("phase", "changed", "errors")},
                         indent=1)[:4000])
        if args.export_seed:
            print("seed items:", store.export_seed(store.connect()))
        print(json.dumps(status(), indent=1)[:1500])
    elif args.cmd == "character":
        from .charopt import evaluate_current, find, import_character, optimize_character
        hits = find(args.name, args.region, args.server)
        if not hits:
            print("no character found")
            return 1
        if len(hits) > 1 and args.server is None:
            print("several matches; pass --server:")
            for h in hits[:15]:
                print(f"  {h['name']:16s} Lv {h['level']:2d}  {h['server']} ({h['server_id']})")
        h = hits[0]
        imp = import_character(h["character_id"], h["server_id"], h["region"], progress=lambda m: print("  ..", m))
        print(f"{imp.name} ({imp.server}) {imp.cls} Lv {imp.level}  CP {imp.combat_power}")
        for w in imp.warnings:
            print("  note:", w)
        if args.optimize:
            out = args.out or f"results/characters/{imp.loadout_name()[5:]}"
            summ = optimize_character(imp, out, iterations=args.iterations)
            print(json.dumps(summ, indent=1))
            print("report:", out + "/README.md", "· diff:", out + "/DIFF.md")
        else:
            cur = evaluate_current(imp)
            print(json.dumps({"dps": cur["dps"], "budgets": cur["budgets"], "build": cur["build"]["sp"]},
                             indent=1))
    elif args.cmd == "analyze":
        from .combat.adapters import load
        from .combat.analyze import analyze, vs_optimal
        enc = load(args.log)
        a = analyze(enc)
        sm = a["summary"]
        print(f"{enc['meta'].get('class')}  {sm['duration']:.0f}s  DPS {sm['dps']:,.0f}  casts/min {sm['cpm']:.0f}  "
              f"crit {100 * sm['crit']:.0f}%  double {100 * sm['double']:.0f}%  perfect {100 * sm['perfect']:.0f}%  "
              f"idle {sm['idle_seconds']:.1f}s")
        for r in a["skills"][:14]:
            use = f"{100 * r['cooldown_use']:.0f}%" if r["cooldown_use"] is not None else "-"
            print(f"  {r['skill'][:24]:24s} {100 * r['share']:5.1f}%  casts {r['casts']:3d}  "
                  f"crit {100 * r['crit']:3.0f}%  avg {r['avg_hit']:12,.0f}  cd use {use}")
        o = vs_optimal(enc)
        if "error" not in o:
            print(f"share overlap with the optimal rotation: {100 * o['share_overlap']:.0f}%")
            for t in o["tips"]:
                print("  tip:", t)
        if not args.no_save:
            from .db import store
            print("saved as encounter", store.put_encounter(store.connect(), enc))
    elif args.cmd == "render":
        from .report import rerender
        print(rerender(args.dir))
    elif args.cmd == "app":
        from .app.server import serve
        serve(port=args.port, open_browser=not args.no_browser, sync=not args.no_sync)
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
              "is shown as the share overlap with Korean A2DIL dummy logs. **This is not a class tier "
              "list**: below ~60% overlap the kit is missing class mechanics, and its absolute DPS can be far off "
              "in either direction.\n",
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
