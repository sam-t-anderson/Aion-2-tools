"""Tests for the live damage meter: replay source -> meter -> snapshot / a2log, and the decoder path."""
import json
from pathlib import Path

from aion2calc.combat import a2log as F
from aion2calc.meter import CombatEvent, JsonLinesDecoder, Meter, capture_source, load_decoder, replay_source

DEMO = Path(__file__).resolve().parent.parent / "aion2calc" / "meter" / "demo_session.jsonl"


def test_replay_feeds_meter_snapshot():
    m = Meter()
    for ev in replay_source(DEMO):
        m.add(ev)
    snap = m.snapshot()
    assert snap["duration"] > 5
    names = [p["name"] for p in snap["players"]]
    assert set(names) == {"Zikel", "Aegis"}
    sorc = next(p for p in snap["players"] if p["name"] == "Zikel")
    assert sorc["class"] == "Sorcerer" and sorc["dps"] > 0 and sorc["skills"]
    assert abs(sum(p["share"] for p in snap["players"]) - 1.0) < 1e-6
    assert snap["boss"] == "Gatekeeper Pinopi"


def test_meter_to_a2log_validates_and_analyzes():
    m = Meter()
    for ev in replay_source(DEMO):
        m.add(ev)
    doc = m.to_a2log(title="Demo")                       # to_a2log validates internally
    assert doc["format"] == "a2log" and len(doc["players"]) == 2
    seg = doc["segments"][0]
    assert seg["hits"] and seg["buffs"] and seg["boss"] == "Gatekeeper Pinopi"
    # it flows through the existing analyzer
    from aion2calc.combat.analyze import analyze
    enc = F.to_encounter(doc, doc["players"][0]["id"], 0)
    a = analyze(enc)
    assert a["summary"]["dps"] > 0


def test_pet_damage_folds_into_owner_and_local_player():
    m = Meter()
    m.add(CombatEvent(t=0.0, source="p1", source_name="Me", source_class="spiritmaster", local=True,
                      damage=100, skill="Cold Shock", target="Boss", target_boss=True))
    m.add(CombatEvent(t=1.0, source="pet9", source_name="Water Spirit", is_pet=True, owner="p1",
                      damage=50, skill="Spirit Skill"))
    m.add(CombatEvent(t=2.0, source="pet9", source_name="Water Spirit", is_pet=True,   # owner omitted
                      damage=40, skill="Spirit Skill"))                                # -> solo fallback to local
    snap = m.snapshot()
    assert len(snap["players"]) == 1 and snap["players"][0]["damage"] == 190   # pet folded into its owner
    assert m.local_player == "p1"
    doc = m.to_a2log(title="Pets")
    seg = doc["segments"][0]
    pet_hits = [h for h in seg["hits"] if h.get("pet")]
    assert len(pet_hits) == 2 and all(h["player"] == "p1" for h in pet_hits)   # credited to the owner
    assert any(e["kind"] == "pet" and e["owner"] == "p1" for e in seg["entities"])
    from aion2calc.combat.analyze import analyze
    enc = F.to_encounter(doc, "p1", 0)
    assert analyze(enc)["summary"]["total"] == 190                             # owner's total includes the pet


def test_ping_rides_the_meter_into_snapshot_and_log():
    m = Meter()
    m.add(CombatEvent(t=0.0, source="p1", source_name="Me", source_class="sorcerer",
                      damage=100, skill="Flame Arrow", target="Boss", target_boss=True))
    for i, ms in enumerate([42, 55, 48, 60, 51]):
        m.add(CombatEvent(t=float(i + 1), kind="ping", ping_ms=ms))
    m.add(CombatEvent(t=6.0, source="p1", damage=100, skill="Flame Arrow"))
    snap = m.snapshot()
    assert snap["ping"]["current"] == 51 and snap["ping"]["min"] == 42 and snap["ping"]["max"] == 60
    assert snap["players"][0]["damage"] == 200 and snap["duration"] == 6.0   # ping never moved the clock
    seg = m.to_a2log(title="Ping")["segments"][0]
    assert seg["ping"] == [[1.0, 42.0], [2.0, 55.0], [3.0, 48.0], [4.0, 60.0], [5.0, 51.0]]


