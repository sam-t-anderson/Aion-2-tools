/* Community schedule forecasts; observed defeats never establish spawn state. */
(function(){
  'use strict';
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dayNames=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const build=x=>String(x||'Unknown game version').replace(/version:product:([0-9.]+)/g,(_,v)=>'Product version '+v.split('.').slice(0,4).join('.')).replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,'Legacy build $1 · Steam').replace(/build:purple:A2_[A-Z0-9_]{1,80}_PURPLE:([0-9]{1,20})/g,'Legacy build $1 · PURPLE');
  const local=t=>new Date(t).toLocaleString();
  const countdown=ms=>{const s=Math.max(0,Math.ceil(ms/1000));return `${Math.floor(s/86400)?Math.floor(s/86400)+'d ':''}${String(Math.floor(s/3600)%24).padStart(2,'0')}:${String(Math.floor(s/60)%60).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;};
  function occurrences(event,zone,now,cache){
    const formatter=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
    const parts=t=>Object.fromEntries(formatter.formatToParts(new Date(t)).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]));
    const here=parts(now),result=[];
    for(let delta=-1;delta<=8;delta++){
      const day=new Date(Date.UTC(here.year,here.month-1,here.day+delta));
      if(event.days&&!event.days.includes(day.getUTCDay()))continue;
      const base=day.getTime(),key=zone+':'+base;
      if(!cache.has(key)){
        const offsets=new Set();
        for(const h of [-24,0,12,24,48]){
          const t=base+h*3600000,p=parts(t);
          offsets.add(Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute)-t);
        }
        cache.set(key,[...offsets]);
      }
      for(const hour of event.hours){
        const wall=base+(hour*60+event.minute)*60000;
        for(const offset of cache.get(key)){
          const t=wall-offset,p=parts(t);
          // Skip nonexistent DST wall times; retain both real repeated wall times.
          if(Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute)===wall)result.push(t);
        }
      }
    }
    return [...new Set(result)].sort((a,b)=>a-b);
  }
  function mount(root,io={}){
    let catalog=null,fieldCatalog=null,region='',group='',prepared=[],timer=null,disposed=false,serial=0,bossSerial=0,bossData=null,preparedDay='',killSerial=0,killData=null,killServer='';
    const dur=m=>m==null?'':m>=60?(m%60?Math.floor(m/60)+'h '+(m%60)+'m':Math.floor(m/60)+'h'):m+'m';
    try{const pref=JSON.parse(localStorage.getItem('a2-event-region')||'{}');region=pref.region||'';group=pref.group||'';killServer=String(pref.killServer||'');}catch(_){}
    const $=s=>root.querySelector(s);
    function save(){try{localStorage.setItem('a2-event-region',JSON.stringify({region,group,killServer}));}catch(_){}}
    function render(){
      if(disposed||!root.isConnected)return;
      bossSerial++;bossData=null;killSerial++;killData=null;
      root.innerHTML=`<section class="note"><h2>Regional event timers</h2><p>${esc(catalog.note)}</p><div class="row" style="gap:8px"><label>Game region <select data-region><option value="">Choose a region</option>${catalog.regions.map(r=>`<option value="${esc(r.id)}" ${r.id===region?'selected':''}>${esc(r.name)}</option>`).join('')}</select></label><label data-group-label ${region==='kr'?'':'hidden'}>Korean matching group <select data-group><option value="">Unknown — hide group-specific forecasts</option>${[1,2,3].map(n=>`<option value="${n}" ${group===String(n)?'selected':''}>Group ${n}</option>`).join('')}</select></label></div><p class="small muted">${esc(catalog.source_name)} · source updated ${esc(catalog.source_updated_at)} · checked ${esc(catalog.checked_at)} · review after ${esc(catalog.review_after)}. <a href="https://shugo.gg/timers" target="_blank" rel="noopener noreferrer">Schedule source ↗</a> · <a href="https://aion2codex.wiki/tools/rift-timer" target="_blank" rel="noopener noreferrer">Conflicting rift report ↗</a></p><p data-clock class="small muted"></p><div data-schedule></div></section><section class="note" data-field><h2>Field boss respawn reference</h2><p class="small muted">Loading community respawn reference…</p></section><section class="note"><h2>Field boss kills by server</h2><p class="small muted">Kills found in public combat logs, placed on the home server of the recorded characters who fought the boss. A kill appears when its log is uploaded, not when the boss dies. A visitor from another server reports its own server, so trust a kill more when several uploaders recorded it. The expected return uses a respawn length measured from repeated kills and is the latest it should be back.</p><div class="row" style="gap:8px"><label>Game server <select data-kill-server><option value="">Load kills to choose a server</option></select></label><button class="btn small" data-kill-refresh>Load / refresh kills</button></div><p data-kill-status role="status">Load to retrieve recent kills from the community server.</p><div data-kill-rows></div></section><section class="note"><h2>Recorded boss defeats</h2><p class="small muted">Submitted observations are separate from schedule forecasts. Region is recorded log metadata; it does not establish physical server or channel. Availability and respawn time remain unknown.</p><div class="row" style="gap:8px"><label>Recorded region <input data-boss-region placeholder="All regions" maxlength="32"></label><label>Search displayed bosses <input data-boss-search placeholder="Boss name or NPC ID"></label><button class="btn small" data-boss-refresh>Load / refresh observations</button></div><p data-boss-status role="status">Load to retrieve public observations from the community server.</p><div data-boss-rows></div><p><a href="${io.logsURL||'#/combat'}">Browse combat logs →</a></p></section>`;
      $('[data-region]').onchange=e=>{region=e.target.value;save();render();};
      $('[data-group]').onchange=e=>{group=e.target.value;save();prepare();};
      $('[data-boss-refresh]').onclick=loadBosses;
      $('[data-boss-search]').oninput=renderBosses;
      $('[data-kill-refresh]').onclick=loadKills;
      $('[data-kill-server]').onchange=e=>{killServer=e.target.value;save();renderKills();};
      prepare();renderFieldBosses();
    }
    function renderFieldBosses(){
      const host=$('[data-field]');
      if(!host||disposed||!root.isConnected||!fieldCatalog)return;
      const fc=fieldCatalog,groups=[['elyos','Verteron · Elyos'],['asmodian','Altgard · Asmodian'],['abyss','Abyss · Chaotic Lower Reshanta']];
      const rows=f=>fc.bosses.filter(b=>b.faction===f);
      const body=groups.filter(([f])=>rows(f).length).map(([f,label])=>`<details ${f==='abyss'?'open':''} style="margin:6px 0"><summary>${esc(label)} · ${rows(f).length} bosses</summary><ul class="boss-list">${rows(f).map(b=>`<li><strong>${esc(b.name)}</strong> · <span class="small muted">${esc(b.zone)} · Lv ${esc(b.level)}</span><br><span class="small">${b.respawn_minutes!=null?'Respawn ~'+esc(dur(b.respawn_minutes))+' after kill':esc(b.schedule||'Schedule unknown')}${b.checked_in_game?' · <span class="small muted">checked in game</span>':''}</span></li>`).join('')}</ul></details>`).join('');
      host.innerHTML=`<h2>Field boss respawn reference</h2><p class="small muted">${esc(fc.note)}</p>${body}<p class="small muted">${(fc.sources||[]).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)} ↗</a>`).join(' · ')}${fc.sources&&fc.sources.length?' · ':''}checked ${esc(fc.checked_at)} · review after ${esc(fc.review_after)}.</p>`;
    }
    function prepare(){
      const r=catalog.regions.find(r=>r.id===region),now=Date.now(),cache=new Map();
      preparedDay=new Date(now).toISOString().slice(0,10);
      if(!r){prepared=[];$('[data-schedule]').textContent='Select the region you play. Your device time zone is not used to guess the game region.';tick();return;}
      prepared=catalog.events.map(raw=>{
        const event={...raw,...(catalog.overrides[region]?.[raw.id]||{})};
        const unavailable=!!event.group_times&&!['1','2','3'].includes(group);
        if(event.group_times&&!unavailable){const [h,m]=event.group_times[Number(group)-1].split(':').map(Number);event.hours=[h];event.minute=m;}
        const zone=event.timezone||r.timezone;
        return {event,zone,unavailable,times:unavailable?[]:occurrences(event,zone,now,cache)};
      });
      $('[data-schedule]').innerHTML=`<div class="news-cards">${prepared.map(({event:e,zone,unavailable},i)=>`<article class="news-card"><h3>${esc(e.name)}</h3><p class="small muted">${e.days?e.days.map(d=>dayNames[d]).join(', '):'Daily'} · ${unavailable?'group time unavailable':e.hours.length===24?'hourly at :'+String(e.minute).padStart(2,'0'):e.hours.map(h=>String(h).padStart(2,'0')+':'+String(e.minute).padStart(2,'0')).join(', ')} · ${esc(zone)}${e.group_times?' · matching group '+esc(group||'unknown'):''}</p><p>${e.disputed?'Conflicting community reports — confirm the rift anchor in game.':'Community forecast — not live status.'}</p><p data-status="${i}"></p><strong data-countdown="${i}"></strong><p data-next="${i}"></p><p data-upcoming="${i}" class="small muted"></p>${unavailable?'<p>Select your Korean matching group to calculate this forecast.</p>':''}</article>`).join('')}</div>`;
      tick();
    }
    function tick(){
      if(disposed||!root.isConnected){dispose();return;}
      const now=Date.now();
      if(new Date(now).toISOString().slice(0,10)!==preparedDay){prepare();return;}
      $('[data-clock]').textContent=`Device time: ${local(now)} · local zone ${Intl.DateTimeFormat().resolvedOptions().timeZone}. ${new Date(catalog.review_after+'T00:00:00Z').getTime()<=now?'Schedule review is overdue; forecasts may be stale.':''}`;
      tickKills(now);
      prepared.forEach(({event:e,zone,unavailable,times},i)=>{
        if(unavailable)return;
        const active=times.filter(t=>t<=now&&now<t+e.duration_minutes*60000).at(-1);
        const next=times.find(t=>t>now);
        const entryEnd=active===undefined?null:active+(e.entry_minutes||0)*60000;
        const status=active!==undefined?(e.entry_minutes?(now<entryEnd?'Forecast: entry window':'Forecast: event window; entry closed'):'Forecast: scheduled window'):'Next scheduled start';
        const end=active!==undefined?(e.entry_minutes&&now<entryEnd?entryEnd:active+e.duration_minutes*60000):next;
        $(`[data-status="${i}"]`).textContent=status;
        $(`[data-countdown="${i}"]`).textContent=end===undefined?'No upcoming start in the calculated horizon':countdown(end-now);
        $(`[data-next="${i}"]`).textContent=next===undefined?'':`Next: ${local(next)} local · ${new Date(next).toLocaleString(undefined,{timeZone:zone})} (${zone})`;
        $(`[data-upcoming="${i}"]`).textContent='Upcoming local starts: '+times.filter(t=>t>now).slice(0,3).map(local).join(' · ');
      });
    }
    const sourceLink=(id,segment)=>/^[A-Za-z0-9]{6,16}$/.test(id||'')?`<a href="${esc(io.logURL?io.logURL(id,segment):'#/combat-log/shared/'+id+'?mode=pve')}">Source log${Number.isInteger(segment)?' · encounter '+(segment+1):''}</a>`:'Source unavailable';
    function renderBosses(){
      if(!bossData||disposed||!root.isConnected)return;
      const term=$('[data-boss-search]').value.trim().toLocaleLowerCase();
      const rows=(bossData.groups||[]).filter(x=>(x.boss+' '+x.npc_id).toLocaleLowerCase().includes(term)).slice(0,25);
      $('[data-boss-status]').textContent=`${rows.length} displayed groups (up to 25). Snapshot ${local(bossData.generated_at*1000)}. ${bossData.truncated?'Server results capped. ':''}Search filters the returned snapshot.`;
      $('[data-boss-rows]').innerHTML=rows.map(x=>`<details style="margin:4px 0"><summary>${esc(x.boss)} · ${esc(x.region||'Unknown region')} · ${x.last_defeat_at==null?'Time unavailable':esc(local(x.last_defeat_at*1000))}</summary><p>${Number(x.observed_defeats)||0} observations · ${esc(build(x.game_patch))} · NPC ${esc(x.npc_id)} · map ${esc(x.map_id||'unknown')} / instance ${esc(x.instance_id||'unknown')}. ${sourceLink(x.last_log_id,x.last_segment)}</p><p class="small muted">Availability / respawn: unknown. Physical server / channel: unknown. Different perspectives may repeat one defeat.</p>${x.recent_defeats?`<h4>Recent retained observations</h4><ul>${x.recent_defeats.map(h=>`<li>${h.defeated_at==null?'Time unavailable':esc(local(h.defeated_at*1000))} · ${Number(h.engaged_roster_members)||0} engaged · ${esc(h.evidence||'Evidence unavailable')}${h.timing_basis&&h.timing_basis!=='recorded_clock'?' · '+esc(h.timing_basis):''} · ${sourceLink(h.log_id,h.segment)}</li>`).join('')}</ul><p class="small muted">${Number(x.omitted_history)||0} earlier observations omitted.</p>`:'<p>Update the community server for recent observation history.</p>'}</details>`).join('')||'<p>No recorded defeats match this view.</p>';
      $('[data-boss-rows]').insertAdjacentHTML('beforeend',`<p class="small muted">${esc(bossData.note)}</p>`);
    }
    async function loadBosses(){
      const n=++bossSerial,q=new URLSearchParams(),r=$('[data-boss-region]').value.trim();
      if(r)q.set('region',r);
      $('[data-boss-refresh]').disabled=true;$('[data-boss-status]').textContent='Loading recorded defeats…';
      try{if(!io.api)throw Error('Community server is unavailable.');const data=await io.api('/api/v1/boss-status?'+q);if(n!==bossSerial||disposed||!root.isConnected)return;bossData=data;renderBosses();}
      catch(e){if(n===bossSerial&&!disposed&&root.isConnected){bossData=null;$('[data-boss-rows]').replaceChildren();$('[data-boss-status]').textContent='Could not load observations: '+e.message;}}
      finally{if(n===bossSerial&&!disposed&&root.isConnected)$('[data-boss-refresh]').disabled=false;}
    }
    const serverLabel=k=>(k.server_name||'Server '+k.server)+(k.region?' · '+String(k.region).toUpperCase():'');
    function tickKills(now){
      root.querySelectorAll('[data-kill-back]').forEach(el=>{
        const at=Number(el.dataset.killBack)*1000;
        el.textContent=at>now?'Expected back within '+countdown(at-now)+' ('+local(at)+')':'Expected back since '+local(at);
      });
    }
    function renderKills(){
      if(!killData||disposed||!root.isConnected)return;
      const kills=(killData.kills||[]).filter(k=>k&&k.server!=null&&Number.isFinite(k.killed_at)),servers=new Map();
      kills.forEach(k=>{if(!servers.has(String(k.server)))servers.set(String(k.server),serverLabel(k));});
      if(killServer&&!servers.has(killServer))servers.set(killServer,'Server '+killServer+' · no recent kills');
      $('[data-kill-server]').innerHTML='<option value="">Choose a server</option>'+[...servers].sort((a,b)=>a[1].localeCompare(b[1])).map(([id,name])=>`<option value="${esc(id)}" ${id===killServer?'selected':''}>${esc(name)}</option>`).join('');
      const rows=kills.filter(k=>String(k.server)===killServer);
      $('[data-kill-status]').textContent=killServer?`${rows.length} bosses with a recorded kill in the last ${Math.round(killData.window_seconds/3600)} hours. Snapshot ${local(killData.generated_at*1000)}.`:`${servers.size} servers have recorded kills. Choose yours.`;
      $('[data-kill-rows]').innerHTML=rows.map(k=>`<details style="margin:4px 0"><summary>${esc(k.boss)} · killed ${esc(local(k.killed_at*1000))} · ${Number(k.reports)===1?'1 uploader':esc(Number(k.reports))+' uploaders'}</summary><p>${Number.isFinite(k.respawn_at)?`<span data-kill-back="${esc(k.respawn_at)}"></span> · respawn about ${esc(countdown(k.respawn_seconds*1000))}, measured from ${esc(Number(k.respawn_samples))} gaps between kills`:'Respawn length not measured yet: it needs repeated kills of this boss in uploaded logs.'}</p><p class="small muted">${k.previous_killed_at==null?'':'Previous kill '+esc(local(k.previous_killed_at*1000))+' · '}${(k.logs||[]).slice(0,3).map(id=>sourceLink(id)).join(' · ')}</p></details>`).join('')+(killServer&&!rows.length?'<p class="small muted">No kills recorded for this server yet. They come from public Live Meter logs uploaded by players there.</p>':'');
      tickKills(Date.now());
    }
    async function loadKills(){
      const n=++killSerial;
      $('[data-kill-refresh]').disabled=true;$('[data-kill-status]').textContent='Loading recent kills…';
      try{if(!io.api)throw Error('Community server is unavailable.');const data=await io.api('/api/v1/boss-kills?window=172800');if(n!==killSerial||disposed||!root.isConnected)return;if(!data||!Array.isArray(data.kills))throw Error('The community server does not offer kills yet.');killData=data;renderKills();}
      catch(e){if(n===killSerial&&!disposed&&root.isConnected){killData=null;$('[data-kill-rows]').replaceChildren();$('[data-kill-status]').textContent='Could not load kills: '+e.message;}}
      finally{if(n===killSerial&&!disposed&&root.isConnected)$('[data-kill-refresh]').disabled=false;}
    }
    function dispose(){disposed=true;serial++;bossSerial++;killSerial++;if(timer)clearInterval(timer);}
    async function load(){
      const n=++serial;root.textContent='Loading event schedules…';
      try{const response=await fetch(io.catalogURL||'/static/event-schedules.json');if(!response.ok)throw Error('Schedule file unavailable');const data=await response.json();if(n!==serial||disposed||!root.isConnected)return;if(data.version!==1)throw Error('Unsupported schedule format');catalog=data;render();timer=setInterval(tick,1000);loadFieldBosses();}
      catch(e){if(n===serial&&!disposed&&root.isConnected)root.textContent='Could not load schedules: '+e.message;}
    }
    async function loadFieldBosses(){
      const n=serial;
      try{
        const url=io.fieldBossURL||(io.catalogURL?io.catalogURL.replace(/event-schedules\.json(\?.*)?$/,'field-bosses.json'):'/static/field-bosses.json');
        const r=await fetch(url);if(!r.ok)return;const d=await r.json();
        if(n!==serial||disposed||!root.isConnected||!d||d.version!==1||!Array.isArray(d.bosses))return;
        fieldCatalog=d;renderFieldBosses();
      }catch(_){/* the respawn reference is optional; leave the placeholder */}
    }
    load();return {dispose};
  }
  window.A2Timers={mount};
})();
