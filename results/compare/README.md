# Class comparison (boss, each class's reported budgets, 2 optimizer iterations per class)

Each class is optimized on its own median global loadout with the highest skill, stigma and Daevanion points and bonus skill levels (gear rolls and arcana cards) its players have reported to the community server: reports, not verified game caps. The planner's bundled presets, offered before a character is imported, are made this way; a character's own optimization uses its own points. The budgets differ by class, so the DPS columns also compare different resources. **Gain** (optimized vs the typical top global build of that class with the same points and bonus levels, same rotation optimizer) is the reliable number. Every class has a hand-written kit (see `aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, with action times measured from recorded fights where captures exist; the kits' fidelity is shown as the share overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and assume a player doing nothing but damage, but for the Cleric's and the Chanter's heals at their recorded rates in a boss fight.

| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Skill / stigma / Daevanion points | Bonus levels (most on one skill) | Report |
|---|---:|---:|---:|---:|---:|---:|---|
| sorcerer | 49,658 | 44,920 | +10.5% | 78% | 383 / 188 / 417 | 50 (6) | [sorcerer](sorcerer/README.md) |
| chanter | 37,594 | 35,550 | +5.7% | 40% | 383 / 300 / 416 | 76 (13) | [chanter](chanter/README.md) |
| templar | 35,686 | 31,666 | +12.7% | 66% | 383 / 300 / 416 | 70 (9) | [templar](templar/README.md) |
| gladiator | 31,875 | 30,562 | +4.3% | 43% | 383 / 260 / 416 | 90 (14) | [gladiator](gladiator/README.md) |
| cleric | 29,700 | 19,286 | +54.0% | 78% | 383 / 116 / 412 | 43 (5) | [cleric](cleric/README.md) |
| assassin | 26,845 | 20,916 | +28.3% | 59% | 383 / 268 / 438 | 52 (6) | [assassin](assassin/README.md) |
| ranger | 20,048 | 17,243 | +16.3% | 61% | 383 / 276 / 415 | 59 (7) | [ranger](ranger/README.md) |
| spiritmaster | 17,205 | 15,859 | +8.5% | 47% | 347 / 50 / 305 | none reported | [spiritmaster](spiritmaster/README.md) |

The Cleric's boss number includes its heals at the recorded Clerics' rate (4.6 a minute, about 3.4 % of the fight). Recorded Clerics still fit about a third as many Condemnations into each Earth Punishment window: they press Judgment Thunder there as well.

The Chanter's boss number includes its heals at the recorded Chanters' rate (1.2 a minute, about 1 % of the fight).
