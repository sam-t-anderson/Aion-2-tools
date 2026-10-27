"""HTTPS certificate checks (0.2.345): the app asks the operating system's verifier (truststore) about every
server's certificate, Mozilla's roots (certifi) second, instead of Python's check against its own copy of
the Windows certificate stores, which failed GitHub's chain on computers that had not downloaded its root
("certificate verify failed: unable to get issuer certificate"), so the update check never saw a release."""
import datetime
import http.client
import http.server
import ssl
import sys
import threading
import urllib.error
import urllib.request

import certifi
import pytest
import truststore

from aion2calc import launcher, tls


@pytest.fixture(autouse=True)
def pythons_own_check():
    """Each test starts and ends with Python's own check (the command-line tests install the app's)."""
    tls.uninstall()
    yield
    tls.uninstall()


@pytest.fixture
def installed():
    assert tls.install()


def test_https_requests_use_the_systems_verifier_with_mozillas_roots_second(installed):
    context = ssl._create_default_https_context()
    assert isinstance(context, truststore.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert isinstance(http.client.HTTPSConnection("example.test")._context, truststore.SSLContext)
    assert tls.status() == {"system": True, "bundled": True, "roots": certifi.where(), "roots_present": True}


def test_each_connection_gets_a_context_of_its_own(installed):
    # A truststore context holds a lock through each handshake. Python 3.12 gives urllib's shared opener one
    # context for every request, so the app's requests would wait on one another (a stalled handshake on
    # the log server would hold up the update check): urllib's opener now makes one per connection.
    assert ssl._create_default_https_context() is not ssl._create_default_https_context()
    handlers = urllib.request._opener.handlers
    assert any(isinstance(h, tls._ContextPerConnection) for h in handlers)
    assert not any(type(h) is urllib.request.HTTPSHandler for h in handlers)


def test_uninstall_puts_pythons_own_check_back(installed):
    tls.uninstall()
    assert not isinstance(ssl._create_default_https_context(), truststore.SSLContext)
    assert urllib.request._opener is None and tls.status()["system"] is False


def test_without_truststore_pythons_own_check_stays(monkeypatch):
    monkeypatch.setitem(sys.modules, "truststore", None)                  # import truststore raises ImportError
    assert tls.install() is False
    assert ssl._create_default_https_context is tls._DEFAULT and tls.status()["system"] is False


def test_the_app_and_the_command_line_install_it_before_anything_else(monkeypatch):
    from aion2calc import __main__ as cli
    calls = []
    monkeypatch.setattr(tls, "install", lambda: calls.append(1) or True)
    for main in (launcher.main, cli.main):
        with pytest.raises(SystemExit):
            main(["--help"])
    assert calls == [1, 1]


def _issue(tmp_path):
    """A chain like the one that failed: a root, the same root cross-signed by an older root nobody has any
    more, an intermediate and a server certificate for 127.0.0.1. Returns the files of the root, of its
    cross-signed copy and of the server's certificate, intermediate and key."""
    x509 = pytest.importorskip("cryptography.x509")
    import ipaddress
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    now = datetime.datetime.now(datetime.timezone.utc)
    name = lambda cn: x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])                  # noqa: E731

    def cert(subject, issuer, key, signer, ca, san=None):
        build = (x509.CertificateBuilder().subject_name(name(subject)).issuer_name(name(issuer))
                 .public_key(key.public_key()).serial_number(x509.random_serial_number())
                 .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=2))
                 .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if san:
            build = build.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(san))]),
                                        critical=False)
        return build.sign(signer, hashes.SHA256())

    old, root, middle, leaf = (ec.generate_private_key(ec.SECP256R1()) for _ in range(4))
    pem = lambda c: c.public_bytes(serialization.Encoding.PEM)                                  # noqa: E731
    files = {"root": pem(cert("test root", "test root", root, root, True)),
             "cross": pem(cert("test root", "older test root", root, old, True)),
             "server": pem(cert("127.0.0.1", "test intermediate", leaf, middle, False, san="127.0.0.1"))
             + pem(cert("test intermediate", "test root", middle, root, True))
             + leaf.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())}
    for key, data in files.items():
        (tmp_path / f"{key}.pem").write_bytes(data)
    return {key: tmp_path / f"{key}.pem" for key in files}


@pytest.fixture
def https_server(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    files = _issue(tmp_path)

    class Hello(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hello)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(files["server"])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"https://127.0.0.1:{server.server_address[1]}/", files
    server.shutdown()


def test_the_old_check_fails_where_the_new_one_verifies(https_server, monkeypatch):
    url, files = https_server
    # Python's own check on Windows: OpenSSL trusts what the Windows stores hold, the intermediate store
    # included. Holding the cross-signed copy of the root but not the root itself, it stops at the older
    # root above that copy, with the error players saw.
    stores = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    stores.minimum_version = ssl.TLSVersion.TLSv1_2
    stores.load_verify_locations(cafile=files["cross"])
    with pytest.raises(urllib.error.URLError) as refused:
        urllib.request.urlopen(url, timeout=10, context=stores)
    assert "unable to get issuer certificate" in str(refused.value.reason)
    # The app's check: the system's verifier, and Mozilla's roots second (here the test root stands in for
    # certifi's file, as Windows would download the real root).
    monkeypatch.setattr(tls, "_bundled_roots", lambda: str(files["root"]))
    assert tls.install()
    try:
        with urllib.request.urlopen(url, timeout=10) as answer:
            assert answer.read() == b"hello"
    finally:
        tls.uninstall()


def test_a_certificate_nobody_trusts_is_refused(https_server, installed):
    url, _ = https_server
    with pytest.raises(urllib.error.URLError) as refused:
        urllib.request.urlopen(url, timeout=10)
    assert isinstance(refused.value.reason, ssl.SSLCertVerificationError)
