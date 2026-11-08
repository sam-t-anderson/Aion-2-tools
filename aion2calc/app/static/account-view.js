/* The optional account, for the desktop app and the website: My logs, Top parses (its own tab since 0.2.392),
   Legions, and Sign-in & security.
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

  // A log list's query: its page, the boss, and the From/To days. The days are the viewer's own, as the table
  // shows its times, so the server gets the instants they span (From's midnight up to the midnight after To).
  const listQuery = (f, limit = 50) => {
    const q = new URLSearchParams({ page: String(f.page), limit: String(limit) });
    if (f.boss) q.set("boss", f.boss);
    const midnight = (day, plus) => {
      const [y, m, d] = day.split("-").map(Number);
      return new Date(y, m - 1, d + plus).toISOString();
    };
    if (f.since) q.set("since", midnight(f.since, 0));
    if (f.until) q.set("until", midnight(f.until, 1));
    return q;
  };
  const filtering = (f) => Boolean(f.boss || f.since || f.until);
  const filterRow = (f, what) =>
    `<input type="search" data-boss value="${esc(f.boss)}" placeholder="${esc(tr("Boss"))}" aria-label="${esc(tr("Filter {0} by boss", what))}">
      <label>${esc(tr("From"))} <input type="date" data-since value="${esc(f.since)}" aria-label="${esc(tr("Uploaded on or after"))}"></label>
      <label>${esc(tr("To"))} <input type="date" data-until value="${esc(f.until)}" aria-label="${esc(tr("Uploaded on or before"))}"></label>
      <button class="btn small" data-filter>${esc(tr("Filter"))}</button>${filtering(f) ? `<button class="btn small" data-clear>${esc(tr("Clear"))}</button>` : ""}`;
  const pager = (f, r) => {
    const pages = Math.max(1, Math.ceil((r.total || 0) / (r.limit || 50)));
    return `<div class="row">${f.page > 1 ? `<button class="btn small" data-page="${f.page - 1}">${esc(tr("Previous"))}</button>` : ""}<span class="small muted">${esc(tr("Page {0} of {1}", f.page, pages))}</span>${f.page < pages ? `<button class="btn small" data-page="${f.page + 1}">${esc(tr("Next"))}</button>` : ""}</div>`;
  };
  const wireList = (el, f, show) => {
    const apply = () => {
      f.boss = el.querySelector("[data-boss]").value.trim();
      f.since = el.querySelector("[data-since]").value;
      f.until = el.querySelector("[data-until]").value;
      f.page = 1;
      show();
    };
    el.querySelector("[data-filter]").onclick = apply;
    el.querySelectorAll("[data-boss],[data-since],[data-until]").forEach((i) => (i.onkeydown = (ev) => ev.key === "Enter" && apply()));
    const clear = el.querySelector("[data-clear]");
    if (clear)
      clear.onclick = () => {
        Object.assign(f, fresh(f.id));
        show();
      };
    el.querySelectorAll("[data-page]").forEach((b) => (b.onclick = () => ((f.page = +b.dataset.page), show())));
  };
  const fresh = (id) => ({ id, page: 1, boss: "", since: "", until: "" });
  // Top parses' page (0.2.392): its order, filters and page for the visit; the page size is kept in this browser.
  const PARSES_PER_PAGE = "aion2.account.parsesPerPage";
  const parsesPerPage = () => {
    try {
      const n = Number(localStorage.getItem(PARSES_PER_PAGE));
      return [25, 50, 100].includes(n) ? n : 25;
    } catch (e) {
      return 25;
    }
  };
  const freshParses = () => ({ page: 1, limit: parsesPerPage(), sort: "parse", order: "desc", boss: "", difficulty: "", cls: "", character: "" });

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
          <a role="menuitem" href="${esc(io.href("parses"))}">${esc(tr("Top parses"))}</a>
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
    const st = { tab: opts.tab || "logs", mine: fresh(null), shared: fresh(null), legion: opts.legion || null, invite: opts.invite || null, me: null, flash: "", parses: freshParses(), parsesAll: null };
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
      const tabs = [["logs", tr("My logs")], ["parses", tr("Top parses")], ["legions", tr("Legions")], ["security", tr("Sign-in & security")]];
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
        await { logs: renderLogs, parses: renderParses, legions: renderLegions, security: renderSecurity }[st.tab](body);
      } catch (e) {
        if (e && e.signedOut) return render();
        body.innerHTML = box(plain(e.message));
      }
    }

    async function act(work, done) {
      st.parsesAll = null; // a log changed: an older server's whole list of parses is asked for again
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
      const f = st.mine;
      const r = await call("GET", "/api/v1/account/logs?" + listQuery(f));
      el.innerHTML = `<div class="row">${filterRow(f, tr("your logs"))}${io.logTools ? io.logTools() : ""}<span class="small muted">${esc(many(r.total || 0, "{0} log", "{0} logs"))}</span></div>
        ${r.logs.length ? `<table class="t acct-logs"><thead><tr><th>${esc(tr("Description"))}</th><th>${esc(tr("Character"))}</th><th>${esc(tr("Uploaded"))}</th><th class="r">${esc(tr("Duration"))}</th><th>${esc(tr("Visibility"))}</th><th>${esc(tr("Edit"))}</th><th>${esc(tr("Delete"))}</th></tr></thead><tbody>
        ${r.logs.map((l, i) => `<tr><td><a href="${esc(io.logHref(l))}"${io.logTarget || ""}>${esc(l.title || l.boss || l.id)}</a>${l.held ? ` <span class="chip">${esc(tr("under review"))}</span>` : ""}<div class="small muted" translate="no">${esc(l.boss || "")}</div></td>
          <td translate="no">${esc(l.uploader || "—")}</td><td>${when(l.created_at)}</td><td class="r">${length(l.duration)}</td>
          <td><select data-vis="${i}" aria-label="${esc(tr("Who can see {0}", l.title || l.id))}" ${l.held ? "disabled" : ""}>${VIS().map(([v, t]) => `<option value="${v}" ${v === l.visibility ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></td>
          <td><button class="btn small" data-title="${i}">${esc(tr("Edit"))}</button></td><td><button class="btn small" data-del="${i}">${esc(tr("Delete"))}</button></td></tr>`).join("")}</tbody></table>
        ${pager(f, r)}`
        : `<p class="empty">${esc(filtering(f) ? tr("No logs match.") : tr("No logs yet. Uploads from your signed-in app join here, and the app adds the ones it uploaded before."))}</p>`}
        <p class="small muted">${esc(tr("Legion only: the members of your legions open it; it is listed nowhere else. Private: only its secret link opens it."))}</p>`;
      wireList(el, f, render);
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

    // ------------------------------------------------------------ top parses (0.2.391; its own tab since 0.2.392)
    // The account's best run on each boss and difficulty for each of its characters (log server 0.2.170), with the
    // parse the rankings give it: WCL-style colours, gold for the bracket's best run, provisional under five runs.
    // Log server 0.2.171 pages, sorts and filters them and offers the filter menus (facets); log server 0.2.170
    // sends the whole list whatever is asked, so the tab does the same with it here (locally).
    const parseTier = (p, rank) =>
      rank === 1 || p >= 100 ? "gold" : p >= 99 ? "pink" : p >= 95 ? "orange" : p >= 75 ? "purple" : p >= 50 ? "blue" : p >= 25 ? "green" : "grey";
    const parseCell = (p) => {
      if (p.parse === null || p.parse === undefined)
        return `<span class="parse q-none" title="${esc(tr("No parse yet: no other ranked run of this class on this encounter"))}">·</span>`;
      const title =
        tr("Parse {0}, rank {1} of {2} ranked runs of this class on this encounter", p.parse, p.parse_rank ?? "—", p.parse_runs) +
        (p.provisional ? " " + tr("Provisional: fewer than 5 runs.") : "");
      return `<span class="parse q-${parseTier(p.parse, p.parse_rank)}${p.provisional ? " provisional" : ""}" title="${esc(title)}">${Math.round(p.parse)}</span>`;
    };
    const cap = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : "—");
    // Each column's sort and its first direction, as the server has them.
    const SORTS = { parse: "desc", dps: "desc", date: "desc", boss: "asc", difficulty: "asc", character: "asc", class: "asc" };
    const low = (v) => String(v ?? "").toLowerCase();
    const order = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
    // The character menu's value: the name and the server together.
    const pick = (name, server) => `${name}|${server}`;
    const unpick = (value) => {
      const at = String(value).lastIndexOf("|");
      return at < 0 ? [String(value), ""] : [value.slice(0, at), value.slice(at + 1)];
    };

    // Log server 0.2.171's page, made here from 0.2.170's whole list: the menus, the filters, the order and the page.
    function locally(all, p) {
      const tally = (key) => {
        const seen = new Map();
        for (const r of all) seen.set(key(r), (seen.get(key(r)) || 0) + 1);
        return [...seen].sort((a, b) => order(low(a[0]), low(b[0])) || order(a[0], b[0]));
      };
      const facets = {
        bosses: tally((r) => r.boss).map(([value, count]) => ({ value, count })),
        difficulties: tally((r) => r.difficulty).map(([value, count]) => ({ value, count })),
        classes: tally((r) => r.class).map(([value, count]) => ({ value, count })),
        characters: tally((r) => pick(r.character, r.server)).map(([value, count]) => {
          const [character, server] = unpick(value);
          return { character, server, count };
        }),
      };
      const [name, server] = unpick(p.character);
      const kept = all.filter(
        (r) =>
          (!p.boss || low(r.boss) === low(p.boss)) &&
          (!p.difficulty || low(r.difficulty) === low(p.difficulty)) &&
          (!p.cls || low(r.class) === low(p.cls)) &&
          (!p.character || (low(r.character) === low(name) && String(r.server) === server)),
      );
      // ties by DPS (highest first), then boss, difficulty and character; a run with no parse yet last by parse
      const base = kept
        .slice()
        .sort((a, b) => order(low(a.boss), low(b.boss)) || order(low(a.difficulty), low(b.difficulty)) || order(low(a.character), low(b.character)))
        .sort((a, b) => (b.dps || 0) - (a.dps || 0));
      const dir = p.order === "asc" ? 1 : -1;
      let rows;
      if (p.sort === "parse") {
        const none = (r) => r.parse === null || r.parse === undefined;
        rows = base
          .filter((r) => !none(r))
          .sort((a, b) => dir * (a.parse - b.parse))
          .concat(base.filter(none));
      } else {
        const key = {
          dps: (r) => [r.dps || 0],
          date: (r) => [r.uploaded_at || 0],
          boss: (r) => [low(r.boss), low(r.difficulty)],
          difficulty: (r) => [low(r.difficulty), low(r.boss)],
          character: (r) => [low(r.character), String(r.server)],
          class: (r) => [low(r.class)],
        }[p.sort];
        rows = base.slice().sort((a, b) => {
          const x = key(a),
            y = key(b);
          return dir * (x.map((v, i) => order(v, y[i])).find((c) => c) || 0);
        });
      }
      const pages = Math.max(1, Math.ceil(rows.length / p.limit)),
        page = Math.min(p.page, pages);
      return { parses: rows.slice((page - 1) * p.limit, page * p.limit), total: rows.length, page, limit: p.limit, pages, all: all.length, facets };
    }

    async function fetchParses(p) {
      if (st.parsesAll) return locally(st.parsesAll.parses, p);
      const q = new URLSearchParams({ page: String(p.page), limit: String(p.limit), sort: p.sort, order: p.order });
      if (p.boss) q.set("boss", p.boss);
      if (p.difficulty) q.set("difficulty", p.difficulty);
      if (p.cls) q.set("class", p.cls);
      if (p.character) {
        const [name, server] = unpick(p.character);
        q.set("character", name);
        if (server) q.set("server", server);
      }
      const r = await call("GET", "/api/v1/account/top-parses?" + q);
      if (r.page === undefined || !r.facets) {
        // log server 0.2.170: the whole list (its best 500 by DPS), paged, sorted and filtered here
        st.parsesAll = { parses: r.parses || [], truncated: Boolean(r.truncated) };
        return locally(st.parsesAll.parses, p);
      }
      return r;
    }

    async function renderParses(el, focus) {
      const p = st.parses;
      if (!el.children.length) el.innerHTML = `<p class="small muted">${esc(tr("Loading your top parses…"))}</p>`;
      el.setAttribute("aria-busy", "true");
      let r;
      try {
        r = await fetchParses(p);
      } catch (e) {
        if (e && e.signedOut) throw e;
        const missing = /not found|404|does not send that request/i.test(String((e && e.message) || ""));
        el.innerHTML = `<p class="small muted">${esc(missing ? tr("The community server doesn't list top parses yet.") : plain(e.message))}</p>`;
        return;
      } finally {
        el.removeAttribute("aria-busy");
      }
      if (!el.isConnected) return;
      p.page = r.page;
      const again = (selector) =>
        renderParses(el, selector).catch((e) => {
          if (e && e.signedOut) return render();
          el.innerHTML = box(plain(e.message));
        });
      const note = `<p class="small muted">${esc(tr("Your best DPS on each boss and difficulty for each of your characters, from the logs in this account (any visibility), in ranking-eligible PvE fights. The parse compares it with every ranked public run of the same boss, game version and difficulty by the same class: 100 is above them all."))}</p>`;
      if (!(r.all ?? r.total)) {
        el.innerHTML = `<p class="small acct-top-empty">${esc(tr("No ranked boss fights in your logs yet. Your best run on each boss shows here, with its parse against every public run of your class."))}</p>${note}`;
        return;
      }
      const f = r.facets || {};
      const filtered = Boolean(p.boss || p.difficulty || p.cls || p.character);
      const menu = (key, label, everything, items) =>
        `<label>${esc(label)} <select data-pf="${key}"><option value="">${esc(everything)}</option>${items
          .map(([value, shown, count]) => `<option value="${esc(value)}" ${value === p[key] ? "selected" : ""}>${esc(shown)} (${count})</option>`)
          .join("")}</select></label>`;
      const COLUMNS = [
        ["boss", tr("Boss")],
        ["difficulty", tr("Difficulty")],
        ["character", tr("Character")],
        ["class", tr("Class")],
        ["dps", tr("DPS"), "r"],
        ["parse", tr("Parse"), "r"],
        ["date", tr("Date")],
      ];
      const heads = COLUMNS.map(([key, label, align]) => {
        const on = p.sort === key;
        return `<th class="${align || ""}" aria-sort="${on ? (p.order === "asc" ? "ascending" : "descending") : "none"}"><button type="button" class="sort${on ? " on" : ""}" data-sort="${key}">${esc(label)}<span class="arrow" aria-hidden="true">${on ? (p.order === "asc" ? "▲" : "▼") : ""}</span></button></th>`;
      }).join("");
      el.innerHTML = `<div class="row acct-parse-filters">
          ${menu("boss", tr("Boss"), tr("All bosses"), (f.bosses || []).map((x) => [x.value, x.value, x.count]))}
          ${menu("difficulty", tr("Difficulty"), tr("All difficulties"), (f.difficulties || []).map((x) => [x.value, cap(x.value), x.count]))}
          ${menu("cls", tr("Class"), tr("All classes"), (f.classes || []).map((x) => [x.value, cap(x.value), x.count]))}
          ${menu("character", tr("Character"), tr("All characters"), (f.characters || []).map((x) => [pick(x.character, x.server), `${x.character} (${world(x.server)})`, x.count]))}
          <button class="btn small" data-pf-reset ${filtered ? "" : "disabled"}>${esc(tr("Reset"))}</button></div>
        ${
          r.parses.length
            ? `<table class="t acct-parses"><thead><tr>${heads}<th>${esc(tr("Log"))}</th></tr></thead><tbody>
          ${r.parses
            .map(
              (x) => `<tr><td translate="no">${esc(x.boss || "—")}</td><td>${esc(cap(x.difficulty))}</td>
            <td><span translate="no">${esc(x.character || "—")}</span> <span class="small muted" translate="no">${esc(world(x.server))}</span></td>
            <td>${esc(cap(x.class))}</td><td class="r" title="${esc(many(x.attempts || 1, "Best of {0} ranked run", "Best of {0} ranked runs"))}">${Math.round(+x.dps || 0).toLocaleString("en-US")}</td>
            <td class="r">${parseCell(x)}</td><td>${when(x.uploaded_at)}</td>
            <td><a href="${esc(io.logHref({ id: x.log, url: x.url, segment: x.segment }))}"${io.logTarget || ""}>${esc(tr("Open"))}</a></td></tr>`,
            )
            .join("")}</tbody></table>`
            : `<p class="small acct-top-empty">${esc(tr("No parses match."))}</p>`
        }
        <div class="row acct-pager"><button class="btn small" data-pp="prev" ${r.page > 1 ? "" : "disabled"}>${esc(tr("Previous"))}</button>
          <span class="small muted" data-pp-status>${esc(tr("Page {0} of {1}", r.page, r.pages) + " · " + many(r.total, "{0} parse", "{0} parses"))}</span>
          <button class="btn small" data-pp="next" ${r.page < r.pages ? "" : "disabled"}>${esc(tr("Next"))}</button>
          <label>${esc(tr("Per page"))} <select data-pl>${[25, 50, 100].map((n) => `<option value="${n}" ${n === p.limit ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
        ${st.parsesAll && st.parsesAll.truncated ? `<p class="small muted">${esc(tr("The best {0} by DPS are shown.", st.parsesAll.parses.length))}</p>` : ""}${note}`;
      el.querySelectorAll("[data-pf]").forEach(
        (sel) =>
          (sel.onchange = () => {
            p[sel.dataset.pf] = sel.value;
            p.page = 1;
            again(`[data-pf="${sel.dataset.pf}"]`);
          }),
      );
      el.querySelector("[data-pf-reset]").onclick = () => {
        Object.assign(p, { boss: "", difficulty: "", cls: "", character: "", page: 1 });
        again("[data-pf=boss]");
      };
      el.querySelectorAll("[data-sort]").forEach(
        (b) =>
          (b.onclick = () => {
            const key = b.dataset.sort;
            if (p.sort === key) p.order = p.order === "asc" ? "desc" : "asc";
            else Object.assign(p, { sort: key, order: SORTS[key] });
            p.page = 1;
            again(`[data-sort="${key}"]`);
          }),
      );
      el.querySelectorAll("[data-pp]").forEach(
        (b) =>
          (b.onclick = () => {
            p.page += b.dataset.pp === "next" ? 1 : -1;
            again(`[data-pp="${b.dataset.pp}"]`);
          }),
      );
      el.querySelector("[data-pl]").onchange = (ev) => {
        p.limit = Number(ev.target.value);
        p.page = 1;
        try {
          localStorage.setItem(PARSES_PER_PAGE, String(p.limit));
        } catch (e) {
          // storage blocked: the default next visit
        }
        again("[data-pl]");
      };
      // a control redrawn under the reader keeps the focus (a disabled one leaves it to the table)
      const target = focus && el.querySelector(focus);
      if (target && !target.disabled) target.focus();
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
      // The featured encounters' race and progress pages (log server 0.2.145) show a legion only when its leader says so.
      const featured = lead
        ? `<h4>${esc(tr("Featured encounters"))}</h4><label><input type="checkbox" data-show-progress ${L.show_progress ? "checked" : ""}> ${esc(tr("Show this legion on the featured encounters' race and progress pages"))}</label>
          <p class="small muted">${esc(tr("Off until you turn it on. When on, a featured boss fought by a member with the character they joined with counts for the legion, under its name; its members are never listed."))}</p>`
        : L.show_progress
          ? `<p class="small muted">${esc(tr("The leader shows this legion on the featured encounters' race and progress pages."))}</p>`
          : "";
      el.innerHTML = `${back}${head}<h4>${esc(tr("Members"))}</h4><table class="t"><thead><tr><th>${esc(tr("Character"))}</th><th>${esc(tr("Role"))}</th><th>${esc(tr("Joined"))}</th><th></th></tr></thead><tbody>${roster}</tbody></table>
        ${requests}${invites}${featured}<h4>${esc(tr("The legion's logs"))}</h4><div data-legion-logs>${esc(tr("Loading…"))}</div>
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
      const showProgress = el.querySelector("[data-show-progress]");
      if (showProgress)
        showProgress.onchange = () =>
          act(() => call("POST", `/api/v1/legions/${id}/progress`, { show: showProgress.checked }), showProgress.checked ? tr("Shown on the featured encounters' pages") : tr("Hidden from the featured encounters' pages"));
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
      if (st.shared.id !== id) st.shared = fresh(id);
      await legionLogs(id, el.querySelector("[data-legion-logs]"));
    }
    // The legion's logs take the filters My logs takes (boss, From, To) and page the same way; they draw on their own,
    // without the rest of the legion's page.
    async function legionLogs(id, logs) {
      const f = st.shared;
      try {
        const r = await call("GET", `/api/v1/legions/${id}/logs?` + listQuery(f));
        logs.innerHTML = `<div class="row">${filterRow(f, tr("the legion's logs"))}<span class="small muted">${esc(many(r.total || 0, "{0} log", "{0} logs"))}</span></div>
          ${r.logs.length
            ? `<table class="t"><thead><tr><th>${esc(tr("Description"))}</th><th>${esc(tr("Member"))}</th><th>${esc(tr("Uploaded"))}</th><th class="r">${esc(tr("Duration"))}</th><th>${esc(tr("Visibility"))}</th></tr></thead><tbody>${r.logs.map((l) => `<tr><td><a href="${esc(io.logHref(l))}"${io.logTarget || ""}>${esc(l.title || l.boss || l.id)}</a><div class="small muted" translate="no">${esc(l.boss || "")}</div></td><td translate="no">${esc(l.member || l.uploader || "—")}</td><td>${when(l.created_at)}</td><td class="r">${length(l.duration)}</td><td>${esc(visLabel(l.visibility))}</td></tr>`).join("")}</tbody></table>${pager(f, r)}`
            : `<p class="empty">${esc(filtering(f) ? tr("No logs match.") : tr("No logs shared yet. Members share a log by making it public or legion only."))}</p>`}`;
        wireList(logs, f, () => legionLogs(id, logs));
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
