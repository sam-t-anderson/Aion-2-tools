"""Open the compact meter / raid-plan overlay in a transparent, always-on-top window.

    python -m aion2calc.overlay                       # connects to the running app
    python -m aion2calc.overlay --url http://127.0.0.1:8765/overlay

A frameless, transparent, always-on-top window needs pywebview (``pip install pywebview``). Without
it the overlay opens in your default browser — a normal window you can size and place next to the
game. The overlay shows the live damage meter (from /api/meter) and plays your most recent raid plan.
"""
from __future__ import annotations

import argparse
import webbrowser


def _default_url() -> str:
    """The URL the running app wrote on startup (home/app_url.txt), else the default port."""
    try:
        from .paths import home
        f = home() / "app_url.txt"
        if f.is_file():
            return f.read_text(encoding="utf-8").strip().rstrip("/") + "/overlay"
    except Exception:
        pass
    return "http://127.0.0.1:8765/overlay"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aion2calc.overlay", description="aion2calc transparent overlay")
    ap.add_argument("--url", default=None, help="overlay URL (default: the running app's /overlay)")
    ap.add_argument("--width", type=int, default=300)
    ap.add_argument("--height", type=int, default=430)
    a = ap.parse_args(argv)
    url = a.url or _default_url()
    try:
        import webview  # pywebview, optional
    except Exception:
        print("pywebview is not installed; opening the overlay in your browser.\n"
              "For a transparent, always-on-top overlay:  pip install pywebview")
        webbrowser.open(url)
        return 0
    webview.create_window("aion2calc overlay", url, frameless=True, easy_drag=True,
                          on_top=True, transparent=True, width=a.width, height=a.height)
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
