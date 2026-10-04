"""Tests for the database, sync, character import, combat analysis and app server.

Network access is never needed: sources are replaced by fakes.
"""
import json
import threading
import time
import urllib.request

import pytest

from aion2calc.kit.base import ClassData


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.db import store
    monkeypatch.setattr(store, "SEED", tmp_path / "no-seed.json.gz")
    store._local.__dict__.clear()
    yield tmp_path / "home"
    store._local.__dict__.clear()


def test_overlay_prefers_user_copy(home):
    from aion2calc.paths import data_file, read_json, write_user_json
    assert "data" in str(data_file("global", "titles.json"))
    write_user_json([{"name": "X"}], "global", "titles.json")
    assert str(data_file("global", "titles.json")).startswith(str(home))
    assert read_json("global", "titles.json") == [{"name": "X"}]


def test_store_roundtrip_and_seed(home, tmp_path):
    from aion2calc.db import store
    conn = store.connect(tmp_path / "a.db")
    store.upsert_item(conn, {"slug": "rupture-tome", "name": "Rupture Tome", "grade": "Unique",
                             "category": "Spellbook", "item_level": 54, "meta": {"Class": "Sorcerer"}}, "2026-10-01")
    conn.commit()
    assert store.items(conn, search="rupture")[0]["grade"] == "Unique"
    seed = tmp_path / "seed.json.gz"
    assert store.export_seed(conn, seed) == 1
    conn2 = store.connect(tmp_path / "b.db")
    assert store.import_seed(conn2, seed) == 1
    assert store.item(conn2, "rupture-tome")["name"] == "Rupture Tome"


def test_sync_fetches_only_new_or_changed(home, monkeypatch, tmp_path):
    from aion2calc.db import store, sync
    from aion2calc.scrape import metabot
    base = metabot.BASE
    lastmods = {f"{base}/items/a-sword": "2026-10-01", f"{base}/items/b-ring": "2026-10-01"}
    fetched = []
    monkeypatch.setattr(metabot, "sitemap", lambda name: dict(lastmods) if name == "aion-2-items-1" else {})
    monkeypatch.setattr(metabot, "category_slugs", lambda cat: ["a-sword", "b-ring"] if cat == "weapons" else [])
    monkeypatch.setattr(metabot, "item_full", lambda slug, cache=False: fetched.append(slug) or
                        {"slug": slug, "name": slug, "grade": "Rare", "category": "Sword", "meta": {}})
    monkeypatch.setattr(metabot, "titles", lambda fresh=False: [])
    monkeypatch.setattr(sync.Sync, "_classes", lambda self, conn, pages: [])
    db = tmp_path / "s.db"
    sync.Sync(db_path=db).run()
    assert sorted(fetched) == ["a-sword", "b-ring"]
    fetched.clear()
    sync.Sync(db_path=db).run()
    assert fetched == []                                  # nothing changed
    lastmods[f"{base}/items/b-ring"] = "2026-10-05"
    sync.Sync(db_path=db).run()
    assert fetched == ["b-ring"]                          # only the changed page
    assert store.connect(db).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def _profile():
    """A synthetic level-45 Sorcerer profile shaped like the official API response."""
    cd = ClassData("sorcerer")
    fa = cd.by_name["Flame Arrow"]["id"]
    board = next(b for b in cd.boards if b["name"] == "Nezekan")
    fa_nodes = [n for n in board["nodes"] if n.get("skillId") == fa][:1]
    nodes = [{"nodeId": n["id"], "open": 1} for n in fa_nodes]
    return {
        "region": "nae",
        "profile": {"characterId": "test=", "characterName": "TestSorc", "className": "Sorcerer",
                    "characterLevel": 45, "combatPower": 50000, "serverId": 1101, "serverName": "Siel"},
        "stat": {"statList": [{"type": "STR", "name": "Might", "value": 20}, {"type": "Death", "value": 30}]},
        "title": {"titleList": [{"equipCategory": "Attack", "name": "T", "grade": "Epic",
                                 "equipStatList": [{"desc": "PvE Damage Boost +3%"}]}]},
        "petwing": {"wing": {"name": "Ultimate Daeva Wings"}, "pet": {"name": "P", "level": 1}},
        "skill": {"skillList": [
            {"id": fa, "name": "Flame Arrow", "category": "Active", "skillLevel": 12, "equip": 1},
            {"id": cd.by_name["Element Enhancement"]["id"], "name": "Element Enhancement", "category": "Dp",
             "skillLevel": 8, "equip": 1},
            {"id": cd.by_name["Cold Storm"]["id"], "name": "Cold Storm", "category": "Dp", "skillLevel": 5,
             "equip": 0}]},
        "equipment": {"equipmentList": [{"slotPos": 1, "slotPosName": "MainHand", "id": 1, "name": "Book",
                                         "grade": "Unique", "enchantLevel": 10},
                                        {"slotPos": 41, "slotPosName": "Arcana1", "id": 2, "name": "Parchment of Magic",
                                         "grade": "Unique", "enchantLevel": 0}]},
        "items": {"1": {"mainStats": [{"id": "WeaponFixingDamage", "minValue": "206", "value": "229", "extra": "50"},
                                      {"id": "Critical", "name": "Critical Hit", "value": "100"}],
                        "subStats": [{"id": "CombatSpeed", "name": "Combat Speed", "value": "3.2%"}],
                        "magicStoneStat": [{"id": "WeaponFixingDamage", "name": "Attack", "value": "+10"}]},
                  "41": {"mainStats": [{"id": "Destiny", "value": "20"}],
                         "subSkills": [{"id": fa, "name": "Flame Arrow", "level": 1}]}},
        "daevanion_detail": {str(board["id"]): {"nodeList": nodes}},
    }


