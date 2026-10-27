"""The player's optional account on the log server (the server's accounts.py and legions.py).

An account has no password. This app creates it and keeps its credential in ``account.json`` beside the
ownership backup, never in a settings export; the app's pages never see the credential: they ask this
module, which talks to the server. A website signs in when the app approves the code it shows, or opens
signed in from the app; another computer's app joins with a code from a signed-in website, and an app that
lost its credential recovers the account from the ownership backup.

Once signed in, uploads join the account, and the logs and characters this app already holds (the
ownership backup and the identity claims) are added to it, so the website shows them under the player's
name. The account belongs to the server it was made on; another server in Settings is not signed in.
"""
from __future__ import annotations

import json
import platform
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from ..paths import data_file, read_json, user_data, write_user_json

FILE = ("account.json",)
LOCK = threading.RLock()
TOKEN = re.compile(r"a2app_[A-Za-z0-9_-]{20,90}")
#: the website where accounts sign in, when the server does not name its own
DEFAULT_SITE = "https://sam-t-anderson.github.io/Aion-2-tools/"

#: what the app's pages may ask the server through ``request`` (everything else has a function here)
_ALLOWED = {
    "GET": re.compile(r"/api/v1/(account|account/(logs|sessions|activity|passkeys|signin/lookup)"
                      r"|legions|legions/mine|legions/lg_[0-9a-f]{12}(/logs)?)"),
    "POST": re.compile(r"/api/v1/(account/(logs/[A-Za-z0-9]{6,16}/(visibility|title|delete|detach)|sessions/revoke|name"
                       r"|signin/(approve|deny)|link|passkeys/remove|discord/unlink|delete)"
                       r"|legions|legions/(invite/preview|join)"
                       r"|legions/lg_[0-9a-f]{12}/(invites|invites/revoke|request|request/withdraw|requests/decide"
                       r"|role|remove|leave|disband))"),
}
_QUERY = re.compile(r"[A-Za-z0-9_=&%.+-]{0,300}")
#: where Discord's sign-in returns: this app's own page on this computer (app/server.py serves it)
DISCORD_BACK = re.compile(r"http://127\.0\.0\.1:[0-9]{1,5}/api/account/discord-done")
_HANDOFF = re.compile(r"[A-Za-z0-9_-]{20,100}")
_pending = {}                         # the Discord sign-in this app waits for: request, secret (never sent to the page)
_POLL = threading.Lock()              # one poll of the server at a time: the page's and the browser's return


class SignedOut(Exception):
    """The server ended this app's sign-in (revoked, expired or the account closed)."""


def _server() -> str:
    from .share import effective
    return str(effective().get("url") or "").rstrip("/")


def _load() -> dict:
    with LOCK:
        try:
            row = read_json(*FILE) if data_file(*FILE).exists() else {}
        except (OSError, ValueError):
            return {}
        if not isinstance(row, dict) or not TOKEN.fullmatch(str(row.get("token") or "")):
            return {}
        return {"server": str(row.get("server") or "").rstrip("/"), "token": row["token"],
                "id": str(row.get("id") or ""), "name": str(row.get("name") or "")}


def _save(server: str, token: str, account: dict) -> None:
    if not TOKEN.fullmatch(token or ""):
        raise ValueError("The server answered without a valid app credential")
    with LOCK:
        write_user_json({"server": server, "token": token, "id": account.get("id"), "name": account.get("name")}, *FILE)


def _forget() -> None:
    with LOCK:
        user_data().joinpath(*FILE).unlink(missing_ok=True)


def label() -> str:
    """How this computer is named in the account's sessions."""
    system = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(platform.system(), platform.system() or "a computer")
    return f"Desktop app on {system}"


def _call(server: str, method: str, path: str, body=None, token: str | None = None, timeout: float = 30) -> dict:
    """One request to the server; its own words are the error. Never follows a redirect with the credential."""
    if not re.fullmatch(r"https?://[^/\s]+(/[^\s?#]*)?", server or ""):
        raise ValueError("Set a log server in Settings first")
    headers = {"User-Agent": "aion2calc", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["X-Account-Token"] = token

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        req = urllib.request.Request(server + path, data, headers, method=method)
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read() or b"{}").get("error")
        except (ValueError, AttributeError):
            reason = None
        if exc.code == 401 and token:
            raise SignedOut(reason or "Sign in again: this sign-in has ended") from None
        if exc.code == 404 and not reason:
            reason = "This server has no accounts yet (it needs server 0.2.139 or later)"
        raise ValueError(reason or f"The server refused ({exc.code})") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"Could not reach the log server ({getattr(exc, 'reason', exc)})") from None


