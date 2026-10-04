/* aion2calc front end — vanilla JS, no build step. */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
const icon = (u) => (u ? "/api/icon?u=" + encodeURIComponent(u.startsWith("/") ? "https://metabot.gg" + u : u) : "");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
const app = () => $("#app");

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
async function runJob(path, body, onLog) {
  const { job } = await api(path, body);
  for (;;) {
    await new Promise((r) => setTimeout(r, 1200));
    const j = await api("/api/jobs/" + job);
    onLog && onLog(j.log || []);
    if (j.status === "done") return j.result;
    if (j.status === "error") throw new Error(j.error);
  }
}
function copyText(t) {
  navigator.clipboard?.writeText(t).then(() => toast("Copied to clipboard"), () => toast("Copy failed"));
}
function toast(msg) {
  const d = document.createElement("div");
  d.textContent = msg;
  Object.assign(d.style, { position: "fixed", bottom: "20px", left: "50%", transform: "translateX(-50%)", background: "#1c2438",
    border: "1px solid rgba(233,203,128,.6)", padding: "8px 16px", borderRadius: "6px", zIndex: 99, color: "#e8cf8e" });
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 1800);
}
const statGrid = (rows, title = "Stats from this system") =>
  rows && rows.length
    ? `<div class="statsum"><h4>${esc(title)}</h4><div class="statgrid">${rows
        .map((r) => `<div><span>${esc(r.label)}</span><span>${esc(r.text)}</span></div>`).join("")}</div></div>`
    : "";
const kv = (pairs) => `<div class="statgrid">${pairs.map(([k, v]) => `<div><span>${esc(k)}</span><span>${v}</span></div>`).join("")}</div>`;

// "my screenshot" — users can pin their own in-game screenshot next to a window
function shotTools(key) {
  return `<button class="btn small" data-shot="${key}" title="Put your in-game screenshot of this window next to it">My screenshot</button>`;
}
function shotBlock(key) {
  let src = null;
  try { src = localStorage.getItem("shot:" + key); } catch (e) {}
  return src ? `<div class="shot"><div class="row small muted">Your in-game screenshot <button class="btn small" data-shot-del="${key}">remove</button></div><img src="${src}" alt="screenshot"></div>` : "";
}
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-shot]");
  if (b) {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = "image/*";
    inp.onchange = () => {
      const f = inp.files[0]; if (!f) return;
      const rd = new FileReader();
      rd.onload = () => { try { localStorage.setItem("shot:" + b.dataset.shot, rd.result); } catch (e) { toast("Image too large to keep"); } route(); };
      rd.readAsDataURL(f);
    };
    inp.click();
  }
  const d = ev.target.closest("[data-shot-del]");
  if (d) { try { localStorage.removeItem("shot:" + d.dataset.shotDel); } catch (e) {} route(); }
  const c = ev.target.closest("[data-copy]");
  if (c && window.__copy && window.__copy[c.dataset.copy]) copyText(window.__copy[c.dataset.copy]);
});
window.__copy = {};

function win(title, sub, body, { key, tools = "", copy } = {}) {
  if (copy && key) window.__copy[key] = copy;
  return `<section class="win"><div class="wh"><h2>${esc(title)}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}
    <div class="tools">${copy ? `<button class="btn small" data-copy="${key}">Copy as text</button>` : ""}${key ? shotTools(key) : ""}${tools}</div></div>
    <div class="wb">${body}${key ? shotBlock(key) : ""}</div></section>`;
}

// ------------------------------------------------------- window renderers
function winSkills(v, tab = "active") {
  const list = v.skills[tab] || [];
  const bud = v.budgets || {};
  const counter = `<span class="counter"><small>Skill points</small> ${n0(v.points?.skill)} / ${n0(bud.skill)}</span>`;
  const rows = list.map((s) => {
    const chosen = s.specs.filter((x) => x.chosen);
    return `<div class="skill ${s.eff <= 1 ? "dim" : ""}">
      <div class="icon"><img src="${icon(s.icon)}" alt="" loading="lazy"><span class="lv">Lv${s.eff}</span></div>
      <div><div class="nm">${esc(s.name)}</div>
        <div class="lvl"><b>Lv ${s.eff}</b> = SP ${s.sp} + Daevanion ${s.daev}${s.gear ? ` + gear ${s.gear}` : ""}</div></div>
      <div class="specs">${s.specs.map((x) => `<div class="spec ${x.chosen ? "on" : x.available ? "av" : ""}" title="${esc(`${x.n}. ${x.text} (unlocks at Lv ${x.unlock})`)}">${x.n}</div>`).join("")}</div>
      ${chosen.length ? `<div class="spectext">${chosen.map((x) => `<span>${x.n}</span> ${esc(x.text)}`).join(" &nbsp;·&nbsp; ")}</div>` : ""}
    </div>`;
  }).join("");
  const copy = (v.skills.active.concat(v.skills.passive)).filter((s) => s.sp > 1 || s.specs.some((x) => x.chosen))
    .map((s) => `${s.name}: train to ${s.sp} (Lv ${s.eff})${s.specs.some((x) => x.chosen) ? " — specs " + s.specs.filter((x) => x.chosen).map((x) => x.n).join(", ") : ""}`).join("\n");
  const tabs = `<div class="tabs">${["active", "passive"].map((t) => `<button data-skilltab="${t}" class="${t === tab ? "on" : ""}">${cap(t)}</button>`).join("")}</div>`;
  const rolls = (v.gear_skill_rolls || []).map((r) => `${r.name} +${r.levels}`).join(", ");
  return win("Skills", counter, tabs + `<div class="skilllist">${rows}</div>` +
    statGrid([{ label: "Skill points spent", text: `${n0(v.points?.skill)} / ${n0(bud.skill)}` },
              ...(rolls ? [{ label: "Skill levels from gear", text: rolls }] : [])], "From this system"),
    { key: "skills", copy });
}

