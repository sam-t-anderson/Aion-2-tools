"""High level helpers: build a character, simulate it, compare builds."""
from __future__ import annotations

import importlib
from dataclasses import dataclass

from .kit.base import Build, ClassData
from .model.character import daevanion_to_stats, load_loadout, loadout_stats
from .model.stats import Stats
from .sim.engine import Sim, SimConfig, SimResult, Target

#: MP the client does not list per class/level (assumption; see docs).
BASE_MP_45 = 2500.0
BASE_MP_REGEN = 20.0 / 3.0


def kit_module(cls: str):
    try:
        return importlib.import_module(f"aion2calc.kit.{cls}")
    except ModuleNotFoundError:
        return importlib.import_module("aion2calc.kit.generic")


@dataclass
class Scenario:
    loadout: str = "sorcerer_l45_global_median"
    target: Target = None
    config: SimConfig = None
    buffs: tuple = ()          # extra stat dicts (food, scrolls, party buffs)

    def __post_init__(self):
        self.target = self.target or Target()
        self.config = self.config or SimConfig()


def character_stats(build: Build, cd: ClassData, scenario: Scenario, kit_static: dict) -> Stats:
    lo = load_loadout(scenario.loadout) if isinstance(scenario.loadout, str) else scenario.loadout
    s = loadout_stats(lo)
    base = cd.base_stats(build.level)
    s.add({"attack": base["attack"], "mp_max": BASE_MP_45, "mp_regen": BASE_MP_REGEN})
    s.add(daevanion_to_stats(cd.daevanion_stats(build.daevanion)))
    s.add(kit_static)
    for b in scenario.buffs:
        s.add(b)
    return s


def prepare(build: Build, scenario: Scenario, policy: list | None = None, filler: str | None = None):
    cd = ClassData(build.cls)
    # gear skill-level bonuses are part of the loadout; merge into the build copy
    lo = load_loadout(scenario.loadout) if isinstance(scenario.loadout, str) else scenario.loadout
    gear_bonus = loadout_stats(lo).skill_bonus
    b = build.copy()
    for sid, lv in gear_bonus.items():
        b.bonus[sid] = b.bonus.get(sid, 0) + lv
    mod = kit_module(build.cls)
    kit = mod.build_kit(b, cd, filler=filler or "flame_arrow") if filler else mod.build_kit(b, cd)
    stats = character_stats(b, cd, scenario, kit.static)
    return cd, b, kit, stats


def simulate(build: Build, scenario: Scenario | None = None, policy: list | None = None,
             filler: str | None = None) -> SimResult:
    scenario = scenario or Scenario()
    cd, b, kit, stats = prepare(build, scenario, filler=filler)
    sim = Sim(stats.derived(), kit.actions, policy or kit.policy, scenario.target, scenario.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim.run()
