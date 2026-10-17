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

## Identity after a Kibelisk teleport — no capture spans one yet; a name-based re-bind ships meanwhile (0.2.300)

Reported: after a **Kibelisk** teleport (Altgard's and Verteron's fast-travel points, a teleport within the same map) the overlay did not re-acquire the local player. Every diagnostic capture supplied so far was checked for one (eleven captures, 10–15 October, replayed through the real engine with a timeline of zone-state and identity packets):

- A **zone load** always sends the self zone-transition record (`23 36`, entity 0, with the destination coordinates) and, within about a second, the local-player record (`33 36`: actor id, name, server, class, level). The engine resets identities on the first and re-identifies from the second. Three captures show this six, three and two times; identity never stayed missing.
- **In-instance actor-id changes without any zone packet** (Krao Cave, four times in ten minutes — revives or in-instance teleports) each came with a fresh `33 36` record, and identity followed every time.
- Two captures carried no `33 36` record at all because they started after login with no zone load (identity is acquired only from a zone load or the typed character name — the documented limit).
- **No capture contains a Kibelisk teleport in the open world** (the only open-world time, map 1110, ends shortly after the load). The hypothesis therefore stays unverified: a same-map teleport most likely sends the `23 36` transition (which resets the identities) but **no** new `33 36` record, so nothing re-identifies the player until the next zone load.

The raw records also showed that `23 36` frames whose varint is not 0 are JSON text from another program's traffic on the same interface (`"#6203", "damage": …`), not game records — harmless for the zone logic, which keys on entity 0, and skipped by the value probe.

**What ships (0.2.300):** the engine keeps the game-verified local name across a zone reset and, when no self record follows, re-binds the local player to the one actor that carries that name again (names are unique per server; exactly one match, summons excluded, never a guess), the same rule the typed character name already uses; a self record from the game still replaces it. A capture **spanning a Kibelisk teleport with raw TCP recording on** is what confirms the packet sequence; with one, the probe (`python -m aion2calc probe`) and the zone timeline can pin the exact record, and the reset can be refined if the game does send something at a teleport.

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
| `09 38` | NPC · … · skill · … · target · … · x/y/z · … | NPC cast at a player | Samples only. |
| `2e 37`, `3c 37` | entity · skill · positions and direction | dodge rolls and boss charges; skill-driven leaps and dashes (Leaping Slam, Rushing Smash, Infiltrate) | Samples only. |
| `1a 37`, `1b 37`, `1c 37`, `2f 37` | entity · x/y/z (f32), with a heading on `2f 37` | position and movement updates for players and NPCs | Samples only; units and map transforms unverified. |
| `00 36` | u64 | server clock in epoch milliseconds, about every 50 ms | The values track the capture clock. |
| `00 8d` | entity · subtype · value | `02 01 00` is the decoded HP feed (party members included); `01 01 01` hovers near 2,900 (a resource?); `01 01 03` and `01 01 06` count down by 500 and 750 per update | Probe targets. |
| `4a 36`, `4b 36` | local player · (stat id, value) × n / player · count · (stat id, signed delta) × n | stat lists and signed stat changes | Unverified. |

**Limits.** The 11 October crowd capture (194 players, a busy capture) matched only 35% of hits to a cast: the casts of distant players were missing (a median 9.4 s since that actor's previous cast), so cast coverage holds for the party and nearby players, not for a crowd. Party buffs (`0e 92`) cover party members only; `2b 38` covers everything in range, including effects re-sent as entities come into view.

**What it enables** (the roadmap tracks these): a cast timeline and rotation per player; real cast/lock times and cooldowns for the optimizer's kits and a skill-cooldown overlay; chain usage; buff and debuff uptime with sources; crowd control landed and how long it held; each player's break-gauge contribution and the break windows; dodges and leaps; NPC casts for a boss-ability timeline. **Still undecoded:** resources, shield absorption, interrupts, misses, mitigation, the unit and map transform of positions, and PvP rounds; overheal is computable from the HP feed but not yet checked.

## Classification review of recent uploads (16 October): one real defect, the rest data-gated

The 51 newest public logs on the live server (889 encounter contexts, 15–16 October, all Live Meter sessions) tabulated by instance, difficulty, encounter type and boss role:

- **Difficulty is set on 78 %** of contexts (expedition normal / exploration / hard, transcendence stage 1 / 3, ascension hard / extreme, nightmare level 1). The 22 % without one are open-world combat (`pve_open_world` field bosses and `pve_unverified` trash on instance 0, which have no difficulty) plus nine nightmare contexts whose tier the catalog does not carry — data-gated.
- **Encounter types:** expedition 427, transcendence 229, open world 99, unverified 90, ascension 23, nightmare 21. `pve_unverified` is open-world combat with no boss and no instance (labelled *Combat N*): by design, not a gap.
- **Instance runs typed from the boss while the instance id was 0** (33 transcendence, 22 expedition, 18 ascension, 12 nightmare contexts): captures that began mid-instance, classified by the catalog's boss identity, as intended.
- **The defect:** 14 contexts carried an instance id (600092 Ferocious Horn Den, 600068) *and* an open-world type with a field-boss role — Watchdog Kwapo, Necromancer Duanka, Ferocious Horn Nuakum, trash pulls. In the recorder's own log the first segments after entering an instance read `map 1110, instance 600092, pve_open_world` (source *Recorded map ID + bundled open-world map table*) and the later ones `map 600092, expedition`: the instance-entry record arrived before the map record, so the open-world map id was stale, and the classifier typed those pulls open world (with a conflict note and no zone). **Fixed in 0.2.300:** a recorded instance id that the catalog knows wins over an open-world map id, the zone source says the map had not updated at entry, and the evidence carries `stale_map`. Older uploads reclassify on re-import or a server re-index with the pinned analyzer. The default-scope kill feed never listed these bosses (they are not on the field-boss list), so the observed timers were not affected; the `scope=all` feed was.
- **Ranking eligibility** is 29 of 889 contexts (expedition 21, transcendence 8), one per completed boss kill with clean capture — consistent with the per-run expectation; nothing here points at the gate.
- **Protocol variants:** no new identity, spawn or roster layout appeared in the eleven captures; the identity records were the known `33 36` / `44 36` / `45 36`, the zone state `21 36` / `23 36`. The census above lists the undecoded records by frequency for the probe.

