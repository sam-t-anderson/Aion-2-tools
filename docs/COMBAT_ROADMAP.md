# Combat logging iterations

## Iteration 1 — 0.2.16

- Show verified automatic local identity. The optional name override is for captures started after the identity packet. Combat entity IDs change between instances; roster database character IDs and server IDs are retained separately when observed.
- Add **Split now** and **Automatic splits**. Automatic grouping uses the configurable idle gap; manual splits take effect on the next damage event.
- Add **Hide overlay**; Open overlay restores it.
- Save full decoded party sessions locally on Stop/normal Quit and show **Combat Logs → Recent full sessions**. TCP ZIPs remain bounded troubleshooting captures, not full dungeon recordings.
- Use one desktop, Pages and server viewer: Summary, Damage Done, Damage Taken and Healing; Table default, Timeline and Events; visibility toggles; actor/server labels; enemies below the graph; effect/death markers; recorded HP lines; class color controls; supported pet ownership; basic local/public log comparisons.
- Retain healing recipients only when explicitly decoded. Deaths use explicit death markers; absent markers do not prove survival. Skills on the timeline are recorded effects, not inferred cast starts.
- Accept verified normalized positions in imported a2logs, play those back and export a raid-plan file. **Live movement decoding remains unimplemented.**
- Keep the Pages banner, navigation links and theme button consistent on every page. Open public Logs and Leaderboard entries in the Pages viewer.
- Update the server to 0.2.5 to retain/display the optional a2log fields.

## Iteration 2 — community comparison and ownership

- Encounter-type filters: Transcendence dungeon, daily dungeon, expedition, ascension trials, nightmare and sanctuary raids, plus Unknown for logs without reliable classification. Record type, difficulty and game patch on upload; preserve them in local history and server indexes.
- A class-performance summary on desktop Combat Logs and Pages: distributions/box plots, median, quartiles, range and parse counts for the selected patch and encounter category. Expose data coverage; do not combine unrelated bosses, difficulties or patches into a misleading balance ranking.

- Player/run ranks by server, region and all submitted public community logs. Match boss, difficulty and patch, and report sample sizes; do not claim the dataset covers every player worldwide.
- Personal-record search/history using verified database character ID or name plus server.
- A dedicated comparison workflow with selectable matching players, encounter filters and multiple runs. Iteration 1 provides basic recorded-DPS comparisons.
- Edit published raid plans using locally stored owner credentials and authenticated updates that preserve the shared link. Add credential backup/import; author names must not grant ownership.

## Iteration 3 — protocol and replay enrichment

- Decode verified boss positions/movement and connect directly to Raid Planner import. Establish coordinates, map and arena transform first.
- Extend healing-recipient, pet-ownership and player-death coverage against representative captures.
- Refresh trusted creature metadata, retain observed type IDs and review unknown IDs. Future game/protocol updates cannot be guaranteed to supply names.
- Add supported casts, buffs, debuffs and resources as evidence permits. Unobserved threat, interrupts, mitigation and misses remain unavailable.
- Add periodic disk checkpoints and crash recovery. Iteration 1 saves on Stop/normal Quit; forced termination can lose the active session.

## Last priority — only after iterations 1–3 are complete

- PvP tracking with the same supported combat metrics and dedicated leaderboards for battlegrounds, arenas, Abyss, rifts and other verified modes. Separate PvP from PvE datasets and rankings.
- A server-local dashboard/domain for service health, capture/upload/error counts, logs by encounter/PvP type, storage and job metrics, build performance, class/player insights and data-quality coverage. Keep administrative operations authenticated and local/private by default; choose the host/domain when implementing it.

## Capture evidence

Both supplied 0.2.15 ZIPs automatically identify Spirited as entity 16306, server 2102, Gladiator level 45, without a name override. The boss tail contains HP and death records. Only approximately 65 and 33 seconds remain in those diagnostic buffers. Full new captures are needed to assess every metric across a dungeon run.
