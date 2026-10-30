"""A recording a meter of 0.2.66 or earlier made carries only the Steam launcher's build id: its game
version was "Legacy build N · Steam", a comparison group of its own. A build id installs recorded
beside the executable's Product version joins that version's group (0.2.355), from the pairs in the
diagnostic captures and those a host learns; and the upload before the size cap deletes a part no
longer sends such a recording (176 parts of one 7 October session reached the server one by one)."""
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


def test_the_upload_before_the_size_cap_skips_a_legacy_recording():
    legacy = {"meta": {"game_patch": "build:steam:3393110:25767555", "installed_build_namespace": "steam:3393110"}}
    current = {"meta": {"game_patch": "version:product:2.0.9.0", "installed_build_namespace": "aion2:product"}}
    assert share.legacy_recording(legacy) and not share.legacy_recording(current) and not share.legacy_recording({})
