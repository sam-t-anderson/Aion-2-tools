/* Live Meter (#/meter): the packet capture, the live parse and the fights recorded. */
"use strict";

async function meterStatus() {
  const controller = new AbortController(),
    timeout = setTimeout(() => controller.abort(), 8000);
  try {
    return await api("/api/meter", undefined, controller.signal);
  } finally {
    clearTimeout(timeout);
  }
}
function replaceMeterHtml(element, html) {
  // Reuse decoded image nodes across live updates instead of loading every icon again.
  const images = new Map();
  element.querySelectorAll("img").forEach((node) => {
    const key = node.dataset.skillSource || node.getAttribute("src");
    if (!images.has(key)) images.set(key, []);
    images.get(key).push(node);
  });
  const template = document.createElement("template");
  template.innerHTML = html;
  template.content.querySelectorAll("img").forEach((node) => {
    const key = node.dataset.skillSource || node.getAttribute("src"),
      old = images.get(key)?.shift();
    if (old) node.replaceWith(old);
  });
  element.replaceChildren(template.content);
}

// The recording player's Odyle Energy (from the game's own counter records) beside its recharge-item icon.
const ODYLE_ICON = "https://metabot.gg/web/aion2/items/icon_item_odenergy_a_001a.webp";
function odyleLine(o) {
  if (!o) return "";
  const src = window.A2AssetHealth ? A2AssetHealth.source(ODYLE_ICON) : ODYLE_ICON;
  const regular = Number(o.regular) || 0,
    bonus = Number(o.bonus) || 0;
  return `<p class="small muted odyle" title="Your Odyle Energy, as the game sent it: the regular energy regenerates 15 every 3 hours, and a claimed reward cube spends it first, then the bonus"><img src="${esc(src)}" alt="" width="20" height="20"> Odyle Energy ${(regular + bonus).toLocaleString()}${bonus ? ` (${regular.toLocaleString()} + ${bonus.toLocaleString()} bonus)` : ""}</p>`;
}
// Your Shugo Festival Reward Keys (the game's counter 1, since 0.2.332), on the Live Meter page under the Odyle line.
function shugoLine(o) {
  if (!o) return "";
  const regular = Number(o.regular) || 0,
    bonus = Number(o.bonus) || 0;
  return `<p class="small muted odyle" title="Your Shugo Festival Reward Keys, as the game sent them: the regular keys, then the bonus ones (the same count the festival window shows)"><i class="keyicon" aria-hidden="true"></i> Shugo Keys ${(regular + bonus).toLocaleString()}${bonus ? ` (${regular.toLocaleString()} + ${bonus.toLocaleString()} bonus)` : ""}</p>`;
}
// Your Nightmare tickets (the game's counter 4, the one 0.2.329 took for the Shugo keys), under the Shugo line.
function nightmareLine(o) {
  if (!o) return "";
  const regular = Number(o.regular) || 0,
    bonus = Number(o.bonus) || 0;
  return `<p class="small muted odyle" title="Your Nightmare tickets, as the game sent them: the regular tickets, then the bonus ones, spent one at a time, the regular first"><i class="ticketicon" aria-hidden="true"></i> Nightmare Tickets ${(regular + bonus).toLocaleString()}${bonus ? ` (${regular.toLocaleString()} + ${bonus.toLocaleString()} bonus)` : ""}</p>`;
}
function parseFromMeter(snap, idx) {
  const p = (snap.players || [])[idx];
  if (!p) return null;
  return {
    name: p.name,
    cls: p.class,
    gs: null,
    cp: null,
    dmg: p.damage,
    dps: p.dps,
    contrib: p.share,
    duration: snap.duration,
    boss: snap.boss,
    highest: null,
    rates: {
      crit: p.crit,
      double: p.double ?? null,
      perfect: p.perfect ?? null,
      multi: p.multi ?? null,
      back: p.back ?? null,
      front: p.front ?? null,
      parry: p.parry ?? null,
    },
    skills: (p.skills || []).map((s) => ({
      skill: s.skill,
      skill_id: s.skill_id,
      hits: s.hits,
      dps: (s.damage || 0) / (snap.duration || 1),
      avg: (s.damage || 0) / (s.hits || 1),
      min: s.min ?? null,
      max: s.max ?? null,
      damage: s.damage,
      share: s.share,
    })),
    rotation: [],
    timeline: p.timeline || null,
    incoming: p.incoming,
    healing: p.healing,
    live: true,
  };
}
async function pageMeter() {
  const st = S.meter,
    shown = stillShown();
  const ui = await api("/api/ui");
  if (!shown()) return;
  st.lastMeterRender = null; // The previous DOM was removed when leaving this page.
  app().innerHTML = `<section class="win"><div class="wh"><h2>Live damage meter</h2><span class="sub">built-in A2Tools packet capture, live analysis and a2log sharing</span></div>
    <div class="wb"><div class="row"><label class="muted small" for="msrc">Source</label>
        <select id="msrc"><option value="a2tools" selected>Live Capture</option><option value="replay">Demo replay</option><option value="live">Custom decoder</option></select>
        <button class="btn primary" id="mstart" aria-pressed="false">Start</button>
        <label class="small muted"><input id="mautooverlay" type="checkbox" ${ui.overlay_on_start !== false ? "checked" : ""}> Show overlay when starting</label>
        <button class="btn small" id="mclear">Clear session</button><button class="btn small" id="msave">Save to Combat Logs</button><button class="btn small" id="mexport">Export a2log</button>
        <button class="btn small" id="mupload">Upload</button><button class="btn small" id="mshot">Screenshot</button>
        <button class="btn small" id="msplit">Split now</button><button class="btn small" id="mfinishrun">Finish run</button><button class="btn small" id="mhide">Hide overlay</button><button class="btn small" id="movl" title="Open the compact overlay in a separate window">Open overlay</button><span id="mmsg" class="small muted"></span></div>
      <div class="row" id="mcustom" style="display:none;margin-top:6px"><label class="small muted">Decoder file <input id="mcustomdec" type="file" accept=".py"></label><span id="mdecodername" class="small muted">Choose a trusted Python decoder. Its code runs when capture starts.</span></div>
      <div id="npcap" class="small" role="status" style="margin-top:8px" hidden></div>
      <div class="row" style="margin-top:8px"><label class="small muted">Players <select id="mscope"><option value="auto">Automatic · allow partial metrics</option><option value="party" selected>Self + Party</option><option value="self">Self only</option><option value="all">All observed players</option></select></label><label class="small muted"><input id="mcombinepets" type="checkbox" checked> Combine pets with owner</label><label class="small muted"><input id="mautosplit" type="checkbox" checked> Automatic splits</label><label class="small muted">Split after no outgoing damage for <input id="msegap" type="number" min="120" max="3600" value="120" style="width:69px"> seconds</label><label class="small muted">Combat <select id="msegments"><option value="">Latest combat</option><option value="all">Whole session</option></select></label><button class="btn small" id="mallenemies">All enemies</button><button class="btn small" id="mfollow" hidden>Follow latest combat</button><span id="mviewstate" class="small muted" role="status"></span></div>
      <div class="row" style="margin-top:4px"><button class="btn small" id="mregionretry" style="display:none">Retry region detection</button><span class="small muted" id="mregionmsg" role="status"></span></div>
      <div id="mrun" class="small" role="status"></div><div id="midentity" class="small" role="status"></div><div id="msaved" class="small" role="status"></div><div id="mnotice" class="small" role="status"></div>
      <details class="note" id="madvanced" style="margin-top:10px"><summary><b>Advanced capture</b> <span class="small muted">network interface and game port, name override, game installation, final boss, diagnostics</span></summary>
        <div class="row" id="mlive" style="display:none;margin-top:6px">
        <label class="small muted">Encoder <input id="mdec" type="text" value="Built-in A2Tools decoder" readonly aria-label="Encoder module" style="width:206px"></label>
        <label class="small muted">Interface <select id="miface" aria-label="Capture interface" title="Npcap interface; Auto monitors all available adapters"><option value="auto">Auto</option></select></label><button class="btn small" id="mifacesrefresh">Refresh interfaces</button>
        <label class="small muted">Game host <input id="mhost" type="text" value="any" aria-label="Game host" style="width:115px" title="Use an address to limit the capture; any accepts game traffic on the port"></label>
        <label class="small muted"><input id="mautoport" type="checkbox" checked> Detect game port</label><label class="small muted">Fixed port <input id="mport" type="number" value="50349" aria-label="Game server port" style="width:92px"></label>

        <label class="small muted">Name override (optional) <input id="mchar" type="text" placeholder="Auto-detect" style="width:138px"></label></div>
        <div class="row"><label class="small">Game installation <select id="minstall"><option value="">Auto (one installed copy)</option></select></label><button class="btn small" id="minstallrefresh">Refresh installations</button><span class="small muted" id="minstallstatus" role="status"></span></div><div class="row" style="margin-top:6px"><label class="small">Add install folder manually <input id="minstallpath" type="text" placeholder="C:\\Program Files (x86)\\NC\\AION 2" style="min-width:366px"></label><button class="btn small" id="minstalladd">Add path</button><span class="small muted" id="minstalladdstatus" role="status"></span></div>
        <details class="note small"><summary id="mautometa-sum">Installed game version and capture context</summary><div id="mautometa" role="status"></div></details>
        <div class="row"><label class="small"><input id="mautofinish" type="checkbox" checked> Finish on configured final-boss death</label><label class="small">Final-boss NPC type IDs <input id="mfinalboss" placeholder="Comma-separated verified NPC IDs"></label></div><p class="small muted">Final-boss order and PvP match-end packets are not yet verified. Configure the final boss before Start, or use Finish run. Map/instance changes create separate runs without claiming completion. Capture keeps running.</p>
        <p class="small faint">Live Capture uses the included A2Tools protocol engine. It needs Npcap in WinPcap-compatible mode, Scapy, and capture permission. <span id="npcapinfo"></span> Export writes an open a2log file; Upload uses the log server configured in Settings.</p>
        <details class="note" style="margin-top:10px"><summary><b>Capture diagnostics</b> <span class="small muted">capture counters, TCP recording for diagnostics, diagnostics export</span></summary><div id="mdriverstats" class="small muted" role="status"></div>
        <div class="row"><label><input id="mrecord" type="checkbox"> Record TCP payloads for diagnostics (optional; remembered, and every capture records while it is ticked)</label><button class="btn small" id="mdiag">Export capture diagnostics</button><button class="btn small" id="mdiagfolder">Open diagnostics folder</button><span id="mrecordstatus" class="small muted"></span></div>
        <p class="small faint">Diagnostic ZIPs include capture counters, status errors and a readable summary even with TCP recording off. Open diagnostics folder to find saved ZIPs. Ticked, TCP recording additionally writes raw payloads without a record or size limit, even when no combat events are decoded: for every capture however it starts (here, the overlay's Start, the Start/Stop hotkey or the start at launch), and from the moment you tick it during a capture. Available disk space limits recording. Saves a diagnostic ZIP automatically when capture stops; long recordings take longer to compress. Raw traffic may contain character names, IP addresses and other traffic; review before sharing.</p><div id="mdiagresult" class="small" role="status"></div><div id="mdiagerror" class="small" role="alert"></div></details></details>
    </div></section><div id="mview"></div><div id="mlog-review"></div>`;
  // Advanced capture opens as the player last left it (closed at first).
  const advanced = $("#madvanced");
  try {
    advanced.open = localStorage.getItem("meter-advanced-open") === "1";
  } catch (e) {}
  advanced.ontoggle = () => {
    try {
      localStorage.setItem("meter-advanced-open", advanced.open ? "1" : "0");
    } catch (e) {}
  };
  const live = () => {
    $("#mlive").style.display = $("#msrc").value !== "replay" ? "flex" : "none";
    $("#mcustom").style.display = $("#msrc").value === "live" ? "flex" : "none";
  };
  $("#msrc").onchange = live;
  live();
  try {
    $("#mchar").value = localStorage.getItem("meter-character") || "";
  } catch (e) {}
  // Restore the "Players" scope choice so it persists across app restarts.
  try {
    const s = localStorage.getItem("meter-scope");
    if (["auto", "party", "self", "all"].includes(s)) $("#mscope").value = s;
  } catch (e) {}
  try {
    $("#mfinalboss").value = localStorage.getItem("meter-final-boss-ids") || "";
  } catch (_) {}
  $("#mfinalboss").onchange = () => localStorage.setItem("meter-final-boss-ids", $("#mfinalboss").value);
  const updateView = async (body) => {
    try {
      renderMeter(await api("/api/meter", { action: "view", ...body }));
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  // Legacy session-wide overrides must never contaminate automatic captures.
  try {
    localStorage.removeItem("meter-metadata");
  } catch (_) {}
  $("#mchar").onchange = () => {
    try {
      localStorage.setItem("meter-character", $("#mchar").value.trim());
    } catch (e) {}
    updateView({ character_name: $("#mchar").value.trim() });
  };
  $("#mcombinepets").onchange = () => updateView({ combine_pets: $("#mcombinepets").checked });
  $("#mscope").onchange = () => {
    try {
      localStorage.setItem("meter-scope", $("#mscope").value);
    } catch (e) {}
    updateView({ scope: $("#mscope").value });
  };
  $("#msegap").onchange = () => updateView({ segment_gap: +$("#msegap").value || 120 });
  $("#msplit").onclick = async () => {
    st.pinnedSegment = "";
    renderMeter(await api("/api/meter", { action: "split" }));
    $("#mnotice").textContent = "Next combat event starts a new split.";
  };
  $("#mautosplit").onchange = () => updateView({ automatic_splits: $("#mautosplit").checked });
  $("#mhide").onclick = async () => {
    await api("/api/overlay", { action: "hide" });
    if (st.overlayPopup) st.overlayPopup.close();
    $("#mnotice").textContent = "Overlay hidden. Open overlay to show it again.";
  };
  $("#msegments").onchange = () => {
    st.pinnedSegment = $("#msegments").value;
    updateView({ segment: st.pinnedSegment });
  };
  $("#mallenemies").onclick = () => updateView({ enemy: null });
  $("#mfollow").onclick = () => {
    st.pinnedSegment = "";
    updateView({ segment: null, enemy: null });
  };
  $("#mclear").onclick = async () => {
    if (!window.confirm("Clear retained combat history? Export or save it first if you want to keep a copy.")) return;
    if (st.liveReview) st.liveReview.dispose();
    if ($("#mlog-review")) $("#mlog-review").innerHTML = "";
    st.liveReviewRoot = null;
    try {
      st.pinnedSegment = "";
      renderMeter(await api("/api/meter", { action: "clear" }));
      $("#mnotice").textContent = "Combat history cleared.";
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  $("#mfinishrun").onclick = async () => {
    try {
      renderMeter(await api("/api/meter", { action: "finish-run" }));
      $("#mnotice").textContent = "Run finished. Capture continues; the next fight starts a new run.";
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  let decoderPath = null;
  $("#mcustomdec").onchange = async () => {
    const file = $("#mcustomdec").files[0];
    decoderPath = null;
    if (!file) return;
    try {
      if (file.size > 1048576) throw new Error("Decoder files must be smaller than 1 MiB");
      const imported = await api("/api/meter/decoder", { name: file.name, source: await file.text() });
      decoderPath = imported.path;
      $("#mdecodername").textContent = imported.name;
    } catch (e) {
      $("#mdecodername").textContent = e.message;
    }
  };
  const renderInstallations = (r) => {
    const select = $("#minstall");
    if (!select) return;
    select.innerHTML =
      '<option value="">Auto (one installed copy)</option>' +
      (r.installations || []).map((row) => `<option value="${esc(row.id)}">${esc(row.label)}</option>`).join("");
    if (r.selected && !(r.installations || []).some((row) => row.id === r.selected))
      select.add(new Option("Selected installation unavailable", r.selected));
    select.value = r.selected || "";
    if (r.selection_required) $("#madvanced").open = true; // the choice is under Advanced capture
    $("#minstallstatus").textContent = r.selection_required
      ? "Multiple copies found: choose the copy you play."
      : (r.installations || []).length
        ? "Selection applies to the next capture. Save and clear retained combat before changing it."
        : "No registered installation found. Capture can still run; Product version remains unavailable.";
  };
  const refreshInstallations = async () => {
    try {
      renderInstallations(await api("/api/meter/installations"));
    } catch (e) {
      const status = $("#minstallstatus");
      if (status) status.textContent = e.message;
    }
  };
  $("#minstallrefresh").onclick = refreshInstallations;
  $("#minstall").onchange = async () => {
    try {
      renderInstallations(await api("/api/meter", { action: "installation", id: $("#minstall").value }));
    } catch (e) {
      await refreshInstallations();
      $("#minstallstatus").textContent = e.message;
    }
  };
  if ($("#mregionretry"))
    $("#mregionretry").onclick = async () => {
      const b = $("#mregionretry"),
        msg = $("#mregionmsg");
      b.disabled = true;
      if (msg) msg.textContent = "Re-checking official region and world list…";
      try {
        await api("/api/meter", { action: "retry-region" });
        if (msg) msg.textContent = "Retrying — the region and world update here when it resolves.";
      } catch (e) {
        if (msg) msg.textContent = e.message;
      } finally {
        if (b.isConnected) b.disabled = false;
      }
    };
  $("#minstalladd").onclick = async () => {
    const path = $("#minstallpath").value.trim();
    if (!path) {
      $("#minstalladdstatus").textContent = "Enter the game’s install folder.";
      return;
    }
    $("#minstalladdstatus").textContent = "Checking…";
    try {
      renderInstallations(await api("/api/meter", { action: "install-path", path }));
      $("#minstallpath").value = "";
      $("#minstalladdstatus").textContent = "Added and selected.";
    } catch (e) {
      $("#minstalladdstatus").textContent = e.message;
    }
  };
  refreshInstallations();
  const refreshInterfaces = async () => {
    try {
      const r = await api("/api/meter/interfaces");
      const select = $("#miface");
      if (!select) return; // the page was left while the list loaded
      const selected = select.value;
      select.innerHTML =
        `<option value="auto">Auto</option>` +
        (r.devices || (r.interfaces || []).map((name) => ({ name, label: name })))
          .map(
            (device) =>
              `<option value="${esc(device.name)}">${esc(device.label)}${device.address ? " · " + esc(device.address) : ""}</option>`,
          )
          .join("");
      if ([...select.options].some((option) => option.value === selected)) select.value = selected;
    } catch (e) {
      const notice = $("#mnotice");
      if (notice) notice.textContent = "Could not list capture interfaces: " + e.message;
    }
  };
  $("#mifacesrefresh").onclick = refreshInterfaces;
  refreshInterfaces();
  const refreshNpcap = async () => {
    const node = $("#npcap");
    if (!node) return;
    // Nothing to do is a line under Advanced capture; anything to do shows above the meter.
    const fine = (text) => {
      node.hidden = true;
      node.textContent = "";
      if ($("#npcapinfo")) $("#npcapinfo").textContent = text;
    };
    try {
      const r = await api("/api/npcap");
      if (!r.supported) {
        fine("Npcap setup is only needed on Windows.");
        return;
      }
      if (r.installed) {
        fine(
          "Npcap is installed. Live Capture may need administrator permissions if Npcap was installed with administrator-only access.",
        );
        return;
      }
      node.hidden = false;
      if (r.detection_error) {
        node.textContent =
          r.detection_error + " Installation status is unknown; check with your administrator before reinstalling.";
        return;
      }
      if (["finding", "downloading", "opening"].includes(r.status)) {
        node.textContent = {
          finding: "Finding the current official Npcap installer…",
          downloading: `Downloading Npcap ${r.version || ""}…`,
          opening: "Opening the Npcap installer…",
        }[r.status];
        setTimeout(refreshNpcap, 1200);
        return;
      }
      if (r.status === "installer-opened") {
        node.innerHTML = `Npcap ${esc(r.version || "")} installer is open. Finish its setup, then <button class="btn small" id="npcapcheck">Check again</button>.`;
        $("#npcapcheck").onclick = refreshNpcap;
        return;
      }
      const detail = r.error ? ` ${r.error}` : "";
      node.innerHTML = `Npcap is required for Live Capture. <button class="btn small" id="npcapinstall">Install Npcap</button>${esc(detail)}`;
      $("#npcapinstall").onclick = async () => {
        if (
          !window.confirm(
            "Download the current Npcap installer from npcap.com and open it now? Npcap is installed separately and may ask for administrator approval.",
          )
        )
          return;
        node.textContent = "Starting Npcap setup…";
        try {
          await api("/api/npcap", { action: "install" });
          refreshNpcap();
        } catch (e) {
          node.textContent = e.message;
        }
      };
    } catch (e) {
      node.textContent = "Could not check Npcap: " + e.message;
    }
  };
  refreshNpcap();
  $("#mautooverlay").onchange = async () => {
    const control = $("#mautooverlay"),
      selected = control.checked;
    try {
      await api("/api/ui", { overlay_on_start: selected });
    } catch (e) {
      control.checked = !selected;
      $("#mnotice").textContent = "Could not save overlay preference: " + e.message;
    }
  };
  async function openMeterOverlay() {
    if (!st.nativeOverlayUnavailable) {
      try {
        const result = await api("/api/overlay", {});
        if (result.native) return result.already_open ? "Overlay is already open." : "Overlay opened.";
        st.nativeOverlayUnavailable = true;
      } catch (e) {
        /* Browser fallback remains available. */
      }
    }
    st.overlayPopup = window.open("/overlay", "a2overlay", "width=300,height=430");
    return st.overlayPopup ? "Overlay opened in a window." : "Overlay popup was blocked. Click Open overlay to retry.";
  }
  $("#mstart").onclick = async () => {
    const button = $("#mstart");
    if (st.captureBusy || st.finalizing) return;
    if (st.running) {
      st.captureBusy = true;
      button.disabled = true;
      try {
        $("#mnotice").textContent = "Stopping capture and saving logs…";
        const result = await api("/api/meter", { action: "stop" });
        renderMeter(result);
        $("#mnotice").textContent = result.diagnostics?.log_save_error
          ? "Capture stopped, but log saving failed: " + result.diagnostics.log_save_error
          : result.saved_log
            ? "Capture stopped. Session saved to " + result.saved_log
            : "Capture stopped. No session file was saved; check Combat Logs and capture diagnostics.";
        toast($("#mnotice").textContent, 6000);
        // Auto-upload the saved session to the configured server (on by default).
        if (result.saved_log) {
          let autoUp = true;
          try {
            const u = await api("/api/ui");
            autoUp = u.meter_auto_upload !== false;
          } catch (_) {}
          if (autoUp) {
            $("#mnotice").textContent = "Capture stopped. Uploading the log to the server…";
            try {
              const r = await runJob("/api/meter", { action: "upload" }, (lines) => {
                if (lines.length && $("#mnotice")) $("#mnotice").textContent = lines[lines.length - 1];
              });
              if ($("#mnotice"))
                $("#mnotice").innerHTML = r.url
                  ? `Capture stopped and uploaded — <a href="${esc(r.url)}" target="_blank" rel="noopener">open shared log</a>`
                  : "Capture stopped and uploaded.";
            } catch (e) {
              if ($("#mnotice"))
                $("#mnotice").textContent =
                  "Capture stopped and saved. Auto-upload failed: " + e.message + " (you can still Upload manually).";
            }
          }
        }
      } catch (e) {
        $("#mnotice").textContent = e.message;
      } finally {
        st.captureBusy = false;
        button.disabled = !!st.finalizing;
      }
      return;
    }
    const source = $("#msrc").value;
    if (source === "live" && !decoderPath) {
      $("#mnotice").textContent = "Choose a decoder .py file first.";
      return;
    }
    if (source !== "replay") {
      try {
        const setup = await api("/api/capture/setup");
        if (setup.detection_error) throw Error(setup.detection_error);
        if (setup.supported && !setup.installed) {
          if (window.confirm(setup.prompt || "Install packet-capture support now?")) {
            await api("/api/capture/setup", { action: "install" });
            $("#mnotice").textContent = `${setup.kind} setup is starting. Finish it, then press Start again.`;
          } else {
            $("#mnotice").textContent = `${setup.kind} is required before Live Capture can start.`;
          }
          return;
        }
      } catch (e) {
        $("#mnotice").textContent = "Could not check Npcap: " + e.message;
        return;
      }
    }
    const body = {
      action: "start",
      source,
      scope: $("#mscope").value,
      segment_gap: +$("#msegap").value || 120,
      decoder: source === "live" ? decoderPath : null,
      auto_port: source === "a2tools" && $("#mautoport").checked,
      automatic_splits: $("#mautosplit").checked,
      auto_finish: $("#mautofinish").checked,
      final_boss_ids: $("#mfinalboss")
        .value.split(",")
        .map((x) => x.trim())
        .filter((x) => /^\d+$/.test(x))
        .map(Number),
      iface: source !== "replay" && $("#miface").value !== "auto" ? $("#miface").value : null,
      host: source !== "replay" && $("#mhost").value !== "any" ? $("#mhost").value : null,
      port: source !== "replay" ? +$("#mport").value || 50349 : null,
      target_mode: "allTargets",
      character_name: source === "a2tools" ? $("#mchar").value || null : null,
    };
    const showOverlay = $("#mautooverlay").checked;
    st.captureBusy = true;
    button.disabled = true;
    try {
      st.pinnedSegment = "";
      const started = await api("/api/meter", body);
      renderMeter(started);
      if (!started.running) {
        $("#mnotice").textContent = started.error || "Capture did not start. Check capture diagnostics.";
        return;
      }
      $("#mnotice").textContent = "Capture started. Waiting for combat data.";
      toast("Capture started");
      if (showOverlay) {
        try {
          $("#mnotice").textContent = "Capture started. " + (await openMeterOverlay());
        } catch (e) {
          $("#mnotice").textContent = "Capture started. Could not open overlay: " + e.message;
        }
      }
    } catch (e) {
      $("#mnotice").textContent = e.message;
    } finally {
      st.captureBusy = false;
      button.disabled = !!st.finalizing;
    }
  };
  renderDiagnosticExport(st.diagnosticExport);
  $("#mdiagfolder").onclick = async () => {
    try {
      const result = await api("/api/meter", { action: "diagnostics-folder" });
      $("#mnotice").textContent = "Diagnostics folder requested: " + result.folder;
    } catch (e) {
      $("#mnotice").textContent = "Could not open diagnostics folder: " + e.message;
    }
  };
  $("#mdiag").onclick = async () => {
    try {
      st.diagnosticExport = await api("/api/meter", { action: "diagnostics" });
      renderDiagnosticExport(st.diagnosticExport);
      $("#mnotice").textContent =
        `Diagnostic ZIP saved (${n0(st.diagnosticExport.size_bytes)} bytes) to ${st.diagnosticExport.file}. ${st.diagnosticExport.records ? st.diagnosticExport.records + " raw TCP records." : "Metadata-only ZIP; raw TCP recording is off or empty."}`;
    } catch (e) {
      $("#mnotice").textContent = "Diagnostic export failed: " + e.message;
    }
  };
  $("#movl").onclick = async () => {
    $("#mnotice").textContent = "opening overlay…";
    try {
      $("#mnotice").textContent = await openMeterOverlay();
    } catch (e) {
      $("#mnotice").textContent = "Could not open overlay: " + e.message;
    }
  };
  $("#msave").onclick = async () => {
    $("#mnotice").textContent = "saving…";
    try {
      const r = await api("/api/meter", { action: "save" });
      $("#mnotice").innerHTML = `saved as encounter #${r.id} — <a href="#/combat">open in Combat Logs</a>`;
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  $("#mexport").onclick = async () => {
    $("#mnotice").textContent = "exporting…";
    try {
      const r = await api("/api/meter", { action: "export" });
      $("#mnotice").textContent = `exported ${r.file}`;
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  $("#mupload").onclick = async () => {
    $("#mnotice").textContent = "uploading…";
    try {
      const r = await runJob("/api/meter", { action: "upload" }, (lines) => {
        if (lines.length && $("#mnotice")) $("#mnotice").textContent = lines[lines.length - 1];
      });
      $("#mnotice").innerHTML = r.url
        ? `uploaded — <a href="${esc(r.url)}" target="_blank" rel="noopener">open shared log</a>`
        : "uploaded";
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  $("#mshot").onclick = async () => {
    $("#mnotice").textContent = "capturing screenshot…";
    try {
      await A2Screenshot.capture(
        (body) => api("/api/screenshot", body),
        (text) => {
          if ($("#mnotice")) $("#mnotice").textContent = text;
        },
      );
    } catch (e) {
      $("#mnotice").textContent = e.message;
    }
  };
  // Keep action feedback visible while polling updates the live readings.
  const actionLabels = {
    mdiagfolder: "Opening diagnostics folder…",
    mdiag: "Exporting diagnostic ZIP…",
    mexport: "Exporting combat log…",
    msave: "Saving combat log…",
    mupload: "Uploading combat log…",
    mshot: "Saving screenshot…",
    msplit: "Splitting encounter…",
    mfinishrun: "Finishing run…",
    mhide: "Hiding overlay…",
    movl: "Opening overlay…",
    mifacesrefresh: "Refreshing interfaces…",
  };
  for (const [id, pending] of Object.entries(actionLabels)) {
    const button = $("#" + id),
      handler = button.onclick;
    button.onclick = async () => {
      if (button.disabled) return;
      const label = button.textContent,
        notice = $("#mnotice");
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = pending;
      notice.textContent = pending;
      try {
        await handler();
        if (notice.textContent === pending)
          notice.textContent = id === "mifacesrefresh" ? "Capture interfaces refreshed." : "Action completed.";
        toast(notice.textContent, 6000);
      } catch (e) {
        notice.textContent = "Action failed: " + e.message;
        toast(notice.textContent, 6000);
      } finally {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = label;
      }
    };
  }
  const meterMountedAt = Date.now();
  // The meter is the DEFAULT route, so at launch location.hash is "" (not "#/meter") while this
  // page is already mounted. Match the router's own rule (empty hash => "meter"); otherwise the
  // first poll tick returns before rescheduling and the loop dies, leaving the Start/Stop button
  // stuck on its pre-auto-start render until the user switches tabs (which sets the hash and
  // re-mounts). That dead loop — not the poll cadence — was why the button showed "Start" at launch.
  const onMeterPage = () => (location.hash.replace(/^#\//, "") || "meter").split("/")[0] === "meter";
  const poll = async () => {
    if (!onMeterPage()) return;
    try {
      const result = await meterStatus();
      if (onMeterPage()) renderMeter(result);
    } catch (e) {
      if ($("#mmsg"))
        $("#mmsg").textContent =
          "Could not refresh the meter: " +
          e.message +
          ". Last readings retained; capture status is unknown. Export capture diagnostics, or wait for automatic retry.";
    }
    // Poll briskly for the first few seconds after opening the page so the Start/Stop button
    // catches the launch-time auto-start (it fires ~1.6s after launch) as promptly as the overlay.
    // A window that is minimized or behind another (document.hidden) polls every few seconds: the
    // overlay shows the fight; the page catches up when it is looked at again (0.2.336).
    // Performance mode (Settings → App & data) refreshes a running meter here every 1.5 s.
    const warming = Date.now() - meterMountedAt < 6000,
      light = (S.ui || {}).performance_mode === true;
    setTimeout(poll, document.hidden ? 3000 : st.running ? (light ? 1500 : 700) : warming ? 300 : light ? 2000 : 1200);
  };
  const initial = await meterStatus().catch(() => ({ snapshot: { players: [] } }));
  if (initial.source) {
    $("#msrc").value = initial.source;
    live();
  }
  // Record TCP payloads is a saved setting that every Start follows (the overlay's, the hotkey's
  // and the start at launch too); ticking it during a capture records from then on.
  $("#mrecord").checked = ui.meter_record_packets === true;
  $("#mrecord").onchange = async () => {
    const box = $("#mrecord"),
      on = box.checked;
    st.recordBusy = true;
    box.disabled = true;
    try {
      await api("/api/ui", { meter_record_packets: on });
      toast(on ? "TCP recording on: every capture records raw TCP from now on" : "TCP recording off");
      renderMeter(await meterStatus());
    } catch (e) {
      box.checked = !on;
      $("#mnotice").textContent = "Could not change TCP recording: " + e.message;
    } finally {
      st.recordBusy = false;
      box.disabled = !!st.finalizing;
    }
  };
  renderMeter(initial);
  poll();
}
function renderDiagnosticExport(r) {
  const target = $("#mdiagresult");
  if (!r || !target) return;
  if (target.dataset.savedFile === r.file) return;
  target.dataset.savedFile = r.file;
  target.innerHTML = `<a class="btn small primary" href="${esc(r.download_url)}" download>Download diagnostic ZIP</a> Saved ZIP: ${n0(r.size_bytes)} bytes · ${n0(r.records)} raw TCP records.<br>Capture packets: ${n0(r.capture_packets)} · decoded events: ${n0(r.decoded_events)} · retained effects: ${n0(r.retained_effects)}.<br>Saved on this computer: <span style="overflow-wrap:anywhere">${esc(r.file)}</span><br>Contains a readable capture-summary.txt and diagnostics.json.${r.records ? "" : "<br>Raw TCP recording was off or empty, so tcp-payloads.jsonl is intentionally empty. The ZIP still contains capture status, counters and errors. Use Open diagnostics folder to find it."}`;
}
function renderMeter(s) {
  if ($("#mdriverstats")) {
    const d = s.diagnostics || {};
    $("#mdriverstats").textContent = d.pcap_stats_sampled
      ? `Driver counters${d.pcap_stats_partial ? " (partial coverage)" : ""}: ${d.pcap_received || 0} received, ${d.pcap_dropped || 0} capture-buffer drops, ${d.pcap_if_dropped || 0} interface/driver drops. Zero does not prove loss-free capture; counts can include other traffic.`
      : "Driver counters: unavailable or not sampled. TCP reassembly monitoring is separate.";
  }

  if ($("#mcombinepets")) $("#mcombinepets").checked = s.combine_pets !== false;
  if ($("#minstall")) $("#minstall").disabled = !!s.installation_locked;
  if ($("#mautometa-sum")) {
    const m = s.automatic_metadata || {};
    $("#mautometa-sum").textContent =
      `Installed game version: ${m.installed_build || m.status || "unavailable"}${m.installed_build_source ? " (" + m.installed_build_source + ")" : ""} · ${(s.automatic_context || {}).zone || "zone not identified"} · expand for the comparison version, region and catalog coverage`;
  }
  if ($("#mautometa")) {
    const m = s.automatic_metadata || {};
    $("#mautometa").textContent =
      `Installed game version: ${m.installed_build || m.status || "unavailable"}${m.installed_build_source ? " (" + m.installed_build_source + ")" : ""}. Comparison version: ${m.game_patch ? String(m.game_patch).replace(/^version:product:/, "") : "unavailable"}. Automatic region: ${m.region || (m.region_status === "ready" ? "waiting for recorded server ID" : m.region_status) || "unavailable"}. World: ${m.server_name || (m.region_status === "ready" ? "waiting for recorded server ID" : "unavailable")}. Zone: ${(s.automatic_context || {}).zone || "not identified"}. Content: ${(s.automatic_context || {}).encounter_type || "not identified"}. Difficulty: ${(s.automatic_context || {}).difficulty || "not identified"}. Map / instance IDs: ${s.catalog_coverage?.map_id || "not recorded"} / ${s.catalog_coverage?.instance_id || "not recorded"}. ${s.catalog_coverage?.unmapped?.length || 0} unmapped catalog IDs and ${s.catalog_coverage?.npc_entities_without_type || 0} enemy references without an NPC type in this view (included in diagnostics). ${s.automatic_context?.classification?.conflicts?.length ? "Context conflict: " + s.automatic_context.classification.conflicts.join("; ") + ". " : ""}${s.automatic_context?.classification?.basis === "npc_only" ? "NPC-only instance suggestion; entry remains unverified. " : ""}${m.reason ? m.reason + " " : ""}Product version identifies comparison groups across launchers; legacy capture metadata is retained.`;
    // Offer a manual retry only when the official lookup failed (offline/blocked at launch); a
    // "ready" map that simply hasn't matched a server ID yet, or an in-progress fetch, needs no button.
    const retry = $("#mregionretry");
    if (retry) retry.style.display = m.region_status === "unavailable" ? "" : "none";
  }
  const st = S.meter;
  st.running = !!s.running;
  st.finalizing = !!s.finalizing;
  if ($("#mrun") && s.run)
    $("#mrun").textContent =
      `Run ${s.run.id} · ${s.run.closed ? "finished/boundary recorded; waiting for next fight" : "recording"}${s.run.end_reason ? " · " + s.run.end_reason : ""}`;
  if (s.diagnostic_export) st.diagnosticExport = s.diagnostic_export;
  renderDiagnosticExport(st.diagnosticExport);
  if ($("#mdiagerror"))
    $("#mdiagerror").textContent = [
      s.recording?.error
        ? `TCP recording stopped writing: ${s.recording.error}. ${s.recording.discarded_records || 0} records were not saved. Free disk space and export the retained data.`
        : "",
      s.diagnostics?.decoder_warning
        ? `${s.diagnostics.decoder_warning}. Capture continues; affected data remains unranked.`
        : "",
      s.diagnostics?.archive_deferred || "",
      s.diagnostics?.archive_error
        ? `Could not save diagnostic ZIP: ${s.diagnostics.archive_error}. Use Export capture diagnostics to retry before starting another capture.`
        : "",
      s.diagnostics?.recording_cleanup_error
        ? `Raw diagnostic cleanup failed: ${s.diagnostics.recording_cleanup_error}. The raw file remains in the diagnostics folder.`
        : "",
      s.snapshot?.decode_backlog?.catching_up
        ? `Live view is catching up (${s.snapshot.decode_backlog.queue_depth} packets queued) during a heavy fight; final totals are unaffected.`
        : "",
    ]
      .filter(Boolean)
      .join(" ");
  const button = $("#mstart");
  if (button) {
    button.disabled = !!st.captureBusy || !!s.finalizing;
    button.textContent = s.finalizing ? "Saving…" : st.running ? "Stop" : "Start";
    button.classList.toggle("danger", st.running);
    button.classList.toggle("primary", !st.running);
    button.setAttribute("aria-pressed", String(st.running));
  }
  const who = s.identity;
  if ($("#midentity")) {
    const worldName = (s.automatic_metadata || {}).server_name;
    $("#midentity").textContent = who?.id
      ? `${who.verified ? "Detected automatically" : "Matched name override"}: ${who.name || "Player #" + who.id}${who.serverId ? " · " + (worldName || worldFor(who.serverId, "server " + who.serverId)) : ""} · combat entity #${who.id} (changes between instances)`
      : "Auto-detecting your character. Start before entering an instance, or set a name override under Advanced capture.";
  }
  if ($("#midentity") && s.snapshot?.identity_status) {
    const i = s.snapshot.identity_status;
    $("#midentity").textContent +=
      ` Selected combat: ${i.self_identified ? "Self identified" : "Self identity not received"} · ${i.unnamed_actors} unnamed actors · ${i.linked_pets} linked pets. Unknown actors remain separate until identity/owner links arrive.`;
  }
  if ($("#msaved"))
    $("#msaved").textContent =
      s.diagnostics?.log_save_error ||
      (s.diagnostics?.archive_parts_saved
        ? `${s.diagnostics.archive_parts_saved} earlier archive part(s) saved in Combat Logs. Upload combines every part into one recording; live view and export show the current part. `
        : "") +
        (s.saved_log
          ? "Latest saved part: " + s.saved_log
          : "Current part checkpoints every 15 seconds and saves on Stop.");
  // The live review panel: refreshed every four seconds, or every eight times what the last export
  // took when that is longer (a long fight's log takes most of a second to export), and never while
  // this window is hidden; the server serves the last export again while nothing changed (0.2.336).
  if (
    s.snapshot?.players?.length &&
    $("#mlog-review") &&
    !st.reviewLoading &&
    !document.hidden &&
    Date.now() - (st.reviewAt || 0) > Math.max(4000, 8 * (st.reviewCostMs || 0))
  ) {
    st.reviewLoading = true;
    st.reviewAt = Date.now();
    api("/api/meter/log")
      .then((doc) => {
        st.reviewCostMs = Number(doc.review_cost_ms) || 0;
        const target = $("#mlog-review");
        if (!target) return;
        if (st.liveReviewRoot !== target) {
          if (st.liveReview) st.liveReview.dispose();
          st.liveReview = A2CombatReview.mount(target, doc, { ...localReviewOptions(), live: true });
          st.liveReviewRoot = target;
        } else st.liveReview.update(doc);
      })
      .catch(() => {})
      .finally(() => {
        st.reviewLoading = false;
      });
  }
  const record = $("#mrecord");
  if (record) record.disabled = !!s.finalizing || !!st.recordBusy;
  if ($("#mclear")) $("#mclear").disabled = st.running || !!s.finalizing;
  const recordStatus = $("#mrecordstatus");
  const recorded = `${s.recording?.records || 0} TCP payload records · ${((s.recording?.disk_bytes || 0) / 1048576).toFixed(1)} MiB on disk`;
  if (recordStatus)
    recordStatus.textContent = s.recording?.enabled
      ? `Recording raw TCP · ${recorded} · no record limit`
      : s.recording?.records
        ? `Raw TCP recording off · ${recorded}, kept for this capture's diagnostic ZIP`
        : "Raw TCP recording is off · not required for live combat capture";
  const snap = s.snapshot || { players: [] },
    msg = $("#mmsg");
  if ($("#mscope") && snap.scope) $("#mscope").value = snap.scope;
  const mode = snap.selection_mode || "latest";
  if ($("#mfollow")) $("#mfollow").hidden = mode === "latest";
  if ($("#mviewstate"))
    $("#mviewstate").textContent =
      mode === "whole"
        ? "Viewing the whole retained session."
        : mode === "encounter"
          ? snap.viewing_historical
            ? "Viewing an earlier encounter; capture continues into newer combat."
            : "This encounter is pinned; select Follow latest combat to follow the next pull."
          : "Following latest combat. Overlay always follows the latest encounter.";
  const d = s.diagnostics || {};
  if ($("#mdriverstats") && d.pipeline) {
    const stages = {
      capture_error: "Capture reported an error",
      waiting_for_tcp: "No TCP packets observed",
      waiting_for_payloads: "TCP packets observed; waiting for payload data",
      waiting_for_game_flow: "Payloads observed; automatic game-flow detection is waiting",
      waiting_for_reassembly: "Payloads observed; waiting for reassembled game data",
      waiting_for_combat_effects: "Game data forwarded; no combat effects decoded yet",
      no_players_in_selected_view: "Combat effects decoded; no players in the selected scope / encounter / enemy view",
      combat_visible: "Decoded combat is visible in the selected view",
    };
    $("#mdriverstats").textContent +=
      ` Capture stage: ${stages[d.pipeline.stage] || d.pipeline.stage}. Payload packets ${d.payload_packets || 0}; forwarded chunks ${d.forwarded || 0}; decoded effects ${d.decoded_events || 0}; visible players ${d.pipeline.visible_players || 0}. This summarizes retained counters, not proof of current activity. Raw payload recording is optional.`;
  }
  if ($("#mdriverstats"))
    $("#mdriverstats").textContent +=
      ` Last forwarded game data: ${d.last_packet_age_seconds == null ? "not observed" : d.last_packet_age_seconds.toFixed(1) + "s ago"}. Last decoded effect: ${d.last_combat_age_seconds == null ? "not observed" : d.last_combat_age_seconds.toFixed(1) + "s ago"}. Idle time alone does not establish a capture failure.`;
  if ($("#mdriverstats") && d.capture_processing) {
    const p = d.capture_processing,
      n = (k) => (p[k] == null ? "not recorded" : n0(p[k]));
    $("#mdriverstats").textContent +=
      ` Session processing: ${n("decoder_errors")} decoder failures; ${n("shutdown_discarded_payloads")} shutdown payload discards; ${n("shutdown_drained_payloads")} payloads retained during shutdown. Legacy error/discard count ${n("capture_errors")} overlaps these counters.`;
  }
  const selector = $("#msegments");
  if (selector && snap.segments && document.activeElement !== selector) {
    const options =
      `<option value="">Latest combat</option><option value="all">Whole session</option>` +
      snap.segments
        .map(
          (segment) =>
            `<option value="${esc(segment.id)}">${esc(segment.label)} · ${clockAt(segment.start)} · ${segment.duration.toFixed(1)}s</option>`,
        )
        .join("");
    if (selector.innerHTML !== options) selector.innerHTML = options;
    selector.value = st.pinnedSegment || (snap.selected_segment === "all" ? "all" : "");
  }
  if (msg) {
    if (s.error) msg.textContent = s.error;
    else {
      const d = s.diagnostics || {};
      msg.textContent = s.finalizing
        ? "Saving stopped capture and diagnostics…"
        : s.running && d.state === "stopping"
          ? "Stopping capture · decoding queued payloads before saving…"
          : s.running
            ? `${s.snapshot?.paused ? "Paused DPS · capture continues" : "Recording"} · ${d.packets || 0} TCP packets · ${d.decoded_events || 0} combat events${d.tcp_stream_resets ? " · " + d.tcp_stream_resets + " lossy TCP recovery boundaries (capture incomplete)" : ""}${d.port ? " · port " + d.port : d.auto_port ? " · detecting game port" : ""}${d.pcap_dropped || d.pcap_if_dropped ? " · Capture drops detected; data may be incomplete (see diagnostics)" : ""}`
            : "Stopped";
    }
  }
  const view = $("#mview");
  if (!view) return;
  if (!snap.players.length) {
    st.lastMeterRender = null;
    view.innerHTML = win(
      "Meter",
      "",
      `<div class="empty">${s.diagnostics?.decoded_events ? "Combat effects were decoded; waiting for a matching player identity or party roster in this view." : s.running ? (s.diagnostics?.packets || 0 ? (s.diagnostics?.forwarded ? "The game stream is reaching the decoder but no combat events have been recognized. Enable TCP recording before Start and export capture diagnostics after fighting briefly." : "Packets are arriving. Waiting for a recognized game stream — enter combat. Enable TCP recording before Start to investigate.") : "No packets yet. Check capture support, adapter permissions and your interface selection, then enter combat.") : "No data yet — choose a source and press Start."}${snap.warning ? "<p>" + esc(snap.warning) + "</p>" : ""}${s.diagnostics?.warnings?.length ? "<p>" + esc(s.diagnostics.warnings.join("; ")) + "</p>" : ""}</div>`,
    );
    return;
  }
  const mx = Math.max(...snap.players.map((p) => p.dps), 1);
  const selected = snap.players.findIndex((player) => (player.key || player.id) === st.selectedPlayerKey);
  st.sel = selected >= 0 ? selected : 0;
  st.selectedPlayerKey = snap.players[st.sel].key || snap.players[st.sel].id;
  const signature = JSON.stringify([snap, st.selectedPlayerKey, _ptab]);
  if (st.lastMeterRender === signature) return;
  st.lastMeterRender = signature;
  const rows = snap.players
    .map(
      (p, i) => `<div class="pm ${i === st.sel ? "on" : ""}" data-sel="${i}">
      <div class="nmc"><b>${esc(p.name)}</b>${p.server_name ? ` <span class="muted small">· ${esc(p.server_name)}</span>` : ""} <span class="muted small">${esc(cap(p.class || ""))}</span></div>
      <div class="bar"><i style="width:${(100 * p.dps) / mx}%"></i><span>${kfmt(p.dps)}/s · ${pct(p.share, 0)}</span></div></div>`,
    )
    .join("");
  const enemyTable = snap.enemies?.length
    ? win(
        "Enemies",
        "select an enemy to show each player's damage against it",
        `<table class="t"><tr><th>Enemy</th><th>Party damage dealt</th><th>Party DPS</th></tr>${snap.enemies.map((enemy) => `<tr class="${enemy.key === snap.selected_enemy ? "sel" : ""}"><td><button class="btn small" data-enemy="${esc(enemy.key)}">${esc(enemy.name)}</button></td><td>${kfmt(enemy.damage)}</td><td>${kfmt(enemy.dps)}</td></tr>`).join("")}</table>`,
      )
    : "";
  replaceMeterHtml(
    view,
    (snap.warning ? `<p class="note">${esc(snap.warning)}</p>` : "") +
      enemyTable +
      win(
        "Players",
        `${esc(snap.boss || "")}${snap.boss ? " · " : ""}${(snap.duration || 0).toFixed(0)}s · ${kfmt(snap.dps || 0)} raid DPS`,
        `<div class="pmeters">${rows}</div>${snap.ping ? `<p class="small muted">Ping ${kfmt(snap.ping.current)} ms now · ${kfmt(snap.ping.avg)} ms capture avg · ${kfmt(snap.ping.min)}–${kfmt(snap.ping.max)} ms range (${snap.ping.samples} samples across this recording connection, logged over time)</p>` : ""}${odyleLine(snap.odyle)}${shugoLine(snap.shugo_keys)}${nightmareLine(snap.nightmare_tickets)}`,
      ) +
      `<div id="pbd">${renderParse(parseFromMeter(snap, st.sel))}</div>`,
  );
  $$("[data-enemy]").forEach(
    (el) =>
      (el.onclick = async () => {
        try {
          renderMeter(await api("/api/meter", { action: "view", enemy: el.dataset.enemy }));
        } catch (e) {
          $("#mnotice").textContent = e.message;
        }
      }),
  );
  $$("[data-sel]").forEach(
    (el) =>
      (el.onclick = () => {
        st.sel = +el.dataset.sel;
        st.selectedPlayerKey = snap.players[st.sel].key || snap.players[st.sel].id;
        replaceMeterHtml($("#pbd"), renderParse(parseFromMeter(snap, st.sel)));
        $$("[data-sel]").forEach((x) => x.classList.toggle("on", +x.dataset.sel === st.sel));
      }),
  );
}
