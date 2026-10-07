# The aion2calc app

## Capture driver evidence (0.2.37)

Live Meter capture diagnostics and shared combat-review quality panels show received packets, capture-buffer drops and interface/driver drops when the active Npcap/libpcap backend provides statistics. Unsupported backends are labeled unavailable; partial adapter coverage is labeled. Counters are retained in saved/exported logs and diagnostic ZIPs, including the final sample after capture stops and cumulative evidence across capture restarts in a retained session.

A positive reported drop counter conservatively makes the recording unranked. It does not identify which game effects were lost: counters cover the capture handle and may include other traffic. Zero does not prove loss-free capture, and missing counters are not zero. These counts must not be added to TCP discards to estimate unique lost game packets. Native capture backends without a libpcap handle remain usable, with driver statistics unavailable. Other capture-quality rules remain in effect; driver support alone neither grants eligibility nor blocks older logs.

Statistics are sampled before capture, in that adapter's packet callback and after its thread exits. Optional statistics failures do not interrupt packet decoding. See the [libpcap counter documentation](https://www.tcpdump.org/manpages/pcap_stats.3pcap.html) for platform-specific meanings and availability.

The pet review filter now follows a selected pet to its owner when enabling **Combine pets with owner**, instead of leaving a selection that disappears from grouped rows.


## Pet and spirit grouping

In desktop/website combat review, **Combine pets with owner** is checked by default above the graph. Uncheck it for separate pet rows/lanes. **Pets** controls pet effect visibility in the graph/timeline; it does not remove pet damage from the recorded table totals. Encounter insights retain separate source labels. Pet deaths are not counted as owner deaths.

Live Meter and the overlay now both have **Combine pets with owner**, enabled by default and synchronized for the active capture. The overlay includes recorded linked-pet damage in the owner row. Uncheck either control to inspect separate live pet rows. Grouping requires a recorded ownership link; unknown spirits are not assigned by name, proximity or class. Saved logs keep separate pet source IDs so grouping does not destroy detail.


## Encounter catalog coverage (0.2.36)

Live Meter fills difficulty only when the recorded PvE instance ID has an explicit difficulty in the bundled dungeon table. It does not infer difficulty from ID suffixes, damage, names or gear. Manual difficulty overrides remain available and their source is recorded. Content categories without a known mapping and the ranking game patch still require confirmation.

Combat review on desktop and Pages includes **Mapping coverage** with recorded map/instance IDs, a catalog revision, unresolved NPC types and enemy references missing their type. **Export mapping report** downloads this bounded ID report without character names or raw traffic. Diagnostic ZIPs include current-view catalog coverage as well; the full combat log contains coverage per retained encounter. A supplied creature name does not automatically become a trusted catalog entry.

Reports keep at most 100 unresolved IDs per encounter and show omitted counts. Entity references and effects are counts of retained evidence, not kills; player opponents and owned pets are excluded from NPC coverage. A missing type cannot be resolved from an actor ID, which changes between instances. An unmapped ID means absent from the installed catalog, not proof of new content.


## Automatic capture metadata and idle DPS (0.2.35)

Live Meter detects the installed game build for registered Windows installs and resolves recorded server IDs against official regional metadata in the background. Installation paths are not exported. Steam build IDs and executable versions are build evidence, not automatically a game patch. Optional classification overrides take precedence within the recorded PvE/PvP mode.

Recorded map/instance IDs identify known open-world categories, Fire Temple Arena and available dungeon names. Unmapped content, difficulty, patch and match outcomes remain unknown. Detection provenance is visible in shared log review. Opponents without their own server ID are not assigned your server.

Live DPS uses the recorded damage interval and pauses after two seconds without damage while capture continues. Healing after the last damage no longer lowers live DPS. Actual new damage resumes it. Saved logs preserve the full event interval, including healing/deaths, so report rates can differ from the live rate. This does not establish a kill or match result.


## Full-session TCP diagnostics

TCP diagnostics record the entire session to disk with no record-count or size cap. Available disk space is the limit; the UI shows recording size and write errors. Long sessions take longer to compress on Stop or export. Export during capture takes a fixed snapshot while recording continues. Raw `tcp-session-*.jsonl` files stay recoverable after a crash or failed export; successful stopped-session exports remove their raw temporary copy. ZIPs remain until you delete them. Raw traffic can contain character names and network addresses; review before sharing. This changes raw diagnostic retention, not the separate decoded combat-history limits.

Files are in the user data folder’s `diagnostics` directory (`%LOCALAPPDATA%\aion2calc\diagnostics` on Windows). Keep leftover raw files after a failed export for troubleshooting; remove them and old ZIPs manually when no longer needed. Nothing is automatically uploaded.

