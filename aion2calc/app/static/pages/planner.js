/* Build Planner (#/planner): optimized builds for a class, and the welcome card. */
"use strict";

function welcomeCard() {
  let hidden = false;
  try { hidden = localStorage.getItem("welcome-hidden") === "1"; } catch (e) {}
  if (hidden) return "";
  return `<section class="win" id="welcome"><div class="wh"><h2>Welcome</h2><span class="sub">three steps to your best build</span>
      <div class="tools"><button class="btn small" id="whide">Hide</button></div></div><div class="wb">
    <div class="hero"><img src="/static/logo.png" alt=""><div><p class="herotitle">Aion 2 Calc</p><div class="muted">Plan your AION 2 build, check your gear and learn from your fights. Everything runs on this computer; the game database updates itself.</div>
      <div class="small" style="margin-top:6px">Questions or builds to share? <a href="${DISCORD}" target="_blank" rel="noopener">Join the Discord</a>.</div></div></div>
    <div class="welcome" style="margin-top:14px">
      <div class="wstep"><div class="n">I</div><h3>Import your character</h3><div class="small muted">Search your name on the official site: gear, rolls, skills, stigmas and Daevanion come in.</div>
        <a class="btn primary small" href="#/character" style="margin-top:8px;display:inline-block">My Character</a></div>
      <div class="wstep"><div class="n">II</div><h3>Get your advice</h3><div class="small muted">Best gear from your inventory, goal gear, arcana, titles, pantheon and genus insight, ranked by DPS gain.</div>
        <a class="btn primary small" href="#/gear" style="margin-top:8px;display:inline-block">Gear &amp; Advice</a></div>
      <div class="wstep"><div class="n">III</div><h3>Add your fights</h3><div class="small muted">Record them with the Live Meter, or import an AbyssLogs link under Combat Logs: see your rotation against the optimum, and the model learns from them.</div>
        <a class="btn primary small" href="#/meter" style="margin-top:8px;display:inline-block">Live Meter</a></div>
    </div></div></section>`;
}

