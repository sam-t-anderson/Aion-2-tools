/* aion2calc front end — vanilla JS, no build step. */
"use strict";

// ------------------------------------------------------------------ helpers
const DISCORD = "https://discord.gg/9y6zkUyvBv";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
const icon = u => {const source=u?"/api/icon?u="+encodeURIComponent(u.startsWith("/")?"https://metabot.gg"+u:u):"";return window.A2AssetHealth?A2AssetHealth.source(source):source;};
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
function toast(msg, duration = 4000) {
  const d = document.createElement("div");
  d.setAttribute("role", "status");
  d.textContent = msg;
  Object.assign(d.style, { position: "fixed", bottom: "20px", left: "50%", transform: "translateX(-50%)", background: "#1c2438",
    border: "1px solid rgba(233,203,128,.6)", padding: "8px 16px", borderRadius: "6px", zIndex: 99, color: "#e8cf8e" });
  document.body.appendChild(d);
  setTimeout(() => d.remove(), duration);
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
      <div class="skill-overview"><div class="skill-heading">
        <div class="icon"><img src="${icon(s.icon)}" alt="" loading="lazy"><span class="lv">Lv${s.eff}</span></div>
        <div class="skill-title"><div class="nm">${esc(s.name)}</div>
          <div class="lvl"><b>Lv ${s.eff}</b> = SP ${s.sp} + Daevanion ${s.daev}${s.gear ? ` + gear ${s.gear}` : ""}</div></div>
      </div>${s.specs.length?`<p class="skill-slot-summary small muted">${esc(s.slots)} selection slot(s)<br>${chosen.length} recommended${s.next_effect_level?`<br>Next effect at Lv ${esc(s.next_effect_level)}`:''}</p>`:''}</div>
      ${s.specs.length?`<div class="specs" role="list" aria-label="Supporting effects for ${esc(s.name)}">${s.specs.map(x=>`<div class="skill-effect" role="listitem"><span class="spec ${x.chosen?'on':x.available?'av':''}" title="${esc(x.chosen?'Recommended':x.available?'Available':'Locked')}">${esc(x.n)}</span><div class="skill-effect-text">${esc(x.name||x.text)}<small class="${x.chosen?'effect-recommended':'faint'}">Lv ${esc(x.unlock)} · ${x.chosen?'Recommended':x.available?'Available':'Locked'}</small></div></div>`).join('')}</div>`:''}
    </div>`;
  }).join("");
  const copy = (v.skills.active.concat(v.skills.passive)).filter((s) => s.sp > 1 || s.specs.some((x) => x.chosen))
    .map((s) => `${s.name}: train to ${s.sp} (Lv ${s.eff})${s.specs.some((x) => x.chosen) ? " — specialties " + s.specs.filter((x) => x.chosen).map((x) => `${x.n}: ${x.text} (effect Lv ${esc(x.unlock)})`).join("; ") : ""}`).join("\n");
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
      style="grid-row:${nd.row};grid-column:${nd.col}" title="${esc(tip)}">${nd.type==="SkillLevel" && Number.isSafeInteger(+nd.skill_id) && +nd.skill_id>0?`<img class="node-skill-icon" src="${esc(icon("https://metabot.gg/web/aion2/skills/"+nd.skill_id+".webp"))}" alt="${esc(nd.skill||"Skill")}" loading="lazy" onerror="this.hidden=true">`:""}<span>${txt}</span></div>`;
  }).join("");
  const tabs = `<div class="tabs">${d.boards.map((x, i) => `<button data-board="${i}" class="${i === boardIdx ? "on" : ""}">${esc(x.name)} <span class="faint">${x.used}/${x.total}</span></button>`).join("")}</div>`;
  const side = `<div class="daevside">
      <div class="counter"><small>Points used</small> ${d.used} / ${d.budget ?? "Unknown"}</div>
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
      <div class="icon sm with-fallback"><span class="asset-placeholder" aria-hidden="true">◇</span>${s.icon ? `<img src="${icon(s.icon)}" alt="${esc(s.item || s.name || s.slot)}" loading="lazy" onerror="this.hidden=true">` : ""}${s.enchant ? `<span class="lv">+${s.enchant}</span>` : ""}</div>
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
  return win("Equipment", v.equipment_source || (v.name ? "current gear (official profile)" : "loadout used for this build"),
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

function rotationIcon(s) {
  return `<div class="hotbar-icon">${s.icon ? `<img src="${esc(icon(s.icon))}" alt="" onerror="this.hidden=true">` : ""}<b class="hotbar-key">${esc(s.binding || "")}</b><span class="hotbar-level">Lv ${n0(s.level)}</span></div>`;
}
function winHotbar(v) {
  const h = v.hotbar;
  if (!h) return win("Skills hotbar", "", '<div class="empty">Optimize your build to generate its hotbar and macro setup.</div>');
  const rows = [];
  const total = Math.max(12, Math.ceil(h.slots.length / 12) * 12);
  for (let first = 0; first < total; first += 12) {
    rows.push(`<div class="hotbar-row"><span class="hotbar-row-label">${first / 12}</span>${Array.from({ length: 12 }, (_, i) => {
      const s = h.slots[first + i];
      return s ? `<div class="hotbar-slot ${s.manual ? "manual" : "automatic"}" title="${esc(s.name)} — ${s.manual ? "Manual" : "Macro"}${s.charged ? "; hold to charge" : ""}">
        ${rotationIcon(s)}<span class="hotbar-name">${esc(s.name)}</span><small>${s.charged ? "Hold to charge" : s.manual ? "Manual" : "Macro"}</small></div>` : '<div class="hotbar-slot empty-slot"><span>+</span></div>';
    }).join("")}</div>`);
  }
  const copy = h.slots.map((s) => `${s.binding}: ${s.name} (${s.charged ? "manual hold to charge" : s.manual ? "manual" : "macro"})`).join("\n") + `\nSuggested macro key: ${h.macro_binding}`;
  return win("Skills hotbar", "suggested key bindings", `<p>Place each skill on your hotbar and assign the key shown on its icon. These are suggested bindings: match your in-game Key Settings, or use your own keys consistently in both tabs.</p>
    <div class="hotbar-wrap">${rows.reverse().join("")}</div>
    <p><b class="gold">Manual / Hold to charge:</b> keep these skills outside the macro. Hold a charge skill’s own key, then release it at the required charge level.</p>
    <p>Reserve <kbd>${esc(h.macro_binding)}</kbd> for the macro, then follow <b>Macro &amp; rotation</b>. Hotbar positions are key bindings; the numbered macro rows are the order the macro tries skills.</p>`, { key: "hotbar", copy });
}
function winMacro(v) {
  const m = v.macro, r = v.rotation;
  if (!m || !r) return win("Skill Macro", "", '<div class="empty">No macro (run an optimization)</div>');
  const manual = r.manual.map((s) => `<div class="manual-skill">${rotationIcon(s)}<div><b>${esc(s.name)}</b><div class="small muted">${s.charged ? `Hold this skill’s key${s.charge_level ? ` to charge level ${s.charge_level}` : " to charge"}, then release. Never add it as a macro tap.` : "Press manually when ready."}${s.condition ? ` Use ${esc(s.condition)}.` : ""}</div></div></div>`).join("");
  const steps = r.steps.map((s, i) => `<div class="macro-step"><strong class="macro-number">${i + 1}</strong><div>${rotationIcon(s)}<b>${esc(s.name)}</b></div><span class="macro-key-label">Hotbar key <kbd>${esc(s.binding)}</kbd></span></div>
    ${i < r.steps.length - 1 ? '<div class="macro-delay"><span></span>Delay <b>10</b> ms<span></span></div>' : ""}`).join("");
  const copy = r.steps.map((s, i) => `${i + 1}. ${s.name} — hotbar key ${s.binding}; delay 10 ms`).join("\n") +
    (r.manual.length ? "\nManual: " + r.manual.map((s) => `${s.name} (${s.binding}${s.charged ? "; hold to charge" : ""})`).join(", ") : "");
  const body = `<ol class="macro-instructions"><li>Copy the suggested bindings from <b>Skills hotbar</b>, or substitute your own.</li>
    <li>Open <b>Settings → Key Settings → General → Skill Macro</b>. Add the skills below once each, from top to bottom. The large numbers are macro steps, not hotbar keys.</li>
    <li>Set each step’s delay to <b>10 ms</b>, enable <b>Skill Queue</b>, and save the macro to an unused key (suggested: <kbd>${esc(v.hotbar?.macro_binding || "Right-click")}</kbd>).</li>
    <li>Hold the macro key during combat. Release it to use a manual skill; charge skills need their own button held before release. Resume the macro afterwards.</li></ol>
    <div class="macro-layout"><div class="macro-editor"><h3>Macro</h3>${steps || '<p class="muted">This rotation uses manual skills only.</p>'}<div class="macro-save">Save to ${esc(v.hotbar?.macro_binding || "Right-click")} in game</div></div>
    <div><h4 class="gold">MANUAL SKILLS</h4>${manual || '<p class="muted">No manual skills for this rotation.</p>'}
    <p class="small muted">${m.needs_refresh ? "This saved build predates charge-aware macros. Charged skills have been moved to manual controls; optimize again to recalculate the macro estimate." : `Estimated macro + manual execution: ${pct(m.dps_macro / m.dps_priority)} of the ideal priority rotation. This assumes you use the manual skills, including their charges.`}</p>
    <h4 class="gold small">WHEN MULTIPLE SKILLS ARE READY</h4><p class="small muted">This priority list explains the optimizer’s decisions. It is not another macro to copy.</p><ol>${r.priority.map((s) => `<li>${esc(s.name)}${s.condition ? ` <span class="muted">(${esc(s.condition)})</span>` : ""}</li>`).join("")}</ol></div></div>`;
  return win("Skill Macro & rotation", "", body, { key: "macro", copy });
}

function survivalSummary(plan) {
  if(!plan)return '';
  return `<section class="note"><h3>HP reserve · constrained damage optimization</h3><p>Crystal-board flat HP: <b>${n0(plan.selected_node_hp)}</b> · requested floor: ${n0(plan.minimum_node_hp)} · previous contribution: ${n0(plan.reference_node_hp)}. ${plan.meets_node_floor?'Reserve met.':'Reserve not met.'}</p>
    ${plan.estimated_total_hp_proxy!=null?`<p>Estimated total HP proxy: ${n0(plan.estimated_total_hp_proxy)} · worst assumed headroom: ${plan.worst_headroom_hp==null?'Not assessed':n0(plan.worst_headroom_hp)}</p>`:''}
    ${plan.opponents?.length?`<div class="cr-scroll"><table class="t"><tr><th>Assumed encounter / opponent</th><th>Hit + pressure + reserve</th><th>HP headroom (proxy)</th></tr>${plan.opponents.map(row=>`<tr><td>${esc(row.name)}<br><small>User assumption · ${row.window_s}s window</small></td><td>${n0(row.required_hp)}</td><td>${n0(row.headroom_hp)} · ${row.meets_assumed_pressure?'Meets assumed HP requirement':'Below requirement'}</td></tr>`).join('')}</table></div>`:''}
    <p class="small muted">${esc(plan.note)}</p><p class="small muted">DPS is maximized subject to this HP floor. These personal constraints are not compared against damage-only community presets.</p></section>`;
}
function skillReserveSummary(plan) {
  if(!plan)return '';
  return `<section class="note"><h3>Trained skill reserves · ${plan.met?'met':'not met'}</h3><table class="t"><tr><th>Skill</th><th>Minimum</th><th>Selected</th></tr>${plan.skills.map(row=>`<tr><td>${esc(row.name)}</td><td>${row.minimum}</td><td>${row.selected}</td></tr>`).join('')}</table><p class="small muted">${esc(plan.note)}</p></section>`;
}
function mountSkillReserves(root,key,v) {
  let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')||{};}catch(_){}
  const rows=[...(v.skills?.active||[]),...(v.skills?.passive||[])].map(row=>({...row,field:'sp',level:row.sp,max:row.buy_max||10})).concat((v.stigmas||[]).map(row=>({...row,field:'stigmas',max:20})));
  root.innerHTML=`<details><summary>Retain trained skills and equipped stigmas</summary><p class="small muted">Optional minimums for skills you rely on for defense, control or movement. Applies to both PvE and PvP. Damage is optimized within these constraints. Bonuses and specialties may change; effective-level unlocks are not locked. Use utility skills manually when absent from the rotation. This does not simulate defensive skill use, crowd control, movement or opponent matchups.</p><div class="cr-scroll"><table class="t"><tr><th>Retain</th><th>Skill</th><th>Minimum trained level</th></tr>${rows.map(row=>`<tr data-reserve-row data-field="${row.field}" data-id="${row.id}"><td><input type="checkbox" data-reserve-enable aria-label="Retain ${esc(row.name)}" ${saved[row.field]?.[row.id]?'checked':''}></td><td>${esc(row.name)}${row.field==='stigmas'?' · keep equipped':''}</td><td><input type="number" data-reserve-level aria-label="Minimum ${esc(row.name)} level" min="1" max="${row.max}" value="${Math.max(1,Math.min(row.max,Number(saved[row.field]?.[row.id]||row.level||1)))}" style="width:80px"></td></tr>`).join('')}</table></div></details>`;
  function read(){const plan={sp:{},stigmas:{}};root.querySelectorAll('[data-reserve-row]').forEach(row=>{const enable=row.querySelector('[data-reserve-enable]'),input=row.querySelector('[data-reserve-level]');input.disabled=!enable.checked;if(enable.checked){if(!input.checkValidity())throw new Error('Reserve levels must be whole numbers within the shown range.');plan[row.dataset.field][row.dataset.id]=Number(input.value);}});return plan;}
  function save(){const plan=read();try{localStorage.setItem(key,JSON.stringify(plan));}catch(e){toast('Could not save skill reserves: '+e.message);}return plan;}
  root.onchange=()=>{try{save();}catch(e){toast(e.message);}};read();return {read:save};
}
function mountSurvivalOptions(root,key) {
  let settings={preserve_hp:true,min_node_hp:0,current_hp:null,opponents:[]};
  try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved && typeof saved==='object')settings={...settings,...saved,opponents:Array.isArray(saved.opponents)?saved.opponents.slice(0,8):[]};}catch(_){}
  const read=()=>{settings={preserve_hp:root.querySelector('[data-preserve-hp]').checked,min_node_hp:Number(root.querySelector('[data-hp-floor]').value),current_hp:root.querySelector('[data-current-hp]').value===''?null:Number(root.querySelector('[data-current-hp]').value),
    opponents:[...root.querySelectorAll('[data-pressure-row]')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-pressure]')].map(input=>[input.dataset.pressure,input.dataset.pressure==='name'?input.value:Number(input.value)])))};return settings;};
  const save=()=>{read();try{localStorage.setItem(key,JSON.stringify(settings));}catch(e){toast('Could not save survival options: '+e.message);}return settings;};
  function render(){root.innerHTML=`<details><summary>Survivability · preserve HP while optimizing damage</summary><p class="small muted">Protects flat HP from crystal-board nodes. It does not model armor, defensive skills or CC. Incoming scenarios are optional manual assumptions, not decoded boss mechanics or actual opponent simulations.</p>
    <div class="row"><label><input type="checkbox" data-preserve-hp ${settings.preserve_hp?'checked':''}> Preserve current crystal-board HP</label><label>Minimum crystal-board HP <input data-hp-floor type="number" min="0" max="1000000000" value="${esc(settings.min_node_hp)}"></label><label>Current in-game maximum HP (for scenarios) <input data-current-hp type="number" min="1" max="1000000000" value="${esc(settings.current_hp??'')}" placeholder="Optional"></label></div>
    <p class="small muted">Use hits and incoming DPS after your mitigation. The requirement is one hit plus net pressure over the selected window plus a positive HP reserve. Healing is treated as sustained, never as a shield against the first hit. Total HP uses only a flat node-delta proxy; verify the result in game.</p>
    <div class="cr-scroll"><table class="t"><tr><th>Encounter / opponent</th><th>Hit damage</th><th>Incoming DPS</th><th>Seconds</th><th>Assumed HPS</th><th>HP reserve</th><th></th></tr>${settings.opponents.map((row,index)=>`<tr data-pressure-row><td><input data-pressure="name" maxlength="100" value="${esc(row.name||'Incoming pressure')}"></td>${[['burst_damage',0],['pressure_dps',0],['window_s',5],['healing_hps',0],['reserve_hp',1]].map(([field,fallback])=>`<td><input data-pressure="${field}" aria-label="${field.replaceAll('_',' ')}" type="number" min="${field==='window_s'?'.1':field==='reserve_hp'?'1':'0'}" max="${field==='window_s'?'120':'1000000000'}" step="any" value="${esc(row[field]??fallback)}" style="width:95px"></td>`).join('')}<td><button class="btn small" data-remove-pressure="${index}">Remove</button></td></tr>`).join('')}</table></div>
    <button class="btn small" data-add-pressure ${settings.opponents.length>=8?'disabled':''}>Add encounter / opponent scenario</button><p class="small muted">Up to eight scenarios; the strictest HP requirement constrains the build. For PvP, enter different burst/pressure opponents. Optimized opponent profiles, matchup damage, crowd control, mobility and win chances are still future work.</p></details>`;
    root.onchange=save;
    root.querySelector('[data-add-pressure]').onclick=()=>{save();settings.opponents.push({name:'Pressure '+(settings.opponents.length+1),burst_damage:0,pressure_dps:0,window_s:5,healing_hps:0,reserve_hp:1});saveState();render();};
    root.querySelectorAll('[data-remove-pressure]').forEach(button=>button.onclick=()=>{save();settings.opponents.splice(Number(button.dataset.removePressure),1);saveState();render();});
  }
  function saveState(){try{localStorage.setItem(key,JSON.stringify(settings));}catch(e){toast('Could not save survival options: '+e.message);}}
  render();return {read:save};
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
  return win("Overview", esc(v.loadout_name || ""), kpis + (v.scoring_policy ? `<div class="note">${v.preset_source==='community'?'Community':'Common comparison'} ${esc((v.scoring_policy.mode||'').toUpperCase())} preset · ${n0(v.score)} weighted modeled DPS<br><span class="small">Equal weighting of ${v.scoring_policy.mode==='pvp'?'sustained and burst player-target damage':'boss and training-dummy damage'}. Common gear and comparison point budgets. ${v.preset_checked_at?'Last checked '+esc(new Date(v.preset_checked_at*1000).toLocaleString()):''}</span><details><summary>Comparison assumptions</summary>${esc(v.scoring_policy.note)}<br>Evaluator ${esc(v.scoring_policy.model)}${v.candidate_generation?`<br>Candidate search: ${esc(v.candidate_generation.objective)} · ${esc(v.candidate_generation.iterations)} iteration(s). Selected by the common weighted score; not a global optimum.`:""}</details></div>` : '') + (v.model_note?`<p class="small muted">${esc(v.model_note)}</p>`:'') + survivalSummary(v.survival) + skillReserveSummary(v.skill_reserves) + `<div class="grid2" style="margin-top:14px"><div><h4 class="gold small">STAT PRIORITY (DPS PER UPGRADE)</h4><table class="t">${w}</table></div>
     <div><h4 class="gold small">DAMAGE SHARE</h4><table class="t">${sh}</table></div></div>`, { key: "overview" });
}

function winGenus(v) {
  const g=v.genus;
  if(!g)return win('Pet Genus Insight','', '<p class="muted">This result has no Genus snapshot. Save your lines in My Character or Gear &amp; Advice, then optimize again.</p>');
  const rows=(g.lines||[]).map(x=>`<tr><td>${esc(x.genus)} · ${esc(x.slot)}</td><td>${esc(x.stat)}</td><td>${esc(x.value)}</td><td>${x.gain==null?'—':(100*x.gain).toFixed(2)+'%'}</td><td>${esc(x.reason||'Included in the damage model')}</td></tr>`).join('');
  const levels=Object.entries(g.state||{}).map(([k,x])=>`${esc(k)} Lv ${esc(x.level)}`).join(' · ');
  const mix=Object.entries(g.mix||{}).map(([k,x])=>`${esc(k)} ${(x*100).toFixed(1)}%`).join(' · ');
  return win('Pet Genus Insight',esc((g.mode||'').toUpperCase()), `<p>${g.enabled?'Saved manual lines included':'Genus scoring disabled for this run'}</p><p class="small muted">${esc(g.note)}</p><p>${levels}</p>${mix?`<p>${esc(g.mix_source)}: ${mix}</p>`:''}<div class="tablewrap"><table class="t"><tr><th>Genus · slot</th><th>Analysis line</th><th>Value</th><th>DPS contribution</th><th>Model status</th></tr>${rows||'<tr><td colspan="5">No saved lines were used.</td></tr>'}</table></div><p class="small muted">Review low-contribution lines for this mode first. This does not predict reroll cost or guarantee a better obtainable roll. Levels and slots are preserved exactly as entered.</p>`);
}

function mountCharacterGenus(root,key) {
  let editor=null,ready=false;
  const prefKey='character-genus-options:'+key;
  let saved={};try{saved=JSON.parse(localStorage.getItem(prefKey)||'{}');}catch(_){}
  root.innerHTML=`<details><summary>Pet Genus Insight · PvE and PvP</summary><p class="small muted">Use the saved analysis lines from this character's Gear &amp; Advice inventory. Save edits before optimizing. Current-build and optimized scores use identical lines; Genus rolls are held fixed.</p><label><input type="checkbox" data-use-genus ${saved.enabled===false?'':'checked'}> Include saved Genus lines</label><p class="small muted">PvE enemy mix (relative weights; default equal). PvP ignores this mix and excludes genus-specific effects whose applicability to players is unverified.</p><div class="row">${['Cogni','Fera','Natura','Varian','Special'].map(g=>`<label>${g} <input data-genus-mix="${g}" type="number" min="0" max="100" step="any" value="${esc(saved.mix?.[g]??(g==='Special'?0:25))}" style="width:75px"></label>`).join('')}</div><div data-character-genus-editor role="status">Loading saved lines…</div></details>`;
  const host=root.querySelector('[data-character-genus-editor]');
  api('/api/inventory?character='+encodeURIComponent(key)).then(inv=>{
    if(!root.isConnected)return;
    editor=A2GenusEditor.mount(host,inv.genus||{},async draft=>{
      const result=await api('/api/inventory/genus',{character:key,genus:draft});
      return result.genus||{};
    });ready=true;
  }).catch(e=>{if(root.isConnected)host.textContent='Could not load Genus: '+e.message;});
  return {read(mode){
    const enabled=root.querySelector('[data-use-genus]').checked;
    if(enabled&&(!ready||editor?.isDirty()))throw Error(ready?'Save your Genus edits before optimizing.':'Wait for Genus lines to load, or disable Genus scoring.');
    const mix=Object.fromEntries([...root.querySelectorAll('[data-genus-mix]')].map(e=>[e.dataset.genusMix,Number(e.value)]));
    if(mode==='pve'&&enabled&&(Object.values(mix).some(x=>!Number.isFinite(x)||x<0||x>100)||!Object.values(mix).some(x=>x>0)))throw Error('Set a positive PvE Genus mix using weights from 0 to 100.');
    localStorage.setItem(prefKey,JSON.stringify({enabled,mix}));
    return mode==='pvp'||!enabled?{enabled}:{enabled,mix};
  }};
}

