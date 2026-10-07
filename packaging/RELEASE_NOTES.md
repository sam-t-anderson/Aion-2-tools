# Aion 2 Calc 0.2.61

Reduce Windows capture pressure by requesting an 8 MiB Npcap kernel buffer per adapter before sniffing. Capture uses non-promiscuous mode. Diagnostics record whether the buffer request succeeded; a rejected request retains the backend default and shows a warning.

Opt-in TCP diagnostics batch disk writes with a bounded 256 KiB buffer, flushing during recording and before export. Export still copies a fixed prefix while capture continues. Write/flush failures remain visible; failed recordings are retained. A sudden process termination can lose the unflushed diagnostic tail; combat logging is separate.

Analysis of the supplied 0.2.59 recording found capture-driver drops and long TCP forwarding gaps. Replaying its retained segments with 0.2.60 reduced the longest forwarding gap from about 521 seconds to 7.6 seconds. This is a transport replay, not proof of complete combat decoding or loss-free capture. Keep 0.2.60's bounded TCP recovery and incomplete-capture reporting; missing data cannot be reconstructed.

# Aion 2 Calc 0.2.60

Prevent known capture stalls after a missing TCP chunk: allow normal packet reordering for five seconds, then resume from fresh bytes with a recorded lossy boundary instead of buffering later encounters indefinitely. Queue limits and observed replacement SYN also reset stale partial decoder framing. Recovery splits the encounter, preserves earlier data and records capture loss for ranking eligibility. Live Meter displays the recovery count. Missing packets are not reconstructed.

An enemy filter from a previous encounter is cleared when that enemy is absent from the selected combat, so a new pull is visible in both the desktop meter and overlay. Explicit historical encounter selections remain available.

Capture errors now reach the displayed meter status and Start/Stop control instead of being discarded as failed status requests. Meter polling has a timeout and retries; desktop and overlay retain the last readings with a visible connection warning when refresh fails. An interrupted view does not establish whether capture is still running.

The Live Combat Session explorer also follows new encounters by default, rather than staying on its first encounter. Selecting a historical encounter or run pins it; enable **Follow latest encounter** to resume following. Saved-log and shared-log viewers retain their normal historical selection behavior.

The overlay follows the latest encounter independently of desktop history/enemy selections. Live Meter labels a pinned or historical view and offers Follow latest combat. Diagnostics show the age of the last forwarded game data and decoded effect to distinguish idle combat from missing input; these ages are included in diagnostic exports.

These address confirmed code paths that can hide or interrupt subsequent combat. The reported 0.2.58 incident has no diagnostic archive yet, so its specific cause is not established. Capture should continue across encounters without reopening the overlay.

# Aion 2 Calc 0.2.59

Overview can generate a separate common-budget community comparison for PvE or PvP. Two anonymous common-loadout searches are scored with the same weighted objective; completed results are cached by scoring inputs, reused across restarts and retained when submission fails. Personal gear, point totals, Genus and survival/trained-skill constraints are never trimmed into a shared candidate. Progress survives tab navigation. Model calculation jobs serialize to avoid shared optimizer/calibration state races.

New Steam live captures automatically record the selected install's exact build number as their comparison key. Build namespaces remain separate internally; desktop, Pages and shared review display build numbers and retain provenance. No named build or decimal version is required. Historical logs are not assigned today's build. Generic executable/engine versions and unrecognized PURPLE build metadata remain unavailable. Other ranking eligibility requirements still apply.

# Aion 2 Calc 0.2.58

Bundle fresh PvP comparison examples for all eight classes. Each class has separate sustained and burst allocation searches; both candidates are independently scored using equal-weight sustained/burst damage, and the stronger candidate is retained. Common gear, fixed example resources, frozen allocations and search provenance make these examples reproducible. They are not progression maxima, global optima or validated competitive PvP builds.

Planner distinguishes bundled common-comparison examples from community presets and displays their weighted scores and search assumptions. PvP conditional critical effects now use the same fixed player-target critical curve as the rest of the PvP model, without importing personal PvE critical calibration.

# Aion 2 Calc 0.2.57

Planner synchronizes one cached canonical PvE and PvP preset per class from servers supporting mode-specific comparison policies. Refresh presets checks again without restarting. Generic class/level/region/mode labels, weighted modeled DPS, comparison assumptions and last-check time distinguish community comparisons from bundled examples. Personal runs remain in Saved Results.

