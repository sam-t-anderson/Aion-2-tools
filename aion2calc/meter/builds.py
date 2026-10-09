"""Product-version comparison keys with historical launcher-build compatibility."""
from __future__ import annotations

import re


def resolve(evidence: dict) -> dict:
    version = str(evidence.get("installed_build") or "")
    namespace = str(evidence.get("installed_build_namespace") or "")
    if namespace == "aion2:product" and re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,12}){1,7}", version):
        cohort = "version:product:" + version
        return {"game_patch": cohort, "game_patch_basis": "executable_product_version",
                "game_patch_source": "Game executable ProductVersion string (full value)",
                "installed_build_cohort": cohort, "patch_status": "version_identified",
                "patch_reason": "Product version identifies the comparison group across launchers; file versions and launcher IDs are diagnostic evidence only."}
    # Historical records and external integrations may still provide launcher build IDs.
    if re.fullmatch(r"steam:[0-9]{1,12}", namespace) and re.fullmatch(r"[0-9]{1,20}", version):
        cohort = "build:" + namespace + ":" + version
        return {"game_patch": cohort, "game_patch_basis": "installed_build_cohort",
                "game_patch_source": "Legacy launcher build metadata", "installed_build_cohort": cohort,
                "patch_status": "build_identified", "patch_reason": "Legacy build metadata; Product version was not recorded."}
    return {"patch_status": "unavailable", "patch_reason": "No game Product version is available; launcher IDs and engine versions do not substitute for it."}
