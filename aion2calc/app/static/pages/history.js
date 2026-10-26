/* Saved Results (#/history): optimizer and advice snapshots, which survive process and browser restarts. */
"use strict";

async function pageHistory() {
  app().innerHTML =
    win(
      "Saved results",
      "Previous optimizations and advice, stored on this computer",
      `<div class="row"><label>Import previous result <input id="result-import" type="file" accept=".json"></label><span id="history-msg" class="small muted"></span></div><div id="history-list"></div>`,
    ) + `<div id="history-view"></div>`;
  const refresh = async () => {
    const rows = await api("/api/history");
    $("#history-list").innerHTML = rows.length
      ? `<table class="t"><tr><th>Run</th><th>Recorded</th><th><span class="sr-only">Actions</span></th></tr>${rows.map((r) => `<tr><td>${esc(r.title)}</td><td>${whenAt(r.created * 1000)}</td><td><button class="btn small" data-history="${r.id}">Open</button><button class="btn small" data-history-export="${r.id}">Export</button></td></tr>`).join("")}</table>`
      : "<p>No saved runs yet. Completed optimizations and advice save here automatically.</p>";
    document.querySelectorAll("[data-history]").forEach(
      (b) =>
        (b.onclick = async () => {
          try {
            const d = await api("/api/history?id=" + b.dataset.history);
            const box = $("#history-view");
            box.innerHTML = `<p class="small muted">Saved result from ${whenAt(d.created * 1000)}. This is a snapshot; advice may change as gear or game data changes.</p>`;
            if (d.kind === "advice-text") box.innerHTML += `<pre class="diff">${esc(d.result.text)}</pre>`;
            else if (d.kind === "advice") {
              S.gear ||= {};
              box.innerHTML += '<div id="gout">' + renderAdvice(d.result) + "</div>";
              bindAdvice(d.result);
            } else {
              const v = d.kind === "optimize-character" ? d.result.optimized : d.result;
              box.innerHTML += '<div id="saved-windows"></div>';
              renderWindows(v, { win: "overview" }, $("#saved-windows"));
            }
            box.scrollIntoView({ behavior: "smooth" });
          } catch (e) {
            $("#history-msg").textContent = e.message;
          }
        }),
    );
    document.querySelectorAll("[data-history-export]").forEach(
      (b) =>
        (b.onclick = async () => {
          const d = await api("/api/history?id=" + b.dataset.historyExport),
            url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" })),
            a = document.createElement("a");
          a.href = url;
          a.download = "aion2calc-result-" + b.dataset.historyExport + ".json";
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }),
    );
  };
  $("#result-import").onchange = async (e) => {
    try {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 20 * 1024 * 1024) throw Error("Result exceeds 20 MiB");
      const result = JSON.parse(await file.text());
      await api("/api/history", result);
      await refresh();
      $("#history-msg").textContent = "Result imported";
    } catch (e) {
      $("#history-msg").textContent = e.message;
    }
  };
  await refresh();
}
