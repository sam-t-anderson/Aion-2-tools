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

**Sorcerer results:** [`results/sorcerer_l45/README.md`](results/sorcerer_l45/README.md)
(median launch gear) and [`results/sorcerer_l45_geared/README.md`](results/sorcerer_l45_geared/README.md)
(first-month upgrade target; what changes: [`DIFF.md`](results/sorcerer_l45_geared/DIFF.md)).

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

# re-scrape everything (global client via metabot.gg, KR via gamers4.life / A2DIL)
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
