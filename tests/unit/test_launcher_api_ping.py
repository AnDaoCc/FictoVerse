from __future__ import annotations

from novel_world.launcher.api import LauncherApi


def test_launcher_api_ping() -> None:
    api = LauncherApi()
    assert api.ping() == {"ok": True}
