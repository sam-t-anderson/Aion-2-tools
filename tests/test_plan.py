"""Gear / arcana / pantheon / genus planners, learning from fights, and the log server.

No network: catalog items are written into a temporary database.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.db import store
    monkeypatch.setattr(store, "SEED", tmp_path / "no-seed.json.gz")
    store._local.__dict__.clear()
    yield tmp_path / "home"
    store._local.__dict__.clear()
    from aion2calc import learn
    learn.reset()


RING = {"slug": "test-ring", "name": "Test Ring", "grade": "Unique", "category": "Ring", "item_level": 70,
        "fixed": {"Attack": "+100"}, "description": "rolls 2 random stats on top of its fixed stats",
        "random": [{"stat": "Critical Hit", "range": "+30 – +50", "chance": "50%"},
                   {"stat": "HP", "range": "+200 – +300", "chance": "50%"}],
        "enchant": [{"step": "+0 → +1", "stats": "Attack +5"}, {"step": "+1 → +2", "stats": "Attack +10"},
                    {"step": "+14 → +15", "stats": "Attack +80"}, {"step": "+15 → +16", "stats": "Attack +5, Damage Boost +0.5%"}],
        "meta": {"Category": "Ring", "Required Level": "45", "Max enhance": "+15 (+16)"}}
WEAK = {**RING, "slug": "weak-ring", "name": "Weak Ring", "fixed": {"Attack": "+10"}, "item_level": 40}
BOOK = {"slug": "test-book", "name": "Test Book", "grade": "Unique", "category": "Spellbook", "item_level": 45,
        "fixed": {"Max Attack": "206–229", "Critical Hit": "+100"}, "description": "rolls 0 random stats",
        "random": [{"stat": "Might", "range": "+15 – +15", "chance": "0%"}],
        "enchant": [{"step": "+9 → +10", "stats": "Max Attack 50"}], "meta": {"Class": "Sorcerer"}}


def _catalog(*items):
    from aion2calc.db import store
    conn = store.connect()
    for it in items:
        store.upsert_item(conn, it, "2026-10-01")
    conn.commit()


def test_item_stats_from_catalog_text():
    from aion2calc.plan import items as I
    st = I.item_stats(BOOK, 10)
    assert (st["weapon_min"], st["weapon_max"], st["crit"], st["might"]) == (256, 279, 100, 15)   # fixed sub-stats
    assert I.enchant_stats(RING, 2) == {"attack": 10}
    assert I.enchant_stats(RING, 16) == {"attack": 85, "amp_all": 0.005}                     # past +15 adds on
    exp = I.roll_stats(RING)                                         # 2 rolls x 50% Critical Hit (mid 40)
    assert abs(exp["crit"] - 40) < 1e-9 and "HP" not in exp
    good = I.roll_stats(RING, "good", lambda f: f.get("crit", 0))
    assert good == {"crit": 40.0}                                    # distinct stats only; HP is worth nothing
    assert I.fits(BOOK, "MainHand", "sorcerer") and not I.fits(BOOK, "MainHand", "ranger")
    assert I.slot_of_category("Ring", "sorcerer") == ["Ring1", "Ring2"]


def test_best_equip_and_goal_gear(home):
    from aion2calc.plan import inventory as INV
    from aion2calc.plan.context import PlanContext
    from aion2calc.plan.gear import best_equip, goal_gear, upgrade_path
    _catalog(RING, WEAK, BOOK)
    ctx = PlanContext.for_class("sorcerer")
    inv = {"profile": "t", "class": "sorcerer", "items": []}
    for slug in ("weak-ring", "weak-ring", "test-ring", "test-ring"):
        INV.add(inv, slug, 2)
    base = ctx.dps({})
    r = best_equip(ctx, inv)
    assert r["best_dps"] >= base
    names = {e["name"] for e in inv["items"] if e["id"] in (r["choice"].get("Ring1"), r["choice"].get("Ring2"))}
    assert names == {"Test Ring"}                                    # both ring slots take the strong ring
    g = goal_gear(ctx)
    assert g["slots"]["Ring1"]["best"][0]["name"] == "Test Ring"
    assert g["slots"]["Ring1"]["best"][0]["enchant"] == 15
    p = upgrade_path(ctx, g["slots"], steps=3, target="best")
    assert p["end_dps"] >= p["start_dps"] and all(s["gain"] > 0 for s in p["steps"])


def test_median_loadout_groups_scale_with_chosen_slots(home):
    from aion2calc.plan.context import PlanContext
    _catalog(RING)
    ctx = PlanContext.for_class("sorcerer")
    e = {"source": "inventory", "slug": "test-ring", "name": "Test Ring", "category": "Ring", "enchant": 0}
    lo = ctx.assemble({"Ring1": e})
    rings = next(c for c in lo["components"] if c["slot"] == "Rings x2")
    orig = next(c for c in ctx.loadout["components"] if c["slot"] == "Rings x2")
    assert abs(rings["stats"]["attack"] - orig["stats"]["attack"] / 2) < 1e-9     # half the median pair stays
    assert any(c["slot"] == "Ring1" for c in lo["components"])


def test_arcana_rolls_ideal_and_expected():
    from aion2calc.plan.arcana import _expected, _ideal
    values = {"A": [0.02, 0.04, 0.06, 0.08], "B": [0.01, 0.02, 0.03, 0.04], "C": [0.0, 0.0, 0.0, 0.0]}
    pool = {"A": 1.0, "B": 1.0, "C": 1.0}
    lv, gain = _ideal(pool, values, 9, 4)
    assert lv == {"A": 4, "B": 4, "C": 1} and abs(gain - 0.12) < 1e-9
    e = _expected(pool, values, 4, 4, samples=4000)
    assert 0.03 < e < 0.05                                           # 4 random rolls of a 3-skill pool


def test_genus_lines_and_content_mix(home):
    from aion2calc.paths import write_user_json
    from aion2calc.plan.genus import content_mix, line_stats
    from aion2calc.sources.monsters import parse_type
    write_user_json({"Big Boss": "Varian", "Other": "Cogni"}, "global", "monster_genus.json")
    mix = content_mix([{"boss": "Big Boss", "duration": 300}, {"boss": "Other", "duration": 100},
                       {"boss": "Training Scarecrow", "duration": 60}], fetch_missing=False)
    assert mix == {"Varian": 0.75, "Cogni": 0.25}
    assert line_stats("Varian Damage Boost", "4%", "Varian", mix) == {"amp_all": 0.04 * 0.75}
    assert line_stats("Cogni Attack", "8", "Cogni", mix) == {"attack": 8 * 0.25}
    assert line_stats("Varian Defense", "60", "Varian", mix) == {}
    assert line_stats("Critical Hit", "12", "Fera", mix) == {"crit": 12}
    assert parse_type("<div>Type</div><div>Varian</div>") == "Varian"


def test_pantheon_ranks_damage_deities(home):
    from aion2calc.plan.context import PlanContext
    from aion2calc.plan.pantheon import plan_pantheon
    p = plan_pantheon(PlanContext.for_class("sorcerer"))
    assert {r["deity"] for r in p["per_point"] if r["field"] is None} == {"Life [Yustiel]", "Destiny [Marchutan]",
                                                                          "Space [Israphel]"}
    assert p["per_point"][0]["gain_per_point"] > 0
    assert p["choices"][-1]["source"].startswith("Bracelet")


def test_learning_fit_is_bounded_and_applies(home):
    from aion2calc import learn
    from aion2calc.db import store
    from aion2calc.model import stats as S
    from aion2calc.sim import engine
    conn = store.connect()
    for i in range(3):
        store.put_observation(conn, i, 1, "sorcerer", "Me", {
            "player": "Me", "hits": 500, "crit_stat": 900.0, "crit_resist": 0.0,
            "observed": {"crit": 0.40, "double": 0.10, "perfect": 0.05, "multihit": 0.10, "cpm": 60, "idle": 3},
            "predicted": {"crit": 0.30, "double": 0.05, "perfect": 0.05, "multihit": 0.10, "cpm": 70},
            "skills": {"Hellfire": {"damage": 30000, "casts": 10, "kind": "active"}},
            "sim_skills": {"Hellfire": {"damage": 20000, "casts": 10}}})
    cal = learn.fit("sorcerer", conn)
    lo, hi = learn.BOUNDS["rate"]
    assert cal["active"] and 1 < cal["rates"]["double"] <= hi                 # 2x observed, shrunk and bounded
    assert abs(cal["rates"]["perfect"] - 1) < 1e-9
    assert 1 < cal["skills"]["Hellfire"] <= learn.BOUNDS["skill"][1]
    assert cal["crit_x0"] < S.CRIT_X0                                        # more crit than the curve predicts
    with learn.calibrated("sorcerer"):
        assert engine.SKILL_MULT["Hellfire"] == cal["skills"]["Hellfire"] and S.CALIBRATION["double"] > 1
    assert not engine.SKILL_MULT and S.CALIBRATION["double"] == 1.0           # restored afterwards
    assert cal["players"]["Me"]["fights"] == 3


# ------------------------------------------------------------------ log server
def _doc():
    return {"format": "a2log", "version": 1, "meta": {"source": "test", "title": "Boss fight"},
            "players": [{"id": "a", "name": "Sorc", "class": "Sorcerer", "specs": {"Hellfire": [2, 4]}},
                        {"id": "b", "name": "Tank", "class": "templar"}],
            "segments": [{"label": "Boss", "boss": "Boss", "duration": 20, "killed": True,
                          "hits": [{"t": i, "player": "a" if i % 2 else "b", "skill_id": 15060130 if i % 2 else 12010000,
                                    "skill": "Hellfire" if i % 2 else "Vicious Strike", "damage": 1000 + i,
                                    "crit": i % 3 == 0} for i in range(20)],
                          "buffs": [{"player": "a", "name": "Element Enhancement", "start": 0, "end": 10}]}]}


def test_a2log_validation_and_conversion():
    from aion2calc.combat.adapters import from_csv
    from aion2calc.logserver import format as F
    d = F.validate(_doc())
    assert d["players"][0]["class"] == "sorcerer" and d["players"][0]["specs"] == {"Hellfire": [2, 4]}
    for bad, msg in ((dict(_doc(), format="x"), "format"), (dict(_doc(), players=[]), "players"),
                     ({**_doc(), "segments": [{"duration": 5, "hits": [{"t": 0, "player": "zz", "damage": 1}]}]},
                      "player")):
        with pytest.raises(F.Invalid, match=msg):
            F.validate(bad)
    enc = F.to_encounter(d, "a")
    assert {h["skill_id"] for h in enc["hits"]} == {15060000}                # variant code -> class skill
    assert enc["specs"] == {"Hellfire": "2, 4"} and enc["buffs"][0]["uptime"] == 0.5
    csv = from_csv("t,skill,damage\n0,Hellfire,100\n5,Blaze,50", {"player": "Me", "class": "sorcerer"})
    back = F.validate(F.from_encounter(csv))
    assert back["players"][0]["name"] == "Me" and len(back["segments"][0]["hits"]) == 2


def test_log_server_upload_view_private_delete(tmp_path):
    from http.server import ThreadingHTTPServer

    from aion2calc.logserver import server as LS
    LS.CONFIG = LS.Config(str(tmp_path / "logs"), public_url="https://logs.test")
    _, key = LS.CONFIG.store.create_key("test")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), LS.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None, method=None, auth=None, raw=False):
        h = {"Content-Type": "application/json"}
        if auth:
            h["Authorization"] = "Bearer " + auth
        req = urllib.request.Request(base + path, None if body is None else json.dumps(body).encode(), h,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                return r.status, (data.decode() if raw else json.loads(data))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert call("/.well-known/a2log.json")[1]["upload_url"] == "https://logs.test/api/v1/logs"
        assert call("/schema/a2log-v1.json")[1]["properties"]["format"]["const"] == "a2log"
        assert call("/api/v1/logs", _doc())[0] == 401                         # a key is required
        code, bad = call("/api/v1/logs", {"format": "a2log"}, auth=key)
        assert code == 400 and "version" in bad["error"]
        code, up = call("/api/v1/logs?visibility=public", _doc(), auth=key)
        assert code == 201 and up["url"].startswith("https://logs.test/l/")
        lid = up["id"]
        s = call(f"/api/v1/logs/{lid}")[1]
        assert s["title"] == "Boss fight" and [p["name"] for p in s["segments"][0]["players"]] == ["Sorc", "Tank"]
        a = call(f"/api/v1/logs/{lid}/analysis?segment=0&player=a")[1]
        assert a["summary"]["hits"] == 10 and a["meta"]["class"] == "sorcerer"
        code, page = call(f"/l/{lid}", raw=True)
        assert code == 200 and "Boss fight" in page and "<script>" not in page.split("</head>")[0]
        assert call("/api/v1/logs")[1]["total"] == 1
        code, priv = call("/api/v1/logs?visibility=private", _doc(), auth=key)
        assert call(f"/api/v1/logs/{priv['id']}")[0] == 403
        assert call(f"/api/v1/logs/{priv['id']}?" + priv["url"].split("?")[1])[0] == 200
        assert call("/api/v1/logs")[1]["total"] == 1                          # private is not listed
        assert call(f"/api/v1/logs/{lid}?token=wrong", method="DELETE")[0] == 403
        assert call(f"/api/v1/logs/{lid}?token={up['delete_token']}", method="DELETE")[0] == 200
        assert call(f"/api/v1/logs/{lid}")[0] == 404
    finally:
        srv.shutdown()


def _big_doc(i: int, stats: bool = True):
    hits = []
    for k in range(120):
        hits.append({"t": k * 0.5, "player": "a", "skill_id": [15060130, 15050130, 15040240][k % 3],
                     "skill": ["Hellfire", "Blaze", "Firestorm"][k % 3], "damage": 2000.0 + 50 * i + (k % 3) * 300,
                     "crit": k % 4 == 0})
    p = {"id": "a", "name": f"Sorc{i}", "class": "sorcerer", "combat_power": 70000 + 1000 * i,
         "specs": {"Hellfire": [2, 4]}}
    if stats:
        p["stats"] = {"critical_hit": 900.0, "double_pct": 2.0, "perfect_pct": 5.0}
    return {"format": "a2log", "version": 1, "meta": {"source": "test"}, "players": [p],
            "segments": [{"boss": "Boss", "duration": 60.0, "hits": hits}]}


def test_community_learning_from_uploads(tmp_path):
    from aion2calc.logserver import learn as L
    from aion2calc.logserver import server as LS
    from aion2calc.logserver.format import validate
    LS.CONFIG = LS.Config(str(tmp_path / "logs"))
    st = LS.CONFIG.store
    rows = []
    for i in range(6):
        doc = validate(_big_doc(i))
        obs = L.observe_doc(doc)
        assert len(obs) == 1 and obs[0]["class"] == "sorcerer" and "Sorc" not in json.dumps(obs)   # no names
        st.put_observations(f"log{i}", obs)
        rows += obs
    agg = L.aggregate(st.observations("sorcerer"))
    assert agg["observations"] == 6 and agg["top_quarter"]["specs"][0]["picks"][0]["specs"] == "2, 4"
    assert {r["skill"] for r in agg["top_quarter"]["skills"]} == {"Hellfire", "Blaze", "Firestorm"}
    cal = L.calibration("sorcerer", rows)
    assert cal["active"] and cal["with_stats"] == 6
    lo, hi = L.BOUNDS["skill"]
    assert cal["skills"] and all(lo <= v <= hi for v in cal["skills"].values())
    assert cal["rates"]["double"] != 1.0 or cal["rates"]["perfect"] != 1.0
    st.delete("log0")
    assert len(st.observations("sorcerer")) == 5                          # deleting a log forgets it


def test_upload_feeds_stats_but_private_does_not(tmp_path):
    from http.server import ThreadingHTTPServer

    from aion2calc.logserver import server as LS
    LS.CONFIG = LS.Config(str(tmp_path / "logs"))
    _, key = LS.CONFIG.store.create_key("t")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), LS.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(doc, vis):
        req = urllib.request.Request(f"{base}/api/v1/logs?visibility={vis}", json.dumps(doc).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + key})
        return json.load(urllib.request.urlopen(req, timeout=30))
    try:
        assert post(_big_doc(1), "unlisted")["learned_from"] == 1
        assert post(_big_doc(2), "private")["learned_from"] == 0
        d = _big_doc(3)
        d["meta"]["contribute"] = "no"
        assert post(d, "public")["learned_from"] == 0
        s = json.load(urllib.request.urlopen(base + "/api/v1/stats/sorcerer", timeout=30))
        assert s["observations"] == 1
        assert json.load(urllib.request.urlopen(base + "/api/v1/calibration/sorcerer", timeout=30))["fights"] == 1
        assert json.load(urllib.request.urlopen(base + "/.well-known/a2log.json"))["calibration_url"].endswith("{class}")
    finally:
        srv.shutdown()


def test_local_calibration_merges_community(home):
    import time as _t

    from aion2calc import learn
    from aion2calc.paths import write_user_json
    from aion2calc.sim import engine
    write_user_json({"class": "sorcerer", "active": True, "fights": 9, "fetched_at": _t.time(), "crit_x0": 1000.0,
                     "rates": {"double": 1.2}, "skills": {"Blaze": 0.9, "Hellfire": 1.1}},
                    "calibration", "community_sorcerer.json")
    write_user_json({"class": "sorcerer", "active": True, "fights": 3, "crit_x0": learn._DEFAULT_X0,
                     "rates": {}, "skills": {"Hellfire": 1.3}}, "calibration", "sorcerer.json")
    m = learn.merged("sorcerer")
    assert m["skills"] == {"Blaze": 0.9, "Hellfire": 1.3}                  # yours wins where it exists
    assert m["rates"] == {"double": 1.2} and m["crit_x0"] == 1000.0
    with learn.calibrated("sorcerer"):
        assert engine.SKILL_MULT["Blaze"] == 0.9
    assert not engine.SKILL_MULT


def test_titles_plan_per_slot_and_collection(home):
    from aion2calc.paths import write_user_json
    from aion2calc.plan.context import PlanContext
    from aion2calc.plan.titles import plan_titles
    write_user_json([
        {"name": "Strong", "grade": "Unique", "faction": "Both factions", "slot": "Attack",
         "equip": "PvE Damage Boost +4.5%, Attack Bonus +34", "owned": "PvE Damage Boost +1%", "earn": "do a thing"},
        {"name": "Weak", "grade": "Common", "faction": "Both factions", "slot": "Attack",
         "equip": "Attack Bonus +5", "owned": "Accuracy Bonus +5"},
        {"name": "Fast", "grade": "Epic", "faction": "Both factions", "slot": "Etc",
         "equip": "Cooldown Reduction +3%", "owned": "—"},
        {"name": "Tough", "grade": "Rare", "faction": "Both factions", "slot": "Defense",
         "equip": "Critical Hit +20", "owned": "Critical Hit +5"}], "global", "titles.json")
    ctx = PlanContext.for_class("sorcerer")
    t = plan_titles(ctx, owned=["Weak"])
    a = t["slots"]["Attack"]
    assert a["best"][0]["name"] == "Strong" and a["best"][0]["gain"] > a["best"][1]["gain"]
    assert a["best_owned"]["name"] == "Weak"
    assert t["slots"]["Etc"]["best"][0]["name"] == "Fast" and t["slots"]["Defense"]["best"][0]["name"] == "Tough"
    assert [c["name"] for c in t["collect"]][0] == "Strong"               # +1% PvE owned bonus beats +5 crit
    assert "Weak" not in [c["name"] for c in t["collect"]]                # already owned


def test_title_page_parse(monkeypatch):
    from aion2calc.scrape import metabot
    page = "x"
    monkeypatch.setattr(metabot, "fetch", lambda url, **kw: page)
    monkeypatch.setattr(metabot, "flight", lambda h: h)
    monkeypatch.setattr(metabot, "text_lines", lambda h: ["Unbound by Genus", "Category", "Growth", "Role", "Offensive",
                                                          "How to earn", "Achievement"])
    d = metabot.title_detail("unbound-by-genus")
    assert d == {"slug": "unbound-by-genus", "category": "Growth", "role": "Offensive", "how": "Achievement",
                 "slot": "Attack"}
