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

from ..paths import PKG_DATA, user_data, write_user_json

REGIONS = ("nae", "eu", "as", "la")
_COLLECTION_LOCK = threading.Lock()
_CONTENT_LOCK = threading.Lock()
_CONTENT_CACHE = {}



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


def _build_evidence(root):
    """Return public build evidence only; paths remain local."""
    # Steam common/<installdir> is discovered through the registry, not a fixed drive.
    if root.parent.name.casefold() == "common":
        for manifest in sorted(root.parent.parent.glob("appmanifest_*.acf")):
            try:
                fields = dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"', manifest.read_text(encoding="utf-8")))
                if fields.get("installdir", "").casefold() != root.name.casefold():
                    continue
                if fields.get("buildid", "").isdigit():
                    return {"installed_build": fields["buildid"], "installed_build_source": "Steam app manifest",
                            "installed_build_namespace": "steam:" + fields.get("appid", ""), "status": "ready"}
            except (OSError, UnicodeError):
                continue
    purple = _purple_build_evidence(root)
    if purple is not None:
        return purple
    for binary in (root / "Aion2/Binaries/Win64/AION2.exe", root / "AION2.exe"):
        version = _file_version(binary)
        if version:
            return {"installed_build": version, "installed_build_source": "Game executable version resource", "status": "ready"}
    return {"status": "unavailable", "reason": "No usable version resource or Steam build ID was found."}


def _content_fingerprint(root):
    """Expected gameplay content: index/signature bytes and payload lengths, excluding L10N."""
    folder = root / "Aion2/Content/Paks"
    try:
        files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in (".utoc", ".sig", ".pak", ".ucas"))
        if not files or len(files) > 4096 or not any(p.suffix == ".utoc" for p in files):
            return None
        stats = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files]
        if sum(size for name, size, _ in stats if Path(name).suffix in (".utoc", ".sig")) > 512 * 1024 * 1024:
            return None
        key = str(folder.resolve())
        with _CONTENT_LOCK:
            cached = _CONTENT_CACHE.get(key)
            if cached and cached[0] == stats:
                return cached[1]
            rows = [[p.name, size, hashlib.sha256(p.read_bytes()).hexdigest() if p.suffix in (".utoc", ".sig") else None]
                    for p, (_, size, _) in zip(files, stats)]
            if stats != [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files]:
                return None
            digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
            if len(_CONTENT_CACHE) >= 8:
                _CONTENT_CACHE.clear()
            _CONTENT_CACHE[key] = (stats, digest)
            return digest
    except (OSError, ValueError):
        return None


def _comparison_build_evidence(root, evidence):
    if evidence.get("status") != "ready":
        return evidence
    fingerprint = _content_fingerprint(root)
    if not fingerprint:
        return evidence
    candidates = []
    try:
        catalog = json.loads((PKG_DATA / "global/build_equivalence.json").read_text(encoding="utf-8"))
        for row in catalog.get("aliases", []):
            if row.get("fingerprint") == fingerprint:
                candidates.append((row.get("comparison_namespace"), row.get("comparison_build")))
    except (OSError, ValueError, TypeError):
        pass
    # New builds can be compared directly when both launchers are installed.
    if not candidates and str(evidence.get("installed_build_namespace", "")).startswith("purple:"):
        for steam_root in _steam_game_roots():
            other = _build_evidence(steam_root)
            if other.get("status") == "ready" and _content_fingerprint(steam_root) == fingerprint:
                candidates.append((other.get("installed_build_namespace"), other.get("installed_build")))
    candidates = {(ns, build) for ns, build in candidates
                  if isinstance(ns, str) and re.fullmatch(r"steam:[0-9]{1,12}", ns)
                  and isinstance(build, str) and re.fullmatch(r"[0-9]{1,20}", build)}
    if len(candidates) != 1:
        return evidence
    namespace, build = candidates.pop()
    return {**evidence, "comparison_build_namespace": namespace, "comparison_build": build,
            "installed_build_fingerprint": fingerprint,
            "comparison_build_source": "Matching gameplay content indexes, signatures and package lengths across launcher installs"}


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
        evidence = _comparison_build_evidence(root, _build_evidence(root))
        launcher = ("Steam" if root.parent.name.casefold() == "common" else
                    "PURPLE" if evidence.get("installed_build_namespace", "").startswith("purple:") else
                    "Registered Windows install")
        label = f"{launcher} · {root.name} · {root.drive or 'local'}"
        if evidence.get("installed_build"):
            label += " · build " + evidence["installed_build"]
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
        return _comparison_build_evidence(roots[0], _build_evidence(roots[0]))
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
