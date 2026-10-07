# Methodology, sources and assumptions

## Capture driver evidence (0.2.37)

Live Meter capture diagnostics and shared combat-review quality panels show received packets, capture-buffer drops and interface/driver drops when the active Npcap/libpcap backend provides statistics. Unsupported backends are labeled unavailable; partial adapter coverage is labeled. Counters are retained in saved/exported logs and diagnostic ZIPs, including the final sample after capture stops and cumulative evidence across capture restarts in a retained session.

A positive reported drop counter conservatively makes the recording unranked. It does not identify which game effects were lost: counters cover the capture handle and may include other traffic. Zero does not prove loss-free capture, and missing counters are not zero. These counts must not be added to TCP discards to estimate unique lost game packets. Native capture backends without a libpcap handle remain usable, with driver statistics unavailable. Other capture-quality rules remain in effect; driver support alone neither grants eligibility nor blocks older logs.

Statistics are sampled before capture, in that adapter's packet callback and after its thread exits. Optional statistics failures do not interrupt packet decoding. See the [libpcap counter documentation](https://www.tcpdump.org/manpages/pcap_stats.3pcap.html) for platform-specific meanings and availability.

The pet review filter now follows a selected pet to its owner when enabling **Combine pets with owner**, instead of leaving a selection that disappears from grouped rows.


## Encounter catalog coverage (0.2.36)

Live Meter fills difficulty only when the recorded PvE instance ID has an explicit difficulty in the bundled dungeon table. It does not infer difficulty from ID suffixes, damage, names or gear. Manual difficulty overrides remain available and their source is recorded. Content categories without a known mapping and the ranking game patch still require confirmation.

Combat review on desktop and Pages includes **Mapping coverage** with recorded map/instance IDs, a catalog revision, unresolved NPC types and enemy references missing their type. **Export mapping report** downloads this bounded ID report without character names or raw traffic. Diagnostic ZIPs include current-view catalog coverage as well; the full combat log contains coverage per retained encounter. A supplied creature name does not automatically become a trusted catalog entry.

Reports keep at most 100 unresolved IDs per encounter and show omitted counts. Entity references and effects are counts of retained evidence, not kills; player opponents and owned pets are excluded from NPC coverage. A missing type cannot be resolved from an actor ID, which changes between instances. An unmapped ID means absent from the installed catalog, not proof of new content.


## Automatic capture metadata and idle DPS (0.2.35)

Live Meter detects the installed game build for registered Windows installs and resolves recorded server IDs against official regional metadata in the background. Installation paths are not exported. Steam build IDs and executable versions are build evidence, not automatically a game patch. Optional classification overrides take precedence within the recorded PvE/PvP mode.

Recorded map/instance IDs identify known open-world categories, Fire Temple Arena and available dungeon names. Unmapped content, difficulty, patch and match outcomes remain unknown. Detection provenance is visible in shared log review. Opponents without their own server ID are not assigned your server.

Live DPS uses the recorded damage interval and pauses after two seconds without damage while capture continues. Healing after the last damage no longer lowers live DPS. Actual new damage resumes it. Saved logs preserve the full event interval, including healing/deaths, so report rates can differ from the live rate. This does not establish a kill or match result.


This document explains where every number in `aion2calc` comes from, which
parts are measured community knowledge, and which parts are assumptions you
may want to tune.

## 1. Which game version is modelled

* **Global launch (Oct 2026)** opens at **level 45** on the Korean "Season 1"
  content tier (KR Season 1 ran Nov 2025 – Jan 2026).  Global Early Access
  started 30 Sep 2026 for Founder's Pack owners; open launch is 5 Oct 2026.
