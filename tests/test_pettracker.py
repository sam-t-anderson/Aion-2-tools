"""Pet Tracker inside Aion 2 Calc (0.2.337). Pet Tracker is 0Fox2Give's separate GPL-3.0 program, used with its
author's permission. Aion 2 Calc installs it on request, starting its installer only once it matches the release
its publisher signed, drives its capture worker over the worker's named-pipe protocol (one JSON command per
connection, one JSON view back), and draws its pets in a separate overlay window and an app page, with the
rules Pet Tracker's own overlay uses (``Activity.Select``)."""
import base64
import hashlib
import io
import json
import os
import pathlib
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from aion2calc.app import overlay_launch, pettracker as pt, pettracker_setup as setup, server
from aion2calc.overlay_health import RelaunchLimiter

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)

#: Pet Tracker's real signed release feed (releases.win-stable.signed.json, published 23 Oct 2026, valid to 22 Nov):
#: public release metadata (0.1.57), signed with the key Pet Tracker's updater pins: the payload and its P1363 signature.
LIVE_PAYLOAD = (
    "eyJBcHBJZCI6IlBldFRyYWNrZXIuRGVza3RvcCIsIkNoYW5uZWwiOiJ3aW4tc3RhYmxlIiwiUHVibGlzaGVkVXRjIjoiMjAyNi0x"
    "MC0yM1QxMjozMToyNC40MDY3ODAzKzAwOjAwIiwiRXhwaXJlc1V0YyI6IjIwMjYtMTEtMjJUMTI6MzE6MjQuNDA2NzgwMyswMDow"
    "MCIsIkZlZWQiOiJ7XHUwMDIyQXNzZXRzXHUwMDIyOlt7XHUwMDIyUGFja2FnZUlkXHUwMDIyOlx1MDAyMlBldFRyYWNrZXIuRGVz"
    "a3RvcFx1MDAyMixcdTAwMjJWZXJzaW9uXHUwMDIyOlx1MDAyMjAuMS41N1x1MDAyMixcdTAwMjJUeXBlXHUwMDIyOlx1MDAyMkZ1"
    "bGxcdTAwMjIsXHUwMDIyRmlsZU5hbWVcdTAwMjI6XHUwMDIyUGV0VHJhY2tlci5EZXNrdG9wLTAuMS41Ny13aW4tc3RhYmxlLWZ1"
    "bGwubnVwa2dcdTAwMjIsXHUwMDIyU0hBMVx1MDAyMjpcdTAwMjJEMzU0MUU3ODZCNkUwMzk0QzU2OTFCOEZBREREQ0VGQzNCQTVD"
    "RDlFXHUwMDIyLFx1MDAyMlNIQTI1Nlx1MDAyMjpcdTAwMjIwMTMwRTNCQUQ4QzU0MkQ3RTVCNTY4RDg3MTA2MDhEQjU2RUZCMTlC"
    "MkRDRTVBRjk2QkEzMTRENTI5NjQ0MzlBXHUwMDIyLFx1MDAyMlNpemVcdTAwMjI6MTE5MzcyNjY2LFx1MDAyMk5vdGVzTWFya2Rv"
    "d25cdTAwMjI6XHUwMDIyUGV0IFRyYWNrZXIgMC4xLjU3XFxuXFxuTWVyY2hhbnQgc3RhdHVzIG5vdyBzdGF5cyB2aXNpYmxlIGlu"
    "IFNldHRpbmdzIFx1MDAzRSBUcmFja2luZyBhZnRlciBjb2xsZWN0aW9uIHN5bmMuIEl0IHNob3dzIHdoZXRoZXIgc2hvcCBzdG9j"
    "ayB3YXMgcmVjZWl2ZWQgYW5kIGhvdyBtYW55IHBldHMgcXVhbGlmeS5cXG5cXG5TdXBwb3J0IHJlcG9ydHMgbm93IGluY2x1ZGUg"
    "Y29sbGVjdGlvbiBzeW5jIGFuZCBtZXJjaGFudCBzdG9jayBjb3VudHMuIFRoZXkgc3RpbGwgZXhjbHVkZSBwZXQgbGlzdHMsIGNo"
    "YXJhY3RlciBuYW1lcyBhbmQgcGFja2V0IGRhdGEuXFxuXFxuVGhpcyB1cGRhdGUgaW1wcm92ZXMgdHJvdWJsZXNob290aW5nLiBN"
    "aXNzaW5nIG9yIGRpc2FwcGVhcmluZyBtZXJjaGFudCByZWNvbW1lbmRhdGlvbnMgcmVtYWluIHVuZGVyIGludmVzdGlnYXRpb24u"
    "XHUwMDIyLFx1MDAyMk5vdGVzSFRNTFx1MDAyMjpcdTAwMjJcdTAwM0NwXHUwMDNFUGV0IFRyYWNrZXIgMC4xLjU3XHUwMDNDL3Bc"
    "dTAwM0VcXG5cdTAwM0NwXHUwMDNFTWVyY2hhbnQgc3RhdHVzIG5vdyBzdGF5cyB2aXNpYmxlIGluIFNldHRpbmdzIFx1MDAyNmd0"
    "OyBUcmFja2luZyBhZnRlciBjb2xsZWN0aW9uIHN5bmMuIEl0IHNob3dzIHdoZXRoZXIgc2hvcCBzdG9jayB3YXMgcmVjZWl2ZWQg"
    "YW5kIGhvdyBtYW55IHBldHMgcXVhbGlmeS5cdTAwM0MvcFx1MDAzRVxcblx1MDAzQ3BcdTAwM0VTdXBwb3J0IHJlcG9ydHMgbm93"
    "IGluY2x1ZGUgY29sbGVjdGlvbiBzeW5jIGFuZCBtZXJjaGFudCBzdG9jayBjb3VudHMuIFRoZXkgc3RpbGwgZXhjbHVkZSBwZXQg"
    "bGlzdHMsIGNoYXJhY3RlciBuYW1lcyBhbmQgcGFja2V0IGRhdGEuXHUwMDNDL3BcdTAwM0VcXG5cdTAwM0NwXHUwMDNFVGhpcyB1"
    "cGRhdGUgaW1wcm92ZXMgdHJvdWJsZXNob290aW5nLiBNaXNzaW5nIG9yIGRpc2FwcGVhcmluZyBtZXJjaGFudCByZWNvbW1lbmRh"
    "dGlvbnMgcmVtYWluIHVuZGVyIGludmVzdGlnYXRpb24uXHUwMDNDL3BcdTAwM0VcdTAwMjJ9XX0iLCJJbnN0YWxsZXJTSEEyNTYi"
    "OiIxQjYzQjRBQkU5OUMwQkFCMjlCQ0RGNUM3MDFEN0MxQTRDNTRFOTExNDM1NjJGRjMwNTkzREUwQkM5ODg5MkIwIn0=")
LIVE_SIGNATURE = "ps+eO1yPFs04ly5AqQ2PaZ23Wyygc3nLCLSdZ7RCfBS5BXLQLTTDkFUyjX6XyewgjX2be3OFh0uiGTqnTiceog=="
LIVE_FEED = json.dumps({"Payload": LIVE_PAYLOAD, "Signature": LIVE_SIGNATURE}).encode()
LIVE_INSTALLER_SHA256 = "1b63b4abe99c0bab29bcdf5c701d7c1a4c54e91143562ff30593de0bc98892b0"


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", ".1234567+00:00")


