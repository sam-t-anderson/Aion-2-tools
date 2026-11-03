"""The overlay's window moved with a real mouse on a real Windows desktop (CI, 0.2.374).

A press on the card hands the move to the native host (begin_drag in overlay.py), which follows the cursor until
the press is over. Until 0.2.374 the host read the button with GetAsyncKeyState, which Windows answers with 0 (the
button up) for a program that is not elevated whenever the window in front belongs to one that is (UI Privilege
Isolation): a game run as administrator. The overlay windows never take the foreground (they do not activate), so
over such a game every move ended as it began and no overlay window could be moved.

The app runs from this checkout with a fresh home, under a window owned by a process named like the game's
executable (the stand-in game, pure green). Each case starts the overlay, brings the game to the front with a click
on it, then presses on the card (a point the page itself names over a CDP connection to its WebView2, outside the
card's controls), moves the cursor and lets go, and reads where the window went:

  game-in-front   the game in front at the overlay's own privilege level;
  key-state-up    the same, with every GetAsyncKeyState the overlay makes answered 0, as Windows answers it under an
                  elevated window;
  elevated-game   when this check runs elevated: the overlay started as a standard user at medium integrity, as a
                  player's own launch is, under the game at high integrity, the case players meet, when Windows
                  enforces UIPI here (a probe first reads the left button at both levels while it is held over the
                  game, from a process given a medium-integrity copy of this one's token, and says what it found).

Usage: python tools/overlay_drag_check.py [OUTDIR]. Exits 1 with the overlay's log when the window did not move."""
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

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "overlay-drag-check")
os.makedirs(OUT, exist_ok=True)
PORT, CDP_PORT = 8792, 9231
MOVE = (120, 80)                  # how far each drag takes the cursor
TOLERANCE = 3                     # px the window may end from where the cursor took it
TITLE = "Aion 2 Calc Overlay"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.POINT)]
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.DWORD)]
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
advapi32.DuplicateTokenEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                      ctypes.POINTER(wintypes.HANDLE)]
advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
advapi32.SetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
advapi32.SaferCreateLevel.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
                                      ctypes.c_void_p]
advapi32.SaferComputeTokenFromLevel.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE),
                                                wintypes.DWORD, ctypes.c_void_p]
advapi32.SaferCloseLevel.argtypes = [wintypes.HANDLE]

TOKEN_ASSIGN_PRIMARY, TOKEN_DUPLICATE, TOKEN_QUERY, TOKEN_ADJUST_DEFAULT = 0x1, 0x2, 0x8, 0x80
TOKEN_INTEGRITY_LEVEL = 25
LEVELS = {0x1000: "low", 0x2000: "medium", 0x3000: "high", 0x4000: "system"}


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE), ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD)]


advapi32.CreateProcessAsUserW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                                          ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
                                          wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW),
                                          ctypes.POINTER(PROCESS_INFORMATION)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
LEFTDOWN, LEFTUP = 0x0002, 0x0004

# Started in place of `python -m aion2calc.overlay`: the page's WebView2 opens a CDP port for this check, and with
# "block" every GetAsyncKeyState the overlay makes reads 0, as Windows answers it under an elevated window.
BOOT = r'''
import ctypes, runpy, sys
port, mode = int(sys.argv[1]), sys.argv[2]
import webview
webview.settings["REMOTE_DEBUGGING_PORT"] = port
if mode == "block":
    real = ctypes.WinDLL

    class User32:
        def __init__(self, dll):
            self.__dict__["_dll"] = dll

        def __getattr__(self, name):
            if name == "GetAsyncKeyState":
                return lambda key: 0
            return getattr(self._dll, name)

        def __setattr__(self, name, value):
            setattr(self._dll, name, value)

    def WinDLL(name, *args, **kwargs):
        dll = real(name, *args, **kwargs)
        return User32(dll) if str(name).lower().startswith("user32") else dll
    ctypes.WinDLL = WinDLL
sys.argv = ["aion2calc.overlay"] + sys.argv[3:]
runpy.run_module("aion2calc.overlay", run_name="__main__", alter_sys=True)
'''

# Reads the left button a few times once the go-file exists, and says at what integrity level it ran.
PROBE = r'''
import ctypes, json, os, sys, time
from ctypes import wintypes
out, go = sys.argv[1], sys.argv[2]
u = ctypes.WinDLL("user32")
u.GetAsyncKeyState.restype = ctypes.c_short
end = time.monotonic() + 30
while not os.path.exists(go) and time.monotonic() < end:
    time.sleep(0.02)
values = []
for _ in range(8):
    values.append(u.GetAsyncKeyState(0x01) & 0xFFFF)
    time.sleep(0.03)
with open(out, "w") as f:
    json.dump(values, f)
'''

