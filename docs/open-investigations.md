# Open investigations

Findings from issues that were investigated but are **gated on inputs we do not control from
the client** — server log population, protocol captures, or source-backed catalog data — rather
than on unwritten code. Each entry records what was found, why it is not a client-side code fix
today, and the concrete next step. This complements the high-level gated items in
[the roadmap](COMBAT_ROADMAP.md).

## Ranked logs showing 0 (server)

**Finding: the ranking gate is working as designed; 0 reflects the sample, not a bug.**

A log is ranked only when it clears *every* evidence gate in `aion2calc/combat/quality.py`
`assess()` — `eligible = not reasons`. The gates require, among others: a full fight observed
from a full-health boss (`start_unverified`) through every recorded boss's death
(`end_unverified`); no storage-boundary crossing (`storage_boundary`); a complete, non-partial
capture (`partial_capture`); every participant identified by name/server/class
(`identity_unverified`); no capture/driver loss (`capture_loss`); a verified decoder/transport;
and party scope for party encounters (`party_scope_unverified`). The server reads this verdict
from the uploaded a2log — it never recomputes or accepts a client-asserted "eligible".

The local sample available here is composed of **rollover fragments and partial mid-instance
captures**, which legitimately trip `storage_boundary` / `partial_capture`, so 0 ranked is the
correct result for *that* sample. Whether the live server shows 0 depends on its uploaded
population clearing the same gates.

**Not changed, deliberately.** Loosening these gates blind — without a real ranked-eligible
capture to validate against — would admit incomplete fights into the ranking and corrupt the
very medians the leaderboard/stats pages report. (The `capture_loss` gate was already loosened in
a measured, validated way for recovered frame-skips in 0.2.x; that is the pattern to repeat.)

**Next step (needs server-side input):** on the live server, bucket a day of uploads by the
`reasons[]` they carry. If a *specific* reason dominates among fights that are otherwise complete,
that reason is the candidate to re-examine (with a captured example), exactly as the frame-skip
gate was. Until then there is nothing safe to change on the client.

## Logs page visual overhaul + tabs

**Finding: the reference page is a separate application; our server lacks most of its endpoints.**

The requested look (tabbed "Community combat logs", "Completed-run speed", "Boss progression",
"Class performance", "Highest observed build points") matches a separate, advanced single-page
app. This repository's Pages site is static HTML + vanilla JS talking to the open
`aion2logs` API, which exposes per-class stats (`/api/v1/stats`, `/api/v1/stats/<class>`) and
calibration — now surfaced by the new **[Class stats](../site/stats.html)** page — but **not** the
leaderboard/progression/speed-ranking endpoints those tabs would need. There is no
`/api/v1/leaderboard` in the open server checkout.

**Shipped the safe, verifiable slice.** The Class stats page (#83) delivers the "Class
performance" tab's substance against real, existing endpoints, read defensively so a missing field
or an unreachable server degrades to a friendly message instead of breaking the site.

**Not built, deliberately.** The remaining tabs would require either inventing server endpoints
that do not exist in the open repo, or hard-coding a UI against response shapes that cannot be
verified here, with no way to test the result in a browser against live data. Either path ships
unverifiable code to a public site.

**Next step:** decide per tab which data the open `aion2logs` server should expose (a server-repo
task), add the endpoint there, then add the tab here against the real shape — the same additive,
defensive pattern as the Class stats page.

## Database cleanup: catalog refs + enemy NPC types

Two distinct sub-problems:

### 1. Missing npc / map / title names for catalog IDs — **data-gated, pipeline already exists**

Names for content IDs come from the upstream published source, pulled in by the asset-refresh
auto-merge. Where the shipped catalog has an ID but no name, the **unknown-ids diagnostics beacon**
(`aion2calc/combat/diag_report.py` `unknown_from_doc` → `/api/v1/diag/unknown-ids`) already reports
the gap so the server can rank it and upstream can publish the name; the next asset refresh fills
it. This is self-healing as players encounter content and is not advanced by a client code change.
Hand-filling names would also fight the auto-refresh.

### 2. "Enemies missing NPC types (some may be players falsely flagged)" — **a real edge case; fix is validation-gated**

**Where it happens.** In `aion2calc/meter/session.py`, the entity-classification `else` branch
(around lines 1330–1334): an actor that is not a pet, not a party member, and whose name was never
captured is labelled `kind: "enemy"` with `mob_code = identity["spawns"].get(id, {}).get("mobCode")`.
When no spawn packet was seen for that actor, `mob_code` is `None` — an **enemy with no NPC type**.

**Why most are still correct.** In PvE, an unidentified actor that deals or takes party damage is
almost always a real mob whose spawn packet we missed. PvP opponents are already caught: the branch
sets `is_player = (id in opponents)`, so opponents get `is_player: True`. The genuine false-flag is
narrow: a nearby player who is neither in your party nor your opponent, whose name we never saw and
who has no mobCode — labelled `is_player: False, kind: "enemy", mob_code: None`.

**Proposed fix (not shipped).** Distinguish by **skill provenance**:
`aion2calc/meter/a2parser/lookup.py` `job_from_skill(skill_code)` maps only player-job skill-ID
families (100510–103500, 109300–109362, and the 10M–19.99M ranges) to a class; NPC skills fall
outside these. Pre-scan each group's records for actor → used skill-IDs; in the `else` branch, if a
mob_code-less actor used any skill with a non-`None` `job_from_skill`, treat it as a player
(`is_player: True`, `class` from the skill) instead of an enemy.

**Why it is gated, not shipped now.** This is a hot live-classification path shared by the meter,
overlay, enemy-HP reporter and DPS attribution. A single wrong skill→job mapping would reclassify a
real enemy as a player and silently corrupt everyone's DPS numbers — a worse defect than the narrow
edge case it fixes. It needs at least one real capture that reproduces the false-flag to validate
end-to-end before it can ship, consistent with the project rule that classification/eligibility
changes are not made blind. The unit-level correctness (a mage-skill actor with no name/mobCode →
player) is straightforward to assert once such a capture exists.

**Diagnostic gap noted for the server-repo:** `unknown_from_doc` skips entities whose `mob_code`
is not an integer, so untyped "enemies" (`mob_code: None`) are invisible to the unknown-ids beacon.
A non-identifying **count** of untyped-enemy entities could be added to the capture-health beacon
to quantify how often this happens in aggregate — the measurement that would tell us whether the
classification fix above is worth the risk. Left for when the server consumes it.
