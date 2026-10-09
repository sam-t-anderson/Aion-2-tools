"""Technical comparison keys from the selected installation build number."""
from __future__ import annotations

import re


def resolve(evidence: dict) -> dict:
    equivalent = bool(evidence.get("comparison_build") and evidence.get("comparison_build_namespace"))
    build = str(evidence.get("comparison_build") if equivalent else evidence.get("installed_build") or "")
    namespace = str(evidence.get("comparison_build_namespace") if equivalent else evidence.get("installed_build_namespace") or "")
    if not re.fullmatch(r"(?:steam:[0-9]{1,12}|purple:A2_[A-Z0-9_]{1,80}_PURPLE)", namespace) or not re.fullmatch(r"[0-9]{1,20}", build):
        return {"patch_status": "unavailable", "patch_reason": "No unique launcher build ID is available; executable versions alone do not identify a game build."}
    cohort = "build:" + namespace + ":" + build
    return {"game_patch": cohort, "game_patch_basis": "installed_build_cohort",
            "game_patch_source": (evidence.get("comparison_build_source") if equivalent else
                                  "Build number from the selected launcher installation"),
            "installed_build_cohort": cohort, "patch_status": "build_identified",
            "patch_reason": ("Equivalent gameplay content maps launcher revisions to a common comparison build; original installation IDs remain recorded."
                             if equivalent else "Exact launcher build number used; cross-launcher equivalence has not been established.")}
