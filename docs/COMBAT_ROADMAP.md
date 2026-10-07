# Combat logging iterations

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


## Insights roadmap — checkpoint 1 (0.2.23)

Implemented capture-quality reasons, Party encounter ranking eligibility, bounded-history/validation/TCP loss evidence, public cross-uploader duplicate grouping and operator counts. Incomplete and legacy captures stay reviewable; PvP boundaries remain unverified and unranked. Duplicate matching requires identical outgoing damage, stable player identities and anchored encounter time; partial/ambiguous matches are intentionally not merged. Quality uses submitted telemetry, not authenticated game records.

## Insights roadmap — checkpoint 2 (0.2.24)

Implemented per-run timing/progression, conservative observed wipes, best wipe HP, recovery gaps and matched public run speed rankings. Unknown attempts remain separate; manual chunks sharing an unresolved boss actor are joined. Speed eligibility requires observed entry, configured final-boss completion, stable identified party and no known capture loss. Public duplicate run/attempt samples count once. Existing bounded-history limits still apply; no unlimited archive or verified PvP match boundaries are claimed.

## Insights roadmap — checkpoint 3 (0.2.25)

Implemented observed party-size/instance cohorts for player comparisons, class distributions and personal bests; current same-patch and reconstructed at-upload standings for players and run speed; minimum sample/distinct identity gates, cap warnings, tie-aware empirical percentiles and provisional labels. Community and Pages filters expose party size. Historical reconstruction uses currently public retained uploads, not immutable snapshots. Gear brackets remain unavailable until encounter-time gear is reliable; upload-time profiles are insufficient. No cross-patch normalization is inferred.

## Insights roadmap — checkpoint 4 (0.2.26)

Implemented bounded explicit-player-death recaps with observed damage/healing/HP, relative timestamps, missing-evidence/short-window notices and no inferred killing blows. Pet deaths no longer count as owner deaths; identical markers are deduplicated. Shared desktop/Pages personal search shows matched public completed-boss consistency and recent-five/previous-five trends, minimum sample gates, capped history and descriptive caveats. Wipes remain reviewable with recaps but unranked for these public rate trends. Avoidable damage, defensives and causal improvement require further protocol/encounter evidence.

## Insights roadmap — checkpoint 5 (0.2.27)

Implemented optional shared Encounter insights: healing source/recipient relationships and missing attribution, merged/clipped imported buff uptime, ability effect counts and first/last times, bounded opening effect sequences and first sampled boss HP thresholds. Local validation/saved sessions and protected server/raw views recompute from retained evidence. Details and omissions are bounded and visible; pets retain distinct sources. No effect count is labeled a cast, no HP threshold is named a mechanic phase, and no effective-healing/support-credit or optimal-rotation verdict is inferred.

Pending evidence for phase/support/rotation enrichment: verified cast-start/end, buff source/application/removal, resources, shields/overheal and encounter mechanic definitions. Live movement and richer PvP protocol evidence remain pending. Imported windows do not establish live decoding support.

## Insights roadmap — checkpoint 6 (0.2.28)

Implemented per-upload ownership retention on desktop/CLI, shared My uploads management on desktop/Pages/server views, current status, visibility changes, private-link rotation, deletion, private credential backups/import and recovery with original delete tokens. Shared upload keys no longer read private combat logs or delete logs. Privacy changes reindex reports and exclude private calibration; mutable responses use no-store. This is upload ownership, not proof of character identity. Existing downloads/caches cannot be recalled, and lost unique credentials cannot be inferred.

Remaining ownership/community work: verified character claims, opt-out of appearances in other uploaders' logs, account/device recovery and individual moderator identities/appeals workflows. Those need an explicit trustworthy identity/authentication design. Richer PvP scoring still requires representative match/kill/objective evidence; user will gather PvP captures later. Live protocol enrichment remains dependent on verified packet evidence.

## Insights roadmap — checkpoint 7 (0.2.30)

Implemented private anonymous reports from shared desktop/Pages/server combat review, bounded/rate-limited intake and receipts, private LAN dashboard review/dismiss/quarantine/release, required decision notes and audit history. Reports never automatically hide uploads. Quarantine rotates shared access, excludes public/calibration samples and pauses owner visibility changes; original unique credentials retain review/deletion. Release leaves the upload private. No report contents are exposed publicly.

Remaining: verified character claims and opt-out across other uploaders' logs, account/device recovery, individual moderator identities/roles and an authenticated appeals/status workflow. Shared admin-token audit establishes credential use, not the identity of a person. Protocol-dependent metrics (live positions, casts, buffs, resources, effective healing and PvP outcomes/objectives) still require representative evidence. Further work should begin with verified character authentication design or new protocol captures.

Pending capture-quality follow-ups: additional OS/driver packet-drop counters, verified match boundaries, robust matching of incomplete perspectives, trusted game-version mapping and unlimited disk archival beyond bounded retention. These are not inferred from missing events.

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

### Run boundaries (0.2.21)

Implemented retained run groups, configured final-boss death completion, manual Finish run, map/dungeon transition boundaries and source-specific open-world/unverified categories. Shared viewer selects individual runs. Missing final-boss order and arena/battleground match-end protocol evidence prevents guessing automatic completion. Long-capture archival/rollover beyond the existing bounded history limits remains pending.

### PvP optimizer checkpoint (0.2.33)

Separate PvE and experimental PvP damage actions, isolated saved results and explicit model limits. Live Meter actions now provide progress and completion feedback. A full arena capture against RaZoR was supplied with a reported 0–3 loss and three local deaths; replay currently observes only two local zero-HP transitions and no explicit local death markers. Death and round/match detection therefore remain incomplete. Next: reconcile this capture with death/round signals, then verify automatic arena completion and classification. Verified PvP coefficients, opponent defenses and defensive/CC objectives remain future work.

## Long live sessions (0.2.38)

Live capture automatically saves a numbered archive part before the current history reaches its effect, telemetry, encounter or observed-party identity budget. Each part has a shared archive ID and appears separately in **Combat Logs**. Capture continues with the same decoder and current identity context; the live meter and its export/upload buttons cover the current part. Open an earlier part from Combat Logs to review or upload it. There is no fixed total part count or automatic deletion; available disk space is the practical storage limit. The recent list shows the newest 100 files; older parts remain in the user logs folder and can be imported.

A storage boundary is not a boss kill, instance finish or arena result. Parts crossing a storage boundary are conservatively unranked, and a continued run does not inherit observed entry. Parts are not automatically stitched into a combined report or uploaded as a batch. A failed rollover save stops capture visibly and retains the in-memory history instead of clearing it. Periodic recovery is still every 15 seconds; abrupt termination can lose newer unsaved effects.

Per-file format/validation limits still apply. In unusually large All-observed rosters, a part can exceed the 64-player validation limit; the app reports a save error rather than silently clearing it. Party/Self scope is recommended. This is automatic bounded-part archival, not an unlimited single JSON document. Raw TCP diagnostics remain a separate opt-in recording.

Implementation: rollover is checked between decoded packet batches at 100,000 retained effects, 20,000 telemetry samples, 100 conservative candidate encounter boundaries or 48 observed party actor references. Saves use atomic replacement and fsync before releasing the old part. Thresholds leave headroom for normal packet batches. Counters remain conservative cumulative capture evidence across parts. No live TCP stream is reopened, historical identity epochs are not merged, and recorded pet links remain available.
