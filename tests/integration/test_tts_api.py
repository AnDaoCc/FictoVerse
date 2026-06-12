from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from novel_world.bootstrap.app_context import create_app_context
from novel_world.infrastructure.user_preferences import save_user_prefs


@pytest.fixture
def tts_client(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    save_user_prefs(
        runtime.session.connection,
        {
            "tts_enabled": True,
            "tts_backend": "edge",
            "tts_voice": "zh-CN-XiaoxiaoNeural",
        },
    )
    runtime.commit()
    runtime.close()

    from novel_world.web import app as web_app

    web_app._CTX = ctx
    client = TestClient(web_app.app)
    yield client
    web_app._CTX = None


def test_tts_voices_endpoint(tts_client: TestClient) -> None:
    resp = tts_client.get("/api/tts/voices?backend=edge&locale=zh")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["voices"]) >= 1


@patch("novel_world.modules.ai.providers.tts_registry.build_tts_provider")
def test_tts_speak_endpoint(mock_build, tts_client: TestClient) -> None:
    mock_provider = mock_build.return_value
    mock_provider.synthesize.return_value = b"\xff\xfb"
    mock_provider.media_type.return_value = "audio/mpeg"
    resp = tts_client.post("/api/tts/speak", json={"text": "你好"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/mpeg")
    mock_provider.synthesize.assert_called_once()


def test_tts_voices_custom_http_backend(tts_client: TestClient) -> None:
    from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
    from novel_world.web import app as web_app

    ctx = web_app._CTX
    runtime = ctx.open()
    existing = get_user_prefs(runtime.session.connection)
    save_user_prefs(
        runtime.session.connection,
        {
            **existing,
            "tts_backend": "custom_http",
            "tts_custom": {
                "url": "http://127.0.0.1:7851/tts",
                "voices": [{"id": "v1", "name": "Voice 1"}],
            },
        },
    )
    runtime.commit()
    runtime.close()

    resp = tts_client.get("/api/tts/voices?backend=custom_http")
    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "custom_http"
    assert data["voices"][0]["id"] == "v1"