function winStigmas(v) {
  const bud = v.budgets || {};
  const cards = v.stigmas.map((s) => `<div class="stigma">
      <div class="icon"><img src="${icon(s.icon)}" alt="" loading="lazy"><span class="lv">Lv${s.level}</span></div>
      <div class="nm gold"><b>${esc(s.name)}</b></div><div class="small muted">Level ${s.level}</div>
      <ul>${s.specs.map((x) => `<li class="${x.active ? "on" : ""}"><b>${x.n}</b>${esc(x.text)} <span class="faint">(Lv ${x.unlock})</span></li>`).join("")}</ul>
    </div>`).join("");
  const copy = v.stigmas.map((s) => `${s.name}: Lv ${s.level}`).join("\n");
  return win("Stigma", `<span class="counter"><small>Stigma points</small> ${n0(v.points?.stigma)} / ${n0(bud.stigma)}</span>`,
    `<div class="stigmas">${cards || '<div class="empty">No stigmas</div>'}</div>` +
    statGrid(v.stigmas.map((s) => ({ label: s.name, text: `Lv ${s.level} · ${s.specs.filter((x) => x.active).length} effects` }))),
    { key: "stigma", copy });
}

function winDaevanion(v, boardIdx = 0) {
  const d = v.daevanion;
  const b = d.boards[boardIdx] || d.boards[0];
  if (!b) return win("Daevanion", "", '<div class="empty">No board data</div>');
  const cells = b.nodes.map((nd) => {
    const cls = nd.type === "Start" ? "start" : nd.type === "SkillLevel" ? "skill" : nd.type === "None" ? "none" : "";
    const tip = nd.type === "SkillLevel" ? `${nd.skill} +1 (${nd.grade}, ${nd.cost} pt)` : nd.type === "Start" ? "Start" : `${nd.label} (${nd.grade}, ${nd.cost} pt)`;
    const txt = nd.type === "SkillLevel" ? (nd.skill || "").split(/\s+/).map((w) => w[0]).join("").slice(0, 3) : nd.type === "Start" ? "" : esc(nd.short || "");
    return `<div class="node ${cls} ${nd.selected || nd.type === "Start" ? "sel" : ""}" data-grade="${esc(nd.grade)}"
      style="grid-row:${nd.row};grid-column:${nd.col}" title="${esc(tip)}">${txt}</div>`;
  }).join("");
  const tabs = `<div class="tabs">${d.boards.map((x, i) => `<button data-board="${i}" class="${i === boardIdx ? "on" : ""}">${esc(x.name)} <span class="faint">${x.used}/${x.total}</span></button>`).join("")}</div>`;
  const side = `<div class="daevside">
      <div class="counter"><small>Points used</small> ${d.used} / ${d.budget ?? 360}</div>
      <h4>${esc(b.name)} board</h4><div class="small">${b.used} / ${b.total} points · ${b.nodes.filter((x) => x.selected).length} nodes</div>
      <h4>Skill levels</h4>${d.skills.map((s) => `<div class="small">${esc(s.name)} <b class="gold">+${s.levels}</b></div>`).join("") || '<div class="faint small">none</div>'}
      <h4>Stats (all boards)</h4>${d.stats.map((s) => `<div class="small">${esc(s.label)} <b>${esc(s.text)}</b></div>`).join("")}
    </div>`;
  const legend = `<div class="legend"><span><i style="background:#c9ccd3"></i>Common 1 pt</span><span><i style="background:#4aa3e6"></i>Rare 2 pt</span>
    <span><i style="background:#a46cf0"></i>Epic 3 pt</span><span><i style="background:#f0bf4a"></i>Unique 4 pt</span>
    <span>squares = stats · circles = +1 skill level · bright = take it</span></div>`;
  const copy = d.boards.map((x) => `${x.name}: ${x.used}/${x.total} pts`).join("\n") + (v.links?.metabot_daevanion ? `\nPlanner link: ${v.links.metabot_daevanion}` : "");
  const tools = v.links?.metabot_daevanion ? `<a class="btn small" target="_blank" href="${esc(v.links.metabot_daevanion)}">Open in metabot planner</a>` : "";
  return win("Daevanion", "", tabs + `<div class="daev">${side}<div><div class="board-wrap"><div class="board"
      style="grid-template-columns:repeat(${b.cols},34px);grid-template-rows:repeat(${b.rows},34px)">${cells}</div></div>${legend}</div></div>` +
    statGrid(d.stats), { key: "daevanion-" + b.name, copy, tools });
}

const LEFT_SLOTS = ["MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt",
  "Main hand", "Off-hand", "Armor x7"];
