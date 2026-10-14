// Class statistics from shared public logs (anonymous — no names kept). Reads the server's
// /api/v1/stats (class index) and /api/v1/stats/<class> (per-class medians, hit rates, tempo and
// damage by skill — the same data the server's own /stats page uses). The default view is a
// cross-class performance comparison with a median-DPS bar graph; a class dropdown drills into one
// class's detail, and a boss dropdown filters it. Every field is read defensively: if the server is
// unreachable or a field is missing, a friendly message shows instead of breaking the rest of the site.
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const note = (e) => `<div class="note">${esc((e && e.message) || "Could not reach the stats server.")}</div>`;
  const params = new URLSearchParams(location.search);
  const body = document.getElementById("stats-body");
  const classSel = document.getElementById("class-select");
  const bossSel = document.getElementById("boss-select");
  const bossWrap = document.getElementById("boss-wrap");

  const go = (c, b) => { const u = new URLSearchParams(); if (c) u.set("class", c); if (b) u.set("boss", b); location.search = u.toString(); };
  function kpis(pairs) {
    return '<div class="kpis">' + pairs.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("") + "</div>";
  }

  async function render() {
    let idx;
    try { idx = await A2.api("/api/v1/stats"); }
    catch (e) { body.innerHTML = note(e); classSel.innerHTML = '<option>—</option>'; return; }
    const classes = (idx && idx.classes) || [];
    if (!classes.length) { body.innerHTML = '<div class="empty">No fights uploaded yet. Share public logs from the app to populate class stats.</div>'; classSel.innerHTML = '<option>—</option>'; return; }

    const cls = params.get("class") || "";
    const boss = params.get("boss") || "";
    classSel.innerHTML = '<option value="">All classes (overview)</option>' +
      classes.map((c) => `<option value="${esc(c.class)}"${c.class === cls ? " selected" : ""}>${esc(cap(c.class))} (${c.observations})</option>`).join("");
    classSel.onchange = () => go(classSel.value, "");

    if (!cls) { bossWrap.hidden = true; return renderOverview(classes); }
    bossWrap.hidden = false;
    return renderClass(cls, boss);
  }

  // A horizontal box-and-whisker "spread" of a class's DPS distribution, on an axis shared across
  // all classes (0..gmax). The box is the middle half (p25–p75, or median–p75 until the server
  // reports p25); a strong line marks the median; a whisker runs to the best (max), with p90 ticked.
  function spread(dps, gmax) {
    const x = (v) => (v == null || isNaN(v) || !gmax ? null : Math.max(0, Math.min(100, 100 * v / gmax)));
    const med = x(dps.median), p25 = x(dps.p25), p75 = x(dps.p75), p90 = x(dps.p90), mxv = x(dps.max);
    const boxL = p25 != null ? p25 : med, boxR = p75 != null ? p75 : med;
    const parts = [];
    const wr = mxv != null ? mxv : (p90 != null ? p90 : boxR);
    if (boxL != null && wr != null) parts.push(`<line x1="${boxL}" y1="10" x2="${wr}" y2="10" stroke="currentColor" stroke-opacity=".4" stroke-width="1.2"/>`);
    if (boxL != null && boxR != null && boxR > boxL) parts.push(`<rect x="${boxL}" y="4" width="${(boxR - boxL).toFixed(2)}" height="12" rx="2" fill="#2a8fb0" fill-opacity=".55"/>`);
    if (p90 != null) parts.push(`<line x1="${p90}" y1="6" x2="${p90}" y2="14" stroke="currentColor" stroke-opacity=".55" stroke-width="1.2"/>`);
    if (mxv != null) parts.push(`<line x1="${mxv}" y1="4" x2="${mxv}" y2="16" stroke="currentColor" stroke-opacity=".7" stroke-width="1.2"/>`);
    if (med != null) parts.push(`<line x1="${med}" y1="1" x2="${med}" y2="19" stroke="currentColor" stroke-width="2.2"/>`);
    return `<svg viewBox="0 0 100 20" preserveAspectRatio="none" width="100%" height="20" role="img" aria-label="DPS spread: median ${n0(dps.median)}, middle half ${n0(dps.p25)}–${n0(dps.p75)}, best ${n0(dps.max)}">${parts.join("")}</svg>`;
  }

  async function renderOverview(classes) {
    body.innerHTML = '<div class="empty">Loading…</div>';
    const results = await Promise.all(classes.map(async (c) => {
      try { const s = await A2.api(`/api/v1/stats/${encodeURIComponent(c.class)}`); return { cls: c.class, obs: c.observations, dps: s.dps || {} }; }
      catch (e) { return { cls: c.class, obs: c.observations, dps: {} }; }
    }));
    const rows = results.filter((r) => r.dps && r.dps.median != null).sort((a, b) => (b.dps.median || 0) - (a.dps.median || 0));
    if (!rows.length) { body.innerHTML = '<div class="empty">Not enough data for a class comparison yet.</div>'; return; }
    const gmax = Math.max(...rows.map((r) => r.dps.max || r.dps.p90 || r.dps.median || 0), 1);
    const tr = rows.map((r) => `<tr><td>${esc(cap(r.cls))}</td>
      <td style="width:40%">${spread(r.dps, gmax)}</td>
      <td class="r num">${n0(r.dps.median)}</td><td class="r">${n0(r.dps.p75)}</td><td class="r">${n0(r.dps.p90)}</td>
      <td class="r">${n0(r.obs)}</td><td><a href="stats.html?class=${encodeURIComponent(r.cls)}">details →</a></td></tr>`).join("");
    body.innerHTML =
      '<h2 class="pagetitle" style="font-size:18px">Performance by class</h2>' +
      `<table class="t"><tr><th>Class</th><th>Spread (DPS)</th><th class="r">Median DPS</th><th class="r">Top 25% DPS</th><th class="r">Top 10% DPS</th><th class="r">Samples</th><th></th></tr>${tr}</table>` +
      '<p class="small muted" style="margin-top:10px">Each bar is that class\'s DPS spread on a shared axis: the box is the middle half of players, the strong line is the median, the whisker runs to the best recorded. Highest median first. Choose a class above for its hit rates, cast tempo and damage by skill.</p>';
  }

  async function renderClass(cls, boss) {
    body.innerHTML = '<div class="empty">Loading…</div>';
    let s;
    try { s = await A2.api(`/api/v1/stats/${encodeURIComponent(cls)}` + (boss ? "?boss=" + encodeURIComponent(boss) : "")); }
    catch (e) { body.innerHTML = note(e); return; }
    bossSel.innerHTML = '<option value="">All fights</option>' +
      (((s && s.bosses) || []).map(([b, n]) => `<option value="${esc(b)}"${b === boss ? " selected" : ""}>${esc(b)} (${n})</option>`).join(""));
    bossSel.onchange = () => go(cls, bossSel.value);

    if (!s || !s.observations) { body.innerHTML = '<div class="empty">No data for this selection.</div>'; return; }
    const dps = s.dps || {}, rates = s.rates || {}, tempo = s.tempo || {}, tq = s.top_quarter || {};
    const allShare = Object.fromEntries((((s.all || {}).skills) || []).map((r) => [r.skill, r.share]));
    const skills = tq.skills || [];
    const mx = Math.max(...skills.map((r) => r.share || 0), 0.0001);
    const kp = [
      ["Players", n0(s.observations)], ["Median DPS", n0(dps.median)],
      ["Top 25% DPS", n0(dps.p75)], ["Top 10% DPS", n0(dps.p90)],
      ["Crit", pct(rates.crit)], ["Double", pct(rates.double)], ["Perfect", pct(rates.perfect)],
      ["Casts / min", tempo.cpm != null ? Math.round(tempo.cpm) : "—"],
      ["Idle (all)", pct(tempo.idle_share)], ["Idle (top 25%)", pct((tq.tempo || {}).idle_share)],
    ];
    const skillRows = skills.map((r) => `<tr><td>${esc(r.skill)}</td>
      <td style="width:34%"><div class="bar"><i style="width:${(100 * (r.share || 0) / mx).toFixed(1)}%"></i><span>${pct(r.share)}</span></div></td>
      <td class="r">${pct(allShare[r.skill] ?? 0)}</td><td class="r">${r.cpm != null ? r.cpm.toFixed(1) : "—"}</td><td class="r">${pct(r.used_by, 0)}</td></tr>`).join("");
    const cpRows = ((s.by_combat_power) || []).map((b) => `<tr><td>${n0(b.from)}–${n0(b.to)}</td><td class="r">${n0(b.players)}</td><td class="r num">${n0(b.median_dps)}</td></tr>`).join("");
    body.innerHTML =
      `<h2 class="pagetitle" style="font-size:18px">${esc(cap(cls))}${boss ? " vs " + esc(boss) : ""}</h2>` +
      kpis(kp) +
      '<h2 class="pagetitle" style="font-size:18px;margin-top:18px">Top 25% of players: damage by skill</h2>' +
      (skillRows
        ? `<table class="t"><tr><th>Skill</th><th>Share (top 25%)</th><th class="r">All players</th><th class="r">Casts / min</th><th class="r">Used by</th></tr>${skillRows}</table>`
        : '<div class="empty">No skill breakdown for this selection.</div>') +
      '<h2 class="pagetitle" style="font-size:18px;margin-top:18px">DPS by combat power</h2>' +
      (cpRows
        ? `<table class="t"><tr><th>Combat power</th><th class="r">Players</th><th class="r">Median DPS</th></tr>${cpRows}</table>`
        : '<div class="empty">Not enough data for combat-power brackets.</div>');
  }

  render();
})();
