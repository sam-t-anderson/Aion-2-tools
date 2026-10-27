/* Reading the game's screen into the app, for Gear & Advice and My Character: the Genus Insight panel or a page of
   the Title window, read by the text recognition built into Windows (aion2calc/screenread), for the player to check
   and save. Nothing is saved to a character here. */
"use strict";

// The newest read each kind of panel has taken in this session of the app: a hotkey read made while the app was in
// the background is taken once, by the first panel of its kind the player opens.
const screenReadsTaken = { genus: 0, titles: 0 };

function screenReadText(record) {
  if (record.kind === "genus") {
    const checks = (record.lines || []).filter((line) => line.check).length;
    return `Read ${esc(record.genus)} Insight${record.level ? " Lv " + esc(record.level) : " (the level was not read)"}: ${record.lines.length} line${record.lines.length === 1 ? "" : "s"}${checks ? `, ${checks} to check` : ""}.`;
  }
  if (record.kind === "titles") {
    const box =
      record.unacquired_only === true ? "ticked" : record.unacquired_only === false ? "not ticked" : "not seen";
    return `Read a page of the Title window: ${record.titles.length} title${record.titles.length === 1 ? "" : "s"}, “Show unacquired titles only” ${box}.`;
  }
  const seen = record.seen?.length
    ? `<details><summary>What was read</summary><pre class="small">${esc(record.seen.join("\n"))}</pre></details>`
    : "";
  return esc(record.error || (record.notes || [])[0] || "Nothing was recognised on the screen.") + seen;
}

// A row of ways to read the game into the page: the game screen after a countdown (time to switch to the game), a
// screenshot chosen or pasted (Ctrl+V on the row), and the Read the game screen hotkey pressed in the game, whose
// reads the row picks up while its page is open. `onRead(record)` gets each read of `kind` ("genus" or "titles").
function screenReadPanel(host, { kind, onRead }) {
  const what = kind === "genus" ? "the Genus Insight panel" : "a page of the Title window";
  host.innerHTML = `<div class="screen-read" tabindex="0" aria-label="Read ${what} from the game. Paste a screenshot here.">
    <div class="row"><b class="small">Read from the game</b><button type="button" class="btn small" data-sr-screen>Read the game screen</button>
    <label class="btn small">Choose a screenshot…<input type="file" accept="image/png,image/jpeg,image/bmp,image/webp" data-sr-file hidden></label></div>
    <p class="small muted">Open ${what} in the game, press <b>Read the game screen</b> and switch to the game within 3 seconds, or press the <b>Read the game screen</b> hotkey in the game (Settings → Hotkeys). A screenshot works too: choose it, or click this box and paste it (Ctrl+V).</p>
    <p class="small" role="status" aria-live="polite" data-sr-status></p></div>`;
  const box = host.firstElementChild,
    other = kind === "genus" ? "titles" : "genus",
    taken = new Set(),
    opened = Date.now();
  const status = (html) => {
    const line = box.querySelector("[data-sr-status]");
    if (line) line.innerHTML = html;
  };
  const take = (record) => {
    if (taken.has(record.id)) return;
    taken.add(record.id);
    if (record.kind === kind) {
      screenReadsTaken[kind] = Math.max(screenReadsTaken[kind], record.id);
      onRead(record);
      status(screenReadText(record));
    } else if (record.kind === other)
      status(
        other === "titles"
          ? "That is a page of the Title window: it is listed under <b>Titles you own</b> on Gear &amp; Advice."
          : "That is the Genus Insight panel: read it under <b>Genus Insight</b>.",
      );
    else status(screenReadText(record));
  };
  const send = async (body, waiting) => {
    status(waiting);
    try {
      take(await api("/api/screen-read", body));
    } catch (e) {
      status(esc("Not read: " + e.message));
    }
  };
  const readFile = (file) => {
    if (!file) return;
    if (file.size > 24 * 1024 * 1024) return status("That screenshot is larger than 24 MB.");
    const reader = new FileReader();
    reader.onload = () => send({ action: "image", image: reader.result }, "Reading the screenshot…");
    reader.onerror = () => status("The screenshot could not be opened.");
    reader.readAsDataURL(file);
  };
  const button = box.querySelector("[data-sr-screen]"),
    file = box.querySelector("[data-sr-file]");
  button.onclick = async () => {
    button.disabled = true;
    let left = 3;
    const say = () => status(left > 0 ? `Reading in ${left}… switch to the game now.` : "Reading…");
    say();
    const timer = setInterval(() => {
      left -= 1;
      say();
      if (left <= 0) clearInterval(timer);
    }, 1000);
    try {
      await send({ action: "read", delay: 3 }, `Reading in ${left}… switch to the game now.`);
    } finally {
      clearInterval(timer);
      button.disabled = false;
    }
  };
  file.onchange = () => {
    const chosen = file.files?.[0];
    file.value = "";
    readFile(chosen);
  };
  box.addEventListener("paste", (ev) => {
    const item = [...(ev.clipboardData?.items || [])].find((i) => i.kind === "file" && i.type.startsWith("image/"));
    if (!item) return;
    ev.preventDefault();
    readFile(item.getAsFile());
  });
  // The hotkey's reads: each new one of this kind, and a failed one pressed since the page opened.
  let poller = 0;
  const poll = async () => {
    if (!box.isConnected) return clearInterval(poller);
    let state;
    try {
      state = await api("/api/screen-read?since=" + screenReadsTaken[kind]);
    } catch (e) {
      return;
    }
    if (!box.isConnected) return clearInterval(poller);
    if (!state.available) {
      clearInterval(poller);
      button.disabled = file.disabled = true;
      return status(esc(state.message));
    }
    for (const record of state.reads) {
      if (record.kind === kind || (record.kind == null && record.source === "hotkey" && record.at * 1000 >= opened))
        take(record);
      screenReadsTaken[kind] = Math.max(screenReadsTaken[kind], record.id);
    }
  };
  poll();
  poller = setInterval(poll, 2000);
}

