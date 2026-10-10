# Command line and development

The desktop app ([install.md](install.md)) is all most people need. This page is
the command-line interface and the developer workflow, for contributors and for
scripted/batch runs.

## From source

```bash
git clone https://github.com/sam-t-anderson/Aion-2-tools && cd Aion-2-tools
pip install -e ".[dev]"
python -m aion2calc app        # the same app in your browser at http://127.0.0.1:8765
```

## CLI

```bash
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

# show each detected install's version signals and, across Steam + PURPLE, the shared game-version key
python -m aion2calc install-version          # add --json for raw evidence and the signal comparison

# check how closely each class kit matches real logs, and suggest tuned TIMING/ASSUME knobs
python -m aion2calc calibrate                       # every class vs the KR aggregate, worst fidelity first
python -m aion2calc calibrate gladiator --tune      # per-skill share gaps + suggested knob values
python -m aion2calc calibrate --capture fight.a2log.json --tune   # calibrate against your own capture
python -m aion2calc calibrate --capture fight.a2log.json --timings # measure skill cadence + pet swing periods

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

The installed desktop app also takes `--port` (default 8765), `--no-browser` and
`--no-sync` (skip the launch-time database update).

## Encounter catalog refresh

The enemy and dungeon tables come from the community [A2Tools parser](https://github.com/taengu/A2Tools-DPS-Meter). Refresh them independently of item/skill database sync:

```bash
python -m aion2calc catalog-refresh --revision FULL_40_CHARACTER_COMMIT_SHA --out catalog-staging
```

Use a reviewed upstream commit and a new output directory. The command downloads only NPC/dungeon JSON from that commit, validates IDs and row types, rejects duplicate keys and mismatched locale ID sets, and stages all 14 localized tables. It leaves installed mappings intact.

`catalog-audit.json` lists added, removed and changed ID counts per table, with up to 100 changes per table and omitted counts. Review the staged tables for complete changes, especially boss/dummy flags, dungeon links and difficulty. `catalog-source.json` records the upstream commit, check date, record counts, normalized table SHA-256 hashes and original download hashes.

For a release, copy the reviewed `i18n/npcs` and `i18n/dungeons` directories and `catalog-source.json` into `aion2calc/meter/a2parser/data/`, then submit the diff through CI. Keep source attribution and license obligations. Mapping coverage shows the source commit on desktop and Pages for new reports; older logs may lack this metadata. A community source revision does not establish its applicable game Build ID. No build association, missing portrait, difficulty or miniboss role is invented.

## Testing

```bash
python -m pytest -q
```

Every push runs the tests and builds the app on Windows, macOS and Linux
([CI](../.github/workflows/ci.yml)); raising the version on `main` publishes a release.

## Building the desktop app locally

```bash
python -m pip install . pyinstaller
pyinstaller packaging/aion2calc.spec --noconfirm     # -> dist/aion2calc/ (and dist/aion2calc.app on macOS)
dist/aion2calc/aion2calc --smoke-test                # prints each check, exit code 0 when all pass
```

The Windows installer needs [Inno Setup 6](https://jrsoftware.org/isdl.php):

```bat
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.2 packaging\windows\aion2calc.iss
```

PuLP's bundled CBC solver runs on Windows and Linux. On macOS, PuLP ships only an Intel CBC, so the
app uses HiGHS instead (the `highspy` package, installed automatically on macOS).

## Releasing

1. Raise the version in **both** `aion2calc/__init__.py` (`__version__`) and `pyproject.toml`.
2. Merge to `main`. CI builds, tests and publishes release `v<version>` (a merge that keeps the
   version builds and tests but publishes nothing). To publish without changing `main`, push a tag:
   `git tag v0.2.3 && git push origin v0.2.3`.

Signing the Windows build: [code-signing.md](code-signing.md).

### Presetting the log server for new users

Set the repository variable `A2LOGS_PUBLIC_URL` (**Settings → Secrets and variables → Actions →
Variables**) to the address of the log server your players share fights to, for example
`https://logs.example.com`. Every build then ships a `client.json`, and new users start with that
server selected. A `client.json` placed next to `aion2calc.exe` does the same for one copy:

```json
{"logserver_url": "https://logs.example.com", "visibility": "unlisted"}
```

`"key": "a2l_..."` may be added for people you trust to upload. The preset is used only when the
user has not chosen a server yet.

## Adding or refining a class

Each class needs a loadout in `aion2calc/data/global/loadouts/<class>_l45_global_median.json`
(`python -c "from aion2calc.loadouts import make_all; make_all()"` regenerates all eight
from the live top-player data). `kit/generic.py` works for every class straight from the data. For
best fidelity, copy `kit/sorcerer.py` to `kit/<class>.py` and encode the class's special interactions
(chains, resets, conditional skills); `run.kit_module` picks it up automatically.

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

Formulas, sources, and every assumption: [methodology.md](methodology.md).