PAGE_POINT = """() => {
  const api = window.pywebview && window.pywebview.api;
  if (api && !window.__a2wrapped) {
    for (const name of ["begin_drag", "end_drag"]) {
      const real = api[name];
      if (typeof real === "function") api[name] = (...args) => { (window.__a2calls = window.__a2calls || []).push([name, ...args]); return real(...args); };
    }
    window.__a2wrapped = true;
  }
  const card = document.querySelector(".ovcard");
  if (!card) return { error: "no card" };
  const r = card.getBoundingClientRect(), skip = "button, input, select, textarea, a, label, .ovgrip";
  let point = null;
  for (let y = Math.ceil(r.top) + 8; y < r.bottom - 8 && !point; y += 2)
    for (let x = Math.ceil(r.left) + 16; x < r.right - 16; x += 2) {
      const el = document.elementFromPoint(x, y);
      if (el && card.contains(el) && !el.closest(skip)) { point = { x, y, on: el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (typeof el.className === "string" && el.className ? "." + el.className.split(" ").join(".") : "") }; break; }
    }
  return { point, dpr: window.devicePixelRatio, card: [r.left, r.top, r.width, r.height],
           api: api ? Object.keys(api).filter((k) => typeof api[k] === "function").sort() : null };
}"""


def say(*parts):
    print("[drag]", *parts, flush=True)


