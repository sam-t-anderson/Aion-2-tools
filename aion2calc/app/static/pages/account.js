/* Account (#/account/logs|legions|security): the optional sign-in, and with it My logs, Legions and
   Sign-in & security (account-view.js), plus the account menu in the header. The app keeps the
   credential (combat/account.py): this page asks the app, which talks to the server. */
"use strict";

const ACCOUNT_SITE = "https://sam-t-anderson.github.io/Aion-2-tools/";
const accountText = (text, ...values) =>
  window.A2I18n ? window.A2I18n.t(text, ...values) : text.replace(/\{(\d)\}/g, (m, i) => values[i] ?? "");
let accountMenu = null,
  accountView = null;

async function accountStatus() {
  // apiState: the status's "error" (a server without accounts, or offline) is part of what it reports
  const s = await apiState("/api/account");
  // Signed in on another server than Settings uses: shown as signed out here, with that said.
  return s.signed_in && s.here === false ? { ...s, signed_in: false, elsewhere: s.account_server } : s;
}

async function accountCall(method, path, body) {
  try {
    return await api("/api/account", { action: "request", method, path, body });
  } catch (e) {
    if (/sign in again|signed out|Sign in first/i.test(e.message) && accountMenu) accountMenu.refresh();
    throw e;
  }
}

// The app approves a website sign-in by the code the website shows, after showing which browser asks.
async function approveWebsiteSignIn(code) {
  code = (code || prompt(accountText("The code the website shows (eight letters and digits)")) || "").trim();
  if (!code) return null;
  const seen = await accountCall("GET", "/api/v1/account/signin/lookup?code=" + encodeURIComponent(code));
  const network =
    seen.same_network === true
      ? accountText("It started on this computer's internet connection.")
      : seen.same_network === false
        ? accountText(
            "It did NOT start on this computer's internet connection. If someone asked you for this code, deny it.",
          )
        : accountText("The server cannot tell which internet connection it started on.");
  const yes = confirm(
    accountText("Sign in {0} on the website as your account?", seen.browser) +
      "\n\n" +
      network +
      "\n\n" +
      accountText("Approve only a sign-in you started yourself."),
  );
  const result = await accountCall("POST", "/api/v1/account/signin/" + (yes ? "approve" : "deny"), { code: seen.code });
  toast(yes ? accountText("Website signed in") : accountText("Sign-in denied"));
  return result;
}

