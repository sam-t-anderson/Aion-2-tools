# Class comparison (boss, same settings, 2 optimizer iterations per class)

Each class is optimized with the same budgets (203 SP, 30 stigma points, 360 Daevanion) on its own median global loadout. **Gain** (optimized vs the typical top global build of that class, same rotation optimizer) is the reliable number. Every class has a hand-written kit (see `aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, with action times measured from recorded fights where captures exist; the kits' fidelity is shown as the share overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and assume a player doing nothing but damage, but for the Cleric's and the Chanter's heals at their recorded rates in a boss fight.

| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |
|---|---:|---:|---:|---:|---|
| sorcerer | 21,507 | 18,873 | +14.0% | 71% | [sorcerer](sorcerer/README.md) |
| chanter | 20,469 | 18,443 | +11.0% | 28% | [chanter](chanter/README.md) |
| templar | 20,293 | 16,903 | +20.1% | 39% | [templar](templar/README.md) |
| spiritmaster | 16,032 | 14,781 | +8.5% | 47% | [spiritmaster](spiritmaster/README.md) |
| cleric | 15,937 | 12,137 | +31.3% | 72% | [cleric](cleric/README.md) |
| gladiator | 13,063 | 11,593 | +12.7% | 33% | [gladiator](gladiator/README.md) |
| ranger | 12,175 | 10,701 | +13.8% | 61% | [ranger](ranger/README.md) |
| assassin | 9,346 | 8,009 | +16.7% | 41% | [assassin](assassin/README.md) |

The Cleric's boss number includes its heals at the recorded Clerics' rate (4.6 a minute, about 3.4 % of the fight). Recorded Clerics still fit about a third as many Condemnations into each Earth Punishment window: they press Judgment Thunder there as well.

The Chanter's boss number includes its heals at the recorded Chanters' rate (1.2 a minute, about 1 % of the fight).
