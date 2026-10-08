/* Shared recorded character presentation; reference stats are never draft recalculations. */
(function(){
'use strict';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const profileImage=value=>{try{const u=new URL(value);return u.protocol==='https:' && !u.username && !u.password && ['assets.playnccdn.com','profileimg.plaync.com','metabot.gg','a2dil.com'].includes(u.hostname)?u.href:'';}catch(_){return '';}};
    const profileIcon=(value,label,reference)=>{const url=profileImage(value);return url?`<img${window.A2AssetHealth?.attributes(reference)||''} src="${esc(window.A2AssetHealth?A2AssetHealth.source(url):url)}" alt="${esc(label)}" referrerpolicy="no-referrer" loading="lazy" onerror="this.onerror=null;this.src='static/logo.png';this.title='Source image unavailable'">`:'<span class="cr-profile-empty" aria-label="Image unavailable">◇</span>';};
    const profileList=value=>Array.isArray(value)?value.filter(x=>x!==null&&x!==undefined).slice(0,1000):[];
    const statLabel=row=>({아이템레벨:'Gear score (item level)'}[String(row.name||'').replace(/\s/g,'')] || row.name || row.type || 'Unnamed stat');
    const secondaryStat=row=>typeof row==='string'?row.trim():row && typeof row==='object' && (row.name||row.type) && row.value!==undefined && row.value!==null && row.value!==''?`${statLabel(row)}: ${row.value}`:'';
    function details(data,region){
      if(!data||typeof data!=='object'||Array.isArray(data))return '<p>No character profile was supplied.</p>';
      const gear=profileList(data.equipment?.equipmentList),skills=profileList(data.skill?.skillList);
      const asset=(kind,entry)=>({namespace:"official",kind,id:entry.id,region});
      const profile=data.profile||{}, stats=profileList(data.stat?.statList), boards=profileList(data.daevanion?.boardList);
      const score=profile.gearScore ?? stats.find(row=>String(row.name||'').replace(/\s/g,'')==='아이템레벨' || /^(gear score|item level)$/i.test(String(row.name||'').trim()))?.value;
      const item=(entry,slot,kind="item")=>`<article class="cr-profile-card" data-grade="${esc(entry.grade||'')}">${profileIcon(entry.icon,entry.name||slot,asset(kind,entry))}<div><small>${esc(slot)}</small><strong>${esc(entry.name||entry.itemName||entry.id||'Unknown')}</strong><span>${entry.enchantLevel!==undefined?'+'+esc(entry.enchantLevel)+' · ':''}${esc(entry.grade||'')}${entry.level!==undefined?' · Lv '+esc(entry.level):''}</span></div></article>`;
      return `<div class="cr-profile-hero">${profileIcon(profile.profileImage,profile.characterName||'Character portrait')}<div><h2>${esc(profile.characterName||'Character')}</h2><p>Lv ${esc(profile.characterLevel??'Unavailable')} · ${esc(profile.className||'Unknown class')} · ${esc(profile.raceName||'')}<br>${esc(profile.serverName||profile.serverId||'Unknown server')} · ${esc(profile.regionName||data.region||'Unknown region')}<br>Gear score: ${esc(score??'Unavailable')}<br>Combat power: ${esc(profile.combatPower??'Unavailable')}</p></div></div>
        <h3>Character stats</h3><div class="cr-profile-stats">${stats.map(row=>`<div><strong>${esc(statLabel(row))}</strong><span>${esc(row.value??'Unavailable')}</span>${profileList(row.statSecondList).map(secondaryStat).filter(Boolean).map(text=>`<small>${esc(text)}</small>`).join('')}</div>`).join('')||'Stats were not included in this snapshot.'}</div>
        <h3>Equipment and inventory slots</h3><div class="cr-profile-grid">${gear.map(entry=>item(entry,entry.slotPosName||'Slot '+entry.slotPos)).join('')||'Equipment was not included in this snapshot.'}</div>
        <h3>Skills, passives and stigmas</h3><div class="cr-profile-grid">${skills.map(entry=>`<article class="cr-profile-card">${profileIcon(entry.icon,entry.name||'Skill',asset('skill',entry))}<div><small>${esc(entry.category||'Skill')}</small><strong>${esc(entry.name||entry.skillName||entry.id)}</strong><span>Lv ${esc(entry.skillLevel??entry.level??'Unavailable')} · ${entry.equip===1||entry.equip===true?'Equipped':entry.equip===0||entry.equip===false?'Not equipped':'Equip state unavailable'}</span></div></article>`).join('')||'Skills were not included in this snapshot.'}</div>
        <h3>Pet and wings</h3><div class="cr-profile-grid">${Object.entries(data.petwing||{}).filter(([,entry])=>entry&&typeof entry==='object'&&!Array.isArray(entry)).map(([slot,entry])=>item(entry,slot,['pet','wing'].includes(slot)?slot:null)).join('')||'Pet and wings were not included in this snapshot.'}</div><p class="small muted">Pet genus is shown only when recorded: ${esc(data.petwing?.pet?.genusName||data.petwing?.pet?.genus||'not included in the official profile snapshot')}.</p>
        <h3>Daevanion boards</h3><div class="cr-profile-grid">${boards.map(entry=>`<article class="cr-profile-card">${profileIcon(entry.icon,entry.name||'Board',asset('board',entry))}<div><strong>${esc(entry.name||entry.id)}</strong><span>${entry.open?'Open':'Locked'} · ${esc(entry.openNodeCount??'?')} / ${esc(entry.totalNodeCount??'?')} nodes</span></div></article>`).join('')||'Boards were not included in this snapshot.'}</div>`;
    }

window.A2CharacterView={details};
})();
