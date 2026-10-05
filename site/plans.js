// Public raid-plan gallery. Reads /api/v1/plans and links each to the server's /p/<id> view and to
// the planner (planner.html?plan=<id>, which fetches and loads it).
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

  async function load() {
    $("#list").innerHTML = '<div class="empty">Loading…</div>';
    try {
      const data = await window.A2.api("/api/v1/plans?limit=100");
      const base = window.A2.base();
      const cards = (data.plans || []).map((p) => `<div class="pcard">
        <div class="gname">${esc(p.name || "Plan")}</div>
        <div class="small muted">${esc(p.author || "unknown")} · ${(p.duration || 0).toFixed(0)}s · ${p.tokens || 0} tokens${p.has_fight ? " · with a fight" : ""}</div>
        <div class="small" style="margin:4px 0">${(p.classes || []).map((c) => `<span class="chip">${esc(cap(c))}</span>`).join(" ")}</div>
        <div class="row small"><a class="btn small" href="${esc(base)}/p/${esc(p.id)}" target="_blank" rel="noopener">View</a>
          <a class="btn small primary" href="planner.html?plan=${esc(p.id)}">Open in planner</a></div></div>`).join("");
      $("#list").innerHTML = cards
        ? `<div class="pcards">${cards}</div>`
        : '<div class="empty">No public plans yet. Publish one from the Raid Planner.</div>';
    } catch (e) { $("#list").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }
  load();
})();
