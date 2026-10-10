# Roadmap and completion criteria

This page describes current capabilities and remaining work. Release-by-release changes belong in [GitHub Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases). See [the app guide](app.md), [user guide](user-guide.md) and [methodology](methodology.md) for behavior and limits.

The seven requested workstreams have delivered their implementation checkpoints. Some follow-ups depend on game data or protocol evidence that is not available yet; they remain open below. A display, proxy or entered assumption is not a verified game mechanic.

## 1. Capture reliability and recording reconstruction

**Available:** continuous bounded-part archival, periodic recovery snapshots, saved-part pagination and upload queues, durable upload request retries, part discovery, combined stopped-part review and original-source navigation. Shared outgoing-damage clocks freeze during inactivity, resume without resetting player totals and use a minimum 120-second automatic split gap. Partial mid-instance captures remain visible and unranked. Supported late roster and summon-owner evidence reconciles retained effects within its identity context. A combat event carries explicit owner, pet and local-player markers, so the meter folds a pet's damage into its owner instead of counting a phantom player, tracks the local recording player, and in a solo partial capture attributes an unowned pet to the sole local player; saved a2log documents record pet hits under their owner with a pet entity link. Overlay DPS/HPS/incoming metrics, grouping, text colors and foreground behavior are configurable.

**Remaining:**

- Support additional local-player, spawn, roster, death and instance-entry protocol variants using representative captures. The owner/pet/local markers and the solo-capture pet fallback are in place, but the decoder must set them from verified protocol evidence; in a multi-player capture an unowned pet is still left with its own identity rather than guessed. Do not assign an unnamed actor from class, name similarity, proximity or damage.
- Confirm the zone/ownership and repeat-encounter fixes on affected devices and game sessions, with TCP recording both enabled and disabled.
- Stitch boss attempts crossing archive parts, reconcile overlaps and retain contradictory/ambiguous source evidence. Promote complete chains to rankings only after explicit entry/completion, stable identity and loss evidence pass independently defined rules.
- Improve matching of incomplete views from multiple uploaders without merging unrelated fights. Lost upload responses retain ownership-recovery limits even when request retries prevent duplicate creation.
- Add additional supported OS/driver loss evidence. Missing or zero counters cannot prove loss-free capture, and driver/TCP counters must not be added as unique packet loss.

**Completion evidence:** entry-to-completion captures, partial captures, party/zone changes, reconnects, stops and rollovers with known participants/outcomes. Historical missing packets cannot be restored.

## 2. Encounter classification, game versions and catalog coverage

**Available:** validated Steam/registered-install discovery and local selection, executable Product versions with diagnostic launcher IDs, recorded regional server identity, automatic exact map/instance/NPC catalog matching, post-recording corrections, evidence explanations, unresolved-ID exports and a reproducible pinned upstream catalog audit. Public boss HP candidate signatures retain build, region, context, roster size and source provenance. Reported maximum HP stays separate from peak observed current HP. A launcher-independent shipped-content fingerprint (sha256 of the sorted `.pak`/`.utoc`/`.ucas` name+size manifest) is recorded alongside the Product version, and `python -m aion2calc install-version` compares the version signals across detected installs.

**Remaining:**

- Measured on a real dual-launcher pair (Steam and PURPLE, nominally the same game): the shipped-content fingerprints did **not** match exactly — 743 of 758 packages byte-identical, 15 content chunks drifted a small amount (`pakchunk0`, the `pakchunk220000` cluster, `pakchunk30000`, `pakchunk41001`), none added or removed. That is the same content base at a different patch/hotfix tick, so the fingerprint is kept as a diagnostic signal and is **not** promoted to an authoritative cross-launcher key; `install-version`/`compare_installs` now quantify identical/drifted/only-some package overlap instead of a binary match. Neither the launcher-stamped Product version nor the raw content set is a reliable shared game version on its own, because installs drift by patch revision independently per launcher. A clean confirmation would need two installs patched to the exact same revision at the same time; even then the comparator reports overlap rather than assuming identity.
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

