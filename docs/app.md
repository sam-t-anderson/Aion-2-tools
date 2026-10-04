# The aion2calc app

Players install the desktop app (Windows installer, or portable builds for Windows, macOS and
Linux): see [install.md](install.md). From source:

```bash
pip install -e .
python -m aion2calc app            # http://127.0.0.1:8765 opens in your browser
```

Everything runs on your machine. The app talks to four public sites:

| Site | Used for |
|---|---|
| metabot.gg | game data from the global client: classes, skills, items, titles, arcana pools, Daevanion boards |
| aion2.plaync.com | official character profiles (character import) and official item data |
| abysslogs.com | fights recorded with the AbyssLogs meter and shared by link (combat-log import) |
| a2dil.com | public Korean training-dummy logs (combat-log import) |

## Where your data is saved

Everything the app writes goes in one folder:

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\aion2calc` (`C:\Users\<you>\AppData\Local\aion2calc`) |
| Linux, macOS | `~/.aion2calc` |
| any (override) | the folder in the `AION2CALC_HOME` environment variable |

| Inside | Holds |
|---|---|
| `logs\` | one JSON file per analyzed combat log |
| `results\` | optimizations run from the app, and your character optimizations |
| `data\` | game data the launch-time sync downloaded, model calibration (`calibration\`), log server settings |
| `inventory\` | one inventory per character for the gear planner |
| `aion2.db` | item catalog, imported characters, encounter history |
| `cache\`, `icons\` | downloaded pages and icons |

Earlier versions kept this folder in `C:\Users\<you>\.aion2calc` on Windows too. The first launch
moves it to AppData. `python -m aion2calc logs` prints the data folder and the logs folder, and
`--open` opens the logs folder in Explorer.

## Pages

| Planner: skills | Planner: Daevanion |
|---|---|
| ![Skills](screenshots/planner_skills.png) | ![Daevanion](screenshots/planner_daevanion.png) |
| **Planner: equipment** | **Planner: arcana** |
| ![Equipment](screenshots/planner_equipment.png) | ![Arcana](screenshots/planner_arcana.png) |
| **Combat logs** | **Database** |
| ![Combat logs](screenshots/combat_logs.png) | ![Database](screenshots/database.png) |

### Planner

Every optimized build is shown as a set of windows laid out like the in-game
screens, so you can copy each one into the game:

| Window | Shows |
|---|---|
| Overview | DPS, crit chance, cooldown reduction, combat speed, stat priority, damage share |
| Skills | Active and Passive tabs. Each skill shows its icon with a level badge, the level split (skill points + Daevanion + gear), and the five numbered specialization chips. The chosen specs are highlighted and their text is spelled out |
| Stigma | the four slots with level and which specializations are unlocked |
| Daevanion | one tab per board with the node grid (taken nodes lit), and the game's left-side summary: points used, skill levels gained, stats gained. There is also a link to the metabot planner |
| Equipment | a paper-doll layout of the loadout, the rolls to keep or reroll toward, and enchant priority |
| Arcana | the recommended variant per slot, and the value of each slot's skill rolls (Unique +0 and +5) |
| Titles & wings | equipped titles, wings, pet, and the best titles for the build |
| Macro & rotation | the in-game Skill Macro steps and the priority list |

Below each window there is a **Stats from this system** summary. **Copy as
text** puts the window's choices on the clipboard. **My screenshot** lets you
pin a screenshot of the same in-game window next to it, so you can compare them
side by side. The screenshot is kept only in your browser.

The **Optimize** button runs a new optimization for any class. The skill-point
and stigma-point budgets are optional.

### My Character

1. Search a character name (global regions: North America, Europe, Asia, Latin America).
2. **Import** reads the official character page: profile stats, every equipped
   item with its rolls, manastones, theostones and skill rolls, arcana, titles,
   wings, pet, skill levels, slotted stigmas and every open Daevanion node.
3. The build is scored as it is. The official profile does not show
   specializations, so the score uses the best legal specs for your levels.
4. **Optimize my build** keeps your gear and the points you have already spent
   (skill points, stigma points, Daevanion points). It finds the best
   allocation and rotation, then shows the DPS gain and what to change.

What the profile does not show, and how it is handled:

| Missing | Handling |
|---|---|
| specializations | assumed best for your levels |
| bonus from owned (unequipped) titles | estimated (+4 Attack, +20 Crit, +30 Accuracy) |
| stats of uncommon wings | counted only for wings in a small table (Ultimate Daeva Wings) |

### Gear & Advice

Pick an imported character to see its inventory: the equipped items come from the official page,
and you add the rest from the catalog, with enchant level and skill options. You also enter its
Genus Insight lines and the titles you own here. **Run advice** then plans gear (best set from
the inventory, goal gear, upgrade path), arcana, titles, pantheon, genus insight and your fights,
ranked by simulated DPS gain. The results are shown as game-style windows with the game's icons:
an equipment paper doll, the upgrade path as item cards, arcana cards, title plates, the
pantheon deities and the genus insight grids. The
model is calibrated from the character's fights when there are enough. Details:
[planner.md](planner.md).

### Combat Logs

Import a log in any of these ways:

| Source | How |
|---|---|
| AbyssLogs | record the fight with the free [AbyssLogs meter](https://abysslogs.com), press **Share** in the meter, and paste the `https://abysslogs.com/e/<id>` link. Any public or unlisted fight works, yours or someone else's |
| AbyssLogs file | a segment file saved from abysslogs.com (`.json` or `.json.gz`) |
| A2DIL | a record link (Korean training-dummy logs) |
| your own tool | a JSON or CSV file in the formats below |