# ------------------------------------------------------------------ the signed release and the installer

def test_pet_trackers_real_signed_feed_verifies_with_its_pinned_key():
    release = setup.verify_feed(LIVE_FEED, now=NOW)
    assert release["installer_sha256"] == LIVE_INSTALLER_SHA256
    assert release["version"] == "0.1.57"
    assert release["published"].startswith("2026-10-23T12:31:24") and release["expires"].startswith("2026-11-22")


def test_a_changed_feed_or_another_key_is_refused():
    doc = json.loads(LIVE_FEED)
    payload = base64.b64decode(doc["Payload"]).replace(b'"InstallerSHA256":"1B', b'"InstallerSHA256":"2B')
    forged = json.dumps({"Payload": base64.b64encode(payload).decode(), "Signature": doc["Signature"]}).encode()
    with pytest.raises(setup.SetupError, match="not signed by its publisher"):
        setup.verify_feed(forged, now=NOW)
    signature = bytearray(base64.b64decode(doc["Signature"]))
    signature[5] ^= 1
    with pytest.raises(setup.SetupError, match="not signed by its publisher"):
        setup.verify_feed(json.dumps({"Payload": doc["Payload"], "Signature": base64.b64encode(bytes(signature)).decode()}).encode(), now=NOW)
    # a valid P-256 key that is not the publisher's: the curve's generator point as a public key
    der = setup._SPKI_P256 + b"\x04" + setup._G[0].to_bytes(32, "big") + setup._G[1].to_bytes(32, "big")
    other = "-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(der).decode() + "\n-----END PUBLIC KEY-----"
    with pytest.raises(setup.SetupError, match="not signed by its publisher"):
        setup.verify_feed(LIVE_FEED, now=NOW, key_pem=other)
    with pytest.raises(setup.SetupError, match="expired or is not valid yet"):
        setup.verify_feed(LIVE_FEED, now=datetime(2026, 12, 1, tzinfo=timezone.utc))
    with pytest.raises(setup.SetupError):
        setup.verify_feed(b"not json", now=NOW)
    with pytest.raises(setup.SetupError, match="too large"):
        setup.verify_feed(b" " * (setup.MAX_FEED_BYTES + 1), now=NOW)


def test_the_publisher_key_must_be_an_uncompressed_p256_point():
    assert setup._on_curve(setup.public_key_point(setup.PUBLIC_KEY_PEM))
    with pytest.raises(setup.SetupError):
        setup.public_key_point("-----BEGIN PUBLIC KEY-----\n" + base64.b64encode(b"\x30" * 91).decode() + "\n-----END PUBLIC KEY-----")


@pytest.fixture
def signer():
    """Sign test releases with a throwaway P-256 key (needs the cryptography package, as a development tool)."""
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def sign(message: bytes) -> bytes:
        r, s = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    def feed(**release) -> bytes:
        body = {"AppId": "PetTracker.Desktop", "Channel": "win-stable", "PublishedUtc": _iso(NOW - timedelta(days=2)),
                "ExpiresUtc": _iso(NOW + timedelta(days=28)), "InstallerSHA256": "AB" * 32,
                "Feed": json.dumps({"Assets": [{"Version": "0.1.9"}, {"Version": "0.1.58"}]})}
        body.update(release)
        payload = json.dumps({k: v for k, v in body.items() if v is not None}).encode()
        return json.dumps({"Payload": base64.b64encode(payload).decode(), "Signature": base64.b64encode(sign(payload)).decode()}).encode()
    return type("Signer", (), {"pem": pem, "sign": staticmethod(sign), "feed": staticmethod(feed)})


def test_signatures_made_by_a_standard_library_verify(signer):
    point = setup.public_key_point(signer.pem)
    for size in (0, 1, 33, 500):
        message = bytes(range(256)) * 2
        message = message[:size]
        signature = signer.sign(message)
        assert setup.verify_signature(point, message, signature)
        assert not setup.verify_signature(point, message + b"x", signature)
        assert not setup.verify_signature(point, message, signature[:-1])


def test_the_signed_release_must_name_pet_tracker_and_be_in_date(signer):
    assert setup.verify_feed(signer.feed(), now=NOW, key_pem=signer.pem)["version"] == "0.1.58"   # newest listed
    for change, words in (({"AppId": "Someone.Else"}, "different program"), ({"Channel": "win-beta"}, "different program"),
                          ({"ExpiresUtc": _iso(NOW - timedelta(minutes=1))}, "expired"),
                          ({"PublishedUtc": _iso(NOW + timedelta(hours=1))}, "not valid yet"),
                          ({"PublishedUtc": _iso(NOW - timedelta(days=100))}, "expired"),
                          ({"InstallerSHA256": None}, "checksum"), ({"InstallerSHA256": "12"}, "checksum")):
        with pytest.raises(setup.SetupError, match=words):
            setup.verify_feed(signer.feed(**change), now=NOW, key_pem=signer.pem)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def test_a_download_is_kept_only_when_its_checksum_matches(tmp_path):
    data = b"installer bytes" * 1000
    good = hashlib.sha256(data).hexdigest()
    opener = lambda request, timeout=0: _Response(data)
    target = setup.download_verified("https://example.invalid/setup.exe", tmp_path / "setup.exe", good.upper(), opener=opener)
    assert target.read_bytes() == data
    with pytest.raises(setup.SetupError, match="does not match its signed checksum"):
        setup.download_verified("https://example.invalid/setup.exe", tmp_path / "other.exe", "0" * 64, opener=opener)
    with pytest.raises(setup.SetupError, match="larger than expected"):
        setup.download_verified("https://example.invalid/setup.exe", tmp_path / "big.exe", good, limit=100, opener=opener)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["setup.exe"]          # no partial file is left behind


class _Proc:
    def __init__(self, code=0):
        self.code = code

    def wait(self, timeout=None):
        return self.code


def test_install_verifies_downloads_and_starts_the_installer(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    data = b"MZ fake setup"
    release = {"installer_sha256": hashlib.sha256(data).hexdigest(), "version": "0.1.58", "published": "", "expires": ""}
    monkeypatch.setattr(setup, "verify_feed", lambda envelope, now=None: release)
    urls, started = [], []

    def opener(request, timeout=0):
        urls.append(request.full_url)
        return _Response(b"{}" if request.full_url.endswith(".json") else data)
    folder = tmp_path / "downloads" / "pettracker"
    folder.mkdir(parents=True)
    (folder / "PetTracker-0.1.50-Setup.exe").write_bytes(b"an older download")
    result = setup.install(wait=5, opener=opener, start=lambda path: started.append((path, path.read_bytes())) or _Proc(0))
    assert result["status"] == "installed" and result["version"] == "0.1.58" and result["error"] is None
    assert urls == [setup.FEED_ROOT + setup.SIGNED_FEED, setup.FEED_ROOT + setup.SETUP_NAME]
    assert started[0][0].name == "PetTracker-0.1.58-Setup.exe" and started[0][1] == data
    assert list(folder.iterdir()) == []                                              # installed: nothing is left
    assert setup.install(opener=opener, start=lambda path: None)["status"] == "started"      # Windows' own prompt
    assert [p.name for p in folder.iterdir()] == ["PetTracker-0.1.58-Setup.exe"]      # still in use: kept
    assert setup.install(wait=5, opener=opener, start=lambda path: _Proc(3))["error"] == "Pet Tracker's installer ended with code 3."
    monkeypatch.setattr(setup, "verify_feed", lambda envelope, now=None: dict(release, installer_sha256="0" * 64))
    failed = setup.install(wait=5, opener=opener, start=lambda path: started.append((path, b"")) or _Proc(0))
    assert failed["status"] == "error" and "does not match" in failed["error"] and len(started) == 1


def test_install_from_the_app_does_not_start_twice(monkeypatch):
    monkeypatch.setitem(setup._STATE, "status", "downloading")
    monkeypatch.setattr(setup.threading, "Thread", lambda *a, **k: pytest.fail("a second install started"))
    assert setup.begin_install()["status"] == "downloading"


# ------------------------------------------------------------------ finding Pet Tracker and its pipe

def _program(folder: pathlib.Path, version: str | None = None) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / pt.APP_EXE).write_bytes(b"MZ")
    (folder / pt.WORKER_EXE).write_bytes(b"MZ")
    if version:
        (folder / "sq.version").write_text(f"<package><metadata><version>{version}</version></metadata></package>", encoding="utf-8")
    return folder


