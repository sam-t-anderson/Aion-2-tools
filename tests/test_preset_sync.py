"""Community preset sync (aion2calc/combat/preset_sync.py): the client keeps a copy of each class's
canonical v2 preset from its log server, after checking that the preset matches the server's scoring
policy, and submits its own optimized builds there. A preset that does not check out is never cached, a
cache belongs to the server it came from, and a server without v2 presets leaves the v1 path to run."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "a2l_community-key"


@pytest.fixture(scope="module")
def preset():
    """A real canonical preset: the bundled Sorcerer build scored under the current policy, as a server serves it."""
    from aion2calc.canonical_presets import candidate, evaluate, scoring_policy
    summary = json.loads((ROOT / "results" / "compare" / "sorcerer" / "build.json").read_text(encoding="utf-8"))
    policy = scoring_policy("sorcerer", "pve")
    evaluated = evaluate(candidate(summary, policy))
    return {"summary": summary, "policy": policy,
            "remote": {"class": "sorcerer", "mode": "pve", "scope": policy["scope"], "score": evaluated["score"],
                       "updated_at": 1000.0, "build": evaluated}}


class Community:
    """A stand-in log server answering the preset routes from ``routes`` (path -> status and JSON body, or a
    callable giving them) and keeping every request it saw."""

    def __init__(self, preset):
        self.requests = []
        self.routes = {
            "/.well-known/a2log.json": (200, {"canonical_presets_version": 2}),
            "/api/v2/presets": (200, {"presets": [{"class": "sorcerer", "mode": "pve", "scope": preset["policy"]["scope"],
                                                   "updated_at": 1000.0}]}),
            "/api/v2/presets/sorcerer/pve": (200, preset["remote"]),
            "/api/v2/presets/sorcerer/pve/policy": (200, preset["policy"]),
            "POST /api/v2/presets": (200, {"accepted": True, "outcome": "accepted"}),
        }
        community = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, method):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if method == "POST" else b""
                community.requests.append({"method": method, "path": self.path, "headers": dict(self.headers),
                                           "body": json.loads(body) if body else None})
                route = community.routes.get(self.path if method == "GET" else f"POST {self.path}", (404, {"error": "not found"}))
                status, payload, *headers = route() if callable(route) else route
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                for name, value in (headers[0] if headers else {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                self.answer("GET")

            def do_POST(self):
                self.answer("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def seen(self, path, method="GET"):
        return [r for r in self.requests if r["path"] == path and r["method"] == method]


@pytest.fixture
def community(tmp_path, monkeypatch, preset):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    server = Community(preset)
    from aion2calc.combat import share
    share.save_settings(url=server.url, key=KEY)          # a saved key: the project default is never consulted
    yield server
    server.server.shutdown()


def cached_file():
    from aion2calc.paths import data_file
    return data_file("community_presets_v2", "sorcerer_pve.json")


def test_a_valid_preset_is_cached_for_its_server_and_fetched_again_only_when_it_changes(community, preset):
    from aion2calc.combat.preset_sync import cached_presets, sync
    community.routes["/api/v2/presets"][1]["presets"] += [
        {"class": "warlock", "mode": "pve", "scope": "a" * 64},                    # not a class of this client
        {"class": "sorcerer", "mode": "raid", "scope": "a" * 64},
        {"class": "templar", "mode": "pve", "scope": "not-a-fingerprint"},
        {"class": "sorcerer", "mode": "pve", "scope": "b" * 64},                   # a second sorcerer/pve row
        "junk"]
    assert sync() == ["sorcerer_pve"]
    rows = cached_presets()
    assert len(rows) == 1 and rows[0]["class"] == "sorcerer" and rows[0]["mode"] == "pve"
    assert rows[0]["source"] == community.url and rows[0]["build"]["score"] == preset["remote"]["score"]
    assert rows[0]["checked_at"] <= time.time()
    assert sync() == [] and len(community.seen("/api/v2/presets/sorcerer/pve")) == 1     # unchanged: not fetched again
    community.routes["/api/v2/presets"][1]["presets"][0]["updated_at"] = 2000.0
    community.routes["/api/v2/presets/sorcerer/pve"][1]["updated_at"] = 2000.0
    assert sync() == ["sorcerer_pve"] and len(community.seen("/api/v2/presets/sorcerer/pve")) == 2


def test_a_cache_belongs_to_the_server_it_came_from(community):
    from aion2calc.combat import share
    from aion2calc.combat.preset_sync import cached_presets, sync
    assert sync() == ["sorcerer_pve"] and cached_presets()
    share.save_settings(url="http://127.0.0.1:9", key=KEY)                    # the user picked another server
    assert cached_presets() == []


def tampered(change):
    def apply(remote):
        remote = json.loads(json.dumps(remote))
        change(remote)
        return remote
    return apply


@pytest.mark.parametrize("change, problem", [
    (lambda r: r.update(score=r["score"] * 1.1), "weighted score is inconsistent"),
    (lambda r: r["build"]["scoring_policy"]["weights"].update(boss=.9, dummy=.1), "does not match the supported scoring policy"),
    (lambda r: r["build"]["scoring_policy"].update(model="0.0.1"), "fingerprint is inconsistent"),
    (lambda r: r.update(**{"class": "templar"}), "does not match the supported scoring policy"),
    (lambda r: r["build"]["dps"].update(boss=float("inf")), "finite positive numbers"),
    (lambda r: r["build"]["loadout_snapshot"].update(level=50), "bounded common-loadout snapshot"),
    (lambda r: r["build"]["loadout_snapshot"]["components"][0]["stats"].update(made_up_stat=5), "Invalid preset stats"),
    (lambda r: r.update(updated_at="yesterday"), "Invalid preset update time"),
])
def test_a_preset_that_does_not_check_out_is_refused(preset, change, problem):
    from aion2calc.combat.preset_sync import _validate
    with pytest.raises(ValueError, match=problem):
        _validate(tampered(change)(preset["remote"]), "sorcerer", "pve", preset["policy"]["scope"])


def test_sync_skips_a_refused_preset_without_caching_it(community, preset):
    from aion2calc.combat.preset_sync import cached_presets, sync
    community.routes["/api/v2/presets/sorcerer/pve"] = (200, tampered(lambda r: r.update(score=1.0))(preset["remote"]))
    assert sync() == [] and cached_presets() == [] and not cached_file().exists()


def test_a_server_without_v2_presets_leaves_the_v1_path_to_run(community, preset):
    from aion2calc.combat.preset_sync import cached_presets, submit, sync
    from aion2calc.paths import data_file
    community.routes["/.well-known/a2log.json"] = (200, {"canonical_presets_version": 1})
    assert sync() == [] and submit(preset["summary"]) is None
    community.routes["/.well-known/a2log.json"] = (404, {"error": "not found"})
    assert sync() == [] and submit(preset["summary"]) is None
    assert not data_file("community_presets_v2", "index.json").exists() and cached_presets() == []
    community.routes["/.well-known/a2log.json"] = (500, {"error": "down"})        # an outage is not an answer
    assert sync() == []
    outcome = submit(preset["summary"])
    assert outcome["submitted"] is False and outcome["reason"].startswith("Canonical preset submission unavailable")


def test_a_submission_is_the_scored_candidate_with_the_upload_key(community, preset):
    from aion2calc.combat.preset_sync import cached_presets, submit
    assert submit(preset["summary"]) == {"accepted": True, "outcome": "accepted", "submitted": True}
    post, = community.seen("/api/v2/presets", "POST")
    assert post["headers"]["Authorization"] == "Bearer " + KEY
    document = post["body"]
    assert (document["format"], document["version"], document["class"], document["mode"]) == ("a2preset", 2, "sorcerer", "pve")
    assert document["scope"] == preset["policy"]["scope"] and document["build"]["scenario"] == "boss"
    for thread in [t for t in threading.enumerate() if t.name == "canonical-preset-refresh"]:
        thread.join(30)                                       # an accepted preset refreshes the cache at once
    assert cached_presets()[0]["build"]["score"] == preset["remote"]["score"]


def test_personal_builds_and_unknown_classes_are_not_submitted(community, preset):
    from aion2calc.combat.preset_sync import submit
    personal = {**preset["summary"], "survival": {"minimum_node_hp": 500}}
    outcome = submit(personal)
    assert outcome["submitted"] is False and "personal constraints" in outcome["reason"]
    assert submit({**preset["summary"], "class": "warlock"})["reason"].endswith("unknown class")
    assert community.seen("/api/v2/presets", "POST") == []


def test_a_submission_never_follows_a_redirect(community, preset):
    from aion2calc.combat.preset_sync import submit
    community.routes["POST /api/v2/presets"] = (307, {}, {"Location": community.url + "/elsewhere"})
    outcome = submit(preset["summary"])
    assert outcome["submitted"] is False and "redirects are not followed" in outcome["reason"]
    assert community.seen("/elsewhere", "POST") == [] and community.seen("/elsewhere") == []


def test_an_oversized_answer_is_refused(community):
    from aion2calc.combat.preset_sync import _request, cached_presets, sync
    community.routes["/api/v2/presets/sorcerer/pve"] = (200, b'{"pad": "' + b"x" * 100_000 + b'"}')
    with pytest.raises(ValueError, match="exceeds 100 KB"):
        _request(community.url, "/api/v2/presets/sorcerer/pve")
    assert sync() == [] and cached_presets() == []
    community.routes["/api/v2/presets"] = (200, [])
    with pytest.raises(ValueError, match="Expected a preset response object"):
        _request(community.url, "/api/v2/presets")


def test_switching_servers_during_a_sync_keeps_the_old_servers_presets_out(community, preset):
    from aion2calc.combat import share
    from aion2calc.combat.preset_sync import sync
    from aion2calc.paths import data_file

    def switch():
        share.save_settings(url="http://127.0.0.1:9", key=KEY)
        return 200, preset["remote"]
    community.routes["/api/v2/presets/sorcerer/pve"] = switch
    assert sync() == []
    assert not cached_file().exists() and not data_file("community_presets_v2", "index.json").exists()


def test_without_a_server_nothing_is_asked(tmp_path, monkeypatch, preset):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.combat import preset_sync
    monkeypatch.setattr(preset_sync, "effective", lambda: {"is_default": False})
    assert preset_sync.sync() == [] and preset_sync.submit(preset["summary"]) is None
    assert preset_sync.cached_presets() == []