- Replace the kits' estimated animation/pet `TIMING` with measured values. `python -m aion2calc calibrate --capture LOG --timings` now measures per-skill cast cadence (the shortest filler interval bounds its action time) and pet swing periods directly from a capture, reported against the kit so timings are fitted to real logs rather than community estimates. Measured evidence only; defensive/healing/CC mechanics below still need verified coefficients.
- Model verified defensive skills, shields, percentage HP, healing, CC duration/success/immunity and movement effects with explicit action/cooldown costs.
- Model matchup-specific incoming/outgoing mitigation, worst-case timing alignment and reactive optimized opponents.
- Validate model predictions against representative encounters and matchups. Gross expected damage and entered pressure reductions are assumptions, not effective HP, guaranteed survival or win probability.
- Verify current-build gear-roll legality and model reactive tactical decisions from verified mechanics. Catalog item selection, enhancements, distinct source-pool roll entry and bounded full-window priority search for fixed draft allocations are available. This local search does not optimize allocations or establish a globally optimal or competitive PvP strategy.

**Completion evidence:** current-build coefficients, mechanics and validation captures. Competitive PvP claims require more than a damage ranking.

## 4. Genus Insight and progression

**Available:** manual five-genus/nine-slot editor, unlocked-slot validation, saved inventory/advice snapshots, in-game-inspired radial presentation, per-slot damage contribution and supported-slot replacement advice. Saved modeled lines participate in PvE/PvP optimization. Coverage distinguishes saved, unlocked and missing slots; progression budgets retain observed-versus-entered provenance. The official profile import records each Pantheon deity stat's total and its self-describing effect strings (e.g. Justice → Defense +4%, Perfect Chance +4%), splitting damage effects from survival/utility ones, with source attribution, and now labels each deity with its proper name (Justice → Nezekan, Time → Siel, …) transcribed from the in-game Pantheon screen. A first ground-truth capture of the in-game Genus Insight and Pantheon (`data/global/genus_pantheon_observed.json`) records one character's five genus levels, Analysis Effect lines and the nine Pantheon deities' display values with full provenance — a reference to validate the model against, not fed into the damage model.

**Remaining:**

- Retrieve official Genus allocations and owned collection effects when a supported source provides them. Verified against the live official character API (`/api/character/info` + `/equipment`): it exposes no Genus Insight allocations, Pantheon node allocations or collection data — only deity stat totals with effect strings (now recorded) and a cosmetic pet summary. A hand-transcribed in-game observation now exists (`genus_pantheon_observed.json`: five genus levels + Analysis Effect lines, nine deity display values, 15/94 collection) as single-character ground truth; it validates the modelled structure but is not a per-level rule and is not auto-applied. It also showed re-analysis cost scales with genus level (Special Lv.10 = 248 soul crystals / 62,000 kinah), so the modelled flat analysis cost is a base figure. Blank Genus/collection slots are still not invented and stay manual-entry until a supported machine-readable source carries them.
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

**Available:** regional event pages, named-zone/local countdowns, dated community schedule provenance, conflict/staleness notices and public observed boss-defeat histories with party engagement and source-log links. Schedule windows and last defeats remain separate from availability. Uploads of one defeat recorded by several party members are grouped into a single distinct defeat (`python -m aion2calc defeats`, over the community server or a local a2log folder) by boss, region, difficulty, recorded instance, game patch, shared party identities and matching duration, so repeated perspectives do not inflate counts while clears at different difficulties, in distinct recorded instances or under different balance patches stay separate.

**Remaining:**

- Verify regional schedules and current-build applicability independently; copied community forecasts are not official schedules.
- Record physical server/channel scope and verify timed/world-boss roles and respawn rules.
- Harden same-defeat grouping toward respawn/availability estimates: the perspective dedup is a heuristic on recorded identities and duration, not proof, and repeat clears by one party are separated only by their duration spread. Physical server/channel scope and verified respawn rules are still required before a last defeat can estimate whether a boss is alive now.

**Completion evidence:** independently confirmed schedule/respawn rules and sufficiently scoped observations. A last observed defeat does not show whether a boss is alive now.

## 7. Website and shared player tools

