// Public logs browser. Reads the server's /api/v1/logs and links each log to the server's own
// viewer page (/l/<id>), which renders the full AionFlex-style breakdown.
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const ago = (t) => { if (!t) return ""; const s = Date.now() / 1000 - t; return s < 3600 ? Math.round(s / 60) + "m" : s < 86400 ? Math.round(s / 3600) + "h" : new Date(t * 1000).toLocaleDateString(); };

  async function load() {
    const boss = $("#boss").value.trim();
    $("#list").innerHTML = '<div class="empty">Loading…</div>';
    try {
      const data = await window.A2.api("/api/v1/logs?limit=100" + (boss ? "&boss=" + encodeURIComponent(boss) : ""));
      const rows = (data.logs || []).map((l) => {
        const top = (l.players || [])[0] || {};
        return `<tr onclick="location.href='log.html?id=${esc(l.id)}'" style="cursor:pointer">
          <td class="gold">${esc(l.boss || l.title || "Fight")}</td>
          <td>${esc(top.name || "")} <span class="muted small">${esc(cap(top.class || ""))}</span></td>
          <td class="r num">${n0(l.top_dps)}</td>
          <td class="r">${(l.duration || 0).toFixed(0)}s</td>
          <td class="r">${(l.players || []).length}</td>
          <td class="small muted">${esc(l.source || "")}</td>
          <td class="small muted r">${ago(l.created_at)}</td></tr>`;
      }).join("");
      $("#list").innerHTML = rows
        ? `<table class="t"><tr><th>Boss</th><th>Top player</th><th class="r">Top DPS</th><th class="r">Length</th><th class="r">Players</th><th>Source</th><th class="r">When</th></tr>${rows}</table>`
        : '<div class="empty">No public logs yet. Share a fight from the app (Combat Logs → Share, visibility public).</div>';
      $("#msg").textContent = `${(data.logs || []).length} of ${data.total || 0}`;
    } catch (e) { $("#list").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }
  function cap(s) { return s ? s[0].toUpperCase() + s.slice(1) : ""; }
  $("#go").onclick = load;
  $("#boss").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  load();
})();
