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

## Review and upload saved parts (0.2.39)

**Combat Logs → Saved parts** browses local files in pages of 25, including files older than the newest 100. Open a part to review it, filter the current page by encounter type, name or archive ID, and select up to 100 saved files across pages. Choose Public, Unlisted or Private, then **Upload selected / retry remaining**. The default is Unlisted. Each file creates an independent report; archive parts are not stitched into one timeline or combined score.

The same queue is available on the Pages **Logs** page: choose saved a2log v1 JSON files (up to 50 MiB each), review locally and select the parts to upload. Uploads use the community server configured for the site or the visitor's saved Raid Planner server settings. Reading a file does not upload it. The browser compresses uploads when CompressionStream is available; server size/rate limits still apply.

The queue shows progress, uploaded report links, errors and ownership-save warnings for each file. Cancel stops before the next upload; an in-flight request can finish. Successful entries are skipped when retrying within the same queue. Network/authentication/rate-limit failures stop the queue with remaining files pending. A lost response can be ambiguous: retry can create another upload if the server already accepted the first. Clearing the queue or leaving/reloading the page loses this queue's retry state, but saved ownership credentials remain available under My uploads. Navigating away stops before the next request, not necessarily the current one.

Active or unfinished checkpoints are excluded from batch upload; stop capture first. An unfinished crash-recovery checkpoint can still be reviewed and published individually as partial evidence. Local pagination is a live file listing: concurrent new checkpoints can shift page boundaries, so selection is tracked by filename and should be reviewed before upload. Filters apply to the current page, not every file on disk. Changing server/visibility requires clearing the queue; desktop requests reject a server change during a batch.

**Export upload results** saves a manifest of selected files, archive/part labels, statuses and report IDs. Public/unlisted links may be included, so unlisted links should be shared deliberately. Private links, upload keys and ownership credentials are excluded. Keep using My uploads → Export private credentials for an ownership backup. A manifest is a list of outcomes, not a combined combat log, permanent privacy snapshot or automatic import/resume credential.

## Focused log review (0.2.39)

- Open saved, analyzed and shared logs in a focused detail view with **Back to combat logs**. History, upload queues and server settings stay on the list screen. Pages local previews use a temporary focused browser view; refresh requires reopening the file.
- Reconstructed rate graphs now offer live-style bars with a trailing 10-second average, player series and time inspection. Timeline adds a seconds ruler, sticky player labels, skill icons, zoom windows and navigation; hover, focus or click shows effect details. Markers represent observed effects, not inferred cast durations. Crowded markers are labeled and remain available in Events.

Skill images use the desktop icon cache or metabot.gg on the website; unavailable images retain labeled tiles. Local previews and queue state are temporary; saved files and server reports remain available.

## Recovering an upload queue (0.2.40)

**Combat Logs → Saved parts → Restore saved queue** restores the last queue saved on this computer. On Pages, it restores the last queue in this browser/site storage; reselect the original JSON files before resuming. Recovery metadata is saved after selections and before/after each request. Keep only one active queue per computer/browser; concurrent windows are not coordinated. A local-storage or disk write failure stops further uploads.

**Export recovery file** / **Import recovery file** moves a queue checkpoint between launches or computers. It stores filenames, titles, SHA-256 fingerprints, original server/visibility, statuses and report IDs. It does not include combat documents, upload keys, owner credentials or private links. Select the same server and supply any required key through ordinary settings. Keep **My uploads → Export private credentials** as a separate ownership backup. The older results manifest is for reporting outcomes, not recovery.

The file fingerprint must match before a successful entry is skipped or another request is sent. A changed file stops the queue; remove it or clear/review a new queue. A missing file must be restored or removed. Pages can reattach uniquely named files after copying; fingerprints still verify content. Recovery files are user-editable local records, not authenticated server receipts or upload ownership.

Requests interrupted during upload restore as **unknown**. Check **My uploads**/the original server before checking the explicit uncertain-retry option. The server may already have accepted a request even if the response was lost; explicit retry can duplicate it. Known successful uploads are skipped, but this is not durable server idempotency. No automatic upload starts when restoring or importing. Private report links must be reopened through My uploads, since recovery files intentionally omit them. Clearing a queue also clears its saved checkpoint, without deleting logs or uploads.

## Planned optimizer objective update

User priority: maximize PvE damage while meeting configurable survivability constraints, including avoidable one-shot thresholds and sustained trash pressure. Expose the assumed incoming hit/pressure, defenses and mitigation support instead of promising survival. Defensive benefits unsupported by skill data remain unavailable; no invented damage reduction or healing coefficients.