function slotTile(s) {
  const extras = [];
  (s.rolls || []).forEach(([k, val]) => extras.push(`<span class="chip">${esc(k)} ${esc(val)}</span>`));
  (s.manastones || []).forEach(([k, val]) => extras.push(`<span class="chip gold" title="Manastone">${esc(k)} ${esc(val)}</span>`));
  (s.theostones || []).forEach((t) => extras.push(`<span class="chip gold">${esc(t)}</span>`));
  (s.skills || []).forEach(([k, lv]) => extras.push(`<span class="chip" style="color:#e8cf8e">${esc(k)} +${lv}</span>`));
  const st = (s.stats || []).slice(0, 4).map((x) => `<b>${esc(x.text)}</b> ${esc(x.label)}`).join(" · ");
  return `<div class="slot" data-grade="${esc(s.grade || "")}">
      <div class="icon sm">${s.icon ? `<img src="${icon(s.icon)}" alt="">` : ""}${s.enchant ? `<span class="lv">+${s.enchant}</span>` : ""}</div>
      <div><div class="sl">${esc(s.slot)}</div><div class="gname">${esc(s.item || s.name || "")}</div>
        <div class="st">${st}</div>${extras.length ? `<div>${extras.join("")}</div>` : ""}${s.source ? `<div class="faint small">${esc(s.source)}</div>` : ""}</div>
    </div>`;
}
function winEquipment(v) {
  const e = v.equipment;
  const left = e.slots.filter((s) => LEFT_SLOTS.includes(s.slot));
  const right = e.slots.filter((s) => !LEFT_SLOTS.includes(s.slot));
  const doll = `<div class="doll"><div><div class="cls">${esc(cap(v.class))}</div><div class="small">${esc(v.name ? `${v.name} · ${v.server}` : v.loadout_name || "")}</div>
      ${v.combat_power ? `<div class="gold">Combat Power ${n0(v.combat_power)}</div>` : ""}</div></div>`;
  let rolls = "";
  if (e.rolls && Object.keys(e.rolls).length) {
    rolls = `<div class="grid2" style="margin-top:12px"><div><h4 class="gold small">KEEP / REROLL TOWARD (best first)</h4>${Object.entries(e.rolls).slice(0, 8).map(([slug, rs]) =>
      `<div class="small"><b>${esc(slug.replace(/-/g, " "))}</b>: ${rs.map((r) => esc(r.stat)).join(" › ")}</div>`).join("")}</div>
      <div><h4 class="gold small">ENCHANT PRIORITY</h4>${(e.enchant || []).map((r) => `<div class="small">${esc(r.slot)} <b>${r.dps.toFixed(1)}</b> DPS / level</div>`).join("")}</div></div>`;
  }
  const copy = e.slots.map((s) => `${s.slot}: ${s.item || s.name}`).join("\n");
  return win("Equipment", v.name ? "current gear (official profile)" : "loadout used for this build",
    `<div class="paperdoll"><div class="slots">${left.map(slotTile).join("")}</div>${doll}<div class="slots">${right.map(slotTile).join("")}</div></div>` +
    rolls + statGrid(e.total, "Stats from equipment, rolls and manastones"), { key: "equipment", copy });
}

function winArcana(v) {
  const ex = v.extras || {};
  let body = "";
  if (v.arcana_items && v.arcana_items.length) {
    body += `<div class="cards">${v.arcana_items.map((a) => `<div class="card" data-grade="${esc(a.grade)}">
      <div class="icon" style="margin:0 auto 6px">${a.icon ? `<img src="${icon(a.icon)}">` : ""}<span class="lv">+${a.enchant || 0}</span></div>
      <div class="gname">${esc(a.name)}</div>${(a.skills || []).map(([k, lv]) => `<span class="chip">${esc(k)} +${lv}</span>`).join("")}
      <div class="small muted">${(a.stats || []).map((s) => esc(s.label + " " + s.text)).join(", ")}</div></div>`).join("")}</div>`;
  }
  if (ex.arcana && ex.arcana.length) {
    body += `<h4 class="gold small" style="margin-top:12px">RECOMMENDED VARIANT PER SLOT</h4><div class="cards">${ex.arcana.map((a) => `<div class="card">
      <div class="t">${esc(a.slot)}</div><div class="pick">${a.tie ? "Either variant" : esc(a.pick)}</div>
      <div class="alt">${Object.entries(a.variants).map(([k, s]) => `${esc(k)}: ${esc(s)}`).join("<br>")}</div></div>`).join("")}</div>`;
  }
  const rolls = ex.arcana_rolls || {};
  if (Object.keys(rolls).length) {
    const rows = Object.entries(rolls).sort((a, b) => b[1].expected_unique_5 - a[1].expected_unique_5);
    body += `<h4 class="gold small" style="margin-top:14px">SKILL ROLLS — value of each arcana slot (Unique: 4 rolls at +0, 9 at +5)</h4>
      <table class="t"><tr><th>Slot</th><th class="r">Unique +0</th><th class="r">Unique +5</th><th>Best rolls (+1 / +2)</th></tr>
      ${rows.map(([slot, a]) => `<tr><td class="gold">${esc(cap(slot))}</td><td class="r">+${a.expected_unique_0.toFixed(1)}%</td><td class="r">+${a.expected_unique_5.toFixed(1)}%</td>
        <td class="small">${Object.entries(a.skills).sort((x, y) => y[1][1] - x[1][1]).slice(0, 4).map(([k, g]) => `${esc(k)} ${g[0] >= 0 ? "+" : ""}${g[0].toFixed(1)}% / ${g[1] >= 0 ? "+" : ""}${g[1].toFixed(1)}%`).join(" · ")}</td></tr>`).join("")}</table>`;
  }
  const deity = ex.deity || [];
  return win("Arcana", "Chalice, Parchment, Compass roll active skills · Bell, Mirror roll passives", body || '<div class="empty">No arcana data</div>',
    { key: "arcana", copy: (ex.arcana || []).map((a) => `${a.slot}: ${a.tie ? "either" : a.pick}`).join("\n") }) +
    (deity.length ? win("Deity & primary stats", "", statGrid(deity, "Totals")) : "");
}