const WINDOWS = [
  ["overview", "Overview", "◆"], ["skills", "Skills", "✦"], ["stigma", "Stigma", "⬢"], ["daevanion", "Daevanion", "✧"],
  ["genus", "Pet Genus", "◈"], ["equipment", "Equipment", "⚔"], ["arcana", "Arcana", "❖"], ["titles", "Titles & wings", "♛"], ["hotbar", "Skills hotbar", "▦"], ["macro", "Macro & rotation", "⌨"],
];
function renderCommonComparisons() {
  document.querySelectorAll('[data-common-comparison]').forEach(root=>{
    const cls=root.dataset.commonClass, mode=root.dataset.commonMode, key=cls+':'+mode;
    const state=S.commonComparisons[key], running=state?.status==='running';
    const result=state?.result, submission=result?.submission;
    let message=state?.message||'';
    if(result) message=`${result.reused?'Saved comparison reused':'Comparison saved'} · ${n0(result.score)} weighted modeled DPS (${result.model}). `+(submission?.reason||(submission?.accepted?'Community preset updated.':'Current community preset retained.'));
    root.innerHTML=`<button class="btn small" data-common-start ${running?'disabled':''}>${running?'Calculating…':result?'Resubmit saved comparison':'Generate community comparison'}</button><p class="small ${submission?.accepted?'good':'muted'}" role="status">${esc(message)}</p>${result?`<div class="small muted">${Object.entries(result.dps||{}).map(([name,value])=>esc(name)+': '+n0(value)+' modeled DPS').join(' · ')}${submission?.candidate_score!=null?'<br>Server evaluation: '+n0(submission.candidate_score)+' weighted modeled DPS (server policy).':''}</div>`:''}`;
    root.querySelector('[data-common-start]').onclick=async()=>{
      S.commonComparisons[key]={status:'running',message:'Starting a separate common-budget calculation…'};renderCommonComparisons();
      try {
        const {job}=await api('/api/planner/presets/contribute',{class:cls,mode});
        for(;;){
          await new Promise(resolve=>setTimeout(resolve,1200));
          const next=await api('/api/jobs/'+job);
          S.commonComparisons[key]={status:next.status,message:next.log?.at(-1)||'Waiting for the calculation…',result:next.result};
          renderCommonComparisons();
          if(next.status==='error')throw Error(next.error);
          if(next.status==='done')break;
        }
      } catch(error){S.commonComparisons[key]={status:'error',message:error.message};renderCommonComparisons();}
    };
  });
}

function renderWindows(v, state, host) {
  const side = `<section class="win sidemenu"><div class="wb">${WINDOWS.map(([k, t, ic]) => `<a href="javascript:void 0" data-win="${k}" class="${state.win === k ? "on" : ""}"><span class="ic">${ic}</span>${t}</a>`).join("")}</div></section>`;
  let body = "";
  switch (state.win) {
    case "skills": body = winSkills(v, state.skilltab || "active"); break;
    case "stigma": body = winStigmas(v); break;
    case "daevanion": body = winDaevanion(v, state.board || 0); break;
    case "genus": body = winGenus(v); break;
    case "equipment": body = winEquipment(v); break;
    case "arcana": body = winArcana(v); break;
    case "titles": body = winTitles(v); break;
    case "hotbar": body = winHotbar(v); break;
    case "macro": body = winMacro(v); break;
    default: body = winOverview(v);
  }
  const comparison=(state.win||'overview')==='overview'?`<section class="win" style="margin-top:12px"><div class="wb"><details><summary>Contribute a community comparison</summary><p class="small muted">Generate a separate ${String(v.scenario||'').startsWith('pvp')?'PvP':'PvE'} example with common gear and 203 Skill / 30 Stigma / 360 crystal Daevanion points. Your personal build, Genus and HP/skill reserves stay saved separately. Two searches can take several minutes; completed comparisons are reused until the scoring inputs change. Only anonymous allocations are submitted. Stationary damage comparison, not a survival or win-rate model.</p><div data-common-comparison></div></details></div></section>`:'';
  host.innerHTML = `<div class="layout"><div>${side}</div><div>${body}${comparison}</div></div>`;
  const common=host.querySelector('[data-common-comparison]');
  if(common){common.dataset.commonClass=v.class;common.dataset.commonMode=String(v.scenario||'').startsWith('pvp')?'pvp':'pve';renderCommonComparisons();}
  $$("[data-win]", host).forEach((a) => (a.onclick = () => { state.win = a.dataset.win; renderWindows(v, state, host); }));
  $$("[data-skilltab]", host).forEach((b) => (b.onclick = () => { state.skilltab = b.dataset.skilltab; renderWindows(v, state, host); }));
  $$("[data-board]", host).forEach((b) => (b.onclick = () => { state.board = +b.dataset.board; renderWindows(v, state, host); }));
}