**Available:** consistent Pages navigation, focused logs and character pages with Back to log, recorded images/equipment/stats/skills/boards, local build allocation drafts, catalog validation, saved drafts/import/export and community preset seeding. Maps use the provider's published embed mode for four supported maps. Crafting has a source-attributed recipe snapshot, profession/faction search, icons/rarity, crafted-product base stats, enhancement previews and possible random-roll ranges from ID-matched publisher records, mastery/fees/materials, supported intermediate expansion, conditional combo scenarios and material-plan export. Official Global/Korean/Taiwan headline/preview cards preserve region, publication/retrieval dates, source-provided summaries, approved official thumbnails and original links.

**Remaining:**

- Verify current-build arcana rules and obtain Pantheon node controls/artwork from source data as described in workstreams 3–4. Catalog card skill selectors now use bundled class/slot pools and grade/enhancement bounds, separate from manual skill bonuses. Explicit draft rescoring is available without publishing or changing source profiles.
- Obtain permitted native map coordinates, layers and assets if replacing the provider viewer with local map tools. Cross-origin provider account/checklist state remains with the provider.
- Verify crafting general success/failure rewards, refunds, combo quantity/replacement rules, modifier formulas and build/region applicability. Current combo simulations are conditional completed-craft checks, not guaranteed item yields.
- Confirm item-stat and recipe applicability to current Product versions/regions. The detailed snapshot supplies stats for 1,162 of 1,288 output records; the other 126 retain unavailable status. These counts describe source coverage, not verified live-game completeness.
- Add further feeds only after confirming their official source, API/RSS availability and reuse constraints. Do not embed arbitrary article HTML or invent summaries/images absent from a supported feed.
- Supply the remaining NPC ID-to-image mappings. The catalog has portrait art for 1,321 of 9,780 NPCs; `python -m aion2calc npc-evidence` now ranks the observed NPC type IDs with no bundled portrait by how often uploads hit them, so art is sourced for the NPCs players actually encounter first. Skill/item icon URLs are derived from IDs and checked at runtime by the asset-health report; only art genuinely absent from a supported source is reported, never invented.

## Maintenance, screenshots and assets

**Available:** application-content screenshots include below-fold content without monitor capture; storage inventory and explicit cleanup cover recognized disposable caches; updater helpers self-clean and bounded retention preserves recent logs, releases and active helpers. Saved logs, imports, credentials, results and upload queues are preserved. Asset diagnostics distinguish browser failures, proxy status, official same-region/item-ID references and publisher-specific item namespaces. Pinned catalog audits and profile image re-indexing are available.

**Remaining:**

- Confirm full-page rendering on target devices and handle browser/CORS limitations for remote images.
- Reconcile additional item/title/NPC/passive assets using stable source IDs and reviewed namespaces. Do not derive NPC portraits from names or equate third-party item IDs with official IDs.
- Review newly encountered cache/update file types before making them eligible for cleanup; unknown files remain preserved.

## Community identity and operations

**Available:** owned upload management, credential backups/import, privacy changes, request retry receipts, moderation reports/audit history, private authenticated server dashboard, public PvE/PvP class/player samples and an updater that checks successful main CI before installing/restarting. Existing-host deployment must be confirmed separately from repository publication. Settings can query the configured server’s discovery response for its running server/analyzer package versions; older servers that omit these fields remain explicitly unverified. `python -m aion2calc doctor` is an operator self-check that gathers the client-verifiable operations state in one read-only pass — install kind/version, the CI-gated updater and its remembered release, writable home/logs/results/data paths, the configured log server's discovery (flagging servers that do not report their version), and the catalog source manifest — while stating that device screenshot checks and the server's ownership/recovery/moderator policies are verified on the operator's device and server deployment, not from the client.

**Remaining:** verified character claims, opt-out of appearances in others' uploads, account/device recovery and named moderator roles/appeals need a trustworthy authentication design. Shared admin credentials establish credential use, not the identity of a person. Previously downloaded public data cannot be recalled.

## Pending user-supplied evidence

The user will supply the following later; these are pending inputs, not completed verification:

