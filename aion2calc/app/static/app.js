/* aion2calc front end — vanilla JS, no build step. */
"use strict";

// ------------------------------------------------------------------ helpers
const DISCORD = "https://discord.gg/9y6zkUyvBv";
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
  (s.skills || []).forEach(([k, lv]) => extras.push(`<span class="chip" style="color:var(--gold)">${esc(k)} +${lv}</span>`));
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
const S = { planner: { win: "overview" }, character: { win: "overview" }, combat: {}, database: {}, gear: {}, raid: {} };

function welcomeCard() {
  let hidden = false;
  try { hidden = localStorage.getItem("welcome-hidden") === "1"; } catch (e) {}
  if (hidden) return "";
  return `<section class="win" id="welcome"><div class="wh"><h2>Welcome</h2><span class="sub">three steps to your best build</span>
      <div class="tools"><button class="btn small" id="whide">Hide</button></div></div><div class="wb">
    <div class="hero"><img src="/static/logo.png" alt=""><div><h1>aion2calc</h1><div class="muted">Plan your AION 2 build, check your gear and learn from your fights. Everything runs on this computer; the game database updates itself.</div>
      <div class="small" style="margin-top:6px">Questions or builds to share? <a href="${DISCORD}" target="_blank" rel="noopener">Join the Discord</a>.</div></div></div>
    <div class="welcome" style="margin-top:14px">
      <div class="wstep"><div class="n">I</div><h4>Import your character</h4><div class="small muted">Search your name on the official site: gear, rolls, skills, stigmas and Daevanion come in.</div>
        <a class="btn primary small" href="#/character" style="margin-top:8px;display:inline-block">My Character</a></div>
      <div class="wstep"><div class="n">II</div><h4>Get your advice</h4><div class="small muted">Best gear from your inventory, goal gear, arcana, titles, pantheon and genus insight, ranked by DPS gain.</div>
        <a class="btn primary small" href="#/gear" style="margin-top:8px;display:inline-block">Gear &amp; Advice</a></div>
      <div class="wstep"><div class="n">III</div><h4>Add your fights</h4><div class="small muted">Paste AbyssLogs links: see your rotation against the optimum, and the model learns from them.</div>
        <a class="btn primary small" href="#/combat" style="margin-top:8px;display:inline-block">Combat Logs</a></div>
    </div></div></section>`;
}

async function pagePlanner() {
  const st = S.planner;
  app().innerHTML = welcomeCard() + `<section class="win"><div class="wh"><h2>Build planner</h2><span class="sub">optimized builds — copy each window into the game</span></div>
    <div class="wb"><div class="row"><label class="muted small">Build</label><select id="res"></select>
      <span class="muted small">or optimize:</span><select id="cls"></select>
      <input id="sp" type="number" placeholder="skill pts (203)" title="skill points (default 203)" style="width:150px"><input id="stg" type="number" placeholder="stigma pts (30)" title="stigma points (default 30)" style="width:150px">
      <button class="btn primary" id="go">Optimize</button><span id="jobmsg" class="small muted"></span></div></div></section><div id="wins"></div>`;
  if ($("#whide")) $("#whide").onclick = () => { try { localStorage.setItem("welcome-hidden", "1"); } catch (e) {} $("#welcome").remove(); };
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
  const bars = per.map((v, i) => `<rect x="${(i / n) * W}" y="${H - (v / mx) * H}" width="${Math.max(1, W / n - 1)}" height="${(v / mx) * H}" style="fill:var(--chart-bar)"/>`).join("");
  const pts = roll.map((v, i) => `${((i + 0.5) / n) * W},${H - (v / mx) * H}`).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}<polyline points="${pts}" fill="none" style="stroke:var(--chart-line)" stroke-width="2"/></svg>
    <div class="row small muted"><span>bars: damage per second</span><span style="color:var(--gold)">line: 10 s average</span><span>peak 10 s: ${n0(Math.max(...roll))}</span></div>`;
}

async function pageCombat() {
  const st = S.combat;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Combat logs</h2><span class="sub">per-skill breakdown, timeline, rates, idle time — compared with your optimal rotation</span></div>
    <div class="wb"><div class="row"><input id="ref" type="text" placeholder="AbyssLogs link (abysslogs.com/e/…) or A2DIL link" style="width:400px">
      <input id="player" type="text" placeholder="player (party logs)" style="width:150px"><button class="btn primary" id="imp">Analyze</button>
      <span class="muted small">or</span><input id="file" type="file" accept=".json,.gz,.csv"><span id="lmsg" class="small muted"></span></div>
      <p class="small faint">Record a fight with the free <a href="https://abysslogs.com" target="_blank" rel="noopener">AbyssLogs meter</a>, press Share, and paste the link here. A party log shows the recorder's damage unless you name a player.
        Files: AbyssLogs segment (.json / .json.gz), aion2calc JSON (see docs), or CSV with columns t, skill, damage, crit, double, perfect, multi, dot.</p>
      <div class="row small" id="logsdir"></div>
      <div class="row small" id="lsrv"></div>
      <div id="hist"></div></div></section><div id="enc"></div>`;
  api("/api/logs").then((l) => {
    $("#logsdir").innerHTML = `<span class="muted">Every analyzed log is saved as a file in</span> <code>${esc(l.folder)}</code> <span class="faint">(${l.files} files)</span>
      <button class="btn small" id="openlogs">Open folder</button>`;
    $("#openlogs").onclick = () => api("/api/logs/open", {}).catch((e) => ($("#lmsg").textContent = e.message));
  }).catch(() => {});
  const srv = async () => {
    const c = await api("/api/logserver").catch(() => ({}));
    $("#lsrv").innerHTML = `<span class="muted">Share to a log server:</span><input id="lsurl" type="text" placeholder="https://logs.example.com" value="${esc(c.url || "")}" style="width:240px">
      <input id="lskey" type="password" placeholder="${c.has_key ? "key saved" : "upload key"}" style="width:160px">
      <select id="lsvis">${["unlisted", "public", "private"].map((v) => `<option ${v === (c.visibility || "unlisted") ? "selected" : ""}>${v}</option>`).join("")}</select>
      <button class="btn small" id="lssave">Save</button>`;
    $("#lssave").onclick = async () => { await api("/api/logserver", { url: $("#lsurl").value, key: $("#lskey").value || null, visibility: $("#lsvis").value }); toast("Saved"); srv(); };
  };
  srv();
  const hist = await api("/api/encounters").catch(() => []);
  $("#hist").innerHTML = hist.length ? `<table class="t"><tr><th>#</th><th>Player</th><th>Class</th><th>Target</th><th>Source</th><th class="r">Duration</th><th class="r">DPS</th><th></th></tr>${hist.map((e) =>
    `<tr><td>${e.id}</td><td>${esc(e.player || "")}</td><td>${esc(cap(e.class_name))}</td><td>${esc(e.boss || "")}</td><td>${esc(e.source)}</td><td class="r">${(e.duration || 0).toFixed(0)}s</td><td class="r num">${n0(e.dps)}</td>
     <td class="r"><button class="btn small" data-enc="${e.id}">Open</button></td></tr>`).join("")}</table>` : '<div class="faint small">No encounters yet.</div>';
  $$("[data-enc]").forEach((b) => (b.onclick = () => openEnc(+b.dataset.enc)));
  const progress = (l) => ($("#lmsg").textContent = l[l.length - 1] || "");
  const show = (a) => {
    st.a = a; $("#enc").innerHTML = renderEncounter(a);
    $$("[data-share]").forEach((b) => (b.onclick = async () => {
      try {
        const r = await api(`/api/encounters/${a.id}/share`, {});
        $("#shared").innerHTML = `Shared: <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a> <button class="btn small" id="cpy">Copy link</button>`;
        $("#cpy").onclick = () => copyText(r.url);
      } catch (e) { $("#shared").textContent = e.message; }
    }));
    $$("[data-player]").forEach((b) => (b.onclick = async () => {        // another player of the same party log
      try { show(await runJob("/api/encounters/import", { ref: a.meta.url, player: b.dataset.player }, progress)); pageCombatHistory(); }
      catch (e) { $("#lmsg").textContent = e.message; }
    }));
  };
  const openEnc = async (id) => { $("#enc").innerHTML = '<div class="empty"><span class="spinner"></span></div>'; show(await api("/api/encounters/" + id)); };
  $("#imp").onclick = async () => {
    try { show(await runJob("/api/encounters/import", { ref: $("#ref").value, player: $("#player").value }, progress)); pageCombatHistory(); }
    catch (e) { $("#lmsg").textContent = e.message; }
  };
  $("#file").onchange = async () => {
    const f = $("#file").files[0]; if (!f) return;
    try {
      const gz = new Uint8Array(await f.slice(0, 2).arrayBuffer());
      const text = gz[0] === 0x1f && gz[1] === 0x8b                      // AbyssLogs segment files are gzip
        ? await new Response(f.stream().pipeThrough(new DecompressionStream("gzip"))).text() : await f.text();
      show(await runJob("/api/encounters/import", { text, name: f.name, player: $("#player").value }, progress)); pageCombatHistory();
    } catch (e) { $("#lmsg").textContent = e.message; }
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
  const specs = (o.specs || []).length ? `<h4 class="gold small" style="margin-top:14px">SPECIALIZATIONS (from the log)</h4>
    <table class="t"><tr><th>Skill</th><th>In this log</th><th>Optimized build</th></tr>${o.specs.map((d) =>
      `<tr><td>${esc(d.skill)}</td><td class="${d.differs ? "bad" : ""}">${esc(d.yours || "none")}</td><td class="gold">${esc(d.optimal)}</td></tr>`).join("")}</table>` : "";
  const t = a.vs_top || {};
  const top = t.rows ? `<p>Share overlap with the top Korean logs for this class: <b class="gold">${pct(t.overlap, 0)}</b></p><table class="t"><tr><th>Skill</th><th>You</th><th>Top logs</th><th class="r">Hits/min</th><th class="r">Top hits/min</th></tr>${t.rows.map((r) =>
      `<tr><td>${esc(r.skill)}</td><td>${pct(r.share)}</td><td>${pct(r.top_share)}</td><td class="r">${r.hpm.toFixed(0)}</td><td class="r">${r.top_hpm.toFixed(0)}</td></tr>`).join("")}</table>` : "";
  const party = (m.party || []).length > 1 ? `<div class="row small" style="margin-top:10px"><span class="muted">Party:</span>${m.party.map((p) =>
      `<button class="btn small ${p.name === m.player ? "primary" : ""}" data-player="${esc(p.name)}" title="${esc(p.class)} · ${n0(p.damage)} damage">${esc(p.name)} <span class="faint">${esc(p.class || "")}</span></button>`).join("")}</div>` : "";
  const shareRow = a.id ? `<div class="row small" style="margin-top:8px"><button class="btn small primary" data-share="1">Share link</button><span id="shared" class="muted"></span></div>` : "";
  const info = shareRow + `<div class="small muted" style="margin-top:8px">${(m.notes || []).map(esc).join(" · ")}${m.url ? ` · <a href="${esc(m.url)}" target="_blank" rel="noopener">open on AbyssLogs</a>` : ""}${a.file ? ` · saved as <code>${esc(a.file)}</code>` : ""}</div>`;
  return win("Encounter", `${esc(m.player || "")} · ${esc(cap(m.class || m.class_name || ""))} · ${esc(m.target || "")} · ${esc(m.source)}${m.combat_power ? " · CP " + n0(m.combat_power) : ""}`,
      `${party}${info}<div class="kpis">${kp.map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
       <div style="margin-top:14px">${lineChart(a.timeline.per_second, a.timeline.rolling10)}</div>`) +
    win("Damage by skill", "", table) +
    `<div class="grid2">${win("Rotation (first casts)", "", rot)}${win("Buff uptime", "", `<table class="t">${buffs}</table>` + (a.gaps.length ? `<p class="small muted">Idle gaps: ${a.gaps.map((g) => `${g.start.toFixed(1)}–${g.end.toFixed(1)}s`).join(", ")}</p>` : ""))}</div>` +
    win("Compared with your optimal rotation", "same fight length, simulated", opt + specs) + (top ? win("Compared with top players", "A2DIL top-10 dummy logs", top) : "");
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

// ------------------------------------------------------------- raid planner
// A plan is an "a2plan" document: tokens (players, enemies, markers, AoE zones) whose
// positions are keyframed over a timeline, plus party-buff windows. Positions are
// normalized 0..1 on a square arena and interpolated linearly between keyframes, so a
// time slider (timelapse) plays the movement back. Plans are kept in localStorage and
// can be exported, imported or shared as a code; a saved combat log can be overlaid on
// the same timeline to compare the planned route with the real execution.
const A2PLAN_KEY = "a2plans";
const RAID_CLASSES = ["Gladiator", "Templar", "Assassin", "Ranger", "Sorcerer", "Spiritmaster", "Cleric", "Chanter", "Bard", "Painter", "Aethertech"];
const TOKEN_COLORS = ["#e66a5a", "#39c2e0", "#6fcf7a", "#e9a43a", "#a46cf0", "#f05a8c", "#5bc0de", "#b9984f", "#7fd6a8", "#6fa8dc", "#d4b45a", "#9fd36f"];
const RAID_MARKERS = ["A", "B", "C", "D", "1", "2", "3", "4"];

function raidPlans() { try { return JSON.parse(localStorage.getItem(A2PLAN_KEY) || "{}"); } catch (e) { return {}; } }
function saveRaidPlans(all) { try { localStorage.setItem(A2PLAN_KEY, JSON.stringify(all)); } catch (e) { toast("Could not save — browser storage is full"); } }
function uid() { return Math.random().toString(36).slice(2, 9); }
function newPlan(name) {
  return { format: "a2plan", version: 1,
    meta: { name: name || "New plan", author: "", notes: "", created: Date.now(), updated: Date.now() },
    arena: { kind: "square" }, duration: 60, tokens: [], buffs: [], source: {} };
}
// position of a token at time t, interpolating its keyframes; null if it has none
function tokenPos(tk, t) {
  const k = tk.keyframes || [];
  if (!k.length) return null;
  if (t <= k[0].t) return { x: k[0].x, y: k[0].y };
  const last = k[k.length - 1];
  if (t >= last.t) return { x: last.x, y: last.y };
  for (let i = 1; i < k.length; i++) {
    if (t <= k[i].t) { const a = k[i - 1], b = k[i], f = (t - a.t) / Math.max(1e-6, b.t - a.t); return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f }; }
  }
  return { x: last.x, y: last.y };
}
function setKeyframe(tk, t, x, y) {
  t = Math.round(t * 10) / 10;
  x = Math.max(0, Math.min(1, x)); y = Math.max(0, Math.min(1, y));
  tk.keyframes = tk.keyframes || [];
  const i = tk.keyframes.findIndex((kf) => Math.abs(kf.t - t) < 0.05);
  if (i >= 0) { tk.keyframes[i].x = x; tk.keyframes[i].y = y; }
  else { tk.keyframes.push({ t, x, y }); tk.keyframes.sort((a, b) => a.t - b.t); }
}
function planToCode(p) { const b = new TextEncoder().encode(JSON.stringify(p)); let s = ""; b.forEach((c) => (s += String.fromCharCode(c))); return btoa(s); }
function codeToPlan(code) {
  const bin = atob(code.trim()), b = Uint8Array.from(bin, (c) => c.charCodeAt(0)), p = JSON.parse(new TextDecoder().decode(b));
  if (!p || p.format !== "a2plan") throw new Error("That is not an a2plan share code");
  return p;
}
function download(name, text, type = "application/json") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

