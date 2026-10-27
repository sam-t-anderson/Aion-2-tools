"""The Account page before signing in (pages/account.js, account-view.js): where the log server has accounts,
the page offers to create one and the header offers to sign in; where it has none, the page says the server's
reason and offers no sign-up that could only fail."""
import community as stand_in
from apphelpers import close_context, go, open_context, watched_page


def test_signing_up_is_offered_where_the_server_has_accounts(browser, app_url):
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/account/")
        page.wait_for_selector("[data-register]")
        assert page.locator("[data-register]").is_enabled()
        assert page.locator("#account-menu .acct-signin").inner_text() == "Sign in"
        assert not page.locator("#account-root div.note").count()      # no notice above the sign-up
    finally:
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()


def test_a_server_without_accounts_says_so(browser, app_url):
    config = stand_in.ANSWERS.pop("/api/v1/account/config")
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    try:
        go(page, app_url, "#/account/")
        page.wait_for_selector("[data-register]")
        assert page.locator("#account-root div.note").inner_text() == "not served by the test server"
        assert page.locator("[data-register]").is_disabled()
        assert page.locator("#account-menu .acct-signin").inner_text() == "Sign in"
    finally:
        stand_in.ANSWERS["/api/v1/account/config"] = config
        close_context(context)
    assert not watch.unexpected(), watch.unexpected()
