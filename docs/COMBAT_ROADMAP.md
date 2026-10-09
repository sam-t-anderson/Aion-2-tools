# Roadmap and completion criteria

This page describes current capabilities and remaining work. Release-by-release changes belong in [GitHub Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases). See [the app guide](app.md), [user guide](user-guide.md) and [methodology](methodology.md) for behavior and limits.

The seven requested workstreams have delivered their implementation checkpoints. Some follow-ups depend on game data or protocol evidence that is not available yet; they remain open below. A display, proxy or entered assumption is not a verified game mechanic.

## 1. Capture reliability and recording reconstruction

**Available:** continuous bounded-part archival, periodic recovery snapshots, saved-part pagination and upload queues, durable upload request retries, part discovery, combined stopped-part review and original-source navigation. Shared outgoing-damage clocks freeze during inactivity, resume without resetting player totals and use a minimum 120-second automatic split gap. Partial mid-instance captures remain visible and unranked. Supported late roster and summon-owner evidence reconciles retained effects within its identity context. Overlay DPS/HPS/incoming metrics, grouping, text colors and foreground behavior are configurable.

**Remaining:**

- Support additional local-player, spawn, roster, death and instance-entry protocol variants using representative captures. Do not assign an unnamed actor from class, name similarity, proximity or damage.
- Confirm the zone/ownership and repeat-encounter fixes on affected devices and game sessions, with TCP recording both enabled and disabled.
- Stitch boss attempts crossing archive parts, reconcile overlaps and retain contradictory/ambiguous source evidence. Promote complete chains to rankings only after explicit entry/completion, stable identity and loss evidence pass independently defined rules.
- Improve matching of incomplete views from multiple uploaders without merging unrelated fights. Lost upload responses retain ownership-recovery limits even when request retries prevent duplicate creation.
- Add additional supported OS/driver loss evidence. Missing or zero counters cannot prove loss-free capture, and driver/TCP counters must not be added as unique packet loss.

**Completion evidence:** entry-to-completion captures, partial captures, party/zone changes, reconnects, stops and rollovers with known participants/outcomes. Historical missing packets cannot be restored.

## 2. Encounter classification, installed builds and catalog coverage

**Available:** validated Steam/registered-install discovery and local selection, launcher Build IDs, recorded regional server identity, automatic exact map/instance/NPC catalog matching, post-recording corrections, evidence explanations, unresolved-ID exports and a reproducible pinned upstream catalog audit. Public boss HP candidate signatures retain build, region, context, roster size and source provenance. Reported maximum HP stays separate from peak observed current HP.

**Remaining:**

- Discover unregistered PURPLE installs from verified registration/configuration formats and retain distinct launcher build namespaces.
- Establish independent build/region applicability for catalog records and boss signatures, including party scaling and encounter modifiers.
- Obtain independently confirmed difficulty labels, explicit difficulty flags and comparable boss HP/ability signatures. Received damage varies with mitigation, gear and buffs and cannot establish difficulty by itself.
- Calibrate probabilistic classification on independently labeled, held-out builds/regions. Target at least 99% measured precision before automatic promotion; abstain when evidence conflicts or coverage is insufficient. No such precision guarantee is currently established.
- Resolve supported missing NPC identity variants, new stable type IDs and exact area names from source evidence. Map 200003 and the exact arena name for map 61 remain unresolved where evidence is insufficient.
- Obtain explicit major/miniboss/world-boss roles and trusted portraits. Reindex derived progression after reviewed role changes; the broad catalog boss flag does not distinguish every miniboss.

**Completion evidence:** source-backed mappings and labeled captures by build, region, difficulty and scaling conditions. A current website announcement cannot retroactively identify an old log's build.

## 3. Optimizer damage, survival and optimized opponents

**Available:** separate PvE/PvP objectives and saved results, weighted damage scenarios, flat crystal-HP reserves, entered hit/sustained-pressure assumptions, trained-skill/stigma reservations and timed expected-hit traces. Imported optimized PvP opponents can supply gross-damage windows; the strictest entered incoming scenario constrains the personal build. Canonical community presets use comparable budgets/objectives and generic class/level/region/mode labels; explicit server regeneration searches both scenario seeds and their weighted objective using current reported budgets, retaining a stronger concurrent winner; fresh anonymous candidates can also be offered through the existing preset API for independent server scoring; personal constraints are excluded from damage-only preset comparisons.