async function pageRaid() {
  const st = S.raid;
  if (st.timer) { clearInterval(st.timer); st.timer = null; }   // stop any playback from a previous visit
  st.playing = false;
  if (st.speed == null) st.speed = 1;
  if (st.t == null) st.t = 0;
  const all = raidPlans();
  if (!st.id || !all[st.id]) {
    const ids = Object.keys(all).sort((a, b) => (all[b].meta?.updated || 0) - (all[a].meta?.updated || 0));
    if (ids.length) st.id = ids[0];
    else { const p = newPlan("My first plan"); st.id = uid(); all[st.id] = p; saveRaidPlans(all); }
  }
  st.plan = raidPlans()[st.id];
  st.encounters = await api("/api/encounters").catch(() => []);
  renderRaid();
}

function persistRaid() {
  const st = S.raid; if (!st.id || !st.plan) return;
  st.plan.meta = st.plan.meta || {}; st.plan.meta.updated = Date.now();
  const all = raidPlans(); all[st.id] = st.plan; saveRaidPlans(all);
}

function renderRaid() {
  const st = S.raid, p = st.plan, dur = p.duration || 1;
  const all = raidPlans();
  const planOpts = Object.entries(all).sort((a, b) => (b[1].meta?.updated || 0) - (a[1].meta?.updated || 0))
    .map(([id, pl]) => `<option value="${esc(id)}" ${id === st.id ? "selected" : ""}>${esc(pl.meta?.name || "Untitled")}</option>`).join("");
  const sel = p.tokens.find((x) => x.id === st.sel) || null;
  const players = p.tokens.filter((x) => x.kind === "player");

  const header = `<div class="row"><label class="muted small">Plan</label><select id="rplan" style="min-width:180px">${planOpts}</select>
      <button class="btn small" id="rnew">New</button><button class="btn small" id="rdup">Duplicate</button><button class="btn small" id="rdel">Delete</button></div>
    <div class="row" style="margin-top:8px"><input id="rname" type="text" value="${esc(p.meta?.name || "")}" placeholder="Plan name" style="width:200px">
      <input id="rauthor" type="text" value="${esc(p.meta?.author || "")}" placeholder="Author (optional)" style="width:160px">
      <label class="muted small">Length</label><input id="rdur" type="number" min="5" max="1800" value="${dur}" style="width:80px"><span class="muted small">s</span>
      <label class="muted small">Arena</label><select id="rarena"><option value="square" ${p.arena?.kind !== "circle" ? "selected" : ""}>Square</option><option value="circle" ${p.arena?.kind === "circle" ? "selected" : ""}>Circle</option></select></div>
    <div class="row" style="margin-top:8px"><button class="btn small" id="rexport">Export file</button>
      <label class="btn small" style="cursor:pointer">Import file<input id="rimport" type="file" accept=".json,.a2plan" hidden></label>
      <button class="btn small" id="rcode">Copy share code</button><button class="btn small" id="rload">Load from code</button>
      <span class="faint small">Plans are saved on this computer. Publishing to a server and live co-viewing are coming next.</span></div>`;

  const tokensHtml = p.tokens.map((tk) => {
    const s = tk.id === st.sel ? " sel" : "";
    if (tk.kind === "aoe") return `<div class="rtoken aoe${s}" id="tok-${tk.id}" data-tid="${tk.id}" style="--tc:${esc(tk.color)}" title="${esc(tk.label || "AoE zone")}"></div>`;
    const glyph = tk.kind === "marker" ? esc(tk.label || "?") : esc((tk.label && tk.label[0]) || (tk.cls && tk.cls[0]) || (tk.kind === "enemy" ? "B" : "P")).toUpperCase();
    return `<div class="rtoken ${tk.kind}${s}" id="tok-${tk.id}" data-tid="${tk.id}" style="--tc:${esc(tk.color)}" title="${esc(tk.label || tk.cls || tk.kind)}"><span class="rl">${glyph}</span></div>`;
  }).join("");

  const buffColor = (bf) => { const by = players.find((x) => (x.label || x.cls) === bf.by); return by ? by.color : "var(--gold)"; };
  const buffBars = p.buffs.map((bf) => {
    const l = 100 * Math.max(0, bf.start) / dur, w = 100 * Math.max(0, bf.end - bf.start) / dur;
    return `<div class="bufbar" data-start="${bf.start}" data-end="${bf.end}" style="left:${l}%;width:${w}%;--tc:${buffColor(bf)}" title="${esc(bf.name)}${bf.by ? " · " + esc(bf.by) : ""}">${esc(bf.name)}</div>`;
  }).join("");
  const actualLane = st.actual ? `<div class="rlane"><div class="lanehd">Actual casts</div><div class="lanebody">
      ${st.actual.rotation.map(([ct]) => `<i class="casttick" style="left:${100 * ct / dur}%"></i>`).join("")}</div></div><div class="row small" id="castnow"></div>` : "";

  const left = `<div class="arena ${p.arena?.kind === "circle" ? "circle" : ""}" id="arena"><svg class="rpath" id="rpath" viewBox="0 0 100 100" preserveAspectRatio="none"></svg>${tokensHtml}
      ${p.tokens.length ? "" : '<div class="arenahint">Add players, enemies, markers or AoE zones from the panel, then drag them on the map.</div>'}</div>
    <div class="rtransport"><button class="btn small" id="rstart" title="Back to start">⏮</button>
      <button class="btn small primary" id="rplay">${st.playing ? "⏸ Pause" : "▶ Play"}</button>
      <select id="rspeed" title="Playback speed">${[0.5, 1, 2, 4].map((x) => `<option value="${x}" ${st.speed === x ? "selected" : ""}>${x}×</option>`).join("")}</select>
      <input type="range" id="rscrub" min="0" max="${dur}" step="0.1" value="${st.t}" style="flex:1">
      <span id="rtime" class="small muted mono"></span></div>
    <div class="rlane"><div class="lanehd">Party buffs</div><div class="lanebody" id="buflane">${buffBars || '<span class="faint small" style="padding:0 6px">add buffs in the panel →</span>'}</div></div>
    <div class="row small" id="bufnow"></div>${actualLane}`;

  let editor = '<p class="faint small">Select a token on the map to edit it.</p>';
  if (sel) {
    const kfs = (sel.keyframes || []).map((k, i) => `<div class="kfrow"><button class="btn small" data-kgo="${k.t}">${k.t.toFixed(1)}s</button>
        <span class="small muted">x ${(k.x * 100).toFixed(0)} · y ${(k.y * 100).toFixed(0)}</span>${(sel.keyframes.length > 1) ? `<button class="btn small" data-kdel="${i}" title="Delete this keyframe">✕</button>` : ""}</div>`).join("");
    editor = `<div class="row"><input id="slabel" type="text" value="${esc(sel.label || "")}" placeholder="Label" style="width:120px">
        <input id="scolor" type="color" value="${esc(sel.color || "#39c2e0")}" style="width:40px;padding:2px">
        ${sel.kind === "player" ? `<select id="scls">${RAID_CLASSES.map((c) => `<option ${c === sel.cls ? "selected" : ""}>${c}</option>`).join("")}</select>` : ""}</div>
      ${sel.kind === "aoe" ? `<div class="row" style="margin-top:6px"><label class="muted small">Radius</label><input id="srad" type="range" min="4" max="50" value="${Math.round((sel.radius || 0.14) * 100)}" style="flex:1"></div>` : ""}
      <div class="kflist" style="margin-top:8px"><div class="small muted">Keyframes (position over time)</div>${kfs || '<div class="faint small">none</div>'}
        <button class="btn small" id="kadd" style="margin-top:4px">Set position at ${st.t.toFixed(1)}s</button></div>
      <button class="btn small" id="sdel" style="margin-top:8px">Remove token</button>`;
  }

  const buffList = p.buffs.map((bf, i) => `<div class="row small bufedit"><input data-bf="${i}" data-k="name" value="${esc(bf.name)}" style="width:110px">
      <select data-bf="${i}" data-k="by" style="width:90px"><option value="">—</option>${players.map((pl) => { const nm = pl.label || pl.cls; return `<option ${nm === bf.by ? "selected" : ""}>${esc(nm)}</option>`; }).join("")}</select>
      <input data-bf="${i}" data-k="start" type="number" min="0" value="${bf.start}" style="width:58px"><span class="faint">–</span>
      <input data-bf="${i}" data-k="end" type="number" min="0" value="${bf.end}" style="width:58px"><button class="btn small" data-bfdel="${i}">✕</button></div>`).join("");

  const side = `<div class="rpanel"><h4 class="gold small">ADD</h4>
      <div class="row"><select id="rcls">${RAID_CLASSES.map((c) => `<option>${c}</option>`).join("")}</select><button class="btn small primary" id="raddp">+ Player</button></div>
      <div class="row" style="margin-top:6px"><button class="btn small" id="radde">+ Enemy</button><button class="btn small" id="raddm">+ Marker</button><button class="btn small" id="radda">+ AoE</button></div>
      <p class="small faint">Move the slider to a moment, then drag a token to where it should be then. The planner interpolates the movement in between.</p>
      <h4 class="gold small">SELECTED TOKEN</h4>${editor}
      <h4 class="gold small">PARTY BUFFS</h4><div class="bufedits">${buffList || '<div class="faint small">none yet</div>'}</div>
      <div class="row small" style="margin-top:6px"><input id="bfname" placeholder="Buff name" style="width:110px"><select id="bfby" style="width:90px"><option value="">source…</option>${players.map((pl) => { const nm = pl.label || pl.cls; return `<option>${esc(nm)}</option>`; }).join("")}</select>
        <input id="bfstart" type="number" min="0" value="0" style="width:52px"><span class="faint">–</span><input id="bfend" type="number" min="0" value="10" style="width:52px"><button class="btn small" id="bfadd">Add</button></div>
      <h4 class="gold small">COMPARE WITH A FIGHT</h4>
      <div class="row"><select id="ractual"><option value="">— none —</option>${(st.encounters || []).map((e) => `<option value="${e.id}" ${st.actual && st.actual.id === e.id ? "selected" : ""}>#${e.id} ${esc(e.player || "")} ${esc(e.boss || "")} ${(e.duration || 0).toFixed(0)}s</option>`).join("")}</select></div>
      <p class="small faint">Overlay a saved combat log so its skill casts and buff windows play on the same timeline (map positions show here when a log carries them). Planner-only data defaults to private; attaching a fight shares the real run too.</p>
      <h4 class="gold small">NOTES</h4><textarea id="rnotes" rows="4" style="width:100%" placeholder="Callouts, phases, assignments…">${esc(p.meta?.notes || "")}</textarea></div>`;

  app().innerHTML = win("Raid & boss planner", "drag player tokens on the map and scrub the timeline to plan movement, cooldowns and party buffs",
    header + `<div class="raidwrap"><div>${left}</div>${side}</div>`, { key: "raidplanner" });

  bindRaid();
}

function bindRaid() {
  const st = S.raid, p = st.plan;
  const arena = $("#arena");

  const layout = () => {
    const t = st.t, dur = p.duration || 1;
    if (!arena) return;
    p.tokens.forEach((tk) => {
      const el = arena.querySelector("#tok-" + tk.id); if (!el) return;
      const pos = tokenPos(tk, t);
      if (!pos) { el.style.display = "none"; return; }
      el.style.display = ""; el.style.left = (pos.x * 100) + "%"; el.style.top = (pos.y * 100) + "%";
      if (tk.kind === "aoe") { const d = (tk.radius || 0.14) * 2 * 100; el.style.width = d + "%"; el.style.height = d + "%"; }
    });
    const path = $("#rpath"), tk = p.tokens.find((x) => x.id === st.sel);
    if (path) path.innerHTML = !tk || !tk.keyframes ? "" :
      (tk.keyframes.length > 1 ? `<polyline points="${tk.keyframes.map((k) => `${k.x * 100},${k.y * 100}`).join(" ")}"/>` : "")
      + tk.keyframes.map((k) => `<circle cx="${k.x * 100}" cy="${k.y * 100}" r="1.6" class="${Math.abs(k.t - t) < 0.06 ? "kon" : ""}"/>`).join("");
    const rd = $("#rtime"); if (rd) rd.textContent = t.toFixed(1) + " / " + dur + "s";
    const sc = $("#rscrub"); if (sc && document.activeElement !== sc) sc.value = String(t);
    $$(".bufbar").forEach((b) => b.classList.toggle("on", +b.dataset.start <= t && t <= +b.dataset.end));
    const now = p.buffs.filter((bf) => bf.start <= t && t <= bf.end), bn = $("#bufnow");
    if (bn) bn.innerHTML = `<span class="muted">Buffs now:</span> ` + (now.length ? now.map((bf) => `<span class="chip gold">${esc(bf.name)}${bf.by ? " · " + esc(bf.by) : ""}</span>`).join(" ") : '<span class="faint">none</span>');
    if (st.actual) { const near = st.actual.rotation.filter(([ct]) => Math.abs(ct - t) < 0.4).map(([, k]) => k), cn = $("#castnow");
      if (cn) cn.innerHTML = `<span class="muted">Casts:</span> ` + (near.length ? near.map((k) => `<span class="chip">${esc(k)}</span>`).join(" ") : '<span class="faint">—</span>'); }
  };
  st.layout = layout;

  const pause = () => { if (st.timer) { clearInterval(st.timer); st.timer = null; } st.playing = false; const b = $("#rplay"); if (b) b.textContent = "▶ Play"; };
  const play = () => {
    if (st.timer) return;
    st.playing = true; const b = $("#rplay"); if (b) b.textContent = "⏸ Pause";
    st.timer = setInterval(() => {
      if (!location.hash.startsWith("#/raid")) { pause(); return; }
      st.t = Math.round((st.t + 0.05 * (st.speed || 1)) * 100) / 100;
      if (st.t >= (p.duration || 1)) { st.t = p.duration || 1; layout(); pause(); return; }
      layout();
    }, 50);
  };

  // --- plan management
  const reload = () => { st.plan = raidPlans()[st.id]; st.sel = null; st.t = 0; st.actual = null; renderRaid(); };
  $("#rplan").onchange = (e) => { st.id = e.target.value; reload(); };
  $("#rnew").onclick = () => { const all = raidPlans(), id = uid(); all[id] = newPlan("New plan"); saveRaidPlans(all); st.id = id; reload(); };
  $("#rdup").onclick = () => { const all = raidPlans(), id = uid(), copy = JSON.parse(JSON.stringify(p)); copy.meta.name = (p.meta?.name || "Plan") + " copy"; copy.meta.created = copy.meta.updated = Date.now(); all[id] = copy; saveRaidPlans(all); st.id = id; reload(); };
  $("#rdel").onclick = () => { if (!confirm("Delete this plan?")) return; const all = raidPlans(); delete all[st.id]; saveRaidPlans(all); st.id = null; reload(); };
  $("#rname").onchange = (e) => { p.meta.name = e.target.value; persistRaid(); };
  $("#rauthor").onchange = (e) => { p.meta.author = e.target.value; persistRaid(); };
  $("#rdur").onchange = (e) => { p.duration = Math.max(5, +e.target.value || 60); persistRaid(); renderRaid(); };
  $("#rarena").onchange = (e) => { p.arena.kind = e.target.value; persistRaid(); renderRaid(); };
  $("#rnotes").onchange = (e) => { p.meta.notes = e.target.value; persistRaid(); };
  $("#rexport").onclick = () => download((p.meta?.name || "plan").replace(/[^\w-]+/g, "_") + ".a2plan", JSON.stringify(p, null, 2));
  $("#rimport").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { const pl = JSON.parse(await f.text()); if (pl.format !== "a2plan") throw new Error("Not an a2plan file");
      const all = raidPlans(), id = uid(); pl.meta = pl.meta || {}; pl.meta.updated = Date.now(); all[id] = pl; saveRaidPlans(all); st.id = id; reload(); toast("Plan imported"); }
    catch (err) { toast(err.message); }
  };
  $("#rcode").onclick = () => { copyText(planToCode(p)); };
  $("#rload").onclick = () => {
    const code = prompt("Paste an a2plan share code:"); if (!code) return;
    try { const pl = codeToPlan(code), all = raidPlans(), id = uid(); pl.meta = pl.meta || {}; pl.meta.updated = Date.now(); all[id] = pl; saveRaidPlans(all); st.id = id; reload(); toast("Plan loaded"); }
    catch (err) { toast(err.message); }
  };

  // --- add tokens
  const pickColor = () => { const used = new Set(p.tokens.map((t) => t.color)); return TOKEN_COLORS.find((c) => !used.has(c)) || TOKEN_COLORS[p.tokens.length % TOKEN_COLORS.length]; };
  const addToken = (tk) => { setKeyframe(tk, 0, 0.5 + (Math.random() - 0.5) * 0.3, 0.5 + (Math.random() - 0.5) * 0.3); p.tokens.push(tk); st.sel = tk.id; persistRaid(); renderRaid(); };
  $("#raddp").onclick = () => { const cls = $("#rcls").value; addToken({ id: uid(), kind: "player", label: cls, cls, color: pickColor(), keyframes: [] }); };
  $("#radde").onclick = () => addToken({ id: uid(), kind: "enemy", label: "Boss", color: "#d33939", keyframes: [] });
  $("#raddm").onclick = () => { const used = p.tokens.filter((t) => t.kind === "marker").length; addToken({ id: uid(), kind: "marker", label: RAID_MARKERS[used % RAID_MARKERS.length], color: "#e9cf8e", keyframes: [] }); };
  $("#radda").onclick = () => addToken({ id: uid(), kind: "aoe", label: "AoE", color: "#e9a43a", radius: 0.16, keyframes: [] });

  // --- selected token editor
  if (st.sel) {
    const tk = p.tokens.find((x) => x.id === st.sel);
    if ($("#slabel")) $("#slabel").onchange = (e) => { tk.label = e.target.value; persistRaid(); renderRaid(); };
    if ($("#scolor")) $("#scolor").onchange = (e) => { tk.color = e.target.value; persistRaid(); renderRaid(); };
    if ($("#scls")) $("#scls").onchange = (e) => { tk.cls = e.target.value; if (!tk.label || RAID_CLASSES.includes(tk.label)) tk.label = e.target.value; persistRaid(); renderRaid(); };
    if ($("#srad")) $("#srad").oninput = (e) => { tk.radius = (+e.target.value) / 100; layout(); };
    if ($("#srad")) $("#srad").onchange = () => persistRaid();
    if ($("#kadd")) $("#kadd").onclick = () => { const pos = tokenPos(tk, st.t) || { x: 0.5, y: 0.5 }; setKeyframe(tk, st.t, pos.x, pos.y); persistRaid(); renderRaid(); };
    $$("[data-kgo]").forEach((b) => (b.onclick = () => { st.t = +b.dataset.kgo; layout(); }));
    $$("[data-kdel]").forEach((b) => (b.onclick = () => { tk.keyframes.splice(+b.dataset.kdel, 1); persistRaid(); renderRaid(); }));
    if ($("#sdel")) $("#sdel").onclick = () => { p.tokens = p.tokens.filter((x) => x.id !== st.sel); st.sel = null; persistRaid(); renderRaid(); };
  }

  // --- buffs
  $$("[data-bf]").forEach((inp) => (inp.onchange = () => {
    const bf = p.buffs[+inp.dataset.bf]; if (!bf) return;
    const k = inp.dataset.k; bf[k] = (k === "start" || k === "end") ? (+inp.value || 0) : inp.value;
    persistRaid(); renderRaid();
  }));
  $$("[data-bfdel]").forEach((b) => (b.onclick = () => { p.buffs.splice(+b.dataset.bfdel, 1); persistRaid(); renderRaid(); }));
  if ($("#bfadd")) $("#bfadd").onclick = () => {
    const name = $("#bfname").value.trim(); if (!name) { toast("Name the buff"); return; }
    p.buffs.push({ id: uid(), name, by: $("#bfby").value, start: +$("#bfstart").value || 0, end: +$("#bfend").value || 0, note: "" });
    persistRaid(); renderRaid();
  };

  // --- compare-with-a-fight overlay
  if ($("#ractual")) $("#ractual").onchange = async (e) => {
    const id = e.target.value;
    if (!id) { st.actual = null; renderRaid(); return; }
    try {
      const a = await api("/api/encounters/" + id);
      st.actual = { id: +id, rotation: a.rotation || [], buffs: a.buffs || [], duration: a.summary?.duration || p.duration };
      if (st.actual.duration > p.duration) { p.duration = Math.ceil(st.actual.duration); persistRaid(); }
      renderRaid();
    } catch (err) { toast(err.message); }
  };

  // --- transport
  if ($("#rplay")) $("#rplay").onclick = () => (st.playing ? pause() : play());
  if ($("#rstart")) $("#rstart").onclick = () => { st.t = 0; layout(); };
  if ($("#rspeed")) $("#rspeed").onchange = (e) => { st.speed = +e.target.value; };
  if ($("#rscrub")) $("#rscrub").oninput = (e) => { if (st.playing) pause(); st.t = +e.target.value; layout(); };

  // --- drag tokens on the map (sets a keyframe at the current time)
  let drag = null;
  const norm = (ev, rect) => ({ x: Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height)) });
  if (arena) {
    arena.addEventListener("pointerdown", (ev) => {
      const el = ev.target.closest(".rtoken"); if (!el) return;
      if (st.playing) pause();
      const tid = el.dataset.tid;
      st.sel = tid; $$(".rtoken", arena).forEach((x) => x.classList.toggle("sel", x.dataset.tid === tid)); layout();
      drag = { tid, el, rect: arena.getBoundingClientRect(), moved: false };
      try { el.setPointerCapture(ev.pointerId); } catch (e) {}
      ev.preventDefault();
    });
    arena.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      const q = norm(ev, drag.rect); drag.x = q.x; drag.y = q.y; drag.moved = true;
      drag.el.style.left = (q.x * 100) + "%"; drag.el.style.top = (q.y * 100) + "%";
      const tk = p.tokens.find((x) => x.id === drag.tid), path = $("#rpath");
      if (tk && path) { const pts = (tk.keyframes || []).map((k) => Math.abs(k.t - st.t) < 0.06 ? `${q.x * 100},${q.y * 100}` : `${k.x * 100},${k.y * 100}`);
        path.innerHTML = (pts.length > 1 ? `<polyline points="${pts.join(" ")}"/>` : "") + `<circle cx="${q.x * 100}" cy="${q.y * 100}" r="1.6" class="kon"/>`; }
    });
    const drop = () => {
      if (!drag) return; const d = drag; drag = null;
      if (d.moved) { const tk = p.tokens.find((x) => x.id === d.tid); if (tk) { setKeyframe(tk, st.t, d.x, d.y); persistRaid(); } }
      renderRaid();
    };
    arena.addEventListener("pointerup", drop);
    arena.addEventListener("pointercancel", drop);
  }

  layout();
}

// ------------------------------------------------------------- gear & advice
const sp = (x) => (x == null ? "—" : (x >= 0 ? "+" : "") + (100 * x).toFixed(1) + "%");
async function pageGear() {
  const st = S.gear || (S.gear = {});
  const chars = await api("/api/characters").catch(() => []);
  app().innerHTML = `<section class="win"><div class="wh"><h2>Gear &amp; advice</h2><span class="sub">what to wear from your inventory, goal gear, upgrade path, arcana, pantheon, genus insight — on simulated DPS</span></div>
    <div class="wb">${chars.length ? `<div class="row"><select id="gchar">${chars.map((c) => `<option value="${esc(c.key)}" ${c.key === st.key ? "selected" : ""}>${esc(c.name)} · ${esc(c.class_name)} · ${esc(c.region)}</option>`).join("")}</select>
      <button class="btn primary" id="gadv">Run advice</button><span id="gmsg" class="small muted"></span></div>
      <p class="small faint">Import the character on My Character first. The official page shows only equipped items: add bag and warehouse items below so the planner can use them. Fights you import on Combat Logs are matched to the gear the character wore and calibrate the model.</p>` :
      '<div class="note">Import a character on My Character first.</div>'}
    <div id="ginv"></div></div></section><div id="gout"></div>`;
  if (!chars.length) return;
  const key = () => (st.key = $("#gchar").value);
  const showInv = async () => {
    const inv = await api("/api/inventory?character=" + encodeURIComponent(key()));
    st.inv = inv;
    const rows = inv.items.map((e) => `<tr><td>${esc(e.slot || e.category || "")}</td><td class="gname" data-grade="${esc(e.grade)}">${esc(e.name)} +${e.enchant || 0}</td>
      <td class="small">${esc((e.skills || []).map(([n, l]) => `${n} +${l}`).join(", "))}</td><td class="small muted">${esc(e.source)}</td>
      <td class="r">${e.source === "inventory" ? `<button class="btn small" data-rm="${esc(e.id)}">Remove</button>` : ""}</td></tr>`).join("");
    const genus = inv.genus || {};
    $("#ginv").innerHTML = `<h4 class="gold small" style="margin-top:12px">INVENTORY</h4>
      <table class="t"><tr><th>Slot</th><th>Item</th><th>Skill options</th><th>Source</th><th></th></tr>${rows}</table>
      <div class="row" style="margin-top:8px"><input id="gq" type="text" placeholder="search the catalog to add an item" style="width:280px"><button class="btn small" id="gsrch">Search</button>
        <input id="gen" type="number" min="0" max="20" value="0" style="width:70px" title="enchant level"><input id="gsk" type="text" placeholder="skill options, e.g. Hellfire=2, Blaze=1" style="width:260px"></div>
      <div id="gres"></div>
      <h4 class="gold small" style="margin-top:12px">GENUS INSIGHT</h4>
      <p class="small faint">One line per analysis slot: <code>Genus | level | slot | stat | value</code>, e.g. <code>Varian | 7 | 4 | Varian Damage Boost | 3.6%</code></p>
      <textarea id="ggen" rows="5" style="width:100%">${esc(Object.entries(genus).flatMap(([g, x]) => (x.lines || []).map((l) => `${g} | ${x.level || 0} | ${l.slot ?? ""} | ${l.stat} | ${l.value}`)).join("\n"))}</textarea>
      <button class="btn small" id="ggsave">Save genus lines</button>
      <h4 class="gold small" style="margin-top:12px">TITLES YOU OWN</h4>
      <p class="small faint">The official page shows only equipped titles. One title name per line (copy them from the in-game Titles window).</p>
      <textarea id="gtit" rows="4" style="width:100%">${esc((inv.titles_owned || []).join("\n"))}</textarea>
      <button class="btn small" id="gtsave">Save titles</button>`;
    $$("[data-rm]").forEach((b) => (b.onclick = async () => { await api("/api/inventory/remove", { character: key(), id: b.dataset.rm }); showInv(); }));
    $("#gsrch").onclick = async () => {
      const items = await api(`/api/items?search=${encodeURIComponent($("#gq").value)}&limit=30`);
      $("#gres").innerHTML = `<table class="t">${items.map((it) => `<tr><td class="gname" data-grade="${esc(it.grade)}">${esc(it.name)}</td><td>${esc(it.category)}</td><td class="r">${it.item_level ?? ""}</td>
        <td class="r"><button class="btn small" data-add="${esc(it.slug)}">Add</button></td></tr>`).join("")}</table>`;
      $$("[data-add]").forEach((b) => (b.onclick = async () => {
        const skills = $("#gsk").value.split(",").map((x) => x.trim()).filter(Boolean).map((x) => { const [n, l] = x.split("="); return [n.trim(), +(l || 1)]; });
        await api("/api/inventory/add", { character: key(), slug: b.dataset.add, enchant: +$("#gen").value, skills });
        toast("Added"); showInv();
      }));
    };
    $("#gtsave").onclick = async () => { await api("/api/inventory/titles", { character: key(), titles: $("#gtit").value.split("\n") }); toast("Saved"); showInv(); };
    $("#ggsave").onclick = async () => {
      const g = {};
      $("#ggen").value.split("\n").map((l) => l.split("|").map((x) => x.trim())).filter((p) => p.length >= 5 && p[3]).forEach(([gn, lv, slot, stat, value]) => {
        const x = (g[gn] = g[gn] || { level: +lv || 0, lines: [] });
        x.level = Math.max(x.level, +lv || 0);
        x.lines.push({ slot: +slot || null, stat, value });
      });
      await api("/api/inventory/genus", { character: key(), genus: g }); toast("Saved"); await showInv();
      if (st.adv) { $("#gout").innerHTML = renderAdvice(st.adv); bindAdvice(st.adv); }
    };
  };
  $("#gchar").onchange = () => { st.adv = null; $("#gout").innerHTML = ""; showInv(); };
  $("#gadv").onclick = async () => {
    $("#gout").innerHTML = '<div class="empty"><span class="spinner"></span></div>';
    try { st.adv = await runJob("/api/advice", { character: key() }, (l) => ($("#gmsg").textContent = l[l.length - 1] || "")); $("#gout").innerHTML = renderAdvice(st.adv); bindAdvice(st.adv); }
    catch (e) { $("#gout").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  };
  await showInv();
  if (st.adv) { $("#gout").innerHTML = renderAdvice(st.adv); bindAdvice(st.adv); }
}

const SKILL_ICON = (id) => (id ? "https://metabot.gg/web/aion2/skills/" + id + ".webp" : "");
const DOLL_LEFT = ["MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt"];
const DOLL_RIGHT = ["Necklace", "Earring1", "Earring2", "Ring1", "Ring2", "Bracelet1", "Bracelet2", "Amulet", "Rune1", "Rune2"];
const SLOT_NAME = { MainHand: "Main hand", SubHand: "Off-hand", Torso: "Chest", Pants: "Legs", Cape: "Cloak", Earring1: "Earring", Earring2: "Earring",
  Ring1: "Ring", Ring2: "Ring", Bracelet1: "Bracelet", Bracelet2: "Bracelet", Rune1: "Rune", Rune2: "Rune" };
const itemIcon = (it, cls = "") => `<div class="icon ${cls}" data-grade="${esc(it?.grade || "")}">${it?.icon ? `<img src="${icon(it.icon)}" alt="">` : ""}${it?.enchant ? `<span class="lv">+${it.enchant}</span>` : ""}</div>`;
function itemCard(it, label, gain, extra = "") {
  if (!it) return `<div class="icard empty"><div class="ilabel">${esc(label)}</div><div class="faint small">—</div></div>`;
  return `<div class="icard" data-grade="${esc(it.grade || "")}"><div class="ilabel">${esc(label)}</div>${itemIcon(it, "lg")}
    <div class="gname">${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.name)}</a>` : esc(it.name)}</div>
    <div class="small muted">${it.item_level ? "iLv " + it.item_level + " · " : ""}+${it.enchant || 0}</div>
    ${gain != null ? `<div class="gain ${gain >= 0 ? "up" : "down"}">${sp(gain)}</div>` : ""}${extra}</div>`;
}

