/* Gathering (gathering.html): everyone's drop rates from the log server and, signed in, the account's own records
   (the website's session, account.js); static/gathering.js draws both. It starts once every script of the page
   has run: account.js, which keeps the session, comes after this one. */
(function () {
  "use strict";
  function start() {
    A2Gathering.mount(document.getElementById("gathering"), {
      mineLabel: "Your account",
      signedOut:
        '<p class="muted gt-signin">Sign in (top right) with the account your desktop app is signed in to, and what you gathered and took from reward cubes shows here.</p>',
      mine: async () => {
        await A2.ensure();
        if (!window.A2Session || !A2Session.token(A2Session.base())) return null;
        try {
          return await A2Session.call("GET", "/api/v1/account/gathering");
        } catch (e) {
          if (e.signedOut) return null;
          throw e;
        }
      },
      community: () => A2.api("/api/v1/gathering/stats"),
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