function winTitles(v) {
  const ex = v.extras || {};
  const cur = (ex.titles || []).map((t) => `<div class="slot"><div class="icon sm"></div><div><div class="sl">${esc(t.slot)}</div>
     <div class="gname">${esc(t.item)}</div><div class="st">${t.stats.map((s) => `<b>${esc(s.text)}</b> ${esc(s.label)}`).join(" · ")}</div></div></div>`).join("");
  const rank = (ex.title_ranking || []).map((t) => `<tr><td class="gname" data-grade="${esc(t.grade)}">${esc(t.name)}</td><td class="small">${esc(t.equip)}</td><td class="small muted">${esc(t.owned)}</td></tr>`).join("");
  const wings = (ex.wings || []).map((w) => `<div class="slot" data-grade="Unique"><div class="icon sm">${ex.wing?.icon ? `<img src="${icon(ex.wing.icon)}">` : ""}</div>
     <div><div class="sl">Wings</div><div class="gname">${esc(w.item)}</div><div class="st">${w.stats.map((s) => `<b>${esc(s.text)}</b> ${esc(s.label)}`).join(" · ")}</div></div></div>`).join("");
  const pet = ex.pet ? `<div class="slot"><div class="icon sm">${ex.pet.icon ? `<img src="${icon(ex.pet.icon)}">` : ""}</div><div><div class="sl">Pet</div>
     <div class="gname">${esc(ex.pet.name)} <span class="muted">Lv ${esc(ex.pet.level)}</span></div><div class="st">Pet bonuses are mostly against one monster genus.</div></div></div>` : "";
  return win("Titles, wings & pet", "", `<div class="grid2"><div class="slots">${cur}${wings}${pet}</div>
      <div><h4 class="gold small">BEST TITLES FOR THIS BUILD</h4><table class="t"><tr><th>Title</th><th>Equip bonus</th><th>Owned bonus</th></tr>${rank}</table></div></div>` +
    statGrid(ex.titles_total, "Stats from equipped titles"), { key: "titles" });
}

function winMacro(v) {
  const m = v.macro;
  if (!m) return win("Skill Macro", "", '<div class="empty">No macro (run an optimization)</div>');
  const step = (s, i) => `<div class="r"><b class="gold">${i + 1}</b> ${esc(s)}</div>`;
  const body = `<p class="muted small">Settings → Key Settings → General → Skill Macro. Skill Queue <b>ON</b>, 10 ms delay on every step, hold the key.</p>
    <div class="rot">${m.steps.map(step).join("")}</div>
    <p>${m.manual && m.manual.length ? `Manual keys: <b>${m.manual.map(esc).join(", ")}</b>` : "No manual keys — hold the macro key for the whole fight."}</p>
    <p class="small muted">Simulated: ${pct(m.dps_macro / m.dps_priority)} of the ideal priority list.${m.alt_steps ? ` Alternative layout: ${pct(m.dps_alt / m.dps_priority)}.` : ""}</p>
    <h4 class="gold small">PRIORITY LIST</h4><ol>${(v.policy || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ol>`;
  return win("Skill Macro & rotation", "", body, { key: "macro", copy: m.steps.map((s, i) => `${i + 1}. ${s}`).join("\n") + (m.manual?.length ? `\nManual: ${m.manual.join(", ")}` : "") });
}

function winOverview(v) {
  const dps = v.dps || {};
  const st = v.stats || {};
  const kpis = `<div class="kpis">${Object.entries(dps).map(([k, x]) => `<div class="kpi"><div class="k">${esc(k)} DPS</div><div class="v">${n0(x)}</div></div>`).join("")}
    ${v.baseline ? `<div class="kpi"><div class="k">Typical top build</div><div class="v">${n0(v.baseline.community_optimized_rotation)}</div></div>` : ""}
    <div class="kpi"><div class="k">Crit chance</div><div class="v">${pct(st.crit_chance_vs_target)}</div></div>
    <div class="kpi"><div class="k">Cooldown red.</div><div class="v">${pct(st.cdr)}</div></div>
    <div class="kpi"><div class="k">Combat speed</div><div class="v">${pct(st.combat_speed)}</div></div></div>`;
  const w = (v.weights || []).map((x) => `<tr><td>${esc(x.label)}</td><td class="r num">${x.pct >= 0 ? "+" : ""}${x.pct.toFixed(2)}%</td><td style="width:45%"><div class="bar"><i style="width:${Math.max(0, Math.min(100, x.pct * 25))}%"></i></div></td></tr>`).join("");
  const sh = Object.entries(v.shares || {}).slice(0, 12).map(([k, x]) => `<tr><td>${esc(k)}</td><td style="width:55%"><div class="bar"><i style="width:${100 * x / Math.max(...Object.values(v.shares))}%"></i><span>${pct(x)}</span></div></td></tr>`).join("");
  return win("Overview", esc(v.loadout_name || ""), kpis + `<div class="grid2" style="margin-top:14px"><div><h4 class="gold small">STAT PRIORITY (DPS PER UPGRADE)</h4><table class="t">${w}</table></div>
     <div><h4 class="gold small">DAMAGE SHARE</h4><table class="t">${sh}</table></div></div>`, { key: "overview" });
}