function advDoll(a) {
  const d = a.doll;
  const tile = (slot) => {
    const x = d[slot] || {};
    const it = x.worn || x.wear || null;
    const up = x.wear ? x.wear_gain : null;
    const goal = x.next && x.next.gain > 0.02;
    return `<button class="dslot" data-dslot="${slot}" data-grade="${esc(it?.grade || "")}">${itemIcon(it, "sm")}
      <div class="dtxt"><div class="sl">${esc(SLOT_NAME[slot] || slot)}</div><div class="gname">${esc(it?.name || "empty")}</div></div>
      ${up ? `<span class="badge up" title="better item in your inventory">▲ ${sp(up)}</span>` : goal ? `<span class="badge goal" title="next goal">◆ ${sp(x.next.gain)}</span>` : ""}
      ${x.steps.length ? `<span class="badge step" title="upgrade path step">#${x.steps[0]}</span>` : ""}</button>`;
  };
  const arc = ["Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"];
  return win("Equipment", "click a slot: what you wear → better from your inventory → next goal → best in slot",
    `<div class="pdoll"><div class="dcol">${DOLL_LEFT.map(tile).join("")}</div>
      <div class="dcenter"><div class="cls">${esc(cap(a.character.class))}</div><div class="small">${esc(a.character.name)} · ${esc(a.character.server)}</div>
        <div class="dps">${n0(a.dps)}<small>boss DPS</small></div>
        <div class="legend2"><span class="badge up">▲</span> better item in your inventory<br><span class="badge goal">◆</span> next goal gain<br><span class="badge step">#</span> upgrade path step</div>
        <div class="arow">${arc.map((s) => { const it = d[s]?.worn; return `<button class="dslot mini" data-dslot="${s}" title="${esc(s)}">${itemIcon(it, "sm")}</button>`; }).join("")}</div></div>
      <div class="dcol">${DOLL_RIGHT.map(tile).join("")}</div></div><div id="dslotinfo" class="dinfo"></div>`,
    { key: "adv-equip", copy: Object.entries(d).filter(([, x]) => x.wear || x.next).map(([s, x]) => `${s}: ${x.wear ? "wear " + x.wear.name + " +" + x.wear.enchant + "; " : ""}${x.next ? "next goal " + x.next.name : ""}`).join("\n") });
}
function bindDoll(a) {
  const show = (slot) => {
    const x = a.doll[slot] || {};
    $$("[data-dslot]").forEach((b) => b.classList.toggle("on", b.dataset.dslot === slot));
    const chips = (it) => it ? `${(it.skills || []).map(([k, l]) => `<span class="chip gold">${esc(k)} +${l}</span>`).join("")}${(it.rolls || []).map((r) => `<span class="chip">${esc(Array.isArray(r) ? r.join(" ") : r)}</span>`).join("")}` : "";
    $("#dslotinfo").innerHTML = `<h4 class="gold small">${esc(SLOT_NAME[slot] || slot).toUpperCase()}</h4><div class="iflow">
      ${itemCard(x.worn, "Wearing", null, `<div>${chips(x.worn)}</div>`)}<div class="arr">➜</div>
      ${itemCard(x.wear, "From your inventory", x.wear_gain, `<div>${chips(x.wear)}</div>`)}<div class="arr">➜</div>
      ${itemCard(x.next, "Next goal", x.next?.gain)}<div class="arr">➜</div>${itemCard(x.best, "Best in slot", x.best?.gain)}</div>
      ${x.steps.length ? `<p class="small muted">Upgrade path steps for this slot: ${x.steps.map((n) => "#" + n).join(", ")}</p>` : ""}`;
  };
  $$("[data-dslot]").forEach((b) => (b.onclick = () => show(b.dataset.dslot)));
  const first = Object.keys(a.doll).find((s) => a.doll[s].wear) || Object.keys(a.doll).find((s) => a.doll[s].next) || "MainHand";
  show(first);
}