def test_profile_to_build_and_loadout():
    from aion2calc.model.character import loadout_stats
    from aion2calc.sources.character import from_profile
    imp = from_profile(_profile())
    cd = ClassData("sorcerer")
    fa = cd.by_name["Flame Arrow"]["id"]
    # total 12 = SP + 1 Daevanion node + 1 arcana roll
    assert imp.build.sp[fa] == 10
    assert set(cd.skills[k]["name"] for k in imp.build.stigmas) == {"Element Enhancement"}
    st = loadout_stats(imp.loadout)
    assert st.weapon_min == 206 and st.weapon_max == 279
    from aion2calc.sources.character import OWNED_TITLES_ESTIMATE as est
    assert st.attack == 10 + est["attack"] and st.crit == 100 + est["crit"]      # manastone + title estimate
    assert abs(st.combat_speed - 0.032) < 1e-9
    assert st.skill_bonus == {fa: 1}
    assert st.might == 20 and st.death == 30 and abs(st.amp_pve - 0.03) < 1e-9


def test_combat_csv_breakdown():
    from aion2calc.combat.adapters import from_csv
    from aion2calc.combat.analyze import analyze, casts_of
    cd = ClassData("sorcerer")
    hf, fm = cd.by_name["Hellfire"]["id"], cd.by_name["Fire Mark"]["id"]
    rows = ["t,skill_id,skill,damage,crit,double,perfect,multi,dot"]
    rows += [f"{0.0 + i * 0.1:.1f},{hf},Hellfire,1000,1,0,0,2,0" for i in range(3)]      # one multi-hit cast
    rows += [f"{50.0 + i * 0.1:.1f},{hf},Hellfire,1000,0,1,0,0,0" for i in range(3)]     # second cast
    rows += [f"{t},{fm},Fire Mark,100,0,0,0,0,0" for t in (1, 2, 3, 4)]                  # passive procs
    enc = from_csv("\n".join(rows))
    assert enc["meta"]["class"] == "sorcerer"
    a = analyze(enc)
    hfrow = next(r for r in a["skills"] if r["skill"] == "Hellfire")
    assert hfrow["casts"] == 2 and abs(hfrow["crit"] - 0.5) < 1e-9 and abs(hfrow["double"] - 0.5) < 1e-9
    assert abs(sum(r["share"] for r in a["skills"]) - 1) < 1e-9
    assert all(c["skill"] != "Fire Mark" for c in casts_of(enc["hits"], cd))       # procs are not casts
    assert a["summary"]["idle_seconds"] > 40                                       # 50 s gap