def _signed_in() -> dict:
    row = _load()
    if not row:
        raise PermissionError("Sign in first")
    if row["server"] != _server():
        raise PermissionError(f"You are signed in on {row['server']}; choose it in Settings → Log server, or sign out")
    return row


def _authed(method, path, body=None):
    row = _signed_in()
    try:
        return _call(row["server"], method, path, body, row["token"])
    except SignedOut:
        _forget()
        raise


def token_for(url: str) -> str | None:
    """The credential that joins an upload to the account, when the upload goes to the account's server."""
    row = _load()
    return row["token"] if row and row["server"] == str(url or "").rstrip("/") else None


def status() -> dict:
    """Whether this app is signed in, and the account as the server sees it now (no credential)."""
    server, row = _server(), _load()
    out = {"signed_in": False, "server": server, "account_server": row.get("server") or None}
    if not row:
        try:
            out["config"] = _call(server, "GET", "/api/v1/account/config", timeout=10) if server else None
        except ValueError as exc:
            out["config"], out["error"] = None, str(exc)
        return out
    out.update(signed_in=True, here=row["server"] == server, account={"id": row["id"], "name": row["name"]})
    if row["server"] != server:
        return out
    try:
        found = _call(row["server"], "GET", "/api/v1/account", token=row["token"], timeout=15)
        if _offer_claims(row):                  # claims made before 0.2.349 reached the account only with a sync
            found = _call(row["server"], "GET", "/api/v1/account", token=row["token"], timeout=15)
        out["account"], out["session"] = found.get("account"), found.get("session")
        if out["account"] and out["account"].get("name") != row["name"]:
            _save(row["server"], row["token"], out["account"])
    except SignedOut as exc:
        _forget()
        return {"signed_in": False, "server": server, "account_server": None, "ended": str(exc)}
    except ValueError as exc:
        out["error"] = str(exc)                     # offline: still signed in
    return out


def _signed_on(server, result) -> dict:
    _save(server, result["token"], result.get("account") or {})
    added = sync()
    return status() | {"added": added}


def register(name=None) -> dict:
    """A new account, with this app signed in to it."""
    server = _server()
    if _load():
        raise ValueError("This app is already signed in; sign out first")
    body = {"label": label()} | ({"name": str(name).strip()} if str(name or "").strip() else {})
    return _signed_on(server, _call(server, "POST", "/api/v1/account/register", body))


def link(code) -> dict:
    """Join the account of a signed-in website by the code it shows (Account → Link another computer)."""
    server = _server()
    if _load():
        raise ValueError("This app is already signed in; sign out first")
    return _signed_on(server, _call(server, "POST", "/api/v1/account/link/redeem", {"code": str(code or ""), "label": label()}))


def recover() -> dict:
    """An app that lost its credential gets one again from the ownership backup (three of the account's logs)."""
    from .ownership import entries
    server = _server()
    evidence = [{"id": r["id"], "delete_token": r["delete_token"]} for r in entries() if r["server"] == server][-500:]
    if len(evidence) < 3:
        raise ValueError("Recovery needs the private credentials of at least three of the account's uploads "
                         "(import your ownership backup on Combat Logs → My uploads first)")
    return _signed_on(server, _call(server, "POST", "/api/v1/account/recover", {"evidence": evidence, "label": label()}))


def discord_start(return_to: str) -> dict:
    """Open Discord's sign-in in the browser. The browser comes back to this app's own page on this computer
    (``return_to``) with a one-time handoff, which ``discord_finish`` takes; the server issues the app's
    credential only for it, so a Discord link sent to someone else signs nobody in here."""
    server = _server()
    if _load():
        raise ValueError("This app is already signed in; sign out first")
    if not DISCORD_BACK.fullmatch(str(return_to or "")):
        raise ValueError("Discord sign-in returns only to this app on this computer")
    started = _call(server, "POST", "/api/v1/account/discord/start", {"purpose": "app", "return_to": return_to})
    url = str(started.get("url") or "")
    if not url.startswith("https://discord.com/"):
        raise ValueError("The server did not start a Discord sign-in")
    with LOCK:
        _pending.clear()
        _pending.update(server=server, request=started.get("request"), secret=started.get("secret"))
    webbrowser.open(url)
    return {"waiting": True, "interval": max(2, int(started.get("interval") or 3))}


def _poll_server(waiting) -> dict:
    body = {"request": waiting["request"], "secret": waiting["secret"], "label": label()}
    if waiting.get("handoff"):
        body["handoff"] = waiting["handoff"]
    result = _call(waiting["server"], "POST", "/api/v1/account/discord/poll", body)
    if result.get("status") == "approved":
        return {"status": "approved"} | _signed_on(waiting["server"], result)
    return {"status": result.get("status") or "expired"} | ({"error": str(result["error"])[:200]} if result.get("error") else {})