function advPath(a) {
  const steps = a.upgrade_path.steps;
  const kind = { enchant: "＋1", reroll: "⟳", replace: "⇄" };
  return win("Upgrade path", "one change at a time, biggest gain first, toward the next goals",
    `<div class="path">${steps.map((s) => `<div class="pstep" data-grade="${esc(s.item?.grade || "")}"><div class="pn">#${s.step}</div>
      <div class="sl">${esc(SLOT_NAME[s.slot] || s.slot)}</div>${itemIcon(s.item, "lg")}<span class="kind" title="${esc(s.kind || "")}">${kind[s.kind] || ""}</span>
      <div class="gname small">${esc(s.item?.name || "")}</div><div class="small faint">${esc(s.action)}</div>
      <div class="gain up">${sp(s.gain)}</div><div class="cum"><i style="width:${Math.min(100, 100 * s.total_gain / Math.max(0.0001, steps[steps.length - 1].total_gain))}%"></i><span>${sp(s.total_gain)}</span></div></div>`).join("")}</div>`,
    { key: "adv-path", copy: steps.map((s) => `${s.step}. ${s.slot}: ${s.action} (${sp(s.gain)})`).join("\n") });
}

function advArcana(a) {
  const order = ["Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"];
  const cards = order.filter((s) => a.arcana.slots[s]).map((slot) => {
    const x = a.arcana.slots[slot], v = x.variant || {};
    const prio = a.arcana.priority.indexOf(slot) + 1;
    const opts = Object.entries(x.ideal.skills).map(([k, lv]) => `<div class="sk" title="${esc(k)} +${lv}"><div class="icon sm"><img src="${icon(SKILL_ICON(x.skill_ids[k]))}" alt=""><span class="lv">+${lv}</span></div><div class="small">${esc(k)}</div></div>`).join("");
    const owned = x.owned.map((o) => `<div class="owned ${o.verdict === "keep" ? "ok" : "bad"}">${itemIcon(o, "xs")}<span class="small">${esc(o.name)} +${o.enchant}</span>
      <span class="small">${sp(o.gain)}</span><span class="chip ${o.verdict === "keep" ? "gold" : ""}">${o.verdict === "keep" ? "keep" : "replace"}</span></div>`).join("");
    return `<div class="acard" data-grade="${esc(v.grade || "Unique")}"><div class="t">${esc(slot.replace("Arcana ", ""))}<span class="prio">#${prio}</span></div>
      ${itemIcon({ ...v, enchant: 5 }, "xl")}<div class="gname">${esc(v.name || "")}</div>
      <div class="deity">${esc(v.deity || "")} +${v.points ?? ""}</div>
      <div class="sub">TARGET OPTIONS · UNIQUE +5</div><div class="opts">${opts}</div>
      <div class="vals"><span>ideal <b>${sp(x.ideal.gain)}</b></span><span>average <b>${sp(x.expected.unique_5)}</b></span></div>
      ${owned ? `<div class="sub">YOURS</div>${owned}` : ""}</div>`;
  }).join("");
  return win("Arcana", "variant per slot, the skill options to chase (icons = target levels), and your arcana", `<div class="acards">${cards}</div>`,
    { key: "adv-arcana", copy: order.filter((s) => a.arcana.slots[s]).map((s) => { const x = a.arcana.slots[s]; return `${s}: ${x.variant?.name} — ${Object.entries(x.ideal.skills).map(([k, l]) => k + " +" + l).join(", ")}`; }).join("\n") });
}

