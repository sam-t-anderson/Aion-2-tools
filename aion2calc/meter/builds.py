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


#: Candidate install version signals, best cross-launcher identifier first. Each
#: is ``(evidence key, label, is the value expected to match across launchers)``.
_SIGNALS = (
    ("installed_content_build", "Shipped content fingerprint", True),
    ("installed_build", "Executable ProductVersion", None),      # None: depends on the launcher's stamping
    ("file_version", "Executable fixed FileVersion", None),
    ("launcher_build", "Launcher build id", False),
)


def version_signals(evidence: dict) -> list[dict]:
    """The version signals present in one install's evidence, strongest first.

    ``cross_launcher`` records whether a signal is expected to match between a
    Steam and a PURPLE install of the same patch: the shipped content
    fingerprint should, a launcher build id should not, and the executable
    ProductVersion / fixed FileVersion are unknown until observed on both
    (that is exactly what :func:`compare_installs` measures)."""
    out = []
    for key, label, cross in _SIGNALS:
        value = evidence.get(key)
        if value:
            namespace = evidence.get({"installed_build": "installed_build_namespace",
                                      "installed_content_build": "installed_content_namespace",
                                      "launcher_build": "launcher_build_namespace"}.get(key, ""), "")
            out.append({"key": key, "label": label, "value": str(value),
                        "namespace": namespace or None, "cross_launcher": cross})
    return out


def compare_installs(installs: list[dict]) -> dict:
    """Compare version signals across two or more installs' evidence.

    Each input is one install's evidence (``_build_evidence`` output), ideally
    carrying a ``launcher`` label. Reports, per signal, whether every install
    that has it agrees, so the launcher-independent game-version key can be
    identified empirically rather than assumed. The shipped content fingerprint
    agreeing while the executable ProductVersion differs is the expected Steam
    vs PURPLE result and the basis for a shared version key."""
    labels = {key: label for key, label, _ in _SIGNALS}
    rows = []
    for key, label, cross in _SIGNALS:
        present = [i for i in installs if i.get(key)]
        if not present:
            continue
        values = {str(i.get(key)) for i in present}
        rows.append({"key": key, "label": label, "cross_launcher": cross,
                     "present_in": len(present), "total": len(installs),
                     "agrees": len(values) == 1 and len(present) == len(installs),
                     "values": sorted(values)})
    agreeing = [r for r in rows if r["agrees"]]
    shared = next((r for r in agreeing if r["key"] == "installed_content_build"), agreeing[0] if agreeing else None)
    return {"signals": rows, "shared_version_key": shared["key"] if shared else None,
            "shared_version_label": labels.get(shared["key"]) if shared else None,
            "note": ("The shipped content fingerprint matches across these installs; it is the launcher-independent "
                     "game-version key." if shared and shared["key"] == "installed_content_build" else
                     "No launcher-independent content fingerprint matched; see per-signal agreement below."
                     if not shared or shared["key"] != "installed_content_build" else "")}
