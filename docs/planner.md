# Gear, arcana, pantheon and genus planning, and learning from your fights

Everything here runs on simulated DPS: each candidate change is equipped and the fight is simulated
again (about 15 ms per run). It uses your character's own skill levels, Daevanion nodes and stigmas,
the best specializations for those levels, and the class's optimized priority list. No linear stat
weights are used.

Use it from the app's **Gear & Advice** page, or with:

```bash
python -m aion2calc advise "Name" --server Zikel              # writes ADVICE.md + advice.json
python -m aion2calc inventory "Name" --add aulamus-ring --enchant 8
python -m aion2calc inventory "Name" --add parchment-of-magic --enchant 2 --skill Hellfire=2 --skill Blaze=1
python -m aion2calc learn                                     # refit the calibration from saved fights
```

The advice is saved in the data folder, under `results/characters/<name>_<server>/ADVICE.md`.

## Inventory

The official character page shows only what is equipped. Those items are imported with their exact
rolls, manastones, skill options and deity points. Bag and warehouse items have to be added, either
on the Gear & Advice page (search the catalog, set the enchant level and any skill options) or by
editing `inventory/<character>.json` in the data folder:

```json
{"slug": "aulamus-ring", "enchant": 8, "rolls": [["Critical Hit", 41], ["Attack", 28]],
 "skills": [["Hellfire", 2]]}
```

Without `rolls`, an item counts as the expected value of its roll pool. Items that have fixed
sub-stats (for example the Spiritforged weapons) always count them.

## What it plans

| Planner | Answers |
|---|---|
| Best set from inventory | which owned item to wear in every slot. Rings, earrings, bracelets and runes fill both slots of their pair |
| Goal gear | per slot, the best catalog item at its max enchant (up to +15) with good rolls (the most valuable distinct stats of its pool, at mid range). **Next** is the nearest item level that still gains at least 2%, so you have a goal before end-game |
| Upgrade path | one change at a time, always the biggest simulated gain: an enchant level, a reroll toward good rolls, or the slot's next goal |
| Arcana | per slot: the variant whose deity stat is worth more, the skill options to chase, the ideal Unique +5 (9 options, at most 4 per skill), the expected value of random options, and whether each owned arcana is above the average for its grade and level |
| Pantheon | the ten deity stats by DPS per point (Life, Destiny and Space do nothing for damage), your current split, the arcana variant choices and the best bracelet deity roll |
| Titles | per title slot (Attack, Defense, Other): the equipped title, the best one you own, the best in the game with how to earn it, and the titles worth collecting for their owned bonus |
| Genus insight | the value of each analysis line you enter, the lines to reroll first, the genus damage line to chase (slots 4 and 7, 2.4-4.8%), and which genus to level |
| Your fights | skills you cast less than the optimal rotation does, idle time, and specializations that differ from the optimized build, across all of the character's saved fights |

### How it looks

The results are laid out like the game's own windows, using the game's item, arcana and skill icons
(served from the official CDN and metabot, and cached locally):

| Window | Layout |
|---|---|
| Equipment | a paper doll: armor down the left, accessories down the right, arcana under the character. Each slot shows the item icon in its grade color with its enchant level. ▲ marks a better item in your inventory, ◆ the next goal's gain, # its upgrade-path step. Click a slot to see *Wearing → From your inventory → Next goal → Best in slot* as item cards, with rolls, skill options and links to the item pages |
| Upgrade path | a row of item cards in order, each with its action (＋1 enchant, ⟳ reroll, ⇄ replace), the step's gain and the running total |
| Arcana | the five arcana cards (Chalice, Parchment, Compass, Bell, Mirror) with the variant to use, its deity stat, the target skill options as skill icons with their levels, the ideal and average gain, and your own arcana marked keep or replace |
| Titles | the three title slots as title plates (equipped, best owned, best in slot), and the titles worth collecting |
| Pantheon | the ten deities with their Lord, your points, what the stat does, and the DPS of 10 more points; the best one is highlighted |
| Genus Insight | one tab per genus, with its 3×3 analysis grid: locked slots, slots 4 and 7 framed as the genus-damage slots, each line with its DPS value (or *no damage: reroll*), plus your fight time per genus and the level order |

Every window has **Copy as text**, and **My screenshot** to pin your own in-game screenshot next to
it for side-by-side checking.

### Titles

Each title's slot comes from its metabot page ("Role: Offensive" → Attack, "Defensive" → Defense,
"Utility" → Other). Titles whose page gives no role are placed by their stats. The sync reads the
pages of new or changed titles. The official page shows only equipped titles, so list the ones you
own on the Gear & Advice page (one name per line) to get "best you own".

### Genus insight

Lines named after a genus ("Varian Damage Boost", "Cogni Attack") count only against monsters of
that genus. The planner weighs them by your fight time per genus. Each boss's genus is read from its
metabot page ("Type: Varian"), looked up once, and cached in `data/global/monster_genus.json`. With no
saved fights, the four main genera count equally. The level table (slot unlocks and grade chances)
comes from the global client data published on wikily.gg. The full property list per slot is not
public, so you enter the lines you have.

Enter lines on the Gear & Advice page, one per slot: `Varian | 7 | 4 | Varian Damage Boost | 3.6%`
(genus, insight level, slot, stat, value).

### Two caveats

* Tempo stats (Combat Speed, Cooldown) shift every cast time. With a fixed priority list, a single
  simulation can alias. Time and Illusion are therefore valued with the stat weights, which use
  re-optimized rotation slopes. Skill-level values are kept non-decreasing, because a level never
  lowers damage once the rotation adapts.
* Goal items are compared with good rolls and without manastones. Your equipped items keep their
  real manastones.

## Learning from your fights

Every fight you save (an AbyssLogs link, A2DIL, JSON or CSV) is matched to what its player had
equipped at the time. Each character import stores a snapshot, and the fight uses the nearest
snapshot taken before it. The fight then becomes an **observation**: the model's prediction for
that exact gear next to what the log recorded.

| Compared | Becomes |
|---|---|
| crit rate vs. the crit curve at the character's Critical Hit | a shifted crit curve |
| double, perfect and multi-hit rates vs. the stats | rate factors |
| damage per cast of each skill vs. the simulation | per-skill damage factors |
| casts per minute and idle time | your execution numbers (advice only, never fed into the model) |

The observations are pooled per class into `data/calibration/<class>.json`. Every factor is shrunk
toward 1, as if 8 fights agreed with the community model, and kept within bounds (rates 0.6-1.6x,
skills 0.75-1.33x, crit curve ±250). One odd log cannot swing the model, and more fights move it
further. The calibration turns on once 2 fights are matched. It is used by the planners and the
advice, never by the published class reports. The model is refit after every import, and
`python -m aion2calc learn` refits it from scratch.

With a log server set for sharing, the app also pulls that server's **community calibration**
(when it publishes one), learned from everyone's uploads. It is the starting point,
and your own fights override it where they exist. So the model is calibrated from day one, before
you have saved any fights of your own.

The more fights you import after re-importing your character (so the snapshot matches the gear you
wore), the closer the simulation gets to your actual damage. The planners then rank changes on that
calibrated model.