def test_pet_tracker_is_found_where_its_installers_put_it(tmp_path):
    local = tmp_path / "Local"
    assert pt.find_install("", str(local)) is None
    _program(local / "Programs" / "PetTracker")
    assert pt.find_install("", str(local))["kind"] == "offline"
    _program(local / "PetTracker.Desktop" / "current", "0.1.57")
    found = pt.find_install("", str(local))
    assert found["kind"] == "installer" and found["version"] == "0.1.57" and found["worker"].endswith(pt.WORKER_EXE)
    portable = _program(tmp_path / "Portable")
    assert pt.find_install(str(portable), str(local))["kind"] == "custom"            # a folder picked in Settings comes first
    (portable / pt.WORKER_EXE).unlink()
    assert pt.find_install(str(portable), str(local))["kind"] == "installer"         # both programs are needed


def test_the_pipe_name_is_pet_trackers_storage_pipe():
    root = r"C:\Users\Sam\AppData\Local\PetTracker"
    expected = "PetTracker-" + hashlib.sha256(("Sam" + root.upper()).encode("utf-8")).hexdigest().upper()[:20]
    assert pt.pipe_name(root, "Sam") == expected
    for spelling in (root + "\\", root.lower(), "C:/Users/Sam/AppData/Local/PetTracker", r"C:\Users\Sam\AppData\Local\.\PetTracker"):
        assert pt.pipe_name(spelling, "Sam") == expected                            # GetFullPath, trimmed, in capitals
    assert pt.pipe_name(root, "Alex") != expected                                   # the user name is part of it
    assert pt._upper_invariant("Straße") == "STRAßE"                                # .NET keeps ß; Python would write SS


# ------------------------------------------------------------------ the protocol

def _view(**overrides) -> dict:
    def pet(i, name, category, level, souls, goal, **extra):
        return {"Id": i, "CatalogName": name.replace(" ", "") + "_01", "DisplayName": name, "Category": category,
                "Level": level, "LevelVerified": True, "Souls": souls, "Goal": goal, "CounterVerified": True, **extra}
    view = {"Protocol": 3, "Ready": True, "CollectionSynced": True, "Status": "Live", "Detail": "Receiving soul updates.",
            "Character": "Ranger", "Devices": 1, "Received": 1000, "Dropped": 0,
            "Profile": {"Pets": {"1001": pet(1001, "Black Dragon", "Special", 2, 72, 75),
                                 "1002": pet(1002, "Krall Laborer", "Intellect", 3, None, None),
                                 "1003": pet(1003, "Forest Specter", "Nature", 0, 3, 5),
                                 "1004": pet(1004, "Fossa", "Feral", 1, 10, 25, TargetRank=3),
                                 "1005": pet(1005, "Klaw", "Trans", 1, 20, 25)}},
            "Recent": [{"PetId": 1003, "NpcId": 5, "CreatureName": "Wisp", "SeenUtc": _iso(NOW - timedelta(seconds=5)), "IsNearby": False},
                       {"PetId": 1002, "NpcId": 6, "CreatureName": "Krall", "SeenUtc": _iso(NOW - timedelta(seconds=2)), "IsNearby": False},
                       {"PetId": 1005, "NpcId": 8, "CreatureName": "Neuth", "SeenUtc": _iso(NOW - timedelta(seconds=9)), "IsNearby": False},
                       {"PetId": 1001, "NpcId": 7, "CreatureName": "Drake", "SeenUtc": _iso(NOW - timedelta(seconds=40)), "IsNearby": False}],
            "Nearby": [], "Increase": None,
            "Settings": {"TrackerMode": "Recent", "PinnedPetIds": [], "RowLimit": 5, "InactiveSeconds": 20,
                         "ExpireInactive": True, "Sort": "Unfinished first", "NearbyStaleSeconds": 60, "PinLimit": 3},
            "Farming": {"StartedUtc": _iso(NOW - timedelta(minutes=10)), "Incomplete": False,
                        "Pets": [{"PetId": 1003, "Souls": 3, "RankUps": 0}, {"PetId": 1004, "Souls": 5, "RankUps": 1}]}}
    for key, value in overrides.items():
        if key in view["Settings"] or key in ("PinnedPetId", "HideMaxed", "Visible"):
            view["Settings"][key] = value
        else:
            view[key] = value
    return view


def test_the_client_sends_one_json_line_and_reads_one_view():
    sent = []

    def request(name, line, timeout):
        sent.append((name, line))
        return json.dumps(_view()).encode() + b"\r\n"
    client = pt.Client([r"C:\U\PetTracker"], "Sam", request)
    view = client.send({"Action": "pin", "PetId": 1003})
    assert view["Protocol"] == 3
    name, line = sent[0]
    assert name == pt.pipe_name(r"C:\U\PetTracker", "Sam") and line.endswith(b"\n") and line.count(b"\n") == 1
    assert json.loads(line) == {"Action": "pin", "PetId": 1003}                     # Pet Tracker's own key names


def test_the_client_tries_each_data_folder_and_remembers_the_one_that_answers():
    tried = []

    def request(name, line, timeout):
        tried.append(name)
        if name == pt.pipe_name(r"C:\A\PetTracker", "Sam"):
            raise pt.NotRunning("no worker here")
        return json.dumps(_view()).encode()
    client = pt.Client([r"C:\A\PetTracker", r"C:\B\PetTracker"], "Sam", request)
    client.send({"Action": "status"})
    client.send({"Action": "status"})
    second = pt.pipe_name(r"C:\B\PetTracker", "Sam")
    assert tried == [pt.pipe_name(r"C:\A\PetTracker", "Sam"), second, second]
    with pytest.raises(pt.NotRunning):
        pt.Client([r"C:\A\PetTracker"], "Sam", request).send({"Action": "status"})


def test_worker_errors_and_other_protocols_are_reported_in_words():
    with pytest.raises(pt.PetTrackerError, match="Pin limit reached"):
        pt.parse_answer(b'{"Error":"Pin limit reached. Unpin a pet or raise the limit in Settings > Tracking."}')
    with pytest.raises(pt.Unsupported, match="protocol 4"):
        pt.parse_answer(json.dumps({"Protocol": 4}).encode())
    with pytest.raises(pt.PetTrackerError, match="could not be read"):
        pt.parse_answer(b"\x00garbage")


