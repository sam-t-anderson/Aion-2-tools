"""The operator self-check (doctor)."""


def test_checkup_is_offline_safe_and_covers_core(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc import ops
    report = ops.checkup(network=False)
    names = {c["name"] for c in report["checks"]}
    assert {"version", "updater", "path:home", "path:logs", "log-server", "catalog", "npc-art"} <= names
    # every check has a valid status and nothing raised
    assert all(c["status"] in ("ok", "warn", "unavailable") for c in report["checks"])
    # the fresh tmp home is writable, so the path checks pass
    assert all(c["status"] == "ok" for c in report["checks"] if c["name"].startswith("path:"))
    assert set(report["summary"]) == {"ok", "warn", "unavailable"}


def test_checkup_reports_missing_server_as_warning(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc import ops
    from aion2calc.combat import share
    monkeypatch.setattr(share, "default_server", lambda: {})
    report = ops.checkup(network=False)
    server = next(c for c in report["checks"] if c["name"] == "log-server")
    assert server["status"] == "warn" and "No log server" in server["detail"]
