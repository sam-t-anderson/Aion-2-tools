"""The overlay's watchdog: what it watches for, how it decides to heal, and the limits on healing.

Kept apart from the window code (``aion2calc/overlay.py``) so every decision is tested on any platform;
the Windows glue (the WebView2 events, capturing the window, reloading it) stays thin.

Reported on 21 October: the live meter overlay goes blank after it has been open for a while, a dark
card-coloured rectangle with nothing in it. The screenshot's pixels are the WinForms host's own colour at
the window's opacity, with square corners: the WebView2 control had stopped drawing. That happens when
its render process dies or hangs, when its browser process is gone, or when the control stops presenting
after the GPU or the display changed; pywebview installs no handler for any of them, so the window stayed
blank until it was closed and opened again. The overlay now probes its page every few seconds and heals
it in steps: hide and show the control, reload the page, navigate to it afresh, and at last restart the
process, which the app relaunches. Each step is logged in ``logs/overlay.log``.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from datetime import datetime

#: The host form's colour and the card's: what a blank window is full of (RGB).
HOST_COLOR = (27, 32, 42)
#: A capture with at least this share of host-coloured pixels shows nothing: the header text, the card's
#: border, the metric pills and the opacity slider cover more than 1 % of the largest window.
BLANK_FRACTION = 0.998
#: The overlay process exits with this code to ask the app to start it again.
RESTART_EXIT_CODE = 3
#: ... and with this one when it could not open its window at all (no pywebview, or WebView2 would not start,
#: 0.2.390): the app does not start it again, and Open overlay falls back to the page's own small window. Until then
#: the overlay opened its address in the default browser instead, a full-size browser window, and when that came
#: as the app was going away (an error while the window closed) the browser showed "127.0.0.1 refused to connect".
UNAVAILABLE_EXIT_CODE = 4
#: The heal steps, gentlest first.
STEPS = ("nudge", "reload", "navigate", "restart")


def host_fraction(dib, color=HOST_COLOR):
    """The share of a 32-bit BGRA pixel buffer (a top-down DIB) that is ``color``, or None for no pixels.
    Counted as byte patterns, so a run across two pixels could count once in a million; the verdict needs
    99.8 %."""
    pixels = len(dib) // 4
    if pixels <= 0:
        return None
    pattern = bytes((color[2], color[1], color[0]))
    return min(1.0, bytes(dib).count(pattern) / pixels)


class BlankDetector:
    """Turns captures of the window into verdicts. Disarmed until one capture has shown content, so a
    machine where the capture cannot see the control (every frame reads as the host colour, or as nothing)
    never produces a false blank."""

    def __init__(self, threshold=BLANK_FRACTION):
        self.threshold = threshold
        self.armed = False
        self.last_fraction = None

    def verdict(self, dib):
        """True = blank, False = content, None = no verdict (no capture, or not armed yet)."""
        fraction = host_fraction(dib) if dib else None
        self.last_fraction = fraction
        if fraction is None:
            return None
        if fraction < self.threshold:
            self.armed = True
            return False
        return True if self.armed else None


class HealPolicy:
    """What to do from what the probes see.

    ``observe`` takes the time, whether the page answered (True, False, or None for no probe) and whether
    the window drew nothing (True, False, or None for no verdict) and returns the next step or None. Three
    bad observations in a row (15 s at the 5 s probe) start a step; each step then gets a grace period to
    take effect; a page healthy for two minutes ends the episode, so the next trouble starts again from the
    gentlest step. A page that does not answer skips the nudge, which only helps a page that is alive but
    not drawn. ``force`` takes a step at once, for a failure WebView2 reported itself."""

    def __init__(self, misses=3, grace=20.0, calm=120.0):
        self.misses, self.grace, self.calm = misses, grace, calm
        self.bad = 0
        self.step = 0
        self.last_action = None
        self.healthy_since = None
        self.reason = ""

    def observe(self, now, alive, blank):
        if alive is None and blank is None:
            return None
        dead, undrawn = alive is False, blank is True
        if not dead and not undrawn:
            self.bad = 0
            if self.healthy_since is None:
                self.healthy_since = now
            elif now - self.healthy_since >= self.calm:
                self.step = 0
            return None
        self.healthy_since = None
        if self.last_action is not None and now - self.last_action < self.grace:
            return None
        self.bad += 1
        if self.bad < self.misses:
            return None
        self.bad = 0
        self.reason = "the page did not answer" if dead else "the window drew nothing"
        if dead and self.step == 0:
            self.step = 1
        action = STEPS[min(self.step, len(STEPS) - 1)]
        self.step += 1
        self.last_action = now
        return action

    def force(self, now, action, reason):
        self.reason = reason
        self.step = max(self.step, STEPS.index(action) + 1)
        self.last_action = now
        self.bad = 0
        self.healthy_since = None
        return action


def app_answers(app_base, timeout=1.0, opener=None):
    """Whether the app at ``app_base`` (``http://127.0.0.1:<port>``) answers HTTP (0.2.390): the overlay asks before
    it sends its window to the app, since WebView2 shows the browser's own error page ("127.0.0.1 refused to
    connect") for an address where nothing listens. Any answer counts, an error status included; a refused or
    unanswered connection does not. ``/api/overlay/commands`` is the lightest thing the app serves."""
    if not app_base:
        return True
    opener = opener or urllib.request.urlopen
    try:
        with opener(f"{app_base.rstrip('/')}/api/overlay/commands", timeout=timeout) as response:
            response.read(64)
        return True
    except urllib.error.HTTPError as err:
        err.close()
        return True
    except Exception:
        return False


#: What the overlay window shows while the app does not answer (0.2.390): its own card at its own size, never the
#: browser's error page. Inline, so it shows with no app to load it from.
WAITING_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Aion 2 Calc Overlay</title><style>
html,body{margin:0;height:100%;overflow:hidden;background:#1b202a;color:#c9d2e3;
font:600 12px/1.4 "Segoe UI",system-ui,sans-serif;user-select:none;cursor:default}
body{display:flex;align-items:center;justify-content:center;gap:8px;padding:0 12px;box-sizing:border-box}
i{width:8px;height:8px;border-radius:50%;background:#e8cf8e;animation:p 1.2s ease-in-out infinite}
@keyframes p{50%{opacity:.25}}@media (prefers-reduced-motion:reduce){i{animation:none}}
</style></head><body><i aria-hidden="true"></i><span id="waiting" role="status">Waiting for Aion 2 Calc…</span></body></html>"""


class RelaunchLimiter:
    """At most ``limit`` relaunches within ``window`` seconds, so an overlay that cannot come back is not
    started again forever."""

    def __init__(self, limit=5, window=600.0):
        self.limit, self.window, self.times = limit, window, []

    def allow(self, now):
        self.times = [t for t in self.times if now - t < self.window]
        if len(self.times) >= self.limit:
            return False
        self.times.append(now)
        return True


class OverlayLog:
    """A small log of what the watchdog saw and did: ``logs/overlay.log`` in the app's data folder, kept
    under a megabyte. The overlay process writes to it, the app writes the page's own errors and its
    relaunches, and the capture diagnostics ZIP carries its tail."""

    def __init__(self, path, who="overlay", limit=1_000_000, keep=256_000):
        self.path, self.who, self.limit, self.keep = str(path), who, limit, keep

    def write(self, message):
        try:
            try:
                if os.path.getsize(self.path) > self.limit:
                    with open(self.path, "rb") as fh:
                        fh.seek(-self.keep, os.SEEK_END)
                        tail = fh.read()
                    with open(self.path, "wb") as fh:
                        fh.write(tail[tail.find(b"\n") + 1:])
            except OSError:
                pass
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat(timespec='seconds')} {self.who}: {message}\n")
        except Exception:
            pass

    def tail(self, limit=200_000):
        """The end of the log as text, or an empty string."""
        try:
            with open(self.path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - limit))
                return fh.read().decode("utf-8", "replace")
        except OSError:
            return ""