Planner can generate class examples separately in PvE or experimental PvP mode. Eligible anonymous class and character optimizations submit allocations against the server's authoritative policy. Responses are bounded and validated; snapshots preserve common gear, score components and scope. Servers without v2 support use the existing PvE path. Personal Genus/HP/skill constraints and over-budget builds are not silently converted into common-loadout candidates. PvP hotbar reconstruction uses the player-target kit.

# Aion 2 Calc 0.2.56

Adds a versioned common-loadout scoring foundation for canonical PvE and PvP presets. Comparisons use fixed example budgets and equal weighting of two mode-specific damage scenarios. Each scope records the model, class data, common loadout and policy so changed inputs cannot be compared silently. Submitted gear, reported scores and personal constraints are excluded.

PvP scores remain experimental stationary damage estimates. Server storage, preset synchronization and Planner selection follow in subsequent checkpoints. Shared budgets describe a comparison, not verified character progression maxima.

# Aion 2 Calc 0.2.55

My Character includes saved Pet Genus Insight lines in PvE and PvP optimization. Edit and save the same inventory used by Gear & Advice, choose a PvE enemy mix, or disable Genus scoring. Current-build comparisons, optimization and saved reports share a frozen allocation snapshot. The Pet Genus results window and Markdown show line contributions and excluded effects. Unsaved edits must be saved before optimization.

Genus rolls remain fixed; this optimizes other build choices around the lines you own. PvE uses weighted stats as an approximation. PvP includes supported general effects and excludes genus-specific effects whose applicability to players is unverified. Defensive effects, owned collection bonuses and reroll costs are not simulated. Personal Genus builds are excluded from shared presets that use a common loadout.

# Aion 2 Calc 0.2.54

Saved Parts adds **Show recording** and **All recordings** controls. Desktop searches saved session files for the exact recorded archive ID and pages them in part order; Pages filters the files selected locally. Existing upload selections and retry receipts survive recording navigation. Restored files recover their recorded archive metadata.

Parts remain separate reports. Shared archive IDs are grouping metadata, not proof of completeness, authenticity or ownership; no effects are stitched or deduplicated. Initial desktop searches read uncached file metadata and may take time for large archives.

# Aion 2 Calc 0.2.53

Settings → Export image coverage now includes desktop image-proxy HTTP status/error counters alongside browser image failures. Counters are local to the running desktop process and contain only approved source hosts, outcomes, status codes, counts and timestamps. No full image URLs, portrait paths, character identities, credentials or exception text are retained. Cache hits and browser-direct image errors remain distinct from HTTP checks.

Counts describe request attempts rather than unique missing assets; capture the export before closing the app. Existing fetch retries and cache behavior are unchanged.

# Aion 2 Calc 0.2.52

My Character can retain minimum trained active/passive skill levels and keep selected equipped stigmas at minimum levels while maximizing modeled damage. Options persist per character and apply to PvE and PvP; saved results and Markdown retain the constraints. Requests that cannot fit the point/slot budgets fail without publishing an unconstrained fallback. Personal constrained builds stay out of community damage presets.

This preserves allocations, not tactical use: gear/Daevanion bonuses and specialties may change. Utility skills outside the suggested rotation need manual use. Defensive effects, CC, movement and optimized opponent matchups remain unmodeled.

# Aion 2 Calc 0.2.51

Remember up to 200 failed remote image resources in the current browser session. Render a stable placeholder for five minutes instead of repeatedly requesting a failed image on each live/review update. Apply this to desktop equipment/skill artwork and shared combat skill/profile images on desktop and Pages. Retry images clears the session failure list and permits another attempt; combat review rerenders immediately, while Settings asks users to reopen the affected view.

Image coverage exports include browser failure counts, source hosts and recognized public skill IDs, without full URLs, query strings, portrait paths, character identifiers or tokens. Browser error events do not expose an HTTP status or prove a missing catalog mapping. No image failure records are uploaded automatically. The catalog audit found 2,081 bundled item references, all with image URLs and none with official ID fields; official and third-party IDs remain separate.

# Aion 2 Calc 0.2.50

Gear & Advice replaces the free-text genus-line entry with five genus tabs and nine analysis-slot cards. Enter Insight level, stat and exact value, clear individual slots, and save all genera together with explicit progress/error feedback. Drafts stay across genus tabs. Advanced JSON retains older malformed entries for repair instead of silently dropping them.

