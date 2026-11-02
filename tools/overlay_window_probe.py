"""Temporary probe, removed before merge: what the overlay host's window shape does on a real Windows desktop.

A green window stands in for the game. The overlay host's own _OverlayAPI drives a pywebview window set up like
aion2calc.overlay's, and its page reports two pieces as the window's shape through the JS bridge. The screen is
then read back inside and outside the pieces for several host setups, with the region Windows holds and what the
mouse would hit at each point."""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="probe-out")
ap.add_argument("--name", default="default")
ap.add_argument("--extra-args", default="")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)


def log(*parts):
    print(f"[{a.name}]", *parts, flush=True)


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = ctypes.c_void_p
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.c_void_p
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRgnBox.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumChildWindows.argtypes = [ctypes.c_void_p, EnumProc, ctypes.c_void_p]

GREEN = "#00ff00"
background = subprocess.Popen([sys.executable, "-c", (
    "import tkinter as tk\nr=tk.Tk()\nr.overrideredirect(True)\nr.geometry('800x560+0+0')\n"
    f"r.configure(bg='{GREEN}')\nr.title('probe-background')\nr.mainloop()")])
time.sleep(3)

import webview  # noqa: E402
from aion2calc.overlay import _OverlayAPI  # noqa: E402
from aion2calc.overlay_health import OverlayLog  # noqa: E402

log("pywebview", getattr(webview, "__version__", "?"))
PORT = 9222
webview.settings["REMOTE_DEBUGGING_PORT"] = f"{PORT} {a.extra_args}".strip()

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:transparent;overflow:hidden}
.p{position:absolute;width:100px;height:60px}
#a{left:20px;top:20px;background:#ff0000;border-radius:12px}
#b{left:20px;top:120px;background:#0000ff}
</style></head><body><div class="p" id="a"></div><div class="p" id="b"></div><script>
function send(){const api=window.pywebview&&window.pywebview.api;
  if(!api||typeof api.set_window_shape!=="function"){setTimeout(send,100);return;}
  api.set_window_shape([[20,20,120,80,12],[20,120,120,180]]).then(()=>{document.title="shape-sent";});}
