"""The native interface's errors on record (0.2.503): every uncaught Python error of a native process (the app's
window, the meter overlay, a companion window), raised in a Qt handler (a button's, a timer's, a reply's), in a thread
or as it starts, written with its traceback to ``logs/native.log`` in the app's data folder under the process's name.

The installed app is built without a console, so a native window's process has nowhere to print: until now such an
error went unseen, and only what it left undone showed. The log is kept under a megabyte, as the overlay's is
(``overlay_health.OverlayLog``), and the capture diagnostics carry its end (``meter/diagnostics.py``). An error is
still shown as before as well (on the console of a run from source).
"""
from __future__ import annotations

import sys
import threading
import traceback

from ..overlay_health import OverlayLog

LOG_NAME = "native.log"


def log_path():
    """``logs/native.log`` in the app's data folder."""
    from ..paths import logs_dir
    return logs_dir() / LOG_NAME


def record(who: str, path=None) -> OverlayLog:
    """Write every uncaught error of this process from now on to the log (``path``, ``logs/native.log`` by default)
    under ``who`` ("window", "overlay", "party window"...), then hand it on to the hook that was there before."""
    log = OverlayLog(log_path() if path is None else path, who)
    before, threads_before = sys.excepthook, threading.excepthook

    def written(kind, value, tb) -> None:
        try:
            log.write("".join(traceback.format_exception(kind, value, tb)).rstrip())
        except Exception:                                # the log is a help, never a second failure
            pass

    def hook(kind, value, tb) -> None:
        written(kind, value, tb)
        try:
            if before is not None:
                before(kind, value, tb)
        except Exception:                                # no console to show it on: on record all the same
            pass

    def thread_hook(args) -> None:
        if args.exc_type is not SystemExit:
            written(args.exc_type, args.exc_value, args.exc_traceback)
        try:
            if threads_before is not None:
                threads_before(args)
        except Exception:
            pass

    sys.excepthook, threading.excepthook = hook, thread_hook
    return log
