// The optional account on the website: the session, the name and its menu in the header, and the account
// page (account.html, drawn by static/account-view.js).
//
// A session is a website credential (a2web_…, at most 30 days unused) that this browser keeps for one log
// server and sends only to it, as X-Account-Token: no cookies, so another site's page can never act with
// it. It is handed over once, after one of: the desktop app approving the code shown here, a one-time
// link from the app (#a2ticket=… in the address, a part of the address browsers never send to a site), a
// passkey, or Discord. Lasting changes (a passkey, Discord, linking another computer, closing the account)
// need a sign-in from the last 15 minutes; the server says so when one is older.
window.A2Session = (function () {
  "use strict";
  const KEY = "a2-account-v1";
  const TOKEN = /^a2web_[A-Za-z0-9_-]{20,90}$/;
  const clean = (u) => String(u || "").replace(/\/+$/, "");
  function load() {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) || "null");
      return v && TOKEN.test(v.token || "") && /^https?:\/\//.test(v.server || "") ? v : null;
    } catch (e) {
      return null;
    }
  }
  function save(server, token, account) {
    if (!TOKEN.test(token || "")) throw Error("The server answered without a website session");
    try {
      localStorage.setItem(KEY, JSON.stringify({ server: clean(server), token, name: (account || {}).name || "" }));
    } catch (e) {
      throw Error("This browser does not keep sign-ins (private window or blocked storage)", { cause: e });
    }
  }
  function clear() {
    try {
      localStorage.removeItem(KEY);
    } catch (e) {}
  }
  const base = () => clean(window.A2 && A2.base ? A2.base() : "");
  // The credential for a request to `server`, when this browser is signed in there.
  function token(server) {
    const s = load();
    return s && s.server === clean(server) ? s.token : null;
  }
  async function send(method, path, body, credential) {
    const b = base();
    if (!b) throw Error("No log server is set up for this site yet");
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (credential) headers["X-Account-Token"] = credential;
    let r;
    try {
      r = await fetch(b + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: "omit", cache: "no-store", redirect: "error" });
    } catch (e) {
      throw Error("Can't reach the log server at " + b, { cause: e });
    }
    const j = await r.json().catch(() => ({}));
    if (r.status === 401 && credential) {
      clear();
      const err = Error(j.error || "Sign in again: this sign-in has ended");
      err.signedOut = true;
      throw err;
    }
    if (!r.ok) {
      const err = Error(j.error || r.statusText || "The server refused");
      err.status = r.status;
      err.body = j; // a choice the server offers (moving Discord from another account)
      throw err;
    }
    return j;
  }
  async function call(method, path, body) {
    const t = token(base());
    if (!t) {
      const err = Error("Sign in first");
      err.signedOut = true;
      throw err;
    }
    return send(method, path, body, t);
  }
  async function status() {
    const b = base();
    if (!b) return { signed_in: false, server: "" };
    const t = token(b);
    if (!t) {
      let config = null;
      try {
        config = await send("GET", "/api/v1/account/config");
      } catch (e) {}
      return { signed_in: false, server: b, config };
    }
    try {
      const me = await send("GET", "/api/v1/account", undefined, t);
      return { signed_in: true, server: b, account: me.account, session: me.session };
    } catch (e) {
      if (e.signedOut) return { signed_in: false, server: b, ended: e.message };
      throw e;
    }
  }
  async function signout() {
    const t = token(base());
    clear();
    if (t) await send("POST", "/api/v1/account/signout", {}, t).catch(() => {});
  }
  // Signing in: each way ends with the server's {token, account}.
  async function finish(result) {
    save(base(), result.token, result.account);
    return result;
  }
  return { load, save, clear, token, send, call, status, signout, finish, base };
})();