def test_app_server_endpoints(home):
    from http.server import ThreadingHTTPServer

    from aion2calc.app.server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path):
        return json.loads(urllib.request.urlopen(base + path, timeout=30).read())

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    try:
        assert "sorcerer" in get("/api/classes")
        assert get("/api/status")["db"]["items"] >= 0
        res = get("/api/results")
        assert res and res[0]["class"] == "sorcerer"
        v = get("/api/build?path=" + res[0]["path"])
        assert v["skills"]["active"] and v["daevanion"]["boards"] and v["equipment"]["slots"]
        assert urllib.request.urlopen(base + "/", timeout=10).status == 200
        cd = ClassData("sorcerer")
        hf = cd.by_name["Hellfire"]["id"]
        csv = "t,skill_id,damage\n" + "\n".join(f"{i},{hf},1000" for i in range(0, 60, 2))
        job = post("/api/encounters/import", {"text": csv, "name": "t.csv"})["job"]
        for _ in range(100):
            j = get("/api/jobs/" + job)
            if j["status"] != "running":
                break
            time.sleep(0.2)
        assert j["status"] == "done", j
        assert j["result"]["summary"]["casts"] >= 2
        assert j["result"]["file"].startswith(str(home / "logs"))          # written to the logs folder
        assert get("/api/logs")["files"] == 1
    finally:
        srv.shutdown()


def test_new_skill_from_a_patch_is_simulated():
    """A skill the hand-written kit does not know falls back to the tooltip-driven model."""
    import copy

    from aion2calc.kit import sorcerer
    from aion2calc.kit.base import Build
    cd = ClassData("sorcerer")
    new = copy.deepcopy(cd.by_name["Blaze"])
    new["id"], new["name"] = 15999000, "Test Patch Skill"
    cd.skills[new["id"]] = new
    cd.by_name[new["name"]] = new
    kit = sorcerer.build_kit(Build("sorcerer", sp={15999000: 5}), cd)
    assert any(a.skill_id == 15999000 for a in kit.actions.values())
    assert "test_patch_skill" in kit.policy


def test_windows_data_folder_is_appdata(tmp_path, monkeypatch):
    """On Windows everything goes to %LOCALAPPDATA%\\aion2calc; an old ~/.aion2calc is moved there."""
    from aion2calc import paths
    monkeypatch.delenv("AION2CALC_HOME", raising=False)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("HOME", str(tmp_path / "me"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "me"))
    legacy = tmp_path / "me" / ".aion2calc"
    legacy.mkdir(parents=True)
    (legacy / "aion2.db").write_text("x")
    h = paths.home()
    assert h == tmp_path / "AppData" / "Local" / "aion2calc"
    assert (h / "aion2.db").read_text() == "x" and not legacy.exists()
    assert paths.logs_dir() == h / "logs" and paths.results_dir() == h / "results"
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "custom"))            # explicit folder still wins
    assert paths.home() == tmp_path / "custom"


def test_logs_folder_files(home):
    from aion2calc.combat import logs
    from aion2calc.combat.adapters import from_csv
    from aion2calc.db import store
    assert logs._safe('Boss: "X" / <Y>?') == "Boss-X-Y"                     # valid Windows file name
    enc = from_csv("t,skill,damage\n0,Hellfire,100\n5,Hellfire,100", {"ref": "a.csv", "player": "Me",
                                                                     "target": "Training Scarecrow"})
    eid, path = logs.save(enc)
    assert path.parent == home / "logs" and path.name.endswith(f"_csv-{eid}.json") and "_Me_" in path.name
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["total"] == 200
    eid2, path2 = logs.save(enc)                                            # re-import replaces the old file
    assert eid2 != eid and not path.exists() and len(list((home / "logs").glob("*.json"))) == 1
    conn = store.connect()
    enc3 = from_csv("t,skill,damage\n0,Blaze,50", {"ref": "b.csv"})
    store.put_encounter(conn, enc3)                                         # stored before the folder existed
    assert logs.backfill(conn) == 1 and len(list((home / "logs").glob("*.json"))) == 2


