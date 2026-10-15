"""The client-minted, machine-salted per-recording dedup key sent on upload.

A finished recording gets a stable fingerprint derived from a local, never-sent install salt and the
recording's archive id. Re-uploading the same recording sends the same key, so the log server can
recognise and ignore the duplicate (see the server's store.put / recording_keys table). The key is
one-way, per-install and per-recording, so it cannot be forged or correlated across recordings.
"""
import pytest

from aion2calc.combat import heartbeat, share


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


_CLOSED = {"id": "1762b0bdfe0f4054a832464f6e9fdb05", "part": 1, "closed": True}


def _doc(archive):
    d = {"format": "a2log", "version": 1, "meta": {"source": "meter"},
         "players": [{"id": "p1", "name": "Sorc", "class": "sorcerer"}], "segments": []}
    if archive is not None:
        d["meta"]["archive"] = archive
    return d


def test_recording_key_is_stable_salted_and_closed_only(isolated_home):
    k = share.recording_key(_doc(_CLOSED))
    assert isinstance(k, str) and len(k) == 64 and all(c in "0123456789abcdef" for c in k)
    assert share.recording_key(_doc(_CLOSED)) == k                       # stable across calls/uploads
    assert heartbeat._install_salt() not in k                            # one-way: the salt never leaks
    assert share.recording_key(_doc({**_CLOSED, "id": "f" * 32})) != k   # distinct per recording
    # Only a finished (closed) archive is a stable identity; a checkpoint / keyless doc gets nothing.
    assert share.recording_key(_doc({**_CLOSED, "closed": False})) is None
    assert share.recording_key(_doc({"part": 1, "closed": True})) is None     # no archive id
    assert share.recording_key(_doc(None)) is None                           # no archive at all
    assert share.recording_key({}) is None


def test_recording_key_differs_between_installs(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "a"))
    ka = share.recording_key(_doc(_CLOSED))
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "b"))
    kb = share.recording_key(_doc(_CLOSED))
    assert ka and kb and ka != kb                                        # same recording, two machines


def test_upload_attaches_recording_key_header(isolated_home, monkeypatch):
    reqs = []

    class _Resp:
        def __init__(self, req):
            reqs.append(req)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    monkeypatch.setattr(share, "validate", lambda d: d)
    monkeypatch.setattr(share, "effective",
                        lambda: {"url": "https://logs.test", "visibility": "unlisted", "is_default": False})
    monkeypatch.setattr(share.urllib.request, "urlopen", lambda req, timeout=None: _Resp(req))

    def _posts():
        # discover() passes a bare URL string to urlopen; only the Request objects are uploads.
        return [r for r in reqs if hasattr(r, "get_method") and r.get_method() == "POST"]

    share.upload(_doc(_CLOSED))
    posts = _posts()
    assert posts, "no upload POST was made"
    header = next((v for k, v in posts[-1].headers.items() if k.lower() == "x-aion-recording-key"), None)
    assert header == share.recording_key(_doc(_CLOSED))

    # An in-progress checkpoint must not carry the dedup header (it is not a stable identity).
    reqs.clear()
    share.upload(_doc({**_CLOSED, "closed": False}))
    posts = _posts()
    assert posts and not any(k.lower() == "x-aion-recording-key" for k in posts[-1].headers)


def test_recording_key_is_per_part_and_keys_open_parts_only_when_asked(isolated_home):
    part1 = share.recording_key(_doc(_CLOSED))
    part2 = share.recording_key(_doc({**_CLOSED, "part": 2}))
    assert part1 and part2 and part1 != part2                                  # Part 2 is never a re-upload of Part 1
    open_part = {**_CLOSED, "closed": False}
    assert share.recording_key(_doc(open_part)) is None                        # default: finished parts only
    assert share.recording_key(_doc(open_part), include_open=True) == part1    # keyed for a superseding server, same key as its final upload
    assert share.recording_key(_doc({**_CLOSED, "part": "1"}), include_open=True) is None   # the part must be an int


def test_upload_keys_an_open_part_only_when_the_server_supersedes(isolated_home, monkeypatch):
    import json
    reqs, flag = [], {"supersede": False}

    class _Resp:
        def __init__(self, req):
            reqs.append(req)
            self._discover = isinstance(req, str)        # discover() passes the bare well-known URL

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"recording_supersede": True} if self._discover and flag["supersede"] else {}).encode()

    monkeypatch.setattr(share, "validate", lambda d: d)
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test", "visibility": "unlisted", "is_default": False})
    monkeypatch.setattr(share.urllib.request, "urlopen", lambda req, timeout=None: _Resp(req))
    open_doc = _doc({**_CLOSED, "closed": False})

    def _key():
        posts = [r for r in reqs if hasattr(r, "get_method") and r.get_method() == "POST"]
        return next((v for k, v in posts[-1].headers.items() if k.lower() == "x-aion-recording-key"), None)

    share.upload(open_doc)
    assert _key() is None                                                      # an older server: an open part is not keyed
    reqs.clear()
    flag["supersede"] = True
    share.upload(open_doc)
    assert _key() == share.recording_key(open_doc, include_open=True)          # a superseding server: keyed
