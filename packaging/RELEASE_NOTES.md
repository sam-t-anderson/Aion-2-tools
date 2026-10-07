# Aion 2 Calc 0.2.33

- Show timeline marker details in a visible panel on hover, click or keyboard focus; explain unavailable comparison ranks instead of relying on hidden tooltips.

- Let combat-review users supply a missing character home server and region for a current official profile preview. Manual previews remain separate from upload-time historical snapshots. Pages and server views require server 0.2.18. Show PvP timing without unrelated boss-progression/speed tables.

- Upload Live Meter logs as a background job using a detached session copy. Prepare summaries outside the capture lock so uploads do not monopolize packet decoding; expose upload progress and restore controls after failure.

- Add separate **Optimize PvE build** and **Optimize PvP damage (experimental)** actions. Save PvP results separately and identify their model in reports and recovered results.
- The PvP damage proxy excludes PvE/boss bonuses and PvE calibration. It compares sustained and burst damage against a stationary neutral player target; it does not predict survivability, crowd control, movement, opponent mitigation or win chance. Dedicated PvP progression and verified PvP skill coefficients remain pending.
- Keep experimental PvP results out of PvE community presets.
- Add Live Meter action progress, disabled buttons during requests and completion/error notifications for exports, uploads, screenshots, splits, run completion and overlay controls. Export confirmation includes the saved path.

# Aion 2 Calc 0.2.32

- Remove the live TCP diagnostic record-count and size caps. Stream the complete opted-in session to disk and export ZIPs without loading the full recording into memory.
- Show diagnostic disk usage and recording failures. Preserve raw recordings after a crash or failed export; remove temporary raw files after a successful stopped-session archive.
- Update capture documentation. Available disk space limits recording; long captures take longer to compress. Decoded combat-history limits are unchanged.

# Aion 2 Calc 0.2.31

- Fix shared combat timelines under the server Content Security Policy by drawing markers with SVG attributes instead of blocked inline styles. Correct incoming-damage lanes and independent healing visibility, add a time scale, and restore Timeline when its view button is selected.

- Add skill-specialty recommendations to Gear & Advice without requiring combat logs: effect descriptions, selection numbers, effective levels and unlock requirements, plus automatic stigma effects.
- Save specialty snapshots with calculated advice and optimizer/current-build JSON. Older advice remains readable and explains when recalculation is needed.
- Show effect unlock levels and next thresholds in the optimizer Skills screen and copyable setup.
- Clean invalid specialty choices before each optimizer specialty search after gear/level changes. Use each skill's effect requirements separately from the existing selection-slot level gates, confirmed by the user for this iteration.

# Aion 2 Calc 0.2.30

- Add private report forms to shared combat logs on desktop, Pages and server views, with receipt numbers and clear unverified-report labels.
- Show moderator hold reasons in My uploads and pause visibility/link changes during review; owner deletion and desktop review remain available.
- Pair with server v0.2.16 for private human moderation. Reports never automatically remove a log. Releasing a hold leaves it private for the owner to republish.
- Keep report drafts and submission state through viewer redraws. Original uploads, credentials and downloaded copies remain subject to existing privacy limits.

## 0.2.29

- Fix Npcap installer launch failing with WinError 740: request Windows administrator approval through the normal runas/UAC installer flow.
- Check installation via read-only service registry detection, without starting sc.exe or elevating the application. Unknown detection is shown separately from not installed.
- Explain denied/cancelled UAC approval and distinguish an installed driver from capture access permissions.
- Includes the My uploads ownership/privacy controls from 0.2.28.

## 0.2.28

- Add My uploads to desktop Combat Logs, Pages Logs/shared review and the server viewer: refresh privacy status, change visibility, rotate private links, delete uploads, and back up/import per-upload credentials.
- Save credentials automatically for new desktop/CLI uploads outside public combat files. Desktop storage persists independently of the webview port; browser storage is local to each site/browser. Recover older uploads with their original delete credential.
- Require per-upload credentials for combat-log management. Shared upload keys no longer read private combat logs or authorize deletion. Private view links grant viewing only.
- Update ranking/deduplication indexes when privacy changes, remove private logs from legacy calibration, and disable future HTTP caching for mutable combat-log responses. Privacy cannot recall already downloaded copies or old cached responses.
- Lost original credentials cannot be recovered from a character name or shared upload key. Character identity verification and richer PvP evidence remain pending.

## 0.2.27

