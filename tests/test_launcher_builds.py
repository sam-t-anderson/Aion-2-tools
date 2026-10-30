"""A recording a meter of 0.2.66 or earlier made carries only the Steam launcher's build id: its game
version was "Legacy build N · Steam", a comparison group of its own. A build id installs recorded
beside the executable's Product version joins that version's group (0.2.355), from the pairs in the
diagnostic captures and those a host learns. And the upload before the size cap deletes a part no longer
sends a part of a recording a meter before 0.2.290 made weeks earlier: such meters could cut a recording
into hundreds of parts of a few seconds, and four of them reached the server one by one (29-30 October)."""
import pytest

from aion2calc.combat import share
from aion2calc.meter import builds


@pytest.fixture(autouse=True)
def _clean():
    builds._learned_products.clear()
    yield
    builds._learned_products.clear()


def test_a_known_launcher_build_joins_its_product_versions_group():
    assert builds.comparison_version("build:steam:3393110:25800038") == "version:product:2.0.6.0"
    assert builds.comparison_version("build:steam:3393110:25767555") == "build:steam:3393110:25767555"   # unknown: its own
    assert builds.comparison_version("version:product:2.0.9.0.2026102801") == "version:product:2.0.9.0"


def test_a_host_learns_pairs_and_an_ambiguous_build_maps_to_neither():
    meta = {"installed_build": "2.0.6.0.2026100701", "installed_build_namespace": "aion2:product",
            "launcher_build": "25767555", "launcher_build_namespace": "steam:3393110"}
    pair = builds.launcher_pair(meta)
    assert pair == (("steam:3393110", "25767555"), "2.0.6.0")
    builds.learn_launcher_products(dict([pair]))
    assert builds.comparison_version("build:steam:3393110:25767555") == "version:product:2.0.6.0"
    builds.learn_launcher_products({("steam:3393110", "25767555"): "1.0.21.0"})       # seen with another version
    assert builds.comparison_version("build:steam:3393110:25767555") == "build:steam:3393110:25767555"
    builds.learn_launcher_products([pair])                                             # and for good
    assert builds.launcher_product("steam:3393110", "25767555") is None
    builds.learn_launcher_products([(("steam:3393110", "1"), "2.0.8.0"), (("steam:3393110", "1"), "2.0.9.0")])
    assert builds.launcher_product("steam:3393110", "1") is None                       # two at once, the same
    builds.learn_launcher_products({("steam:3393110", "25800038"): "9.9.9.9"})        # the bundled pair stands
    assert builds.launcher_product("steam:3393110", "25800038") == "2.0.6.0"
    assert builds.launcher_pair({"installed_build_namespace": "steam:3393110", "installed_build": "25767555"}) is None


def _part(meter, saved, archive=True):
    meta = {"capture_quality": {"app_version": meter}, "checkpoint_at": saved}
    return {"meta": meta | ({"archive": {"id": "a" * 32, "part": 3, "closed": True}} if archive else {})}


def test_a_part_of_an_old_meters_recording_from_weeks_ago_is_stale():
    # The four recordings the log cache sent part by part (29-30 October): meters 0.2.59 to 0.2.209,
    # uploaded 18 to 23 days after they were saved; a current upload arrives within hours.
    day, now = 86400.0, 1_793_000_000.0
    assert share.stale_part(_part("0.2.209", now - 19 * day), now)
    assert share.stale_part(_part("0.2.59", now - 23 * day), now)
    assert share.stale_part(_part("0.2.289", now - 7 * day), now)
    assert not share.stale_part(_part("0.2.290", now - 30 * day), now)    # its rollovers are sane
    assert not share.stale_part(_part("0.2.209", now - 6 * day), now)     # recent: a fight just played
    assert not share.stale_part(_part("0.2.209", now - 30 * day, archive=False), now)   # not a recording part
    assert not share.stale_part(_part(None, now - 30 * day), now)         # no meter version
    assert not share.stale_part(_part("0.2.209", None), now) and not share.stale_part(_part("0.2.209", True), now)
    assert not share.stale_part({}, now) and not share.stale_part({"meta": []}, now)


def test_the_upload_before_the_size_cap_deletes_a_stale_part_without_sending_it(tmp_path, monkeypatch):
    import json
    import time
    from aion2calc.app import meter_runner, server
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_upload_before_prune": True})
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(share, "already_uploaded", lambda doc: False)
    monkeypatch.setattr(share, "automatic_uploads_paused", lambda: False)
    sent = []
    monkeypatch.setattr(share, "upload", lambda doc, **kw: sent.append(doc) or {"id": "abc123"})
    evict = meter_runner.upload_evictor()
    old, new = tmp_path / "old.a2log.json", tmp_path / "new.a2log.json"
    old.write_text(json.dumps(_part("0.2.209", time.time() - 20 * 86400)), encoding="utf-8")
    new.write_text(json.dumps(_part("0.2.355", time.time() - 20 * 86400)), encoding="utf-8")
    assert evict(old) is True and sent == []                               # deleted, never sent
    assert evict(new) is True and len(sent) == 1
