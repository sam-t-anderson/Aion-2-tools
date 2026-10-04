# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build of the aion2calc client:  pyinstaller packaging/aion2calc.spec --noconfirm
# Output: dist/aion2calc/ (the app folder; aion2calc.exe on Windows), and dist/aion2calc.app on macOS.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PLAT = {"win32": "win", "darwin": "osx"}.get(sys.platform, "linux")

datas = collect_data_files("aion2calc")
# PuLP ships CBC solver binaries for every platform; keep this platform's only
datas += [d for d in collect_data_files("pulp") if "solverdir" not in d[0] or os.sep + PLAT + os.sep in d[0]
          or "/" + PLAT + "/" in d[0]]
# PuLP looks for its solver at pulp/apis/../solverdir; the folder must exist in the bundle
datas += [(os.path.join(SPECPATH, "pulp_apis_keep.txt"), os.path.join("pulp", "apis"))]
datas += [(os.path.join(ROOT, "results"), "results"), (os.path.join(ROOT, "example"), "example")]
if os.path.exists(os.path.join(SPECPATH, "client.json")):          # optional log-server preset
    datas.append((os.path.join(SPECPATH, "client.json"), "."))

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=collect_submodules("aion2calc"),          # class kits are imported by name
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
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="aion2calc", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="aion2calc.app", icon=os.path.join(SPECPATH, "aion2calc.png"),
                 bundle_identifier="io.github.aion2calc")
