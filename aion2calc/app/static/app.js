/* aion2calc front end — vanilla JS, no build step.
   This script holds what every page shares: the helpers, the navigation, the theme and accent, the router and the
   launch. Each page is drawn by its own script in pages/, which index.html loads after this one; the app starts
   once they have all loaded. */
"use strict";

// ------------------------------------------------------------------ helpers
const DISCORD = "https://discord.gg/9y6zkUyvBv";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
const sp = (x) => (x == null ? "—" : (x >= 0 ? "+" : "") + (100 * x).toFixed(1) + "%");
// Every date the app shows carries the time of day, in the computer's clock: 2026-10-23 15:04:05. Each script that
// shows a date carries this same line (tests/test_date_time_stamps.py compares them), so the formatter leaves it as is.
// prettier-ignore
const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
// prettier-ignore
const clockAt = (x) => { const s = whenAt(x); return s.length > 11 ? s.slice(11) : s; }; // the time of day alone, 15:04:05
// A server by its world name (2102 -> Zikel) from the bundled list; `fallback` (or the ID) when unknown.
const worldFor = (id, fallback) => (window.A2Servers ? A2Servers.label(id, fallback) : (fallback ?? String(id ?? "")));
const icon = (u) => {
  const source = u ? "/api/icon?u=" + encodeURIComponent(u.startsWith("/") ? "https://metabot.gg" + u : u) : "";
  return window.A2AssetHealth ? A2AssetHealth.source(source) : source;
};
const assetAttrs = (kind, item) =>
  window.A2AssetHealth?.attributes(
    item?.item_id
      ? { namespace: "official", kind, id: item.item_id, region: item.item_region }
      : { namespace: "metabot", kind, id: item?.item_slug || item?.slug },
  ) || "";
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
const app = () => $("#page-body"); // a page renders here, inside <main id="app"> after its heading

async function api(path, body, signal) {
  const opt =
    body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  if (signal) opt.signal = signal;
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: r.statusText }));
  const captureStatus = path.split("?")[0] === "/api/meter" && typeof j.running === "boolean" && j.snapshot;
  if (!r.ok || (j.error && !captureStatus)) throw new Error(j.error || r.statusText);
  return j;
}
// A status document whose "error" is part of what it reports (why RTSS or the radar is not running), not a
// failed request, which api() would make of it.
async function apiState(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}
// The log server's public routes, through this app's proxy.
const communityAPI = (path, body) =>
  body ? api("/api/community", { path, body }) : api("/api/community?path=" + encodeURIComponent(path));
async function runJob(path, body, onLog) {
  const { job } = await api(path, body);
  for (;;) {
    await new Promise((r) => setTimeout(r, 1200));
    const j = await api("/api/jobs/" + job);
    onLog && onLog(j.log || []);
    if (j.status === "done") return j.result;
    if (j.status === "error") throw new Error(j.error);
  }
}
function copyText(t) {
  navigator.clipboard?.writeText(t).then(
    () => toast("Copied to clipboard"),
    () => toast("Copy failed"),
  );
}
function toast(msg, duration = 4000) {
  const d = document.createElement("div");
  d.setAttribute("role", "status");
  d.textContent = msg;
  Object.assign(d.style, {
    position: "fixed",
    bottom: "20px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "#1c2438",
    border: "1px solid rgba(233,203,128,.6)",
    padding: "8px 16px",
    borderRadius: "6px",
    zIndex: 99,
    color: "#e8cf8e",
  });
  document.body.appendChild(d);
  setTimeout(() => d.remove(), duration);
}
const statGrid = (rows, title = "Stats from this system") =>
  rows && rows.length
    ? `<div class="statsum"><h4>${esc(title)}</h4><div class="statgrid">${rows
        .map((r) => `<div><span>${esc(r.label)}</span><span>${esc(r.text)}</span></div>`)
        .join("")}</div></div>`
    : "";
const kv = (pairs) =>
  `<div class="statgrid">${pairs.map(([k, v]) => `<div><span>${esc(k)}</span><span>${v}</span></div>`).join("")}</div>`;