* **Primary data source = the global client**, as published by
  [metabot.gg](https://metabot.gg/en/aion-2), which reads the global client's
  skill, Daevanion, item, title and stat tables.  The global client differs from
  the current Korean live service (e.g. Sorcerer *Blaze* is `198 + 193.2% Attack`
  at Lv 1 globally; Flame Arrow's 4th specialization is "+5% Fire Damage Boost
  on Pyroclasm" globally but "Fire Mark" in KR; Daevanion stat nodes are
  `Crit +5 / Attack +3 / corners +1.5%` globally vs `+10 / +5 / +2.5–5%` in KR).
* **Korean data is used only where the global client is silent**:
  per-skill hit counts (gamers4.life skill records), the damage-formula
  research (Taiwanese Bahamut / Inven tests run in KR Season 1), and the
  top-player training-dummy logs on [A2DIL](https://a2dil.com) for validation.

## 2. Budgets at level 45 (global client)

| Resource | Value | Source |
|---|---|---|
| Skill points | 203 from levels **+ 1 per Wisdom Stone** (Empyrean Traces → monolith exchange); top global level-45 profiles show 382–383 spent. Configurable (`--skill-points`); imported characters use their own total | metabot (client Exp table), official profiles |
| Skill level price | Lv 2–4: 1, Lv 5–7: 2, Lv 8–10: 4 (21 per skill to Lv 10) | metabot (skill acquire table) |
| Skill level cap from points | 10; Daevanion +4 max per skill (4 nodes per skill) | metabot / Inven |
| Arcana skill rolls | (grade base + enhancement level) random skill levels per arcana — Rare 2, Legend 3, Unique 4 base, +1 per enhancement (Unique +5 = 9); repeats stack up to +4 per skill. Chalice (any skill), Parchment and Compass (two halves of the active skills) roll actives; Bell and Mirror roll passives | official item data (`/api/gameconst/item`, character equipment) + metabot pools (`data/global/arcana_skill_pools.json`) |
| Accessory skill rolls | Unique accessories (e.g. Aulamus/Gartua) roll up to 4 passive skills at +1 from a 10-skill pool | official item data, metabot pools |
| Specialization slots | 1 at skill Lv 8, 2 at Lv 12, 3 at Lv 20; options unlock at 8/12/16 | client data |
| Highest active skill level at 45 | 10 SP + 4 Daevanion nodes + arcana rolls. A Unique +5 Parchment spreads 9 levels over six core actives, so the Lv 16 options (Pyroclasm reset, Wish −10 s, Blaze → Wish, Hellfire −15 s) are reachable with good rolls; a level-45 profile with only Rare arcana already shows Lv 15 actives | official profiles, derived |
| Stigma points | 29 (+1 from the 3rd Ascension reward = 30) from levels; some profiles show more (up to ~70), so it is configurable (`--stigma-points`) | metabot, official profiles |
| Stigma level price | Lv 1–5: 1, 6–10: 2, 11–15: 4, 16–20: 8 (75 to Lv 20) | metabot |
| Stigma slots | 4 (Lv 22/27/32/37) | client data |
| Daevanion Crystal points | **360** (136 from levels + 122 from 61 sealed dungeons + 58 regional quests + shop/fragment crystals) | metabot board guide; the global top-player "most common" board spends 351 |
| Daevanion boards | Nezekan (134), Zikel (134), Vaizel (134), Triniel (168) share the crystal pool; Azphel (232) is PvP and uses its own currency | client data |

Daevanion connectivity rule (same as the in-game window and both public
planners): a node can be taken only if it touches the board centre or another
taken node orthogonally.

## 3. Damage formula

Expected damage of one hit (implemented in `aion2calc/model/damage.py`):

```
Attack     = (all "Attack"/"Attack Bonus" + weapon roll) × (1 + Attack increase%)
base       = Attack × skill coefficient + skill flat + PvE/Boss Attack + Penetration/10
boost      = 1 + (Damage Boost + PvE Damage Boost + Boss Damage Boost + buffs) − target Damage Tolerance
element    = 1 + Fire/Water Attack%                      (separate multiplier)
vulnerable = 1 + "damage taken from the caster" debuffs   (separate multiplier)
weapon     = 1 + 0.66 × Weapon Damage Boost
crit       = 1 + P(crit) × (0.5 + Critical Damage Boost)   (+ Critical Attack on crit)
double     = Double (Smite) = ×2 ; Perfect = max weapon roll ; Double and Perfect never stack
multi-hit  = 1 + P(multi-hit) × 0.125
DoT ticks  : no defense, no crit/double/perfect/multi-hit
```

Sources: Taiwanese Bahamut research translated on Inven
([902](https://www.inven.co.kr/board/aion2/6444/902),
[909](https://www.inven.co.kr/board/aion2/6444/909),
[1431](https://www.inven.co.kr/board/aion2/6444/1431)), the Inven Double-chance
article ([news 312835](https://www.inven.co.kr/webzine/news/?news=312835&site=aion2)),
and the community DPS calculator
[aion2ssow](https://bongbong99999-debug.github.io/aion2ssow/) (weapon-boost 66 %
efficiency, multi-hit 12.5 %, crit curve capped at 80 %).

* **Skill value = coefficient × Attack + flat** — the coefficient is constant
  across skill levels; only the flat part grows (TW tests, confirmed by the
  global tables).
* **Tooltip totals**: for multi-hit skills the tooltip number is the total of
  all hits (`SkillUIMinDmgsum`); the simulator splits it evenly.  This is the
  only reading that reproduces the KR log ratios between Firestorm fireballs,
  Hellfire and Blaze.
* **Crit chance** `= 1.0461 / (1 + e^(−0.006 (Crit − 1024.5)))`, capped at 80 % in
  the model (fit to dummy tests: 1048 → 56 %, 1220 → 80 %, 1326 → 90 %;
  [Inven](https://www.inven.co.kr/board/aion2/6444/909)).  The cap never binds at
  launch.  At global-launch crit values (~400–700) the fit is an extrapolation and
  gives 3–15 % — the largest single uncertainty for crit-related advice (§6).
* **Primary and deity stats**: +0.1 % per point to each of their effects in the
  global client (metabot "Stats explained"; KR later raised deity stats to
  0.2 %).  Might/Destruction → Attack %, Precision/Death → Crit %, Wisdom →
  Double + MP cost, Justice → Perfect, Time → Combat Speed, Illusion → Cooldown.
* **Parry**: insufficient Accuracy turns hits into parries (−50 %).  The
  simulator assumes the Accuracy threshold is met (back attacks and
  "ignores Block and Evasion" skills bypass parry); Accuracy is therefore a
  threshold stat, not a DPS stat.

## 4. Simulation

`aion2calc/sim/engine.py` is a deterministic, expected-value, event-driven
simulator.  Skills are `Action`s with an on-cast callback; the kit decides what
they do (hits, DoTs, buffs, debuffs, cooldown resets/reductions, MP).  Procs
with a chance and an internal cooldown use an accumulator so their long-run
rate is exact without randomness.  Action time = base time / (1 + Combat Speed
+ skill speed) + latency (30 ms).  Optional tick quantization (262.5 ms server
tick, visible in A2DIL logs) is available but off by default because base
animation times are not known precisely enough for breakpoints to be
meaningful.

Fight scenarios (`aion2calc/scenarios.py`):

* **boss** (default objective): 180 s, 30 % Damage Tolerance (TW measured
  ~30 % on a Season-1 conquest boss), HP falling linearly (matters for
  HP-threshold passives), three 8 s stagger windows.
* **dummy**: 180 s, 10 % Damage Tolerance (TW measurement), 100 % HP.

## 5. Optimization

`aion2calc/opt/pipeline.py` alternates, accepting only improvements:

1. **Specializations** – coordinate descent over every legal combination per
   skill at the current levels.
2. **Rotation** – hill climbing over priority lists (relocate / drop / add
   entries, Hellfire charge level, filler choice, optional "wait for Delayed
   Explosion" and "inside Element Enhancement" conditions), several restarts.
3. **Stigmas** – all 4-of-N damage stigmas, then every stigma-level pattern that
   spends the 30 points for the best sets.
4. **Per-skill level curves** – DPS as a function of each skill's effective
   level (best specialization at each level), plus **stat weights** by finite
   differences.
5. **Daevanion + skill points** – one integer program (PuLP/CBC): node choices
   with flow-based connectivity per board, the 360-point budget, the 203 SP
   budget with the real price table, and ordered "level ≥ k" indicators so
   specialization breakpoints (non-concave value jumps) are handled exactly.
6. **Skill-point polish** – after the last iteration, a local search with the
   full simulator moves 1–2 skill levels between skills (or spends left-over
   points) while any move gains DPS.  It catches interactions that the
   separable level curves of step 5 cannot see (one skill's level changing
   another skill's value, spec slots opening at Lv 8/12).

Every step is scored on the full 180 s fight of the chosen scenario, so the
numbers in the log are directly comparable.  The stat weights, the curves and
the program are re-computed each iteration around the current build, and a
reallocation is accepted only if the full simulation confirms it.

The in-game **Skill Macro** plan (`opt/macro.py`) keeps short-cooldown skills
and fillers in the hold-to-run macro and leaves long-cooldown burst skills on
manual keys, then simulates the macro's round-robin behaviour to check it gets
close to the ideal priority.

### Baseline ("typical top global build")

Reports compare against what the top tracked global level-45 players of the
class actually run (metabot.gg live statistics): each skill at its average
level (minus the levels the most-picked Daevanion nodes give, fitted to 203
SP), the four most-picked damage stigmas at their average levels (fitted to 30
points) and the most-picked Daevanion nodes.  Specializations are not
published, so the baseline gets the best legal specs for its levels.  It is
shown with the default priority and with the same rotation optimizer.

## 6. Assumptions you may want to tune

| Item | Value | Where |
|---|---|---|
| Base animation times | Flame Arrow step 0.80 s, Blaze 0.75 s, Firestorm 1.25 s, Hellfire 0.5 s/charge + 0.6 s ... | `kit/sorcerer.py: TIMING` |
| Flame Arrow chain multipliers | 1.00 / 1.12 / 1.33 (A2DIL share ratios) | `ASSUME` |
| Blaze "delayed damage" size | 30 % of the main hit | `ASSUME` |
| Hellfire "Fire DoT" size | 25 % of the hit over 10 s | `ASSUME` |
| Enhanced Embers / Frostbite | one extra Embers/Frostbite tick per landed attack, 1 s ICD | `ASSUME` |
| Base MP at 45 | 2,500 (+gear, +Robe of Earth %) | `run.py` |
| Gear rolls | expected value of each item's random roll pool | loadout JSON |
| Loadouts | `*_l45_global_median` = most common gear of top tracked global players; `sorcerer_l45_geared` = first-month upgrade target (Rupture Tome +10, Bakarma Guard +10, Aulamus +10, Abyssal Bracelets +10, Unbound by Genus + Empty Closet, 5 Unique arcana +5) | `data/global/loadouts/` |
| Crit curve at low crit | TW logistic, extrapolated below its measured range | `model/stats.py` |

The report's **sensitivity** section perturbs every animation time by up to
±25 % and re-optimizes the rotation; a small loss for the fixed recommendation
means it is robust to these unknowns.

## 7. Validation

* Simulated Sorcerer damage shares match the A2DIL top-KR dummy logs closely
  (Hellfire ~20 %, Fire Wall ~15 %, Cold Storm ~10–12 %, Blaze ~11–14 %,
  Firestorm ~8–10 %, Flame Arrow chain ~7 %, Delayed Explosion ~1.6–2 %).
* The optimizer's stigma pick matches the global top-player majority
  (Element Enhancement, Fire Wall, Delayed Explosion, Cold Storm — metabot).
* The global "most common" Daevanion board spends 351 of the 360 points.

## 8. What is *not* modelled

Movement/boss mechanics, party buffs (optional via `Scenario.buffs`), PvP,
pets' genus-specific damage (only matters versus that genus), Power Shards,
and any content gated behind levels > 45.

## Experimental PvP optimizer

My Character provides separate PvE and PvP damage actions. PvP uses the generic class kit against a stationary neutral player proxy, excludes PvE/boss stat buckets and learned PvE skill/proc/critical calibration, and assesses sustained (180 seconds) and burst (30 seconds) damage. Saved results retain this model description. It does not optimize dedicated PvP progression, survival, crowd control, movement or opponent-specific defenses, and its skill coefficients are not validated PvP coefficients. PvP output is excluded from PvE community preset submission.

## Long live sessions (0.2.38)

Live capture automatically saves a numbered archive part before the current history reaches its effect, telemetry, encounter or observed-party identity budget. Each part has a shared archive ID and appears separately in **Combat Logs**. Capture continues with the same decoder and current identity context; the live meter and its export/upload buttons cover the current part. Open an earlier part from Combat Logs to review or upload it. There is no fixed total part count or automatic deletion; available disk space is the practical storage limit. The recent list shows the newest 100 files; older parts remain in the user logs folder and can be imported.

A storage boundary is not a boss kill, instance finish or arena result. Parts crossing a storage boundary are conservatively unranked, and a continued run does not inherit observed entry. Parts are not automatically stitched into a combined report or uploaded as a batch. A failed rollover save stops capture visibly and retains the in-memory history instead of clearing it. Periodic recovery is still every 15 seconds; abrupt termination can lose newer unsaved effects.

Per-file format/validation limits still apply. In unusually large All-observed rosters, a part can exceed the 64-player validation limit; the app reports a save error rather than silently clearing it. Party/Self scope is recommended. This is automatic bounded-part archival, not an unlimited single JSON document. Raw TCP diagnostics remain a separate opt-in recording.

Implementation: rollover is checked between decoded packet batches at 100,000 retained effects, 20,000 telemetry samples, 100 conservative candidate encounter boundaries or 48 observed party actor references. Saves use atomic replacement and fsync before releasing the old part. Thresholds leave headroom for normal packet batches. Counters remain conservative cumulative capture evidence across parts. No live TCP stream is reopened, historical identity epochs are not merged, and recorded pet links remain available.
