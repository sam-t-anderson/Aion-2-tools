# Methodology, sources and assumptions

This guide explains how build recommendations are calculated and how recorded combat evidence is interpreted. Start with the model's data and budgets, then follow the calculation and optimization steps. The final sections cover telemetry and its limits.

For controls and setup, see the [app guide](app.md) and [user guide](user-guide.md). Version-by-version changes are in [Releases](https://github.com/sam-t-anderson/Aion-2-tools/releases).

## Contents

- [Data sources and model scope](#data-sources-and-model-scope)
- [Character budgets and legal allocations](#character-budgets-and-legal-allocations)
- [Damage calculation](#damage-calculation)
- [Simulation and scenarios](#simulation-and-scenarios)
- [Optimization and macro planning](#optimization-and-macro-planning)
- [Experimental PvP model](#experimental-pvp-model)
- [Canonical preset comparison policy](#canonical-preset-comparison-policy)
- [Manual Genus Insight](#manual-genus-insight)
- [Damage optimization with an HP reserve](#damage-optimization-with-an-hp-reserve)
- [Assumptions and limitations](#assumptions-and-limitations)
- [Validation and sensitivity](#validation-and-sensitivity)
- [Combat-log evidence](#combat-log-evidence)
- [Installation, identity and live rate evidence](#installation-identity-and-live-rate-evidence)
- [Encounter catalog and boss roles](#encounter-catalog-and-boss-roles)
- [Capture-driver counters](#capture-driver-counters)
- [Archive boundaries and retention](#archive-boundaries-and-retention)

## Data sources and model scope

The bundled model targets the global level-45 dataset. It is a versioned data snapshot, not a guarantee that every coefficient matches the latest regional live build. Korean data fills specified gaps; region and source differences remain relevant.

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

## Character budgets and legal allocations

Budgets constrain a particular optimization, not the maximum progression available in the game. Official profiles can omit unspent points, so imported allocated points are a lower bound. Enter the actual in-game total before optimizing. Community observations distinguish profile spend from user-entered totals and do not establish a game maximum.

| Resource | Value | Source |
|---|---|---|
| Skill points | 203 is the example level-based budget; additional progression grants points. Configurable (`--skill-points`); use the character's in-game spent + unspent total | metabot (client Exp table), official profiles |
| Skill level price | Lv 2–4: 1, Lv 5–7: 2, Lv 8–10: 4 (21 per skill to Lv 10) | metabot (skill acquire table) |
| Skill level cap from points | 10; Daevanion +4 max per skill (4 nodes per skill) | metabot / Inven |
| Arcana skill rolls | (grade base + enhancement level) random skill levels per arcana — Rare 2, Legend 3, Unique 4 base, +1 per enhancement (Unique +5 = 9); repeats stack up to +4 per skill. Chalice (any skill), Parchment and Compass (two halves of the active skills) roll actives; Bell and Mirror roll passives | official item data (`/api/gameconst/item`, character equipment) + metabot pools (`data/global/arcana_skill_pools.json`) |
| Accessory skill rolls | Unique accessories (e.g. Aulamus/Gartua) roll up to 4 passive skills at +1 from a 10-skill pool | official item data, metabot pools |
| Specialization slots | 1 at skill Lv 8, 2 at Lv 12, 3 at Lv 20; options unlock at 8/12/16 | client data |
| Highest active skill level at 45 | 10 SP + 4 Daevanion nodes + arcana rolls. A Unique +5 Parchment spreads 9 levels over six core actives, so the Lv 16 options (Pyroclasm reset, Wish −10 s, Blaze → Wish, Hellfire −15 s) are reachable with good rolls; a level-45 profile with only Rare arcana already shows Lv 15 actives | official profiles, derived |
| Stigma points | 30 is the example budget including the third Ascension reward; additional progression can increase it. Configurable (`--stigma-points`) | metabot, official profiles |
| Stigma level price | Lv 1–5: 1, 6–10: 2, 11–15: 4, 16–20: 8 (75 to Lv 20) | metabot |
| Stigma slots | 4 (Lv 22/27/32/37) | client data |
| Daevanion Crystal points | **360** is the example PvE budget, including level, dungeon, quest and other progression sources; it is configurable and is not a verified maximum | metabot board guide; the global top-player "most common" board spends 351 |
| Daevanion boards | Nezekan (134), Zikel (134), Vaizel (134), Triniel (168) share the crystal pool; Azphel (232) is PvP and uses its own currency | client data |

Daevanion connectivity rule (same as the in-game window and both public
planners): a node can be taken only if it touches the board centre or another
taken node orthogonally.

## Damage calculation

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
  gives 3–15 % — the largest single uncertainty for crit-related advice (see [Assumptions and limitations](#assumptions-and-limitations)).
* **Primary and deity stats**: +0.1 % per point to each of their effects in the
  global client (metabot "Stats explained"; KR later raised deity stats to
  0.2 %).  Might/Destruction → Attack %, Precision/Death → Crit %, Wisdom →
  Double + MP cost, Justice → Perfect, Time → Combat Speed, Illusion → Cooldown.
* **Parry**: insufficient Accuracy turns hits into parries (−50 %).  The
  simulator assumes the Accuracy threshold is met (back attacks and
  "ignores Block and Evasion" skills bypass parry); Accuracy is therefore a
  threshold stat, not a DPS stat.

## Simulation and scenarios

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

## Optimization and macro planning

`aion2calc/opt/pipeline.py` alternates, accepting only improvements:

1. **Specializations** – coordinate descent over every legal combination per
   skill at the current levels.
2. **Rotation** – hill climbing over priority lists (relocate / drop / add
   entries, Hellfire charge level, filler choice, optional "wait for Delayed
   Explosion" and "inside Element Enhancement" conditions), several restarts.
3. **Stigmas** – all 4-of-N damage stigmas, then every stigma-level pattern that
   uses the configured stigma budget for the best sets.
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

Every step is scored on the full fight of the chosen scenario, so the
numbers in the log are directly comparable.  The stat weights, the curves and
the program are re-computed each iteration around the current build, and a
reallocation is accepted only if the full simulation confirms it.

The in-game **Skill Macro** plan (`opt/macro.py`) keeps short-cooldown skills
and fillers in the hold-to-run macro and leaves long-cooldown burst skills on
manual keys, then simulates the macro's round-robin behaviour to check it gets
close to the ideal priority. Skills requiring charge are kept on manual keys because the game macro only taps them; the macro is not assumed to hold a charge. The suggested macro binding is Right-click; the app does not change game bindings.

### Example baseline

Reports compare against a snapshot of tracked global level-45 player
statistics from metabot.gg: each skill at its average
level (minus the levels the most-picked Daevanion nodes give, fitted to 203
SP in this example), the four most-picked damage stigmas at their average levels (fitted to 30
points) and the most-picked Daevanion nodes.  Specializations are not
published, so the baseline gets the best legal specs for its levels.  It is
shown with the default priority and with the same rotation optimizer.

## Experimental PvP model

My Character provides separate PvE and PvP damage actions. PvP uses the generic class kit against a stationary neutral player proxy, excludes PvE/boss stat buckets and learned PvE skill/proc/critical calibration, and assesses sustained (180 seconds) and burst (30 seconds) damage. Saved results retain this model description. It does not optimize dedicated PvP progression, defensive skill use, crowd control, movement or opponent-specific defenses, and its skill coefficients are not validated PvP coefficients. PvP output is excluded from PvE community preset submission.

The optional HP reserve below also applies to PvP, but it is a manual incoming-pressure constraint, not a simulation of an optimized opponent or a competitive win probability.

### Personal multi-scenario optimization

Personal character search can use its primary scenario or an equal-weight pair within the same mode. Frozen gear, Genus lines, point budgets and HP/trained-skill reserves are shared across scenarios. Current-build specialties and priority are evaluated with the same selected objective before comparison. Full weighted simulations score specialty/stigma choices, skill curves and priority changes; weighted finite-difference slopes guide approximate board proposals before full-score acceptance. Results preserve both component DPS and combined modeled DPS. Higher combined damage does not guarantee higher primary damage, survivability or PvP win probability. Ancillary skill-share, macro and sensitivity views remain primary-scenario views.

## Canonical preset comparison policy

The versioned canonical preset evaluator compares allocations within one class, combat mode and scoring scope. It uses a common median loadout and fixed example budgets of 203 Skill, 30 Stigma and 360 crystal-board Daevanion points. These are comparison resources, not verified game maxima. Over-budget submissions need a separate optimization under these resources; they are not silently trimmed into a different build.

PvE weights the 180-second boss and dummy damage scenarios equally. PvP weights the 180-second stationary player proxy and 30-second burst proxy equally. The score is the arithmetic mean of the two modeled DPS values, not a percentile, user rating or win probability. Personal gear, Genus, HP reserves and trained skill constraints are not shared comparison inputs. Learned calibration is disabled.

Bundled PvP examples run separate sustained and burst allocation searches, each with one optimization iteration and personal calibration disabled. Both allocations are reevaluated with the same weighted objective, and only the stronger example is published per class. Search objective, iteration count, score components and frozen common loadout are retained. This two-candidate search does not establish global optimality.

The scope fingerprints the scoring-model revision (separate from capture/UI application versions), class data, hit profiles, common loadout, budgets, durations and weights. A different scope requires reevaluation. The best eligible evaluated candidate can become canonical; that does not establish a global optimum or a competitive PvP build. Mode-scoped storage records one current winner per comparison scope. Planner synchronizes bounded, validated common-loadout snapshots from the configured server and labels cached comparisons separately from examples. The server owns scoring; clients display its components and policy rather than substituting a score from a different local model.

### Weighted contribution search

Anonymous common-loadout contributions start with independent searches for each mode's two scenarios, then refine the better seed against their equally weighted modeled DPS. Skill/specialty/stigma comparisons, point polishing and priority search use both full-duration simulations. Crystal-board proposals use weighted separable skill curves and finite-difference stat weights; timing slopes retain the existing per-scenario rotation approximation. Full weighted evaluation accepts or rejects the proposal. The final candidates are independently scored under the same policy and the best is retained, including either original seed.

The saved contribution records search revision, objectives and candidate scores. A changed scoring scope or search revision regenerates it. This local search does not establish a global optimum. Personal optimizations and their HP/skill reserves are separate. Experimental PvP remains a damage proxy; weighted damage is not a survivability or win-probability score.

## Manual Genus Insight

Character optimization reads the saved inventory's manual Genus analysis lines by default. Both the current-build score and optimized build use the same frozen loadout component, including comparison scenarios and baseline builds. The official character import is unchanged; it does not supply Genus allocations. Saved reports retain levels, slots, values, mode, assumed mix and excluded effects.

PvE scales genus-specific stat lines by a user-assumed enemy mix (equal Cogni/Fera/Natura/Varian by default). This is a weighted-stat approximation: nonlinear effects are not simulated separately for each enemy genus. PvP includes supported general damage stats and excludes genus-specific effects because their applicability to players is unverified. Unsupported effects, defensive lines and owned collection effects contribute no modeled benefit.

Optimization holds rolls fixed while selecting other allocations. Reported line contributions remove one line from the final build using its existing rotation; contributions are conditional and not additive. They do not represent reroll probabilities, costs or guaranteed obtainable replacements. Genus-dependent personal builds are not submitted to common-loadout presets.

## Damage optimization with an HP reserve

My Character → **Survivability** preserves the character's imported flat **HPMax** contribution from the four optimized crystal boards by default. The existing DPS objective stays primary inside the set of allocations meeting this floor. Skill, stigma and Daevanion budgets and board connectivity remain enforced. A stricter minimum can trade some modeled DPS for more crystal HP. Disable preservation and leave the minimum/scenarios empty to use the previous damage-only objective. This is an HP-node constraint, not a full survival simulator.

Optional scenarios describe one hit followed by sustained pressure. Enter current in-game maximum HP and up to eight encounter/opponent assumptions: **hit damage after mitigation + max(0, incoming DPS − assumed sustained HPS) × seconds + positive HP reserve**. The largest requirement sets the floor. HPS never absorbs the initial hit. Estimated total HP is entered current HP plus the flat node-HP change; percentage modifiers and passive/gear changes are not modeled. Headroom is a scenario proxy, not verified effective HP, guaranteed survival or win probability. Confirm final HP in game.

Settings persist per selected character in this browser. Saved Results/build JSON/Markdown retain assumptions and the assessment. Infeasible requests report an error without publishing a lower-HP fallback. Solver limits can prevent finding an allocation even when one exists. Damage-only stat priorities, baseline comparisons and Gear & Advice do not validate survival; constrained builds are not submitted as community damage presets.

PvP supports a manual multi-opponent **incoming-pressure** envelope, not optimized opponent-build combat. Next modeling work: resolve official current/historical opponent gear with provenance; evaluate outgoing damage and adverse matchups; include verified defensive skill, CC, mobility and coefficient rules before scoring them. Those metrics are explicitly unavailable here. Mitigation and tactical coefficients are not inferred from these manual scenarios.


### Timed pressure assumptions

Personal incoming-pressure scenarios can include up to eight named defensive, control or movement windows. All percentages and timings are user assumptions. Within the scenario window, each interval uses `incoming DPS × (1 − strongest active reduction) − active healing HPS`. The running ongoing deficit is floored at zero; its maximum determines the pressure component of the HP requirement. Interval boundaries include all reduction and healing starts and ends. The initial burst is added separately and is never reduced by these windows. Overlaps do not add or multiply reductions.

Results retain a reference with identical healing and no added reductions. This is sensitivity analysis, not a calibrated tactical model: skill availability, casts, cooldowns, immunity, chance of control/avoidance and outgoing damage opportunity costs are not inferred. Optional linked skills/effects are unioned with personal reserves at optimizer construction and validated against the same budgets and effect-slot limits. Stricter trained minimums win; effect sets are unioned. Stigma links keep their slots equipped. No link is dropped because its window has zero duration or lies outside the scenario. This guarantees allocation availability, not the assumed pressure reduction or successful use. An additional no-reduction scenario can constrain the same build for failed execution or immune opponents.

Optional **assumed effective cooldown** checks reuse of a linked skill within each scenario. Blank means unknown, not verified available; zero imposes no reuse gap. All skills start ready. Positive-duration, positive-reduction windows count as activations; entries sharing the same start count once. The largest entered cooldown for that skill applies when assumptions differ. Reuse before that cooldown is rejected. Scenarios are alternative encounters and are checked separately. Saved Results and Markdown retain starts, the shortest reuse gap and the assessment. These are user-entered effective values: review them after gear or cooldown-reduction changes. Charges, resets and shared cooldown groups are not modeled. Explicit outgoing action-time assumptions are entered separately.

### Outgoing action-time assumptions

Personal PvE and PvP optimization accepts up to eight explicit pauses for defense or movement. Enter starts (0–3600 seconds) and durations (0–120 seconds) on one fight’s outgoing rotation clock. Each damage scenario applies the schedule once, clipped to its duration; overlaps use their union. A schedule covering an entire scenario is rejected. Incoming pressure scenarios have independent clocks and are never automatically copied.

The simulator chooses actions that finish before each pause and waits through it. Previously scheduled hits, DoTs and pet damage still resolve, and cooldowns and regeneration continue. Candidate builds, rotation search, stat weights, macros and the current-character comparison use this schedule. Community damage references remain unpaused; they are not equivalent tactical comparisons. Saved Results, exports and reconstructed reports preserve the assumptions.

Optionally link each outgoing pause to a catalog active skill or stigma and a supporting effect. Linked minimums merge with incoming-window links and separate reserves: the strictest trained level wins and effects are unioned within the same point and slot budgets. Passives cannot be outgoing action links. Zero-duration and clipped-out entries still retain their requested allocation; only positive-duration windows starting before a damage scenario ends count as assumed uses in that scenario.

An optional **assumed effective cooldown** checks the spacing of those uses independently for each outgoing damage scenario. Blank remains unknown; zero imposes no gap. Same-start entries represent one assumed use; the largest entered cooldown for a skill applies, including assumptions on clipped-out entries. Reuse before that assumed cooldown is rejected. Saved Results and Markdown retain linked requirements, per-scenario starts, shortest reuse gap and unknown/satisfied status. Incoming pressure clocks stay independent. Reuse checks alone do not alter offensive cooldown availability. **Reserve cooldown in rotation** opts into an explicit exclusion for each linked positive-duration use before the scenario ends; an entered cooldown is required. Matching uses share the kit's explicit cooldown groups. Offensive casts are held if their modeled cooldown or the entered assumption (whichever is larger) would overlap the upcoming use. The group is excluded from the use start until the entered cooldown expires afterward. Reset hooks do not shorten that fixed exclusion. Conflicting assumed uses in an explicit shared group are rejected. Same-start uses in a group count once with the largest entered cooldown.

Saved current/optimized results and Markdown identify matched action keys/groups or **no matching modeled action**. Missing kit actions are not treated as a successfully reserved cooldown. Cross-skill hooks and resource readiness are not verified; an exclusion is not proof of tactical availability. These exclusions do not execute the tactical skill, consume MP, apply damage/shields/CC, establish success or discover unrecorded shared groups and charges. Old schedules default to no rotation reservation; explicit unavailability windows still apply.

These pauses model unavailable offensive time, not an actual defensive skill: tactical MP, cooldowns, shields, crowd-control success and movement outcomes still need verified rules. Empty schedules preserve the default damage model.

### Trained skill and stigma reserves

My Character → **Retain trained skills and equipped stigmas** optionally sets minimum purchasable levels for active/passive skills and currently equipped stigmas. A reserved stigma stays equipped. The optimizer maximizes modeled damage within these floors and the point/slot budgets; infeasible requests produce an error. Settings persist per character and apply to both PvE and PvP. Saved Results, build JSON and Markdown retain the minimum and selected levels. These personal builds are excluded from community damage preset comparisons.

Skill minimums apply to trained levels. Reserved supporting effects additionally constrain effective levels for their catalog unlocks and selection slots. The joint allocation can fund these with trained points, fixed gear bonuses and connected Daevanion nodes within the same budgets. Other specialties and bonuses may change. A feasible seed is required before searching damage; the final allocation and point-polishing moves must preserve the required effective levels. Infeasible or unconfirmed solver allocations are rejected without an unconstrained fallback. Use utility skills manually when absent from the suggested rotation. Reserving a defensive or movement skill does not simulate its tactical use, CC, shields, opponent defenses or win probability; damage baselines remain unconstrained references, while personal stat priorities use the selected scenarios and explicit outgoing pauses.

## Assumptions and limitations

The model does not reproduce movement or boss mechanics, complete party interactions (optional buffs can be supplied via `Scenario.buffs`), verified opponent-specific PvP combat, verified per-genus pet combat interactions, Power Shards, or content beyond its modeled level range. An HP-node reserve does not fill these gaps.

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

## Validation and sensitivity

The following are historical Sorcerer comparison examples for the bundled dataset, not a current guarantee for every class, build, gear set or encounter.

* Simulated Sorcerer damage shares match the A2DIL top-KR dummy logs closely
  (Hellfire ~20 %, Fire Wall ~15 %, Cold Storm ~10–12 %, Blaze ~11–14 %,
  Firestorm ~8–10 %, Flame Arrow chain ~7 %, Delayed Explosion ~1.6–2 %).
* The optimizer's stigma pick matches the global top-player majority
  (Element Enhancement, Fire Wall, Delayed Explosion, Cold Storm — metabot).
* The global "most common" Daevanion board spends 351 of the 360 points.

## Combat-log evidence

Combat review describes retained observations separately from simulated expectations. Recorded effects are not proof of cast starts, complete capture or authenticated game results. Missing telemetry remains unavailable. Linked pets retain their source IDs when totals are grouped with their owner.

See the [user guide](user-guide.md) for matched comparison cohorts, ranking eligibility, privacy and review controls.

## Installation, identity and live rate evidence

Live Meter reads installed build evidence from Steam library manifests and recognized Windows game registrations, including PURPLE registrations. It resolves recorded server IDs against official regional metadata in the background. Installation paths are not exported. New Steam captures use the exact selected-installation Build ID, qualified by the Steam app namespace, as their technical build comparison key. Executable resources can contain engine versions and are not promoted to game build identifiers. Unrecognized PURPLE build metadata remains unavailable; launcher namespaces are not merged without verified equivalence. Capture records this evidence for its session and never retrospectively applies a current install build to historical logs. Optional classification overrides take precedence within the recorded PvE/PvP mode.

Recorded map/instance IDs identify known open-world categories, Fire Temple Arena and available dungeon names. Unmapped content, difficulty, build and match outcomes remain unknown. Detection provenance is visible in shared log review. Opponents without their own server ID are not assigned your server.

Live DPS uses the recorded damage interval and pauses after two seconds without damage while capture continues. Healing after the last damage does not extend the live damage interval. Actual new damage resumes it. Saved logs preserve the full event interval, including healing/deaths, so report rates can differ from the live rate. This does not establish a kill or match result.

Unknown difficulty is not guessed from boss damage or observed current HP. Build-specific maximum-HP signatures and corroborating evidence require independently labeled collection and validation before automatic inference. Current installation evidence is never applied retrospectively to historical logs.

## Encounter catalog and boss roles

Live Meter fills difficulty only when the recorded PvE instance ID has an explicit difficulty in the bundled dungeon table. It does not infer difficulty from ID suffixes, damage, names or gear. Manual difficulty overrides remain available and their source is recorded. Content categories without a known mapping still require confirmation. Missing unique launcher build evidence stays unavailable.

Combat review on desktop and Pages includes **Mapping coverage** with recorded map/instance IDs, a catalog revision, unresolved NPC types and enemy references missing their type. **Export mapping report** downloads this bounded ID report without character names or raw traffic. Diagnostic ZIPs include current-view catalog coverage as well; the full combat log contains coverage per retained encounter. A supplied creature name does not automatically become a trusted catalog entry.

Reports keep at most 100 unresolved IDs per encounter and show omitted counts. Entity references and effects are counts of retained evidence, not kills; player opponents and owned pets are excluded from NPC coverage. A missing type cannot be resolved from an actor ID, which changes between instances. An unmapped ID means absent from the installed catalog, not proof of new content.

Boss progression requires catalog-confirmed bosses and observed engagement, excluding players, linked pets, dummies and known non-bosses. The broad catalog flag does not distinguish every miniboss from a major or world boss; that role distinction remains incomplete.

## Capture-driver counters

Live Meter capture diagnostics and shared combat-review quality panels show received packets, capture-buffer drops and interface/driver drops when the active Npcap/libpcap backend provides statistics. Unsupported backends are labeled unavailable; partial adapter coverage is labeled. Counters are retained in saved/exported logs and diagnostic ZIPs, including the final sample after capture stops and cumulative evidence across capture restarts in a retained session.

A positive reported drop counter conservatively makes the recording unranked. It does not identify which game effects were lost: counters cover the capture handle and may include other traffic. Zero does not prove loss-free capture, and missing counters are not zero. These counts must not be added to TCP discards to estimate unique lost game packets. Native capture backends without a libpcap handle remain usable, with driver statistics unavailable. Other capture-quality rules remain in effect; driver support alone neither grants eligibility nor blocks older logs.

Statistics are sampled before capture, in that adapter's packet callback and after its thread exits. Optional statistics failures do not interrupt packet decoding. See the [libpcap counter documentation](https://www.tcpdump.org/manpages/pcap_stats.3pcap.html) for platform-specific meanings and availability.

## Archive boundaries and retention

Live capture automatically saves a numbered archive part before the current history reaches its effect, telemetry, encounter or observed-party identity budget. Each part has a shared archive ID and appears separately in **Combat Logs**. Capture continues with the same decoder and current identity context; the live meter and its export/upload buttons cover the current part. Open an earlier part from Combat Logs to review or upload it. There is no fixed total part count or automatic deletion; available disk space is the practical storage limit. The recent list shows the newest 100 files; Saved Parts paginates the archive, and older files can also be imported.

A storage boundary is not a boss kill, instance finish or arena result. Parts crossing a storage boundary are conservatively unranked, and a continued run does not inherit observed entry. Parts are not automatically stitched into a combined report. Saved Parts supports a batch queue that uploads each part as an independent report. A failed rollover save stops capture visibly and retains the in-memory history instead of clearing it. Periodic recovery is still every 15 seconds; abrupt termination can lose newer unsaved effects.

Per-file format/validation limits still apply. In unusually large All-observed rosters, a part can exceed the 64-player validation limit; the app reports a save error rather than silently clearing it. Party/Self scope is recommended. This is automatic bounded-part archival, not an unlimited single JSON document. Raw TCP diagnostics remain a separate opt-in recording.

Implementation: rollover is checked between decoded packet batches at 100,000 retained effects, 20,000 telemetry samples, 100 conservative candidate encounter boundaries or 48 observed party actor references. Saves use atomic replacement and fsync before releasing the old part. Thresholds leave headroom for normal packet batches. Counters remain conservative cumulative capture evidence across parts. No live TCP stream is reopened, historical identity epochs are not merged, and recorded pet links remain available.

## Active damage time for combat metrics

DPS uses the same clock for every recorded player in an encounter. Starting at the first outgoing hit, count one-second buckets containing any outgoing player or linked-pet damage. Empty buckets do not count. A minimum one second prevents division by zero for a single hit. Graph bars and their trailing average remain rates over elapsed encounter time, so they can differ from the active-time DPS summary.

DPS holds during a pause and resumes with the existing damage totals and active seconds. If a player dies while others keep damaging, active seconds continue for everyone and that player's DPS falls without resetting. Automatic inactivity splits require at least 120 seconds since the last outgoing hit; manual splits and map/mode boundaries are independent. Normal gaps between skills can leave empty buckets too, so active-time DPS can exceed an elapsed-time DPS calculation. This measures recorded damage activity, not verified combat state or time spent pressing skills.

Optimizer analysis retains original elapsed hit times, buff windows and encounter duration for cooldown and uptime modeling. Active-time DPS is a combat-meter/report measure; it does not compress optimizer inputs.

## Capture shutdown evidence

Stopping intake does not mean queued payloads have already been decoded. The worker drains its ordered queue for up to five seconds after observing the stop signal, consuming final transport statistics before saving. A failed decoder call or an exceeded drain budget can still leave discarded payloads; those counts keep the report incomplete. A currently executing decoder call cannot be preempted by that budget. Successfully drained payloads do not count as loss.

`capture_errors` is the legacy combined count of processing/capture errors and abandoned queue payloads. New logs also record `decoder_errors`, `shutdown_discarded_payloads` and `shutdown_drained_payloads`. These counters overlap; they are not independent packet-loss totals. A capture-adapter shutdown that has not finished blocks replacement/clearing and delays final archival until Stop succeeds. Previously exported logs cannot recover discarded payloads or distinguish the causes inside a legacy combined count.

## Navigating long-recording parts

Archive part discovery matches the submitted archive ID and sorts by part number, with pagination. Local views search locally saved files. Shared views expose public, available uploads only; hidden or removed siblings are not counted. A token authorizing the current private log is not forwarded when opening another part.

Matching archive IDs are not verified provenance: users can supply or copy metadata, and duplicate part numbers or gaps can occur. Each part retains its own timing, totals, quality and ranking status. Storage flags describe a saved boundary or checkpoint, not encounter completion. Verified continuity, combined reports and entry/completion reconstruction remain separate work.

### Submitted archive sequence evidence

New live archives retain a per-part random token, the preceding closed storage part's token and final decoded-record counter, a first/last sequence range, retained record count and first/last identity context. The sequence increments for retained damage/healing effects across storage continuation. Clearing the session starts a new archive; restarting capture or observing identity-context changes advances context. Checkpoint saves retain their token and can extend their range. A predecessor is advanced only after its atomic disk save succeeds.

These are submitted consistency checks, not signatures or proof of packet continuity. Counters cover decoded effects before scope filtering; undecoded/lost packets and capture downtime cannot be ruled out by adjacent counters. Multiple uploads for the same part are ambiguous even when their tokens match. Only available local files or current public, unmoderated uploads are compared, including neighbors outside the current page. Missing/private/held predecessors are unavailable. No report merging, quality inheritance or retrospective completion is performed.


## Connected recording review

Combined review validates stopped source documents and requires one submitted recording ID, one capture scope, consecutive unique part numbers/tokens, closed predecessors, exact adjacent retained-record sequences, nondecreasing identity contexts and ordered non-overlapping encounter timestamps. Sequence continuity describes decoded records before filtering, not packet continuity or authenticity. Missing/contradictory chains are rejected; source logs remain unchanged. Actor references are namespaced by part, except player totals with a recorded region/server/database-ID identity. Names alone never join players. Source fights/run boundaries remain separate and differing profile snapshots are not pooled into a historical build. Output retains bounded source descriptors, cleaned-document SHA-256 fingerprints and record/context ranges; its derived summaries honor combat-mode filters.

Combined output remains explicitly unranked and non-contributing, including after validation/import/export. Capture counters are maxima of submitted cumulative values; source files provide the individual evidence. No original quality verdict, observed entry, completion, missing effect or cross-part boss attempt is inherited. Review uses at most 32 parts/64 MiB of source JSON and the existing aggregate player/encounter/effect bounds, with errors rather than truncation. Server reconstruction accepts public available source parts only; private view credentials do not grant access to siblings. Combining descriptive review is separate from reconstructing a verified complete run.


New capture-only run provenance contains a stable random token and origin record sequence, observed entry timestamp where supplied, and configured final-boss ID/completion timestamp where observed. Rollover preserves this ledger independently of each part's incomplete entry/quality flags. Descriptive combined run timing requires consistent context/origin, an origin within the selected record range, an entry before the selected combat, and a matching catalog-boss death marker at the recorded completion time in the same instance. Missing or conflicting provenance yields unavailable timing; it does not modify source segment flags or grant ranking eligibility. Older parts cannot be assigned this provenance retroactively.

## Encounter context from catalog records

Context derivation uses stable recorded NPC, map and instance IDs. Explicit community NPC categories map Dungeon to expedition, Transcendence to transcendence, Nightmare to nightmare, Ascension Trial to ascension and Raid to sanctuary. Tier normalization maps Exploration and Conquest labels to the existing difficulty groups; stage/level and named tiers remain distinct. No map suffix, NPC name, damage amount or HP value is used as a classifier.

A recorded instance's NPC records must agree before their shared category/tier is used. Participating NPC records can resolve an otherwise ambiguous tier. Map/NPC candidates never populate a missing recorded instance ID or establish run entry; quality remains unranked without that recorded instance. Conflicts block ranking. Multiple tiers without an exact match leave difficulty unavailable. Submitted manual metadata is preserved and displayed separately from recomputed catalog evidence.

Catalog context is derived again on validation and during server indexing/review. Uploaded context verdicts are not trusted. The server refreshes derived comparison indexes after this rule change while retaining original files, profile snapshots and upload credentials. Its HP signature inventory keeps launcher namespace, classification basis and candidate instance separate; independent difficulty labels and scaling rules are still required before calibrating an HP-based classifier.


### Timed optimized-opponent pressure

Final optimized results retain complete expected hit times and damage for both evaluated damage scenarios. Recording these traces is disabled during the optimizer's repeated scoring evaluations and does not change the damage objective. Imported traces are bounded to 50,000 hits, validated for finite chronological values and matching duration/total/DPS, and rejected rather than truncated. They are user-supplied model evidence, not authenticated combat telemetry.

The timed opponent import selects a fixed-length greatest gross-damage window before applying the user's healing/pressure reductions. Its hits are instantaneous; simultaneous hits are summed, continuous healing reduces accumulated deficits without banking excess, and reduction intervals are half-open. The strongest overlapping reduction applies to each timed hit and any additional continuous pressure. A separate manual initial hit is added independently. The maximum deficit plus the positive HP reserve defines the required HP proxy. Up to eight scenarios contribute independent constraints; their largest requirement sets the crystal-board HP floor. This is not a worst-case search over every tactical alignment, stochastic critical outcome or opponent response. Legacy average-pressure imports remain explicitly available.