const WINDOWS = [
  ["overview", "Overview", "◆"], ["skills", "Skills", "✦"], ["stigma", "Stigma", "⬢"], ["daevanion", "Daevanion", "✧"],
  ["equipment", "Equipment", "⚔"], ["arcana", "Arcana", "❖"], ["titles", "Titles & wings", "♛"], ["macro", "Macro & rotation", "⌨"],
];
function renderWindows(v, state, host) {
  const side = `<section class="win sidemenu"><div class="wb">${WINDOWS.map(([k, t, ic]) => `<a href="javascript:void 0" data-win="${k}" class="${state.win === k ? "on" : ""}"><span class="ic">${ic}</span>${t}</a>`).join("")}</div></section>`;
  let body = "";
  switch (state.win) {
    case "skills": body = winSkills(v, state.skilltab || "active"); break;
    case "stigma": body = winStigmas(v); break;
    case "daevanion": body = winDaevanion(v, state.board || 0); break;
    case "equipment": body = winEquipment(v); break;
    case "arcana": body = winArcana(v); break;
    case "titles": body = winTitles(v); break;
    case "macro": body = winMacro(v); break;
    default: body = winOverview(v);
  }
  host.innerHTML = `<div class="layout"><div>${side}</div><div>${body}</div></div>`;
  $$("[data-win]", host).forEach((a) => (a.onclick = () => { state.win = a.dataset.win; renderWindows(v, state, host); }));
  $$("[data-skilltab]", host).forEach((b) => (b.onclick = () => { state.skilltab = b.dataset.skilltab; renderWindows(v, state, host); }));
  $$("[data-board]", host).forEach((b) => (b.onclick = () => { state.board = +b.dataset.board; renderWindows(v, state, host); }));
}

// ------------------------------------------------------------------ pages
const S = { planner: { win: "overview" }, character: { win: "overview" }, combat: {}, database: {} };

async function pagePlanner() {
  const st = S.planner;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Build planner</h2><span class="sub">optimized builds — copy each window into the game</span></div>
    <div class="wb"><div class="row"><label class="muted small">Build</label><select id="res"></select>
      <span class="muted small">or optimize:</span><select id="cls"></select>
      <input id="sp" type="number" placeholder="skill pts (203)" style="width:130px"><input id="stg" type="number" placeholder="stigma pts (30)" style="width:130px">
      <button class="btn primary" id="go">Optimize</button><span id="jobmsg" class="small muted"></span></div></div></section><div id="wins"></div>`;
  const [results, classes] = await Promise.all([api("/api/results"), api("/api/classes")]);
  $("#res").innerHTML = results.map((r) => `<option value="${esc(r.path)}">${esc(cap(r.class))} · ${esc(r.loadout || "")} · ${n0(r.dps?.[r.scenario])} ${esc(r.scenario || "")} DPS</option>`).join("");
  $("#cls").innerHTML = classes.map((c) => `<option>${esc(c)}</option>`).join("");
  if (st.path) $("#res").value = st.path;
  const load = async () => {
    st.path = $("#res").value;
    if (!st.path) { $("#wins").innerHTML = '<div class="empty">No optimized builds yet — pick a class and press Optimize.</div>'; return; }
    $("#wins").innerHTML = '<div class="empty"><span class="spinner"></span> loading</div>';
    const v = await api("/api/build?path=" + encodeURIComponent(st.path));
    $("#cls").value = v.class;
    renderWindows(v, st, $("#wins"));
  };
  $("#res").onchange = load;
  $("#go").onclick = async () => {
    $("#go").disabled = true;
    try {
      const v = await runJob("/api/optimize", { class: $("#cls").value, skill_points: +$("#sp").value || null, stigma_points: +$("#stg").value || null },
        (log) => ($("#jobmsg").textContent = log[log.length - 1] || "working…"));
      renderWindows(v, st, $("#wins"));
      $("#jobmsg").textContent = "done";
    } catch (e) { $("#jobmsg").textContent = e.message; }
    $("#go").disabled = false;
  };
  load().catch((e) => ($("#wins").innerHTML = `<div class="note">${esc(e.message)}</div>`));
}

async function pageCharacter() {
  const st = S.character;
  app().innerHTML = `<section class="win"><div class="wh"><h2>My character</h2><span class="sub">import from the official AION 2 character page, then optimize it with the same gear</span></div>
    <div class="wb"><div class="row"><input id="nm" type="text" placeholder="Character name" style="width:220px">
      <select id="rg"><option value="nae">North America</option><option value="eu">Europe</option><option value="as">Asia</option><option value="la">Latin America</option></select>
      <button class="btn primary" id="find">Search</button><span id="cmsg" class="small muted"></span></div>
      <div id="hits" style="margin-top:10px"></div><div id="known" style="margin-top:10px"></div></div></section><div id="cview"></div>`;
  const known = await api("/api/characters").catch(() => []);
  if (known.length) $("#known").innerHTML = `<div class="small muted">Imported before: ${known.slice(0, 8).map((c) => `<span class="chip gold">${esc(c.name)} · ${esc(c.class_name)} · ${n0(c.combat_power)}</span>`).join("")}</div>`;
  $("#find").onclick = async () => {
    $("#cmsg").innerHTML = '<span class="spinner"></span>';
    try {
      const hits = await api(`/api/character/search?name=${encodeURIComponent($("#nm").value)}&region=${$("#rg").value}`);
      $("#cmsg").textContent = `${hits.length} found`;
      $("#hits").innerHTML = `<table class="t"><tr><th>Name</th><th>Level</th><th>Server</th><th></th></tr>${hits.slice(0, 30).map((h, i) =>
        `<tr><td>${esc(h.name)}</td><td>${h.level}</td><td>${esc(h.server)}</td><td class="r"><button class="btn small" data-imp="${i}">Import</button></td></tr>`).join("")}</table>`;
      $$("[data-imp]").forEach((b) => (b.onclick = () => doImport(hits[+b.dataset.imp])));
    } catch (e) { $("#cmsg").textContent = e.message; }
  };
  const doImport = async (h) => {
    $("#cview").innerHTML = '<div class="empty"><span class="spinner"></span> importing from the official site…</div>';
    try {
      const v = await runJob("/api/character/import", h, (log) => ($("#cmsg").textContent = log[log.length - 1] || ""));
      st.v = v; st.hit = h; showChar();
    } catch (e) { $("#cview").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  };
  const showChar = () => {
    const v = st.v;
    $("#cview").innerHTML = `<section class="win"><div class="wh"><h2>${esc(v.name)}</h2><span class="sub">${esc(cap(v.class))} · Lv ${v.level} · ${esc(v.server)} · Combat Power ${n0(v.combat_power)}</span>
      <div class="tools"><button class="btn primary" id="opt">Optimize my build</button></div></div><div class="wb">
      <div class="kpis">${Object.entries(v.dps || {}).map(([k, x]) => `<div class="kpi"><div class="k">${esc(k)} DPS as-is</div><div class="v">${n0(x)}</div></div>`).join("")}
        <div class="kpi"><div class="k">Skill points</div><div class="v">${v.points.skill}</div></div><div class="kpi"><div class="k">Stigma points</div><div class="v">${v.points.stigma}</div></div>
        <div class="kpi"><div class="k">Daevanion</div><div class="v">${v.points.daevanion}</div></div></div>
      ${(v.warnings || []).map((w) => `<div class="small muted">• ${esc(w)}</div>`).join("")}<div id="optres"></div></div></section><div id="cwins"></div>`;
    renderWindows(v, st, $("#cwins"));
    $("#opt").onclick = async () => {
      $("#opt").disabled = true;
      $("#optres").innerHTML = '<p><span class="spinner"></span> optimizing with your gear and points (several minutes)… <span id="olog" class="small muted"></span></p>';
      try {
        const r = await runJob("/api/character/optimize", st.hit, (log) => { const el = $("#olog"); if (el) el.textContent = log[log.length - 1] || ""; });
        const g = r.summary.gain;
        $("#optres").innerHTML = `<div class="kpis" style="margin-top:12px"><div class="kpi"><div class="k">Optimized boss DPS</div><div class="v">${n0(r.optimized.dps.boss)}</div></div>
          <div class="kpi"><div class="k">Gain</div><div class="v ${g > 0 ? "good" : ""}">${g >= 0 ? "+" : ""}${pct(g)}</div></div></div>
          <p class="small muted">The windows below now show the optimized build. What changes:</p><pre class="diff">${esc(r.diff)}</pre>`;
        st.v = Object.assign({}, r.optimized, { name: v.name, server: v.server, combat_power: v.combat_power });
        renderWindows(st.v, st, $("#cwins"));
      } catch (e) { $("#optres").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
      $("#opt").disabled = false;
    };
  };
  if (st.v) showChar();
}

function lineChart(per, roll) {
  const W = 1000, H = 190, n = per.length || 1, mx = Math.max(...per, ...roll, 1);
  const bars = per.map((v, i) => `<rect x="${(i / n) * W}" y="${H - (v / mx) * H}" width="${Math.max(1, W / n - 1)}" height="${(v / mx) * H}" fill="rgba(57,194,224,.28)"/>`).join("");
  const pts = roll.map((v, i) => `${((i + 0.5) / n) * W},${H - (v / mx) * H}`).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}<polyline points="${pts}" fill="none" stroke="#e8cf8e" stroke-width="2"/></svg>
    <div class="row small muted"><span>bars: damage per second</span><span style="color:#e8cf8e">line: 10 s average</span><span>peak 10 s: ${n0(Math.max(...roll))}</span></div>`;
}

