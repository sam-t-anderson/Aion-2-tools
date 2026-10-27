/* Combat Logs (#/combat) and one combat log (#/combat-log/...): the community's logs, saved logs, AbyssLogs
   imports and a fight's review. */
"use strict";

function parseFromEncounter(a) {
  const s = a.summary,
    m = a.meta,
    tot = s.total || 1,
    nameToId = {};
  (a.skills || []).forEach((k) => {
    if (k.skill_id) nameToId[k.skill] = k.skill_id;
  });
  return {
    name: m.player,
    cls: m.class || m.class_name,
    gs: null,
    cp: m.combat_power || null,
    dmg: s.total,
    dps: s.dps,
    contrib: null,
    duration: s.duration,
    boss: m.target,
    highest: s.biggest_hit ? s.biggest_hit.damage : null,
    rates: {
      crit: s.crit,
      double: s.double,
      perfect: s.perfect,
      multi: s.multi,
      back: s.back ?? null,
      front: s.front ?? null,
    },
    skills: (a.skills || []).map((k) => {
      const dmg = (k.share || 0) * tot;
      return {
        skill: k.skill,
        skill_id: k.skill_id,
        hits: k.hits,
        dps: dmg / (s.duration || 1),
        avg: k.avg_hit,
        min: null,
        max: k.max_hit,
        damage: dmg,
        share: k.share,
      };
    }),
    rotation: (a.rotation || []).map(([t, k]) => ({ t, skill: k, skill_id: nameToId[k] })),
    timeline: a.timeline,
    live: false,
  };
}
async function pageCombatLog() {
  const routeHash = location.hash,
    routeParts = routeHash.split("?"),
    parts = routeParts[0].split("/"),
    kind = parts[2],
    value = decodeURIComponent(parts.slice(3).join("/")),
    mode = new URLSearchParams(routeParts[1] || "").get("mode");
  if (S.combat.review) {
    S.combat.review.dispose();
    S.combat.review = null;
  }
  app().innerHTML =
    '<p><a class="btn small" href="#/combat">← Back to combat logs</a></p><div id="focused-log">Loading combat log…</div>';
  const target = $("#focused-log");
  let doc,
    options = { ...localReviewOptions(), mode };
  if (kind === "analysis") {
    const analysis = await api("/api/encounters/" + encodeURIComponent(value));
    if (location.hash !== routeHash || !target.isConnected) return;
    target.innerHTML = renderEncounter(analysis);
    target.querySelectorAll("[data-share]").forEach(
      (button) =>
        (button.onclick = async () => {
          button.disabled = true;
          try {
            const result = await api("/api/encounters/" + analysis.id + "/share", {});
            const link = document.createElement("a");
            link.href = result.url;
            link.textContent = "Open shared log";
            link.target = "_blank";
            link.rel = "noopener";
            target.querySelector("#shared").replaceChildren(link);
            if (result.ownership_warning) toast(result.ownership_warning);
          } catch (e) {
            target.querySelector("#shared").textContent = e.message;
          } finally {
            button.disabled = false;
          }
        }),
    );
    target.querySelectorAll("[data-player]").forEach(
      (button) =>
        (button.onclick = async () => {
          try {
            button.disabled = true;
            const next = await runJob(
              "/api/encounters/import",
              { ref: analysis.meta.url, player: button.dataset.player },
              (lines) => toast(lines.at(-1) || "Analyzing…"),
            );
            location.hash = "/combat-log/analysis/" + next.id;
          } catch (e) {
            toast(e.message);
            button.disabled = false;
          }
        }),
    );
    window.scrollTo(0, 0);
    return;
  }
  if (kind === "local") {
    doc = await api("/api/sessions?file=" + encodeURIComponent(value));
    options = { ...localReviewOptions(value), mode };
  } else if (kind === "shared") {
    doc = await communityAPI("/api/v1/logs/" + encodeURIComponent(value) + "/raw");
    options = {
      ...options,
      reconstructArchive: (first, last) =>
        communityAPI("/api/v1/logs/" + encodeURIComponent(value) + "/reconstruction?first=" + first + "&last=" + last),
      archiveCurrent: value,
      archiveParts: (offset, limit) =>
        communityAPI("/api/v1/logs/" + encodeURIComponent(value) + "/parts?offset=" + offset + "&limit=" + limit),
      openArchivePart: (row, mode) => {
        location.hash = "/combat-log/shared/" + encodeURIComponent(row.id) + "?mode=" + encodeURIComponent(mode || "");
      },
      report: (body) => communityAPI("/api/v1/logs/" + encodeURIComponent(value) + "/reports", body),
      rankings: (segment) => communityAPI("/api/v1/logs/" + encodeURIComponent(value) + "/rankings?segment=" + segment),
    };
  } else if (kind === "opened" && S.combat.openedLog) doc = S.combat.openedLog;
  else {
    target.textContent = "This temporary preview is no longer available. Return to combat logs to open it again.";
    return;
  }
  if (location.hash !== routeHash || !target.isConnected) return;
  const initialSegment = new URLSearchParams(routeParts[1] || "").get("segment");
  if (/^\d{1,6}$/.test(initialSegment || "") && Number(initialSegment) < doc.segments.length)
    options.state = { segment: Number(initialSegment) };
  S.combat.review = A2CombatReview.mount(target, doc, options);
  window.scrollTo(0, 0);
}
async function pageCombat() {
  const st = S.combat;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Combat logs</h2><span class="sub">per-skill breakdown, timeline, rates, idle time — compared with your optimal rotation</span></div>
    <div class="wb"><div id="logs-view"><div class="row" role="tablist" id="logs-tabs" aria-label="Combat log views" style="flex-wrap:wrap;gap:6px"><button class="btn small" role="tab" type="button" data-tab="community" aria-selected="true">Browse logs</button><button class="btn small" role="tab" type="button" data-tab="speed" aria-selected="false">Completed-run speed</button><button class="btn small" role="tab" type="button" data-tab="progression" aria-selected="false">Boss progression</button><button class="btn small" role="tab" type="button" data-tab="points" aria-selected="false">Highest observed build points</button><button class="btn small" role="tab" type="button" data-tab="extras" aria-selected="false">Personal records</button></div>
    <div data-logs-panel="community" style="margin-top:12px"><div id="combat-log-tabs"><div class="row" role="tablist" aria-label="Combat log sources"><button class="btn small" role="tab" id="log-tab-community" data-log-tab="community" aria-controls="log-panel-community">Community Combat Logs</button><button class="btn small" role="tab" id="log-tab-owned" data-log-tab="owned" aria-controls="log-panel-owned">My Uploads</button><button class="btn small" role="tab" id="log-tab-saved" data-log-tab="saved" aria-controls="log-panel-saved">Saved Logs</button></div><div id="log-panel-saved" data-log-panel="saved" role="tabpanel" aria-labelledby="log-tab-saved"><div class="row"><input id="ref" type="text" placeholder="AbyssLogs link (abysslogs.com/e/…) or A2DIL link" style="width:458px">
      <input id="player" type="text" placeholder="player (party logs)" style="width:172px"><button class="btn primary" id="imp">Analyze</button>
      <span class="muted small">or</span><input id="file" type="file" accept=".json,.gz,.csv"><span id="lmsg" class="small muted"></span></div>
      <p class="small faint">Record a fight with the free <a href="https://abysslogs.com" target="_blank" rel="noopener">AbyssLogs meter</a>, press Share, and paste the link here. A party log shows the recorder's damage unless you name a player.
        Files: AbyssLogs segment (.json / .json.gz), aion2calc JSON (see docs), or CSV with columns t, skill, damage, crit, double, perfect, multi, dot.</p>
      <div class="row small" id="logsdir"></div>
      <div class="row small" id="lsrv"></div>
      <h3>Recorded encounters by type</h3><div id="saved-browse"></div>
      <h3>Upload recordings</h3><div id="sessions"></div><div id="session-review"></div><h3>Analyzed encounters</h3><div id="hist"></div></div><div id="log-panel-owned" data-log-panel="owned" role="tabpanel" aria-labelledby="log-tab-owned" hidden><div id="owned-logs"></div><div id="my-characters"></div></div><div id="log-panel-community" data-log-panel="community" role="tabpanel" aria-labelledby="log-tab-community" hidden><div id="community"></div></div></div></div>
    <div data-logs-panel="speed" hidden><div id="speed-body" style="margin-top:12px"><div class="empty">Loading…</div></div></div>
    <div data-logs-panel="progression" hidden><div id="progression-body" style="margin-top:12px"><div class="empty">Loading…</div></div></div>
    <div data-logs-panel="points" hidden><div id="points-body" style="margin-top:12px"><div class="empty">Loading…</div></div></div>
    <div data-logs-panel="extras" hidden><div id="records-extra" style="margin-top:12px"></div></div>
    </div></div></section><div id="enc"></div>`;
  A2LogTabs.mount($("#combat-log-tabs"), st.listTab || "community", (value) => {
    st.listTab = value;
  });
  // Saved Logs, grouped by encounter type (PvP / world / field boss / raid / nightmare / … ) so it
  // reads like the website's Community Combat Logs. Opens each encounter at its own segment.
  A2SavedLogs.mount($("#saved-browse"), {
    api,
    open: (file, segment) => {
      location.hash =
        "/combat-log/local/" + encodeURIComponent(file) + (Number.isInteger(segment) ? "?segment=" + segment : "");
    },
  });
  api("/api/logs")
    .then((l) => {
      if (!$("#logsdir")) return;
      $("#logsdir").innerHTML =
        `<span class="muted">Every analyzed log is saved as a file in</span> <code>${esc(l.folder)}</code> <span class="faint">(${l.files} files)</span>
      <button class="btn small" id="openlogs">Open folder</button>`;
      $("#openlogs").onclick = () => api("/api/logs/open", {}).catch((e) => ($("#lmsg").textContent = e.message));
    })
    .catch(() => {});
  const srv = async () => {
    const c = await api("/api/logserver").catch(() => ({}));
    if (!$("#lsrv")) return;
    $("#lsrv").innerHTML =
      `<span class="muted">Share to a log server:</span><input id="lsurl" type="text" placeholder="https://logs.example.com" value="${esc(c.url || "")}" style="width:275px">
      <input id="lskey" type="password" placeholder="${c.has_key ? "key saved" : "upload key"}" style="width:183px">
      <select id="lsvis" aria-label="Who can see your uploads">${["public", "unlisted", "legion", "private"].map((v) => `<option value="${v}" ${v === (c.visibility || "public") ? "selected" : ""}>${v === "legion" ? "legion only" : v}</option>`).join("")}</select>
      <button class="btn small" id="lssave">Save</button>`;
    $("#lssave").onclick = async () => {
      await api("/api/logserver", {
        url: $("#lsurl").value,
        key: $("#lskey").value || null,
        visibility: $("#lsvis").value,
      });
      toast("Saved");
      srv();
    };
  };
  srv();
  A2ArchiveUpload.mount($("#sessions"), {
    types: A2Community.types,
    list: (offset, limit, archive) =>
      api(
        "/api/sessions?paged=1&offset=" + offset + "&limit=" + limit + "&archive=" + encodeURIComponent(archive || ""),
      ),
    context: () => api("/api/logserver"),
    loadCheckpoint: () => api("/api/upload-queue"),
    saveCheckpoint: (value) => api("/api/upload-queue", value),
    fingerprint: async (row) => (await api("/api/sessions?fingerprint=" + encodeURIComponent(row.file))).fingerprint,
    open: (row) => {
      location.hash = "/combat-log/local/" + encodeURIComponent(row.file);
    },
    upload: (row, batch) =>
      api("/api/sessions/share", {
        file: row.file,
        visibility: batch.visibility,
        server: batch.url,
        completed_only: true,
        fingerprint: row.fingerprint,
        request_id: row.request_id,
      }),
  });
  A2LogOwnership.mount($("#owned-logs"), {
    list: () => api("/api/log-ownership"),
    import: (owners) => api("/api/log-ownership", { action: "import", owners }),
    forget: (owner) => api("/api/log-ownership", { action: "forget", owner }),
    request: (owner, action, value) =>
      api(
        "/api/log-ownership",
        action === "appeal" ? { owner, action, statement: value } : { owner, action, visibility: value },
      ),
    open: (doc) => {
      S.combat.openedLog = doc;
      location.hash = "/combat-log/opened/" + Date.now();
    },
  });
  // Community identity: the characters this computer's recordings can claim (credentials and the
  // issued identity credentials stay in the app's data folder, never in the browser).
  A2Identity.mount($("#my-characters"), {
    credentials: () => api("/api/log-ownership"),
    server: async () => String((await api("/api/logserver")).url || "").replace(/\/+$/, ""),
    claims: () => api("/api/identity-claims"),
    save: (rows) => api("/api/identity-claims", { action: "replace", claims: rows }),
  });
  const openShared = (id, mode, segment) => {
    location.hash =
      "/combat-log/shared/" +
      encodeURIComponent(id) +
      "?mode=" +
      encodeURIComponent(mode || "") +
      (Number.isInteger(segment) ? "&segment=" + segment : "");
  };
  // Website-style outer tabs (community combat logs / speed / boss progression / build points)
  // plus an app-only "Personal records" tab carrying the extras the website's logs page omits
  // (boss defeats, class performance, personal records, consistency) via a sectioned A2Community.
  A2LogsView.mount($("#logs-view"), {
    api: communityAPI,
    open: openShared,
    initial: st.logsTab || "community",
    onTab: (value) => {
      st.logsTab = value;
    },
    extras: () =>
      A2Community.mount($("#records-extra"), {
        api: communityAPI,
        open: openShared,
        sections: ["bosses", "performance", "records"],
      }),
  });
  const hist = await api("/api/encounters").catch(() => []);
  if (!$("#hist")) return;
  $("#hist").innerHTML = hist.length
    ? `<table class="t"><tr><th>#</th><th>Player</th><th>Class</th><th>Target</th><th>Source</th><th class="r">Duration</th><th class="r">DPS</th><th><span class="sr-only">Actions</span></th></tr>${hist
        .map(
          (e) =>
            `<tr><td>${e.id}</td><td>${esc(e.player || "")}</td><td>${esc(cap(e.class_name))}</td><td>${esc(e.boss || "")}</td><td>${esc(e.source)}</td><td class="r">${(e.duration || 0).toFixed(0)}s</td><td class="r num">${n0(e.dps)}</td>
     <td class="r"><button class="btn small" data-enc="${e.id}">Open</button></td></tr>`,
        )
        .join("")}</table>`
    : '<div class="faint small">No encounters yet.</div>';
  $$("[data-enc]").forEach((b) => (b.onclick = () => openEnc(+b.dataset.enc)));
  const progress = (l) => ($("#lmsg").textContent = l[l.length - 1] || "");
  const show = (a) => {
    st.a = a;
    location.hash = "/combat-log/analysis/" + a.id;
  };
  const openEnc = (id) => {
    location.hash = "/combat-log/analysis/" + id;
  };
  $("#imp").onclick = async () => {
    try {
      show(await runJob("/api/encounters/import", { ref: $("#ref").value, player: $("#player").value }, progress));
    } catch (e) {
      $("#lmsg").textContent = e.message;
    }
  };
  $("#file").onchange = async () => {
    const f = $("#file").files[0];
    if (!f) return;
    try {
      const gz = new Uint8Array(await f.slice(0, 2).arrayBuffer());
      const text =
        gz[0] === 0x1f && gz[1] === 0x8b // AbyssLogs segment files are gzip
          ? await new Response(f.stream().pipeThrough(new DecompressionStream("gzip"))).text()
          : await f.text();
      show(await runJob("/api/encounters/import", { text, name: f.name, player: $("#player").value }, progress));
    } catch (e) {
      $("#lmsg").textContent = e.message;
    }
  };
}

function renderEncounter(a) {
  const s = a.summary,
    m = a.meta;
  const extra = [
    ["Casts / min", s.cpm.toFixed(0)],
    ["Multi-hit", pct(s.multi)],
    ["Idle", s.idle_seconds.toFixed(1) + " s"],
  ];
  const buffs = a.buffs
    .map(
      (b) =>
        `<tr><td>${esc(b.name)}</td><td style="width:60%"><div class="bar"><i class="alt" style="width:${100 * (b.uptime || 0)}%"></i><span>${pct(b.uptime, 0)}</span></div></td></tr>`,
    )
    .join("");
  const o = a.vs_optimal || {};
  const opt = o.error
    ? `<div class="note">${esc(o.error)}</div>`
    : `${o.note ? `<div class="note">${esc(o.note)}</div>` : ""}
    <p>Share overlap with the optimal rotation: <b class="gold">${pct(o.share_overlap, 0)}</b>${o.comparable_dps ? ` · optimal DPS ${n0(o.sim_dps)} vs yours ${n0(o.actual_dps)}` : ""}</p>
    ${(o.tips || []).map((t) => `<div class="tip">${esc(t)}</div>`).join("")}
    <table class="t"><tr><th>Skill</th><th>Your share</th><th>Optimal share</th><th class="r">Your casts</th><th class="r">Optimal casts</th></tr>${(
      o.skills || []
    )
      .slice(0, 16)
      .map(
        (r) =>
          `<tr><td>${esc(r.skill)}</td><td style="width:22%"><div class="bar"><i style="width:${100 * r.share}%"></i><span>${pct(r.share)}</span></div></td>
       <td style="width:22%"><div class="bar"><i class="alt" style="width:${100 * r.sim_share}%"></i><span>${pct(r.sim_share)}</span></div></td><td class="r">${r.casts}</td><td class="r">${r.sim_casts}</td></tr>`,
      )
      .join("")}</table>`;
  const specs = (o.specs || []).length
    ? `<h4 class="gold small" style="margin-top:14px">SPECIALIZATIONS (from the log)</h4>
    <table class="t"><tr><th>Skill</th><th>In this log</th><th>Optimized build</th></tr>${o.specs
      .map(
        (d) =>
          `<tr><td>${esc(d.skill)}</td><td class="${d.differs ? "bad" : ""}">${esc(d.yours || "none")}</td><td class="gold">${esc(d.optimal)}</td></tr>`,
      )
      .join("")}</table>`
    : "";
  const t = a.vs_top || {};
  const top = t.rows
    ? `<p>Share overlap with the top Korean logs for this class: <b class="gold">${pct(t.overlap, 0)}</b></p><table class="t"><tr><th>Skill</th><th>You</th><th>Top logs</th><th class="r">Hits/min</th><th class="r">Top hits/min</th></tr>${t.rows
        .map(
          (r) =>
            `<tr><td>${esc(r.skill)}</td><td>${pct(r.share)}</td><td>${pct(r.top_share)}</td><td class="r">${r.hpm.toFixed(0)}</td><td class="r">${r.top_hpm.toFixed(0)}</td></tr>`,
        )
        .join("")}</table>`
    : "";
  const party =
    (m.party || []).length > 1
      ? `<div class="row small" style="margin-top:10px"><span class="muted">Party:</span>${m.party
          .map(
            (p) =>
              `<button class="btn small ${p.name === m.player ? "primary" : ""}" data-player="${esc(p.name)}" title="${esc(p.class)} · ${n0(p.damage)} damage">${esc(p.name)} <span class="faint">${esc(p.class || "")}</span></button>`,
          )
          .join("")}</div>`
      : "";
  const shareRow = a.id
    ? `<div class="row small" style="margin-top:8px"><button class="btn small primary" data-share="1">Share link</button><span id="shared" class="muted"></span></div>`
    : "";
  const info =
    shareRow +
    `<div class="small muted" style="margin-top:8px">${(m.notes || []).map(esc).join(" · ")}${m.url ? ` · <a href="${esc(m.url)}" target="_blank" rel="noopener">open on AbyssLogs</a>` : ""}${a.file ? ` · saved as <code>${esc(a.file)}</code>` : ""}</div>`;
  const chips = `<div class="row small" style="margin-top:8px">${extra.map(([k, v]) => `<span class="muted">${k}: <b>${v}</b></span>`).join("")}</div>`;
  return (
    win(
      "Encounter",
      `${esc(m.player || "")} · ${esc(cap(m.class || m.class_name || ""))} · ${esc(m.target || "")} · ${esc(m.source)}${m.combat_power ? " · CP " + n0(m.combat_power) : ""}`,
      `${party}${info}${renderParse(parseFromEncounter(a))}${chips}`,
    ) +
    win(
      "Buff uptime",
      "",
      `<table class="t">${buffs}</table>` +
        (a.gaps.length
          ? `<p class="small muted">Idle gaps: ${a.gaps.map((g) => `${g.start.toFixed(1)}–${g.end.toFixed(1)}s`).join(", ")}</p>`
          : ""),
    ) +
    win("Compared with your optimal rotation", "same fight length, simulated", opt + specs) +
    (top ? win("Compared with top players", "A2DIL top-10 dummy logs", top) : "")
  );
}