// "my screenshot" — users can pin their own in-game screenshot next to a window
function shotTools(key) {
  return `<button class="btn small" data-shot="${key}" title="Put your in-game screenshot of this window next to it">My screenshot</button>`;
}
function shotBlock(key) {
  let src = null;
  try {
    src = localStorage.getItem("shot:" + key);
  } catch (e) {}
  return src
    ? `<div class="shot"><div class="row small muted">Your in-game screenshot <button class="btn small" data-shot-del="${key}">remove</button></div><img src="${src}" alt="screenshot"></div>`
    : "";
}
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-shot]");
  if (b) {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "image/*";
    inp.onchange = () => {
      const f = inp.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = () => {
        try {
          localStorage.setItem("shot:" + b.dataset.shot, rd.result);
        } catch (e) {
          toast("Image too large to keep");
        }
        route();
      };
      rd.readAsDataURL(f);
    };
    inp.click();
  }
  const d = ev.target.closest("[data-shot-del]");
  if (d) {
    try {
      localStorage.removeItem("shot:" + d.dataset.shotDel);
    } catch (e) {}
    route();
  }
  const c = ev.target.closest("[data-copy]");
  if (c && window.__copy && window.__copy[c.dataset.copy]) copyText(window.__copy[c.dataset.copy]);
});
window.__copy = {};

function win(title, sub, body, { key, tools = "", copy } = {}) {
  if (copy && key) window.__copy[key] = copy;
  return `<section class="win"><div class="wh"><h2>${esc(title)}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}
    <div class="tools">${copy ? `<button class="btn small" data-copy="${key}">Copy as text</button>` : ""}${key ? shotTools(key) : ""}${tools}</div></div>
    <div class="wb">${body}${key ? shotBlock(key) : ""}</div></section>`;
}

