"""The Account page's words (0.2.447), as pages/account.js and account-view.js write them: the account offered when
signed out, the account's name and counts, and Sign-in & security (the ways in, where it is signed in, what it did
lately, closing it). The app keeps the credential and talks to the server (combat/account.py); the page asks the app.
"""
from __future__ import annotations

import re
import urllib.parse

from .character import js_number
from .news import when as moment
from .results import _dict, _list, _truthy, js_text

SITE = "https://sam-t-anderson.github.io/Aion-2-tools/"
INTRO = ("An account is optional. With one, your uploads from this app and the ones it made before are in one place, on "
         "the website too, under your name; you can share logs with your legion and see theirs.")
NO_PASSWORD = "There is no password: this app stays signed in, and it approves your sign-ins on the website."
NAME_HINT = "Your name (optional)"
CREATE = "Create my account"
HAVE_ONE = "I already have an account"
DISCORD = "Sign in with Discord"
DISCORD_NOTE = "if you linked Discord on the website"
CODE_HINT = "ABCD-EFGH"
LINK = "Link with a code"
LINK_NOTE = "Website: Sign-in & security → Link another computer's app"
RECOVER = "Recover with my uploads"
RECOVER_NOTE = "Uses the private credentials of three of the account's uploads (your ownership backup)"
DISCORD_WAIT = "Finish signing in with Discord in your browser…"
DISCORD_ENDED = "The Discord sign-in ended. Try again."
DISCORD_WAIT_S = 10 * 60
CHOOSE_SERVER = "Choose a log server in Settings first."
TABS = (("logs", "My logs"), ("parses", "Top parses"), ("legions", "Legions"), ("security", "Sign-in & security"))
APPROVE = "Approve a website sign-in"
WEBSITE = "Open the website signed in"
WAYS_NOTE = ("On the website, choose Sign in → Approve in the app, then enter the code it shows here. Passkeys and Discord "
             "are added on the website (Sign-in & security there), and another computer's app joins with a code from the "
             "website.")
CODE_ASK = "The code the website shows (eight letters and digits)"
RENAME_ASK = "Your account's name (2-24 letters or digits)"
END_ALL_ASK = "Sign out every other app and website?"
RECENT_NOTE = "Anything you do not recognise? Sign out everywhere else, then check how you sign in."
CLOSE = "Close the account"
CLOSE_NOTE = ("Your logs stay on the server and keep working with their upload credentials, unless you delete them too. You "
              "leave your legions; one you lead passes to an officer.")
CLOSE_LOGS = "Delete my logs as well"
CLOSE_WORDS = "delete my account"
CLOSE_TYPE = 'Type "delete my account" to close it.'
ACTIVITY = {"created": "Account created", "signed_in": "Signed in", "signed_out": "Signed out", "renamed": "Renamed",
            "logs_attached": "Logs added", "visibility": "Visibility changed", "retitled": "Log renamed",
            "log_deleted": "Log deleted", "log_detached": "Log removed from the account", "character_added": "Character added",
            "discord_linked": "Discord linked", "discord_unlinked": "Discord unlinked", "passkey_added": "Passkey added",
            "passkey_removed": "Passkey removed", "signin_approved": "Website sign-in approved",
            "signin_denied": "Website sign-in denied", "link_code": "Link code made", "legion_created": "Legion founded",
            "legion_joined": "Legion joined", "recovered": "Recovered", "disabled": "Disabled by the operator",
            "active": "Enabled by the operator"}
ON_THE_WEB = {"logs": "My logs open in the web interface for now.", "parses": "Top parses open in the web interface for now.",
              "legions": "Legions open in the web interface for now."}


def when(t) -> str:
    """A moment the server gives in seconds, in the computer's clock (account-view.js ``when``); "—" for none."""
    if not _truthy(t):
        return "—"
    return moment(js_number(t) * 1000)


def many(n, one: str, other: str) -> str:
    """``many``: the words for one, or for any other count."""
    return (one if js_number(n) == 1 else other).replace("{0}", js_text(n))


def plain(message) -> str:
    """A refusal's words without the exception's name the app may put first."""
    return re.sub(r"^(ValueError|PermissionError|RuntimeError|LookupError|Error): ", "", js_text(message or ""))