def test_jsonlines_decoder_and_capture_source():
    dec = load_decoder("jsonlines")
    assert isinstance(dec, JsonLinesDecoder)
    frames = [json.dumps({"t": 1.0, "source": "p1", "source_name": "A", "skill": "X", "damage": 100, "crit": True}).encode(),
              json.dumps([{"t": 2.0, "source": "p1", "skill": "X", "damage": 50}]).encode(),
              b"not json"]
    m = Meter()
    for ev in capture_source(dec, frames):
        m.add(ev)
    snap = m.snapshot()
    assert len(snap["players"]) == 1 and snap["players"][0]["damage"] == 150


def test_combatevent_from_dict_ignores_unknown_keys():
    ev = CombatEvent.from_dict({"t": 1.0, "source": "p1", "damage": 10, "bogus": 1})
    assert ev.t == 1.0 and ev.damage == 10 and ev.source == "p1"


def test_runner_replay_and_save(tmp_path, monkeypatch):
    import time as _time

    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.app.meter_runner import Runner
    r = Runner()
    r.start("replay", path=str(DEMO), realtime=False)
    for _ in range(100):                                  # the fast replay finishes almost immediately
        if not r.status()["running"]:
            break
        _time.sleep(0.05)
    snap = r.status()["snapshot"]
    assert snap["duration"] > 0 and len(snap["players"]) == 2
    doc = r.to_a2log(title="Run")
    assert doc["format"] == "a2log" and doc["segments"][0]["hits"]
    r.stop()


def test_runner_live_without_decoder_reports_error():
    from aion2calc.app.meter_runner import Runner
    st = Runner().start("live")
    assert not st["running"] and "decoder" in (st["error"] or "")


def _make_install(root, paks, *, purple_rev=None, steam_build=None, appid="123"):
    """A synthetic AION 2 install tree: shared content, launcher-specific metadata."""
    paks_dir = root / "Aion2" / "Content" / "Paks"
    paks_dir.mkdir(parents=True, exist_ok=True)
    for name, size in paks.items():
        (paks_dir / name).write_bytes(b"\0" * size)
    if purple_rev is not None:
        (root / f"VersionInfo_A2_LIVE_PURPLE.xml").write_text(
            f"<VersionInfo><Version>{purple_rev}</Version><Updated>1</Updated></VersionInfo>", encoding="utf-8")
    if steam_build is not None:
        (root.parent.parent / f"appmanifest_{appid}.acf").write_text(
            f'"AppState"\n{{\n"appid" "{appid}"\n"installdir" "{root.name}"\n"buildid" "{steam_build}"\n}}\n',
            encoding="utf-8")
    return root


def test_shared_content_fingerprint_aligns_steam_and_purple(tmp_path):
    """The shipped-package fingerprint matches across launchers of the same patch,
    even though their launcher build ids differ; the comparator names it the
    shared version key."""
    from aion2calc.meter.metadata import _build_evidence
    from aion2calc.meter.builds import compare_installs, version_signals
    content = {"global.pak": 4096, "pakchunk0-WindowsClient.utoc": 2048, "pakchunk0-WindowsClient.ucas": 8192}
    steam_root = _make_install(tmp_path / "steamapps" / "common" / "AION2", content, steam_build="900100")
    purple_root = _make_install(tmp_path / "Purple" / "AION2", content, purple_rev="20250101")

    steam = _build_evidence(steam_root)
    purple = _build_evidence(purple_root)
    assert steam["installed_content_build"] == purple["installed_content_build"]       # same content -> same key
    assert steam["installed_content_build"].startswith("content:")
    assert steam["launcher_build"] == "900100" and purple["launcher_build"] == "20250101"   # launcher ids differ
    assert steam["launcher_build_namespace"] == "steam:123"
    assert purple["launcher_build_namespace"].startswith("purple:")

    cmp = compare_installs([{**steam, "launcher": "Steam"}, {**purple, "launcher": "PURPLE"}])
    assert cmp["shared_version_key"] == "installed_content_build"
    content_row = next(r for r in cmp["signals"] if r["key"] == "installed_content_build")
    launcher_row = next(r for r in cmp["signals"] if r["key"] == "launcher_build")
    assert content_row["agrees"] is True and launcher_row["agrees"] is False
    assert any(s["cross_launcher"] is True for s in version_signals(steam))


def test_content_fingerprint_changes_when_content_patches(tmp_path):
    """A content patch (a pak changes size) yields a different fingerprint."""
    from aion2calc.meter.metadata import _build_evidence
    a = _build_evidence(_make_install(tmp_path / "a" / "AION2", {"global.pak": 4096}))
    b = _build_evidence(_make_install(tmp_path / "b" / "AION2", {"global.pak": 5000}))
    assert a["installed_content_build"] != b["installed_content_build"]