# ------------------------------------------------------------------ the rows, as Pet Tracker's overlay shows them

def _ids(view, now=NOW):
    return [a["PetId"] for a in pt.select_activities(view, now)]


def test_recent_rewards_are_listed_newest_first_and_expire():
    # 1001's reward is 40 s old, past the 20 s inactive time; the maxed 1002 comes after the unmaxed ones
    assert _ids(_view()) == [1003, 1005, 1002]
    assert _ids(_view(ExpireInactive=False)) == [1003, 1005, 1001, 1002]
    assert _ids(_view(HideMaxed=True)) == [1003, 1005]
    assert _ids(_view(InactiveSeconds=60)) == [1003, 1005, 1001, 1002]


def test_pinned_pets_lead_in_pinned_order_and_leave_room_for_one_more():
    assert _ids(_view(PinnedPetIds=[1004, 1002])) == [1004, 1002, 1003, 1005]       # 1004 has no reward: still listed
    assert _ids(_view(PinnedPetIds=[1004, 1002], RowLimit=3)) == [1004, 1002, 1003]
    assert _ids(_view(PinnedPetIds=[1004, 1002, 1001], RowLimit=3)) == [1004, 1002, 1001, 1003]   # pins + 1
    assert _ids(_view(PinnedPetIds=[9999])) == [1003, 1005, 1002]                    # a pin that is no pet is ignored
    assert _ids(_view(PinnedPetIds=None, PinnedPetId=1004)) == [1004, 1003, 1005, 1002]   # the older single pin


def test_the_sort_orders():
    assert _ids(_view(Sort="Recent only", ExpireInactive=False)) == [1002, 1003, 1005, 1001]
    # closest to the next rank: 1001 at 72/75, 1005 at 20/25, 1003 at 3/5; maxed last
    assert _ids(_view(Sort="Closest to next rank", ExpireInactive=False)) == [1001, 1005, 1003, 1002]


def test_nearby_mode_lists_fresh_sightings_with_how_fresh_they_are():
    nearby = [{"PetId": 1005, "CreatureName": "Neuth", "SeenUtc": _iso(NOW - timedelta(seconds=30))},
              {"PetId": 1001, "CreatureName": "Drake", "SeenUtc": _iso(NOW - timedelta(seconds=5))},
              {"PetId": 1004, "CreatureName": "Fossa", "SeenUtc": _iso(NOW - timedelta(seconds=90))}]   # stale at 60 s
    view = _view(TrackerMode="Nearby", Nearby=nearby, PinnedPetIds=[1003])
    assert _ids(view) == [1003, 1001, 1005]                                          # by name, not by freshness
    rows = {r["id"]: r for r in pt.render(view, NOW)["rows"]}
    # whole seconds, rounded down as Pet Tracker does: _iso puts this sighting 29.88 s ago
    assert rows[1005]["notice"] == "Last seen 29s ago" and rows[1001]["notice"] == ""
    assert rows[1003]["notice"] == "Pinned · Not currently observed"
    assert pt.render(_view(TrackerMode="Nearby"), NOW)["empty"] == "No pet mobs detected nearby. Explore to discover more."


def test_each_row_reads_as_pet_trackers_overlay():
    view = _view(PinnedPetIds=[1004], Increase={"PetId": 1005, "Rank": 1, "SeenUtc": _iso(NOW - timedelta(seconds=5))})
    view["Profile"]["Pets"]["1003"].update(ProgressNeedsSync=True, Souls=5)           # unlocked, waiting for the game
    view["Profile"]["Pets"]["1001"].update(EstimatedSouls=74)
    rows = {r["id"]: r for r in pt.render(dict(view, Recent=view["Recent"]), NOW)["rows"]}
    fossa, specter, klaw, krall = rows[1004], rows[1003], rows[1005], rows[1002]
    assert (fossa["family"], fossa["rank_text"], fossa["progress"], fossa["ratio"], fossa["notice"]) == ("Fera", "Rank 1", "10 / 25", 0.4, "Pinned")
    assert fossa["goal_text"] == "90 souls to Rank 3" and fossa["remaining"] == 15
    assert (specter["rank_text"], specter["notice"], specter["paused"]) == ("Unranked", "Rank increase pending", True)
    assert klaw["notice"] == "Rank increased" and klaw["family"] == "Varian"
    assert (krall["max"], krall["progress"], krall["rank_text"]) == (True, "MAX", "Rank 3")
    expired = pt.render(dict(view, Recent=view["Recent"], Increase={"PetId": 1005, "Rank": 1, "SeenUtc": _iso(NOW - timedelta(seconds=25))}), NOW)
    assert {r["id"]: r for r in expired["rows"]}[1005]["notice"] == ""                # "Rank increased" lasts 20 s
    estimated = pt.render(_view(ExpireInactive=False, Recent=view["Recent"], Profile=view["Profile"]), NOW)["rows"]
    dragon = next(r for r in estimated if r["id"] == 1001)
    assert dragon["estimated"] and dragon["progress"] == "74 / 75" and dragon["remaining"] is None


def test_what_the_overlay_says_when_it_lists_nothing():
    assert pt.empty_text(_view(Ready=False, Status="Waiting for Aion 2"), NOW) == "Waiting for Aion 2"
    assert pt.empty_text(_view(Recent=[]), NOW) == "Recent pet rewards will appear here."
    assert pt.empty_text(_view(Recent=[], Status="Collection sync needed"), NOW).startswith("Connected. Waiting for collection totals")
    only_maxed = [{"PetId": 1002, "SeenUtc": _iso(NOW - timedelta(seconds=2))}]
    assert pt.empty_text(_view(Recent=only_maxed, HideMaxed=True), NOW) == "Recent pets are maxed. Turn off Hide maxed to see them."
    old = [{"PetId": 1003, "SeenUtc": _iso(NOW - timedelta(minutes=5))}]
    assert pt.empty_text(_view(Recent=old), NOW) == ""                                # rows that just expired leave it blank
    paused = pt.render(_view(CollectionSynced=False, Status="Collection sync needed"), NOW)
    assert paused["sync_notice"] is True and all(r["paused"] for r in paused["rows"])


KEY = "0123456789abcdef01234567"
ACCOUNT = {"ProfileKey": KEY, "AccountName": "Main account", "CharacterName": "Ranger", "LinkedCharacters": ["Healer"], "RealmLabel": ""}


def test_a_character_pet_tracker_waits_to_link_to_its_account_is_named_with_the_way_to_link_it():
    waiting = _view(Ready=False, Status="Alt — link to account", Detail="Selected account: Main account. Open Settings > Account "
                    "> Manage accounts to link Alt or select another account.", DetectedCharacter="Alt", Profiles=[ACCOUNT], Selected=KEY)
    link = pt.link_needed(waiting)
    assert link == {"character": "Alt", "account": "Main account", "characters": ["Ranger", "Healer"], "key": KEY}
    shown = pt.render(waiting, NOW)
    assert shown["link"] == link and shown["rows"] == [] and shown["empty"].startswith("Alt is not linked to your Pet Tracker account Main account")
    other = dict(ACCOUNT, ProfileKey="f" * 24, AccountName="Second")
    assert pt.link_needed(dict(waiting, Profiles=[ACCOUNT, other]))["key"] is None       # several accounts: Pet Tracker chooses
    assert pt.link_needed(dict(waiting, DetectedCharacter="healer")) is None              # already one of the account's
    assert pt.link_needed(dict(waiting, Profiles=[dict(ACCOUNT, AccountName="")])) is None  # a character profile, not an account
    assert pt.link_needed(dict(waiting, Ready=True)) is None and pt.render(_view(), NOW)["link"] is None


