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
  stamped on 17 different logs).

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
