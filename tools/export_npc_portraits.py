"""Bundle portraits only for existing catalog IDs with exact English name agreement."""
import concurrent.futures
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
root=Path(__file__).resolve().parents[1]
static=root/'aion2calc/app/static'
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path,help='Downloaded https://dbaion2.ru/data-en/npcs.json')
raw=parser.parse_args().source.read_bytes()
source=json.loads(raw.decode('utf-8-sig'))
catalog=json.loads((root/'aion2calc/meter/a2parser/data/i18n/npcs/en.json').read_text(encoding='utf-8'))
rows={str(r['id']):r for r in source if catalog.get(str(r.get('id')),{}).get('isBoss')
      and catalog[str(r['id'])]['name'].casefold()==str(r.get('name','')).casefold()
      and re.fullmatch(r'[A-Za-z0-9_]{1,120}',str(r.get('icon') or ''))}
urls={'https://dbaion2.ru/icons/'+r['icon']+'.webp' for r in rows.values()}
def fetch(url):
 name=hashlib.sha256(url.encode()).hexdigest()[:24]+'.webp';p=static/'game-assets'/name
 if not p.exists():
  with urlopen(Request(url,headers={'User-Agent':'Aion2Calc asset snapshot'}),timeout=25) as r:
   data=r.read(256*1024+1)
   if len(data)>256*1024 or not data.startswith(b'RIFF') or data[8:12]!=b'WEBP':raise ValueError('Not bounded WebP')
   p.write_bytes(data)
 return url,'game-assets/'+name
assets={};missing=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 tasks={pool.submit(fetch,u):u for u in sorted(urls)}
 for f in concurrent.futures.as_completed(tasks):
  try:u,path=f.result();assets[u]=path
  except Exception:missing.append(tasks[f])
portraits={k:{'name':r['name'],'icon':'https://dbaion2.ru/icons/'+r['icon']+'.webp'} for k,r in rows.items() if 'https://dbaion2.ru/icons/'+r['icon']+'.webp' in assets}
target=root/'aion2calc/meter/a2parser/data/i18n/npc-portraits';target.mkdir(exist_ok=True)
(target/'en.json').write_text(json.dumps(portraits,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
manifest=json.loads((static/'game-assets.json').read_text(encoding='utf-8'))
manifest['assets'].update(assets);manifest['npc_portrait_source']={'url':'https://dbaion2.ru/data-en/npcs.json','sha256':hashlib.sha256(raw).hexdigest(),'retrieved_at':'2026-10-08','matched_npcs':len(portraits),'rule':'Only existing boss-category NPC IDs with exact case-insensitive English name agreement. Portraits do not alter NPC roles, zone, difficulty or game build.'}
manifest['missing']+=missing
manifest['npc_portraits']={k:r['icon'] for k,r in portraits.items()}
(static/'game-assets.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
(static/'game-assets.js').write_text('/* Unmodified game icons. Sources and exact NPC ID/name agreement: game-assets.json. */\nwindow.A2BundledAssets={base:new URL(".",document.currentScript.src).href,files:'+json.dumps(manifest['assets'],separators=(',',':'))+',npcs:'+json.dumps(manifest['npc_portraits'],separators=(',',':'))+'};\n',encoding='utf-8')
print('NPC references',len(portraits),'portraits',len(assets),'missing',len(missing))
