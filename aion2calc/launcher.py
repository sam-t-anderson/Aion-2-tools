"""Entry point of the installed app (the Windows installer, the portable builds).

Double-clicking the app starts the local server and opens the browser. Starting
it again while it runs just opens the browser on the running copy. The app's
top bar has a Quit button; there is no console window.

* ``client.json`` next to the executable (or in the bundle) presets the log
  server for new users: ``{"logserver_url": "https://logs.example.com",
  "visibility": "unlisted"}`` (an upload ``key`` may be added for trusted users).
* Errors go to ``aion2calc.log`` in the data folder, and on Windows a message box.
* ``--smoke-test`` starts the server on a free port, checks it answers, and
  exits with 0 (used by the build pipeline on every platform).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _log_to_file() -> Path:
    from .paths import home
    path = home() / "aion2calc.log"
    if _frozen() or sys.stdout is None:
        f = open(path, "a", encoding="utf-8", buffering=1)      # noqa: SIM115 - lives as long as the app
        sys.stdout = sys.stderr = f
    return path


def _alert(msg: str) -> None:
    print(msg)
    if sys.platform == "win32" and _frozen():
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "aion2calc", 0x10)
        except Exception:
            pass


def client_config() -> dict:
    """``client.json`` next to the executable, else in the bundle."""
    from .paths import resource_root
    for d in (Path(sys.executable).parent if _frozen() else None, resource_root()):
        if d and (d / "client.json").exists():
            try:
                return json.loads((d / "client.json").read_text(encoding="utf-8"))
            except ValueError:
                return {}
    return {}


def apply_client_config(cfg: dict) -> bool:
    """Preset the log server unless the user already chose one."""
    from .combat import share
    if not cfg.get("logserver_url") or share.settings().get("url"):
        return False
    share.save_settings(cfg["logserver_url"], cfg.get("key"), cfg.get("visibility") or "unlisted")
    return True


def running_app(port: int) -> bool:
    """Is our app already answering on ``port``?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return json.load(r).get("app") == "aion2calc"
    except Exception:
        return False


def free_port(preferred: int) -> int:
    for p in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def app_browser() -> str | None:
    """Edge or Chrome (for a chromeless app window), if installed."""
    import shutil
    cands = []
    if sys.platform == "win32":
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                cands += [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                          Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"]
    elif sys.platform == "darwin":
        cands += [Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    else:
        cands += [Path(w) for w in (shutil.which(n) for n in ("microsoft-edge", "google-chrome", "chromium",
                                                                "chromium-browser")) if w]
    return next((str(c) for c in cands if c.exists()), None)


def open_window(url: str, prefer_app: bool = True):
    """Open the UI: its own app window when Edge/Chrome is there (returns the process), else a browser tab."""
    import subprocess
    from .paths import home
    exe = app_browser() if prefer_app else None
    if exe:
        try:
            return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={home() / 'window'}", "--no-first-run",
                                     "--no-default-browser-check", "--start-maximized"])
        except OSError:
            pass
    webbrowser.open(url)
    return None


def watch(proc, stop, idle_after: float = 180.0) -> None:
    """Stop the app when its window closes, or (browser tab) when no page has pinged for a while."""
    from .app import server
    if proc is not None:
        started = time.time()
        proc.wait()
        if time.time() - started > 10:            # the window was closed
            stop()
            return
        # the browser handed the window to an instance already running: fall back to the page's pings
    server.PING["at"] = time.time()
    while True:
        time.sleep(15)
        if time.time() - server.PING["at"] > idle_after:
            stop()
            return


def smoke_test(out: str | None = None) -> int:
    """Start the server on a free port and check the main routes answer."""
    from .app import server
    srv = server.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    lines, ok = [], True
    for path in ("/api/status", "/", "/api/results", "/api/classes"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60) as r:
                body = r.read()
            lines.append(f"{path} {r.status} {len(body)} bytes")
            if path == "/api/results":
                ok &= len(json.loads(body)) > 0          # the bundled class results were found
        except Exception as err:
            ok = False
            lines.append(f"{path} FAILED {err}")
    from .opt import solver as lp
    try:                                          # the bundled solver (Daevanion optimizer)
        import pulp
        prob = pulp.LpProblem("smoke", pulp.LpMaximize)
        x = pulp.LpVariable("x", 0, 3, cat="Integer")
        prob += x
        prob += 2 * x <= 5
        prob.solve(lp.solver())
        solved = round(pulp.value(x)) == 2
        ok &= solved
        lines.append(f"{lp.name()} solver {'OK' if solved else 'wrong answer'}")
    except Exception as err:
        ok = False
        lines.append(f"{lp.name()} solver FAILED {err}")
    from . import __version__
    lines.append(f"aion2calc {__version__}: {'OK' if ok else 'FAILED'}")
    srv.shutdown()
    text = "\n".join(lines)
    print(text)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 1


def main(argv=None) -> int:
    if os.environ.get("AION2CALC_OVERLAY"):       # the app re-ran the bundle to open the native overlay
        from . import overlay
        return overlay.main([])
    p = argparse.ArgumentParser(prog="aion2calc", description="AION 2 build planner and combat analyzer")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-sync", action="store_true", help="skip the launch-time database update")
    p.add_argument("--install-npcap", action="store_true", help="download and open the current Npcap installer")
    p.add_argument("--smoke-test", nargs="?", const="", metavar="OUT", help="check the app starts, then exit")
    args = p.parse_args(argv)
    for name in ("stdout", "stderr"):            # the windowed build has no console
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))      # noqa: SIM115
    if args.install_npcap:
        from .app import npcap
        npcap.install_now()
        return 0
    if args.smoke_test is not None:
        return smoke_test(args.smoke_test or None)
    log = _log_to_file()
    try:
        from .update import cleanup_updates
        cleanup_updates()
        # The default log server is resolved live from share.default_server() (so a changed
        # quick-tunnel URL needs no rebuild); it is not persisted into the user's settings here.
        from .app import server
        prefer_app = server.ui_settings().get("app_window", True)
        if running_app(args.port):                # already running: just show it
            if not args.no_browser:
                open_window(f"http://127.0.0.1:{args.port}/", prefer_app)
            return 0
        port = free_port(args.port)
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "starting on port", port)
        httpd = server.make_server("127.0.0.1", port)
        if _frozen() and server.ui_settings().get("auto_update", True):
            def updater():
                from . import update
                status = update.auto_update(httpd.shutdown)
                print("update:", status)
            threading.Thread(target=updater, daemon=True).start()
        if not args.no_browser:
            def show():
                time.sleep(0.8)
                proc = open_window(f"http://127.0.0.1:{port}/", prefer_app)
                if proc is not None:
                    server.APP_WINDOW["process"] = proc
                if _frozen():                     # the installed app stops with its window
                    watch(proc, httpd.shutdown)
            threading.Thread(target=show, daemon=True).start()
        server.serve(open_browser=False, sync=not args.no_sync, httpd=httpd)
        if _frozen() and server.HTTPD.get("closing"):
            # Optimizer/solver worker exit hooks can otherwise keep the frozen
            # executable locked after an explicit Quit or installer handoff.
            # serve() has already stopped capture and closed the HTTP server.
            for stream in (sys.stdout, sys.stderr):
                if stream:
                    stream.flush()
            os._exit(0)
        return 0
    except Exception:
        print(traceback.format_exc())
        _alert(f"aion2calc could not start. Details are in:\n{log}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
