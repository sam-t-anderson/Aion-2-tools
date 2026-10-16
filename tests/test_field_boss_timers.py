"""Observed field-boss timers: the kills the live meter observed on the player's own server
(the share server's kill feed: uploaded recordings and corroborated auto-reports, never the
Discord bot's manual timers), filtered to the player's faction's zones plus the Abyss, with the
expected return from the community respawn reference. Shown on the overlay's event strip and
on the Timers page, where the identified server and faction are the defaults."""
import json
import pathlib
import time

from aion2calc.combat import field_bosses as fb

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERLAY = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")
TIMERS = (ROOT / "aion2calc" / "app" / "static" / "timers.js").read_text(encoding="utf-8")
APP = (ROOT / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
RUNNER = (ROOT / "aion2calc" / "app" / "meter_runner.py").read_text(encoding="utf-8")

NOW = 1_800_000_000.0


def _table(tmp_path):
    rows = [{"name": "Kernon of the West", "faction": "elyos", "zone": "Verteron · Cantas Valley", "respawn_minutes": 30},
            {"name": "Immortal Gartua", "faction": "asmodian", "zone": "Altgard · Mumu Village", "respawn_minutes": 60},
            {"name": "Watcher Kaira", "faction": "abyss", "zone": "Abyss", "respawn_minutes": None},
            {"name": "Silent Dartan", "faction": "elyos", "zone": "Verteron · South", "respawn_minutes": 180},
            {"name": "Silent Dartan", "faction": "asmodian", "zone": "Altgard · Forest", "respawn_minutes": 360}]
    path = tmp_path / "field-bosses.json"
    path.write_text(json.dumps({"version": 1, "bosses": rows}), encoding="utf-8")
    return fb.reference(path)


def test_bundled_reference_loads_and_knows_the_factions():
    table = fb.reference()
    assert len(table) >= 40
    assert fb.faction_of_boss("Kernon of the West") == "elyos"
    assert fb.faction_of_boss("nobody at all") is None
    assert any(fb.faction_of_boss(name) == "abyss" for name in table)


def test_relevant_keeps_own_faction_and_abyss_with_the_reference_return(tmp_path):
    table = _table(tmp_path)
    kills = [{"boss": "Kernon of the West", "killed_at": NOW - 600, "reports": 2, "server": "2102", "map_id": 1010},
             {"boss": "Immortal Gartua", "killed_at": NOW - 100, "reports": 1, "server": "2102", "map_id": 1110},
             {"boss": "Watcher Kaira", "killed_at": NOW - 100, "respawn_at": NOW + 500, "reports": 3},
             {"boss": "Unknown Thing", "killed_at": NOW - 50}]
    asmo = fb.relevant(kills, "asmodian", NOW, table)
    assert [k["boss"] for k in asmo] == ["Watcher Kaira", "Immortal Gartua"]       # soonest return first
    gartua = asmo[1]
    assert gartua["expected_at"] == NOW - 100 + 3600 and gartua["respawn_basis"] == "reference"
    assert gartua["zone"] == "Altgard · Mumu Village" and gartua["faction"] == "asmodian"
    assert asmo[0]["respawn_basis"] == "measured" and asmo[0]["expected_at"] == NOW + 500
    elyos = fb.relevant(kills, "elyos", NOW, table)
    assert [k["boss"] for k in elyos] == ["Watcher Kaira", "Kernon of the West"]
    # No faction wanted ("every zone"): every kill passes, a boss the reference does not know included
    # (the feed already limits itself to field bosses); it just carries no zone or reference return.
    everything = fb.relevant(kills, None, NOW, table)
    assert {k["boss"] for k in everything} == {"Kernon of the West", "Immortal Gartua", "Watcher Kaira", "Unknown Thing"}
    unknown = next(k for k in everything if k["boss"] == "Unknown Thing")
    assert unknown["zone"] is None and unknown["expected_at"] is None and unknown["faction"] is None


def test_relevant_drops_stale_kills_and_long_passed_returns(tmp_path):
    table = _table(tmp_path)
    kills = [{"boss": "Kernon of the West", "killed_at": NOW - fb.FEED_WINDOW_S - 1},             # older than the window
             {"boss": "Kernon of the West", "killed_at": NOW - 30 * 60 - fb.DUE_GRACE_S - 1},     # returned long ago
             {"boss": "Kernon of the West", "killed_at": NOW - 30 * 60 - 60}]                      # due a minute ago: kept
    out = fb.relevant(kills, "elyos", NOW, table)
    assert len(out) == 1 and out[0]["expected_at"] == NOW - 60


def test_a_name_in_both_zones_is_told_apart_by_the_kill_map(tmp_path):
    table = _table(tmp_path)
    assert fb.boss_entry("Silent Dartan", table, 1110)["zone"] == "Altgard · Forest"
    assert fb.boss_entry("Silent Dartan", table, 1010)["zone"] == "Verteron · South"
    assert fb.boss_entry("Silent Dartan", table, 101007)["faction"] == "elyos"
    merged = fb.boss_entry("Silent Dartan", table, 5)          # an unexpected map: both factions, no reference
    assert merged["faction"] == "abyss" and merged["respawn_minutes"] is None
    kills = [{"boss": "Silent Dartan", "killed_at": NOW - 60, "map_id": 1110}]
    asmo = fb.relevant(kills, "asmodian", NOW, table)
    assert asmo and asmo[0]["respawn_minutes"] == 360
    assert fb.relevant(kills, "elyos", NOW, table) == []       # the Altgard kill is not an Elyos timer


def test_the_kill_map_decides_the_faction_before_the_reference_name(tmp_path):
    table = _table(tmp_path)
    kills = [{"boss": "Watchdog Kwapo", "killed_at": NOW - 60, "map_id": 1110, "respawn_at": NOW + 900},   # not in the reference
             {"boss": "Argo, the Spirit King", "killed_at": NOW - 60, "map_id": 1110},                     # an Abyss namesake, killed in Altgard
             {"boss": "Kernon of the West", "killed_at": NOW - 60, "map_id": 1110}]                        # an Elyos row, but an Altgard kill
    table["argo the spirit king"] = [{"name": "Argo the Spirit King", "faction": "abyss", "zone": "Reshanta", "respawn_minutes": 120}]
    asmo = fb.relevant(kills, "asmodian", NOW, table)
    assert [(k["boss"], k["zone"], k["respawn_basis"]) for k in asmo] == [
        ("Watchdog Kwapo", "Altgard", "measured"), ("Argo, the Spirit King", "Altgard", None), ("Kernon of the West", "Altgard", None)]
    assert fb.relevant(kills, "elyos", NOW, table) == []
    assert fb.faction_of_map(1010) == "elyos" and fb.faction_of_map(101007) == "elyos"
    assert fb.faction_of_map(141002) is None and fb.faction_of_map("1110") is None and fb.faction_of_map(True) is None
    # Punctuation never breaks a name match, and an Abyss row serves when the map is unknown.
    assert fb.boss_entry("Argo, the Spirit King", table)["zone"] == "Reshanta"
    assert fb.relevant([{"boss": "Argo the Spirit King", "killed_at": NOW - 60}], "elyos", NOW, table)[0]["faction"] == "abyss"


def test_faction_lookup_is_cached_positive_and_negative(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    calls = []

    def search(name, region, server_id):
        calls.append((name, region, server_id))
        if region == "nae":
            return [{"name": "Spirited", "server_id": 2102, "race": "Asmodian"},
                    {"name": "Spiritedx", "server_id": 2102, "race": "Elyos"}]
        return []
    assert fb.faction_for("Spirited", "2102", "nae", search=search, now=NOW) == "asmodian"
    assert calls == [("Spirited", "nae", 2102)]
    assert fb.faction_for("Spirited", "2102", "nae", search=search, now=NOW + 10) == "asmodian"
    assert len(calls) == 1                                     # served from the cache
    # Unknown region: every region is tried until an exact match answers.
    assert fb.faction_for("Nobody", "2102", None, search=search, now=NOW) is None
    assert {c[1] for c in calls[1:]} == {"nae", "eu", "as", "la"}
    before = len(calls)
    assert fb.faction_for("Nobody", "2102", None, search=search, now=NOW + 3600) is None
    assert len(calls) == before                                # a miss is remembered for a day
    assert fb.faction_for("Nobody", "2102", None, search=search, now=NOW + 2 * 86400) is None
    assert len(calls) > before                                 # and retried after it
    # A race code we cannot read is never guessed.
    assert fb.faction_from_race(2) is None and fb.faction_from_race("Elyos") == "elyos"


def test_document_carries_identity_and_only_relevant_kills(tmp_path):
    table = _table(tmp_path)
    fb._reference = table
    try:
        kills = [{"boss": "Kernon of the West", "killed_at": NOW - 60, "map_id": 1010},
                 {"boss": "Immortal Gartua", "killed_at": NOW - 60, "map_id": 1110}]
        doc = fb.document("2102", "Spirited", "asmodian", kills, server_name="Zikel", now=NOW)
        assert doc["server"] == "2102" and doc["server_name"] == "Zikel" and doc["faction"] == "asmodian"
        assert [k["boss"] for k in doc["kills"]] == ["Immortal Gartua"]
        assert "Discord" in doc["note"] and "never" in doc["note"]
        assert fb.document("2102", "Spirited", None, kills, now=NOW)["kills"] == []   # faction unknown: nothing shown
    finally:
        fb._reference = None


class _Engine:
    def __init__(self, local=9940, name="Spirited", server=2102):
        self.local_player_id = local
        self.names = {local: name} if local is not None else {}
        self.local_profile = {"serverId": server} if server else {}
        self.roster = {}


def _runner(monkeypatch, tmp_path, engine, running=True, **ui):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.paths import write_user_json
    if ui:
        write_user_json(ui, "ui.json")
    from aion2calc.app.meter_runner import Runner
    r = Runner()
    r.running = running
    r.packet_engine = engine
    started = []
    monkeypatch.setattr(r, "_field_bosses_refresh", lambda *a: (started.append(a), setattr(r, "_field_bosses_busy", False)))
    return r, started


def _wait(started):
    for _ in range(100):
        if started:
            return True
        time.sleep(0.005)
    return False


def test_runner_reads_the_feed_once_the_local_player_and_server_are_known(monkeypatch, tmp_path):
    r, started = _runner(monkeypatch, tmp_path, _Engine())
    r._maybe_field_bosses()
    assert _wait(started) and started[0][:2] == ("Spirited", "2102")
    started.clear()
    r._maybe_field_bosses()                                     # too soon: the refresh interval holds
    assert not _wait(started)
    r._field_bosses_at = 0.0
    r._maybe_field_bosses()
    assert _wait(started)


def test_runner_waits_for_identity_and_respects_the_strip_setting(monkeypatch, tmp_path):
    r, started = _runner(monkeypatch, tmp_path, _Engine(local=None))
    r._maybe_field_bosses()
    assert not _wait(started)                                   # no local player yet
    r, started = _runner(monkeypatch, tmp_path, _Engine(server=None))
    r._maybe_field_bosses()
    assert not _wait(started)                                   # no home server yet
    r, started = _runner(monkeypatch, tmp_path, _Engine(), overlay_show_events=False)
    r._maybe_field_bosses()
    assert not _wait(started)                                   # strip off: nothing read


def test_runner_keeps_refreshing_the_last_identity_while_stopped(monkeypatch, tmp_path):
    r, started = _runner(monkeypatch, tmp_path, None, running=False)
    r._field_bosses = {"server": "2102", "character": "Spirited", "faction": "asmodian", "kills": []}
    r._maybe_field_bosses()
    assert _wait(started) and started[0][:2] == ("Spirited", "2102")


def test_snapshot_and_pages_are_wired():
    assert 'snap["field_bosses"] = self._field_bosses' in RUNNER
    assert 'status["faction"]' in RUNNER
    # Overlay: observed kills join the strip, labelled as observed, with their own grace window.
    assert "observedBossEvents" in OVERLAY and "snapshot.field_bosses" in OVERLAY
    assert "OBSERVED_GRACE_MS" in OVERLAY and "ovobserved" in OVERLAY and "not Discord timers" in OVERLAY
    assert "if(!region&&!observed.length)" in OVERLAY           # the strip shows observed kills even without a region
    # Timers page: faction filter, identity line, the identified server as the default, map-based zone split.
    assert "data-kill-faction" in TIMERS and "Mine (from the live meter)" in TIMERS
    assert "loadIdentity" in TIMERS and "io.identity" in TIMERS and "ZONE_MAPS" in TIMERS
    assert "Discord bot's manual timers are never used" in TIMERS
    assert "identity:async()=>{const m=await api('/api/meter?view=latest')" in APP
