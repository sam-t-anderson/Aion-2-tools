"""The overlay's window on a real Windows desktop (CI, 0.2.371): the see-through background modes show the game
between their pieces, in the light and the dark app themes.

The app runs from this checkout with a fresh home. A window owned by a process named like the game's executable
stands in for the game, pure green, so the overlay shows over it. For each background mode the overlay process
starts and the screen is read back over its window: the share of pure green there is how much of the game shows
through. Until 0.2.371 a dark app theme made DWM paint a backdrop across the whole window, outside its region, so
the see-through modes showed a dark box on a dark desktop while every check made in a browser passed.

Usage: python tools/overlay_window_check.py THEME [OUTDIR], THEME light or dark; the caller sets the theme. Exits 1
with the overlay's log when a mode fails."""
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

THEME = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "overlay-window-check"
os.makedirs(OUT, exist_ok=True)
GREEN, GREY = (0, 255, 0), ((23, 95, 23), (32, 32, 32))      # the game; the dark backdrop alone and at the opacity
SEE_THROUGH = 0.15                                           # the least share of the game the light theme shows is 0.35
# How long the page may take to load and send its outline. On a fresh runner the first overlays took 13 s and more
# (the dark pass right after took 1-2 s), and until then the window shows only the game, or a flat fill at its first
# size, so no mode is judged before Windows holds the outline.
READY = 90.0
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = ctypes.c_void_p
user32.GetWindowRgnBox.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]


def say(*parts):
    print(f"[{THEME}]", *parts, flush=True)


def measure(hwnd, label):
    """The share of the game and of the dark backdrop over the overlay's window, and the region Windows holds."""
    from PIL import ImageGrab
    rect, box = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    kind = user32.GetWindowRgnBox(hwnd, ctypes.byref(box))
    shot = ImageGrab.grab(all_screens=True).crop((rect.left, rect.top, rect.right, rect.bottom)).convert("RGB")
    shot.save(os.path.join(OUT, f"{THEME}-{label}.png"))
    pixels = list(shot.get_flattened_data() if hasattr(shot, "get_flattened_data") else shot.getdata())
    seen = {"game": round(sum(p == GREEN for p in pixels) / max(1, len(pixels)), 4),
            "backdrop": round(sum(p in GREY for p in pixels) / max(1, len(pixels)), 4),
            "region": kind in (2, 3)}
    say(label, json.dumps(seen))
    return seen


def drawn(seen):
    """The page has drawn and sent its outline: Windows holds a region, and the window shows more than the game."""
    return seen["region"] and seen["game"] < 0.95


def until(hwnd, label, ok, wait=READY):
    """Measure until ``ok`` holds or ``wait`` seconds pass; the last measurement."""
    end = time.monotonic() + wait
    while True:
        seen = measure(hwnd, label)
        if ok(seen) or time.monotonic() > end:
            return seen
        time.sleep(1.0)


home = tempfile.mkdtemp(prefix="a2home")
env = {**os.environ, "AION2CALC_HOME": home, "PYTHONUNBUFFERED": "1"}
game_exe = os.path.join(os.path.dirname(sys.executable), "aion2.exe")
if not os.path.exists(game_exe):
    shutil.copy(sys.executable, game_exe)
game = subprocess.Popen([game_exe, "-c", "import tkinter as tk\nr=tk.Tk()\nr.title('AION2')\n"
                         "r.geometry('1000x720+0+0')\nr.configure(bg='#00ff00')\nr.mainloop()"])
PORT = 8791
base = f"http://127.0.0.1:{PORT}"
app = subprocess.Popen([sys.executable, "-m", "aion2calc", "app", "--no-browser", "--no-sync", "--port", str(PORT)],
                       env=env, stdout=open(os.path.join(OUT, f"app-{THEME}.log"), "w"), stderr=subprocess.STDOUT)
failures = []
try:
    for _ in range(300):
        try:
            urllib.request.urlopen(base + "/api/ui", timeout=2)
            break
        except OSError:
            time.sleep(0.3)
    for mode in ("none", "top", "card"):
        request = urllib.request.Request(base + "/api/ui", data=json.dumps({"overlay_bg_mode": mode}).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=10)
        overlay = subprocess.Popen([sys.executable, "-m", "aion2calc.overlay", "--url", base + "/overlay"], env=env)
        try:
            hwnd = None
            for _ in range(160):
                hwnd = user32.FindWindowW(None, "Aion 2 Calc Overlay")
                if hwnd and user32.IsWindowVisible(hwnd):
                    break
                time.sleep(0.25)
            if not hwnd:
                failures.append(f"{mode}: the overlay window never showed")
                continue
            if mode == "card":
                seen = until(hwnd, mode, lambda s: drawn(s) and s["game"] > 0)
                if not drawn(seen):
                    failures.append(f"{mode}: the page sent no outline within {READY:.0f} s ({seen})")
                elif not 0 < seen["game"] < 0.05 or seen["backdrop"]:
                    failures.append(f"{mode}: the window is not the card's rounded outline ({seen})")
                continue
            seen = until(hwnd, mode, lambda s: drawn(s) and s["game"] >= SEE_THROUGH)
            if not drawn(seen):
                failures.append(f"{mode}: the page sent no outline within {READY:.0f} s ({seen})")
            elif seen["game"] < SEE_THROUGH or seen["backdrop"]:
                failures.append(f"{mode}: the game does not show between the pieces ({seen})")
            elif THEME == "dark" and mode == "none":
                # pywebview asks for the backdrop again on every change of the user's preferences
                result = ctypes.c_size_t()
                user32.SendMessageTimeoutW(ctypes.c_void_p(0xFFFF), 0x001A, 0, ctypes.c_wchar_p("ImmersiveColorSet"),
                                           2, 5000, ctypes.byref(result))
                time.sleep(0.5)
                seen = until(hwnd, mode + "-after-a-preference-change", lambda s: s["game"] >= SEE_THROUGH, wait=6.0)
                if seen["game"] < SEE_THROUGH:
                    failures.append(f"{mode}: the backdrop came back after a preference change ({seen})")
        finally:
            subprocess.run(["taskkill", "/PID", str(overlay.pid), "/T", "/F"], capture_output=True)
            time.sleep(1.5)
finally:
    app.kill()
    game.kill()
if failures:
    for failure in failures:
        say("FAILED:", failure)
    log = os.path.join(home, "logs", "overlay.log")
    if os.path.exists(log):
        say("overlay.log:\n" + open(log, encoding="utf-8", errors="replace").read()[-8000:])
    sys.exit(1)
say("the see-through modes show the game between their pieces")
