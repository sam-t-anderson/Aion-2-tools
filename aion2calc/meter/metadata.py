"""Read-only installation evidence and background official server-region metadata."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from ..paths import user_data, write_user_json

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


def _file_version(path, *, product=False):
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
    if product:
        # Explorer's Product version is StringFileInfo, not the engine's fixed DWORD version.
        translations = ctypes.c_void_p()
        translation_length = wintypes.UINT()
        if not api.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(translations), ctypes.byref(translation_length)):
            return None
        if not translations.value or not 4 <= translation_length.value <= 256 or translation_length.value % 4:
            return None
        words = ctypes.cast(translations, ctypes.POINTER(wintypes.WORD))
        versions = set()
        for index in range(translation_length.value // 4):
            block = f"\\StringFileInfo\\{words[2*index]:04x}{words[2*index+1]:04x}\\ProductVersion"
            value, value_length = ctypes.c_void_p(), wintypes.UINT()
            if api.VerQueryValueW(buffer, block, ctypes.byref(value), ctypes.byref(value_length)) and value.value and 1 <= value_length.value <= 128:
                text = ctypes.wstring_at(value, value_length.value).rstrip("\0").strip()
                if re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,12}){1,7}", text) and text != "0.0.0.0":
                    versions.add(text)
        return versions.pop() if len(versions) == 1 else None
    values = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
    if values[0] != 0xFEEF04BD:
        return None
    version = f"{values[2] >> 16}.{values[2] & 65535}.{values[3] >> 16}.{values[3] & 65535}"
    return None if version in ("0.0.0.0", "1.0.0.0") else version


def _purple_build_evidence(root):
    """Read the observed PURPLE launcher revision, not the engine executable version."""
    manifests = sorted(root.glob("VersionInfo_A2_*_PURPLE.xml"))
    if not manifests:
        return None
    revisions = set()
    try:
        if len(manifests) > 8:
            raise ValueError("Too many launcher manifests")
        for path in manifests:
            if not re.fullmatch(r"VersionInfo_(A2_[A-Z0-9_]+_PURPLE)\.xml", path.name):
                raise ValueError("Unrecognized launcher namespace")
            if path.stat().st_size > 16384:
                raise ValueError("Launcher manifest too large")
            tree = ET.fromstring(path.read_bytes())
            version = (tree.findtext("Version") or "").strip()
            if tree.tag != "VersionInfo" or tree.findtext("Updated") != "1" or not re.fullmatch(r"[0-9]{1,20}", version) or int(version) <= 0:
                raise ValueError("Incomplete launcher revision")
            namespace = "purple:" + path.stem.removeprefix("VersionInfo_")
            revisions.add((namespace, version))
        if len(revisions) != 1:
            raise ValueError("Conflicting launcher revisions")
        namespace, version = revisions.pop()
        return {"installed_build": version, "installed_build_source": "PURPLE VersionInfo launcher revision",
                "installed_build_namespace": namespace, "status": "ready"}
    except (OSError, ValueError, ET.ParseError):
        return {"status": "unavailable", "reason": "PURPLE launcher revision is incomplete, conflicting or unreadable."}


#: The PURPLE (NCSOFT launcher) application id for AION 2 Global, as it names
#: its per-app data folder under %LOCALAPPDATA%\NCSOFT\NccrData.
_PURPLE_APP = "com.ncsoft.aion2global"


def _parse_purple_execution(data) -> dict | None:
    """One launcher execution breadcrumb -> a bounded PURPLE version signal.

    The NCSOFT launcher writes an ``<id>.execution.json`` per game launch with
    the game's ``appVersion`` ("2.0.6-Rev1424533.020d67") and ``appBuildNumber``.
    It carries the game's own version and build, independent of the executable's
    launcher-stamped ProductVersion, so it is a cross-check and a presence
    signal. Only these two bounded fields are read; account ids in the sibling
    ``extra.json`` are never touched. Returns ``None`` when the fields are
    missing or malformed rather than guessing."""
    if not isinstance(data, dict):
        return None
    version = str(data.get("appVersion") or "").strip()
    build = str(data.get("appBuildNumber") or "").strip()
    core = re.match(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}", version)
    if not core or len(version) > 64 or (build and not re.fullmatch(r"[0-9]{1,12}", build)):
        return None
    return {"purple_app": _PURPLE_APP, "purple_app_version": version,
            "purple_app_core_version": core.group(0), "purple_build_number": build or None,
            "purple_launcher_source": r"NCSOFT launcher execution breadcrumb (%LOCALAPPDATA%\NCSOFT\NccrData)"}


def purple_launcher_evidence(local_appdata=None) -> dict | None:
    """The newest PURPLE launcher version breadcrumb for AION 2 Global, if present.

    Reads the most recent ``*.execution.json`` under
    ``%LOCALAPPDATA%\\NCSOFT\\NccrData\\com.ncsoft.aion2global``. Its presence
    confirms a PURPLE AION 2 Global install on this machine even when the
    Windows uninstall entry that locates the folder is missing; the breadcrumb
    gives the game version but not the install path. Read-only and bounded;
    returns ``None`` when absent or unreadable."""
    base = local_appdata or (os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None)
    if not base:
        return None
    folder = Path(base) / "NCSOFT" / "NccrData" / _PURPLE_APP
    if not folder.is_dir():
        return None
    try:
        files = sorted((p for p in folder.glob("*.execution.json") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    except OSError:
        return None
    for path in files:
        try:
            if path.stat().st_size > 16384:
                continue
            parsed = _parse_purple_execution(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if parsed:
            return parsed
    return None


#: Where Unreal ships the game content packages, relative to an install root.
_PAK_DIRS = ("Aion2/Content/Paks", "Content/Paks")
#: Package extensions that hold shipped game content (the same across launchers
#: for one patch). Signatures (.sig) and launcher chunk manifests are excluded
#: because a store can re-sign or re-chunk identical content.
_PAK_SUFFIXES = (".pak", ".utoc", ".ucas")


def _content_fingerprint(root):
    """A launcher-independent content signal from the shipped package set.

    The executable's ProductVersion resource is stamped per launcher, so Steam
    and PURPLE installs of the same patch disagree on it. The Unreal content
    packages, however, are the same bytes on both; their sorted ``(name, size)``
    manifest is a cheap, store-independent fingerprint of the installed content.
    The file name alone is used, never its parent folder, because the launchers
    nest ``Content/Paks`` differently (PURPLE under ``Aion2/``, Steam at the
    root) — keying on the path would make identical content hash differently
    across launchers, defeating the purpose. Full file hashing is avoided (paks
    are gigabytes); name+size already changes on any content patch. Read-only
    and bounded; returns ``{}`` when no package directory is present.
    """
    files = []
    try:
        for relative in _PAK_DIRS:
            directory = root / relative
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                if entry.suffix.casefold() in _PAK_SUFFIXES and entry.is_file():
                    files.append((entry.name, entry.stat().st_size))   # name only: the parent folder differs by
                if len(files) >= 16384:                      # launcher (Aion2/Content/Paks vs Content/Paks), and
                    break                                    # a full AION 2 install is ~1k package files (bounded)
            if files:
                break
    except OSError:
        return {}
    if not files:
        return {}
    files.sort()
    manifest = [[name, size] for name, size in files]
    digest = hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    return {"installed_content_build": "content:" + digest,
            "installed_content_namespace": "aion2:content",
            "installed_content_source": f"Shipped package set ({len(files)} files, "
                                        f"{sum(s for _, s in files):,} bytes) name+size fingerprint",
            "installed_content_manifest": manifest}


def _build_evidence(root):
    """Use the game's ProductVersion string; retain launcher IDs only as diagnostic evidence."""
    launcher = _purple_build_evidence(root) or {}
    if root.parent.name.casefold() == "common":
        for manifest in sorted(root.parent.parent.glob("appmanifest_*.acf")):
            try:
                fields = dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"', manifest.read_text(encoding="utf-8")))
                if fields.get("installdir", "").casefold() == root.name.casefold() and fields.get("buildid", "").isdigit():
                    launcher = {"installed_build": fields["buildid"], "installed_build_namespace": "steam:" + fields.get("appid", ""),
                                "installed_build_source": "Steam app manifest"}
                    break
            except (OSError, UnicodeError):
                continue
    evidence = {"launcher_build": launcher.get("installed_build"), "launcher_build_namespace": launcher.get("installed_build_namespace"),
                "launcher_build_source": launcher.get("installed_build_source")}
    evidence = {key: value for key, value in evidence.items() if value}
    evidence.update(_content_fingerprint(root))              # launcher-independent content signal (diagnostic)
    for binary in (root / "Aion2/Binaries/Win64/AION2.exe", root / "AION2.exe"):
        version = _file_version(binary, product=True)
        if version:
            return {**evidence, "installed_build": version, "installed_build_source": "Game executable ProductVersion string",
                    "installed_build_namespace": "aion2:product", "file_version": _file_version(binary), "status": "ready"}
    if evidence.get("installed_content_build"):              # no executable version, but content is identifiable
        return {**evidence, "status": "ready", "installed_build_source": "Shipped content fingerprint (executable ProductVersion unavailable)"}
    return {**evidence, "status": "unavailable", "reason": "No unambiguous game executable ProductVersion string was found. Launcher IDs and engine file versions are diagnostic evidence only."}