// Gear & Advice → Titles you own: the Title window pages read so far, whether each was read with "Show unacquired
// titles only" ticked (correctable), and the titles they say the character owns, which go into the list only when
// the player puts them there (and are saved with Save titles).
function titleReadSummary(host, characterKey, list) {
  const draw = (t) => {
    if (!host.isConnected) return;
    if (t.error) return (host.innerHTML = `<p class="small">${esc(t.error)}</p>`);
    const notes = t.notes.map((n) => `<p class="small muted">${esc(n)}</p>`).join("");
    if (!t.pages.length) return (host.innerHTML = notes);
    const choice = (p, value, label) =>
      `<option value="${value}" ${String(p.unacquired_only ?? "") === value ? "selected" : ""}>${label}</option>`;
    host.innerHTML = `<table class="t"><tr><th>Page</th><th>Read at</th><th>Titles</th><th>“Show unacquired titles only”</th><th><span class="sr-only">Actions</span></th></tr>
      ${t.pages
        .map(
          (p, i) =>
            `<tr><td>${i + 1}</td><td class="small">${esc(clockAt(p.at * 1000))}</td><td title="${esc(p.titles.join(", "))}">${p.titles.length}</td>
          <td><select data-tpage="${p.id}" aria-label="Page ${i + 1}: was Show unacquired titles only ticked?">${choice(p, "true", "ticked")}${choice(p, "false", "not ticked")}${choice(p, "", "not seen: choose")}</select></td>
          <td class="r"><button class="btn small" data-tforget="${p.id}">Forget</button></td></tr>`,
        )
        .join("")}</table>
      <p class="small">Not acquired yet: <b>${t.unacquired.length}</b> · ${t.basis ? `you own: <b>${t.owned.length}</b>` : "the titles you own are not worked out yet"}${t.faction ? ` · ${esc(cap(t.faction))}: ${t.faction_titles} titles in the app's catalog` : ""}${t.collection ? ` · the game counts ${t.collection.owned} of ${t.collection.total}` : ""}</p>${notes}
      ${t.owned.length ? `<details><summary>The titles you own (${t.owned.length})</summary><p class="small">${esc(t.owned.join(" · "))}</p></details>` : ""}
      ${t.unacquired.length ? `<details><summary>Not acquired yet (${t.unacquired.length})</summary><p class="small">${esc(t.unacquired.join(" · "))}</p></details>` : ""}
      <div class="row">${t.owned.length ? '<button class="btn small" data-tuse>Put these in the list</button><button class="btn small" data-tadd>Add them to the list</button>' : ""}<button class="btn small" data-tclear>Start over</button></div>`;
    const change = (body) =>
      api("/api/screen-read", { ...body, character: characterKey })
        .then(draw)
        .catch((e) => toast("Not changed: " + e.message));
    host.querySelectorAll("[data-tpage]").forEach(
      (s) =>
        (s.onchange = () =>
          change({
            action: "page",
            page: +s.dataset.tpage,
            unacquired_only: s.value === "" ? null : s.value === "true",
          })),
    );
    host
      .querySelectorAll("[data-tforget]")
      .forEach((b) => (b.onclick = () => change({ action: "forget-page", page: +b.dataset.tforget })));
    host.querySelector("[data-tclear]").onclick = () => change({ action: "clear-titles" });
    const fill = (names) => {
      list.value = names.join("\n");
      list.dispatchEvent(new Event("input"));
      toast("The list is filled in: check it, then press Save titles.");
    };
    const use = host.querySelector("[data-tuse]"),
      add = host.querySelector("[data-tadd]");
    if (use) use.onclick = () => fill(t.owned);
    if (add)
      add.onclick = () => {
        const have = list.value
          .split("\n")
          .map((x) => x.trim())
          .filter(Boolean);
        fill([...have, ...t.owned.filter((name) => !have.includes(name))]);
      };
  };
  const refresh = () =>
    api("/api/screen-read/titles?character=" + encodeURIComponent(characterKey))
      .then(draw)
      .catch((e) => draw({ error: "The pages read could not be shown: " + e.message }));
  refresh();
  return { refresh };
}
