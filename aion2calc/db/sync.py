"""Launch-time database sync: discover new and changed game data, no hard-coded lists.

How it finds things
    * metabot.gg sitemaps list every class, skill, item, title and wing page with
      a last-modified date; a page is fetched again only when that date moves.
    * the equipment universe is whatever metabot's category pages list
      (weapons, armor, accessories, arcana, theostones), so new items appear
      automatically.
    * classes are discovered from the sitemap, so a new class shows up too.

What it writes
    * items into the SQLite catalog (``db/store.py``)
    * class data, titles, arcana pools, the compact item reference and median
      loadouts into the user data overlay (``paths.py``), which every reader
      prefers over the bundled copies.

The sync is resumable and time-boxed (``budget_s``): whatever is not done in
one launch continues on the next.  ``python -m aion2calc sync`` runs it by hand.
"""
from __future__ import annotations

import re
import threading
import time
import traceback
from dataclasses import dataclass, field

from ..kit.base import valid_base_stats
from ..paths import read_json, write_user_json
from ..scrape import metabot
from ..scrape.http import NotFound
from . import store

EQUIP_CATEGORIES = ("weapons", "armor", "accessories", "arcana", "godstones")
CLASS_MAX_AGE = 86400          # re-read class pages at most daily unless the sitemap moved
SITEMAPS = ("aion-2", "aion-2-items-1", "aion-2-collections")


