"""Rebuild the static browser allocation catalog from bundled global class data.

Run from the repository root with PYTHONPATH=. python tools/export_build_catalog.py.
"""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
from aion2calc.kit.base import SP_COST, STIGMA_COST, SPEC_SLOT_LEVELS
classes={}
for p in sorted((root/'aion2calc/data/global/classes').glob('*.json')):
 raw=json.loads(p.read_text(encoding='utf-8'))
 def icon(value):
  from urllib.parse import parse_qs,urlparse
  if value and value.startswith('/api/image?'):
   value=parse_qs(urlparse(value).query).get('src',[''])[0]
  return value if value and value.startswith('https://metabot.gg/') else ''
 skills=[]
 for s in raw['skills']:
  row={k:s.get(k) for k in ('id','name','kind','unlock','buyMax','max','need')}
  row['icon']=icon(s.get('icon'))
  row['specs']=[{k:e.get(k) for k in ('id','text','unlock')} for e in s.get('specs',[])]
  skills.append(row)
 boards=[]
 for b in raw['boards']:
  boards.append({k:b[k] for k in ('id','name','needLevel')} | {'nodes':[
   {k:n.get(k) for k in ('id','row','col','type','grade','cost','needLevel','label','short','skillId','skillName','skillLevels','stats')}
   for n in b['nodes']]})
 classes[p.stem]={'source':raw.get('source'),'skills':skills,'boards':boards,'budget':raw['budget']}
payload={'version':1,'classes':classes,'skill_cost':SP_COST,'stigma_cost':STIGMA_COST,
 'spec_slot_levels':SPEC_SLOT_LEVELS,'crystal_boards':['Nezekan','Zikel','Vaizel','Triniel'],
 'note':'Bundled class catalog and planner rules; not independently verified against the current installed game build. Entered point totals and bonus levels are assumptions. Catalog validation is not server/game verification.'}
# Reuse the simulator's bundled item rules; source slugs are not numeric game IDs.
import gzip
from dataclasses import fields
from aion2calc.model.stats import Stats
from aion2calc.plan import items as I
from aion2calc.plan.pantheon import DEITIES
allowed={f.name for f in fields(Stats)}-{'level','pvp','skill_bonus'}
items=[]
for entry in json.loads(gzip.decompress((root/'aion2calc/data/seed/items.json.gz').read_bytes())):
 item=entry['data'];category=item.get('category')
 if category not in {v for values in I.SLOTS.values() for v in values}|set(I.WEAPON.values()):continue
 levels=[]
 for level in range(min(20,I.max_enchant(item))+1):
  stats=I.item_stats(item,level,mode='none')
  levels.append({k:v for k,v in stats.items() if k in allowed and v>=0})
 rolls=[]
 for option in I.roll_options(item) if I.roll_count(item) else []:
  numbers=[abs(n) for n in I._numbers(option['range'])]
  low,high=min(numbers),max(numbers)
  unit=I._label_value(option['stat'],'1'+('%' if '%' in option['range'] else ''),False)
  rolls.append({'stat':option['stat'],'range':option['range'],'min':low,'max':high,
                'unit':{k:v for k,v in unit.items() if k in allowed and v>=0}})
 items.append({'roll_count':min(20,I.roll_count(item)),'roll_options':rolls,'slug':item['slug'],'name':item.get('name',item['slug']),'icon':item.get('icon',''),'category':category,'grade':item.get('grade',''),'required_level':int((I._numbers(item.get('meta',{}).get('Required Level','0')) or [0])[0]),'levels':levels})
payload['items']=sorted(items,key=lambda x:x['slug'])
payload['equipment_slots']=I.SLOTS
payload['class_weapons']=I.WEAPON
payload['deities']=[{'name':name,'field':field} for name,field in DEITIES]
payload['item_note']='Bundled catalog fixed stats and listed cumulative enchant bonuses only; Random roll choices use the bundled source pool/ranges and entered values; ownership, current-build applicability and unsupported defensive effects are not inferred. Source slugs remain separate from numeric game IDs.'
payload['revision']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
(root/'aion2calc/app/static/build-catalog.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')

