import base64
from unittest.mock import MagicMock, patch

import httpx

from novel_world.modules.ai.providers.custom_http_tts_provider import (
    CustomHttpTTSProvider,
    apply_body_template,
    normalize_custom_config,
)


def test_apply_body_template_placeholders() -> None:
    body = apply_body_template(
        '{"text":"{{text}}","voice":"{{voice}}","speed":{{rate}}}',
        text='你好 "世界"',
        voice="speaker1",
        rate=1.2,
    )
    assert '"你好 \\"世界\\""' in body or "你好" in body
    assert "speaker1" in body
    assert "1.2" in body


def test_list_voices_static() -> None:
    provider = CustomHttpTTSProvider(
        {
            "url": "http://127.0.0.1:7851/tts",
            "voices": [{"id": "alice", "name": "Alice"}],
        }
    )
    voices = provider.list_voices()
    assert voices == [{"id": "alice", "name": "Alice", "locale": "", "gender": ""}]


def test_list_voices_default_without_config() -> None:
    provider = CustomHttpTTSProvider({"url": "http://127.0.0.1/tts"})
    voices = provider.list_voices()
    assert voices[0]["id"] == "default"


@patch("novel_world.modules.ai.providers.custom_http_tts_provider.httpx.Client")
def test_synthesize_binary_response(mock_client_cls) -> None:
    mock_resp = MagicMock()
    mock_resp.content = b"\xff\xfb"
    mock_resp.headers = {"content-type": "audio/mpeg"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    provider = CustomHttpTTSProvider(
        {
            "url": "http://127.0.0.1:7851/tts",
            "body_template": '{"text":"{{text}}","voice":"{{voice}}"}',
            "response_mode": "binary",
        }
    )
    audio = provider.synthesize("hello", voice="v1")
    assert audio == b"\xff\xfb"
    mock_client.request.assert_called_once()


@patch("novel_world.modules.ai.providers.custom_http_tts_provider.httpx.Client")
def test_synthesize_json_base64(mock_client_cls) -> None:
    payload = base64.b64encode(b"audio-bytes").decode()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"audio": payload}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.request.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    provider = CustomHttpTTSProvider(
        {
            "url": "http://127.0.0.1/tts",
            "response_mode": "json_base64",
            "response_json_path": "data.audio",
        }
    )
    audio = provider.synthesize("hi")
    assert audio == b"audio-bytes"


def test_normalize_custom_config_defaults() -> None:
    cfg = normalize_custom_config(None)
    assert cfg["method"] == "POST"
    assert cfg["response_mode"] == "binary"
