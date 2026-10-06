"""Close only Chromium processes using Aion 2 Calc's dedicated profile."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _arguments(command: str) -> list[str]:
    import ctypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:
        return []
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(argv)


def _owns_profile(arguments: list[str], profile: Path) -> bool:
    expected = os.path.normcase(str(profile.resolve()))
    for index, arg in enumerate(arguments):
        if arg.startswith("--user-data-dir="):
            value = arg.partition("=")[2]
        elif arg == "--user-data-dir" and index + 1 < len(arguments):
            value = arguments[index + 1]
        else:
            continue
        if os.path.normcase(str(Path(value).resolve())) == expected:
            return True
    return False


def close_app_browser() -> None:
    if sys.platform != "win32":
        return
    from ..paths import home
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' OR Name='chrome.exe'\" | "
              "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run([str(shell), "-NoProfile", "-Command", script], capture_output=True,
                            text=True, timeout=10, creationflags=flags)
    rows = json.loads(result.stdout or "[]") or []
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        command = row.get("CommandLine") or ""
        if _owns_profile(_arguments(command), home() / "window"):
            pid = int(row["ProcessId"])
            subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, creationflags=flags)
