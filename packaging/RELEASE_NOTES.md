## Capture-filter diagnostics, 150% log pages, and cleaner community filters (0.2.272)

- **Diagnostics now record the active capture filter and whether the game flow was located** (`capture_filter`, `auto_port`, `flow_detected` in a log's capture quality). This is the groundwork for cutting packet loss: an uploaded log now reveals whether the capture ran the broad "all TCP" filter (which floods the buffer) or a narrow game-flow filter — so the fix can target the real cause. No behavior change yet; capture itself is unchanged this release.
- **The combat-log and combat-review pages now scale to 150%** (down from 200%), still full browser width.
- **Community combat logs:** the PvE view hides generic non-boss "Combat N" rows (PvP skirmishes are kept), and the Difficulty filter is sorted.

## Wider combat-log pages, correct uploader attribution, and per-encounter parties (0.2.271)

- **Community combat logs and the combat-review (log details) page now use the full browser width and render at 200% scale**, so the dense per-encounter tables, class/boss icons and the combat breakdown are far easier to read on a large monitor. Other pages are unchanged.
- **Your uploads attribute to you even when a fight was captured with heavy packet loss.** The uploader is now taken from your character's name as it appears in the log's own roster (matched by your official character id), not from the live combat-entity id — which can be an unnamed `#number` when the identity packets are dropped. Previously that left the log "Anonymous" even though the meter had detected you.
- **Each community-log encounter shows its own party**, not the whole log's combined roster. A session that chains several fights (e.g. a solo pull then a 5-player dungeon) no longer shows the dungeon group on the solo fight. Pairs with the server's per-encounter participants (0.2.90).
- **The log-details page shows only the selected encounter's players and builds**, instead of every player across a multi-encounter log — so you no longer see builds for characters who weren't in the fight you're looking at.

## Website: filterable community logs, class/boss icons, a hover read-out on the spread graph, and tidier log details (0.2.270)

- **Class-stats spread graph now reads out on hover.** Move the cursor across a class's spread and a tooltip shows the approximate DPS under it, which percentile band that is (bottom 25% → top 10%), and the class's own markers (median, 25th/75th/90th, best) with the nearest one highlighted, plus a guide line in the bar.
- **Best DPS, median gear score and median combat power on Class stats.** Added as columns in the cross-class comparison and to each class's detail. Medians show only where players reported those values (otherwise "—"), and pair with the server's 0.2.89 stats aggregate.
- **Community combat logs are filterable again — and then some.** The single boss search is replaced by dropdowns for mode (PvE/PvP), boss, difficulty, encounter type, region, product version and party size, populated from the server's live facets so only real values appear.
- **Class icons and boss portraits in the community table.** The party is shown as class icons (hover one for the player's name and class) instead of a names list, and each boss row shows the mob's portrait beside its name.
- **Log details open tidier.** On a shared log, the Automatic encounter context, Mapping coverage, Capture quality, Run timing / boss progression and Other parts sections now start collapsed, so the encounter and damage tables are front and centre; expand any section when you want its detail.

## Capture: a much larger buffer to stop dropped packets, and your name on logs you upload (0.2.269)

- **Bigger capture buffer — the real fix for dropped packets.** Busy fights (raids, big expeditions) burst far past the old 8 MiB kernel capture buffer, so a quarter to a half of packets were being dropped — which is why those fights stayed unranked and why many enemies showed up unidentified (their spawn packets were among the dropped). The capture now requests a **64 MiB** buffer, stepping down (32 / 16 / 8 MiB) until the backend accepts one. A larger buffer absorbs the bursts, so far fewer packets are lost; cleaner captures mean fights can actually rank and mobs keep their names. (Windows/Npcap; if the backend refuses a larger buffer the old default is used, as before.)
- **Your uploads show who you are.** A public log now records the uploading (local) player's name, so the website's community logs can show who shared each one. It's the character the meter is recording as you; if that isn't established, the log stays **Anonymous**. It's a label only — it never affects ranking — and existing logs are unchanged.
- Note: this helps *new* captures. It can't recover packets already lost in logs uploaded before this version, and a capture that still drops a large share stays correctly unranked.

## Ranking: a storage rollover or a few dropped packets no longer unranks a whole session (0.2.268)

- **The symptom.** Across the live server's uploaded logs, **every** fight was coming back unranked. Running the real eligibility gate over a sample of recent public uploads showed two reasons firing on essentially everything: `storage_boundary` on **100%** of fights and `capture_loss` on **98%** — the rest (open-world trash with no boss, PvP) is correctly unrankable.
- **Root cause — whole-session facts stamped on every fight.** Two pieces of evidence are cumulative over a capture session but were applied to each fight individually: (1) `storage_boundary` is set on every rolled-over archive part *and its continuation*, so any session long enough to roll storage over (all of them) marked every fight — even fights wholly captured within one part; (2) `pcap_dropped` is a running packet-drop counter since capture start, so one early buffer overflow unranked every later fight, including fights that lost nothing (the identical drop count appeared stamped on many different logs).
- **The fix — attribute loss per fight.** A fight that observed its **own** start and reached its **own** verified end (a kill, or a cleanly completed run) is wholly contained in its part, so a boundary at the part's edges no longer unranks it; a fight that was actually truncated (start or end outside the part) is still gated, as are partial captures. And dropped packets now use a **budget** (like the recovered frame-skip budget from 0.2.258): a handful is routine, only a material share of the session's packets counts as capture loss. Genuine per-event loss — a fatal decoder failure, abandoned payloads, discarded TCP payloads — still voids ranking on any nonzero count.
- **Honest scope.** This removes the *bogus* blanket exclusion so a clean, complete boss kill can rank — which was previously impossible. It does **not** paper over genuine capture loss: in the current sample every actual boss kill came from a session that dropped **26–51%** of its packets (a capture-performance problem, not a gate bug), so those stay correctly unranked until the capture itself keeps up. The gate change helps new, low-loss captures; the server re-derives eligibility on reindex, so existing logs are re-ranked when it updates.
- Regression-tested (a self-contained kill is spared `storage_boundary`; a truncated fight is still gated; small packet drops are tolerated while a material share still gates; genuine decoder/TCP loss still gates).

## Optimizer: never hang, and say so clearly when the solver is missing (0.2.267)

- **The symptom.** On some imported characters the PvE build optimizer froze mid-run — e.g. stuck at **"stat weights: timing simulations 3/4"** — and never finished. Separately, **"Contribute a community comparison"** failed with *"RuntimeError: The HiGHS solver dependency is missing or unavailable."*
- **Root cause — the freeze.** The optimizer runs a damage simulation for each candidate. A kit skill's hook can land another hit at the *same instant* (an on-hit proc), and with extreme imported gear a proc can keep re-triggering on its own hit, scheduling same-instant work without end. That spun the simulator forever (or overflowed the stack), so the whole optimize hung at whatever phase was running — most visibly the stat-weight timing simulations.
- **The fix — the simulator always terminates.** Three independent safety caps now bound every simulation: the synchronous on-hit recursion depth, the number of same-instant events drained at once, and a last-resort per-run wall-clock. A healthy fight never comes close to any of them (they sit far above a real 3-minute parse); a pathological build now ends with a bounded result flagged as degenerate instead of freezing the app. This is build-independent — it protects against this whole class of hang, not one gear set.
- **Root cause — the solver error.** The Daevanion/skill-point step uses the in-process **HiGHS** solver (`highspy`). It's bundled in the installer and portable builds, but a from-source install can miss it. Nothing checked for it until deep in the run, so a missing solver looked like a stall.
- **The fix — fail fast with guidance.** The optimize now checks the solver **before** the long rotation/stat-weight search and, if it's missing, stops immediately with an actionable message (*install `highspy`, or reinstall the app*) instead of appearing to hang. The community-comparison path already reported this; both now point at the exact fix.
- Regression-tested (a self-triggering hook terminates and is flagged; a normal fight never trips the caps; the optimize fails fast with guidance when HiGHS is unavailable). If the optimizer froze for you before, update and re-run; if you installed from source and see the solver message, run `pip install highspy`.

## Spiritmaster: the one-spirit-at-a-time rollup now works on non-English clients (0.2.266)

- **The gap.** The 0.2.265 rule that folds a replaced basic spirit into its owner identified the basic spirits (Fire / Water / Wind / Earth) and the coexisting Ancient Spirit by the summoned pet's **name** — and those names were taken from the English game tables. On a client in another language the pet's name comes through localized, so it didn't match, and the one-at-a-time replacement quietly fell back to the 8s idle rule (the stale basic-spirit rows a non-English Spiritmaster cycles through took up to 8s to clear instead of folding in at once).
- **The fix.** A summon is now classified by the **skill IDs it attacks with** — which are numeric and the same in every locale — resolved against the client's shipped skill table. A Fire/Water/Wind/Earth spirit's own attacks mark it a basic spirit (so a newer one replacing it folds the old one in immediately); the Ancient Spirit's attacks mark it the coexisting exception. The pet's displayed name is kept only as a fallback until an identifying skill is seen. So the replacement rule now behaves the same on every language client, not just English.
- Live-view only (`CombatSession._summary`); stored and already-uploaded logs are unchanged. Regression-tested (basic spirits classified by their attack skills, and the replacement folds a just-replaced spirit even when its name is non-English and does not match the English set; the English name path still works as a fallback).

## Spiritmaster: a de-spawned spirit's damage stays on its owner instead of falling off the list (0.2.265)

- **The symptom.** With **"combine pets with owner" unchecked**, a Spiritmaster's spirits each get their own row — but a Spiritmaster cycles through many short-lived spirits, and once a spirit de-spawned its row went quiet and, in a busy fight, scrolled past the overlay's row cap. Its damage dropped out of view and was **not rolled into the owner**, so the Spiritmaster's visible total kept shedding the contribution of every spirit it had already dismissed.
- **Root cause.** The live view only ever collapsed a pet into its owner when "combine pets" was **on**. With it off, every summon stayed a standalone row for the rest of the fight — including the dozens a Spiritmaster had already de-spawned — and those dead rows competed for the limited overlay slots with the live ones.
- **The fix — idle de-spawn.** With pets shown separately, a summon that has **gone quiet long enough to be de-spawned** (idle ≥ `PET_DESPAWN_IDLE_MS`, 8s) now folds back into its owner, so its damage stays counted on the Spiritmaster and the stale row disappears. The owner's **still-active** spirits keep their own rows — only idle/de-spawned ones fold in — so you still see what's currently out. With "combine pets" **on**, every spirit folds into the owner exactly as before.
- **The fix — one basic spirit at a time.** A Spiritmaster can only have **one basic spirit** (Fire / Water / Wind / Earth) out at once, and summoning a new one replaces the last. So the moment a newer basic spirit appears, the one it replaced is folded into the owner **immediately** — it doesn't have to go idle first. The spirits cycle far faster than the 8s idle window (a real Vakron fight churned ~45 basic spirits in 147s, a new one every ~3s), so without this several just-replaced basic-spirit rows would pile up at once; now only the **current** basic spirit keeps its own row. **Ancient Spirit** is the one spirit that can be out alongside a basic spirit, so it is exempt from the one-at-a-time replacement and keeps its row until it idles out. The basic spirits are identified from the Spiritmaster's own summon skills, so the rule stays tied to that class.
- **Scope.** This is a live-meter / overlay summary change (`CombatSession._summary`, the packet path the overlay and app read). It affects the live view and future captures; already-uploaded shared logs are served from their stored segments (`to_a2log`, which builds its own entities and is untouched) and are unchanged. Regression-tested (a de-spawned spirit folds into the owner while an active spirit stays its own row; a basic spirit folds in the instant a newer one replaces it, even within the idle window; Ancient Spirit stays out alongside the current basic spirit; still-active pets don't over-fold before the threshold; combine-on still folds everything).

## Encounters: split a dungeon run into one encounter per boss, not one long fight (0.2.264)

- **The symptom.** In a dungeon run, after finishing one boss the meter kept the next boss in the **same** encounter, so a mini-boss and the boss after it showed up as one long continuous fight instead of two encounters.
- **Root cause.** A new encounter was only ever cut on a **120s damage gap**, a wipe, or a leash/reset — a clean **boss kill never ended the encounter**. In a continuous run (trash and travel between bosses, no two-minute lull), consecutive bosses collapsed into one segment. In the shared log, Watchdog Kwapo died and the next boss was engaged **117 seconds later** — just under the 120s threshold — so the two bosses stayed merged.
- **The fix.** A boss / mini-boss **kill now ends its encounter**: when the next boss is engaged after a kill in the same run, it starts a fresh encounter, so each boss is its own segment regardless of how little time passed between them. The split is gated so it never fires twice (a kill already closed by a wipe, reset, finish or run change doesn't add a second split) and never cuts a single continuous boss fight (the kill must come before the next boss is engaged). A trash mob already being fought before the kill — promoted to a "major" engagement only later — never splits the fight it belonged to.
- Regression-tested: two bosses killed back-to-back with no lull become two encounters; a single boss fought straight through to the kill stays one encounter; the existing wipe / leash / battle-rez boundaries are unchanged.

## Upload: send the whole recording, and view it stitched back together (0.2.263)

- **The symptom.** Uploading a long session that had rolled across a storage boundary into parts failed with `upload refused (400): Combined recording reviews cannot be uploaded; upload the original source parts` — the recording never reached the server. And even when parts did upload, a shared link showed only one fragment, so an encounter split across a storage boundary looked incomplete.
- **Root cause.** The whole-recording Upload (0.2.252) stitched the parts into one **combined recording** client-side and uploaded *that*. A combined recording is a reconstructed *review*; the server refuses an uploader's stitched review (it can't authenticate it) and instead stores the **real source parts** so each one can be verified and ranked, then stitches them back on demand. The client wasn't sending the parts, and the viewer wasn't showing the server's stitched result by default.
- **The fix — click Upload, send everything.** Upload now reliably sends **every raw source part** (the live current part plus each earlier closed part). The server links them under one recording by archive id and reconstructs the complete recording — every run and encounter, rejoined across the storage boundaries — so nothing is dropped and each part still counts for rankings. If an earlier part can't be sent, the upload still succeeds and tells you how many parts will go up on the next attempt.
- **The fix — view the whole thing.** Opening any part of a multi-part recording now shows the **complete stitched recording as the main view** (with one click back to a single part, which keeps that part's own rankings). This works for your own **unlisted and private** recordings — the default upload visibility — not just public ones (paired server release). It degrades gracefully: an older server, a missing part, or a very large archive simply leaves you on the single part.
- The combined recording stays unranked by itself (a reconstructed review isn't a verified single capture); ranking still comes from the individual parts. Regression-tested (Upload sends the source parts and never a stitched review; the viewer auto-opens the combined recording and falls back cleanly; single-part and missing-part uploads unchanged).

## Overlay: auto-contrast the text to your background image (0.2.262)

- When you set a background image for the overlay, the text can now adapt to it so it stays readable — no more hunting through the colour pickers. **Settings → Overlay → Overlay background → Auto-contrast text to image:**
  - **Dynamic (per-pixel blend):** each glyph is painted as the inverse of whatever is directly behind it (`mix-blend-mode: difference`), computed per-pixel and updated live — white over dark areas, dark over light.
  - **By brightness (computed):** samples the image's **WCAG relative luminance** (`0.2126·R + 0.7152·G + 0.0722·B` on linearized sRGB, with the Darken slider folded in) and sets one solid light-or-dark text colour for guaranteed contrast on any image, including flat mid-tones.
- It reads **only the overlay's own background image**, not the live game behind a transparent window (the OS composites the game after the page renders, out of CSS/canvas reach) — so it pairs with a background image, which also hides the game clutter behind the panel. Off by default; your own text colours are restored when you switch it off, and it rides the overlay look presets.
- This is a CSS/canvas rendering change that can't be exercised headless, so verify the final look on the Windows overlay. Regression-tested (the setting defaults off and validates its three modes; the overlay drives both the blend class and the computed-luminance colour; the settings page offers and saves it).

## Encounters: one boss fight is no longer split into dozens of phantom "attempts" (0.2.261)

- **The symptom.** A single dungeon/world/abyss boss fight showed up as many separate encounters — one Argo pull appeared as 5 segments; the leaderboard counted a boss (e.g. Vakron) with 86 "attempts", 2 kills and 84 "unknown". Because each fragment started mid-fight and never saw the boss go from full HP to death, **every fragment was partial and unranked** — which is why Completed-run speed, best wipe HP, fastest kill, Class performance and the matched comparisons were all empty.
- **Root cause (confirmed from a real log).** The meter starts a fresh "attempt" when an engaged boss is seen back at **full HP** — the intended signal for a leash/wipe-runback. But a boss's HP packets are **sparse and erratic**: stale or over-max readings (one Argo sample read 808M against a 276M max) make the boss briefly read "full" *while the party is still hitting it*. In the shared log the Argo fight had **747 hits with a maximum 3.8s gap in damage** — completely continuous — yet was split into 5 segments, because each spurious "full" reading (often right after a player death/revive) looked like a reset. Packet timestamps are monotonic capture-order, so this is not a timestamp reorder to filter; it is a spurious *value* during unbroken combat.
- **The fix.** A boss climbing back to full now counts as a leash/reset **only after a real lull in our damage to it** (≥ 26s, tunable via `RESET_LULL_MS`). That sits well above the observed continuous-combat gap (max 3.8s) and short mechanic pauses, while a genuine wipe or leash stops the party's damage (everyone dead, or ran out of range) for well beyond it before the boss is seen at full; a spurious reading mid-fight — and a battle-rez where others keep hitting — no longer splits the encounter. Erratic readings are still recorded in the event log; they just don't start a new attempt. One continuous fight stays one encounter, so a complete capture (boss full → dead in one segment) can rank again.
- Regression-tested against the observed pattern (a "full" reading during continuous combat does not reset; a return to full after a real damage lull still does), and all existing leash/wipe/battle-rez boundary tests still pass.
- Note: open-world/field bosses that are tagged mid-fight (no instance entry, boss never seen at full at the start) remain a separate eligibility question, tracked for a follow-up.

## Live meter: keep up during big boss fights, and show when it is catching up (0.2.260)

- **The symptom.** On a major world / abyss / field boss with a full raid (e.g. Argo), the live meter fell behind — party members were slow to appear and the boss's defeat only registered a while after the fight actually ended. It was never losing data (the final totals are always correct); the *live view* was just lagging real time, then draining once combat stopped.
- **Why.** One thread decodes packets one at a time, and a heavy fight enqueues them faster than it drains. Two things made the decoder slower exactly when it was busiest: it did its per-packet bookkeeping (run-save / rollover / checkpoint, each taking the shared lock) once **per packet**, and the live-view snapshot — a full recompute over every event in the fight — holds that **same lock**, so a long fight's ever-costlier recompute was stealing up to half the decoder's time. High ping makes it worse (more out-of-order TCP to reassemble).
- **The fix (only when it's needed).** When — and only when — a backlog builds up during a heavy fight, the decoder switches to draining the burst in a **batch** and doing the per-burst bookkeeping once per batch instead of once per packet, and the costly live-snapshot recompute **steps aside** (refreshing a little less often) so the decoder reclaims the shared lock and drains the queue. **Normal encounters and dungeons are unchanged** — they stay on the proven one-packet-at-a-time path with the full-cadence snapshot, exactly as before; batching engages only once the queue is genuinely backed up. Each packet's own decode still takes the lock individually, so the display keeps updating between packets. Net: the live view keeps pace through far bigger fights, and party members show up promptly.
- **"Catching up" indicator.** When the decoder is behind during a burst, the meter (app and overlay) now says it is **catching up** and how deep the queue is, instead of looking frozen. Final totals are unaffected — the backlog is drained, never dropped.
- **Capture-stability fix riding along.** A recovered decode skip (now routine, since a perfect frame stream isn't achievable) was writing its error history to the same key the numeric `processing_errors` counter uses. After any skip, the next transient hiccup hit `list + 1` and **stopped capture**. The error history now has its own key, so a routine skip can no longer take capture down — and the `processing_errors` health counter is numeric again for diagnostics. Regression-tested.

## Overlay: event notifications (rift / Shugo / world bosses) now show, because the region reaches the overlay (0.2.259)

- **The bug.** The overlay's regional event strip never appeared — and so its chime never fired at event time — even though the in-app **Test** button played the sound fine. The strip only shows once a region is chosen on the Timers page, but that region was saved **only to `localStorage`**, and the overlay is a separate native window that does not share the Timers page's `localStorage`. Every *other* overlay setting already travels through the app server's `/api/ui`; the region was the lone exception, so the overlay always read an empty region and hid the strip.
- **The fix.** Picking a region on the Timers page now also mirrors it to the server (`/api/ui`), and the overlay reads the region from the same settings feed it already uses for everything else (falling back to `localStorage` for the in-app view). With a region present, the strip shows the next rift / Shugo Festival / Dimensional Invasion / siege / world-boss window when it is active or within 15 minutes, exactly as the Timers page forecasts.
- **About the sound.** The overlay chime is still opt-in — enable **"Play a sound when an event notification appears"** in Settings (the in-app Test button only previews the sound; it does not enable it). Once that is on *and* a region is set, the chime fires as each event enters the strip.
- Pick your region on the Timers page once and the overlay strip follows. Regression-tested (server defaults/accepts the region, the Timers page mirrors it, the overlay reads it).

## Ranking: a recovered frame-skip no longer unranks a whole session (0.2.258)

- **The bug.** Nothing was coming in as ranked, on any content. A fight is ranking-eligible only if **zero** completeness checks trip, and one check (`capture_loss`) fired on essentially every session: when the decoder skips a malformed or over-limit compressed frame it logs *"capture continues"* — a benign, recovered skip — but it was incrementing the same `decoder_errors` / `capture_errors` counters the gate treats as fatal loss. The gate trips on `any(counter > 0)`, so **a single recovered skip anywhere in a session unranked every fight in it**. A perfect frame/packet stream is not achievable, so in practice this was always-on.
- **The fix.** Recovered skips (a malformed/over-limit compressed frame, or a single unsupported packet the decoder skips and continues past) now increment their own informational `recovered_frame_skips` counter instead of the loss counters. Ranking tolerates them up to a **material threshold** — more than 200 skipped frames, or 2% of the packets received, whichever is larger — beyond which the capture is genuinely incomplete and still won't rank. **Genuine loss still gates ranking**: a fatal decoder failure, driver-dropped packets, abandoned payloads, TCP loss and validation discards are unchanged.
- **Scope.** This is a completeness/eligibility change only; it does not touch authenticity. It applies to new captures (the recovered-skip count is recorded going forward), and because the server re-computes eligibility from the capture evidence the client sends, both the live per-fight rank badge and the uploaded-log leaderboard start ranking normal captures again. Dummies and bossless pulls remain unranked by design (no boss start/death to verify). Regression-tested.

## Gladiator: fix the MP-starved rotation so Rending Blow weaves at its real rate (0.2.257)

- **The residual.** A real Gladiator dummy parse weaves **Rending Blow at ~1.9/s (~14.5% of damage)** and the basic-attack string at a similar rate, and uses **no** crowd-control / gap-closers (Ankle Slice, Rush Strike, Mocking Blade, Leaping Slam, Crushing Wave). The model instead cast Rending Blow at ~4% and sprinkled in those CC skills — because the rotation had **no modelled MP sustain**: Rending Blow costs ~96 MP, nothing restored it, so MP pinned at 0 and Rending was skipped, and when it was skipped the engine reached the non-restoring CC skills *before* the MP-restoring basic string.
- **The fix.** The basic-attack weapon string now **restores MP** (standard melee sustain), and in the rotation it **out-prioritises the low-DPS crowd-control skills** — so when Rending Blow has drained MP, the engine casts the basic string (refilling MP) instead of a CC skill, and Rending weaves back in. On a dummy the CC skills now carry ~0% (matching the parse), and Rending Blow rises from ~4% to a real share.
- Effect: the Gladiator's modelled dummy rotation tracks the parse far better (Overhead Slam + Upward Strike core, Rending Blow + basic-string weave, Ruinous Blow and Murderous Burst), modelled DPS ticks up, and Combat Speed stays at the top of the stat ranking. The remaining Overhead-vs-parse gap is the median loadout's low combat speed (your own geared character casts faster, closing it). Regression-tested.

## Optimizer: calibrate every class from community parses — add the skills the catalog hides (0.2.256)

- **The systemic bug, all classes.** metabot's build page lists 35 skills per class, but the game logs several real skills under their own id that metabot only names inside a *parent* skill's specialization text — a chain (`Adds [X] Chain Skill`), an "on landing [X]" variant, or an unlisted basic-combo step. A hand-written kit that modelled the parent directly **silently dropped** that chain/variant, and the optimizer never saw it. Measured against community level-45 parses, the dropped damage was **18–42% of a class's output** (chanter worst, then spiritmaster, templar, assassin, cleric). Because the missing nukes weren't there, the model **over-weighted the filler** that expanded to fill their place (e.g. assassin Savage Roar modelled at 27% of damage vs ~5% real).
- **Chain finishers are finishers, not taps — raised 0.85× → 1.5× for every class.** `Adds [X] Chain Skill` follow-ups were modelled at a flat placeholder; community parses measured them at **1.38–2.1×** the base (chanter Piercing Strike 1.65×, sorcerer Winter's Illusion 1.86×, ranger Shackling Arrow 1.38×, plus the Gladiator 2.1× from 0.2.254). The shared default is now 1.5×.
- **Chanter** (was the worst, ~40% unmodelled): **Piercing Strike** (the Dark Crush chain, ~22% of real damage) and **Bursting Blow** (the Incandescent Blow variant, ~15%) were both dropped; they are now modelled at their measured **1.65×** and **2.23×**. Modelled dummy DPS rises ~13% and **Illusion / Cooldown jumps to #2 in the stat ranking** (the Dark Crush→Piercing chain is cooldown-bound).
- **Cleric**: **Divine Punishment** (Judgment Thunder's companion strike, ~11%) was dropped — now rides every Judgment at its measured **1.09×**; **Discharge** uses the raised chain coefficient; Judgment Thunder is given a cadence so it is not spammed as a bare filler. Modelled DPS rises ~14% and the Judgment/Divine-Punishment/Condemnation/Bolt shares track the parse.
- **Assassin**: the **Quick Slice basic combo** (Swift Slice 0.67×, Breaking Slice 0.76×, ~13% of real damage) was dropped, and **Savage Roar** was a second always-on filler spammed to ~27% of damage. Savage Roar is demoted to a cadenced Insignia-upkeep skill (~5% real) and the Quick Slice combo is the filler. Modelled DPS rises ~23% and Critical leads the ranking.
- **Templar**: the **Vicious Strike combo** (Decisive 1.20×, Desperate 1.54×) is modelled. Punishing Strike (~13%, undocumented parent mechanic) and the Pummel filler's magnitude are **flagged** for a gear-matched capture rather than guessed.
- **Ranger / Spiritmaster / Sorcerer** get the raised chain coefficient; ranger was already close to its parse, spiritmaster already models its pet stream, and sorcerer is the reference class.
- Every coefficient above is measured from a real parse (non-crit damage per hit, which cancels crit-rate and gear). The remaining gaps — templar Punishing Strike, assassin Savage Smash / Back Kick, spiritmaster per-spirit pets — are documented in [Methodology → catalog gaps](https://github.com/sam-t-anderson/Aion-2-tools/blob/main/docs/methodology.md) with their measured ratios, for a future gear-matched calibration. Regression tests cover the new skills and the chain coefficient.

## Gladiator: model Ruinous Blow's multi-hit (lifts Cooldown Reduction) (0.2.255)

- Building on 0.2.254: **Ruinous Blow lands as a multi-strike** (~4 raw hits per cast in a real parse, ~7.7% of damage), but the model treated it as a single hit — so it was undervalued and, because it is the Gladiator's main cooldown-bound nuke, it **undervalued Cooldown Reduction / Illusion**. It is now modelled as ~3 full-coefficient strikes, landing at its measured ~7.7% share.
- Effect: Ruinous Blow's modelled share rises from ~2.5% to ~7.9% (matching the parse), and **Cooldown Reduction's and Illusion's stat weights roughly double**. Combat Speed still leads the ranking — the Gladiator rotation is genuinely combat-speed-bound at ~7 attacks/s — but Cooldown is no longer near-zero.

## Damage optimizer: fix the DPS underestimate and stat ranking (0.2.254)

- **The stat ranking was missing stats, for every class.** `Precision` and `Freedom` were never evaluated — Precision (a crit stat) simply never appeared in the priority list. Both are now ranked for all eight classes.
- **Chain follow-ups were undervalued everywhere.** Every class kit modelled a chain skill at a flat **0.60×** the base hit — an uncalibrated placeholder. A real Gladiator dummy parse measured a chain (Upward Strike) at **~2.1×** the base, i.e. the single biggest hit in the rotation. The shared default is raised to **0.85×** as a conservative class-agnostic estimate, marked in each kit as pending a per-class parse to measure the true value.
- **Gladiator is recalibrated against a real parse.** The model estimated ~25K dummy DPS where a real parse was ~41K, and misranked tempo/crit stats. Root causes, all fixed:
  - **Upward Strike** (the Overhead Slam chain, ~27% of real damage) was modelled at 0.60× Overhead; it is really ~2.1×. It is now the top hit, following ~half of Overhead Slams (measured).
  - **The basic-attack combo** (Smashing Blow, ~15% of real damage) was not modelled at all — the kit used Keen Strike as filler, which a real parse barely casts. A basic combo is now the filler, at its measured ~0.54× Overhead.
  - **Overhead Slam** was gated behind sparse knockdown windows and a dead `knockdown_uses` constant; on a breakable training target it is available and spammed (~1.5/s, measured), as in the parse.
  - **Murderous Burst** over-procced (≈12% modelled vs ≈5% real); an internal cooldown gates it to the measured rate.
  - The rotation now leads with Overhead Slam + Upward Strike + the Rending Blow / basic-combo weave instead of spamming crowd-control skills for damage.
- Net: modelled Gladiator dummy DPS rises ~60% (tracking the real parse once scaled to your gear), the damage shares track the parse, and **Combat Speed rises to the top of the stat ranking** (the rotation is combat-speed-bound at ~7 attacks/s). The non-Gladiator chain change is an estimate; send a dummy parse for any class to calibrate it the same way. Regression tests cover the ranking additions, the chain default, and the Gladiator shares.

## Live meter: show one row per player when their actor ID changes mid-fight (0.2.253)

- **The bug.** When you die and revive — or an instance mechanic swaps your character — the game hands you a **new combat actor ID**. The live meter keyed each row by actor ID, so your damage before the swap and after it landed on **two rows with the same name** ("Spirited" 15% and "Spirited" 10%), and the overlay had to warn that matching names have separate actor IDs. (Reported on a run where the player died exactly when the second "Spirited" row appeared.)
- **Your own character — authoritative.** The engine records the local-player ID on every captured record and re-acquires it after a tele/port/revive, so the live view now folds **every ID the engine confirmed as yours** into a single "you" row. This never guesses from names, so a different player who happens to share your name is never counted as you.
- **Party members — a careful behavioural match (as suggested).** For other players, where there is no authoritative self-link, re-registered IDs are correlated only when all three hold: the **same player name**, a **compatible class** (the same skills imply the same class — a class *conflict* blocks the merge), and **activity that never overlaps** (a hand-off: the old ID goes silent exactly when the new one appears). Two different players who share a name but trade blows **at the same time** are left as separate rows — the overlap is the tell that they are two people, not one re-registered character. These inferred merges are flagged, and the overlay notes when a row was combined this way.
- Why not merge on skills alone: skills identify a *class*, not an individual, so two players of the same class would wrongly merge. The authoritative local-ID link plus the name + class + non-overlapping-timing rule is the reliable version. Saved/uploaded logs are unaffected (they already key players by server + character ID). Regression tests cover your own re-registration, a party member's, and two concurrent same-name players staying separate.

## Upload now sends the whole session, not just the latest part (0.2.252)

- **The bug.** When a long run crosses a storage boundary, the live session is flushed to a numbered "part" on disk and a fresh one continues (this is the memory flush that also resets the live view). **Upload** sent only the *current* in-memory part, so pressing it after a rollover shared just the latest fragment — the earlier encounters, saved safely on disk as earlier parts, were left out. Confirmed from a real public log titled "…·Part 2": it held a single 17-second fight (records 30973–31312), while Part 1 (the first ~30,972 records) never reached that upload. The excessive splitting that made this common was the summon/re-registration reset storm — fixed in 0.2.249–0.2.251 — so normal runs now stay in one part; this fixes the genuinely long run that still legitimately rolls over.
- **The fix.** Upload now stitches the current part together with the earlier **closed** parts of the same recording (matched by archive id on disk) into **one combined recording**, so a single share link holds every encounter. The parts' continuity metadata is already recorded on rollover, so no re-capture or re-finalizing is needed — the live current part chains straight onto the saved ones.
- **Graceful fallback.** When the parts can't be merged into one — more than 32 parts, more than 200 encounters, over the 64 MiB review cap, or an earlier part was pruned off disk — Upload instead uploads every part individually; the server groups them under one recording by archive id (and offers a combined server-side review), so nothing is dropped. A single-part session (the normal case) uploads exactly as before.
- A combined recording is a *review* of linked parts: it's marked reconstructed and is **not** itself leaderboard-ranked (per-part rankings aren't inherited across a storage boundary). Save/Export still write the current part only; this change is scoped to the Upload button. Regression tests cover the stitch, the single-part passthrough, and the missing-part fallback.

## Really fix the Start/Stop button showing "Start" at launch (0.2.251)

- **Root cause (the 0.2.250 cadence tweak wasn't enough).** The Live Meter is the app's *default* route, so at launch `location.hash` is empty (`""`) while the meter page is already mounted. The status-poll that keeps the Start/Stop button in sync guarded on `location.hash.startsWith("#/meter")` — which is **false** for an empty hash — so its very first tick returned *before rescheduling* and the poll loop **died**. The button stayed on its pre-auto-start "Start" render until you switched tabs (which sets the hash and re-mounts the page, reviving the poll) — exactly the "switching tabs fixes it" behavior.
- The poll now detects the meter page the same way the router does (an empty hash counts as the meter route), so the loop stays alive from launch and the button flips to **Stop** as soon as the meter auto-starts — matching the overlay, with no tab switch needed. It still stops polling when you navigate to another page.

## Pets never count as players, and the Start/Stop button syncs at launch (0.2.250)

- **Pets are their own bucket — they never add to the party count.** Building on 0.2.249, the rollover's player bound now *excludes* spawned entities entirely: anything with a spawn mob code (a summon, pet or turret) contributes **nothing** to the player total, whether or not its owner link has resolved yet. Once the link does resolve, the pet's damage attributes to its owner (as the live meter and saved logs already do). So a pet class' constant spawn/despawn churn can never inflate the player count or trip the reset — not even by one. (0.2.249 collapsed owner-linked pets to the owner; this also covers named, not-yet-linked summons that `all`/`auto` scope would otherwise have counted.)
- **Start/Stop button matches the overlay at launch.** The meter auto-starts ~1.6s after launch; the app's Live Meter button polled only every 1.2s, so for a moment it showed **Start** while the overlay already showed **Stop**. The Live Meter page now polls every 300ms for its first few seconds, so the button catches the auto-start as promptly as the overlay and the two agree.
- No change to how pet damage is logged: owner-linked pet damage is already folded into the owner in saved and uploaded logs (pets are recorded as `kind:"pet"` with their owner), so the server already counts it toward the player.

## Fix the live meter resetting mid-fight on summon-heavy expeditions (0.2.249)

- **Vakron Sky Island (and similar) reset the overlay's DPS over and over during the fight.** The storage rollover — a memory flush that also resets the live view — is tripped when too many distinct *players* are retained (a 48-player bound, meant to catch huge open-world crowds). That bound was counting raw **entity ids**, so two things inflated it on a long instance: a class spawning a **fresh-id summon/pet on every cast**, and party members **re-registering under a new id** after a death or a phase teleport. The same five-person party looked like dozens of players, tripped the bound, flushed a part, and reset the meter — 336 times in the reported run.
- The bound now counts distinct **player identities**: a summon/pet counts as its owner, and a player counts as its name (so a new id for the same character is the same player). Five players stay five, no matter how many summon ids or re-registrations churn through.
- This is the id-churn sibling of the 0.2.243 fix (which stopped *epoch* churn from inflating the same bound after phase teleports). Regression test added for summon spam + re-registration.

## Anonymous diagnostics beacons: fill catalog gaps and catch meter regressions (0.2.248)

- Two tiny, anonymous, **opt-out (on by default)** beacons after a fight, alongside the existing enemy-HP/heartbeat ones. They carry **no** account, character, server, IP or combat-log data — only a per-install rotating token (from the local, never-sent install salt), the client/game version, a coarse region, and small integers:
  - **unknown-ids** — the NPC mob codes and skill ids a session used that the **shipped catalog can't name yet** (new content whose id→name tables upstream hasn't published, e.g. the `295xxxx` range). The server ranks these so catalog gaps get filled from what players actually encounter. Deduped per id + game build, so each code is reported at most once per build.
  - **capture-health** — a whitelist of capture-pipeline counters (rollover parts saved, decoder/processing/capture errors, dropped-packet totals, …) from a finished session, so regressions like a meter that rolls over and resets mid-fight surface in aggregate across users instead of one shared diagnostics zip at a time. Sent once per session, on the final save.
- A single Settings → Recording toggle, **"Share anonymous diagnostics…"**, turns both off. Best-effort and silent: a failure (or a server without the endpoint) simply means no contribution and never affects capture or the app. Mirrors the enemy-HP reporter's privacy model exactly.

## Show real names for NPCs the catalog hasn't mapped yet, from the community overlay (0.2.247)

- New-content NPCs the bundled catalog doesn't map (e.g. the `295xxxx` range from Product 2.0.6.0) showed as a bare `#<code>`, because the game packets carry only the numeric mob code and the upstream id→name table hadn't published those ids. The log server's `aion2logs portraits` job now harvests the current display name by id from the id-keyed community database (server 0.2.83), and this release consumes those names as a **fallback behind the curated table**:
  - The client library's `npc_info`/`npc_name` now resolve an unmapped id to its scraped community name (marked `community`), so backend-produced labels — meter, overlay, saved logs, the server's leaderboards and boss status — can show a real name instead of `#<code>`. A name-less overlay entry never invents an NPC; only a real scraped name resolves an unknown id, and a curated name/portrait always wins.
  - The web UI's community overlay (`npc-portraits.js`) now also loads names into `window.A2CommunityNames`, and the combat review swaps a `#<code>` label for the community name when one is known.
- Community-sourced and id-matched, not official or id-verified; this is a display fallback only and the curated bundled table stays primary. (Rendering the names on the public site and the live meter also needs the server to publish them on `/api/v1/npc-portraits` and to pick up this library version — a paired server release.)

## Wire two more global hotkey actions: Open Settings and Screenshot lock (0.2.246)

- Two previously-unbindable global-hotkey actions are now wired: **Open the Settings page** (opens the app on its Settings route, not just the window) and **Screenshot lock** (toggles the overlay's screenshot freeze). Both appear in Settings → Global hotkeys like the others; unbound by default.
- Screenshot lock needed a faster path than the ~10s settings sync, because a *locked* overlay stops its meter poll and so can't be reached to unlock. A global hotkey fires in the app process and can't call the separate overlay window directly, so the app now bumps a one-shot counter (`/api/overlay/commands`) and the overlay watches it on a light ~1s command poll that keeps running even while locked — so the same key locks and unlocks within about a second.
- As before, global hotkeys are Windows-only (they work even while the game is focused) and inert until you assign keys; nothing changes for anyone who hasn't bound them.

## Optional: update your community-rank badge live after each fight (0.2.245)

- The overlay's community-rank badge (e.g. "World Top 8%") fills after an upload — until now only when you pressed **Upload** or on quit. A new overlay setting, **"Update the rank live after each fight"** (off by default), refreshes it during play: once a **ranked** fight has paused, the client uploads that encounter **unlisted** and re-fetches your standing, so the badge keeps up without a manual upload.
- Tightly bounded and private-by-default: it only runs when you turn it on **and** the rank badge is on **and** a share server is set; it waits until combat has been idle a few seconds (a fight ended), uploads at most once every 20s, runs one refresh at a time on a background worker, and **only uploads ranked-eligible fights** — trash pulls are never uploaded and never clear a standing you already earned. All best-effort and guarded, so it never disturbs capture.

## Optional: show each player's server (world) name on the live meter (0.2.244)

- A new Live Meter / Combat records setting — **"Show each player's server (world) name next to their name"**, **off by default** — labels every row (you and party members) with their home world, e.g. `Me · Nezekan`. The id→world name comes from the official server list already used for region detection (0.2.242); if it hasn't resolved, the **Retry region detection** button fills it in.
- The live snapshot now carries each player's home **server id** (from the party roster, or your profile for yourself), and the name is resolved per row only while the option is on — so turning it off removes the labels immediately and nothing is added when a server can't be matched.

## Fix the live meter resetting repeatedly during long instance fights (0.2.243)

- **Symptom:** during sustained runs (e.g. a Krao expedition) the live meter kept zeroing itself mid-fight. A capture showed **997 storage rollovers** in one session — each rollover flushes a part and starts a fresh live view, so the totals reset again and again.
- **Cause:** in-instance phase teleports flip the engine's zone-reset signal, which advances the identity *epoch*. The rollover's memory-bound counters — "distinct players" and "segments" retained — were keyed on `(epoch, …)`, so the same small party looked like dozens of new players and hundreds of new segments as the epoch churned, tripping the 48-player rollover over and over.
- **Fix:** those counters now measure real combat volume — distinct party **actors** and genuine **segments** (a manual split, a PvE/PvP switch, or a lull longer than the segment gap) — independent of epoch. Epoch churn no longer forces rollovers, so the live view holds through a long fight; genuine large fights (many real players / segments) and the hard record/telemetry caps still bound memory and roll over as before. These counters are used only for the rollover decision, so nothing in analysis, segmentation or saved logs changes.

## Capture your world/server name, and a "retry region detection" button (0.2.242)

- **World/server name is now captured, not just the ID.** The app already resolved your region from your recorded server ID against the official server list; it now also keeps that list's **world name** per server, so recordings carry it (`meta.server_name` and per-player `server_name`). The Live Meter page shows it next to the region and beside your identity (e.g. "server 2102 (Nezekan)"), and the shared combat view shows it beside each player's server ID. It's hotlinked from the official list and omitted cleanly when a server has no published name.
- **Retry region detection.** Region resolution runs once at launch and can fail if you were offline or the official source was blocked. A **Retry region detection** button now appears on the Live Meter page when that lookup failed; it re-fetches the region and world list immediately (bypassing the cache), and the region/world fill in here when it resolves — no app restart needed. It stays hidden when the lookup succeeded or is still in progress.
- Because region is derived entirely from the server ID, resolving it here is also what makes the **Region** community-ranking scope available; the recording never needs to carry a region directly.

## Crafting: proficiency shown as tier + level, correct names and caps (0.2.241)

- **Fixed the proficiency requirement.** A recipe now reads as a **tier plus the level within that tier** instead of a single absolute number. Proficiency runs 50 levels per tier — Novice 1–50, Professional 51–100, Expert 101–150, Master 151–200 — so the *Star Dragon Lord Longsword* (source level 55) now correctly reads **Professional level 5** (55 − 50), not "intermediate mastery 55". The recipe list, the detail header, the "can you craft this" standing and the success-rate line all use this throughout.
- **Correct tier names.** The "your mastery" tier dropdown now shows the in-game names — **Novice** and **Professional** (previously "beginner"/"intermediate") — plus Expert/Master, and only offers the tiers the selected profession actually makes recipes in.
- **Level caps at 50.** The level field is a number up to **50** (per tier), and when a tier is the profession's highest it caps at that profession's real maximum in that tier, matching "up to the max for that profession".
- Your mastery is compared to a recipe on one absolute scale under the hood, so "✓ you can craft / locked for you", the craftable-only filter and the over-level success projection are all consistent with the new tier + level entry.

## Crafting: community-measured success rates (0.2.240)

- The Crafting workshop now shows a **success rate** per recipe. Our recipe source (gamers4.life) only carries the combo *trigger* rate and NCSoft publishes no official success table, so this is sourced from **metabot.gg's** community-measured data: a new `tools/export_crafting_success.py` scrapes each product's **base success chance at its required proficiency** (plus combo chance) into a small, source-attributed `crafting-success.json`, which the workshop matches to its recipes by name (158 products, all matching our catalog).
- For a matched recipe it shows the **measured base %** at the requirement, and — when you enter a higher mastery level — an **estimated** projection toward the per-tier cap (standard gear never reaches 100%). Where a recipe isn't in the community dataset it says **not available**. Everything is labelled community-measured (metabot.gg), not developer-confirmed, and the base/estimate/not-available distinction is explicit.
- The snapshot refreshes on the existing **daily** asset-refresh job and is served to the app and the public site.

## Crafting: rarity and item-type filters, and "what can I craft?" (0.2.239)

- The Crafting workshop no longer effectively shows only Unique-and-up recipes. It always carried every tier (Common/Rare/Epic/Unique/Heroic) and types, but the list showed the first 80 matches with no way to narrow them, and Unique dominates. Added:
  - a **Rarity** filter (Common · Rare · Epic · Unique · Heroic), derived from each recipe's output grade;
  - an **Item type** filter (Weapon · Armor · Accessory · Material/other), derived from the output's icon path;
  - a **Your crafting mastery** row — pick your mastery tier and enter your level, and each recipe shows whether you can make it (and your level margin), with an **"Only what I can craft"** toggle to hide the rest. The recipe detail spells out the requirement and your standing. The exact success percentage isn't in the source data, so it's described as a level margin, not a fabricated number.

## Share build points when you collect a character (0.2.238)

- Collecting a character in **My Character** now shares its observed point totals with the community **"highest observed build points"** — on by default, with a toggle under Settings → Community stats (*"Share your build's point totals when you collect a character"*). Previously only running an **Optimize** submitted anything, so a character you just collected never appeared in the server's observed totals. The submission is anonymous: only the class, region, game version and the spent skill / stigma / Daevanion point totals (source `profile_lower_bound`) — never your name, character id, server, IP or gear — and it's best-effort, so a missing server or an opt-out simply sends nothing.

## Upload recordings before the size cap deletes them (0.2.237)

- A new opt-out setting, **Upload a recording to the server before auto-delete reclaims it** (`meter_upload_before_prune`, on by default), under Settings → Combat records. When the logs folder is over its size cap and the oldest recordings are about to be deleted to make room, each is uploaded (unlisted, like the stop/quit auto-upload) **first**, so a long session's older parts — and the boss kills recorded in them — aren't lost before they can be shared. It only acts while auto-delete is on and a share server is set, is best-effort, and never keeps the folder over its cap if an upload fails. Applies to both the in-capture prune (the active recording is still never deleted) and the launch-time prune.

## Roadmap: per-effect split and dedup hardening marked shipped (0.2.236)

- Documentation only: the combat roadmap now records two server-side items as **shipped** — the **per-effect PvE/PvP split** in community rankings (server 0.2.79; a mixed segment counts only its mode-matching damage) and the **anonymized party-signature hardening** of same-defeat grouping (server 0.2.78; different parties killing near-simultaneously stay distinct). No app behavior change in this release.

## Two more bindable global hotkeys (0.2.235)

- Added two global-hotkey actions you can bind in Settings → Hotkeys: **Show / hide overlay event notifications** (mute/un-mute the new event strip without opening the app) and **Exit Aion 2 Calc**. Both call the same in-process code the UI does. As with the other hotkeys, binding and dispatch are cross-platform but a key actually firing while the game is focused is Windows-only.
- Still unwired (need a faster app→overlay channel or page navigation, tracked in the roadmap): screenshot-and-lock, open a specific page, and field-boss/artifact status.

## World comparison reason + open-world boss-kill reporting on by default (0.2.234)

- Combat review's *Matched public comparisons* now says **why** the **World** scope is Unavailable when it is — "no comparable public cohort yet", naming what World matching groups on (the encounter's boss, game version, difficulty and party size), rather than a generic line. This completes the "why a scope is Unavailable" hint started in 0.2.231 (which covered the Server/Region no-profile case).
- **Report open-world boss kills to the community world-boss feed is now on by default** (opt-out), matching the enemy-HP reporter. Reporting stays anonymous (a per-install key) and a kill is still surfaced only once two distinct installs agree, so no single install's kill is shown alone. Turn it off in Settings → Combat records.

## Regional event notifications on the overlay (0.2.233)

- The overlay now shows a compact **event strip** — the next rift, Shugo, battlefield and field-boss windows — when one is active or within 15 minutes. On by default, with a toggle in **Settings → Overlay** ("Show regional event notifications").
- It uses the region you pick on the **Timers page** (shared between the app and overlay), and the same bundled community schedule the Timers page already uses — a scheduled window is a **community forecast, not live status**, and each entry says so on hover (including a note when community reports conflict). No new data source and no extra network calls.
- Active events show their remaining window (entry countdown while the entry window is open); upcoming ones show a "in 5m" countdown. The DST-aware schedule math is now a shared engine (`event-schedule.js`) used by both the Timers page and the overlay, so the two never drift.
- **Optional sound** (off by default): a short built-in two-note chime can play when a new event notification appears, with a toggle in Settings → Overlay. You can **upload your own sound** (MP3/OGG/WAV/WebM, ≤1 MB, ~2 seconds) and a Test button to preview it; the sound is stored locally and never included in a settings backup.

## Community NPC portraits show in combat review and the overlay (0.2.232)

- NPC portraits scraped by the log server (the `aion2logs portraits` job) now **display** across the app as a fallback behind the curated bundled table. Combat review's *Enemy encounters* shows a small portrait beside each boss/NPC, the live overlay shows the current target's portrait on its target line, and the shared log-view pages pick them up too.
- The portrait lookup (`npc_info`) gains a **community overlay**: for a catalog NPC with no bundled art, it falls back to the server's `npc-portraits-community.json`. Curated bundled portraits always win; community art never overrides one, and is never invented onto an NPC the catalog does not already know.
- The frontend fetches the map from the configured log server (`/api/v1/npc-portraits`) and merges it into the asset map behind the bundled entries; images hotlink from the community source and render through the existing host-allowlisted image path. Community-sourced and name/id-matched — not an official or id-verified mapping.

## Combat review says *why* a comparison scope is unavailable (0.2.231)

- In the *Matched public comparisons*, a Server or Region scope that shows **Unavailable** now says which of the two reasons it is: **no verified official profile** for that character (so its home server/region can't be matched — World still compares globally), versus **not enough comparable logs yet** (which already lists the specific sample/identity shortfall). Previously both read the same generic line.

## Community rank indicator on the overlay (0.2.230)

- Wires up the off-by-default **community rank** badge: after you upload a session, the overlay shows each player's community standing (e.g. *"World Top 8%"*) for that session's main fight, beside their name. It covers the local player **and resolved party members**, keying each on their own verified standing.
- It shows the **most specific confident scope** (Server → Region → World) and only when the server's cohort is large enough to rank it — a provisional or too-thin standing shows nothing rather than a number that would swing as more logs arrive.
- The standing is fetched **once** after the upload and held for that fight (no repeated polling). Enable it under Settings → Overlay ("Show your community rank…"); it stays off until you do, and the fetch only happens when the feature is on.
- Note: the badge fills when a session is uploaded (the **Upload** button, or any upload). Per-fight auto-upload during play would make it update live after each fight — tracked as a follow-up.

## Groundwork for the community rank indicator (0.2.229)

- Lays the plumbing for an off-by-default overlay badge showing your community standing (e.g. *"World Top 8%"*) for your most recently auto-uploaded fight: a tested helper that reads a log-server rankings payload into a per-player badge (preferring the most specific populated scope — server → region → world), the `overlay_show_community_rank` setting, and the overlay rendering that appends the badge to your identity line when the data is present.
- The step that fills the badge after an upload is intentionally left for review (see the roadmap's open design questions), so enabling the setting shows nothing yet. No change to the overlay otherwise.

## Richer overlay text: per-element fonts, halo and retroreflection (0.2.228)

- **Per-element fonts.** Each labelled overlay text element — the rate (DPS/HPS), total·percent, player name, header, target line, target HP/TTK, target label, also-targets "+N", ping line and identity line — can now take its own **font family, size and weight**, each falling back to the global overlay font when left on Inherit/Auto. Pick an element in Settings → Overlay and set just that one.
- **Halo** adds a soft luminous ring around the overlay text (its own colour), layered on top of any glow. **Retroreflection** sweeps a subtle sheen across the headline text like reflective material catching light. Both are off by default and respect your reduced-motion setting.
- These ride the overlay look presets and the settings backup like the other appearance options. No change to the overlay until you enable them.

## Groundwork for the overlay on macOS and Linux (0.2.227)

- **Internal plumbing, no change on Windows.** The overlay's native layer (always-on-top, click-through, remembering its position, following the game window) is now behind a single platform interface, with the Windows implementation unchanged and documented macOS/Linux scaffolds for the native work still to come. macOS and Linux keep today's browser/plain-window overlay for now; this is the structure that lets the native overlay reach them next, with the cross-platform logic unit-tested.

## Overlay remembers its spot per monitor layout (0.2.226)

- **The remembered overlay position now restores correctly on multi-monitor setups.** Before, the overlay saved one screen position and only checked it against the whole desktop box — so rearranging or renumbering monitors could reopen it on the wrong screen (or just off-view). It now saves the **monitor layout** alongside the position: if your layout is unchanged it reopens exactly where you left it, if a monitor moved it re-seats at the same spot *within that monitor*, and if the screen it was on is gone it falls back to following the game window instead of opening somewhere stale. (Windows; the restore logic is covered by tests, the native monitor read is validated on a real Windows build.)

## Recolour more of the overlay's text (0.2.225)

- **Colour pickers for the overlay's remaining fixed text.** Settings → Overlay colors & fonts now has pickers for the **"Target"/"Dummy parse" labels**, the **also-targets "+N" names**, the **ping line** and the **identity line** — the last text elements that were stuck on a fixed colour. Each one left at its default keeps today's look, and they ride the settings backup and the overlay look presets alongside the existing colours.

## Enemy HP learns the true value, without the killing-blow overkill (0.2.224)

- **The community enemy-HP each meter learns is now the enemy's *true* HP, not an inflated one.** When you land the finishing blow, the game records its full hit even though only part of it was needed to kill — so "total damage dealt" overcounts the real HP by that overkill. The meter now reads the enemy's own HP packets to back out the true amount: at the last packet where the enemy was still alive it measures how far its HP% had fallen and scales that to 100%, keeping every point of HP actually removed and dropping only the finisher's overshoot. It falls back to total damage only when no live HP packet was seen. On real fights the correction scales with the enemy: only ~2% on a big boss (one hit is a tiny slice of its HP) up to ~25% on fast-killed trash, and nothing when there was no overkill. Combined with the server's reset, the shared HP values re-gather to accurate numbers.

## Accurate per-release notes (0.2.223)

- **The release notes shown on each download now match the version.** Previously, when a version had no section in the changelog the publisher quietly fell back to the newest *existing* section, so several releases showed the wrong (older) notes. It now publishes a correct per-version body — or a clear generic one when a section is genuinely missing — and a test fails the build if a version is bumped without its changelog entry.

## Browse community raid plans by boss (0.2.222)

- **Find the plan for the fight you're in.** The raid planner's *Browse plans* now has a **boss filter**: pick a boss (from the bosses other players have published plans for) to see just those plans, or *All* to clear it. Plan cards show the boss a plan is for.

## Raid plans play themselves on the overlay (0.2.220)

- **Bind a plan to a boss, and the overlay plays it for you.** In the planner, set a plan's **Boss / NPC id** (or inherit it from a compared fight). Then the overlay's **Plan tab** auto-plays that plan for the boss you're actually fighting, synced to the pull's elapsed time, so the token positions match the real encounter. With no match (or auto-play turned off) it loops the latest plan as a preview. New setting: *Auto-play a saved raid plan* (on by default).

## The overlay no longer resets mid-fight — bosses and mini-bosses (0.2.219)

- **Mechanic pauses don't clear the meter.** A boss (or a sustained mini-boss/elite fight) that stops taking damage for a few seconds during a mechanic no longer makes the overlay reset or collapse. The fight is held as long as the enemy is still engaged and below full HP and your party is alive.
- **Wipes and resets end it reliably.** A full wipe, the enemy leashing back to full HP, or running back and re-pulling correctly starts a fresh attempt — even when deaths weren't captured out of range. A battle-rez mid-fight never falsely resets.

## Community enemy-HP database + accurate HP% (0.2.218)

- **Enemy HP shown as a real, community-calibrated amount.** The meter learns each enemy's effective HP (the damage it takes to die) pooled anonymously across players, and blends it with the game's broadcast HP fraction so the target's HP reads correctly in the same units as your damage. Sharing is anonymous and on by default; turn it off with *Share enemy HP data* in Settings.
- Also includes the first version of the mid-fight overlay-hold fix for bosses (hardened further in 0.2.219).

## Enemy HP: effective-HP on hover + sturdier max-HP capture (0.2.216)

- **Hover the target's HP% to see its effective HP in damage terms** — the total recorded damage dealt to it so far (packet-sourced and exact, on the same scale as your damage), alongside the game's raw internal HP for reference. For a completed kill this is the real "HP ≈ damage to kill it."
- **Sturdier max-HP capture.** The target's max HP is now taken from a sample observed at full HP (current ≥ max) — the reliable value the game reports at spawn — mirroring reference meters. Only when you joined a fight mid-pull (never saw it at full) does it fall back to the largest value seen, so a stray mid-fight sample can't inflate the max.

## Enemy HP shown as a percentage, not a mismatched raw number (0.2.215)

- **Fixed the confusing "enemy HP doesn't match my damage" readout.** Investigated with two diagnostic captures plus the game's own combat-analysis screen: the game killed a mob with **6,420 damage** that the packets report as **119.70K HP** — enemy HP is carried on a **~16–19× larger internal scale than damage**, so printing it next to your damage (e.g. `0 / 810K`) could never line up. Our damage numbers are correct (they match the game's own meter); the raw HP value just isn't comparable to them.
- The overlay now shows the target's remaining HP as a **percentage and bar** (both exact and packet-sourced). The raw internal HP numbers are still available **on hover**, clearly labelled as the game's internal scale. This is a display change only — no number is invented or rescaled.

## Fix: the overlay's opacity slider could stop the meter (0.2.214)

- **Fixed: dragging or clicking the overlay's opacity slider could stop the live meter** for some users. The overlay is a frameless always-on-top window; interacting with the slider could shift it under a stationary cursor, so the browser's resulting mouse click landed on the Start/Stop button in the header and posted a stop. The Start/Stop button now only toggles when the click genuinely *began* on the button, so a click that drifted onto it from elsewhere is ignored. Keyboard activation of the button still works.

## Configurable global hotkeys (0.2.213)

- **New Settings → Overlay → Hotkeys section (Windows).** Assign a global shortcut to any of: show/hide the overlay, start/stop the meter, clear the meter (battle reset), toggle click-through, show/hide the Party-DPS overlay, and open the app window. They fire even while the game has focus. Click a field, press the combo (e.g. Ctrl+Shift+M), Save; Clear unbinds.
- **Off by default** — no keys are bound until you assign them, so nothing changes for existing setups. Bindings ride the settings backup.
- Dispatch runs in-process (each hotkey calls the same code the on-screen button does), and only the listed actions can be bound, each validated — a settings file can't register an arbitrary key. macOS/Linux global hotkeys are still to come; the pass is Windows-first.

## Stopping the meter no longer hides the overlay (0.2.212)

- **The overlay now stays open when you stop the meter.** Previously, pressing Stop — including the overlay's own Stop button — closed the transparent overlay, which was jarring (the overlay you just clicked vanished). Now stopping leaves the overlay up showing the last fight's numbers, with its Start button ready to go again.
- **The overlay's own Stop button never closes the overlay**, regardless of the setting below.
- **New setting** (Settings → Overlay, **off by default**): "Close the overlay when I stop the meter" — turn it on to restore the old behaviour where stopping from the app also closes the overlay. Rides the settings backup.

## Click through the overlay (0.2.211)

- **New "Click through the overlay" toggle** (Settings → Overlay layout, **off by default**, Windows). When on, the mouse **passes through the overlay to the game** so the always-on-top meter never intercepts a click — handy for streamers and in raids. It applies to an open overlay within ~10 seconds and rides the settings backup.
- **Your overlay buttons still work.** Rather than making the whole window click-through (which would lock you out of Start/Stop and the sliders), the overlay reports where its controls are and a fast cursor hit-test drops click-through **only while you're hovering a control** — so clicks pass through everywhere else but the buttons, tabs and opacity slider stay usable. To drag or resize the overlay, hover it (or turn the toggle off).
- Windows first; macOS/Linux pass-through is still to come. The pass-through itself is validated on a real Windows build (the test harness only runs the web page, not the native window).

## Customization profiles now carry their overlay background (0.2.210)

- **A saved customization profile now bundles your overlay background image**, so switching to a profile also restores the background it was saved with — not just the colours, fonts and sliders. The image is stored **locally, in this browser on your own machine** (kept at a reduced size so it fits): it is **never uploaded** and is **left out of the "Copy share code"**, which still carries only your colours and settings. Applying a profile that was saved with no background clears the current one; older profiles saved before this change leave the background untouched.
- **New square selector under Settings → Profiles & backup → Customization profiles.** Every profile that carries a background now shows as a square tile with a preview of that background and the profile's name — click a tile to apply that whole profile in one step.

## Overlay no longer flickers a black edge over the game (0.2.209)

- **Fixed: a black band could flash at the top of the screen whenever the overlay was open** (reported on Windows 10, borderless-windowed, regardless of where the overlay sat). The overlay was running a continuous per-frame loop just to measure its own render FPS — even though the FPS readout is off by default — which kept the always-on-top, semi-transparent window compositing every frame and made the desktop compositor flicker over a borderless game. The frame loop now runs **only while the FPS readout is enabled**, so a normal overlay sits idle between its twice-a-second updates and no longer drives constant repaints.

## Update-on-close no longer hangs; accurate Start/Stop; overlay tidy-ups (0.2.208)

- **Fixed: applying an update could hang on close until you quit from the tray icon.** With "keep running in the system tray" enabled, closing the window only *collapses to the tray* — the process stays alive — so the updater (which waits for the app to exit before swapping files) never proceeded. A programmatic Quit or update now also stops the tray icon so the process actually exits, and the update path no longer waits on the on-quit upload. (The tray setting is **off by default**, so most installs were never affected — this fixes it for anyone who turned it on.)
- **The app's Start/Stop button now reflects the auto-started meter promptly.** With auto-start on, the meter is already running at launch; the app button could lag behind the overlay's (which showed "Stop") for a couple of seconds. The app now refreshes its meter status briskly while idle, so the button matches the real capture state right away.
- **Overlay: the "Latest combat" status line moved to the right of the D.Taken button** (into the metric row), and the Start/Stop button stays pinned to the right of the header.

## Long instanced runs stay rankable + automatic logs cleanup (0.2.207)

- **Fixed: a long instanced fight could flip to "partial capture · unranked" partway through.** When a run is long enough to roll over into a new internal storage part, that part resets its "entry observed" flag — and the meter was treating that as "I joined mid-instance," so it marked the rest of the fight unranked (this showed up after a death in a long run, which is just a late point in the fight). The entry **was** observed at the start and is carried across parts, so a rolled-over run now stays rankable in both the live view and the saved log. (Diagnosed from a user's capture that rolled over into 270 parts.)
- **Automatic logs-folder cleanup with a size cap.** A long session writes many rollover parts, so the `logs` folder could grow very large. The app now keeps it under a configurable cap — **default 1024 MB (1 GB)** — by deleting the oldest recordings first when it's exceeded (never the session being captured). Set it under **Settings → Combat records → "Keep the logs folder under … MB"**; `0` turns auto-delete off. Cleanup runs during capture and once at launch.

## Always-on meter, overlay Start/Stop, smoother resize, quit-upload (0.2.206)

- **The meter now starts automatically when the app launches** (on by default), so the app and overlay show live data without pressing Start — Start/Stop then just pauses and resumes. It's best-effort: if packet-capture support (Npcap/libpcap) isn't installed yet it stays stopped and the first Start walks you through installing it. Toggle under **Settings → Combat records → "Start the meter automatically when the app launches"**.
- **The transparent overlay has its own Start/Stop button** at the right of its header (under the "Latest combat" line). It mirrors the app's button — green **Start** when stopped, red **Stop** while running — so you can start or stop capture without alt-tabbing to the app. It uses your remembered Players scope.
- **Smoother overlay resize.** Dragging the resize grips was glitchy because each drag step both resized the native window and re-triggered a layout observer that resized it again — a feedback loop. Resizing now drives the window directly and coalesces to one native resize per frame, so the grips track the pointer cleanly.
- **Auto-upload on quit.** If you close or quit the app while the meter is still running, the session is now auto-uploaded on the way out (same **Upload on stop** setting, bounded so it never hangs shutdown). If you'd already pressed Stop, it was already uploaded, so quitting won't upload a duplicate.
- **Website:** the "● N meters today" count now sits just left of the colour switcher in the header.

## Meter stability in big fights + overlay/filter persistence (0.2.205)

Three fixes from field reports:

- **The meter no longer freezes in very large fights (e.g. Abyss world bosses).** The app page and the transparent overlay both poll the live meter about twice a second; in a huge fight the full-session recompute behind each poll is expensive, and running it several times a second while holding the capture lock could starve the capture thread — the meter would freeze mid-fight and names could degrade to placeholders like "Player M". The live snapshot is now memoized for a short, **self-tuning** interval (it never recomputes more often than the last recompute actually took), so snapshot work stays at roughly half the time budget no matter how big the fight gets and capture keeps up. Because a frozen app can't finish **Stop**, this also indirectly protects the auto-saved log, the diagnostics ZIP and the auto-upload that run when you stop.
- **The overlay now remembers where you put it by default.** Previously the overlay re-anchored to the game window every time it reopened (after Stop, or on launch), so a position you'd dragged it to was lost. "Remember overlay position" is now **on by default**: the overlay reopens exactly where you last left it (each overlay — meter and party — remembers its own spot). On a first run with nothing saved yet it still places itself sensibly next to the game once, then stays put. You can switch back to follow-the-game under **Settings → Overlay**.
- **The "Players" filter on the live meter now persists** across closing and reopening the app (like the character-name field already did), and its default is now **Self + Party** instead of Automatic — lighter by default and the common choice, while All observed players stays one click away.

## Dream Guardian Eonos no longer counts as a boss (0.2.204)

- **"Dream Guardian Eonos"** (the solo story/leveling encounter) was flagged as a boss in the upstream NPC catalog, so it showed up in the community **boss lists** (boss progression, recorded defeats and boss kills). It's now corrected to **not a boss** via the verified local NPC-role override, so it no longer headlines an encounter or appears in any boss list. The correction lives outside the generated catalog, so a catalog refresh won't re-introduce it.

## Report world-boss kills to the community feed (0.2.203)

- New **opt-in** setting under **Settings → Combat records → "Report open-world boss kills to the community world-boss feed"** (off by default). When on, finishing a fight that contains a confirmed **open-world boss defeat** posts one tiny, anonymous kill event to your configured community server's new `/api/v1/boss-kill` endpoint — so world-boss respawn/availability tracking and the Discord bot update promptly **without uploading the whole combat log**.
- **Anonymous by design.** The report carries only what the kill feed needs to place and merge it — boss NPC id and name, physical server, kill time, and map/instance/region/difficulty/patch — plus a **stable per-install reporter key** derived from the same random, local-only salt the daily heartbeat uses (the salt is never sent, and this key is distinct from the heartbeat token). No account, character, IP or capture data is sent.
- **Corroborated, not one-click.** A world-boss kill seen only by these standalone reports surfaces on the public feed **only once two different installs report it** — the server decides the threshold; your client only ever reports its own verified defeat and never moves a timer alone. Only real, packet-confirmed open-world boss deaths qualify, and each distinct kill is reported at most once (a local marker dedupes repeated auto-saves of the same fight). The toggle rides the settings backup.

## Accessibility: "Skip to content" link (0.2.202)

- Every page — the desktop app and all website pages — now starts with a **"Skip to content"** link as the first focusable element. It's hidden until a keyboard user presses Tab, then appears at the top-left and jumps past the navigation straight to the main content. Mouse users never see it. This closes the last gap listed in the accessibility statement.

## Accessibility: reduce-motion and visible keyboard focus (0.2.201)

- The app and website now honor your operating system's **"reduce motion"** setting (`prefers-reduced-motion`): animations and transitions collapse to near-instant and smooth scrolling is turned off, for a still interface — in addition to the existing per-feature motion controls.
- **Keyboard focus is always visible.** Every interactive control shows a clear focus outline when you reach it by keyboard, including the form fields that previously showed only a border change. Mouse clicks keep the quiet style, so the outline is there for keyboard users without adding clutter for pointer users.

## Class-coloured player trend sparklines (0.2.200)

- The per-player DPS trend sparkline (shown when you expand a row with the DPS graph on) is now drawn in that **player's class colour**, with a faint matching fill, so it reads at a glance and lines up with their bar colour instead of a generic gold line.

## Per-player DPS trend when you expand a row (0.2.199)

- With the live DPS graph enabled, **clicking a player's row** (which already shows their per-skill breakdown) now also shows a small **sparkline of that player's DPS over the fight**, right above their skills — so you can see who's ramping, bursting or dropping off at a glance. Each point is a real per-poll reading, kept per player and reset when a new fight starts. It's tied to the same **Settings → Overlay → "Show a live DPS/HPS graph"** toggle, so if you don't use graphs, expanding a row looks exactly as before.

## Stream the overlay to Discord / OBS (0.2.198)

- New **Settings → Overlay → Streaming (OBS / Discord)** helper with the overlay's **browser-source URL** and a **Copy URL** button. Add it as an **OBS/Streamlabs Browser Source** (it renders transparent), composite it over your game scene, and stream that to Discord — the overlay shows on your stream. For Discord **Go Live** directly, share your **whole screen** so the always-on-top overlay is included.
- Honest note built in: a game-**window**-only share won't show the overlay, because it's a separate window layered on top rather than part of the game's own frame (the same reason most meter overlays don't appear in window captures). Use a Browser Source or a full-screen share. (We deliberately do **not** inject into the game process to force it into a window capture — that risks an anti-cheat ban.)

## Open the overlay when the app starts (0.2.197)

- The transparent overlay now **opens together with the app**, on by default, so it's ready the moment you launch — it waits for the game and still follows the AION 2 window when that appears. Turn it off under **Settings → Overlay → "Open the overlay when the app starts"**. This is separate from **"Show overlay when starting the live meter"** (which opens it when you press Start): leave both on to always have the overlay up, or keep only the meter-start one if you'd rather it appear with capture. The setting rides the settings backup.

## Accent-matched overlay presets (0.2.196)

- Five new starter **overlay look presets** named to match the app's **accent colours** — **Crimson, Emerald, Azure, Amethyst** and **Rose** — each with a header and glow in that accent on rounded gradient bars. Pick the same name as your app accent (Settings → Appearance) for a coordinated look in one click, under Settings → Overlay → Overlay look presets. Like all presets, they carry only overlay look settings and are re-validated on import.

## Podium colours on the top three ranks (0.2.195)

- When overlay **rank numbers** are shown, the top three places are now tinted **gold, silver and bronze**, so the leaders stand out at a glance like a mature meter's leaderboard. It's pure styling of the existing ranking — nothing below third place changes, and it's only visible with rank numbers turned on (Settings → Overlay → Overlay layout).

## "New fight" button on the overlay (0.2.194)

- The overlay header has a new **New** button that **starts a fresh encounter** — the next combat event begins a new split — so you can reset the meter between pulls without alt-tabbing back to the app (it's the same action as **Split now** on the Live Meter page). It briefly confirms with **New ✓** and clears the live graph so the next fight starts clean. The header's **Copy** button is now styled to match **Lock**, **New** and **Hide** instead of showing as a plain browser button.

## Live DPS/HPS graph on the overlay (0.2.193)

- The overlay can now show a **live DPS/HPS graph** — a sparkline of the party total over the current fight, like NotMeter's trend line. Turn it on under **Settings → Overlay → Overlay layout → "Show a live DPS/HPS graph"**. It follows the active metric tab (DPS, HPS or damage taken), labels the current and peak value, and resets when a new fight starts. Every point is a **real reading** taken each refresh (the summed live party rate at that moment) — nothing is interpolated or invented — and it rides your overlay look presets and the settings backup. Off by default.

## Share customization profiles by code (0.2.192)

- Customization profiles can now be **shared**. In Settings → Profiles & backup, **Copy share code** turns the selected profile into a short code to send a friend; **Paste a shared code** saves one they sent you. The code carries only the look — theme, accent, class colours and overlay look — and is re-validated on import (unknown theme/accent fall back to defaults; only recognised look settings are kept), so a bad or tampered code is rejected rather than applied.

## Auto-upload the log when you stop the meter (0.2.191)

- When you **stop the meter**, the saved session is now **uploaded to your configured log server automatically** — **on by default**. The notice shows the shared-log link when it's done, and if the upload fails the session is still saved locally and you can Upload manually. Turn it off any time under **Settings → Meter → "Upload the log to the configured server when you stop the meter"**. It respects your configured server and visibility (unlisted/public/private) and only runs when a session was actually saved.

## Customization profiles (0.2.190)

- Save your whole look as a named **customization profile** and switch between them in one click (Settings → **Profiles & backup**). A profile bundles your **theme**, **accent colour**, **class colours** and the **overlay look**, so you can keep, say, a bright "Streaming" set and a muted "Raiding" set and flip between them instantly. **Save current as…**, **Apply** and **Delete** manage them; profiles are stored in your browser.

## Settings organised into subtabs (0.2.189)

- The **Settings** page is now split into clear subtabs — **Appearance**, **Overlay**, **Meter**, **Server**, **Profiles & backup** and **App & data** — instead of one long scroll. Click a tab to see just those settings; your last-used tab is remembered. Nothing moved out of Settings, it's only grouped, so every control is where you'd expect under its heading.

## Per-skill breakdown on the overlay (0.2.188)

- **Click a player's row** in the overlay's DPS view to expand a **per-skill damage breakdown** — their top skills with each skill's damage and share of their total (e.g. *Flame Harpoon 240K · 40%*). Click again to collapse. Expanded rows stay open as the meter keeps updating, and the breakdown uses data the overlay already receives (no extra load). This brings the overlay in line with full meters like NotMeter, where you can drill into who did what.

## Accent colours on the website too (0.2.187)

- The public site (aion2calc GitHub Pages) now has the same **accent-colour** picker as the app: a small ◉ button in the top-right header, beside the light/dark toggle, cycles **Gold → Crimson → Emerald → Azure → Amethyst → Rose**. Your choice is remembered per browser and applied before the page paints, so the whole site recolours to match the look you set in the app.

## Copy the meter to the clipboard (0.2.186)

- New **Copy** button in the overlay header (beside Lock) copies the current view as a tidy text leaderboard — metric, boss and duration, then each player's rank, per-second rate and share — ready to paste into party chat or Discord, e.g. `1. Nyx  6.00K/s  (44%)`. It follows whichever metric tab is active (DPS, HPS or damage taken) and confirms with a brief "Copied".

## App accent-colour themes (0.2.185)

- New **Accent colour** setting (Settings → Appearance, right under Theme) recolours the whole app's accent — the brand text, nav highlight, section headers, links and the live indicator — in one click. Choose **Gold** (the default), **Crimson**, **Emerald**, **Azure**, **Amethyst** or **Rose**. It layers on top of your light/dark theme (each accent has tuned light and dark shades) and is remembered across launches, applied before the first paint so there's no flash.

## Class-colour palette presets (0.2.184)

- The app's **class colours** (used across the Live Meter, combat review, charts and the overlay bars) now have one-click **palette presets**: in **Settings → Combat class colors**, pick a palette and **Apply** to set all eight classes at once. Palettes are **Default**, **Colourblind-friendly** (the Okabe–Ito set, chosen to stay distinct for red/green colour-vision deficiencies), **High contrast**, **Pastel** and **Vivid**. You can still fine-tune any class afterwards, and the picker appears everywhere class colours are edited — the app and the public site's combat review.

## Documented the overlay look & presets (0.2.183)

- The user guide now has an **"Overlay look and look presets"** section covering the overlay appearance settings (rank numbers, compact rows, class swatch, class-coloured names, zebra striping, bar style, text outline, colour-cycle, highlight-my-row, the self-rank line and the smooth bar animation) and how to save, apply and **share** look presets by code — so the features added across 0.2.172–0.2.182 are discoverable.

## Share overlay look presets by code (0.2.182)

- Overlay look presets can now be **shared between players**. In Settings → Overlay look presets, **Copy share code** turns the selected preset (or your current live look) into a short code you can send a friend; **Paste a shared code** saves one they sent you as a new named preset. Only overlay look settings travel in the code — never your server, keys, background image or any personal data — and every imported preset is re-validated before it's saved, so a bad or tampered code is rejected rather than applied.

## Search the field boss respawn reference (0.2.181)

- The **Timers** page's field-boss respawn reference gains a **search box** — type a boss name or zone to filter the 54-boss catalogue instantly (matching groups auto-expand, and each shows its live match count). Makes finding one boss among the Verteron, Altgard and Abyss lists quick.

## Your rank on the overlay's "You" line (0.2.180)

- The overlay's **You: <name>** line now shows your **live standing** on the current metric — e.g. **You: Nyx · #2 of 8** — so you can see where you place without scanning the rows. It tracks whichever metric is shown (DPS, HPS or damage taken), uses your re-acquired identity (so it follows you across teleports and instance changes), and only appears once there are at least two players.

## Three new overlay look presets (0.2.179)

- Three ready-made looks in Settings → Overlay presets, each wiring up the full newer feature set in one click:
  - **Streamer** — a showcase look for stream capture: big outlined gold text, rounded gradient bars, class-colour swatches, rank numbers, zebra rows and your own row highlighted.
  - **Tournament** — maximum readability for competition: white outlined text on a strongly darkened card, flat bars, zebra rows, rank numbers and your own row highlighted.
  - **Compact raid** — a dense full-raid view: small class-coloured names, class swatches, rank numbers, compact rows (rate only), zebra striping and your own row highlighted.
- These are the first bundled presets to carry the rank-number, class-swatch, zebra-stripe, compact-row and highlight-my-row settings, so applying one is a quick way to try them all together.

## Smooth animated DPS bars (0.2.178)

- The overlay's player bars now **glide** to their new length between polls instead of snapping, so a bar that's climbing or being overtaken reads as motion rather than a jump — matching the already-smooth target-HP and TTK bars. It rides the existing **"Smoothly animate the per-second numbers"** toggle (Settings → Overlay), so turning that on now eases the bar fill as well as the number; with it off, bars behave exactly as before. Honours *prefers-reduced-motion*.

## Highlight my own row (0.2.177)

- New **"Highlight my own row"** toggle (Settings → Overlay layout, **off by default**) marks your own player row in the overlay with an accent bar and a soft tint (matched to your glow colour), so you can find yourself at a glance in a crowded party list — like the self-highlight in mature meters. Uses the re-acquired local identity, so it follows you across teleports and instance changes. Rides the settings backup and your saved look presets.

## Field boss respawn reference (0.2.176)

- The **Timers** page gains a **"Field boss respawn reference"** section: a staged, searchable catalogue of **54 named field bosses** across Verteron (Elyos), Altgard (Asmodian) and the Abyss, each with its zone, level, and the community-reported respawn — a kill-based cycle (e.g. *~2h after kill*) for open-world field bosses, or a fixed schedule for the Abyss bosses (Watcher Kaira, the three Executors, Guardian Lord Nahma). This covers the field bosses that had **no staged timer** in the schedule before.
- Everything here is **community-sourced and clearly flagged**: the section carries a *community_unverified* note, a *"confirm in game"* reminder, a *disputed* flag (sources disagree on whether these cycles are fixed at all), dated source links, and a *"checked in game"* marker on the Altgard set that was reported verified. Nothing here establishes live spawn state — it's a planning reference, kept beside the live schedule and the log-driven kill tracker.
- Groundwork for the Fera Discord bot: the staged values live in a dedicated `field-bosses.json` the bot can later surface in `/setup timers` for the bosses missing from it today.

## Overlay rank numbers (0.2.175)

- New **"Show rank numbers"** toggle (Settings → Overlay layout, **off by default**) prefixes each player row with its position — **1.**, **2.**, **3.** … — so you can see standings at a glance. Rides the settings backup and your saved look presets.

## Overlay compact rows (0.2.174)

- New **"Compact rows"** toggle (Settings → Overlay layout, **off by default**) hides each player row's trailing **total · percent**, leaving just the big per-second rate — tidier on a narrow overlay. Rides the settings backup and your saved look presets.

## Overlay class-colour swatch (0.2.173)

- New **"Show a class-colour swatch before each name"** toggle (Settings → Overlay layout, **off by default**) puts a small class-coloured square before each player's name — an at-a-glance class indicator, like the class colouring in mature meters, without recolouring the name text. Rides the settings backup and your saved look presets.

## Overlay zebra striping (0.2.172)

- New **"Zebra-stripe the player rows"** toggle (Settings → Overlay layout, **off by default**) gives alternating rows a subtle background tint, so a long party list is easier to read at a glance. Rides the settings backup and your saved look presets.

## Anonymous daily-active-meters count (0.2.171)

- The app now contributes to a **community "daily active meters"** count: once per day a packaged install tells the configured log server that *a* meter ran, so the public stats can show how many are active. It's **on by default (opt-out)** and **fully anonymous** — it sends only a token that **rotates every UTC day** (generated from a random local salt that never leaves your PC, so it can't be traced to you or linked across days), the date, and the app version. **No** name, character, server, IP or combat data is ever sent. Turn it off anytime under **Settings → Community stats**. It's best-effort and only runs from the installed desktop app (never from dev runs or tests).
- **Server side (separate repo) — pending:** a lightweight `/api/v1/heartbeat` endpoint that counts distinct daily tokens into a retention-bounded aggregate and exposes only the count. Until it exists the beacon is harmlessly ignored; once it does, the site can show the daily/trend number.

## Overlay colour-cycle effect (0.2.170)

- New **"Colour-cycle"** toggle (Settings → Overlay colors & fonts, **off by default**) slowly animates the overlay's **header and player names** through the colour spectrum — a lively palette-shift flourish. It's opt-in and honours your system **reduced-motion** preference (no animation if you've asked for less motion). Rides the settings backup and your saved look presets.

## Overlay themes now style the bars too, plus Aurora & Sunset (0.2.169)

- The overlay starter themes now set the **bar style** as part of their look, so they apply in one click: **Neon, Midnight blue, Ember** gain rounded **gradient** bars, **Minimal** gets soft rounded flat bars, and **Default (gold)** / **High contrast** stay flat (as before). Two new themes join the set — **Aurora** (teal-and-green with gradient rounded bars and class-coloured names) and **Sunset** (pink-to-orange warmth) — bringing the starter themes to **nine**. Your own saved presets are unaffected, and the per-theme description notes the bar look.

## Overlay bar styles: gradient, rounded, class-coloured names (0.2.168)

- New overlay **bar styling** (Settings → Overlay layout):
  - **Bar style: Flat or Gradient** — gradient fills shade each player's class-coloured bar from the class colour toward a darker edge, for a richer look (flat is the default, unchanged).
  - **Rounded bar corners** — makes the DPS/HPS bars pill-shaped.
  - **Colour player names by class** — tints each row's name with that player's class colour (like many mature meters), instead of the single name colour.
- All three default off/flat, apply to the live overlay within ~10 seconds, and ride the settings backup and your saved look presets.

## Five new overlay starter themes (0.2.167)

- The overlay look presets (Settings → Overlay look presets) now ship **seven starter themes** instead of two. New: **High contrast** (white text + black outline on a darkened card, for readability over any scene), **Neon** (vivid cyan/green/magenta with a glow and a monospace font), **Minimal** (muted greys, thin and slightly transparent), **Midnight blue** and **Ember**. Each is a complete look — colours (including the new target/HP/TTK text and bars), glow, outline, font and background sliders — applied in one click. Picking a theme in the dropdown now shows a short description of it. Your own saved presets and per-class bar colours are unaffected.

## Overlay: color pickers for the target-line readouts (0.2.166)

- Settings → Overlay colors & fonts now has color pickers for the **target line** too: **Target text**, **Enemy-HP text** and **TTK text**, alongside the existing rate/total/name/header pickers. So you can recolor the current-target readout to taste (or for contrast over a background photo), not just the damage numbers. Each defaults to its current look and, like the other overlay colors, rides the settings backup/restore file and the overlay look presets.

## Overlay text outline for legibility (0.2.165)

- New **"Text outline"** toggle (Settings → Overlay colors & fonts, **off by default**) draws a crisp outline around the overlay text so it stays readable over busy or bright backgrounds — a game scene behind a transparent overlay, or a light background photo. It's separate from the existing soft **Text glow**: the outline is a sharp edge drawn *behind* the letters (so glyphs aren't eaten into), and you can use either, both, or neither. A dedicated **Outline color** picker (`overlay_outline_color`, default black) sets the edge color. Both ride the settings backup/restore file and the overlay look presets like the other overlay colors.

## Overlay names multiple targets during AOE (0.2.164)

- When you're hitting **several enemies at the same instant** (AOE/cleave), the overlay's **Target** line now names the extra enemies too — e.g. `Target Mob A +2 (Mob B, Mob C)` — instead of showing only the single "most-hit" one. It triggers only when the extra enemies are struck in the **same ~1-second window** as the main target, so simply **switching** from one enemy to another (a moment apart) still shows just the new single target, exactly as before. Up to three extra names are listed; the full list is in the line's tooltip. Packet-sourced from the recorded hits — nothing guessed.

## Overlay time-to-kill bar (0.2.163)

- The overlay can now draw a **time-to-kill bar** under the target line, alongside the existing TTK number. It shows how far through the estimated **whole kill** you are **by time** — engaged time so far versus the time-to-kill still remaining — so you get an at-a-glance "almost done" without reading the seconds. It is deliberately distinct from the enemy-HP bar (which shows health remaining): the TTK bar can run ahead of or behind the HP bar when a fight starts slow or finishes fast. It appears with the TTK readout (the "Show estimated time-to-kill for the current target" toggle in Settings) whenever a TTK is available, and stays blank when TTK can't be measured — never guessed.
- New **TTK bar color** picker (Settings → Overlay colors & fonts; `overlay_ttk_color`, default a muted blue `#8fb3d0`). It rides the settings backup/restore file and overlay look presets like the other overlay colors.

## Boss progression: fastest-kill column with a log link (0.2.162)

- The **Boss progression** table (community view on the website and in the app's Combat Logs) now has a **"Fastest kill · log"** column: the quickest recorded clear time for each boss, with an **Open log** button that jumps to that log so you can review the run. It shows "Unavailable" until the server reports the fastest kill for a boss. *(Client side is live now; the server needs to start reporting the fastest-kill time and log id per boss for the times to appear — tracked on the roadmap.)*

## Remember where you drag the overlay (0.2.161)

- New **"Remember where I drag the overlay"** toggle (Settings → Overlay layout, **off by default**, Windows). With it on, the live-meter and party overlays **reopen where you last put them** instead of snapping back to follow the game window. Each overlay remembers its own spot; a drag is saved about a second after it settles, and on next launch the position is restored only if it still lands on a connected screen (otherwise it falls back to anchoring near the game). The saved positions are machine-specific — they stay on your PC and never travel in the shareable settings backup (only the toggle does). With the toggle off, the overlay follows the game window exactly as before.

## More accurate overlay time-to-kill (0.2.160)

Fixes TTK reading far too high (e.g. "5 min" at half HP on a mob that dies in under a minute).

- **Time-to-kill is now based on the enemy's observed HP-decline rate** — how fast its HP is actually dropping, from recorded HP samples — instead of dividing remaining HP by *your party's* DPS. The old method couldn't see damage from other players (open-world tagging) or account for a slow start, so it badly over-estimated how long a mob would take. The new method counts **every** damage source, so TTK matches how fast the mob is really dying and lines up with its average kill time. Verified against a real capture: a mob that died in ~8s now reads ~8s TTK at half HP (was tens of seconds / minutes).
- It stays packet-sourced — computed only from recorded HP observations, never guessed — and falls back to the party's DPS to that target only when there aren't yet enough HP samples to measure the drop. The per-target DPS fallback is also no longer diluted by time spent on other enemies in the same encounter.

## Clearer "partial capture" message (0.2.159)

- When the overlay/meter shows **"Partial capture · unranked"** because it joined an instance without seeing the entry, the message now adds that **this may not be a real partial capture** — if you didn't start the meter mid-instance, **teleport or change instances (zone out and back)** so the meter observes a fresh entry and can rank the run. (The open-world maps like the Abyss are still never flagged partial.)

## Live meter no longer clears itself after a fight by default (0.2.158)

Fixes the overlay losing its numbers shortly after combat ends.

- **"Clear the live meter after a battle ends" is now OFF by default.** It was on, with a 5-second delay, so a few seconds after you stopped hitting something the overlay/Live Meter blanked to "Ready — waiting for the next fight." Confirmed from your diagnostics: the fight's numbers stay in the session, but `battle_over` flipped at the reset delay and the overlay cleared the display. Now the **last fight's numbers stay on the overlay** until the next fight begins, a party wipe, or you clear it manually — which is what most people expect.
- If you liked the auto-clear, re-enable it under **Settings → Combat records → "Clear the live meter after a battle ends"** (the reset delay still applies). Existing installs that never changed this setting pick up the new off-by-default; anyone who explicitly turned it on keeps it on.

## Boss progression hides unknown-only bosses (0.2.157)

- The **Boss progression** table (community view on the website and in the app's Combat Logs) no longer lists bosses whose every recorded attempt is **"unknown."** A boss like *Execution Nua* that only ever appears from partial captures — where the kill or a complete wipe was never recorded — carries no progression signal, so it's now hidden; only bosses with at least one **recorded kill or observed wipe** are shown. When a filter leaves nothing with a known outcome, the table shows a short "nothing yet" note instead of a wall of unknown rows.

## Overlay keeps its numbers during heavy-combat bursts (0.2.156)

- During the busiest moments of a fight the capture thread can briefly hold the meter's data lock, which made a meter/overlay refresh **fail with "capture busy / refresh failed"** and freeze until the next successful poll (the `TimeoutError: Capture data is busy` seen in exported diagnostics). Now, when a refresh can't grab the lock in time, the meter **serves the most recent reading** (flagged internally as stale) instead of failing — so the overlay and the app's Live Meter keep showing the last numbers and recover smoothly on the next poll, rather than flashing an error mid-fight. The next successful read replaces it as usual.

## Overlay stays visible when the game isn't focused (0.2.155)

Fixes the overlays hiding each other and flicking away during play.

- New **"Keep the overlay visible even when the game is not in focus"** toggle (Settings → Overlay layout, **on by default**). With it on, the live-meter and party overlays stay on top even when the game window isn't the foreground window — so **clicking one overlay no longer hides the other**, focusing the app window doesn't hide the overlay, and a game loot/reward popup after a kill doesn't make the meter flick away.
- Before this, the overlay was shown only while the game (or the overlay itself) was the foreground window, so anything else taking focus — including our own second overlay — hid it. That was behind the reports of the overlay disappearing when switching between the meter and party overlays and dropping right after defeating an enemy.
- With the toggle on, the overlay still hides when the game is **minimised or closed** (so it never sits over unrelated apps); turn the toggle off to restore the old "hide whenever the game loses focus" behaviour. The screenshot **Lock** pin still overrides both. Takes effect when the overlay is reopened. `overlay_always_visible` rides the settings backup file.

Note: if your live DPS numbers themselves freeze or drop during very heavy fights (not the whole overlay hiding), that's a separate capture-under-load issue being investigated — please mention it if you still see it after this update.

## Overlay toolbar: Lock/Hide grouped with the tabs (0.2.154)

- Fixed the overlay header so the **Meter/Plan tabs and the Lock/Hide buttons sit grouped together on the left**, with the status text right-aligned. They were spread apart with `justify-content: space-between`, which let Lock/Hide float into the middle and, at narrower widths or larger fonts, visually crowd the Meter/Plan tabs. The layout is now deterministic regardless of width or font.

## Settings page: consistent left padding (0.2.153)

- Fixed a layout bug on the **Settings** page where every section from **Live meter overlay** downward (Overlay layout, Combat records, backups, colors, presets, class colors, etc.) was missing the left gutter that the top rows (Theme … Log server) had, so the newer settings looked flush against the panel edge and out of line with the rest. The Log server row closed the settings body container one tag early; now all rows share the same left padding.

## Overlay resize: grow width, drag height, px fields (0.2.152)

Fixes the long-standing overlay resize problems and adds height sizing.

- **Drag-to-resize now grows, not just shrinks.** With "Resize the overlay by dragging its edges/corners" enabled (Settings → Overlay layout), the overlay can now be made **bigger**, not only smaller. The card was clamped to the window's current width, so dragging the edge outward could never grow it — only inward (shrink) worked. In the native overlay window the card is now free to grow past the window's current size and the window follows it.
- **Drag the height too.** There are now three grips when resizing is on: the **right edge** resizes width, the **bottom edge** resizes height, and the **bottom-right corner** resizes both. Previously there was no height handle at all.
- **Width and height px fields.** Settings → Overlay layout now has a **Height** field next to Width (`overlay_height`, `0` = fit to contents). Changing either value updates an open overlay within ~10 seconds — the width field no longer appears to "do nothing" when you increase it (same clamp fix as the drag).
- `overlay_height` rides the settings backup/restore file.

## Overlay look presets (0.2.151)

Switch your whole overlay theme in one click.

- A new **Overlay look presets** picker (Settings → under Overlay background) lets you **apply, save and delete named presets** that capture the overlay's whole look together: text colours, the glow toggle and its colour, the enemy-HP bar colour, font family/size/weight, the background sliders (opacity/zoom/darken), the name display mode, and your per-class bar colour overrides. Pick a preset, click **Apply**, and all of those change at once.
- Two **bundled starter presets** ship — "Default (gold)" and "Bold & large" — and **Save current look as…** stores your current settings as a named preset you can come back to.
- Saved presets live in the **settings backup/restore file** (`overlay_presets`), so they export, import and share alongside the rest of your settings. Each preset's settings are validated against the same visual-setting allowlist as a normal import, so a shared or hand-edited preset can only ever carry known, type-checked look settings — never arbitrary state.
- The background *image* itself isn't part of a preset (it's a local file on your machine, not a shareable value); everything else about the look is.

## Smoother, more real-time DPS ticking (0.2.150)

Follow-up to the live-ticking DPS from 0.2.149, to make the numbers visibly change in real time:

- The overlay now **polls the meter about twice a second** (was ~once) for more frequent genuine updates, and the between-poll animation runs at a **higher default frame rate** (the live-ticking refresh defaults to 50 ms, was 100 ms) with snappier easing — so the DPS/HPS numbers move continuously and read as live. Still packet-sourced, and you can slow or disable it under Settings → Overlay layout.

## Live-ticking DPS numbers (0.2.149)

- The overlay's DPS/HPS numbers now **keep moving in real time between polls** instead of freezing on the last value. Between updates the overlay recomputes each row's true average rate against the elapsing clock (`amount / (elapsed + time-since-poll)`), so the number ticks down smoothly while you're not landing hits and snaps back up on the next hit — the lively, real-time feel of a mature meter. It stays **packet-sourced**: only the time denominator advances; the damage/healing amount is always the recorded value, and projection runs only while combat is actually running (not when paused/idle).
- This is **on by default** now (it was the opt-in "animate DPS" toggle); you can still turn it off or change its refresh interval under Settings → Overlay layout ("Live-ticking DPS numbers").

Also:

- **Identity guidance.** When the meter is waiting for your player identity, the message now tells you to **teleport or change instances (zone in or out)** so the game resends it — the same signal the meter uses to re-bind identity — in addition to entering your character name before Start. The overlay's "Self identity not received" line says the same.
- **Overlay drag-to-resize really works now.** The resize grip was inside the overlay's drag region, so dragging it moved the window instead of resizing. The grip now sits outside the drag region (and is a bit more visible when enabled), so dragging the right edge resizes the overlay width as intended.

## Overlay enemy-HP bar (0.2.148)

- The overlay now draws the current target's **remaining HP as a bar** under the target line — a filled bar over the max, so you can read the pull at a glance. It shows only when the enemy-HP readout is enabled (Settings → Live meter overlay) and real HP was captured for that target; it's never guessed.
- A dedicated **Enemy HP bar color** picker (Settings → Overlay colors & fonts, `overlay_hp_color`, default red) sets the fill colour, and it rides the settings backup/restore file.

## Overlay & meter fixes: target tracking, open-world capture, resize, background defaults (0.2.147)

Overlay / live-meter fixes and settings:

- **Current target now follows a target switch.** The overlay's Target readout used to stick to whichever enemy had taken the most damage (e.g. a boss you just killed); it now follows the enemy you hit most recently, so it updates when you move to a new mob.
- **No more "Partial Capture" in the open world.** Open-world zones (abyss, the overworld/starter maps, etc.) have no instance entry to "join mid-way", so a run there is no longer flagged as a partial capture. Instanced content is unchanged.
- **Drag-to-resize actually works.** The frameless overlay auto-fits its card, which defeated native edge-resizing; there is now a right-edge grip (shown when *Resize the overlay by dragging its edges* is enabled in Settings → Overlay layout) that resizes the overlay width and remembers it.
- **Overlay background defaults:** visibility now defaults to **100%** and darken to **20%** — but the background still shows nothing until you actually choose an image.
- **Wider saved-session review.** Opening a previous combat session from Combat Logs now uses the full window width (like the build/craft workspaces) instead of the narrower default column.

Security / code scanning:

- Cleared 6 more CodeQL alerts with real fixes: the 4 remaining `xss-through-dom` findings (the raid-planner imported-notes/owner-revision fields and the community metric column headers are now escaped or set as DOM text), plus the custom-decoder loader is constrained to the app's managed decoders folder (a localhost request can no longer execute an arbitrary `.py` by path) and the install-id path is canonicalized.

Roadmap:

- Added overlay **look presets** (colours + fonts + background + per-class bar colours, savable/shareable) under §8.

## Security hardening: code-scanning fixes (0.2.146)

Addressed the repository's CodeQL code-scanning findings, verified by running the same default query suite (remote threat model) locally. No user-facing behavior changes; these are security hardening and defensive validation.

- **Path traversal (path-injection):** added realpath + commonpath containment (`aion2calc/paths.within`) and single-segment name validation (`safe_component`), applied to session-log file access, bundled class/hit-profile loading, and static-file serving, so a request-controlled name can no longer escape its intended directory.
- **SSRF (upload management):** the request to manage a shared upload is now built from the server selected in Settings, never from the host carried in a (possibly imported) credential row, so a crafted ownership backup cannot redirect the request (e.g. to a cloud metadata endpoint).
- **HTTP response splitting:** `_send` now accepts only a well-formed MIME token for `Content-Type`, so a request-derived filename/URL suffix cannot inject CR/LF into a response header.
- **Incomplete HTML filtering:** the scraper's `<script>` stripping is now case-insensitive and tolerates whitespace/junk in the end tag.
- **Public site / app JavaScript:** download and release links from the GitHub API are accepted only when they are `http(s)` URLs; the share-server address is validated as an `http(s)` URL and the retired quick-tunnel host is matched by parsed hostname (not a substring); the interactive-map id is constrained to the known set; the publish link is validated before display.
- Added `tests/test_path_safety.py`.

Some findings are intentionally retained as documented, non-exploitable cases: localhost-only, user-initiated "point at my own local file/folder" features (loading a replay file, a custom decoder, or scanning a chosen game-install folder), and requests to the share server the user themselves configured. These cannot be constrained to a fixed allow-list without removing the feature, and are gated to `127.0.0.1`.

## Community health files, accessibility statement and dependency automation (0.2.145)

Repository/project documentation only — no app change.

- Added a **Code of Conduct** (Contributor Covenant 2.1), **Contributing guide**, **Security policy** (private vulnerability reporting via GitHub Security Advisories), and **issue/pull-request templates**, so the project meets GitHub's community-standards checklist.
- Added an **[accessibility statement](docs/accessibility.md)** describing the current state (semantic roles, ARIA labels and live regions, keyboard operation, adjustable overlay fonts/sizes/colours, system light/dark theming), known gaps (no formal audit, `prefers-reduced-motion`, some contrast/focus items, no skip-link), and how to send feedback — written honestly from the actual app/website and roadmap.
- Added a **Dependabot** configuration to keep Python dependencies and GitHub Actions up to date with weekly, grouped, rate-limited update PRs.
- README now links the new Community and Accessibility docs.
- Roadmap (§8): added raid-plan import into an in-app library that opens in the overlay, and auto-starting plan playback when a verified encounter begins.

## Live DPS interpolation, screenshot-lock, overlay FPS + asset-refresh reliability (0.2.144)

Three client-side overlay options, all **off by default** so the overlay is unchanged until you turn one on (Settings → Overlay layout):

- **Smoothly animate DPS numbers between updates** — between packets, each row's DPS eases toward the latest packet-backed value for a "live" feel, with a refresh-rate (ms) control (50–1000) so weaker machines can slow or disable it. The underlying numbers are still packet-sourced; only the on-screen tweening is interpolated.
- **Screenshot & lock** — a **Lock** button on the overlay freezes the display and pins the window in place (even if the game loses focus) so you can capture it cleanly; click again to resume.
- **Overlay FPS** — shows the overlay's *own* render frame rate ("Overlay N FPS"). The game's FPS cannot be read from packet capture, so this is deliberately the overlay's rate, not the game's.
- All three ride the settings backup/restore file.

Reliability:

- The scheduled **Refresh game asset references** workflow no longer aborts on a single transient network blip: the external item-detail/catalog downloads now retry transient failures (read timeouts, dropped connections, HTTP 429/5xx) with backoff, while validation and size limits still fail fast.

## Save-records toggle and overlay name display modes (0.2.143)

- **Save combat records** (Settings → Combat records, on by default): when off, the live meter no longer auto-writes each session to the logs folder. You can still Save/Export/Upload a session explicitly. Applies to the next capture.
- **Overlay name display** (Settings → Overlay layout): show **character names** (default), **class + party number** (e.g. "Sorcerer 2"), or **party number only** ("P2"). Party numbers are assigned stably (independent of damage order). Useful for streaming or when you'd rather not show names.
- Both ride the settings backup/restore file.

## Roadmap: Daily active meters (0.2.142)

- Documentation only — no app change. Added a roadmap item (§7) for a privacy-scoped "Daily active meters" community-size signal: an anonymous, per-install, date-rotating daily heartbeat the server counts into an aggregate-only daily tally, with no PII and an opt-out. To be designed and verified before any implementation.

## Overlay visual settings: colors, fonts, background, native behaviors, Party overlay (0.2.141)

The rest of the overlay visual-settings group. Everything is **off / inert by default**, so the overlay looks and behaves exactly as before until you turn a feature on.

- **Colors & fonts** (Settings → Overlay colors & fonts): color pickers for player-name and header text (added to the existing rate/total number colors); font family, size (80–160%) and weight; and a text **glow** toggle with its own color.
- **Background photo** (Settings → Overlay background): choose a PNG/JPEG (8 MB max) shown behind the overlay card, with Visibility, Zoom and Darken sliders. Set Visibility above 0 to show it. The image is stored locally and is *not* included in the settings backup (only the sliders are).
- **Native window behaviors** (apply when the overlay is reopened): resize the overlay by dragging its edges, snap to the game window's edges, and expand upward (anchor near the bottom of the game window).
- **Separate Party-DPS overlay**: a second always-on-top window showing raid totals (party DPS/HPS/damage-taken/total) instead of per-player rows, sharing the overlay's visual settings. Off by default; it opens alongside the meter overlay and closes with it.
- **Long-name scrolling**: long player names scroll on hover when enabled.
- Also moved the **Hide overlay** button next to **Open overlay** on the Live Meter page, and fixed a Settings row alignment issue (labels now top-align with their controls).

All colour/font/background/toggle settings apply to an open overlay within ~10 seconds (native-window options need a reopen) and ride the settings backup/restore file (except the background image itself).

## Overlay layout settings (0.2.140)

- First batch of the overlay visual-settings pass, under **Settings → Overlay layout**:
  - **Players shown** (1–24, default 8) — how many rows the overlay lists.
  - **Width** (260–800 px, default 340) and **row height** (14–48 px, default 22) — resize the card and row density.
  - **Auto-expand to show every captured player** (off by default) — raise past the limit when more players are in the fight.
  - **Show the meter only during combat** (off by default) — collapse the overlay to its header between pulls.
- All apply to an open overlay within ~10 seconds and ride the settings backup/restore file.
- Still to come in the visual group (they need native window work, best verified on a desktop): expand-upwards, snap-to-edge, drag-to-resize, per-element fonts/colors, background photo, glow effects, a separate Party-DPS overlay, and long-name scrolling.

## Combat power on the overlay (0.2.139)

- The overlay now shows **your combat power** beside your name ("You: Name · CP 48.2K") when the game reports it, read from the same recorded character info the saved log uses. Blank when not captured; on by default, toggle in **Settings → Live meter overlay**.

## Training-dummy parse readout (0.2.138)

- When you're hitting a **training dummy** (a Punching Bag / balance-test NPC), the live meter and overlay now show a dedicated **dummy parse** line: elapsed time vs the standard parse window, your DPS, and the party total to the dummy — with a ✓ once the window is reached. Detected from the dummy's catalog flag (`isDummy`); shown only on a dummy, never estimated.
- **Settings → Combat records:** a toggle (on by default) and a **parse window** value (default 60s, 5–3600) that defines the standard dummy-parse length. Both apply live and ride the settings backup/restore file.
- Completes the combat-records group alongside 0.2.136's reset-after-battle and record cap. (Save-combat-records on/off remains the one deferred item there, as it touches the autosave path.)

## Shining Mau Totem no longer shows as a boss on the logs page (0.2.137)

- The public logs viewer (and the in-app combat review) could still list the **Shining Mau Totem** — a miniboss — in the boss list and boss progression, because older logs (and logs classified by a server that predates the catalog fix) carry a stale `is_boss` flag baked in. The viewer now applies the same verified miniboss override client-side (`combat-review.js`): the totem is never marked "(boss)", never appears in the Remaining-boss-HP table or the boss-HP graph line, and is filtered out of the boss-attempt progression and attempts tables — regardless of what a stale log or server said.
- Newly saved logs were already correct at the source (the client bakes `is_boss` from `npc_info`, which carries the 0.2.132 override); this release fixes the display for logs recorded or classified before that. Covered by `tests/test_boss_display.py`.

## Combat-records settings: reset-after-battle and record cap (0.2.136)

- **Clear the live meter after a battle ends** (on by default): once combat has been idle past a **reset delay** (default 5s, 1–120), the live meter and overlay clear to a "Ready — waiting for the next fight" state instead of leaving the last pull pinned. **Settings → Combat records.**
- **Keep up to N past combats** (default 20, 1–500): caps how many finished encounters the segment list retains.
- The recorded data is never discarded by these — a cleared battle's details stay available in the segment list (and in the whole-session view) until replaced. Changes apply live to a running meter and carry in the settings backup/restore file.
- Still to come in this group: save-combat-records on/off and the training-dummy record-time tracking.

## Overlay target HP, time-to-kill, and death indicator (0.2.135)

- **Current target remaining HP** on the overlay (opt-in): shows the target's HP % and current/max when the game reports it — e.g. "Target Boss 42% (420K/1.0M)". Off by default (respecting the earlier overlay-HP preference); enable in **Settings → Live meter overlay**. Shown only when real HP was captured; never estimated.
- **Time-to-kill (TTK)** for the current target (opt-in, off by default): the target's remaining HP ÷ the party's current DPS to it. Blank unless HP was observed, so it is never a guess.
- **Party-member death indicator** (on by default): a player who has died shows a DEAD badge and dims until a later HP>0 sample revives the row, tracked live from recorded death/HP telemetry.
- All three are packet-sourced and ride the settings backup/restore added in 0.2.134.

## Overlay combat info and settings backup (0.2.134)

- **Your contribution on the overlay.** The meter now shows your share of the current encounter's damage — "Your contribution: 42% · 1.2M (18.3K/s)" — computed from the same recorded damage as the player table, not invented. On by default; toggle in **Settings → Live meter overlay**.
- **Current target with per-player DPS.** The overlay shows the enemy you're hitting most and each contributor's DPS to it, so you can see who's actually on the priority target. The target is inferred from your own recorded damage; shown only for enemies (never party members). Toggle in Settings.
- **Settings backup / restore.** **Settings → Settings backup** exports all overlay and app settings to a JSON file you can keep or share, and imports one back. Import validates every field and ignores unknown or tampered keys, so a hand-edited or foreign file can't inject arbitrary state.
- Every new number stays packet-sourced; nothing is estimated or invented.

## Live meter run segmentation, overlay lifecycle, and collapse-to-tray (0.2.133)

- **Multiple runs are no longer collapsed into one "partial" instance.** The decoder reports a stale map id across some zone loads (it stayed on the dungeon id even after a teleport out), so run segmentation — which keyed on the map/instance value changing — never fired, and every re-entry piled into one run. The live view then merged them all and showed every player seen across the session (e.g. **17 "players" in one instance**), with every run flagged partial. Segmentation now keys on the reliable signal a real capture carries: **a genuine zone load (instance re-entry, teleport, revive into a new instance) reassigns your own actor id**, while an in-instance phase teleport keeps it. Replaying a real multi-run diagnostic: one run that the capture joined mid-pull (correctly partial) plus three fully-observed re-entries, each its own run with its own party — not one 17-player blob. An in-instance mechanic phase that only pauses DPS still stays one continuing run, so the live meter does not reset mid-fight.
- **Partial capture now reflects reality.** A run whose instance entry we actually witnessed (a zone load during capture) is no longer flagged partial; only a run the capture joined already in progress is. "All runs say partial even when started from the beginning" is fixed.
- **Overlay lifecycle.** The transparent overlay now closes when you Stop the meter, and it self-closes when the app goes away — window closed, quit, or killed — via a lightweight parent-liveness check, so a stale meter can no longer stay pinned on top after the app is gone.
- **Re-acquired identity on the overlay.** After a tele/port/revive/instance change your actor id is reassigned; the overlay now shows a "You: <name>" confirmation that reappears once your identity is picked back up.
- **Collapse to the system tray (Windows, macOS, Linux).** New **Settings → Collapse to tray**: when enabled, closing the window keeps the app, meter and overlay running behind a tray icon with Open and Quit. Off by default; needs no extra install (pystray is bundled) and degrades to the normal "closing the window stops the app" behaviour where no tray backend is available.

## Shining Mau Totem is a miniboss, and a verified NPC-role override layer (0.2.132)

- Shining Mau Totem was being treated as an encounter boss; it is a miniboss and no longer headlines a fight as the boss. Added a verified local NPC-role override layer (`meter/a2parser/data/npc_role_overrides.json`, applied in `npc_info`) so corrections to the upstream catalog's boss/role flags survive a catalog refresh, and recording the intended major/miniboss/world-boss role that the catalog itself does not yet carry.
- Captured a large live-meter & overlay quality-of-life workstream in the roadmap (`docs/COMBAT_ROADMAP.md` §8): the reported capture/overlay bugs with their root causes (several need a current-build diagnostic capture to fix without guessing), plus the full visual/settings/combat-info/notifications/backup vision and a long-term RivaTuner Statistics Server item. No behavior change from the roadmap entry itself.

## Manual install path and Live Meter as the first tab (0.2.131)

- Add a game install folder by hand when auto-detection misses your copy: **Settings → Add install folder manually** (or `install-version --add-path "<folder>"`). The folder is accepted only when it actually looks like an AION 2 install (it contains `AION2.exe` or the shipped `Content\Paks`), then it is stored, selected and behaves exactly like a detected install for capture and version signals; remove it with the same control or `--remove-path`. This covers PURPLE and any other copy whose Windows registration is missing.
- **Live Meter is now the first tab** and the app's landing page, so recording combat is one step away on launch. The other tabs are unchanged, just reordered after it.

## PURPLE launcher version detection (0.2.130)

- `install-version` now reads the NCSOFT (PURPLE) launcher's own run record for AION 2 Global (`%LOCALAPPDATA%\NCSOFT\NccrData\com.ncsoft.aion2global\*.execution.json`) and reports the game version and build it logged (`appVersion` 2.0.6, `appBuildNumber`). This confirms a PURPLE AION 2 Global install and cross-checks its version independently of the launcher-stamped executable ProductVersion — and still surfaces the version even when the game's install folder was not located automatically (the Windows uninstall entry is the only machine-readable path source found on a real install; the launcher breadcrumb carries the version but no path). Only the two version fields are read; the account ids in the sibling `extra.json` are never touched. Verified against a real PURPLE install.

## Pantheon deity names and a ground-truth Genus/Pantheon capture (0.2.129)

- Character import now labels each Pantheon deity with its proper name (Justice → Nezekan, Time → Siel, Illusion → Kaisinel, …), transcribed from the in-game Pantheon screen — the official API carries only the effect-category totals. "Destruction" was not on the observed board, so its deity name is left unrecorded rather than guessed.
- Added the first ground-truth capture of the in-game Genus Insight and Pantheon (`data/global/genus_pantheon_observed.json`): one character's five genus levels and Analysis Effect lines, the nine Pantheon deities' display values, and 15/94 collection progress, with full provenance. It confirms the five modelled genera and the level-to-10 progression, and shows re-analysis cost scales with genus level (so the modelled flat analysis cost is a base figure). It is a reference to validate the model against — character-specific, not a per-level rule, and not fed into the damage model.

## Cross-launcher install comparison reports content overlap (0.2.128)

- `install-version` now quantifies how much two installs' shipped content actually overlaps instead of a bare match/differ on the fingerprint digest. Measured against a real Steam and PURPLE install of nominally the same game: 743 of 758 packages were byte-identical, 15 content chunks were drifted a small amount (same names, slightly different sizes), and none were added or removed — the signature of the same content base at a different patch/hotfix tick, not a launcher-specific repackaging and not two different games. The comparator (`compare_installs`) now reports identical / drifted / only-some package counts and the identical fraction, names a sample of the drifted packages, and keeps *not* claiming a shared launcher-independent version key when the fingerprints differ. Finding: neither the executable ProductVersion nor the raw content set aligns exactly across launchers, because installs drift by patch revision independently — so the content fingerprint stays a diagnostic signal, never an authoritative cross-launcher key.

## Launcher-independent content fingerprint (0.2.127)

- The installed-content fingerprint now keys on each package's **file name only**, not its folder path. The launchers nest the content differently — PURPLE under `Aion2/Content/Paks`, Steam with `Content/Paks` at the install root — so including the parent path made identical game content hash differently across launchers, defeating the fingerprint's whole purpose as a store-independent version signal. Verified against a real Steam install's package listing (the recursive sweep there also surfaced Chromium-webview `.pak` resources outside `Content/Paks`, which the non-recursive scan already excludes). Whether a given Steam and PURPLE install of the same patch share one fingerprint is confirmed per install; the comparator reports agreement or the specific difference rather than assuming it.

## npc-evidence reads a folder of logs too (0.2.126)

- `aion2calc npc-evidence` now accepts a folder of a2log files, not only individual files, matching how `defeats` already works — point either at a directory to analyze your whole local corpus offline. Both commands now share one loader that skips a missing or malformed file with a note instead of failing the run, so one bad capture never loses the rest. No change to the server path or to the evidence aggregation.

## Defeat dedup also separates balance patches (0.2.125)

- `aion2calc defeats` no longer folds together two clears of the same boss recorded on **different game patches** — a kill under one balance patch and a kill under a later one are different balance contexts, so merging them misrepresented clear history across a patch boundary. Grouping now reads `game_patch` too (from the a2log segment locally and the server's per-segment `contexts` for uploads), on the same footing as difficulty and recorded instance: when the field is absent on one side it is not used as a separator, so nothing that matched before stops matching except a real patch disagreement. Group records carry `game_patch`.

## Defeat dedup respects difficulty and recorded instance (0.2.124)

- `aion2calc defeats` no longer merges two clears of the same boss that were recorded at different difficulties (e.g. a normal run and a nightmare run) or in distinct recorded instances — they are genuinely different defeats, and folding them together under-counted clears. Grouping now also reads `difficulty` and `instance_id`, from the a2log segment locally and from the server's per-segment `contexts` block for uploads; when a field is absent on one side it is simply not used as a separator, so nothing that matched before stops matching except a real difficulty/instance disagreement. The text output gains a difficulty column.

## Dedupe boss defeats from your own saved logs (0.2.123)

- `aion2calc defeats` now accepts local a2log files or folders of them, not only the community server: point it at your own saved `.a2log.json` corpus to collapse the same boss kill recorded from several party members' perspectives into one defeat, so offline respawn/availability and clear counts are not inflated by duplicate uploads. Each saved fight segment becomes one perspective; grouping still uses boss, region, shared party identities and matching duration, and never merges non-overlapping rosters. No change to the server path or the dedupe heuristic.
- Fix a latent `UnboundLocalError` in the CLI: a redundant function-local `Path` import in the `render` branch shadowed the module import, so subcommands that build a filesystem path (e.g. `render`, `character --export`, local-file `npc-evidence`) could crash. The module import is now used throughout.

## Release pipeline guard (0.2.122)

- Run the release CI's lint (`pyflakes`) inside the test suite so a lint error that would block the release job is caught by a normal `pytest` run, not only after a merge. A stray f-string had blocked 0.2.121 from being cut until it was fixed; this prevents that class of regression recurring. No behavior change to the app.

## Live meter stays through DPS-stop mechanics (0.2.121)

- Keep the live meter and overlay from resetting when a mechanic stops your DPS. A mid-fight self zone-transition (a teleport or phase) no longer blanks the latest view: the continuing run's segments are re-joined and each player's totals carry across the pause. A genuinely separate pull (a real combat gap or a new run/instance) still starts its own encounter, and explicit segment, whole-session and saved-log views are unchanged.
- Keep live capture running across an instance/zone transition: a transient error handling one capture packet during the transition is recorded in diagnostics instead of stopping the meter.
- Record a launcher-independent shipped-content fingerprint alongside the executable Product version, and add `aion2calc install-version`, `calibrate`, `npc-evidence`, `defeats` and `doctor` helper commands (see the docs). Record Pantheon deity stat effects from the official profile.

## Automatic encounter catalog context (0.2.95)

- Resolve missing PvE category and difficulty using exact recorded instance/map IDs and explicit NPC catalog category/tier fields. Unique recorded NPC instance matches can suggest a zone when entry metadata is missing, without filling the recorded instance ID or proving entry.
- Recompute bounded context evidence on import and upload; preserve manual post-capture corrections. Conflicting map/instance/NPC evidence and suggestions without a recorded instance keep samples unranked. Unknown IDs, multiple tiers and missing data remain visible.
- Add an Automatic encounter context panel shared by desktop, Pages and the server viewer, with recorded IDs, catalog candidates, category/tier records and conflicts. Include this evidence in mapping reports and live diagnostics.
- Re-audit all 14 localized upstream NPC/dungeon tables at commit 4cc5a513531fb6910f23dc3a7d250fa440125934: no added, removed or changed records. Catalog applicability to individual installed builds and missing NPC portraits remain unverified.

## Connected recording review (0.2.94)

- Review 2–32 connected stopped recording parts together on desktop and in shared Pages/server review, with mode-specific recording totals, source encounters, provenance and export/back controls.
- Require consistent recording IDs/scopes, unique parts/tokens, exact predecessor ranges and ordered non-overlapping encounter timestamps. Reject ambiguous, missing, active, incompatible or oversized chains without changing source files.
- Join player totals only by recorded region/server/database character identity; preserve unresolved actors separately and namespace entity/run references by part. Keep source encounter/run boundaries and original entry/completion evidence.
- Retain stable run tokens, origin record sequences and observed entry/final-boss evidence in new captures. Show combined run timing only when the selected chain contains consistent origin/entry and corroborating configured boss-death evidence; older captures remain unavailable.
- Combined reviews remain unranked, excluded from contribution and blocked from server upload. Source parts retain their own rankings/profiles; no completion or eligibility is inherited.
- Fix oversized graph legend SVGs that caused large blank areas above the plot on desktop and Pages.

## Zone actor identity and pet ownership (0.2.93)

- Reset zone-scoped player IDs, names, roster, NPC state and pet ownership at an observed idle zone transition before decoding the new zone's identities. Preserve earlier encounters in session history.
- Resolve name-based pet owner fields only when one current actor matches. Explicit owner IDs remain supported; ambiguous names are not merged.
- Prevent old player IDs from attracting pets in a later dungeon and appearing as extra team-member rows. Previously saved logs are not rewritten.

## Overlay metric rows (0.2.92)

- Hide overlay rows with zero recorded amount in the selected DPS, HPS or D.Taken metric. Retain their effects in other tabs and saved logs.
- Show actor IDs below repeated names and explain that their identity/ownership is unresolved. Do not merge different actors solely by matching names.
- Show an explicit empty-metric message when combat exists but the selected metric has no recorded effects.

## Recording-part continuity metadata (0.2.91)

- Default overlay rate and total/share numbers to black. Add separate saved color pickers in Settings, shared by DPS/HPS/D.Taken, with a reset button and automatic overlay refresh.

- Record retained decoded-effect ranges, capture/identity contexts and predecessor tokens for new archive parts. Preserve metadata through imports/uploads.
- Show continuity details in recording-part navigation: gaps, overlaps, duplicate parts, changed contexts, unavailable predecessors and connecting submitted ranges.
- Compare all available local parts before paging. Server comparisons use public available parts only, including predecessor checks across pages.
- Counters and tokens are submitted metadata, not verified packet continuity. Parts stay separate; no totals, run completion or ranking eligibility are inherited. Older logs remain unavailable rather than receiving invented ranges.

## Overlay metrics and partial-capture links (0.2.90)

- Add persistent DPS, HPS and D.Taken overlay buttons below Meter/Plan/Hide, with metric-specific sorting, rate, total and share.
- Use recorded encounter spans for healing/incoming rates while retaining the active outgoing DPS clock. Healing alone does not start an encounter.
- Decode explicit summon-owner links in compressed inner packets, improving pet grouping when these records arrive during a partial capture.
- Show Self identity, unnamed actor and linked-pet status in Live Meter and the overlay. Missing identity/ownership packets remain unresolved; diagnostics are still needed to identify unsupported variants.
- Reuse roster/ownership membership sets within each locked snapshot/export to reduce refresh contention in long partial captures; rebuild them for every read.
- Hide the Windows overlay when no supported game window is found or another app has focus; style/opacity initialization failures no longer disable foreground tracking.
- Split the next pull after an observed boss wipe: complete unchanged identified party, all recorded deaths, positive boss HP and two seconds without incoming/outgoing damage. Preserve prior metrics; uncertain/partial death evidence retains normal split rules.

## Recording-part navigation (0.2.89)

- Add **Other parts of this recording** to saved desktop logs and shared desktop/Pages review, with paged results and direct part opening.
- Show part numbers, titles, recorded spans, encounter counts and saved/checkpoint state; preserve the PvE/PvP filter while navigating.
- Shared discovery lists public available uploads only. Private view tokens stay with the current log and are not forwarded to siblings.
- Parts keep separate totals and quality. Matching archive IDs are unverified metadata; gaps/duplicates do not establish a complete run.

## Capture shutdown retention (0.2.88)

- Stop drains queued game payloads for up to five seconds before final saving, rather than immediately discarding them. An executing decoder call cannot be forcibly interrupted.
- Show stopping progress, decoder failures, shutdown discards and successfully drained payload counts in diagnostics and reviewed logs. Successful drains do not count as capture loss; actual errors/discards still do.
- Serialize capture Start/Stop/Clear and block replacement while an old worker or adapter is still stopping. Long diagnostic ZIP compression can take additional time.
- Preserve the legacy combined error/discard counter for compatibility. Older logs cannot separate its causes or recover lost data.

## Encounter clocks and review clarity (0.2.87)

- Automatic inactivity splits wait at least 120 seconds without outgoing player damage. Map/mode changes and manual splits remain explicit boundaries.
- All players share a one-second active damage clock; empty outgoing-damage buckets are excluded. Incoming hits, healing, idle time and deaths do not extend or reset DPS; surviving players continuing to damage increase the shared denominator.
- Add a graph key for total rate bars, trailing 10-second average, player-series line styles and boss HP on the right axis.
- Scope character buttons to the selected encounter timeframe when a specific run is selected. All runs retains the upload-wide character list; plotted events already use the selected encounter.
- Defer soft archive rollover during active combat; hard retention limits still produce labeled incomplete parts. Soft segment limits follow the selected player scope.
- Explain that an archive continuation may lack entry evidence recorded in an earlier part, independently of raw TCP diagnostic recording. The reported public log was Part 3 with a storage boundary and 43 capture-error/discard counts; earlier evidence cannot be reconstructed from that part alone.

## Partial mid-dungeon metrics (0.2.86)

- Default live view automatically shows observed players when local identity is missing, including numbered unnamed actors; nearby players may be included. Self and party membership are never guessed.
- Show partial-capture status in the app and overlay; retained metrics and saved/uploaded log review remain available. Strict Self and Party filters remain selectable.
- Persist partial evidence and keep runs without observed entry or player membership unranked. Updated server processing excludes these samples from community learning.
- Importing partial a2log metrics for local analysis preserves their exclusion from personal optimizer calibration.
- TCP recording remains optional for live decoding; it cannot reconstruct packets sent before capture started.

# Aion 2 Calc 0.2.85

- Fixed Party filtering for captures started mid-instance: earlier retained effects can be matched to the first roster observed later in the same identity context. Later roster changes do not rewrite that initial roster.
- App and overlay show the same recovered Party readings and explain late roster evidence. Self still requires an observed identity or an exact name override; unnamed actors are not assigned to you.
- Late-roster encounters remain reviewable but unranked, and do not establish a complete earlier party roster. Saved logs preserve this evidence.
- Corrected the empty-meter message when effects were decoded but the selected identity/party view cannot yet show them.

# Aion 2 Calc 0.2.84

- Corrected live capture diagnostics that excluded enemies without recorded NPC types before counting missing identities. Identified players and owned pets remain excluded from NPC coverage.
- Reviewed logs and mapping exports now list bounded session actor references with missing NPC types and their recorded effect counts, separately from unmapped catalog IDs. Desktop and Pages show both totals.
- Actor references do not establish a reusable NPC ID, name or boss role. Existing logs need to be reopened locally or reprocessed by an updated server to populate the new detail fields.

# Aion 2 Calc 0.2.83

- Desktop and GitHub Pages community combat logs now include a collapsible PvE **Recorded boss defeats** feed, with local boss/NPC search, build/region filtering, recorded defeat times, roster engagement and source-log links.
- Loads on expansion, supports explicit refresh and rejects stale responses after filter or mode changes. Older/unavailable servers show a retry message without blocking other combat-log views.
- Observations do not establish current availability, verified unique kills or timed-boss roles. Respawn times and physical server/channel remain unknown pending verified evidence. Requires a community server with the boss observation feed.

# Aion 2 Calc 0.2.82

- Fixed premature live-meter archive splits caused by unrelated nearby combat. The storage encounter counter now follows Self, Party and All-player relevance separately, preserving the existing archive size limits.
- Investigated a supplied capture that produced 12 premature parts despite only a few visible encounters. Raw TCP recording remains optional; it does not control combat decoding.

# Aion 2 Calc 0.2.81

- Capture diagnostics now auto-save a metadata ZIP on Stop even when raw TCP recording is unchecked. Added a readable summary, ZIP size/counter feedback and **Open diagnostics folder** so metadata-only exports are easy to locate. Raw payloads remain intentionally absent when not recorded.

- Added optional **Reserve cooldown in rotation** for linked outgoing tactical windows. An entered cooldown keeps matching modeled skill IDs and explicit cooldown groups available before the assumed use, then excludes them for the entered cooldown afterward.
- Saved current/optimized results and Markdown identify matched actions/groups and report unavailable kit matches. Conflicting assumed uses within an explicit shared group are rejected.
- Existing schedules keep their previous behavior unless enabled. Tactical MP, damage, shields, CC success, charges and unrecorded shared cooldown groups remain unmodeled; fixed exclusions do not benefit from reset hooks.

# Aion 2 Calc 0.2.80

- Outgoing action-time assumptions can now retain an active skill or stigma, its trained minimum and an optional supporting effect. Links merge with other personal reserves without dropping stricter requirements.
- Optional effective-cooldown assumptions check reuse separately for each outgoing damage scenario. Saved advice and Markdown show linked requirements, clipped scenario use times and unknown or satisfied reuse status.
- Timing remains user-entered: actual tactical casts, MP/cooldown consumption, offensive-rotation reuse, CC success and shared cooldown groups are not simulated. Empty schedules preserve the existing damage model.

# Aion 2 Calc 0.2.79

- Personal PvE/PvP optimization now accepts explicit outgoing action-time windows for defense or movement. Candidate scoring, rotations, stat weights and the current-character comparison share the entered schedule.
- Scheduled hits, DoTs and pets continue during pauses; cooldown recovery and regeneration continue. Overlapping pauses count once and each scenario clips the schedule to its duration.
- Saved advice, exports and reconstructed reports retain the timing assumptions and clipped totals. Community references remain unpaused. Actual defensive casts, tactical MP/cooldowns and CC success are not inferred.

# Aion 2 Calc 0.2.78

- Missing-image reports now include validated displayed asset references where available: region-scoped official IDs, catalog item slugs and skill IDs remain separate.
- Added **Export image failures** to desktop/Pages log and character-build views, with download feedback.
- Reports expose retention/truncation limits and omit full URLs, portraits, character names, stats and credentials. This identifies failures for investigation; it does not create trusted mappings or retrieve missing artwork.

# Aion 2 Calc 0.2.77

- Added a pinned encounter-catalog refresh command that stages NPC/dungeon tables with schema checks, hashes and an ID-change audit for release review.
- New mapping coverage includes the community source commit and check date on desktop and Pages. Game-build applicability remains explicitly unestablished.
- Audited all 14 localized tables: the existing 9,780 NPC IDs and 58 dungeon IDs match the checked upstream snapshot. No new mappings or portraits are claimed.

# Aion 2 Calc 0.2.76

- Settings now offers **Re-index cached icons**, with progress and a completion summary, to recover official item, skill, pet, wing, title and board references from previously imported profiles.
- Re-indexing uses original import times, preserves newer references and flags conflicting icons rather than using an ambiguous fallback. Saved builds and historical logs are retained.
- Image coverage exports include the last re-index summary. Re-indexing does not fetch new profiles, validate remote image availability or add NPC/boss mappings.

# Aion 2 Calc 0.2.75

Yellow information and warning panels now have a consistent small vertical margin (3px, approximately 2pt), including adjacent panels and panels directly below overview metrics. The shared stylesheet covers desktop views and GitHub Pages: optimizer summaries, HP/skill reserves, combat-log notices, diagnostics, uploads and expandable information panels. Explicit larger view spacing remains in effect.

Pet Genus Insight results now show five genus selectors, a nine-slot ring and a full analysis list. The manual editor also shows the ring. Missing snapshot levels and lines are explicitly not recorded, rather than looking like an empty successful import; links explain where to save actual in-game allocations and recalculate. The official profile currently supplies equipped pet details, not Insight allocations. Ring colors represent recording status, not inferred rarity or grades.

Gear & Advice now shows sticky progress beside its controls, with actual job stages, an indeterminate progress bar and elapsed time. Completed jobs show a scroll-down prompt and View results button. Duplicate starts are disabled, and returning to the page retains the current job's feedback and completed result. Missing saved Genus levels in advice are labeled not recorded rather than Lv 0; possible recommended lines remain separate from owned rolls.

This extends the earlier expandable-menu spacing to the bordered notice panels themselves. Common scoring and capture behavior are unchanged.

# Aion 2 Calc 0.2.74

Live Meter no longer offers session-wide encounter type, build, difficulty, zone or region overrides, and ignores their legacy browser settings. Capture uses automatic evidence; unidentified metadata remains unknown. The live configuration API rejects classification changes.

Completed saved logs support corrections to one encounter or every encounter with the same recorded run ID. Only changed fields propagate; boss name stays encounter-specific and region stays session-wide. Active captures have no correction form. Saved corrections do not rewrite an already uploaded copy.

Character build headers now show gear score from the official profile's gearScore or item-level stat, alongside combat power. The Korean item-level label is translated. Secondary-stat effects supplied as text now render correctly instead of showing “: Unavailable”; empty entries are hidden. The shared viewer applies to desktop and Pages. Common scoring is unchanged; no server update is required.

# Aion 2 Calc 0.2.73

Personal PvE and PvP pressure windows now accept an optional assumed effective cooldown for their linked skill. Repeated activations within each scenario must respect the largest supplied cooldown for that skill. Blank stays unknown, zero permits immediate reuse, and entries at the same start count as one activation. Separate encounter scenarios are checked independently with all skills initially ready.

Saved Results and Markdown show activation starts, shortest reuse gaps and whether spacing satisfies the entered assumption. Changing a linked skill clears its previous cooldown input. Charges, resets, shared groups and outgoing action-time costs remain unmodeled; no catalog cooldown or tactical success is inferred. Review effective cooldown assumptions when gear or cooldown reduction changes.

Common scoring is unchanged; no server update is required. Action-time integration and asset/catalog re-indexing remain pending.

# Aion 2 Calc 0.2.72

Personal pressure-reduction windows can now link a class skill, its minimum trained level and an optional active-skill supporting effect. The optimizer automatically unions those requirements with personal reserves, preserves stricter minimums, keeps linked stigmas equipped and enforces supporting-effect unlocks through trained points, fixed bonuses and connected Daevanion nodes. Requests that exceed effect slots or point budgets fail explicitly.

Saved Results and Markdown show the linked requirements. All links apply, including zero-duration windows; unlinked windows remain manual assumptions. Links retain allocations, not casts: timing, reduction percentages, immunity, cooldowns, tactical success and outgoing damage costs are still user assumptions or unmodeled.

Common scoring is unchanged; no server update is required. Cooldown and opportunity-cost modeling remain next.

# Aion 2 Calc 0.2.71

Personal PvE and PvP survivability scenarios now support timed pressure-reduction assumptions for defense, control or movement. Enter up to eight windows per scenario. The optimizer checks peak ongoing pressure across their boundaries and the healing schedule, uses only the strongest overlapping reduction, and keeps the initial hit unchanged.

Saved Results and Markdown retain timings and compare required HP with the same healing but no added reductions. These are explicit manual assumptions; skill casts, cooldowns, immunity, tactical success and outgoing damage costs are not simulated. Skill/supporting-effect reserves remain separate. Add a no-reduction scenario to constrain the build for failed execution.

Common community scoring is unchanged; no server update is needed. Verified skill coefficients and full opponent matchup scoring remain future work.

# Aion 2 Calc 0.2.70

Overlay refresh failures now show the HTTP/response/timeout reason, last successful refresh age and a Retry button. Last readings remain visible with capture status explicitly unknown. Overlay polling skips auxiliary catalog and installation work. Status requests return a clear busy error after a bounded wait for the decoder lock. Run and identity metadata are captured together to avoid reading them across a session replacement.

Diagnostics export no longer calls the combat display snapshot. It can export counters, recorded status failures and opted-in TCP payloads even if graph aggregation fails; a busy decoder produces explicitly best-effort metadata. Cached display context includes its timestamp, and the no-payload message explains that counters remain useful without TCP recording.

This improves recovery and evidence collection for the reported connection warning; the original failure has not yet been reproduced. Optimizer CC, mobility and defensive timing work remains next. No server update or community evaluator change is required.

# Aion 2 Calc 0.2.69

Supporting-effect reserves now allow unlocks that depend on Daevanion levels. The optimizer jointly allocates trained points and connected board nodes while respecting skill, Daevanion and HP reserves. It requires a feasible allocation before damage search, preserves effective-level floors during point polishing, and validates the final effects. Requests that cannot be satisfied within the budgets and solver time limit fail explicitly.

Saved results and Markdown show each required effective level and its trained, Daevanion and fixed-bonus contributions. Utility effects remain user-selected constraints; tactical CC, mobility, shields and matchup simulation are still future work. Common community scoring is unchanged; no server update is needed.

# Aion 2 Calc 0.2.68

Personal skill reserves now support specific supporting effects on active skills. The optimizer retains selected effects while searching the remaining damage choices. Minimum trained levels automatically cover effect unlocks and selection-slot gates using fixed gear bonuses, with the same skill-point budget. Saved results and Markdown list the retained effects.

Effects that require changeable Daevanion levels beyond the guaranteed trained-plus-gear floor are rejected in this first version. Stigma effects remain automatic. Utility effects are preserved by user choice, not ranked by inferred defensive, CC or mobility coefficients. Canonical community scoring is unchanged; no server evaluator update is required.

# Aion 2 Calc 0.2.67

Personal survival settings can import an exported optimized PvP result as an opponent pressure benchmark. Choose sustained or burst-average modeled DPS, explicitly enter an incoming scale, and choose the pressure window. Saved results and Markdown retain the original result label, class, score, duration, model note and scale alongside editable assumptions.

This reuses a saved damage estimate; it does not simulate a duel, infer mitigation against your gear, refresh an opponent profile or reconstruct peak burst from average DPS. Legacy durations are labeled when absent from the source objective. PvE/advice results are rejected. Up to eight pressure scenarios share the existing strictest HP reserve constraint. CC, mobility and defensive-ability interactions remain pending. Canonical scoring is unchanged; no server evaluator update is required.

# Aion 2 Calc 0.2.66

Personal survivability pressure scenarios now support healing delay and duration. This covers assumptions such as a healer reacting late or healing ending before incoming pressure stops. The HP constraint uses the largest ongoing damage deficit, never banks excess healing, and preserves the initial burst as a separate requirement. Default zero delay and blank duration retain the previous constant-healing behavior; zero duration disables healing in that scenario.

Results, recovered views and Markdown show the timing assumptions and peak pressure deficit. Timings remain user assumptions; this does not simulate defensive abilities, crowd control, movement, armor changes or optimized opponent builds. Imported gross damage windows still start with zero healing and sustained pressure. Live Meter now shows capture-stage counters and diagnostics retain scope, roster/identity availability and filter visibility even when raw TCP recording is off. The raw-recording checkbox is explicitly labeled optional; the reported checkbox-dependent capture failure has not been reproduced or confirmed. Canonical community scoring is unchanged; no server evaluator update is required.

# Aion 2 Calc 0.2.65

Survivability settings can import a recorded incoming-damage scenario from an exported a2log JSON file. Choose the encounter, player recipient and rolling time window. The largest recorded gross damage window becomes a burst requirement, with zero additional sustained damage or healing to avoid counting the same pressure twice. Recorded deaths reset the window so observed separate lives are not combined. Review your maximum HP and positive reserve before optimizing.

Saved results retain the recording label, recipient, peak window, largest hit and event count alongside editable assumptions. These are user-imported observations, not authenticated telemetry or a matchup simulation. Damage reflects the recorded recipient's defenses; packet loss can understate pressure. Crowd control, mobility, armor changes and opponent-build simulation remain future work. Expandable information headings and contents have a small consistent spacing gap in the desktop app and Pages. Live Meter now shows capture-stage counters and diagnostics retain scope, roster/identity availability and filter visibility even when raw TCP recording is off. The raw-recording checkbox is explicitly labeled optional; the reported checkbox-dependent capture failure has not been reproduced or confirmed. Canonical community scoring is unchanged; no server evaluator update is required.

# Aion 2 Calc 0.2.64

My Character offers a saved damage-objective choice: the existing primary scenario or balanced 50/50 PvE boss/dummy or PvP sustained/burst scoring. Balanced personal optimization uses the frozen imported gear, saved Genus lines, point totals and the same HP/skill reserves across both scenarios. The existing primary objective remains the default; balanced simulations take longer.

Current-build specialty/rotation evaluation uses the selected objective too. Results, Saved Results, Markdown and build differences retain objective weights, component DPS and combined score. The reported gain compares matching objectives, while each scenario's DPS remains separately available. Skill shares, opener, macro and sensitivity remain primary-scenario views; a higher combined score may trade away primary damage. Board proposals remain approximate, accepted against full weighted scoring. No global optimum or competitive PvP efficacy is claimed.

This personal-search option does not change the canonical common-loadout scoring model or require a server evaluator update. PvP crowd control, mobility, opponent builds and full survivability modeling remain future work; the current HP and trained-skill constraints still apply.

# Aion 2 Calc 0.2.63

Automatic storage rollover no longer treats an unidentified/filtered-out session as a decoder failure. When the selected Self/Party filter cannot form a report, capture continues and rollover retries after five seconds, preserving the bounded current session. Live Meter shows a deferred-archive warning. Identity and party filtering remain enforced; unknown nearby players are not silently included. If identity remains unresolved, ordinary retention limits and loss counters still apply. Actual decoder failures and failed disk saves remain errors.

The common-comparison evaluator keeps model revision 0.2.62 for this capture-only fix, so clients remain compatible with a server using that released model. Application versions and scoring-model revisions are now separate.

# Aion 2 Calc 0.2.62

Community comparison contributions now refine the combined PvE or experimental PvP objective directly. Two independent scenario searches seed a weighted refinement of specialties, skill points, stigmas, crystal-board allocation and priority. Every comparison uses the full configured scenario durations and existing equal weights. The best independently evaluated seed remains eligible, so a weaker refinement is not published as the winner.

Board allocation still uses approximate separable curves and finite-difference stat weights; full weighted evaluation accepts or rejects the proposed allocation. This remains a local search, not proof of a global optimum. Cached contributions record the search revision and selection scores. The extra refinement increases calculation time and reports its progress.

This checkpoint changes anonymous common-loadout contribution searches. Personal-build optimization, HP/skill reserves and fixed Genus inputs retain their existing behavior. PvP is still a stationary damage proxy without competitive crowd-control, movement, opponent survival or win-rate modeling. Servers must use the matching model release before accepting its scope.

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
