/* Gathering (the app's Game › Gathering page and the website's gathering.html): what you gathered and took from
   dungeon reward cubes, and everyone's drop rates. The page hands in where its data comes from:
     mine()      -> your records summed up (the app: this computer's gathering log; the website: the signed-in
                    account's), or null when there are none to show (the website, signed out)
     community() -> the log server's drop rates (/api/v1/gathering/stats)
     mineLabel   -> what "yours" is ("This computer", "Your account")
     signedOut   -> HTML shown instead of your records when mine() gives null
   Both summaries share one shape (aion2calc/combat/gathering.py summary(), aion2logs/gathering.py stats()).
   Item, node, place and character names come from the game and its players, so the language picker
   (i18n.js) leaves them as they are (translate="no"). */
(function () {
  "use strict";
  const esc = (x) =>
    String(x ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  const num = (n) => (Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : "—");
  const pct = (v) => (Number.isFinite(v) ? (v * 100).toFixed(1) + "%" : "—");
  const RESULTS = { normal: "Normal", better: "Better grade", failed: "Failed" };
  const whenAt = (seconds) => {
    const d = new Date(seconds * 1000);
    if (!Number.isFinite(d.getTime())) return "—";
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  };
  const item = (row) =>
    `<i class="gt-dot" data-grade="${esc(row.grade || "")}" aria-hidden="true"></i><span translate="no">${esc(row.name || "Item " + row.item)}</span>`;

  function mount(root, io) {
    let tab = "nodes";
    let source = "everyone";
    let showAll = false;
    let mine = null;
    let community = null;
    let mineError = "";
    let communityError = "";
    let loading = true;
    try {
      const saved = localStorage.getItem("a2-gathering-tab");
      if (["nodes", "dungeons", "log"].includes(saved)) tab = saved;
    } catch (_) {
      /* storage off: the first tab */
    }

    function view() {
      return source === "yours" ? mine : community;
    }

    function totals() {
      if (!mine) return io.signedOut || "";
      const r = mine.results || {};
      const share = (n) => (mine.gathers ? ` <span class="muted">(${pct(n / mine.gathers)})</span>` : "");
      return `<div class="kpis gt-kpis">
        <div class="kpi"><div class="k">Gathers</div><div class="v">${num(mine.gathers)}</div></div>
        <div class="kpi"><div class="k">Items gathered</div><div class="v">${num(mine.gathered)}</div></div>
        <div class="kpi"><div class="k">Better grade</div><div class="v">${num(r.better)}${share(r.better)}</div></div>
        <div class="kpi"><div class="k">Failed</div><div class="v">${num(r.failed)}${share(r.failed)}</div></div>
        <div class="kpi"><div class="k">Reward cubes</div><div class="v">${num(mine.cubes)}</div></div>
      </div>`;
    }

    function sourcePicker() {
      const button = (id, label) =>
        `<button type="button" data-source="${id}" class="${source === id ? "on" : ""}" aria-pressed="${source === id}">${esc(label)}</button>`;
      return `<div class="seg gt-source" role="group" aria-label="Whose records">${button("everyone", "Everyone")}${button("yours", io.mineLabel || "Yours")}</div>`;
    }

    function empty(what) {
      if (source === "everyone") {
        if (communityError) return `<p class="muted">${esc(communityError)}</p>`;
        return `<p class="muted">Nobody has shared any ${what} yet. The desktop app shares them while "Share gathering and drop data" is on in Settings.</p>`;
      }
      if (!mine) return io.signedOut || `<p class="muted">${esc(mineError || "Nothing recorded yet.")}</p>`;
      return `<p class="muted">No ${what} recorded yet: run the Live Meter while you play and they appear here.</p>`;
    }

    function nodes() {
      const data = view();
      const rows = (data && data.nodes) || [];
      if (!rows.length) return empty("gathering");
      return rows
        .map((node) => {
          const r = node.results || {};
          const of = (n) => (node.gathers ? pct(n / node.gathers) : "—");
          const who = Number.isFinite(node.reporters) ? ` · ${num(node.reporters)} players` : "";
          return `<article class="card gt-node"><h3><span translate="no">${esc(node.name)}</span> <span class="small muted">${num(node.gathers)} gathers${who}</span></h3>
          <p class="small">${Object.entries(RESULTS)
            .map(([k, label]) => `${label} <b>${of(r[k] || 0)}</b>`)
            .join(" · ")}</p>
          <div class="gt-scroll"><table class="t"><thead><tr><th>Gave</th><th>Grade</th><th class="r">Chance</th><th class="r">How many</th></tr></thead><tbody>
          ${(node.items || [])
            .map(
              (row) =>
                `<tr><td>${item(row)}</td><td>${esc(row.grade || "—")}</td><td class="r">${pct(row.share)}</td><td class="r">${Number.isFinite(row.average) ? row.average.toFixed(2) : row.gathers ? (row.count / row.gathers).toFixed(2) : "—"}</td></tr>`,
            )
            .join("")}</tbody></table></div></article>`;
        })
        .join("");
    }

    function dungeons() {
      const data = view();
      const rows = (data && data.dungeons) || [];
      if (!rows.length) return empty("reward cubes");
      return rows
        .map((place) => {
          const items = (place.items || []).filter((row) => showAll || row.material);
          const who = Number.isFinite(place.reporters) ? ` · ${num(place.reporters)} players` : "";
          return `<article class="card gt-dungeon"><h3><span translate="no">${esc(place.name || "Unknown place")}</span> <span class="small muted">${num(place.cubes)} reward cubes${who}</span></h3>
          ${
            items.length
              ? `<div class="gt-scroll"><table class="t"><thead><tr><th>${showAll ? "Drop" : "Material"}</th><th>Grade</th><th class="r">In cubes</th><th class="r">How many</th></tr></thead><tbody>
          ${items
            .map(
              (row) =>
                `<tr><td>${item(row)}</td><td>${esc(row.grade || "—")}</td><td class="r">${pct(row.share)}</td><td class="r">${Number.isFinite(row.average) ? row.average.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}</td></tr>`,
            )
            .join("")}</tbody></table></div>`
              : `<p class="muted">No crafting materials in these cubes.</p>`
          }</article>`;
        })
        .join("");
    }

    // A log entry: a gather's item and how many (a failed one gave nothing), or a reward cube's materials.
    function what(row) {
      if (row.kind === "gather")
        return row.result === "failed"
          ? `${item(row)} <span class="small muted">Failed: nothing gathered</span>`
          : `${item(row)} ×${num(row.count)} <span class="small muted">${esc(RESULTS[row.result] || "")}</span>`;
      const materials = (row.items || []).filter((it) => it.material).map((it) => `${item(it)} ×${num(it.count)}`);
      return `Reward cube: ${materials.join(", ") || "no crafting materials"} <span class="small muted">(${num((row.items || []).length)} drops)</span>`;
    }

    function log() {
      if (!mine) return io.signedOut || `<p class="muted">${esc(mineError || "Nothing recorded yet.")}</p>`;
      const rows = mine.recent || [];
      if (!rows.length) return `<p class="muted">Nothing recorded yet: run the Live Meter while you gather or open a dungeon's reward cube.</p>`;
      return `<div class="gt-scroll"><table class="t gt-log"><thead><tr><th>When</th><th>Where</th><th>What</th><th>Character</th></tr></thead><tbody>
        ${rows
          .map(
            (row) =>
              `<tr><td>${esc(whenAt(row.t))}</td><td translate="no">${esc(row.place || "—")}</td><td>${what(row)}</td><td translate="no">${esc(row.character || "—")}</td></tr>`,
          )
          .join("")}</tbody></table></div>`;
    }

    function render() {
      if (!root.isConnected) return;
      const tabs = [
        ["nodes", "Gathering"],
        ["dungeons", "Dungeon materials"],
        ["log", "Your log"],
      ];
      const body =
        loading && !mine && !community
          ? `<p class="muted" role="status">Loading…</p>`
          : tab === "nodes"
            ? `<div class="row gt-head">${sourcePicker()}<p class="small muted">How often each kind of node gives each grade, and how many a gather gives. A better-grade result gives the Fine or Pure material; a failed one gives nothing.</p></div>${nodes()}`
            : tab === "dungeons"
              ? `<div class="row gt-head">${sourcePicker()}<label class="small"><input type="checkbox" data-show-all ${showAll ? "checked" : ""}> Show every drop (equipment, currency)</label></div>
                 <p class="small muted">A dungeon's reward cube pays out the run's loot when claimed. "In cubes" is the share of claimed cubes holding the material; "How many" is the average count when it is there.</p>${dungeons()}`
              : log();
      root.innerHTML = `<section class="gt">${totals()}
        <div class="tabs gt-tabs" role="tablist">${tabs
          .map(
            ([id, label]) =>
              `<button type="button" role="tab" data-tab="${id}" class="${tab === id ? "on" : ""}" aria-selected="${tab === id}">${esc(label)}</button>`,
          )
          .join("")}</div>
        <div class="gt-body" role="tabpanel">${body}</div></section>`;
      root.querySelectorAll("[data-tab]").forEach((b) => {
        b.onclick = () => {
          tab = b.dataset.tab;
          try {
            localStorage.setItem("a2-gathering-tab", tab);
          } catch (_) {
            /* storage off */
          }
          render();
        };
      });
      root.querySelectorAll("[data-source]").forEach((b) => {
        b.onclick = () => {
          source = b.dataset.source;
          render();
        };
      });
      const all = root.querySelector("[data-show-all]");
      if (all)
        all.onchange = () => {
          showAll = all.checked;
          render();
        };
    }

    async function load() {
      loading = true;
      render();
      const [m, c] = await Promise.allSettled([io.mine(), io.community()]);
      mine = m.status === "fulfilled" ? m.value : null;
      mineError = m.status === "rejected" ? (m.reason && m.reason.message) || "Your records could not be read." : "";
      community = c.status === "fulfilled" ? c.value : null;
      communityError =
        c.status === "rejected"
          ? "Everyone's drop rates are not available: the log server does not have them yet, or cannot be reached."
          : "";
      if (!community && mine) source = "yours";
      loading = false;
      render();
    }

    render();
    load();
    return { reload: load };
  }

  window.A2Gathering = { mount };
})();
