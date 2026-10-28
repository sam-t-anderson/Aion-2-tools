/* What's new after an update (0.2.353): the release notes this app has not shown yet, in a dialog on the first
   launch of a new version, once. Closing it tells the app, which then never shows them again; Settings opens this
   version's notes on request and links to every version's on GitHub. The notes come as HTML the app drew from
   the changelog it carries. */
(function () {
  "use strict";
  const esc = (x) =>
    String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const t = (text, ...values) =>
    window.A2I18n ? window.A2I18n.t(text, ...values) : text.replace(/\{(\d)\}/g, (m, i) => values[i] ?? m);

  // One modal dialog: each version's notes, newest first, then the link to all of them and Close. Escape, Close
  // and a click outside it close it; onClose runs once it is closed.
  function open(data, onClose) {
    document.querySelector("#patch-notes")?.remove();
    const dialog = document.createElement("dialog");
    dialog.id = "patch-notes";
    dialog.className = "patch-notes";
    dialog.setAttribute("aria-labelledby", "patch-notes-title");
    dialog.innerHTML =
      `<h2 id="patch-notes-title">${esc(t("What's new in Aion 2 Calc {0}", data.version))}</h2>` +
      `<div class="pn-body">${data.notes
        .map((n) => `<section><h3>${esc(n.title)} <span class="pn-version">${esc(n.version)}</span></h3>${n.html}</section>`)
        .join("")}</div>` +
      `<div class="pn-foot"><a href="${esc(data.all)}" target="_blank" rel="noopener">All patch notes on GitHub</a>` +
      `<button class="btn" type="button" data-close>Close</button></div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("[data-close]").onclick = () => dialog.close();
    dialog.addEventListener("click", (e) => {
      const r = dialog.getBoundingClientRect();
      if (e.target === dialog && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom))
        dialog.close(); // the backdrop
    });
    dialog.addEventListener("close", () => {
      dialog.remove();
      if (onClose) onClose();
    });
    dialog.showModal();
    dialog.querySelector("[data-close]").focus();
  }

  // At launch: the notes, once after an update; closing them records it on this computer.
  async function check(api) {
    let data;
    try {
      data = await api("/api/patch-notes");
    } catch (e) {
      return; // no notes to show
    }
    if (data.show && data.notes.length) open(data, () => api("/api/patch-notes", { action: "seen" }).catch(() => {}));
  }

  // Settings' What's new: this version's notes, whatever was seen.
  async function show(api) {
    const data = await api("/api/patch-notes?force=1");
    if (!data.notes.length) throw new Error("This copy of the app does not hold this version's notes.");
    open(data);
  }

  window.A2PatchNotes = { check, show };
})();