**Remaining:**

- Model verified defensive skills, shields, percentage HP, healing, CC duration/success/immunity and movement effects with explicit action/cooldown costs.
- Model matchup-specific incoming/outgoing mitigation, worst-case timing alignment and reactive optimized opponents.
- Validate model predictions against representative encounters and matchups. Gross expected damage and entered pressure reductions are assumptions, not effective HP, guaranteed survival or win probability.
- Verify current-build gear-roll legality and model reactive tactical decisions from verified mechanics. Catalog item selection, enhancements, distinct source-pool roll entry and bounded full-window priority search for fixed draft allocations are available. This local search does not optimize allocations or establish a globally optimal or competitive PvP strategy.

**Completion evidence:** current-build coefficients, mechanics and validation captures. Competitive PvP claims require more than a damage ranking.

## 4. Genus Insight and progression

**Available:** manual five-genus/nine-slot editor, unlocked-slot validation, saved inventory/advice snapshots, in-game-inspired radial presentation, per-slot damage contribution and supported-slot replacement advice. Saved modeled lines participate in PvE/PvP optimization. Coverage distinguishes saved, unlocked and missing slots; progression budgets retain observed-versus-entered provenance.

**Remaining:**

- Retrieve official Genus allocations and owned collection effects when a supported source provides them. Current public profiles do not supply those allocations; blank slots are not invented.
- Verify defensive/owned-effect coefficients, current-build roll probabilities, costs and progression maxima.
- Extend the existing visual slot and Genus controls with verified collection/progression rules while preserving entered assumptions and reference snapshots. The standalone workspace now retains and evaluates manual equipment/Genus inputs.

**Completion evidence:** allocation payloads or user-entered in-game data, plus source-backed formulas and limits.

## 5. Combat analytics and protocol enrichment

**Available:** shared desktop/Pages/server review with focused log pages, run/encounter/participant scopes, graph keys, hover/click detail, timeline hide/collapse controls, damage/healing/incoming breakdowns, peak windows, explicit death recaps, imported buff overlap and evidence coverage. Linked pets can be combined without destroying source IDs. Partial/unknown evidence remains reviewable. Normalized imported positions can be handed to Raid Planner.

**Remaining:**

- Verify live cast starts/ends, buff sources/applications/removals, resources, shields, effective healing/overheal, interrupts, mitigation, misses and CC success.
- Verify live position coordinates, map transforms and movement decoding. Recognizing an opcode is insufficient to decode coordinates.
- Verify PvP team/round/match boundaries, objectives and kill credit. The reported RaZoR 0–3 arena loss has incomplete decoded death evidence and cannot establish match detection.
- Define encounter mechanics before assigning phase names, avoidable damage or causal support/rotation advice.
- Resolve per-effect mode when a single segment contains mixed PvE/PvP activity. Currently mixed uploads appear in both mode lists using their recorded matching segments.

**Completion evidence:** representative packets with independently known actions, targets, timing and outcomes.

## 6. Regional timers and timed-boss history

**Available:** regional event pages, named-zone/local countdowns, dated community schedule provenance, conflict/staleness notices and public observed boss-defeat histories with party engagement and source-log links. Schedule windows and last defeats remain separate from availability.

**Remaining:**

- Verify regional schedules and current-build applicability independently; copied community forecasts are not official schedules.
- Record physical server/channel scope and verify timed/world-boss roles and respawn rules.
- Deduplicate perspectives of the same defeat before estimating respawn or availability. Exact encounter duplicates alone do not solve this.

**Completion evidence:** independently confirmed schedule/respawn rules and sufficiently scoped observations. A last observed defeat does not show whether a boss is alive now.

## 7. Website and shared player tools

**Available:** consistent Pages navigation, focused logs and character pages with Back to log, recorded images/equipment/stats/skills/boards, local build allocation drafts, catalog validation, saved drafts/import/export and community preset seeding. Maps use the provider's published embed mode for four supported maps. Crafting has a source-attributed recipe snapshot, profession/faction search, icons/rarity, mastery/fees/materials, supported intermediate expansion, conditional combo scenarios and material-plan export. Official Global/Korean/Taiwan headline/preview cards preserve region, publication/retrieval dates, source-provided summaries, approved official thumbnails and original links.

**Remaining:**

