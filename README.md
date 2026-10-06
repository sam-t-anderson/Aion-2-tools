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

## For developers

The command-line interface, running from source, the architecture overview, building the desktop
app, testing, releasing and adding a class are in **[`docs/cli.md`](docs/cli.md)**. Formulas,
sources and every assumption are in [`docs/methodology.md`](docs/methodology.md).

## Author

**Spirited - Zikel : Asmodian | Legion: WhaleWatch**

## License

GPL-3.0 (see `LICENSE`).  Game data belongs to NCSOFT; community data belongs
to its respective sites.  This project is fan-made and not affiliated with NCSOFT.

### Live Capture, overlays and optimized presets

Windows setup selects **Download and install Npcap for Live Capture** by default. It downloads the current official installer separately; finish Npcap setup with **WinPcap API-compatible Mode** selected, then restart Aion 2 Calc. Scapy and LZ4 are included in desktop packages. Source installations need the dependencies in `pyproject.toml`; the native Windows overlay additionally requires pywebview and WebView2. macOS uses its system capture framework; Linux requires libpcap and capture permissions. The app offers capture setup when needed.

**Live Meter → Live Capture → Start** uses the built-in decoder, all available adapters in **Auto**, host **any**, and automatic game-port detection. Enter combat to establish a recognized game flow. Packet and event counters distinguish adapter/permission problems from unrecognized protocol traffic. Disable detection to use a known fixed port (initial value `50349`). Stop cancels recording and retains the last result for export; Quit closes capture and the overlay. Custom decoders are trusted Python `.py` imports whose code executes when capture starts.

The single overlay attaches to the AION 2 process on Windows, preserves its dragged offset, and remains available while waiting for the game. Tabs and the opacity slider are interactive; controls do not initiate dragging. Exclusive fullscreen behavior depends on the game and Windows compositor.

**Skills hotbar** shows suggested bindings. **Macro & rotation** shows numbered macro steps with matching keys and 10 ms delays. Charged skills are manual: hold their own key and release after charging. The optimizer fills all legally reachable skill-point allocations; points can remain only when no further purchasable level fits.

After character optimization, anonymous allocations and rotation are sent to the configured server. The server resimulates them with common level-45 median gear and budgets (203 skill / 30 stigma / 360 Daevanion), compares against both the current Planner build and its saved class preset, and saves only improvements. It receives no character identity, private loadout names or gear. Higher-budget builds are rejected rather than unfairly compared. On launch, updated presets appear first in the Planner selection and remain cached offline.

Windows **Install now** stages and validates the installer, starts a detached helper, closes the app, then opens the installer interactively after the process exits. Updates preserve user data. If the helper fails, its log is in the data folder's `updates` directory. macOS/Linux archives are staged for manual replacement.

### Troubleshooting capture and updates

If TCP packets arrive but no combat data appears, enable **Live Meter → Record TCP payloads for diagnostics** before **Start**, fight briefly, then **Stop**. Opted-in TCP diagnostics save automatically on Stop (also before another Start and on normal Quit); **Export capture diagnostics** offers a manual export. The ZIP is saved to `%LOCALAPPDATA%\aion2calc\diagnostics` on Windows (`~/.aion2calc/diagnostics` elsewhere). It contains status/candidate-flow metadata and, only when recording was enabled, original TCP segments with timestamps and sequence numbers. The newest 4 MiB / 4096 records are retained. Raw traffic can contain character names, IP addresses and other traffic; review before sharing. No automatic upload occurs. A metadata-only ZIP can be exported without enabling payload recording.

The application status log is `%LOCALAPPDATA%\aion2calc\aion2calc.log`; update handoff scripts/logs are under `%LOCALAPPDATA%\aion2calc\updates`. A plain `apply-update.ps1` is from an older version; newer helpers are named `apply-update-<id>.ps1` and log readiness, installer launch or failure. Two downloaded release packages are retained; older packages are removed after a successful staging step. Helper logs are preserved.

Windows setup leaves Npcap checked by default when missing. If its service is already installed, the checkbox is disabled and unchecked, and Npcap setup is skipped.

### Raid plan publishing and playback

In **Raid Planner**, choose **Visibility** beside **Publish plan**: **Public** lists the plan in Browse plans; **Unlisted** shares it only by link; **Private** requires the secret link. The desktop uses the server and upload key from Settings. Publishing creates a new shared copy; to make an older unlisted plan public, open it, select Public, and publish again.

Shared `/p/<id>` pages support **Play/Pause**, **Rewind**, playback speed and a timeline scrub bar with moving tokens and active buffs on server 0.2.4 or later. Existing shared links get these controls after the server is updated.

Live Meter uses one yellow **Start** / red **Stop** button. Under **Capture diagnostics**, enable TCP recording before Start, enter combat, then stop. The diagnostic ZIP saves automatically; the recorded payload count, saved path and ZIP download link remain visible. Use Export capture diagnostics for a manual archive. The Windows copy is also saved under `%LOCALAPPDATA%\aion2calc\diagnostics`; ordinary application logs do not contain TCP payloads. Export does not require decoded combat events.

### Live combat history and party scope

Live Meter defaults to **Self + Party**. Enter **My character** before Start when attaching mid-session; the name is remembered locally and matched only to a unique observed player. Decoded party rosters identify party members. **Self only** hides everyone else; **All observed players** explicitly includes nearby players. Capture retains data while identity is pending and explains why the filtered view is empty.

Fighting enemies within **Group combat within** (10 seconds by default) forms a single segment. The **Combat** selector shows earlier fights or the whole session. Segment data survives inactivity, zone changes and Stop/Start within the app; **Clear session** explicitly removes it. Export/upload includes the retained segments. Save or export before quitting. The history limit is 400,000 records / 200 displayed segments.

The **Enemies** table selects a target for the **Players** meter. Accuracy reports decoded outgoing hit flags; Defense reports received damage, parried hits and attackers. Getting hit alone cannot determine hit chance, avoided attacks, armor or mitigation percentages. Creature names come from captured entity-to-NPC-type mappings plus the included creature database; a missing spawn record leaves an honest unknown entity label.
