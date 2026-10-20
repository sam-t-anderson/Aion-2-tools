"""Automated logs-folder cleanup: keep the combat-logs folder under a user cap
(default 1 GB) by deleting the oldest recordings first, never the active one."""
import json
import os

import pytest

from aion2calc.app import server, settings_backup
from aion2calc.combat import sessions
from aion2calc.paths import logs_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def _write(name: str, size: int, mtime: float):
    p = logs_dir() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    os.utime(p, (mtime, mtime))
    return p


def test_default_cap_is_one_gigabyte(home):
    assert server.ui_settings()["meter_log_cache_mb"] == 1024


def test_cap_rides_the_settings_backup(home):
    assert settings_backup.import_settings({"meter_log_cache_mb": 512})["settings"]["meter_log_cache_mb"] == 512
    assert settings_backup.import_settings({"meter_log_cache_mb": 0})["settings"]["meter_log_cache_mb"] == 0
    with pytest.raises(ValueError):
        settings_backup.import_settings({"meter_log_cache_mb": -1})


def test_prune_deletes_oldest_first_until_under_cap(home):
    a = _write("session-a.a2log.json", 400, mtime=1000)   # oldest
    b = _write("session-b.a2log.json", 400, mtime=2000)
    c = _write("session-c.a2log.json", 400, mtime=3000)   # newest
    result = sessions.prune_logs(900)                      # cap fits one file + part of another → keep newest two
    assert not a.exists()                                  # oldest removed
    assert b.exists() and c.exists()                       # newer kept
    assert result["removed"] == 1
    assert result["total_bytes"] == 800


def test_prune_never_removes_the_active_file(home):
    old = _write("session-old.a2log.json", 800, mtime=1000)
    active = _write("session-active.a2log.json", 800, mtime=2000)
    # Cap below both; the active file is protected even though removing it is needed to fit.
    result = sessions.prune_logs(500, keep={"session-active.a2log.json"})
    assert not old.exists()
    assert active.exists()
    assert result["removed"] == 1


def test_zero_cap_disables_pruning(home):
    f = _write("session-x.a2log.json", 5000, mtime=1000)
    result = sessions.prune_logs(0)
    assert f.exists()
    assert result["removed"] == 0


# --- Upload a recording before the size cap reclaims it (meter_upload_before_prune) ---

def test_upload_before_prune_default_on(home):
    assert server.ui_settings()["meter_upload_before_prune"] is True


def test_prune_evicts_doomed_files_but_never_the_kept_one(home):
    a = _write("session-a.a2log.json", 400, mtime=1000)   # oldest -> deleted
    _write("session-b.a2log.json", 400, mtime=2000)       # deleted
    active = _write("session-active.a2log.json", 400, mtime=3000)
    evicted = []
    result = sessions.prune_logs(500, keep={"session-active.a2log.json"},
                                 evict=lambda p: (evicted.append(p.name) or True))
    assert "session-a.a2log.json" in evicted              # uploaded before deletion
    assert "session-active.a2log.json" not in evicted     # the active file is never swept or uploaded
    assert not a.exists() and active.exists()
    assert result["evicted"] == 2 and result["removed"] == 2


def test_prune_still_deletes_when_the_upload_hook_fails(home):
    a = _write("session-a.a2log.json", 800, mtime=1000)
    b = _write("session-b.a2log.json", 800, mtime=2000)

    def boom(_p):
        raise RuntimeError("upload failed")

    result = sessions.prune_logs(900, evict=boom)
    assert not a.exists() and b.exists()                  # the cap is honoured despite the failure
    assert result["removed"] == 1 and result["evicted"] == 0


def test_upload_evictor_is_off_without_the_setting_or_a_server(home, monkeypatch):
    from aion2calc.app import meter_runner
    from aion2calc.combat import share
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.example.com"})
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_upload_before_prune": False})
    assert meter_runner.upload_evictor() is None          # feature turned off
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_upload_before_prune": True})
    monkeypatch.setattr(share, "effective", lambda: {})
    assert meter_runner.upload_evictor() is None          # no share server configured


def test_upload_evictor_uploads_the_recording_before_delete(home, monkeypatch):
    from aion2calc.app import meter_runner
    from aion2calc.combat import share
    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_upload_before_prune": True})
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.example.com"})
    uploaded = []
    monkeypatch.setattr(share, "upload", lambda doc, **kw: (uploaded.append((doc, kw)) or {"id": "abc123"}))
    evict = meter_runner.upload_evictor()
    assert evict is not None
    f = _write("session-x.a2log.json", 0, mtime=1000)
    f.write_text(json.dumps({"meta": {}, "players": [], "segments": []}), encoding="utf-8")
    assert evict(f) is True
    assert len(uploaded) == 1
    doc, kw = uploaded[0]
    assert doc["segments"] == [] and kw.get("visibility") is None     # the visibility set for uploads