- Add optional Encounter insights to shared desktop, Pages and server combat review: healer/recipient pairs, imported buff uptime, observed ability effects and opening sequences, and sampled boss HP milestones.
- Merge overlapping imported buff windows, clip them to encounter duration, expose missing healing attribution and bounded detail omissions. Preserve separate pet sources.
- Recompute insights from retained evidence for local files, saved sessions and shared archives. No cast counts, named mechanic phases, effective healing, support damage credit or cooldown/rotation verdicts are inferred.
- Live cast/buff/resource and movement decoding still require representative protocol evidence.

## Changes in 0.2.26 — death recaps and character trends

- Add a Death recaps tab on desktop, Pages and shared logs, showing up to 10 seconds of recorded incoming damage, received healing and HP before explicit player death markers.
- Show relative event times, last observed incoming hit, latest HP timestamp, short-window and density-limit notices. Unknown killing blows, mitigation and defensives are never inferred.
- Correct pet deaths being added to owner death counts; deduplicate identical player death markers. No markers is labeled explicitly rather than claiming a deathless recording.
- Add Character consistency and trends after personal-record search: matched completed-boss rates, median/range, standard deviation, median absolute deviation, relative variation and upload-ordered history.
- Variation requires 5 matched recordings; recent-five versus previous-five trends require 10. Cap warnings suppress variation/trends.

Updated server v0.2.13 provides community trends and recomputed recaps for older shared logs. Recaps are limited to 200 per session and the last 200 effects/HP samples per window; totals include omitted effects. Split boundaries can shorten windows. Missing healing recipients, HP and death markers remain unavailable. Public trends exclude unranked captures/wipes under the current eligibility policy and do not prove improved play: gear, teammates and fight lengths can differ. Existing capture, PvP and gear-evidence limits remain.

## Changes in 0.2.25 — matched comparisons and historical percentiles

- Show current same-patch and reconstructed at-upload standings side by side in desktop, Pages and shared combat review, including run speed.
- Match player comparisons by boss, class, encounter category, patch, difficulty, observed party size and instance. Keep personal bests and class distributions separate by party size/instance too.
- Add party-size filters to community browsing and the Pages leaderboard; replace the leaderboard's cross-cohort row number with matched cohort rank.
- Show percentile availability, public sample counts, distinct identities and provisional local/private comparisons. Percentiles need at least 10 samples and five distinct characters, or five distinct parties for run speed. Capped datasets do not receive a percentile.

Requires server v0.2.12 for the new comparison fields. At-upload standings are reconstructed from currently public retained uploads received by that time; deletion, visibility and policy changes can change them. Current means current samples from the log's patch, not comparison with a newer patch. Ties share midrank percentiles. Small-sample class quartiles remain descriptive and show coverage warnings. HPS depends on healing demand; damage taken is descriptive, not a performance ranking. Upload-time gear cannot establish encounter-time equipment, so gear-adjusted brackets remain unavailable. Unknown party/instance evidence has no formal percentile. Existing capture and PvP evidence limits remain.

## Changes in 0.2.24 — run timing and boss progression

- Review each recorded run independently in desktop, Pages and shared logs: recorded span, encounter time, gaps and verified entry-to-final-boss elapsed time when available.
- Show recorded boss attempts, kills, observed wipes, unknown outcomes, attempts to first recorded clear, best observed wipe HP and recovery gaps.
- Join unresolved manual chunks of the same boss actor instead of counting each split as another pull.
- Add public completed-run speed tables and boss progression summaries with the updated server. Speed comparisons match instance, boss route, patch, difficulty and party size; duplicate recordings count once.
- Preserve observed instance-entry times and stable party-roster evidence for future captures.

Speed eligibility requires an observed open-world-to-instance transition, configured final-boss completion, a stable identified party and complete capture evidence. Captures started inside an instance and manual finishes remain reviewable but unranked for speed. Unknown outcomes are not wipes; missing HP/death markers are unavailable. Encounter time is the union of recorded fight intervals, not action uptime. Existing bounded-history limits and unverified PvP boundaries remain.

## Changes in 0.2.23 — capture quality

- Show capture-quality status and exclusion reasons in the shared desktop, Pages and server combat viewer.
- Preserve decoder/application versions, capture scope, retained-history losses, validation losses, capture failures and observed TCP reassembly losses in exported sessions.
- Preserve recent pre-pull boss HP evidence to distinguish a captured start from joining a fight partway through.
- With the updated server, only sufficiently complete Party boss captures qualify for rankings, class distributions and personal bests. Other recordings remain available for review and personal history.
- Show duplicate-public-upload status and rank eligibility alongside community logs and history.