const LORDS = { "Destruction [Zikel]": ["Zikel", "#d9534f"], "Death [Triniel]": ["Triniel", "#9b59b6"], "Wisdom [Lumiel]": ["Lumiel", "#5bc0de"],
  "Time [Siel]": ["Siel", "#f0ad4e"], "Illusion [Kaisinel]": ["Kaisinel", "#8e7cc3"], "Justice [Nezekan]": ["Nezekan", "#e8cf8e"],
  "Freedom [Vaizel]": ["Vaizel", "#5cb85c"], "Life [Yustiel]": ["Yustiel", "#7fd6a8"], "Destiny [Marchutan]": ["Marchutan", "#c0a16b"], "Space [Israphel]": ["Israphel", "#6fa8dc"] };
const DEITY_FX = { "Destruction [Zikel]": "Attack, Perfect Resist", "Death [Triniel]": "Critical Hit, Regen Penetration", "Wisdom [Lumiel]": "Double chance, MP cost",
  "Time [Siel]": "Combat Speed, Double Resist", "Illusion [Kaisinel]": "Cooldown, Endurance Penetration", "Justice [Nezekan]": "Perfect chance, Defense",
  "Freedom [Vaizel]": "Accuracy, Evasion", "Life [Yustiel]": "HP, Regeneration", "Destiny [Marchutan]": "MP, Endurance", "Space [Israphel]": "Move Speed, Block" };
