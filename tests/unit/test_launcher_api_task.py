from __future__ import annotations

import time

from novel_world.launcher.api import LauncherApi


def test_get_task_status_idle() -> None:
    api = LauncherApi()
    task = api.get_task_status()
    assert task["running"] is False
    assert task["ok"] is None


def test_launch_async_rejects_when_busy(monkeypatch) -> None:
    api = LauncherApi()
    api._set_task(running=True, kind="launch", label="busy")

    result = api.launch_async(True)
    assert result["ok"] is False
    assert result["started"] is False
    assert "进行中" in result["message"]


def test_check_prerequisites_async_completes(monkeypatch) -> None:
    from novel_world.launcher import bootstrap

    monkeypatch.setattr(
        bootstrap,
        "check_prerequisites",
        lambda: {
            "python_ok": True,
            "ready": True,
            "venv_exists": True,
            "deps_need_install": False,
        },
    )

    api = LauncherApi()
    started = api.check_prerequisites_async()
    assert started["ok"] is True
    assert started["started"] is True

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        task = api.get_task_status()
        if not task["running"]:
            break
        time.sleep(0.05)

    task = api.get_task_status()
    assert task["running"] is False
    assert task["ok"] is True
    assert task["prerequisites"]["ready"] is True
