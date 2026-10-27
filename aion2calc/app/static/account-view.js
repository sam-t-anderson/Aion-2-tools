/* The optional account, for the desktop app and the website: My logs, Legions, and Sign-in & security.
   The page hands in `io`: how to reach the server (the app asks its own local server, which keeps the
   credential; the website sends its session), what to show when signed out, and what only it can do.
   Everything the server says is escaped before it is shown. */
(function () {
  "use strict";
  const esc = (x) =>
    String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const tr = (text, ...values) => (window.A2I18n ? window.A2I18n.t(text, ...values) : text.replace(/\{(\d)\}/g, (m, i) => values[i] ?? ""));
  const pad = (n) => String(n).padStart(2, "0");
  const many = (n, one, other) => tr(Number(n) === 1 ? one : other, n);
  const when = (t) => {
    if (!t) return "—";
    const d = new Date(t * 1000);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };
  const length = (s) => {
    s = Math.max(0, Math.round(+s || 0));
    return s >= 3600 ? `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}` : `${Math.floor(s / 60)}:${pad(s % 60)}`;
  };
  const world = (s) => (window.A2Servers ? A2Servers.label(s, s) : s) || "—";
  const plain = (m) => String(m || "").replace(/^(ValueError|PermissionError|RuntimeError|LookupError|Error): /, "");
  const VIS = () => [["public", tr("Public")], ["unlisted", tr("Unlisted")], ["legion", tr("Legion only")], ["private", tr("Private")]];
  const ROLE = () => ({ leader: tr("Leader"), officer: tr("Officer"), member: tr("Member") });
  const INVITE = /a2inv_[A-Za-z0-9_-]{20,60}/;
  const ACTIVITY = () => ({
    created: tr("Account created"), signed_in: tr("Signed in"), signed_out: tr("Signed out"), renamed: tr("Renamed"),
    logs_attached: tr("Logs added"), visibility: tr("Visibility changed"), retitled: tr("Log renamed"),
    log_deleted: tr("Log deleted"), log_detached: tr("Log removed from the account"), character_added: tr("Character added"),
    discord_linked: tr("Discord linked"), discord_unlinked: tr("Discord unlinked"), passkey_added: tr("Passkey added"),
    passkey_removed: tr("Passkey removed"), signin_approved: tr("Website sign-in approved"),
    signin_denied: tr("Website sign-in denied"), link_code: tr("Link code made"), legion_created: tr("Legion founded"),
    legion_joined: tr("Legion joined"), recovered: tr("Recovered"), disabled: tr("Disabled by the operator"),
    active: tr("Enabled by the operator"),
  });
  const visLabel = (v) => (VIS().find(([k]) => k === v) || [v, v])[1];
  const box = (text, kind = "note") => `<div class="${kind}" role="status">${esc(text)}</div>`;

  // The menu in the header: "Sign in", or the account's name with what an account offers under it.
  function menu(el, io) {
    if (!el) return { refresh() {} };
    let open = false;
    async function refresh() {
      let s = null;
      try {
        s = await io.status();
      } catch (e) {}
      const name = s && s.signed_in && s.account ? s.account.name : null;
      if (!name) {
        el.innerHTML = `<a class="btn small acct-signin" href="${esc(io.href("signin"))}">${esc(tr("Sign in"))}</a>`;
        return;
      }
      el.innerHTML = `<div class="acct-menu"><button class="btn small" type="button" aria-haspopup="true" aria-expanded="${open}">${esc(name)} ▾</button>
        <div class="acct-drop" role="menu" ${open ? "" : "hidden"}>
          <a role="menuitem" href="${esc(io.href("logs"))}">${esc(tr("My logs"))}</a>
          <a role="menuitem" href="${esc(io.href("legions"))}">${esc(tr("Legions"))}</a>
          <a role="menuitem" href="${esc(io.href("security"))}">${esc(tr("Sign-in & security"))}</a>
          ${(io.menuItems || []).map(([id, label]) => `<button type="button" role="menuitem" data-acct-item="${esc(id)}">${esc(label)}</button>`).join("")}
          <button type="button" role="menuitem" data-acct-out>${esc(tr("Sign out"))}</button></div></div>`;
      const button = el.querySelector("button[aria-haspopup]"),
        drop = el.querySelector(".acct-drop");
      const show = (value) => {
        open = value;
        drop.hidden = !value;
        button.setAttribute("aria-expanded", String(value));
      };
      button.onclick = (ev) => {
        ev.stopPropagation();
        show(!open);
      };
      drop.onclick = () => show(false);
      el.querySelectorAll("[data-acct-item]").forEach((b) => (b.onclick = () => io.menuAction(b.dataset.acctItem)));
      el.querySelector("[data-acct-out]").onclick = async () => {
        if (!confirm(tr("Sign out of {0}?", name))) return;
        await io.signout().catch(() => {});
        refresh();
        if (io.onSignedOut) io.onSignedOut();
      };
    }
    document.addEventListener("click", () => {
      const drop = el.querySelector(".acct-drop");
      if (open && drop) {
        open = false;
        drop.hidden = true;
        el.querySelector("button[aria-haspopup]")?.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && open) el.querySelector("button[aria-haspopup]")?.click();
    });
    refresh();
    return { refresh };
  }

  function mount(root, io, opts = {}) {
    const st = { tab: opts.tab || "logs", page: 1, boss: "", legion: opts.legion || null, invite: opts.invite || null, me: null, flash: "" };
    const call = (method, path, body) => io.call(method, path, body);
    const flash = (text) => {
      st.flash = text;
    };

    async function render() {
      let s;
      try {
        s = await io.status();
      } catch (e) {
        root.innerHTML = box(plain(e.message));
        return;
      }
      if (!s.signed_in) {
        root.innerHTML = "";
        io.signedOut(root, s, render);
        return;
      }
      st.me = s.account || {};
      const tabs = [["logs", tr("My logs")], ["legions", tr("Legions")], ["security", tr("Sign-in & security")]];
      root.innerHTML = `<div class="acct-page"><div class="row acct-title"><h2 translate="no">${esc(st.me.name)}</h2>
          <span class="small muted">${esc(many(st.me.logs ?? 0, "{0} log", "{0} logs") + " · " + many((st.me.characters || []).length, "{0} character", "{0} characters"))}</span></div>
        <div class="tabs" role="tablist">${tabs.map(([id, label]) => `<button role="tab" data-acct-tab="${id}" class="${id === st.tab ? "on" : ""}" aria-selected="${id === st.tab}">${esc(label)}</button>`).join("")}</div>
        ${st.flash ? box(st.flash, "note acct-flash") : ""}<div data-acct-body>${esc(tr("Loading…"))}</div></div>`;
      st.flash = "";
      root.querySelectorAll("[data-acct-tab]").forEach(
        (b) =>
          (b.onclick = () => {
            st.tab = b.dataset.acctTab;
            st.legion = null;
            if (io.onTab) io.onTab(st.tab);
            render();
          }),
      );
      const body = root.querySelector("[data-acct-body]");
      try {
        await { logs: renderLogs, legions: renderLegions, security: renderSecurity }[st.tab](body);
      } catch (e) {
        if (e && e.signedOut) return render();
        body.innerHTML = box(plain(e.message));
      }
    }

    async function act(work, done) {
      try {
        const result = await work();
        if (done) flash(typeof done === "function" ? done(result) : done);
      } catch (e) {
        flash(plain(e.message));
      }
      render();
    }

    // ------------------------------------------------------------ my logs
    async function renderLogs(el) {
      const q = new URLSearchParams({ page: String(st.page), limit: "50" });
      if (st.boss) q.set("boss", st.boss);
      const r = await call("GET", "/api/v1/account/logs?" + q);
      const pages = Math.max(1, Math.ceil((r.total || 0) / (r.limit || 50)));
      el.innerHTML = `<div class="row"><input type="search" data-boss value="${esc(st.boss)}" placeholder="${esc(tr("Boss"))}" aria-label="${esc(tr("Filter your logs by boss"))}">
          <button class="btn small" data-filter>${esc(tr("Filter"))}</button>${io.logTools ? io.logTools() : ""}<span class="small muted">${esc(many(r.total || 0, "{0} log", "{0} logs"))}</span></div>
        ${r.logs.length ? `<table class="t acct-logs"><thead><tr><th>${esc(tr("Description"))}</th><th>${esc(tr("Character"))}</th><th>${esc(tr("Uploaded"))}</th><th class="r">${esc(tr("Duration"))}</th><th>${esc(tr("Visibility"))}</th><th>${esc(tr("Edit"))}</th><th>${esc(tr("Delete"))}</th></tr></thead><tbody>
        ${r.logs.map((l, i) => `<tr><td><a href="${esc(io.logHref(l))}"${io.logTarget || ""}>${esc(l.title || l.boss || l.id)}</a>${l.held ? ` <span class="chip">${esc(tr("under review"))}</span>` : ""}<div class="small muted" translate="no">${esc(l.boss || "")}</div></td>
          <td translate="no">${esc(l.uploader || "—")}</td><td>${when(l.created_at)}</td><td class="r">${length(l.duration)}</td>
          <td><select data-vis="${i}" aria-label="${esc(tr("Who can see {0}", l.title || l.id))}" ${l.held ? "disabled" : ""}>${VIS().map(([v, t]) => `<option value="${v}" ${v === l.visibility ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></td>
          <td><button class="btn small" data-title="${i}">${esc(tr("Edit"))}</button></td><td><button class="btn small" data-del="${i}">${esc(tr("Delete"))}</button></td></tr>`).join("")}</tbody></table>
        <div class="row">${st.page > 1 ? `<button class="btn small" data-page="${st.page - 1}">${esc(tr("Previous"))}</button>` : ""}<span class="small muted">${esc(tr("Page {0} of {1}", st.page, pages))}</span>${st.page < pages ? `<button class="btn small" data-page="${st.page + 1}">${esc(tr("Next"))}</button>` : ""}</div>`
        : `<p class="empty">${esc(st.boss ? tr("No logs match.") : tr("No logs yet. Uploads from your signed-in app join here, and the app adds the ones it uploaded before."))}</p>`}
        <p class="small muted">${esc(tr("Legion only: the members of your legions open it; it is listed nowhere else. Private: only its secret link opens it."))}</p>`;
      const box2 = el.querySelector("[data-boss]");
      el.querySelector("[data-filter]").onclick = () => {
        st.boss = box2.value.trim();
        st.page = 1;
        render();
      };
      box2.onkeydown = (ev) => ev.key === "Enter" && el.querySelector("[data-filter]").click();
      el.querySelectorAll("[data-page]").forEach((b) => (b.onclick = () => ((st.page = +b.dataset.page), render())));
      el.querySelectorAll("[data-vis]").forEach(
        (s) =>
          (s.onchange = () => {
            const l = r.logs[+s.dataset.vis];
            act(() => call("POST", `/api/v1/account/logs/${l.id}/visibility`, { visibility: s.value }), tr("{0} is now {1}", l.title || l.id, visLabel(s.value)));
          }),
      );
      el.querySelectorAll("[data-title]").forEach(
        (b) =>
          (b.onclick = () => {
            const l = r.logs[+b.dataset.title],
              title = prompt(tr("A new description for this log (1-80 characters)"), l.title || "");
            if (title && title.trim()) act(() => call("POST", `/api/v1/account/logs/${l.id}/title`, { title: title.trim() }), tr("Description saved"));
          }),
      );
      el.querySelectorAll("[data-del]").forEach(
        (b) =>
          (b.onclick = () => {
            const l = r.logs[+b.dataset.del];
            if (confirm(tr("Delete {0} from the server for everyone? This cannot be undone.", l.title || l.id)))
              act(() => call("POST", `/api/v1/account/logs/${l.id}/delete`, {}), tr("Log deleted"));
          }),
      );
      if (io.afterLogs) io.afterLogs(el, render);
    }

    // ------------------------------------------------------------ legions
    const characters = () => (st.me.characters || []).filter((c) => c.status === "active");
    const characterOptions = (server) => {
      const list = characters().filter((c) => !server || c.server === server);
      return list.length
        ? list.map((c) => `<option value="${esc(c.id)}">${esc(c.name)} (${esc(world(c.server))})</option>`).join("")
        : `<option value="">${esc(server ? tr("No claimed character on {0}", world(server)) : tr("No claimed character yet"))}</option>`;
    };
    // Where characters are claimed: Combat Logs → My Character Identities (io.claimHref), named and linked here.
    const noCharacter = () =>
      characters().length
        ? ""
        : `<div class="note" role="status">${esc(tr(io.claimHint || "A legion needs one of your claimed characters. Claim yours on Combat Logs → My Character Identities, and it joins your account."))}${io.claimHref ? ` <a href="${esc(io.claimHref)}">${esc(tr("Open My Character Identities"))}</a>` : ""}</div>`;

    async function renderLegions(el) {
      if (st.legion) return renderLegion(el, st.legion);
      const mine = (await call("GET", "/api/v1/legions/mine")).legions || [];
      const servers = [...new Set(characters().map((c) => c.server))];
      el.innerHTML = `${noCharacter()}
        <h3>${esc(tr("Your legions"))}</h3>
        ${mine.length ? `<table class="t"><thead><tr><th>${esc(tr("Legion"))}</th><th>${esc(tr("Server"))}</th><th>${esc(tr("As"))}</th><th>${esc(tr("Your role"))}</th><th class="r">${esc(tr("Members"))}</th></tr></thead><tbody>
          ${mine.map((l) => `<tr><td><a href="#" data-open="${esc(l.id)}" translate="no">${esc(l.name)}</a>${l.faction ? ` <span class="small muted">${esc(tr(l.faction))}</span>` : ""}</td><td translate="no">${esc(world(l.server))}</td><td translate="no">${esc(l.character || "—")}</td><td>${esc(ROLE()[l.role] || l.role)}</td><td class="r">${l.members}</td></tr>`).join("")}</tbody></table>`
          : `<p class="empty">${esc(tr("You are in no legion yet."))}</p>`}
        <details class="note" ${st.invite ? "open" : ""}><summary><b>${esc(tr("Join with an invite link"))}</b></summary>
          <div class="row"><input data-invite size="48" value="${esc(st.invite || "")}" placeholder="${esc(tr("Paste the invite link"))}" aria-label="${esc(tr("Invite link"))}"><button class="btn small" data-preview>${esc(tr("Look"))}</button></div><div data-invite-out></div></details>
        <details class="note"><summary><b>${esc(tr("Find a legion"))}</b></summary>
          <div class="row"><select data-find-server aria-label="${esc(tr("Server"))}"><option value="">${esc(tr("Every server"))}</option>${servers.map((s) => `<option value="${esc(s)}">${esc(world(s))}</option>`).join("")}</select>
          <input data-find-name placeholder="${esc(tr("Legion name"))}" aria-label="${esc(tr("Legion name"))}"><button class="btn small" data-find>${esc(tr("Search"))}</button></div><div data-find-out></div></details>
        <details class="note"><summary><b>${esc(tr("Found a legion"))}</b></summary>
          <div class="row"><input data-new-name maxlength="24" placeholder="${esc(tr("Legion name, as in the game"))}" aria-label="${esc(tr("Legion name"))}">
          <select data-new-character aria-label="${esc(tr("Your character"))}">${characterOptions()}</select>
          <select data-new-faction aria-label="${esc(tr("Faction"))}"><option value="">${esc(tr("Faction"))}</option><option value="Elyos">${esc(tr("Elyos"))}</option><option value="Asmodian">${esc(tr("Asmodian"))}</option></select>
          <input data-new-desc maxlength="200" placeholder="${esc(tr("A line about it (optional)"))}" aria-label="${esc(tr("Description"))}"><button class="btn small primary" data-create>${esc(tr("Found"))}</button></div>
          <p class="small muted">${esc(tr("The legion is on your character's server, and you lead it. Its name must be free there."))}</p></details>
        <p class="small muted">${esc(tr("The game does not say who is in a legion, so each legion's leader decides: an invite link joins at once, and a request waits for the leader or an officer. Members see each other's public and legion-only logs."))}</p>`;
      el.querySelectorAll("[data-open]").forEach(
        (a) =>
          (a.onclick = (ev) => {
            ev.preventDefault();
            st.legion = a.dataset.open;
            if (io.onLegion) io.onLegion(st.legion);
            render();
          }),
      );
      const invite = el.querySelector("[data-invite]"),
        inviteOut = el.querySelector("[data-invite-out]");
      el.querySelector("[data-preview]").onclick = async () => {
        const token = (invite.value.match(INVITE) || [])[0];
        if (!token) return (inviteOut.innerHTML = box(tr("That is not an invite link.")));
        try {
          const p = await call("POST", "/api/v1/legions/invite/preview", { invite: token });
          inviteOut.innerHTML = `<p><b translate="no">${esc(p.legion.name)}</b> · <span translate="no">${esc(world(p.legion.server))}</span> · ${esc(many(p.legion.members, "{0} member", "{0} members"))}${p.legion.leader ? ` · ${esc(tr("led by {0}", p.legion.leader))}` : ""}</p>
            <div class="row"><select data-join-character aria-label="${esc(tr("Your character"))}">${characterOptions(p.legion.server)}</select><button class="btn small primary" data-join>${esc(tr("Join"))}</button></div>`;
          inviteOut.querySelector("[data-join]").onclick = () =>
            act(async () => {
              const joined = await call("POST", "/api/v1/legions/join", { invite: token, character: +inviteOut.querySelector("[data-join-character]").value });
              st.legion = joined.id;
              st.invite = null;
              if (io.onLegion) io.onLegion(st.legion);
            }, tr("Welcome to {0}", p.legion.name));
        } catch (e) {
          inviteOut.innerHTML = box(plain(e.message));
        }
      };
      if (st.invite) el.querySelector("[data-preview]").click();
      const findOut = el.querySelector("[data-find-out]");
      el.querySelector("[data-find]").onclick = async () => {
        const q = new URLSearchParams();
        const server = el.querySelector("[data-find-server]").value,
          name = el.querySelector("[data-find-name]").value.trim();
        if (server) q.set("server", server);
        if (name) q.set("q", name);
        try {
          const found = (await call("GET", "/api/v1/legions?" + q)).legions || [];
          findOut.innerHTML = found.length
            ? `<table class="t"><tbody>${found.map((l) => `<tr><td><a href="#" data-open-found="${esc(l.id)}" translate="no">${esc(l.name)}</a></td><td translate="no">${esc(world(l.server))}</td><td>${l.faction ? esc(tr(l.faction)) : ""}</td><td translate="no">${esc(l.leader ? tr("led by {0}", l.leader) : "")}</td><td class="r">${esc(many(l.members, "{0} member", "{0} members"))}</td></tr>`).join("")}</tbody></table>`
            : `<p class="empty">${esc(tr("No legion found."))}</p>`;
          findOut.querySelectorAll("[data-open-found]").forEach(
            (a) =>
              (a.onclick = (ev) => {
                ev.preventDefault();
                st.legion = a.dataset.openFound;
                render();
              }),
          );
        } catch (e) {
          findOut.innerHTML = box(plain(e.message));
        }
      };
      el.querySelector("[data-create]").onclick = () => {
        const body = {
          name: el.querySelector("[data-new-name]").value.trim(),
          character: +el.querySelector("[data-new-character]").value,
          faction: el.querySelector("[data-new-faction]").value,
          description: el.querySelector("[data-new-desc]").value.trim(),
        };
        act(async () => {
          const made = await call("POST", "/api/v1/legions", body);
          st.legion = made.id;
        }, tr("{0} is founded. Make an invite link for your members.", body.name));
      };
    }

    async function renderLegion(el, id) {
      const L = await call("GET", "/api/v1/legions/" + id);
      const back = `<p><button class="btn small" data-back>← ${esc(tr("Legions"))}</button></p>`;
      const head = `<h3 translate="no">${esc(L.name)}</h3><p class="small muted"><span translate="no">${esc(world(L.server))}</span>${L.faction ? " · " + esc(tr(L.faction)) : ""} · ${esc(many(L.members, "{0} member", "{0} members"))}${L.leader ? ` · ${esc(tr("led by {0}", L.leader))}` : ""}</p>${L.description ? `<p translate="no">${esc(L.description)}</p>` : ""}`;
      const lead = L.role === "leader",
        staff = lead || L.role === "officer";
      if (!L.role) {
        el.innerHTML = `${back}${head}${L.requested
          ? `<p>${esc(tr("Your request is waiting for the leader."))}</p><button class="btn small" data-withdraw>${esc(tr("Withdraw the request"))}</button>`
          : `<div class="row"><select data-ask-character aria-label="${esc(tr("Your character"))}">${characterOptions(L.server)}</select><input data-ask-message maxlength="200" placeholder="${esc(tr("A message for the leader (optional)"))}" aria-label="${esc(tr("Message"))}"><button class="btn small primary" data-ask>${esc(tr("Ask to join"))}</button></div>`}`;
        wireBack(el);
        const ask = el.querySelector("[data-ask]");
        if (ask)
          ask.onclick = () =>
            act(() => call("POST", `/api/v1/legions/${id}/request`, { character: +el.querySelector("[data-ask-character]").value, message: el.querySelector("[data-ask-message]").value }), tr("Request sent"));
        const withdraw = el.querySelector("[data-withdraw]");
        if (withdraw) withdraw.onclick = () => act(() => call("POST", `/api/v1/legions/${id}/request/withdraw`, {}), tr("Request withdrawn"));
        return;
      }
      const roster = (L.roster || [])
        .map((m) => {
          const tools = [];
          if (lead && !m.you) {
            if (m.role !== "officer") tools.push(`<button class="btn small" data-role="officer" data-member="${esc(m.member)}">${esc(tr("Make officer"))}</button>`);
            if (m.role === "officer") tools.push(`<button class="btn small" data-role="member" data-member="${esc(m.member)}">${esc(tr("Make member"))}</button>`);
            tools.push(`<button class="btn small" data-role="leader" data-member="${esc(m.member)}">${esc(tr("Hand over"))}</button>`);
          }
          if (staff && !m.you && m.role !== "leader" && (lead || m.role === "member"))
            tools.push(`<button class="btn small" data-remove="${esc(m.member)}" data-name="${esc(m.character || "")}">${esc(tr("Remove"))}</button>`);
          return `<tr><td translate="no">${esc(m.character || "—")}${m.you ? ` <span class="chip gold">${esc(tr("you"))}</span>` : ""}${m.claim !== "active" ? ` <span class="chip">${esc(tr("claim lapsed"))}</span>` : ""}</td><td>${esc(ROLE()[m.role] || m.role)}</td><td>${when(m.joined_at)}</td><td class="gacts">${tools.join(" ")}</td></tr>`;
        })
        .join("");
      const requests = staff && (L.requests || []).length
        ? `<h4>${esc(tr("Asking to join"))}</h4><table class="t"><tbody>${L.requests.map((r) => `<tr><td translate="no">${esc(r.character || "—")}</td><td translate="no">${esc(r.message || "")}</td><td>${when(r.created_at)}</td><td class="gacts"><button class="btn small primary" data-decide="${esc(r.id)}" data-approve="1">${esc(tr("Approve"))}</button> <button class="btn small" data-decide="${esc(r.id)}">${esc(tr("Decline"))}</button></td></tr>`).join("")}</tbody></table>`
        : "";
      const invites = staff
        ? `<h4>${esc(tr("Invite links"))}</h4>${(L.invites || []).length ? `<table class="t"><tbody>${L.invites.map((v) => `<tr><td>${esc(tr("made {0}", when(v.created_at)))}</td><td>${esc(tr("until {0}", when(v.expires_at)))}</td><td>${esc(tr("{0} of {1} used", v.uses, v.max_uses))}</td><td><button class="btn small" data-revoke="${esc(v.id)}">${esc(tr("Revoke"))}</button></td></tr>`).join("")}</tbody></table>` : ""}
          <div class="row"><label>${esc(tr("Lasts"))} <select data-days>${[1, 3, 7, 14, 30].map((d) => `<option value="${d}" ${d === 7 ? "selected" : ""}>${esc(many(d, "{0} day", "{0} days"))}</option>`).join("")}</select></label>
          <label>${esc(tr("Admits"))} <select data-uses>${[1, 5, 10, 25, 50, 100].map((u) => `<option value="${u}" ${u === 25 ? "selected" : ""}>${esc(many(u, "{0} player", "{0} players"))}</option>`).join("")}</select></label>
          <button class="btn small primary" data-invite-new>${esc(tr("New invite link"))}</button></div><div data-invite-link></div>`
        : "";
      el.innerHTML = `${back}${head}<h4>${esc(tr("Members"))}</h4><table class="t"><thead><tr><th>${esc(tr("Character"))}</th><th>${esc(tr("Role"))}</th><th>${esc(tr("Joined"))}</th><th></th></tr></thead><tbody>${roster}</tbody></table>
        ${requests}${invites}<h4>${esc(tr("The legion's logs"))}</h4><div data-legion-logs>${esc(tr("Loading…"))}</div>
        <div class="row" style="margin-top:12px"><button class="btn small" data-leave>${esc(tr("Leave the legion"))}</button>${lead ? `<button class="btn small" data-disband>${esc(tr("Disband"))}</button>` : ""}</div>`;
      wireBack(el);
      el.querySelectorAll("[data-role]").forEach(
        (b) =>
          (b.onclick = () => {
            if (b.dataset.role === "leader" && !confirm(tr("Hand the legion over? You stay an officer."))) return;
            act(() => call("POST", `/api/v1/legions/${id}/role`, { member: +b.dataset.member, role: b.dataset.role }), tr("Roles updated"));
          }),
      );
      el.querySelectorAll("[data-remove]").forEach(
        (b) =>
          (b.onclick = () => {
            if (confirm(tr("Remove {0} from the legion?", b.dataset.name)))
              act(() => call("POST", `/api/v1/legions/${id}/remove`, { member: +b.dataset.remove }), tr("Member removed"));
          }),
      );
      el.querySelectorAll("[data-decide]").forEach(
        (b) => (b.onclick = () => act(() => call("POST", `/api/v1/legions/${id}/requests/decide`, { id: b.dataset.decide, approve: !!b.dataset.approve }), b.dataset.approve ? tr("Approved") : tr("Declined"))),
      );
      el.querySelectorAll("[data-revoke]").forEach((b) => (b.onclick = () => act(() => call("POST", `/api/v1/legions/${id}/invites/revoke`, { id: b.dataset.revoke }), tr("Invite link revoked"))));
      const make = el.querySelector("[data-invite-new]");
      if (make)
        make.onclick = async () => {
          const out = el.querySelector("[data-invite-link]");
          try {
            const made = await call("POST", `/api/v1/legions/${id}/invites`, { days: +el.querySelector("[data-days]").value, uses: +el.querySelector("[data-uses]").value });
            const link = io.inviteLink(made.invite);
            out.innerHTML = `<div class="note"><p>${esc(tr("Share this link with your members. It is shown once."))}</p><div class="row"><input readonly size="60" value="${esc(link)}" aria-label="${esc(tr("Invite link"))}"><button class="btn small" data-copy-invite>${esc(tr("Copy"))}</button></div></div>`;
            out.querySelector("[data-copy-invite]").onclick = () => navigator.clipboard?.writeText(link);
          } catch (e) {
            out.innerHTML = box(plain(e.message));
          }
        };
      el.querySelector("[data-leave]").onclick = () => {
        if (confirm(tr("Leave {0}?", L.name)))
          act(async () => {
            await call("POST", `/api/v1/legions/${id}/leave`, {});
            st.legion = null;
          }, tr("You left {0}", L.name));
      };
      const disband = el.querySelector("[data-disband]");
      if (disband)
        disband.onclick = () => {
          const typed = prompt(tr("This ends {0} for every member. Type its name to disband it.", L.name));
          if (typed)
            act(async () => {
              await call("POST", `/api/v1/legions/${id}/disband`, { confirm: typed });
              st.legion = null;
            }, tr("{0} is disbanded", L.name));
        };
      const logs = el.querySelector("[data-legion-logs]");
      try {
        const r = await call("GET", `/api/v1/legions/${id}/logs?limit=50`);
        logs.innerHTML = r.logs.length
          ? `<table class="t"><thead><tr><th>${esc(tr("Description"))}</th><th>${esc(tr("Member"))}</th><th>${esc(tr("Uploaded"))}</th><th class="r">${esc(tr("Duration"))}</th><th>${esc(tr("Visibility"))}</th></tr></thead><tbody>${r.logs.map((l) => `<tr><td><a href="${esc(io.logHref(l))}"${io.logTarget || ""}>${esc(l.title || l.boss || l.id)}</a><div class="small muted" translate="no">${esc(l.boss || "")}</div></td><td translate="no">${esc(l.member || l.uploader || "—")}</td><td>${when(l.created_at)}</td><td class="r">${length(l.duration)}</td><td>${esc(visLabel(l.visibility))}</td></tr>`).join("")}</tbody></table>`
          : `<p class="empty">${esc(tr("No logs shared yet. Members share a log by making it public or legion only."))}</p>`;
      } catch (e) {
        logs.innerHTML = box(plain(e.message));
      }
    }
    function wireBack(el) {
      el.querySelector("[data-back]").onclick = () => {
        st.legion = null;
        if (io.onLegion) io.onLegion(null);
        render();
      };
    }

    // ------------------------------------------------------------ sign-in & security
    async function renderSecurity(el) {
      const [sessions, activity] = await Promise.all([call("GET", "/api/v1/account/sessions"), call("GET", "/api/v1/account/activity")]);
      const names = ACTIVITY();
      el.innerHTML = `<div class="row"><span>${esc(tr("Name"))}: <b translate="no">${esc(st.me.name)}</b></span><button class="btn small" data-rename>${esc(tr("Rename"))}</button></div>
        <div data-acct-extras></div>
        <h3>${esc(tr("Signed in"))}</h3><table class="t"><thead><tr><th>${esc(tr("Where"))}</th><th>${esc(tr("Since"))}</th><th>${esc(tr("Last used"))}</th><th></th></tr></thead><tbody>
        ${(sessions.sessions || []).map((s) => `<tr><td translate="no">${esc(s.label)} <span class="small muted">${esc(s.kind === "app" ? tr("desktop app") : tr("website"))}</span></td><td>${when(s.created_at)}</td><td>${when(s.last_used)}</td><td>${s.current ? `<span class="chip gold">${esc(tr("this one"))}</span>` : `<button class="btn small" data-end="${esc(s.id)}">${esc(tr("Sign out"))}</button>`}</td></tr>`).join("")}</tbody></table>
        <div class="row"><button class="btn small" data-end-all>${esc(tr("Sign out everywhere else"))}</button></div>
        <h3>${esc(tr("Recent activity"))}</h3><p class="small muted">${esc(tr("Anything you do not recognise? Sign out everywhere else, then check how you sign in."))}</p>
        <table class="t"><tbody>${(activity.activity || []).map((a) => `<tr><td>${when(a.created_at)}</td><td>${esc(names[a.action] || a.action)}</td><td translate="no">${esc(a.note || "")}</td></tr>`).join("")}</tbody></table>
        <details class="note"><summary><b>${esc(tr("Close the account"))}</b></summary><p>${esc(tr("Your logs stay on the server and keep working with their upload credentials, unless you delete them too. You leave your legions; one you lead passes to an officer."))}</p>
          <label><input type="checkbox" data-close-logs> ${esc(tr("Delete my logs as well"))}</label>
          <div class="row"><input data-close-confirm placeholder="delete my account" aria-label="${esc(tr("Type delete my account"))}"><button class="btn small" data-close>${esc(tr("Close the account"))}</button></div></details>`;
      el.querySelector("[data-rename]").onclick = () => {
        const name = prompt(tr("Your account's name (2-24 letters or digits)"), st.me.name || "");
        if (name && name.trim()) act(() => call("POST", "/api/v1/account/name", { name: name.trim() }).then((r) => io.renamed && io.renamed(r)), tr("Renamed"));
      };
      el.querySelectorAll("[data-end]").forEach((b) => (b.onclick = () => act(() => call("POST", "/api/v1/account/sessions/revoke", { id: +b.dataset.end }), tr("Signed out there"))));
      el.querySelector("[data-end-all]").onclick = () => {
        if (confirm(tr("Sign out every other app and website?"))) act(() => call("POST", "/api/v1/account/sessions/revoke", { all: true }), (r) => tr("{0} signed out", r.signed_out));
      };
      el.querySelector("[data-close]").onclick = async () => {
        const typed = el.querySelector("[data-close-confirm]").value.trim();
        if (typed !== "delete my account") return alert(tr('Type "delete my account" to close it.'));
        try {
          await call("POST", "/api/v1/account/delete", { confirm: typed, delete_logs: el.querySelector("[data-close-logs]").checked });
          if (io.closed) io.closed();
          render();
        } catch (e) {
          flash(plain(e.message));
          render();
        }
      };
      if (io.security) await io.security(el.querySelector("[data-acct-extras]"), st.me, render, flash);
    }

    render();
    return {
      render,
      show(tab, legion) {
        st.tab = tab || "logs";
        st.legion = legion || null;
        render();
      },
    };
  }

  window.A2Account = { menu, mount, escape: esc, when, plain };
})();
