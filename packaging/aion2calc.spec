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

# Bundle pystray (+ its platform backend) so "collapse to tray" works with no extra
# install. Guarded: a missing package never fails the build; the app then keeps the
# default "closing the window stops the app" behaviour instead.
for pkg in ("pystray",):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as err:
        print(f"aion2calc.spec: skipping {pkg} ({err})")
# pystray imports its backend lazily by platform; name them so PyInstaller keeps one.
hiddenimports += {"win32": ["pystray._win32"], "darwin": ["pystray._darwin"]}.get(
    sys.platform, ["pystray._xorg", "pystray._appindicator", "pystray._gtk"])

# Bundle the in-process HiGHS solver (highspy) on every platform so the packaged app never falls back
# to CBC's external subprocess, which hangs in the windowed build at the Daevanion solve. highspy is a
# required dependency, so import it up front: that fails the build loudly if it is missing, instead of
# silently shipping a bundle whose optimizer and community comparisons always raise "HiGHS unavailable".
# (Its native libraries are pulled in by PyInstaller's own module analysis, so collect_all's "binaries"
# list is legitimately empty on Linux/Windows -- do not gate the build on it.)
import highspy
d, b, h = collect_all("highspy")
datas += d
binaries += b
hiddenimports += h
if sys.platform == "win32":
    # The Windows wheel keeps its private HiGHS DLL in the sibling ``highspy.libs`` directory (vendored
    # by delvewheel, which patches highspy/__init__.py to add that directory to the DLL search path).
    # PyInstaller collects the extension module but not this wheel-specific sibling. Copy every file
    # there -- including delvewheel's ``.load-order`` manifest -- into the matching ``highspy.libs``
    # folder so the loader finds it, and the DLLs also into the bundle root as a fallback search path.
    highs_libs = os.path.join(os.path.dirname(highspy.__file__), "..", "highspy.libs")
    if os.path.isdir(highs_libs):
        for name in os.listdir(highs_libs):
            src = os.path.join(highs_libs, name)
            if not os.path.isfile(src):
                continue
            if name.lower().endswith(".dll"):
                binaries += [(src, "highspy.libs"), (src, ".")]
            else:
                datas += [(src, "highspy.libs")]
    # HiGHS is a C++ library, so highs.dll depends on the Microsoft Visual C++ runtime (msvcp140*,
    # vcruntime140_1, the C++ exception/STL runtime). PyInstaller bundles only the C runtime CPython
    # itself needs, so on a machine without the "Visual C++ 2015-2022 Redistributable" the HiGHS DLL
    # cannot load and the solver reports itself unavailable -- even though the build's own smoke test
    # passes, because CI runners have the redistributable installed. Bundle the C++ runtime from the
    # build machine so the solver loads on a clean install too.
    sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    for dll in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll",
                "vcruntime140_1.dll", "concrt140.dll", "vcomp140.dll"):
        src = os.path.join(sys32, dll)
        if os.path.isfile(src):
            binaries.append((src, "."))
# The live meter imports its capture and decompression backends on demand.  Collecting them
# explicitly keeps the feature available in the desktop bundle as well as in source installs.
for pkg in ("scapy", "lz4"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as err:
        print(f"aion2calc.spec: skipping {pkg} ({err})")
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
            StringStruct("CompanyName", "Aion 2 Calc"),
            StringStruct("FileDescription", "Aion 2 Calc: AION 2 build planner and combat analyzer"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "aion2calc"),
            StringStruct("LegalCopyright", "GPL-3.0, https://github.com/sam-t-anderson/Aion-2-tools"),
            StringStruct("OriginalFilename", "aion2calc.exe"),
            StringStruct("ProductName", "Aion 2 Calc"),
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
