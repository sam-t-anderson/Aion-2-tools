/* Pet Tracker (0Fox2Give's program, https://github.com/0Fox2Give/PetTracker) inside Aion 2 Calc: draws what
   GET /api/pettracker returns, for the Pet Tracker window (pet-overlay.html) and the Pet Tracker page. The server
   builds the rows with Pet Tracker's own overlay rules (aion2calc/app/pettracker.py); this file only draws them
   and sends the controls back (POST /api/pettracker). */
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const FAMILIES = { Cogni: "cogni", Fera: "fera", Natura: "natura", Varian: "varian", Special: "special" };
  const ACCENTS = { Gold: "#d9b24c", Blue: "#60b1ec", Teal: "#53c9b5" };   // Pet Tracker's accent choices

  // One line on how Pet Tracker is doing, and how it reads: "ok", "wait" or "off".
  function status(state) {
    if (!state) return { text: "Loading Pet Tracker…", tone: "wait" };
    if (!state.supported) return { text: "Pet Tracker runs on Windows only.", tone: "off" };
    if (!state.installed) return { text: "Pet Tracker is not installed. Install it under Settings → Pet Tracker.", tone: "off" };
    if (!state.enabled) return { text: "Pet Tracker is off. Turn it on under Settings → Pet Tracker.", tone: "off" };
    if (!state.connected) return { text: state.problem ? state.problem + " Starting it…" : "Starting Pet Tracker's capture…", tone: "wait" };
    const who = state.character ? state.character + " · " : "";
    return { text: who + (state.status || "Connected"), tone: state.status === "Live" ? "ok" : "wait", title: state.detail || "" };
  }

  // One pet: portrait, name, family, rank, souls toward the next rank and the bar, and Pet Tracker's notice.
  function row(r, opts) {
    opts = opts || {};
    const fam = FAMILIES[r.family] || "";
    const tip = [r.creature && "From " + r.creature, r.remaining != null && (r.remaining + " soul" + (r.remaining === 1 ? "" : "s") + " to the next rank"),
      r.estimated && "Estimated while totals sync", r.goal_text].filter(Boolean).join(" · ");
    const bar = r.max || opts.bars === false ? "" :
      `<div class="ptbar${r.paused ? " paused" : ""}" aria-hidden="true"><i style="width:${Math.round((r.ratio || 0) * 100)}%"></i></div>`;
    const pic = opts.portraits === false ? "" :
      `<img class="ptpic" src="${esc(r.portrait)}" alt="" loading="lazy" onerror="this.classList.add('none')">`;
    const pin = opts.pins === false ? "" :
      `<button type="button" class="ptpin${r.pinned ? " on" : ""}" data-pin="${r.id}" aria-pressed="${r.pinned}" title="${r.pinned ? "Unpin this pet" : "Pin this pet to the top"}">${r.pinned ? "★" : "☆"}</button>`;
    return `<div class="ptrow${r.max ? " max" : ""}"${tip ? ` title="${esc(tip)}"` : ""}>${pic}<div class="ptbody">
      <div class="ptline"><span class="ptname">${esc(r.name)}</span>${r.family ? `<span class="ptfam ${fam}">${esc(r.family)}</span>` : ""}<span class="ptrank">${esc(r.rank_text)}</span></div>
      <div class="ptline ptsub"><span class="ptprog">${r.max ? "✓ MAX" : (r.estimated ? "≈" : "") + esc(r.progress)}</span>${r.notice ? `<span class="ptnotice">${esc(r.notice)}</span>` : ""}</div>
      ${bar}</div>${pin}</div>`;
  }

  function rows(state, opts) {
    if (!state || !state.connected) return `<div class="ptempty">${esc(status(state).text)}</div>`;
    const o = state.options || {};
    const options = Object.assign({ portraits: o.portraits, bars: o.progress_bars }, opts || {});
    if (!(state.rows || []).length) return state.empty ? `<div class="ptempty">${esc(state.empty)}</div>` : "";
    return state.rows.map((r) => row(r, options)).join("");
  }

  function accent(state) {
    return ACCENTS[(state && state.options && state.options.accent) || "Gold"] || ACCENTS.Gold;
  }

  async function control(body) {
    const r = await fetch("/api/pettracker", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  }

  window.A2Pets = { esc, status, row, rows, accent, control };
})();