function advPantheon(a) {
  const p = a.pantheon;
  const mx = Math.max(...p.per_point.map((r) => r.gain_per_point), 1e-9);
  const tiles = Object.keys(LORDS).map((dname) => {
    const r = p.per_point.find((x) => x.deity === dname) || {};
    const [lord, col] = LORDS[dname];
    const best = dname === p.best;
    return `<div class="dtile ${best ? "best" : ""} ${r.field ? "" : "dim"}"><div class="sigil" style="--dc:${col}">${esc(lord[0])}</div>
      <div class="dn">${esc(dname.split(" [")[0])}</div><div class="lord">${esc(lord)}</div><div class="pts">${p.current[dname] ?? 0}</div>
      <div class="fx">${esc(DEITY_FX[dname])}</div><div class="bar"><i style="width:${Math.max(0, 100 * (r.gain_per_point || 0) / mx)}%"></i><span>${sp(10 * (r.gain_per_point || 0))} / 10</span></div>
      ${best ? '<span class="chip gold">best for damage</span>' : ""}</div>`;
  }).join("");
  const choices = p.choices.map((c) => `<div class="pchoice"><span class="muted small">${esc(c.source)}</span> <b>${esc(c.pick)}</b>${c.deity ? ` <span class="small">(${esc(c.deity)})</span>` : ""} <span class="gain up">${sp(c.gain)}</span></div>`).join("");
  return win("Pantheon", "deity stats: points you have, and what 10 more points are worth", `<div class="dtiles">${tiles}</div><div class="pchoices">${choices}</div>`,
    { key: "adv-pantheon", copy: p.per_point.map((r) => `${r.deity}: ${sp(10 * r.gain_per_point)} per 10`).join("\n") });
}

