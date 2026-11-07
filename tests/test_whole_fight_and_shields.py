"""0.2.363: a whole fight's DPS beside the rotation's (the recorded idle and dodging share), the Templar's shields
in the survival models, the 1d 37 movement step, and the instances named from outside the catalog."""
import struct
from dataclasses import replace

import pytest

from aion2calc.combat import a2log
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import scan_move_delta
from aion2calc.meter.context import CURATED_ZONES, classify
from aion2calc.opt import world as W
from aion2calc.opt.rotation import materialize
from aion2calc.run import prepare
from aion2calc.scenarios import boss, dummy, pvp_world, typical_build
from aion2calc.sim import engine as E
from aion2calc.sim.engine import FIGHT_INACTIVE, Sim

STREAM = "1.2.3.4:13328->192.168.1.9:57424"


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _frame(opcode, body):
    inner = opcode + body
    return _varint(len(inner) + 4) + inner


def _run(cls, scenario, **config):
    build = typical_build(cls)
    _, _, kit, stats = prepare(build, scenario)
    return Sim(stats.derived(), kit.actions, materialize(kit.policy), scenario.target,
               replace(scenario.config, **config), hooks=kit.hooks, cond_mods=kit.cond_mods).run()


# ----------------------------------------------------------------- whole fight
def test_every_class_has_a_recorded_inactive_share_between_a_quarter_and_two_fifths():
    assert set(FIGHT_INACTIVE) == {"assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer", "spiritmaster", "templar"}
    assert all(0.25 <= v <= 0.45 for v in FIGHT_INACTIVE.values())


@pytest.mark.parametrize("cls", ["gladiator", "sorcerer"])
def test_a_whole_fights_dps_is_the_rotation_stretched_over_the_idle_and_dodging_share(cls):
    """With ``whole_fight`` on a boss scenario every action takes longer by the class's recorded inactive share, so
    fillers are pressed less and cooldown skills nearly as often: the DPS falls, by less than the share itself."""
    rotation = _run(cls, boss(f"{cls}_l45_global_median"))
    fight = _run(cls, boss(f"{cls}_l45_global_median"), whole_fight=True)
    share = FIGHT_INACTIVE[cls]
    assert rotation.inactive_share == 0.0 and fight.inactive_share == pytest.approx(share)
    assert fight.dps < rotation.dps
    assert fight.dps > rotation.dps * (1 - share) * 0.97           # cooldown skills keep their cadence
    assert sum(fight.casts.values()) < sum(rotation.casts.values())


def test_the_dummy_never_stretches_and_the_rotations_dps_is_the_objective():
    """A dummy takes no party damage, so the share does not apply; the optimizer scores rotations without it."""
    plain = _run("gladiator", dummy("gladiator_l45_global_median"))
    asked = _run("gladiator", dummy("gladiator_l45_global_median"), whole_fight=True)
    assert asked.inactive_share == 0.0 and asked.dps == pytest.approx(plain.dps)


def test_an_unknown_class_gets_no_share(monkeypatch):
    """A kit whose skill ids name no class (a toy) is left alone rather than guessed."""
    monkeypatch.setitem(FIGHT_INACTIVE, "gladiator", 0.4)
    poke = E.Action("poke", "Poke", 99, cast=0.5, on_cast=lambda sim, a: sim.hit(a.name, 100.0, 1.0), is_filler=True)
    from aion2calc.model.stats import Stats
    derived = Stats().derived()
    plain = Sim(derived, {"poke": poke}, ["poke"], E.Target(party_damage=True), E.SimConfig(duration=20.0)).run()
    asked = Sim(derived, {"poke": poke}, ["poke"], E.Target(party_damage=True), E.SimConfig(duration=20.0, whole_fight=True)).run()
    assert asked.inactive_share == 0.0 and asked.dps == pytest.approx(plain.dps)


# ---------------------------------------------------------------------- shields
def test_a_cast_that_shields_counts_toward_the_rotations_absorb_share():
    from aion2calc.model.stats import Stats
    guard = E.Action("guard", "Guard", 12070000, cast=0.5, cooldown=10.0, absorb=0.05,
                     on_cast=lambda sim, a: sim.hit(a.name, 100.0, 1.0))
    poke = E.Action("poke", "Poke", 12010000, cast=0.5, on_cast=lambda sim, a: sim.hit(a.name, 10.0, 1.0), is_filler=True)
    res = Sim(Stats().derived(), {"guard": guard, "poke": poke}, ["guard", "poke"], E.Target(), E.SimConfig(duration=30.0)).run()
    assert res.casts["guard"] == 3 and res.absorb_share == pytest.approx(0.15)


