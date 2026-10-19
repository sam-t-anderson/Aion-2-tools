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
- [Estimated buff contribution (0.2.307)](#estimated-buff-contribution-02307)
- [Effective healing and overheal (0.2.307)](#effective-healing-and-overheal-02307)
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
position   : a direct hit lands from the front, from behind or from the side, in the target's shares;
             Front/Back Attack (flat), Front/Back Attack Damage Boost (its own multiplier) and
             Front/Back Attack Critical Hit (added Critical Hit) count only on hits from their side
DoT ticks  : no defense, no position, no crit/double/perfect/multi-hit
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
  Recorded boss fights crit more than the curve gives at the players' profile
  Critical Hit: about 200 more Critical Hit than the profile shows, or a flatter
  curve, would explain them, and the profile leaves out Genus Insight and
  Pantheon ([checked 17 October](open-investigations.md#hit-positions-crit-and-the-remaining-genus-lines-17-october)).
  The curve is kept; learning from your own fights shifts it per class.
* **Front / Back Attack Critical Hit** add Critical Hit on hits from their side
  and are assumed to scale with Critical Hit increase, Precision and Death like
  Critical Hit itself.
* **Primary and deity stats**: +0.1 % per point to each of their effects in the
  global client (metabot "Stats explained"; KR later raised deity stats to
  0.2 %).  Might/Destruction → Attack %, Precision/Death → Crit %, Wisdom →
  Double + MP cost, Justice → Perfect, Time → Combat Speed, Illusion → Cooldown.
* **Parry**: insufficient Accuracy turns hits into parries (−50 %).  Hits from
  behind are never parried (none of 6,573 recorded boss hits from behind was),
  nor are guaranteed crits and "ignores Block and Evasion" skills.  The
  simulator assumes the Accuracy threshold is met, so the scenarios have no
  parries and Accuracy is a threshold stat, not a DPS stat.  Recorded bosses
  parried under 1 % of most classes' hits and 2.4–3.8 % of the casters', but
  how Accuracy lowers that is not known.

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
  HP-threshold passives), three 8 s stagger windows.  Each class's direct hits
  land from the front, from behind and from the side in its recorded shares
  (`BOSS_POSITIONS` in `sim/engine.py`; from the front / from behind: Assassin
  12 / 70 %, Chanter 22 / 55 %, Cleric 27 / 24 %, Gladiator 31 / 51 %, Ranger
  34 / 35 %, Sorcerer 43 / 30 %, Spiritmaster 29 / 34 %, Templar 48 / 31 %;
  54 characters' boss hits in the archived logs and captures,
  [findings](open-investigations.md#hit-positions-crit-and-the-remaining-genus-lines-17-october)).
* **dummy**: 180 s, 10 % Damage Tolerance (TW measurement), 100 % HP, every hit
  from the front.

## Kit knob calibration against real logs

Every damage *number* a hand-written kit uses is read from the global client's
skill tables.  The only free parameters are the handful of values the client
never exposes — animation/recovery lengths (`TIMING`) and chain fractions,
proc/break uptimes and pet windows (`ASSUME`) — collected in each kit so they
can be audited and calibrated.  `aion2calc/calibrate.py` (CLI: `python -m
aion2calc calibrate [cls] [--capture LOG] [--tune]`) measures how well a kit's
simulated per-skill damage-share distribution matches real logs, and can fit
those knobs to them.

Ground truth is the public KR A2DIL aggregate training-dummy share distribution
(`data/kr/a2dil/<cls>.json`), and/or the player's own A2Parser capture (any
saved `.a2log.json`, or an A2DIL / AbyssLogs reference).  The KR logs run at a
higher level with specializations and skills the global build does not have, so
a share of their damage can never be matched; `calibrate` reports that
unreachable mass, the reachable ceiling (`1 − unreachable`) and a `fidelity`
ratio (`overlap / ceiling`) so the score is read against what is achievable, not
against 100 %.  Fidelity is a diagnostic for the class kit, not a target.

Tuning is a bounded coordinate descent: only float knobs move, each within a
multiple of its authored value (probabilities/fractions/uptimes also clamp to
`[0, 1]`); integer mechanics (stack counts, knockdown uses) and boolean
mechanic flags are never touched, so the fit never invents a game rule.  It is
evaluated against the tool's optimized rotation (frozen once) and reports
suggested values rather than rewriting the kits — the KR gains are modest and
come mostly from slowing fillers to match KR's higher-level rotation, so the
remaining divergence is structural and the honest path is calibrating against
the player's own captures.  Since 0.2.307 most `TIMING` values are measured
(below), so a tuned `TIMING` suggestion points at a modelling gap, not at a
better action time.

### Measured action times (0.2.307)

`TIMING` was estimated until 0.2.307. It is now measured, for every key the
recordings time well, from the press sequences in the diagnostic captures (26 players
with 50 or more presses). A press is counted the way the log review
counts casts (`combat/actions.pressed`).

* **A skill's action time** is the median time from its press to that player's
  next press (gaps up to 1.5 s), plus the basic-attack steps woven in after it
  (next point), less the simulator's 30 ms latency, times 1.082 (the typical
  build's 8.2 % Combat Speed) for the value at 0 % Combat Speed. The players'
  own Combat Speed is not recorded. `calibrate.kit_action_time` does the
  conversion, and `calibrate --timings` suggests values the same way.
* **Basic attacks are woven between skills.** Every class but the Cleric presses
  a step of its three-step basic-attack chain (Keen → Rupture → Wrathful Strike,
  Flame Arrow → Burst → Pyroclasm and so on) between two skills and cancels it
  after 0.10–0.16 s; pressed back to back, the steps take 0.3–1.2 s each. A kit
  filler that stands for the basic chain takes the chain's own cadence: Gladiator
  Keen Strike 0.40, Sorcerer Flame Arrow 0.73, Chanter Onslaught 0.94, and the
  Assassin's Quick Slice, which lands all three steps in one cast, 1.93. A woven
  step's time goes to the skill it follows (0–0.15 s; Rending Blow 0.05 s on
  average); since 0.2.309 its damage is modelled too
  ([woven basic attacks](#woven-basic-attacks-02309)). The basic chain as a whole
  is 2.8 % of the Gladiator's KR damage, about 14 % of the Assassin's and 12 % of
  the Chanter's.
* **Charged skills count their charge:** the extra time into the press over the
  previous skill's usual gap, plus the release (Ranger Deadshot 0.72, Cleric Bolt
  1.56). The Sorcerer's Hellfire charge keeps its estimate, because the charge
  level is not recorded.
* **A chain step is its own press.** Where a kit folds a chain hit into its
  parent action, the parent also carries the chain press's measured time when
  the build takes the chain: Upward Strike 0.15 at Overhead Slam's chain chance,
  Tempest Arrow 0.24, Bursting Blow 0.82 every second Incandescent Blow,
  Piercing Strike 0.57. The Cleric's Discharge procs without a spec, so it is
  charged at its chance (0.80).
* **Thresholds.** A value needs 15 or more presses by at least two players, or
  20 or more where one player made nearly all of a class's presses (Cleric,
  Spiritmaster).
  Everything else keeps its estimate: the whole Templar kit (one player, at most
  18 presses a skill; measured since 0.2.315, see [The Templar from the log server's uploads](#the-templar-from-the-log-servers-uploads-02315)), Judgment Thunder (not pressed in the captures), Snipe and Cold Shock (only
  ever woven), and skills with too few presses. The Gladiator's "Remove
  cooldown" Overhead Slam cycle (`ASSUME`) is measured too: never under about
  1 s (10th percentile 0.97 s), not the ~0.65 s estimated from a 0.2.254 parse.

Effect on the calibration (optimized rotation, typical build, 180 s dummy). The
own-capture overlap compares the simulated damage shares with the captured
players' boss fights (the same captures the timings came from):

| Class | KR fidelity, before → after | Own-capture overlap, before → after |
|---|---|---|
| Assassin | 0.151 → 0.514 | 0.19 → 0.58 (4 fights) |
| Cleric | 0.417 → 0.433 | 0.50 → 0.52 (4) |
| Chanter | 0.868 → 0.871 | 0.55 → 0.53 (5) |
| Gladiator | 0.361 → 0.346 | 0.31 → 0.30 (7) |
| Sorcerer | 0.719 → 0.688 | 0.68 → 0.66 (5) |
| Ranger | 0.731 → 0.697 | no exported fight |
| Spiritmaster | 0.440 → 0.409 | 0.48 → 0.44 (2) |
| Templar | 0.177, unchanged | — |

The measured skills are faster than the estimates, so the simulation casts more
and the extra time goes to each class's filler. That exposed what the slow
estimates had absorbed: the Spiritmaster's Dimensional Control, Elemental Fusion
and summon presses (about a quarter of a recorded Spiritmaster's active time),
Smashing Blow (a free filler, although the game opens it only after Rending
Blow), the Cleric's Thunder and Lightning step and the damage of woven basic
attacks. 0.2.309 models them (next two sections). Re-fitting `ASSUME` to win the
fidelity back only pushed knobs to their bounds (for example halving the
parse-measured Assassin combo fractions), so it was not done.

### Kit gaps from the measured action times (0.2.309)

Measured from the same diagnostic captures, now with the pets' recorded casts
and hits, the recording player's MP readings and the boss fights' damage.

* **Spiritmaster: the summon cycle.** The recorded Spiritmasters press their four
  summons on cooldown (16–19 a minute, 0.24 a press). A summon's Spirit uses its
  skill about 0.3 s after the press (the skill the meter credits to the summon),
  and the Fire and Earth Spirits stay and use it again on the 3 s Spirit Skill
  Cooldown: per summon, 1.8 more uses for the Fire Spirit, 1.35 for Earth, 0.5
  for Wind and 0.15 for Water, with 0.85–3.3 basic attacks at about a tenth of
  the skill hit. Every Spirit skill opens Dimensional Control for about a second
  (97 % of the recorded presses come within 1 s of one) and adds an element; four
  grant Four Elements, which Elemental Fusion spends. Both are presses now (0.36
  and 0.34) instead of firing on their own, with their "Extra damage after 3s"
  specializations at the recorded size (0.36 and 0.24 of the hit), Elemental
  Fusion's 25 % regain and the Ancient Spirit's outright grants. The Ancient
  Spirit attacks through its 30 s (21 basic attacks, its skill every seventh)
  instead of casting every 3 s, Spirit's Descent procs on the caster's hits for
  10 s after a summon (30 s after the Ancient Spirit), and the caster's procs no
  longer fire on the Spirits' hits. A dummy-optimized rotation presses
  Dimensional Control about 33 times a minute: an attentive player's rate. The
  recorded players press it 15–18 times (they catch 75–83 % of the windows a
  summon opens but a third of the others) and KR's top players about 21.
* **Gladiator: Smashing Blow.** Smashing Blow follows 85–94 % of the recorded
  Rending Blows, at most 2.9 s later, and almost never comes without one, so it
  now needs Rending Blow's chain window. It restores no MP of its own: in the
  recording player's MP readings Rending Blow costs 94 and every basic-attack
  step returns 140–180, so the flat restore Smashing Blow carried is gone and the
  basic chain pressed on its own (Keen Strike → Rupture Strike → Wrathful
  Strike, one step a press) is the filler. Keen Strike's specializations ride its
  own step: on every press, the bundled build's "−1s Ruinous Blow cooldown on
  hit" had Ruinous Blow cast 4 times a minute for 48 % of the damage; the recorded
  Gladiators cast it 2.2–2.6 times, the model now 2.3.
* **Cleric: Thunder and Lightning.** The Cleric's basic chain is Earth's
  Retribution → Thunder and Lightning → Discharge. Thunder and Lightning follows
  88 % of the recorded Earth's Retributions at 1.09–1.16 times its damage (0.55
  a press). Condemnation's cooldown reset on a critical hit and Multi-Hit, and
  Chain of Torment's longer and faster damage over time are modelled too, since
  every top KR Cleric takes them; the reset follows the modelled crit chance,
  which for the median loadout is low (5 %).
* **Saved priority lists.** A kit can name essential actions (the Spiritmaster's
  summons, Dimensional Control and Elemental Fusion). A saved list with none of
  them was made before they existed, so the planner, the log review and the
  bundled results put them in front when they replay it; an older optimization
  keeps its pets.

Effect on the calibration (optimized rotation, typical build, 180 s dummy; boss
DPS of the bundled optimized build as the planner replays it):

| Class | KR fidelity | Own-capture overlap | Boss DPS |
|---|---|---|---|
| Spiritmaster | 0.409 → 0.753 | 0.44 → 0.73 (2 fights) | 12,977 → 14,325 |
| Gladiator | 0.346 → 0.462 | 0.30 → 0.45 (7) | 21,640 → 17,389 |
| Cleric | 0.433 → 0.446 | 0.52 → 0.52 (4) | 6,880 → 7,129 |
| Assassin | 0.514 → 0.495 | 0.58 → 0.56 (4) | 6,413 → 6,741 |
| Chanter | 0.871 → 0.841 | 0.53 → 0.50 (5) | 8,652 → 9,424 |
| Sorcerer | 0.688 → 0.686 | 0.66 → 0.70 (5) | 19,400 → 19,541 |
| Ranger | 0.697 → 0.629 | no exported fight | 10,035 → 10,095 |
| Templar | 0.177, unchanged | — | 10,968, unchanged |

The woven steps cost the Assassin, Chanter and Ranger some fidelity partly by
construction: basic-chain steps 2 and 3 are not catalog skills, so the KR side
drops them from its ceiling while the simulated side loses that share (taking
them out restores 0.01–0.02). The Ranger also presses Snipe on its own less,
because the woven steps return MP for Tempest Shot; that is the recorded
Rangers' pattern (Tempest Shot 63 a minute, Snipe on its own about 4), not
KR's.

### Woven basic attacks (0.2.309)

The measured action times already hold the woven steps' time, so the kits add
their damage and MP (`kit.common.add_weave`): after each press, the steps
recorded after that skill (15 or more presses), and after any other press the
median of the class's per-skill rates. The rate accumulates and each whole step
lands as one hit, so per-hit bonuses count once a step, and the steps are dealt
in their recorded mix (about 40 / 32 / 28 % for steps 1, 2 and 3). A step deals
its recorded damage per press against the first step, and restores the first
step's MP (the Gladiator's MP readings show every step returning at least that).

| Class | Woven steps after the main presses | Any other press | Steps 2 and 3 vs step 1 |
|---|---|---|---|
| Gladiator | Rending Blow 0.22, Smashing Blow 0.25, Overhead Slam 0.10 (+ Upward Strike 0.01), Ruinous Blow 0.13, Crushing Wave 0.53 (0.2.319; 0.38, 0.36, 0.17 + 0.12, 0 and 0.73 before) | 0.10 | 1.17, 1.60 |
| Assassin | Savage Roar 0.66, Insignia Explosion 0.04 | 0.04 | 1.49, 1.14 |
| Chanter | Incandescent Blow 0.72 (+ Bursting Blow 0.55), Dark Crush 0.50 (+ Piercing Strike 0.25), Rushing Smash 0.21 (0.2.319; 0.64 + 0.51, 0.43 + 0.16 and 0.07 before) | 0.09 | 1.19, 1.67 |
| Sorcerer | Ice Chain 0.39, Blaze 0.03, Firestorm 0.04 | 0.04 | 1.10, 1.40 |
| Ranger | Tempest Shot 0.32, Marking Shot 0.12 | 0.05 | 1.25, 1.45 (the others' average; no exported Ranger fight) |
| Spiritmaster | Combustion 0.34, Dimensional Control 0.09, summons 0–0.03 | 0.02 | 1.29, 1.45 |

The Cleric weaves almost nothing (8 steps in 873 presses), so its kit does not
weave; the Templar's does since 0.2.315 ([The Templar from the log server's uploads](#the-templar-from-the-log-servers-uploads-02315)). Steps after a Dodge (up to
40 % of a class's woven steps) are left out with the Dodge.

### The Cleric's Condemnation build (0.2.310)

Online Cleric guides build the class's damage around Condemnation, and the archived server logs and the
recorded Cleric show why. Earth Punishment's first specialization (stigma level 5) reads "[Condemnation]
lands as a Critical Hit on targets afflicted with [Earth Punishment]", and Condemnation's level-12
specialization resets its cooldown on a critical hit, so while Earth Punishment lasts Condemnation is pressed
back to back.

* **Guides.** A KR Inven PvE guide (16 April 2026) ranks Condemnation first (30 %+ of the damage, Judgment
  Thunder below 20 %, from over 50 % before Earth Punishment), takes Judgment Thunder to 16 for its extra
  Divine Punishment, Bolt's Skill Speed and +20 %, Earth's Retribution's specializations 2 and 3, Divine
  Aura's attacking speed and +3 s, and Chain of Torment's 2 and 4, with Light of Protection, Earth
  Punishment and Prayer of Amplification as the core stigmas. An older Inven guide (January 2026) already
  prefers Condemnation 20 to Judgment Thunder 20 "because of Earth Punishment". The global guides on
  GamesFuze, GAMES.GG and Mobalytics (October 2026) agree on Condemnation with Chain of Torment and
  Earth Punishment; PixelNitro (September 2026) still calls Judgment Thunder a core investment.
* **Server logs.** 92 % of the Condemnations landing within 2 s of an Earth Punishment tick crit (510 of
  554), against 21 % otherwise (159 of 769). Six of the 13 Clerics whose damage the logs hold carry Earth
  Punishment and five press Condemnation inside its windows (23–38 % of their damage); the other seven play
  the older Judgment Thunder build (26–45 % with Divine Punishment). Where the logs carry the chosen
  specializations (damage-over-time skill ids), nine of the 13 take Chain of Torment's 2 and 4, and most
  Divine Aura casts tick 13 times (both of its damage specializations).
* **The recorded Cleric** carries Earth Punishment at stigma level 15 or more and presses Condemnation 0.59
  times a second inside the windows, against 0.10 outside, in chains of 2.7 presses 0.51 s apart, broken by
  Dodges, heals and debuff refreshes.

The kit models Earth Punishment's hit and damage over time (the listed amount over 10 s, 20 s at level 20;
the logs show ten ticks of a tenth of the hit), Earth's Blessing (+10 % Double Chance from level 10, +10 %
Attack from 15) and the guaranteed crit; Condemnation's +12 %; Chain of Torment's PvE Damage Tolerance
reduction (5 %, +10 % with its specialization; it lowers the target's tolerance, never below zero); Divine
Aura's ticks (6, 8, 10 and 13 a cast for none, the speed, the duration and both specializations, as the
logs show, each a fifth of the listed damage); Bolt's Skill Speed, +20 % and crit; Debilitating Mark's
faster ticks; Prayer of Amplification's listed duration and specializations; and Light of Protection as an
aura left on (the recorded Cleric pressed it twice in 16 minutes). The optimizer now picks the guides'
build: Earth Punishment, Prayer of Amplification and Light of Protection, Condemnation's reset, Chain of
Torment's 2 and 4, Divine Aura's speed and duration and Bolt's speed and +20 %. The bundled Cleric build
reaches 16,342 boss DPS, Condemnation 47 % of it. Taking each new effect away from it:

| Without | Boss DPS |
|---|---|
| Earth Punishment's crit (stigma level 4) | −32 % (Condemnation 13.7 a minute instead of 37) |
| Condemnation's cooldown reset | −26 % |
| Chain of Torment's +10 % tolerance reduction | −7.5 % |
| Prayer of Amplification's Damage Boost | −7.2 % |
| Divine Aura's speed and duration | −5.6 % |
| Bolt's +20 % | −1.3 % |

This was a ceiling for a Cleric who does nothing but damage: the model fits about 19 Condemnations into a
10 s window, the recorded Cleric about 6 (up to 14) around its heals, and the server-log Clerics' median
boss DPS is 4,930 (the other classes' 7,600–13,600). Since 0.2.317 the boss scenario takes the heals'
recorded share of the time ([The Cleric's heals and basic chain](#the-clerics-heals-and-basic-chain-02317)).

### World PvP (0.2.310)

`--scenario pvp_world` (and **Optimize World PvP** in the app) optimizes for large fights. The damage side
is the PvP kit with three additions read from the tooltips: how many enemies a skill hits ("up to N
enemies"), how far it reaches ("a target within X m", else its radius around the caster) and its hard crowd
control (Stun, Knockdown, Airborne, Fear, Sleep, Frost: chance × duration, with the chosen specializations'
extra chance and duration; conditional clauses are left out). The objective is

    score = world DPS × (1 − exp(−x)),   x = ln 2 × (EHP / typical EHP) × (1.5 / attackers) / (1 − controlled)

| Assumption | Value |
|---|---|
| Enemies an area skill reaches | 3 |
| No enemy within reach | the last 3 s of every 10 s; only skills reaching 10 m or more can be used then |
| Players hitting you at once | 3 on a melee class (Gladiator, Templar, Assassin, Chanter), 1.5 on a ranged one |
| Typical build | survives half the fight when played by a ranged class without crowd control |
| Crowd control | takes away its share of the attackers' time, at most 50 % |
| Reference attacker | your class's typical build, a 200 % Attack + 1,000 hit |

Effective HP is HP over the share of the reference hit you take through the damage formula (Defense,
Critical Hit Resist, Critical Damage Tolerance, Damage Tolerance and PvP Damage Tolerance). The class base
comes from the class data; without recorded gear the loadout gets the median level-45 gear survival stats of
58 official profiles in the archived logs (`data/global/survival_medians.json`: about 4,400 HP and 7,100
Defense, plus Constitution, Life and Dexterity points). The board solver values HP, Defense and Critical Hit
Resist nodes by the survival they add; damage stats by their DPS times the share survived.

With these assumptions a melee class values survival more than a ranged one (a typical melee build survives
about 30 % of the fight, so each point of effective HP adds more), crowd control pays through survival, and
melee classes keep their gap closers and ranged skills for the out-of-reach windows. The Gladiator's World
PvP build takes Assault Strike, Fracturing Rush, Wrath Wave and Blade Toss, Mocking Blade's and Ankle Slice's
Knockdown specializations, every HP node and most Defense nodes (HP is its best stat); the Sorcerer's
leans on its area skills and takes every HP node too. Block, Evasion, Status Effect Resist, crowd-control
immunity, healing, shields, movement and player reactions are not modelled; these are assumptions, not
measurements, and are shown with every result.

### Bundled builds regenerated (0.2.311)

The bundled optimized builds (`results/compare/<class>`, the Sorcerer example in `results/sorcerer_l45` and
its variants) feed the planner, the log review's comparison with the optimum, the Advice page and the
server's canonical-preset seeds. Except the Cleric's (0.2.310), they were made before the measured action
times (0.2.307), the hit positions (0.2.308) and the kit gaps closed in 0.2.309 and 0.2.310. Every
consumer replays a saved build under the current model, so none of them used stale damage numbers, but the
builds themselves were no longer what the optimizer finds. 0.2.311 re-optimizes them with the comparison
settings: 203 skill points, 30 stigma points, 360 Daevanion points, the class's median global loadout and 2
optimizer iterations (3 for the Sorcerer example). Modeled boss DPS, and the KR share overlap of the new
build's dummy shares:

| Class | Old build, replayed | New build | Typical build | Gain | KR share overlap |
|---|---:|---:|---:|---:|---:|
| Sorcerer | 19,602 | 21,507 | 18,873 | +14.0 % | 71 % |
| Gladiator | 17,389 | 19,473 | 16,679 | +16.7 % | 29 % |
| Spiritmaster | 14,325 | 16,032 | 14,781 | +8.5 % | 47 % |
| Templar | 10,968 | 15,700 | 14,309 | +9.7 % | 12 % |
| Ranger | 10,095 | 12,175 | 10,701 | +13.8 % | 61 % |
| Chanter | 9,424 | 11,872 | 10,760 | +10.3 % | 35 % |
| Assassin | 6,741 | 9,346 | 8,009 | +16.7 % | 41 % |
| Cleric | 16,342 (0.2.310) | unchanged | 12,411 | +31.7 % | 71 % |

The Sorcerer example reaches 21,722 on median gear, 22,756 with 383 skill points and 31,547 on the
first-month upgrade gear.

The old Templar build replayed below its own typical build, the clearest sign of a stale optimum. Its new
build is the least certain one: its simulated damage shares overlap the Korean dummy logs least (12 %; the
typical build's 0.177 in the 0.2.309 table), so the kit's shares, not only its numbers, still differ from
real Templars. 0.2.315 measures the kit from five recorded Templars and fixes those shares ([The Templar from the log server's uploads](#the-templar-from-the-log-servers-uploads-02315)).

The integer program that buys Daevanion nodes and skill points stops at 120 s, and PuLP reports the best
board found by then as optimal. For most classes that board spends the whole budget. The Spiritmaster's
first solve stopped with only 195 of its 360 points spent, even with the machine to itself, and the
regenerated build fell to 12,687, below its typical build. The solver now spends what a stopped solve
left: it takes the cheapest connected path to the untaken node that adds the most value per point (stat
nodes by their stat value, skill-level nodes by their skill curve's next level, never past the curve's
end) until nothing affordable adds value. An optimal board has no such path and comes back unchanged. On
the 195-point board the step adds 165 points, and boss DPS rises from 12,687 to 15,246; the Spiritmaster
build above comes from the optimizer with this step.

Bundled PvP examples (`results/pvp`) are re-scored under the current evaluator: seven of eight score exactly
as when they were made (the PvP model has not changed for them). The Assassin's old allocation scores 8,249
(7,946 when made); a fresh search with the same two-search procedure finds 8,809 and replaces it.

The canonical preset model version moves to 0.3.6 without an evaluator change. A server keeps a comparison
scope's winner until the scope changes, so the new scope makes it re-seed from its stored winners and these
builds; a community winner that scores higher stays the winner.

### The Templar from the log server's uploads (0.2.315)

Until 0.2.315 one Templar had been recorded, too few presses to time, so the Templar kit kept its
estimates. Uploads from meter 0.2.306 or later carry every party member's casts. Four on the log
server hold five global Templars: 2,935 presses and 25 boss fights. A fifth upload was a second copy
of another's recording part and is left out (see [archive boundaries](#archive-boundaries-and-retention)).
What they show, and what the kit does about it:

* **The basic-attack chain is woven, never pressed on its own.** A Vicious Strike, Decisive Strike or
  Desperate Strike step comes about 0.10 s before the next skill (620 woven steps); pressed back to
  back, the chain made 14 steps in all, about 0.54 s a step. The kit dealt all three steps in one
  0.8 s action, which outdamaged every other press, so the optimized rotation pressed nothing else:
  its Judgment share was 0 %, against 21 % in the recorded fights and 42 % in the KR logs. The chain
  is now one step a press, like the Gladiator's (the 0.55 s step time was an estimate from those 14
  steps; since 0.2.317 it is 0.46 s, measured from 26 steps by six Templars), and its steps are woven
  after each press at the recorded rate: Pummel 0.53, Punishing
  Strike 0.49, Shield Rush 0.26, Poach 0.24, Judgment 0.19, Punishment 0.17 and any other press 0.17.
  The steps come in their recorded mix (38 / 33 / 29 %) at 1.18 and 1.41 times Vicious Strike a press
  (0.2.256's parse had 1.20 and 1.54).
* **Pummel is three strikes, and Punishing Strike is its chain press.** Every recorded Pummel lands
  three hits on a boss about 0.1 s apart. Each is 0.46–0.48 of a plain Vicious Strike (the four
  Templars with enough of both), close to the third of the tooltip that three strikes imply, so the
  tooltip is the damage of the whole press.
  Punishing Strike (skill 12060000) is 14 % of the recorded Templars' damage and 21 % of the KR
  logs'; the client data names it only in Pummel's specializations. 96 % of its presses come within
  3 s of a Pummel, often with Judgment, Shield Smite or Warding Strike pressed in between. Its plain
  hits are 3.52 times one of Pummel's strikes (3.50–3.58 across the five Templars), 1.17 times a
  whole Pummel. It is now a press that needs Pummel's chain window and spends it. Pummel also costs
  its 120 MP (96 with its first specialization), which the kit had left out. No recorded Templar has
  Pummel at 16, where "[Punishing Strike] grants extra damage on hit" unlocks, so that
  specialization adds the kits' usual 30 % for an "extra damage" that names no number.
* **Judgment windows.** 94 % of the Judgments after a trigger come within 2 s of Shield Smite,
  Warding Strike, Shield Rush or Doom Shield, and 99 % within 3 s. The windows now come from the
  tooltips: 2 s, and 3 s for Doom Shield. The kit described Doom Shield's Judgment trigger and
  knockdown but never applied them; it does now. Recorded Templars press Judgment in 59 % of the
  windows; the model uses every one.
* **Punishment is charged fully.** Its hits are 16–18 times a plain Vicious Strike, which only the
  full charge reaches. The charge takes 0.95 s before the 0.50 s release, so its action time is 1.56
  (the estimate was 1.20).
* **A specialization mix-up.** "−2s [Warding Strike] cooldown on hit" is Vicious Strike's fourth
  specialization. The kit had given it to the second, which absorbs HP.

Action times at 0 % Combat Speed, by the rules of [measured action times](#measured-action-times-02307)
(median press-to-next-press time up to 1.5 s plus the steps woven after it, less the 30 ms latency,
times the typical build's 1.082):

| Skill | Presses (players) | Measured | `TIMING` | Before |
|---|---:|---:|---:|---:|
| Pummel | 544 (5) | 0.613 s | 0.63 | 0.90 |
| Punishing Strike | 495 (5) | 0.557 s | 0.57 | — |
| Judgment | 258 (5) | 0.549 s | 0.56 | 0.70 |
| Shield Smite | 136 (4) | 0.348 s | 0.34 | 0.90 |
| Warding Strike | 97 (5) | 0.352 s | 0.35 | 1.00 |
| Annihilate | 72 (5) | 0.350 s | 0.35 | 1.00 |
| Shield Rush | 43 (5) | 0.326 s | 0.32 | 0.90 |
| Debilitating Smash | 36 (3) | 0.519 s | 0.53 | 0.90 |
| Punishment | 42 (5) | 0.95 s charge + 0.52 s | 1.56 | 1.20 |
| Doom Shield | 57 (4) | 0.352 s | 0.35 | 1.00 |
| Taunt | 56 (4) | 0.601 s | 0.62 | 1.00 |
| Other stigmas, pooled | 144 (5) | 0.409 s | 0.41 | 1.00 |
| Poach | 34 (4) | 0.494 s | 0.50 | generic |
| Vicious Strike, one step | 14 steps (4) | 0.541 s | 0.55 | 0.80 for all three |

Effect on the calibration (optimized rotation, typical build, 180 s dummy) and on the bundled build
(boss DPS as the planner replays it; the share overlap is with the 25 recorded boss fights, the
catalog skills only, and in brackets by name with Punishing Strike and the chain steps counted):

| | Before | After |
|---|---:|---:|
| KR fidelity | 0.177 | 0.543 |
| Own-capture overlap | 0.17 (0.27) | 0.54 (0.64) |
| Bundled build, boss DPS | 15,700 (8,386 under the new kit) | 14,785 (typical build 13,029) |
| Bundled build, KR share overlap | 12 % | 44 % |

The bundled build is re-optimized with the [0.2.311 settings](#bundled-builds-regenerated-02311). Its
boss shares are Punishing Strike 18 %, Judgment 17 %, Pummel 16 %, the woven steps 15 %, Punishment 9 %
and Annihilate 9 %, against 14, 21, 13, 15, 10 and 6 % in the recorded boss fights. The KR logs' larger
Judgment share needs Judgment's cooldown removal (its level-16 specialization, taken by every KR
Templar), which the typical build behind the fidelity number does not have. Still estimated: the MP
that steps 2 and 3 restore (none of the recorded Templars made the recording, so their MP readings
are not in the logs; 0.2.317's uploads have none either), and Threatening Blow, which no recorded
Templar took. The step time is measured since 0.2.317: pressed back to back, six Templars made 26
steps, a median 0.452 s apart (quartiles 0.42 and 0.56), so `TIMING["vicious_strike"]` moves from 0.55
to 0.46. The bundled build never presses the chain on its own, so it stays at 14,785; the typical
build's KR fidelity moves from 0.543 to 0.540 and the own-capture overlap from 0.53 to 0.52 (34
fights). The canonical preset model version moves to 0.3.7, so a server re-seeds the comparison scopes from
its stored winners and the regenerated builds under the new kit.

### The Cleric's heals and basic chain (0.2.317)

Until 0.2.317 the Cleric kit left heals out, so its modelled boss DPS was a ceiling for a Cleric who
never heals. The log server's uploads from meter 0.2.306 or later hold 61 boss fights of 14 Clerics
(128.5 minutes, all expedition bosses; a fight several party members uploaded counts once). What they
show:

* **Heals take about a tenth of a Cleric's pressing time.** The Clerics press a heal (Healing Light,
  Light of Regeneration, Radiant Recovery, now and then Absolution or Benevolence) 4.6 times a minute:
  587 presses; the median fight 4.45 a minute, the quartiles 1.3 and 7.6. Counting each press as
  holding the time to the next one (up to 1.5 s), heals take 9.5 % of the Clerics' pressing time (the
  Chanters' 2.5 %, the Templars' 0.5 %, the other classes' none), dodges 13 % and the support skills
  (Light of Protection, Yustiel's Power, Defiance, Salvation, resurrection) 3 %. A heal press takes
  0.45 s by the rules of [measured action times](#measured-action-times-02307) (475 presses). The
  Clerics heal as often inside Earth Punishment's windows (4.3 a minute) as outside them (3.7).
* **Every class spends 28–43 % of a boss fight not pressing anything** (the Cleric 39 %), and dodges
  take 8–23 % of its pressing time. The model has neither for any class, so its DPS is a rotation's,
  not a whole fight's.
* **The windows hold fewer Condemnations by the players' choice.** The Clerics who play the build
  (their Condemnations crit 80 % of the time or more inside the windows; 78 windows) press
  Condemnation 0.57 times a second while Chain of Torment is up, and press Judgment Thunder there
  224 times against Condemnation's 326, though a Condemnation there deals 11,863 a press against
  Judgment Thunder's 8,586 with Divine Punishment, in a shorter action. The reset does not hold them
  back: a Condemnation's hit lands 0.35 s after the press, inside its 0.52 s action, and the quickest
  tenth of the back-to-back presses after a critical hit are 0.57 s apart.
* **Earth's Retribution is never pressed twice running.** Of 880 presses followed by another within
  3 s, none was Earth's Retribution again, and with no Thunder and Lightning between them two were
  always 3.15 s or more apart (169 pairs): while its chain window is open, the basic chain sits on
  Thunder and Lightning. The kit allowed the repeat, so the build re-optimized with heals, which has
  Earth's Retribution's "−7s [Bolt] cooldown on landing [Discharge]", pressed it back to back and left
  Thunder and Lightning out.

The kit now spreads the heals' time over every other press in a boss fight: 4.6 a minute at 0.45 s,
3.4 % of the time at the typical build's Combat Speed, so each press takes 1/(1 − 0.034) as long
(`Action.heal`, `Target.party_damage`). That is what a heal at an unknown moment costs on average:
heals pressed on a fixed schedule moved the bundled build's DPS by 2.5 % depending on whether they fell
inside an Earth Punishment window, which the optimizer could have exploited. A training dummy deals no
damage, so there the Cleric never heals, and the KR fidelity (scored on a dummy) does not move.
`ASSUME["heals_per_minute"] = 0` gives back a Cleric doing nothing but damage. Earth's Retribution now
waits while its chain window is open, until Thunder and Lightning spends it or it lapses; the old
bundled build's rotation already alternated the two and is unaffected.

| | Before | After |
|---|---:|---:|
| Bundled build, boss DPS | 16,342 | 15,671 replayed, 15,937 re-optimized |
| Typical build, boss DPS (optimized rotation) | 12,411 | 12,137 |
| Condemnations per Earth Punishment window, bundled build | 11.4 | 11.7 (the recorded build: 4.2) |
| Bundled build, KR share overlap | 71 % | 72 % |

The re-optimized build (the [0.2.311 settings](#bundled-builds-regenerated-02311)) keeps its skills
and stigmas and changes three specializations and the Daevanion board (38 nodes out, 37 in): Earth's
Retribution's +20 % Discharge chance instead of +50 % Multi-Hit, and a stun the model gives no effect
on Bolt and on Debilitating Mark, in place of Bolt's +30 % Skill Speed (0.6 % lower here: the faster
charge shifts the rotation) and Debilitating Mark's MP (the Cleric's MP never runs short). The canonical preset model
version moves to 0.3.8, so a server re-seeds the comparison scopes from its stored winners and the
regenerated build.

### The Gladiator and the Chanter from the log server's uploads (0.2.319)

The log server's uploads from meter 0.2.306 or later and the nine logs of 18 October hold, with cast
records, 45 boss fights of 7 Gladiators (115 minutes) and 175 boss fights of 14 Chanters (348 minutes);
a fight several party members uploaded counts once. Two Gladiators and two Chanters made recordings,
so their MP readings are there too (103 and 230 fights), and the uploads carry each player's official
profile. The kits are measured against them as the Templar's was in 0.2.315, per press and on bosses:

* **Damage a press.** A hit's damage without its critical, double or perfect roll ("plain"), times
  the hits a press: the ratio of two skills' values cancels the player's gear and the boss's
  defences. With the profile's Attack and skill levels, the same ratio can be set against the two
  skills' tooltips.
* **Two records, one tooltip.** Overhead Slam, Rending Blow, Smashing Blow, Leaping Slam, Incandescent
  Blow and Onslaught land each press as two equal records within 0.25 s. Both are damage: on 169 bosses
  with HP readings the recorded damage matches the HP lost (median ratio 1.000) whatever share the
  second records make of it (5–25 %). Together they deal the tooltip once: at each player's own level
  and Attack, Rending Blow lands 0.93 and Leaping Slam 0.87 of its tooltip for Overhead Slam's 1.00, and
  the Chanter's skills 0.89–1.14 for Incandescent Blow's. The 0.2.254 parse that set Upward Strike at
  2.09 times Overhead Slam counted one of Overhead Slam's two records.
* **Certain crits.** Four Gladiators' Overhead Slams crit every time ("Critical Hit on hit"), and
  the two of them with its chain crit on every Upward Strike too; 16 of 20 Chanters' Dark Crushes crit
  every time, and so do the Piercing Strikes of those with the chain, and two Chanters' Spinning Strikes
  ("lands as a Critical Hit"). No Gladiator's Ruinous Blow crits every time, so its "+30% Skill
  Critical Hit" is now 30 % more Critical Hit for that skill, not a certain crit.
* **MP.** In the recording players' readings a press changes MP by the same amount every time, and
  over the fights the MP gained and spent balance (the Gladiators 4,362 and 4,387 a minute, the
  Chanters 3,145 and 3,192).

The Gladiator:

| | Recorded | Kit before | Kit now |
|---|---|---|---|
| An Upward Strike press, against an Overhead Slam press | 1.08 | 2.09 | 1.08 |
| Upward Strike after Overhead Slam, with the chain taken | 89–97 % | 50 % | 90 % |
| A Smashing Blow press, against an Overhead Slam press | 0.47 | 0.54 | 0.47 |
| A Ruinous Blow press | 1.33 of its tooltip for Overhead Slam's 1.00 | three strikes | one strike (1.3 with the extra-damage spec) |
| Rage Burst's hit | 0.24 of its tooltip, as above | the tooltip | 0.25 |
| A basic-chain step | 0.65 of Keen Strike's tooltip, as above | the tooltip | 0.65 |
| Destructive Impulse on a boss | none in 115 minutes, nor in the KR dummy logs | half the hits (1 s apart) | none |
| MP a press | Rending Blow and Smashing Blow −93, Overhead Slam and Upward Strike +50, a basic step +180 | Rending Blow −96, Smashing Blow and Overhead Slam 0, a step +120 | as recorded |
| Steps woven after Rending Blow, Smashing Blow, Overhead Slam | 0.22, 0.25, 0.10 | 0.38, 0.36, 0.17 | as recorded |

The two Gladiators with "Remove cooldown" send no cooldown for Overhead Slam and press it 0.95–0.98 s
apart at the 10th percentile, as the kit's 1 s cycle has it. Smashing Blow now comes before Rending
Blow in the default priority: it is there only in Rending Blow's chain window and costs the same MP.

The Chanter:

| | Recorded | Kit before | Kit now |
|---|---|---|---|
| Incandescent Blow | no cooldown, 12.9 a minute, a median 1.6 s apart | every 6 s at most, no MP cost | its MP cost only |
| Bursting Blow after Incandescent Blow | 84–97 % for every Chanter: the skill's own chain | every 2nd, with a specialization | 90 % |
| A Bursting Blow press, against an Incandescent Blow press | 1.19, MP −95 like Incandescent Blow | 2.23, free | 1.19, the same MP |
| Piercing Strike after Dark Crush, with the chain taken | 92 %, 1.52 times a Dark Crush press | always, 1.65 | 92 %, 1.52 |
| Dark Crush with "Removes [Dark Crush] cooldown" | 0.6 s apart in a window, 13–19 a minute | its 5 s cooldown | back to back in a window |
| Marchutan's Wrath | opens Dark Crush for 3 s (its tooltip) | did not | does |
| Wind's Promise | 7.1 hits a minute; the Chanters crit about 20 % | its 50 % of a 60 % crit rate | its 50 % of the hit's own crit chance |
| Raging Spell on a boss | 2.0 a minute, 98.8 % of them crits | half the hits (1 s apart) | about 2 a minute, crits |
| Heals | Recuperation 1.2 a minute, 0.56 s a press | none | as the Cleric's (`Action.heal`) |
| Undefeated Mantra | 0.1 presses a minute: a toggled aura, its tooltip gives no duration | a 10 s buff re-pressed every 5 s, a tenth of the fight | pressed once |
| Steps woven after Incandescent Blow (with Bursting Blow's), Dark Crush | 1.22, 0.50 | 0.64 (+0.26 with the spec), 0.43 | as recorded |

Spinning Strike's specializations count too: −5 s (its game cooldown is 24.5 s), up to +20 % on fewer
targets and the certain crit; so do Incandescent Blow's −20 % MP and up to +12 % on fewer targets, and
Impactful Crush's +30 % Skill Speed.

Effect on the calibration (optimized rotation, typical build, 180 s dummy, as before), on the overlap
with the recorded boss fights (the catalog skills only, and by name with the chain and basic steps
counted) and on the bundled builds (boss DPS as the planner replays them):

| | Gladiator, before → after | Chanter, before → after |
|---|---:|---:|
| KR fidelity | 0.462 → 0.516 | 0.841 → 0.534 |
| Own-capture overlap, catalog skills (182 and 270 fights) | 0.425 → 0.432 | 0.474 → 0.402 |
| Overlap by name, typical build on the dummy | 0.594 → 0.608 | 0.523 → 0.702 |
| Overlap by name, typical build with its best specializations in a boss fight | 0.408 → 0.719 | 0.628 → 0.738 |
| Bundled build, boss DPS | 19,473 → 13,017 replayed, 13,063 re-optimized | 11,872 → 13,485 replayed, 20,469 re-optimized |

Bursting Blow, a fifth of the recorded Chanters' damage, is not a catalog skill, so neither the
catalog overlap nor the KR fidelity can count it; and the KR dummy logs press Incandescent Blow far
less (6 % of their damage) and put 43 % on skills the global data lacks. By name the model now matches
the recorded Chanters much better. The model still presses more than any player: every class spends
28–43 % of a recorded boss fight pressing nothing ([The Cleric's heals and basic
chain](#the-clerics-heals-and-basic-chain-02317)), and the bundled builds press Rending Blow 50 times a
minute where the recorded Gladiators press it 20, and Incandescent Blow 40 where the Chanters press it
13; over the 180 s fight the Chanter's starting MP pays for the difference. Still estimated: Murderous
Burst's rate (8.8 a minute in the recorded boss fights, about 19 in the model at the 0.2.254 dummy
parse's one per 3 s), and Ankle Slice, Heat Wave Blow, Wave Blow and Tremor Crush, which the recorded
players rarely press. The canonical preset model version moves to 0.3.9, so
a server re-seeds the comparison scopes from its stored winners and the regenerated builds.

### The Templar guide checked against the recorded Templars (0.2.320)

A Templar guide (the transcript of a video, supplied with this release) gives the specializations,
stigmas, passives and macro it plays for boss damage. The bundled build disagreed with most of them:
it took neither of the guide's two must-take stigmas, spent its specializations on MP and pressed no
Warding Strike. Each difference was checked against the tooltips and the log server's uploads: the
official profiles of 12 Templars (their stigmas and skill levels; a profile lists no specializations)
and 29 boss fights of 7 Templars with casts.

* **Taunt and Noble Armor.** The kit counted Taunt's hit only, and Noble Armor only raised HP. From
  stigma level 5 Taunt's Shrink lowers the target's PvE Damage Tolerance by 10 % for 15 s (20 s at 20,
  and 5 s off Taunt's cooldown at 15). Noble Armor multiplies Insulting Roar's Attack (from level 10)
  and Fury (from 15) by 1.5 for its 120 s. 9 of the 12 Templars equip Noble Armor and 5 Taunt.
* **Fury's block buff.** Fury gives the Templar and the party a PvE Damage Boost on Block for 20 s. It
  is up 33 % of a boss fight on the Templars (29 fights) and 29 % on the party members recording
  beside one (31 fights, 9 Templars). The model counts it at 30 % in a boss fight. A training dummy
  never attacks, so there it never counts.
* **Shield Rush only after a dodge.** Its tooltip makes it usable only "after using [Dodge] or while
  flying". The Templars press it 0.93 times a minute of boss fight (against 4.5 dodges), and the model
  pressed it on cooldown, 6.3 times. It now comes no oftener than recorded.
* **Annihilate on a boss.** Its third specialization, "+100% damage to targets with Incapacitated
  Immunity", applies to a dungeon boss. A plain Annihilate hit on a boss equals 14–19 plain Pummel
  strikes in 12 of 18 Templar boss fights, and 8–10 in 4: twice as much for most Templars. Against the
  tooltips at each player's own levels and Attack, Annihilate delivers 1.89 times what Pummel does (5
  fights with a profile, all single hits). Annihilate's tooltip also gives it "a 5% chance to trigger
  when attacking a target with Incapacitated Immunity", and 30 % of the recorded Annihilates (104
  presses) follow no stun of the Templar's own in the 4 s before. The model keeps Annihilate behind
  the Templar's own stuns, which already let it press Annihilate 6.3 times a minute against the
  recorded 1.7. With the specialization it doubles the hit in a boss fight
  (`ASSUME["boss_incap_immune"]`) but not on a dummy.
* **Punishment's damage over time.** Its second specialization ticks 6 times on each target a press
  hits, 0.5 s apart over 3 s. Each tick is 0.076 of the press's plain hit (44 presses in the 11 boss
  fights of Templars who take it), and no tick crits. In those fights it adds 29 % to Punishment's
  damage. The kit left it out.
* **Judgment's "Extra damage on hit"** delivers 1.29 times its tooltip against Pummel (9 fights), as
  the kit's 30 % for an unquantified "extra damage" has it.
* **A woven Vicious Strike is a Vicious Strike.** Its +50 % Multi-Hit and its −2 s Warding Strike
  cooldown now apply to the woven first steps too, and Pummel's "−1s [Punishment] cooldown on hit" is
  applied. The kit described both and applied neither.
* **MP.** The model's Templar ran out of MP: its lowest reading in a boss fight was 95 of 4,700. So
  the optimizer took Vicious Strike's +20 % MP restored and Shield Smite's free cast, and pressed no
  Warding Strike: added to that build it cost 3 % of the boss DPS. The guide takes neither
  specialization. No Templar has made a recording, so no Templar MP readings exist. The Templar's MP
  layout is the Gladiator's: a basic step whose tooltip says "Restores 100 MP", the same +20 % and −20
  % MP specializations and the same Daevanion MP nodes. The recording Gladiators' readings rise 150 a
  step ([0.2.319](#the-gladiator-and-the-chanter-from-the-log-servers-uploads-02319)), so the
  Templar's step now restores 150 (`ASSUME["step_mp"]`; it was the tooltip's 100). This is an
  inference until a Templar records.

The guide, the recorded Templars and the bundled build (two specialization slots below skill level 20):

| | Guide | Recorded Templars | Bundled build before | Bundled build now |
|---|---|---|---|---|
| Stigmas | Taunt and Noble Armor; Battlefield Banner, Shield of Protection or Doom Shield | equipped: Doom Shield 9 of 12, Noble Armor 9, Battlefield Banner 7, Empyrean Lord's Punishment 6, Taunt 5, Nezekan's Shield 4, Shield of Protection 3, Executing Blade 1 | Assault Fury 5, Doom Shield 10, Executing Blade 7, Battlefield Banner 1 | Taunt 5, Noble Armor 10, Executing Blade 7, Comrade in Arms 1 |
| Vicious Strike | 3, 4 | level 14 (median) | 1, 2 | 1, 3 |
| Pummel | 3, 4 | 14 | 1, 3 | 3, 4 |
| Judgment | 3, 4 (3, 5 at 16) | 15 | 3, 4 | 3, 4 |
| Punishment | 2, 3 | 14 | 1, 3 | 2, 3 |
| Annihilate | 3, 4 | 14 | 1, 4 | 3, 4 |
| Shield Smite | 3, 4 | 13 | 2 | 2 |
| Warding Strike | 1, 3; pressed in the macro | 13.5; 2.1 presses a minute | 2; 2 presses a minute | 1; 2.7 presses a minute |
| Shield Rush | 2, 4; only after a dodge | 0.93 presses a minute | 1, 4; 6.3 a minute | none; 1 a minute |
| Damage passives | Fury, Insulting Roar, Punishing Benediction, Impact Hit | | the same four, Fury 7 | the same four |

Effect on the calibration (optimized rotation, typical build, 180 s dummy) and on the bundled build:

| | Before | After |
|---|---:|---:|
| KR fidelity | 0.540 | 0.516 |
| Own-capture overlap (51 fights) | 0.525 | 0.537 |
| Typical build, optimized rotation, boss DPS | 13,029 | 16,903 |
| Bundled build, boss DPS | 14,785 (14,749 under the new kit) | 20,293 |
| Bundled build, KR share overlap | 44 % | 39 % |

Switched off one at a time on the new build, Annihilate's +100 % on a boss is worth 6.3 % of its boss
DPS, Punishment's damage over time 5.7 %, Taunt's Shrink 5.3 %, the 150 MP a step 4.9 %, Fury's block
buff 3.4 % and Noble Armor's ×1.5 2.9 %. The old build barely moves (it gains Fury's block buff and
loses its six Shield Rushes a minute). The KR fidelity falls because the KR dummy logs put 42 % of
their damage on Judgment with its cooldown removed, and capping Shield Rush takes Judgment windows
from the typical build, which has no "Remove cooldown".

What still differs from the guide:

* **Judgment's share.** The guide puts Judgment at 35–40 % of a Templar's damage from level 16, where
  "Remove cooldown" unlocks. The bundled build has Judgment at 14 and puts 9.9 % on it. The same build
  with Judgment at 16 and its third and fifth specializations, pressed first as in the guide's macro,
  puts 34.5 % on Judgment. At 20 with all three it puts 44.7 %, against 42 % in the KR logs.
* **The last two stigmas.** Within the build's 30 stigma points Noble Armor 15 (35 points) is out of
  reach. The optimizer fills the other two slots with Executing Blade (1 of the 12 recorded Templars
  equips it) and Comrade in Arms at level 1, a defensive stigma. Doom Shield, Shield of Protection or
  Battlefield Banner in their place cost 0.3–1.3 % of the modelled boss DPS. Banner's own effect
  ("Increases Attack proportional to Defense") gives no number and is left out. Shield of Protection's
  guaranteed Block feeds Fury's block buff, which the model counts at its recorded uptime whatever the
  stigmas.
* **Vicious Strike's and Shield Smite's MP specializations.** The bundled build presses Annihilate 6.3
  times a minute (recorded: 1.7), Punishment 3.7 (1.1) and Pummel 37 (12): its main skills 1.6 to 3.7
  times as often as the recorded Templars, as for every class ([The Cleric's heals and basic
  chain](#the-clerics-heals-and-basic-chain-02317)). That much pressing needs the MP.
* **Not modelled:** Shield Smite's "50% chance to trigger [Debilitating Smash]", Debilitating Smash's
  −25 % Defense (the guide notes that bosses have almost none; the model gives them none) and
  Annihilate's 5 % trigger on an immune target.

The canonical preset model version moves to 0.3.10, so a server re-seeds the comparison scopes from its
stored winners and the regenerated builds under the new kit.

### Chain, variant and combo skills, and known catalog gaps

metabot's build-planner page exposes 35 skills per class. Several real skills
are **not** in that list: the game logs them under their own skill id, but
metabot only names them inside a parent skill's specialization text — a chain
(`Adds [X] Chain Skill`), an "on landing [X]" variant, or an unlisted basic-combo
step. A generic reading can only simulate what is in the catalog, and a
hand-written kit that models a parent skill directly used to *drop* that parent's
chain/variant entirely (the generic chain reader only fires for skills the kit
leaves to it). So these skills were invisible to the optimizer, which both
undervalued DPS and over-weighted the fillers that expanded to fill the idle
time the missing skills should have occupied.

Community level-45 training-dummy and raid parses (A2Parser captures) measure each
such skill's coefficient as a ratio to a modelled parent (non-crit damage per hit,
which cancels crit-rate and gear). The ratios drive the per-class knobs added in
0.2.256:

| Class | Added / fixed from parses | Measured ratio |
| --- | --- | --- |
| all | `Adds [X] Chain Skill` finishers (generic + kit `chain_frac`) | 1.5x base (was 0.60/0.85; measured 1.38–2.1) |
| Chanter | Piercing Strike (Dark Crush chain), Bursting Blow (Incandescent Blow variant) | 1.65x, 2.23x (1.52x and 1.19x a press, after 92 % and 90 % of the presses, from 14 recorded Chanters, 0.2.319) |
| Cleric | Divine Punishment (Judgment Thunder companion), Discharge coefficient | 1.09x, 1.5x |
| Assassin | Quick Slice basic combo (Swift + Breaking Slice); Savage Roar demoted to a cadenced upkeep skill | 0.67x, 0.76x |
| Templar | Vicious Strike combo (Decisive + Desperate Strike) | 1.20x, 1.54x (1.18x, 1.41x a press from five recorded Templars, 0.2.315) |

**Still flagged for a gear-matched capture** (measured ratios recorded in the kit
notes / `ASSUME` for when one is available, not yet modelled):

* **Templar** — modelled since 0.2.315: Punishing Strike is Pummel's chain press and
  Pummel's tooltip is the damage of three strikes ([The Templar from the log server's uploads](#the-templar-from-the-log-servers-uploads-02315)).
  Since 0.2.320 a basic step restores the Gladiator's measured 150 MP (no Templar has made a recording;
  [The Templar guide checked against the recorded Templars](#the-templar-guide-checked-against-the-recorded-templars-02320)).
* **Assassin** — Savage Smash (~6%, 3.3x Quick Slice) and Savage Back Kick (~6%,
  1.45x), and Heart Gore's cadence (under-cast vs parses).
* **Spiritmaster** — the Spirits' cadence is measured per summon from two
  players' boss fights (0.2.309). The KR logs (a dummy, higher levels) show far
  larger Spirit basic-attack and Ancient Spirit shares, and the model presses
  Dimensional Control at an attentive player's rate.
* **Cleric** — since 0.2.310 the Condemnation crits come from Earth Punishment
  (see *The Cleric's Condemnation build*), and the optimizer suggests the build
  the guides and five of the 13 server-log Clerics play; the other eight lean on
  Judgment Thunder (27 % of the server-log Clerics' damage with Divine
  Punishment, close to the model's 30 %). Since 0.2.317 its heals take their
  recorded share of a boss fight (see *The Cleric's heals and basic chain*).
* **Sorcerer** — Burst / Pyroclasm / Cold Wave are partly covered by the Flame
  Arrow chain multipliers; a dedicated capture would refine them.
* **Gladiator** — the MP economy is measured since 0.2.319 from two recording
  Gladiators' readings: Rending Blow and Smashing Blow cost the same, Overhead Slam
  and Upward Strike restore 50 a press and a basic step 180 with its specialization
  (150 without; [The Gladiator and the
  Chanter from the log server's uploads](#the-gladiator-and-the-chanter-from-the-log-servers-uploads-02319)).
* DoT ticks already modelled as their parent skill (Debilitating Mark, Chain of
  Torment, Poison) and consumable **theostone** procs are intentionally not
  class-skill damage.

As always this is a diagnostic, not a target: the honest path for any single
character is calibrating against that player's own captures.

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
5. **Daevanion + skill points** – one integer program (PuLP with the
   in-process HiGHS solver): node choices with flow-based connectivity per
   board, the 360-point budget, the 203 SP budget with the real price table,
   and ordered "level ≥ k" indicators so specialization breakpoints
   (non-concave value jumps) are handled exactly.  The solve stops after
   120 s and often gets there, returning the best allocation found so far,
   which on a busy machine could leave much of the board unspent.  So it
   starts from the current allocation, completed first: unspent points go
   along the cheapest connected path (by node cost) to the node worth most per
   point (stat nodes by their stat weights, skill nodes by the next level's
   gain on the skill's curve, never past its end), and the skill points are
   retrained for that board (an exact knapsack over the SP budget), until
   neither adds value.  The result is never worth less to the program than
   that start, and the solver's own result is completed the same way; points
   nothing of modeled value can use then go on nodes with no modeled effect
   (defensive stats in PvE), as skill points still left after step 6 go to
   DPS-neutral levels.  The log says when the solve stopped at its time
   limit, with the remaining gap to the solver's bound on the best allocation.
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

Community comparison policies, generation and server evaluation use bundled class, hit-profile and common-loadout data. Local synchronized copies continue to supply personal planning. Their loader caches are separated, and comparison scope is restored after each call; user settings and storage remain available. Actual model/data mismatches still reject submission and identify the differing policy fields.

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

### Genus coverage and candidate evaluation

Advice and character optimization share effect validation and mode/primary-stat filters. Advice includes saved modeled Genus stats in its base loadout. Per-line contributions remove one modeled line without changing rotation; unsupported/defensive effects have no damage estimate. Single-slot candidates replace the old line in an unlocked catalog damage slot; missing target lines require an explicit empty-slot assumption. No synthetic tenth slot, additive candidate total, ownership, reroll cost or defensive equivalence is inferred. Five-genus coverage retains missing levels/lines distinctly from zero and known locked slots.

Point budget provenance separates observed allocations, selected available totals and assumed unspent balances. Current profile allocations, saved user totals and level-based examples do not establish maximum progression or available unspent points. Personal saved results retain these assumptions alongside the Genus snapshot.

## Recorded combat pressure

Encounter insights use normalized retained effects. For each friendly source/recipient and metric, a rolling window finds the greatest gross amount over 1, 3 and 5 seconds, including both endpoints; equal maxima keep the earliest ending window. Window starts are clipped to encounter start or the latest recorded actor death. Effects exactly at that actor's death timestamp are excluded from windows because same-time ordering is unknown. Missing death markers can join lives; missing packets or attribution can understate amounts. Incoming ability totals include all retained in-range damage, including death-time effects, and do not infer killing blows or avoidability.

Incoming windows report recorded healing received separately, without subtraction or effective-healing claims. Imported buff intervals are clipped and unioned per recipient/buff; overlapping damage includes that recipient's own outgoing effects in half-open intervals `[start, end)`. Pets remain separate, and overlapping buffs can each contain the same damage. This establishes temporal overlap rather than causal buff contribution. Each detailed section is capped at 100 rows before display filters and exposes omissions. Evidence coverage reports retained counts and unsupported protocol fields; zero records do not prove absence. Derived summaries do not change ranking eligibility, comparisons or optimizer learning.

## Damage optimization with an HP reserve

My Character → **Survivability** preserves the character's imported flat **HPMax** contribution from the four optimized crystal boards by default. The existing DPS objective stays primary inside the set of allocations meeting this floor. Skill, stigma and Daevanion budgets and board connectivity remain enforced. A stricter minimum can trade some modeled DPS for more crystal HP. Disable preservation and leave the minimum/scenarios empty to use the previous damage-only objective. This is an HP-node constraint, not a full survival simulator.

Optional scenarios describe one hit followed by sustained pressure. Enter current in-game maximum HP and up to eight encounter/opponent assumptions: **hit damage after mitigation + max(0, incoming DPS − assumed sustained HPS) × seconds + positive HP reserve**. The largest requirement sets the floor. HPS never absorbs the initial hit. Estimated total HP is entered current HP plus the flat node-HP change; percentage modifiers and passive/gear changes are not modeled. Headroom is a scenario proxy, not verified effective HP, guaranteed survival or win probability. Confirm final HP in game.

Settings persist per selected character in this browser. Saved Results/build JSON/Markdown retain assumptions and the assessment. Infeasible requests report an error without publishing a lower-HP fallback. Solver limits can prevent finding an allocation even when one exists. Damage-only stat priorities, baseline comparisons and Gear & Advice do not validate survival; constrained builds are not submitted as community damage presets.

PvP supports a manual multi-opponent **incoming-pressure** envelope, not optimized opponent-build combat. Next modeling work: resolve official current/historical opponent gear with provenance; evaluate outgoing damage and adverse matchups; include verified defensive skill, CC, mobility and coefficient rules before scoring them. Those metrics are explicitly unavailable here. Mitigation and tactical coefficients are not inferred from these manual scenarios.


### Timed pressure assumptions

Personal incoming-pressure scenarios can include up to eight named defensive, control or movement windows. All percentages and timings are user assumptions. Within the scenario window, each interval uses `incoming DPS × (1 − strongest active reduction) − active healing HPS`. The running ongoing deficit is floored at zero; its maximum determines the pressure component of the HP requirement. Interval boundaries include all reduction and healing starts and ends. The initial burst is added separately and is never reduced by these windows. Overlaps do not add or multiply reductions.

Results retain a reference with identical healing and no added reductions. This is sensitivity analysis, not a calibrated tactical model: skill availability, casts, cooldowns, immunity, chance of control/avoidance and outgoing damage opportunity costs are not inferred. Optional linked skills/effects are unioned with personal reserves at optimizer construction and validated against the same budgets and effect-slot limits. Stricter trained minimums win; effect sets are unioned. Stigma links keep their slots equipped. No link is dropped because its window has zero duration or lies outside the scenario. This guarantees allocation availability, not the assumed pressure reduction or successful use. An additional no-reduction scenario can constrain the same build for failed execution or immune opponents.

Optional **assumed effective cooldown** checks reuse of a linked skill within each scenario. Blank means unknown, not verified available; zero imposes no reuse gap. All skills start ready. Positive-duration, positive-reduction windows count as activations; entries sharing the same start count once. The largest entered cooldown for that skill applies when assumptions differ. Reuse before that cooldown is rejected. Scenarios are alternative encounters and are checked separately. Saved Results and Markdown retain starts, the shortest reuse gap and the assessment. These are user-entered effective values: review them after gear or cooldown-reduction changes. Charges, resets and shared cooldown groups are not modeled. Explicit outgoing action-time assumptions are entered separately.

### Timed optimized-opponent pressure

Final optimized results retain complete expected hit times and damage for both evaluated damage scenarios. Recording these traces is disabled during the optimizer's repeated scoring evaluations and does not change the damage objective. Imported traces are bounded to 50,000 hits, validated for finite chronological values and matching duration/total/DPS, and rejected rather than truncated. They are user-supplied model evidence, not authenticated combat telemetry.

The timed opponent import selects a fixed-length greatest gross-damage window before applying the user's healing/pressure reductions. Its hits are instantaneous; simultaneous hits are summed, continuous healing reduces accumulated deficits without banking excess, and reduction intervals are half-open. The strongest overlapping reduction applies to each timed hit and any additional continuous pressure. A separate manual initial hit is added independently. The maximum deficit plus the positive HP reserve defines the required HP proxy. Up to eight scenarios contribute independent constraints; their largest requirement sets the crystal-board HP floor. This is not a worst-case search over every tactical alignment, stochastic critical outcome or opponent response. Legacy average-pressure imports remain explicitly available.

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
| Base animation times | measured from recorded casts where enough presses exist (Flame Arrow step 0.73 s, Blaze 0.33 s, Firestorm 0.56 s, Hellfire release 0.56 s); the Hellfire charge (0.5 s per level) and a few rarely pressed skills are estimates — see *Measured action times* | `kit/sorcerer.py: TIMING` |
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

## Estimated buff contribution (0.2.307)

The log review's **Buff contribution** tab splits each player's damage the way rDPS does (an idea
FFLogs popularised): the part of their hits that came from other players' damage buffs and debuffs
moves to whoever cast them. *Buff-adjusted DPS* is a player's DPS without what others gave; *rDPS*
adds back what their own buffs gave others, so the party's total is unchanged. It is an estimate and
is **never used for rankings or parse percentiles**; it stays that way until the check below agrees
with the estimate across enough fights. `aion2calc/combat/contribution.py` computes it.

**Recorded:** each credited effect's window, who applied it and who it was on (live meter 0.2.306 or
later), and every hit inside those windows.

**Estimated:**

* **Which buffs.** Only those whose effect on damage is a known number in the boost formula: the PvE
  Damage Boost auras Undefeated Mantra and Light of Protection (10.5–22.5% by level; they do not
  stack with each other, so the stronger applies), the party PvE Damage Boost on block from Fury and
  Experienced Counterstrike (likewise exclusive), and the enemy PvE Damage Tolerance cuts from Chain
  of Torment (5% at every level) and Earth's Promise (5.4% upward by level; not while Chain of Torment
  is up). One buff from several casters applies once and its credit is shared. Defense cuts (Blade
  Toss, Debilitate, Defense Break, Executing Blade, Fracturing Blow) need the boss's Defense, and
  Combat Speed buffs (Power of the Storm) change how many hits land, so neither is credited.
* **How big.** The value at the caster's skill level, from the official profile uploaded with the log
  when it lists the skill, else (for a stigma aura) from the effect record, else the typical top
  player's level. The effect record's level is inferred, not a published rule. An effect id is the
  skill variant × 10 plus a stack digit, and a stigma aura's variant carries the level band it has
  reached (`x1` = levels 5–9 … `x4` = 20–24, taken at the band's middle). In the diagnostic captures
  the digit took several values across 17 casters, followed combat power where that is known (three
  casters), differed between one player's stigmas, and matched the level implied by Power of the
  Storm's duration; in the log server's uploads it held the level the caster's profile lists in 36 of
  37 cases. A passive's variant does not carry its level (0.2.319): Fury's was `01` for casters whose
  profiles list levels 6–17, Experienced Counterstrike's `07` for levels 9–16 and Earth's Promise's
  `01` for levels 12–16, so a passive takes the profile's level or the typical one.
* **How much of a hit it made.** The boost bucket is additive (`1 + B + X − tolerance`, see
  [Damage calculation](#damage-calculation)), so a +X% buff made `X / (1 + B + X − tolerance)` of a hit
  landed with it. `B`, the player's other damage boosts, is not recorded: it is the typical build's for
  their class (0.07–0.26). Each uploader's own `B`, computed from their official profile, gives nearly
  the same estimate (below). The Damage Tolerance is 30% against a boss and 10% otherwise, the
  optimizer's scenario values. A player's own buff on themselves is their own damage. Pet hits are not
  adjusted, because whether party buffs reach pets is not known.

**The check.** For each credited buff group, the same player's *plain* hits with one skill on one
target (no critical, double, perfect or periodic damage, and none during a break window, which
multiplies everyone's damage) with only that group up are compared with those landed with no credited
buff up, and the measured gain is set against the gain the estimate predicts for the same hits. The
target is part of the comparison since 0.2.319: a skill's hits on a boss and on its adds differ in
Defense and Damage Tolerance. One fight rarely holds enough hits without a buff, so
`python -m aion2calc calibrate --buffs <logs or folders>` pools many.

On the supplied captures:

* **Party PvE Damage Boost on block** (Experienced Counterstrike, at the level 7 its effect id was
  then read as) measured **+6.7%** against **+8.5%** estimated, over 345 hits with it and 1,122
  without (Vakron).
* **The auras** are not settled. A Transcendent Bakarma fight agreed (+22% measured, +17% estimated)
  on only 33 hits. Four Deus Research Base fights measured +5.5% against +24% (502 hits with an aura,
  66 without), but their unbuffed hits fall in a few short windows of the fight, so a phase effect
  cannot be ruled out.

On the log server's uploads (0.2.315: 14 fights with a comparison in nine logs from meter 0.2.306 or
later):

* **The auras** measured **+8.9%** against **+16.5%** estimated, pooled over 44 player-skill pairs
  with 1,148 hits with an aura and 520 without. The fights scatter from −6% to +31% (one of them
  +195% on 11 hits), and only three come within a few points of the estimate. With the Deus fights
  above, the estimate is about twice what the auras measure. A larger share of other damage boosts
  in the same additive bucket than the typical build's would shrink each aura's part in this way;
  the uploads do not record those boosts.
* **The block buff** and **the tolerance cut** have one fight each (−3.7% against +10.6% on 38
  hits; −5.0% against +12.0% on 217).

0.2.317 re-ran the check on the 42 uploads from meter 0.2.306 or later (26 fights with a comparison):

* **The auras** measured **+5.6%** against **+16.2%** estimated, over 25 fights, 70 player-skill
  pairs, 2,349 hits with an aura and 849 without: about a third of the estimate. Boss hits alone give
  the same (+5.1% against +17.1%, 17 fights), so the mix of boss and add targets (30 % and 10 %
  Damage Tolerance) is not the cause. The uploaded official profiles list the players' primary and
  deity stats but not their damage boosts, so the typical build's boost bucket stays the leading
  suspect.
* **The block buff** still has one fight, **the tolerance cut** two (−1.8% against +11.8%, 282 hits).

0.2.319 re-ran it on 100 logs: the 91 uploads from meter 0.2.306 or later and the nine logs of 18
October (world and field bosses in the Abyss), each fight counted once however many party members
uploaded it.

* **The boost bucket is not the cause.** With each player's own `B`, computed from the official
  profile uploaded with the log as the character import reads it (equipment with its rolls, Daevanion
  boards, skills; 5,648 of 5,743 comparisons had one), the auras' estimate moved from +20.6% to
  +20.2%. Six classes' median own `B` is within 0.02 of the typical build's; the Assassins' is higher
  (0.43 against 0.26) and the Chanters' lower (0.14 against 0.19).
* **Undefeated Mantra agrees.** Comparing a skill's hits on the same target only, and the two auras
  apart, the Mantra measured **+20.6%** against **+21.7%** estimated (24 fights, 179 comparisons,
  7,284 hits with it and 2,436 without): +23.3% against +22.7% in the 18 October logs and +12.7%
  against +17.3% in the older uploads. The same-target comparison alone moved the older uploads' auras
  from +5.6% to +9.7% (against +16.9%), and all the logs' from +17.1% to +19.8% (against +21.5%).
* **Light of Protection** measured −5.3% against +14.8%, in six fights from the older uploads with
  only 57 hits without it. Its tooltip is the Mantra's, so more fights are needed before reading
  anything into it.
* **The block buff** measured **+7.3%** against **+12.6%** (nine fights, 1,924 hits with it and 3,555
  without), Fury and Experienced Counterstrike alike. Its windows last the 20 s the tooltip gives and
  its casters' levels come from their profiles, so neither explains the gap.
* **The tolerance cut** still has two fights (−1.8% against +11.8%).
* **Fight phases still weigh.** The per-fight results scatter from −28% to +195%. Around a window's
  edge (no other window within 10 s), the same skill's hits on the same target step up at the start
  and down at the end, by 10–30%. Far from any edge, hits inside and outside the windows differed by
  nothing in the older uploads and by +25% in the 18 October logs, so a whole fight mixes the aura
  with openers and bursts. In the 18 October logs the damage rose about 2 s before a recorded start
  and fell about 1 s after the end. Leaving out unbuffed hits within 3 s of a window, in case the
  records' edges lag, raised the 18 October logs to +34.1% against +22.8% and left the older uploads
  five fights, so the check does not.

Until the block buff and Light of Protection agree too, the tab says it is an estimate and rankings
use recorded DPS only.

## Effective healing and overheal (0.2.307)

The game reports how much a heal restored, not how much of it was overheal, so encounter insights
derive that from the party HP feed (`aion2calc/combat/healing.py`). The server sends each party
member's HP after every change. The members' maximum HP comes with it, and the recording player's
from their own record on entering a zone.

* **Instant heals.** A heal on a player restores at most the HP they are missing, so its effective
  part is `min(amount, maximum HP − HP before)` and the rest is overheal. HP before is the target's
  last reading from an earlier read than the heal, plus the effective part of heals already counted
  in the same read. Each player's last reading from before the fight is kept for heals early in it.
  A heal with no earlier reading or no known maximum is counted as *No reading*, never guessed.
* **Heals over time and shields are not measured.**
  * A heal over time ("restores … HP every 1s for 14s") arrives as one record carrying its whole
    amount, while the HP feed rises tick by tick. Light of Regeneration's ~6,000 rose ~418 per tick,
    and it was 68% of the recorded healing in the 15 October capture.
  * Some shields arrive as healing of the shield's size ("a Protective Shield that blocks damage";
    Impeding Authority) and restore no HP.
  * Both are listed apart, told apart by the skill descriptions. Potions, which have none, count as
    healing over time: their next readings rose far less than their amounts.
* **The check.** For each read that healed a player, the target's HP after it (their last reading in
  that read, else the next within a second) should equal the HP before plus the read's effective
  healing. In the 15 October capture, 256 reads matched in full and 22 matched topped up to maximum
  HP. 168 had other changes in between (damage, ticks of other heals). Read in arrival order, 215
  heals raised HP by exactly their amount and 18 stopped at maximum HP.

Pets and enemies are not covered, and shield absorption itself is not decoded.

## Installation, identity and live rate evidence

Live Meter discovers Steam libraries and registered Windows/PURPLE game installations, then reads the first four **Product version** components of the selected executable for comparison groups across launchers. The engine file version and launcher build IDs are diagnostic evidence only. Installation paths are not exported. Recorded home server IDs are matched against official regional metadata; the installation language does not establish a physical region.

Numeric Product version suffixes after the fourth component are diagnostic revisions and share a metric group. For example, `2.0.6.0.2026100701` groups as `2.0.6.0`; `2.0.7.0` stays separate. The full executable version remains recorded. Server derived indexes normalize historical product-version keys without rewriting uploaded files; other cohort requirements remain unchanged.

The executable's ProductVersion resource is stamped by the launcher, so a Steam and a PURPLE install of the same patch can disagree on it. The shipped Unreal content packages are identical on both, so Live Meter also records a launcher-independent **content fingerprint**: the sha256 of the sorted `(name, size)` list of the `.pak`/`.utoc`/`.ucas` files under `Aion2/Content/Paks` (name+size, not a full-file hash, since the packages are gigabytes; the fingerprint still changes on any content patch). `python -m aion2calc install-version` prints every version signal for each detected install and, when two or more are present (e.g. Steam and PURPLE), reports which signal agrees across them — identifying the shared game-version key by observation rather than assumption. The content fingerprint is currently recorded as diagnostic evidence alongside the Product-version cohort; promoting it to the authoritative comparison group is gated on confirming, on real dual-launcher installs, that it agrees where the Product version does not.

Recorded map/instance IDs identify known open-world categories, Fire Temple Arena and available dungeon names. Unmapped content, difficulty, build and match outcomes remain unknown. Detection provenance is visible in shared log review. Opponents without their own server ID are not assigned your server.

Live DPS uses the recorded damage interval and pauses after two seconds without damage while capture continues. Healing after the last damage does not extend the live damage interval. Actual new damage resumes it. Saved logs preserve the full event interval, including healing/deaths, so report rates can differ from the live rate. This does not establish a kill or match result.

Unknown difficulty is not guessed from boss damage or observed current HP. Build-specific maximum-HP signatures and corroborating evidence require independently labeled collection and validation before automatic inference. Current installation evidence is never applied retrospectively to historical logs.

## Event forecasts and boss observations

Event schedules are a bundled, dated community snapshot with source, review date and explicit conflicting rift reports. Region and Korean matching group are selected by the user. Recurrences are resolved in IANA schedule time zones, then displayed in device-local time. Global reset forecasts use UTC; regional reset forecasts use their specified local clock. The horizon includes the previous day and eight upcoming calendar days; nonexistent daylight-saving wall times are omitted and ambiguous repeated times retain both real instants. Countdown calculations use the device clock and refresh after backgrounding. No build applicability, maintenance override or actual event activation is inferred.

Recorded boss history is independent of event forecasts. Existing NPC IDs, engagement, defeat markers, recorder-clock timestamps and submitted context determine observation groups. Up to 20 observations per group are retained in the response after exact indexed duplicate removal; omissions and scan/group limits remain explicit. Public reads exclude active moderation holds as well as non-public/deleted logs. Different perspectives can still duplicate a fight. Source-log links identify the recorded encounter, not verified kill credit. Schedules are not mapped to NPC IDs by name, and no physical server/channel, respawn estimate or live availability is inferred.

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

## Allocation drafts and reference profiles

The Build workspace checks an allocation against a bundled class catalog and user-entered budgets. Connectivity uses the board's orthogonal grid paths from its start node. Effective skill levels add trained, entered bonus and selected board contributions; supporting-effect slots and individual unlocks are checked separately. These checks do not establish current-build legality, ownership, combat viability or optimizer quality. PvE/PvP labels alone do not change tactical scores.

Saved character profiles are read-only evidence from their recorded fetch time, not necessarily the encounter's historical equipment. Imported optimizer scores and stats remain reference values after edits. Official total skill levels are not enough to recover all trained/gear/board allocations and are not silently converted into editable allocations. Export is blocked on listed catalog errors; local saving may retain an invalid draft for later correction.

## Crafting probabilities and external maps

Crafting uses a source-attributed recipe graph with exact recipe/item references, ingredients, mastery/faction gates, output quantities, listed fees and combo rates. Rates divide the source's 10,000-point values by 10,000. The source does not establish general success, failure refunds, combo quantity/replacement semantics or modifier coefficients. User effective rates are assumptions; missing success data is not replaced with 100%.

Crafted-output stat previews use the publisher's detailed item record with an exact numeric ID match inside the same namespace. Base stats, cumulative bonuses for a selected enhancement and possible random-roll ranges are shown separately. The preview adds only the listed enhancement bonus to base stats; random rolls and breakthrough bonuses are excluded. Display units follow the publisher's explicit formatting metadata; unknown stat IDs remain raw. A missing stat table is unavailable data, not proof that an item has no effect. Source retrieval time does not verify applicability to the installed Product version or region.

For N completed, independent checks with a constant assumed combo probability p, expected triggers are Np and probability of at least one is 1−(1−p)^N. Seeded Bernoulli examples illustrate this assumption, not game RNG or guaranteed outputs. Material expansion uses only explicit source-linked same-faction recipes without combo outcomes, rounds each branch separately and rejects cycles or excessive expansion. Owned amounts subtract only from final material rows. Historical/current-build applicability is not inferred from retrieval time.

Interactive maps run in the publisher's supported embed mode in a sandboxed cross-origin frame. Application data and tokens are not passed to it. External marker positions never become capture positions, NPC mappings, region evidence or encounter classification inputs. Source asset references retain their publisher namespace rather than asserting cross-catalog numeric-ID equivalence.

## Edited build evaluation

Standalone drafts can supply manual per-component stat contributions and Genus lines to the existing damage simulator. Class base stats, selected board stats and passive effects are added separately; source profile totals and prior optimizer scores are not recomputed. Gear skill bonuses are represented once in draft bonus levels. The evaluator validates allocations against catalog gates/paths and entered budgets, then runs fixed-duration boss/dummy or experimental player-target/burst scenarios with the default class priority. It does not search allocations, supporting effects or rotation.

Responses record evaluator version, calibration, input hash, modeled DPS/ability shares and Genus coverage. This hash identifies submitted model inputs, not authentic game equipment. Unsupported defensive and collection effects remain unsupported. Edited drafts do not become public samples or canonical presets. Percentage inputs use fractions, and bounded finite inputs limit request work rather than establish game caps.

Draft scoring currently supports level 45, matching the model's base-resource assumptions. Lower-level allocation drafts remain editable and exportable; no lower-level score is supplied.

Draft evaluation excludes learned personal/community calibration and records neutral proc-rate, critical-midpoint and skill-multiplier parameters. Desktop and server serialize this model context against their other model calculations.


## Automatic NPC troubleshooting evidence

New live-session logs and diagnostic exports retain bounded numeric spawn-decoder observations without enabling TCP payload recording. Each identity epoch includes scan/candidate counters, omitted-observation counts and up to 128 recognized spawn observations (32 epochs maximum), with actor ID, timestamp, opcode, decoded NPC code or missing-type-marker status. Scan counts include outer and decompressed scans and are not unique packet counts. Evidence is validated on import and upload; packet bytes, text and connection addresses are excluded. A missing observation does not prove no packet arrived, particularly after truncation or an unsupported opcode. This helps diagnose missing NPC links but cannot reconstruct an unfamiliar packet format; optional raw capture can still be needed. Historical logs do not gain missing evidence retroactively.

The user confirmed continuous capture, cleanup, partial runs and character imports work again. Ascension missing NPC-type identities remain a new pending report; catalog boss portraits already exist. Responding production packages were verified as server 0.2.65 and analyzer 0.2.115 before this update.


## Genus target values

Optimizer results and Gear & Advice show catalog upper-range targets even when only levels are entered. PvE targets cover the catalog's genus Damage Boost slots with saved-line comparison, unlock level and assumed enemy-share ordering. Levels do not supply rolled values. Targets are aspirations, not expected reroll outcomes; current-version legality, odds, costs and defensive tradeoffs remain unverified. Other slot ranges, Special and numeric PvP targets are unavailable from the supported catalog. Saved lines remain unchanged.

