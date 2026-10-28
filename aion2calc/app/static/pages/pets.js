/* Pet Tracker (#/pets). */
"use strict";

// Pet Tracker (0Fox2Give's program, https://github.com/0Fox2Give/PetTracker) inside the app: its capture's data from
// GET /api/pettracker, drawn with pet-tracker.js (the Pet Tracker window draws the same rows). Its own window, opened
// with Open Pet Tracker, adds Find a pet, farming maps and the Black Cloud Merchant list.
let petsView = null;
const PET_SETUP = {
  finding: "Checking Pet Tracker's signed release…",
  downloading: "Downloading Pet Tracker…",
  installing: "Pet Tracker's installer is running…",
  started: "Pet Tracker's installer is running; this page notices when it finishes.",
  installed: "Pet Tracker is installed.",
};
// The update notice (GET /api/pettracker's "update"): a newer Pet Tracker than the installed one. Its button opens
// Pet Tracker for its own updater (installer copies), installs the new one over an older offline copy, or, for a
// copy in a folder of the player's own, the notice links to Pet Tracker's releases.
function petUpdateNotice(s, id) {
  const u = s && s.update;
  if (!u || !u.available) return "";
  const what = `Pet Tracker ${esc(u.latest)} is available (you have ${esc(u.installed)}).`;
  if (u.kind === "custom")
    return `<div class="note ptupdate">${what} <a href="${esc((s.source || "") + "/releases")}" target="_blank" rel="noopener">Download it from Pet Tracker's releases</a></div>`;
  const label = u.kind === "offline" ? `Install Pet Tracker ${esc(u.latest)}` : "Update Pet Tracker";
  return `<div class="note ptupdate">${what} <button type="button" class="btn small" id="${id}">${label}</button></div>`;
}
function petSetupText(setup) {
  if (!setup) return "";
  if (setup.status === "error") return setup.error || "Pet Tracker could not be installed.";
  const text = PET_SETUP[setup.status] || "";
  return setup.status === "downloading" && setup.version ? `Downloading Pet Tracker ${setup.version}…` : text;
}
async function pagePets() {
  const P = window.A2Pets;
  const st = {
    state: null,
    collection: null,
    alive: true,
    timer: 0,
    ctimer: 0,
    filters: { q: "", family: "", rank: "all", sort: "name" },
  };
  const shown = stillShown();
  const ui = await api("/api/ui").catch(() => ({}));
  if (!shown()) return;
  app().innerHTML = `<section class="win ptpage"><div class="wh"><h2>Pet Tracker</h2><span class="sub">by 0Fox2Give · your pet ranks and the souls you still need, inside Aion 2 Calc</span></div>
    <div class="setrow"><div class="lbl">Pet Tracker</div><div><div id="pt-head">Loading Pet Tracker…</div><p id="pt-note" class="small" role="status"></p></div></div>
    <div class="setrow"><div class="lbl">Now</div><div>
      <div class="row"><div class="seg" id="pt-modes"><button type="button" data-mode="Recent">Recent</button><button type="button" data-mode="Nearby">Nearby</button></div>
        <label><input type="checkbox" id="pt-hidemax"> Hide maxed</label><span id="pt-msg" class="small muted" role="status"></span></div>
      <div id="pt-sync" class="note" hidden>Totals paused. Return to character selection, then log back in; pet rewards still appear meanwhile.</div>
      <div class="ptrows" id="pt-live"></div></div></div>
    <div class="setrow"><div class="lbl">This session</div><div id="pt-session"></div></div>
    <div class="setrow"><div class="lbl">Collection</div><div>
      <div class="ptsummary" id="pt-summary"></div>
      <div class="ptfilters"><input type="search" id="pt-q" placeholder="Search pets" aria-label="Search pets">
        <select id="pt-family" aria-label="Family"><option value="">All families</option>${["Cogni", "Fera", "Natura", "Varian", "Special"].map((f) => `<option>${f}</option>`).join("")}</select>
        <select id="pt-rank" aria-label="Rank"><option value="all">All ranks</option><option value="0">Uncollected</option><option value="1">Rank 1</option><option value="2">Rank 2</option><option value="3">Maxed</option><option value="unknown">Rank unknown</option><option value="hide">Hide maxed</option></select>
        <select id="pt-sort" aria-label="Sort"><option value="name">By name</option><option value="closest">Closest to next rank</option></select></div>
      <div class="ptgrid" id="pt-collection"></div></div></div>
    <p class="ptattrib">Pet Tracker is a separate program by 0Fox2Give, open source under GPL-3.0 (<a href="https://github.com/0Fox2Give/PetTracker" target="_blank" rel="noopener">its source and releases</a>), used here with its author's permission. Aion 2 Calc runs its capture and shows its data. Like any third-party tool, it is unofficial, and using it can put your game account at risk.</p>
  </section>`;
  const setHtml = (el, html) => {
    if (el && el._a2html !== html) {
      el._a2html = html;
      el.innerHTML = html;
    }
  };
  const say = (text) => {
    const m = $("#pt-msg");
    if (m) {
      m.textContent = text;
      setTimeout(() => {
        if (m.isConnected && m.textContent === text) m.textContent = "";
      }, 4000);
    }
  };
  function head(s) {
    if (!s.supported) return `<p class="note">Pet Tracker runs on Windows only.</p>`;
    const setup = petSetupText(s.setup);
    if (!s.installed) {
      const busy = ["finding", "downloading", "installing"].includes((s.setup || {}).status);
      return `<p>Pet Tracker is not installed on this computer.</p>
        <div class="row"><button type="button" class="btn primary small" id="pt-install" ${busy ? "disabled" : ""}>Install Pet Tracker</button><span class="small muted" role="status">${esc(setup)}</span></div>
        <p class="small muted">Downloads Pet Tracker's official installer from its GitHub release, and starts it only once it matches the release its publisher signed. Pet Tracker needs Npcap, as the Live Meter does.</p>`;
    }
    const line = P.status(s),
      run = s.running || {},
      style = ui.pettracker_overlay_style === "pettracker" ? "pettracker" : "app";
    return `<div class="row"><b>Pet Tracker${s.installed.version ? " " + esc(s.installed.version) : ""}</b><span class="small muted">${esc(s.installed.folder)}</span></div>
      ${petUpdateNotice(s, "pt-update")}
      <div class="row"><label><input type="checkbox" id="pt-enabled" ${s.enabled ? "checked" : ""}> Use Pet Tracker with Aion 2 Calc</label>
        <label><input type="checkbox" id="pt-overlay" ${ui.pettracker_overlay === true ? "checked" : ""} ${s.enabled ? "" : "disabled"}> Show the Pet Tracker overlay</label>
        <select id="pt-style" aria-label="Which window" ${s.enabled ? "" : "disabled"}><option value="app" ${style === "app" ? "selected" : ""}>in Aion 2 Calc's own window</option><option value="pettracker" ${style === "pettracker" ? "selected" : ""}>as Pet Tracker's own window</option></select></div>
      <div class="row"><span class="ptstatus" data-tone="${line.tone}" title="${esc(line.title || "")}">${esc(line.text)}</span>
        <button type="button" class="btn small" id="pt-open" ${run.app ? "disabled" : ""} title="${run.app ? "Pet Tracker is running: its paw icon in the Windows tray opens Find a pet, its settings and more" : "Starts Pet Tracker: its overlay, and its paw icon in the Windows tray with Find a pet, its settings and more"}">${run.app ? "Pet Tracker is running (tray icon)" : "Open Pet Tracker"}</button></div>`;
  }
  function session(s) {
    const se = s.session;
    if (!s.connected || !se)
      return `<p class="muted">Pet Tracker's farming session shows here once it is connected.</p>`;
    const reset = `<button type="button" class="btn small" id="pt-reset">Reset session</button>`;
    if (!se.pets.length) return `<p class="muted">No soul rewards yet this session.</p>${reset}`;
    return `<p><b>${se.souls}</b> soul${se.souls === 1 ? "" : "s"} · <b>${se.ranked}</b> pet${se.ranked === 1 ? "" : "s"} ranked up${se.incomplete ? ` <span class="muted">· some rewards may be missing: capture was interrupted</span>` : ""}</p>
      <table class="t small"><tr><th>Pet</th><th>Souls</th><th>Rank ups</th></tr>${se.pets.map((p) => `<tr><td>${esc(p.name)}</td><td>${p.souls}</td><td>${p.rank_ups}</td></tr>`).join("")}</table>${reset}`;
  }
  const rankMatch = (r, f) =>
    f === "all" ? true : f === "unknown" ? r.rank == null : f === "hide" ? r.rank !== 3 : r.rank === Number(f);
  function collection() {
    const c = st.collection;
    if (!c || !c.connected) return `<p class="muted">Your collection shows here once Pet Tracker is connected.</p>`;
    const f = st.filters,
      q = f.q.trim().toLowerCase();
    const items = (c.collection || []).filter(
      (r) => (!q || r.name.toLowerCase().includes(q)) && (!f.family || r.family === f.family) && rankMatch(r, f.rank),
    );
    if (f.sort === "closest")
      items.sort((a, b) => (a.remaining ?? 1e9) - (b.remaining ?? 1e9) || a.name.localeCompare(b.name));
    if (!items.length) return `<p class="muted">No pet matches.</p>`;
    const goals = [
      ["", "No goal"],
      ["1", "Rank 1"],
      ["2", "Rank 2"],
      ["3", "Rank 3"],
    ];
    return items
      .map(
        (r) =>
          `<div class="ptitem">${P.row(r)}<div class="small muted ptgoal"><label>Farming goal <select data-goal="${r.id}">${goals.map(([v, l]) => `<option value="${v}" ${String(r.goal_rank ?? "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label> ${esc(r.goal_text || "")}</div></div>`,
      )
      .join("");
  }
  function draw() {
    const s = st.state;
    if (!s) return;
    setHtml($("#pt-head"), head(s));
    const o = s.options || {};
    $$("#pt-modes [data-mode]").forEach((b) => {
      b.classList.toggle("on", b.dataset.mode === (o.mode || "Recent"));
      b.disabled = !s.connected;
    });
    $("#pt-hidemax").checked = !!o.hide_maxed;
    $("#pt-hidemax").disabled = !s.connected;
    $("#pt-sync").hidden = !s.sync_notice;
    document.documentElement.style.setProperty("--pt-accent", P.accent(s));
    setHtml($("#pt-live"), P.rows(s));
    setHtml($("#pt-session"), session(s));
    const sum = (st.collection || s).summary;
    setHtml(
      $("#pt-summary"),
      s.connected && sum
        ? `<span>Pets <b>${sum.total}</b></span><span>Collected <b>${sum.collected}</b></span><span>Maxed <b>${sum.maxed}</b></span><span>Rank unknown <b>${sum.unknown}</b></span>`
        : "",
    );
    setHtml($("#pt-collection"), collection());
  }
  async function refresh() {
    clearTimeout(st.timer);
    try {
      st.state = await (await fetch("/api/pettracker", { cache: "no-store" })).json();
      draw();
    } catch (e) {
      /* the next poll retries */
    }
    if (st.alive) st.timer = setTimeout(refresh, st.state && st.state.connected ? 1500 : 3000);
  }
  async function refreshCollection() {
    clearTimeout(st.ctimer);
    try {
      st.collection = await (await fetch("/api/pettracker?collection=1", { cache: "no-store" })).json();
      draw();
    } catch (e) {
      /* retried */
    }
    if (st.alive) st.ctimer = setTimeout(refreshCollection, 10000);
  }
  const act = (body) =>
    P.control(body)
      .then((s) => {
        st.state = s;
        draw();
        refreshCollection();
        return s;
      })
      .catch((e) => say(e.message));
  const setUi = (changes) =>
    api("/api/ui", changes)
      .then((cur) => {
        Object.assign(ui, changes);
        toast("Saved");
        setTimeout(refresh, 600);
        return cur;
      })
      .catch((e) => say(e.message));
  $("#pt-head").addEventListener("click", (e) => {
    if (e.target.closest("#pt-install")) act({ action: "install" });
    else if (e.target.closest("#pt-open")) act({ action: "open" });
    else if (e.target.closest("#pt-update")) {
      P.control({ action: "update" })
        .then((s) => {
          st.state = s;
          draw();
          $("#pt-note").textContent = s.message || "";
        })
        .catch((err) => {
          $("#pt-note").textContent = err.message;
        });
    }
  });
  $("#pt-head").addEventListener("change", (e) => {
    if (e.target.id === "pt-enabled") setUi({ pettracker_enabled: e.target.checked });
    else if (e.target.id === "pt-overlay") setUi({ pettracker_overlay: e.target.checked });
    else if (e.target.id === "pt-style") setUi({ pettracker_overlay_style: e.target.value });
  });
  $("#pt-modes").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]");
    if (b) act({ action: "mode", value: b.dataset.mode });
  });
  $("#pt-hidemax").onchange = (e) => act({ action: "hide_maxed", value: e.target.checked });
  const pinClick = (e) => {
    const link = e.target.closest("[data-link]");
    if (link) {
      link.disabled = true;
      act({ action: "link", character: link.dataset.link });
      return;
    }
    const b = e.target.closest("[data-pin]");
    if (b) act({ action: "pin", pet: Number(b.dataset.pin), value: b.getAttribute("aria-pressed") !== "true" });
  };
  $("#pt-live").addEventListener("click", pinClick);
  $("#pt-collection").addEventListener("click", pinClick);
  $("#pt-collection").addEventListener("change", (e) => {
    const sel = e.target.closest("[data-goal]");
    if (sel) act({ action: "goal", pet: Number(sel.dataset.goal), rank: sel.value ? Number(sel.value) : null });
  });
  $("#pt-session").addEventListener("click", (e) => {
    if (e.target.closest("#pt-reset")) act({ action: "reset_session" });
  });
  const filter = () => {
    st.filters = {
      q: $("#pt-q").value,
      family: $("#pt-family").value,
      rank: $("#pt-rank").value,
      sort: $("#pt-sort").value,
    };
    draw();
  };
  ["pt-q", "pt-family", "pt-rank", "pt-sort"].forEach((id) => $("#" + id).addEventListener("input", filter));
  petsView = {
    dispose() {
      st.alive = false;
      clearTimeout(st.timer);
      clearTimeout(st.ctimer);
    },
  };
  refresh();
  refreshCollection();
}