async function pagePlanner() {
  const st = S.planner;
  app().innerHTML = welcomeCard() + `<section class="win"><div class="wh"><h2>Build planner</h2><a class="btn small" href="#/history">Saved results</a><span class="sub">optimized builds — copy each window into the game</span></div>
    <div class="wb"><div class="row"><label class="muted small" for="res">Build</label><select id="res"></select><button class="btn small" id="refresh-presets">Refresh presets</button>
      <span class="muted small">or optimize:</span><select id="cls" aria-label="Class to optimize"></select><select id="preset-mode" aria-label="Optimization mode"><option value="pve">PvE</option><option value="pvp">PvP damage (experimental)</option><option value="world">World PvP (experimental)</option></select>
      <input id="sp" type="number" min="0" max="10000" placeholder="Skill budget" aria-label="Skill point budget" title="Highest server-reported skill points, or enter explicitly" style="width:172px"><input id="stg" type="number" min="0" max="10000" placeholder="Stigma budget" aria-label="Stigma point budget" title="Highest server-reported stigma points, or enter explicitly" style="width:172px">
      <input id="dv" type="number" min="0" max="10000" placeholder="Daevanion budget" aria-label="Daevanion point budget" style="width:206px"><span id="planner-budget-source" class="small muted" role="status"></span><button class="btn primary" id="go">Optimize</button><span id="jobmsg" class="small muted"></span></div></div></section><div id="wins"></div>`;
  if ($("#whide")) $("#whide").onclick = () => { try { localStorage.setItem("welcome-hidden", "1"); } catch (e) {} $("#welcome").remove(); };
  const [results, classes] = await Promise.all([api("/api/planner/presets"), api("/api/classes")]);
  $("#res").innerHTML = results.map((r) => `<option value="${esc(r.path)}">${r.canonical ? "Community · " : "Example · "}${esc(r.preset_label || cap(r.class))} · ${r.scoring_policy?n0(r.score)+" weighted DPS":n0(r.dps?.[r.scenario])+" "+esc(r.scenario||"")+" DPS"}</option>`).join("");
  $("#cls").innerHTML = classes.map((c) => `<option>${esc(c)}</option>`).join("");
  if (results.some(r=>r.path===st.path)) $("#res").value = st.path;
  else if(st.choice){const match=results.find(r=>r.class===st.choice.class&&r.mode===st.choice.mode);if(match)$("#res").value=match.path;}
  $("#refresh-presets").onclick=async()=>{const b=$("#refresh-presets");b.disabled=true;try{const result=await runJob("/api/planner/presets/refresh",{},log=>$("#jobmsg").textContent=log.at(-1)||"Checking presets…");await pagePlanner();$("#jobmsg").textContent=result.checked?"Community presets checked.":"Showing saved presets or examples; server refresh unavailable.";}catch(e){$("#jobmsg").textContent=e.message;b.disabled=false;}};
  const load = async () => {
    st.path = $("#res").value;
    const selected=results.find(r=>r.path===st.path);if(selected)st.choice={class:selected.class,mode:selected.mode};
    if (!st.path) { $("#wins").innerHTML = '<div class="empty">No optimized builds yet — pick a class and press Optimize.</div>'; return; }
    $("#wins").innerHTML = '<div class="empty"><span class="spinner"></span> loading</div>';
    const v = await api("/api/build?path=" + encodeURIComponent(st.path));
    if (!$("#cls")) return;                       // the page was left while the build loaded
    $("#cls").value = v.class;
    $("#preset-mode").value = v.scenario==="pvp_world"?"world":String(v.scenario||"").startsWith("pvp")?"pvp":"pve";
    renderWindows(v, st, $("#wins"));
    if(v.weight_job){
      const path=st.path,jobId=v.weight_job,weightTarget=$('#wins');
      const pollWeights=async()=>{
        if(st.path!==path || (location.hash && !location.hash.startsWith('#/planner')) || !weightTarget.isConnected)return;
        try{
          const job=await api('/api/jobs/'+encodeURIComponent(jobId));
          if(st.path!==path || !weightTarget.isConnected)return;
          if(job.status==='done'){v.weights=job.result.slice(0,12);delete v.weight_job;renderWindows(v,st,$('#wins'));return;}
          const status=$('[data-weight-status]');if(status)status.textContent=job.status==='error'?'Stat priority failed: '+job.error:(job.log?.at(-1)||'Calculating stat priority…');
          if(job.status==='error')return;
        }catch(e){const status=$('[data-weight-status]');if(status)status.textContent='Stat priority refresh delayed: '+e.message;}
        setTimeout(pollWeights,1200);
      };pollWeights();
    }
    loadPointBudgets();
  };
  let pointRequest=0;
  const loadPointBudgets=async()=>{
    const request=++pointRequest,cls=$("#cls").value,fields={skill:$("#sp"),stigma:$("#stg"),daevanion:$("#dv")};
    Object.values(fields).forEach(e=>e.value='');
    $("#planner-budget-source").textContent='Loading server-reported budgets…';
    try{const result=await A2ProgressionBudgets.read(communityAPI,cls);if(request!==pointRequest||!$("#planner-budget-source"))return;for(const [key,e] of Object.entries(fields))if(e.isConnected&&e.value===''&&result.points[key]!==null)e.value=result.points[key];$("#planner-budget-source").textContent=result.note;}
    catch(e){if(request===pointRequest&&$("#planner-budget-source"))$("#planner-budget-source").textContent='Server budgets unavailable. Enter your available points explicitly.';}
  };
  $("#cls").onchange=loadPointBudgets;
  loadPointBudgets();
  $("#res").onchange = load;
  $("#go").onclick = async () => {
    if(["#sp","#stg","#dv"].some(id=>$(id).value===""||!Number.isInteger(+$(id).value)||+$(id).value<0||+$(id).value>10000)){$("#jobmsg").textContent="Enter all three available point budgets (0–10000).";return;}
    $("#go").disabled = true;
    try {
      const v = await runJob("/api/optimize", { class: $("#cls").value, mode:$("#preset-mode").value, skill_points: +$("#sp").value, stigma_points: +$("#stg").value, daevanion: +$("#dv").value },
        (log) => ($("#jobmsg").textContent = log[log.length - 1] || "working…"));
      renderWindows(v, st, $("#wins"));
      $("#jobmsg").textContent = v.preset_submission?.reason || "done";
    } catch (e) { $("#jobmsg").textContent = e.message; }
    $("#go").disabled = false;
  };
  load().catch((e) => { if ($("#wins")) $("#wins").innerHTML = `<div class="note">${esc(e.message)}</div>`; });
}