Older captures and PvP matches lack verified completeness evidence and remain unranked. These checks do not establish authenticity or guarantee every packet was captured. Server duplicate matching is conservative; ambiguous or incomplete captures may remain separate.

## Changes in 0.2.22 — distinct fight identities

- Keep split IDs unique when multiple PvE/PvP fight groups start in the same decoded packet, preserving correct encounter selection in live review.
- Includes the run-boundary functionality introduced in 0.2.21; its evidence and retention limits still apply.

## Changes in 0.2.21 — run boundaries

- Retain run IDs, completion/boundary reasons, map and dungeon IDs inside multi-fight captures; select a run on desktop and Pages.
- Add Finish run without stopping capture, plus automatic completion for configured final-boss NPC IDs with observed deaths and matching dungeon context.
- Separate observed damage against identified players from PvE fights, including mixed open-world captures; unknown actors are not guessed to be PvP opponents.
- Separate confirmed open-world maps from unverified PvE/PvP sources.
- Keep boss death markers that arrive shortly after the final damage; checkpoint changed run boundaries immediately.
- Reuse identified player references across actor resets when character server/name or database identity is available.

Final-boss order and PvP match-end packets remain unverified. No final-boss rule is enabled without supplied NPC IDs. Existing retained-history limits still apply.

## Changes in 0.2.20 — character builds in combat logs

- Recover structured advice from `advice.json` and upgrade existing recovered text entries, restoring the same interactive Gear & Advice panels without recalculating.
- Click friendly characters and identified PvP opponents to view saved official gear/build profiles in desktop and Pages.
- Show equipment, skill/stigma levels, available item/Daevanion details and profile JSON export.
- Preserve upload/fetch timestamps and pending/partial/unavailable states; historical snapshots are never silently replaced with current gear.
- Add an explicit current-profile preview for local desktop logs. It does not modify historical logs.

Official identity must resolve uniquely. Profiles reflect fetch time, not guaranteed encounter-time equipment; older logs are not backfilled with today's gear.

## Changes in 0.2.19 — PvP tracking

- Add explicit battleground, arena, Abyss, rift, open-world and other PvP categories.
- Use Self/Party scope for PvP and exclude known NPCs/unidentified opponents from session grouping. Clear session when changing between PvE and PvP.
- Separate PvE/PvP community reports and Pages leaderboards, with DPS/HPS/damage-taken rate filters and personal records.
- Preserve identified opponent classes in logs and reuse supported timeline, event, healing, damage-taken and death views.

PvP mode is manually selected. Match outcomes, objectives, kill credit and automatic mode detection are unavailable. Additional PvP captures are needed to confirm coverage. The updated share server supplies the new report metrics; the dashboard and server administration are documented only in the server repository.

## Changes in 0.2.18 — checkpoint 3A

- Save live sessions atomically every 15 seconds and on Stop. Interrupted sessions remain under Combat Logs as unfinished checkpoints for review/export; new captures start independently.
- Retain explicit incoming healing recipients across party filters without letting regeneration join encounters or bypass manual splits.
- Protect export against cyclic pet-owner references.
- Open normalized recorded movement directly in Raid Planner from desktop and Pages as a new local plan.
- Move developer, author and license information to the end of the client README.

Live movement coordinates, new cast/buff/resource protocol coverage and trusted creature metadata refresh remain pending in `docs/COMBAT_ROADMAP.md`. Checkpoints retain the selected scope and existing history limits; up to 15 seconds plus save time can be lost on forced termination.

## Changes in 0.2.17 — community review and plan ownership

- Filter community and recent local logs by encounter category; record game patch, difficulty and region for comparisons.
- Show separate class DPS distributions and parse counts, public server/region/community rankings, and personal record history. Unknown metadata remains unranked.
- Compare multiple runs with explicit same-class player and encounter selection.
- Update published raid plans in place using locally saved ownership credentials; export/import private ownership backups and detect revision conflicts.
- Show imported point budgets correctly and let users enter actual skill, stigma and PvE Daevanion totals, including unused points. Remove the invented extra stigma point.
- Save completed optimizer/advice results across restarts, with export/import and recovery of existing older files.
- Persist edited point budgets per character and update anonymous community highest-observed resources after optimization.
- Keep player guides in this repository and hosting/administration guidance in the server repository.

## Changes in 0.2.16 — combat review iteration 1

