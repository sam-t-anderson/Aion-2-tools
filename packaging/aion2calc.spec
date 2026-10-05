# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build of the aion2calc client:  pyinstaller packaging/aion2calc.spec --noconfirm
# Output: dist/aion2calc/ (the app folder; aion2calc.exe on Windows), and dist/aion2calc.app on macOS.
import os
import re
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PLAT = {"win32": "win", "darwin": "osx"}.get(sys.platform, "linux")

datas = collect_data_files("aion2calc")
binaries = []
hiddenimports = collect_submodules("aion2calc")          # class kits are imported by name

# Bundle pywebview (Windows) so the app can open the transparent overlay with no extra install. Guarded
# so a missing package never fails the build; the overlay falls back to a browser window without it.
if sys.platform == "win32":
    for pkg in ("webview", "clr_loader", "pythonnet"):
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception as err:
            print(f"aion2calc.spec: skipping {pkg} ({err})")

# Bundle the in-process HiGHS solver (highspy) on every platform so the packaged app never falls back
# to CBC's external subprocess, which hangs in the windowed build at the Daevanion solve.
try:
    d, b, h = collect_all("highspy")
    datas += d
    binaries += b
    hiddenimports += h
except Exception as err:
    print(f"aion2calc.spec: skipping highspy ({err})")
# PuLP ships CBC solver binaries for every platform; keep this platform's only
datas += [d for d in collect_data_files("pulp") if "solverdir" not in d[0] or os.sep + PLAT + os.sep in d[0]
          or "/" + PLAT + "/" in d[0]]
# PuLP looks for its solver at pulp/apis/../solverdir; the folder must exist in the bundle
datas += [(os.path.join(SPECPATH, "pulp_apis_keep.txt"), os.path.join("pulp", "apis"))]
datas += [(os.path.join(ROOT, "results"), "results"), (os.path.join(ROOT, "example"), "example")]
if os.path.exists(os.path.join(SPECPATH, "client.json")):          # optional log-server preset
    datas.append((os.path.join(SPECPATH, "client.json"), "."))

# Windows file properties (product name and version), which code signing checks
with open(os.path.join(ROOT, "aion2calc", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__ = "([^"]+)"', f.read()).group(1)
version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(int(x) for x in VERSION.split(".")[:3]) + (0,)
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "aion2calc"),
            StringStruct("FileDescription", "aion2calc: AION 2 build planner and combat analyzer"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "aion2calc"),
            StringStruct("LegalCopyright", "GPL-3.0, https://github.com/sam-t-anderson/Aion-2-tools"),
            StringStruct("OriginalFilename", "aion2calc.exe"),
            StringStruct("ProductName", "aion2calc"),
            StringStruct("ProductVersion", VERSION)])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "IPython", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="aion2calc",
    console=False,                       # no console window; the app has a Quit button
    icon=os.path.join(SPECPATH, "aion2calc.ico"),
    version=version_info,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="aion2calc", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="aion2calc.app", icon=os.path.join(SPECPATH, "aion2calc.png"),
                 bundle_identifier="io.github.aion2calc")
