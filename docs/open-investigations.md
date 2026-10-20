# Open investigations

Findings from issues investigated against the **live server's real uploaded logs** (pulled via the
public API) and the server source. Each entry records what was found, what was fixed, and what
remains gated on inputs outside the client (chiefly capture packet loss). Complements the
high-level gated items in [the roadmap](COMBAT_ROADMAP.md).

## Ranked logs showing 0 — a real bug (fixed 0.2.268) plus genuine capture loss

Running the real gate (`aion2calc/combat/quality.py` `assess()`) over 40 recent public uploads
(630 segments) returned **0 eligible**. Two reasons fired on nearly everything, and both were
**whole-session facts applied to every fight**:

- `storage_boundary` (**100%** of segments) — set on every rolled-over archive part *and its
  continuation* (`meter_runner.py:536,560`), so any session long enough to roll storage over (all
  of them) marked every fight, even fights wholly captured inside one part. Clean 0-drop captures
  were flagged too.
- `capture_loss` (**97.6%**) — `pcap_dropped`/`pcap_if_dropped` are **cumulative since capture
  start**, so one early buffer overflow unranked every later fight (the identical drop count was
  stamped on 17 different logs). **0.2.292:** the recorder places each loss in time and stamps every fight with the losses inside its own window (`capture_loss` per segment) and each continuation part with its counter baseline (`part_baseline`); the gate charges a fight only with those, and the log server derives the baseline from the previous part for older uploads. The whole-session reading remains only for single-part uploads from older clients.

**Fixed (0.2.268).** `assess()` now attributes both per fight: a self-contained fight (its own
start observed *and* its own verified end — a kill or a cleanly completed run) is no longer gated
by a part-edge boundary, and dropped packets use a fraction budget (like the 0.2.258 frame-skip
budget). A genuinely truncated fight, or a materially lossy capture, is still gated. The server
re-derives eligibility on reindex (`reports.index_log` → `assess`), so server **0.2.87** bumps the
pin and `REPORT_INDEX_VERSION` to re-rank the existing corpus, not just new uploads.

**Remaining blocker is NOT a gate bug — it is capture packet loss.** In the sampled corpus every
actual boss kill came from a session that dropped **26–51% of its packets** (kernel/pcap buffer
overflow — the capturing PC can't keep up with AION 2's traffic). A parse built on half the packets
is unreliable and correctly stays unranked. Populating the leaderboard depends on reducing that
loss at capture time (larger pcap buffer / capture-path performance), not on further gate changes.

## Logs page split into tabs — endpoints already existed (shipped)

**Correction to the earlier note here:** it previously said the open server "lacks the
leaderboard/progression/speed endpoints." That was wrong — it was written without the server repo
attached. The server already serves **all five** tab endpoints, live:

