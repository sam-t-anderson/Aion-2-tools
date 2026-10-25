"""Install Pet Tracker on request: the current official installer, checked before it runs.

Pet Tracker (https://github.com/0Fox2Give/PetTracker, by 0Fox2Give, GPL-3.0) is a separate Windows program;
Aion 2 Calc never ships it. When the user asks for it (the optional task in Aion 2 Calc's installer, or Install
under Settings → Pet Tracker), this module

1. downloads Pet Tracker's signed release feed (``releases.win-stable.signed.json``) from its GitHub release,
2. checks the publisher's ECDSA P-256 signature with the same public key Pet Tracker's own updater pins
   (``publisher.json`` in its repository), and the feed's identity and validity period, as that updater does,
3. reads the installer's SHA-256 from the signed feed (Pet Tracker's release script refuses to publish an
   installer without it),
4. downloads ``PetTracker.Desktop-win-stable-Setup.exe`` and starts it only when its digest matches.

Nothing runs that the publisher did not sign for. The signature check is a small verify-only P-256
implementation (the frozen app carries no cryptography library); it handles only public data, so it needs no
constant-time arithmetic.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_ID = "PetTracker.Desktop"
CHANNEL = "win-stable"
FEED_ROOT = "https://github.com/0Fox2Give/PetTracker/releases/download/updates/"
SIGNED_FEED = f"releases.{CHANNEL}.signed.json"
SETUP_NAME = f"{APP_ID}-{CHANNEL}-Setup.exe"
RELEASES_URL = "https://github.com/0Fox2Give/PetTracker/releases/tag/updates"
#: Pet Tracker's release-signing public key, as its repository's publisher.json and its updater pin it.
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEFa/62/yl3f9kUJGiMRGNdIOnqs4a
UqR5D1HXsHGX1fFCnr6eglbwoSKwrOMumgRfRsFi2gvtKKQoinIx27udVA==
-----END PUBLIC KEY-----"""

MAX_FEED_BYTES = 2 * 1024 * 1024          # the limits Pet Tracker's updater applies to the feed
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_SETUP_BYTES = 512 * 1024 * 1024
MAX_VALIDITY = timedelta(days=90)
CLOCK_SKEW = timedelta(minutes=5)
_AGENT = {"User-Agent": "aion2calc Pet Tracker setup"}


class SetupError(Exception):
    """A step of the install that did not succeed, worded for the person reading it."""


# ------------------------------------------------------------------ ECDSA P-256 (verify only)

_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_A = _P - 3
_B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
_G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
      0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)
#: DER SubjectPublicKeyInfo header of an uncompressed P-256 key: id-ecPublicKey, prime256v1, BIT STRING.
_SPKI_P256 = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")


def _on_curve(point) -> bool:
    x, y = point
    return 0 <= x < _P and 0 <= y < _P and (y * y - (x * x * x + _A * x + _B)) % _P == 0


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        slope = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        slope = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (slope * slope - x1 - x2) % _P
    return x3, (slope * (x1 - x3) - y1) % _P


def _multiply(k: int, point):
    result, addend = None, point
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def public_key_point(pem: str) -> tuple[int, int]:
    """The (x, y) point of a PEM P-256 public key; anything else is refused."""
    body = "".join(line.strip() for line in pem.strip().splitlines() if line.strip() and not line.startswith("-----"))
    der = base64.b64decode(body, validate=True)
    if len(der) != 91 or not der.startswith(_SPKI_P256) or der[26] != 4:
        raise SetupError("The publisher key is not an uncompressed P-256 public key.")
    point = int.from_bytes(der[27:59], "big"), int.from_bytes(der[59:91], "big")
    if not _on_curve(point):
        raise SetupError("The publisher key is not a point on P-256.")
    return point