def test_the_session_summary_and_collection():
    out = pt.render(_view(), NOW, collection=True)
    assert out["summary"] == {"total": 5, "collected": 4, "maxed": 1, "unknown": 0}
    assert out["session"]["souls"] == 8 and out["session"]["ranked"] == 1
    assert [p["name"] for p in out["session"]["pets"]] == ["Forest Specter", "Fossa"]
    assert [r["name"] for r in out["collection"]] == ["Black Dragon", "Forest Specter", "Fossa", "Klaw", "Krall Laborer"]
    assert out["options"]["mode"] == "Recent" and out["options"]["pin_limit"] == 3 and out["character"] == "Ranger"
    assert "collection" not in pt.render(_view(), NOW)


def test_names_and_farming_goals():
    assert pt.pet_name({"Id": 1, "CatalogName": "BlackDragon_01", "DisplayName": "Black Dragon"}) == "Black Dragon"
    assert pt.pet_name({"Id": 1, "CatalogName": "BlackDragon_01", "DisplayName": "Smaug"}) == "Smaug"
    assert pt.pet_name({"Id": 1, "CatalogName": "BlackDragon_01", "DisplayName": ""}) == "Black Dragon"
    assert pt.pet_name({"Id": 7}) == "Pet #7"
    pet = {"Id": 1, "Level": 1, "LevelVerified": True, "Souls": 20, "Goal": 25, "CounterVerified": True, "TargetRank": 2}
    assert pt.goal_text(pet, True) == "5 souls to Rank 2"
    assert pt.goal_text(dict(pet, Souls=24), True) == "1 soul to Rank 2"
    assert pt.goal_text(dict(pet, TargetRank=1), True) == "Rank 1 goal reached"
    assert pt.goal_text(pet, False) == "Goal: Rank 2 · waiting for collection sync"
    assert pt.goal_text(dict(pet, LevelVerified=False), True) == "Goal: Rank 2 · waiting for collection sync"
    assert pt.goal_text(dict(pet, TargetRank=None), True) == ""
    assert pt.souls_remaining(pet) == 5 and pt.souls_remaining(dict(pet, CounterVerified=False)) is None


# ------------------------------------------------------------------ the service the app runs

class FakePlatform:
    def __init__(self, local):
        self.local, self.procs, self.spawned, self.sent, self.paths = str(local), {}, [], [], {}
        self.versions, self.version_reads = {}, []
        self.view = _view()
        self.answers = []

    def local_appdata(self):
        return self.local

    def user_name(self):
        return "Sam"

    def processes(self):
        return dict(self.procs)

    def image_path(self, pid):
        return self.paths.get(pid)

    def file_version(self, path):
        self.version_reads.append(path)
        return self.versions.get(path)

    def spawn(self, args, cwd, hidden):
        self.spawned.append((args, cwd, hidden))

    def request(self, name, line, timeout):
        self.sent.append(json.loads(line))
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if pt.WORKER_EXE.lower() not in self.procs:
            raise pt.NotRunning("Pet Tracker's capture is not running.")
        return json.dumps(self.view).encode()