def _installation_id(root):
    return hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()[:24]


def selected_installation():
    try:
        saved = json.loads((user_data() / "capture-installation.json").read_text(encoding="utf-8"))
        value = saved.get("id", "")
        return value if isinstance(value, str) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def installation_options():
    rows = []
    for root in _installed_roots():
        evidence = _build_evidence(root)
        launcher = ("Steam" if root.parent.name.casefold() == "common" else
                    "PURPLE" if evidence.get("launcher_build_namespace", "").startswith("purple:") else
                    "Registered Windows install")
        label = f"{launcher} · {root.name} · {root.drive or 'local'}"
        if evidence.get("installed_build"):
            label += " · Product version " + evidence["installed_build"]
        if evidence.get("installed_content_build"):
            label += " · content " + evidence["installed_content_build"].removeprefix("content:")[:8]
        rows.append({"id": _installation_id(root), "label": label, **evidence})
    selected = selected_installation()
    return {"installations": rows, "selected": selected,
            "selection_required": not selected and len(rows) > 1}


def choose_installation(value):
    if not isinstance(value, str) or (value and value not in {_installation_id(root) for root in _installed_roots()}):
        raise ValueError("Choose an installation discovered on this computer, or Auto.")
    write_user_json({"id": value}, "capture-installation.json")
    return installation_options()


