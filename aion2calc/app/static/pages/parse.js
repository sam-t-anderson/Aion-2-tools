/* The AionFlex-style breakdown of a fight, and the combat review's options, shared by the Live Meter and
   Combat Logs. */
"use strict";

function lineChart(per, roll) {
  const W = 1000,
    H = 190,
    n = per.length || 1,
    mx = Math.max(...per, ...roll, 1);
  const bars = per
    .map(
      (v, i) =>
        `<rect x="${(i / n) * W}" y="${H - (v / mx) * H}" width="${Math.max(1, W / n - 1)}" height="${(v / mx) * H}" style="fill:var(--chart-bar)"/>`,
    )
    .join("");
  const pts = roll.map((v, i) => `${((i + 0.5) / n) * W},${H - (v / mx) * H}`).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}<polyline points="${pts}" fill="none" style="stroke:var(--chart-line)" stroke-width="2"/></svg>
    <div class="row small muted"><span>bars: damage per second</span><span style="color:var(--gold)">line: 10 s average</span><span>peak 10 s: ${n0(Math.max(...roll))}</span></div>`;
}
// One parse card (header stats · DPS/Defense/Accuracy tabs · damage-source donut · per-skill table ·
// rotation strip), shared by the Combat Logs view and the Live Meter. Fed by a normalized object so
// a saved log and a live snapshot render identically. No paid tiers — every panel is shown.
const PCOL = ["#e8cf8e", "#58a6ff", "#b18cff", "#6fcf7a", "#e68a5a", "#5ad1c4", "#e45a8a", "#d7c15a", "#8a92a8"];
let _ptab = "dps";
const skillIcon = (id) =>
  id ? icon("https://metabot.gg/web/aion2/skills/" + Math.floor(Number(id) / 10000) * 10000 + ".webp") : "";
const SKILL_PLACEHOLDER =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" rx="4" fill="#263048"/><path d="M12 4L19 12L12 20L5 12Z" fill="none" stroke="#e8cf8e"/></svg>',
  );
function skillArt(id, name = "") {
  const source = skillIcon(id);
  return `<img class="skill-art" width="24" height="24" data-skill-source="${esc(source)}" src="${esc(source || SKILL_PLACEHOLDER)}" title="${esc(name)}" alt="" onerror="this.onerror=null;this.src=SKILL_PLACEHOLDER">`;
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
  const R = 86,
    r = 55,
    cx = 95,
    cy = 95;
  let a0 = -Math.PI / 2;
  const seg = parts
    .map((p) => {
      const frac = Math.min((p.value || 0) / tot, 0.99999);
      if (frac <= 0) return "";
      const a1 = a0 + frac * 2 * Math.PI,
        big = frac > 0.5 ? 1 : 0;
      const x0 = cx + R * Math.cos(a0),
        y0 = cy + R * Math.sin(a0),
        x1 = cx + R * Math.cos(a1),
        y1 = cy + R * Math.sin(a1);
      const xi1 = cx + r * Math.cos(a1),
        yi1 = cy + r * Math.sin(a1),
        xi0 = cx + r * Math.cos(a0),
        yi0 = cy + r * Math.sin(a0);
      a0 = a1;
      return `<path d="M${x0} ${y0} A${R} ${R} 0 ${big} 1 ${x1} ${y1} L${xi1} ${yi1} A${r} ${r} 0 ${big} 0 ${xi0} ${yi0} Z" fill="${p.color}"/>`;
    })
    .join("");
  return `<div class="pdonut"><svg viewBox="0 0 190 190">${seg}</svg><div class="mid"><b>${center[0]}</b><span>${center[1]}</span></div></div>`;
}
function renderParse(d) {
  if (!d) return "";
  const at = _ptab;
  const skills = (d.skills || []).slice().sort((a, b) => (b.damage || 0) - (a.damage || 0));
  const totDmg = d.dmg || skills.reduce((s, x) => s + (x.damage || 0), 0) || 1;
  const top = skills.slice(0, 5),
    rest = skills.slice(5);
  const otherDmg = rest.reduce((s, x) => s + (x.damage || 0), 0);
  const parts = top.map((s, i) => ({ label: s.skill, value: s.damage || 0, color: PCOL[i % PCOL.length] }));
  if (otherDmg > 0) parts.push({ label: `Other (${rest.length})`, value: otherDmg, color: PCOL[8] });
  const topList = parts
    .map(
      (p) =>
        `<div class="trow"><span class="sw" style="background:${p.color}"></span><span class="nm">${esc(p.label)}</span><span class="pc">${Math.round((100 * p.value) / totDmg)}%</span></div>`,
    )
    .join("");
  const mxDmg = Math.max(...skills.map((s) => s.damage || 0), 1);
  const srows = skills
    .map(
      (s) => `<tr><td class="nm">${skillArt(s.skill_id, s.skill)}${esc(s.skill)}</td>
    <td>${s.hits ?? "—"}</td><td>${kfmt(s.dps)}</td><td>${kfmt(s.avg)}</td><td>${s.min == null ? "—" : kfmt(s.min)}</td><td>${s.max == null ? "—" : kfmt(s.max)}</td>
    <td class="dmg"><i style="width:${(100 * (s.damage || 0)) / mxDmg}%"></i><span>${kfmt(s.damage)}<span class="pcpct">${Math.round((100 * (s.damage || 0)) / totDmg)}%</span></span></td></tr>`,
    )
    .join("");
  const spark = d.timeline
    ? `<div style="margin:4px 0 12px">${lineChart(d.timeline.per_second, d.timeline.rolling10)}</div>`
    : "";
  const dpsPanel = `<div class="ppanel" data-pane="dps"${at === "dps" ? "" : " hidden"}>
    ${d.highest != null ? `<div class="phi"><div class="k">Highest hit</div><div class="v">${kfmt(d.highest)}</div></div>` : ""}
    <div class="psplit">${pdonut(parts.length ? parts : [{ value: 1, color: "#2a3045" }], [kfmt(d.dps), "DPS"])}<div class="ptop">${topList || '<span class="muted">No skills recorded.</span>'}</div></div>
    ${spark}<table class="pskills"><tr><th>Skill</th><th>Hit</th><th>DPS</th><th>Avg</th><th>Min</th><th>Max</th><th>Damage</th></tr>${srows}</table></div>`;
  const rate = (x) => (x == null ? "—" : Math.round(100 * x) + "%");
  const rc = (k, v) => `<div class="rc"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const accPanel = `<div class="ppanel" data-pane="acc"${at === "acc" ? "" : " hidden"}><div class="prates">
    ${rc("Hit chance", "Unavailable")}${rc("Crit", rate(d.rates.crit))}${rc("Back", rate(d.rates.back))}${rc("Front", rate(d.rates.front))}${rc("Double", rate(d.rates.double))}${rc("Perfect", rate(d.rates.perfect))}${rc("Multi", rate(d.rates.multi))}${rc("Parried", rate(d.rates.parry))}</div><p class="small muted">Rates use decoded outgoing hits. Hit chance requires attempted attacks and misses, which this source does not currently provide.</p></div>`;
  const defense = d.incoming;
  const defPanel = `<div class="ppanel" data-pane="def"${at === "def" ? "" : " hidden"}>${
    defense
      ? `<div class="prates">${rc("Damage taken", kfmt(defense.damage))}${rc("Incoming hits", n0(defense.hits))}${rc("Parried hits", n0(defense.parries))}${rc("Healing done", kfmt(d.healing || 0))}</div><table class="t"><tr><th>Attacker</th><th>Damage taken</th></tr>${Object.entries(
          defense.sources || {},
        )
          .sort((a, b) => b[1] - a[1])
          .map(([name, damage]) => `<tr><td>${esc(name)}</td><td>${kfmt(damage)}</td></tr>`)
          .join(
            "",
          )}</table><p class="small muted">Damage received and parry flags are measured from decoded hits. Avoided attacks and pre-mitigation damage are unavailable; armor, mitigation and dodge percentages cannot be inferred from received damage alone.</p>`
      : `<div class="pnote">This source does not provide incoming-damage events.</div>`
  }</div>`;
  const rot = (d.rotation || []).length
    ? `<div class="prot"><div class="lbl">Skill rotation</div><div class="strip">${d.rotation
        .slice(0, 80)
        .map(
          (e) =>
            `<div class="ic">${skillArt(e.skill_id, e.skill)}<small>${esc(e.skill || "")}</small><span>${e.t != null ? e.t.toFixed(0) + "s" : ""}</span></div>`,
        )
        .join("")}</div></div>`
    : "";
  const stat = (l, v, gold) =>
    `<div><span class="pl">${l}</span><span class="pv${gold ? " gold" : ""}">${v}</span></div>`;
  const clsIcon = d.cls
    ? `<img class="pcls" src="${icon("https://metabot.gg/web/aion2/classes/" + String(d.cls).toLowerCase() + ".webp")}" alt="" onerror="this.style.visibility='hidden'">`
    : "";
  return `<div class="parse">
    <div class="phead"><div class="pwho">${clsIcon}<b>${esc(d.name || "—")}</b><span class="psub">${esc(cap(d.cls || ""))}${d.boss ? " · " + esc(d.boss) : ""}</span></div>
      <div class="pstats">${d.gs != null ? stat("GS", n0(d.gs)) : ""}${d.cp != null ? stat("CP", kfmt(d.cp)) : ""}${stat("DMG", kfmt(d.dmg))}${stat("DPS", kfmt(d.dps), true)}${d.contrib != null ? stat("Contrib", Math.round(100 * d.contrib) + "%") : ""}</div></div>
    <div class="ptabs"><button data-ptab="dps" class="${at === "dps" ? "on" : ""}">DPS</button><button data-ptab="def" class="${at === "def" ? "on" : ""}">Defense</button><button data-ptab="acc" class="${at === "acc" ? "on" : ""}">Accuracy</button></div>
    ${dpsPanel}${defPanel}${accPanel}${rot}</div>`;
}
document.addEventListener("click", (e) => {
  // one delegated handler toggles the parse tabs
  const b = e.target.closest && e.target.closest(".ptabs [data-ptab]");
  if (!b) return;
  _ptab = b.dataset.ptab;
  const parse = b.closest(".parse");
  parse.querySelectorAll(".ptabs [data-ptab]").forEach((x) => x.classList.toggle("on", x === b));
  parse.querySelectorAll(".ppanel").forEach((p) => (p.hidden = p.dataset.pane !== _ptab));
});
const localReviewOptions = (file) => ({
  openBuildWorkspace: (actor) => {
    buildWorkspaceContext = {
      reference: { snapshot: actor.profile_snapshot },
      className: actor.class,
      level: actor.profile_snapshot?.data?.profile?.characterLevel,
      source: { actor: actor.id, basis: "Saved profile from combat log; reference only." },
      backURL: location.hash,
    };
    location.hash = "/builds";
  },
  skillIcon,
  lookupProfile: (player, region) => api("/api/character/profile", { player, region }),
  importPlan: (plan) => {
    window.A2Raid.importPlan(plan);
    location.hash = "/raid";
  },
  compare: (id) => communityAPI("/api/v1/logs/" + encodeURIComponent(id) + "/raw"),
  rankings: (segment, log) => communityAPI("/api/v1/rankings", { segment, log }),
  ...(file
    ? {
        reconstructArchive: (first, last) =>
          api("/api/sessions/reconstruction?file=" + encodeURIComponent(file) + "&first=" + first + "&last=" + last),
        archiveCurrent: file,
        archiveParts: (offset, limit, archive) =>
          api("/api/sessions?paged=1&offset=" + offset + "&limit=" + limit + "&archive=" + encodeURIComponent(archive)),
        openArchivePart: (row, mode) => {
          location.hash =
            "/combat-log/local/" + encodeURIComponent(row.file) + "?mode=" + encodeURIComponent(mode || "");
        },
        saveMetadata: (log) => api("/api/sessions", { file, log }),
        publish: (visibility) => api("/api/sessions/share", { file, visibility }),
      }
    : {}),
});