// ------------------------------------------------------------------ pages
const S = { commonComparisons: {}, planner: { win: "overview" }, character: { win: "overview" }, combat: {}, database: {}, gear: {}, raid: {}, meter: {} };

function welcomeCard() {
  let hidden = false;
  try { hidden = localStorage.getItem("welcome-hidden") === "1"; } catch (e) {}
  if (hidden) return "";
  return `<section class="win" id="welcome"><div class="wh"><h2>Welcome</h2><span class="sub">three steps to your best build</span>
      <div class="tools"><button class="btn small" id="whide">Hide</button></div></div><div class="wb">
    <div class="hero"><img src="/static/logo.png" alt=""><div><h1>Aion 2 Calc</h1><div class="muted">Plan your AION 2 build, check your gear and learn from your fights. Everything runs on this computer; the game database updates itself.</div>
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
  app().innerHTML = welcomeCard() + `<section class="win"><div class="wh"><h2>Build planner</h2><a class="btn small" href="#/history">Saved results</a><span class="sub">optimized builds — copy each window into the game</span></div>
    <div class="wb"><div class="row"><label class="muted small">Build</label><select id="res"></select><button class="btn small" id="refresh-presets">Refresh presets</button>
      <span class="muted small">or optimize:</span><select id="cls"></select><select id="preset-mode" aria-label="Optimization mode"><option value="pve">PvE</option><option value="pvp">PvP damage (experimental)</option></select>
      <input id="sp" type="number" placeholder="skill pts (203)" title="skill points (default 203)" style="width:150px"><input id="stg" type="number" placeholder="stigma pts (30)" title="stigma points (default 30)" style="width:150px">
      <input id="dv" type="number" min="0" max="10000" placeholder="Daevanion pts (360 preset)" aria-label="Daevanion point budget" style="width:180px"><button class="btn primary" id="go">Optimize</button><span id="jobmsg" class="small muted"></span></div></div></section><div id="wins"></div>`;
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
    $("#cls").value = v.class;
    $("#preset-mode").value = String(v.scenario||"").startsWith("pvp")?"pvp":"pve";
    renderWindows(v, st, $("#wins"));
  };
  $("#res").onchange = load;
  $("#go").onclick = async () => {
    $("#go").disabled = true;
    try {
      const v = await runJob("/api/optimize", { class: $("#cls").value, mode:$("#preset-mode").value, skill_points: $("#sp").value===""?null:+$("#sp").value, stigma_points: $("#stg").value===""?null:+$("#stg").value, daevanion: $("#dv").value===""?360:+$("#dv").value },
        (log) => ($("#jobmsg").textContent = log[log.length - 1] || "working…"));
      renderWindows(v, st, $("#wins"));
      $("#jobmsg").textContent = v.preset_submission?.reason || "done";
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
  if (known.length) $("#known").innerHTML = `<div class="small muted">Imported before · newest first (click to fetch current profile): <div class="row">${known.slice(0, 8).map((c,i) => `<button class="btn small" data-known-character="${i}">${esc(c.name)} · ${esc(c.class_name)} · ${n0(c.combat_power)}</button>`).join("")}</div></div>`;
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
  $$("[data-known-character]").forEach(b=>b.onclick=()=>{const c=known[Number(b.dataset.knownCharacter)];doImport({character_id:c.character_id,server_id:c.server_id,region:c.region,name:c.name});});
  const showChar = () => {
    const v = st.v;
    let savedBudgets={};try{savedBudgets=JSON.parse(localStorage.getItem('character-point-budgets')||'{}')[v.key]||{};}catch(_){}
    const availableBudgets=Object.fromEntries(['skill','stigma','daevanion'].map(k=>[k,Math.max(v.points[k],savedBudgets[k]??v.budgets?.[k]??v.points[k])]));
    const rememberBudgets=()=>{const values=Object.fromEntries([...document.querySelectorAll('[data-character-budget]')].map(e=>[e.dataset.characterBudget,+e.value]));let all={};try{all=JSON.parse(localStorage.getItem('character-point-budgets')||'{}');}catch(_){}all[v.key]=values;localStorage.setItem('character-point-budgets',JSON.stringify(all));return values;};
    $("#cview").innerHTML = `<section class="win"><div class="wh"><h2>${esc(v.name)}</h2><span class="sub">${esc(cap(v.class))} · Lv ${v.level} · ${esc(v.server)} · Combat Power ${n0(v.combat_power)}</span>
      <div class="tools"><button class="btn primary" id="opt" data-opt-mode="pve">Optimize PvE build</button><button class="btn" id="optpvp" data-opt-mode="pvp">Optimize PvP damage (experimental)</button></div></div><div class="wb">
      <div class="kpis">${Object.entries(v.dps || {}).map(([k, x]) => `<div class="kpi"><div class="k">${esc(k)} ${v.genus?"saved build DPS":"imported DPS (without manual Genus)"}</div><div class="v">${n0(x)}</div></div>`).join("")}
        <div class="kpi"><div class="k">Skill points</div><div class="v">${v.points.skill} / ${v.budgets?.skill??"Unknown"}</div></div><div class="kpi"><div class="k">Stigma points</div><div class="v">${v.points.stigma} / ${v.budgets?.stigma??"Unknown"}</div></div>
        <div class="kpi"><div class="k">Daevanion</div><div class="v">${v.points.daevanion} / ${v.budgets?.daevanion??"Unknown"}</div></div></div>
      ${(v.warnings || []).map((w) => `<div class="small muted">• ${esc(w)}</div>`).join("")}<p class="small muted">The profile gives allocated points. Unspent points and some quest rewards may be absent. Enter the total available in your game window (spent + unspent) before optimizing. These values are the observed lower bound, not a verified maximum.</p><div class="row">${['skill','stigma','daevanion'].map(k=>`<label>${cap(k)} total <input type="number" data-character-budget="${k}" min="${v.points[k]}" max="10000" value="${availableBudgets[k]}" style="width:90px"></label>`).join('')}<label>Game build (optional) <input id="cpointpatch" maxlength="100" placeholder="Unknown" value="${esc(localStorage.getItem('point-game-patch')||'')}"></label></div><p class="small muted">PvP optimization is an experimental damage-only estimate against a stationary player proxy. It does not score survival, crowd control or win chance. PvE and PvP results are saved separately.</p><div id="survival-options"></div><div id="skill-reserves"></div><div id="character-genus"></div><div id="optres"></div></div></section><div id="cwins"></div>`;
    const survivalOptions=mountSurvivalOptions($('#survival-options'),'character-survival:'+JSON.stringify(st.hit||v.key||v.loadout));
    const reservesOptions=mountSkillReserves($('#skill-reserves'),'character-skill-reserves:'+JSON.stringify(st.hit||v.key||v.loadout),v);
    const genusOptions=mountCharacterGenus($("#character-genus"),v.key);
    renderWindows(v, st, $("#cwins"));
    st.optMeta = { key: v.key, name: v.name, level: v.level, warnings: v.warnings, server: v.server, combat_power: v.combat_power };
    $("#cpointpatch").onchange=()=>localStorage.setItem("point-game-patch",$("#cpointpatch").value.trim());
    document.querySelectorAll("[data-character-budget]").forEach(e=>e.onchange=rememberBudgets);
    document.querySelectorAll("[data-opt-mode]").forEach(button => button.onclick = async () => {
      if (S.character.opt?.status === "running") return;
      const mode = button.dataset.optMode;
      S.character.opt = { status: "running", mode, log: [], jobid: null };
      renderOptState();
      try {
        const { job } = await api("/api/character/optimize", {...st.hit,mode,budgets:rememberBudgets(),survival:survivalOptions.read(),skill_reserves:reservesOptions.read(),genus:genusOptions.read(mode),game_patch:$("#cpointpatch").value.trim()});
        S.character.opt.jobid = job;
        pollOpt();
      } catch (e) { S.character.opt = { status: "error", error: e.message }; renderOptState(); }
    });
    renderOptState();                 // show a job that is still running (or finished) after returning to this tab
  };
  if (st.v) showChar();
}

// The character optimize runs for minutes on the server; keep its state in S.character so it survives
// switching tabs, and poll it with a background loop that repaints when the character page is shown.
function renderOptResult(r) {
  const st = S.character, box = $("#optres");
  if (!box) return;
  const g = r.summary.gain, scenario = r.summary.scenario || r.optimized.scenario || "boss";
  const preset = r.preset?.submitted ? (r.preset.accepted ? "This build is now the community preset for its class." : "The server kept its current Planner preset: " + (r.preset.reason || "no improvement at the shared budgets") + "") : (r.preset?.reason ? "Community preset: " + r.preset.reason : "");
  box.innerHTML = `<div class="kpis" style="margin-top:12px"><div class="kpi"><div class="k">Optimized ${scenario === "pvp" ? "PvP proxy" : "boss"} DPS</div><div class="v">${n0(r.optimized.dps[scenario])}</div></div>
      <div class="kpi"><div class="k">Gain</div><div class="v ${g > 0 ? "good" : ""}">${g >= 0 ? "+" : ""}${pct(g)}</div></div></div>
      ${r.optimized.model_note ? `<p class="note">${esc(r.optimized.model_note)}</p>` : ""}${preset ? `<p class="small ${r.preset?.accepted?"good":"muted"}">${esc(preset)}</p>` : ""}<p class="small muted">The windows below now show the optimized build. What changes:</p><pre class="diff">${esc(r.diff)}</pre>`;
  st.v = Object.assign({}, r.optimized, st.optMeta || {});
  if ($("#cwins")) renderWindows(st.v, st, $("#cwins"));
}
function renderOptState() {
  if (!location.hash.startsWith("#/character")) return;
  const o = S.character.opt, box = $("#optres");
  if (!o || !box) return;
  document.querySelectorAll("[data-opt-mode]").forEach(b=>b.disabled = o.status === "running");
  if (o.status === "running") {
    const log = o.log || [];
    const last = log.length ? log[log.length - 1] : "starting…";
    box.innerHTML = `<p><span class="spinner"></span> Optimizing ${o.mode === "pvp" ? "PvP damage (experimental)" : "PvE build"} — <b>${esc(last)}</b></p>
      <pre class="diff small" style="max-height:150px;overflow:auto;margin-top:6px">${esc(log.slice(-8).join("\n"))}</pre>
      <p class="small faint">Runs the rotation, stigma, Daevanion and skill-point search. Progress stays visible during the stigma and skill-level searches; the full optimization may take a few minutes.</p>`;
  }
  else if (o.status === "error") box.innerHTML = `<div class="note">${esc(o.error || "optimization failed")}</div>`;
  else if (o.status === "done" && o.result) renderOptResult(o.result);
}
function pollOpt() {
  const o = S.character.opt;
  if (!o || o.status !== "running" || !o.jobid) return;
  api("/api/jobs/" + o.jobid).then((j) => {
    if (S.character.opt !== o) return;                 // a newer run superseded this one
    o.log = j.log || o.log;
    if (j.status === "done") { o.status = "done"; o.result = j.result; }
    else if (j.status === "error") { o.status = "error"; o.error = j.error; }
    renderOptState();
    if (o.status === "running") setTimeout(pollOpt, 1200);
  }).catch(() => setTimeout(pollOpt, 2500));            // keep polling through transient fetch errors
}

function lineChart(per, roll) {
  const W = 1000, H = 190, n = per.length || 1, mx = Math.max(...per, ...roll, 1);
  const bars = per.map((v, i) => `<rect x="${(i / n) * W}" y="${H - (v / mx) * H}" width="${Math.max(1, W / n - 1)}" height="${(v / mx) * H}" style="fill:var(--chart-bar)"/>`).join("");
  const pts = roll.map((v, i) => `${((i + 0.5) / n) * W},${H - (v / mx) * H}`).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}<polyline points="${pts}" fill="none" style="stroke:var(--chart-line)" stroke-width="2"/></svg>
    <div class="row small muted"><span>bars: damage per second</span><span style="color:var(--gold)">line: 10 s average</span><span>peak 10 s: ${n0(Math.max(...roll))}</span></div>`;
}

// ------------------------------------------------------------- AionFlex-style breakdown
// One parse card (header stats · DPS/Defense/Accuracy tabs · damage-source donut · per-skill table ·
// rotation strip), shared by the Combat Logs view and the Live Meter. Fed by a normalized object so
// a saved log and a live snapshot render identically. No paid tiers — every panel is shown.
const PCOL = ["#e8cf8e", "#58a6ff", "#b18cff", "#6fcf7a", "#e68a5a", "#5ad1c4", "#e45a8a", "#d7c15a", "#8a92a8"];
let _ptab = "dps";
const skillIcon = (id) => (id ? icon("https://metabot.gg/web/aion2/skills/" + (Math.floor(Number(id) / 10000) * 10000) + ".webp") : "");
const SKILL_PLACEHOLDER = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" rx="4" fill="#263048"/><path d="M12 4L19 12L12 20L5 12Z" fill="none" stroke="#e8cf8e"/></svg>');
function skillArt(id, name = "") {
  const source = skillIcon(id);
  return `<img class="skill-art" width="24" height="24" data-skill-source="${esc(source)}" src="${esc(source || SKILL_PLACEHOLDER)}" title="${esc(name)}" alt="" onerror="this.onerror=null;this.src=SKILL_PLACEHOLDER">`;
}
function replaceMeterHtml(element, html) {
  // Reuse decoded image nodes across live updates instead of loading every icon again.
  const images = new Map();
  element.querySelectorAll("img").forEach((node) => {
    const key = node.dataset.skillSource || node.getAttribute("src");
    if (!images.has(key)) images.set(key, []);
    images.get(key).push(node);
  });
  const template = document.createElement("template"); template.innerHTML = html;
  template.content.querySelectorAll("img").forEach((node) => {
    const key = node.dataset.skillSource || node.getAttribute("src"), old = images.get(key)?.shift();
    if (old) node.replaceWith(old);
  });
  element.replaceChildren(template.content);
}

