"""Command line entry point: ``python -m aion2calc <command>``.

Commands
  catalog-refresh  stage pinned enemy/dungeon tables and an audit for release review
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


def _load_local_docs(paths, on_skip=print):
    """Load a2log JSON documents from the given files and folders.

    Each path is a file, or a folder whose ``*.json`` files are each loaded.
    A file that is missing or not valid JSON is skipped with a note, never
    fatal, so one bad file does not lose the rest of a corpus."""
    docs = []
    for path in paths:
        p = Path(path)
        files = sorted(f for f in p.glob("*.json")) if p.is_dir() else [p]
        for f in files:
            try:
                docs.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                on_skip(f"skipped {f}: {e}")
    return docs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aion2calc", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refresh", help="re-scrape sources and rebuild aion2calc/data")
    r.add_argument("--only", help="a single class key, e.g. sorcerer")
    r.add_argument("--skip-kr", action="store_true", help="skip gamers4.life / A2DIL")
    r.add_argument("--items-only", action="store_true", help="only items and titles")

    cat = sub.add_parser("catalog-refresh", help="stage pinned NPC/dungeon tables and a review diff")
    cat.add_argument("--revision", required=True, help="full upstream commit SHA (40 lowercase hex characters)")
    cat.add_argument("--out", required=True, help="new staging directory; does not replace installed tables")

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

    cb = sub.add_parser("calibrate", help="check kit fidelity against real logs (KR aggregate or a capture) "
                                          "and suggest tuned TIMING/ASSUME knobs")
    cb.add_argument("cls", nargs="?", help="class key (default: every class, worst fidelity first)")
    cb.add_argument("--capture", metavar="LOG", help="compare to a real A2Parser capture / saved .a2log.json, "
                                                     "A2DIL record or AbyssLogs reference instead of the KR aggregate")
    cb.add_argument("--player", help="whose damage to read in a party capture (default: the recording player)")
    cb.add_argument("--tune", action="store_true", help="also suggest bounded TIMING/ASSUME values that raise the "
                                                        "share overlap (reported only; kits are not modified)")
    cb.add_argument("--timings", action="store_true", help="with --capture: measure per-skill cast cadence and pet "
                                                           "swing periods from the capture and compare to the kit")

    iv2 = sub.add_parser("install-version", help="show each detected game install's version signals and, with "
                                                 "two or more (e.g. Steam and PURPLE), which signal is the shared "
                                                 "launcher-independent game version")
    iv2.add_argument("--json", action="store_true", help="print the raw evidence and comparison as JSON")
    iv2.add_argument("--add-path", metavar="FOLDER", help="add a game install folder by hand (for a copy auto-detection "
                                                         "misses) and select it; must contain AION2.exe or Content/Paks")
    iv2.add_argument("--remove-path", metavar="FOLDER", help="remove a previously added manual install folder")

    ne = sub.add_parser("npc-evidence", help="aggregate the NPC decoder evidence across uploaded logs: candidate "
                                             "NPC type IDs (named, needs-name, abstained) and identity/packet variants")
    ne.add_argument("logs", nargs="*", help="local a2log JSON files or folders of them; default: fetch public "
                                            "uploads from the log server")
    ne.add_argument("--server", help="log server base URL (default: the configured community server)")
    ne.add_argument("--limit", type=int, default=500, help="max uploads to fetch from the server")
    ne.add_argument("--min-logs", type=int, default=2, help="distinct uploads a code needs before it is promoted")
    ne.add_argument("--min-records", type=int, default=5, help="records a code needs before it is promoted")
    ne.add_argument("--json", action="store_true", help="print the full aggregate, candidates and variants as JSON")

    df2 = sub.add_parser("defeats", help="deduplicate the same boss defeat across uploader perspectives on the "
                                         "log server, so respawn/availability counts are not inflated by duplicates")
    df2.add_argument("logs", nargs="*", help="local a2log JSON files or folders of them; default: fetch public "
                                             "uploads from the log server")
    df2.add_argument("--server", help="log server base URL (default: the configured community server)")
    df2.add_argument("--limit", type=int, default=500, help="max uploads to fetch")
    df2.add_argument("--json", action="store_true", help="print the full grouping as JSON")

    lg = sub.add_parser("logs", help="show the combat logs folder (one file per analyzed log)")
    lg.add_argument("--open", action="store_true", help="open the folder in Explorer / Finder")

    dr = sub.add_parser("doctor", help="operator self-check: install, updater, paths, log server and catalog")
    dr.add_argument("--offline", action="store_true", help="skip network checks (updater and server discovery)")
    dr.add_argument("--json", action="store_true", help="print the full report as JSON")

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
    if args.cmd == "catalog-refresh":
        from .scrape.catalog import stage
        stage(args.revision, args.out)
    elif args.cmd == "refresh":
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
    elif args.cmd == "calibrate":
        from . import calibrate as C
        if args.capture:
            r = C.from_capture(args.capture, player=args.player)
            vs = r["vs_sim"]
            print(f"{r['class']}  {r['duration']:.0f}s  capture DPS {r.get('dps') or 0:,.0f}  "
                  f"sim DPS {vs.get('sim_dps', 0):,.0f}  ({r['source']})")
            if "error" in vs:
                print("  " + vs["error"])
            else:
                print(f"  share overlap with the optimal rotation: {100 * vs['share_overlap']:.0f}%")
                print(f"  {'skill':24s} {'capture':>8s} {'sim':>8s}  casts cap/sim")
                for s in vs["skills"][:14]:
                    print(f"  {s['skill'][:24]:24s} {100 * s['share']:7.1f}% {100 * s['sim_share']:7.1f}%  "
                          f"{s['casts']:4d}/{s['sim_casts']:<4d}")
                if r["vs_top"].get("overlap") is not None:
                    print(f"  overlap with the KR top logs: {100 * r['vs_top']['overlap']:.0f}%")
            if args.timings:
                mt = C.measured_timings(args.capture, player=args.player)
                if "error" in mt:
                    print("\n  " + mt["error"])
                else:
                    kit = mt.get("kit") or {}
                    print(f"\n  measured skill cast cadence (filler: {kit.get('filler') or '?'}, "
                          f"kit action time {kit.get('filler_action_time')}):")
                    for s in mt["skills"][:14]:
                        print(f"    {s['skill'][:24]:24s} casts {s['count']:3d}  min {s['min']:.2f}s  median {s['median']:.2f}s")
                    if mt["pets"]:
                        print("  measured pet swing periods:")
                        for pet in mt["pets"]:
                            print(f"    {str(pet['pet'])[:24]:24s} hits {pet['count']:3d}  swing {pet['swing_period']:.2f}s")
                    else:
                        print("  no pet hits with enough timing in this capture.")
            if args.tune:
                cls, target = C.capture_target(args.capture, player=args.player)
                t = C.tune(cls, target=target)
                print(f"\n  tuned to this capture: overlap {t['overlap_before']:.3f} -> {t['overlap_after']:.3f} "
                      f"(+{t['gain']:.3f})")
                print("  suggested:", json.dumps(t["suggested"]) if t["suggested"] else "no change improves the fit")
        else:
            classes = [args.cls] if args.cls else list(C.CLASSES)
            print(f"{'class':13s} {'overlap':>8s} {'ceiling':>8s} {'fidelity':>9s}  biggest sim-vs-KR share gaps")
            for cls in (sorted(classes, key=lambda c: C.gaps(c)['fidelity']) if not args.cls else classes):
                g = C.gaps(cls)
                tops = "  ".join(f"{x['skill'][:14]} {x['delta']:+.2f}" for x in g["gaps"][:3])
                print(f"{cls:13s} {g['overlap']:8.3f} {g['ceiling']:8.3f} {g['fidelity']:9.3f}  {tops}")
                if args.cls:
                    for x in g["gaps"]:
                        print(f"    {x['skill'][:28]:28s} sim {100 * x['sim']:5.1f}%  KR {100 * x['kr']:5.1f}%  "
                              f"{x['delta']:+.3f}")
                if args.tune:
                    t = C.tune(cls, target=None)
                    print(f"    tune: overlap {t['overlap_before']:.3f} -> {t['overlap_after']:.3f} "
                          f"(+{t['gain']:.3f})  suggested " +
                          (json.dumps(t["suggested"]) if t["suggested"] else "no change"))
            print("\nKR logs run higher-level with skills the global build lacks, so overlap cannot reach 1.0; "
                  "'ceiling' is the reachable maximum and 'fidelity' = overlap / ceiling. Share a capture with "
                  "--capture to calibrate against your own fight.")
    elif args.cmd == "install-version":
        from .meter.builds import compare_installs, resolve, version_signals
        from .meter.metadata import (_build_evidence, _installed_roots, _installation_id, _manual_roots,
                                     purple_launcher_evidence)
        if args.add_path or args.remove_path:
            from .meter.metadata import set_manual_installation
            try:
                set_manual_installation(args.remove_path or args.add_path, remove=bool(args.remove_path))
                print(("Removed" if args.remove_path else "Added and selected") + " manual install: "
                      + (args.remove_path or args.add_path))
            except ValueError as e:
                print(f"error: {e}")
                return 1
        installs = []
        manual_ids = {_installation_id(r) for r in _manual_roots()}
        for root in _installed_roots():
            evidence = _build_evidence(root)
            iid = _installation_id(root)
            launcher = ("Manual" if iid in manual_ids else
                        "Steam" if root.parent.name.casefold() == "common" else
                        "PURPLE" if str(evidence.get("launcher_build_namespace", "")).startswith("purple:") else
                        "Registered Windows install")
            installs.append({**evidence, "launcher": launcher, "root": str(root),
                             "id": iid, **resolve(evidence)})
        purple = purple_launcher_evidence()
        comparison = compare_installs(installs) if len(installs) >= 2 else None
        if args.json:
            print(json.dumps({"installs": installs, "comparison": comparison, "purple_launcher": purple}, indent=1))
            return 0
        if not installs:
            print("No game installation was detected. Detection supports Steam libraries and recognized "
                  "Windows registrations, including PURPLE. Run this on the machine with the game installed.")
            if purple:
                print(f"\nHowever, the PURPLE launcher recorded running AION 2 Global "
                      f"(version {purple['purple_app_core_version']}, build {purple['purple_build_number'] or '?'}) "
                      "on this machine. Its install folder was not located automatically — select it in the app, "
                      "or re-run where the Windows uninstall entry is present.")
            return 0
        for i in installs:
            print(f"\n{i['launcher']} · {i['root']}")
            print(f"  comparison cohort (game_patch): {i.get('game_patch') or 'unavailable'} "
                  f"· {i.get('game_patch_source') or i.get('patch_reason', '')}")
            for s in version_signals(i):
                tag = {True: "same across launchers", False: "launcher-specific", None: "launcher-dependent"}[s["cross_launcher"]]
                print(f"  - {s['label']:30s} {s['value']}  ({tag})")
        if comparison:
            print("\nAcross the detected installs:")
            for r in comparison["signals"]:
                state = ("agrees" if r["agrees"] else "differs" if r["present_in"] == r["total"] else
                         f"only {r['present_in']}/{r['total']} installs")
                print(f"  - {r['label']:30s} {state}" + ("" if r["agrees"] else "  " + " | ".join(r["values"])))
            overlap = comparison.get("content_overlap")
            if overlap:
                print(f"  - {'Shipped content overlap':30s} {overlap['identical']}/{overlap['packages']} identical "
                      f"({overlap['identical_fraction']:.1%}) · {overlap['drifted']} drifted · "
                      f"{overlap['only_some']} in only some")
                if overlap["drifted_sample"]:
                    print(f"      drifted packages: {', '.join(overlap['drifted_sample'][:8])}"
                          + ("…" if overlap["drifted"] > 8 else ""))
            if comparison["shared_version_key"]:
                print(f"\nShared launcher-independent version: {comparison['shared_version_label']}. {comparison['note']}")
            else:
                print(f"\n{comparison['note']}")
        else:
            print("\nInstall one copy from each launcher (Steam and PURPLE) to compare which signal is the shared "
                  "game version.")
        if purple:
            print(f"\nPURPLE launcher: AION 2 Global version {purple['purple_app_version']} "
                  f"(build {purple['purple_build_number'] or '?'}), from the launcher's own run record. "
                  "This confirms the PURPLE game version independently of the executable; it does not carry an "
                  "install path.")
    elif args.cmd == "npc-evidence":
        from .combat import npc_aggregate as NA
        if args.logs:
            docs = _load_local_docs(args.logs)
            source = f"{len(docs)} local file(s)"
        else:
            docs = NA.from_server(limit=args.limit, base_url=args.server)
            source = (args.server or "the configured community log server")
        agg = NA.aggregate(docs)
        cand = NA.candidates(agg, min_logs=args.min_logs, min_records=args.min_records)
        var = NA.variants(agg)
        art = NA.missing_portraits(agg)
        if args.json:
            print(json.dumps({"source": source, "aggregate": agg, "candidates": cand, "variants": var,
                              "missing_portraits": art}, indent=1))
            return 0
        print(f"Source: {source}")
        print(f"{agg['uploads_with_diagnostics']}/{agg['uploads']} uploads carry NPC decoder evidence · "
              f"{agg['distinct_mob_codes']} distinct mob codes · {agg['total_records']} records")
        if not agg["total_records"]:
            print("No NPC decoder evidence yet. It accumulates as clients that record it upload fights.")
            return 0
        print(f"\nStable observed NPC types the catalog cannot name ({len(cand['needs_name'])}) "
              f"— candidates to identify from source evidence:")
        for c in cand["needs_name"]:
            print(f"  {c['mob_code']:>9}  {c['logs']} uploads · {c['records']} records · "
                  f"{c['decoded_fraction']:.0%} decoded · catalog: {c['name'] or 'unknown'}")
        print(f"\nDecoder-confirmed catalog NPCs ({len(cand['named'])}): " +
              (", ".join(f"{c['mob_code']}={c['name']}" for c in cand['named'][:8]) + ("…" if len(cand['named']) > 8 else "")
               or "none promoted yet"))
        print(f"Abstained for low support ({len(cand['abstain'])}; need "
              f"≥{args.min_logs} uploads and ≥{args.min_records} records).")
        print("\nIdentity / packet variants by opcode (a low decoded rate = an unclassified variant):")
        for r in var["opcodes"]:
            print(f"  opcode {r['opcode']}: {r['decoded_fraction']:.0%} decoded over {r['records']} records · {r['statuses']}")
        print(f"  type-marker-missing observations: {var['marker_missing_observations']}")
        print(f"\nObserved NPCs without portrait art ({art['observed_without_portrait']}) — remaining ID-to-image mappings:")
        for r in art["rows"][:12]:
            print(f"  {r['mob_code']:>9}  {r['logs']} uploads · {r['records']} records · catalog: {r['name'] or 'unknown'}")
        print("\nNames are only ever taken from the catalog; unnamed codes are reported, never guessed.")
    elif args.cmd == "defeats":
        from .combat import defeats as DF
        if args.logs:
            docs = _load_local_docs(args.logs)
            rows = DF.rows_from_docs(docs)
            source = f"{len(docs)} local file(s)"
        else:
            rows = DF.from_server(limit=args.limit, base_url=args.server)
            source = (args.server or "the configured community log server")
        r = DF.dedupe_defeats(rows)
        print(f"Source: {source}")
        if args.json:
            print(json.dumps(r, indent=1))
            return 0
        print(f"{r['named_logs']} named uploads -> {r['distinct_defeats']} distinct defeats "
              f"({r['duplicate_logs']} duplicate perspectives folded; {r['total_logs']} uploads total)")
        for g in r["groups"]:
            tag = f"{g['perspectives']} perspectives" if g["perspectives"] > 1 else "single"
            diff = str(g.get("difficulty") or "-")
            print(f"  {str(g['boss'])[:30]:30s} {str(g['region'] or '?'):4s} {diff:10s} {g['duration']:>8.1f}s  "
                  f"party {g['party_size']}  {tag}")
        print("\n" + r["note"])
    elif args.cmd == "doctor":
        from . import ops
        report = ops.checkup(network=not args.offline)
        if args.json:
            print(json.dumps(report, indent=1))
            return 0
        mark = {"ok": "OK  ", "warn": "WARN", "unavailable": "n/a "}
        for c in report["checks"]:
            print(f"  [{mark.get(c['status'], '????')}] {c['name']:12s} {c['detail']}")
        s = report["summary"]
        print(f"\n{s['ok']} ok · {s['warn']} warn · {s['unavailable']} unavailable")
        print(report["note"])
        return 1 if s["warn"] or s["unavailable"] else 0
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
              "rotation optimizer) is the reliable number. Every class now has a hand-written kit (see "
              "`aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, so absolute "
              "DPS across classes is far more comparable than before; the kits' fidelity is still shown as the share "
              "overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute "
              "numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and "
              "await calibration against real combat-log captures.\n",
              "| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |",
              "|---|---:|---:|---:|---:|---|"]
        for cls, dps, comm, fid in rows:
            print(f"{cls:14s} {dps:12,.0f} {comm:12,.0f} {100 * (dps / comm - 1):6.1f}%")
            md.append(f"| {cls} | {dps:,.0f} | {comm:,.0f} | {100 * (dps / comm - 1):+.1f}% | "
                      f"{'—' if fid is None else f'{100 * fid:.0f}%'} | [{cls}]({cls}/README.md) |")
        Path(args.out, "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