async function pageCombat() {
  const st = S.combat;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Combat logs</h2><span class="sub">per-skill breakdown, timeline, rates, idle time — compared with your optimal rotation</span></div>
    <div class="wb"><div class="row"><input id="ref" type="text" placeholder="A2DIL record link or id" style="width:380px"><button class="btn primary" id="imp">Analyze</button>
      <span class="muted small">or</span><input id="file" type="file" accept=".json,.csv"><span id="lmsg" class="small muted"></span></div>
      <p class="small faint">Log format: JSON (see docs) or CSV with columns t, skill, damage, crit, double, perfect, multi, dot. Live capture plugs in through <code>aion2calc/combat/live.py</code>.</p>
      <div id="hist"></div></div></section><div id="enc"></div>`;
  const hist = await api("/api/encounters").catch(() => []);
  $("#hist").innerHTML = hist.length ? `<table class="t"><tr><th>#</th><th>Class</th><th>Target</th><th>Source</th><th class="r">Duration</th><th class="r">DPS</th><th></th></tr>${hist.map((e) =>
    `<tr><td>${e.id}</td><td>${esc(cap(e.class_name))}</td><td>${esc(e.boss || "")}</td><td>${esc(e.source)}</td><td class="r">${(e.duration || 0).toFixed(0)}s</td><td class="r num">${n0(e.dps)}</td>
     <td class="r"><button class="btn small" data-enc="${e.id}">Open</button></td></tr>`).join("")}</table>` : '<div class="faint small">No encounters yet.</div>';
  $$("[data-enc]").forEach((b) => (b.onclick = () => openEnc(+b.dataset.enc)));
  const show = (a) => { st.a = a; $("#enc").innerHTML = renderEncounter(a); };
  const openEnc = async (id) => { $("#enc").innerHTML = '<div class="empty"><span class="spinner"></span></div>'; show(await api("/api/encounters/" + id)); };
  $("#imp").onclick = async () => {
    try { show(await runJob("/api/encounters/import", { ref: $("#ref").value }, (l) => ($("#lmsg").textContent = l[l.length - 1] || ""))); pageCombatHistory(); }
    catch (e) { $("#lmsg").textContent = e.message; }
  };
  $("#file").onchange = async () => {
    const f = $("#file").files[0]; if (!f) return;
    const text = await f.text();
    try { show(await runJob("/api/encounters/import", { text, name: f.name }, (l) => ($("#lmsg").textContent = l[l.length - 1] || ""))); }
    catch (e) { $("#lmsg").textContent = e.message; }
  };
  if (st.a) show(st.a);
}
async function pageCombatHistory() { /* refresh list after import */ if (location.hash.startsWith("#/combat")) { const a = S.combat.a; await pageCombat(); if (a) $("#enc").innerHTML = renderEncounter(a); } }

function renderEncounter(a) {
  const s = a.summary, m = a.meta;
  const kp = [["DPS", n0(s.dps)], ["Total", n0(s.total)], ["Duration", s.duration.toFixed(0) + " s"], ["Casts / min", s.cpm.toFixed(0)],
    ["Crit", pct(s.crit)], ["Double", pct(s.double)], ["Perfect", pct(s.perfect)], ["Multi-hit", pct(s.multi)], ["Idle", s.idle_seconds.toFixed(1) + " s"],
    ["Biggest hit", s.biggest_hit ? `${n0(s.biggest_hit.damage)}` : "—"]];
  const mx = Math.max(...a.skills.map((r) => r.share), 0.0001);
  const table = `<table class="t"><tr><th>Skill</th><th>Share</th><th class="r">Casts</th><th class="r">Hits</th><th class="r">Crit</th><th class="r">Double</th><th class="r">Perfect</th>
    <th class="r">Avg hit</th><th class="r">Max hit</th><th class="r">Cooldown use</th></tr>${a.skills.map((r) => `<tr><td>${r.skill_id ? `<span class="icon xs" style="display:inline-block;vertical-align:middle;margin-right:6px"><img src="${icon("https://metabot.gg/web/aion2/skills/" + r.skill_id + ".webp")}"></span>` : ""}${esc(r.skill)}</td>
    <td style="width:22%"><div class="bar"><i style="width:${(100 * r.share) / mx}%"></i><span>${pct(r.share)}</span></div></td><td class="r">${r.kind === "passive" ? "proc" : r.casts}</td><td class="r">${r.hits}</td>
    <td class="r">${pct(r.crit, 0)}</td><td class="r">${pct(r.double, 0)}</td><td class="r">${pct(r.perfect, 0)}</td><td class="r num">${n0(r.avg_hit)}</td><td class="r num">${n0(r.max_hit)}</td>
    <td class="r">${r.cooldown_use == null ? "—" : pct(r.cooldown_use, 0)}</td></tr>`).join("")}</table>`;
  const rot = `<div class="rot">${a.rotation.map(([t, k]) => `<div class="r"><span class="faint">${t.toFixed(1)}</span> ${esc(k)}</div>`).join("")}</div>`;
  const buffs = a.buffs.map((b) => `<tr><td>${esc(b.name)}</td><td style="width:60%"><div class="bar"><i class="alt" style="width:${100 * (b.uptime || 0)}%"></i><span>${pct(b.uptime, 0)}</span></div></td></tr>`).join("");
  const o = a.vs_optimal || {};
  const opt = o.error ? `<div class="note">${esc(o.error)}</div>` : `${o.note ? `<div class="note">${esc(o.note)}</div>` : ""}
    <p>Share overlap with the optimal rotation: <b class="gold">${pct(o.share_overlap, 0)}</b>${o.comparable_dps ? ` · optimal DPS ${n0(o.sim_dps)} vs yours ${n0(o.actual_dps)}` : ""}</p>
    ${(o.tips || []).map((t) => `<div class="tip">${esc(t)}</div>`).join("")}
    <table class="t"><tr><th>Skill</th><th>Your share</th><th>Optimal share</th><th class="r">Your casts</th><th class="r">Optimal casts</th></tr>${(o.skills || []).slice(0, 16).map((r) =>
      `<tr><td>${esc(r.skill)}</td><td style="width:22%"><div class="bar"><i style="width:${100 * r.share}%"></i><span>${pct(r.share)}</span></div></td>
       <td style="width:22%"><div class="bar"><i class="alt" style="width:${100 * r.sim_share}%"></i><span>${pct(r.sim_share)}</span></div></td><td class="r">${r.casts}</td><td class="r">${r.sim_casts}</td></tr>`).join("")}</table>`;
  const t = a.vs_top || {};
  const top = t.rows ? `<p>Share overlap with the top Korean logs for this class: <b class="gold">${pct(t.overlap, 0)}</b></p><table class="t"><tr><th>Skill</th><th>You</th><th>Top logs</th><th class="r">Hits/min</th><th class="r">Top hits/min</th></tr>${t.rows.map((r) =>
      `<tr><td>${esc(r.skill)}</td><td>${pct(r.share)}</td><td>${pct(r.top_share)}</td><td class="r">${r.hpm.toFixed(0)}</td><td class="r">${r.top_hpm.toFixed(0)}</td></tr>`).join("")}</table>` : "";
  return win("Encounter", `${esc(cap(m.class))} · ${esc(m.target || "")} · ${esc(m.source)}${m.combat_power ? " · CP " + n0(m.combat_power) : ""}`,
      `<div class="kpis">${kp.map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
       <div style="margin-top:14px">${lineChart(a.timeline.per_second, a.timeline.rolling10)}</div>`) +
    win("Damage by skill", "", table) +
    `<div class="grid2">${win("Rotation (first casts)", "", rot)}${win("Buff uptime", "", `<table class="t">${buffs}</table>` + (a.gaps.length ? `<p class="small muted">Idle gaps: ${a.gaps.map((g) => `${g.start.toFixed(1)}–${g.end.toFixed(1)}s`).join(", ")}</p>` : ""))}</div>` +
    win("Compared with your optimal rotation", "same fight length, simulated", opt) + (top ? win("Compared with top players", "A2DIL top-10 dummy logs", top) : "");
}

async function pageDatabase() {
  app().innerHTML = `<section class="win"><div class="wh"><h2>Game database</h2><span class="sub">updates itself on every launch from the live sources — no code changes needed for new items, skills or classes</span>
    <div class="tools"><button class="btn" id="sync">Check for updates</button><button class="btn small" id="full">Full re-sync</button></div></div><div class="wb" id="dbs"></div></section>
    <section class="win"><div class="wh"><h2>Item catalog</h2></div><div class="wb"><div class="row"><input id="q" type="text" placeholder="search items"><select id="cat"><option value="">all categories</option></select>
      <button class="btn" id="srch">Search</button></div><div id="items" style="margin-top:10px"></div><div id="item"></div></div></section>`;
  const show = async () => {
    const s = await api("/api/status");
    const sy = s.sync, db = s.db, last = db.last_sync;
    $("#dbs").innerHTML = `<div class="kpis"><div class="kpi"><div class="k">Items</div><div class="v">${n0(db.items)}</div></div>
      <div class="kpi"><div class="k">Characters</div><div class="v">${db.characters}</div></div><div class="kpi"><div class="k">Encounters</div><div class="v">${db.encounters}</div></div>
      <div class="kpi"><div class="k">Last sync</div><div class="v small">${last ? new Date(last.at * 1000).toLocaleString() : "never"}</div></div></div>
      ${sy ? `<div style="margin-top:12px"><div class="row small"><b class="gold">${esc(sy.phase)}</b><span class="muted">${esc(sy.message)}</span><span class="faint">${sy.done}/${sy.total}</span></div>
        <div class="prog"><i style="width:${sy.total ? (100 * sy.done) / sy.total : sy.running ? 5 : 100}%"></i></div>
        ${Object.keys(sy.changed || {}).length ? `<div class="small muted" style="margin-top:6px">changed: ${esc(JSON.stringify(sy.changed))}</div>` : ""}
        ${(sy.errors || []).slice(0, 5).map((e) => `<div class="small bad">${esc(e)}</div>`).join("")}</div>` : ""}
      <p class="small faint">Data folder: ${esc(s.home)}</p>`;
    $("#cat").innerHTML = '<option value="">all categories</option>' + (db.categories || []).map(([c, k]) => `<option value="${esc(c)}">${esc(c)} (${k})</option>`).join("");
    return sy && sy.running;
  };
  const loop = async () => { if (!location.hash.startsWith("#/database")) return; const running = await show().catch(() => false); setTimeout(loop, running ? 2000 : 15000); };
  $("#sync").onclick = async () => { await api("/api/sync", {}); show(); };
  $("#full").onclick = async () => { await api("/api/sync", { force: true, budget: 3600 }); show(); };
  $("#srch").onclick = async () => {
    const items = await api(`/api/items?search=${encodeURIComponent($("#q").value)}&category=${encodeURIComponent($("#cat").value)}`);
    $("#items").innerHTML = `<table class="t"><tr><th></th><th>Item</th><th>Category</th><th class="r">Item level</th></tr>${items.map((it) =>
      `<tr data-item="${esc(it.slug)}" style="cursor:pointer"><td>${it.icon ? `<span class="icon xs"><img src="${icon(it.icon)}"></span>` : ""}</td><td class="gname" data-grade="${esc(it.grade)}">${esc(it.name)}</td>
       <td>${esc(it.category)}</td><td class="r">${it.item_level ?? ""}</td></tr>`).join("")}</table>`;
    $$("[data-item]").forEach((tr) => (tr.onclick = async () => {
      const it = await api("/api/items/" + tr.dataset.item);
      $("#item").innerHTML = win(it.name || it.slug, `${esc(it.grade || "")} ${esc(it.category || "")}`,
        `<div class="grid2"><div><h4 class="gold small">FIXED</h4>${kv(Object.entries(it.fixed || {}).map(([k, v]) => [k, esc(v)]))}
          <h4 class="gold small">ENCHANT</h4>${kv((it.enchant || []).map((e) => [e.step, esc(e.stats)]))}</div>
         <div><h4 class="gold small">RANDOM ROLL POOL</h4>${kv((it.random || []).map((r) => [r.stat, `${esc(r.range)} <span class="faint">${esc(r.chance)}</span>`]))}
          ${it.skill_pools && Object.keys(it.skill_pools).length ? `<h4 class="gold small">SKILL ROLL POOLS</h4>${Object.entries(it.skill_pools).map(([c, p]) => `<div class="small"><b>${esc(cap(c))}</b> (up to +${p.max_level}): ${p.skills.map(esc).join(", ")}</div>`).join("")}` : ""}</div></div>`);
    }));
  };
  loop();
}

// ------------------------------------------------------------- router
async function route() {
  const page = (location.hash.replace(/^#\//, "") || "planner").split("/")[0];
  $$(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  try {
    if (page === "character") await pageCharacter();
    else if (page === "combat") await pageCombat();
    else if (page === "database") await pageDatabase();
    else await pagePlanner();
  } catch (e) { app().innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);

async function syncPill() {
  try {
    const s = await api("/api/status");
    const sy = s.sync, el = $("#syncpill");
    const running = sy && sy.running;
    el.innerHTML = `<span class="dot ${running ? "run" : sy && sy.errors && sy.errors.length ? "err" : "ok"}"></span><span>${
      running ? `updating database · ${esc(sy.phase)} ${sy.total ? `${sy.done}/${sy.total}` : ""}` : `database ${n0(s.db.items)} items`}</span>`;
    setTimeout(syncPill, running ? 2500 : 20000);
  } catch (e) { setTimeout(syncPill, 20000); }
}
route();
syncPill();
