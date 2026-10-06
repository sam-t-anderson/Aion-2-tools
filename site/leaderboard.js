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
      const data = await window.A2.api("/api/v1/leaderboard?limit=100" + (cls ? "&class=" + encodeURIComponent(cls.toLowerCase()) : "") + (boss ? "&boss=" + encodeURIComponent(boss) : ""));
      const entries = data.entries || [];
      const mx = Math.max(...entries.map((e) => e.dps || 0), 1);
      const rows = entries.map((e, i) => `<tr onclick="location.href='log.html?id=${esc(e.log)}'" style="cursor:pointer">
        <td class="r muted">${i + 1}</td><td class="gold">${esc(e.name || "")}</td><td>${esc(cap(e.class || ""))}</td>
        <td style="width:40%"><div class="bar"><i style="width:${100 * (e.dps || 0) / mx}%"></i><span>${n0(e.dps)}</span></div></td>
        <td>${esc(e.boss || "")}</td></tr>`).join("");
      $("#list").innerHTML = rows
        ? `<table class="t"><tr><th class="r">#</th><th>Player</th><th>Class</th><th>DPS</th><th>Boss</th></tr>${rows}</table>`
        : '<div class="empty">No parses yet. Share public logs from the app to populate the leaderboard.</div>';
      $("#msg").textContent = `${entries.length} parses`;
    } catch (e) { $("#list").innerHTML = `<div class="note">${esc(e.message)}</div>`; }
  }
  $("#go").onclick = load;
  $("#cls").onchange = load;
  $("#boss").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  load();
})();