- A current-build diagnostic capture with independently known character/server, difficulty, boss and outcome. This is required for additional identity/protocol variants and classification validation.
- PURPLE install registration/configuration metadata, when available, for formats not covered by installed-game discovery. A KR/Taiwan installation is optional and is not a prerequisite for independent work.
- Any available in-game Genus/Pantheon allocation export or independently recorded allocation data for source-backed import and board reconstruction.

New capture data and a registered Global PURPLE installation are available for review. Additional independently known capture labels remain pending. Repository-wide auto-merge capability is enabled for the public client repository after explicit authorization. GitHub does not enable it for the private server repository on the current account plan; that requires a plan supporting private-repository auto-merge.

## How to supply the remaining evidence

Record from before entering the instance when possible; include the full encounter and completion. Preserve the ordinary saved combat log as well as a diagnostic ZIP, the app version, selected installation/build, character/server, known difficulty and observed outcome. For protocol investigations, enable TCP payload recording before Start; for checkbox-specific issues, provide a separate unchecked capture with its capture counters. Partial captures are still useful when labeled accurately. Supply explicit in-game observations or source records for new boss roles, Genus lines, crafting rules and timer scope.

## Build workspace and asset collection

**Available:** section tabs for skills, passives, stigmas, Daevanion, equipment, arcana, Pantheon and Genus. Budgets appear in the relevant allocation sections. Equipment uses inventory-slot tiles with source-linked catalog item images and enhancement choices; arcana uses separate card slots with skill icons and level selectors. Pantheon shows editable modeled deity contributions and read-only recorded totals. Model inputs and official source snapshots remain distinct.

Highest available server-reported skill, stigma and Daevanion totals supply personal planning and comparison scopes; reports are observations, not verified progression maxima. Combat log tabs are Community Combat Logs, My Uploads and Saved Logs. Boss portraits accompany boss names and progression; repeated portraits beside session-opening buttons are omitted.

Scheduled collection tracks source-ID image mappings, revisions and hashes. Community source slugs remain separate from numeric game IDs. Unknown NPC IDs and role changes are staged in a catalog audit; collection context does not establish current-build applicability. New snapshots open review PRs. Auto-merge capability is enabled on the client repository; GitHub plan support is still required for the private server repository. Individual PRs require a separate opt-in.

**Remaining:** verified in-game Pantheon node/allocation data and artwork, official Genus allocations, current-build item rules and verification of the installed production package. Fresh anonymous comparison candidates can reach the server through its preset API or the explicit regeneration CLI; their receipt is separate from confirming the installed package version. Catalog equipment selection includes fixed stats, listed enhancement bonuses and entered random-roll lines bounded by the source pool, count and ranges. Unsupported effects remain unscored; source ranges do not establish current-build legality. Imported aggregate contributions must be removed when replacing them with individual gear to avoid overlap.

Crafting, Build Workspace and embedded maps use the available horizontal display space, with layouts that collapse on smaller screens.


## Remaining work and its prerequisites

| Open item | Prerequisite / next action |
| --- | --- |
| Local identity, pet ownership, repeated encounters and partial-instance capture validation | The meter now folds pet damage into its owner, tracks the local player and attributes an unowned pet to the sole local player in a solo capture (owner/pet/local event markers). Remaining: multi-player protocol variants and validation against current-build diagnostics with known participants and outcomes, including separate TCP-checkbox states. The user is collecting these. |
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
| Server repository auto-merge capability | Explicit authorization is received and the client setting is enabled. GitHub rejects private-repository protection/auto-merge on the current plan; a supporting account plan is required to keep the server repository private. |

These items are still open. The postponed captures and metadata are required inputs for their dependent implementation and validation, not new bug reports or a completed roadmap.

## Character import during catalog updates

A newly reported database-lock error exposed catalog transactions spanning network fetches. Catalog page and item writes now commit before the next remote request, failed sync transactions roll back, and failed connection initialization closes without caching the connection. Character/profile asset writes commit or roll back together. Validation on the affected device remains pending.

## Empty base-stat tables after sync

A new character import error was traced to empty base-stat tables in all eight local class overlays. Loading recovers the bundled table with an import warning; sync rejects incomplete tables before replacing class data. Source-page extraction now accepts the observed CSS classes and Lv. labels rather than depending on an undefined CSS class and bare level numbers.