window.addEventListener("pywebviewready",send);
</script></body></html>"""

api = _OverlayAPI()
api.log = OverlayLog(os.path.join(a.out, f"overlay-{a.name}.log"))
window = webview.create_window("probe-overlay", html=PAGE, frameless=True, easy_drag=False, shadow=False, on_top=True,
                               hidden=True, focus=False, transparent=False, background_color="#010203",
                               width=300, height=240, js_api=api)
api._window = window
X, Y = 100, 100
POINTS = {"in_red": (70, 50), "in_blue": (70, 150), "gap_right": (200, 50), "between": (70, 100),
          "red_corner": (22, 22), "below": (150, 220)}
results = {}


def classname(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def pid_of(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def region_box(hwnd):
    rect = wintypes.RECT()
    kind = user32.GetWindowRgnBox(hwnd, ctypes.byref(rect))
    return {"type": {0: "error/none", 1: "null", 2: "simple", 3: "complex"}.get(kind, kind),
            "box": [rect.left, rect.top, rect.right, rect.bottom]}


def children(hwnd):
    found = []

    def visit(child, _):
        found.append({"hwnd": child, "class": classname(child), "pid": pid_of(child),
                      "region": region_box(child)})
        return True

    user32.EnumChildWindows(hwnd, EnumProc(visit), None)
    return found


def sample(name, hwnd):
    from PIL import ImageGrab
    time.sleep(2.0)
    image = ImageGrab.grab(all_screens=True)
    image.save(os.path.join(a.out, f"{a.name}-{name}.png"))
    pixels, hits = {}, {}
    for key, (dx, dy) in POINTS.items():
        pixels[key] = list(image.getpixel((X + dx, Y + dy))[:3])
        hit = user32.WindowFromPoint(wintypes.POINT(X + dx, Y + dy))
        root = user32.GetAncestor(hit, 2) if hit else None
        hits[key] = "overlay" if root == hwnd else (classname(root) if root else None)
    entry = {"pixels": pixels, "mouse_hits": hits, "region": region_box(hwnd),
             "exstyle": hex(user32.GetWindowLongPtrW(hwnd, -20) & 0xFFFFFFFF)}
    results[name] = entry
    log(name, json.dumps(entry))


def gpu_info():
    try:
        version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=5).read())
        import websocket
        ws = websocket.create_connection(version["webSocketDebuggerUrl"], timeout=10)
        ws.send(json.dumps({"id": 1, "method": "SystemInfo.getInfo"}))
        while True:
            reply = json.loads(ws.recv())
            if reply.get("id") == 1:
                break
        ws.close()
        gpu = reply.get("result", {}).get("gpu", {})
        return {"browser": version.get("Browser"), "featureStatus": gpu.get("featureStatus"),
                "devices": [{k: d.get(k) for k in ("vendorString", "deviceString", "driverVendor")}
                            for d in gpu.get("devices", [])]}
    except Exception as err:
        return {"error": f"{type(err).__name__}: {err}"}


def ui(callback):
    api._on_ui(callback)


def run():
    try:
        if not window.events.shown.wait(30):
            log("window never shown")
            return
        api._configure_windows()
        window.show()
        hwnd = window.native.Handle.ToInt64()
        user32.SetWindowPos(hwnd, None, X, Y, 0, 0, 0x0001 | 0x0004 | 0x0010)   # NOSIZE | NOZORDER | NOACTIVATE
        for _ in range(200):
            if api._shape is not None:
                break
            time.sleep(0.1)
        log("shape from the page", api._shape)
        log("gpu", json.dumps(gpu_info()))
        try:
            renderer = window.evaluate_js("(()=>{const g=document.createElement('canvas').getContext('webgl');"
                                          "if(!g)return 'no webgl';const e=g.getExtension('WEBGL_debug_renderer_info');"
                                          "return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):'no ext';})()")
        except Exception as err:
            renderer = f"{type(err).__name__}: {err}"
        log("webgl renderer", renderer)
        log("children", json.dumps(children(hwnd)))
        from System.Drawing import Color
        native = window.native
        sample("v0_production", hwnd)

        ui(lambda: setattr(native, "Opacity", 1.0))
        sample("v1_opaque_window", hwnd)

        ui(lambda: setattr(native.webview, "DefaultBackgroundColor", Color.FromArgb(0, 0, 0, 0)))
        sample("v2_transparent_webview_opaque_window", hwnd)

        ui(lambda: setattr(native, "Opacity", 0.72))
        sample("v3_transparent_webview_translucent_window", hwnd)

        def child_region():
            native.webview.Region = api._shape_region(rounded=True)
        ui(lambda: setattr(native.webview, "DefaultBackgroundColor", Color.FromArgb(27, 32, 42)))
        ui(child_region)
        sample("v4_production_plus_control_region", hwnd)
        log("children after control region", json.dumps(children(hwnd)))

        def color_key():
            native.webview.Region = None
            native.Region = None
            key = Color.FromArgb(1, 2, 3)
            native.BackColor = key
            native.TransparencyKey = key
            native.webview.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0)
        ui(color_key)
        sample("v5_color_key_no_region", hwnd)

        def color_key_region():
            native.Region = api._shape_region(rounded=True)
        ui(color_key_region)
        sample("v6_color_key_plus_region", hwnd)

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]

        def glass():
            native.Region = None
            native.TransparencyKey = Color.Empty
            native.BackColor = Color.Black
            native.webview.DefaultBackgroundColor = Color.FromArgb(0, 0, 0, 0)
            result = ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd),
                                                                      ctypes.byref(MARGINS(-1, -1, -1, -1)))
            log("DwmExtendFrameIntoClientArea", hex(result & 0xFFFFFFFF))
        ui(glass)
        sample("v7_glass_translucent_no_region", hwnd)
        ui(lambda: setattr(native, "Opacity", 1.0))
        sample("v8_glass_opaque_no_region", hwnd)
        ui(lambda: setattr(native, "Region", api._shape_region(rounded=True)))
        sample("v9_glass_opaque_plus_region", hwnd)
    except Exception as err:
        log("probe failed", f"{type(err).__name__}: {err}")
        import traceback
        traceback.print_exc()
    finally:
        with open(os.path.join(a.out, f"results-{a.name}.json"), "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1)
        threading.Timer(1.0, window.destroy).start()


webview.start(run, gui="edgechromium")
background.kill()
log("done")
