# Roadmap and completion criteria

This page describes current capabilities and remaining work. Release-by-release changes belong in [GitHub Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases). See [the app guide](app.md), [user guide](user-guide.md) and [methodology](methodology.md) for behavior and limits, and [open investigations](open-investigations.md) for the detailed findings behind the gated items.

The seven requested workstreams have delivered their implementation checkpoints. What is left is mostly **gated on inputs we do not control** — a verified in-game capture, source-confirmed data, or hardware to test on — rather than unwritten code; each item says what it waits on. A display, proxy or entered assumption is not a verified game mechanic.

**This page has four parts:**

- **[✅ Shipped](#-shipped--implemented-and-in-the-app)** — what already works today.
- **[🚧 Outstanding](#-outstanding--still-to-build-or-verify)** — what is left, and what each item is waiting on.
- **[📥 Waiting on the owner](#-waiting-on-the-owner)** — tests and captures only the owner can supply.
- **[Detailed notes by workstream](#detailed-notes-by-workstream)** — the evidence requirements and caveats behind each area.

---

## ✅ Shipped — implemented and in the app

- **Capture & recording** — continuous bounded archival, periodic recovery snapshots, saved-part pagination, durable upload queues/retries, combined stopped-part review; **runs stitched across archive parts and boss attempts cut by a rollover merged back into one ranked encounter (server 0.2.96: same archive id *and* uploader key, connected retained-record continuity, the per-run token carried across the boundary, each encounter's own evidence still assessed)**; **the same fight recorded by several party members matched by a 64-largest-hit sketch (half the smaller sketch shared, same context, starts within ten minutes) and counted once per character (server 0.2.96)**; shared DPS/HPS clocks that freeze on inactivity and auto-split after 120s; partial mid-instance captures stay visible and unranked; owner/pet/local-player packet markers fold a pet's damage into its owner and attribute a solo-capture pet to the local player; configurable overlay metrics.
- **Encounter classification & catalog** — Steam/registered-install discovery and selection, executable Product versions, recorded regional server identity, exact map/instance/NPC matching, post-recording corrections, unresolved-ID exports, a pinned catalog audit, boss-HP candidate signatures with provenance, a shipped-content fingerprint with `install-version` cross-install comparison, and runs in instances the catalog does not name labelled by their final boss (0.2.294).
- **Optimizer** — separate PvE/PvP objectives and saved results, weighted damage scenarios, crystal-HP reserves, skill/stigma reservations, timed expected-hit traces, imported PvP opponents, canonical community presets with server regeneration, and `calibrate --timings` measuring cast/pet cadence from a capture. Dedicated PvE kits for all eight classes. The build workspace (skills, passives, stigmas, Daevanion, equipment, arcana, Pantheon and Genus tabs) is described in [the app guide](app.md#build-workspace).
- **Genus & progression** — the five-genus/nine-slot editor with validation, saved snapshots, per-slot contribution and replacement advice; **per-slot roll targets from the bundled Global slot property tables (2,062 properties, value ranges per grade), scored on the character's build whether or not anything is recorded (0.2.291)**; official-profile Pantheon deity totals, effect strings and proper deity names; **a bundled Pantheon decoration catalog (colossi, statues, artworks with deity points, availability and sources) and the recommended board by modeled damage (0.2.291)**; a hand-transcribed ground-truth reference capture; collected characters contribute their observed point allocations to the community totals (0.2.238, opt-out).
- **Combat analytics** — shared desktop/Pages/server review with run/encounter/participant scopes, graph keys, hover/click detail, damage/healing/incoming breakdowns, peak windows, death recaps, imported buff overlap and evidence coverage; pet combine without destroying source IDs; normalized positions handed to Raid Planner; and a **per-effect PvE/PvP split** so a mixed segment counts only its mode-matching damage toward each mode's community ranking (server 0.2.79).
- **Timers & timed bosses** — regional event pages and countdowns with dated provenance and staleness notices, public observed boss-defeat histories, perspective-dedup grouping of one defeat seen by several party members (**hardened with an anonymized party signature so different parties killing near-simultaneously stay distinct, server 0.2.78**), a field-boss kill auto-report (≥2 reporters) and a community respawn reference, the **overlay event-notification strip with an optional chime (0.2.233)**, the Fera bot consuming and refreshing `field-bosses.json` (bot PRs #5, #6), and **observed field-boss timers** on the overlay strip and the Timers page (0.2.298).
- **Website & shared tools** — Pages navigation, focused log/character pages, local build drafts, catalog validation, preset seeding, embedded maps, a source-attributed crafting snapshot, official news cards, **per-verified-profile Server/Region matched comparisons (server 0.2.75)**, the **"why a scope is Unavailable" hint (0.2.231)**, **community NPC portraits displayed behind the curated table (client 0.2.232, server 0.2.76–0.2.77)**, and attributed collection routes for Verteron, Altgard and Chaotic Lower Reshanta on the Maps page (0.2.296).
- **Live meter & overlay quality-of-life** — run segmentation and the partial-capture/17-player/mid-reset fixes; overlay lifecycle + collapse-to-tray; layout, colour, font, background and per-element font settings with halo/retroreflection effects; enemy-HP / target / TTK / contribution / combat-power / death readouts; identity re-acquisition; live-millisecond DPS; screenshot-and-lock; FPS counter; settings backup/restore; layout-aware multi-monitor position restore; the **community-rank badge (0.2.230)**, optionally refreshed after each ranked fight (0.2.245); a **target portrait on the overlay (0.2.232)**; OBS Browser-Source + click-through and configurable global hotkeys (Windows; the native layer, multi-monitor placement and hotkeys were **validated by the owner on 2026-10-16**); the overlay reset on a boss pull and after the kill (0.2.277, hardened in 0.2.302 and 0.2.304).
- **Maintenance & operations** — application-content screenshots, storage inventory and cleanup, self-cleaning updater with bounded retention, asset diagnostics, owned-upload management, credential backup/restore, a private authenticated dashboard with a **Deployment card (server 0.2.99)**, a CI-gated auto-updater that also keeps the pinned analyzer current, the **Merge on green** workflow (server 0.2.101), and `doctor` self-check.
- **Community identity & auth** — recording-backed character claims, the verified mark, the pseudonymising opt-out, renewal, recovery, seven-day challenges and scoped moderator credentials (**0.2.295 / server 0.2.100**).
- **Uploads & timers** — automatic uploads from every way the meter stops, the launch catch-up (0.2.293), the **per-fight upload** when a boss dies (0.2.297), the upload of a recording before auto-delete reclaims it (0.2.237); the **value probe** for undecoded records (0.2.299); **RTSS in-game text**, first draft (0.2.300).

## 🚧 Outstanding — still to build or verify

- **Combat analytics** — **decoded from the supplied captures (17 October; [findings](open-investigations.md#combat-records-decoded-from-the-diagnostic-captures-17-october)):** skill casts with their target, cast/lock time and cooldown; chain-skill windows; party buffs and enemy debuffs/crowd control with source and exact duration; the boss **break gauge**; dodges, dashes and movement; NPC casts. *Buildable now:* bring them into the meter and log review (cast timeline and rotation, buff/debuff uptime, CC landed and how long it held, break-gauge contribution and break windows), then confirm the names against what the game shows. *Still gated on probe captures or labelled evidence:* resources (MP), shield absorption, interrupts, misses, mitigation, effective healing/overheal, position units and map transforms, PvP teams/rounds/kill credit, and encounter mechanics before naming phases or avoidable damage.
- **Capture & recording** — more local-player/spawn/roster/death/instance protocol variants from verified captures (in a multi-player capture an unowned pet stays unguessed); more OS/driver loss evidence; an archive part that repeats some of its predecessor's records still breaks run stitching instead of being de-duplicated (server). *Gated on current-build diagnostic captures with known participants and outcomes (TCP recording on and off).*
- **Encounter classification & catalog** — a reliable cross-launcher version key (fingerprints drift by patch per launcher); unregistered-PURPLE install-path discovery; build/region applicability for catalog records and boss signatures; independently confirmed difficulty labels; calibrated ≥99%-precision auto-classification; remaining NPC identity variants (map 200003, the map-61 arena name) and the Citadel of the Fallen Daeva tiers' final boss; **trusted, id-verified boss roles and portraits** (a community portrait fallback fills art meanwhile). *Gated on source-backed mappings and labelled captures.*
- **Optimizer** — replace the kits' estimated cast timings with the measured cast/lock times and cooldowns now readable from the cast records; measured defensive/shield/healing/CC coefficients and costs; matchup-specific mitigation, worst-case timing and reactive opponents; validation against representative encounters; current-build gear-roll legality. *Gated on verified coefficients and validation captures.*
- **Genus & progression** — verified defensive/owned-effect coefficients, roll probabilities, costs and maxima. Genus and Pantheon allocations stay **manual entry**: the game exposes no API for them, so there is no official import to wait for. *Gated on source-backed formulas or in-game observations.*
- **Timers & timed bosses** — independently verified regional schedules and respawn rules (the reference stays community-unverified, shown as such); physical server/channel scope (a kill on another channel is still a kill on your server); recognising field bosses the catalog misses (captures); confirming Verteron's open-world map ids by an Elyos kill (Altgard's are confirmed by the feed).
- **Website & shared tools** — populating the **World** comparison scope (needs enough encounter metadata to match); verified arcana and Pantheon artwork; permitted native map coordinates/layers/assets; verified crafting success/refund/combo rules; item-stat/recipe applicability to current builds; further feeds only from confirmed official sources; the **remaining id-verified NPC portraits**. *Gated on source data and cohort/metadata coverage.*
- **Live meter & overlay** — **RTSS in-game text** awaits the owner's live test; identity after a **Kibelisk teleport** awaits a capture that spans one (a name-based re-bind covers it since 0.2.300); estimated time-to-enrage stays data-gated; two hotkey actions are not wired yet (a combat-assist UI and a field-boss/artifact status); macOS/Linux native overlay and hotkeys are **optional**, kept as tested scaffolds until a Mac or Linux machine with the game is available.
- **Community identity & auth** — authenticated appeals.
- **Routes & companion features** — gathering-node and mob-farming loops with waypoints need a source that publishes node or camp positions under reuse terms (none does yet; the catalog links guides only). A **Hidden Cube radar** and a **server-driven field-boss respawn feed** (candidate opcode `01 91`) need a capture with raw TCP recording and the values noted, for the value probe to confirm the records first. A **skill-cooldown overlay** no longer needs the probe: the cast records carry each skill's cooldown.
- **Maintenance** — confirm full-page screenshots on target devices; reconcile further item/title/NPC/passive assets by stable source ids; review newly seen cache/update file types before making them eligible for cleanup.
- **Deployment & infrastructure** — nothing outstanding.

## 📥 Waiting on the owner

These are inputs only the owner can supply; the dependent items above stay open until they arrive.

- **RTSS live test** on 0.2.301 or later (Settings → In-game (RTSS), Windows): position, size and the colour-tag style are the parts most likely to need adjusting.
- **A Kibelisk teleport capture** in the open world with raw TCP recording on, to confirm the packet sequence behind the identity loss.
- **Value-probe captures** with raw TCP recording on and the in-game values noted at known times — a Hidden Cube count, Odyle Energy, a cooldown, your MP — for `python -m aion2calc probe` to pin the records.
- **A labelled current-build diagnostic capture**: character and server, difficulty, boss and outcome, ideally once with TCP recording on and once off.
- **Optional:** PURPLE launcher registration/configuration metadata for formats installed-game discovery does not cover; a glance at the in-game break bar and buff timers during a capture, to confirm the decoded names (the decodes themselves are consistent across eight captures).

**How to supply it:** record from before entering the instance when possible and include the full encounter and its completion. Keep the ordinary saved combat log as well as the diagnostic ZIP, and note the app version, installation/build, character/server, known difficulty and observed outcome. For protocol questions, enable TCP payload recording before Start; for a checkbox-specific issue, add a separate unchecked capture with its counters. Partial captures are still useful when labelled accurately.

---

## Detailed notes by workstream

The notes below keep the per-area detail the summaries distill: what is available, what remains, and the evidence that would close each item.

### 1. Capture reliability and recording reconstruction

**Available:** continuous bounded-part archival, periodic recovery snapshots, saved-part pagination and upload queues, durable upload request retries, part discovery, combined stopped-part review and original-source navigation. Shared outgoing-damage clocks freeze during inactivity, resume without resetting player totals and use a minimum 120-second automatic split gap. Partial mid-instance captures remain visible and unranked. Supported late roster and summon-owner evidence reconciles retained effects within its identity context. A combat event carries explicit owner, pet and local-player markers, so the meter folds a pet's damage into its owner, tracks the local recording player, and in a solo partial capture attributes an unowned pet to the sole local player. Runs that roll over between archive parts are stitched, and several party members' recordings of one fight are matched and counted once (server 0.2.96–0.2.98).

**Remaining:**

- Support additional local-player, spawn, roster, death and instance-entry protocol variants from representative captures. In a multi-player capture an unowned pet keeps its own identity rather than being guessed; never assign an unnamed actor from class, name similarity, proximity or damage.
- De-duplicate an archive part that overlaps its predecessor (repeats some of its records); today an overlap is a break, like a gap or a context change.
- Add further supported OS/driver loss evidence. Missing or zero counters cannot prove loss-free capture, and driver/TCP counters must not be added as unique packet loss.

**Completion evidence:** entry-to-completion captures, partial captures, party/zone changes, reconnects, stops and rollovers with known participants and outcomes. Historical missing packets cannot be restored.

### 2. Encounter classification, game versions and catalog coverage

**Available:** validated Steam/registered-install discovery and local selection, executable Product versions with diagnostic launcher IDs, recorded regional server identity, automatic exact map/instance/NPC catalog matching, post-recording corrections, evidence explanations, unresolved-ID exports (`catalog-gaps`) and a reproducible pinned upstream catalog audit. Public boss HP candidate signatures retain build, region, context, roster size and source provenance. A launcher-independent shipped-content fingerprint is recorded alongside the Product version, and `python -m aion2calc install-version` compares the version signals across detected installs.

**Remaining:**

- **Cross-launcher version key.** On a real Steam/PURPLE pair the content fingerprints did not match exactly: 743 of 758 packages identical, 15 drifted slightly, none added or removed — the same content base at a different patch tick. The fingerprint therefore stays a diagnostic signal; `install-version` reports identical/drifted/only-some overlap rather than a binary match. A clean confirmation needs two installs patched to the same revision at the same time.
- **Unregistered PURPLE install paths.** The launcher's `%LOCALAPPDATA%\NCSOFT\NccrData\com.ncsoft.aion2global\*.execution.json` confirms a PURPLE install and its version (`purple_launcher_evidence()`), but no plain launcher config carries the install path; the Windows uninstall entry is still the only machine-readable path source. Open pending the launcher's game-registry format.
- Establish build/region applicability for catalog records and boss signatures, including party scaling and encounter modifiers.
- Obtain independently confirmed difficulty labels and explicit difficulty flags. Received damage varies with mitigation, gear and buffs and cannot establish difficulty by itself.
- Calibrate probabilistic classification on independently labelled, held-out builds/regions: at least 99% measured precision before automatic promotion, abstaining when evidence conflicts.
- Resolve the remaining NPC identity variants: map 200003, the exact arena name for map 61, and a final boss for the Citadel of the Fallen Daeva tiers (600151–600153, until a capture shows one).
- Obtain explicit major/miniboss/world-boss roles and trusted, id-verified portraits; reindex derived progression after reviewed role changes. The broad catalog boss flag does not distinguish every miniboss.

**Completion evidence:** source-backed mappings and labelled captures by build, region, difficulty and scaling conditions. A current website announcement cannot retroactively identify an old log's build.

### 3. Optimizer damage, survival and optimized opponents

**Available:** separate PvE/PvP objectives and saved results, weighted damage scenarios, flat crystal-HP reserves, entered hit/sustained-pressure assumptions, trained-skill/stigma reservations and timed expected-hit traces. Imported optimized PvP opponents can supply gross-damage windows; the strictest entered incoming scenario constrains the personal build. Canonical community presets use comparable budgets and objectives; explicit server regeneration searches both scenario seeds and their weighted objective using current reported budgets.

**Remaining:**

- Replace the kits' estimated animation/pet `TIMING` with measured values. `calibrate --timings` measures cadence from damage spacing; the cast records decoded in workstream 5 give each skill's real cast/lock time (cast start to cast end) and its cooldown, which is the better source.
- Model verified defensive skills, shields, percentage HP, healing, CC duration/success/immunity and movement effects with explicit action/cooldown costs.
- Model matchup-specific incoming/outgoing mitigation, worst-case timing alignment and reactive optimized opponents.
- Validate model predictions against representative encounters and matchups. Gross expected damage and entered pressure reductions are assumptions, not effective HP, guaranteed survival or win probability.
- Verify current-build gear-roll legality and model reactive tactical decisions from verified mechanics. Source ranges do not establish current-build legality.

**Completion evidence:** current-build coefficients, mechanics and validation captures. Competitive PvP claims require more than a damage ranking.

### 4. Genus Insight and progression

**Available:** manual five-genus/nine-slot editor, unlocked-slot validation, saved inventory/advice snapshots, radial presentation, per-slot damage contribution and replacement advice, and per-slot roll targets. Saved modelled lines participate in PvE/PvP optimization. The official profile import records each Pantheon deity's total and effect strings with proper deity names. A hand-transcribed in-game observation (`data/global/genus_pantheon_observed.json`) validates the modelled structure without being fed into the damage model.

**Allocations are manual by design.** The official character API (`/api/character/info` + `/equipment`) exposes no Genus Insight allocations, Pantheon node allocations or collection data, and no other machine-readable source exists, so allocations are entered by hand; blank slots are never invented.

**Remaining:**

- Verify defensive/owned-effect coefficients, current-build roll probabilities, costs and progression maxima. Re-analysis cost scales with genus level (Special Lv.10 = 248 soul crystals / 62,000 kinah), so the modelled flat analysis cost is a base figure.

**Completion evidence:** source-backed formulas and limits, or user-entered in-game observations.

### 5. Combat analytics and protocol enrichment

**Available:** shared desktop/Pages/server review with focused log pages, run/encounter/participant scopes, graph keys, hover/click detail, timeline hide/collapse controls, damage/healing/incoming breakdowns, peak windows, explicit death recaps, imported buff overlap and evidence coverage. Linked pets can be combined without destroying source IDs. Normalized imported positions can be handed to Raid Planner.

**Decoded from the supplied captures (17 October).** Eight diagnostic captures with raw TCP recording yielded the server records for casts, cast ends, chain windows, party buffs, effect instances with durations (buffs, debuffs and crowd control on enemies), the boss break gauge, movement and NPC casts. The evidence is internal consistency across captures and builds — in seven of the eight captures a cast precedes 92–100% of the damage it causes, buff adds and removes pair up, durations match the field exactly, each skill moves the break gauge by a fixed amount. See [open investigations](open-investigations.md#combat-records-decoded-from-the-diagnostic-captures-17-october) for the layouts and numbers. The client-to-server direction is encrypted, so everything comes from the server's broadcast; in crowded areas the casts of distant players can be missing.

**Remaining:**

- Build the decoded records into the meter and log review: a per-player cast timeline and rotation, cast/lock times and cooldowns, chain usage, buff and debuff uptime with their sources, CC landed and how long it held, dodges, and break-gauge contribution with the break windows.
- Confirm the decoded names and meanings against in-game observations before presenting them as verified.
- **Boss break gauge (PvE only).** The gauge is decoded: a maximum that varies by boss (150 to 1200 in the captures) and a current value, a fixed contribution per skill, and a break of about five to seven seconds when it empties before it refills. Remaining: show each player's contribution and the break windows, never for PvP, and confirm the break timing against the in-game bar.
- Still undecoded: resources (MP/DP), shield absorption, interrupts, misses and mitigation; effective healing/overheal (the party HP feed makes it computable, still to verify); position units and map transforms (recognising a coordinate field is not decoding the map); PvP team/round/objective boundaries and kill credit (the reported RaZoR 0–3 arena loss has incomplete death evidence); encounter mechanics before assigning phase names, avoidable damage or causal advice.

**Completion evidence:** representative packets with independently known actions, targets, timing and outcomes.

### 6. Regional timers and timed-boss history

**Available:** regional event pages, named-zone/local countdowns, dated community schedule provenance, conflict/staleness notices and public observed boss-defeat histories with party engagement and source-log links. Uploads of one defeat recorded by several party members are grouped into a single distinct defeat (`python -m aion2calc defeats`) by boss, region, difficulty, recorded instance, game patch, shared party identities and matching duration, and the open-world kill feed keeps near-simultaneous kills by different parties apart by an anonymized party signature (server 0.2.78). Field-boss kills reach the server from an auto-report (shown once ≥2 reporters agree) and from per-fight uploads; the overlay strip and the Timers page count down the kills the live meter observed on the player's server and faction (0.2.298).

**Remaining:**

- Verify regional schedules and current-build applicability independently; copied community forecasts are not official schedules.
- Record physical server/channel scope and verify timed/world-boss roles and respawn rules. The same-defeat grouping is a heuristic on recorded identities and duration, not proof that a boss is alive now.
- Recognise field bosses the catalog misses: an open-world NPC without the boss flag is never recorded as a kill, so each is data-gated on a capture (`python -m aion2calc npc-evidence` ranks candidates).
- Confirm Verteron's open-world map ids with an Elyos kill (Altgard's are confirmed by the feed).
- Optionally tighten the anonymous per-install reporter key to authenticated reporters.

**Completion evidence:** independently confirmed schedule/respawn rules and sufficiently scoped observations.

### 7. Website and shared player tools

**Available:** consistent Pages navigation, focused logs and character pages, recorded images/equipment/stats/skills/boards, local build drafts, catalog validation and community preset seeding; embedded provider maps and attributed collection routes; a source-attributed crafting snapshot with rarity/type filters, a mastery tier/level input and community-measured success rates; official Global/Korean/Taiwan news cards; Server and Region matched comparisons keyed on each character's verified official-profile home world, with a hint explaining an Unavailable scope.

**Remaining:**

- Populate the **World** comparison scope, which needs enough encounter metadata (boss, version, difficulty, party) to match anyone. A character whose profile never resolves stays Unavailable in Server/Region by design.
- Verify current-build arcana rules and obtain Pantheon artwork from source data.
- Obtain permitted native map coordinates, layers and assets if the provider viewer is ever replaced with local map tools.
- Verify crafting success/failure rewards, refunds, combo quantity/replacement rules, modifier formulas and build/region applicability. Combo simulations are conditional completed-craft checks, not guaranteed yields.
- Confirm item-stat and recipe applicability to current Product versions/regions (the snapshot supplies stats for 1,162 of 1,288 output records).
- Add further feeds only after confirming their official source, API/RSS availability and reuse terms.
- Supply the remaining id-verified NPC portraits. The curated table has art for 1,321 of 9,780 NPCs; `npc-evidence` ranks the unportrayed NPCs uploads hit most, and the community fallback (`aion2logs portraits`) fills art behind the curated table without overwriting it.

### 8. Live meter & overlay

Most of the live-meter pass has shipped (0.2.133 onwards). Every metric stays packet-sourced: TTK, contribution and current target are computed from recorded damage/HP or left blank, and mechanics-dependent values stay data-gated.

**Open:**

- **RTSS in-game text** (0.2.300; 0.2.301 kept it running through a busy meter): *Settings → In-game (RTSS)* hands the meter text to RivaTuner Statistics Server's own OSD slot — optional, Windows-only, off by default, nothing injected into the game. Awaiting the owner's live test, then any follow-ups it raises.
- **Identity after a Kibelisk teleport.** The engine keeps the game-verified local name across a zone reset and re-binds the local player to the one actor carrying it when no self record follows (0.2.300). None of the captures supplied spans a Kibelisk teleport; the hypothesis is a `23 36` zone transition with no new `33 36` self record. A capture spanning one confirms it. Meanwhile zoning, reviving or entering the character name before Start also re-binds identity.
- **Estimated time-to-enrage** — data-gated on verified per-boss enrage timers.
- **Hotkeys** — the two actions not yet wired: a combat-assist UI and a field-boss/artifact status.
- **Event notifications** — rift, Shugo and battlefield windows remain the bundled community forecast (labelled as such); field-boss windows come from observed kills. A server-driven respawn feed is a probe target (see Routes).
- **macOS / Linux parity (optional, hardware-gated).** The native layer is Windows-only; `overlay.native_overlay()` selects `_Windows` / `_MacOS` / `_Linux`, and the macOS/Linux backends are inert scaffolds (`supported=False`, so those platforms keep the browser/plain-window fallback). Blueprint for when hardware exists: macOS via pyobjc (`NSWindow.setLevel_(NSStatusWindowLevel)` and `NSWindowCollectionBehaviorCanJoinAllSpaces`, `setIgnoresMouseEvents_`, `setFrameOrigin_`, `CGWindowListCopyWindowInfo`, `NSScreen.screens()`, flipping Cocoa's bottom-left origin); Linux on X11 via python-xlib (`_NET_WM_STATE_ABOVE`, an empty `XShapeCombineRectangles` input shape, `XMoveWindow`, RandR/Xinerama). Wayland generally forbids app-driven always-on-top and input shapes, so Linux stays X11-only. Each backend must be validated on a real machine with the game running before `supported` is set.
- **Declined:** game-process DLL injection to draw inside a window/application capture (anti-cheat tampering and account-ban risk, EULA violation, fragility; revisit only as an explicit owner decision) and Discord Rich Presence (2026-10-11).

### Maintenance, screenshots and assets

**Available:** application-content screenshots include below-fold content without monitor capture; storage inventory and explicit cleanup cover recognized disposable caches; updater helpers self-clean and bounded retention preserves recent logs, releases and active helpers. Saved logs, imports, credentials, results and upload queues are preserved. Asset diagnostics distinguish browser failures, proxy status, official same-region/item-ID references and publisher-specific item namespaces.

**Remaining:**

- Confirm full-page rendering on target devices and handle browser/CORS limitations for remote images.
- Reconcile additional item/title/NPC/passive assets using stable source IDs and reviewed namespaces. Do not derive NPC portraits from names or equate third-party item IDs with official IDs.
- Review newly encountered cache/update file types before making them eligible for cleanup; unknown files remain preserved.

### Community identity and operations

**Available:** owned upload management, credential backups/import, privacy changes, request retry receipts, moderation reports/audit history, the private authenticated server dashboard with its Deployment card, public PvE/PvP class/player samples, a CI-gated updater, the Merge on green workflow, and `python -m aion2calc doctor` as a read-only operator self-check. Character claims, the opt-out, recovery and named moderator roles shipped in 0.2.295 / server 0.2.100.

**Remaining:** authenticated appeals. Previously downloaded public data cannot be recalled.