def integrity(pid=None):
    """The integrity level's RID of a process (this one when pid is None), or None."""
    process = kernel32.OpenProcess(0x1000, False, pid) if pid else kernel32.GetCurrentProcess()
    if not process:
        return None
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, TOKEN_INTEGRITY_LEVEL, buf, size, ctypes.byref(size)):
            return None
        sid = ctypes.cast(buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents.Label.Sid
        count = advapi32.GetSidSubAuthorityCount(sid).contents.value
        return advapi32.GetSidSubAuthority(sid, count - 1).contents.value
    finally:
        if token:
            kernel32.CloseHandle(token)
        if pid:
            kernel32.CloseHandle(process)


def level(rid):
    return LEVELS.get(rid, f"0x{rid:x}" if rid is not None else "unknown")


def start_lower(argv, env, rid, standard_user=False):
    """Start ``argv`` at integrity level ``rid`` (below this process's): a duplicate of this process's token with
    that label, as Microsoft's sample for starting a low-integrity process does, or with ``standard_user`` the token
    `runas /trustlevel:0x20000` starts a program with (the Administrators group for deny only, a standard user's
    privileges), the kind a player's own launch has. (pid, process handle)."""
    token, primary, sid = wintypes.HANDLE(), wintypes.HANDLE(), ctypes.c_void_p()
    if standard_user:
        safer = wintypes.HANDLE()
        if not advapi32.SaferCreateLevel(2, 0x20000, 1, ctypes.byref(safer), None):      # user scope, normal user, open
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not advapi32.SaferComputeTokenFromLevel(safer, None, ctypes.byref(primary), 0, None):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            advapi32.SaferCloseLevel(safer)
    else:
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_DUPLICATE | TOKEN_QUERY
                                         | TOKEN_ASSIGN_PRIMARY | TOKEN_ADJUST_DEFAULT, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not advapi32.DuplicateTokenEx(token, 0x02000000, None, 2, 1, ctypes.byref(primary)):
            raise ctypes.WinError(ctypes.get_last_error())
    if not advapi32.ConvertStringSidToSidW(f"S-1-16-{rid}", ctypes.byref(sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    label = TOKEN_MANDATORY_LABEL(SID_AND_ATTRIBUTES(sid, 0x20))
    if not advapi32.SetTokenInformation(primary, TOKEN_INTEGRITY_LEVEL, ctypes.byref(label),
                                        ctypes.sizeof(label) + advapi32.GetLengthSid(sid)):
        raise ctypes.WinError(ctypes.get_last_error())
    block = "".join(f"{k}={v}\0" for k, v in sorted(env.items())) + "\0"
    environment = (ctypes.c_wchar * len(block))(*block)
    startup, info = STARTUPINFOW(), PROCESS_INFORMATION()
    startup.cb = ctypes.sizeof(startup)
    command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    if not advapi32.CreateProcessAsUserW(primary, None, command, None, None, False, 0x00000400 | 0x08000000,
                                         ctypes.cast(environment, ctypes.c_void_p), None, ctypes.byref(startup),
                                         ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel32.CloseHandle(info.hThread)
    if token:
        kernel32.CloseHandle(token)
    kernel32.CloseHandle(primary)
    return info.dwProcessId, info.hProcess


def button(flags):
    event = INPUT(type=0)
    event.u.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def click(x, y):
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    button(LEFTDOWN)
    time.sleep(0.08)
    button(LEFTUP)
    time.sleep(0.4)


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def foreground_pid():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def overlay_log(home):
    path = os.path.join(home, "logs", "overlay.log")
    return open(path, encoding="utf-8", errors="replace").read()[-6000:] if os.path.exists(path) else "(no overlay.log)"


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def end_process(pid):
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    subprocess.run(["taskkill", "/IM", "msedgewebview2.exe", "/F"], capture_output=True)
    time.sleep(2.0)


def wait_for_page(playwright):
    """The overlay page over CDP once its bridge is in and its card drawn: (browser, page, what it said)."""
    end, last = time.monotonic() + 90, None
    while time.monotonic() < end:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            pages = [p for c in browser.contexts for p in c.pages if "/overlay" in p.url]
            if pages:
                said = pages[0].evaluate(PAGE_POINT)
                last = said
                if said.get("point") and said.get("api") and "begin_drag" in said["api"]:
                    return browser, pages[0], said
        except Exception as err:                                   # noqa: BLE001 - not up yet
            last = f"{type(err).__name__}: {err}"
        time.sleep(1.0)
    raise RuntimeError(f"the overlay page never got ready over CDP ({last})")


def drag_case(name, start, home, game_pid, failures, needs=None):
    """Start the overlay with ``start()``, bring the game to the front, drag the card by MOVE and check the window
    went with the cursor and stayed there. ``needs`` is the overlay's integrity level the case is about: at another
    level, or when its page cannot start under the lowered token at all, the case says so and is not judged."""
    from playwright.sync_api import sync_playwright
    start()
    pid = None
    try:
        hwnd = None
        for _ in range(240):
            hwnd = user32.FindWindowW(None, TITLE)
            if hwnd and user32.IsWindowVisible(hwnd):
                break
            time.sleep(0.25)
        if not hwnd:
            failures.append(f"{name}: the overlay window never showed")
            return
        pid = window_pid(hwnd)
        if needs is not None and integrity(pid) != needs:
            say(f"{name}: not judged, the overlay runs at {level(integrity(pid))} integrity, not {level(needs)}")
            return
        with sync_playwright() as playwright:
            try:
                _, page, said = wait_for_page(playwright)
            except RuntimeError as err:
                if needs is None:
                    raise
                say(f"{name}: not judged, the overlay page did not start at {level(needs)} integrity here ({err})")
                say(f"{name} overlay.log:\n" + overlay_log(home))
                return
            time.sleep(1.5)                                        # the follow loop has placed the window
            click(900, 650)                                        # the game to the front
            before = rect(hwnd)
            origin = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(origin))
            dpr = said.get("dpr") or 1
            x, y = origin.x + round(said["point"]["x"] * dpr), origin.y + round(said["point"]["y"] * dpr)
            front = foreground_pid()
            say(name, json.dumps({"overlay": level(integrity(pid)),
                                  "game": level(integrity(game_pid)), "game in front": front == game_pid,
                                  "press": [x, y], "on": said["point"].get("on"), "window": before, "dpr": dpr}))
            user32.SetCursorPos(x, y)
            time.sleep(0.3)
            button(LEFTDOWN)
            time.sleep(0.3)
            steps = 12
            for i in range(1, steps + 1):
                user32.SetCursorPos(x + MOVE[0] * i // steps, y + MOVE[1] * i // steps)
                time.sleep(0.04)
            time.sleep(0.3)
            moved = rect(hwnd)
            button(LEFTUP)
            time.sleep(1.5)                                        # the follow loop has had its say
            after = rect(hwnd)
            calls = page.evaluate("window.__a2calls || []")
        went = (after[0] - before[0], after[1] - before[1])
        say(name, json.dumps({"while held": [moved[0] - before[0], moved[1] - before[1]], "after": went,
                              "page calls": calls}))
        if abs(went[0] - MOVE[0]) > TOLERANCE or abs(went[1] - MOVE[1]) > TOLERANCE:
            failures.append(f"{name}: the window went {went}, the cursor {MOVE}")
            say(f"{name} overlay.log:\n" + overlay_log(home))
    except Exception as err:                                       # noqa: BLE001 - said, and the next case runs
        failures.append(f"{name}: {type(err).__name__}: {err}")
        say(f"{name} overlay.log:\n" + overlay_log(home))
    finally:
        end_process(pid)


def probe_key_state(env, game_pid, lower):
    """The left button read by a process at this level and one at ``lower`` while it is held over the game, in
    front: whether Windows answers the lower one."""
    folder = tempfile.mkdtemp(prefix="a2probe")
    script, go = os.path.join(folder, "probe.py"), os.path.join(folder, "go")
    with open(script, "w") as f:
        f.write(PROBE)
    same_out, lower_out = os.path.join(folder, "same.json"), os.path.join(folder, "lower.json")
    same = subprocess.Popen([sys.executable, script, same_out, go], env=env)
    low = start_lower([sys.executable, script, lower_out, go], env, lower)
    time.sleep(1.5)
    click(900, 650)
    user32.SetCursorPos(880, 600)
    time.sleep(0.2)
    button(LEFTDOWN)
    time.sleep(0.2)
    open(go, "w").close()
    time.sleep(0.6)
    button(LEFTUP)
    same.wait(15)
    kernel32.WaitForSingleObject(low[1], 15000)
    read = {}
    for key, path in (("same level", same_out), (level(lower), lower_out)):
        read[key] = json.load(open(path)) if os.path.exists(path) else None
    return read, foreground_pid() == game_pid


try:                                         # screen pixels throughout, as the overlay's own reads are
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    pass
home = tempfile.mkdtemp(prefix="a2home")
boot_dir = tempfile.mkdtemp(prefix="a2boot")
boot = os.path.join(boot_dir, "overlay_boot.py")
with open(boot, "w") as f:
    f.write(BOOT)
env = {**os.environ, "AION2CALC_HOME": home, "PYTHONUNBUFFERED": "1"}
game_exe = os.path.join(os.path.dirname(sys.executable), "aion2.exe")
if not os.path.exists(game_exe):
    shutil.copy(sys.executable, game_exe)
game = subprocess.Popen([game_exe, "-c", "import tkinter as tk\nr=tk.Tk()\nr.title('AION2')\n"
                         "r.geometry('1000x720+0+0')\nr.configure(bg='#00ff00')\nr.mainloop()"])
base = f"http://127.0.0.1:{PORT}"
app = subprocess.Popen([sys.executable, "-m", "aion2calc", "app", "--no-browser", "--no-sync", "--port", str(PORT)],
                       env=env, stdout=open(os.path.join(OUT, "drag-app.log"), "w"), stderr=subprocess.STDOUT)
failures = []
try:
    for _ in range(300):
        try:
            urllib.request.urlopen(base + "/api/ui", timeout=2)
            break
        except OSError:
            time.sleep(0.3)
    request = urllib.request.Request(base + "/api/ui", data=json.dumps({"overlay_bg_mode": "card"}).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(request, timeout=10)
    mine = integrity()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System") as key:
            lua = winreg.QueryValueEx(key, "EnableLUA")[0]
    except OSError:
        lua = "unset"
    say(json.dumps({"this check": level(mine), "game": level(integrity(game.pid)), "EnableLUA": lua}))
    overlay_argv = ["--url", base + "/overlay"]

    def plain(mode):
        return lambda: subprocess.Popen([sys.executable, boot, str(CDP_PORT), mode] + overlay_argv, env=env)
    drag_case("game-in-front", plain("plain"), home, game.pid, failures)
    drag_case("key-state-up", plain("block"), home, game.pid, failures)
    if mine is not None and mine >= 0x3000:
        try:
            read, in_front = probe_key_state(env, game.pid, 0x2000)
            blocked = bool(read.get("same level")) and any(read["same level"]) and read.get("medium") is not None \
                and not any(read["medium"])
            say("key-state probe", json.dumps({"read": read, "game in front": in_front,
                                               "UIPI answers the medium process with 0": blocked}))
        except Exception as err:                                   # noqa: BLE001 - the probe is evidence, not a case
            blocked = False
            say("key-state probe not run:", f"{type(err).__name__}: {err}")
        if blocked:
            drag_case("elevated-game", lambda: start_lower([sys.executable, boot, str(CDP_PORT), "plain"]
                                                           + overlay_argv, env, 0x2000, standard_user=True),
                      home, game.pid, failures, needs=0x2000)
        else:
            say("elevated-game: not run, Windows does not hold the medium process's reads back here")
    else:
        say("elevated-game: not run, this check is not elevated")
finally:
    app.kill()
    game.kill()
if failures:
    for failure in failures:
        say("FAILED:", failure)
    sys.exit(1)
say("every overlay window case moved with the cursor")