def _segment():
    """A small AbyssLogs segment: a Sorcerer and a Templar on a boss."""
    me, mate, boss = 101, 102, 900
    ev = lambda t, pid, code, dmg, **kw: {"timeMs": t, "playerId": pid, "targetId": boss, "skillCode": code,
                                          "damage": dmg, "hitCount": kw.pop("hits", 1), **kw}
    return {
        "id": "seg-1", "label": "Gatekeeper", "startTime": "2026-10-04T19:00:00.000Z",
        "endTime": "2026-10-04T19:00:20.000Z", "region": "na", "recorderName": "Mate",
        "players": {
            str(me): {"entityId": me, "name": "Sorc", "classHint": "Sorcerer", "combatPower": 70000,
                      "totalDamage": 6000, "targets": {str(boss): {"skills": {
                          "15060130": {"skillName": "Hellfire", "specialities": [{"slot": 4}, {"slot": 1}]},
                          "15090230": {"skillName": "Ice Chain", "specialities": [{"slot": 2}]}}}}},
            str(mate): {"entityId": mate, "name": "Mate", "classHint": "Templar", "totalDamage": 500,
                        "targets": {}}},
        "targets": {str(boss): {"entityId": boss, "name": "Gatekeeper", "isBoss": True, "isDead": True}},
        "bossTimeline": {
            "events": [ev(0, me, 15060130, 3000, isCrit=True, hits=3), ev(2000, me, 15090230, 500),
                       ev(2600, me, 15100230, 600, isDouble=True), ev(4000, me, 15210230, 400),
                       ev(4700, me, 15030230, 450), ev(6000, me, 1539001012, 50, isDot=True),
                       ev(7000, me, 3000024, 1000), ev(8000, mate, 12010000, 500)],
            "skills": {"15100230": {"skillName": "Cold Wave"}, "15030230": {"skillName": "Burst"},
                       "3000024": {"skillName": "Theostone: Rathman's Greed"}, "15400000": {"skillName": "x"}},
            "buffSpans": [{"startMs": 0, "endMs": 5000, "skillCode": 15400000, "targetId": me, "sourceId": me},
                          {"startMs": 4000, "endMs": 10000, "skillCode": 15400000, "targetId": me, "sourceId": me},
                          {"startMs": 0, "endMs": 20000, "skillCode": 15400000, "targetId": mate, "sourceId": mate}]},
    }


def test_abysslogs_segment_to_encounter():
    from aion2calc.combat import abysslogs
    from aion2calc.combat.adapters import from_text
    from aion2calc.combat.analyze import analyze
    assert abysslogs.parse_ref("https://abysslogs.com/e/zpzMbLAE?g=0&seg=7d2b") == ("zpzMbLAE", "7d2b")
    assert abysslogs.parse_ref("abysslogs.com/e/P6CE2bER") == ("P6CE2bER", None)
    seg = _segment()
    with pytest.raises(ValueError):
        abysslogs.from_segment(seg, player="Nobody")
    enc = from_text(json.dumps(seg), player="sorc")                      # detected as an AbyssLogs segment
    m = enc["meta"]
    assert (m["source"], m["class"], m["player"], m["target"], m["duration"]) == \
        ("abysslogs", "sorcerer", "Sorc", "Gatekeeper", 20.0)
    assert [p["name"] for p in m["party"]] == ["Sorc", "Mate"] and m["boss_killed"]
    cd = ClassData("sorcerer")
    by = {h["skill"]: h for h in enc["hits"]}
    assert by["Hellfire"]["skill_id"] == cd.by_name["Hellfire"]["id"] and by["Hellfire"]["multi"] == 2
    assert by["Ice Chain (Cold Wave)"]["skill_id"] == cd.by_name["Ice Chain"]["id"]     # named in the tooltip
    assert by["Flame Arrow (Burst)"]["skill_id"] == cd.by_name["Flame Arrow"]["id"]     # listed chain step
    assert by["Fire Wall"]["dot"] and by["Ice Chain (Cold Wave)"]["double"]           # 10-digit DoT code
    assert "Theostone: Rathman's Greed" in by and len(enc["hits"]) == 7                # the Templar's hit is left out
    assert enc["specs"] == {"Hellfire": "1, 4", "Ice Chain": "2"}
    buff = enc["buffs"][0]
    assert buff["windows"] == [[0.0, 10.0]] and abs(buff["uptime"] - 0.5) < 1e-9
    assert from_text(json.dumps(seg))["meta"]["player"] == "Mate"                  # default: the recorder
    rows = {r["skill"]: r for r in analyze(enc)["skills"]}
    assert rows["Ice Chain"]["casts"] == 1 and rows["Ice Chain (Cold Wave)"]["casts"] == 1


def test_spec_diff_against_build():
    from aion2calc.combat.analyze import spec_diff
    from aion2calc.kit.base import Build
    cd = ClassData("sorcerer")
    hf = cd.by_name["Hellfire"]
    build = Build("sorcerer", specs={hf["id"]: (hf["specs"][1]["id"], hf["specs"][3]["id"])})
    d = spec_diff({"specs": {"Hellfire": "1, 4", "Unknown": "1"}}, build)
    assert d == [{"skill": "Hellfire", "yours": "1, 4", "optimal": "2, 4", "differs": True}]
