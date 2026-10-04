# The aion2calc app

```bash
pip install -e .
python -m aion2calc app            # http://127.0.0.1:8765 opens in your browser
```

Everything runs on your machine. The app talks to three public sites:

| Site | Used for |
|---|---|
| metabot.gg | game data from the global client: classes, skills, items, titles, arcana pools, Daevanion boards |
| aion2.plaync.com | official character profiles (character import) and official item data |
| a2dil.com | public Korean training-dummy logs (combat-log import) |

## Pages

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

### Combat Logs

Import a log as an A2DIL record link, a JSON file or a CSV file. The analyzer
shows:

* DPS, total damage, duration, casts per minute, and crit / double / perfect /
  multi-hit rates
* a per-second DPS timeline with a 10-second average
* damage by skill: share, casts, hits, rates, average and biggest hit, and how
  well each skill's cooldown was used
* the opening rotation, buff uptimes and idle gaps
* **Compared with your optimal rotation**: the same fight length simulated with
  the optimized build. It shows share and casts per skill, plus concrete tips
  such as "cast 21x, the optimal rotation casts it 27x"
* **Compared with top players**: the class's top-10 A2DIL dummy logs

Every imported log is stored in the encounter history.

Korean logs come from higher-level gear than the global simulation, so compare
their shares and casts, not their DPS.

#### Log formats

JSON (the canonical format):

```json
{"meta": {"source": "my-tool", "player": "Name", "target": "Boss", "duration": 180},
 "hits": [{"t": 0.0, "skill_id": 15060000, "skill": "Hellfire", "damage": 12345,
           "crit": true, "double": false, "perfect": false, "multi": 2, "dot": false}],
 "buffs": [{"name": "Element Enhancement", "skill_id": 15400000, "uptime": 0.98}]}
```

CSV needs these columns: `t, skill, damage`, plus optionally `skill_id, crit, double, perfect, multi, dot`.

#### Live capture

AionFlex, A2DIL's recorder and every other AION 2 meter capture the game's
network traffic and decode an undocumented binary protocol that changes with
patches. That decoder is not public. It can only be reverse-engineered from
captures of a running game client, so it is not included here.

`aion2calc/combat/live.py` defines the interface a live source implements. Any
tool that yields hits plugs straight into the analyzer and the history. Using
third-party capture tools may break the game's terms of service.

### Database

The page shows sync progress, the last sync, item, character and encounter
counts, and an item catalog with search. Each item lists its fixed stats,
enchant table, random roll pool and per-class skill-roll pools.

## Auto-update on launch

When the app starts, a background sync checks for new and changed data. No
code changes are needed when the game adds content:

* **Discovery.** metabot's sitemaps list every class, skill, item, title and
  wing page with a last-modified date. The sync fetches a page again only when
  that date moves. The equipment universe is whatever metabot's category
  pages list (weapons, armor, accessories, arcana, theostones). Classes are
  discovered from the sitemap as well.
* **Where updates go.** Class data, titles, arcana pools and median loadouts
  are written to `~/.aion2calc/data` (or `$AION2CALC_HOME/data`). Every reader
  prefers that copy over the bundled one. Items go into `~/.aion2calc/aion2.db`.
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
`/api/encounters/<id>`, `/api/items?search=&category=`, `/api/items/<slug>`,
`/api/jobs/<id>`, `/api/icon?u=`

`POST /api/sync`, `/api/optimize`, `/api/character/import`,
`/api/character/optimize`, `/api/encounters/import`

Long requests return a job id; poll `/api/jobs/<id>` until its status is `done`.
