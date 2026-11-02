"""Temporary probe, removed before merge: the real app and the real overlay host on a Windows desktop.

A green window owned by a process named like the game's executable stands in for the game, so the overlay shows
over it. The app runs from this checkout with a fresh home; for each background mode the overlay process starts,
the screen is read back over the overlay's window, and the share of pure green there says whether the game shows
between the pieces. The overlay's own log follows."""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from ctypes import wintypes

OUT, NAME, MODES = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
os.makedirs(OUT, exist_ok=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = ctypes.c_void_p
user32.GetWindowRgnBox.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]


def log(*parts):
    print(f"[{NAME}]", *parts, flush=True)


home = tempfile.mkdtemp(prefix="a2home")
env = {**os.environ, "AION2CALC_HOME": home, "PYTHONUNBUFFERED": "1"}
game_exe = os.path.join(os.path.dirname(sys.executable), "aion2.exe")
if not os.path.exists(game_exe):
    shutil.copy(sys.executable, game_exe)
game = subprocess.Popen([game_exe, "-c", "import tkinter as tk\nr=tk.Tk()\nr.title('AION2')\n"
                         "r.geometry('1000x720+0+0')\nr.configure(bg='#00ff00')\nr.mainloop()"])
PORT = 8791
app_log = open(os.path.join(OUT, f"app-{NAME}.log"), "w")
app = subprocess.Popen([sys.executable, "-m", "aion2calc", "app", "--no-browser", "--no-sync", "--port", str(PORT)],
                       env=env, stdout=app_log, stderr=subprocess.STDOUT)
base = f"http://127.0.0.1:{PORT}"
for _ in range(300):
    try:
        urllib.request.urlopen(base + "/api/ui", timeout=2)
        break
    except OSError:
        time.sleep(0.3)
else:
    log("the app never answered")


def post_ui(body):
    request = urllib.request.Request(base + "/api/ui", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(request, timeout=10).read() or b"{}")


try:
    for mode in MODES:
        post_ui({"overlay_bg_mode": mode})
        overlay = subprocess.Popen([sys.executable, "-m", "aion2calc.overlay", "--url", base + "/overlay"], env=env)
        hwnd = None
        for _ in range(120):
            hwnd = user32.FindWindowW(None, "Aion 2 Calc Overlay")
            if hwnd and user32.IsWindowVisible(hwnd):
                break
            time.sleep(0.25)
        time.sleep(8)
        if not hwnd:
            log(mode, "no overlay window")
            overlay.kill()
            continue
        rect, box = wintypes.RECT(), wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        kind = user32.GetWindowRgnBox(hwnd, ctypes.byref(box))
        from PIL import ImageGrab
        shot = ImageGrab.grab(all_screens=True)
        crop = shot.crop((rect.left, rect.top, rect.right, rect.bottom)).convert("RGB")
        crop.save(os.path.join(OUT, f"{NAME}-{mode}.png"))
        shot.crop((0, 0, 1000, 720)).save(os.path.join(OUT, f"{NAME}-{mode}-screen.png"))
        pixels = list(crop.getdata())
        green = sum(1 for p in pixels if p == (0, 255, 0))
        log(mode, json.dumps({"window": [rect.left, rect.top, rect.right, rect.bottom],
                              "region": {0: "none", 1: "null", 2: "simple", 3: "complex"}.get(kind, kind),
                              "region_box": [box.left, box.top, box.right, box.bottom],
                              "green_share": round(green / max(1, len(pixels)), 4)}))
        subprocess.run(["taskkill", "/PID", str(overlay.pid), "/T", "/F"], capture_output=True)
        time.sleep(2)
finally:
    path = os.path.join(home, "logs", "overlay.log")
    if os.path.exists(path):
        log("overlay.log:\n" + open(path, encoding="utf-8", errors="replace").read()[-6000:])
    else:
        found = [os.path.join(d, f) for d, _, fs in os.walk(home) for f in fs if f.endswith(".log")]
        log("logs in home:", found)
    app.kill()
    game.kill()
