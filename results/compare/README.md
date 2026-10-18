# Class comparison (boss, same settings, 2 optimizer iterations per class)

Each class is optimized with the same budgets (203 SP, 30 stigma points, 360 Daevanion) on its own median global loadout. **Gain** (optimized vs the typical top global build of that class, same rotation optimizer) is the reliable number. Every class has a hand-written kit (see `aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, with action times measured from recorded fights where captures exist; the kits' fidelity is shown as the share overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and assume a player doing nothing but damage.

| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |
|---|---:|---:|---:|---:|---|
| sorcerer | 21,507 | 18,873 | +14.0% | 71% | [sorcerer](sorcerer/README.md) |
| gladiator | 19,473 | 16,679 | +16.7% | 29% | [gladiator](gladiator/README.md) |
| cleric | 16,342 | 12,411 | +31.7% | 71% | [cleric](cleric/README.md) |
| spiritmaster | 16,032 | 14,781 | +8.5% | 47% | [spiritmaster](spiritmaster/README.md) |
| templar | 15,700 | 14,309 | +9.7% | 12% | [templar](templar/README.md) |
| ranger | 12,175 | 10,701 | +13.8% | 61% | [ranger](ranger/README.md) |
| chanter | 11,872 | 10,760 | +10.3% | 35% | [chanter](chanter/README.md) |
| assassin | 9,346 | 8,009 | +16.7% | 41% | [assassin](assassin/README.md) |

The Cleric's number is a ceiling for a Cleric that never heals: recorded Clerics heal and fit about a third as many Condemnations into each Earth Punishment window.