Validate known genera, levels 0–10, unique unlocked slots 1–9, bounded stat labels and nonnegative numeric/percentage values before replacing saved allocations. Invalid saves preserve the previous inventory. Saving invalidates the on-screen advice so users recalculate rather than viewing old scores against new inputs. Saved advice retains its original allocation snapshot. These are manual entries; official profiles do not expose Genus Insight, and defensive/CC/movement effects are not newly simulated.

# Aion 2 Calc 0.2.49

Fresh official profile imports retain public item/skill/pet/wing/title/board image references by region, kind and recorded ID. Equipment with a missing recorded icon can use an unchanged official reference for the same region/item ID before catalog slug/name fallback. Character identities, gear stats and tokens are not stored in this reference registry. Recorded gear snapshots remain intact; no new remote image search or guessed NPC mapping is performed.

Settings → Game database → Export image coverage downloads aggregate reference coverage and up to 200 missing/changed IDs for troubleshooting. It also counts missing catalog item references. URL presence does not prove the image can be downloaded; HTTP failures and NPC portraits remain follow-up work. Old cached profiles need refreshing to populate these references. No optimizer formulas or score changes.

# Aion 2 Calc 0.2.48

Desktop and Pages add **News**, with official English/global notice and update headlines, publication/retrieval dates, category filters and direct source links. All Pages tabs keep the same banner/navigation, including News. The configured community server caches the fixed official feeds; stale or unavailable sources are explained and official list links remain available offline from the community feed.

No article HTML, unofficial RSS or embedded executable content is loaded. Source announcements are not installed-game version evidence and do not set historical log/ranking builds. Korean/Taiwan feeds, build-to-build matching, regional event timers and broader news sources remain follow-up work. A supporting community server is required for cached headline cards.

# Aion 2 Calc 0.2.47

Saved Parts queues generate and persist a random request ID before sending each file, on desktop and Pages. Recovery exports retain that non-secret ID. Updated servers reuse the accepted report for matching retries under the same upload-key identity (or anonymous scope), content and visibility, including after a client/server restart. Fingerprint checks and explicit uncertain-retry approval remain. Older servers and old uncertain requests without a prior ID can still duplicate; clearing the queue starts fresh request IDs.

A reused request reports that no duplicate was created. Retry receipts do not reissue ownership tokens or private links; use the original My Uploads entry or ownership backup. If the first response and its ownership credentials were lost, this retry cannot recover them. Changed content/visibility returns a conflict; deleted originals return Gone instead of being recreated. These errors stop the queue for review.

This applies to Saved Parts batch uploads using supporting servers. It does not combine archive parts, deduplicate every manual/live-meter upload, coordinate separate queues or repair duplicates already submitted.

# Aion 2 Calc 0.2.46

Imported equipment now retains official item IDs, inventory positions, icons, rarity and enchant levels in optimizer loadouts. Equipment and Gear & Advice show a consistent placeholder when an image is missing or fails. Catalog fallback prefers explicit slugs and unique name matches; grouped item families and ambiguous matches no longer borrow an arbitrary item's picture.

New optimizer reports embed the loadout used for simulation in `build.json`. Current-character evaluation and optimization use frozen copies of that gear; report review and rerender use the saved copy instead of a later import's loadout file. Recovered new reports can therefore show their saved equipment and gear skill bonuses even after the original loadout file changes or disappears. Existing Saved Results snapshots remain unchanged. Older raw build reports without a gear snapshot retain their legacy lookup and explicitly show that the original gear snapshot is unavailable; old equipment cannot be reconstructed retroactively.

This preserves reported equipment visuals and optimizer inputs, not a full official upload-time combat profile. It does not change damage or survivability formulas or recover assets missing from their source.

# Aion 2 Calc 0.2.45

Clicking a character in a combat log opens a focused build view with **Back to log**, preserving the encounter, metric and timeline selections. Desktop and Pages share the view. Display the recorded official portrait, character identity, stats, equipment with inventory slots and rarity borders, skill/passive/stigma images and levels, pets/wings and Daevanion boards when present. Expand Full recorded build information for item rolls, specialties, titles, skins and every other saved official section. Export retains the original profile JSON.