- Show automatic character detection with server and changing combat entity ID; keep an optional name override.
- Add Split now, an Automatic splits toggle, and Hide overlay controls.
- Save full party sessions on Stop/normal Quit and show Recent full sessions in Combat Logs.
- Share a Summary/Damage Done/Damage Taken/Healing viewer across desktop, Pages and server: Table/Timeline/Events, graph/timeline visibility, actor/server labels, enemy encounters, class colors, known pet ownership and basic comparisons.
- Retain explicit death markers, HP samples and supported healing recipients. Timeline markers represent effects; missing data is labeled unavailable.
- Keep every Pages banner/navigation menu consistent and open public logs within Pages.
- Play verified positions from imported logs and export a raid plan. Live movement decoding, community ranks/personal records, editable published plans and creature-mapping updates remain in later iterations: `docs/COMBAT_ROADMAP.md`.

Existing logs remain readable.

## Changes in 0.2.15

- Retain live combat history independently of the protocol engine's idle and zone resets. Nearby pulls within a configurable gap (default 10 seconds) form one combat segment. Choose Latest combat, an earlier combat, or Whole session; history remains through Stop/Start until Clear session or application exit. Export/upload preserves all retained combat segments, rather than only the currently selected enemy. History is bounded to 400,000 decoded records and 200 displayed/exported segments.
- Default to Self + Party filtering, with explicit Self only and All observed players options. Party membership comes from decoded rosters, not merely proximity. If identity is unavailable, preserve the captured records and display a warning rather than treat strangers as party members.
- Bind an explicitly entered character name to a unique observed identity, case-insensitively, and remember the input locally. This resolves the attached capture's `spirited` actor without guessing from highest damage.
- Read NPC spawn and HP metadata inside compressed packets and merge partial updates so known creature database IDs/names are not erased by a later partial record. Unknown types retain their entity ID instead of a guessed creature name.
- Separate Players and Enemies in Live Meter; select an enemy to see per-player damage against it. Keep the selected player stable as damage ranks change.
- Populate Accuracy with decoded crit, back/front, double, perfect, multi and parry rates. Populate Defense with incoming damage, hits, parries and attacker breakdowns. Accept NPC attack skill IDs directed at verified players. Hit chance, dodge and mitigation percentages remain unavailable when attempted attacks or pre-mitigation values are absent.
- Reuse loaded skill-image nodes during polling and use a fixed-size fallback when an icon is unavailable. Unchanged snapshots no longer rebuild the meter graph.
- Automatically save opted-in TCP diagnostics to a ZIP when capture stops, including capture errors, before another Start replaces the buffer and on normal Quit. Show the last saved file path and download link; repeated Stop calls reuse the saved archive. Earlier versions kept each recording in memory until Export, so recordings replaced by another Start cannot be recovered from that buffer.

Enter your character name in Live Meter before Start if you attach after login or a zone load. Stop and export before Clear session or quitting if you want to retain a file. The latest attached solo sample confirms self filtering and incoming NPC damage; a separate party sample is still needed to confirm roster decoding for that run.

## Changes in 0.2.14

- Choose Public, Unlisted or Private next to **Publish plan** in the website and desktop Raid Planner. Public plans appear in Browse plans; unlisted plans are accessible by link; private plans require the secret link. The choice is saved with each local plan. Publishing creates a new shared copy; existing links retain their original visibility.
- Connect desktop plan publishing and browsing to the share server configured in Settings, including its upload key.
- Replace Live Meter's separate Start/Stop controls with one button: yellow Start, red Stop while running.
- Make TCP diagnostics prominent, display the number of recorded payloads, and keep export results visible during polling. Export offers a direct ZIP download as well as the saved file path.
- Exclude Ethernet padding from TCP payloads so padding on ACK packets cannot advance reassembly or corrupt framed messages. Resume game-flow detection after an idle/disconnected socket, including a FIN/RST in the opposite direction. A stopped user capture produced 24 combat events in offline analysis after excluding its padding; live game capture still needs confirmation with this release.


## Changes in 0.2.13

- Close the desktop's dedicated Chromium profile even when its launcher handed the window to an existing browser process. Explicit Quit/update exits the packaged process after server/capture cleanup so solver exit hooks cannot block the installer. Update helper logs now record readiness immediately.
- Keep the two most recent update packages, including the staged installer; retain helper scripts and logs for troubleshooting.
- Disable and uncheck the Npcap install task when its Windows service already exists, and skip launching its installer if detected at the final install step.
- Remove color-key hit-test transparency from the overlay. The compact dark host uses window alpha, so tabs, dragging and the opacity slider remain interactive.
- Add optional bounded TCP diagnostic recording before game-port selection and an **Export capture diagnostics** button. ZIPs are saved under the data folder's `diagnostics` directory. Nothing is uploaded automatically. Use this to investigate TCP packets arriving without recognized combat events.