function advGenus(a, inv) {
  const g = a.genus, state = (inv && inv.genus) || {};
  const genera = ["Cogni", "Fera", "Natura", "Varian", "Special"];
  const S2 = S.gear;
  const cur = S2.genusTab || (g.level_order[0] && g.level_order[0].genus) || "Cogni";
  const st = state[cur] || { level: 0, lines: [] };
  const val = {};
  g.lines.filter((l) => l.genus === cur).forEach((l) => (val[l.slot] = l));
  const chase = g.chase.find((c) => c.genus === cur);
  const cells = Array.from({ length: 9 }, (_, i) => {
    const n = i + 1, line = (st.lines || []).find((l) => +l.slot === n), v = val[n];
    const locked = n > (st.level || 0);
    const special = n === 4 || n === 7;
    if (locked) return `<div class="gslot locked ${special ? "sp" : ""}"><div class="gn">${n}</div><div class="small faint">opens at Lv ${n}</div></div>`;
    if (!line) return `<div class="gslot ${special ? "sp" : ""}"><div class="gn">${n}</div><div class="small faint">${special && chase ? "chase: " + esc(chase.line) : "empty"}</div></div>`;
    const dead = v && v.gain <= 1e-6;
    return `<div class="gslot filled ${special ? "sp" : ""} ${dead ? "dead" : ""}"><div class="gn">${n}</div><div class="gst">${esc(line.stat)}</div><div class="gv">${esc(line.value)}</div>
      ${v ? `<div class="gain ${dead ? "down" : "up"}">${dead ? "no damage: reroll" : (v.gain < 0.001 ? "+" + (100 * v.gain).toFixed(2) + "%" : sp(v.gain))}</div>` : ""}</div>`;
  }).join("");
  const mix = Object.entries(g.mix).map(([k, v]) => `<span class="mixseg" style="flex:${v}" title="${esc(k)} ${pct(v, 0)}">${esc(k)} ${pct(v, 0)}</span>`).join("");
  return win("Genus Insight", "pet genus lines: slots 4 and 7 hold the genus damage line; lines are weighted by your fight time per genus",
    `<div class="tabs">${genera.map((x) => `<button data-gtab="${x}" class="${x === cur ? "on" : ""}">${x} <span class="faint">Lv ${(state[x] || {}).level || 0}</span></button>`).join("")}</div>
     <div class="gwrap"><div class="ggrid">${cells}</div><div class="gside"><h4 class="gold small">YOUR FIGHT TIME</h4><div class="mix">${mix}</div>
       ${chase ? `<h4 class="gold small">CHASE</h4><div>${esc(chase.line)} <span class="small muted">${esc(chase.value)}</span> <span class="gain up">${sp(chase.gain)}</span></div>` : ""}
       <h4 class="gold small">LEVEL ORDER</h4>${g.level_order.slice(0, 5).map((r, i) => `<div class="small">${i + 1}. ${esc(r.genus)} <span class="faint">Lv ${r.level} · ${pct(r.share, 0)} of fights${r.next ? ` · next opens slot ${r.next.opens_slot}` : ""}</span></div>`).join("")}</div></div>`,
    { key: "adv-genus", copy: g.lines.map((l) => `${l.genus} slot ${l.slot}: ${l.stat} ${l.value} (${sp(l.gain)})`).join("\n") });
}

function titlePlate(t, label, extra = "") {
  if (!t) return `<div class="tplate empty"><div class="ilabel">${esc(label)}</div><div class="faint small">—</div></div>`;
  return `<div class="tplate" data-grade="${esc(t.grade || "")}"><div class="ilabel">${esc(label)}</div>
    <div class="tname gname">❖ ${esc(t.name)} ❖</div><div class="small">${esc(t.equip || "")}</div>
    ${t.owned_bonus && t.owned_bonus !== "—" ? `<div class="small muted">owned: ${esc(t.owned_bonus)}</div>` : ""}
    ${t.gain != null && label !== "Equipped" ? `<div class="gain ${t.gain >= 0 ? "up" : "down"}">${sp(t.gain)}</div>` : ""}
    ${t.how ? `<div class="small faint" title="${esc(t.how)}">${esc(t.how.replace(/^You earn it by /, "").split(/\. How to get it/)[0].slice(0, 110))}</div>` : ""}${extra}</div>`;
}
function advTitles(a) {
  const t = a.titles;
  if (!t) return "";
  const cols = ["Attack", "Defense", "Etc"].map((slot) => { const x = t.slots[slot] || {};
    return `<div class="tcol"><div class="t">${slot === "Etc" ? "Other" : slot} title</div>${titlePlate(x.equipped, "Equipped")}
      ${t.owned_known ? titlePlate(x.best_owned, "Best you own") : ""}
      <div class="sub">BEST IN SLOT</div>${(x.best || []).length ? "" : '<div class="small faint">No title for this slot adds damage.</div>'}${(x.best || []).slice(0, 3).map((r, i) => titlePlate(r, i ? "" : "Best", r.owned ? '<span class="chip gold">owned</span>' : "")).join("")}</div>`; }).join("");
  const coll = t.collect.map((c) => titlePlate({ ...c, equip: "" }, "Collect", "")).join("");
  return win("Titles", "equip bonus per slot, and titles worth collecting for their owned bonus",
    `<div class="tcols">${cols}</div>${t.note ? `<p class="small faint">${esc(t.note)}</p>` : ""}
     ${coll ? `<h4 class="gold small" style="margin-top:12px">WORTH COLLECTING (owned bonus)</h4><div class="tcollect">${coll}</div>` : ""}`,
    { key: "adv-titles", copy: ["Attack", "Defense", "Etc"].map((s) => `${s}: ${(t.slots[s]?.best_owned || t.slots[s]?.best?.[0] || {}).name || "-"}`).join("\n") });
}