Saved upload-time profiles and manually fetched current previews remain clearly separated. Missing profiles/assets remain unavailable; no gear or historical snapshots are guessed. Image URLs must use HTTPS on supported game asset hosts. Pet genus is shown only if the profile supplies it; the current official snapshot generally lacks genus, so the complete in-game genus planner remains follow-up work.

Daevanion skill/passive level nodes now show their skill images inside the existing rarity-colored ring, with initials as a fallback. Planner build choices use generic class/level/data-region/mode labels such as `sorcerer_45_global_PvE`; missing fields remain `unknown`. This does not create canonical PvP presets or change personal Saved Results names or optimizer scoring.

# Aion 2 Calc 0.2.44

Community Combat Logs replaces Type/build/difficulty in the list with recorded-event count, build and encounter icons. PvP shows each recorded opponent class once; PvE shows catalog-confirmed bosses. Missing classes, absent bosses and missing portraits use the bundled AION 2 emblem with explanatory hover/accessible labels. The current NPC catalog does not contain boss portraits; those remain placeholders until verified assets are available.

Opening a community log carries the selected PvE/PvP mode into its focused review. The Combat mode dropdown filters encounter choices, graphs, tables, timelines and events while preserving original segment indices for rankings. Choose All recorded modes to inspect the full document. Whole-run timing/progression is hidden while a mode filter is active to avoid mixing run-wide totals. Mixed documents appear in both community lists when the server identifies segments of each recorded mode. Mode-specific list counts and aggregates require the corresponding server update; older servers show event count unavailable.

This filters recorded encounter classifications. It does not infer ambiguous PvE/PvP activity inside a single encounter, guess missing opponent identities or change uploaded evidence.

# Aion 2 Calc 0.2.43

**Live Meter → Game installation** lists detected Steam libraries and recognized registered Windows/PURPLE game installs. Choose a copy when several are present; Auto only selects a single discovered copy. The local preference survives application restarts. Removed selections stay unavailable instead of silently switching to another install. Installation paths and the local selector ID are not added to uploaded combat documents.

Installation selection is locked during capture and while combat history is retained. Stop, save/export and clear the session before selecting another copy. Clear also removes retained demo-meter data. Installed build evidence stays with retained live combat when capture is restarted. Capture remains available when no install/version is detected; missing evidence stays unavailable.

Region overrides now use a dropdown with Auto (recorded home server) and the existing official region choices. A manually chosen recording region does not assign that region to opponents or other players. The official server-region cache now writes to the user data directory, including on first use in packaged installations. Installed build IDs are separate from published game builds; automatic build/difficulty inference and discovery of unregistered PURPLE installs remain pending.

# Aion 2 Calc 0.2.42

Discover Steam AION 2 installations from library manifests, including alternate library drives, alongside recognized Windows/PURPLE registrations. Installed build IDs remain separate from official published build labels. Multiple-install/region selection and automatic difficulty inference remain follow-up work.


Combat Logs separates **Saved Parts**, **My Uploads** and **Community Combat Logs** on desktop and Pages. Desktop remembers the selected list tab while opening a focused log and returning; Pages preserves it while opening a local preview. Tabs hide their panels without resetting upload queues. Website Saved Parts means files selected from your computer, not direct access to the desktop archive directory. Arrow keys, Home and End navigate tabs.

Completed-run speed and Boss progression are now permitted read-only community endpoints in the desktop proxy. Boss progression requires catalog-confirmed bosses with observed engagement and excludes players, pets, dummies and catalog non-bosses. Unmapped NPCs do not establish boss roles. The current catalog does not separate every miniboss from a major or world boss; comprehensive miniboss exclusion remains pending verified role metadata. Unknown build/difficulty and ranking eligibility rules are unchanged.

**My Character → Imported before** lists the newest eight imports as buttons that fetch the current official profile. Macro/hotbar suggestions reserve **Right-click** instead of F. This is guidance; the app does not change game bindings.

Recovered old build titles show PvE/PvP and use the saved character sidecar name when available. Generic class titles remain when identity is unavailable. Existing generic recovered titles are upgraded without replacing their result snapshot or timestamp. Recovery entries and explicit run snapshots remain separate historical records.

# Aion 2 Calc 0.2.41

- Recognize map 61 as a user-confirmed arena when player combat is present, retaining an explicit unknown-specific-name label. Catalog revisions now include map evidence and coverage rules so the server can refresh existing coverage.

