"""``python -m aion2calc.logserver``: run the log server and manage upload keys.

Settings come from the command line or the environment (A2LOGS_DATA, A2LOGS_HOST, A2LOGS_PORT,
A2LOGS_PUBLIC_URL, A2LOGS_ALLOW_ANONYMOUS, A2LOGS_MAX_MB, A2LOGS_UPLOADS_PER_HOUR,
A2LOGS_TRUST_PROXY, A2LOGS_NAME).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from .server import env_defaults, serve
from .store import Store


def main(argv=None) -> int:
    env = env_defaults()
    p = argparse.ArgumentParser(prog="python -m aion2calc.logserver", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=env["data"], help="folder for the database and the logs")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the server")
    s.add_argument("--host", default=env["host"])
    s.add_argument("--port", type=int, default=env["port"])
    s.add_argument("--public-url", default=env["public_url"], help="https://logs.example.com (used in links)")
    s.add_argument("--allow-anonymous", action="store_true", default=env["allow_anonymous"],
                   help="accept uploads without a key (rate limited per IP)")
    s.add_argument("--max-mb", type=int, default=env["max_bytes"] // (1024 * 1024))
    s.add_argument("--uploads-per-hour", type=int, default=env["uploads_per_hour"])
    s.add_argument("--trust-proxy", action="store_true", default=env["trust_proxy"],
                   help="behind nginx: take the client IP and scheme from X-Forwarded-* headers")
    s.add_argument("--name", default=env["name"])
    k = sub.add_parser("keys", help="upload keys")
    ks = k.add_subparsers(dest="kcmd", required=True)
    kc = ks.add_parser("create")
    kc.add_argument("name", help="who or what uses the key (an app, a person)")
    ks.add_parser("list")
    kr = ks.add_parser("revoke")
    kr.add_argument("id", type=int)
    args = p.parse_args(argv)
    if args.cmd == "serve":
        serve(args.data, args.host, args.port, public_url=args.public_url, allow_anonymous=args.allow_anonymous,
              max_bytes=args.max_mb * 1024 * 1024, uploads_per_hour=args.uploads_per_hour,
              trust_proxy=args.trust_proxy, name=args.name)
        return 0
    st = Store(args.data)
    if args.kcmd == "create":
        kid, token = st.create_key(args.name)
        print(f"key {kid} for {args.name}:\n  {token}\nIt is shown only once; uploads send it as "
              "'Authorization: Bearer <key>'.")
    elif args.kcmd == "list":
        for r in st.keys():
            when = dt.datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d")
            print(f"{r['id']:4d}  {r['name']:30s} {when}  uploads {r['uploads']:6d}  {'revoked' if r['revoked'] else ''}")
    elif args.kcmd == "revoke":
        print("revoked" if st.revoke(args.id) else "no such key")
    return 0


if __name__ == "__main__":
    sys.exit(main())
