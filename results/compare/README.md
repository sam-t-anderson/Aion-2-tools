# Class comparison (boss, same settings, 1 optimizer iteration per class)

Each class is optimized with the same budgets (203 SP, 30 stigma points, 360 Daevanion) on its own median global loadout. **Gain** (optimized vs the typical top global build of that class, same rotation optimizer) is the reliable number. Every class has a hand-written kit (see `aion2calc/kit/`) that models its chains, crowd-control combos, pet and damage-amp buffs, with action times measured from recorded fights where captures exist; the kits' fidelity is shown as the share overlap with Korean A2DIL dummy logs where available. **This is not a class tier list**: absolute numbers depend on each kit's audited assumptions (pet cadence, boss-break uptime, DoT spread) and assume a player doing nothing but damage.

| Class | Optimized DPS | Typical top build DPS | Gain | KR share overlap | Report |
|---|---:|---:|---:|---:|---|
| sorcerer | 17,879 | 16,512 | +8.3% | 80% | [sorcerer](sorcerer/README.md) |
| cleric | 16,342 | 12,411 | +31.7% | 71% | [cleric](cleric/README.md) |
| spiritmaster | 10,649 | 9,594 | +11.0% | 27% | [spiritmaster](spiritmaster/README.md) |
| gladiator | 9,992 | 6,926 | +44.3% | 28% | [gladiator](gladiator/README.md) |
| templar | 8,884 | 7,616 | +16.6% | 53% | [templar](templar/README.md) |
| ranger | 8,837 | 7,070 | +25.0% | 61% | [ranger](ranger/README.md) |
| chanter | 8,298 | 7,513 | +10.4% | 39% | [chanter](chanter/README.md) |
| assassin | 8,014 | 6,826 | +17.4% | 37% | [assassin](assassin/README.md) |

The Cleric's number is a ceiling for a Cleric that never heals: recorded Clerics heal and fit about a third as many Condemnations into each Earth Punishment window.
