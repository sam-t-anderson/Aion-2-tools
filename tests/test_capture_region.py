"""Region + world-name resolution for capture metadata.

The automatic region is derived from the recorded server ID against the official
server list, and the world/server name is captured from that same list so reports
can show "server 2102 (Nezekan)" rather than a bare ID. These guard that parsing,
the cache round-trip (names included), the force/refresh bypass, and the snapshot.
No real network or app data dir is touched — both are monkeypatched.
"""
import json
import threading

from aion2calc.meter import metadata as M


class _FakeResponse:
    def __init__(self, payload):
        self._bytes = json.dumps(payload).encode("utf-8")

    def read(self, *a):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# One distinct server per region so a given ID resolves to exactly one region, each
# carrying a human-readable name under the common "serverName" key.
_SERVERS = {"nae": ("2102", "Nezekan"), "eu": ("3001", "Siel"),
            "as": ("4001", "Israphel"), "la": ("5001", "Kahrun")}


def _fake_urlopen(request, timeout=0):
    url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
    region = url.rsplit("region=", 1)[-1]
    sid, name = _SERVERS[region]
    return _FakeResponse({"serverList": [{"serverId": int(sid), "serverName": name}]})


def _bare_instance():
    """A CaptureMetadata without running __init__ (which would spawn a network thread)."""
    obj = object.__new__(M.CaptureMetadata)
    obj.lock = threading.Lock()
    obj.build = {"status": "ready"}
    obj.regions = {}
    obj.names = {}
    obj.region_status = "detecting"
    return obj


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(M.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(M, "user_data", lambda: tmp_path)


def test_collect_regions_captures_ids_and_world_names(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    obj = _bare_instance()
    obj._collect_regions(force=True)
    assert obj.region_status == "ready"
    assert obj.regions["nae"] == ["2102"] and obj.regions["eu"] == ["3001"]
    assert obj.names["2102"] == "Nezekan" and obj.names["4001"] == "Israphel"


def test_snapshot_resolves_region_and_world_name(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    obj = _bare_instance()
    obj._collect_regions(force=True)
    snap = obj.snapshot("2102")
    assert snap["region"] == "nae" and snap["server_name"] == "Nezekan"
    assert snap["region_source"]
    # An unknown server resolves neither (and never raises).
    unknown = obj.snapshot("999999")
    assert unknown["region"] is None and unknown["server_name"] is None


def test_cache_round_trip_preserves_names(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    cache = tmp_path / "cache" / "capture-server-regions.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": __import__("time").time(),
                                 "regions": {r: [s] for r, (s, _) in _SERVERS.items()},
                                 "names": {"2102": "Nezekan"}}), encoding="utf-8")
    obj = _bare_instance()
    # Not forced: it must load the cache (names included) without any fetch.
    monkeypatch.setattr(M.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch when cache is fresh")))
    obj._collect_regions(force=False)
    assert obj.region_status == "ready" and obj.names["2102"] == "Nezekan"


def test_force_bypasses_a_fresh_cache(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    cache = tmp_path / "cache" / "capture-server-regions.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    # A cache that would otherwise be used, with a stale name for 2102.
    cache.write_text(json.dumps({"fetched_at": __import__("time").time(),
                                 "regions": {r: [s] for r, (s, _) in _SERVERS.items()},
                                 "names": {"2102": "OldName"}}), encoding="utf-8")
    obj = _bare_instance()
    obj._collect_regions(force=True)   # ignore the cache and re-fetch
    assert obj.names["2102"] == "Nezekan"   # fresh value, not the cached "OldName"


def test_refresh_sets_detecting_and_reresolves(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    obj = _bare_instance()
    obj.region_status = "unavailable"
    snap = obj.refresh()
    assert isinstance(snap, dict) and "region_status" in snap
    # The background fetch resolves shortly after.
    for _ in range(200):
        if obj.region_status == "ready":
            break
        __import__("time").sleep(0.01)
    assert obj.region_status == "ready" and obj.names.get("2102") == "Nezekan"
