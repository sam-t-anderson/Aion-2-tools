/* The Pet Tracker window (pet-overlay.html): polls GET /api/pettracker about once a second and draws Pet Tracker's
   rows with pet-tracker.js; Recent/Nearby, Hide maxed and the row stars go back to Pet Tracker's capture
   (POST /api/pettracker), so its own window, when open, shows the same. Lock, Hide, opacity, click-through and the
   fit-to-content window work as on the radar's window (overlay.js). */
(function () {
  "use strict";
  window.A2OverlayUp = "starting";
  const $ = (s) => document.querySelector(s);
  const P = window.A2Pets;
  let nativeReady = false, op = 0.9, locked = false, clickThrough = false, rectTimer = 0, timer = 0, busy = false, last = null;
  try { const v = parseFloat(localStorage.getItem("ovopacity-pets")); if (v >= 0.2 && v <= 1) op = v; } catch (e) { /* optional storage */ }
  // Write a readout only when it changes: a write of the same content still costs a style and layout pass.
  const setText = (el, text) => { if (el && el._a2text !== text) { el._a2text = text; el.textContent = text; } };
  const setHtml = (el, html) => { if (el && el._a2html !== html) { el._a2html = html; el.innerHTML = html; return true; } return false; };

  function nativeCall(name, ...args) {
    const api = nativeReady && window.pywebview?.api;
    if (api && typeof api[name] === "function") api[name](...args).catch(() => {});
  }
  // Click-through (Settings → overlay click-through): the window passes clicks to the game except over its controls,
  // whose boxes the native side needs in device pixels.
  function reportRects() {
    if (!clickThrough) return;
    const dpr = window.devicePixelRatio || 1, rects = [];
    document.querySelectorAll("#ov button, #ov input, #ov label, #ov a").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) rects.push([r.left * dpr, r.top * dpr, r.right * dpr, r.bottom * dpr]);
    });
    nativeCall("set_interactive_rects", rects);
  }
  function applyClickThrough(on) {
    if (clickThrough === !!on && rectTimer) return;
    clickThrough = !!on;
    nativeCall("set_click_through", clickThrough);
    clearInterval(rectTimer); rectTimer = 0;
    if (clickThrough) { reportRects(); rectTimer = setInterval(reportRects, 2000); }
  }
  let fitQueued = false;
  function fit() {
    if (fitQueued) return;
    fitQueued = true;
    requestAnimationFrame(() => {
      fitQueued = false;
      const r = $("#ov").getBoundingClientRect();
      nativeCall("fit", Math.ceil(r.width), Math.ceil(r.height));
    });
  }
  function applyOpacity() {
    document.documentElement.style.setProperty("--ovbg", op);
    nativeCall("set_opacity", op);
  }
  function nativeInit() {
    nativeReady = true;
    document.documentElement.classList.toggle("native-windows", window.pywebview?.platform === "edgechromium");
    applyOpacity(); fit();
    nativeCall("set_click_through", clickThrough);
    if (clickThrough) reportRects();
  }
  window.addEventListener("pywebviewready", nativeInit);
  if (window.pywebview?.api?.fit) nativeInit();
  new ResizeObserver(fit).observe($("#ov"));

  function render(state) {
    last = state;
    const st = P.status(state), line = $("#ptstatus");
    setText(line, st.text);
    line.title = st.title || "";
    line.dataset.tone = st.tone;
    const o = (state && state.options) || {}, live = !!(state && state.connected);
    document.querySelectorAll("[data-mode]").forEach((b) => {
      const on = b.dataset.mode === (o.mode || "Recent");
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
      b.disabled = !live;
    });
    const hide = $("#pthidemax");
    hide.checked = !!o.hide_maxed;
    hide.disabled = !live;
    $("#ptsync").hidden = !(state && state.sync_notice);
    document.documentElement.style.setProperty("--pt-accent", P.accent(state));
    $("#ov").classList.toggle("pt-compact", !!o.compact);
    if (setHtml($("#ptrows"), P.rows(state)) && clickThrough) reportRects();
  }
  function showError(err) {
    const line = $("#ptstatus");
    setText(line, err && err.message ? err.message : String(err));
    line.dataset.tone = "off";
  }
  async function poll() {
    clearTimeout(timer);
    if (!busy && !locked) {
      busy = true;
      try {
        const r = await fetch("/api/pettracker", { cache: "no-store" });
        if (r.ok) render(await r.json());
      } catch (e) {
        render(null);
      } finally {
        busy = false;
      }
    }
    timer = setTimeout(poll, last && last.connected ? 1000 : 2000);
  }

  document.querySelectorAll("[data-mode]").forEach((b) => {
    b.onclick = () => P.control({ action: "mode", value: b.dataset.mode }).then(render).catch(showError);
  });
  $("#pthidemax").onchange = (e) => P.control({ action: "hide_maxed", value: e.target.checked }).then(render).catch(showError);
  $("#ptrows").addEventListener("click", (e) => {
    const link = e.target.closest("[data-link]");
    if (link) {
      link.disabled = true;
      P.control({ action: "link", character: link.dataset.link }).then(render).catch(showError);
      return;
    }
    const b = e.target.closest("[data-pin]");
    if (!b) return;
    P.control({ action: "pin", pet: Number(b.dataset.pin), value: b.getAttribute("aria-pressed") !== "true" }).then(render).catch(showError);
  });
  // Hide closes this window and turns its setting off; Settings → Pet Tracker or its hotkey shows it again.
  $("#ovhide").onclick = () => fetch("/api/overlay", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "hide", view: "pets" }) }).then(() => window.close());
  const lockBtn = $("#ovlock");
  lockBtn.onclick = () => {
    locked = !locked;
    lockBtn.textContent = locked ? "Unlock" : "Lock";
    lockBtn.classList.toggle("on", locked);
    $("#ov").classList.toggle("ov-locked", locked);
    nativeCall("set_locked", locked);
    if (!locked) poll();
  };
  const slider = $("#ovop");
  slider.value = String(Math.round(op * 100));
  slider.oninput = () => {
    op = Number(slider.value) / 100;
    applyOpacity();
    try { localStorage.setItem("ovopacity-pets", String(op)); } catch (e) { /* optional storage */ }
  };
  // Controls must not start a drag of the card, the rows' stars included (they are redrawn, so this listens above them).
  const stop = (e) => e.stopPropagation();
  ["pointerdown", "mousedown", "touchstart"].forEach((type) => {
    document.querySelectorAll(".ovhd button, .pttools button, .pttools label, .ovfoot input, .ovfoot label").forEach((c) => c.addEventListener(type, stop));
    $("#ptrows").addEventListener(type, (e) => { if (e.target.closest("button")) e.stopPropagation(); });
  });
  function syncSettings() {
    fetch("/api/ui", { cache: "no-store" }).then((r) => r.json()).then((ui) => applyClickThrough(ui.overlay_click_through === true)).catch(() => {});
  }
  syncSettings();
  setInterval(syncSettings, 10000);
  poll();
  window.A2OverlayUp = "ready";
})();