def discord_finish(handoff=None, error=None) -> dict:
    """The browser came back from Discord to this app with its one-time handoff, or Discord's refusal: finish
    the sign-in now (the Account page need not be open); the page's next poll reads how it went."""
    with _POLL:
        with LOCK:
            waiting = dict(_pending)
        if not waiting or waiting.get("result"):
            return {"status": "expired"}
        if error:
            out = {"status": "error", "error": str(error)[:200]}
        elif not _HANDOFF.fullmatch(str(handoff or "")):
            out = {"status": "error", "error": "The browser came back from Discord without a sign-in"}
        else:
            out = _poll_server(waiting | {"handoff": handoff})
        if out["status"] != "pending":
            with LOCK:
                _pending["result"] = out
        return out


def discord_poll() -> dict:
    """The Discord sign-in this app waits for: pending until the browser comes back to this app."""
    with _POLL:
        with LOCK:
            waiting = dict(_pending)
        if not waiting:
            return {"status": "expired"}
        out = waiting.get("result") or _poll_server(waiting)
        if out["status"] != "pending":
            with LOCK:
                _pending.clear()
        return out


def sync() -> dict:
    """Add the uploads (ownership backup) and characters (identity claims) this app holds to the account."""
    from . import ownership
    row = _signed_in()
    owned = [{"id": r["id"], "delete_token": r["delete_token"]} for r in ownership.entries() if r["server"] == row["server"]]
    out = {"logs": 0, "characters": 0}
    for start in range(0, len(owned), 500):
        out["logs"] += int(_authed("POST", "/api/v1/account/logs/attach", {"evidence": owned[start:start + 500]}).get("attached") or 0)
    out["characters"] = _attach_claims(row)
    return out


def _attach_claims(row) -> int:
    from . import identity
    tokens = [c["token"] for c in identity.entries() if c["server"] == row["server"]][:200]
    if not tokens:
        return 0
    added = int(_authed("POST", "/api/v1/account/claims/attach", {"tokens": tokens}).get("added") or 0)
    _offered.update((row["server"], t) for t in tokens)
    return added


_offered = set()                      # (server, claim credential) this run already gave the account


def _offer_claims(row) -> int:
    """Once per run, the account is given every claim this app holds for its server, so a character claimed
    before signing in, or before claims joined the account at once, reaches it (and its legions) by itself."""
    from . import identity
    held = {(row["server"], c["token"]) for c in identity.entries() if c["server"] == row["server"]}
    if held <= _offered:
        return 0
    _offered.update(held)                 # offered once, even when the server is unreachable now
    try:
        return _attach_claims(row)
    except (ValueError, OSError):
        return 0


def attach_claims_quietly() -> int:
    """After a claim: add this app's claimed characters to the account, when the app is signed in on the server
    it claims on, so the account (and its legions) know the character at once. A failure only waits for the
    next sync; it never undoes the claim."""
    row = _load()
    if not row or row["server"] != _server():
        return 0
    try:
        return _attach_claims(row)
    except (SignedOut, ValueError, OSError):
        return 0


def open_website(page: str = "account.html") -> dict:
    """Open the website signed in, with a one-time ticket in the address's fragment (never sent to the site)."""
    if page != "account.html":
        raise ValueError("Unknown website page")
    row = _signed_in()
    try:
        site = str((_call(row["server"], "GET", "/api/v1/account/config", timeout=10) or {}).get("site") or "")
    except ValueError:
        site = ""
    if not re.fullmatch(r"https://[^/\s]+/[^\s?#]*", site):
        site = DEFAULT_SITE
    ticket = _authed("POST", "/api/v1/account/ticket", {})["ticket"]
    webbrowser.open(site.rstrip("/") + "/" + page + "#" + urllib.parse.urlencode({"a2ticket": ticket}))
    return {"opened": True}


def signout() -> dict:
    row = _load()
    if row:
        try:
            _call(row["server"], "POST", "/api/v1/account/signout", {}, row["token"], timeout=10)
        except (SignedOut, ValueError):
            pass                                    # signed out here either way
    _forget()
    return {"signed_in": False}


def request(method: str, path: str, body=None) -> dict:
    """What the app's pages ask the server for the account (listed in ``_ALLOWED``)."""
    method = str(method or "GET").upper()
    route, _, query = str(path or "").partition("?")
    rule = _ALLOWED.get(method)
    if not rule or not rule.fullmatch(route) or not _QUERY.fullmatch(query):
        raise PermissionError("The app does not send that request")
    result = _authed(method, route + ("?" + query if query else ""), body if method == "POST" else None)
    if route == "/api/v1/account/delete":
        _forget()
    return result