- Verify current-build arcana rules and obtain Pantheon node controls/artwork from source data as described in workstreams 3–4. Catalog card skill selectors now use bundled class/slot pools and grade/enhancement bounds, separate from manual skill bonuses. Explicit draft rescoring is available without publishing or changing source profiles.
- Obtain permitted native map coordinates, layers and assets if replacing the provider viewer with local map tools. Cross-origin provider account/checklist state remains with the provider.
- Verify crafting general success/failure rewards, refunds, combo quantity/replacement rules, modifier formulas and build/region applicability. Current combo simulations are conditional completed-craft checks, not guaranteed item yields.
- Show source-backed stats for crafted output items when they have stats, alongside the product preview. Preserve units, ranges and enhancement or variant context when available; distinguish unavailable data from items without stats.
- Add further feeds only after confirming their official source, API/RSS availability and reuse constraints. Do not embed arbitrary article HTML or invent summaries/images absent from a supported feed.

## Maintenance, screenshots and assets

**Available:** application-content screenshots include below-fold content without monitor capture; storage inventory and explicit cleanup cover recognized disposable caches; updater helpers self-clean and bounded retention preserves recent logs, releases and active helpers. Saved logs, imports, credentials, results and upload queues are preserved. Asset diagnostics distinguish browser failures, proxy status, official same-region/item-ID references and publisher-specific item namespaces. Pinned catalog audits and profile image re-indexing are available.

**Remaining:**

- Confirm full-page rendering on target devices and handle browser/CORS limitations for remote images.
- Reconcile additional item/title/NPC/passive assets using stable source IDs and reviewed namespaces. Do not derive NPC portraits from names or equate third-party item IDs with official IDs.
- Review newly encountered cache/update file types before making them eligible for cleanup; unknown files remain preserved.

## Community identity and operations

**Available:** owned upload management, credential backups/import, privacy changes, request retry receipts, moderation reports/audit history, private authenticated server dashboard, public PvE/PvP class/player samples and an updater that checks successful main CI before installing/restarting. Existing-host deployment must be confirmed separately from repository publication.

**Remaining:** verified character claims, opt-out of appearances in others' uploads, account/device recovery and named moderator roles/appeals need a trustworthy authentication design. Shared admin credentials establish credential use, not the identity of a person. Previously downloaded public data cannot be recalled.

## Pending user-supplied evidence

The user will supply the following later; these are pending inputs, not completed verification:

- A current-build diagnostic capture with independently known character/server, difficulty, boss and outcome. This is required for additional identity/protocol variants and classification validation.
- PURPLE install registration/configuration metadata, when available, for formats not covered by installed-game discovery. A KR/Taiwan installation is optional and is not a prerequisite for independent work.
- Any available in-game Genus/Pantheon allocation export or independently recorded allocation data for source-backed import and board reconstruction.

New capture data and a registered Global PURPLE installation are available for review. Additional independently known capture labels remain pending. Repository-wide automatic merging also remains pending the specific authorization previously requested.

## How to supply the remaining evidence

Record from before entering the instance when possible; include the full encounter and completion. Preserve the ordinary saved combat log as well as a diagnostic ZIP, the app version, selected installation/build, character/server, known difficulty and observed outcome. For protocol investigations, enable TCP payload recording before Start; for checkbox-specific issues, provide a separate unchecked capture with its capture counters. Partial captures are still useful when labeled accurately. Supply explicit in-game observations or source records for new boss roles, Genus lines, crafting rules and timer scope.

## Build workspace and asset collection

**Available:** section tabs for skills, passives, stigmas, Daevanion, equipment, arcana, Pantheon and Genus. Budgets appear in the relevant allocation sections. Equipment uses inventory-slot tiles with source-linked catalog item images and enhancement choices; arcana uses separate card slots with skill icons and level selectors. Pantheon shows editable modeled deity contributions and read-only recorded totals. Model inputs and official source snapshots remain distinct.

Highest available server-reported skill, stigma and Daevanion totals supply personal planning and comparison scopes; reports are observations, not verified progression maxima. Combat log tabs are Community Combat Logs, My Uploads and Saved Logs. Boss portraits accompany boss names and progression; repeated portraits beside session-opening buttons are omitted.

Scheduled collection tracks source-ID image mappings, revisions and hashes. Community source slugs remain separate from numeric game IDs. Unknown NPC IDs and role changes are staged in a catalog audit; collection context does not establish current-build applicability. New snapshots open review PRs. Automatic merging remains disabled pending explicit repository-wide authorization.

