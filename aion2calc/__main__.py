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
  analyze    break down a combat log (AbyssLogs or A2DIL link, JSON or CSV) and compare it with the optimum
  logs       show (or open) the folder where every analyzed combat log is saved
  advise     gear / arcana / pantheon / genus / rotation advice for a character, ranked by DPS gain
  inventory  list or edit the items the gear planner may equip
  learn      refit the model calibration from your saved fights
  share      upload a saved fight to a log server (open a2log format) and print its link
  app        start the local planner / analyzer app in the browser
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    chp.add_argument("--out", help="output folder (default <user folder>/results/characters/<name>_<server>)")

    an = sub.add_parser("analyze", help="analyze a combat log and keep it in the encounter history")
    an.add_argument("log", help="AbyssLogs link (abysslogs.com/e/<id>), A2DIL record URL/id, "
                                "or a .json / .json.gz / .csv log file")
    an.add_argument("--player", help="whose damage to analyze in a party log (default: who recorded it)")
    an.add_argument("--no-save", action="store_true", help="do not store it in the encounter history")

    ad = sub.add_parser("advise", help="gear, arcana, pantheon, genus and rotation advice for a character")
    ad.add_argument("name")
    ad.add_argument("--region", default="nae", choices=["nae", "eu", "as", "la"])
    ad.add_argument("--server", help="server name or id when several characters match")
    ad.add_argument("--out", help="output folder (default <user folder>/results/characters/<name>_<server>)")

    iv = sub.add_parser("inventory", help="list or edit the items the gear planner may equip")
    iv.add_argument("name")
    iv.add_argument("--region", default="nae", choices=["nae", "eu", "as", "la"])
    iv.add_argument("--server")
    iv.add_argument("--add", metavar="ITEM", help="catalog item id (slug), e.g. aulamus-ring")
    iv.add_argument("--enchant", type=int, default=0)
    iv.add_argument("--skill", action="append", default=[], metavar="NAME=LEVELS",
                    help="skill option on the item (repeatable), e.g. Hellfire=2")
    iv.add_argument("--remove", metavar="ID")

    sh = sub.add_parser("share", help="upload a saved fight to a log server (a2log) and print its link")
    sh.add_argument("encounter", nargs="?", type=int, help="encounter id (see the Combat Logs page or `logs`)")
    sh.add_argument("--server", help="log server URL; saved for next time")
    sh.add_argument("--key", help="upload key; saved for next time")
    sh.add_argument("--visibility", choices=["public", "unlisted", "private"])
    sh.add_argument("--export", metavar="FILE", help="write the a2log JSON to FILE instead of uploading")

    le = sub.add_parser("learn", help="refit the model calibration from your saved fights")
    le.add_argument("cls", nargs="?", help="class (default: every class with fights)")

    lg = sub.add_parser("logs", help="show the combat logs folder (one file per analyzed log)")
    lg.add_argument("--open", action="store_true", help="open the folder in Explorer / Finder")

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
            from .paths import results_dir
            out = args.out or str(results_dir() / "characters" / imp.loadout_name()[5:])
            summ = optimize_character(imp, out, iterations=args.iterations)
            print(json.dumps(summ, indent=1))
            print("report:", Path(out) / "README.md", "· diff:", Path(out) / "DIFF.md")
        else:
            cur = evaluate_current(imp)
            print(json.dumps({"dps": cur["dps"], "budgets": cur["budgets"], "build": cur["build"]["sp"]},
                             indent=1))
    elif args.cmd == "analyze":
        from .combat.adapters import load
        from .combat.analyze import analyze, vs_optimal
        enc = load(args.log, player=args.player)
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
            from . import learn
            from .combat.logs import save
            eid, path = save(enc)
            print(f"saved as encounter {eid}: {path}")
            try:
                cal = learn.update(eid)
                if cal:
                    print("calibration:", "; ".join(learn.summary(cal)))
            except Exception as err:
                print("not used for calibration:", err)
    elif args.cmd in ("advise", "inventory"):
        from .charopt import find, import_character
        from .plan import inventory as INV
        hits = find(args.name, args.region, args.server)
        if not hits:
            print("no character found")
            return 1
        h = hits[0]
        imp = import_character(h["character_id"], h["server_id"], h["region"], use_cache=3600,
                               progress=lambda m: print("  ..", m))
        inv = INV.from_character(imp)
        if args.cmd == "inventory":
            if args.add:
                skills = [[x.split("=")[0], int(x.split("=")[1]) if "=" in x else 1] for x in args.skill]
                e = INV.add(inv, args.add, args.enchant, skills=skills)
                print("added", e["id"], e["name"], f"+{e['enchant']}")
            if args.remove:
                print("removed" if INV.remove(inv, args.remove) else "no such entry", args.remove)
            print("inventory file:", INV.save(inv))
            for e in inv["items"]:
                print(f"  {e['id']:12s} {e.get('slot') or e.get('category') or '':18s} {e['name']} +{e.get('enchant', 0)}"
                      + (f"  skills {e['skills']}" if e.get("skills") else "") + f"  [{e['source']}]")
        else:
            from .paths import results_dir
            from .plan.advisor import advise, write_markdown
            adv = advise(imp, inv, progress=lambda m: print("  ..", m))
            out = Path(args.out) if args.out else results_dir() / "characters" / imp.loadout_name()[5:]
            p = write_markdown(adv, out)
            for r in adv["top"][:12]:
                g = "" if r["gain"] is None else f"{100 * r['gain']:+.1f}%"
                print(f"  {r['area']:18s} {g:>7s}  {r['text']}")
            print("advice:", p)
    elif args.cmd == "share":
        from .combat import share
        if args.server or args.key or (args.visibility and args.encounter is None):
            share.save_settings(args.server, args.key, args.visibility)
            print("log server settings saved")
        if args.encounter is not None:
            if args.export:
                from .db import store
                from .combat.a2log import from_encounter
                enc = store.encounter(store.connect(), args.encounter)
                Path(args.export).write_text(json.dumps(from_encounter(enc), indent=1), encoding="utf-8")
                print("wrote", args.export)
            else:
                r = share.share_encounter(args.encounter, visibility=args.visibility)
                print(r["url"])
                print("delete link:", r.get("delete_url"))
    elif args.cmd == "learn":
        from . import learn
        from .db import store
        conn = store.connect()
        classes = [args.cls] if args.cls else sorted({e["class_name"] for e in store.encounters(conn) if e["class_name"]})
        for e in store.encounters(conn):
            if e["class_name"] in classes:
                learn.observe(e["id"], conn)
        for c in classes:
            print(c + ":", "; ".join(learn.summary(learn.fit(c, conn))))
    elif args.cmd == "logs":
        from .combat.logs import backfill, open_folder
        from .paths import home, logs_dir
        n = backfill()
        print(f"data folder:  {home()}")
        print(f"combat logs:  {logs_dir()}  ({len(list(logs_dir().glob('*.json')))} files"
              + (f", {n} written now" if n else "") + ")")
        if args.open:
            open_folder()
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
