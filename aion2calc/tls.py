"""How the app checks the certificates of the HTTPS servers it talks to (0.2.345).

Python checks a server's certificate chain with OpenSSL against a copy of the certificates already in
the Windows certificate stores, the intermediate store included. Windows itself downloads a root it
does not have yet the first time a chain needs it, and chooses among cross-signed paths to one it
trusts; Python does neither. When the chain it built led through a stored intermediate to a root the
computer had not downloaded, the update check failed with "certificate verify failed: unable to get
issuer certificate" while the browser opened GitHub fine, and the app never offered the release that
would fix it.

:func:`install` makes every HTTPS request the app makes (urllib and http.client, with no context of
their own) check the certificate with the operating system's verifier, as browsers do: truststore,
which asks the Windows chain engine, the macOS Security framework or the system's certificates on
Linux. Mozilla's roots, bundled with the app (certifi), come second: on Windows they are tried only
when the system's chain fails, elsewhere they are trusted alongside the system's."""
from __future__ import annotations

import http.client
import os
import ssl
import urllib.request

_DEFAULT = ssl._create_default_https_context      # Python's own, put back by uninstall()
_INSTALLED = {"system": False, "bundled": False}


class _ContextPerConnection(urllib.request.HTTPSHandler):
    """urllib's HTTPS handler with a context of its own for each connection. Python 3.12 makes one per
    opener, so every request through urllib's shared opener would wait on that context's lock, which a
    truststore context holds through each handshake."""

    def https_open(self, req):
        return self.do_open(http.client.HTTPSConnection, req, context=ssl._create_default_https_context())


def _bundled_roots() -> str | None:
    """The file of Mozilla's roots that ships with the app, or None without certifi."""
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return None


def install() -> bool:
    """Check HTTPS certificates with the operating system's verifier from now on, Mozilla's roots
    second. Call it before the first request. False, and Python's own check stays, when truststore is
    missing (a checkout without the app's dependencies)."""
    try:
        import truststore
    except ImportError:
        return False
    roots = _bundled_roots()

    def https_context() -> ssl.SSLContext:
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if roots:
            context.load_verify_locations(cafile=roots)
        return context

    ssl._create_default_https_context = https_context
    urllib.request.install_opener(urllib.request.build_opener(_ContextPerConnection()))
    _INSTALLED.update(system=True, bundled=bool(roots))
    return True


def uninstall() -> None:
    """Python's own certificate check again (for tests)."""
    ssl._create_default_https_context = _DEFAULT
    urllib.request.install_opener(None)
    _INSTALLED.update(system=False, bundled=False)


def status() -> dict:
    """What checks HTTPS certificates in this process: ``system`` (the operating system's verifier)
    and ``bundled`` (Mozilla's roots as well), and whether the file of those roots is there."""
    roots = _bundled_roots()
    return {**_INSTALLED, "roots": roots, "roots_present": bool(roots and os.path.isfile(roots))}