def verify_signature(point: tuple[int, int], message: bytes, signature: bytes) -> bool:
    """ECDSA P-256 with SHA-256 over ``message``; ``signature`` is r‖s (IEEE P1363, 64 bytes), the format
    .NET's ``ECDsa.SignData`` produces and Pet Tracker's updater verifies."""
    if len(signature) != 64 or not _on_curve(point):
        return False
    r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    if not (1 <= r < _N and 1 <= s < _N):
        return False
    e = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, _N)
    total = _add(_multiply(e * w % _N, _G), _multiply(r * w % _N, point))
    return total is not None and total[0] % _N == r


# ------------------------------------------------------------------ the signed feed

def parse_time(value) -> datetime:
    """A .NET DateTimeOffset as JSON writes it (``2026-10-19T17:02:15.1157942+00:00``), as aware UTC."""
    if not isinstance(value, str):
        raise SetupError("The release feed has no valid dates.")
    text = value.strip().replace("Z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)          # .NET writes seven fractional digits
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise SetupError("The release feed has no valid dates.") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def verify_feed(envelope: bytes, now: datetime | None = None, key_pem: str = PUBLIC_KEY_PEM) -> dict:
    """Check the signed feed as Pet Tracker's updater does and return what the install needs:
    ``{"installer_sha256", "version", "published", "expires"}``."""
    now = now or datetime.now(timezone.utc)
    if len(envelope) > MAX_FEED_BYTES:
        raise SetupError("Pet Tracker's release feed is too large.")
    try:
        doc = json.loads(envelope.decode("utf-8-sig"))
        payload = base64.b64decode(doc["Payload"], validate=True)
        signature = base64.b64decode(doc["Signature"], validate=True)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise SetupError("Pet Tracker's release feed could not be read.") from None
    if len(payload) > MAX_PAYLOAD_BYTES or len(signature) > 256:
        raise SetupError("Pet Tracker's release feed is too large.")
    if not verify_signature(public_key_point(key_pem), payload, signature):
        raise SetupError("Pet Tracker's release feed is not signed by its publisher, so nothing was installed.")
    try:
        release = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SetupError("Pet Tracker's signed release could not be read.") from None
    if not isinstance(release, dict) or release.get("AppId") != APP_ID or release.get("Channel") != CHANNEL:
        raise SetupError("Pet Tracker's signed release names a different program or channel.")
    published, expires = parse_time(release.get("PublishedUtc")), parse_time(release.get("ExpiresUtc"))
    if published > now + CLOCK_SKEW or expires <= now or expires <= published or expires - published > MAX_VALIDITY:
        raise SetupError("Pet Tracker's signed release feed has expired or is not valid yet. "
                         "Check the computer's clock, or try again later.")
    digest = release.get("InstallerSHA256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", digest):
        raise SetupError("Pet Tracker's signed release does not list its installer's checksum, so nothing was installed.")
    return {"installer_sha256": digest.lower(), "version": _feed_version(release.get("Feed")),
            "published": published.isoformat(), "expires": expires.isoformat()}


def latest_release(opener=None, now: datetime | None = None) -> dict:
    """The newest release Pet Tracker's publisher signed, checked exactly as ``install`` checks it (the app's
    update notice compares it with the installed version)."""
    return verify_feed(_fetch(FEED_ROOT + SIGNED_FEED, MAX_FEED_BYTES, opener), now=now)


def _feed_version(feed) -> str | None:
    """The newest version the signed Velopack feed lists (for the status line only)."""
    try:
        assets = json.loads(feed).get("Assets") or []
    except (TypeError, ValueError, AttributeError):
        return None
    versions = [a.get("Version") for a in assets if isinstance(a, dict) and isinstance(a.get("Version"), str)
                and re.fullmatch(r"\d+(\.\d+){1,3}", a["Version"])]
    return max(versions, key=lambda v: tuple(int(p) for p in v.split(".")), default=None)


# ------------------------------------------------------------------ download and open

def _fetch(url: str, limit: int, opener=None) -> bytes:
    request = urllib.request.Request(url, headers=_AGENT)
    with (opener or urllib.request.urlopen)(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise SetupError("A Pet Tracker download was larger than expected.")
    return data


def download_verified(url: str, target: Path, sha256: str, limit: int = MAX_SETUP_BYTES, opener=None,
                      progress=None) -> Path:
    """Download ``url`` to ``target`` and keep it only when its SHA-256 is ``sha256``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest, total = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers=_AGENT)
    try:
        with (opener or urllib.request.urlopen)(request, timeout=60) as response, open(partial, "wb") as out:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > limit:
                    raise SetupError("The Pet Tracker installer was larger than expected.")
                digest.update(block)
                out.write(block)
                if progress:
                    progress(total)
        if digest.hexdigest() != sha256.lower():
            raise SetupError("The downloaded Pet Tracker installer does not match its signed checksum, so it was not "
                             "started. Its release may be updating right now; try again in a few minutes.")
        os.replace(partial, target)
    finally:
        try:
            partial.unlink()
        except OSError:
            pass
    return target


_LOCK = threading.RLock()
_STATE: dict = {"status": "idle", "version": None, "error": None}


def status() -> dict:
    with _LOCK:
        return {"supported": sys.platform == "win32", **_STATE}


def _set(**values) -> None:
    with _LOCK:
        _STATE.update(values)


def _folder() -> Path:
    from ..paths import home
    return home() / "downloads" / "pettracker"


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass                                       # still open (an antivirus scan); the next install clears it


def _start_installer(path: Path):
    """Start the installer. Pet Tracker installs per user, so it needs no elevation; should a later one ask
    for it, ShellExecute shows Windows' own prompt."""
    try:
        return subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
    except OSError as err:
        if getattr(err, "winerror", None) == 740:              # the installer asked for elevation
            os.startfile(str(path), "runas", cwd=str(path.parent))   # noqa: S606 - the verified installer
            return None
        raise


def install(wait: float | None = None, opener=None, now: datetime | None = None, start=None) -> dict:
    """Verify, download and start Pet Tracker's installer; with ``wait`` (seconds), wait that long for it to
    finish. Returns :func:`status`."""
    if sys.platform != "win32" and start is None:
        _set(status="error", error="Pet Tracker runs on Windows only.")
        return status()
    try:
        _set(status="finding", error=None)
        release = verify_feed(_fetch(FEED_ROOT + SIGNED_FEED, MAX_FEED_BYTES, opener), now=now)
        _set(status="downloading", version=release["version"])
        name = f"PetTracker-{release['version']}-Setup.exe" if release["version"] else SETUP_NAME
        target = download_verified(FEED_ROOT + SETUP_NAME, _folder() / name, release["installer_sha256"], opener=opener)
        for old in target.parent.glob("PetTracker*Setup.exe"):
            if old != target:
                _discard(old)                      # an earlier download
        _set(status="installing")
        proc = (start or _start_installer)(target)
        if proc is None or not wait:
            _set(status="started")                 # running on its own; the app notices the install when it lands
            return status()
        try:
            code = proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            _set(status="started")
            return status()
        if code != 0:
            raise SetupError(f"Pet Tracker's installer ended with code {code}.")
        _discard(target)                           # installed: its installer is not needed again
        _set(status="installed")
    except SetupError as err:
        _set(status="error", error=str(err))
    except Exception as err:                                                     # noqa: BLE001 - shown to the user
        if getattr(err, "winerror", None) in (5, 740, 1223):
            message = "Windows did not allow Pet Tracker's installer to start."
        else:
            message = f"Pet Tracker could not be installed: {type(err).__name__}: {err}"
        _set(status="error", error=message)
    return status()


def begin_install(opener=None) -> dict:
    """Start :func:`install` in the background (Settings → Pet Tracker → Install) and return at once."""
    with _LOCK:
        if _STATE.get("status") in ("finding", "downloading", "installing"):
            return status()
        _STATE.update(status="finding", version=None, error=None)
    threading.Thread(target=install, kwargs={"wait": 900, "opener": opener}, daemon=True,
                     name="pettracker-setup").start()
    return status()