For AbyssLogs:

* A link to a whole dungeon run picks its biggest boss pull. A link with `?seg=` (a link to one
  pull) uses that pull.
* A party log shows the damage of whoever recorded it. Type a name in **player**, or click a party
  member above the results, to see someone else's.
* AbyssLogs records hit-by-hit timelines for boss pulls only, so trash pulls cannot be analyzed.
* Chain follow-ups are listed under their skill, for example *Ice Chain (Cold Wave)* and
  *Flame Arrow (Burst)*.
* The log includes each skill's specializations. The comparison lists the ones that differ from
  the optimized build. The official character page does not show specializations.

The analyzer shows:

* DPS, total damage, duration, casts per minute, and crit / double / perfect /
  multi-hit rates
* a per-second DPS timeline with a 10-second average
* damage by skill: share, casts, hits, rates, average and biggest hit, and how
  well each skill's cooldown was used
* the opening rotation, buff uptimes and idle gaps
* **Compared with your optimal rotation**: the same fight length simulated with
  the optimized build. It shows share and casts per skill, specializations
  that differ, and concrete tips such as "cast 21x, the optimal rotation casts
  it 27x"
* **Compared with top players**: the class's top-10 A2DIL dummy logs

Every imported log is stored in the encounter history and saved as a file in
the `logs` folder (see [Where your data is saved](#where-your-data-is-saved)),
for example
`2026-10-04_190338_sorcerer_Name_Guardian-Captain-Raur_abysslogs-12.json`.
The file uses the canonical JSON format below, so it can be kept, shared or
analyzed again (`python -m aion2calc analyze <file>`). **Open folder** on the
Combat Logs page opens the folder.

Compare shares and casts more than DPS when:

* the log is Korean (A2DIL): those players have higher-level gear than the global simulation;
* the log is a boss fight: movement, mechanics and party buffs are not in a training-dummy
  simulation.

#### Sharing a fight

Set your log server once (**Share to a log server**: URL, upload key, default visibility). After
that, **Share link** on any fight uploads it in the open a2log format and shows a link anyone can
open. See [logserver.md](logserver.md) to host the server on Ubuntu.

Every saved fight is also matched to the gear its player wore and used to calibrate the model (see
[planner.md](planner.md#learning-from-your-fights)).

#### Uploading to AbyssLogs

AbyssLogs takes fights only from its own meter. The site has no file upload, and only a meter
linked to your account can upload. Its leaderboards depend on every fight having been recorded by
that meter. aion2calc therefore does not write files for AbyssLogs. To share a fight, record it
with the AbyssLogs meter and share it from there. Then paste the same link into aion2calc to
compare it with your optimal rotation.

#### Log formats

JSON (the canonical format):

```json
{"meta": {"source": "my-tool", "player": "Name", "target": "Boss", "duration": 180},
 "hits": [{"t": 0.0, "skill_id": 15060000, "skill": "Hellfire", "damage": 12345,
           "crit": true, "double": false, "perfect": false, "multi": 2, "dot": false}],
 "buffs": [{"name": "Element Enhancement", "skill_id": 15400000, "uptime": 0.98}]}
```

Optional per hit: `front`, `back`, and `step`, the name of a chain follow-up
(`"skill_id": 15090000, "step": "Cold Wave"` is shown as *Ice Chain (Cold Wave)*).
Optional at the top level: `"specs": {"Hellfire": "2, 4"}`.

CSV needs these columns: `t, skill, damage`, plus optionally `skill_id, crit, double, perfect, multi, dot`.

#### Live capture

AbyssLogs, AionFlex, A2DIL's recorder and every other AION 2 meter capture the
game's network traffic and decode an undocumented binary protocol that changes
with patches. That decoder is not public, so aion2calc does not capture
anything itself. The simplest way to get your own fights in is the AbyssLogs
meter and a share link (above).

`aion2calc/combat/live.py` defines the interface a live source implements. Any
tool that yields hits plugs straight into the analyzer and the history. Using
third-party capture tools may break the game's terms of service.

### Database

The page shows sync progress, the last sync, item, character and encounter
counts, and an item catalog with search. Each item lists its fixed stats,
enchant table, random roll pool and per-class skill-roll pools.

### Settings

| Setting | What it does |
|---|---|
| Theme | **Follow computer** (light or dark with your system), **Light** (parchment and gold) or **Dark** (night sky and gold). The ◐ button in the top bar switches between them too. The choice is kept in this browser |
| Open as its own window | the installed app opens in an Edge or Chrome app window, without tabs or address bar, and stops when you close it. Off: it opens in your default browser |
| Your data | the data folder, with buttons to open it, the combat logs and the results |
| Log server | where **Share link** uploads fights, an optional upload key, and the default visibility. **Save** checks the server answers |
| Game database | item count, last update, and **Check now** |
| Version | the app version, and a link when your log server offers a newer one |
| Stop the app | the same as **Quit** in the top bar |

## Auto-update on launch

When the app starts, a background sync checks for new and changed data. No
code changes are needed when the game adds content:

* **Discovery.** metabot's sitemaps list every class, skill, item, title and
  wing page with a last-modified date. The sync fetches a page again only when
  that date moves. The equipment universe is whatever metabot's category
  pages list (weapons, armor, accessories, arcana, theostones). Classes are
  discovered from the sitemap as well.
* **Where updates go.** Class data, titles, arcana pools and median loadouts
  are written to the `data` subfolder of the data folder (see
  [Where your data is saved](#where-your-data-is-saved)). Every reader prefers
  that copy over the bundled one. Items go into `aion2.db` in the same folder.
* **Seed.** A fresh install starts from the bundled seed catalog
  (`aion2calc/data/seed/items.json.gz`), so only the changes are fetched.
* **Limits.** The sync is time-boxed (15 minutes per launch) and resumable. A
  page whose layout changed is skipped, and the old data is kept.
* **New skills.** A skill that appears in a patch is simulated from its tooltip
  by the generic kit, even for classes with a hand-written kit.

To sync by hand: `python -m aion2calc sync` (`--force` re-reads everything,
`--budget SECONDS` caps the run).

## Point budgets

| Budget | Value |
|---|---|
| Skill points | 203 from levels, plus 1 per Wisdom Stone. Wisdom Stones are exchanged for Empyrean Traces at monoliths; top global players at level 45 have spent 382–383 points. Pass `--skill-points` (CLI) or set it in the Planner. An imported character is optimized with what it has spent |
| Stigma points | 30 from levels. Some profiles show more (up to about 70), so it is configurable the same way |
| Daevanion | 360 crystal points at launch. An imported character is optimized with its own crystal spend |

## API

`GET /api/status`, `/api/classes`, `/api/results`, `/api/build?path=`,
`/api/character/search?name=&region=`, `/api/characters`, `/api/encounters`,
`/api/encounters/<id>`, `/api/logs`, `/api/logserver`, `/api/inventory?character=`,
`/api/calibration?class=`, `/api/items?search=&category=`,
`/api/items/<slug>`, `/api/jobs/<id>`, `/api/icon?u=`

`POST /api/sync`, `/api/optimize`, `/api/character/import`,
`/api/character/optimize`, `/api/encounters/import` (`{"ref": link, "player": name}`
or `{"text": file contents, "name": file name, "player": name}`), `/api/encounters/<id>/share`,
`/api/logserver`, `/api/inventory/add|remove|genus`, `/api/advice` (job), `/api/logs/open`

Long requests return a job id; poll `/api/jobs/<id>` until its status is `done`.
