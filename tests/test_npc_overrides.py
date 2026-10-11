"""Verified local NPC-role overrides win over the generated catalog so a
catalog refresh cannot re-introduce a fixed boss/role error."""
from aion2calc.meter.a2parser.lookup import _npc_overrides, npc_info


def test_shining_mau_totem_is_a_miniboss_not_a_boss():
    _npc_overrides.cache_clear()
    for code in (2300907, 2310907, 2320907):          # the three dungeon-tier Shining Mau Totem codes
        info = npc_info(code)
        assert info["name"] == "Shining Mau Totem"    # name preserved from the catalog
        assert info["isBoss"] is False                # overridden: it must not headline as the boss
        assert info["role"] == "miniboss"             # intended role recorded


def test_override_leaves_other_npcs_untouched():
    _npc_overrides.cache_clear()
    assert npc_info(2702071)["isBoss"] is False        # a plain mob, no override, unchanged
    assert "role" not in npc_info(2702071)             # override fields appear only where declared