function kfmt(x) {
  if (x == null || isNaN(x)) return "—";
  const a = Math.abs(x);
  if (a >= 1e6) return (x / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (x / 1e3).toFixed(2) + "K";
  return Math.round(x).toString();
}
function pdonut(parts, center) {
  const tot = parts.reduce((s, p) => s + (p.value || 0), 0) || 1;
  const R = 86, r = 55, cx = 95, cy = 95;
  let a0 = -Math.PI / 2;
  const seg = parts.map((p) => {
    const frac = Math.min((p.value || 0) / tot, 0.99999);
    if (frac <= 0) return "";
    const a1 = a0 + frac * 2 * Math.PI, big = frac > 0.5 ? 1 : 0;
    const x0 = cx + R * Math.cos(a0), y0 = cy + R * Math.sin(a0), x1 = cx + R * Math.cos(a1), y1 = cy + R * Math.sin(a1);
    const xi1 = cx + r * Math.cos(a1), yi1 = cy + r * Math.sin(a1), xi0 = cx + r * Math.cos(a0), yi0 = cy + r * Math.sin(a0);
    a0 = a1;
    return `<path d="M${x0} ${y0} A${R} ${R} 0 ${big} 1 ${x1} ${y1} L${xi1} ${yi1} A${r} ${r} 0 ${big} 0 ${xi0} ${yi0} Z" fill="${p.color}"/>`;
  }).join("");
  return `<div class="pdonut"><svg viewBox="0 0 190 190">${seg}</svg><div class="mid"><b>${center[0]}</b><span>${center[1]}</span></div></div>`;
}
function renderParse(d) {
  if (!d) return "";
  const at = _ptab;
  const skills = (d.skills || []).slice().sort((a, b) => (b.damage || 0) - (a.damage || 0));
  const totDmg = d.dmg || skills.reduce((s, x) => s + (x.damage || 0), 0) || 1;
  const top = skills.slice(0, 5), rest = skills.slice(5);
  const otherDmg = rest.reduce((s, x) => s + (x.damage || 0), 0);
  const parts = top.map((s, i) => ({ label: s.skill, value: s.damage || 0, color: PCOL[i % PCOL.length] }));
  if (otherDmg > 0) parts.push({ label: `Other (${rest.length})`, value: otherDmg, color: PCOL[8] });
  const topList = parts.map((p) => `<div class="trow"><span class="sw" style="background:${p.color}"></span><span class="nm">${esc(p.label)}</span><span class="pc">${Math.round(100 * p.value / totDmg)}%</span></div>`).join("");
  const mxDmg = Math.max(...skills.map((s) => s.damage || 0), 1);
  const srows = skills.map((s) => `<tr><td class="nm">${skillArt(s.skill_id, s.skill)}${esc(s.skill)}</td>
    <td>${s.hits ?? "—"}</td><td>${kfmt(s.dps)}</td><td>${kfmt(s.avg)}</td><td>${s.min == null ? "—" : kfmt(s.min)}</td><td>${s.max == null ? "—" : kfmt(s.max)}</td>
    <td class="dmg"><i style="width:${100 * (s.damage || 0) / mxDmg}%"></i><span>${kfmt(s.damage)}<span class="pcpct">${Math.round(100 * (s.damage || 0) / totDmg)}%</span></span></td></tr>`).join("");
  const spark = d.timeline ? `<div style="margin:4px 0 12px">${lineChart(d.timeline.per_second, d.timeline.rolling10)}</div>` : "";
  const dpsPanel = `<div class="ppanel" data-pane="dps"${at === "dps" ? "" : " hidden"}>
    ${d.highest != null ? `<div class="phi"><div class="k">Highest hit</div><div class="v">${kfmt(d.highest)}</div></div>` : ""}
    <div class="psplit">${pdonut(parts.length ? parts : [{ value: 1, color: "#2a3045" }], [kfmt(d.dps), "DPS"])}<div class="ptop">${topList || '<span class="muted">No skills recorded.</span>'}</div></div>
    ${spark}<table class="pskills"><tr><th>Skill</th><th>Hit</th><th>DPS</th><th>Avg</th><th>Min</th><th>Max</th><th>Damage</th></tr>${srows}</table></div>`;
  const rate = (x) => (x == null ? "—" : Math.round(100 * x) + "%");
  const rc = (k, v) => `<div class="rc"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const accPanel = `<div class="ppanel" data-pane="acc"${at === "acc" ? "" : " hidden"}><div class="prates">
    ${rc("Hit chance", "Unavailable")}${rc("Crit", rate(d.rates.crit))}${rc("Back", rate(d.rates.back))}${rc("Front", rate(d.rates.front))}${rc("Double", rate(d.rates.double))}${rc("Perfect", rate(d.rates.perfect))}${rc("Multi", rate(d.rates.multi))}${rc("Parried", rate(d.rates.parry))}</div><p class="small muted">Rates use decoded outgoing hits. Hit chance requires attempted attacks and misses, which this source does not currently provide.</p></div>`;
  const defense = d.incoming;
  const defPanel = `<div class="ppanel" data-pane="def"${at === "def" ? "" : " hidden"}>${defense ? `<div class="prates">${rc("Damage taken", kfmt(defense.damage))}${rc("Incoming hits", n0(defense.hits))}${rc("Parried hits", n0(defense.parries))}${rc("Healing done", kfmt(d.healing || 0))}</div><table class="t"><tr><th>Attacker</th><th>Damage taken</th></tr>${Object.entries(defense.sources || {}).sort((a,b) => b[1]-a[1]).map(([name,damage]) => `<tr><td>${esc(name)}</td><td>${kfmt(damage)}</td></tr>`).join("")}</table><p class="small muted">Damage received and parry flags are measured from decoded hits. Avoided attacks and pre-mitigation damage are unavailable; armor, mitigation and dodge percentages cannot be inferred from received damage alone.</p>` : `<div class="pnote">This source does not provide incoming-damage events.</div>`}</div>`;
  const rot = (d.rotation || []).length ? `<div class="prot"><div class="lbl">Skill rotation</div><div class="strip">${d.rotation.slice(0, 80).map((e) => `<div class="ic">${skillArt(e.skill_id, e.skill)}<small>${esc(e.skill || "")}</small><span>${e.t != null ? e.t.toFixed(0) + "s" : ""}</span></div>`).join("")}</div></div>` : "";
  const stat = (l, v, gold) => `<div><span class="pl">${l}</span><span class="pv${gold ? " gold" : ""}">${v}</span></div>`;
  const clsIcon = d.cls ? `<img class="pcls" src="${icon("https://metabot.gg/web/aion2/classes/" + String(d.cls).toLowerCase() + ".webp")}" alt="" onerror="this.style.visibility='hidden'">` : "";
  return `<div class="parse">
    <div class="phead"><div class="pwho">${clsIcon}<b>${esc(d.name || "—")}</b><span class="psub">${esc(cap(d.cls || ""))}${d.boss ? " · " + esc(d.boss) : ""}</span></div>
      <div class="pstats">${d.gs != null ? stat("GS", n0(d.gs)) : ""}${d.cp != null ? stat("CP", kfmt(d.cp)) : ""}${stat("DMG", kfmt(d.dmg))}${stat("DPS", kfmt(d.dps), true)}${d.contrib != null ? stat("Contrib", Math.round(100 * d.contrib) + "%") : ""}</div></div>
    <div class="ptabs"><button data-ptab="dps" class="${at === "dps" ? "on" : ""}">DPS</button><button data-ptab="def" class="${at === "def" ? "on" : ""}">Defense</button><button data-ptab="acc" class="${at === "acc" ? "on" : ""}">Accuracy</button></div>
    ${dpsPanel}${defPanel}${accPanel}${rot}</div>`;
}
document.addEventListener("click", (e) => {                 // one delegated handler toggles the parse tabs
  const b = e.target.closest && e.target.closest(".ptabs [data-ptab]");
  if (!b) return;
  _ptab = b.dataset.ptab;
  const parse = b.closest(".parse");
  parse.querySelectorAll(".ptabs [data-ptab]").forEach((x) => x.classList.toggle("on", x === b));
  parse.querySelectorAll(".ppanel").forEach((p) => (p.hidden = p.dataset.pane !== _ptab));
});
function parseFromEncounter(a) {
  const s = a.summary, m = a.meta, tot = s.total || 1, nameToId = {};
  (a.skills || []).forEach((k) => { if (k.skill_id) nameToId[k.skill] = k.skill_id; });
  return {
    name: m.player, cls: m.class || m.class_name, gs: null, cp: m.combat_power || null,
    dmg: s.total, dps: s.dps, contrib: null, duration: s.duration, boss: m.target,
    highest: s.biggest_hit ? s.biggest_hit.damage : null,
    rates: { crit: s.crit, double: s.double, perfect: s.perfect, multi: s.multi, back: s.back ?? null, front: s.front ?? null },
    skills: (a.skills || []).map((k) => { const dmg = (k.share || 0) * tot; return { skill: k.skill, skill_id: k.skill_id, hits: k.hits, dps: dmg / (s.duration || 1), avg: k.avg_hit, min: null, max: k.max_hit, damage: dmg, share: k.share }; }),
    rotation: (a.rotation || []).map(([t, k]) => ({ t, skill: k, skill_id: nameToId[k] })),
    timeline: a.timeline, live: false,
  };
}
function parseFromMeter(snap, idx) {
  const p = (snap.players || [])[idx];
  if (!p) return null;
  return {
    name: p.name, cls: p.class, gs: null, cp: null,
    dmg: p.damage, dps: p.dps, contrib: p.share, duration: snap.duration, boss: snap.boss, highest: null,
    rates: { crit: p.crit, double: p.double ?? null, perfect: p.perfect ?? null, multi: p.multi ?? null, back: p.back ?? null, front: p.front ?? null, parry: p.parry ?? null },
    skills: (p.skills || []).map((s) => ({ skill: s.skill, skill_id: s.skill_id, hits: s.hits, dps: (s.damage || 0) / (snap.duration || 1), avg: (s.damage || 0) / (s.hits || 1), min: s.min ?? null, max: s.max ?? null, damage: s.damage, share: s.share })),
    rotation: [], timeline: p.timeline || null, incoming: p.incoming, healing: p.healing, live: true,
  };
}

const communityAPI=(path,body)=>body?api('/api/community',{path,body}):api('/api/community?path='+encodeURIComponent(path));
const localReviewOptions=file=>({
 skillIcon,
 lookupProfile:(player,region)=>api("/api/character/profile",{player,region}),
 importPlan:plan=>{window.A2Raid.importPlan(plan);location.hash="/raid";},
 compare:id=>communityAPI('/api/v1/logs/'+encodeURIComponent(id)+'/raw'),
 rankings:(segment,log)=>communityAPI('/api/v1/rankings',{segment,log}),
 ...(file?{saveMetadata:log=>api('/api/sessions',{file,log}),publish:visibility=>api('/api/sessions/share',{file,visibility})}:{})
});
async function pageCombatLog() {
  const routeHash=location.hash, routeParts=routeHash.split('?'), parts=routeParts[0].split('/'), kind=parts[2], value=decodeURIComponent(parts.slice(3).join('/')), mode=new URLSearchParams(routeParts[1]||'').get('mode');
  if(S.combat.review){S.combat.review.dispose();S.combat.review=null;}
  app().innerHTML='<p><a class="btn small" href="#/combat">← Back to combat logs</a></p><div id="focused-log">Loading combat log…</div>';
  const target=$('#focused-log');
  let doc,options={...localReviewOptions(),mode};
  if(kind==='analysis'){
    const analysis=await api('/api/encounters/'+encodeURIComponent(value));
    if(location.hash!==routeHash || !target.isConnected)return;
    target.innerHTML=renderEncounter(analysis);
    target.querySelectorAll('[data-share]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const result=await api('/api/encounters/'+analysis.id+'/share',{});const link=document.createElement('a');link.href=result.url;link.textContent='Open shared log';link.target='_blank';link.rel='noopener';target.querySelector('#shared').replaceChildren(link);if(result.ownership_warning)toast(result.ownership_warning);}catch(e){target.querySelector('#shared').textContent=e.message;}finally{button.disabled=false;}});
    target.querySelectorAll('[data-player]').forEach(button=>button.onclick=async()=>{try{button.disabled=true;const next=await runJob('/api/encounters/import',{ref:analysis.meta.url,player:button.dataset.player},lines=>toast(lines.at(-1)||'Analyzing…'));location.hash='/combat-log/analysis/'+next.id;}catch(e){toast(e.message);button.disabled=false;}});
    window.scrollTo(0,0);return;
  }
  if(kind==='local'){doc=await api('/api/sessions?file='+encodeURIComponent(value));options=localReviewOptions(value);}
  else if(kind==='shared'){
    doc=await communityAPI('/api/v1/logs/'+encodeURIComponent(value)+'/raw');
    options={...options,report:body=>communityAPI('/api/v1/logs/'+encodeURIComponent(value)+'/reports',body),rankings:segment=>communityAPI('/api/v1/logs/'+encodeURIComponent(value)+'/rankings?segment='+segment)};
  }else if(kind==='opened' && S.combat.openedLog)doc=S.combat.openedLog;
  else {target.textContent='This temporary preview is no longer available. Return to combat logs to open it again.';return;}
  if(location.hash!==routeHash || !target.isConnected)return;
  S.combat.review=A2CombatReview.mount(target,doc,options);
  window.scrollTo(0,0);
}
async function pageCombat() {
  const st = S.combat;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Combat logs</h2><span class="sub">per-skill breakdown, timeline, rates, idle time — compared with your optimal rotation</span></div>
    <div class="wb"><div id="combat-log-tabs"><div class="row" role="tablist" aria-label="Combat log sources"><button class="btn small" role="tab" id="log-tab-saved" data-log-tab="saved" aria-controls="log-panel-saved">Saved Parts</button><button class="btn small" role="tab" id="log-tab-owned" data-log-tab="owned" aria-controls="log-panel-owned">My Uploads</button><button class="btn small" role="tab" id="log-tab-community" data-log-tab="community" aria-controls="log-panel-community">Community Combat Logs</button></div><div id="log-panel-saved" data-log-panel="saved" role="tabpanel" aria-labelledby="log-tab-saved"><div class="row"><input id="ref" type="text" placeholder="AbyssLogs link (abysslogs.com/e/…) or A2DIL link" style="width:400px">
      <input id="player" type="text" placeholder="player (party logs)" style="width:150px"><button class="btn primary" id="imp">Analyze</button>
      <span class="muted small">or</span><input id="file" type="file" accept=".json,.gz,.csv"><span id="lmsg" class="small muted"></span></div>
      <p class="small faint">Record a fight with the free <a href="https://abysslogs.com" target="_blank" rel="noopener">AbyssLogs meter</a>, press Share, and paste the link here. A party log shows the recorder's damage unless you name a player.
        Files: AbyssLogs segment (.json / .json.gz), aion2calc JSON (see docs), or CSV with columns t, skill, damage, crit, double, perfect, multi, dot.</p>
      <div class="row small" id="logsdir"></div>
      <div class="row small" id="lsrv"></div>
      <div id="sessions"></div><div id="session-review"></div><h3>Analyzed encounters</h3><div id="hist"></div></div><div id="log-panel-owned" data-log-panel="owned" role="tabpanel" aria-labelledby="log-tab-owned" hidden><div id="owned-logs"></div></div><div id="log-panel-community" data-log-panel="community" role="tabpanel" aria-labelledby="log-tab-community" hidden><div id="community"></div></div></div></div></section><div id="enc"></div>`;
  A2LogTabs.mount($('#combat-log-tabs'),st.listTab||'saved',value=>{st.listTab=value;});
  api("/api/logs").then((l) => {
    if(!$("#logsdir"))return;
    $("#logsdir").innerHTML = `<span class="muted">Every analyzed log is saved as a file in</span> <code>${esc(l.folder)}</code> <span class="faint">(${l.files} files)</span>
      <button class="btn small" id="openlogs">Open folder</button>`;
    $("#openlogs").onclick = () => api("/api/logs/open", {}).catch((e) => ($("#lmsg").textContent = e.message));
  }).catch(() => {});
  const srv = async () => {
    const c = await api("/api/logserver").catch(() => ({}));
    if(!$("#lsrv"))return;
    $("#lsrv").innerHTML = `<span class="muted">Share to a log server:</span><input id="lsurl" type="text" placeholder="https://logs.example.com" value="${esc(c.url || "")}" style="width:240px">
      <input id="lskey" type="password" placeholder="${c.has_key ? "key saved" : "upload key"}" style="width:160px">
      <select id="lsvis">${["unlisted", "public", "private"].map((v) => `<option ${v === (c.visibility || "unlisted") ? "selected" : ""}>${v}</option>`).join("")}</select>
      <button class="btn small" id="lssave">Save</button>`;
    $("#lssave").onclick = async () => { await api("/api/logserver", { url: $("#lsurl").value, key: $("#lskey").value || null, visibility: $("#lsvis").value }); toast("Saved"); srv(); };
  };
  srv();
  A2ArchiveUpload.mount($('#sessions'),{
    types:A2Community.types,
    list:(offset,limit,archive)=>api('/api/sessions?paged=1&offset='+offset+'&limit='+limit+'&archive='+encodeURIComponent(archive||'')),
    context:()=>api('/api/logserver'),
    loadCheckpoint:()=>api('/api/upload-queue'),saveCheckpoint:value=>api('/api/upload-queue',value),
    fingerprint:async row=>(await api('/api/sessions?fingerprint='+encodeURIComponent(row.file))).fingerprint,
    open:row=>{location.hash='/combat-log/local/'+encodeURIComponent(row.file);},
    upload:(row,batch)=>api('/api/sessions/share',{file:row.file,visibility:batch.visibility,server:batch.url,completed_only:true,fingerprint:row.fingerprint,request_id:row.request_id})
  });
  A2LogOwnership.mount($('#owned-logs'),{
    list:()=>api('/api/log-ownership'),
    import:owners=>api('/api/log-ownership',{action:'import',owners}),
    forget:owner=>api('/api/log-ownership',{action:'forget',owner}),
    request:(owner,action,visibility)=>api('/api/log-ownership',{owner,action,visibility}),
    open:doc=>{S.combat.openedLog=doc;location.hash='/combat-log/opened/'+Date.now();}
  });
  A2Community.mount($('#community'),{api:communityAPI,open:(id,mode)=>{location.hash='/combat-log/shared/'+encodeURIComponent(id)+'?mode='+encodeURIComponent(mode||'');}});
  const hist = await api("/api/encounters").catch(() => []);
  if(!$("#hist"))return;
  $("#hist").innerHTML = hist.length ? `<table class="t"><tr><th>#</th><th>Player</th><th>Class</th><th>Target</th><th>Source</th><th class="r">Duration</th><th class="r">DPS</th><th></th></tr>${hist.map((e) =>
    `<tr><td>${e.id}</td><td>${esc(e.player || "")}</td><td>${esc(cap(e.class_name))}</td><td>${esc(e.boss || "")}</td><td>${esc(e.source)}</td><td class="r">${(e.duration || 0).toFixed(0)}s</td><td class="r num">${n0(e.dps)}</td>
     <td class="r"><button class="btn small" data-enc="${e.id}">Open</button></td></tr>`).join("")}</table>` : '<div class="faint small">No encounters yet.</div>';
  $$("[data-enc]").forEach((b) => (b.onclick = () => openEnc(+b.dataset.enc)));
  const progress = (l) => ($("#lmsg").textContent = l[l.length - 1] || "");
  const show = a => {st.a=a;location.hash='/combat-log/analysis/'+a.id;};
  const openEnc = id => {location.hash='/combat-log/analysis/'+id;};
  $("#imp").onclick = async () => {
    try { show(await runJob("/api/encounters/import", { ref: $("#ref").value, player: $("#player").value }, progress)); }
    catch (e) { $("#lmsg").textContent = e.message; }
  };
  $("#file").onchange = async () => {
    const f = $("#file").files[0]; if (!f) return;
    try {
      const gz = new Uint8Array(await f.slice(0, 2).arrayBuffer());
      const text = gz[0] === 0x1f && gz[1] === 0x8b                      // AbyssLogs segment files are gzip
        ? await new Response(f.stream().pipeThrough(new DecompressionStream("gzip"))).text() : await f.text();
      show(await runJob("/api/encounters/import", { text, name: f.name, player: $("#player").value }, progress));
    } catch (e) { $("#lmsg").textContent = e.message; }
  };

}


function renderEncounter(a) {
  const s = a.summary, m = a.meta;
  const extra = [["Casts / min", s.cpm.toFixed(0)], ["Multi-hit", pct(s.multi)], ["Idle", s.idle_seconds.toFixed(1) + " s"]];
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
  const chips = `<div class="row small" style="margin-top:8px">${extra.map(([k, v]) => `<span class="muted">${k}: <b>${v}</b></span>`).join("")}</div>`;
  return win("Encounter", `${esc(m.player || "")} · ${esc(cap(m.class || m.class_name || ""))} · ${esc(m.target || "")} · ${esc(m.source)}${m.combat_power ? " · CP " + n0(m.combat_power) : ""}`,
      `${party}${info}${renderParse(parseFromEncounter(a))}${chips}`) +
    win("Buff uptime", "", `<table class="t">${buffs}</table>` + (a.gaps.length ? `<p class="small muted">Idle gaps: ${a.gaps.map((g) => `${g.start.toFixed(1)}–${g.end.toFixed(1)}s`).join(", ")}</p>` : "")) +
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
// The raid & boss planner is a shared module (raid.js), used here and on the planner site. In the
// app it is wired to your saved combat logs so a fight can be overlaid on the plan's timeline.
async function pageRaid() {
  const publicationServer=await api("/api/logserver");
  await window.A2Raid.mount(app(), {
    encounters: () => api("/api/encounters"),
    encounter: (id) => api("/api/encounters/" + id),
    server:()=>publicationServer.url.replace(/\/+$/, ""),
    publish: (plan, visibility, owner) => api("/api/plans", {plan, visibility,owner}),
    refresh:owner=>api("/api/plans",{id:owner.id,owner}),
    browse: async () => (await api("/api/plans")).plans,
    fetchPlan: (id) => api("/api/plans?id=" + encodeURIComponent(id)),
  });
}

// ------------------------------------------------------------- live meter
async function pageMeter() {
  const st = S.meter;
  st.lastMeterRender = null; // The previous DOM was removed when leaving this page.
  app().innerHTML = `<section class="win"><div class="wh"><h2>Live damage meter</h2><span class="sub">built-in A2Tools packet capture, live analysis and a2log sharing</span></div>
    <div class="wb"><div class="row"><label class="muted small">Source</label>
        <select id="msrc"><option value="a2tools" selected>Live Capture</option><option value="replay">Demo replay</option><option value="live">Custom decoder</option></select>
        <button class="btn primary" id="mstart" aria-pressed="false">Start</button>
        <button class="btn small" id="mclear">Clear session</button><button class="btn small" id="msave">Save to Combat Logs</button><button class="btn small" id="mexport">Export a2log</button>
        <button class="btn small" id="mupload">Upload</button><button class="btn small" id="mshot">Screenshot</button>
        <button class="btn small" id="mhide">Hide overlay</button><button class="btn small" id="msplit">Split now</button><button class="btn small" id="mfinishrun">Finish run</button><button class="btn small" id="movl" title="Open the compact overlay in a separate window">Open overlay</button><span id="mmsg" class="small muted"></span></div>
      <div class="row" id="mlive" style="display:none;margin-top:6px">
        <label class="small muted">Encoder <input id="mdec" type="text" value="Built-in A2Tools decoder" readonly aria-label="Encoder module" style="width:180px"></label>
        <label class="small muted">Interface <select id="miface" aria-label="Capture interface" title="Npcap interface; Auto monitors all available adapters"><option value="auto">Auto</option></select></label><button class="btn small" id="mifacesrefresh">Refresh interfaces</button>
        <label class="small muted">Game host <input id="mhost" type="text" value="any" aria-label="Game host" style="width:100px" title="Use an address to limit the capture; any accepts game traffic on the port"></label>
        <label class="small muted"><input id="mautoport" type="checkbox" checked> Detect game port</label><label class="small muted">Fixed port <input id="mport" type="number" value="50349" aria-label="Game server port" style="width:80px"></label>

        <label class="small muted">Name override (optional) <input id="mchar" type="text" placeholder="Auto-detect" style="width:120px"></label></div>
      <div class="row" style="margin-top:8px"><label class="small muted">Players <select id="mscope"><option value="party">Self + Party</option><option value="self">Self only</option><option value="all">All observed players</option></select></label><label class="small muted"><input id="mcombinepets" type="checkbox" checked> Combine pets with owner</label><label class="small muted"><input id="mautosplit" type="checkbox" checked> Automatic splits</label><label class="small muted">Group combat within <input id="msegap" type="number" min="3" max="120" value="10" style="width:60px"> seconds</label><label class="small muted">Combat <select id="msegments"><option value="">Latest combat</option><option value="all">Whole session</option></select></label><button class="btn small" id="mallenemies">All enemies</button></div>
      <div class="row"><label class="small">Game installation <select id="minstall"><option value="">Auto (one installed copy)</option></select></label><button class="btn small" id="minstallrefresh">Refresh installations</button><span class="small muted" id="minstallstatus" role="status"></span></div><div class="row" id="mmetadata"></div><div class="note small" id="mautometa" role="status"></div><div class="row" id="mcustom" style="display:none;margin-top:6px"><label class="small muted">Decoder file <input id="mcustomdec" type="file" accept=".py"></label><span id="mdecodername" class="small muted">Choose a trusted Python decoder. Its code runs when capture starts.</span></div>
      <div class="note" style="margin-top:10px"><b>Capture diagnostics</b><div id="mdriverstats" class="small muted" role="status"></div>
        <div class="row"><label><input id="mrecord" type="checkbox"> Record TCP payloads (enable before Start)</label><button class="btn small" id="mdiag">Export capture diagnostics</button><span id="mrecordstatus" class="small muted"></span></div>
        <p class="small faint">Records the full session to disk without a record or size limit, even when no combat events are decoded. Available disk space limits recording. Saves a diagnostic ZIP automatically when capture stops; long recordings take longer to compress. Raw traffic may contain character names, IP addresses and other traffic; review before sharing.</p><div id="mdiagresult" class="small" role="status"></div><div id="mdiagerror" class="small" role="alert"></div></div><div id="npcap" class="small faint" style="margin-top:8px"></div>
      <p class="small faint">Live Capture uses the included A2Tools protocol engine. It needs Npcap in WinPcap-compatible mode, Scapy, and capture permission. Export writes an open a2log file; Upload uses the log server configured in Settings.</p>
      <div class="row"><label class="small"><input id="mautofinish" type="checkbox" checked> Finish on configured final-boss death</label><label class="small">Final-boss NPC type IDs <input id="mfinalboss" placeholder="Comma-separated verified NPC IDs"></label></div><p class="small muted">Final-boss order and PvP match-end packets are not yet verified. Configure the final boss before Start, or use Finish run. Map/instance changes create separate runs without claiming completion. Capture keeps running.</p><div id="mrun" class="small" role="status"></div><div id="midentity" class="small" role="status"></div><div id="msaved" class="small" role="status"></div><div id="mnotice" class="small" role="status"></div>
    </div></section><div id="mview"></div><div id="mlog-review"></div>`;
  const live = () => {
    $("#mlive").style.display = $("#msrc").value !== "replay" ? "flex" : "none";
    $("#mcustom").style.display = $("#msrc").value === "live" ? "flex" : "none";
  };
  $("#msrc").onchange = live; live();
  try { $("#mchar").value = localStorage.getItem("meter-character") || ""; } catch (e) {}
  try{$('#mfinalboss').value=localStorage.getItem('meter-final-boss-ids')||'';}catch(_){}
  $('#mfinalboss').onchange=()=>localStorage.setItem('meter-final-boss-ids',$('#mfinalboss').value);
  let classification={};try{classification=JSON.parse(localStorage.getItem('meter-metadata'))||{};}catch(_){}
  $('#mmetadata').innerHTML=`<label class="small">Encounter type <select data-capture-meta="encounter_type">${Object.entries(A2Community.types).map(([v,l])=>`<option value="${v}" ${v===(classification.encounter_type||'unknown')?'selected':''}>${v==='unknown'?'Auto detect':esc(l)}</option>`).join('')}</select></label>${['game_patch','difficulty','zone'].map(k=>`<label class="small">${esc(k==='game_patch'?'game build override':k.replaceAll('_',' '))} <input data-capture-meta="${k}" maxlength="200" value="${esc(classification[k]||'')}" placeholder="Unknown" style="width:130px"></label>`).join('')}<label class="small">Region <select data-capture-meta="region"><option value="">Auto (recorded home server)</option>${[['nae','North America'],['eu','Europe'],['as','Asia'],['la','Latin America'],...((classification.region&&!['nae','eu','as','la'].includes(classification.region))?[[classification.region,'Previously saved: '+classification.region]]:[])].map(([v,l])=>`<option value="${esc(v)}" ${v===classification.region?'selected':''}>${esc(l)}</option>`).join('')}</select></label><span class="small muted">Optional overrides. The selected Steam build, recognized maps/instances and region are detected automatically; unknown content stays unverified. Change overrides between sessions.</span>`;
  const updateView = async (body) => { try { renderMeter(await api("/api/meter", {action: "view", ...body})); } catch (e) { $("#mnotice").textContent = e.message; } };
  document.querySelectorAll('[data-capture-meta]').forEach(e=>e.onchange=()=>{classification=Object.fromEntries([...document.querySelectorAll('[data-capture-meta]')].map(e=>[e.dataset.captureMeta,e.value.trim()]));localStorage.setItem('meter-metadata',JSON.stringify(classification));updateView({metadata:classification});});
  updateView({metadata:classification});
  $("#mchar").onchange = () => { try { localStorage.setItem("meter-character", $("#mchar").value.trim()); } catch (e) {} updateView({character_name: $("#mchar").value.trim()}); };
  $("#mcombinepets").onchange = () => updateView({combine_pets: $("#mcombinepets").checked});
  $("#mscope").onchange = () => updateView({scope: $("#mscope").value});
  $("#msegap").onchange = () => updateView({segment_gap: +$("#msegap").value || 10});
  $("#msplit").onclick = async()=>{st.pinnedSegment="";renderMeter(await api("/api/meter",{action:"split"}));$("#mnotice").textContent="Next combat event starts a new split.";};
  $("#mautosplit").onchange=()=>updateView({automatic_splits:$("#mautosplit").checked});
  $("#mhide").onclick=async()=>{await api("/api/overlay",{action:"hide"});if(st.overlayPopup)st.overlayPopup.close();$("#mnotice").textContent="Overlay hidden. Open overlay to show it again.";};
  $("#msegments").onchange = () => { st.pinnedSegment = $("#msegments").value; updateView({segment: st.pinnedSegment}); };
  $("#mallenemies").onclick = () => updateView({enemy: null});
  $("#mclear").onclick = async () => {
    if (!window.confirm("Clear retained combat history? Export or save it first if you want to keep a copy.")) return;
    if(st.liveReview)st.liveReview.dispose();
    if($("#mlog-review"))$("#mlog-review").innerHTML="";
    st.liveReviewRoot=null;
    try { st.pinnedSegment = ""; renderMeter(await api("/api/meter", {action: "clear"})); $("#mnotice").textContent = "Combat history cleared."; } catch (e) { $("#mnotice").textContent = e.message; }
  };
  $('#mfinishrun').onclick=async()=>{try{renderMeter(await api('/api/meter',{action:'finish-run'}));$('#mnotice').textContent='Run finished. Capture continues; the next fight starts a new run.';}catch(e){$('#mnotice').textContent=e.message;}};
  let decoderPath = null;
  $("#mcustomdec").onchange = async () => {
    const file = $("#mcustomdec").files[0]; decoderPath = null;
    if (!file) return;
    try {
      if (file.size > 1048576) throw new Error("Decoder files must be smaller than 1 MiB");
      const imported = await api("/api/meter/decoder", {name: file.name, source: await file.text()});
      decoderPath = imported.path; $("#mdecodername").textContent = imported.name;
    } catch (e) { $("#mdecodername").textContent = e.message; }
  };
  const renderInstallations = (r) => {
    const select = $('#minstall'); if (!select) return;
    select.innerHTML = '<option value="">Auto (one installed copy)</option>' + (r.installations||[]).map(row=>`<option value="${esc(row.id)}">${esc(row.label)}</option>`).join('');
    if(r.selected && !(r.installations||[]).some(row=>row.id===r.selected)) select.add(new Option('Selected installation unavailable',r.selected));
    select.value = r.selected || '';
    $('#minstallstatus').textContent = r.selection_required ? 'Multiple copies found: choose the copy you play.' : (r.installations||[]).length ? 'Selection applies to the next capture. Save and clear retained combat before changing it.' : 'No registered installation found. Capture can still run; installed build remains unavailable.';
  };
  const refreshInstallations = async()=>{try{renderInstallations(await api('/api/meter/installations'));}catch(e){$('#minstallstatus').textContent=e.message;}};
  $('#minstallrefresh').onclick=refreshInstallations;
  $('#minstall').onchange=async()=>{try{renderInstallations(await api('/api/meter',{action:'installation',id:$('#minstall').value}));}catch(e){await refreshInstallations();$('#minstallstatus').textContent=e.message;}};
  refreshInstallations();
  const refreshInterfaces = async () => {
    try {
      const r = await api("/api/meter/interfaces");
      const select = $("#miface"), selected = select.value;
      select.innerHTML = `<option value="auto">Auto</option>` + (r.devices || (r.interfaces || []).map((name) => ({name, label: name}))).map((device) => `<option value="${esc(device.name)}">${esc(device.label)}${device.address ? " · " + esc(device.address) : ""}</option>`).join("");
      if ([...select.options].some((option) => option.value === selected)) select.value = selected;
    } catch (e) { $("#mnotice").textContent = "Could not list capture interfaces: " + e.message; }
  };
  $("#mifacesrefresh").onclick = refreshInterfaces;
  refreshInterfaces();
  const refreshNpcap = async () => {
    const node = $("#npcap"); if (!node) return;
    try {
      const r = await api("/api/npcap");
      if (!r.supported) { node.textContent = "Npcap setup is only needed on Windows."; return; }
      if (r.detection_error) { node.textContent = r.detection_error + " Installation status is unknown; check with your administrator before reinstalling."; return; }
      if (r.installed) { node.textContent = "Npcap is installed. Live Capture may need administrator permissions if Npcap was installed with administrator-only access."; return; }
      if (["finding", "downloading", "opening"].includes(r.status)) {
        node.textContent = { finding: "Finding the current official Npcap installer…", downloading: `Downloading Npcap ${r.version || ""}…`, opening: "Opening the Npcap installer…" }[r.status];
        setTimeout(refreshNpcap, 1200); return;
      }
      if (r.status === "installer-opened") {
        node.innerHTML = `Npcap ${esc(r.version || "")} installer is open. Finish its setup, then <button class="btn small" id="npcapcheck">Check again</button>.`;
        $("#npcapcheck").onclick = refreshNpcap;
        return;
      }
      const detail = r.error ? ` ${r.error}` : "";
      node.innerHTML = `Npcap is required for Live Capture. <button class="btn small" id="npcapinstall">Install Npcap</button>${esc(detail)}`;
      $("#npcapinstall").onclick = async () => {
        if (!window.confirm("Download the current Npcap installer from npcap.com and open it now? Npcap is installed separately and may ask for administrator approval.")) return;
        node.textContent = "Starting Npcap setup…";
        try { await api("/api/npcap", { action: "install" }); refreshNpcap(); }
        catch (e) { node.textContent = e.message; }
      };
    } catch (e) { node.textContent = "Could not check Npcap: " + e.message; }
  };
  refreshNpcap();
  $("#mstart").onclick = async () => {
    const button = $("#mstart");
    if (st.running) {
      button.disabled = true;
      try { $("#mnotice").textContent = "Stopping capture and saving logs…"; const result = await api("/api/meter", {action: "stop"}); renderMeter(result); $("#mnotice").textContent = result.diagnostics?.log_save_error ? "Capture stopped, but log saving failed: " + result.diagnostics.log_save_error : result.saved_log ? "Capture stopped. Session saved to " + result.saved_log : "Capture stopped. No session file was saved; check Combat Logs and capture diagnostics."; toast($("#mnotice").textContent, 6000); }
      catch (e) { $("#mnotice").textContent = e.message; }
      finally { button.disabled = false; }
      return;
    }
    const source = $("#msrc").value;
    if (source === "live" && !decoderPath) { $("#mnotice").textContent = "Choose a decoder .py file first."; return; }
    if (source !== "replay") {
      try {
        const setup = await api("/api/capture/setup");
        if (setup.detection_error) throw Error(setup.detection_error);
        if (setup.supported && !setup.installed) {
          if (window.confirm(setup.prompt || "Install packet-capture support now?")) {
            await api("/api/capture/setup", { action: "install" });
            $("#mnotice").textContent = `${setup.kind} setup is starting. Finish it, then press Start again.`;
          } else {
            $("#mnotice").textContent = `${setup.kind} is required before Live Capture can start.`;
          }
          return;
        }
      } catch (e) { $("#mnotice").textContent = "Could not check Npcap: " + e.message; return; }
    }
    const body = { action: "start", source, scope: $("#mscope").value, segment_gap: +$("#msegap").value || 10, decoder: source === "live" ? decoderPath : null,
      auto_port: source === "a2tools" && $("#mautoport").checked,
      automatic_splits: $("#mautosplit").checked,
      auto_finish:$('#mautofinish').checked,
      final_boss_ids:$('#mfinalboss').value.split(',').map(x=>x.trim()).filter(x=>/^\d+$/.test(x)).map(Number),
      record_packets: source !== "replay" && $("#mrecord").checked,
      iface: source !== "replay" && $("#miface").value !== "auto" ? $("#miface").value : null,
      host: source !== "replay" && $("#mhost").value !== "any" ? $("#mhost").value : null,
      port: source !== "replay" ? (+$("#mport").value || 50349) : null,
      target_mode: "allTargets",
      character_name: source === "a2tools" ? ($("#mchar").value || null) : null };
    button.disabled = true;
    try { st.pinnedSegment = ""; renderMeter(await api("/api/meter", body)); $("#mnotice").textContent = "Capture started. Waiting for combat data."; toast("Capture started"); } catch (e) { $("#mnotice").textContent = e.message; }
    finally { button.disabled = false; }
  };
  renderDiagnosticExport(st.diagnosticExport);
  $("#mdiag").onclick = async () => {
    try { st.diagnosticExport = await api("/api/meter", {action: "diagnostics"}); renderDiagnosticExport(st.diagnosticExport); $("#mnotice").textContent = `Diagnostic ZIP exported to ${st.diagnosticExport.file}`; }
    catch (e) { $("#mnotice").textContent = e.message; }
  };
  $("#movl").onclick = async () => {
    $("#mnotice").textContent = "opening overlay…";
    try {
      const r = await api("/api/overlay", {});          // native transparent window (bundled on Windows)
      if (r.native) { $("#mnotice").textContent = r.already_open ? "overlay is already open" : "overlay opened in a transparent window"; return; }
    } catch (e) { /* fall through to a plain browser window */ }
    st.overlayPopup=window.open("/overlay", "a2overlay", "width=300,height=430");
    $("#mnotice").textContent = "overlay opened in a window";
  };
  $("#msave").onclick = async () => {
    $("#mnotice").textContent = "saving…";
    try { const r = await api("/api/meter", { action: "save" }); $("#mnotice").innerHTML = `saved as encounter #${r.id} — <a href="#/combat">open in Combat Logs</a>`; }
    catch (e) { $("#mnotice").textContent = e.message; }
  };
  $("#mexport").onclick = async () => {
    $("#mnotice").textContent = "exporting…";
    try { const r = await api("/api/meter", { action: "export" }); $("#mnotice").textContent = `exported ${r.file}`; }
    catch (e) { $("#mnotice").textContent = e.message; }
  };
  $("#mupload").onclick = async () => {
    $("#mnotice").textContent = "uploading…";
    try { const r = await runJob("/api/meter", { action: "upload" }, lines => { if (lines.length && $("#mnotice")) $("#mnotice").textContent = lines[lines.length - 1]; }); $("#mnotice").innerHTML = r.url ? `uploaded — <a href="${esc(r.url)}" target="_blank" rel="noopener">open shared log</a>` : "uploaded"; }
    catch (e) { $("#mnotice").textContent = e.message; }
  };
  $("#mshot").onclick = async () => {
    $("#mnotice").textContent = "capturing screenshot…";
    try { const r = await api("/api/meter", { action: "screenshot" }); $("#mnotice").textContent = `screenshot saved to ${r.file}`; }
    catch (e) { $("#mnotice").textContent = e.message; }
  };
  // Keep action feedback visible while polling updates the live readings.
  const actionLabels = {mdiag: "Exporting diagnostic ZIP…", mexport: "Exporting combat log…", msave: "Saving combat log…", mupload: "Uploading combat log…", mshot: "Saving screenshot…", msplit: "Splitting encounter…", mfinishrun: "Finishing run…", mhide: "Hiding overlay…", movl: "Opening overlay…", mifacesrefresh: "Refreshing interfaces…"};
  for (const [id, pending] of Object.entries(actionLabels)) {
    const button = $("#" + id), handler = button.onclick;
    button.onclick = async () => {
      if (button.disabled) return;
      const label = button.textContent, notice = $("#mnotice");
      button.disabled = true; button.setAttribute("aria-busy", "true");
      button.textContent = pending; notice.textContent = pending;
      try {
        await handler();
        if (notice.textContent === pending) notice.textContent = id === "mifacesrefresh" ? "Capture interfaces refreshed." : "Action completed.";
        toast(notice.textContent, 6000);
      } catch (e) { notice.textContent = "Action failed: " + e.message; toast(notice.textContent, 6000); }
      finally { button.disabled = false; button.removeAttribute("aria-busy"); button.textContent = label; }
    };
  }
  const poll = async () => {
    if (!location.hash.startsWith("#/meter")) return;
    try { renderMeter(await api("/api/meter")); } catch (e) {}
    setTimeout(poll, st.running ? 700 : 2500);
  };
  const initial = await api("/api/meter").catch(() => ({snapshot: {players: []}}));
  if (initial.source) { $("#msrc").value = initial.source; live(); }
  $("#mrecord").checked = !!initial.recording?.enabled;
  renderMeter(initial);
  poll();
}
function renderDiagnosticExport(r) {
  const target = $("#mdiagresult"); if (!r || !target) return;
  if (target.dataset.savedFile === r.file) return;
  target.dataset.savedFile = r.file;
  target.innerHTML = `<a class="btn small primary" href="${esc(r.download_url)}" download>Download diagnostic ZIP</a> ${r.records} TCP payload records.<br>Last saved capture: <span style="overflow-wrap:anywhere">${esc(r.file)}</span>${r.records ? "" : "<br>Enable TCP recording before Start, then fight briefly and export again."}`;
}
function renderMeter(s) {
  if($("#mdriverstats")) {const d=s.diagnostics || {};$("#mdriverstats").textContent=d.pcap_stats_sampled?`Driver counters${d.pcap_stats_partial?' (partial coverage)':''}: ${d.pcap_received || 0} received, ${d.pcap_dropped || 0} capture-buffer drops, ${d.pcap_if_dropped || 0} interface/driver drops. Zero does not prove loss-free capture; counts can include other traffic.`:'Driver counters: unavailable or not sampled. TCP reassembly monitoring is separate.';}

  if($("#mcombinepets")) $("#mcombinepets").checked=s.combine_pets!==false;
  if($('#minstall')) $('#minstall').disabled = !!s.installation_locked;
  if($("#mautometa")) { const m=s.automatic_metadata || {}; $("#mautometa").textContent = `Installed game build: ${m.installed_build || m.status || "unavailable"}${m.installed_build_source ? " ("+m.installed_build_source+")" : ""}. Comparison build: ${m.game_patch ? (m.installed_build || m.game_patch) : "unavailable"}. Automatic region: ${m.region || (m.region_status === "ready" ? "waiting for recorded server ID" : m.region_status) || "unavailable"}. Zone: ${(s.automatic_context || {}).zone || "not identified"}. Content: ${(s.automatic_context || {}).encounter_type || "not identified"}. Difficulty: ${(s.automatic_context || {}).difficulty || "not identified"}. Map / instance IDs: ${s.catalog_coverage?.map_id || "not recorded"} / ${s.catalog_coverage?.instance_id || "not recorded"}. ${s.catalog_coverage?.unmapped?.length || 0} unmapped IDs in this view (included in diagnostics). ${m.reason ? m.reason+" " : ""}Build numbers identify comparison groups; launcher namespaces remain separate.`; }
  const st = S.meter; st.running = !!s.running;
  if($("#mrun") && s.run)$("#mrun").textContent=`Run ${s.run.id} · ${s.run.closed?"finished/boundary recorded; waiting for next fight":"recording"}${s.run.end_reason?" · "+s.run.end_reason:""}`;
  if (s.diagnostic_export) st.diagnosticExport = s.diagnostic_export;
  renderDiagnosticExport(st.diagnosticExport);
  if ($("#mdiagerror")) $("#mdiagerror").textContent = [s.recording?.error ? `TCP recording stopped writing: ${s.recording.error}. ${s.recording.discarded_records || 0} records were not saved. Free disk space and export the retained data.` : "", s.diagnostics?.archive_error ? `Could not save diagnostic ZIP: ${s.diagnostics.archive_error}. Use Export capture diagnostics to retry before starting another capture.` : "", s.diagnostics?.recording_cleanup_error ? `Raw diagnostic cleanup failed: ${s.diagnostics.recording_cleanup_error}. The raw file remains in the diagnostics folder.` : ""].filter(Boolean).join(" ");
  const button = $("#mstart");
  if (button) {
    button.textContent = st.running ? "Stop" : "Start";
    button.classList.toggle("danger", st.running);
    button.classList.toggle("primary", !st.running);
    button.setAttribute("aria-pressed", String(st.running));
  }
  const who=s.identity;
  if($("#midentity"))$("#midentity").textContent=who?.id ? `${who.verified ? "Detected automatically" : "Matched name override"}: ${who.name || "Player #"+who.id}${who.serverId ? " · server "+who.serverId : ""} · combat entity #${who.id} (changes between instances)` : "Auto-detecting your character. Start before entering an instance or use the optional name override.";
  if($("#msaved"))$("#msaved").textContent=s.diagnostics?.log_save_error || ((s.diagnostics?.archive_parts_saved ? `${s.diagnostics.archive_parts_saved} earlier archive part(s) saved in Combat Logs. Live view/export contains the current part. ` : "") + (s.saved_log ? "Latest saved part: "+s.saved_log : "Current part checkpoints every 15 seconds and saves on Stop."));
  if(s.snapshot?.players?.length && $("#mlog-review") && !st.reviewLoading && Date.now()-(st.reviewAt || 0)>4000) {
    st.reviewLoading=true;st.reviewAt=Date.now();
    api("/api/meter/log").then(doc=>{const target=$("#mlog-review");if(!target)return;if(st.liveReviewRoot!==target){if(st.liveReview)st.liveReview.dispose();st.liveReview=A2CombatReview.mount(target,doc,localReviewOptions());st.liveReviewRoot=target;}else st.liveReview.update(doc);}).catch(()=>{}).finally(()=>{st.reviewLoading=false;});
  }
  const record = $("#mrecord"); if (record) record.disabled = st.running;
  if ($("#mclear")) $("#mclear").disabled = st.running;
  const recordStatus = $("#mrecordstatus");
  if (recordStatus) recordStatus.textContent = s.recording?.enabled ? `${s.recording.records || 0} TCP payload records · ${((s.recording.disk_bytes || 0)/1048576).toFixed(1)} MiB on disk · no record limit` : "TCP recording is off";
  const snap = s.snapshot || { players: [] }, msg = $("#mmsg");
  if ($("#mscope") && snap.scope) $("#mscope").value = snap.scope;
  const selector = $("#msegments");
  if (selector && snap.segments && document.activeElement !== selector) {
    const options = `<option value="">Latest combat</option><option value="all">Whole session</option>` + snap.segments.map((segment) => `<option value="${esc(segment.id)}">${esc(segment.label)} · ${new Date(segment.start).toLocaleTimeString()} · ${segment.duration.toFixed(1)}s</option>`).join("");
    if (selector.innerHTML !== options) selector.innerHTML = options;
    selector.value = st.pinnedSegment || (snap.selected_segment === "all" ? "all" : "");
  }
  if (msg) { if (s.error) msg.textContent = s.error; else { const d = s.diagnostics || {}; msg.textContent = s.running ? `${s.snapshot?.paused ? "Paused DPS · capture continues" : "Recording"} · ${d.packets || 0} TCP packets · ${d.decoded_events || 0} combat events${d.port ? " · port " + d.port : d.auto_port ? " · detecting game port" : ""}` : "Stopped"; } }
  const view = $("#mview"); if (!view) return;
  if (!snap.players.length) {
    st.lastMeterRender = null;
    view.innerHTML = win("Meter", "", `<div class="empty">${s.running ? ((s.diagnostics?.packets || 0) ? (s.diagnostics?.forwarded ? "The game stream is reaching the decoder but no combat events have been recognized. Enable TCP recording before Start and export capture diagnostics after fighting briefly." : "Packets are arriving. Waiting for a recognized game stream — enter combat. Enable TCP recording before Start to investigate.") : "No packets yet. Check capture support, adapter permissions and your interface selection, then enter combat.") : "No data yet — choose a source and press Start."}${snap.warning ? "<p>" + esc(snap.warning) + "</p>" : ""}${s.diagnostics?.warnings?.length ? "<p>" + esc(s.diagnostics.warnings.join("; ")) + "</p>" : ""}</div>`);
    return;
  }
  const mx = Math.max(...snap.players.map((p) => p.dps), 1);
  const selected = snap.players.findIndex((player) => (player.key || player.id) === st.selectedPlayerKey);
  st.sel = selected >= 0 ? selected : 0;
  st.selectedPlayerKey = snap.players[st.sel].key || snap.players[st.sel].id;
  const signature = JSON.stringify([snap, st.selectedPlayerKey, _ptab]);
  if (st.lastMeterRender === signature) return;
  st.lastMeterRender = signature;
  const rows = snap.players.map((p, i) => `<div class="pm ${i === st.sel ? "on" : ""}" data-sel="${i}">
      <div class="nmc"><b>${esc(p.name)}</b> <span class="muted small">${esc(cap(p.class || ""))}</span></div>
      <div class="bar"><i style="width:${100 * p.dps / mx}%"></i><span>${kfmt(p.dps)}/s · ${pct(p.share, 0)}</span></div></div>`).join("");
  const enemyTable = snap.enemies?.length ? win("Enemies", "select an enemy to show each player's damage against it", `<table class="t"><tr><th>Enemy</th><th>Party damage dealt</th><th>Party DPS</th></tr>${snap.enemies.map((enemy) => `<tr class="${enemy.key === snap.selected_enemy ? "sel" : ""}"><td><button class="btn small" data-enemy="${esc(enemy.key)}">${esc(enemy.name)}</button></td><td>${kfmt(enemy.damage)}</td><td>${kfmt(enemy.dps)}</td></tr>`).join("")}</table>`) : "";
  replaceMeterHtml(view, enemyTable + win("Players", `${esc(snap.boss || "")}${snap.boss ? " · " : ""}${(snap.duration || 0).toFixed(0)}s · ${kfmt(snap.dps || 0)} raid DPS`,
    `<div class="pmeters">${rows}</div>`) + `<div id="pbd">${renderParse(parseFromMeter(snap, st.sel))}</div>`);
  $$("[data-enemy]").forEach((el) => (el.onclick = async () => { try { renderMeter(await api("/api/meter", {action: "view", enemy: el.dataset.enemy})); } catch (e) { $("#mnotice").textContent = e.message; } }));
  $$("[data-sel]").forEach((el) => (el.onclick = () => {
    st.sel = +el.dataset.sel; st.selectedPlayerKey = snap.players[st.sel].key || snap.players[st.sel].id;
    replaceMeterHtml($("#pbd"), renderParse(parseFromMeter(snap, st.sel)));
    $$("[data-sel]").forEach((x) => x.classList.toggle("on", +x.dataset.sel === st.sel));
  }));
}