@pytest.fixture
def platform(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    plat = FakePlatform(tmp_path / "Local")
    clock = {"t": 1000.0}
    service = pt.Service(platform=plat, clock=lambda: clock["t"], now=lambda: NOW)
    service.background = lambda fn: None                                       # no update check reaches the network
    monkeypatch.setattr(pt, "_SERVICE", service)
    return plat, service, clock


def test_the_worker_starts_only_when_pet_tracker_is_on_and_installed(platform, tmp_path):
    plat, service, clock = platform
    assert service.ensure_worker() == "off"
    service.configure(True)
    assert service.ensure_worker() == "missing"
    folder = _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    assert service.ensure_worker() == "started"
    args, cwd, hidden = plat.spawned[0]
    root = str(tmp_path / "Local") + "\\PetTracker"
    assert args == [str(folder / pt.WORKER_EXE), "--data", root] and cwd == str(folder) and hidden
    assert service.ensure_worker() == "waiting"                                      # one launch per 15 s at most
    clock["t"] += 16
    plat.procs[pt.WORKER_EXE.lower()] = [42]
    assert service.ensure_worker() == "running" and len(plat.spawned) == 1
    assert pt.Service(platform=None).ensure_worker() == "unsupported"


def test_the_view_is_shared_for_a_moment_and_a_missing_worker_is_started(platform, tmp_path):
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    assert service.fetch() is None and len(plat.spawned) == 1                         # not running: started
    plat.procs[pt.WORKER_EXE.lower()] = [42]
    assert service.fetch() is None and len(plat.sent) == 1                           # the failure is shared for a moment
    clock["t"] += 1
    assert service.fetch()["Protocol"] == 3 and len(plat.sent) == 2
    clock["t"] += 0.5
    service.fetch()
    assert len(plat.sent) == 2                                                       # the overlay and the page share it
    clock["t"] += 1
    service.fetch()
    assert len(plat.sent) == 3
    state = service.state()
    assert state["connected"] and state["rows"] and state["installed"]["kind"] == "installer" and state["problem"] == ""
    plat.answers.append(pt.Unsupported("This Pet Tracker speaks protocol 4"))
    clock["t"] += 1
    failed = service.state()
    assert failed["connected"] is False and "protocol 4" in failed["problem"] and "rows" not in failed
    assert service.state() == failed and len(plat.sent) == 4
    clock["t"] += 1
    assert service.state()["connected"] and service.state()["problem"] == ""


def test_the_state_says_what_is_missing(platform, tmp_path):
    plat, service, clock = platform
    off = service.state()
    assert off["supported"] and off["installed"] is None and off["connected"] is False and "rows" not in off
    assert pt.Service(platform=None).state()["problem"] == "Pet Tracker runs on Windows only."
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    assert service.state()["installed"] is not None and plat.sent == []               # off: the worker is never asked


def test_the_capture_is_left_to_pet_trackers_own_window_and_its_updater(platform, tmp_path):
    plat, service, clock = platform
    folder = _program(tmp_path / "Local" / "PetTracker.Desktop" / "current", "0.1.57")
    service.configure(True)
    plat.procs[pt.APP_EXE.lower()] = [1]
    assert service.ensure_worker() == "owned" and plat.spawned == []           # its window starts its own capture
    assert service.state()["problem"] == "Pet Tracker's own window is running; waiting for it to start its capture."
    del plat.procs[pt.APP_EXE.lower()]                                         # it closed to install an update
    plat.procs["update.exe"] = [7, 8]
    plat.paths = {7: "C:\\Discord\\Update.exe", 8: str(folder.parent / "Update.exe")}
    assert service.ensure_worker() == "updating" and plat.spawned == []        # its updater replaces its files
    clock["t"] += 1
    assert service.state()["problem"] == "Pet Tracker is installing an update; its capture starts again when it finishes."
    plat.paths[8] = "C:\\Other\\Update.exe"                                    # another program's updater
    assert service.ensure_worker() == "deferred" and plat.spawned == []        # its window closed a moment ago
    clock["t"] += service.APP_GRACE
    assert service.ensure_worker() == "started" and len(plat.spawned) == 1


def test_a_capture_that_cannot_start_says_why(platform, tmp_path):
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    tries = []

    def blocked(args, cwd, hidden):
        tries.append(args)
        raise OSError(1260, "This program is blocked by group policy")
    plat.spawn = blocked
    state = service.state()
    assert state["connected"] is False and state["start"] == "failed" and len(tries) == 1
    assert state["problem"] == ("Windows did not start Pet Tracker's capture: This program is blocked by group policy. "
                                "If Smart App Control or your antivirus blocked it, allow Pet Tracker there.")
    clock["t"] += 1
    assert service.ensure_worker() == "failed" and len(tries) == 1             # tried again after the spacing only
    clock["t"] += service.LAUNCH_SPACING
    plat.spawn = lambda args, cwd, hidden: (_ for _ in ()).throw(FileNotFoundError(2, "No such file or directory"))
    service.ensure_worker()
    assert service.start_error.startswith("Pet Tracker's capture could not start: its program is missing")
    with pytest.raises(pt.PetTrackerError, match="Windows did not start Pet Tracker: Access is denied"):
        plat.spawn = lambda args, cwd, hidden: (_ for _ in ()).throw(OSError(5, "Access is denied"))
        service.launch_app()


def test_a_capture_that_stops_at_startup_shows_its_reason(platform, tmp_path):
    import os
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    assert service.state()["problem"] == "Starting Pet Tracker's capture…"
    data = pathlib.Path(service.roots()[0])
    data.mkdir(parents=True)
    note = data / "startup-error.json"
    note.write_text(json.dumps({"Error": "Npcap is not installed."}), encoding="utf-8")
    clock["t"] += 1
    state = service.state()
    assert state["problem"] == "Pet Tracker's capture stopped: Npcap is not installed." and state["start"] == "stopped"
    clock["t"] += service.LAUNCH_SPACING
    assert service.ensure_worker() == "waiting" and len(plat.spawned) == 1     # not every 15 s: a minute later
    clock["t"] += 3 * service.LAUNCH_SPACING
    os.utime(note, (service.launched_wall - 600, service.launched_wall - 600))  # written before the next start
    assert service.ensure_worker() == "started" and len(plat.spawned) == 2
    clock["t"] += 1
    assert service.state()["problem"] == "Starting Pet Tracker's capture…"     # an older note is not this start's
    plat.procs[pt.WORKER_EXE.lower()] = [9]
    plat.answers.append(pt.NotRunning("no pipe yet"))
    clock["t"] += 1
    assert service.state()["problem"] == "Waiting for Pet Tracker's capture to answer…"


def test_the_update_notice_compares_the_signed_release_with_the_installed_one(platform, tmp_path):
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current", "0.1.57")
    service.configure(True)
    plat.procs[pt.WORKER_EXE.lower()] = [2]
    asked = []
    service.background = lambda fn: fn()
    service.release_source = lambda: asked.append(1) or {"version": "0.1.58"}
    notice = service.state()["update"]
    assert notice == {"available": True, "latest": "0.1.58", "installed": "0.1.57", "kind": "installer",
                      "checked": NOW.isoformat(), "error": ""}
    service.state()
    assert len(asked) == 1                                                       # read again in six hours
    clock["t"] += service.UPDATE_EVERY
    service.state()
    assert len(asked) == 2

    def unreadable():
        raise setup.SetupError("Pet Tracker's release feed could not be read.")
    service.release_source = unreadable
    clock["t"] += service.UPDATE_EVERY
    failed = service.state()["update"]
    assert failed["available"] and failed["latest"] == "0.1.58" and failed["error"].startswith("Pet Tracker's release feed")
    service.release_source = lambda: {"version": "0.1.57"}
    clock["t"] += service.UPDATE_RETRY                                           # an hour after a failure
    assert service.state()["update"]["available"] is False                       # up to date
    assert pt.newer_version("0.1.10", "0.1.9") and not pt.newer_version("0.1.9", "0.1.10")
    assert not pt.newer_version("0.1.58", None) and not pt.newer_version(None, "0.1.57")   # unknown: no notice
    assert pt.Service(platform=None).state().get("update") is None


def test_a_copy_without_sq_version_takes_its_version_from_the_program(platform, tmp_path):
    plat, service, clock = platform
    app = str(_program(tmp_path / "Local" / "Programs" / "PetTracker") / pt.APP_EXE)   # Pet Tracker's offline installer
    plat.versions[app] = "0.1.56"
    service.configure(True)
    plat.procs[pt.WORKER_EXE.lower()] = [2]
    service.background = lambda fn: fn()
    service.release_source = lambda: {"version": "0.1.58"}
    state = service.state()
    assert state["installed"]["version"] == "0.1.56"
    assert state["update"] == {"available": True, "latest": "0.1.58", "installed": "0.1.56", "kind": "offline",
                               "checked": NOW.isoformat(), "error": ""}
    reads = len(plat.version_reads)
    service.state()
    assert len(plat.version_reads) == reads                                      # read once while it is unchanged
    plat.versions[app] = "0.1.58"
    stat = os.stat(app)
    os.utime(app, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))               # installed over
    assert service.state()["update"]["available"] is False
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current", "0.1.58")      # the installer's copy has sq.version
    plat.version_reads.clear()
    assert service.state()["installed"] == {"kind": "installer", "version": "0.1.58",
                                            "folder": str(tmp_path / "Local" / "PetTracker.Desktop" / "current")}
    assert plat.version_reads == []


def test_the_update_button_hands_the_install_to_pet_trackers_own_updater(platform, tmp_path, monkeypatch):
    plat, service, clock = platform
    folder = _program(tmp_path / "Local" / "PetTracker.Desktop" / "current", "0.1.57")
    service.configure(True)
    message = service.open_for_update()
    assert plat.spawned[-1] == ([str(folder / pt.APP_EXE)], str(folder), False)  # opened for its updater
    assert message.startswith("Pet Tracker is opening") and "Updates → Download update → Restart to update" in message
    plat.procs[pt.APP_EXE.lower()] = [1]
    assert service.open_for_update().startswith("Pet Tracker is running: double-click") and len(plat.spawned) == 1
    installs = []
    monkeypatch.setattr(setup, "begin_install", lambda: installs.append(1))
    older = FakePlatform(tmp_path / "Older")
    _program(tmp_path / "Older" / "Programs" / "PetTracker")                      # the older offline installer's copy
    offline = pt.Service(platform=older, clock=lambda: clock["t"], now=lambda: NOW)
    assert offline.open_for_update().startswith("Installing the new Pet Tracker") and installs == [1]
    portable = _program(tmp_path / "Portable")
    mine = pt.Service(platform=FakePlatform(tmp_path / "None"), clock=lambda: clock["t"], now=lambda: NOW)
    mine.configure(True, str(portable))
    assert "folder of your own" in mine.open_for_update()
    with pytest.raises(pt.PetTrackerError, match="not installed"):
        pt.Service(platform=FakePlatform(tmp_path / "Empty")).open_for_update()


