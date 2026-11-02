"""The My Character overview's Healing share (0.2.368): the character's recorded heals pooled per skill from the
recordings saved on this computer, cached per file, restores left out, the character matched by name and server."""
import json
import time

from aion2calc.combat import healing_share


def _doc(name, server, heals, duration=60.0):
    me = {"id": "p:1", "name": name, "class": "cleric", "server": server}
    other = {"id": "p:2", "name": "Tank", "class": "templar", "server": server}
    events = [{"t": 1.0 + i, "kind": "heal", "source": "p:1", "target": "p:2", "skill": skill, "skill_id": sid, "amount": amount}
              for i, (skill, sid, amount) in enumerate(heals)]
    events.append({"t": 3.0, "kind": "heal", "source": "p:2", "target": "p:1", "skill": "Other", "skill_id": 1, "amount": 999})
    return {"format": "a2log", "version": 1, "meta": {"source": "test"}, "players": [me, other],
            "segments": [{"label": "Boss", "boss": "Boss", "duration": duration, "killed": True, "hits": [], "events": events}]}


def test_the_recorded_heals_pool_per_skill_and_the_cache_follows_the_files(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(healing_share, "logs_dir", lambda: logs)
    monkeypatch.setattr(healing_share, "home", lambda: tmp_path)
    (logs / "session-1.a2log.json").write_text(json.dumps(_doc("Seren", "Siel", [("Healing Light", 17010000, 3000), ("Grace", 17020000, 1000)])))
    (logs / "session-2.a2log.json").write_text(json.dumps(_doc("Seren", "Siel", [("Healing Light", 17010000, 2000)], duration=40.0)))
    (logs / "session-3.a2log.json").write_text(json.dumps(_doc("Seren", "Zikel", [("Healing Light", 17010000, 9000)])))   # another server
    (logs / "session-4.a2log.json").write_text(json.dumps(_doc("Seren", "Siel", [("Healing Light", 17010000, 500)], duration=5.0)))  # too short
    out = healing_share.recorded_healing("seren", "Siel")
    assert out["healing"] == 6000 and out["fights"] == 2 and out["recordings"] == 2 and out["seconds"] == 100.0
    assert out["hps"] == 60.0 and out["shares"] == {"Healing Light": 5000 / 6000, "Grace": 1000 / 6000}
    cache = json.loads((tmp_path / healing_share.CACHE).read_text())
    assert len(cache) == 4 and sum(1 for r in cache.values() if r["total"] > 0) == 2
    # a new recording joins, an unchanged one is read from the cache (its file may even go unreadable)
    (logs / "session-5.a2log.json").write_text(json.dumps(_doc("Seren", "Siel", [("Grace", 17020000, 4000)])))
    (logs / "session-1.a2log.json").write_text("{broken")
    time.sleep(0.01)
    out = healing_share.recorded_healing("Seren", "Siel")
    assert out["healing"] == 6000 - 4000 + 4000 and out["recordings"] == 2      # session-1 fell out (changed, unreadable), 5 came in
    assert out["shares"]["Grace"] > out["shares"]["Healing Light"]
    assert healing_share.recorded_healing("Nobody", None) is None
    assert healing_share.recorded_healing("Seren", None)["recordings"] == 3     # without a server every Seren counts
