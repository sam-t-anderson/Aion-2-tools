"""Quiet updates (0.2.353): a newer release downloads in the background with its progress for the app's bar, the
newest one when several come out while the app runs; Update now opens the staged installer, and closing the app
installs it quietly without starting the app again, unless the player turned that off."""
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from aion2calc import update


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(update, "_BG", {**update._BG, "state": "idle", "version": None, "url": None, "kind": None,
                                        "received": 0, "total": 0, "error": None, "path": None, "started": False,
                                        "launched": False})


def release(version, size=100):
    return {"tag_name": f"v{version}", "html_url": f"https://github.test/v{version}",
            "assets": [{"name": f"aion2calc-setup-{version}.exe", "browser_download_url": f"https://dl.test/{version}",
                        "size": size}]}


def staged(tmp_path, monkeypatch, *releases):
    """Releases GitHub names in turn; a fetch writes the setup file, reporting progress on the way."""
    queue = list(releases)
    monkeypatch.setattr(update, "install_kind", lambda: "installer")
    monkeypatch.setattr(update, "latest_release", lambda timeout=5: queue.pop(0) if len(queue) > 1 else queue[0])
    fetched = []

    def fetch(info, progress=None):
        fetched.append(info["version"])
        if progress:
            progress(40, 100)
            assert update.background_state()["state"] == "downloading"
            assert (update.background_state()["received"], update.background_state()["total"]) == (40, 100)
        path = tmp_path / info["asset"]["name"]
        path.write_bytes(b"setup")
        return path
    monkeypatch.setattr(update, "fetch", fetch)
    return fetched


def test_a_newer_release_downloads_with_its_progress_and_waits_ready(tmp_path, monkeypatch):
    fetched = staged(tmp_path, monkeypatch, release("99.0.0"))
    update._download_newest()
    state = update.background_state()
    assert state["state"] == "ready" and state["version"] == "99.0.0" and state["kind"] == "installer"
    assert "path" not in state                                     # the page is not told where the file is
    update._download_newest()                                      # the next look finds nothing newer
    assert fetched == ["99.0.0"]


def test_a_release_out_while_one_waits_downloads_and_the_newest_installs(tmp_path, monkeypatch):
    fetched = staged(tmp_path, monkeypatch, release("99.0.0"), release("99.1.0"))
    update._download_newest()
    update._download_newest()
    assert fetched == ["99.0.0", "99.1.0"] and update.background_state()["version"] == "99.1.0"
    assert update._BG["path"].endswith("aion2calc-setup-99.1.0.exe")


def test_github_out_of_reach_keeps_a_waiting_update(tmp_path, monkeypatch):
    staged(tmp_path, monkeypatch, release("99.0.0"))
    update._download_newest()
    monkeypatch.setattr(update, "latest_release", lambda timeout=5: None)
    update._download_newest()
    assert update.background_state()["state"] == "ready"
    update._BG.update(state="idle", path=None)
    update._download_newest()
    assert update.background_state()["state"] == "failed"         # tried again in a few minutes


def test_a_poke_wakes_the_download_only_for_a_newer_release(monkeypatch):
    update._BG.update(started=True, version="99.1.0")
    update._BG_WAKE.clear()
    update.poke("99.1.0")
    assert not update._BG_WAKE.is_set()
    update.poke("99.2.0")
    assert update._BG_WAKE.is_set()
    update._BG_WAKE.clear()


def test_closing_the_app_installs_the_waiting_update_quietly_unless_turned_off(tmp_path, monkeypatch):
    staged(tmp_path, monkeypatch, release("99.0.0"))
    update._download_newest()
    runs = []
    monkeypatch.setattr(update, "apply_installer", lambda path, silent=True, launch=True: runs.append((path.name, silent, launch)) or True)
    assert update.apply_on_close(False) is False and runs == []
    assert update.apply_on_close(True) is True
    assert runs == [("aion2calc-setup-99.0.0.exe", True, False)]   # silent, and the app does not start again
    assert update.apply_on_close(True) is False and len(runs) == 1  # once


def test_update_now_opens_the_staged_installer_and_closing_then_does_not_run_it_again(tmp_path, monkeypatch):
    staged(tmp_path, monkeypatch, release("99.0.0"))
    update._download_newest()
    runs = []
    monkeypatch.setattr(update, "apply_installer", lambda path, silent=True, launch=True: runs.append((path.name, silent, launch)) or True)
    monkeypatch.setattr(update, "install_now", lambda: pytest.fail("the staged installer is used"))
    assert update.install_ready() == "launching"
    assert runs == [("aion2calc-setup-99.0.0.exe", False, True)]   # with its own window, as the player asked
    assert update.apply_on_close(True) is False and len(runs) == 1


def test_update_now_without_a_staged_installer_downloads_the_newest_first(monkeypatch):
    monkeypatch.setattr(update, "install_now", lambda: "check-failed")
    assert update.install_ready() == "check-failed" and not update._BG["launched"]


def test_a_download_reports_its_progress(tmp_path, monkeypatch):
    body = b"x" * (600 * 1024)

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda req, timeout=0: Response(body))
    seen = []
    path = update.download("https://dl.test/x", tmp_path / "x.exe", progress=lambda got, total: seen.append((got, total)))
    assert path.read_bytes() == body and seen[-1] == (len(body), len(body)) and len(seen) == 3


def test_a_silent_install_on_close_asks_the_installer_not_to_start_the_app(monkeypatch, tmp_path):
    scripts = []

    def spawn(args, **kwargs):
        script = Path(args[-1])
        scripts.append(script.read_text(encoding="utf-8"))
        script.with_suffix(".ready").touch()
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(update.subprocess, "Popen", spawn)
    assert update.apply_installer(tmp_path / "setup.exe", silent=True, launch=False)
    assert "'/VERYSILENT'" in scripts[0] and "'/NOLAUNCH'" in scripts[0]
