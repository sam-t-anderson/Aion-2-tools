"""Links to the app's own pages open in the native window (0.2.500), at the address the web interface reads
(app.js ``route``): Combat Logs at a list, a featured encounter's page, the Account page at a tab and a legion, and
every other page, an unknown one the Build Planner, as there. Until now only an analyzed encounter and a log's review
opened here; every other link to a page went to the web interface, though this window draws them all. Drawn off
screen.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from aion2calc.gui import window as wm  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage, web_route  # noqa: E402

FEATURED = "fe_0123456789"
LEGION = "lg_0123456789ab"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _window(monkeypatch, *extra):
    """The window (with ``extra`` pages in its navigation), the pages it sends to the web interface noted rather than
    opened."""
    on_the_web = []
    monkeypatch.setattr(MainWindow, "open_in_web", lambda self, page: on_the_web.append(page))
    if extra:
        monkeypatch.setattr(wm, "SECTIONS", wm.SECTIONS + (("", extra),))
    window = MainWindow(None)
    window.on_the_web = on_the_web
    window.resize(1200, 800)
    window.show()
    QCoreApplication.processEvents()
    return window


def test_an_address_is_read_as_the_web_interface_reads_it():
    assert web_route("") == web_route(None) == {"page": "meter"}
    assert web_route("character") == {"page": "character"} and web_route("gear/anything") == {"page": "gear"}
    assert web_route("nowhere") == web_route("character?x") == {"page": "planner"}      # an unknown page: the planner
    assert web_route("combat") == {"page": "combat", "list": None}
    assert web_route("combat/identities") == web_route("combat/identities?x=1") == {"page": "combat", "list": "identities"}
    assert web_route("combat/nope")["list"] is None and web_route("combat/saved")["list"] == "saved"
    assert web_route(f"featured/{FEATURED}/rankings?metric=speed") == {"page": "featured", "id": FEATURED,
                                                                         "view": "rankings", "metric": "speed"}
    assert web_route("featured/fe%5Fx") == {"page": "featured", "id": "fe_x", "view": "race", "metric": None}
    assert web_route("featured") == {"page": "featured", "id": "", "view": "race", "metric": None}
    assert web_route(f"account/legions/{LEGION}") == {"page": "account", "tab": "legions", "legion": LEGION}
    assert web_route("account/legions/lg_nope")["legion"] is None
    assert web_route(f"account/parses/{LEGION}") == {"page": "account", "tab": "parses", "legion": None}
    assert web_route("account") == web_route("account/nope") == {"page": "account", "tab": "logs", "legion": None}
    assert web_route("combat-log/analysis/7") == {"page": "combat-log"}
    assert set(wm.COMBAT_LISTS) == {"community", "owned", "saved", "identities"}


def test_the_window_opens_its_own_pages(qapp, monkeypatch):
    window = _window(monkeypatch)
    for page in ("character", "gear", "history", "settings", "timers", "builds", "raid", "pets", "news", "meter"):
        window.open_web(page)
        assert window.current_page() == page and not isinstance(window.page(page), WebPage)
    window.open_web("somewhere-else")
    assert window.current_page() == "planner"                                         # as the web interface shows it
    window.open_web("")
    assert window.current_page() == "meter"
    # Combat Logs: from a page shown in place of its views, back to them, at the list asked for
    combat = window.page("combat")
    window.open_web("combat-log/analysis/7")
    QCoreApplication.processEvents()
    assert combat.analysis_page.isVisibleTo(combat) and not combat.frame.isVisibleTo(combat)
    window.open_web("combat/identities")
    QCoreApplication.processEvents()
    assert window.current_page() == "combat" and combat.frame.isVisibleTo(combat)
    assert not combat.featured_box.isVisibleTo(combat) and combat.list == "identities"
    assert combat.identities is not None and combat.identities.isVisibleTo(combat)
    window.open_web("combat")                                                          # the list as it was left
    assert combat.list == "identities" and combat.view == "community"
    # a featured encounter's page, on its view and metric
    window.open_web(f"featured/{FEATURED}/rankings?metric=hps")
    QCoreApplication.processEvents()
    page = combat.featured_page
    assert window.current_page() == "combat" and page.isVisibleTo(combat) and not combat.frame.isVisibleTo(combat)
    assert (page.fid, page.view, page.state["metric"]) == (FEATURED, "rankings", "hps")
    window.open_web("featured/nothing")
    QCoreApplication.processEvents()
    assert page.fid == "nothing" and any(label.text() == "There is no featured encounter at this address."
                                         for label in page.findChildren(QLabel) if label.isVisibleTo(page))
    # the Account page, at its tab and the legion the address opens
    account = window.page("account")
    window.open_web(f"account/legions/{LEGION}")
    assert window.current_page() == "account" and (account.tab, account.legion) == ("legions", LEGION)
    window.open_web("account/security")
    assert (account.tab, account.legion) == ("security", None)
    window.open_web("account")
    assert account.tab == "logs"
    assert window.on_the_web == []                                                     # nothing went to the web interface
    # a log's address this window cannot read still opens in the web interface
    window.open_web("combat-log/opened/1700000000000")
    assert window.on_the_web == ["combat-log/opened/1700000000000"]


def test_the_links_on_its_pages_open_here(qapp, monkeypatch):
    window = _window(monkeypatch, ("elsewhere", "Elsewhere"))
    window.page("timers")._link("web:combat")                                          # Browse combat logs →
    assert window.current_page() == "combat"
    window.page("account").open_web("combat/identities")                              # the claim's link (CLAIM_PAGE)
    assert window.current_page() == "combat" and window.page("combat").list == "identities"
    window.page("history").open_web("gear")                                            # the Pet Genus window's links
    assert window.current_page() == "gear"
    window.page("character").open_web("character")
    assert window.current_page() == "character"
    assert window.on_the_web == []
    # what means the web interface keeps it: a page not drawn here, and a setting not drawn on Settings yet
    window.open_web("elsewhere")
    placeholder = window.page("elsewhere")
    assert window.current_page() == "elsewhere" and isinstance(placeholder, WebPage) and window.on_the_web == []
    placeholder.button.click()
    assert window.on_the_web == ["elsewhere"]
    window.page("settings").open_web("settings")
    assert window.on_the_web == ["elsewhere", "settings"]