## Optimizer, Product version and continuous capture follow-up

Dedicated PvE kits now cover all eight classes, modeling each class's chains, crowd-control combos, damage-amp buffs and (Spiritmaster) its summoned pet; the Spiritmaster kit now models the Ancient Spirit stigma as the real endgame pet, which the allocation optimizer levels accordingly. PvP still uses the generic mode-specific kit, which now also models chain follow-ups and extra-damage spec riders. Front and Back Attack Damage Boost are applied as their own damage bucket. The macro layout reserves the left mouse button for the class's basic auto-attack rather than an arbitrary skill. Spiritmaster pet and Gladiator stack state are isolated per simulation. Assumed animation, chain/proc, pet and boss-control timings still require capture calibration, which is the main open item for the kits.

The full executable ProductVersion string identifies new comparison groups across Steam and PURPLE, with engine file versions and launcher IDs retained as diagnostics. Both observed installations report 1.0.21.0.2026031801. Legacy logs retain their recorded identifiers; no missing historical Product version is guessed. Registered PURPLE discovery is supported; unregistered discovery remains pending.

Encounter completion does not request capture shutdown. Recoverable malformed-packet decoder exceptions reset affected stream framing and continue capture with explicit loss/error evidence. Fatal adapter/programming/storage errors still stop visibly. Affected-device confirmation and independently labeled capture details remain pending.

## Recorder latency and remaining boss HP

Ping samples are aligned to each encounter's actual origin and uploaded with the log. Desktop, Pages and server review show recorder-side ping over time and sample average/minimum/maximum. Passive TCP acknowledgement RTT is not a measurement of every party member or game action latency. Recorder identity is shown only when recorded; otherwise the connection remains unattributed. Remaining boss HP uses the latest observed sample and its timestamp, with percentages only when a maximum was recorded. Boss HP belongs in post-run log review only; overlay HP is excluded by user preference. Affected-device confirmation remains pending.

Kit ASSUME calibration remains pending independently labeled A2Parser captures with class, equipment, skill levels, selected pet, timings and boss-control context. Damage-effect spacing does not identify animation/cast duration or CC success. No assumed coefficients were changed from unlabeled capture data.

## Compressed-frame recovery and graph review

Malformed LZ4 blocks observed in four local diagnostic archives previously escaped decoder recovery and stopped capture. Bundle decompression is cached within each received batch with shared byte/depth limits; rejected compressed frames retain loss/error evidence while valid neighboring frames and subsequent encounters continue. Run completion never ends the capture adapter. Device confirmation remains pending. Graph hover detail uses player/metric and boss-HP tables; player series are ordered together. Overlay ping has its own wrapping row beneath the controls, with current/average/minimum/maximum or a no-samples message. Missing community-preset weights are calculated and cached locally for display, using the common weighted scenarios and fixed saved rotation.


## Automatic NPC troubleshooting evidence

New live-session logs and diagnostic exports retain bounded numeric spawn-decoder observations without enabling TCP payload recording. Each identity epoch includes scan/candidate counters, omitted-observation counts and up to 128 recognized spawn observations (32 epochs maximum), with actor ID, timestamp, opcode, decoded NPC code or missing-type-marker status. Scan counts include outer and decompressed scans and are not unique packet counts. Evidence is validated on import and upload; packet bytes, text and connection addresses are excluded. A missing observation does not prove no packet arrived, particularly after truncation or an unsupported opcode. This helps diagnose missing NPC links but cannot reconstruct an unfamiliar packet format; optional raw capture can still be needed. Historical logs do not gain missing evidence retroactively.

The user confirmed continuous capture, cleanup, partial runs and character imports work again. Ascension missing NPC-type identities remain a new pending report; catalog boss portraits already exist. Responding production packages were verified as server 0.2.65 and analyzer 0.2.115 before this update.


Genus roll goals appear in current/optimized results and Gear & Advice even for level-only inputs. PvE shows the catalog upper-range Damage Boost target for slots 4 and 7, with unlock levels and saved-line comparisons. Other stat ranges and numeric PvP targets remain unavailable from supported sources; targets do not establish live-version legality or expected reroll outcomes.
