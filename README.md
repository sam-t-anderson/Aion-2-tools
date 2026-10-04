# Aion-calc

A repeatable **Aion 2 build / rotation simulator and optimizer**, built on the
**global client data** (level 45 launch, Oct 2026) with Korean live-service data
as a fallback.

It answers, for any class:

* which skills to put the **203 skill points** into and which **specializations** to run,
* which **4 stigmas** and levels to buy with the **30 stigma points**,
* which **Daevanion nodes** to take with **360 crystal points** (exact connectivity rule),
* the best **priority rotation**, an **in-game Skill Macro** layout and manual keys,
* how much each **stat / item roll / title / arcana / enchant** is worth,

and produces images of the Daevanion boards and a planner-style build page plus
share links for the metabot.gg and gamers4.life planners.

## Sorcerer, level 45 global: results at a glance

| | Median launch gear, 203 SP | Median gear, 383 SP (all Empyrean Traces) | First-month upgrade gear |
|---|---:|---:|---:|
| Optimized build, boss DPS | **17,962** | **18,342** | **25,890** |
| Typical top global build, same rotation optimizer | 16,512 | — | 23,809 |

* Full reports: [median gear](results/sorcerer_l45/README.md) ·
  [383 skill points](results/sorcerer_l45_full_sp/README.md) ([what changes](results/sorcerer_l45_full_sp/DIFF.md)) ·
  [upgrade gear](results/sorcerer_l45_geared/README.md) ([what changes](results/sorcerer_l45_geared/DIFF.md))
* Arcana: Parchment is the slot to chase (core fire skills); two extra Hellfire levels (Lv 16) are
  worth about +5%
* Stigmas: Element Enhancement 10, Cold Storm 6, Fire Wall 6, Delayed Explosion 1
* Priority: Wish → Element Enhancement → Fire Wall → Cold Storm → Winter's Shackles → Blaze →
  Firestorm → Hellfire (full charge) → Bittercold Wind (inside Element Enhancement) → Frost Burst →
  Flame Scattershot → Delayed Explosion → Flame Arrow (filler)
* One-button in-game Skill Macro reaches ~95% of that priority list in simulation
* Stat priority (median gear): Cooldown Reduction > Damage Boost > Penetration ≈ PvE Attack ≈ Double >
  Weapon Damage Boost > Crit > Attack; on upgrade gear Crit moves to the top

![Sorcerer build card](results/sorcerer_l45/images/build_card.png)

## The app

```bash
pip install -e .
python -m aion2calc app        # opens http://127.0.0.1:8765
```

* **Planner**: each optimized build is laid out like the in-game windows (skills with numbered spec
  chips, stigma, Daevanion boards, equipment, arcana, titles and wings, macro). Below each window is
  a "stats from this system" summary, a copy-as-text button, and a slot to pin your own in-game
  screenshot next to it.
* **My Character**: import any character from the official AION 2 site. You get its gear, rolls,
  manastones, arcana skill rolls, Daevanion and skill levels, a DPS score as it is, and one click to
  optimize it with the same gear and points.
* **Combat Logs**: paste an [AbyssLogs](https://abysslogs.com) share link (or an A2DIL link, or a
  JSON/CSV file) for an AionFlex-style breakdown: per-skill share, casts, crit/double/perfect
  rates, cooldown use, timeline, buffs, idle time. It compares the log with the optimal rotation and
  specializations for that build and with top-player logs. Every log is also saved as a file in the
  logs folder.
* **Database**: updates itself on every launch from the live sources. New items, skills or classes
  need no code changes.

Everything the app saves (game database, synced data, combat logs, your optimizations) goes in one
folder: `%LOCALAPPDATA%\aion2calc` on Windows (`C:\Users\<you>\AppData\Local\aion2calc`), or
`~/.aion2calc` on Linux and macOS. Combat logs are in its `logs` subfolder.

Details: [`docs/app.md`](docs/app.md).

## Quick start