// ------------------------------------------------------------- the pages' state and the navigation
// Each page's state, kept between visits (S.ui: the UI settings, read at launch).
const S = {
  commonComparisons: {},
  planner: { win: "overview" },
  character: { win: "overview" },
  combat: {},
  database: {},
  gear: {},
  raid: {},
  meter: {},
  ui: {},
};
// The navigation's pages (id, label): the choices for the page the app opens on at launch.
const PAGES = [
  ["meter", "Live Meter"],
  ["combat", "Combat Logs"],
  ["raid", "Raid Planner"],
  ["planner", "Build Planner"],
  ["builds", "Builds"],
  ["character", "My Character"],
  ["gear", "Gear & Advice"],
  ["history", "Saved Results"],
  ["timers", "Timers"],
  ["maps", "Maps"],
  ["database", "Database"],
  ["crafting", "Crafting"],
  ["pets", "Pet Tracker"],
  ["news", "News"],
  ["settings", "Settings"],
];
// The navigation (index.html) has three sections, Combat, Character and Game, and Settings. The row under
// them lists the pages of the current page's section; a section's link opens the page last used in it, and
// on Settings, which is in no section, the row keeps the last section's pages.
const NAV_LAST = "nav-last-pages";
function sectionOf(page) {
  if (!PAGES.some(([id]) => id === page)) return null; // only known ids reach the selector
  const link = $(`.subnav a[data-page="${page}"]`);
  return link ? link.closest("[data-pages]").dataset.pages : null;
}
function showNavigation(page) {
  const current = page === "combat-log" ? "combat" : page,
    section = sectionOf(current);
  let last = {};
  try {
    last = JSON.parse(localStorage.getItem(NAV_LAST) || "{}") || {};
  } catch (e) {}
  if (section) {
    last[section] = current;
    try {
      localStorage.setItem(NAV_LAST, JSON.stringify(last));
    } catch (e) {}
  }
  const shown = section || S.navSection || "combat";
  S.navSection = shown;
  $$(".nav a[data-section]").forEach((a) => {
    const name = a.dataset.section;
    if (last[name] && sectionOf(last[name]) === name) a.href = "#/" + last[name];
    a.classList.toggle("on", name === section);
    if (name === section) a.setAttribute("aria-current", "true");
    else a.removeAttribute("aria-current");
  });
  $$(".subnav [data-pages]").forEach((group) => {
    group.hidden = group.dataset.pages !== shown;
  });
  const row = $(".subnav"),
    heading = $(`.nav a[data-section="${shown}"]`);
  if (row && heading) row.setAttribute("aria-label", heading.textContent + " pages");
  $$(".nav a[data-page], .subnav a[data-page]").forEach((a) => {
    const on = a.dataset.page === current;
    a.classList.toggle("on", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  // The page's main heading (index.html), for screen readers.
  const title = $("#page-title"),
    label = (PAGES.find(([id]) => id === current) || [])[1];
  if (title) title.textContent = page === "combat-log" ? "Combat log" : label || "Aion 2 Calc";
}
// The app's text size (Settings → Text size): a percentage applied as the page's zoom, so every word and the
// layout around it scale together, as the browser's own zoom would. 100 is the size the app ships with.
function applyTextScale(ui) {
  const pct = Math.max(70, Math.min(150, parseInt((ui || {}).app_text_scale, 10) || 100));
  document.body.style.zoom = pct === 100 ? "" : String(pct / 100);
}

// ------------------------------------------------------------- theme & accent
const THEMES = ["system", "light", "dark"];
function getTheme() {
  try {
    return localStorage.getItem("theme") || "system";
  } catch (e) {
    return "system";
  }
}
function setTheme(t) {
  try {
    localStorage.setItem("theme", t);
  } catch (e) {}
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  const b = $("#theme");
  if (b) {
    b.textContent = { system: "◐", light: "☀", dark: "☾" }[t];
    b.title = `Theme: ${t === "system" ? "follow the computer" : t} (click to change)`;
  }
}
$("#theme").onclick = () => setTheme(THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length]);
setTheme(getTheme());

// Accent-colour preset for the whole app UI (works alongside the light/dark
// theme). "gold" is the default and sets no attribute; others map to the
// data-accent CSS rules in app.css.
const ACCENTS = ["gold", "crimson", "emerald", "azure", "amethyst", "rose"];
function getAccent() {
  try {
    const a = localStorage.getItem("accent") || "gold";
    return ACCENTS.includes(a) ? a : "gold";
  } catch (e) {
    return "gold";
  }
}
function setAccent(a) {
  if (!ACCENTS.includes(a)) a = "gold";
  try {
    localStorage.setItem("accent", a);
  } catch (e) {}
  if (a === "gold") delete document.documentElement.dataset.accent;
  else document.documentElement.dataset.accent = a;
}
setAccent(getAccent());

// ------------------------------------------------------------- router
// Each page shown counts up: a page left while it still loads can fail on the page that replaced it, and its
// error is no longer the current page's to show.
let routeSerial = 0;
// For a page that waits before it draws: whether it is still the page shown, or the player has moved on.
const stillShown = () => {
  const serial = routeSerial;
  return () => serial === routeSerial;
};
async function route() {
  const serial = ++routeSerial;
  if (workshopView) {
    workshopView.dispose();
    workshopView = null;
  }
  if (buildWorkspaceView) {
    buildWorkspaceView.dispose();
    buildWorkspaceView = null;
  }
  if (eventTimerView) {
    eventTimerView.dispose();
    eventTimerView = null;
  }
  if (petsView) {
    petsView.dispose();
    petsView = null;
  }
  const page = (location.hash.replace(/^#\//, "") || "meter").split("/")[0];
  $("#app").classList.toggle(
    "workspace-wide",
    page === "crafting" || page === "builds" || page === "maps" || page === "combat-log",
  );
  $("#app").classList.toggle("logs-zoom", page === "combat" || page === "combat-log"); // 125%, as on the website
  showNavigation(PAGES.some(([id]) => id === page) || page === "combat-log" ? page : "planner"); // an unknown page shows the planner
  if (page !== "combat-log" && S.combat.review) {
    S.combat.review.dispose();
    S.combat.review = null;
  }
  try {
    if (page === "character") await pageCharacter();
    else if (page === "history") await pageHistory();
    else if (page === "gear") await pageGear();
    else if (page === "settings") await pageSettings();
    else if (page === "combat") await pageCombat();
    else if (page === "combat-log") await pageCombatLog();
    else if (page === "raid") await pageRaid();
    else if (page === "meter") await pageMeter();
    else if (page === "database") await pageDatabase();
    else if (page === "maps" || page === "crafting") await pageWorkshop(page);
    else if (page === "builds") await pageBuilds();
    else if (page === "timers") await pageTimers();
    else if (page === "news") await pageNews();
    else if (page === "pets") await pagePets();
    else await pagePlanner();
  } catch (e) {
    if (serial !== routeSerial) return;
    app().innerHTML = `${page === "combat-log" ? '<p><a class="btn small" href="#/combat">← Back to combat logs</a></p>' : ""}<div class="note">${esc(e.message)}</div>`;
  }
}

// ------------------------------------------------------------- top bar
let syncPillFirst = true;
async function syncPill() {
  try {
    // The first poll after the window opens asks for a fresh release check (a window reopened from
    // the tray is the same process; its last check may predate a new release).
    const s = await api("/api/status" + (syncPillFirst ? "?fresh=1" : ""));
    syncPillFirst = false;
    const sy = s.sync,
      el = $("#syncpill");
    const running = sy && sy.running;
    el.innerHTML = `<span class="dot ${running ? "run" : sy && sy.errors && sy.errors.length ? "err" : "ok"}"></span><span>${
      running
        ? `updating database · ${esc(sy.phase)} ${sy.total ? `${sy.done}/${sy.total}` : ""}`
        : `database ${n0(s.db.items)} items`
    }</span>`;
    const up = $("#update");
    if (s.update && up) {
      up.hidden = false;
      up.href = s.update.url;
      up.textContent = `Version ${s.update.version} available`;
    }
    // One prompt per window, for the newest release. It used to ask once per version, so every
    // release published while the app ran asked again and a copy several versions behind was walked
    // through them one at a time. A newer release now only updates the chip; the prompt re-checks
    // first, so it names the newest one, which is what Install installs.
    if (s.update && s.update_prompt !== false && !sessionStorage.getItem("update-prompted")) {
      sessionStorage.setItem("update-prompted", "1");
      setTimeout(async () => {
        let latest = s.update;
        try {
          const c = await api("/api/update/check", {});
          if (c.update) latest = c.update;
          else if (!(c.update_state || {}).error) return; // a fresh check found nothing newer
        } catch (e) {
          /* keep what the last check found */
        }
        if (
          !confirm(
            `Aion 2 Calc ${latest.version} is ready (you have ${s.version}). Install it now?\n\nThis installs the newest version directly, not the versions in between.`,
          )
        )
          return;
        try {
          const r = await api("/api/update", {});
          if (r.status === "launching")
            document.body.innerHTML =
              '<div class="empty" style="margin-top:20vh">Aion 2 Calc is closing. The installer will open in a moment.</div>';
          else
            toast(
              {
                downloaded: "Update downloaded. Open the updates folder to install it.",
                "download-failed": "The update download failed.",
                "check-failed": "Could not reach GitHub for the update. Try again in a minute.",
                "up-to-date": "Already up to date.",
              }[r.status] || r.status,
            );
        } catch (e) {
          toast("Update failed: " + e.message);
        }
      }, 250);
    }
    $("#quit").title = `Stop the app (version ${s.version || ""})`;
    // While the release check is still running, look again in two seconds rather than twenty.
    const checking = !s.update && s.update_state && s.update_state.checking;
    setTimeout(syncPill, running ? 2500 : checking ? 2000 : 20000);
  } catch (e) {
    setTimeout(syncPill, 20000);
  }
}
$("#quit").onclick = async () => {
  if (!confirm("Stop aion2calc? Start it again from the Start menu or desktop shortcut.")) return;
  try {
    localStorage.setItem("aion2calc-closing", String(Date.now()));
  } catch (e) {
    /* native overlay is closed by the server */
  }
  await api("/api/quit", {}).catch(() => {});
  document.body.innerHTML =
    '<div class="empty" style="margin-top:20vh">aion2calc has stopped. You can close this tab.</div>';
  setTimeout(() => window.close(), 250);
};
$("#app-screenshot").onclick = async () => {
  const button = $("#app-screenshot"),
    status = $("#app-screenshot-status");
  button.disabled = true;
  try {
    await A2Screenshot.capture(
      (body) => api("/api/screenshot", body),
      (text) => (status.textContent = text),
    );
  } catch (e) {
    status.textContent = "Screenshot failed: " + e.message;
  } finally {
    button.disabled = false;
  }
};

// ------------------------------------------------------------- launch
// Once every page's script has loaded (pages/*.js follow this one in index.html): the text size and the page to
// open on come from the UI settings; an empty hash (the app's own window, the tray icon, the Open-app hotkey)
// opens the chosen page, a hash in the URL wins as before.
document.addEventListener("DOMContentLoaded", async () => {
  window.addEventListener("hashchange", route);
  try {
    S.ui = await api("/api/ui");
  } catch (e) {
    S.ui = {};
  }
  applyTextScale(S.ui);
  const page = PAGES.some(([id]) => id === S.ui.app_default_page) ? S.ui.app_default_page : "meter";
  if (!location.hash && page !== "meter") {
    location.hash = "/" + page;
    return;
  } // hashchange routes it
  route();
});
// The app keeps running while a page of it is open: a browser tab's app stops once no page has pinged it for a while.
setInterval(() => fetch("/api/ping", { method: "POST" }).catch(() => {}), 20000);
syncPill();
// Uploads became public by default (0.2.323): an install that had the old default, unlisted, is told once.
api("/api/logserver")
  .then((c) => {
    if (!c || !c.visibility_notice) return;
    toast(
      "Your uploads are now public: they appear in the community logs and count in the rankings. To keep them link-only, choose unlisted (or private) in Settings → Log server.",
      15000,
    );
    api("/api/logserver", { action: "notice-seen" }).catch(() => {});
  })
  .catch(() => {});
