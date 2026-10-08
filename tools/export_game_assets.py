"""Refresh unmodified icons referenced by the bundled catalogs (network required)."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
root=Path(__file__).resolve().parents[1]/'aion2calc/app/static'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--additional',type=Path,help='Validated source skill references produced by refresh_assets.py')
parser.add_argument('--refresh-existing',action='store_true')
args=parser.parse_args()
out=root/'game-assets';out.mkdir(exist_ok=True)
build=json.loads((root/'build-catalog.json').read_text(encoding='utf-8'))
craft=json.loads((root/'crafting-catalog.json').read_text(encoding='utf-8'))
urls={s['icon'] for c in build['classes'].values() for s in c['skills'] if s['icon']}
urls|={s['icon'] for s in craft['items'].values() if s['icon']}
urls|={s['icon'] for s in build.get('items',[]) if s.get('icon','').startswith('https://metabot.gg/web/aion2/items/')}
urls|={'https://metabot.gg/web/aion2/classes/'+c+'.webp' for c in build['classes']}
references={}
for c in build['classes'].values():
 for skill in c['skills']:
  if skill['icon']:references['metabot:skill:'+str(skill['id'])]={'namespace':'metabot','kind':'skill','id':str(skill['id']),'url':skill['icon']}
for key,item in craft['items'].items():
 if item['icon']:references['gamers4life:item:'+key]={'namespace':'gamers4life','kind':'item','id':key,'url':item['icon']}
for item in build.get('items',[]):
 if item.get('icon','').startswith('https://metabot.gg/web/aion2/items/'):
  references['metabot:item-slug:'+item['slug']]={'namespace':'metabot','kind':'item-slug','id':item['slug'],'url':item['icon']}
if args.additional:
 import re
 extra=json.loads(args.additional.read_text(encoding='utf-8'))
 if not isinstance(extra,list) or len(extra)>10000:raise ValueError('Invalid extra skill reference list')
 for row in extra:
  if not isinstance(row,dict) or not re.fullmatch(r'[1-9][0-9]{0,18}',str(row.get('id',''))):raise ValueError('Invalid source skill ID')
  expected='https://metabot.gg/web/aion2/skills/'+str(row['id'])+'.webp'
  if row.get('url')!=expected:raise ValueError('Source skill icon does not agree with its ID')
  urls.add(expected);references['metabot:skill:'+str(row['id'])]={'namespace':'metabot','kind':'skill','id':str(row['id']),'url':expected}
def fetch(url):
 name=hashlib.sha256(url.encode()).hexdigest()[:24]+'.webp'
 path=out/name
 if args.refresh_existing or not path.exists():
  with urlopen(Request(url,headers={'User-Agent':'Aion2Calc asset snapshot (+https://github.com/sam-t-anderson/Aion-2-tools)'}),timeout=25) as r:
   data=r.read(256*1024+1)
   if len(data)>256*1024 or not data.startswith(b'RIFF') or data[8:12]!=b'WEBP':raise ValueError('Not a bounded WebP')
   path.write_bytes(data)
 return url,'game-assets/'+name
result={};failed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
 futures={pool.submit(fetch,u):u for u in sorted(urls)}
 for f in concurrent.futures.as_completed(futures):
  try:u,path=f.result();result[u]=path
  except Exception:failed.append(futures[f])
manifest={'retrieved_at':datetime.now(timezone.utc).isoformat(),'sources':['https://metabot.gg/','https://gamers4.life/aion-2/database/en/crafting-calculator/'],'note':'Unmodified game icons referenced by bundled catalogs. Game art belongs to its owners; source URL namespaces are kept separate. Missing assets retain remote-source fallback.','references':references,'assets':dict(sorted(result.items())),'missing':sorted(failed)}
(root/'game-assets.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(root/'game-assets.js').write_text('/* Source-attributed, unmodified game icon snapshot. See game-assets.json. */\nwindow.A2BundledAssets={base:new URL(".",document.currentScript.src).href,files:'+json.dumps(manifest['assets'],separators=(',',':'))+'};\n',encoding='utf-8')
print('Bundled',len(result),'assets;',len(failed),'missing;',sum(p.stat().st_size for p in out.iterdir()),'bytes')
if failed:print('Missing source URLs:',json.dumps(failed))
