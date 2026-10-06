# Combat logging iterations

## Iteration 1 — 0.2.16

- Show verified automatic local identity. The optional name override is for captures started after the identity packet. Combat entity IDs change between instances; roster database character IDs and server IDs are retained separately when observed.
- Add **Split now** and **Automatic splits**. Automatic grouping uses the configurable idle gap; manual splits take effect on the next damage event.
- Add **Hide overlay**; Open overlay restores it.
- Save full decoded party sessions locally on Stop/normal Quit and show **Combat Logs → Recent full sessions**. TCP ZIPs remain bounded troubleshooting captures, not full dungeon recordings.
- Use one desktop, Pages and server viewer: Summary, Damage Done, Damage Taken and Healing; Table default, Timeline and Events; visibility toggles; actor/server labels; enemies below the graph; effect/death markers; recorded HP lines; class color controls; supported pet ownership; basic local/public log comparisons.
- Retain healing recipients only when explicitly decoded. Deaths use explicit death markers; absent markers do not prove survival. Skills on the timeline are recorded effects, not inferred cast starts.
- Accept verified normalized positions in imported a2logs, play those back and export a raid-plan file. **Live movement decoding remains unimplemented.**
- Keep the Pages banner, navigation links and theme button consistent on every page. Open public Logs and Leaderboard entries in the Pages viewer.
- Retain optional a2log event fields when uploading.

## Iteration 2 — 0.2.17 — community comparison and ownership

- Encounter-type filters: Transcendence dungeon, daily dungeon, expedition, ascension trials, nightmare and sanctuary raids, plus Unknown for logs without reliable classification. Record type, difficulty and game patch on upload; preserve them in local history and server indexes.
- A class-performance summary on desktop Combat Logs and Pages: distributions/box plots, median, quartiles, range and parse counts for the selected patch and encounter category. Expose data coverage; do not combine unrelated bosses, difficulties or patches into a misleading balance ranking.

- Player/run ranks by server, region and all submitted public community logs. Match boss, difficulty and patch, and report sample sizes; do not claim the dataset covers every player worldwide.
- Personal-record search/history using verified database character ID or name plus server.
- A dedicated comparison workflow with selectable matching players, encounter filters and multiple runs. Iteration 1 provides basic recorded-DPS comparisons.
- Edit published raid plans using locally stored owner credentials and authenticated updates that preserve the shared link. Add credential backup/import; author names must not grant ownership.

Implemented: encounter metadata and local filters; shared community browser; separate class distributions and public rankings; personal record search; explicit multi-run comparison; authenticated plan updates with ownership backups. Classification is manually supplied when the capture cannot verify it. Rankings are recorded DPS, not gear-adjusted, and World covers community submissions.

Build-point follow-up: correct the imported Daevanion denominator, remove the invented extra stigma point, expose all character point budgets as editable totals, and label imported resources as observed lower bounds. Automatic verification of unspent points remains dependent on profile/capture evidence. Edited totals persist per character; anonymous observations update highest-observed resources by class/region/patch/source. Saved Results preserves optimizer and advice snapshots with export/import.

## Iteration 3 — protocol and replay enrichment

- Decode verified boss positions/movement and connect directly to Raid Planner import. Establish coordinates, map and arena transform first.
- Extend healing-recipient, pet-ownership and player-death coverage against representative captures.
- Refresh trusted creature metadata, retain observed type IDs and review unknown IDs. Future game/protocol updates cannot be guaranteed to supply names.
- Add supported casts, buffs, debuffs and resources as evidence permits. Unobserved threat, interrupts, mitigation and misses remain unavailable.
- Add periodic disk checkpoints and crash recovery. Iteration 1 saves on Stop/normal Quit; forced termination can lose the active session.

### Checkpoint 3A — retained sessions and replay handoff

Implemented: atomic periodic session snapshots every 15 seconds, final save on Stop, unfinished-session labels and reopening from Combat Logs; direct local Raid Planner import for recorded normalized movement on desktop and Pages; incoming healing retains explicit recipient references across scope filtering; healing does not bridge automatic or manual encounter splits; pet-reference cycle protection during export. README developer/author/license sections now follow player documentation.

Still pending in checkpoint 3:
- Verified live positions, coordinate encoding, map IDs and arena transforms. Upstream recognizes the position opcode for zone changes but does not decode its coordinates. Imported normalized replay support does not establish live movement support.
- Additional representative healing, pets and player-death evidence, especially full decoded sessions rather than bounded TCP diagnostics.
- Trusted creature metadata refresh and a review workflow for unknown type IDs.
- Verified cast/buff/debuff/resource packet formats. Recorded damage/healing effects are not cast-start records.

Recovery reopens the last saved a2log as a historical session; it does not resume a lost TCP stream or concatenate a new capture into that historical session. Save errors remain visible under capture diagnostics. The selected scope applies to snapshots, and existing event/identity limits still apply.

## Last priority — only after iterations 1–3 are complete

- PvP tracking with the same supported combat metrics and dedicated leaderboards for battlegrounds, arenas, Abyss, rifts and other verified modes. Separate PvP from PvE datasets and rankings.
- A server-local dashboard/domain for service health, capture/upload/error counts, logs by encounter/PvP type, storage and job metrics, build performance, class/player insights and data-quality coverage. Keep administrative operations authenticated and local/private by default; choose the host/domain when implementing it.

## PvP and server metrics — started at user request before protocol follow-ups

Implemented: explicit PvP categories, roster-based capture scope, known-player combat filtering, separate public PvE/PvP DPS/HPS/DTPS comparisons and records, and exclusion from PvE calibration. Existing supported combat review metrics remain available. New PvP packet formats, match results/objectives/kill credit and automatic mode detection remain unverified.

Server: authenticated private LAN dashboard on port 24662, persistent UTC-day request/error/latency and preset-outcome counters, storage/process health, retained upload counts by type/visibility/day, missing-metadata coverage, simulated presets and public class/player insights. See the server README for access and administration. Client capture errors and actual build-to-combat-performance attribution remain unavailable.

### Upload-time character builds (0.2.20)

Shared desktop/Pages combat review opens saved character profiles for friendlies and identified PvP opponents. Server enrichment uses fresh official public profiles, with immutable upload/fetch timestamps and explicit unavailable states. Current local previews are separate. Actual PvP packet coverage, automatic mode/team/objective detection and accurate encounter-time gear require further evidence; upload-time profiles cannot establish exact gear used in earlier combat.