- My Character optimization preserves the imported flat HP contribution from crystal boards by default, maximizing modeled DPS subject to that reserve. Add a manual minimum or disable preservation for the previous damage-only objective.
- Add up to eight editable incoming-damage scenarios for PvE encounters or PvP opponents. Enter current maximum HP, hit damage after mitigation, incoming DPS, sustained HPS, time window and positive reserve. The strictest assumed requirement constrains the node allocation; show per-scenario HP headroom and worst headroom in results and recovered snapshots.
- Keep HP proxy assumptions visible. Armor, percentage HP, defensive skills, CC, movement, optimized opponent profiles and PvP win probabilities are not modeled in this checkpoint. Gear & Advice remains damage-based. Constrained builds stay local instead of replacing damage-only community presets.
- Reject infeasible HP allocations rather than silently publishing an unconstrained fallback; validate integer solutions, connectivity, budgets and constraints.
- Fix a mapping-coverage false positive when a known dungeon ID is repeated as the map ID (including Fire Temple 600021). Unknown difficulty remains unknown.

# Aion 2 Calc 0.2.40

- Save bounded upload-recovery checkpoints on desktop disk and in Pages browser storage. Restore a saved queue or export/import its recovery file after navigation or restart.
- Verify SHA-256 file fingerprints before retrying or skipping known successful entries; reject changed desktop files again at upload time. Pages requires reselecting original JSON files.
- Mark interrupted or ambiguous requests as uncertain and require explicit retry after checking My uploads. Persistence failures stop further uploads. Recovery contains filenames, titles, fingerprints and report IDs, without upload keys, owner credentials or private links.
- Keep reports independent. This is client recovery, not server idempotency or archive stitching; accepted requests with lost responses may still duplicate when explicitly retried.

# Aion 2 Calc 0.2.39

- Stack supporting effects vertically on the right of skill cards, with effect text, unlock levels and recommendation status beside each number. Fix cramped selection summaries and overlapping text.

- Open saved, analyzed and shared logs in a focused detail view with **Back to combat logs**. History, upload queues and server settings stay on the list screen. Pages local previews use a temporary focused browser view; refresh requires reopening the file.
- Reconstructed rate graphs now offer live-style bars with a trailing 10-second average, player series and time inspection. Timeline adds a seconds ruler, sticky player labels, skill icons, zoom windows and navigation; hover, focus or click shows effect details. Markers represent observed effects, not inferred cast durations. Crowded markers are labeled and remain available in Events.

- Browse saved local logs in pages of 25, reaching older archive parts beyond the previous newest-100 view.
- Add a shared desktop/Pages queue to review and upload up to 100 saved parts sequentially with explicit visibility, per-file results, cancellation between uploads and retry of remaining entries.
- Stop the queue on connection/authentication/rate-limit errors, exclude unfinished checkpoints and retain individual ownership credentials.
- Export a results manifest without upload/ownership keys or private view links. Public/unlisted links can be included.
- Keep parts as independent reports; combined timelines, durable retry/idempotency and automatic archive stitching remain future work.

# Aion 2 Calc 0.2.38

- Fix desktop builds omitting the configured public community upload key, which caused 401 errors for new users. Restore blank-key defaults only for the matching community server; preserve custom servers and personal keys.

- Save long live captures automatically as numbered local archive parts before ordinary history bounds are reached; continue decoding in the next part.
- Retain archive ID/part information through validation, export and shared desktop/Pages/server review. Earlier parts remain in Combat Logs; current live export/upload contains the current part.
- Clear an old part only after an atomic disk save succeeds. A save failure stops capture visibly and preserves memory history.
- Mark storage-boundary parts unranked and remove inherited run-entry evidence. Storage boundaries do not infer kills or completion.
- Per-file limits and the newest-100 local list remain; automatic stitching/batch upload and unusually large All-observed rosters need further work.

# Aion 2 Calc 0.2.37

- Record supported Npcap/libpcap received, buffer-drop and interface/driver-drop counters per adapter. Show partial/unavailable statistics explicitly; zero is not proof of loss-free capture.
- Preserve final statistics on Stop, cumulative evidence across retained-session restarts, saved logs and diagnostic ZIPs. Display evidence in shared desktop/Pages/server quality panels.
- Conservatively exclude recordings with reported positive driver drop counters from rankings. Counters cover capture handles and cannot identify unique lost game effects.
- Keep optional statistics failures separate from decoding and sample handles on their owning thread, with explicit socket cleanup after capture exits.
- Fix selected-pet filters when switching to combined owner rows in shared review.