For PvP, evaluate damage/burst, crowd control, mobility and survival across an ensemble of optimized opponent builds/archetypes. Use official current profiles or recorded profile snapshots when identities resolve, with timestamps and provenance. Include average and adverse matchup results and sensitivity to uncertain coefficients; avoid optimizing against one stationary target or claiming verified win probabilities. User-provided profiles/scenario inputs should remain editable. Current experimental PvP optimizer is still a damage-only proxy until this separate modeling checkpoint is implemented and validated.

Next after recovery: durable server request idempotency and archive navigation/stitching design; optimizer scenario/constraint implementation is a separate substantial checkpoint. Representative PvP round/death, CC/movement and mitigation evidence remains needed to validate mechanical predictions.

## Damage with an HP reserve (0.2.41)

My Character → **Survivability** preserves the character's imported flat **HPMax** contribution from the four optimized crystal boards by default. The existing DPS objective stays primary inside the set of allocations meeting this floor. Skill, stigma and Daevanion budgets and board connectivity remain enforced. A stricter minimum can trade some modeled DPS for more crystal HP. Disable preservation and leave the minimum/scenarios empty to use the previous damage-only objective. This is an HP-node constraint, not a full survival simulator.

Optional scenarios describe one hit followed by sustained pressure. Enter current in-game maximum HP and up to eight encounter/opponent assumptions: **hit damage after mitigation + max(0, incoming DPS − assumed sustained HPS) × seconds + positive HP reserve**. The largest requirement sets the floor. HPS never absorbs the initial hit. Estimated total HP is entered current HP plus the flat node-HP change; percentage modifiers and passive/gear changes are not modeled. Headroom is a scenario proxy, not verified effective HP, guaranteed survival or win probability. Confirm final HP in game.

Settings persist per selected character in this browser. Saved Results/build JSON/Markdown retain assumptions and the assessment. Infeasible requests report an error without publishing a lower-HP fallback. Solver limits can prevent finding an allocation even when one exists. Damage-only stat priorities, baseline comparisons and Gear & Advice do not validate survival; constrained builds are not submitted as community damage presets.

PvP supports a manual multi-opponent **incoming-pressure** envelope, not optimized opponent-build combat. Next modeling work: resolve official current/historical opponent gear with provenance; evaluate outgoing damage and adverse matchups; include verified defensive skill, CC, mobility and coefficient rules before scoring them. Those metrics are explicitly unavailable here. This checkpoint does not invent mitigation or tactical coefficients.

Mapping coverage also recognizes a known dungeon ID repeated in the map field. The submitted 600021 report already identifies Fire Temple; it is no longer separately flagged as an unknown map. Distinct unknown map IDs and missing difficulty remain unresolved.

### Catalog follow-up

Map 61 is categorized as Arena only when identified player combat is recorded, based on a user-confirmed arena capture. The exact arena name remains unverified. Map 600021 with matching known instance 600021 resolves to Fire Temple. Map 200003 remains unresolved: NPC dungeon references alone do not establish the recorded map's name or difficulty. Unknown patch/difficulty are retained rather than guessed.

## Combat log navigation and recovered builds (0.2.42)

Combat Logs separates **Saved Parts**, **My Uploads** and **Community Combat Logs** on desktop and Pages. Desktop remembers the selected list tab while opening a focused log and returning; Pages preserves it while opening a local preview. Tabs hide their panels without resetting upload queues. Website Saved Parts means files selected from your computer, not direct access to the desktop archive directory. Arrow keys, Home and End navigate tabs.

Completed-run speed and Boss progression are now permitted read-only community endpoints in the desktop proxy. Boss progression requires catalog-confirmed bosses with observed engagement and excludes players, pets, dummies and catalog non-bosses. Unmapped NPCs do not establish boss roles. The current catalog does not separate every miniboss from a major or world boss; comprehensive miniboss exclusion remains pending verified role metadata. Unknown patch/difficulty and ranking eligibility rules are unchanged.

**My Character → Imported before** lists the newest eight imports as buttons that fetch the current official profile. Macro/hotbar suggestions reserve **Right-click** instead of F. This is guidance; the app does not change game bindings.

Recovered old build titles show PvE/PvP and use the saved character sidecar name when available. Generic class titles remain when identity is unavailable. Existing generic recovered titles are upgraded without replacing their result snapshot or timestamp. Recovery entries and explicit run snapshots remain separate historical records.

