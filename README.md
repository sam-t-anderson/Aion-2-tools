# Aion-2-tools

Review combat sessions, compare public logs, search personal records, and copy optimized builds into the game. See the [feature roadmap](docs/COMBAT_ROADMAP.md) for remaining work.

[![CI](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-t-anderson/Aion-2-tools/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/9y6zkUyvBv)

**Community: [discord.gg/9y6zkUyvBv](https://discord.gg/9y6zkUyvBv)**

A repeatable **Aion 2 build / rotation simulator and optimizer**, built on the
**global client data** (level 45 launch, Oct 2026) with Korean live-service data
as a fallback.

It answers, for any class:

* which skills to put **your available skill points** into and which **specializations** to run,
* which **4 stigmas** and levels to buy with **your available stigma points**,
* which **Daevanion nodes** to take with **your available PvE crystal points** (exact connectivity rule),
* the best **priority rotation**, an **in-game Skill Macro** layout and manual keys,
* how much each **stat / item roll / title / arcana / enchant** is worth,

and produces images of the Daevanion boards and a planner-style build page plus
share links for the metabot.gg and gamers4.life planners.

## Multiple runs in one capture

Capture can stay running across encounters and runs. **Finish run** closes the current run; the next damage starts another without clearing earlier fights. Map or dungeon-ID changes separate runs and label their completion as unverified. Desktop and Pages review have a **Run** selector; a single uploaded a2log retains the run boundaries and all included encounter splits.

For automatic final-boss completion, enter verified final-boss NPC type IDs before Start and leave **Finish on configured final-boss death** enabled. Completion requires a recorded death of that boss, recorded damage against it and a matching dungeon ID. The bundled NPC tables identify bosses but do not identify which boss is final; no final-boss rule is guessed from NPC ordering. PvP arenas/battlegrounds currently use **Finish run** or map/instance transitions until match-end packets are verified.

Known open-world maps receive separate PvE/PvP open-world categories; unresolved sources use **PvE · Unverified source** or **PvP · Unverified / other** unless you supply a category. Mode selection remains manual. Existing bounded capture limits still apply: 400,000 retained effects, 200 exported encounter splits and 64 unresolved player identities. Completed-run rollover/archival beyond those limits remains a follow-up; this does not provide an unlimited recording.

## Recovered advice

Saved Results restores the same interactive Gear & Advice panels from legacy `advice.json` files, including previously recovered text entries. Reports with only an `ADVICE.md` file remain readable as text because they lack the structured data needed for equipment and other controls. No advice calculation is rerun during recovery.

## Character builds in combat logs

Click a character name in a combat log to view their saved official equipment, skills, stigmas and other available build details. This includes identified PvP opponents on desktop and GitHub Pages. Uploaded logs request fresh public profiles from the official character service; completed snapshots stay with that historical log.

The profile shows when the upload arrived and when the lookup completed. It represents gear reported around upload time, which may differ from gear used in the encounter. Missing names/server identity, ambiguous matches and unavailable official responses are shown explicitly. Older logs have no historical snapshot. Desktop can fetch a clearly labelled current profile preview without replacing the historical build.

## Example: Sorcerer, level 45 global

The optimized Sorcerer build (boss DPS 17,962 on median launch gear, 25,890 on upgrade gear), with its
arcana, stigmas, priority list, macro, stat priority, build card and Daevanion boards, is in
[`example/sorcerer_l45_global`](example/sorcerer_l45_global/README.md).

## Install

**Players:** download the app from the
[Releases page](https://github.com/sam-t-anderson/Aion-2-tools/releases/latest). On Windows, run
`aion2calc-setup-<version>.exe` and start **Aion 2 Calc** from the Start menu; portable builds for
Windows, macOS and Linux are there too. No Python and no command line needed. The app follows your
computer's light or dark mode. Details and updating: [`docs/install.md`](docs/install.md).

Windows may warn that the download is unrecognized until the builds are code-signed: choose **More info →
Run anyway**. [Code signing policy](docs/code-signing.md).

| Dark | Light |
|---|---|
| ![Dark theme](docs/screenshots/app_dark.png) | ![Light theme](docs/screenshots/app_light.png) |

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
* **Live Meter**: capture the game connection with the included A2Tools packet engine. It starts in
  **Live Capture** mode with the built-in encoder, automatic interface and game-host detection, and
  port `50349`. Windows users can choose **Download and install Npcap** in setup or approve the
  prompt when starting Live Capture; the app fetches the current official installer, which must be
  installed in WinPcap-compatible mode. Save a fight to Combat Logs, export its open `a2log` JSON,
  upload it through the configured log server, take a screenshot, or open the transparent overlay.
  The overlay stays above and follows the Aion 2 game window when it is available.
* **Raid planner**: plan a boss fight on a visual map. Drop player, enemy, marker and AoE tokens,
  then scrub a **timelapse** slider and drag each token to where it should be at that moment — the
  planner fills in the movement in between. Lay out **party buffs** on the timeline, overlay a saved
  combat log to compare the plan with the real run, and save, export or share plans as a code.
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

### Live Capture, overlays and optimized presets

Windows setup selects **Download and install Npcap for Live Capture** by default. It downloads the current official installer separately; finish Npcap setup with **WinPcap API-compatible Mode** selected, then restart Aion 2 Calc. Scapy and LZ4 are included in desktop packages. Source installations need the dependencies in `pyproject.toml`; the native Windows overlay additionally requires pywebview and WebView2. macOS uses its system capture framework; Linux requires libpcap and capture permissions. The app offers capture setup when needed.

**Live Meter → Live Capture → Start** uses the built-in decoder, all available adapters in **Auto**, host **any**, and automatic game-port detection. Enter combat to establish a recognized game flow. Packet and event counters distinguish adapter/permission problems from unrecognized protocol traffic. Disable detection to use a known fixed port (initial value `50349`). Stop cancels recording and retains the last result for export; Quit closes capture and the overlay. Custom decoders are trusted Python `.py` imports whose code executes when capture starts.

The single overlay attaches to the AION 2 process on Windows, preserves its dragged offset, and remains available while waiting for the game. Tabs and the opacity slider are interactive; controls do not initiate dragging. Exclusive fullscreen behavior depends on the game and Windows compositor.

**Skills hotbar** shows suggested bindings. **Macro & rotation** shows numbered macro steps with matching keys and 10 ms delays. Charged skills are manual: hold their own key and release after charging. The optimizer fills all legally reachable skill-point allocations; points can remain only when no further purchasable level fits.

After optimization, eligible anonymous builds can improve the class presets used by the Planner. Updated presets are cached for offline use. Character identity and private equipment are not submitted with these build suggestions.

Windows **Install now** stages and validates the installer, starts a detached helper, closes the app, then opens the installer interactively after the process exits. Updates preserve user data. If the helper fails, its log is in the data folder's `updates` directory. macOS/Linux archives are staged for manual replacement.

### Raid plan publishing and playback

In **Raid Planner**, choose **Visibility** beside **Publish plan**: **Public** lists the plan in Browse plans; **Unlisted** shares it only by link; **Private** requires the secret link. The desktop uses the server and upload key from Settings. Publishing saves an owner credential on this device. **Update published plan** changes the same link; **Publish new copy** creates a separate plan. Keep a **Private ownership backup** to edit from another device. Import that backup through Import file. A revision conflict requires Refresh published plan before trying again; export local edits first. Clearing browser data without a backup loses editing access.

Combat logs containing recorded normalized positions offer **Open in Raid Planner** on desktop and Pages; the replay becomes a new local editable plan. Imported coordinates must already match the normalized arena. Live position decoding is not yet available.

Shared `/p/<id>` pages support **Play/Pause**, **Rewind**, playback speed and a timeline scrub bar with moving tokens and active buffs.

Live Meter uses one yellow **Start** / red **Stop** button. Under **Capture diagnostics**, enable TCP recording before Start, enter combat, then stop. The diagnostic ZIP saves automatically; the recorded payload count, saved path and ZIP download link remain visible. Use Export capture diagnostics for a manual archive. The Windows copy is also saved under `%LOCALAPPDATA%\aion2calc\diagnostics`; ordinary application logs do not contain TCP payloads. Export does not require decoded combat events.


## Community combat review

Combat Logs shows recent full sessions and the public community browser. Live sessions checkpoint every 15 seconds and save again on Stop. After a forced close, open the entry marked **unfinished checkpoint** to review or export the retained data. Capture restarts as a new session; up to the last 15 seconds plus disk-write time can be lost. Check **Capture diagnostics** for save errors. Snapshots use the selected Party / Self / All filter. Filter by encounter type, boss, difficulty, patch and region. Add missing classification using **Encounter metadata for comparisons** when opening a local session. Unknown metadata remains visible but cannot produce meaningful rankings.

Class summaries show DPS distributions, median, quartiles, range and sample counts for each matching encounter. Server and region ranks require recorded identity metadata; World means public submissions to this community, not every player worldwide. Personal records search by character name and server ID, or database character ID and server ID. Exact duplicate uploads count once.

Compare multiple local or public logs by choosing the encounter and each same-class player explicitly. Scores are recorded DPS, not adjusted for gear or capture completeness.

## Build points

**My Character** displays points spent and the optimization budget. Official profiles may omit unspent points. Enter the total from your in-game window (spent + unspent) for Skill, Stigma and PvE Daevanion before **Optimize my build**. Imported spend is a lower bound; it is not a verified character maximum. Planner budgets are configurable, including Daevanion. The bundled 203 / 30 / 360 preset describes an example simulation, not the total available to every character. Gear skill levels and PvP Daevanion points are separate from these budgets.

## Saved optimizations and advice

**Saved Results** reopens completed character/class optimizations and advice after restarting. Export a result JSON and import it on another installation. The latest older build and advice files are recovered automatically when available; overwritten historical files cannot be reconstructed. Advice is a snapshot from that run, so regenerate it when your gear or game data changes.

After character optimization, anonymous point observations update the community's highest observed totals by class, region, patch and source. View these under Combat Logs. User-entered totals and allocated profile lower bounds are labelled separately; neither establishes the game's maximum.

## PvP logs and leaderboards

In Live Meter, Stop and **Clear session** before switching between PvE and PvP. Choose a PvP encounter category: battleground, arena, Abyss, rift, open world or other. Use **Self** or **Party** scope. Capture preserves observed player combat, healing and death markers; known NPC damage and unidentified opponents are excluded from PvP session grouping. Start before entering the encounter so identity packets can be observed. Opponent names/classes appear only when decoded.

Enter the game patch, arena/encounter name and difficulty/ruleset for useful comparisons. Community Combat Logs and Pages leaderboards separate PvP from PvE, with DPS, HPS and damage-taken rate selections. Damage-taken rate is a recorded amount, not a higher-is-better performance grade. Healing or deaths with no matching marker remain unavailable in community statistics. Table, timeline, events, graph, splits, pets and replay controls use the same supported event data as PvE.

Match outcomes, objective scores, kill credit, faction/team assignments outside the observed party, and movement not present in the log are not inferred. Mode selection is manual; entering a PvP area does not automatically prove a recording is PvP. A fresh PvP capture is still needed to confirm arena/battleground coverage.

## For developers

The command-line interface, running from source, the architecture overview, building the desktop
app, testing, releasing and adding a class are in **[`docs/cli.md`](docs/cli.md)**. Formulas,
sources and every assumption are in [`docs/methodology.md`](docs/methodology.md).

## Author

**Spirited - Zikel : Asmodian | Legion: WhaleWatch**

## License

GPL-3.0 (see `LICENSE`).  Game data belongs to NCSOFT; community data belongs
to its respective sites.  This project is fan-made and not affiliated with NCSOFT.