def status_view(s) -> dict:
    """The app's account status (``accountStatus``): signed in on another server than Settings uses reads as signed
    out here, with that server said."""
    s = _dict(s)
    if s.get("signed_in") and s.get("here") is False:
        return {**s, "signed_in": False, "elsewhere": s.get("account_server")}
    return s


def signed_out_notes(s: dict) -> list[tuple[str, str]]:
    """The notes over the account offered: a sign-in that ended, one on another server (``elsewhere``, with Sign out),
    and no log server chosen or none reached."""
    notes = []
    if s.get("ended"):
        notes.append(("ended", js_text(s["ended"])))
    if s.get("elsewhere"):
        notes.append(("elsewhere", f"This app is signed in on {js_text(s['elsewhere'])}, not on the server Settings uses now "
                                   f"({js_text(s.get('server') or '—')})."))
    if not s.get("server"):
        notes.append(("server", CHOOSE_SERVER))
    elif s.get("error") and not _truthy(s.get("config")):
        notes.append(("error", js_text(s["error"])))
    return notes


def can_create(s: dict) -> bool:
    """**Create my account** is offered on the server Settings uses once its account settings were read."""
    return not (s.get("elsewhere") or not s.get("server") or not _truthy(s.get("config")))


def discord_offered(s: dict) -> bool:
    return bool(_dict(_dict(s.get("config")).get("methods")).get("discord"))


def signed_in_as(result) -> str:
    return f"Signed in as {js_text(_dict(_dict(result).get('account')).get('name') or '')}"


def title_line(me: dict) -> tuple[str, str]:
    """The account's name, and how many logs and characters it holds."""
    logs = me.get("logs") if me.get("logs") is not None else 0
    return (js_text(me.get("name")), many(logs, "{0} log", "{0} logs") + " · "
            + many(len(_list(me.get("characters"))), "{0} character", "{0} characters"))


def ways_line(me: dict) -> str:
    """How else the account signs in: Discord, its passkeys and its desktop apps."""
    discord = _dict(me.get("discord"))
    passkeys, apps = me.get("passkeys") or 0, me.get("apps") or 0
    return (f"Discord: {js_text(discord.get('name'))}" if _truthy(me.get("discord")) else "Discord: not linked") + " · " + \
        many(passkeys, "{0} passkey", "{0} passkeys") + " · " + many(apps, "{0} desktop app", "{0} desktop apps")


def session_rows(answer) -> list[dict]:
    """Where the account is signed in: each app or website, since when, last used, and this one or Sign out."""
    return [{"where": js_text(s.get("label")), "kind": "desktop app" if s.get("kind") == "app" else "website",
             "since": when(s.get("created_at")), "used": when(s.get("last_used")), "current": bool(s.get("current")),
             "id": s.get("id")} for s in _list(_dict(answer).get("sessions")) if isinstance(s, dict)]


def activity_rows(answer) -> list[tuple[str, str, str]]:
    """What the account did lately: when, what, and its note."""
    return [(when(a.get("created_at")), ACTIVITY.get(a.get("action"), js_text(a.get("action"))), js_text(a.get("note") or ""))
            for a in _list(_dict(answer).get("activity")) if isinstance(a, dict)]


def lookup_path(code: str) -> str:
    return "/api/v1/account/signin/lookup?code=" + urllib.parse.quote(code, safe="")


def approve_question(seen) -> str:
    """The question before a website sign-in is approved (``approveWebsiteSignIn``): which browser asks, and whether
    it started on this computer's internet connection."""
    seen = _dict(seen)
    same = seen.get("same_network")
    network = ("It started on this computer's internet connection." if same is True else
               "It did NOT start on this computer's internet connection. If someone asked you for this code, deny it."
               if same is False else "The server cannot tell which internet connection it started on.")
    return (f"Sign in {js_text(seen.get('browser'))} on the website as your account?\n\n{network}\n\n"
            "Approve only a sign-in you started yourself.")


def revoked(result) -> str:
    return f"{js_text(_dict(result).get('signed_out'))} signed out"


def signed_out_answer(message: str) -> bool:
    """A refusal that means the app is no longer signed in (``accountCall``)."""
    return bool(re.search(r"sign in again|signed out|Sign in first", message or "", re.IGNORECASE))
