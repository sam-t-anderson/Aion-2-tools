"""Operator self-check: validate the local install, updater, paths, log server
and catalog in one read-only pass.

This is the operations side of validation (item 7). It does not change anything
and tolerates being offline — each check is independent and a failure is
reported, never raised. Device screenshot checks and the private server's
ownership/recovery/moderator policies live with the operator and the server
repository; what this command can verify from the client is gathered here so a
run is a single, legible status.
"""
from __future__ import annotations


def _safe(fn):
    try:
        return fn(), None
    except Exception as exc:                                   # a self-check never crashes the caller
        return None, f"{type(exc).__name__}: {exc}"


def _check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def checkup(*, network: bool = True) -> dict:
    """Return a list of operator checks with ok / warn / unavailable status."""
    from pathlib import Path
    checks = []

    from . import __version__
    from . import update
    kind, _ = _safe(update.install_kind)
    frozen, _ = _safe(update.frozen)
    checks.append(_check("version", "ok", f"aion2calc {__version__} · install: {kind or 'unknown'}"
                         f"{' · frozen build' if frozen else ''}"))

    # Updater: the auto-updater only installs a release whose main-branch CI
    # passed; report the remembered state and (online) whether one is available.
    state, _ = _safe(lambda: update._state())
    detail = "Auto-update installs only releases with green main CI."
    if isinstance(state, dict) and state.get("version"):
        detail += f" Last handled release: {state.get('version')}."
    if network and not frozen:
        info, err = _safe(update.available)
        if err:
            checks.append(_check("updater", "unavailable", detail + f" Release check failed: {err}"))
        elif info:
            checks.append(_check("updater", "warn", detail + f" Update available: {info.get('version')}."))
        else:
            checks.append(_check("updater", "ok", detail + " Up to date."))
    else:
        checks.append(_check("updater", "ok", detail + (" Source checkout; app-managed updates do not apply."
                                                        if kind == "source" else "")))

    from .paths import home, logs_dir, results_dir, user_data
    for label, getter in (("home", home), ("logs", logs_dir), ("results", results_dir), ("data", user_data)):
        path, err = _safe(getter)
        if err or path is None:
            checks.append(_check(f"path:{label}", "unavailable", err or "no path"))
            continue
        p = Path(path)
        writable, _ = _safe(lambda: (p.mkdir(parents=True, exist_ok=True) or __import__("os").access(p, 2)))
        checks.append(_check(f"path:{label}", "ok" if writable else "warn",
                             f"{p}{'' if writable else ' (not writable)'}"))

    from .combat import share
    server, _ = _safe(share.default_server)
    url = (server or {}).get("url") if isinstance(server, dict) else None
    if not url:
        checks.append(_check("log-server", "warn", "No log server configured (sharing and leaderboards are off)."))
    elif network:
        info, err = _safe(lambda: share.discover(url))
        if err:
            checks.append(_check("log-server", "unavailable", f"{url} did not answer discovery: {err}"))
        elif isinstance(info, dict):
            ver = info.get("server_version") or info.get("version") or "version not reported"
            analyzer = info.get("analyzer_version")
            checks.append(_check("log-server", "ok", f"{url} · {ver}"
                                 + (f" · analyzer {analyzer}" if analyzer else " · analyzer version not reported")))
        else:
            checks.append(_check("log-server", "warn", f"{url} returned an unexpected discovery response."))
    else:
        checks.append(_check("log-server", "ok", f"{url} (offline check; not queried)"))

    from .combat import catalog
    src, err = _safe(catalog.source)
    if err or not isinstance(src, dict) or not src:
        checks.append(_check("catalog", "warn", "No catalog source manifest; mapping provenance is unavailable."))
    else:
        matches = src.get("english_tables_match_source")
        checks.append(_check("catalog", "ok" if matches else "warn",
                             f"{src.get('repository', 'catalog')} @ {str(src.get('revision') or '')[:12]} · "
                             f"English tables {'match source' if matches else 'not confirmed'}"))

    have, total = _safe(lambda: _portrait_coverage())[0] or (0, 0)
    checks.append(_check("npc-art", "ok", f"portrait art for {have}/{total} catalog NPCs "
                         "(run `npc-evidence` to rank the observed ones still missing art)"))

    summary = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "warn", "unavailable")}
    return {"checks": checks, "summary": summary,
            "note": "Device screenshot/full-page checks and the server's ownership, recovery and moderator policies "
                    "are verified on the operator's device and in the server deployment; they are not client checks."}


def _portrait_coverage():
    from .meter.a2parser.lookup import _table
    npcs = _table("npcs", "en")
    portraits = _table("npc-portraits", "en")
    have = sum(1 for k in npcs if isinstance(portraits.get(k), dict) and portraits[k].get("icon"))
    return have, len(npcs)
