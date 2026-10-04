"""Share links that open a build in the public planners.

* metabot.gg skill/stigma planner  ``#v1~l<lvl>~s<skill.lv.specmask[.bonus]>_...~g<stigmas>~d<daev>``
* metabot.gg Daevanion planner     ``#<boardId>-<base36 node index>.<...>_<boardId>-...``
* gamers4.life Daevanion planner   ``?b=base64url({"c": cls, "d": [node ids]})``
* gamers4.life build calculator    ``?b=base64url({"c": cls, "s": [...], "l": {...}, "d": [...]})``

Formats were read from the planners' own client code (Oct 2026).
"""
from __future__ import annotations

import base64
import json
import urllib.parse

from ..kit.base import Build, ClassData


def _b36(n: int) -> str:
    n = max(0, int(n))
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


def metabot_daevanion_hash(cd: ClassData, nodes: set) -> str:
    parts = []
    for b in cd.boards:
        idx = [_b36(i) for i, n in enumerate(b["nodes"]) if n["id"] in nodes and n["type"] != "Start"]
        if idx:
            parts.append(f"{b['id']}-{'.'.join(idx)}")
    return "_".join(parts)


def metabot_daevanion_url(cd: ClassData, nodes: set) -> str:
    return f"https://metabot.gg/en/aion-2/daevanion/{cd.cls}#{metabot_daevanion_hash(cd, nodes)}"


def metabot_build_url(cd: ClassData, build: Build) -> str:
    parts = ["v1", f"l{_b36(build.level)}"]
    skills = []
    sids = set(build.sp) | set(build.specs) | set(build.bonus) | set(build.stigmas)
    for sid in sorted(sids):
        s = cd.skills.get(sid)
        if not s:
            continue
        lv = build.stigmas.get(sid) if s["kind"] == "stigma" else build.sp.get(sid, 1)
        mask = 0
        for spid in build.specs.get(sid, ()):
            k = (spid - sid) // 10 - 1
            if 0 <= k < 30:
                mask |= 1 << k
        bonus = build.bonus.get(sid, 0) if s["kind"] != "stigma" else 0
        if (lv or 1) <= 1 and not mask and bonus <= 0:
            continue
        t = f"{_b36(sid)}.{_b36(lv or 1)}.{_b36(mask)}"
        if bonus > 0:
            t += f".{_b36(bonus)}"
        skills.append(t)
    if skills:
        parts.append("s" + "_".join(skills))
    stig = list(build.stigmas)[:4]
    if stig:
        parts.append("g" + "_".join(_b36(s) for s in stig))
    dh = metabot_daevanion_hash(cd, build.daevanion)
    if dh:
        parts.append("d" + urllib.parse.quote(dh, safe="").replace("~", "%7E"))
    return f"https://metabot.gg/en/aion-2/classes/{cd.cls}/build#" + "~".join(parts)


def _b64url(obj) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


G4L_CLASS = {"spiritmaster": "elementalist"}


def gamers4life_daevanion_url(cls: str, nodes: set) -> str:
    c = G4L_CLASS.get(cls, cls)
    return f"https://gamers4.life/aion-2/database/en/daevanion-planner/?b={_b64url({'c': c, 'd': sorted(nodes)})}"


def gamers4life_build_url(cls: str, build: Build, tab: str = "skills") -> str:
    c = G4L_CLASS.get(cls, cls)
    payload = {"c": c, "s": [str(s) for s in build.stigmas],
               "l": {str(k): v for k, v in build.stigmas.items()},
               "d": sorted(build.daevanion)}
    return f"https://gamers4.life/aion-2/database/en/build-calculator/?b={_b64url(payload)}&tab={tab}"
