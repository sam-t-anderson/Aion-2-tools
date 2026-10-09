// DPS leaderboard. Reads the server's /api/v1/leaderboard and links each entry to its log viewer.
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const CLASSES = ["Templar", "Gladiator", "Assassin", "Ranger", "Sorcerer", "Spiritmaster", "Cleric", "Chanter"];
  $("#cls").innerHTML = '<option value="">All classes</option>' + CLASSES.map((c) => `<option>${c}</option>`).join("");

  async function load() {
    const cls = $("#cls").value, boss = $("#boss").value.trim();
    $("#list").innerHTML = '<div class="empty">Loading…</div>';
    try {
      const query = new URLSearchParams({limit:100,combat_mode:$("#mode").value,metric:$("#metric").value});
      for(const [key,value] of Object.entries({class:cls.toLowerCase(),boss,encounter_type:$("#type").value,game_patch:$("#build").value.trim(),difficulty:$("#difficulty").value.trim(),party_size:$("#party-size").value}))if(value)query.set(key,value);
      const data = await window.A2.api("/api/v1/leaderboard?"+query);
      const entries = data.entries || [];
      const mx = Math.max(...entries.map((e) => e.score ?? e.dps ?? 0), 1);
      const rows = entries.map((e) => `<tr onclick="location.href='log.html?id=${esc(e.log)}'" style="cursor:pointer">
        <td class="r muted">${e.comparison?.rank??'—'} / ${e.comparison?.count??'—'}<br>${e.comparison?.percentile!==null && e.comparison?.percentile!==undefined?e.comparison.percentile.toFixed(1)+' percentile':'Percentile unavailable'}</td><td class="gold">${esc(e.name || "")}</td><td>${esc(cap(e.class || ""))}</td>
        <td style="width:40%"><div class="bar"><i style="width:${100 * (e.score ?? e.dps ?? 0) / mx}%"></i><span>${n0(e.score??e.dps)}</span></div></td>
        <td>${esc(e.boss || "")} · ${esc(e.difficulty||"Unknown ruleset")} · ${esc(String(e.game_patch||"Unknown game version").replace(/version:product:([0-9.]+)/g,"Product version $1").replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,"Legacy build $1 · Steam"))} · party ${e.party_size||'unknown'} · instance ${e.instance_id||'unknown'}<br><small>${esc((e.comparison?.reasons||[]).join(' '))}</small></td></tr>`).join("");
      $("#list").innerHTML = rows
        ? `<table class="t"><tr><th class="r">Matched cohort rank</th><th>Player</th><th>Class</th><th>${esc($("#metric").value.toUpperCase())}</th><th>Encounter / ruleset / build</th></tr>${rows}</table>`
        : '<div class="empty">No parses yet. Share public logs from the app to populate the leaderboard.</div>';
      $("#msg").textContent = `${entries.length} parses. ${data.note||""}`;
    } catch (e) { $("#list").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }
  $("#go").onclick = load;
  $("#cls").onchange = load;
  $("#boss").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  function modes(){const mode=$("#mode").value;$("#type").innerHTML='<option value="">All in mode</option>'+Object.entries(A2Community.types).filter(([key])=>(key.startsWith('pvp_')?'pvp':'pve')===mode).map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('');load();}
  $("#mode").onchange=modes;$("#metric").onchange=load;$("#type").onchange=load;modes();
})();
