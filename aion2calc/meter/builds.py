"""Product-version comparison keys with historical launcher-build compatibility."""
from __future__ import annotations

import re


def comparison_version(value: str) -> str:
    """Drop only numeric ProductVersion suffixes after its four core components."""
    value = str(value or "").strip()
    prefix = "version:product:"
    version = value[len(prefix):] if value.startswith(prefix) else value
    if re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,12}){3,7}", version):
        return (prefix if value.startswith(prefix) else "") + ".".join(version.split(".")[:4])
    return value


def comparison_document(doc: dict) -> dict:
    """Normalize derived comparison context without changing the source document."""
    def context(row):
        return {**row, **{key: comparison_version(row[key]) for key in
                         ("game_patch", "installed_build_cohort") if key in row}}
    return {**doc, "meta": context(doc.get("meta") or {}),
            "segments": [context(s) for s in doc.get("segments", [])]}


def resolve(evidence: dict) -> dict:
    version = str(evidence.get("installed_build") or "")
    namespace = str(evidence.get("installed_build_namespace") or "")
    if namespace == "aion2:product" and re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,12}){1,7}", version):
        cohort = comparison_version("version:product:" + version)
        return {"game_patch": cohort, "game_patch_basis": "executable_product_version",
                "game_patch_source": "Game executable ProductVersion core (first four components)",
                "installed_build_cohort": cohort, "patch_status": "version_identified",
                "patch_reason": "The first four Product version components identify the comparison group across launchers; numeric suffixes are retained in diagnostics; file versions and launcher IDs are diagnostic evidence only."}
    # Historical records and external integrations may still provide launcher build IDs.
    if re.fullmatch(r"steam:[0-9]{1,12}", namespace) and re.fullmatch(r"[0-9]{1,20}", version):
        cohort = "build:" + namespace + ":" + version
        return {"game_patch": cohort, "game_patch_basis": "installed_build_cohort",
                "game_patch_source": "Legacy launcher build metadata", "installed_build_cohort": cohort,
                "patch_status": "build_identified", "patch_reason": "Legacy build metadata; Product version was not recorded."}
    return {"patch_status": "unavailable", "patch_reason": "No game Product version is available; launcher IDs and engine versions do not substitute for it."}