| Tab | Endpoint |
| --- | --- |
| Community combat logs | `/api/v1/logs` (one row per encounter, from each log's `contexts[]`) |
| Completed-run speed | `/api/v1/run-leaderboard` |
| Boss progression | `/api/v1/encounter-progression` |
| Class performance | `/api/v1/stats`, `/api/v1/stats/<class>` |
| Highest observed build points | `/api/v1/progression` |

So this was a **client-only** build: `site/logs.html` + `site/logs.js` now render the five tabs
defensively through `A2.api`. The Completed-run speed tab (and the DPS leaderboard) read empty
until the 0.2.268 ranking fix propagates and clean runs qualify — the same root cause as ranked=0.

## Enemy NPC types — the skill-provenance reclassification is detrimental; do NOT ship it

Verified against the real logs. Across 432 PvE segments there are 302 untyped enemies (`mob_code:
None`); across 198 PvP segments there are **0** (every PvP "enemy" is correctly `is_player: True`),
so the "player falsely flagged as enemy" case the fix targeted **does not occur** in practice.

The proposed fix — reclassify a mob_code-less actor as a player if it cast a skill
`job_from_skill` maps to a class — was tested on the real logs: **8 untyped enemies cast a
player-job skill, and all 8 are real mobs** (e.g. `Enemy #502` → mapped to "Chanter" yet it *took
85,649 damage from a party member*). Shipping it would flip real mobs into the player DPS tables
and corrupt rankings. **Decision: do not ship it.** NPCs share skill IDs with player classes, so
skill provenance is not a safe signal.

### Why the mobs stay "unidentified" — it is capture loss, not a catalog gap

The self-healing pipeline (unknown-ids beacon → server ranks the gap → upstream publishes the name
→ asset refresh pulls it in) fills **names for codes we captured**. Classifying the real logs:

- **2641** enemies are typed **and named** (we have the code; the catalog has the name).
- **0** enemies have a code but no catalog name — so there is **nothing for self-healing to do**;
  the catalog has no gaps for the content being played.
- **302** enemies have **no `mob_code` at all** — these are the "unidentified" ones. **292 of 302
  (97%) are in sessions that dropped ≥20% of packets**; the other ~10 are open-world mobs already
  present when capture began.

An actor with no `mob_code` never had its spawn packet captured, so there is no code to look a name
up by — self-healing cannot invent one. The fix is the same as for ranked=0: **capture the spawn
packets by reducing packet loss.** (Open-world mobs engaged without witnessing their spawn are an
inherent limit; a future option is decoding a non-spawn packet that carries actor→mobCode, gated on
protocol evidence.) Hand-filling names would also fight the asset-refresh auto-merge.

## Catalog references audit (0.2.292) — what was filled, what stays data-gated

Cross-checked the bundled tables against each other (`dungeon_final_bosses.json`, `i18n/dungeons`,
`i18n/npcs`, `i18n/npc-portraits`, `data/global/titles.json`):

- **Final-boss codes without an NPC record or name: 0.** Codes the catalog flags non-boss: 0.
- **Named dungeon tiers without a curated final boss: 19 → 2.** The upstream catalog attributes no
  NPC to these tiers, so nothing could be curated. Every curated entry follows one pattern (the
  same boss name, boss flag and three-digit code suffix across a dungeon's tiers; 0 exceptions over
  100 entries), so 17 tiers now take their sibling tiers' final boss under every such code
  (`derived_final_bosses`, provenance per entry; curated wins). Citadel of the Fallen Daeva
  600151–600153 have no curated sibling and stay unmapped until a capture shows the boss.
- **Instances with a curated final boss but no dungeon name: 61 → 60.** Their NPC records exist
  upstream (3–4 bosses each, e.g. 610020–610023 "Kromede's Desolation", 910011–910016 "Divided
  Aponos"), the dungeon-name table does not list them. Upstream main (`2b9f9d65`) named one
  (610044 "Dying Dramata's Nest"); the rest are data-gated on upstream. Names are never inferred
  from boss names. Since 0.2.294 such a run is labelled by its curated final boss, `<Final boss>
  (instance N)`, with the zone source saying it is a derived label (the catalog names the boss,
  not the instance); the exact dungeon name replaces it the moment upstream adds one. `python -m
  aion2calc catalog-gaps` exports this list, the unmapped tiers and any unbacked boss codes with
  the catalog source revision for reporting upstream.
- **Boss NPCs without portrait art: 91 of 1,412** (1,321 have art) — the community portrait
  fallback pipeline covers these behind the curated table; no bundled change.
- **Titles: 509 records, stats absent in the bundle by design** — `db/sync.py` fetches each
  title's details into the user copy on launch.
- **Enemy NPC types:** unchanged — see the section above (the skill-provenance reclassification is
  detrimental and is not shipped; untyped enemies are capture loss, not a catalog gap).

## Identity after a Kibelisk teleport — the 19 October recording shows every load re-identified (0.2.323); a name-based re-bind ships since 0.2.300

Reported: after a **Kibelisk** teleport (Altgard's and Verteron's fast-travel points, a teleport within the same map) the overlay did not re-acquire the local player. Every diagnostic capture supplied so far was checked for one (eleven captures, 10–15 October, replayed through the real engine with a timeline of zone-state and identity packets):

- A **zone load** always sends the self zone-transition record (`23 36`, entity 0, with the destination coordinates) and, within about a second, the local-player record (`33 36`: actor id, name, server, class, level). The engine resets identities on the first and re-identifies from the second. Three captures show this six, three and two times; identity never stayed missing.
- **In-instance actor-id changes without any zone packet** (Krao Cave, four times in ten minutes — revives or in-instance teleports) each came with a fresh `33 36` record, and identity followed every time.
- Two captures carried no `33 36` record at all because they started after login with no zone load (identity is acquired only from a zone load or the typed character name — the documented limit).
- **No capture contains a Kibelisk teleport in the open world** (the only open-world time, map 1110, ends shortly after the load). The hypothesis therefore stays unverified: a same-map teleport most likely sends the `23 36` transition (which resets the identities) but **no** new `33 36` record, so nothing re-identifies the player until the next zone load.

The raw records also showed that `23 36` frames whose varint is not 0 are JSON text from another program's traffic on the same interface (`"#6203", "damage": …`), not game records — harmless for the zone logic, which keys on entity 0, and skipped by the value probe.

**What ships (0.2.300):** the engine keeps the game-verified local name across a zone reset and, when no self record follows, re-binds the local player to the one actor that carries that name again (names are unique per server; exactly one match, summons excluded, never a guess), the same rule the typed character name already uses; a self record from the game still replaces it. A capture **spanning a Kibelisk teleport with raw TCP recording on** is what confirms the packet sequence; with one, the probe (`python -m aion2calc probe`) and the zone timeline can pin the exact record, and the reset can be refined if the game does send something at a teleport.

**The 19 October recording, with raw TCP, settles it.** Two hours on seven game connections (each change of server opens a new one), it loads a zone 33 times, 14 of them on the map it was already on, as Kibelisk teleports do. Every load sent the `23 36` transition and, within 86 ms, the local-player record; the meter re-identified the player after every one, and the unnamed damage left over was other players' and monsters'. Where the overlay still lost the recording player, the cause was a meter started inside a zone, which no teleport fixes until the next load: see [the 19 October recordings](#the-19-october-recordings-0323).

**An 18 October recording (0.2.316) held identity across 41 identity epochs, without raw TCP.** It ran two and a half hours, then six minutes more: transcendence and dungeon runs, the open world and the Abyss's field bosses, in nine archive parts. It spans 41 identity epochs, each opened by a zone reset, and consecutive epochs on one map (three in a row on map 1110, two on map 20) are what same-map teleports such as Kibelisk's make. The recording player was identified in every segment of every epoch, and no unnamed player actor dealt its damage. Record TCP payloads was ticked, yet both captures recorded nothing: they started from the launch-time start or the overlay's Start, and those (and the Start/Stop hotkey) ignored the box until 0.2.318. So which record re-identified the player after each teleport, a fresh `33 36` or the name re-bind, stays unconfirmed.

## Observed field-boss feed and the open-world map ids (0.2.298)

The live kill feed placed every Altgard field-boss kill on map **1110** (one on **1100**, the base map), which fixes Altgard's open-world ids; Verteron is taken as the paired numbering of the bundled open-world map table (1000 / 1010 / 1011) until an Elyos kill confirms it. Three bosses the community reference lists in both zones under one name (Silent Dartan, Soul Ruler Kashapa, High Commander Lagta) are told apart by that map; the kill's map is the primary faction signal for every boss, so names the catalog and the reference spell differently still land in the right zone. The probe also found a periodic record (`1c 92`, u32 at offset 12) that carries the current map id alongside the server id at offset 6 — unverified beyond one capture, noted here as a lead.

## Server-record census of the diagnostic captures (protocol-variant leads)

A census of the server-to-client records in two captures (the 15 October instance run, 439,482 records over 744 opcodes; the 11 October arena-and-open-world session, 8,751 records over 198 opcodes), as a map for the value probe. The decoder reads damage (`04 38`), damage and healing over time (`05 38`), the identity records (`33 36`, `44 36`, `45 36`), the zone state (`21 36`, `23 36`), spawns and deaths (`40 36`, `41 36`, `42 36`), the roster and the HP feed (`00 8d`, `1b 92`). The first version of this table listed `04 38` as undecoded; it is the damage record. The decode in the next section identified most of the other frequent records.

| Opcode | Records (instance / open world) | Meaning (see the next section) |
| --- | --- | --- |
| `02 38` | 121,637 / 388 | skill cast |
| `06 38` | 106,855 / 353 | cast end |
| `04 38` | 66,365 / 557 | damage (decoded since the first meter) |
| `2b 38` | 40,969 / 559 | effect instance added (buffs, debuffs, crowd control) |
| `00 36` | 19,762 / 3,583 | server clock |
| `1d 37` | 16,198 / 264 | undecoded |
| `00 8d` | 14,130 / 587 | HP feed (decoded) plus resource-like and countdown subtypes (probe targets) |
| `1c 92` | 1,776 / 55 | carries the **server id** (offset 6) and the **current map id** (offset 12): a periodic status record, per the probe (one capture; unverified) |
| `45 36` | 0 / 28 | the large roster/identity record seen in the open world |
| `84 56`, `34 36`, `2d 92`, `03 36`, `4e 36`, `3a 36` | open world only | records the instance run never sent: open-world candidates for the probe |

## Combat records decoded from the diagnostic captures (17 October)

The eight distinct diagnostic captures with raw TCP recording (10–15 October; an instance run, Vakron, Krao Cave, arena and open-world sessions) were replayed through the real decoder. The decoded damage, heal, spawn and identity events served as anchors for the undecoded records: which actor, which target, which skill, and when. The client-to-server direction is encrypted (more than 23,000 distinct leading byte pairs in one capture), so everything below is the server's broadcast. The evidence is internal consistency — timing, pairing, fixed values — repeated across captures and game builds, not an in-game label; the names come from the bundled skill table, so they still want a look in the game before the app presents them as verified.

| Record | Layout after the opcode | Meaning | Evidence |
| --- | --- | --- | --- |
| `02 38` | actor · `00` · skill (u32) · sequence (u8) · kind (u8: 2 = at a target, 0 = self or proc) · target · facing (f32) · target x/y/z (f32, kind 2) · … · cooldown (varint ms, the last field) | **skill cast** | In seven of eight captures, 92–100% of decoded hits follow a cast of the same skill family by the same actor within 4 s (median 98 ms), against 0–50% with the casts shifted by 30 s. The player casts never followed by damage are buffs, heals and utility (Sprint Mantra, Light of Protection, Protection Circle, Undefeated Mantra, Dodge). Per exact skill id, 80% of re-casts come no earlier than 97% of the last field and the median re-cast lands at 1.03× it (Leaping Slam 13.6 s, Rage Burst 27.2 s, Ruinous Blow 40.9 s, Zikel's Blessing 109 s): a cooldown. |
| `06 38` | actor · skill (u32) · sequence · flag | **cast end** — sent for the local player and NPCs, not for other players | Same actor, skill and sequence as the cast. Start to end is stable per skill (Smashing Blow 319 ms, Overhead Slam 310 ms, Upward Strike 142 ms, Keen Strike 79 ms; procs 0). |
| `18 38` / `19 38` | skill (u32) · `01` · chain skill (u32) / `01` · chain skill | **chain window opened / closed** (local player) | The pairs are the class chains: Keen Strike → Rupture Strike, Rending Blow → Smashing Blow, Overhead Slam → Upward Strike. |
| `0e 92` / `1a 92` | target · `01` · effect (u32) / target · effect | **party buff added / removed**; effect = skill variant × 10 + stack | 15 October: 2,058 adds, 2,049 removes, 2,029 paired. Across captures 92–100% of adds follow a cast of the same skill within 1.5 s, by the class that owns it (the Chanter's Mantras and Protection Circle, the Cleric's Light of Regeneration). Durations are fixed per buff: Rage Burst 10.0 s, Ruinous Blow 20.0 s, Lunge Stance 18.5 s, Recuperation 12.0 s. |
| `2b 38` / `2c 38` | target · `13` · instance (varint) · effect (u32) · duration (u64 ms; all ones = permanent) · time (u64) · source · … · skill (u32) · … · x/y/z (f32) / target · count · (`00` · instance · reason) × count | **effect instance added / removed**, for any entity in range — enemies included | The duration field equals the time to an "expired" (reason 1) removal on three captures. On enemies: Forced Fall 3000 → 3.02 s, Overhead Slam 3000 → 3.06 s, Ice Chain 5000 → 5.00 s, Debilitating Mark 10000 → 10.01 s, Drill Dart 6000 → 6.00 s. On players: Experienced Counterstrike 20000 → 20.05 s, Ambush Stance 10000 → 10.01 s. |
| `05 e0` | boss · `03` · `01` · maximum (u32) · current (u32) · state | **boss break (stagger) gauge** | 99–100% of the gauge's drops share a read with a hit on that boss, and each skill takes a fixed amount (Rending Blow 2, Overhead Slam 5, Condemnation 7, Debilitating Mark 10, Rage Burst 20, Ruinous Blow 25; some hits 1.5×). Maxima differ by boss: 1200 (Vakron, Gelcos, Nazmun), 750 (the Krao Cave bosses), 317 (Transcendent Bakarma), 240, 150. Near zero the gauge stays down 5.1–6.7 s and refills; party damage in the ten seconds after a break was 1.2–2.1× the ten seconds before. |
| `09 38` | actor · `00` · skill (u32) · sequence · kind (2) · target · facing · position — the `02 38` layout | **an NPC's skill cast** (NPCs send `02 38` too) | 345 in the 15 October capture, every one aimed at a target. A boss's casts carry its named abilities (Nazmun: Ultra Laser, Trap Install, Reaction Speed Test; Transcendent Bakarma: Swipe, Subspace Dominion). Recorded per fight for catalog bosses since 0.2.307. |
| `2e 37`, `3c 37` | entity · skill · positions and direction | dodge rolls and boss charges; skill-driven leaps and dashes (Leaping Slam, Rushing Smash, Infiltrate) | Samples only. |
| `1a 37`, `1b 37`, `1c 37`, `2f 37` | entity · x/y/z (f32), with a heading on `2f 37` | position and movement updates for players and NPCs | Samples only; units and map transforms unverified. |
| `00 36` | u64 | server clock in epoch milliseconds, about every 50 ms | The values track the capture clock. |
| `00 8d` | entity · subtype · value (u32) | `02 01 00` is the decoded HP feed (party members included). `01 01 01` is the recording player's **MP**, the only player's the game sends. `01 01 03` and `01 01 06` count down by 500 and 750 per update | MP drops by each MP-costing skill's listed cost: Combustion 120 → a median drop of 119 (18 casts), Curse 80 → 79, Summon: Fire Spirit 150 → 149, Ruinous Blow 250 → 246. It rises by +50 regeneration ticks and with MP-restoring skills. Recorded per fight since 0.2.307. The other two subtypes are probe targets. |
| `33 36` | the recording player's own record, sent on entering a zone: … `01` · HP · maximum HP (varints, equal on entry) · maximum MP (u32), about 200 bytes in | the recording player's **maximum HP and MP** (the HP feed carries neither for them) | Found in five captures; in the three with HP and MP readings to compare, they matched the player's highest readings (23,467 / 3,077; 22,022 / 3,035; 6,610 / 1,816). Read since 0.2.307. |
| `4a 36`, `4b 36` | local player · (stat id, value) × n / player · count · (stat id, signed delta) × n | stat lists and signed stat changes | Unverified. |

**Limits.** The 11 October crowd capture (194 players, a busy capture) matched only 35% of hits to a cast: the casts of distant players were missing (a median 9.4 s since that actor's previous cast), so cast coverage holds for the party and nearby players, not for a crowd. Party buffs (`0e 92`) cover party members only; `2b 38` covers everything in range, including effects re-sent as entities come into view.

**What it enables** (the roadmap tracks these): a cast timeline and rotation per player; real cast/lock times and cooldowns for the optimizer's kits and a skill-cooldown overlay; chain usage; buff and debuff uptime with sources; crowd control landed and how long it held; each player's break-gauge contribution and the break windows; dodges and leaps; NPC casts for a boss-ability timeline. **Still undecoded:** shield absorption, interrupts, misses, mitigation, the unit and map transform of positions, and PvP rounds. MP and overheal (of instant heals) were added in 0.2.307 (below).

**Built into 0.2.306, and what building it showed.**

- **Effect instances are re-sent and reused.** Of 41,246 timed effect applications in the 15 October capture, only 1,252 have a removal within their duration (plus 1.5 s), 29,376 have no removal at all (the client expires them itself), and 10,617 see another application on the same target and instance before any removal. Those are refreshes — a Chanter Mantra is re-sent every second on its instance; an Ice Chain slow on Nazmun was re-applied 13 times in 29 s and expired 5 s after the last — or the instance number reused for a different effect. Only one removal came later than its duration with nothing in between. The meter therefore keeps one row per held effect, extended by each refresh from the same source, and ends a row at the next application on its instance; a removal belongs to the latest application before it.
- **Skill families.** A family zeroes a skill id's last four digits, but the class system actions share the `xx00` family: Dodge (`11000100`) and the Gladiator weapon equip (`11000000`) are different actions. They stay whole.
- **The listed Stagger Gauge Damage matches the gauge.** For 53 of 55 skills seen alone in a read, the drop equals the "N Stagger Gauge Damage" in the bundled skill description; the review splits a drop shared by several hits by those values.
- **Cast lock and next press agree.** For the recording player, the time from a cast to its cast end matches the median time to the next press while chaining (Rending Blow 0.34 s against the kit's 0.55 s, Overhead Slam 0.35 s against 0.45 s), so the game sends the cast end as the next action starts. Players cancel animations: the fastest tenth of next presses are shorter still. `calibrate --timings` reports both.

**Measured into the kits' action times (0.2.307).** The full press sequences of the 26 players with 50 or more presses (Templar: one player; five Templars in the log server's uploads gave its kit in 0.2.315, see [the methodology](methodology.md#the-templar-from-the-log-servers-uploads-02315)) gave the kits' `TIMING`. How each value was derived, and what it did to the calibration, is in [the methodology](methodology.md#measured-action-times-02307). What the sequences showed:

- **Basic attacks are woven.** Every class but the Cleric presses one step of its three-step basic-attack chain between two skills and cancels it 0.10–0.16 s later: a skill, not another step, followed 893 of the Gladiators' 1,005 steps and 403 of the Assassins' 504. Pressed back to back, the steps take 0.3–1.2 s each. The weave is 7–13% of a player's active time; dodges take another 8–14%.
- **Chain steps are separate presses.** Upward Strike, Bursting Blow, Piercing Strike, Tempest Arrow and Discharge each have their own press and time. Smashing Blow follows Rending Blow nearly one for one (627 and 579 presses), as the chain window records say.
- **Charged skills record the release.** Deadshot and Bolt are recorded when released, about 0.15 s and 0.57 s before the next press; the charge shows as extra time before the press (Deadshot 0.55 s, Bolt 0.90 s).
- **"Remove cooldown" Overhead Slam is not spammable.** With the spec, Overhead Slams never came less than about 1 s apart (10th percentile 0.97 s, median 1.18 s, 223 intervals). The 0.2.254 estimate was ~0.65 s.
- **Some presses land as two records (0.2.319).** Overhead Slam, Rending Blow, Smashing Blow, Leaping Slam, Incandescent Blow and Onslaught land each press as two equal records within 0.25 s. Both are damage, not one hit decoded twice: on 169 bosses with HP readings the recorded damage matches the HP lost (median 1.000) however large the second records' share (5–25 %). Together they deal the tooltip once, so a hit-based ratio against these skills counts half a press ([methodology](methodology.md#the-gladiator-and-the-chanter-from-the-log-servers-uploads-02319)).

**Effect ids carry the caster's skill level, and the buff contribution's first check (0.2.307).** The estimated buff contribution in the log review ([method](methodology.md#estimated-buff-contribution-02307)) needs each buff's size, which depends on its caster's skill level. The packets carry no level field, but the effect id (skill variant × 10 + a stack digit) varies with it:

- Undefeated Mantra's ids end `11`, `21`, `31` or `41` across 9 Chanters, and Light of Protection's end `11`, `21` or `31` across 8 Clerics. Where the caster's combat power is known (three of them), the higher digit goes with the higher combat power. One Chanter's Undefeated Mantra shows `41` while their Sprint Mantra shows `21`, so it is per skill, not per class or build.
- Power of the Storm, whose duration grows with its level, ran 12.0 s (level 5) with digit `1`: the digit counts the level thresholds reached (5, 10, 15, 20).
- Passive effects carry the level itself: Robe of Cold showed `07` with the 3.5 s duration of level 7–8, Experienced Counterstrike `07`, Fury `01`. **Not so (0.2.319):** in the log server's uploads Fury's id was `01` for casters whose official profiles list levels 6–17, Experienced Counterstrike's `07` for levels 9–16 and Earth's Promise's `01` for levels 12–16, so a passive's id names the skill, not its level. The stigma auras' bands held the profile's level in 36 of 37 cases.

The check compares the same player's same-skill plain hits (outside break windows, and since 0.2.319 on the same target) with only one credited buff group up against none up:

- The party PvE Damage Boost on block (Experienced Counterstrike at level 7) measured +6.7% against +8.5% estimated, over 1,467 hits (Vakron).
- The auras are open. A Transcendent Bakarma fight agreed (+22% against +17%) on only 33 hits. Four Deus Research Base fights measured +5.5% against +24%, but their 66 unbuffed hits fall in a few short windows of each fight.

`calibrate --buffs` pools more fights. The estimate stays out of rankings until they agree.

**Built into 0.2.307: MP, effective healing and boss casts, and what stays gated.**

- **MP.** The recording player's MP readings (above) are kept per fight. The review shows where MP started and ended, its lowest, MP spent and restored, and the time below a fifth of the maximum. Other players' MP is never sent.
- **Effective healing and overheal** ([method](methodology.md#effective-healing-and-overheal-02307)).
  - An instant heal restores at most the HP its target is missing, read from the party HP feed.
  - Heals over time cannot be measured that way: one record carries the whole amount, and the HP feed rises tick by tick. Light of Regeneration's records of ~6,000 raised HP by ~418 at the next reading, and it was 68% of the recorded healing in the 15 October capture.
  - Impeding Authority's shield arrives as a heal of the shield's size.
  - So heals over time and shields are listed apart. For instant heals, 256 reads matched the HP feed in full and 22 matched topped up to the maximum; 168 had damage or other heals' ticks in between.
- **Boss casts.** Catalog bosses' `02 38` and `09 38` casts are kept per fight, with their targets. The review groups them by skill and lists each cast in order. Most boss skills have no name in the bundled tables.
- **Still gated:**
  - *Interrupts.* Cast ends carry a flag: 0 on instant casts and procs, and on the NPC casts that end at once; 12 on the recording player's ordinary cast ends; and rarely 2, 3, 15 or 33. Flag 3 also ends summoned spirits' basic attacks with nothing landing on the spirit, so it does not mean "interrupted by crowd control".
  - *Misses.* None of the 13,048 decoded hits on enemies or 501 on players carried zero damage, so a miss or evasion travels in a record the decoder does not read yet.
  - *Shield absorption and mitigation.* Neither is in the decoded records.
  - *Movement.* Position updates arrive for party players (thousands per capture), but their units and map transforms are unverified. Dodges and skill leaps already appear in the rotation as casts.

## Genus Insight advice checked against the model and the recorded boss fights (17 October)

A Genus Insight guide for the global client (a video transcript) was compared with the planner's per-slot roll targets — each line at the midpoint of its best grade, on each class's optimized build, in the boss scenario with an even genus mix — and with the three recorded boss sessions in the diagnostic captures (15 player-fights, one to four players per class).

**Where the model agrees with the guide.**

- *Roll slot 4 first.* The best slot-4 line is worth 2.5–3.4% (PvE Damage Boost at 3%); no other slot's best line is worth more than 1.6%.
- *PvE Damage Boost equals Damage Boost.* They share the additive boost bucket, so a point of either is worth the same; PvE Damage Boost ranks first only because it rolls higher (2–4% against 1.5–3%).
- *Slots 1 and 5: PvE Attack and Boss Attack over Attack Bonus.* PvE Attack, Boss Attack and Penetration (+15, +15, +150, all flat damage in the model) beat Attack Bonus (+12, which scales with Attack % and the skill coefficient) for six classes. The Templar and Chanter are the exceptions: their higher Attack % and coefficients put Attack Bonus slightly ahead.
- *Critical Damage Boost only for crit-heavy classes.* It is worth most to the Gladiator (1.0% against 0.2–0.5% for the others), still well below PvE Damage Boost.
- *Natura: Multi-hit and Perfect Chance are bait.* Multi-hit is worth 0.16–0.28%, Perfect Chance less.
- *Special: Double Chance.* Double Chance, Damage Boost and Front Attack Damage Boost are within 0.3% of each other.

**Where it differs, and why.**

- *Fera's Weapon Damage Boost.* The model treats it as an independent multiplier too, but at the community calculator's 66% efficiency, so it is worth 1.2–1.4%: third behind PvE Damage Boost and Damage Boost.
- *Varian: front/back over PvE Damage Boost.* Per point, Front or Back Attack Damage Boost (its own multiplier) is worth 5–7% more than PvE Damage Boost. The boss's 30% tolerance keeps the additive bucket near 1, so additive boosts dilute little. Since PvE Damage Boost rolls higher, it still wins at matching grades; front/back overtakes it only from about 2.8%.
- *Accuracy over crit.* The model treats Accuracy as a threshold it assumes is met, so it scores no accuracy line.

**What the recorded boss fights show.** The hit record carries a position byte (1 = from behind, 2 = from the front, otherwise the side), the parry bit and the crit type. The model's crit rate is the hit-weighted crit chance inside the boss simulation, kit buffs and guaranteed crits included.

| Class | Players | Boss hits | Crit, recorded | Crit, model | Parried | From behind | From the front |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Assassin | 1 | 2,115 | 62.6% | 26.3% | 0% | 77.4% | 15.0% |
| Chanter | 2 | 1,477 | 30.9% | 14.4% | 0% | 58.8% | 18.9% |
| Cleric | 1 | 835 | 29.7% | 9.5% | 0% | 64.6% | 23.0% |
| Gladiator | 4 | 4,241 | 49.8% | 33.8% | 0.07% | 32.4% | 47.6% |
| Ranger | 1 | 1,499 | 39.4% | 28.8% | 0.60% | 36.6% | 43.3% |
| Sorcerer | 2 | 1,988 | 23.5% | 23.1% | 2.36% | 40.5% | 39.4% |
| Spiritmaster | 2 | 1,457 | 21.1% | 20.7% | 3.77% | 53.9% | 24.8% |
| Templar | 1 | 172 | 8.7% | 18.2% | 1.16% | 8.7% | 53.5% |

- **Position.** The boss scenario counted every hit as frontal (until 0.2.308), so the model credited Front Attack lines on every hit and Back Attack lines on none. The flat Back Attack stat (`back_atk`, also the official profile's `BackFixingDamage`) does not reach the damage formula at all. In the recordings, 15–54% of a class's boss hits came from the front and 9–77% from behind.
  - Weighted by those shares, Front and Back Attack Damage Boost fall to 0.2–1.6%. That is below Damage Boost and Double Chance for every class, the Assassin included.
  - A Back Attack line in slot 1 or 5 would be worth about a third of a percent to the Assassin, against 0.64% for PvE Attack. The model also adds PvE Attack to damage-over-time ticks.
- **Parries.** A parried hit loses half its damage.
  - Bosses parried 0–0.6% of the Assassin's, Chanter's, Cleric's, Gladiator's and Ranger's hits, 2.4% of the Sorcerers' and 3.8% of the Spiritmasters' (5.2% for one).
  - Accuracy that removed every parry would be worth up to about 1.2–1.9% to those casters and next to nothing to the others.
  - Misses are not decoded, so how much evasion costs is unknown.
- **Crit.**
  - Recorded boss crit rates reach 51–63% (three Gladiators, the Assassin), so a hard 50% cap on every hit is not supported. A cap on the stat's own share cannot be ruled out.
  - The model's crit rate matches the Sorcerers and Spiritmasters within a point. It is 11–36 points low for the Gladiators, Ranger, Chanters, Cleric and Assassin, and above the one Templar, who was tanking.
  - The recorded players' crit stats are unknown, so this is a lead, not a fit. Where the curve runs low, Critical Hit and Critical Damage Boost lines are undervalued.

**Follow-ups:** the positional mix, Back Attack and the Front/Back Attack Critical Hit lines are in the model since 0.2.308; the crit curve, Max Attack, Power Shard Damage Bonus and the accuracy lines were checked against the archived logs and stay as they are ([checked 17 October](#hit-positions-crit-and-the-remaining-genus-lines-17-october)).

## Hit positions, crit and the remaining Genus lines (17 October)

The follow-ups above were checked against the private diagnostics archive: the diagnostic captures and the sharing-server logs downloaded during past investigations. The hit record's position byte (1 = from behind, 2 = from the front) and its crit and parry bits reach the logs as each hit's `back`, `front` and `crit` flags. Players' official profiles are stored with their uploads.

**Where hits land on bosses.** The mean, over characters with 500 or more direct boss hits, of each character's own shares. One row per character: the logs' row when a character is in both sources. Old exports without front flags were left out.

| Class | Characters | Boss hits | From the front | From behind | Side or none |
| --- | ---: | ---: | ---: | ---: | ---: |
| Assassin | 6 | 32,775 | 11.7% | 69.7% | 18.6% |
| Chanter | 7 | 10,150 | 22.3% | 55.4% | 22.4% |
| Cleric | 13 | 24,098 | 27.2% | 23.7% | 49.1% |
| Gladiator | 4 | 26,834 | 30.5% | 50.5% | 19.0% |
| Ranger | 8 | 19,090 | 34.1% | 34.8% | 31.1% |
| Sorcerer | 5 | 7,117 | 43.3% | 29.5% | 27.2% |
| Spiritmaster | 8 | 19,260 | 29.0% | 34.4% | 36.6% |
| Templar | 3 | 7,615 | 47.8% | 30.9% | 21.3% |

- Characters vary: the four Gladiators ranged from 10% to 61% from the front, the Templars from 37% to 68%.
- The last column also holds hits whose record carries no position (the short record layout). Except for the Gladiators', they crit far less (5–26% against 22–65% for the same class's front and back hits), so some of them are probably hits that cannot crit.

**Parries come only from the front and the side.** In the captures, none of 6,573 boss hits from behind was parried (nor 1,706 on other enemies). From the front 79 of 4,694 were (1.7%), from the side 37 of 2,517. The casters took most of them: 5.1% of the Sorcerers' and 8.6% of the Spiritmasters' front hits.

**Crit by position.** Within the same skill and player, hits from behind crit more often than hits from the front, by 4–13 points, for the Assassin, Chanter, Cleric, Ranger and Spiritmaster (30 of 38 players). They do not for the Gladiators (0 of 2) or Templars (2 of 4), and the Sorcerers' front hits crit 4 points more. A game-wide bonus for hits from behind would show for every class. Players' own Back Attack Critical Hit lines (Genus Insight, 20–40 each) fit the spread better. So no built-in bonus is modeled, but the lines themselves are.

**The crit curve.**

- *The data.* 55 players in the logs had a ready official profile and 100 or more direct boss hits. 35 of them are level 45, have 200 or more front and back hits, and get no crit buff from their kit in the simulation: Assassin 6, Chanter 7, Cleric 11, Spiritmaster 8, Templar 3. For each of them the profile was imported and its Critical Hit compared with their recorded crit rate on front and back hits.
- *The finding.* Every one of the 35 crits more than the curve predicts. To reconcile the curve, they would need 196 more Critical Hit than their profiles show (hit-weighted median; range 23–374). Their Genus Insight lines and Pantheon allocations are not in the official profile. Genus Insight alone offers Critical Hit (15–30) and Front/Back Attack Critical Hit (20–40) in three slots of each genus.
- *A flatter curve fits too.* The missing amount shrinks as the profile's Critical Hit rises (weighted r = −0.42). A refit with nothing missing has a slope of 0.0044 and its midpoint at 865. It gives 17% at 500 Critical Hit (4% now) and 56% at 900 (34% now), and fits these players slightly better (weighted squared error 103 against 133 ×10⁻⁴). But it puts 72% at 1048, where the dummy measurement behind the current curve found 56%.
- *Kept.* The data cannot separate crit the profile does not show from the curve's shape, so the curve stays. [Learning from your fights](planner.md#learning-from-your-fights) already shifts the curve per class from your own recorded crit, by up to ±250 Critical Hit, which absorbs what the profile misses. A fit needs players whose Genus Insight lines are entered as well as recorded.

**The lines that stay unscored.** The planner now says why for each of them.

- *Max Attack* (slots 1 and 5): no official profile stat carries it, and no record shows its effect. The item catalog uses "Max Attack" for a weapon's whole damage range ("206–229") and for its enchant steps. Two readings give different advice:
  - as the top of the weapon roll, a +15 line is worth 0.32–0.35%, below Attack Bonus +12 (0.46–0.52%) and PvE Attack +15 for every class;
  - as flat Attack it is worth 0.58–0.65%, the best slot-1 and slot-5 line for the Chanter, Gladiator and Templar.
- *Power Shard Damage Bonus* (slots 3, 6 and 9; also a gear stat): Power Shards are not simulated. The hit record has a power-shard bit, but none of the 18,247 decoded direct hits in the captures carried it, so nothing measures the bonus.
- *PvE Accuracy and Accuracy Bonus.* Parries cost half a hit and only touch front and side hits. Bosses parried under 1% of most classes' hits and 2.4–3.8% of the casters'. Misses are not decoded, and how Accuracy lowers either rate is not known. The lines stay unscored rather than credited with a guess.

**In the model since 0.2.308.**

- *Positions.* The boss scenario lands each class's direct hits in the shares above (rounded). Front and Back Attack add flat damage, Front and Back Attack Damage Boost is its own multiplier, and Front and Back Attack Critical Hit add Critical Hit, each only on hits from its side. A hit from behind is never parried. The training dummy keeps every hit in front. Damage over time has no position.
- *The effect.* Boss DPS falls 3.7% for the Gladiator and 2.1% for the Templar, whose kits carry a Front Attack Damage Boost passive that used to apply to every hit. The other classes' median builds have no positional stats and do not move.
- *Genus roll targets now.* Each line is valued at the midpoint of its best grade, with an even genus mix:
  - Slot 4: PvE Damage Boost (2.5–3.4%) beats Back Attack Damage Boost (0.5–1.5%) and Front Attack Damage Boost (0.3–1.1%) for every class.
  - Slots 1 and 5: Back Attack is worth 0.11–0.29% and Front Attack 0.05–0.31%, against 0.36–0.86% for PvE Attack.
  - Slots 3, 6 and 9: Back Attack Critical Hit comes close to Critical Hit only for the Assassin (1.44% against 1.53%).

## Cleric builds: online guides against the server logs (18 October)

Six Cleric guides (KR Inven, April and January 2026; GamesFuze, GAMES.GG and Mobalytics, October 2026;
PixelNitro, September 2026) were compared with the 13 Clerics in the archived sharing-server logs and the
recorded Cleric. Shipped in 0.2.310 ([methodology](methodology.md#the-clerics-condemnation-build-02310)).

- **Same build, where the logs show it.** The guides build around Condemnation with Earth Punishment, whose
  first specialization makes every Condemnation on its target crit, and Condemnation's cooldown reset on a
  critical hit. In the logs 92% of Condemnations within 2 s of an Earth Punishment tick crit (510 of 554)
  against 21% otherwise (159 of 769). Five of the 13 Clerics play this build (Condemnation 23–38% of their
  damage) and so does the recorded Cleric (Earth Punishment at stigma level 15 or more, Condemnation 0.59 a
  second inside its windows against 0.10 outside). The guides' specializations match the ones the logs carry:
  Chain of Torment's 2 and 4 for nine of the 13, and Divine Aura's speed and duration (13 ticks a cast) for
  most of them.
- **Different from the guides:** seven of the 13 carry no Earth Punishment (one tried it briefly) and lean on
  Judgment Thunder with Divine Punishment (26–45% of their damage), the build the KR guide calls weaker
  since Earth Punishment (Judgment Thunder was over 50% of the damage before it). They are why the logs
  show Judgment Thunder for every Cleric.
- **Different from the model before 0.2.310:** it never modelled Earth Punishment's crit or several Cleric
  specializations, so its suggested Cleric build took the first two specializations of each skill and
  Judgment Thunder carried 30% of its damage. It now suggests the guides' build.
- *Answered in 0.2.317:* how much of a fight a Cleric spends healing. In 61 boss fights of 14 Clerics on the
  log server a heal comes 4.6 times a minute at 0.45 s a press, inside Earth Punishment's windows as often as
  outside them, and the boss scenario now spreads that time over the other presses (3.4 %). The windows'
  smaller Condemnation count is the players' choice: they press Judgment Thunder there too, for less damage a
  press ([methodology](methodology.md#the-clerics-heals-and-basic-chain-02317)).

## Kit gaps from the recorded casts, pets and MP (18 October)

The four kit gaps the measured action times exposed (Spiritmaster presses, Smashing Blow, the Cleric's Thunder and Lightning, woven basic attacks) were measured from the diagnostic captures and closed in 0.2.309 ([methodology](methodology.md#kit-gaps-from-the-measured-action-times-02309)). What the records showed, and what stays open:

- **The Spirits cast on their own records.** Each pet's skill uses arrive as casts from the pet, so a summon's Spirit can be followed through its life: it uses its skill about 0.3 s after the summon press, and the Fire and Earth Spirits keep using it on the 3 s Spirit Skill Cooldown for several seconds while Water and Wind rarely do. Several Spirits are out at once. The meter credits the summon's own skill to the summon and leaves the Spirits' other skills on their own rows, as the KR logs do.
- **Dimensional Control is a reaction, not a rotation slot.** 97% of its presses come within 1 s of a Spirit skill. The recorded players press it after 75–83% of the summons but after a third of the Spirits' other skills, though they had the time (they pressed Combustion instead); the model presses it whenever a window is open.
- **MP readings settle the Gladiator's sustain.** In the recording player's MP feed, Rending Blow costs 94 and every basic-attack step returns 140–180; Smashing Blow returns nothing of its own (the +50 that sometimes follows it is Rending Blow's "Restores 50 MP on landing a Critical Hit").
- **Two Cleric builds, and Judgment Thunder stays.** The recorded Cleric and all ten KR logs press Earth's Retribution → Thunder and Lightning → Discharge and Condemnation (30–43% of the recorded damage, 53% of KR's), never Judgment Thunder. The archived sharing-server logs disagree: all 13 Clerics whose damage they hold press Judgment Thunder, and with its Divine Punishment companion it is 27% of their pooled damage (19–45% per player), close to the 30% the kit takes from a 0.2.256 community parse, so the kit keeps it. They split into two builds by Condemnation's crit rate: eight crit with Condemnation 0–38% of the time for 0.5–27% of their damage and lean on Judgment Thunder (26–45%), while five crit with it 65–88% of the time for 23–38% of their damage, like the recorded Cleric (62–87%), with Judgment Thunder at 19–26%. Their other skills crit 7–31% of the time, and the median loadout's modelled crit chance is 5%. *Answered in 0.2.310:* the crit comes from Earth Punishment ([below](#cleric-builds-online-guides-against-the-server-logs-18-october)).
- **The KR metric cannot credit basic-chain steps 2 and 3.** They have KR codes but no global catalog entry, so the KR side drops them from its ceiling while the simulated side loses that share; adding the woven steps costs the Assassin, Chanter and Ranger 0.01–0.02 of fidelity by construction. Steps after a Dodge (up to 40% of a class's woven steps) are left out with the Dodge.

## Classification review of recent uploads (16 October): one real defect, the rest data-gated

The 51 newest public logs on the live server (889 encounter contexts, 15–16 October, all Live Meter sessions) tabulated by instance, difficulty, encounter type and boss role:

- **Difficulty is set on 78 %** of contexts (expedition normal / exploration / hard, transcendence stage 1 / 3, ascension hard / extreme, nightmare level 1). The 22 % without one are open-world combat (`pve_open_world` field bosses and `pve_unverified` trash on instance 0, which have no difficulty) plus nine nightmare contexts whose tier the catalog does not carry — data-gated.
- **Encounter types:** expedition 427, transcendence 229, open world 99, unverified 90, ascension 23, nightmare 21. `pve_unverified` is open-world combat with no boss and no instance (labelled *Combat N*): by design, not a gap.
- **Instance runs typed from the boss while the instance id was 0** (33 transcendence, 22 expedition, 18 ascension, 12 nightmare contexts): captures that began mid-instance, classified by the catalog's boss identity, as intended.
- **The defect:** 14 contexts carried an instance id (600092 Ferocious Horn Den, 600068) *and* an open-world type with a field-boss role — Watchdog Kwapo, Necromancer Duanka, Ferocious Horn Nuakum, trash pulls. In the recorder's own log the first segments after entering an instance read `map 1110, instance 600092, pve_open_world` (source *Recorded map ID + bundled open-world map table*) and the later ones `map 600092, expedition`: the instance-entry record arrived before the map record, so the open-world map id was stale, and the classifier typed those pulls open world (with a conflict note and no zone). **Fixed in 0.2.300:** a recorded instance id that the catalog knows wins over an open-world map id, the zone source says the map had not updated at entry, and the evidence carries `stale_map`. Older uploads reclassify on re-import or a server re-index with the pinned analyzer. The default-scope kill feed never listed these bosses (they are not on the field-boss list), so the observed timers were not affected; the `scope=all` feed was.
- **Ranking eligibility** is 29 of 889 contexts (expedition 21, transcendence 8), one per completed boss kill with clean capture — consistent with the per-run expectation; nothing here points at the gate.
- **Protocol variants:** no new identity, spawn or roster layout appeared in the eleven captures; the identity records were the known `33 36` / `44 36` / `45 36`, the zone state `21 36` / `23 36`. The census above lists the undecoded records by frequency for the probe.


## PvP in the recent uploads: what kind, the dungeon fragments and the missing party (19 October)

The log server listed 39 logs as PvP on 19 October (34 of them from one uploader, recorded with clients
0.2.255–0.2.317). Read segment by segment, with the counts only:

- **13 of the 39 hold PvP only inside dungeons and raids** (Krao Cave, Ferocious Horn Den, a transcendence
  and a nightmare instance): hundreds of fragments of a second to a few seconds, the segmentation storm older
  clients produced when one hit was misread. Only the party is inside a group instance, so since 0.2.320 a
  PvP flag there is typed by the instance (with a stale open-world map id too), and those logs leave the PvP
  lists when the server re-indexes.
- **The other 26 are open-world PvP**, 134 segments in the Abyss (map 20) and 22 in Altgard (map 1110),
  plus 29 on two maps nothing identifies: map 62 (17 segments of one recording, up to 7 allies and 10 enemy
  players, with spider mobs about) and map 320024. Since 0.2.320 open-world PvP is named by its zone.
- **No arena or battlefield fight was uploaded.** Arenas are recognised on maps 60 and 61 (user-confirmed
  captures); no battlefield map is identified. The type vocabulary already carries `pvp_battleground`, shown
  as *Battlefield*.
- **The missing party.** Outside a dungeon the meter keeps the effects of the players in the game's party
  list (`02 97`). No segment recorded on map 20 has ever held a party list longer than the recording
  player, in PvP or PvE, across the 105 uploads checked; in Altgard the list does decode
  (one recording holds a complete six- and seven-player list after a dungeon run). A list decoded before a
  zone load is carried across it, so a party formed before entering the Abyss would have shown. The archived
  diagnostic captures hold party lists from dungeon parties only (party names of 14 and 20 bytes, a dungeon
  id, five members), and the 18 October diagnostic ZIPs, the Abyss sessions, recorded no raw TCP and end
  with `roster_entries = 0`. Which of the decoder's checks an Abyss party list fails (an empty party name,
  more than 12 members, another opcode), or whether those sessions were solo, needs a capture with **Record
  TCP payloads** on while in a party in the Abyss, and one of an arena and a battlefield match.
- **Shown meanwhile:** the Party column marks a count made without the party list with *?* (it counts the
  players recorded); the overlay cannot tell a solo player from an undecoded party, so it says nothing.

## The 19 October recordings (0.2.323)

Three diagnostic recordings with raw TCP: eight seconds of HTTPS (a download, no game traffic); two hours over three characters on seven game connections (Krao Cave 600001, the 600092 dungeon twice, the nightmare 200003, a field boss, the open world 1110); and a minute of a level-27 Templar in the open world. They are archived in the diagnostics repository with name-free summaries.

**The overlay without its recorder: a meter started inside a zone.** Reported the next day: the live overlay showed everyone in the party but the recording player. Replays of the recordings had never shown it, because they fed every stream straight to the engine, while the live meter first finds the game's connection (`CombatFlowDetector`: 12 marker records within 3 s, at least 2.5 s after the first) and drops a new connection's packets until then. Replaying through that detector, as the live callback receives the rows, the two-hour recording's seven connection changes all kept the player: each new connection's zone load and self record came 3–4 s after the detector had found it. Starting the replay inside a zone instead, as an app opened or restarted for an update does, left the player unidentified until the next zone load: 33, 85, 224, 296 and 430 s after five of six starts (the sixth saw no fight in its ten minutes), with 22–84 % of the player's hits uncredited in the four that fought first, while the roster and spawn records named the party. An 11 October capture that started inside a zone shows the same: its recorder dealt the most damage, unnamed, for 107 s. The self record (`33 36`) comes only with a zone load. The MP record (`00 8d`, entity, `01 01 01`, u32) is sent for the local player only: all 908 in the two-hour recording and all 946 in the 15 October run were the self record's actor, and in the two captures that started inside a zone every MP record named the one actor with the most cast-end records (`06 38`, sent for the local player and NPCs). Since 0.2.323 the engine takes the local player from the MP record when no self record named one, and moves an identity that no longer fits (adopted from a capture stopped in another zone) after two MP records in a row name another actor. A self record still replaces it. In the same replays the player is found 2.5 s after the start whenever MP changes (that is, in combat), and 99.9 % of their hits are credited.

**Odyle Energy: a lead.** The Templar recording's login record (`0b 61`) carries, after a list of eight-digit ids, the varint 51591 and then two varints: 840 and 50, the value and the bonus noted in game; further entries repeat `<index> 51591 <value> 04 …`. One observation is not a decoded field: a second recording with a known, different value would confirm it, and a live reading needs the record sent when the value changes: claiming the Odyle Energy Cube after an Expedition, Transcendence or Sanctuary run spends it, and a recharge item adds 40 (gathering Odyle, the material, leaves it alone). The base cap is 560 and 840 with the Special Quai Membership; recharges can store more, up to 2,000, which may be the second value.

**The Templar's MP.** The first Templar readings (level 27, MP up to 1,911): Pummel and Punishing Strike each cost 120 (the readings fell 119 at each press), a basic-chain step restores 150, and MP regenerates 50 about every 7.5 s in combat and 250 a second out of it. The kit had inferred the 150 from the Gladiators' readings in 0.2.320 and charged Punishing Strike nothing; it now costs what Pummel costs ([methodology](methodology.md#the-templars-mp-from-a-recorded-templar-02323)).

**Cooldowns.** The cast record's last field is the cooldown after the caster's reduction: across the two-hour recording's eight classes a skill listed at 10 s reads 9.25 s (Insignia Explosion, Ambush) and one at 5 s 4.6 s (Heart Gore, Drill Dart); a specialization shortens some further (Rage Burst 27.05 s against 45 s listed, Rush Strike 9.6 s against 20 s). Players re-press most skills within a median 1.0–1.6 times the decoded cooldown; skills a proc resets come back sooner (Condemnation at a median 0.35 of it).

**Break gauge.** Maxima: 1,200 for the bosses of the 600092 dungeon and of Krao Cave 600001, 240 for Ultimate Berk (480 twice), 150 for the nightmare's bosses and a field boss. The gauge never reads 0: a broken boss's last reading is 0.7–5.0 % of its maximum (60 of 1,200 at most) and the next is a refill 5.5–7.8 s later (median 5.6–6.8 s per boss; one 34 s gap is a boss left alone). The log review counted a break from 5 % or less, so the highest reading was on its edge; since 0.2.323 it counts one from 8 % or less.

**Buffs and debuffs.** Every effect added in the recordings (`2b 38`) maps to a named skill or buff.

**The client's direction.** What the client sends is encrypted. The engine parsed it like the server's records whenever both directions reached it (fixed-port capture and every replay): a byte run that happened to frame as a record named a map, six maps that do not exist in a two-hour replay, and could have reset the zone. Since 0.2.323 only the round trip is read from it. Automatic port detection, the default, passes the server's direction alone and was not affected.


## Party sizes in the logs: solo fights and blank party-list slots (20 October, 0.2.323)

Most of 20 October's logs showed their party as "1?" and some as "3?". From the log server's public list (120 logs, contexts counted by day and type) and the two-hour 19 October recording:

- **Solo fights have no party list.** The game sends the party list (`02 97`) only to a player in a party: the two-hour recording has none until its party formed, and the solo Templar recording has none. Every solo fight was therefore exported with an incomplete roster. On 20 October the open-world (39), Nightmare (14) and unverified (18) fights had no party size, while 23 of 28 expedition fights did.
- **The list cannot tell solo from a party by its absence.** While in a party the list came in bursts (forming, entering a dungeon) and then up to seven minutes apart (416 s inside Krao Cave, 229 s in the open world). No other record appears only in a party: no opcode counted per minute across solo and party stretches was absent while solo.
- **What 0.2.323 does:** a PvE fight with no party list counts as a party of one when nobody else is in it. Every actor that hit, healed or was hit is the player, one of its pets, an NPC the game named, or an enemy the player hit or was hit by, and no other actor hit the fight's enemies while it lasted. With no party list every effect is kept, so other players' hits are in the session even though the fight leaves them out. In the Templar recording's one fight, five named players hit the same monsters, so it stays unknown, correctly. Log server 0.2.118 applies a narrower reading to the stored logs: a fight in a dungeon, Nightmare or Transcendence instance (only the party can be inside) with one member and nobody else recorded.
- **Blank party-list slots.** Some lists leave a member's slot all zeros (no database id, no name). Slots read in the two-hour recording: 170 lists held all five members, 14 lacked slot 5, 7 lacked slot 4 and 7 lacked slots 3 and 5. The recording player was always listed. The decoder stopped one member short and called the list incomplete, the source of the "3?" rows. None of the 112 members left out of such a list hit anything within 20 s of it. None fought before a later list named them again: 91 never fought again in the recording, and the other 21 next fought about 83 minutes later. Since 0.2.323 a list whose unread slots are all blank is complete. Replaying the recording through the meter and the export with and without that rule gave the same party verdict for every fight and the same total damage (127,526,203).
