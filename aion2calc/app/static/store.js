/* The interfaces' own data (0.2.482): what a page keeps in its browser's storage, the app keeps in its data folder
   (interface.json), where the native window finds it too. The app gives its data with the page itself
   (window.A2STORE), and this script, the page's first, puts it in the browser's storage before any other script
   reads it; then each change a page makes to its storage goes to the app.
   The first time a browser opens the app, what it kept before goes to the app, where the app has none of it; once
   the app has said it kept it, the browser is marked (a2-store-browser), and from then on the app's data is the
   whole of it: what the browser still holds that the app no longer has goes.
   A change the app has not yet said it kept stays in the browser's own list (a2-store-pending), and is put back and
   sent again as the next page opens, unless the data that page was given has it. So a page that reloads at once (a
   new language) and is given the app's data a moment before the app has the change loses nothing; nor does a change
   made while the app was not answering. A page that is leaving does not take a change off the list, as the page
   that comes next may have been given the app's data before the app had it.
   A message between the browser's windows (aion2calc-closing) stays in the browser, as do its mark and its list. */
(function () {
  "use strict";
  const given = window.A2STORE;
  if (!given || typeof given !== "object") return; // a page the app served without its data (another computer)
  const MARK = "a2-store-browser",
    PENDING = "a2-store-pending";
  let storage, marked;
  try {
    storage = window.localStorage;
    marked = storage.getItem(MARK) !== null;
  } catch (e) {
    return; // no storage in this browser: the pages keep nothing
  }
  const LOCAL = new Set(["aion2calc-closing", MARK, PENDING]);
  const proto = Storage.prototype;
  const setItem = proto.setItem,
    removeItem = proto.removeItem,
    clear = proto.clear;
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  let leaving = false;
  window.addEventListener("beforeunload", () => (leaving = true));
  window.addEventListener("pagehide", () => (leaving = true));
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) leaving = false; // back from the browser's page cache
  });

  // the changes the app has not said it kept, by key (null: forgotten), shared by the browser's windows
  function unconfirmed() {
    try {
      const list = JSON.parse(storage.getItem(PENDING) || "{}");
      return list && typeof list === "object" && !Array.isArray(list) ? list : {};
    } catch (e) {
      return {};
    }
  }
  function remember(list) {
    try {
      if (Object.keys(list).length) setItem.call(storage, PENDING, JSON.stringify(list));
      else removeItem.call(storage, PENDING);
    } catch (e) {
      /* a full storage: the change still goes to the app */
    }
  }
  function settle(isKept) {
    const list = unconfirmed();
    let changed = false;
    for (const [key, value] of Object.entries(list)) {
      if (isKept(key, value)) {
        delete list[key];
        changed = true;
      }
    }
    if (changed) remember(list);
    return list;
  }

  // The changes go to the app one request after another; those made while a request is on its way go together in
  // the next (a slider dragged changes its value at each step, and the app writes its file for each request).
  let batch = null,
    outbox = {},
    marking = false,
    busy = false;
  function flush() {
    const changes = batch;
    batch = null;
    remember(Object.assign(unconfirmed(), changes)); // before the page can go: a reload comes after this
    Object.assign(outbox, changes);
    if (!busy) post();
  }
  function post() {
    const changes = outbox,
      mark = marking;
    if (!Object.keys(changes).length) {
      busy = false;
      return;
    }
    outbox = {};
    marking = false;
    busy = true;
    const body = JSON.stringify({ set: changes });
    fetch("/api/interface", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: body.length < 60000, // sent even as the page closes, when small enough to be
    })
      .then(
        (answer) => {
          if (!answer.ok || leaving) return; // refused, or the next page settles it
          settle((key, value) => own(changes, key) && changes[key] === value); // unless it changed again since
          if (mark) setItem.call(storage, MARK, "1");
        },
        () => {}, // no answer: sent again as the next page opens
      )
      .then(post);
  }
  function keep(key, value) {
    if (LOCAL.has(key)) return;
    if (!batch) {
      batch = {};
      queueMicrotask(flush);
    }
    batch[key] = value;
  }

  // what the page was given already has, the app kept; what it has not, the browser puts back and sends again
  const waiting = settle((key, value) => {
    if (LOCAL.has(key) || (value !== null && typeof value !== "string")) return true; // never a page's data
    return value === null ? !own(given, key) : given[key] === value;
  });
  const keys = () => Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter((k) => k !== null);
  if (!marked) {
    let giving = false;
    for (const key of keys()) {
      if (!LOCAL.has(key) && !own(given, key) && !own(waiting, key)) {
        keep(key, storage.getItem(key));
        giving = true;
      }
    }
    if (giving) marking = true;
    else setItem.call(storage, MARK, "1"); // nothing of its own to give
  } else {
    for (const key of keys()) if (!LOCAL.has(key) && !own(given, key) && !own(waiting, key)) removeItem.call(storage, key);
  }
  for (const [key, value] of Object.entries(given)) {
    if (typeof value === "string" && !own(waiting, key) && storage.getItem(key) !== value) setItem.call(storage, key, value);
  }
  for (const [key, value] of Object.entries(waiting)) {
    if (value === null) removeItem.call(storage, key);
    else if (storage.getItem(key) !== value) setItem.call(storage, key, value);
    keep(key, value);
  }

  proto.setItem = function (key, value) {
    setItem.call(this, key, value);
    if (this === storage) keep(String(key), String(value));
  };
  proto.removeItem = function (key) {
    removeItem.call(this, key);
    if (this === storage) keep(String(key), null);
  };
  proto.clear = function () {
    if (this !== storage) return clear.call(this);
    const gone = keys(),
      list = unconfirmed(),
      wasMarked = storage.getItem(MARK) !== null;
    clear.call(this);
    if (wasMarked) setItem.call(storage, MARK, "1");
    remember(list);
    for (const key of gone) keep(key, null);
  };
})();
