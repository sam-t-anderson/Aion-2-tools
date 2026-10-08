"""Bounded inspection and cleanup of explicitly disposable application files."""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

from .paths import home

LIMIT = 10000
DAY = 86400
HASH = r"[0-9a-f]{40}"
HELPER = r"apply-update-[0-9a-f]{8}"
PACKAGE = r"aion2calc-(?:setup-[0-9]+\.[0-9]+\.[0-9]+\.exe|[0-9]+\.[0-9]+\.[0-9]+-(?:windows-portable\.zip|macos\.zip|linux\.tar\.gz))"


def _regular(path: Path):
    info = path.stat(follow_symlinks=False)
    return info if stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400 else None


def _folder(relative: str) -> Path | None:
    root = home().resolve()
    path = root / relative
    for part in path.relative_to(root).parts:
        root = root / part
        try:
            info = root.stat(follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return None
        except OSError:
            return None
    return path


def _files(relative: str):
    folder = _folder(relative)
    if folder is None:
        return [], False
    rows = []
    truncated = False
    try:
        with os.scandir(folder) as entries:
            for index, entry in enumerate(entries):
                if index >= LIMIT:
                    truncated = True
                    break
                path = Path(entry.path)
                try:
                    info = _regular(path)
                    if info:
                        rows.append((path, info))
                except OSError:
                    continue
    except OSError:
        pass
    return rows, truncated


def _category(relative: str, name: str) -> tuple[str, int | None]:
    if relative == "cache" and re.fullmatch(HASH + r"\.(html|bin)", name):
        return "Cached web responses", 7 * DAY
    if relative == "icons" and re.fullmatch(HASH + r"\.(png|webp|jpg|jpeg|gif|svg|avif)", name):
        return "Cached images", 30 * DAY
    if relative == "cache/community-comparisons" and re.fullmatch(r"[a-zA-Z0-9_.-]+\.json", name):
        return "Community comparison cache", 7 * DAY
    if relative == "updates":
        if re.fullmatch(HELPER + r"\.(ps1|ready|log)", name):
            return "Updater helpers and logs", None
        if re.fullmatch(PACKAGE, name):
            return "Downloaded update packages", None
        if name.startswith("aion2calc-") and name.endswith(".part"):
            return "Partial update downloads", None
    return "Other files (preserved)", None


def inventory() -> dict:
    now, groups, truncated = time.time(), {}, False
    for relative in ("cache", "icons", "cache/community-comparisons", "updates"):
        rows, limited = _files(relative)
        truncated |= limited
        for path, info in rows:
            category, retention = _category(relative, path.name)
            group = groups.setdefault(category, {"category": category, "files": 0, "bytes": 0,
                                                "oldest_days": 0, "eligible_files": 0, "eligible_bytes": 0})
            age = max(0, now - info.st_mtime)
            group["files"] += 1
            group["bytes"] += info.st_size
            group["oldest_days"] = max(group["oldest_days"], round(age / DAY, 1))
            if retention is not None and age >= retention:
                group["eligible_files"] += 1
                group["eligible_bytes"] += info.st_size
    return {"groups": list(groups.values()), "truncated": truncated, "scan_limit_per_folder": LIMIT,
            "external_web_cache": bool(os.environ.get("AION2CALC_CACHE")),
            "note": "Only direct regular files in managed folders are inspected. Symlinks/junctions and external cache locations are excluded. Credentials, characters, results, logs, diagnostics, upload receipts, game data and unknown files are preserved."}


def _remove(path: Path, expected) -> bool:
    try:
        info = _regular(path)
        if info and (info.st_ino, info.st_size, info.st_mtime_ns) == (expected.st_ino, expected.st_size, expected.st_mtime_ns):
            # Recheck the fixed managed parent immediately before deleting a single file.
            relative = str(path.parent.relative_to(home().resolve()))
            if _folder(relative) == path.parent:
                path.unlink()
                return True
    except (OSError, ValueError):
        pass
    return False


def clean_caches() -> dict:
    now, deleted, freed, skipped = time.time(), 0, 0, 0
    for relative in ("cache", "icons", "cache/community-comparisons"):
        rows, _ = _files(relative)
        for path, info in rows:
            _, age = _category(relative, path.name)
            if age is None or now - info.st_mtime < age:
                continue
            if _remove(path, info):
                deleted += 1
                freed += info.st_size
            else:
                skipped += 1
    return {"deleted": deleted, "freed_bytes": freed, "skipped": skipped, "inventory": inventory()}


def _active_helpers() -> list[str] | None:
    """Failure to inspect Windows helper processes means preserve legacy scripts."""
    if sys.platform != "win32":
        return []
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = ("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -Filter "
              "\"Name='powershell.exe' OR Name='pwsh.exe'\" | "
              "Select-Object -ExpandProperty CommandLine | ConvertTo-Json -Compress")
    try:
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
                                capture_output=True, text=True, timeout=8,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return None
        value = json.loads(result.stdout or "[]")
        lines = value if isinstance(value, list) else [value]
        # A hidden/unreadable command line is ambiguous, so preserve all legacy helpers.
        return [line.casefold() for line in lines] if all(isinstance(line, str) and line for line in lines) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def clean_update_files() -> dict:
    rows, _ = _files("updates")
    now = time.time()
    candidates = [(p, i) for p, i in rows if re.fullmatch(HELPER + r"\.(ps1|ready)", p.name) and now - i.st_mtime >= 7 * DAY]
    active = _active_helpers() if candidates else []
    logs = sorted([(p, i) for p, i in rows if re.fullmatch(HELPER + r"\.log", p.name)], key=lambda row: row[1].st_mtime, reverse=True)
    # Keep at least the five latest logs, and all logs from the last month.
    if active is not None:
        candidates += [(p, i) for p, i in logs[5:] if now - i.st_mtime >= 30 * DAY]
    deleted, skipped = 0, 0
    for path, info in candidates:
        stem = path.stem.casefold()
        if active is None or any(stem in line for line in active):
            skipped += 1
            continue
        if _remove(path, info):
            deleted += 1
        else:
            skipped += 1
    # Partial downloads are deliberately preserved: a separate app may still be writing them.
    return {"deleted": deleted, "skipped": skipped}
