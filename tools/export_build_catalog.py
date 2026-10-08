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
payload['revision']=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
(root/'aion2calc/app/static/build-catalog.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')