def test_quitting_stops_only_a_worker_this_app_started_and_no_one_else_uses(platform, tmp_path):
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    plat.procs[pt.WORKER_EXE.lower()] = [42]
    service.ensure_worker()
    service.shutdown()
    assert plat.sent == []                                                           # it was running already: left alone
    del plat.procs[pt.WORKER_EXE.lower()]
    service.ensure_worker()
    plat.procs[pt.WORKER_EXE.lower()] = [43]
    plat.procs[pt.APP_EXE.lower()] = [44]
    service.shutdown()
    assert plat.sent == []                                                           # Pet Tracker's window still uses it
    service.started_worker = True
    del plat.procs[pt.APP_EXE.lower()]
    service.shutdown()
    assert plat.sent == [{"Action": "exit"}] and service.started_worker is False


def test_pet_trackers_own_window_is_launched_or_follows_its_visible_setting(platform, tmp_path):
    plat, service, clock = platform
    folder = _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    assert service.show_own_window(True) == "launched"
    assert plat.spawned[-1] == ([str(folder / pt.APP_EXE)], str(folder), False)
    plat.procs.update({pt.APP_EXE.lower(): [1], pt.WORKER_EXE.lower(): [2]})
    assert service.launch_app() is False                                             # never a second copy
    assert service.show_own_window(False) == "hidden"
    assert plat.sent[-1] == {"Action": "patch", "Patch": {"Visible": False}}
    assert service.show_own_window(True) == "shown" and plat.sent[-1]["Patch"] == {"Visible": True}


def test_one_pet_overlay_shows_and_what_this_app_hid_is_put_back(platform, tmp_path):
    plat, service, clock = platform
    _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    service.configure(True)
    assert service.follow_overlay(True, False) == "not running" and plat.sent == []   # nothing to hide
    plat.procs.update({pt.APP_EXE.lower(): [1], pt.WORKER_EXE.lower(): [2]})
    assert service.follow_overlay(True, False) == "hidden"                            # Aion 2 Calc's window opened
    assert plat.sent[-1] == {"Action": "patch", "Patch": {"Visible": False}} and service.own_window == "hidden"
    plat.view["Settings"]["Visible"] = False
    count = len(plat.sent)
    assert service.follow_overlay(True, False) == "unchanged" and plat.sent[count:] == [{"Action": "status"}]
    assert service.follow_overlay(False, False) == "shown"                            # it closed: Pet Tracker's is back
    assert plat.sent[-1]["Patch"] == {"Visible": True} and service.own_window is None
    assert service.follow_overlay(False, False) == "unchanged"                        # it was never ours to hide
    plat.view["Settings"]["Visible"] = True
    service.follow_overlay(True, False)
    service.shutdown()                                                               # quitting puts it back too
    assert plat.sent[-1]["Patch"] == {"Visible": True} and service.own_window is None
    assert service.follow_overlay(False, True) == "shown" and service.own_window == "shown"   # its own window chosen
    assert service.follow_overlay(False, False) == "hidden" and plat.sent[-1]["Patch"] == {"Visible": False}
    del plat.procs[pt.APP_EXE.lower()]
    assert service.follow_overlay(False, True) == "launched" and plat.spawned[-1][2] is False


# ------------------------------------------------------------------ the app: settings, routes, the window

def test_settings_default_off_and_are_validated(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    ui = server.ui_settings()
    assert ui["pettracker_enabled"] is False and ui["pettracker_overlay"] is False
    assert ui["pettracker_overlay_style"] == "app" and ui["pettracker_path"] == ""


@pytest.fixture
def app(monkeypatch, tmp_path, platform):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    synced = []
    monkeypatch.setattr(server, "pettracker_sync", lambda: synced.append(server.ui_settings()))
    httpd = server.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()
    yield call, synced, platform
    httpd.shutdown()
    httpd.server_close()


def test_the_settings_endpoint_stores_pet_tracker_settings_and_syncs(app):
    call, synced, _ = app
    code, body = call("/api/ui", {"pettracker_enabled": True, "pettracker_overlay": True,
                                  "pettracker_overlay_style": "pettracker", "pettracker_path": "  C:\\Games\\PetTracker  "})
    saved = json.loads(body)
    assert code == 200 and saved["pettracker_enabled"] is True and saved["pettracker_overlay_style"] == "pettracker"
    assert saved["pettracker_path"] == "C:\\Games\\PetTracker" and len(synced) == 1
    for bad in ({"pettracker_enabled": "yes"}, {"pettracker_overlay_style": "both"}, {"pettracker_path": "relative\\folder"},
                {"overlay_pets_pos_x": 99999}):
        code, body = call("/api/ui", bad)
        assert code == 500 and (b"pettracker" in body or b"overlay_pets_pos_x" in body)
    call("/api/ui", {"overlay_pets_pos_x": 300, "overlay_pets_pos_y": 40, "overlay_pets_pos_layout": [[0, 0, 2560, 1440]]})
    assert server.ui_settings()["overlay_pets_pos_layout"] == [[0, 0, 2560, 1440]] and len(synced) == 1   # a drag does not resync


def test_the_pet_tracker_routes(app, tmp_path):
    call, synced, (plat, service, clock) = app
    code, body = call("/api/pettracker")
    assert code == 200 and json.loads(body)["enabled"] is False
    folder = _program(tmp_path / "Local" / "PetTracker.Desktop" / "current")
    (folder / "portraits").mkdir()
    (folder / "portraits" / "1001.png").write_bytes(b"\x89PNG portrait")
    service.configure(True)
    plat.procs[pt.WORKER_EXE.lower()] = [42]
    state = json.loads(call("/api/pettracker?collection=1")[1])
    assert state["connected"] and len(state["collection"]) == 5 and state["rows"][0]["portrait"] == "/api/pettracker/portrait/1003.png"
    assert call("/api/pettracker/portrait/1001.png") == (200, b"\x89PNG portrait")
    assert call("/api/pettracker/portrait/1002.png")[0] == 404
    assert call("/api/pettracker/portrait/..%2F..%2Fsecret.png")[0] == 404
    code, body = call("/api/pettracker", {"action": "pin", "pet": 1001, "value": True})
    assert code == 200 and plat.sent[-1] == {"Action": "pin", "PetId": 1001}
    call("/api/pettracker", {"action": "mode", "value": "Nearby"})
    assert plat.sent[-1] == {"Action": "patch", "Patch": {"TrackerMode": "Nearby"}}
    call("/api/pettracker", {"action": "goal", "pet": 1004, "rank": None})
    assert plat.sent[-1] == {"Action": "farming-goal", "PetId": 1004, "TargetRank": None}
    call("/api/pettracker", {"action": "reset_session"})
    assert plat.sent[-1] == {"Action": "reset-farming"}
    assert call("/api/pettracker", {"action": "link", "character": "Alt"})[0] == 400           # nothing waits to be linked
    plat.view = _view(Ready=False, Status="Alt — link to account", DetectedCharacter="Alt", Profiles=[ACCOUNT], Selected=KEY)
    assert call("/api/pettracker", {"action": "link", "character": "Someone"})[0] == 400       # the detected character changed
    code, body = call("/api/pettracker", {"action": "link", "character": "Alt"})
    assert code == 200 and plat.sent[-1] == {"Action": "link", "Key": KEY, "Name": "Alt"}
    plat.view = _view()
    plat.answers.append(json.dumps({"Error": "Pin limit reached. Unpin a pet or raise the limit in Settings > Tracking."}).encode())
    code, body = call("/api/pettracker", {"action": "pin", "pet": 1002, "value": True})
    assert code == 400 and json.loads(body) == {"error": "Pin limit reached. Unpin a pet or raise the limit in Settings > Tracking."}
    for bad in ({"action": "mode", "value": "Sideways"}, {"action": "pin", "pet": "x", "value": True},
                {"action": "goal", "pet": 1, "rank": 4}, {"action": "explode"}):
        assert call("/api/pettracker", bad)[0] == 500
    code, body = call("/api/pettracker", {"action": "update"})
    assert code == 200 and json.loads(body)["message"].startswith("Pet Tracker is opening")
    assert plat.spawned[-1][0] == [str(folder / pt.APP_EXE)]
    code, body = call("/overlay?view=pets")
    assert code == 200 and b"pet-overlay.js" in body
    assert b"overlay.js" in call("/overlay")[1] and b"pet-overlay.js" not in call("/overlay")[1]


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))                     # the app fixture's home too
    spawned = []

    class Proc:
        def __init__(self, url):
            self.url, self.returncode = url, None

        def poll(self):
            return self.returncode

        def wait(self):
            import time
            while self.returncode is None:
                time.sleep(0.01)
            return self.returncode

        def terminate(self):
            self.returncode = 1
    monkeypatch.setattr(overlay_launch, "_spawn", lambda url: spawned.append(Proc(url)) or spawned[-1])
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    monkeypatch.setattr(overlay_launch, "_party_enabled", lambda: False)
    monkeypatch.setattr(overlay_launch, "_radar_enabled", lambda: False)
    for slot in ("_PROCESS", "_PARTY_PROCESS", "_RADAR_PROCESS", "_PETS_PROCESS"):
        monkeypatch.setattr(overlay_launch, slot, None)
    monkeypatch.setattr(overlay_launch, "_RELAUNCHES", RelaunchLimiter())
    yield spawned
    overlay_launch.close()


