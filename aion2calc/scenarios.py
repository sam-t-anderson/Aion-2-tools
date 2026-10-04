"""Named fight scenarios and the community baseline build."""
from __future__ import annotations

from .kit.base import Build, ClassData
from .run import Scenario
from .sim.engine import SimConfig, Target


def dummy(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    """Training dummy: 10% Damage Tolerance (community measurement), always 100% HP."""
    return Scenario(loadout=loadout, target=Target(tolerance=0.10, hp_model="dummy"),
                    config=SimConfig(duration=duration))


def boss(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    """Dungeon boss: 30% Damage Tolerance, HP falls linearly, three 8 s stagger windows."""
    windows = tuple((s, s + 8.0) for s in (40.0, 100.0, 160.0) if s < duration)
    return Scenario(loadout=loadout,
                    target=Target(tolerance=0.30, hp_model="linear", stagger_windows=windows),
                    config=SimConfig(duration=duration))


SCENARIOS = {"dummy": dummy, "boss": boss}


def decode_metabot_daevanion(cd: ClassData, h: str) -> set:
    nodes = set()
    for part in (h or "").split("_"):
        if "-" not in part:
            continue
        bid, idx = part.split("-", 1)
        board = next((b for b in cd.boards if str(b["id"]) == bid), None)
        if not board:
            continue
        for i in idx.split("."):
            try:
                nodes.add(board["nodes"][int(i, 36)]["id"])
            except (ValueError, IndexError):
                pass
    return nodes


def community_build(cls: str) -> Build:
    """metabot's 'most common build' among the top tracked global L45 players."""
    cd = ClassData(cls)
    p = cd.raw.get("preset") or {}
    b = Build(cls, level=p.get("level", 45))
    for s in p.get("skills", []):
        sid = s["id"]
        if sid not in cd.skills:
            continue
        if cd.skills[sid]["kind"] == "stigma":
            b.stigmas[sid] = s["level"]
        else:
            b.sp[sid] = min(10, s["level"])
            b.specs[sid] = tuple(s.get("specs", ()))
    stig = p.get("stigmas") or []
    b.stigmas = {sid: b.stigmas.get(sid, 1) for sid in stig if sid in cd.skills}
    b.daevanion = decode_metabot_daevanion(cd, p.get("daevanion", ""))
    return b