(function () {
  "use strict";
  const t = (text, ...values) => (window.A2I18n ? window.A2I18n.t(text, ...values) : text.replace(/\{(\d)\}/g, (m, i) => values[i] ?? ""));
  const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const page = () => new URL("account.html", location.href).href;
  const S = window.A2Session;
  let menu = null,
    view = null,
    notice = "";

  // WebAuthn: the server's options (JSON, base64url) to what the browser takes, and back.
  const dec = (s) => Uint8Array.from(atob(String(s).replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(String(s).length / 4) * 4, "=")), (c) => c.charCodeAt(0)).buffer;
  const enc = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  function credentialJSON(c) {
    const r = c.response;
    const out = { id: c.id, rawId: enc(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {}, response: { clientDataJSON: enc(r.clientDataJSON) } };
    if (c.authenticatorAttachment) out.authenticatorAttachment = c.authenticatorAttachment;
    if (r.attestationObject) {
      out.response.attestationObject = enc(r.attestationObject);
      if (r.getTransports) out.response.transports = r.getTransports();
    }
    if (r.authenticatorData) {
      out.response.authenticatorData = enc(r.authenticatorData);
      out.response.signature = enc(r.signature);
      if (r.userHandle) out.response.userHandle = enc(r.userHandle);
    }
    return out;
  }
  const passkeys = () => !!(window.PublicKeyCredential && navigator.credentials);

  async function passkeySignIn() {
    const started = await S.send("POST", "/api/v1/account/passkeys/signin/options", { origin: location.origin });
    const o = started.options;
    const got = await navigator.credentials.get({ publicKey: { ...o, challenge: dec(o.challenge), allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: dec(c.id) })) } });
    if (!got) throw Error(t("No passkey was chosen"));
    return S.finish(await S.send("POST", "/api/v1/account/passkeys/signin", { request: started.request, credential: credentialJSON(got) }));
  }
  async function passkeyAdd(label) {
    const started = await S.call("POST", "/api/v1/account/passkeys/options", { origin: location.origin });
    const o = started.options;
    const made = await navigator.credentials.create({
      publicKey: { ...o, challenge: dec(o.challenge), user: { ...o.user, id: dec(o.user.id) }, excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: dec(c.id) })) },
    });
    if (!made) throw Error(t("No passkey was made"));
    return S.call("POST", "/api/v1/account/passkeys/add", { request: started.request, credential: credentialJSON(made), label });
  }
  async function discord(purpose) {
    const back = page();
    const started = await (purpose === "link" ? S.call : S.send)("POST", "/api/v1/account/discord/start", { purpose, return_to: back });
    if (!/^https:\/\/discord\.com\//.test(started.url || "")) throw Error(t("The server did not start a Discord sign-in"));
    location.href = started.url;
  }

  // Signed out on the account page: the three ways in.
  function signedOut(root, s, done) {
    const methods = (s.config && s.config.methods) || {};
    root.innerHTML = `<section class="win"><div class="wh"><h2>${esc(t("Sign in"))}</h2></div><div class="wb">
      ${notice ? `<div class="note" role="status">${esc(notice)}</div>` : ""}${s.ended ? `<div class="note">${esc(s.ended)}</div>` : ""}
      ${!s.server ? `<div class="note">${esc(t("No log server is set up for this site yet."))}</div>` : !s.config ? `<div class="note">${esc(t("This log server does not offer accounts yet."))}</div>` : ""}
      <p>${esc(t("An account is optional. Signed in, you see all your uploaded logs in one place, manage them, and share logs with your legion. There is no password."))}</p>
      <h3>${esc(t("Approve in the app"))}</h3>
      <p class="small muted">${esc(t("The desktop app holds your account. Show a code here, then in the app open the menu with your name → Approve a website sign-in, and enter it."))}</p>
      <div class="row"><button class="btn primary" data-code ${s.config ? "" : "disabled"}>${esc(t("Show a sign-in code"))}</button></div><div data-code-out></div>
      ${methods.passkey && passkeys() ? `<h3>${esc(t("Passkey"))}</h3><p class="small muted">${esc(t("Windows Hello, your phone or a security key, once you added one here (Sign-in & security)."))}</p><div class="row"><button class="btn" data-passkey>${esc(t("Sign in with a passkey"))}</button></div>` : ""}
      ${methods.discord ? `<h3>Discord</h3><div class="row"><button class="btn" data-discord>${esc(t("Sign in with Discord"))}</button></div>` : ""}
      <p class="small muted">${esc(t("No account yet? Create it in the desktop app: the menu at the top right → Sign in → Create my account."))} <a href="https://github.com/sam-t-anderson/Aion-2-tools/releases/latest" target="_blank" rel="noopener">${esc(t("Download the app"))}</a></p>
      <div data-out role="status"></div></div></section>`;
    notice = "";
    const say = (text) => (root.querySelector("[data-out]").textContent = text);
    const signed = () => {
      if (menu) menu.refresh();
      done();
    };
    const code = root.querySelector("[data-code]");
    code.onclick = async () => {
      code.disabled = true;
      const out = root.querySelector("[data-code-out]");
      try {
        const started = await S.send("POST", "/api/v1/account/signin/start", {});
        out.innerHTML = `<div class="acct-code" translate="no">${esc(started.code)}</div><p class="small muted">${esc(t("Waiting for the app… The code works for ten minutes, once."))}</p>`;
        const until = Date.now() + (started.expires_in || 600) * 1000;
        while (Date.now() < until && root.isConnected) {
          await new Promise((r) => setTimeout(r, (started.interval || 3) * 1000));
          const r = await S.send("POST", "/api/v1/account/signin/poll", { request: started.request, secret: started.secret });
          if (r.status === "approved") {
            await S.finish(r);
            return signed();
          }
          if (r.status === "denied") throw Error(t("The app denied this sign-in."));
          if (r.status !== "pending") break;
        }
        throw Error(t("The code expired. Show a new one."));
      } catch (e) {
        out.innerHTML = `<div class="note">${esc(e.message)}</div>`;
        code.disabled = false;
      }
    };
    const pk = root.querySelector("[data-passkey]");
    if (pk)
      pk.onclick = async () => {
        try {
          await passkeySignIn();
          signed();
        } catch (e) {
          say(e.name === "NotAllowedError" ? t("The passkey sign-in was cancelled.") : e.message);
        }
      };
    const dc = root.querySelector("[data-discord]");
    if (dc) dc.onclick = () => discord("signin").catch((e) => say(e.message));
  }

  // Signed in, Sign-in & security: what only the website does.
  async function security(el, me, render, flash) {
    let keys = [];
    try {
      keys = (await S.call("GET", "/api/v1/account/passkeys")).passkeys || [];
    } catch (e) {}
    const when = window.A2Account.when;
    el.innerHTML = `<h3>${esc(t("Passkeys"))}</h3>
      ${keys.length ? `<table class="t"><tbody>${keys.map((k) => `<tr><td translate="no">${esc(k.label)}</td><td translate="no">${esc(k.site)}</td><td>${esc(t("added {0}", when(k.created_at)))}</td><td>${esc(t("last used {0}", when(k.last_used)))}</td><td><button class="btn small" data-key-remove="${esc(k.id)}">${esc(t("Remove"))}</button></td></tr>`).join("")}</tbody></table>` : `<p class="small muted">${esc(t("No passkey yet."))}</p>`}
      ${passkeys() ? `<div class="row"><input data-key-label maxlength="60" placeholder="${esc(t("Name it (e.g. my laptop)"))}" aria-label="${esc(t("Passkey name"))}"><button class="btn small primary" data-key-add>${esc(t("Add a passkey"))}</button></div>` : `<p class="small muted">${esc(t("This browser cannot use passkeys."))}</p>`}
      <h3>Discord</h3><div class="row">${me.discord ? `<span>${esc(t("Linked: {0}", me.discord.name))}</span><button class="btn small" data-discord-unlink>${esc(t("Unlink"))}</button>` : `<button class="btn small" data-discord-link>${esc(t("Link Discord"))}</button>`}</div>
      <h3>${esc(t("Another computer's app"))}</h3><div class="row"><button class="btn small" data-link-code>${esc(t("Make a link code"))}</button><span class="small muted">${esc(t("Enter it in that app: Sign in → I already have an account → Link with a code."))}</span></div><div data-link-out></div>
      <p class="small muted">${esc(t("Adding a way in needs a sign-in from the last 15 minutes. If it is refused, sign out, sign in again and retry."))}</p>`;
    const act = async (work, done) => {
      try {
        await work();
        flash(done);
      } catch (e) {
        flash(e.message);
      }
      render();
    };
    el.querySelectorAll("[data-key-remove]").forEach((b) => (b.onclick = () => act(() => S.call("POST", "/api/v1/account/passkeys/remove", { id: b.dataset.keyRemove }), t("Passkey removed"))));
    const add = el.querySelector("[data-key-add]");
    if (add) add.onclick = () => act(() => passkeyAdd(el.querySelector("[data-key-label]").value.trim() || "Passkey"), t("Passkey added"));
    const unlink = el.querySelector("[data-discord-unlink]");
    if (unlink) unlink.onclick = () => act(() => S.call("POST", "/api/v1/account/discord/unlink", {}), t("Discord unlinked"));
    const link = el.querySelector("[data-discord-link]");
    if (link) link.onclick = () => discord("link").catch((e) => (flash(e.message), render()));
    el.querySelector("[data-link-code]").onclick = async () => {
      const out = el.querySelector("[data-link-out]");
      try {
        const r = await S.call("POST", "/api/v1/account/link", {});
        out.innerHTML = `<div class="acct-code" translate="no">${esc(r.code)}</div><p class="small muted">${esc(t("Works for ten minutes, once."))}</p>`;
      } catch (e) {
        out.innerHTML = `<div class="note">${esc(e.message)}</div>`;
      }
    };
  }

  const io = {
    kind: "web",
    status: () => S.status(),
    call: (method, path, body) => S.call(method, path, body),
    href: (tab) => page() + (tab === "signin" ? "" : "#" + tab),
    logHref(l) {
      const view = (String(l.url || "").match(/[?&]t=([A-Za-z0-9_-]+)/) || [])[1];
      return "log.html?id=" + encodeURIComponent(l.id) + (view ? "&t=" + encodeURIComponent(view) : "");
    },
    inviteLink: (token) => page() + "#a2invite=" + token,
    // the desktop app holds the upload credentials a claim needs, so the website names it
    claimHint: "A legion needs one of your claimed characters. Claim yours in the desktop app, on Combat Logs → My Character Identities, and it joins your account.",
    claimHref: "logs.html#identities",
    signout: () => S.signout(),
    onSignedOut() {
      if (view) view.render();
    },
    onTab(tab) {
      if (document.getElementById("account-root")) history.replaceState(null, "", "#" + tab);
    },
    onLegion(id) {
      if (document.getElementById("account-root")) history.replaceState(null, "", id ? "#legions/" + id : "#legions");
    },
    renamed() {
      if (menu) menu.refresh();
    },
    closed() {
      S.clear();
      if (menu) menu.refresh();
    },
    signedOut,
    security,
  };

  // The date with the time of day, in the computer's clock: 2026-10-23 15:04:05.
  const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
  function moveQuestion(other) {
    const made = other.created_at ? whenAt(other.created_at * 1000) : "—";
    return other.closes
      ? t("This Discord account signs in to your other account, {0}, made on {1}. Move Discord to this account? That account's {2} logs and {3} characters come along, and it closes.", other.name, made, other.logs, other.characters)
      : t("This Discord account is linked to your other account, {0}, made on {1}. Move Discord to this account? That account keeps its logs and its other ways to sign in.", other.name, made);
  }

  // Hand-overs that arrive in the address's fragment: a one-time sign-in ticket, Discord's refusal, the code that
  // finishes linking Discord (with this browser's own session: a link started elsewhere is refused), an invite.
  let opened = null;
  async function arrivals() {
    const hash = new URLSearchParams(location.hash.slice(1));
    const ticket = hash.get("a2ticket"),
      error = hash.get("a2error"),
      link = hash.get("a2link"),
      invite = hash.get("a2invite");
    if (ticket || error || link) history.replaceState(null, "", location.pathname + location.search);
    if (ticket) {
      try {
        if (window.A2 && A2.ensure) await A2.ensure();
        await S.finish(await S.send("POST", "/api/v1/account/ticket/redeem", { ticket }));
      } catch (e) {
        notice = e.message;
      }
    }
    if (link) {
      opened = "security";
      try {
        if (window.A2 && A2.ensure) await A2.ensure();
        try {
          await S.call("POST", "/api/v1/account/discord/link/finish", { code: link });
        } catch (e) {
          // Discord already signs in to another account of yours (made by signing in with Discord by mistake): the
          // server names it, and the same code moves Discord here once asked
          const other = e.status === 409 && e.body && e.body.move;
          if (!other || !confirm(moveQuestion(other))) throw e;
          await S.call("POST", "/api/v1/account/discord/link/finish", { code: link, move: true });
        }
        notice = t("Discord linked");
      } catch (e) {
        notice = e.message;
      }
    }
    if (error) notice = error;
    if (invite && !document.getElementById("account-root")) location.href = page() + "#a2invite=" + encodeURIComponent(invite);
    return invite && /^a2inv_[A-Za-z0-9_-]{20,60}$/.test(invite) ? invite : null;
  }

  function slot() {
    const bar = document.querySelector(".topbar");
    if (!bar) return null;
    const el = document.createElement("div");
    el.id = "account-menu";
    el.className = "acct-slot";
    const before = document.getElementById("dau") || document.getElementById("accent") || document.getElementById("theme");
    if (before && before.parentNode === bar) bar.insertBefore(el, before);
    else bar.appendChild(el);
    // On a phone the header keeps one row: the account is a page in the folded menu instead.
    const nav = bar.querySelector(".nav");
    if (nav && !nav.querySelector(".acct-navlink")) {
      const a = document.createElement("a");
      a.className = "acct-navlink";
      a.href = "account.html";
      a.textContent = t("Account");
      nav.appendChild(a);
    }
    return el;
  }

  async function start() {
    const invite = await arrivals();
    if (window.A2 && A2.ensure) await A2.ensure().catch(() => {});
    menu = window.A2Account.menu(slot(), io);
    const root = document.getElementById("account-root");
    if (!root) return;
    const [tab, legion] = location.hash.slice(1).split("/");
    view = window.A2Account.mount(root, io, {
      tab: invite ? "legions" : opened || (["logs", "legions", "security"].includes(tab) ? tab : "logs"),
      legion: /^lg_[0-9a-f]{12}$/.test(legion || "") ? legion : null,
      invite,
    });
    if (notice && S.load()) {
      alert(notice);
      notice = "";
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