**Remaining:** verified in-game Pantheon node/allocation data and artwork, official Genus allocations, current-build item rules and verification of the installed production package. Fresh anonymous comparison candidates can reach the server through its preset API or the explicit regeneration CLI; their receipt is separate from confirming the installed package version. Catalog equipment selection includes fixed stats, listed enhancement bonuses and entered random-roll lines bounded by the source pool, count and ranges. Unsupported effects remain unscored; source ranges do not establish current-build legality. Imported aggregate contributions must be removed when replacing them with individual gear to avoid overlap.

Crafting, Build Workspace and embedded maps use the available horizontal display space, with layouts that collapse on smaller screens.


## Remaining work and its prerequisites

| Open item | Prerequisite / next action |
| --- | --- |
| Local identity, pet ownership, repeated encounters and partial-instance capture validation | Current-build diagnostics with known participants and outcomes, including separate TCP-checkbox states. The user is collecting these. |
| Cross-part boss attempts and ranking promotion | A stable boss lifetime/attempt identifier, plus captured entry, completion and loss evidence. Existing part/run tokens support descriptive review; they do not distinguish reused actor IDs or restore missing packets. |
| Cross-uploader fight matching and defeat deduplication | Independently labeled simultaneous perspectives with physical server/channel scope; define conservative ambiguity/rejection rules before fusing records. |
| PURPLE discovery and regional build metadata | Verified registration/configuration samples; preserve launcher namespaces. KR/Taiwan is optional. |
| Difficulty, encounter roles and calibrated automatic classification | Independent labels, modifier/party-scaling context and held-out captures by build/region. Catalog or HP similarity alone does not establish the requested precision. |
| Defensive PvE/PvP mechanics and reactive matchups | Verified effect coefficients, cooldown/action costs, mitigation and representative matchup validation. Stationary gross damage remains a proxy. |
| Official Genus/Pantheon import and board artwork | Supported allocation payloads, stable node IDs and source-backed rules/assets. Manual controls remain available. |
| Casts, buffs, movement, PvP teams/rounds/objectives and mixed-segment mode | Representative packets with known actions, coordinates, targets and outcomes. Preserve unknown effects rather than assigning them from damage patterns. |
| Timers, crafting and native maps | Verified scoped schedules/respawns, crafting failure/refund/modifier rules and permitted map coordinates/layers/assets. Existing source-attributed tools remain usable. |
| Further NPC/item/title images and namespaces | Source-ID records and reviewed asset mappings. Scheduled collection already stages new source snapshots for review. |
| Device screenshot/cache verification | Affected-device checks and examples of additional file types before expanding cleanup. Unknown files remain preserved. |
| Character claims, opt-out, recovery and moderator identity | A trustworthy account/character ownership source and recovery policy; shared upload/admin keys do not establish a person's identity. |
| Production deployment verification | Confirm the installed server version through authenticated host access. Successful preset API receipts confirm candidate evaluation and replacement outcomes, but do not confirm the installed package version or execution of the native regeneration CLI. |
| Repository-wide auto-merge capability | The specific authorization requested after automatic approval review rejected the broader setting change. Asset PR creation and review continue. |

These items are still open. The postponed captures and metadata are required inputs for their dependent implementation and validation, not new bug reports or a completed roadmap.

## Character import during catalog updates

A newly reported database-lock error exposed catalog transactions spanning network fetches. Catalog page and item writes now commit before the next remote request, failed sync transactions roll back, and failed connection initialization closes without caching the connection. Character/profile asset writes commit or roll back together. Validation on the affected device remains pending.

## Empty base-stat tables after sync

A new character import error was traced to empty base-stat tables in all eight local class overlays. Loading recovers the bundled table with an import warning; sync rejects incomplete tables before replacing class data. Source-page extraction now accepts the observed CSS classes and Lv. labels rather than depending on an undefined CSS class and bare level numbers.

## Optimizer and PURPLE metadata follow-up

Dedicated PvE kits now cover all eight classes; PvP still uses the generic mode-specific kit. Spiritmaster pet and Gladiator stack state are isolated per simulation so repeated rotation and stat-weight evaluations do not carry state between runs. Assumed animation, chain/proc, pet and boss-control timings still require capture calibration. Registered PURPLE installs can report completed VersionInfo launcher revisions under a separate service namespace; Global revision 27 is not Steam build 25767555 and does not identify a physical region. Unregistered PURPLE discovery remains pending.
