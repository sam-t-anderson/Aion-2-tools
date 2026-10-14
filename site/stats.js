// Class statistics from shared public logs (anonymous — no names kept). Reads the server's
// /api/v1/stats and /api/v1/stats/<class> (the same data the server's own /stats page uses) and
// renders median DPS, hit rates, tempo and damage-by-skill per class and boss. Every field is
// read defensively: if the server is unreachable or a field is missing, the page shows a friendly
// message instead of breaking — it can never take down the rest of the site.
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const params = new URLSearchParams(location.search);
  const body = document.getElementById("stats-body");
  const clsRow = document.getElementById("class-picker");
  const bossRow = document.getElementById("boss-picker");

  function chip(label, active, onclick) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.type = "button";
    b.textContent = label;
    b.onclick = onclick;
    if (active) { b.setAttribute("aria-current", "true"); b.style.fontWeight = "700"; b.style.textDecoration = "underline"; }
    return b;
  }
  function kpis(pairs) {
    return '<div class="kpis">' + pairs.map(([k, v]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("") + "</div>";
  }

  async function render() {
    let idx;
    try { idx = await A2.api("/api/v1/stats"); }
    catch (e) { body.innerHTML = `<div class="note">${esc(e.message || "Could not reach the stats server.")}</div>`; return; }
    const classes = (idx && idx.classes) || [];
    if (!classes.length) { body.innerHTML = '<div class="empty">No fights uploaded yet. Share public logs from the app to populate class stats.</div>'; return; }

    const cls = params.get("class") || classes[0].class;
    const boss = params.get("boss") || "";
    const go = (c, b) => { const u = new URLSearchParams(); u.set("class", c); if (b) u.set("boss", b); location.search = u.toString(); };
    clsRow.replaceChildren(...classes.map((c) => chip(`${cap(c.class)} (${c.observations})`, c.class === cls, () => go(c.class, ""))));

    body.innerHTML = '<div class="empty">Loading…</div>';
    let s;
    try { s = await A2.api(`/api/v1/stats/${encodeURIComponent(cls)}` + (boss ? "?boss=" + encodeURIComponent(boss) : "")); }
    catch (e) { body.innerHTML = `<div class="note">${esc(e.message || "Could not load this class.")}</div>`; return; }

    bossRow.replaceChildren(
      chip("All fights", !boss, () => go(cls, "")),
      ...(((s && s.bosses) || []).map(([b, n]) => chip(`${b} (${n})`, b === boss, () => go(cls, b)))));

    if (!s || !s.observations) { body.innerHTML = '<div class="empty">No data for this selection.</div>'; return; }
    const dps = s.dps || {}, rates = s.rates || {}, tempo = s.tempo || {}, tq = s.top_quarter || {};
    const allShare = Object.fromEntries((((s.all || {}).skills) || []).map((r) => [r.skill, r.share]));
    const skills = tq.skills || [];
    const mx = Math.max(...skills.map((r) => r.share || 0), 0.0001);
    const kp = [
      ["Players", n0(s.observations)], ["Median DPS", n0(dps.median)],
      ["Top 25% from", n0(dps.p75)], ["Top 10% from", n0(dps.p90)],
      ["Crit", pct(rates.crit)], ["Double", pct(rates.double)], ["Perfect", pct(rates.perfect)],
      ["Casts / min", tempo.cpm != null ? Math.round(tempo.cpm) : "—"],
      ["Idle (all)", pct(tempo.idle_share)], ["Idle (top 25%)", pct((tq.tempo || {}).idle_share)],
    ];
    const skillRows = skills.map((r) => `<tr><td>${esc(r.skill)}</td>
      <td style="width:34%"><div class="bar"><i style="width:${(100 * (r.share || 0) / mx).toFixed(1)}%"></i><span>${pct(r.share)}</span></div></td>
      <td class="r">${pct(allShare[r.skill] ?? 0)}</td><td class="r">${r.cpm != null ? r.cpm.toFixed(1) : "—"}</td><td class="r">${pct(r.used_by, 0)}</td></tr>`).join("");
    const cpRows = ((s.by_combat_power) || []).map((b) => `<tr><td>${n0(b.from)}–${n0(b.to)}</td><td class="r">${n0(b.players)}</td><td class="r num">${n0(b.median_dps)}</td></tr>`).join("");

    body.innerHTML =
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