```bash
pip install -e .            # numpy, matplotlib, pulp (CBC solver bundled)

# optimize a class and write results/<class>_l45/ (report, build.json, images)
python -m aion2calc optimize sorcerer
python -m aion2calc optimize gladiator --scenario dummy --daevanion 300

# simulate the typical top global build, or a saved optimized build
python -m aion2calc simulate ranger
python -m aion2calc simulate sorcerer --build results/sorcerer_l45/build.json

# optimize with another loadout and diff the two results
python -m aion2calc optimize sorcerer --loadout sorcerer_l45_geared --out results/sorcerer_l45_geared
python -m aion2calc diff results/sorcerer_l45 results/sorcerer_l45_geared

# optimize several classes with identical settings and rank them (writes results/compare/README.md)
python -m aion2calc compare sorcerer ranger assassin gladiator

# import and optimize a real character (official AION 2 site, global regions)
python -m aion2calc character "Name" --server Zikel --optimize

# analyze a combat log against the optimal rotation: AbyssLogs link, A2DIL link, JSON or CSV
python -m aion2calc analyze https://abysslogs.com/e/<id>
python -m aion2calc analyze https://abysslogs.com/e/<id> --player "Name"   # one player of a party log

# show or open the folder where every analyzed log is saved
python -m aion2calc logs --open

# update the local game database (also runs automatically when the app starts)
python -m aion2calc sync

# re-scrape the bundled data (developers; global client via metabot.gg, KR via gamers4.life / A2DIL)
python -m aion2calc refresh
```

Classes: `gladiator templar assassin ranger sorcerer spiritmaster cleric chanter`.

## How it works

| Layer | Module | What it does |
|---|---|---|
| Data | `aion2calc/scrape/*`, `aion2calc/data/` | metabot.gg (global client: skills per level, specs, budgets, Daevanion boards, items, titles, live top-player stats), gamers4.life (KR hit counts), A2DIL (KR dummy logs) |
| Model | `model/stats.py`, `model/damage.py` | stat aggregation, crit/double/perfect/multi-hit, damage-boost buckets, elemental and vulnerability multipliers |
| Kits | `kit/sorcerer.py`, `kit/generic.py` | skills as simulator actions; the Sorcerer kit encodes every interaction by hand, the generic kit parses tooltips and spec texts for any class |
| Simulator | `sim/engine.py` | deterministic expected-value event simulation (buffs, debuffs, DoTs, chains, resets, MP, procs with internal cooldowns, combat speed) |
| Optimizers | `opt/rotation.py`, `opt/pipeline.py`, `opt/daevanion.py`, `opt/statweights.py`, `opt/macro.py`, `opt/gear.py` | rotation search, specs, stigmas, per-skill level curves, joint Daevanion + skill-point integer program, stat weights, macro plan, gear advice |
| Output | `report.py`, `report_md.py`, `diff.py`, `render/*` | build.json, Markdown report, board images, build card, planner links, result diffs |
| Database | `db/store.py`, `db/sync.py`, `paths.py` | SQLite catalog + history, launch-time sync from sitemaps, user data overlay |
| Characters | `sources/official.py`, `sources/character.py`, `charopt.py` | official profile import → build + loadout → score as-is → optimize → diff |
| Combat logs | `combat/adapters.py`, `combat/abysslogs.py`, `combat/analyze.py`, `combat/logs.py`, `combat/live.py` | log formats and AbyssLogs import, breakdown, comparison with the optimum and top logs, the logs folder, live-source interface |
| App | `app/server.py`, `app/views.py`, `app/static/*` | local server (stdlib) and the game-styled UI |

Formulas, sources, and every assumption: [`docs/methodology.md`](docs/methodology.md).

## Testing

```bash
python -m pytest -q
```

## Adding or refining a class

Each class needs a loadout in `aion2calc/data/global/loadouts/<class>_l45_global_median.json`
(`python -c "from aion2calc.loadouts import make_all; make_all()"` regenerates all eight
from the live top-player data).  `kit/generic.py` works for every class straight from the data.  For best
fidelity, copy `kit/sorcerer.py` to `kit/<class>.py` and encode the class's
special interactions (chains, resets, conditional skills); `run.kit_module`
picks it up automatically.

## License

GPL-3.0 (see `LICENSE`).  Game data belongs to NCSOFT; community data belongs
to its respective sites.  This project is fan-made and not affiliated with NCSOFT.