def test_the_templars_shields_raise_its_effective_hp_in_world_pvp():
    """Doom Shield (5 % a cast) and Poach's specialization (10 %) ride their presses; Nezekan's Shield (45 % of the
    caster's maximum HP once a minute at level 5) and Guarding Seal are the defensive share; the World PvP
    survival counts what they absorb as HP."""
    from aion2calc.kit.templar import SID, build_kit, defensive_absorb_share
    from aion2calc.kit.base import ClassData
    scen = pvp_world("templar_l45_global_median")
    build = typical_build("templar")
    build.stigmas[SID["DOOM"]] = max(build.stigmas.get(SID["DOOM"], 0), 1)
    kit = build_kit(build, ClassData("templar"))
    assert kit.actions["doom"].absorb == pytest.approx(0.05)
    assert SID["NEZ"] not in {a.skill_id for a in kit.actions.values()}          # no damage, so no action
    without = defensive_absorb_share(build, 180.0)
    build.stigmas[SID["NEZ"]] = 5
    with_nez = defensive_absorb_share(build, 180.0)
    assert with_nez - without == pytest.approx(0.45 * 3)                        # 45 % at level 5, once a minute

    _, _, kit, stats = prepare(build, scen)
    ref = W.reference("templar", scen)
    bare = W.survival("templar", stats, 0.0, 180.0, ref)
    shielded = W.survival("templar", stats, 0.0, 180.0, ref, absorb_share=0.5)
    assert bare["shield_share"] == 0.0 and bare["effective_hp"] == pytest.approx(bare["effective_hp_without_shields"])
    assert shielded["shield_hp"] > 0 and shielded["effective_hp"] > bare["effective_hp"]
    assert shielded["alive_share"] > bare["alive_share"]
    assessed = W.assess("templar", build, scen, list(kit.policy))
    assert assessed["shield_share"] > 0 and "shields and heals as the HP they absorb or restore" in assessed["note"]
    # 0.2.386: Doom Shield's presses carry their shield into World PvP too (the generic player-target kit had none)
    cd, b, pkit, _ = prepare(build, scen)
    W.world_kit("templar", b, cd, pkit)
    assert pkit.actions["doom_shield"].absorb == pytest.approx(0.05)
    _, _, _, res, inputs = W._run("templar", build, scen, list(kit.policy))
    assert res.casts.get("doom_shield", 0) > 0
    assert inputs["absorb_share"] == pytest.approx(defensive_absorb_share(b, res.duration) + res.absorb_share)
    assert res.absorb_share >= 0.05 * res.casts["doom_shield"] - 1e-9


# ------------------------------------------------------------------ 1d 37 step
def _step(entity, flags, state, axes, h1=16384, h2=16384):
    body = _varint(entity) + bytes([flags, state]) + bytes((v + 256) % 256 for v in axes) + struct.pack("<HH", h1, h2)
    return _frame(b"\x1d\x37", body)


def test_a_movement_step_names_its_axes_in_the_flags_and_adds_up_from_the_last_fix():
    step = scan_move_delta(_step(4063, 0x2F, 3, (13, -20, 2)))
    assert step == {"kind": "delta", "entity": 4063, "dx": 13, "dy": -20, "dz": 2, "heading": 90.0, "moving": True}
    assert scan_move_delta(_step(4063, 0x27, 3, (-5, 7)))["dz"] == 0                     # two axes: x and y
    assert scan_move_delta(_step(4063, 0x25, 3, (9,)))["dy"] == 9                        # y alone
    assert scan_move_delta(_step(4063, 0x2F, 3, (1, 2)))  is None                        # the flags promise three bytes
    assert scan_move_delta(_frame(b"\x1c\x37", _varint(4063) + b"\x04" + struct.pack("<3f", 1, 2, 3))) is None
    assert "delta" in a2log.MOVEMENT_SOURCES

    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_step(4063, 0x2F, 3, (13, -20, 2)), 1_000, STREAM)
    assert engine.positions == []                                                        # no fix to add the step to
    engine.consume(_frame(b"\x1c\x37", _varint(4063) + b"\x04" + struct.pack("<3f", 1000.0, 2000.0, 30.0) + b"\x00\x40\x00\x40\x00"), 2_000, STREAM)
    engine.consume(_step(4063, 0x2F, 3, (13, -20, 2)) + _step(4063, 0x27, 3, (-3, 5)) + _step(4063, 0x21, 3, ()), 2_250, STREAM)
    rows = [(p["src"], p["x"], p["y"], p["z"]) for p in engine.positions if p["entity"] == 4063]
    assert rows == [("delta", 1013.0, 1980.0, 32.0), ("delta", 1010.0, 1985.0, 32.0)]   # a step with no axes adds nothing


# -------------------------------------------------------- instances named outside
def test_the_nightmare_hub_and_the_citadel_are_named_and_their_bosses_end_the_run():
    nightmare = classify(200003, 0, False, [{"kind": "enemy", "mob_code": 2980043}])    # Gatekeeper Pinopi, Level 4
    assert nightmare["zone"] == "Nightmare" and nightmare["encounter_type"] == "nightmare" and nightmare["difficulty"] == "level 4"
    assert "CURATED_ZONES" in nightmare["zone_source"]
    citadel = classify(600144, 600144, False, [{"kind": "enemy", "mob_code": 2301603}])  # Basilus the False
    assert citadel["zone"] == "Citadel of the Fallen Daeva" and citadel["difficulty"] == "exploration"
    assert set(CURATED_ZONES) == {200003, 600144, 600145, 600146}