def test_the_pet_tracker_window_follows_its_setting_alone(windows):
    url = "http://127.0.0.1:1/overlay?view=pets"
    assert overlay_launch.sync_pets(url, True) is True                              # no meter overlay needed
    assert [p.url for p in windows] == [url] and overlay_launch._PETS_PROCESS is windows[0]
    assert overlay_launch.sync_pets(url, True) is False and len(windows) == 1
    overlay_launch.sync_pets(url, False)
    assert windows[0].poll() is not None and overlay_launch._PETS_PROCESS is None
    overlay_launch.sync_pets(url, True)
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    overlay_launch.close_view("meter")                                               # the meter's Hide: everything closes
    assert all(p.poll() is not None for p in windows)
    overlay_launch.sync_pets(url, True)
    overlay_launch.close_view("pets")
    assert overlay_launch._PETS_PROCESS is None and windows[-1].poll() is not None


def test_hide_on_the_pet_tracker_window_turns_its_setting_off(app, windows):
    call, synced, _ = app
    call("/api/ui", {"pettracker_enabled": True, "pettracker_overlay": True})
    overlay_launch.sync_pets("http://127.0.0.1:1/overlay?view=pets", True)
    count = len(synced)
    code, body = call("/api/overlay", {"action": "hide", "view": "pets"})
    assert code == 200 and json.loads(body) == {"hidden": True} and len(synced) == count + 1   # puts Pet Tracker's back
    assert server.ui_settings()["pettracker_overlay"] is False and overlay_launch._PETS_PROCESS is None


def test_the_native_host_knows_the_pet_tracker_window(monkeypatch, tmp_path):
    from aion2calc import overlay
    from aion2calc.paths import write_user_json
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    write_user_json({"overlay_pets_pos_x": 120, "overlay_pets_pos_y": 80}, "ui.json")
    assert overlay._overlay_prefs()["positions"]["pets"] == {"xy": (120, 80), "layout": None}
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: sent.append(req) or _Response(b"{}"))
    overlay._save_overlay_position("http://127.0.0.1:1", "pets", (10, 20))
    assert json.loads(sent[0].data) == {"overlay_pets_pos_x": 10, "overlay_pets_pos_y": 20}
    src = (ROOT / "aion2calc" / "overlay.py").read_text(encoding="utf-8")
    assert '"pets": "Aion 2 Calc Pet Tracker"' in src and 'else "pets" if "view=pets" in url' in src
    assert 'if _view_key(party) == "pets":' in src                                 # first placed below the meter


def test_a_settings_backup_carries_the_switches_but_not_the_folder(monkeypatch, tmp_path):
    from aion2calc.app.settings_backup import APP_PAGES, _clean
    clean = _clean({"pettracker_enabled": True, "pettracker_overlay": False, "pettracker_overlay_style": "pettracker",
                    "pettracker_path": "C:\\Games\\PetTracker", "overlay_pets_pos_x": 5})
    assert clean == {"pettracker_enabled": True, "pettracker_overlay": False, "pettracker_overlay_style": "pettracker"}
    with pytest.raises(ValueError):
        _clean({"pettracker_overlay_style": "both"})
    assert "pets" in APP_PAGES


def test_the_hotkey_launcher_flag_and_installer_task():
    from aion2calc.app import hotkeys
    assert hotkeys.ACTIONS["toggle_pet_tracker"] == "Show / hide the Pet Tracker overlay"
    launcher = (ROOT / "aion2calc" / "launcher.py").read_text(encoding="utf-8")
    assert '"toggle_pet_tracker":' in launcher and "server.pettracker_sync()" in launcher
    assert '"--install-pettracker"' in launcher and "pettracker_setup.install(wait=900)" in launcher
    smoke = launcher[launcher.index("def smoke_test"):launcher.index("def _start_hotkeys")]
    assert "pettracker.self_check()" in smoke and "ok = False" in smoke.split("pettracker.self_check()")[1]
    iss = (ROOT / "packaging" / "windows" / "aion2calc.iss").read_text(encoding="utf-8")
    assert 'Name: "pettracker";' in iss and "Flags: unchecked" in iss.split('Name: "pettracker";')[1].splitlines()[0]
    run = next(line for line in iss.splitlines() if '"--install-pettracker"' in line)
    assert "Tasks: pettracker" in run and "Check: NeedsPetTracker" in run and "skipifsilent" in run
    assert r"{localappdata}\PetTracker.Desktop\current\PetTracker.exe" in iss and r"{localappdata}\Programs\PetTracker\PetTracker.exe" in iss


def test_the_pages():
    page = (STATIC / "pet-overlay.html").read_text(encoding="utf-8")
    assert "a2-pets-reloads" in page and page.index("a2-pets-reloads") < page.index('<script src="/static/pet-tracker.js">')
    assert '/static/overlay.css' in page and 'id="ovlock"' in page and 'id="ovhide"' in page
    script = (STATIC / "pet-overlay.js").read_text(encoding="utf-8")
    assert script.index('window.A2OverlayUp = "starting"') < script.index('window.A2OverlayUp = "ready"')
    assert 'body: JSON.stringify({ action: "hide", view: "pets" })' in script and 'nativeCall("set_locked", locked)' in script
    shared = (STATIC / "pet-tracker.js").read_text(encoding="utf-8")
    assert "window.A2Pets = { esc, status, row, rows, accent, control }" in shared
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<a href="#/pets" data-page="pets">Pet Tracker</a>' in index and "/static/pet-tracker.js" in index
    assert 'text: state.problem || "Starting Pet Tracker\'s capture…"' in shared
    # the app's page, its Settings section and their update notice: tests/browser/test_browser_pages.py