// Saved optimizer/advice snapshots survive process and browser restarts.
async function pageHistory(){
 app().innerHTML=win('Saved results','Previous optimizations and advice, stored on this computer',`<div class="row"><label>Import previous result <input id="result-import" type="file" accept=".json"></label><span id="history-msg" class="small muted"></span></div><div id="history-list"></div>`)+`<div id="history-view"></div>`;
 const refresh=async()=>{const rows=await api('/api/history');$('#history-list').innerHTML=rows.length?`<table class="t"><tr><th>Run</th><th>Recorded</th><th></th></tr>${rows.map(r=>`<tr><td>${esc(r.title)}</td><td>${new Date(r.created*1000).toLocaleString()}</td><td><button class="btn small" data-history="${r.id}">Open</button><button class="btn small" data-history-export="${r.id}">Export</button></td></tr>`).join('')}</table>`:'<p>No saved runs yet. Completed optimizations and advice save here automatically.</p>';
 document.querySelectorAll('[data-history]').forEach(b=>b.onclick=async()=>{try{const d=await api('/api/history?id='+b.dataset.history);const box=$('#history-view');box.innerHTML=`<p class="small muted">Saved result from ${new Date(d.created*1000).toLocaleString()}. This is a snapshot; advice may change as gear or game data changes.</p>`;if(d.kind==='advice-text')box.innerHTML+=`<pre class="diff">${esc(d.result.text)}</pre>`;else if(d.kind==='advice'){S.gear ||= {};box.innerHTML+='<div id="gout">'+renderAdvice(d.result)+'</div>';bindAdvice(d.result);}else{const v=d.kind==='optimize-character'?d.result.optimized:d.result;box.innerHTML+='<div id="saved-windows"></div>';renderWindows(v,{win:'overview'},$('#saved-windows'));}box.scrollIntoView({behavior:'smooth'});}catch(e){$('#history-msg').textContent=e.message;}});
 document.querySelectorAll('[data-history-export]').forEach(b=>b.onclick=async()=>{const d=await api('/api/history?id='+b.dataset.historyExport),url=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='aion2calc-result-'+b.dataset.historyExport+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});};
 $('#result-import').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>20*1024*1024)throw Error('Result exceeds 20 MiB');const result=JSON.parse(await file.text());await api('/api/history',result);await refresh();$('#history-msg').textContent='Result imported';}catch(e){$('#history-msg').textContent=e.message;}};
 await refresh();
}