const accountIO = {
  kind: "app",
  status: accountStatus,
  call: accountCall,
  href: (tab) => "#/account/" + (tab === "signin" ? "" : tab),
  logHref: (l) => "#/combat-log/shared/" + encodeURIComponent(l.id),
  claimHref: "#/combat/identities",
  inviteLink: (token) => ACCOUNT_SITE + "account.html#a2invite=" + token,
  menuItems: [
    ["approve", accountText("Approve a website sign-in")],
    ["website", accountText("Open the website signed in")],
  ],
  menuAction(id) {
    if (id === "approve") approveWebsiteSignIn().catch((e) => toast(e.message));
    if (id === "website") api("/api/account", { action: "website" }).catch((e) => toast(e.message));
  },
  signout: () => api("/api/account", { action: "signout" }),
  onSignedOut() {
    if (location.hash.startsWith("#/account")) route();
  },
  onTab(tab) {
    history.replaceState(null, "", "#/account/" + tab);
  },
  onLegion(id) {
    history.replaceState(null, "", "#/account/legions" + (id ? "/" + id : ""));
  },
  renamed() {
    if (accountMenu) accountMenu.refresh();
  },
  closed() {
    if (accountMenu) accountMenu.refresh();
  },
  logTools: () =>
    `<button class="btn small" data-acct-sync title="${esc(accountText("The uploads and characters this app holds"))}">${esc(accountText("Add this app's uploads"))}</button>`,
  afterLogs(el, render) {
    const b = el.querySelector("[data-acct-sync]");
    if (b)
      b.onclick = async () => {
        b.disabled = true;
        try {
          const r = await api("/api/account", { action: "sync" });
          toast(accountText("{0} logs and {1} characters added", r.logs, r.characters));
          render();
        } catch (e) {
          toast(e.message);
          b.disabled = false;
        }
      };
  },
  async security(el, me) {
    el.innerHTML = `<h3>${esc(accountText("Ways in"))}</h3>
      <div class="row"><button class="btn small primary" data-approve>${esc(accountText("Approve a website sign-in"))}</button>
        <button class="btn small" data-website>${esc(accountText("Open the website signed in"))}</button></div>
      <p class="small muted">${esc(accountText("On the website, choose Sign in → Approve in the app, then enter the code it shows here. Passkeys and Discord are added on the website (Sign-in & security there), and another computer's app joins with a code from the website."))}</p>
      <p>${esc(me.discord ? accountText("Discord: {0}", me.discord.name) : accountText("Discord: not linked"))} · ${esc(accountText((me.passkeys || 0) === 1 ? "{0} passkey" : "{0} passkeys", me.passkeys || 0))} · ${esc(accountText((me.apps || 0) === 1 ? "{0} desktop app" : "{0} desktop apps", me.apps || 0))}</p>`;
    el.querySelector("[data-approve]").onclick = () => approveWebsiteSignIn().catch((e) => toast(e.message));
    el.querySelector("[data-website]").onclick = () =>
      api("/api/account", { action: "website" }).catch((e) => toast(e.message));
  },
  signedOut(root, s, done) {
    const methods = (s.config && s.config.methods) || {};
    root.innerHTML = `<section class="win"><div class="wh"><h2>${esc(accountText("Account"))}</h2></div><div class="wb">
      ${s.ended ? `<div class="note">${esc(s.ended)}</div>` : ""}
      ${s.elsewhere ? `<div class="note">${esc(accountText("This app is signed in on {0}, not on the server Settings uses now ({1}).", s.elsewhere, s.server || "—"))} <button class="btn small" data-out>${esc(accountText("Sign out"))}</button></div>` : ""}
      ${!s.server ? `<div class="note">${esc(accountText("Choose a log server in Settings first."))}</div>` : s.error && !s.config ? `<div class="note">${esc(s.error)}</div>` : ""}
      <p>${esc(accountText("An account is optional. With one, your uploads from this app and the ones it made before are in one place, on the website too, under your name; you can share logs with your legion and see theirs."))}</p>
      <p class="small muted">${esc(accountText("There is no password: this app stays signed in, and it approves your sign-ins on the website."))}</p>
      <div class="row"><input data-name maxlength="24" placeholder="${esc(accountText("Your name (optional)"))}" aria-label="${esc(accountText("Your name"))}">
        <button class="btn primary" data-register ${s.elsewhere || !s.server || !s.config ? "disabled" : ""}>${esc(accountText("Create my account"))}</button></div>
      <details class="note"><summary><b>${esc(accountText("I already have an account"))}</b></summary>
        ${methods.discord ? `<div class="row"><button class="btn small" data-discord>${esc(accountText("Sign in with Discord"))}</button><span class="small muted">${esc(accountText("if you linked Discord on the website"))}</span></div>` : ""}
        <div class="row"><input data-code size="12" placeholder="ABCD-EFGH" aria-label="${esc(accountText("Link code"))}"><button class="btn small" data-link>${esc(accountText("Link with a code"))}</button>
          <span class="small muted">${esc(accountText("Website: Sign-in & security → Link another computer's app"))}</span></div>
        <div class="row"><button class="btn small" data-recover>${esc(accountText("Recover with my uploads"))}</button>
          <span class="small muted">${esc(accountText("Uses the private credentials of three of the account's uploads (your ownership backup)"))}</span></div>
      </details><div data-out-msg role="status"></div></div></section>`;
    const say = (text) => (root.querySelector("[data-out-msg]").textContent = text);
    const signedIn = (r) => {
      toast(accountText("Signed in as {0}", (r.account || {}).name || ""));
      if (accountMenu) accountMenu.refresh();
      done();
    };
    const run = async (button, work) => {
      button.disabled = true;
      try {
        signedIn(await work());
      } catch (e) {
        say(e.message);
        button.disabled = false;
      }
    };
    root.querySelector("[data-register]").onclick = (ev) =>
      run(ev.currentTarget, () =>
        api("/api/account", { action: "register", name: root.querySelector("[data-name]").value.trim() }),
      );
    root.querySelector("[data-link]").onclick = (ev) =>
      run(ev.currentTarget, () =>
        api("/api/account", { action: "link", code: root.querySelector("[data-code]").value }),
      );
    root.querySelector("[data-recover]").onclick = (ev) =>
      run(ev.currentTarget, () => api("/api/account", { action: "recover" }));
    const out = root.querySelector("[data-out]");
    if (out)
      out.onclick = async () => {
        await api("/api/account", { action: "signout" }).catch(() => {});
        if (accountMenu) accountMenu.refresh();
        done();
      };
    const discord = root.querySelector("[data-discord]");
    if (discord)
      discord.onclick = async () => {
        discord.disabled = true;
        try {
          const started = await api("/api/account", { action: "discord-start" });
          say(accountText("Finish signing in with Discord in your browser…"));
          const deadline = Date.now() + 10 * 60 * 1000;
          while (Date.now() < deadline && root.isConnected) {
            await new Promise((r) => setTimeout(r, started.interval * 1000));
            const r = await api("/api/account", { action: "discord-poll" });
            if (r.status === "approved") return signedIn(r);
            if (r.status !== "pending") throw new Error(accountText("The Discord sign-in ended. Try again."));
          }
        } catch (e) {
          say(e.message);
        }
        discord.disabled = false;
      };
  },
};

async function pageAccount() {
  const parts = location.hash.replace(/^#\//, "").split("?")[0].split("/");
  const tab = ["logs", "legions", "security"].includes(parts[1]) ? parts[1] : "logs";
  const legion = tab === "legions" && /^lg_[0-9a-f]{12}$/.test(parts[2] || "") ? parts[2] : null;
  app().innerHTML = '<div id="account-root"></div>';
  accountView = A2Account.mount($("#account-root"), accountIO, { tab, legion });
}

accountMenu = A2Account.menu($("#account-menu"), accountIO);
