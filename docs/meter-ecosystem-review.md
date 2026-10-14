# Third-party AION 2 meter/tool review

A survey of other community AION 2 damage meters and companion tools, done to sanity-check our
decoder approach and to harvest ideas. **We did not copy code from any of these.** Most are GPL
or MIT, but adopting source would entangle licenses and reverse-engineering provenance; the value
here is cross-validation and feature ideas, which are not copyrightable. Concrete protocol facts
(opcodes, markers) noted below are leads to **verify against our own captures**, not code to lift.

Reviewed on 2026-10-14. Repository details can drift; treat specifics as of that date.

## What this confirms about our approach

Every meter here captures the game's traffic **passively** with Npcap/libpcap — the same approach
as our `scapy`/pcap decoder — and none reads game memory or injects. Several independently arrive
at the same building blocks we already use:

- **TCP reassembly → varint frames → LZ4 bundles.** Matches our decoder exactly.
- **Summon/pet damage attributed to owners** via spawn owner links, summoner names, cast variants
  and power scalars — the same signals as our `scan_summon_links` / `summon_owners` / power-scalar
  path (and the Spiritmaster owner-fold work in 0.2.265–0.2.266).
- **Nicknames are absent from damage packets** and only appear on events like teleport / dungeon
  entry — exactly why we re-acquire identity after tele/port/revive (0.2.253 et al.).
- **Reverse-engineering traces back to `taengu` and `Karim`**, the same upstream our asset-refresh
  already tracks (`taengu/A2Tools-DPS-Meter`). One meter (`aether-meter`) is built directly on our
  parser, pinned by revision — our decoder is effectively a reference implementation for the
  community.

Net: our capture/decode architecture is standard and well-validated. The gaps are feature breadth
and a few undecoded record types, not the core pipeline.

## The repositories

| Repo | Lang | License | Notes |
| --- | --- | --- | --- |
| `cyberbadger6969/aion2-dps-meter` | C# / .NET | GPL-3.0 | Most detailed protocol notes (see leads below). Field-boss timers, owner attribution, LZ4/varint. |
| `SkeeveAN/Aion-DPS-Meter` | C# / .NET WPF | MIT | Boss-fight replay (positions, attack areas), learns skill AoE from who it hits, `Tools/aion2-dat` text-table extractor, 9 UI languages, OBS source. |
| `Wany917/aether-meter` | Rust / Tauri / TS | GPL-3.0 | **Built on our parser.** Has a **value-probe workflow** to discover undecoded opcodes; targets hidden cubes, Odyle Energy, quest progress, entry counters. |
| `ZDYoung0519/NOIA2` | Rust / Tauri / TS | GPL-3.0 | Character scoring; intentionally shows unknown actors / distant summons for parser transparency. |
| `Klauensprung/Wingbeat-Aion-Dps-Meter` | C# / .NET | (third-party notices only) | Skill **cooldown overlay** with charge variants; zoomable party rotation timelines; fully offline bundled data. |
| `Kuroukihime/AIon2-Dps-Meter` (RATmeter) | C# / .NET WPF | GPL-3.0 | Buff + cooldown overlays; **stat-efficiency "what-if" calculator** (simulate a stat change before applying) — conceptually our stat weights. |
| `filvoch/AionCoreUpdate` (AionCore) | (closed) | none published | Source not public — **ideas only.** **Hidden Cube radar** (the flagged feature), kill-in / enrage estimate, fight history. |
| `cavernwrenorbit/aion-2-companion-tool` | n/a | MIT | Companion app: **farming routes with waypoints**, world map (NPC/flight/gathering nodes), dungeon timers, loadout planner, item DB. (Makes some unsupported safety claims; treat with caution.) |
| `hydrasergeanttype/aion2-dps-meter-2026` | TS + .NET | MIT | Contribution bars, boss-only mode, experimental timeline playback; auto-detects Steam and PURPLE clients. |
| `lunixxx37/aion2-protocol-research` | Python | MIT | Protocol research: TCP framing, RSA-OAEP handshake, RC4, PCAP tooling, an opcode catalog (`docs/OPCODES.md`, `protocol/opcodes.json`). |

## Concrete protocol leads to verify against our captures

From `cyberbadger6969/aion2-dps-meter`'s README (facts to confirm, not code):

- **Field-boss respawn timers in opcode `01 91`** — carries a map number plus per-boss "alive
  since" / "back at" data; boss slots map to NPC codes via a per-map block learned at runtime. If
  confirmed, this would let the overlay/timers show **accurate server-driven field-boss respawns**
  instead of a local forecast (an open roadmap item).
- **Stream lock-on via a `0E 00 36` heartbeat marker** — worth cross-checking against our own
  `0x36`-based framing in `scan_summon_links` / the decoder.

`lunixxx37/aion2-protocol-research` publishes an opcode catalog (`protocol/opcodes.json`); a
careful diff against our decoded set could surface records we don't yet read. Any adoption must be
re-derived and validated on our own captures before shipping.

## Ideas worth adopting (added to the roadmap)

- **Value-probe tool for undecoded opcodes** (from `aether-meter`): record an action, enter the
  value you saw in-game, find the opcode/offset that holds it. A high-leverage way to decode hidden
  cubes, Odyle Energy, quest/entry counters, and the `01 91` field-boss block safely and verifiably.
- **Hidden Cube radar** (from AionCore): the flagged feature — a direction/distance overlay for
  cube spawns. Large; needs the cube-location packet decoded first (good first target for the probe).
- **Skill-cooldown overlay** (Wingbeat, RATmeter): a compact cooldown strip alongside the meter.
- **Farming routes** (companion-tool): per-faction and Abyss gathering/mob routes with waypoints on
  the maps page (tracked separately on the roadmap).
- **Field-boss timer auto-start on a nearby boss death** and a **server-driven respawn feed** (the
  `01 91` lead), replacing the local forecast.
- **Stat-efficiency what-if** (RATmeter): we already compute stat weights; a one-click "add +X to
  this stat and show the DPS delta" is a small UX win on top.

None of these are implemented here; they are recorded so the ideas aren't lost. Features that need
a newly decoded packet are gated on verified captures, consistent with the rest of the roadmap.
