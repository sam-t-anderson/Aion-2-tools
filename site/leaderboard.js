// DPS leaderboard. Reads the server's /api/v1/leaderboard and links each entry to its log viewer.
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const CLASSES = ["Templar", "Gladiator", "Assassin", "Ranger", "Sorcerer", "Spiritmaster", "Cleric", "Chanter"];
  $("#cls").innerHTML = '<option value="">All classes</option>' + CLASSES.map((c) => `<option>${c}</option>`).join("");
  // WCL-style parse colours: the percentile of this parse among every character's best on the
  // same boss / category / game version / difficulty for the same class (100 = the best).
  const parseTier=p=>p>=100?'gold':p>=99?'pink':p>=95?'orange':p>=75?'purple':p>=50?'blue':p>=25?'green':'grey';
  const parseHTML=e=>{
    if(e.parse===null || e.parse===undefined)return '<span class="parse q-none" title="No parse: this metric is not ranked, or the encounter has no comparable public parses yet">·</span>';
    const few=(e.parse_characters||0)<5;
    return `<span class="parse q-${parseTier(e.parse)}${few?' provisional':''}" title="${e.parse} percentile among ${n0(e.parse_characters)} ${esc(cap(e.class||''))} character${e.parse_characters===1?'':'s'} on this encounter${few?' (provisional: fewer than 5 characters)':''}">${Math.round(e.parse)}</span>`;
  };
  const killTime=s=>(s===null || s===undefined || isNaN(s))?"—":`${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,"0")}`;
  // The date with the time of day, in the computer's clock: 2026-10-23 15:04:05.
  const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
  const day=t=>t?whenAt(t*1000):"—";

  async function load() {
    const cls = $("#cls").value, boss = $("#boss").value.trim();
    $("#list").innerHTML = '<div class="empty">Loading…</div>';
    try {
      const query = new URLSearchParams({limit:100,combat_mode:$("#mode").value,metric:$("#metric").value,sort:$("#sort").value});
      for(const [key,value] of Object.entries({class:cls.toLowerCase(),boss,encounter_type:$("#type").value,game_patch:$("#build").value.trim(),difficulty:$("#difficulty").value.trim(),party_size:$("#party-size").value}))if(value)query.set(key,value);
      const data = await window.A2.api("/api/v1/leaderboard?"+query);
      const entries = data.entries || [];
      const mx = Math.max(...entries.map((e) => e.score ?? e.dps ?? 0), 1);
      const rows = entries.map((e, i) => `<tr onclick="location.href='log.html?id=${esc(e.log)}'" style="cursor:pointer">
        <td class="r muted">${i+1}</td><td class="r">${parseHTML(e)}</td><td class="gold">${esc(e.name || "")}${e.verified?' <span class="verified" title="Verified: claimed by its player">✓</span>':''}</td><td>${esc(cap(e.class || ""))}</td>
        <td style="width:40%"><div class="bar"><i style="width:${100 * (e.score ?? e.dps ?? 0) / mx}%"></i><span>${n0(e.score??e.dps)}</span></div></td>
        <td>${esc(e.boss || "")} · ${esc(e.difficulty||"Unknown ruleset")} · ${esc(String(e.game_patch||"Unknown game version").replace(/version:product:([0-9.]+)/g,(_,v)=>"Product version "+v.split(".").slice(0,4).join(".")).replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,"Legacy build $1 · Steam"))} · party ${e.party_size||'unknown'} · instance ${e.instance_id||'unknown'}<br><small>${esc((e.comparison?.reasons||[]).join(' '))}</small></td><td class="r">${killTime(e.duration)}</td><td class="muted small">${esc(day(e.created_at))}</td><td class="r muted small">${e.comparison?.rank??'—'} / ${e.comparison?.count??'—'}<br>${e.comparison?.percentile!==null && e.comparison?.percentile!==undefined?e.comparison.percentile.toFixed(1)+' percentile':'Percentile unavailable'}</td></tr>`).join("");
      $("#list").innerHTML = rows
        ? `<table class="t"><tr><th class="r">#</th><th class="r">Parse</th><th>Player</th><th>Class</th><th>${esc($("#metric").value.toUpperCase())}</th><th>Encounter / ruleset / build</th><th class="r">Kill time</th><th>Date</th><th class="r">Matched cohort rank</th></tr>${rows}</table><p class="small muted">Parse: this parse's percentile among every character's best ${esc($("#metric").value.toUpperCase())} on the same encounter, category, game version and difficulty for the same class — 100 is the class best; comparable across encounters, so "Sort by parse" ranks a Sorcerer on one boss against a Templar on another. Dimmed parses have fewer than 5 characters to compare with. The matched cohort rank keeps the strict comparison (same party size and instance too).</p>`
        : '<div class="empty">No parses yet. Share public logs from the app to populate the leaderboard.</div>';
      $("#msg").textContent = `${entries.length} parses. ${data.note||""}`;
    } catch (e) { $("#list").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }
  $("#go").onclick = load;
  $("#cls").onchange = load;
  $("#boss").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  function modes(){const mode=$("#mode").value;$("#type").innerHTML='<option value="">All in mode</option>'+Object.entries(A2Community.types).filter(([key])=>(key.startsWith('pvp_')?'pvp':'pve')===mode).map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('');load();}
  $("#mode").onchange=modes;$("#metric").onchange=load;$("#type").onchange=load;$("#sort").onchange=load;modes();
})();