@dataclass
class SyncState:
    phase: str = "idle"
    done: int = 0
    total: int = 0
    message: str = ""
    started: float = 0.0
    finished: float = 0.0
    running: bool = False
    errors: list = field(default_factory=list)
    changed: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class Sync:
    def __init__(self, force: bool = False, budget_s: float | None = None, delay: float = 0.25,
                 log=None, db_path=None):
        self.force = force
        self.budget_s = budget_s
        self.delay = delay
        self.log = log or (lambda msg: None)
        self.db_path = db_path
        self.state = SyncState()

    # ----------------------------------------------------------------- utils
    def _say(self, phase: str, msg: str = "", done: int | None = None, total: int | None = None):
        self.state.phase = phase
        self.state.message = msg
        if done is not None:
            self.state.done = done
        if total is not None:
            self.state.total = total
        self.log(f"[sync] {phase}: {msg}")

    def _out_of_time(self) -> bool:
        return bool(self.budget_s) and time.time() - self.state.started > self.budget_s

    # ------------------------------------------------------------------- run
    def run(self) -> SyncState:
        st = self.state
        st.running, st.started, st.errors, st.changed = True, time.time(), [], {}
        conn = None
        try:
            conn = store.connect(self.db_path)
            pages = self._sitemaps(conn)
            changed_classes = self._classes(conn, pages)
            changed_items = self._items(conn, pages)
            self._collections(conn, pages, changed_items)
            if changed_classes:
                self._say("loadouts", f"regenerating median loadouts for {len(changed_classes)} classes")
                from ..loadouts import make_all
                try:
                    make_all(changed_classes, user=True, verbose=False)
                except Exception as err:  # loadouts are derived data; keep the old ones
                    st.errors.append(f"loadouts: {err}")
            from ..kit.base import clear_caches
            clear_caches()
            store.set_meta(conn, "last_sync", {"at": time.time(), "changed": st.changed,
                                               "complete": not self._out_of_time()})
            self._say("done", "complete" if not self._out_of_time() else "time budget reached; resumes next launch")
        except Exception as err:  # never crash the app because a site changed
            st.errors.append(f"{type(err).__name__}: {err}")
            self.log(traceback.format_exc())
            self._say("error", str(err))
        finally:
            # A failed phase must never leave a cached connection holding a writer lock.
            if conn is not None and conn.in_transaction:
                conn.rollback()
            st.running, st.finished = False, time.time()
        return st

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.run, name="aion2calc-sync", daemon=True)
        t.start()
        return t

    # -------------------------------------------------------------- phases
    def _sitemaps(self, conn) -> dict[str, str]:
        self._say("sitemaps", "reading metabot sitemaps")
        pages: dict[str, str] = {}
        for name in SITEMAPS:
            try:
                pages.update(metabot.sitemap(name))
            except Exception as err:
                self.state.errors.append(f"sitemap {name}: {err}")
        for url, lastmod in pages.items():
            kind, _, slug = url.split("/en/aion-2/")[-1].partition("/")
            conn.execute("INSERT INTO pages(url, kind, slug, lastmod) VALUES (?,?,?,?) "
                         "ON CONFLICT(url) DO UPDATE SET lastmod=excluded.lastmod", (url, kind, slug, lastmod))
        conn.commit()
        self.state.changed["pages_known"] = len(pages)
        return pages

    def _fetched_lastmod(self, conn, url: str):
        row = conn.execute("SELECT fetched_lastmod, fetched_at FROM pages WHERE url=?", (url,)).fetchone()
        return (row[0], row[1] or 0) if row else (None, 0)

    def _mark(self, conn, url: str, lastmod: str | None, status: str = "ok"):
        # Commit before another page is fetched: network requests can take minutes.
        with conn:
            conn.execute("INSERT INTO pages(url, fetched_lastmod, fetched_at, status) VALUES (?,?,?,?) "
                         "ON CONFLICT(url) DO UPDATE SET fetched_lastmod=excluded.fetched_lastmod, "
                         "fetched_at=excluded.fetched_at, status=excluded.status",
                         (url, lastmod, time.time(), status))

    def _classes(self, conn, pages: dict[str, str]) -> list[str]:
        urls = {u: m for u, m in pages.items() if re.fullmatch(r".*/en/aion-2/classes/[a-z]+", u)}
        found = sorted(u.rsplit("/", 1)[-1] for u in urls) or list(metabot.CLASSES)
        changed = []
        self._say("classes", f"{len(found)} classes", 0, len(found))
        for i, cls in enumerate(found):
            url = f"{metabot.BASE}/classes/{cls}"
            lastmod = urls.get(url)
            seen, at = self._fetched_lastmod(conn, url)
            stale = time.time() - at > CLASS_MAX_AGE
            if not (self.force or seen != lastmod or stale):
                continue
            if self._out_of_time():
                break
            self._say("classes", f"reading {cls}", i, len(found))
            try:
                data = metabot.class_data(cls, fresh=True)
                if len(data.get("skills", [])) < 10 or len(data.get("boards", [])) < 4:
                    raise ValueError("page layout changed (too few skills or boards); keeping old data")
                if not valid_base_stats(data.get("base_stats"), data.get("level_cap", 45)):
                    raise ValueError("incomplete base-stat table; keeping previous class data")
                write_user_json(data, "global", "classes", f"{cls}.json")
                self._mark(conn, url, lastmod)
                changed.append(cls)
            except Exception as err:
                self.state.errors.append(f"class {cls}: {err}")
        conn.commit()
        self.state.changed["classes"] = changed
        return changed

    def _items(self, conn, pages: dict[str, str]) -> list[str]:
        slugs: set[str] = set()
        for cat in EQUIP_CATEGORIES:
            try:
                slugs |= set(metabot.category_slugs(cat))
            except Exception as err:
                self.state.errors.append(f"category {cat}: {err}")
        have = {r[0]: r[1] for r in conn.execute("SELECT slug, lastmod FROM items")}
        todo = []
        for slug in sorted(slugs):
            lastmod = pages.get(f"{metabot.BASE}/items/{slug}")
            if self.force or slug not in have or (lastmod and have[slug] != lastmod):
                todo.append((slug, lastmod))
        self._say("items", f"{len(todo)} new or changed of {len(slugs)}", 0, len(todo))
        changed = []
        for i, (slug, lastmod) in enumerate(todo):
            if self._out_of_time():
                break
            try:
                it = metabot.item_full(slug, cache=False)
                with conn:
                    store.upsert_item(conn, it, lastmod)
                changed.append(slug)
            except NotFound:
                pass
            except Exception as err:
                self.state.errors.append(f"item {slug}: {err}")
            self._say("items", slug, i + 1, len(todo))
        conn.commit()
        self.state.changed["items"] = len(changed)
        self.state.changed["items_total"] = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        return changed

    def _collections(self, conn, pages: dict[str, str], changed_items: list[str]) -> None:
        # arcana pools come straight from the catalog: no extra requests
        if any(re.match(r"(%s)-of-" % "|".join(metabot.ARCANA_SLOTS), s) for s in changed_items) or self.force:
            pools = {}
            for r in conn.execute("SELECT slug, data FROM items WHERE category IN "
                                  "('Chalice','Parchment','Compass','Bell','Mirror')"):
                if re.fullmatch(r"(%s)-of-[a-z]+" % "|".join(metabot.ARCANA_SLOTS), r[0]):
                    import json
                    p = json.loads(r[1]).get("skill_pools")
                    if p:
                        pools[r[0]] = p
            if pools:
                write_user_json(pools, "global", "arcana_skill_pools.json")
                self.state.changed["arcana_pools"] = len(pools)
        # compact reference used by the gear advice: refresh from the catalog
        if changed_items:
            import json
            ref = read_json("global", "items.json")
            for slug in list(ref):
                row = conn.execute("SELECT data FROM items WHERE slug=?", (slug,)).fetchone()
                if row:
                    d = json.loads(row[0])
                    ref[slug] = {k: d.get(k) for k in ("slug", "fixed", "random", "enchant", "meta")}
            write_user_json(ref, "global", "items.json")
        # titles: one listing page, refetched when its sitemap entry moves
        url = f"{metabot.BASE}/titles"
        lastmod = pages.get(url)
        seen, at = self._fetched_lastmod(conn, url)
        if self.force or seen != lastmod or time.time() - at > 7 * 86400:
            try:
                titles = metabot.titles(fresh=True)
                if len(titles) > 50:
                    old = {t["name"]: t for t in read_json("global", "titles.json")}
                    for t in titles:                     # keep the per-title details already known
                        for k in ("slug", "slot", "role", "category", "how", "earn", "source"):
                            if k in old.get(t["name"], {}):
                                t.setdefault(k, old[t["name"]][k])
                    write_user_json(titles, "global", "titles.json")
                    self._mark(conn, url, lastmod)
                    self.state.changed["titles"] = len(titles)
            except Exception as err:
                self.state.errors.append(f"titles: {err}")
        self._title_details(conn, pages)
        conn.commit()

    def _title_details(self, conn, pages: dict[str, str]) -> None:
        """Equip slot and how-to-earn of titles that are new or whose page changed."""
        import re as _re
        titles = read_json("global", "titles.json")
        urls = {u.rsplit("/", 1)[1]: (u, m) for u, m in pages.items() if "/titles/" in u}
        n = 0
        for t in titles:
            if self._out_of_time():
                break
            slug = t.get("slug") or _re.sub(r"[^a-z0-9]+", "-", t["name"].lower().replace("'", "")).strip("-")
            if slug not in urls:
                continue
            url, lastmod = urls[slug]
            seen, _ = self._fetched_lastmod(conn, url)
            if t.get("slot") and seen == lastmod and not self.force:
                continue
            if t.get("slot") and seen is None and not self.force:
                self._mark(conn, url, lastmod)           # details came with the bundled data
                continue
            try:
                d = metabot.title_detail(slug, cache=False)
                t.update({k: v for k, v in d.items() if k in ("slug", "slot", "role", "category", "how", "earn",
                                                              "source")})
                self._mark(conn, url, lastmod)
                n += 1
            except Exception as err:
                self.state.errors.append(f"title {slug}: {err}")
        if n:
            write_user_json(titles, "global", "titles.json")
            self.state.changed["title_details"] = n


def status(db_path=None) -> dict:
    conn = store.connect(db_path)
    return {"last_sync": store.get_meta(conn, "last_sync"),
            "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "categories": store.categories(conn)[:30],
            "characters": conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0],
            "encounters": conn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]}