To collect a packet sample: in Live Meter enable **Record TCP payloads for diagnostics** before Start, fight briefly, press Stop, then **Export capture diagnostics**. The newest 4 MiB / 4096 records are retained. Raw payloads may include names, IP addresses and other captured traffic; review before attaching. Existing application logs do not contain TCP payloads.

## Changes in 0.2.12

- Live Capture monitors all available adapters in Auto mode and detects the game port from combat traffic. Adapter names and packet/event counters explain whether traffic is reaching the decoder. A fixed port can still be selected by turning off detection.
- Custom decoders are imported from a trusted `.py` file. Combat variant IDs now map to base skill icons, with graceful display when an asset is unavailable.
- The overlay keeps its tabs and opacity controls stable, fits its content without scrollbars, clears the native Windows host background and hides its taskbar entry. It follows the AION 2 executable specifically and preserves your dragged position. Opening it again reuses the existing overlay.
- Stop cancels capture and replay; Quit closes the app and overlay. Windows updates acknowledge the detached helper before closing, wait for the app to exit, and verify downloaded installer size/digest when provided. Helper failure details are saved under the data folder's `updates` directory.
- Skills hotbar and Macro & rotation now share named skills, icons and key bindings. Charged skills stay manual in both macro layouts; estimates assume you hold their own key to charge. The optimizer spends remaining skill points on reachable legal levels, including utility skills.
- Optimized character allocations and rotation are submitted anonymously to the configured server. It recomputes DPS against the current Planner and stored preset using the same level-45 median gear and budgets (203 skill / 30 stigma / 360 Daevanion), stores only improvements, and discards other submissions. Character names, loadout paths, gear and claimed scores are excluded. New launches refresh class presets while retaining an offline cache.
- The desktop opens maximized with roomier content, uses **Aion 2 Calc** branding and prompts for available updates on launch. Windows Npcap setup is selected by default.

Validation includes unit/integration tests and packaged startup checks in CI. Actual game capture and visual transparency still need confirmation on a machine running AION 2; this development environment could not render a minimal WebView2 test window.

## Download

| Your computer | File |
|---|---|
| **Windows** (recommended) | `aion2calc-setup-<version>.exe`: run it, then start **Aion 2 Calc** from the Start menu |
| Windows, no install | `aion2calc-<version>-windows-portable.zip`: unzip anywhere, run `aion2calc.exe` |
| macOS | `aion2calc-<version>-macos.zip`: unzip and open `aion2calc.app` (see below the first time) |
| Linux | `aion2calc-<version>-linux.tar.gz`: unpack, run `aion2calc/aion2calc` |

## Live Meter capture setup

The built-in A2Tools Live Meter captures the game's network traffic and needs the operating
system's packet-capture support. On Windows, the installer offers a preselected **Download and
install Npcap for Live Capture** choice. Selecting it fetches the newest official Npcap installer
from `npcap.com`; select **WinPcap API-compatible Mode** during Npcap setup. The Live Meter also
asks before downloading Npcap if it is still missing.

macOS already includes its packet-capture framework. Linux uses the distribution's `libpcap`
package; install it with your package manager and grant the account permission to capture packets
before using Live Capture. The desktop app explains the missing capture prerequisite instead of
silently attempting a privileged installation.

The compact overlay is a single transparent, always-on-top window. It follows the Aion 2 game
window when it is running, closes with aion2calc, and its opacity slider no longer moves the overlay.

The app opens in its own window (Edge or Chrome app mode, or your browser) and follows your system's
light or dark mode. It needs no Python and no command line. Your data stays on your computer, in
`%LOCALAPPDATA%\aion2calc` on Windows (`~/.aion2calc` on macOS and Linux). Updating or uninstalling
the app keeps it.

The builds are not code-signed, so the first launch may need one extra click. Windows SmartScreen
("Windows protected your PC"): choose **More info → Run anyway**. macOS ("cannot be opened"): open
**System Settings → Privacy & Security** and choose **Open Anyway** next to the aion2calc message.

[Code signing policy](https://github.com/sam-t-anderson/Aion-2-tools/blob/main/docs/code-signing.md). Installing and updating:
[docs/install.md](https://github.com/sam-t-anderson/Aion-2-tools/blob/main/docs/install.md).