## Next checkpoints and requested expansion (2026-10-07)

### Next: build presentation and asset identity

- Gear & Advice: inventory-slot layout with item icons, rarity, equipped/recommended comparison and accessible fallbacks.
- Daevanion: skill/passive icons in level-up nodes while retaining each node's current border color; resolve affected skills from actual board effects.
- Pet Genus: show imported allocations, benefits and an in-game-style panel across optimizer/advice/build views. Gather public screenshots or user references before copying the interaction model; do not invent pet allocation data absent from the official profile.
- Focused character build pages from combat logs on desktop and Pages: character, stats, equipment, skills/passives, specializations, Daevanion, pets/genus and available images, with Back to log. Preserve historical/current-profile provenance and timestamps. Eventually share rendering with a build viewer, planner and editor.
- Asset audit: current bundled English NPC catalog has 9,780 name/ID records and no icon/image field. Equipment icon lookup currently includes name-based matching. Prefer stable game/item/skill IDs and recorded official image URLs; record missing IDs, HTTP errors and fallback usage. Review additional NPC/enemy/item/title/passive assets and sources before importing mappings; do not derive URLs from a name or assume numeric namespaces match. Missing images must keep readable labels. External asset availability and reuse terms need review at implementation.
- Planner presets: one canonical PvE and one PvP selection per class, server-side. Define versioned comparable budgets/objectives and a weighted rating, retain candidates/audit history, then regenerate canonical builds. Do not rank incomparable gear/budgets or personal HP constraints solely by DPS. Current server preset schema/objective is PvE damage-only; no competitive PvP preset is claimed yet.
- Verified major/miniboss/world-boss role catalog. Current isBoss flag does not distinguish all roles; preserve world bosses and exclude minibosses only from verified role evidence. Reindex derived progression after role updates.

### Later: Pages tools and feeds

- Regional event timers with server/local timezone, DST handling, provenance and editable corrections. References: https://shugo.gg/timers , https://a2db.ru/en/events , https://gamers4.life/aion-2/database/en/events/ . Shugo's page explicitly labels Global event schedules as not officially published; do not present copied times as verified official schedules.
- Build viewer/planner/editor with profile links and return-to-log navigation. References: https://gamers4.life/aion-2/database/en/builds/ and https://questlog.gg/aion-2/en/character-builder . Reuse the focused character view and validate legal allocations before optimization/export.
- News cards from permitted RSS/API feeds, showing publisher, timestamp, preview and source link; sanitize embedded content and avoid arbitrary iframe/HTML injection. Reference https://shugo.gg/news . Feed availability/reuse must be confirmed, not assumed from a news listing.
- Interactive maps: verified zone/coordinate data, search/filters, provenance and permitted tile/icon assets. References https://a2db.ru/en/maps , https://shugo.gg/map , https://interactivemap.app/aion2/maps/ . These are references, not licensed datasets automatically available for copying.
- Crafting simulator resembling the game: materials/quantities, output/rarity, chances/modifiers, explicit recipe/patch/region provenance and unknown values. Research database/wiki formulas and permitted images before modeling; keep deterministic costs distinct from probability estimates and do not invent chances.

Existing priorities remain: verified defensive/CC/mobility/opponent modeling, upload idempotency/archive stitching, combat protocol gaps and evidence-based catalog/patch/difficulty mapping. PvP analytics and operations dashboard continue in parallel with those user-requested checkpoints; expansions above do not imply already-completed features.

### Installation and encounter inference follow-up

Fix Steam-library discovery in v0.2.42; this machine has AION 2 app3393110 in the primary Steam manifest, build25719316, with a newer target update recorded. The installed manifest is evidence of installed build, not proof of the latest live patch or completed pending update.

Next metadata checkpoint: enumerate validated Steam/PURPLE installations, provide a persistent local install/region selector when ambiguous, investigate launcher game registration/config/version files and official regional published patch feeds. Keep paths local and installed/published patch provenance separate; a newer website announcement cannot prove an old installation or historical log ran that patch. Move manual encounter corrections to post-recording once automatic classification is adequately supported.

Classify zone, content and difficulty independently using exact versioned map/instance/NPC IDs, explicit server difficulty flags, verified boss roles, boss sequence and reported maximum HP signatures. Damage/received damage are weak supporting signals due to gear/buffs/mitigation. Evaluate confidence calibration using independently labeled captures, held-out regions/builds and conflicting/missing evidence. Target >=99% measured precision before enabling probabilistic automatic labels; abstain where unsupported rather than inventing a percentage. No such classifier or confidence guarantee ships yet. User requests confidence-based classification without pre-recording manual choices; this remains a priority after discovery fixes.