# Aion 2 Calc 0.2.36

- Fix live pet/spirit totals to collapse into recorded owners by default. Add synchronized Combine pets with owner controls to Live Meter and overlay; keep separate source detail in saved logs.

- Populate PvE difficulty from exact recorded instance IDs when the bundled catalog explicitly lists it; preserve automatic/manual provenance.
- Show map and instance IDs, detected difficulty and current-view unresolved ID count in Live Meter.
- Add Mapping coverage to shared desktop/Pages/server combat review and an exportable JSON report with catalog revision, unresolved NPC/map/instance IDs, retained entity/effect counts and omission notices.
- Include current-view catalog and automatic metadata in diagnostic ZIPs. Reports exclude character names and raw traffic; existing opted-in TCP payloads remain unchanged.
- Correct provenance when editing difficulty, zone or encounter category in saved local logs.
- Unknown category, game build, unrecorded NPC types and PvP outcomes remain unresolved. Catalog reports do not infer kills or automatically trust names.

# Aion 2 Calc 0.2.35

- Style the overlay Hide button with the same dark gradient, gold frame, hover and keyboard focus treatment as the desktop controls.

- Freeze live DPS at the last recorded damage event during healing-only downtime. Show Paused after two seconds without damage; capture continues and new damage resumes the clock. Saved logs retain the full event interval, so historical report rates can differ from live DPS.
- Detect the installed game build from registered Windows installations (Steam manifest or executable version resource). Export build evidence without installation paths. Installed build is separate from the game build used for rankings.
- Resolve recorded server IDs against official regional server lists in the background, with a six-hour cache. Missing or ambiguous IDs remain unresolved.
- Identify Fire Temple Arena from the confirmed map capture, known open-world categories from the map catalog, and dungeon names from recorded instance IDs. Show automatic detection in Live Meter and preserve provenance in shared review. Optional manual overrides remain available.
- Unknown build, difficulty, content and match outcomes remain unknown; additional verified mappings are needed.

# Aion 2 Calc 0.2.34

- Restore the live skill breakdown after tab navigation by invalidating the removed DOM render cache.
- Add per-player ability contribution charts and damage/healing tables to saved/shared log review, including effects, total, share, per-second amount, average, minimum and maximum. Summary defaults to friendly damage done; player filters apply.

- Make Table, Timeline and Events mutually exclusive in the shared desktop, Pages and server combat viewer. Table no longer displays the timeline underneath it. Graph remains an independent toggle.

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

- Show current same-build and reconstructed at-upload standings side by side in desktop, Pages and shared combat review, including run speed.
- Match player comparisons by boss, class, encounter category, build, difficulty, observed party size and instance. Keep personal bests and class distributions separate by party size/instance too.
- Add party-size filters to community browsing and the Pages leaderboard; replace the leaderboard's cross-cohort row number with matched cohort rank.
- Show percentile availability, public sample counts, distinct identities and provisional local/private comparisons. Percentiles need at least 10 samples and five distinct characters, or five distinct parties for run speed. Capped datasets do not receive a percentile.

Requires server v0.2.12 for the new comparison fields. At-upload standings are reconstructed from currently public retained uploads received by that time; deletion, visibility and policy changes can change them. Current means current samples from the log's build, not comparison with a newer build. Ties share midrank percentiles. Small-sample class quartiles remain descriptive and show coverage warnings. HPS depends on healing demand; damage taken is descriptive, not a performance ranking. Upload-time gear cannot establish encounter-time equipment, so gear-adjusted brackets remain unavailable. Unknown party/instance evidence has no formal percentile. Existing capture and PvP evidence limits remain.

## Changes in 0.2.24 — run timing and boss progression

- Review each recorded run independently in desktop, Pages and shared logs: recorded span, encounter time, gaps and verified entry-to-final-boss elapsed time when available.
- Show recorded boss attempts, kills, observed wipes, unknown outcomes, attempts to first recorded clear, best observed wipe HP and recovery gaps.
- Join unresolved manual chunks of the same boss actor instead of counting each split as another pull.
- Add public completed-run speed tables and boss progression summaries with the updated server. Speed comparisons match instance, boss route, build, difficulty and party size; duplicate recordings count once.
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

- Filter community and recent local logs by encounter category; record game build, difficulty and region for comparisons.
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