Players install the desktop app (Windows installer, or portable builds for Windows, macOS and
Linux): see [install.md](install.md). Running from source and the CLI are in [cli.md](cli.md).

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
moves it to AppData. **Settings → Your data** has buttons that open the data, logs and results
folders.

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
analyzed again (drop it back on the Combat Logs page). **Open folder** on the
Combat Logs page opens the folder.

Compare shares and casts more than DPS when:

* the log is Korean (A2DIL): those players have higher-level gear than the global simulation;
* the log is a boss fight: movement, mechanics and party buffs are not in a training-dummy
  simulation.

#### Sharing a fight

Set your log server once (**Share to a log server**: URL, upload key, default visibility). After
that, **Share link** on any fight uploads it in the open a2log format and shows a link anyone can
open.

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

The **Live Meter** tab includes the migrated A2Tools packet engine. Choose
**Live Capture** (the default), then press **Start**. Its built-in encoder,
automatic interface and game-host selection, and port `50349` are filled in
for the standard connection. Set a specific interface or game-host address
only when automatic selection cannot see the game traffic; the **Interfaces**
button lists the identifiers Npcap exposes on this computer. Choose the target
mode and optionally name your character to improve local-player detection.

The Windows desktop build includes Scapy. Windows setup offers an optional
**Download and install Npcap for Live Capture** choice, and Live Meter asks
again when you press Start if Npcap is still missing. After you confirm, it
finds the current installer on [npcap.com](https://npcap.com/), downloads it
to the app's `drivers` folder, and opens its normal installer. This keeps
Npcap separate from aion2calc, as required by its license. Select
WinPcap-compatible mode in the installer and grant capture permission.

Npcap is Windows-only. macOS uses its built-in packet-capture framework.
Linux needs the distribution's `libpcap` package plus permission to capture
packets; Live Meter reports that prerequisite when the operating system denies
capture access.
The meter keeps decoded combat events, not raw packet captures. **Save to
Combat Logs** sends the active fight into the existing analyzer; **Export
a2log** writes an open JSON file to the app's logs folder; **Upload** sends it
to the log server set in Settings; and **Screenshot** saves a desktop image to
the app's screenshots folder. The GitHub Pages site is a viewer, so uploads go
through the configured log-server API that backs it.

#### Desktop updates

**Install update** stages the new installer first. When you choose it, the app
closes its local server, then a detached helper waits for the desktop process
to exit before opening the installer. This prevents a running `aion2calc.exe`
from locking the files the installer needs to replace.

#### Overlay

**Live Meter → Open overlay** opens one compact overlay that shows the live meter and plays your most
recent raid plan. On the installed Windows app it is frameless, transparent, always on top, and follows
the Aion 2 game window when it starts or moves. It closes with the desktop app. Where a native overlay
is not available it opens as a normal small window instead. From source, `python -m aion2calc.overlay`
does the same (`pip install pywebview` for the transparent window).

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
| Version | the app version, and a link when a newer release is out |
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

To sync by hand, use **Settings → Game database → Check now** (or **Full re-sync**
on the Database page).

## Point budgets

The build windows show points spent / optimization budget. Gear and Daevanion bonus skill levels do not consume purchased skill points. PvP Daevanion uses its own resource.

For **My Character**, the official profile gives allocated levels/nodes; unused points may be absent. Enter your in-game **spent + unspent** totals before Optimize my build. Imported budgets are observed lower bounds. Totals below points already spent are rejected. The optimizer preserves gear and uses the entered skill, stigma and PvE Daevanion budgets.

The Planner lets you set all three budgets. Bundled example budgets are 203 skill, 30 stigma and 360 PvE Daevanion; these are simulation presets, not a maximum or a guarantee about quest rewards.

## Community comparisons

Use Combat Logs to browse public submissions by type, boss, patch, difficulty and region. Class distributions stay in separate encounter buckets and show parse counts. Search personal records using server ID plus name, or database character ID. World ranks cover this community's public submissions only. Missing classification prevents ranking; open a local saved session to add verified metadata.

Add multiple comparison logs and select matching encounters and players explicitly. Differences are recorded DPS, not gear-adjusted scores.

## Editing shared plans

Publish stores a unique owner credential locally. Update published plan keeps the shared link; Publish new copy creates a separate publication. Export a Private ownership backup and keep it private. Import file restores that backup on another device. Refresh published plan obtains the current revision and replaces local edits, so export those first. Old publications without a saved ownership/delete credential need a new publication; author names do not grant editing access.

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

## Saved Results

Completed character/class optimizations and advice save automatically under the app data folder's `history` directory. Open **Saved Results**, select Open to review a previous run, or Export/Import its result JSON. Import restores a snapshot; it does not run an optimization or change your equipped gear. The latest existing old build/advice files are recovered when available. Keep exported copies to move runs between installations. Advice reflects the saved run, not future game or gear changes.

Edited point totals persist per character on this installation. Enter spent + unspent resources. Anonymous totals are sent after character optimization and accumulate as highest observed resources on the community service, grouped by class/region/patch/source. Unknown patch observations stay separate, and observed totals are not verified game caps.

## Experimental PvP optimizer

My Character provides separate PvE and PvP damage actions. PvP uses the generic class kit against a stationary neutral player proxy, excludes PvE/boss stat buckets and learned PvE skill/proc/critical calibration, and assesses sustained (180 seconds) and burst (30 seconds) damage. Saved results retain this model description. It does not optimize dedicated PvP progression, survival, crowd control, movement or opponent-specific defenses, and its skill coefficients are not validated PvP coefficients. PvP output is excluded from PvE community preset submission.

## Long live sessions (0.2.38)

Live capture automatically saves a numbered archive part before the current history reaches its effect, telemetry, encounter or observed-party identity budget. Each part has a shared archive ID and appears separately in **Combat Logs**. Capture continues with the same decoder and current identity context; the live meter and its export/upload buttons cover the current part. Open an earlier part from Combat Logs to review or upload it. There is no fixed total part count or automatic deletion; available disk space is the practical storage limit. The recent list shows the newest 100 files; older parts remain in the user logs folder and can be imported.

A storage boundary is not a boss kill, instance finish or arena result. Parts crossing a storage boundary are conservatively unranked, and a continued run does not inherit observed entry. Parts are not automatically stitched into a combined report or uploaded as a batch. A failed rollover save stops capture visibly and retains the in-memory history instead of clearing it. Periodic recovery is still every 15 seconds; abrupt termination can lose newer unsaved effects.

Per-file format/validation limits still apply. In unusually large All-observed rosters, a part can exceed the 64-player validation limit; the app reports a save error rather than silently clearing it. Party/Self scope is recommended. This is automatic bounded-part archival, not an unlimited single JSON document. Raw TCP diagnostics remain a separate opt-in recording.

Implementation: rollover is checked between decoded packet batches at 100,000 retained effects, 20,000 telemetry samples, 100 conservative candidate encounter boundaries or 48 observed party actor references. Saves use atomic replacement and fsync before releasing the old part. Thresholds leave headroom for normal packet batches. Counters remain conservative cumulative capture evidence across parts. No live TCP stream is reopened, historical identity epochs are not merged, and recorded pet links remain available.

## Review and upload saved parts (0.2.39)

**Combat Logs → Saved parts** browses local files in pages of 25, including files older than the newest 100. Open a part to review it, filter the current page by encounter type, name or archive ID, and select up to 100 saved files across pages. Choose Public, Unlisted or Private, then **Upload selected / retry remaining**. The default is Unlisted. Each file creates an independent report; archive parts are not stitched into one timeline or combined score.

The same queue is available on the Pages **Logs** page: choose saved a2log v1 JSON files (up to 50 MiB each), review locally and select the parts to upload. Uploads use the community server configured for the site or the visitor's saved Raid Planner server settings. Reading a file does not upload it. The browser compresses uploads when CompressionStream is available; server size/rate limits still apply.

The queue shows progress, uploaded report links, errors and ownership-save warnings for each file. Cancel stops before the next upload; an in-flight request can finish. Successful entries are skipped when retrying within the same queue. Network/authentication/rate-limit failures stop the queue with remaining files pending. A lost response can be ambiguous: retry can create another upload if the server already accepted the first. Clearing the queue or leaving/reloading the page loses this queue's retry state, but saved ownership credentials remain available under My uploads. Navigating away stops before the next request, not necessarily the current one.

Active or unfinished checkpoints are excluded from batch upload; stop capture first. An unfinished crash-recovery checkpoint can still be reviewed and published individually as partial evidence. Local pagination is a live file listing: concurrent new checkpoints can shift page boundaries, so selection is tracked by filename and should be reviewed before upload. Filters apply to the current page, not every file on disk. Changing server/visibility requires clearing the queue; desktop requests reject a server change during a batch.

**Export upload results** saves a manifest of selected files, archive/part labels, statuses and report IDs. Public/unlisted links may be included, so unlisted links should be shared deliberately. Private links, upload keys and ownership credentials are excluded. Keep using My uploads → Export private credentials for an ownership backup. A manifest is a list of outcomes, not a combined combat log, permanent privacy snapshot or automatic import/resume credential.