function advTop(a) {
  const ic = { titles: "❖", "gear (inventory)": "▲", "gear (upgrade)": "⇧", arcana: "✦", pantheon: "☉", "genus insight": "❖", rotation: "↻", specializations: "◎", community: "☷" };
  return win("Top changes", a.calibrated ? "ranked by simulated DPS gain · model calibrated from fights" : "ranked by simulated DPS gain",
    `<div class="tops">${a.top.map((r) => `<div class="top"><span class="ti">${ic[r.area] || "•"}</span><div><div class="small muted">${esc(r.area)}</div><div>${esc(r.text)}</div></div><div class="gain ${r.gain == null ? "" : "up"}">${r.gain == null ? "" : sp(r.gain)}</div></div>`).join("")}</div>
     <p class="small faint">Saved as <code>${esc(a.file || "")}</code></p>`, { key: "adv-top", copy: a.top.map((r) => `${r.area}: ${r.text} ${r.gain == null ? "" : sp(r.gain)}`).join("\n") });
}

function renderAdvice(a) {
  const r = a.rotation;
  const rot = r.fights ? `<p>${r.fights} fight(s), idle ${pct(r.idle_share, 0)} of the time.</p>${r.under_cast.slice(0, 6).map((t) => `<div class="tip">${esc(t.text)}</div>`).join("")}
    ${r.specs.map((d) => `<div class="tip">${esc(d.skill)}: specs ${esc(d.yours)} in your fights, ${esc(d.optimal)} in the optimized build</div>`).join("")}` : '<p class="muted">No saved fights for this character: import AbyssLogs links on Combat Logs.</p>';
  return advTop(a) + advDoll(a) + advPath(a) + advArcana(a) + advTitles(a) + advPantheon(a) + advGenus(a, S.gear.inv) +
    `<div class="grid2">${win("Your fights", "", rot)}${win("Model calibration", "learned from fights matched to equipped gear", a.calibration.map((x) => `<div class="small">${esc(x)}</div>`).join(""))}</div>`;
}
function bindAdvice(a) {
  bindDoll(a);
  $$("[data-gtab]").forEach((b) => (b.onclick = () => { S.gear.genusTab = b.dataset.gtab; $("#gout").innerHTML = renderAdvice(a); bindAdvice(a); }));
}

// ------------------------------------------------------------- theme & settings
const THEMES = ["system", "light", "dark"];
function getTheme() { try { return localStorage.getItem("theme") || "system"; } catch (e) { return "system"; } }
function setTheme(t) {
  try { localStorage.setItem("theme", t); } catch (e) {}
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  const b = $("#theme");
  if (b) { b.textContent = { system: "◐", light: "☀", dark: "☾" }[t]; b.title = `Theme: ${t === "system" ? "follow the computer" : t} (click to change)`; }
}
$("#theme").onclick = () => setTheme(THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length]);
setTheme(getTheme());

async function pageSettings() {
  const [s, srv, ui] = await Promise.all([api("/api/status"), api("/api/logserver").catch(() => ({})), api("/api/ui").catch(() => ({}))]);
  const t = getTheme();
  app().innerHTML = win("Settings", "", `
    <div class="setrow"><div class="lbl">Theme</div><div><div class="seg">${THEMES.map((x) => `<button data-th="${x}" class="${x === t ? "on" : ""}">${{ system: "Follow computer", light: "Light", dark: "Dark" }[x]}</button>`).join("")}</div></div></div>
    <div class="setrow"><div class="lbl">Open as its own window</div><div><label><input type="checkbox" id="appwin" ${ui.app_window !== false ? "checked" : ""}> start in a separate app window (Edge or Chrome) instead of a browser tab; closing it stops the app</label></div></div>
    <div class="setrow"><div class="lbl">Your data</div><div><code>${esc(s.home)}</code> <button class="btn small" data-open="data">Open folder</button> <button class="btn small" data-open="logs">Combat logs</button> <button class="btn small" data-open="results">Advice &amp; results</button></div></div>
    <div class="setrow"><div class="lbl">Log server</div><div class="row"><input id="surl" type="text" placeholder="${srv.is_default && srv.url ? esc(srv.url) + " (default)" : "https://logs.example.com"}" value="${srv.is_default ? "" : esc(srv.url || "")}" style="width:280px">
      <input id="skey" type="password" placeholder="${srv.has_key ? "key saved" : "upload key (optional)"}" style="width:200px">
      <select id="svis">${["unlisted", "public", "private"].map((v) => `<option ${v === (srv.visibility || "unlisted") ? "selected" : ""}>${v}</option>`).join("")}</select>
      <button class="btn small" id="ssave">Save</button><span id="smsg" class="small muted"></span></div>
      ${srv.is_default && srv.url ? '<div class="small muted" style="margin-top:4px">Using the community default server. Enter your own above to override it.</div>' : ""}</div></div>
    <div class="setrow"><div class="lbl">Game database</div><div>${n0(s.db.items)} items · last update ${s.db.last_sync ? new Date(s.db.last_sync.at * 1000).toLocaleString() : "never"} <button class="btn small" id="sync">Check now</button></div></div>
    <div class="setrow"><div class="lbl">Updates</div><div><label><input type="checkbox" id="autoupd" ${ui.auto_update !== false ? "checked" : ""}> install new versions automatically on launch</label></div></div>
    <div class="setrow"><div class="lbl">Version</div><div>aion2calc ${esc(s.version)} ${s.update ? `· version ${esc(s.update.version)} available <button class="btn small" id="instupd">Install now</button> <a href="${esc(s.update.url)}" target="_blank" rel="noopener">release notes</a>` : '<span class="muted">· up to date</span>'} <span id="updmsg" class="small muted"></span></div></div>
    <div class="setrow"><div class="lbl">Community</div><div><a href="${DISCORD}" target="_blank" rel="noopener">Join the aion2calc Discord</a> — questions, builds and help</div></div>
    <div class="setrow"><div class="lbl">Stop the app</div><div><button class="btn small" id="quit2">Quit aion2calc</button></div></div>
    <div class="setrow" style="border-top:1px solid var(--line);margin-top:8px;padding-top:10px"><div class="lbl">Author</div><div class="muted">Spirited - Zikel : Asmodian&nbsp;&nbsp;|&nbsp;&nbsp;Legion: WhaleWatch</div></div>`);
  $$("[data-th]").forEach((b) => (b.onclick = () => { setTheme(b.dataset.th); pageSettings(); }));
  $("#appwin").onchange = () => api("/api/ui", { app_window: $("#appwin").checked }).then(() => toast("Saved"));
  $("#autoupd").onchange = () => api("/api/ui", { auto_update: $("#autoupd").checked }).then(() => toast("Saved"));
  if ($("#instupd")) $("#instupd").onclick = async () => {
    $("#updmsg").textContent = "downloading…";
    try {
      const r = await api("/api/update", {});
      $("#updmsg").textContent = { applying: "installing — the app will restart", downloaded: "downloaded — open your data folder's 'updates' to apply", "download-failed": "download failed", "up-to-date": "already up to date" }[r.status] || r.status;
    } catch (e) { $("#updmsg").textContent = e.message; }
  };
  $$("[data-open]").forEach((b) => (b.onclick = () => api("/api/open", { what: b.dataset.open }).catch((e) => toast(e.message))));
  $("#ssave").onclick = async () => {
    await api("/api/logserver", { url: $("#surl").value, key: $("#skey").value || null, visibility: $("#svis").value });
    try { const r = await fetch($("#surl").value.replace(/\/$/, "") + "/.well-known/a2log.json"); $("#smsg").textContent = r.ok ? "saved · server reachable" : "saved · server did not answer"; }
    catch (e) { $("#smsg").textContent = "saved · server not reachable from this computer"; }
  };
  $("#sync").onclick = async () => { await api("/api/sync", {}); toast("Checking for game updates"); };
  $("#quit2").onclick = () => $("#quit").click();
}
setInterval(() => fetch("/api/ping", { method: "POST" }).catch(() => {}), 20000);

// ------------------------------------------------------------- router
async function route() {
  const page = (location.hash.replace(/^#\//, "") || "planner").split("/")[0];
  $$(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  try {
    if (page === "character") await pageCharacter();
    else if (page === "gear") await pageGear();
    else if (page === "settings") await pageSettings();
    else if (page === "combat") await pageCombat();
    else if (page === "raid") await pageRaid();
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
    const up = $("#update");
    if (s.update && up) { up.hidden = false; up.href = s.update.url; up.textContent = `Version ${s.update.version} available`; }
    $("#quit").title = `Stop the app (version ${s.version || ""})`;
    setTimeout(syncPill, running ? 2500 : 20000);
  } catch (e) { setTimeout(syncPill, 20000); }
}
$("#quit").onclick = async () => {
  if (!confirm("Stop aion2calc? Start it again from the Start menu or desktop shortcut.")) return;
  await api("/api/quit", {}).catch(() => {});
  document.body.innerHTML = '<div class="empty" style="margin-top:20vh">aion2calc has stopped. You can close this tab.</div>';
};
route();
syncPill();
