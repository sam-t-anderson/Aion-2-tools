"""Run the live damage meter from the command line (development / headless use).

    python -m aion2calc.meter --replay aion2calc/meter/demo_session.jsonl --realtime
    python -m aion2calc.meter --live --iface eth0 --host <game-server> --decoder your_module
    python -m aion2calc.meter --replay session.jsonl --save session.a2log

The live game protocol decoder is not bundled; --live needs your own --decoder.
"""
from __future__ import annotations

import argparse
import sys
import time

from .decoder import load_decoder
from .meter import Meter
from .sources import capture_source, live_frames, replay_source


def _print(snap: dict) -> None:
    dur = snap["duration"]
    lines = [f"\n== {snap.get('boss') or 'Live'} — {dur:.0f}s — total {snap['total']:,.0f} ({snap['dps']:,.0f} DPS) =="]
    for r in snap["players"]:
        lines.append(f"  {r['name']:<16} {r.get('class') or '':<12} {r['dps']:>10,.0f} DPS  {100 * r['share']:>5.1f}%  crit {100 * r['crit']:>4.0f}%")
    print("\n".join(lines), flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aion2calc.meter", description="AION 2 live damage meter")
    ap.add_argument("--replay", help="a JSON-lines file of decoded combat events")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed (with --realtime)")
    ap.add_argument("--realtime", action="store_true", help="pace replay by event time and print running totals")
    ap.add_argument("--live", action="store_true", help="capture live (needs --decoder; requires scapy and privileges)")
    ap.add_argument("--iface", help="capture interface")
    ap.add_argument("--host", help="game server host to filter on")
    ap.add_argument("--port", type=int, help="game server port to filter on")
    ap.add_argument("--decoder", help="decoder: a registered name, module, or module:attr")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between printed updates (--realtime)")
    ap.add_argument("--save", help="write the session as an a2log file when done")
    a = ap.parse_args(argv)

    m = Meter()
    if a.replay:
        src = replay_source(a.replay, speed=a.speed, realtime=a.realtime)
    elif a.live:
        if not a.decoder:
            ap.error("--live needs --decoder (the game protocol decoder is not bundled; supply your own)")
        src = capture_source(load_decoder(a.decoder), live_frames(iface=a.iface, host=a.host, port=a.port))
    else:
        ap.error("pass --replay FILE, or --live --decoder MODULE")
        return 2

    last = 0.0
    try:
        for ev in src:
            m.add(ev)
            if a.realtime and (time.monotonic() - last) >= a.interval:
                last = time.monotonic()
                _print(m.snapshot())
    except KeyboardInterrupt:
        pass
    _print(m.snapshot())
    if a.save:
        import json
        with open(a.save, "w", encoding="utf-8") as f:
            json.dump(m.to_a2log(), f)
        print(f"saved {a.save}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