// ------------------------------------------------------------- gear & advice
const sp = (x) => (x == null ? "—" : (x >= 0 ? "+" : "") + (100 * x).toFixed(1) + "%");
async function pageGear() {
  const st = S.gear || (S.gear = {});
  const chars = await api("/api/characters").catch(() => []);
  app().innerHTML = `<section class="win"><div class="wh"><h2>Gear &amp; advice</h2><a class="btn small" href="#/history">Saved advice</a><span class="sub">what to wear from your inventory, goal gear, upgrade path, arcana, pantheon, genus insight — on simulated DPS</span></div>
    <div class="wb">${chars.length ? `<div class="row"><select id="gchar">${chars.map((c) => `<option value="${esc(c.key)}" ${c.key === st.key ? "selected" : ""}>${esc(c.name)} · ${esc(c.class_name)} · ${esc(c.region)}</option>`).join("")}</select>
      <button class="btn primary" id="gadv">Run advice</button><span id="gmsg" class="small muted"></span></div>
      <p class="small faint">Import the character on My Character first. The official page shows only equipped items: add bag and warehouse items below so the planner can use them. Fights you import on Combat Logs are matched to the gear the character wore and calibrate the model.</p>` :
      '<div class="note">Import a character on My Character first.</div>'}
    <div id="ginv"></div></div></section><div id="gout"></div>`;
  if (!chars.length) return;
  const key = () => (st.key = $("#gchar").value);
  const showInv = async () => {
    const inventoryKey=key();
    const inv = await api("/api/inventory?character=" + encodeURIComponent(inventoryKey));
    if($("#gchar")?.value!==inventoryKey)return;
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
      <div id="genus-editor"></div>
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
    const genusRoot=$('#genus-editor');
    A2GenusEditor.mount(genusRoot,genus,async draft=>{
      const saved=await api('/api/inventory/genus',{character:inventoryKey,genus:draft});
      st.genusRevision=(st.genusRevision||0)+1;
      if(st.key===inventoryKey&&genusRoot.isConnected){st.inv=saved;st.adv=null;
      $('#gout').innerHTML='<p class="note">Genus lines saved. Run advice again to update recommendations.</p>';}
      return saved.genus||{};
    });
  };
  $("#gchar").onchange = () => { st.adv = null; $("#gout").innerHTML = ""; showInv(); };
  $("#gadv").onclick = async () => {
    $("#gout").innerHTML = '<div class="empty"><span class="spinner"></span></div>';
    const characterKey=key(),revision=st.genusRevision||0,run=st.adviceRun=(st.adviceRun||0)+1;
    try {const advice=await runJob("/api/advice",{character:characterKey},lines=>{if($('#gmsg')&&st.key===characterKey&&st.adviceRun===run)$('#gmsg').textContent=lines[lines.length-1]||'';});
      if(!$('#gout')||st.key!==characterKey||st.adviceRun!==run)return;
      if((st.genusRevision||0)!==revision){$('#gout').innerHTML='<p class="note">Genus allocations changed during calculation. Run advice again.</p>';return;}
      st.adv=advice;$('#gout').innerHTML=renderAdvice(advice);bindAdvice(advice);
    }catch(e){if($('#gout')&&st.key===characterKey&&st.adviceRun===run)$('#gout').innerHTML=`<div class="note">${esc(e.message)}</div>`;}
  };
  await showInv();
  if (st.adv) { $("#gout").innerHTML = renderAdvice(st.adv); bindAdvice(st.adv); }
}

