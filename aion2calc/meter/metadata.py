"""Read-only installation evidence and background official server-region metadata."""
from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

from ..paths import data_file

REGIONS = ("nae", "eu", "as", "la")
_COLLECTION_LOCK = threading.Lock()



def _steam_game_roots():
    """Read Steam library manifests, including libraries outside its own drive."""
    if sys.platform != "win32":
        return []
    import winreg
    steam = []
    for hive, key_path, value in ((winreg.HKEY_CURRENT_USER,r"Software\Valve\Steam","SteamPath"),
                                  (winreg.HKEY_LOCAL_MACHINE,r"Software\Valve\Steam","InstallPath")):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,key_path,0,winreg.KEY_READ|view) as key:
                    steam.append(Path(winreg.QueryValueEx(key,value)[0]))
            except OSError:
                continue
    for variable in ("ProgramFiles(x86)","ProgramFiles"):
        if os.environ.get(variable):
            steam.append(Path(os.environ[variable])/"Steam")
    libraries = set(steam)
    for root in steam:
        try:
            text=(root/"steamapps/libraryfolders.vdf").read_text(encoding="utf-8")
            libraries.update(Path(value.replace("\\\\","\\")) for value in re.findall(r'"path"\s+"([^"\n]+)"',text))
        except (OSError,UnicodeError):
            continue
    found=[]
    for library in sorted(libraries):
        common=(library/"steamapps/common").resolve()
        for manifest in sorted((library/"steamapps").glob("appmanifest_*.acf")):
            try:
                fields=dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"',manifest.read_text(encoding="utf-8")))
                if re.sub(r"[^a-z0-9]","",fields.get("name","").casefold()) not in ("aion2","aion2playtest"):
                    continue
                name=fields.get("installdir","")
                root=(common/name).resolve()
                if name and root.is_relative_to(common) and root.is_dir() and root not in found:
                    found.append(root)
            except (OSError,UnicodeError,ValueError):
                continue
    return found


def _installed_roots():
    if sys.platform != "win32":
        return []
    import winreg
    roots = _steam_game_roots()
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as entry:
                                name = str(winreg.QueryValueEx(entry, "DisplayName")[0]).strip().casefold()
                                if not re.fullmatch(r"aion\s*2(?:\s*[-(].*)?|아이온\s*2|永恆之塔\s*2", name):
                                    continue
                                root = Path(winreg.QueryValueEx(entry, "InstallLocation")[0])
                                if root.is_dir() and root not in roots:
                                    roots.append(root)
                        except OSError:
                            continue
            except OSError:
                continue
    return roots


def _file_version(path):
    if sys.platform != "win32" or not path.is_file():
        return None
    from ctypes import wintypes
    api = ctypes.WinDLL("version", use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    ignored = wintypes.DWORD()
    size = api.GetFileVersionInfoSizeW(str(path), ctypes.byref(ignored))
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    if not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        return None
    values = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
    if values[0] != 0xFEEF04BD:
        return None
    version = f"{values[2] >> 16}.{values[2] & 65535}.{values[3] >> 16}.{values[3] & 65535}"
    return None if version in ("0.0.0.0", "1.0.0.0") else version


def installation():
    """Return public build evidence only; never expose the installation path."""
    for root in _installed_roots():
        # Steam common/<installdir> is discovered through the registry, not a fixed drive.
        if root.parent.name.casefold() == "common":
            for manifest in sorted(root.parent.parent.glob("appmanifest_*.acf")):
                try:
                    fields = dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"', manifest.read_text(encoding="utf-8")))
                    if fields.get("installdir", "").casefold() != root.name.casefold():
                        continue
                    if fields.get("buildid", "").isdigit():
                        return {"installed_build": fields["buildid"], "installed_build_source": "Steam app manifest", "status": "ready"}
                except (OSError, UnicodeError):
                    continue
        for binary in (root / "Aion2/Binaries/Win64/AION2.exe", root / "AION2.exe"):
            version = _file_version(binary)
            if version:
                return {"installed_build": version, "installed_build_source": "Game executable version resource", "status": "ready"}
    return {"status": "unavailable", "reason": "No usable installed game build was found. Installation detection currently supports Steam libraries and registered Windows installs, including recognized PURPLE game registrations."}


class CaptureMetadata:
    def __init__(self):
        self.lock = threading.Lock()
        self.build = {"status": "detecting"}
        self.regions = {}
        self.region_status = "detecting"
        threading.Thread(target=self._collect, daemon=True, name="capture-metadata").start()

    def _collect(self):
        try:
            build = installation()
        except (OSError, ValueError):
            build = {"status": "unavailable", "reason": "Installed game metadata could not be read."}
        with self.lock:
            self.build = build
        with _COLLECTION_LOCK:
            self._collect_regions()

    def _collect_regions(self):
        cache = data_file("cache", "capture-server-regions.json")
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if (0 <= time.time() - saved["fetched_at"] < 21600
                    and isinstance(saved["regions"], dict)
                    and set(saved["regions"]) == set(REGIONS)
                    and all(isinstance(ids, list) and ids and all(isinstance(sid, str) and sid.isdigit() for sid in ids)
                            for ids in saved["regions"].values())):
                with self.lock:
                    self.regions, self.region_status = saved["regions"], "ready"
                return
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            regions = {}
            for region in REGIONS:
                request = urllib.request.Request("https://aion2.plaync.com/en-us/api/gameinfo/servers?region=" + region,
                                                 headers={"User-Agent": "Mozilla/5.0 Aion2Calc", "Accept": "application/json",
                                                          "Referer": "https://aion2.plaync.com/"})
                with urllib.request.urlopen(request, timeout=8) as response:
                    rows = json.load(response).get("serverList")
                if not isinstance(rows, list) or not rows:
                    raise ValueError("Incomplete official server metadata")
                regions[region] = [str(row["serverId"]) for row in rows if isinstance(row, dict) and str(row.get("serverId", "")).isdigit()]
                if not regions[region]:
                    raise ValueError("No official server IDs")
            with self.lock:
                self.regions, self.region_status = regions, "ready"
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix(".tmp")
                temporary.write_text(json.dumps({"fetched_at": time.time(), "regions": regions}), encoding="utf-8")
                temporary.replace(cache)
            except OSError:
                pass
        except (OSError, ValueError, KeyError, TypeError):
            with self.lock:
                self.region_status = "unavailable"

    def snapshot(self, server=None):
        with self.lock:
            matches = [region for region, servers in self.regions.items() if str(server) in servers]
            return {**self.build, "region": matches[0] if len(matches) == 1 else None,
                    "region_status": self.region_status,
                    "region_source": "Official server metadata + recorded server ID" if len(matches) == 1 else None}