### Patch-versioned boss signature collection (before difficulty inference)

Collect candidate signatures server-side from retained reported HP samples, grouped by region, installed build/verified patch, instance/map, NPC type, independently confirmed difficulty, party size and scaling/modifier conditions. Preserve source evidence, sample counts and catalog provenance. Separate explicit reported max HP from maximum observed current HP and incomplete captures. Derive ability-specific raw boss damage only when mitigation/buff/ability metadata makes it comparable; received damage alone is not a stable fingerprint.

Promote candidates with verified game tables or repeated independently labeled recordings; do not use the classifier's own predicted labels as confirmation. Track ambiguity and collisions, detect patch shifts, retain old mappings for historical reports, and abstain on new/unverified patches until evidence supports a label. A unique verified maximum-HP signature plus boss/instance identity can be sufficient; overlapping/scaled values need explicit flags or additional evidence. Confidence thresholds need labeled held-out validation, not an invented certainty percentage. Candidate collection and promotion are planned server work, not enabled in v0.2.26.

### Preset naming

Keep homepage/build-planner preset labels generic: `<class>_<level>_<region>_<PvE|PvP>`, for example `sorcerer_45_global_PvE`. Do not expose contributor or character names as preset titles. Keep performance, provenance and loadout variants as separate details. Saved personal optimizer history can retain character names. Apply this when publishing the canonical per-class/mode presets.

### Installation selection checkpoint

Implemented local persistent selection among detected Steam/registered Windows game copies, explicit multiple-copy and missing-copy states, recording-region dropdown, retained-session installation lock and writable first-use official region cache. Follow-up: unregistered PURPLE configuration discovery, verified official regional patch feed and patch-specific encounter signatures. Published patch labels must not be guessed from Steam build IDs or applied retrospectively to older logs.

### Community log presentation and mixed modes

Implemented the community list's Type/patch/difficulty cell replacement with event count, patch and catalog boss placeholders (PvE) or distinct opponent-class icons (PvP). The bundled AION 2 emblem is the fallback; verified boss portraits remain pending because the NPC catalog lacks image URLs. Mixed uploads with recorded segments of both modes appear in both lists with matching-segment totals, and open a mode-filtered viewer preserving original ranking indices. Follow-up: verified boss portraits and unambiguous per-effect mode evidence when one segment contains mixed activity.

### Build visualization checkpoint

Implemented focused character pages shared by desktop/Pages with Back to log, recorded official images/stats/equipment slots/skills/pets/boards and complete expandable source sections. Added skill/passive images to Daevanion nodes preserving rarity rings, and generic Planner selection labels. Remaining: stable-ID catalog icon recovery, game-style Pet Genus using verified data, canonical weighted PvE/PvP presets per class, and richer editable build boards. These display changes do not add survival/CC/movement formulas or change optimizer scores.

### Retained gear and asset provenance

New imported loadouts preserve official equipment IDs/slots/icons/grades/enchants, and new optimizer raw reports freeze their simulation loadout for future review/rerender. Missing/broken equipment images show a placeholder; name fallback requires a unique match and does not choose one member of a grouped family. Follow-up: catalog stable-ID reconciliation and verified NPC/item/title asset coverage. Old reports without gear snapshots cannot be reconstructed retroactively.

Server candidate collection now groups publicly retained engaged boss HP evidence by patch/build/region/NPC/map/instance and submitted difficulty/source/recorded complete roster size, keeping reported max HP separate from peak current HP. Dashboard/export flags changing or inconsistent maxima. Independent labels, scaling/modifiers, promotion and held-out precision validation remain pending; candidates do not classify difficulty or alter ranking eligibility.

### Durable saved-part request retries

Saved Parts desktop/Pages queues persist/export random request IDs before sending. Supporting servers atomically retain request-to-report mappings scoped by upload-key identity (or anonymous), compare normalized content/visibility, replay accepted IDs, reject conflicts and retain deletion tombstones. Retry IDs do not grant ownership; receipts never reissue private links/tokens. Explicit uncertain retries and file fingerprint verification remain. Legacy requests/servers and separately started queues can duplicate; full content-based duplicate reconciliation, archive stitching and ownership recovery after a lost first response remain follow-up work.
