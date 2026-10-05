# Aion-2-tools

[![CI](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/9y6zkUyvBv)

**Community: [discord.gg/9y6zkUyvBv](https://discord.gg/9y6zkUyvBv)**

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

## Example: Sorcerer, level 45 global

The optimized Sorcerer build (boss DPS 17,962 on median launch gear, 25,890 on upgrade gear), with its
arcana, stigmas, priority list, macro, stat priority, build card and Daevanion boards, is in
[`example/sorcerer_l45_global`](example/sorcerer_l45_global/README.md).

## Install

**Players:** download the app from the
[Releases page](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest). On Windows, run
`aion2calc-setup-<version>.exe` and start **aion2calc** from the Start menu; portable builds for
Windows, macOS and Linux are there too. No Python and no command line needed. The app follows your
computer's light or dark mode. Details and updating: [`docs/install.md`](docs/install.md).

Windows may warn that the download is unrecognized until the builds are code-signed: choose **More info →
Run anyway**. [Code signing policy](docs/code-signing.md).

| Dark | Light |
|---|---|
| ![Dark theme](docs/screenshots/app_dark.png) | ![Light theme](docs/screenshots/app_light.png) |

**From source:**

```bash
pip install -e .
python -m aion2calc app        # opens http://127.0.0.1:8765
```

## The app

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
* **Gear & Advice**: what to wear from your inventory, goal gear per slot and an upgrade path,
  arcana (variant, skill options to chase, keep or replace), titles (per slot, and which to collect),
  pantheon (deity stats by value),
  genus insight (which lines to reroll, which genus to level) and what your fights show, all ranked
  by simulated DPS gain, shown as game-style windows with the game's icons. Fights you import are
  matched to the gear you wore and calibrate the model
  ([details](docs/planner.md)).
* **Share**: upload any saved fight to a log server in the open a2log format and get a link anyone
  can open.
* **Database**: updates itself on every launch from the live sources. New items, skills or classes
  need no code changes.
* **Settings**: light, dark or follow-the-computer theme, the data folder, the log server for
  sharing, updates.

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

# gear / arcana / pantheon / genus / rotation advice for a character, and its inventory
python -m aion2calc advise "Name" --server Zikel
python -m aion2calc inventory "Name" --add aulamus-ring --enchant 8

# share a saved fight on a log server (open a2log format) and print the link
python -m aion2calc share 12 --server https://logs.example.com --key a2l_...

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
| Combat logs | `combat/adapters.py`, `combat/abysslogs.py`, `combat/a2log.py`, `combat/analyze.py`, `combat/logs.py`, `combat/live.py` | log formats and AbyssLogs import, breakdown, comparison with the optimum and top logs, the logs folder, live-source interface |
| Planners | `plan/*` | inventory, best set, goal gear, upgrade path, arcana, pantheon, genus insight, advice |
| Learning | `learn.py` | fights matched to equipped-gear snapshots; calibration of crit curve, rates and skill damage |
| App | `app/server.py`, `app/views.py`, `app/static/*` | local server (stdlib) and the game-styled UI |
| Desktop app | `launcher.py`, `packaging/*` | app window, single instance, smoke test; PyInstaller and Inno Setup builds |

Formulas, sources, and every assumption: [`docs/methodology.md`](docs/methodology.md).

## Testing

```bash
python -m pytest -q
```

Every push runs the tests and builds the app on Windows, macOS and Linux
([CI](.github/workflows/ci.yml)); raising the version on `main` publishes a release
([how](docs/install.md#builds-and-releases-maintainers)).

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