const SKILL_ICON = (id) => (id ? "https://metabot.gg/web/aion2/skills/" + id + ".webp" : "");
const DOLL_LEFT = ["MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt"];
const DOLL_RIGHT = ["Necklace", "Earring1", "Earring2", "Ring1", "Ring2", "Bracelet1", "Bracelet2", "Amulet", "Rune1", "Rune2"];
const SLOT_NAME = { MainHand: "Main hand", SubHand: "Off-hand", Torso: "Chest", Pants: "Legs", Cape: "Cloak", Earring1: "Earring", Earring2: "Earring",
  Ring1: "Ring", Ring2: "Ring", Bracelet1: "Bracelet", Bracelet2: "Bracelet", Rune1: "Rune", Rune2: "Rune" };
const itemIcon = (it, cls = "") => `<div class="icon with-fallback ${cls}" data-grade="${esc(it?.grade || "")}"><span class="asset-placeholder" aria-hidden="true">◇</span>${it?.icon ? `<img src="${icon(it.icon)}" alt="${esc(it.name || "Equipment")}" loading="lazy" onerror="this.hidden=true">` : ""}${it?.enchant ? `<span class="lv">+${it.enchant}</span>` : ""}</div>`;
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

function advSpecialties(a) {
  const rows=a.skill_specialties;
  if(!rows)return win("Skill specialties", "", '<p class="muted">This older saved advice has no specialty snapshot. Recalculate advice to include it.</p>');
  const text=rows.map(r=>`${r.skill} · effective Lv ${esc(r.level)}: ${r.effects.filter(e=>e.selected).map(e=>`#${esc(e.number)}: ${e.text} (effect Lv ${esc(e.unlock)})`).join('; ')||'None unlocked/selected'}`).join('\n');
  return win("Skill specialties", "recommended for your imported equipped build", `<p class="small muted">Effective levels include trained, Daevanion and gear bonuses. These are simulated recommendations; the official profile does not show your selected specialties. Stigma effects activate automatically. Recalculate after changing gear or points.</p><table class="t"><tr><th>Skill / effective level</th><th>Recommended specialties</th><th>Next unlock</th></tr>${rows.map(r=>`<tr><td>${esc(r.skill)} · Lv ${esc(r.level)}<br><span class="small muted">${r.automatic?'Automatic stigma effects':esc(r.slots)+' selection slot(s)'}</span></td><td>${r.effects.filter(e=>e.selected).map(e=>`<div><b>#${esc(e.number)}</b> ${esc(e.text)} <span class="faint">(effect Lv ${esc(e.unlock)})</span></div>`).join('')||'None unlocked/selected'}<details><summary>All effects and requirements</summary>${r.effects.map(e=>`<p class="small">#${esc(e.number)} · Lv ${esc(e.unlock)} · ${e.selected?'Recommended':e.available?'Available':'Locked'}: ${esc(e.text)}</p>`).join('')}</details></td><td>${r.next_effect_level?'Effect Lv '+esc(r.next_effect_level):'All effects unlocked'}${r.next_slot_level?'<br>Selection slot Lv '+esc(r.next_slot_level):''}</td></tr>`).join('')}</table>`, {key:'adv-specialties',copy:text});
}
function renderAdvice(a) {
  const r = a.rotation;
  const rot = r.fights ? `<p>${r.fights} fight(s), idle ${pct(r.idle_share, 0)} of the time.</p>${r.under_cast.slice(0, 6).map((t) => `<div class="tip">${esc(t.text)}</div>`).join("")}
    ${r.specs.map((d) => `<div class="tip">${esc(d.skill)}: specs ${esc(d.yours)} in your fights, ${esc(d.optimal)} in the optimized build</div>`).join("")}` : '<p class="muted">No saved fights for this character: import AbyssLogs links on Combat Logs.</p>';
  return advTop(a) + advSpecialties(a) + advDoll(a) + advPath(a) + advArcana(a) + advTitles(a) + advPantheon(a) + advGenus(a, a.inventory_snapshot || S.gear.inv) +
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
    <div class="setrow"><div class="lbl">Combat class colors</div><div id="class-colors"></div></div><div class="setrow"><div class="lbl">Game database</div><div>${n0(s.db.items)} items · last update ${s.db.last_sync ? new Date(s.db.last_sync.at * 1000).toLocaleString() : "never"} <button class="btn small" id="sync">Check now</button> <button class="btn small" id="asset-report">Export image coverage</button> <button class="btn small" id="retry-images">Retry images</button><span id="asset-msg" class="small muted" role="status" aria-live="polite"></span></div></div>
    <div class="setrow"><div class="lbl">Updates</div><div><label><input type="checkbox" id="autoupd" ${ui.auto_update !== false ? "checked" : ""}> check and prompt for updates on launch</label></div></div>
    <div class="setrow"><div class="lbl">Version</div><div>Aion 2 Calc ${esc(s.version)} ${s.update ? `· version ${esc(s.update.version)} available <button class="btn small" id="instupd">Install now</button> <a href="${esc(s.update.url)}" target="_blank" rel="noopener">release notes</a>` : '<span class="muted">· up to date</span>'} <span id="updmsg" class="small muted"></span></div></div>
    <div class="setrow"><div class="lbl">Community</div><div><a href="${DISCORD}" target="_blank" rel="noopener">Join the aion2calc Discord</a> — questions, builds and help</div></div>
    <div class="setrow"><div class="lbl">Stop the app</div><div><button class="btn small" id="quit2">Quit aion2calc</button></div></div>
    <div class="setrow" style="border-top:1px solid var(--line);margin-top:8px;padding-top:10px"><div class="lbl">Author</div><div class="muted">Spirited - Zikel : Asmodian&nbsp;&nbsp;|&nbsp;&nbsp;Legion: WhaleWatch</div></div>`);
  if(ui.combat_colors)localStorage.setItem("a2-combat-colors",JSON.stringify(ui.combat_colors));
  A2CombatReview.settings($("#class-colors"),pref=>api("/api/ui",{combat_colors:pref}));
  $$("[data-th]").forEach((b) => (b.onclick = () => { setTheme(b.dataset.th); pageSettings(); }));
  $("#appwin").onchange = () => api("/api/ui", { app_window: $("#appwin").checked }).then(() => toast("Saved"));
  $("#autoupd").onchange = () => api("/api/ui", { auto_update: $("#autoupd").checked }).then(() => toast("Saved"));
  if ($("#instupd")) $("#instupd").onclick = async () => {
    $("#instupd").disabled = true;
    $("#updmsg").textContent = "Downloading and checking the installer…";
    try {
      const r = await api("/api/update", {});
      if (r.status === "launching") {
        document.body.innerHTML = '<div class="empty" style="margin-top:20vh">Aion 2 Calc is closing. The installer will open in a moment.</div>';
        return;
      }
      $("#instupd").disabled = false;
      $("#updmsg").textContent = { "launch-failed": "The installer helper did not start. Your app is still running; open the updates folder to run the setup file.", applying: "installing — the app will restart", launching: "closing the app, then opening the installer — follow the prompts (choose “More info → Run anyway” if Windows warns)", downloaded: "downloaded — open your data folder’s “updates” to run it", "download-failed": "download failed", "up-to-date": "already up to date" }[r.status] || r.status;
    } catch (e) { if ($("#updmsg")) $("#updmsg").textContent = e.message; if ($("#instupd")) $("#instupd").disabled = false; }
  };
  $$("[data-open]").forEach((b) => (b.onclick = () => api("/api/open", { what: b.dataset.open }).catch((e) => toast(e.message))));
  $("#ssave").onclick = async () => {
    await api("/api/logserver", { url: $("#surl").value, key: $("#skey").value || null, visibility: $("#svis").value });
    $("#smsg").textContent = "saved · checking…";
    // The app (not the browser) probes the server, so CORS and http/https rules don't give a false negative.
    try {
      const r = await api("/api/logserver/check");
      $("#smsg").textContent = r.ok
        ? "saved · server reachable" + (r.name ? " — " + esc(r.name) : "")
        : "saved · can't reach the server" + (r.detail ? " (" + esc(r.detail) + ")" : "");
    } catch (e) { $("#smsg").textContent = "saved · could not check: " + e.message; }
  };
  $("#sync").onclick = async () => { await api("/api/sync", {}); toast("Checking for game updates"); };
  $('#asset-report').onclick = async () => {
    const button=$('#asset-report'),message=$('#asset-msg');button.disabled=true;message.textContent='Collecting image references…';
    try {const data=await api('/api/assets');data.browser_images=window.A2AssetHealth?.report();const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='aion2-asset-coverage.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message.textContent='Image coverage export requested. Check your Downloads folder.';}
    catch(e){message.textContent='Could not export image coverage: '+e.message;}finally{button.disabled=false;}
  };
  $('#retry-images').onclick=()=>{window.A2AssetHealth?.retry();$('#asset-msg').textContent='Image retries enabled. Reopen the affected view to reload its images.';};
  $("#quit2").onclick = () => $("#quit").click();
}
setInterval(() => fetch("/api/ping", { method: "POST" }).catch(() => {}), 20000);

async function pageNews(){
  app().innerHTML='<div id="official-news"></div>';
  A2News.mount($('#official-news'),{api:communityAPI});
}

// ------------------------------------------------------------- router
async function route() {
  const page = (location.hash.replace(/^#\//, "") || "planner").split("/")[0];
  $$(".nav a").forEach((a) => a.classList.toggle("on", a.dataset.page === (page === "combat-log" ? "combat" : page)));
  if(page!=="combat-log" && S.combat.review){S.combat.review.dispose();S.combat.review=null;}
  try {
    if (page === "character") await pageCharacter();
    else if (page === "history") await pageHistory();
    else if (page === "gear") await pageGear();
    else if (page === "settings") await pageSettings();
    else if (page === "combat") await pageCombat();
    else if (page === "combat-log") await pageCombatLog();
    else if (page === "raid") await pageRaid();
    else if (page === "meter") await pageMeter();
    else if (page === "database") await pageDatabase();
    else if (page === "news") await pageNews();
    else await pagePlanner();
  } catch (e) { app().innerHTML = `${page==="combat-log"?'<p><a class="btn small" href="#/combat">← Back to combat logs</a></p>':""}<div class="note">${esc(e.message)}</div>`; }
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
    if (s.update && s.update_prompt !== false && !sessionStorage.getItem("update-prompted:" + s.update.version)) {
      sessionStorage.setItem("update-prompted:" + s.update.version, "1");
      setTimeout(async () => {
        if (!confirm(`Aion 2 Calc ${s.update.version} is ready. Install it now?`)) return;
        try {
          const r = await api("/api/update", {});
          if (r.status === "launching") document.body.innerHTML = '<div class="empty" style="margin-top:20vh">Aion 2 Calc is closing. The installer will open in a moment.</div>';
          else toast({ downloaded: "Update downloaded. Open the updates folder to install it.", "download-failed": "The update download failed." }[r.status] || r.status);
        } catch (e) { toast("Update failed: " + e.message); }
      }, 250);
    }
    $("#quit").title = `Stop the app (version ${s.version || ""})`;
    setTimeout(syncPill, running ? 2500 : 20000);
  } catch (e) { setTimeout(syncPill, 20000); }
}
$("#quit").onclick = async () => {
  if (!confirm("Stop aion2calc? Start it again from the Start menu or desktop shortcut.")) return;
  try { localStorage.setItem("aion2calc-closing", String(Date.now())); } catch (e) { /* native overlay is closed by the server */ }
  await api("/api/quit", {}).catch(() => {});
  document.body.innerHTML = '<div class="empty" style="margin-top:20vh">aion2calc has stopped. You can close this tab.</div>';
  setTimeout(() => window.close(), 250);
};
route();
syncPill();
