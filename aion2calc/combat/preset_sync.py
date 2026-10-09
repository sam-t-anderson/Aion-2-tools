"""Bounded v2 preset sync from the configured community server."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request

from ..paths import list_names, read_json, write_user_json, bundled_model_data
from ..presets import BUDGETS, MAX_BYTES, InvalidPreset, candidate as legacy_candidate, parse
from .share import effective

_LOCK = threading.Lock()
HEX = re.compile(r"[0-9a-f]{64}")


def _base():
    return str(effective().get("url") or "").rstrip("/")


class _NoPostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Preset POST redirects are not followed", headers, fp)


def _request(base, path, body=None):
    headers = {"User-Agent": "aion2calc"}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        settings = effective()
        if str(settings.get("url") or "").rstrip("/") != base:
            raise ValueError("Community server changed; retry submission")
        key = settings.get("key")
        if key:
            headers["Authorization"] = "Bearer " + key
        payload = json.dumps(body, allow_nan=False).encode()
        if len(payload) > MAX_BYTES:
            raise ValueError("Preset exceeds 100 KB")
    request = urllib.request.Request(base + path, payload, headers)
    open_request = urllib.request.build_opener(_NoPostRedirect()).open if body is not None else urllib.request.urlopen
    with open_request(request, timeout=8) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Preset response exceeds 100 KB")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Expected a preset response object")
    return result


def _supported(base):
    try:
        return _request(base, "/.well-known/a2log.json").get("canonical_presets_version") == 2
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _number(value):
    try:
        return type(value) in (float, int) and math.isfinite(value)
    except OverflowError:
        return False


@bundled_model_data
def _validate(remote, cls, mode, scope):
    from ..model.stats import Stats
    primary, secondary = ("pvp", "pvp_burst") if mode == "pvp" else ("boss", "dummy")
    summary = remote["build"]
    policy = summary["scoring_policy"]
    if (remote.get("class") != cls or remote.get("mode") != mode or remote.get("scope") != scope
            or summary.get("class") != cls or summary.get("mode") != mode
            or summary.get("scenario") != primary or summary.get("loadout") != f"{cls}_l45_global_median"
            or policy.get("class") != cls or policy.get("mode") != mode or policy.get("scope") != scope
            or policy.get("version") not in (1, 2)
            or not isinstance(policy.get("budgets"), dict) or set(policy["budgets"]) != set(BUDGETS)
            or any(type(v) is not int or not 0 <= v <= 10000 for v in policy["budgets"].values())
            or (policy.get("version") == 1 and policy["budgets"] != BUDGETS)
            or policy.get("weights") != {primary: .5, secondary: .5}
            or policy.get("durations") != {primary: 180, secondary: 30 if mode == "pvp" else 180}
            or policy.get("calibration") != "disabled"):
        raise ValueError("Preset context does not match the supported scoring policy")
    hashed = {k: v for k, v in policy.items() if k != "scope"}
    digest = hashlib.sha256(json.dumps(hashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    if digest != scope:
        raise ValueError("Preset policy fingerprint is inconsistent")
    score = remote["score"]
    values = summary["dps"]
    if not _number(score) or score <= 0 or any(not _number(values.get(k)) or values[k] <= 0 for k in (primary, secondary)):
        raise ValueError("Preset scores must be finite positive numbers")
    expected = .5 * values[primary] + .5 * values[secondary]
    if not _number(summary.get("score")) or not math.isclose(score, expected, rel_tol=1e-8) or not math.isclose(summary["score"], score, rel_tol=1e-8):
        raise ValueError("Preset weighted score is inconsistent")
    lo = summary["loadout_snapshot"]
    if not isinstance(lo, dict) or lo.get("level") != 45 or not isinstance(lo.get("components"), list) or len(lo["components"]) > 128:
        raise ValueError("Preset needs a bounded common-loadout snapshot")
    for component in lo["components"]:
        if not isinstance(component, dict) or not isinstance(component.get("slot"), str) or not isinstance(component.get("stats"), dict):
            raise ValueError("Invalid preset loadout component")
        for field, value in component["stats"].items():
            if field == "skill_bonus":
                if not isinstance(value, dict) or len(value) > 128 or any(not str(k).isdigit() or len(str(k)) > 10 or type(v) is not int or not 0 <= v <= 100 for k, v in value.items()):
                    raise ValueError("Invalid preset skill bonuses")
            elif field not in Stats.__dataclass_fields__ or not _number(value) or abs(value) > 1e9:
                raise ValueError("Invalid preset stats")
    parse({"format": "a2preset", "version": 1, "class": cls, "build": legacy_candidate(summary)["build"]},
          scenario_name=primary, loadout_snapshot=lo, budgets=policy["budgets"])
    if not _number(remote.get("updated_at")):
        raise ValueError("Invalid preset update time")
    return summary


def sync() -> list[str]:
    changed = []
    base = _base()
    if not base:
        return changed
    with _LOCK:
        try:
            if not _supported(base):
                return changed
            listing = _request(base, "/api/v2/presets")
            if not isinstance(listing.get("presets"), list):
                return changed
            classes = set(list_names("global", "classes"))
            entries, seen = [], set()
            for row in listing["presets"][:2 * len(classes)]:
                if not isinstance(row, dict):
                    continue
                cls, mode, scope = row.get("class"), row.get("mode"), row.get("scope")
                if not isinstance(cls, str) or cls not in classes or mode not in ("pve", "pvp") or not isinstance(scope, str) or not HEX.fullmatch(scope) or (cls, mode) in seen:
                    continue
                seen.add((cls, mode))
                name = f"{cls}_{mode}"
                entries.append({"class": cls, "mode": mode, "scope": scope})
                try:
                    cached = read_json("community_presets_v2", name + ".json")
                except (OSError, ValueError):
                    cached = {}
                if not isinstance(cached, dict):
                    cached = {}
                if cached.get("source") == base and cached.get("scope") == scope and cached.get("updated_at") == row.get("updated_at"):
                    continue
                try:
                    remote = _request(base, f"/api/v2/presets/{cls}/{mode}")
                    summary = _validate(remote, cls, mode, scope)
                    if _base() != base:
                        return changed
                    write_user_json({"source": base, "scope": scope, "updated_at": remote["updated_at"], "build": summary},
                                    "community_presets_v2", name + ".json")
                    changed.append(name)
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    continue
            if _base() == base:
                write_user_json({"source": base, "checked_at": time.time(), "presets": entries}, "community_presets_v2", "index.json")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    return changed


def cached_presets() -> list[dict]:
    try:
        index = read_json("community_presets_v2", "index.json")
        if index.get("source") != _base():
            return []
        classes = set(list_names("global", "classes"))
        rows = []
        for row in index.get("presets", [])[:2 * len(classes)]:
            cls, mode, scope = row["class"], row["mode"], row["scope"]
            if cls not in classes or mode not in ("pve", "pvp"):
                continue
            try:
                cached = read_json("community_presets_v2", f"{cls}_{mode}.json")
            except (OSError, ValueError):
                continue
            if not isinstance(cached, dict):
                continue
            if cached.get("source") == index["source"] and cached.get("scope") == scope:
                rows.append({**cached, "class": cls, "mode": mode, "checked_at": index["checked_at"]})
        return rows
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def submit(summary: dict) -> dict | None:
    """None means confirmed v2 absence, allowing the existing v1 path to run."""
    base = _base()
    if not base:
        return None
    try:
        if not _supported(base):
            return None
        from ..canonical_presets import candidate
        mode = "pvp" if str(summary.get("scenario", "")).startswith("pvp") else "pve"
        cls = summary["class"]
        if cls not in set(list_names("global", "classes")):
            raise InvalidPreset("unknown class")
        policy = _request(base, f"/api/v2/presets/{cls}/{mode}/policy")
        document = candidate(summary, policy)
        if _base() != base:
            raise ValueError("Community server changed; retry submission")
        result = _request(base, "/api/v2/presets", document)
        if result.get("accepted"):
            threading.Thread(target=sync, daemon=True, name="canonical-preset-refresh").start()
        return {**result, "submitted": True}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"submitted": False, "reason": "Canonical preset submission unavailable: " + str(exc)}