def installation(selected=None):
    selected = selected_installation() if selected is None else selected
    roots = _installed_roots()
    if selected:
        roots = [root for root in roots if _installation_id(root) == selected]
        if not roots:
            return {"status": "unavailable", "reason": "The selected game installation is no longer available. Refresh installations and select another before a new session."}
    elif len(roots) > 1:
        return {"status": "selection_required", "reason": "Multiple game installations were found. Select one before starting a new session."}
    if roots:
        return _build_evidence(roots[0])
    return {"status": "unavailable", "reason": "No registered game installation was found. Detection supports Steam libraries and recognized Windows game registrations, including PURPLE."}


class CaptureMetadata:
    def __init__(self):
        self.lock = threading.Lock()
        self.selected = selected_installation()
        self.build = {"status": "detecting"}
        self.regions = {}
        self.region_status = "detecting"
        threading.Thread(target=self._collect, daemon=True, name="capture-metadata").start()

    def _collect(self):
        try:
            build = installation(self.selected)
        except (OSError, ValueError):
            build = {"status": "unavailable", "reason": "Installed game metadata could not be read."}
        with self.lock:
            self.build = build
        with _COLLECTION_LOCK:
            self._collect_regions()

    def _collect_regions(self):
        cache = user_data() / "cache" / "capture-server-regions.json"
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
            from .builds import resolve
            region = matches[0] if len(matches) == 1 else None
            return {**self.build, **resolve(self.build), "region": region,
                    "region_status": self.region_status,
                    "region_source": "Official server metadata + recorded server ID" if len(matches) == 1 else None}
