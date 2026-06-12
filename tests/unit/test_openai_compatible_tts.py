from unittest.mock import MagicMock, patch

from novel_world.modules.ai.providers.openai_compatible_tts_provider import (
    OpenAICompatibleTTSProvider,
    parse_voices_json,
)


def test_parse_voices_json_array() -> None:
    voices = parse_voices_json('[{"id":"v1","name":"Voice 1"}]')
    assert voices == [{"id": "v1", "name": "Voice 1", "locale": "", "gender": ""}]


def test_list_voices_custom_json() -> None:
    provider = OpenAICompatibleTTSProvider(
        api_key="sk-test",
        voices_json='[{"id":"custom","name":"Custom"}]',
    )
    voices = provider.list_voices()
    assert voices[0]["id"] == "custom"


def test_list_voices_builtin_fallback() -> None:
    provider = OpenAICompatibleTTSProvider(api_key="sk-test")
    voices = provider.list_voices()
    assert any(v["id"] == "alloy" for v in voices)


@patch("novel_world.modules.ai.providers.openai_compatible_tts_provider.httpx.Client")
def test_synthesize_posts_audio_speech(mock_client_cls) -> None:
    mock_resp = MagicMock()
    mock_resp.content = b"\xff\xfb"
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    provider = OpenAICompatibleTTSProvider(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="tts-1-hd",
        voice="nova",
        auth_style="api-key",
    )
    audio = provider.synthesize("hello", voice="echo", rate=1.0)
    assert audio == b"\xff\xfb"

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "https://api.example.com/v1/audio/speech"
    assert kwargs["headers"] == {"api-key": "sk-test"}
    assert kwargs["json"]["model"] == "tts-1-hd"
    assert kwargs["json"]["voice"] == "echo"
    assert kwargs["json"]["input"] == "hello"
