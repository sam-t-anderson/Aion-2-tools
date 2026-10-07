"""Technical comparison keys from the selected installation build number."""
from __future__ import annotations

import re


def resolve(evidence: dict) -> dict:
    build = str(evidence.get("installed_build") or "")
    namespace = str(evidence.get("installed_build_namespace") or "")
    if not re.fullmatch(r"steam:[0-9]{1,12}", namespace) or not re.fullmatch(r"[0-9]{1,20}", build):
        return {"patch_status": "unavailable", "patch_reason": "No unique launcher build ID is available; executable versions alone do not identify a game build."}
    cohort = "build:" + namespace + ":" + build
    return {"game_patch": cohort, "game_patch_basis": "installed_build_cohort",
            "game_patch_source": "Build number from the selected Steam installation",
            "installed_build_cohort": cohort, "patch_status": "build_identified",
            "patch_reason": "Exact installation build number used for comparisons; launcher namespaces remain separate."}
