"""The app's icon cache (``/api/icon``) fetches only pictures from its icon hosts, and of aion2hub.com only the item
icons by id that the Pantheon decorations' pictures are (0.2.445: the native interface reads them through it)."""
import pytest

from aion2calc.app.server import icon_allowed


@pytest.mark.parametrize("url, allowed", [
    ("https://aion2hub.com/api/icon/items/123", True),
    ("https://metabot.gg/web/aion2/items/a.webp", True),
    ("https://assets.playnccdn.com/x.png", True),
    ("https://aion2hub.com/api/icon/items/123?size=2", False),          # nothing but the item's id
    ("https://aion2hub.com/api/icon/items/123#x", False),
    ("https://aion2hub.com/api/icon/items/1234567890123", False),
    ("https://aion2hub.com/api/icon/items/12a", False),
    ("https://aion2hub.com/", False),
    ("https://aion2hub.com/api/characters/1", False),
    ("http://aion2hub.com/api/icon/items/123", False),
    ("https://aion2hub.com:8443/api/icon/items/123", False),
    ("https://user@aion2hub.com/api/icon/items/123", False),
    ("https://cdn.aion2hub.com/api/icon/items/123", False),
    ("https://aion2hub.com.example/api/icon/items/123", False),
    ("https://example.com/x.png", False),
    ("", False),
])
def test_the_icon_cache_fetches_only_its_hosts_pictures(url, allowed):
    assert icon_allowed(url) is allowed
