# Class comparison (boss, same settings, 2 optimizer iterations per class)

Each class is optimized with the same budgets (203 SP, 30 stigma points, 360 Daevanion) on its own median global loadout. **Gain** (optimized vs the typical top global build of that class, same rotation optimizer) is the reliable number. Every class has a hand-written kit (see `aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, with action times measured from recorded fights where captures exist; the kits' fidelity is shown as the share overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and assume a player doing nothing but damage, but for the Cleric's and the Chanter's heals at their recorded rates in a boss fight.

| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |
|---|---:|---:|---:|---:|---|
| chanter | 22,515 | 20,007 | +12.5% | 30% | [chanter](chanter/README.md) |
| sorcerer | 21,778 | 19,075 | +14.2% | 76% | [sorcerer](sorcerer/README.md) |
| templar | 20,356 | 16,382 | +24.3% | 43% | [templar](templar/README.md) |
| cleric | 17,050 | 12,863 | +32.6% | 73% | [cleric](cleric/README.md) |
| spiritmaster | 16,910 | 15,780 | +7.2% | 47% | [spiritmaster](spiritmaster/README.md) |
| gladiator | 13,992 | 12,004 | +16.6% | 32% | [gladiator](gladiator/README.md) |
| ranger | 13,047 | 11,751 | +11.0% | 63% | [ranger](ranger/README.md) |
| assassin | 12,097 | 9,150 | +32.2% | 51% | [assassin](assassin/README.md) |

The Cleric's boss number includes its heals at the recorded Clerics' rate (4.6 a minute, about 3.4 % of the fight). Recorded Clerics still fit about a third as many Condemnations into each Earth Punishment window: they press Judgment Thunder there as well.

The Chanter's boss number includes its heals at the recorded Chanters' rate (1.2 a minute, about 1 % of the fight).
